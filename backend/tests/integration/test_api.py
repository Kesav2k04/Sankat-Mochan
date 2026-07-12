"""End-to-end API tests for the FastAPI command post, exercised through the real
ASGI app with Starlette's TestClient. No LLM and no PostgreSQL are configured
(see conftest), so these prove the offline/fallback path a fresh machine gets."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture(scope="module")
def client():
    with TestClient(app_module.app) as c:
        yield c


def _envelope(i: str, **over):
    env = {"i": i, "t": "SOS", "o": "ph-77", "u": 4, "c": "flood",
           "l": "underpass", "g": "water is rising fast", "ln": "en",
           "la": 12.93, "lo": 77.62, "ts": 0, "h": 1}
    env.update(over)
    return env


def test_health_reports_offline_stack(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ai_enabled"] is False            # no LLM configured in tests
    assert body["database"]["connected"] is False # no PostgreSQL in tests
    assert "incidents" in body


def test_dashboard_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_sos_ingest_and_transport_dedup(client):
    env = _envelope("api-1")
    r = client.post("/sos", content=json.dumps(env))
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "new": True}

    # the mesh re-broadcasts; the same envelope id must not create a second incident
    r = client.post("/sos", content=json.dumps(env))
    assert r.json() == {"status": "ok", "new": False}

    snap = client.get("/health").json()
    assert snap["incidents"] >= 1


def test_sos_rejects_garbage_without_leaking_details(client):
    for bad in (b"not json", b"\xff\xfe\x00", json.dumps({"i": "x", "t": "EVIL", "o": "y"}).encode()):
        r = client.post("/sos", content=bad)
        assert r.status_code == 400
        assert r.json() == {"status": "rejected"}   # rule #10: generic, no internals


def test_tags_followup_merges_not_duplicates(client):
    first = _envelope("api-tags-1", o="ph-88", g="trapped near the school wall")
    assert client.post("/sos", content=json.dumps(first)).json()["new"] is True
    before = client.get("/health").json()["incidents"]

    followup = _envelope("api-tags-2", o="ph-88", g="TAGS c:2 inj:bleed trap:y")
    r = client.post("/sos", content=json.dumps(followup))
    assert r.status_code == 200 and r.json()["new"] is True
    assert client.get("/health").json()["incidents"] == before   # merged, no new incident

    malformed = _envelope("api-tags-3", o="ph-88", g="TAGS :::")
    r = client.post("/sos", content=json.dumps(malformed))
    assert r.json()["new"] is False                               # dropped at the gate


def test_inject_button_cycles_demo_scenarios(client):
    r = client.post("/inject")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_audio_endpoint_rejects_path_tricks(client):
    for name in ("../secrets.wav", "..%2fx.wav", "no-such-clip.wav"):
        r = client.get(f"/audio/{name}")
        assert r.status_code in (400, 404)
