"""
Sankat-Mochan command post ("AI PC") — FastAPI.

Receives SOS envelopes (from the Pi/LoRa gateway via POST /sos, or the test
button), runs AI triage, and pushes a live triage queue to the browser
dashboard over WebSocket. Transport-agnostic: the same POST /sos endpoint is
fed by the LoRa gateway later — no changes here.

Run:  uvicorn app:app --host 0.0.0.0 --port 9000
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # MUST run before importing triage (it reads LLM_* env at import time)

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import triage
from models import InvalidEnvelope, parse_envelope, sample_sos

app = FastAPI(title="Sankat-Mochan Command Post")
STATIC_DIR = Path(__file__).parent / "static"

# ---- In-memory state (a demo doesn't need a DB) --------------------------
_seen_ids: set[str] = set()            # dedup / loop guard (CONTRACT 1)
_queue: dict[str, dict[str, Any]] = {} # id -> enriched record
_test_seq = 0


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


def _snapshot() -> dict[str, Any]:
    records = sorted(
        _queue.values(),
        key=lambda r: (r.get("urgency", 0), r.get("ts", 0)),
        reverse=True,
    )
    return {"kind": "snapshot", "records": records, "ai_enabled": triage.is_configured()}


async def _ingest(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Validate → dedup → triage → store → broadcast. Returns the record or None."""
    if envelope["type"] != "SOS":
        # DELIVERED / ACCEPTED just update status on an existing SOS.
        ref = envelope.get("refId")
        if ref and ref in _queue:
            _queue[ref]["status"] = (
                "en route" if envelope["type"] == "ACCEPTED" else "delivered"
            )
            await hub.broadcast({"kind": "update", "record": _queue[ref]})
        return None

    if envelope["id"] in _seen_ids:
        return None  # dedup
    _seen_ids.add(envelope["id"])

    ai = await triage.triage(envelope)
    record = {
        **envelope,
        "triage": ai,
        "eff_urgency": ai.get("urgency", envelope["urgency"]),
        "english": ai.get("english", envelope["gist"]),
        "status": "new",
    }
    # Sort key uses the AI-adjusted urgency when available.
    record["urgency"] = record["eff_urgency"]
    _queue[envelope["id"]] = record
    await hub.broadcast({"kind": "new", "record": record})
    return record


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
    rec = await _ingest(envelope)
    return JSONResponse({"status": "ok", "new": rec is not None})


@app.post("/accept/{sos_id}")
async def accept(sos_id: str) -> JSONResponse:
    """Responder dispatch. For now marks en-route + broadcasts; the return-path
    ACCEPTED envelope back through the mesh is wired when the gateway is up."""
    rec = _queue.get(sos_id)
    if not rec:
        return JSONResponse({"status": "unknown"}, status_code=404)
    rec["status"] = "en route"
    await hub.broadcast({"kind": "update", "record": rec})
    return JSONResponse({"status": "ok"})


@app.post("/inject")
async def inject() -> JSONResponse:
    """Dev helper: push a realistic test SOS through the same path as real ones."""
    global _test_seq
    envelope = parse_envelope(sample_sos(_test_seq))
    _test_seq += 1
    rec = await _ingest(envelope)
    return JSONResponse({"status": "ok", "injected": rec is not None})


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "queued": len(_queue), "ai_enabled": triage.is_configured()}


@app.get("/queue")
async def queue() -> dict[str, Any]:
    """Current triage queue as JSON (debugging / gateway verification)."""
    return _snapshot()


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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Serve remaining static assets (if any) under /static
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
