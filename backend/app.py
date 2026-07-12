"""
Sankat-Mochan command post ("AI PC") — FastAPI.

Receives SOS envelopes (from the Pi/LoRa gateway via POST /sos, or the test
button), runs AI triage, feeds the deterministic intelligence services
(clustering → dedup/corroboration → ranking → proposal → de-confliction,
see intelligence.py / docs/INTELLIGENCE-DESIGN.md), and pushes live snapshots
to the dashboard over WebSocket.

Run:  uvicorn app:app --host 0.0.0.0 --port 9000
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # MUST run before importing triage (it reads LLM_* env at import time)
load_dotenv(Path(__file__).parent / ".postgres.env", override=False)

from fastapi import FastAPI, File, Form, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import intelligence
import stt
import triage
from database import database
from intelligence import store
from models import InvalidEnvelope, parse_envelope, sample_sos

app = FastAPI(title="Sankat-Mochan Command Post")
STATIC_DIR = Path(__file__).parent / "static"
AUDIO_DIR = Path(__file__).parent / "audio_store"
AUDIO_DIR.mkdir(exist_ok=True)


def _purge_audio_store() -> None:
    """Every process start is a fresh session (see database.py). In DB-less mode the
    live Store already starts empty, but voice clips are written to disk under
    audio_store/ and OUTLIVE the process — worse, the clip-id counters (_voice_seq,
    _test_seq) reset to 0 on restart, so a NEW `voice-0` would be served the STALE
    bytes of a previous run's `voice-0.webm`. Clear the transient clips on startup so
    a killed-and-restarted server never replays an old session's audio. Only our own
    generated clip files are removed (validated names + known suffixes); anything else
    a user dropped in the folder is left untouched."""
    if not AUDIO_DIR.exists():
        return
    for f in AUDIO_DIR.iterdir():
        try:
            if f.is_file() and _valid_audio_name(f.name):
                f.unlink()
        except OSError as exc:  # never let a locked/undeletable file stop startup (rule #10)
            print(f"[audio] could not purge {f.name}: {type(exc).__name__}")
WEB_DIST = Path(__file__).parent / "web" / "dist"  # built React app (npm run build)

_seen_ids: set[str] = set()  # transport-level dedup (CONTRACT 1)
_test_seq = 0
_voice_seq = 0
MAX_MESH_AUDIO_BYTES = 110_000  # VoiceChunk.MAX_CHUNKS * MAX_CHUNK plus small slack
MAX_BROWSER_AUDIO_BYTES = 5_000_000
_voice_status = {
    "received": 0, "transcribing": 0, "failed": 0,
    "last_received_ms": None, "last_clip": None,
}


class Hub:
    """Tracks connected dashboards and broadcasts JSON to all of them."""

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)


hub = Hub()


class GatewayHub:
    """The Pi LoRa-gateway edge link (EDGE-LINK.md). One persistent bidirectional
    WebSocket:
      up   — the Pi sends {type:"envelope", id, env}; we ingest + reply {type:"ack", id}.
      down — we send {type:"dispatch", id, env} (ACCEPTED / instruction) for the Pi to
             carry over LoRa/BLE back to the victim (the return path).
    Downlink is buffered until the far end ACKs by id, so a disconnect never loses a
    dispatch; flushed (highest urgency first) on reconnect. Idempotent — the phone/Pi
    dedup by envelope id, so replays are safe.
    """

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._pending: dict[str, dict[str, Any]] = {}  # id -> dispatch msg awaiting ack
        self._seq = 0
        self._last_ack_ms: int | None = None
        self._lock = asyncio.Lock()
        self._edge_status = {"voice_inflight": 0, "voice_queued": 0}

    def connected(self) -> bool:
        return self._ws is not None

    def status(self) -> dict[str, Any]:
        return {"connected": self.connected(), "queued": len(self._pending),
                "last_ack_ms": self._last_ack_ms, **self._edge_status}

    def update_edge_status(self, msg: dict[str, Any]) -> None:
        for key in ("voice_inflight", "voice_queued"):
            value = msg.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 512:
                self._edge_status[key] = value

    async def attach(self, ws: WebSocket) -> None:
        await ws.accept()
        self._ws = ws
        await self._flush()  # replay anything the Pi missed while disconnected

    async def detach(self, ws: WebSocket) -> bool:
        if self._ws is ws:
            self._ws = None
            return True
        return False

    async def send_dispatch(self, env: dict[str, Any]) -> None:
        """Queue a downlink envelope (ACCEPTED/instruction) and try to send it now."""
        self._seq += 1
        mid = f"disp-{self._seq}"
        msg = {"type": "dispatch", "id": mid, "env": env,
               "urgency": int(env.get("u", 3))}
        self._pending[mid] = msg
        await self._try_send(msg)

    async def _try_send(self, msg: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None:
            return  # stays in _pending; flushed on reconnect
        try:
            await ws.send_json(msg)
        except Exception:
            self._ws = None  # broken link; keep it pending

    async def _flush(self) -> None:
        # Criticals first (EDGE-LINK priority flush).
        for msg in sorted(self._pending.values(), key=lambda m: -m.get("urgency", 0)):
            await self._try_send(msg)

    def ack(self, mid: str) -> None:
        if self._pending.pop(mid, None) is not None:
            import time as _t
            self._last_ack_ms = int(_t.time() * 1000)


gateway = GatewayHub()


async def _dispatch_to_victims(incident_id: str, gist: str = "Help is on the way") -> None:
    """Return path: push an ACCEPTED envelope down the gateway for every victim
    report in an incident, so their phones flip to 'help is on the way' in their
    own language. refId = the original SOS id the phone will match on."""
    inc = store.incidents.get(incident_id)
    if not inc:
        return
    for rid in inc.get("report_ids", []):
        rep = store.reports.get(rid)
        if not rep or rep.get("is_sensor"):
            continue
        env = {
            "i": f"cp-{incident_id}-{rid}", "t": "ACCEPTED", "o": "cmdpost",
            "r": rid, "g": gist, "ln": rep.get("lang", "en"), "ts": 0, "h": 0,
        }
        await gateway.send_dispatch(env)


def _snapshot() -> dict[str, Any]:
    snap = store.snapshot()
    snap["kind"] = "snapshot"
    snap["ai_enabled"] = triage.is_configured()
    snap["stt_ready"] = stt.is_ready()
    snap["gateway"] = gateway.status()
    snap["database"] = database.status()
    snap["voice"] = dict(_voice_status)
    return snap


async def _broadcast_snapshot() -> None:
    snapshot = _snapshot()
    try:
        await database.persist_snapshot(snapshot)
    except Exception as exc:
        # Database loss must not stop SOS ingest or the live dashboard. The error is
        # operator-visible in logs/health; voice uploads still fail closed with 503.
        database.error = f"{type(exc).__name__}: {exc}"
        print(f"[database] snapshot write failed: {database.error}")
    await hub.broadcast(snapshot)


async def _ingest(envelope: dict[str, Any], audio_url: str | None = None) -> bool:
    """Validate → dedup → triage[LLM] → intelligence[code] → broadcast."""
    if envelope["type"] != "SOS":
        # Return-path envelopes from the mesh (CONTRACT 1): ACCEPTED locks the
        # incident (responder tapped Accept in the field); DELIVERED is logged.
        ref = envelope.get("refId")
        if ref:
            if envelope["type"] == "ACCEPTED":
                store.accept_from_mesh(ref, envelope["origin"], envelope.get("deviceId", ""))
            else:
                store.delivered_from_mesh(ref, envelope["origin"])
            await _broadcast_snapshot()
        return False
    if envelope["id"] in _seen_ids:
        return False  # transport re-broadcast dedup
    _seen_ids.add(envelope["id"])

    if envelope.get("gist", "").startswith(intelligence.TAGS_PREFIX):
        # Sahayak agent follow-up: machine-authored structured tags. MUST bypass
        # LLM triage — triage would re-label category before dedup and the
        # follow-up would coin-flip into a duplicate incident (and the raw
        # 'TAGS …' string would become a headline). parse_tags is the enum
        # whitelist gate for this untrusted mesh input (rule #8).
        tags = intelligence.parse_tags(envelope["gist"])
        if tags is None:
            print(f"[ingest] dropped malformed TAGS gist from {envelope['origin']}")
            return False
        store.merge_tags_update(envelope, tags)
        await _broadcast_snapshot()
        return True

    if envelope.get("category") == "sensor":
        # C7: sensor envelopes skip the LLM — readings aren't language
        ai = {"urgency": envelope.get("urgency", 3), "category": "sensor",
              "english": envelope.get("gist", ""), "ai": False, "latency_ms": 0}
    else:
        ai = await triage.triage(envelope)
    if audio_url:
        envelope["audio"] = audio_url
    store.add_report(envelope, ai)
    await _broadcast_snapshot()
    return True


# ---- ingest ---------------------------------------------------------------
@app.post("/sos")
async def post_sos(request: Request) -> JSONResponse:
    """Ingest endpoint the LoRa gateway (and the test button) call."""
    try:
        body = await request.body()
        envelope = parse_envelope(body)
    except InvalidEnvelope as e:
        # Rule #10: don't leak internals; log detail server-side, return generic.
        print(f"[ingest] dropped invalid envelope: {e}")
        return JSONResponse({"status": "rejected"}, status_code=400)
    new = await _ingest(envelope)
    return JSONResponse({"status": "ok", "new": new})


@app.post("/inject")
async def inject() -> JSONResponse:
    """Dev/demo helper: push a realistic test SOS through the real path."""
    global _test_seq
    envelope = parse_envelope(sample_sos(_test_seq))
    _test_seq += 1
    new = await _ingest(envelope)
    return JSONResponse({"status": "ok", "injected": new})


# ---- voice ------------------------------------------------------------------
@app.post("/transcribe")
async def transcribe_ep(audio: UploadFile = File(...), lang: str | None = Form(None)) -> JSONResponse:
    """Audio → text (IndicConformer). Runs off the event loop."""
    # Size-cap the upload before it lands in RAM, exactly like /voice_sos and /mesh_voice
    # (CLAUDE.md #8). Reading without a bound let an unauthenticated multi-GB POST OOM the
    # command post. Read one byte past the cap so an over-size body is detectable, not silently
    # truncated into a partial (mis-transcribed) clip.
    data = await audio.read(MAX_BROWSER_AUDIO_BYTES + 1)
    if not data or len(data) > MAX_BROWSER_AUDIO_BYTES:
        return JSONResponse({"status": "rejected"}, status_code=400)
    result = await run_in_threadpool(stt.transcribe, data, lang)
    return JSONResponse(result)


@app.post("/voice_sos")
async def voice_sos(
    audio: UploadFile = File(...),
    lang: str | None = Form(None),
    origin: str = Form("voice"),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
) -> JSONResponse:
    """Full voice path: transcribe → SOS envelope → triage → intelligence.
    The audio itself is kept so the operator can replay it."""
    global _voice_seq
    data = await audio.read(MAX_BROWSER_AUDIO_BYTES + 1)
    if not data or len(data) > MAX_BROWSER_AUDIO_BYTES:
        return JSONResponse({"status": "rejected"}, status_code=400)
    vid = f"voice-{_voice_seq}"
    _voice_seq += 1
    content_type = "audio/webm"
    if database.enabled:
        await database.store_voice(
            clip_id=vid, report_id=None, origin=origin, codec=1,
            content_type=content_type, audio=data,
        )
        audio_url = f"/audio/{vid}"
    else:
        audio_path = AUDIO_DIR / f"{vid}.webm"
        audio_path.write_bytes(data)
        audio_url = f"/audio/{vid}.webm"
    tr = await run_in_threadpool(stt.transcribe, data, lang)
    if not tr.get("text"):
        return JSONResponse({"status": "no_speech", "transcript": tr}, status_code=422)
    env = {
        "i": vid, "t": "SOS", "o": origin, "u": 3,
        "c": "unknown", "g": tr["text"], "ln": tr["lang"], "h": 0,
    }
    if lat is not None and lng is not None:
        env["la"], env["lo"] = lat, lng
    if database.enabled:
        await database.store_voice(
            clip_id=vid, report_id=vid, origin=origin, codec=1,
            content_type=content_type, audio=data, transcript=tr["text"],
        )
    _voice_status.update(received=_voice_status["received"] + 1,
                         last_received_ms=int(time.time() * 1000), last_clip=vid)
    new = await _ingest(parse_envelope(env), audio_url=audio_url)
    return JSONResponse({"status": "ok", "transcript": tr, "ingested": new})


@app.post("/mesh_voice")
async def mesh_voice(
    audio: UploadFile = File(...),
    clip_id: str = Form(...),
    ref_id: str = Form(...),
    origin: str = Form(...),
    codec: int = Form(...),
    lang: str | None = Form(None),
) -> JSONResponse:
    """A complete phone recording reassembled by the Pi.

    Security-sensitive network/file handling (rule #6): identifiers, codec and byte
    size are allowlisted before the payload is stored. The recording enriches an
    existing validated SOS only; it can never create a standalone AI-generated card.
    """
    if (not clip_id.replace("-", "").isalnum()
            or not ref_id.replace("-", "").isalnum()
            or not origin.isalnum()
            or len(clip_id) > 48 or len(ref_id) > 32 or len(origin) > 32
            or codec not in (1, 2)):
        return JSONResponse({"status": "rejected"}, status_code=400)
    if ref_id not in store.reports:
        # The voice ref_id is `{origin}-{voiceSeq}`, but the SOS report is keyed by the
        # SOS envelope id `{origin}-{seq}` — two INDEPENDENT counters on the phone, so an
        # exact match is the exception, not the rule. Fall back to the most recent report
        # from the SAME origin, so a victim's recording still enriches their own card.
        # This never fabricates a card: if that origin has no report yet, the Pi keeps the
        # clip in its durable voice outbox (409) and retries once the SOS lands.
        same_origin = [r for r in store.reports.values() if r.get("origin") == origin]
        if not same_origin:
            return JSONResponse({"status": "awaiting_sos"}, status_code=409)
        ref_id = max(same_origin, key=lambda r: r.get("received_at", 0))["id"]

    data = await audio.read(MAX_MESH_AUDIO_BYTES + 1)
    if not data or len(data) > MAX_MESH_AUDIO_BYTES:
        return JSONResponse({"status": "rejected"}, status_code=400)

    extension = ".3gp" if codec == 2 else ".ogg"
    content_type = "audio/3gpp" if codec == 2 else "audio/ogg"
    if database.enabled:
        await database.store_voice(
            clip_id=clip_id, report_id=ref_id, origin=origin, codec=codec,
            content_type=content_type, audio=data,
        )
        audio_url = f"/audio/{clip_id}"
    else:
        audio_name = f"{clip_id}{extension}"
        audio_path = AUDIO_DIR / audio_name
        audio_path.write_bytes(data)
        audio_url = f"/audio/{audio_name}"

    # Make the recording playable and ACK the Pi before loading/running the STT model.
    # Otherwise first-model-load latency exceeds the Pi's HTTP timeout and the clip looks
    # lost even though it reached this process.
    store.attach_voice(ref_id, audio_url, None, None)
    _voice_status.update(received=_voice_status["received"] + 1,
                         last_received_ms=int(time.time() * 1000), last_clip=clip_id)
    await _broadcast_snapshot()
    asyncio.create_task(_transcribe_mesh_voice(
        clip_id=clip_id, ref_id=ref_id, origin=origin, codec=codec,
        content_type=content_type, data=data, lang=lang, audio_url=audio_url,
    ), name=f"transcribe-{clip_id}")
    return JSONResponse({
        "status": "ok", "clip_id": clip_id, "ref_id": ref_id,
        "stored": True, "transcription": "pending",
    })


async def _transcribe_mesh_voice(*, clip_id: str, ref_id: str, origin: str,
                                 codec: int, content_type: str, data: bytes,
                                 lang: str | None, audio_url: str) -> None:
    _voice_status["transcribing"] += 1
    try:
        # 1. Browser-playable transcode (AMR/3GP → WAV). Runs eagerly here, AFTER the Pi
        #    was already ACKed, so it never blocks the upload. If ffmpeg is missing or the
        #    clip won't decode, we keep the raw url and the card shows a quiet unplayable
        #    state — never a crash (CLAUDE.md #10).
        web = await run_in_threadpool(stt.transcode_for_web, data)
        web_audio = web[0] if web else None
        web_content_type = web[1] if web else None
        playable_url = f"/web_audio/{clip_id}" if web else audio_url
        # File mode: persist the WAV next to the raw clip so /web_audio can serve it.
        if web and not database.enabled:
            (AUDIO_DIR / f"{clip_id}.wav").write_bytes(web_audio)
        # Publish the playable URL NOW, before the (slow) STT below. The card was first
        # attached with the raw .3gp — browsers cannot play AMR, so until this swap the
        # operator's play button is dead. Transcode is fast; STT (first model load) can
        # take minutes, and audio must never wait on it.
        if web and ref_id in store.reports:
            store.attach_voice(ref_id, playable_url, None, None)
            await _broadcast_snapshot()

        # 2. Speech-to-text (native script).
        tr = await run_in_threadpool(stt.transcribe, data, lang)
        transcript = str(tr.get("text", "")).strip()

        # 3. FAITHFUL translation only — never triage. triage() would pattern-complete a
        #    benign clip ("mic testing one two three") into a false life-threatening SOS
        #    and escalate its urgency; translate() is forbidden from adding or inferring.
        ai = None
        if transcript:
            tlang = tr.get("lang") or lang or "en"
            tx = await triage.translate(transcript, tlang)
            ai = {
                "english": tx.get("english") or transcript,
                "ai": bool(tx.get("ai")),
                "latency_ms": tx.get("latency_ms", 0),
            }
        if ref_id in store.reports:
            store.attach_voice(ref_id, playable_url, transcript, ai)
        if database.enabled:
            await database.store_voice(
                clip_id=clip_id, report_id=ref_id, origin=origin, codec=codec,
                content_type=content_type, audio=data, transcript=transcript or None,
                web_audio=web_audio, web_content_type=web_content_type,
            )
        if not transcript:
            _voice_status["failed"] += 1
    except Exception as exc:
        _voice_status["failed"] += 1
        print(f"[voice] background transcription failed for {clip_id}: {type(exc).__name__}")
        if ref_id in store.reports:
            store.attach_voice(ref_id, audio_url, "", None)
    finally:
        _voice_status["transcribing"] = max(0, _voice_status["transcribing"] - 1)
        await _broadcast_snapshot()


# Audio ids we generate are alnum with dashes; recordings carry one known extension.
# Everything else is rejected before it can touch the filesystem or the DB (CLAUDE.md #8).
_AUDIO_SUFFIXES = {".3gp", ".ogg", ".webm", ".wav"}


def _valid_audio_name(name: str) -> bool:
    if len(name) > 64:
        return False
    stem, dot, suffix = name.rpartition(".")
    if dot:
        if f".{suffix}" not in _AUDIO_SUFFIXES:
            return False
    else:
        stem = name  # a bare clip_id (no extension) is used by the DB-mode routes
    return bool(stem) and stem.replace("-", "").isalnum()


_MEDIA_BY_SUFFIX = {".3gp": "audio/3gpp", ".ogg": "audio/ogg",
                    ".webm": "audio/webm", ".wav": "audio/wav"}


@app.get("/audio/{name}")
async def audio_file(name: str) -> Response:
    """Replay a stored voice SOS (raw clip). Name is constrained to our generated ids."""
    if not _valid_audio_name(name):
        return JSONResponse({"status": "rejected"}, status_code=400)
    stored = await database.get_voice(name)
    if stored is not None:
        data, content_type = stored
        return Response(content=data, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=3600"})
    path = AUDIO_DIR / name
    if not path.exists() or not path.resolve().is_relative_to(AUDIO_DIR.resolve()):
        return JSONResponse({"status": "unknown"}, status_code=404)
    return FileResponse(path, media_type=_MEDIA_BY_SUFFIX.get(path.suffix, "audio/webm"))


@app.get("/web_audio/{clip_id}")
async def web_audio_file(clip_id: str) -> Response:
    """Serve the browser-playable (WAV) transcode of a clip. Falls back to 404 if the
    transcode isn't available (e.g. ffmpeg missing) — the card then keeps the raw url."""
    if not _valid_audio_name(clip_id):
        return JSONResponse({"status": "rejected"}, status_code=400)
    stored = await database.get_web_audio(clip_id)
    if stored is not None:
        data, content_type = stored
        return Response(content=data, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=3600"})
    path = AUDIO_DIR / f"{clip_id}.wav"
    if not path.exists() or not path.resolve().is_relative_to(AUDIO_DIR.resolve()):
        return JSONResponse({"status": "unknown"}, status_code=404)
    return FileResponse(path, media_type="audio/wav")


# ---- dispatch lifecycle (C5/C6/C9) -----------------------------------------
@app.post("/propose/{incident_id}")
async def propose(incident_id: str) -> JSONResponse:
    """C5: compute + send the nearest-responder proposal for an incident."""
    proposal = store.propose(incident_id)
    await _broadcast_snapshot()
    if proposal is None:
        return JSONResponse({"status": "awaiting responder"}, status_code=409)
    return JSONResponse({"status": "ok", "proposal": proposal})


@app.post("/accept/{incident_id}")
async def accept(incident_id: str, responder: str | None = None) -> JSONResponse:
    """C6: responder accepts → lock (first-write-wins)."""
    ok, reason = store.accept(incident_id, responder)
    await _broadcast_snapshot()
    if not ok:
        return JSONResponse({"status": reason}, status_code=409)
    # Return path: push "help is on the way" back down the gateway to the victim(s).
    # When both incident and responder have coords, embed a real ETA so the
    # on-phone agent can reassure with facts. No coords → no ETA is ever invented.
    gist = "Help is on the way"
    inc = store.incidents.get(incident_id)
    r = store.responders.get((inc or {}).get("assigned_to") or "")
    if inc and r and inc.get("lat") is not None and r.get("lat") is not None:
        dist = intelligence.haversine_km(inc["lat"], inc["lng"], r["lat"], r["lng"])
        eta_min = int(dist / intelligence.RESPONDER_SPEED_KMH * 60) + 1
        gist = f"Help is on the way · ETA ~{eta_min} min"
    await _dispatch_to_victims(incident_id, gist)
    return JSONResponse({"status": "ok"})


@app.post("/resolve/{incident_id}")
async def resolve(incident_id: str) -> JSONResponse:
    """C9: incident cleared — frees the responder, archives the incident."""
    ok = store.resolve(incident_id)
    await _broadcast_snapshot()
    return JSONResponse({"status": "ok" if ok else "unknown"},
                        status_code=200 if ok else 404)


@app.post("/responder/{responder_id}/heartbeat")
async def responder_heartbeat(responder_id: str, request: Request) -> JSONResponse:
    """C4: responder app beacons location/status back through the mesh."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    ok = store.heartbeat(
        responder_id,
        lat=body.get("lat"), lng=body.get("lng"), status=body.get("status"),
    )
    await _broadcast_snapshot()
    return JSONResponse({"status": "ok" if ok else "unknown"},
                        status_code=200 if ok else 404)


# ---- introspection ----------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "incidents": len(store.incidents),
            "ai_enabled": triage.is_configured(), "stt_ready": stt.is_ready(),
            "gateway": gateway.status(), "database": database.status(),
            "voice": dict(_voice_status)}


@app.get("/queue")
async def queue() -> dict[str, Any]:
    """Current state as JSON (debugging / gateway verification)."""
    return _snapshot()


@app.get("/sessions")
async def sessions() -> dict[str, Any]:
    """Historical runs. The active dashboard always remains on the current session."""
    return {"current": database.session_id, "sessions": await database.list_sessions()}


@app.get("/sessions/{session_id}")
async def session_history(session_id: str) -> Any:
    result = await database.get_session(session_id)
    if result is None:
        return JSONResponse({"status": "unknown"}, status_code=404)
    return result


@app.get("/sessions/{session_id}/audio/{clip_id}")
async def historical_audio(session_id: str, clip_id: str) -> Response:
    if not clip_id.replace("-", "").isalnum() or len(clip_id) > 48:
        return JSONResponse({"status": "rejected"}, status_code=400)
    stored = await database.get_session_voice(session_id, clip_id)
    if stored is None:
        return JSONResponse({"status": "unknown"}, status_code=404)
    data, content_type = stored
    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "private, max-age=3600"})


@app.websocket("/ws")
async def ws(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        await ws.send_json(_snapshot())  # bring new clients up to date
        while True:
            await ws.receive_text()  # keepalive; we don't expect client msgs
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)


@app.websocket("/gateway")
async def gateway_ws(ws: WebSocket) -> None:
    """The Pi LoRa-gateway edge link (EDGE-LINK.md) — bidirectional + ACKed."""
    await gateway.attach(ws)
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "envelope":
                # Up: an SOS/DELIVERED from the mesh. Ingest, then ACK by id so the
                # Pi can drop it from its durable outbox. Idempotent (dedup by id).
                try:
                    env = parse_envelope(msg.get("env", {}))
                    await _ingest(env)
                except InvalidEnvelope as e:
                    print(f"[gateway] dropped invalid envelope: {e}")
                if msg.get("id"):
                    await ws.send_json({"type": "ack", "id": msg["id"]})
            elif kind == "ack":
                # Down: the Pi confirms a dispatch — clear it from our buffer.
                gateway.ack(msg.get("id", ""))
            elif kind == "heartbeat":
                await ws.send_json({"type": "pong"})
            elif kind == "peer":
                node_id = str(msg.get("node_id", ""))
                role = msg.get("role")
                connected = msg.get("connected")
                # device_id is optional (the BLE beacon can't carry it — 13-byte scan-
                # response budget); the store normally learns it from this phone's
                # envelopes. Accept it here too if a future Pi build forwards it.
                device_id = str(msg.get("device_id", ""))[:32]
                if device_id and not device_id.isalnum():
                    device_id = ""
                if (role == "responder" and node_id.isalnum() and len(node_id) <= 8
                        and isinstance(connected, bool)):
                    store.mesh_responder(node_id, connected, device_id)
                    await _broadcast_snapshot()
            elif kind == "status":
                gateway.update_edge_status(msg)
                await _broadcast_snapshot()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if await gateway.detach(ws):
            store.mesh_responders_offline()
            await _broadcast_snapshot()


@app.on_event("startup")
async def start_background() -> None:
    _purge_audio_store()  # fresh session: drop any prior run's cached voice clips
    await database.start()
    await database.persist_snapshot(_snapshot())
    async def watchdog() -> None:
        while True:
            await asyncio.sleep(30)
            before = len(store.activity)
            store.check_stuck()  # C4 stuck-assignment timeout
            if len(store.activity) != before:
                await _broadcast_snapshot()

    asyncio.create_task(watchdog())

    # Load the STT model NOW (in a worker thread) instead of lazily on the first voice
    # clip, so the first real recording doesn't eat the ~13 s cold model load. This
    # never blocks startup; /health `stt_ready` flips true once the model is hot.
    async def _warm_stt() -> None:
        ok = await run_in_threadpool(stt.warmup)
        print(f"[stt] startup warmup {'ready' if ok else 'FAILED'}")
        await _broadcast_snapshot()

    asyncio.create_task(_warm_stt())


@app.on_event("shutdown")
async def close_database() -> None:
    try:
        await database.persist_snapshot(_snapshot())
        await database.close()
    except Exception as exc:
        print(f"[database] shutdown write failed: {type(exc).__name__}")


# ---- basemap / static -------------------------------------------------------
@app.get("/vtiles/{z}/{x}/{y}.pbf")
async def vector_tile(z: int, x: int, y: int):
    """Offline basemap tiles, served straight out of the local PMTiles archive.
    Plain z/x/y HTTP so MapLibre's workers fetch them natively."""
    if not 0 <= z <= 15:
        return Response(status_code=204)
    reader = _pmtiles_reader()
    if reader is None:
        return JSONResponse({"status": "no basemap"}, status_code=404)
    data = reader.get(z, x, y)
    if not data:
        return Response(status_code=204)  # empty tile — maplibre skips it
    return Response(
        content=data,
        media_type="application/x-protobuf",
        headers={"Content-Encoding": "gzip", "Cache-Control": "max-age=86400"},
    )


_pmtiles_cache: list = []  # [Reader] once opened (module-lifetime mmap)


def _pmtiles_reader():
    if _pmtiles_cache:
        return _pmtiles_cache[0]
    path = STATIC_DIR / "bangalore.pmtiles"
    if not path.exists():
        return None
    from pmtiles.reader import Reader, MmapSource

    f = path.open("rb")  # kept open for the process lifetime (mmap backing)
    _pmtiles_cache.append(Reader(MmapSource(f)))
    return _pmtiles_cache[0]


@app.get("/static/bangalore.pmtiles")
async def pmtiles_archive(request: Request):
    """Serve the offline basemap archive with HTTP Range support (RFC 7233)."""
    path = STATIC_DIR / "bangalore.pmtiles"
    if not path.exists():
        return JSONResponse({"status": "missing"}, status_code=404)
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header or not range_header.startswith("bytes="):
        return FileResponse(path, media_type="application/octet-stream")
    try:
        start_s, _, end_s = range_header[6:].partition("-")
        start = int(start_s)
        end = min(int(end_s) if end_s else size - 1, size - 1)
        if start > end or start < 0:
            raise ValueError
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    with path.open("rb") as f:
        f.seek(start)
        chunk = f.read(end - start + 1)
    return Response(
        content=chunk, status_code=206, media_type="application/octet-stream",
        headers={"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"},
    )


@app.get("/")
async def index() -> FileResponse:
    # Prefer the built React app; fall back to the vanilla dashboard.
    if (WEB_DIST / "index.html").exists():
        return FileResponse(WEB_DIST / "index.html")
    return FileResponse(STATIC_DIR / "index.html")


if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

if (STATIC_DIR / "basemaps-assets").exists():
    app.mount(
        "/basemaps-assets",
        StaticFiles(directory=STATIC_DIR / "basemaps-assets"),
        name="basemaps-assets",
    )

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
