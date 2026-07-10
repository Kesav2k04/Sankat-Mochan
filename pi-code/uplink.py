"""
Durable edge-link client: Pi LoRa gateway → AI-PC command post (EDGE-LINK.md).

Bidirectional, lossless, venue-independent:
  - a persistent WebSocket to ws://<mac>:9000/gateway,
  - a SQLite **durable outbox** — an envelope is deleted only after the Mac ACKs it
    by id, so a link blip / Mac reload / Pi restart never loses an SOS,
  - priority flush on reconnect (criticals first),
  - auto-reconnect with backoff + a best-effort HTTP-POST /sos fallback while the
    socket is down,
  - a downlink handler for dispatches (ACCEPTED / instructions) the Mac sends back —
    the return path to the victim.

Wire into gateway.py: replace the fire-and-forget `_make_uplink` with an EdgeUplink;
call `uplink.send_envelope(msg.to_dict())` from the gateway node's on_accept hook, and
give it an `on_dispatch` that injects the returned envelope into the mesh (LoRa/BLE →
victim phone).

Deps: `websockets` (pip). sqlite3 + json are stdlib.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None


class DurableOutbox:
    """SQLite-backed queue of envelopes awaiting Mac ACK. Survives process restart.
    Keyed by type:id so re-enqueuing the same envelope is idempotent."""

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS outbox "
            "(mid TEXT PRIMARY KEY, urgency INTEGER, env TEXT, ts REAL)"
        )
        self.db.commit()

    def enqueue(self, env: dict[str, Any]) -> str:
        mid = f"{env.get('t','SOS')}:{env.get('i','')}"
        self.db.execute(
            "INSERT OR REPLACE INTO outbox(mid, urgency, env, ts) VALUES (?,?,?,?)",
            (mid, int(env.get("u", 3)), json.dumps(env, ensure_ascii=False), time.time()),
        )
        self.db.commit()
        return mid

    def pending(self) -> list[tuple[str, dict[str, Any]]]:
        rows = self.db.execute(
            "SELECT mid, env FROM outbox ORDER BY urgency DESC, ts ASC"
        ).fetchall()
        return [(mid, json.loads(env)) for mid, env in rows]

    def ack(self, mid: str) -> None:
        self.db.execute("DELETE FROM outbox WHERE mid=?", (mid,))
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]


class EdgeUplink:
    def __init__(
        self,
        ws_url: str,
        http_url: str | None,
        outbox_path: str | Path,
        on_dispatch: Callable[[dict[str, Any]], Awaitable[None] | None],
        logger,
    ) -> None:
        self.ws_url = ws_url
        self.http_url = http_url  # e.g. http://<mac>:9000/sos — fallback only
        self.outbox = DurableOutbox(outbox_path)
        self.on_dispatch = on_dispatch
        self.log = logger
        self._wake = asyncio.Event()
        self._ws = None

    # ---- public API (called by gateway.py) ----
    def send_envelope(self, env: dict[str, Any]) -> None:
        """Enqueue durably and nudge the sender. Never blocks, never loses."""
        self.outbox.enqueue(env)
        self._wake.set()

    def connected(self) -> bool:
        return self._ws is not None

    # ---- run loop ----
    async def run(self, stop: asyncio.Event) -> None:
        if websockets is None:
            self.log.error("`websockets` not installed — uplink cannot start "
                           "(pip install websockets). Falling back to HTTP only.")
            await self._http_only(stop)
            return
        backoff = 1.0
        while not stop.is_set():
            try:
                async with websockets.connect(self.ws_url, open_timeout=8, ping_interval=15) as ws:
                    self._ws = ws
                    self.log.info("edge uplink connected: %s", self.ws_url)
                    backoff = 1.0
                    await self._flush(ws)  # replay everything the Mac missed
                    reader = asyncio.create_task(self._reader(ws))
                    sender = asyncio.create_task(self._sender(ws, stop))
                    stopper = asyncio.create_task(stop.wait())
                    done, pend = await asyncio.wait(
                        [reader, sender, stopper], return_when=asyncio.FIRST_COMPLETED)
                    for t in pend:
                        t.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await t
            except Exception as e:
                # This is a local operator log, not dashboard output (rule 10). Include
                # the endpoint and OS error so firewall, refused-port and no-route
                # failures can be distinguished on the Pi without a Python traceback.
                self.log.warning("edge uplink down: %s (%s: %s); %d queued; retrying in %.0fs",
                                 self.ws_url, type(e).__name__, e,
                                 self.outbox.count(), backoff)
                await self._http_fallback()  # best-effort while the socket is dead
            finally:
                self._ws = None
            if stop.is_set():
                break
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            backoff = min(backoff * 2, 30.0)

    async def _flush(self, ws) -> None:
        for mid_key, env in self.outbox.pending():
            await ws.send(json.dumps({"type": "envelope", "id": mid_key, "env": env}))

    async def _sender(self, ws, stop: asyncio.Event) -> None:
        """Send newly-enqueued envelopes as they arrive (woken by send_envelope)."""
        while not stop.is_set():
            await self._wake.wait()
            self._wake.clear()
            await self._flush(ws)

    async def _reader(self, ws) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            kind = msg.get("type")
            if kind == "ack":
                self.outbox.ack(msg.get("id", ""))
            elif kind == "dispatch":
                env = msg.get("env", {})
                res = self.on_dispatch(env)
                if asyncio.iscoroutine(res):
                    await res
                if msg.get("id"):  # confirm downlink so the Mac clears its buffer
                    await ws.send(json.dumps({"type": "ack", "id": msg["id"]}))

    async def _http_fallback(self) -> None:
        """When the socket is down, best-effort POST pending SOS to /sos so up-traffic
        still flows. The Mac dedups by id, so this is safe alongside the WS replay."""
        if not self.http_url:
            return
        import requests
        for _mid, env in self.outbox.pending():
            if env.get("t") != "SOS":
                continue
            try:
                requests.post(self.http_url, json=env, timeout=4)
                # NOTE: we do NOT ack here — the WS ACK is the source of truth so the
                # envelope stays queued until confirmed, avoiding loss if the POST lied.
            except Exception:
                break  # link still down; stop hammering

    async def _http_only(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._http_fallback()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=3.0)
