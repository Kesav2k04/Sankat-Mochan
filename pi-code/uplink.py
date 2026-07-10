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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse, urlunparse

import envelope as envmod

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


@dataclass(frozen=True)
class CompletedVoice:
    clip_id: str
    ref_id: str
    origin: str
    codec: int
    audio: bytes


@dataclass(frozen=True)
class AcceptOutcome:
    """What accepting one chunk did — enough for send_voice_chunk to narrate it."""
    complete: CompletedVoice | None
    started_clip: bool      # this chunk opened a brand-new clip
    filled_gap: bool        # it filled an index that was still missing
    is_repair: bool         # it was a retransmission (attempt > 0)
    remaining: int          # missing pieces still outstanding (0 once complete)


@dataclass(frozen=True)
class AbandonedVoice:
    clip_id: str
    missing: int
    requests: int


class VoiceAssembler:
    """Bounded, validated reassembly of out-of-order/retried voice chunks, with the
    receiver half of the NACK repair loop the phones already speak.

    Threading: every method mutates ``_clips`` and must run on the gateway's single
    event-loop thread only. ``accept`` is driven off LoRa/BLE RX (both marshalled onto
    the loop) and ``due_for_nack`` off the sweeper task — no two touch ``_clips`` at
    once, so no lock is needed. Do not call these from a bare radio-RX thread.
    """

    MAX_IN_FLIGHT = 8

    def __init__(self) -> None:
        self._clips: dict[str, dict[str, Any]] = {}

    def count(self) -> int:
        return len(self._clips)

    def accept(self, chunk: envmod.VoiceChunk) -> AcceptOutcome:
        started = False
        state = self._clips.get(chunk.clip_id)
        if state is None:
            if len(self._clips) >= self.MAX_IN_FLIGHT:
                oldest = min(self._clips, key=lambda k: self._clips[k]["started"])
                del self._clips[oldest]
            now = time.monotonic()
            state = {
                "origin": chunk.origin, "seq": chunk.seq,
                "total": chunk.total, "codec": chunk.codec,
                "parts": [None] * chunk.total,
                "started": now, "last_seen": now, "nack_attempts": 0,
            }
            self._clips[chunk.clip_id] = state
            started = True
        # A frame whose shape disagrees with the clip we are holding is corruption or a
        # stray (untrusted input, CLAUDE.md #8): drop the frame, keep the good clip.
        if state["total"] != chunk.total or state["codec"] != chunk.codec:
            return AcceptOutcome(None, started, False, chunk.attempt > 0,
                                 sum(1 for p in state["parts"] if p is None))
        filled_gap = state["parts"][chunk.index] is None
        state["parts"][chunk.index] = chunk.payload
        state["last_seen"] = time.monotonic()
        remaining = sum(1 for p in state["parts"] if p is None)
        if remaining:
            return AcceptOutcome(None, started, filled_gap, chunk.attempt > 0, remaining)
        audio = b"".join(state["parts"])
        del self._clips[chunk.clip_id]
        complete = CompletedVoice(
            clip_id=chunk.clip_id,
            ref_id=f"{chunk.origin}-{chunk.seq}",
            origin=chunk.origin,
            codec=chunk.codec,
            audio=audio,
        )
        return AcceptOutcome(complete, started, filled_gap, chunk.attempt > 0, 0)

    def due_for_nack(self, quiet_s: float, requester_origin: str
                     ) -> tuple[list[envmod.VoiceNack], list[AbandonedVoice]]:
        """Clips that have gone quiet with pieces still missing. For each, either emit a
        resend-request (mirrors the phone's scheduleNack) or, once the attempt budget is
        spent, abandon it so the dashboard stops showing it stuck forever."""
        now = time.monotonic()
        nacks: list[envmod.VoiceNack] = []
        abandoned: list[AbandonedVoice] = []
        for clip_id, state in list(self._clips.items()):
            if now - state["last_seen"] < quiet_s:
                continue
            missing = tuple(i for i, p in enumerate(state["parts"]) if p is None)
            if not missing:
                continue
            attempt = state["nack_attempts"]
            if attempt >= envmod.MAX_ATTEMPTS - 1:
                del self._clips[clip_id]
                abandoned.append(AbandonedVoice(clip_id, len(missing), attempt))
                continue
            nacks.append(envmod.VoiceNack(
                origin=requester_origin, clip_origin=state["origin"],
                seq=state["seq"], total=state["total"], missing=missing,
                attempt=attempt,
            ))
            state["nack_attempts"] = attempt + 1
            state["last_seen"] = now   # wait another quiet period before asking again
        return nacks, abandoned


class VoiceUploadOutbox:
    """Small durable file outbox. A clip is deleted only after HTTP 2xx."""

    def __init__(self, db_path: str | Path) -> None:
        db_path = Path(db_path)
        self.root = db_path.parent / f"{db_path.stem}_voice"
        self.root.mkdir(parents=True, exist_ok=True)

    def enqueue(self, clip: CompletedVoice, context: dict[str, Any] | None = None) -> None:
        extension = ".3gp" if clip.codec == 2 else ".ogg"
        audio_name = clip.clip_id + extension
        meta = {
            "clip_id": clip.clip_id, "ref_id": clip.ref_id,
            "origin": clip.origin, "codec": clip.codec,
            "audio_name": audio_name,
            "lang": (context or {}).get("ln", ""),
        }
        audio_tmp = self.root / f".{audio_name}.tmp"
        meta_tmp = self.root / f".{clip.clip_id}.json.tmp"
        audio_tmp.write_bytes(clip.audio)
        meta_tmp.write_text(json.dumps(meta, separators=(",", ":")))
        audio_tmp.replace(self.root / audio_name)
        meta_tmp.replace(self.root / f"{clip.clip_id}.json")

    def pending(self) -> list[tuple[Path, dict[str, Any], bytes]]:
        result = []
        for meta_path in sorted(self.root.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text())
                audio_path = self.root / str(meta["audio_name"])
                audio = audio_path.read_bytes()
                if not audio or len(audio) > 110_000:
                    continue
                result.append((meta_path, meta, audio))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return result

    def ack(self, meta_path: Path, meta: dict[str, Any]) -> None:
        with contextlib.suppress(OSError):
            (self.root / str(meta["audio_name"])).unlink()
        with contextlib.suppress(OSError):
            meta_path.unlink()

    def count(self) -> int:
        return len(list(self.root.glob("*.json")))


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
        self.voice_outbox = VoiceUploadOutbox(outbox_path)
        self.voice_assembler = VoiceAssembler()
        self.on_dispatch = on_dispatch
        self.log = logger
        self._wake = asyncio.Event()
        self._ws = None
        self._sos_context: dict[str, dict[str, Any]] = {}
        self._peer_states: dict[str, dict[str, Any]] = {}
        self._voice_flush_lock = asyncio.Lock()

        if http_url:
            parsed = urlparse(http_url)
            self.voice_url = urlunparse((parsed.scheme, parsed.netloc, "/mesh_voice", "", "", ""))
        else:
            self.voice_url = None

    # ---- public API (called by gateway.py) ----
    def send_envelope(self, env: dict[str, Any]) -> None:
        """Enqueue durably and nudge the sender. Never blocks, never loses."""
        if env.get("t") == "SOS" and env.get("o"):
            self._sos_context[str(env["o"])] = dict(env)
            if len(self._sos_context) > 64:
                del self._sos_context[next(iter(self._sos_context))]
        self.outbox.enqueue(env)
        self._wake.set()

    def send_voice_chunk(self, chunk: envmod.VoiceChunk) -> None:
        """Reassemble and durably queue a complete clip for the command post."""
        outcome = self.voice_assembler.accept(chunk)
        self._wake.set()  # publish in-flight progress even before the clip completes
        if outcome.started_clip:
            self.log.info("voice %s incoming from phone %s (%d pieces)",
                          chunk.clip_id, chunk.origin, chunk.total)
        elif outcome.is_repair and outcome.filled_gap:
            self.log.info("voice %s repaired piece %d (%d still missing)",
                          chunk.clip_id, chunk.index, outcome.remaining)
        complete = outcome.complete
        if complete is None:
            return
        # The working mobile protocol sends the text SOS immediately before its voice
        # chunks. Correlate to the latest SOS from that origin without changing a byte
        # of the phone wire format.
        context = self._sos_context.get(complete.origin)
        if context and context.get("i"):
            complete = CompletedVoice(
                clip_id=complete.clip_id,
                ref_id=str(context["i"]),
                origin=complete.origin,
                codec=complete.codec,
                audio=complete.audio,
            )
        self.voice_outbox.enqueue(complete, context)
        self.log.info("voice %s complete (%d bytes) — queued for AI PC",
                      complete.clip_id, len(complete.audio))
        self._wake.set()

    def collect_voice_repairs(self, requester_origin: str, quiet_s: float
                              ) -> tuple[list[envmod.VoiceNack], list[AbandonedVoice]]:
        """Drive the assembler's repair timer. The caller injects the returned NACKs into
        the mesh (gateway node) so the victim phone resends the pieces we never got."""
        nacks, abandoned = self.voice_assembler.due_for_nack(quiet_s, requester_origin)
        if abandoned:
            self._wake.set()  # a dropped clip changes voice_inflight — refresh the dashboard
        return nacks, abandoned

    def connected(self) -> bool:
        return self._ws is not None

    def set_peer_state(self, node_id: str, role: str, connected: bool) -> None:
        """Publish the Pi's real subscribed BLE state, not mere scan visibility."""
        if not node_id.isalnum() or len(node_id) > 8 or role not in {"responder"}:
            return
        self._peer_states[node_id] = {
            "type": "peer", "node_id": node_id,
            "role": role, "connected": bool(connected),
        }
        self._wake.set()

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
                    await self._flush_voices()
                    await self._flush_peer_states(ws)
                    await self._flush_status(ws)
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
            await self._flush_voices()
            await self._flush_peer_states(ws)
            await self._flush_status(ws)

    async def _flush_peer_states(self, ws) -> None:
        for state in self._peer_states.values():
            await ws.send(json.dumps(state))

    async def _flush_status(self, ws) -> None:
        await ws.send(json.dumps({
            "type": "status",
            "voice_inflight": self.voice_assembler.count(),
            "voice_queued": self.voice_outbox.count(),
        }))

    async def _flush_voices(self) -> None:
        if not self.voice_url:
            return
        async with self._voice_flush_lock:
            for meta_path, meta, audio in self.voice_outbox.pending():
                ok = await asyncio.to_thread(self._post_voice, meta, audio)
                if not ok:
                    return
                self.voice_outbox.ack(meta_path, meta)
                self.log.info("voice %s uploaded to AI PC", meta.get("clip_id", "?"))

    def _post_voice(self, meta: dict[str, Any], audio: bytes) -> bool:
        import requests
        content_type = "audio/3gpp" if meta.get("codec") == 2 else "audio/ogg"
        try:
            session = requests.Session()
            session.trust_env = False  # a LAN command post must never go via a proxy
            response = session.post(
                self.voice_url,
                data={k: str(meta.get(k, "")) for k in
                      ("clip_id", "ref_id", "origin", "codec", "lang")},
                files={"audio": (meta["audio_name"], audio, content_type)},
                timeout=120,
            )
            if 200 <= response.status_code < 300:
                return True
            self.log.warning("voice upload returned HTTP %d; clip remains queued",
                             response.status_code)
            return False
        except Exception as exc:
            self.log.warning("voice upload down (%s: %s); clip remains queued",
                             type(exc).__name__, exc)
            return False

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
