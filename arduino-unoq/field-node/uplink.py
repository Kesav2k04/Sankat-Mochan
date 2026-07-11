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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse, urlunparse

try:
    import requests
except Exception:  # pragma: no cover - only needed when an uplink URL is configured
    requests = None

import envelope as envmod

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None


# An urgency-5 SOS is always accepted, even past the cap; only lower-urgency traffic is
# refused when the outbox is full (mesh-transmission.md D4 — never drop an accepted one).
CRITICAL_URGENCY = 5


class OutboxFull(RuntimeError):
    """Raised when a NEW low-urgency envelope is refused because the durable outbox is at
    its cap. An already-accepted envelope is never dropped; instead we push back at intake
    and let the operator see the alarm. Re-enqueuing an id already in the outbox is still
    allowed (it is an idempotent update, not new growth)."""


class DurableOutbox:
    """SQLite-backed queue of envelopes awaiting Mac ACK. Survives process restart.
    Keyed by type:id so re-enqueuing the same envelope is idempotent."""

    def __init__(self, path: str | Path, max_rows: int | None = None) -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS outbox "
            "(mid TEXT PRIMARY KEY, urgency INTEGER, env TEXT, ts REAL)"
        )
        self.db.commit()
        self.max_rows = max_rows

    def _mid(self, env: dict[str, Any]) -> str:
        return f"{env.get('t','SOS')}:{env.get('i','')}"

    def enqueue(self, env: dict[str, Any]) -> str:
        mid = self._mid(env)
        urgency = int(env.get("u", 3))
        # Cap is a backstop against a flood of forged ids filling the SD card. We only
        # refuse *new* low-urgency rows; an urgency-5 SOS and an idempotent re-enqueue of an
        # id already present are always allowed, so no accepted envelope is ever lost.
        if self.max_rows is not None and urgency < CRITICAL_URGENCY:
            already = self.db.execute(
                "SELECT 1 FROM outbox WHERE mid=?", (mid,)
            ).fetchone()
            if already is None and self.count() >= self.max_rows:
                raise OutboxFull(mid)
        self.db.execute(
            "INSERT OR REPLACE INTO outbox(mid, urgency, env, ts) VALUES (?,?,?,?)",
            (mid, urgency, json.dumps(env, ensure_ascii=False), time.time()),
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
        self._sweep_orphans()

    def _sweep_orphans(self) -> None:
        """A crash between enqueue's two atomic renames can leave a half-written pair:
        a `.tmp` that never got promoted, or an audio/meta whose sibling is missing.
        `pending()` globs `*.json`, so an orphan audio is invisible but never reclaimed — a
        slow disk leak. Reclaim `.tmp`s and any file whose partner is gone, on startup."""
        for tmp in self.root.glob(".*.tmp"):
            with contextlib.suppress(OSError):
                tmp.unlink()

        # Audio files a live meta still points at; everything else is an orphan.
        wanted: set[str] = set()
        for meta_path in self.root.glob("*.json"):
            try:
                audio_name = str(json.loads(meta_path.read_text())["audio_name"])
            except (OSError, ValueError, KeyError, TypeError):
                with contextlib.suppress(OSError):   # unreadable meta is dead weight
                    meta_path.unlink()
                continue
            if (self.root / audio_name).exists():
                wanted.add(audio_name)
            else:
                with contextlib.suppress(OSError):   # meta whose audio vanished
                    meta_path.unlink()

        for entry in self.root.iterdir():
            if entry.name.startswith(".") or entry.suffix == ".json":
                continue
            if entry.name not in wanted:
                with contextlib.suppress(OSError):
                    entry.unlink()

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
        *,
        outbox_max: int | None = None,
        voice_concurrency: int = 2,
        voice_connect_s: float = 5.0,
        voice_read_s: float = 30.0,
    ) -> None:
        self.ws_url = ws_url
        self.http_url = http_url  # e.g. http://<mac>:9000/sos — fallback only
        self.outbox = DurableOutbox(outbox_path, max_rows=outbox_max)
        self.voice_outbox = VoiceUploadOutbox(outbox_path)
        self.voice_assembler = VoiceAssembler()
        self.on_dispatch = on_dispatch
        self.log = logger
        self._wake = asyncio.Event()          # WS path: envelopes / peers / status
        self._voice_wake = asyncio.Event()    # voice upload path — decoupled from the WS
        self._ws = None
        self._sos_context: dict[str, dict[str, Any]] = {}
        self._peer_states: dict[str, dict[str, Any]] = {}
        self.outbox_alarm = False             # surfaced on the status frame for the operator
        # Optional provider of extra status fields (e.g. the gateway node's critical-intake
        # alarm) merged into every status frame. Set by the gateway after node creation.
        self.status_extra: Callable[[], dict[str, Any]] | None = None

        # Cross-owner contract (mesh-transmission.md C4b): voice HTTP posts run on their OWN
        # bounded pool so the DEFAULT executor stays reserved for radio TX
        # (LoRaLink.send -> run_in_executor(None,...)). Widening this pool back toward the
        # default one would re-introduce the SOS-vs-voice thread starvation C1 removed.
        self._voice_concurrency = max(1, int(voice_concurrency))
        self._voice_pool = ThreadPoolExecutor(
            max_workers=self._voice_concurrency, thread_name_prefix="voice-upload")
        self._voice_sema = asyncio.Semaphore(self._voice_concurrency)
        self._voice_timeout = (float(voice_connect_s), float(voice_read_s))
        # One reused session (keep-alive) instead of one per POST; never via a proxy.
        self._session = None
        if requests is not None:
            self._session = requests.Session()
            self._session.trust_env = False

        # Liveness heartbeats (A7): each long-lived loop stamps monotonic progress; the
        # gateway watchdog reads these and logs (does not auto-restart) a stalled loop.
        self._heartbeat: dict[str, float] = {}

        if http_url:
            parsed = urlparse(http_url)
            self.voice_url = urlunparse((parsed.scheme, parsed.netloc, "/mesh_voice", "", "", ""))
        else:
            self.voice_url = None

    def _beat(self, who: str) -> None:
        self._heartbeat[who] = time.monotonic()

    def stalled_loops(self, max_age_s: float) -> list[tuple[str, float]]:
        """Loops whose last progress stamp is older than max_age_s (for the watchdog)."""
        now = time.monotonic()
        return [(w, now - t) for w, t in self._heartbeat.items() if now - t > max_age_s]

    def close(self) -> None:
        self._voice_pool.shutdown(wait=False, cancel_futures=True)
        if self._session is not None:
            with contextlib.suppress(Exception):
                self._session.close()

    # ---- public API (called by gateway.py) ----
    def send_envelope(self, env: dict[str, Any]) -> None:
        """Enqueue durably and nudge the sender. Never blocks; never loses an ACCEPTED
        envelope. A NEW low-urgency envelope may be refused (and alarmed) if the outbox is
        capped and full — urgency-5 is always accepted (mesh-transmission.md D4)."""
        if env.get("t") == "SOS" and env.get("o"):
            self._sos_context[str(env["o"])] = dict(env)
            if len(self._sos_context) > 64:
                del self._sos_context[next(iter(self._sos_context))]
        try:
            self.outbox.enqueue(env)
        except OutboxFull:
            # Rule 10: no stack trace on the dashboard — a loud local log + an alarm flag
            # the operator sees on the status frame. The accepted backlog is untouched.
            self.outbox_alarm = True
            self.log.error(
                "OUTBOX FULL — refused a new urgency-%s %s from %s; the durable SOS queue "
                "is at its cap (%s). Accepted messages are safe and still being delivered; "
                "this rejects only NEW low-urgency traffic. Check the link to the AI PC.",
                env.get("u", "?"), env.get("t", "?"), env.get("o", "?"),
                self.outbox.max_rows)
            self._wake.set()   # push the alarm to the dashboard promptly
            return
        self.outbox_alarm = False
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
        self._voice_wake.set()   # wake the voice uploader; NOT the SOS/WS sender
        self._wake.set()         # refresh voice_queued on the status frame

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
                async with websockets.connect(
                    self.ws_url, open_timeout=8, ping_interval=15, ping_timeout=10
                ) as ws:
                    self._ws = ws
                    self.log.info("edge uplink connected: %s", self.ws_url)
                    backoff = 1.0
                    await self._flush(ws)  # replay everything the Mac missed
                    self._voice_wake.set()  # drain any voice that queued while offline
                    await self._flush_peer_states(ws)
                    await self._flush_status(ws)
                    reader = asyncio.create_task(self._reader(ws))
                    sender = asyncio.create_task(self._sender(ws, stop))
                    # Voice upload is decoupled from the WS sender (mesh-transmission.md C1):
                    # a slow/large clip can never delay an SOS envelope again. It is gated on
                    # the WS being up (C7) — if the AI PC is unreachable, HTTP voice fails too.
                    uploader = asyncio.create_task(self._voice_uploader(stop))
                    stopper = asyncio.create_task(stop.wait())
                    done, pend = await asyncio.wait(
                        [reader, sender, uploader, stopper],
                        return_when=asyncio.FIRST_COMPLETED)
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
        """WS path ONLY: envelopes (SOS-first), peer states, status. Voice upload lives in
        its own task (_voice_uploader) so a slow HTTP clip can never stall this loop —
        mesh-transmission.md C1/B1. No voice work here by design."""
        self._beat("sender")
        while not stop.is_set():
            await self._wake.wait()
            self._wake.clear()
            await self._flush(ws)
            await self._flush_peer_states(ws)
            await self._flush_status(ws)
            self._beat("sender")

    async def _voice_uploader(self, stop: asyncio.Event) -> None:
        """The SINGLE consumer of the voice outbox. Being the only caller of _flush_voices,
        it needs no lock and no in-flight set (B1): nothing else ever posts a clip. Within a
        drain pass it uploads up to voice_concurrency clips at once (C2) on the dedicated
        voice pool (C4b), so many victims' clips move in parallel without touching the SOS
        path or the radio thread pool."""
        self._beat("uploader")
        while not stop.is_set():
            await self._voice_wake.wait()
            self._voice_wake.clear()
            await self._flush_voices()
            self._beat("uploader")

    async def _flush_peer_states(self, ws) -> None:
        for state in self._peer_states.values():
            await ws.send(json.dumps(state))

    async def _flush_status(self, ws) -> None:
        status = {
            "type": "status",
            "voice_inflight": self.voice_assembler.count(),
            "voice_queued": self.voice_outbox.count(),
            "outbox_alarm": self.outbox_alarm,
        }
        if self.status_extra is not None:
            try:
                status.update(self.status_extra() or {})
            except Exception:
                pass  # a status-provider glitch must never break the status frame
        await ws.send(json.dumps(status))

    async def _flush_voices(self) -> None:
        """Drain the voice outbox, uploading up to voice_concurrency clips concurrently.
        Called only by the single _voice_uploader task, so it is inherently re-entrancy-free.
        Each clip is acked independently on its own 2xx; a failed clip stays queued and is
        retried next pass (durability unchanged)."""
        if not self.voice_url or self._session is None:
            return
        loop = asyncio.get_running_loop()

        async def _one(meta_path: Path, meta: dict[str, Any], audio: bytes) -> None:
            async with self._voice_sema:
                # Dedicated voice pool — NOT the default executor (reserved for radio TX).
                ok = await loop.run_in_executor(
                    self._voice_pool, self._post_voice, meta, audio)
            if ok:
                self.voice_outbox.ack(meta_path, meta)
                self.log.info("voice %s uploaded to AI PC", meta.get("clip_id", "?"))

        pending = self.voice_outbox.pending()
        if pending:
            await asyncio.gather(*(_one(mp, m, a) for mp, m, a in pending))

    def _post_voice(self, meta: dict[str, Any], audio: bytes) -> bool:
        """Blocking HTTP POST of one clip, run on the dedicated voice pool. A dead/slow AI
        PC pins one voice-pool worker for at most voice_read_s (never a radio thread), so
        voice throughput degrades to zero while the AI PC is unreachable — acceptable
        (voice is best-effort; SOS is on its own path). Do not widen the pool to 'fix' this."""
        if self._session is None:
            return False
        content_type = "audio/3gpp" if meta.get("codec") == 2 else "audio/ogg"
        try:
            response = self._session.post(
                self.voice_url,
                data={k: str(meta.get(k, "")) for k in
                      ("clip_id", "ref_id", "origin", "codec", "lang")},
                files={"audio": (meta["audio_name"], audio, content_type)},
                timeout=self._voice_timeout,
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
        still flows. The Mac dedups by id, so this is safe alongside the WS replay.

        Runs the blocking POST on the dedicated voice pool rather than the default executor,
        keeping the radio thread pool free even during an uplink outage."""
        if not self.http_url or self._session is None:
            return
        loop = asyncio.get_running_loop()

        def _post(env: dict[str, Any]) -> bool:
            try:
                self._session.post(self.http_url, json=env, timeout=4)
                # NOTE: we do NOT ack here — the WS ACK is the source of truth so the
                # envelope stays queued until confirmed, avoiding loss if the POST lied.
                return True
            except Exception:
                return False

        for _mid, env in self.outbox.pending():
            if env.get("t") != "SOS":
                continue
            ok = await loop.run_in_executor(self._voice_pool, _post, env)
            if not ok:
                break  # link still down; stop hammering

    async def _http_only(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._http_fallback()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=3.0)
