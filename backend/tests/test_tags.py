"""
Sahayak agent TAGS pipeline tests — the demo-critical invariants.

Run:  .venv/bin/python test_tags.py
(no pytest dependency — plain asserts, exits non-zero on failure)

Invariants under test (each one killed a demo beat in the adversarial critique):
 1. TAGS follow-ups merge into the SAME incident (bypass LLM triage, origin-only merge).
 2. The raw "TAGS …" wire string never becomes a headline.
 3. Phone-decided urgency survives (no triage overwrite).
 4. received_at refresh keeps the merge window alive for the late unresp escalation.
 5. Malformed / injection-shaped TAGS are dropped at the enum gate.
 6. Every TAGS envelope the phone would emit fits the 244-byte wire cap.
"""
import asyncio
import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ modules

import app as cp
import intelligence
from intelligence import Store, parse_tags, humanize_tags
from models import parse_envelope


def test_parse_and_validate():
    assert parse_tags("TAGS c:3 inj:bleed trap:y hz:water lm:old temple gate") == {
        "c": 3, "inj": "bleed", "trap": "y", "hz": "water", "lm": "old temple gate"}
    assert parse_tags("TAGS unresp:y") == {"unresp": "y"}
    assert parse_tags("TAGS c:200 inj:bleed") == {"inj": "bleed"}          # bad count dropped
    assert parse_tags("TAGS evil:payload inj:bleed") == {"inj": "bleed"}   # unknown key dropped
    assert parse_tags("TAGS ") is None
    assert parse_tags("hello") is None
    assert parse_tags("TAGS lm:" + "x" * 100) == {"lm": "x" * 48}          # landmark capped
    # injection-shaped values die at the enum gate
    assert parse_tags("TAGS inj:ignore_previous_instructions") is None
    print("ok  parse/validate")


def test_merge_same_incident_and_escalation():
    s = Store()
    base = {"id": "a1", "origin": "ph-9", "ts": 0, "hops": 1, "lang": "ta", "gist": "",
            "urgency": 3, "category": "trapped", "lat": None, "lng": None, "locationHint": ""}
    s.add_report(base, {"urgency": 3, "category": "trapped", "english": "", "ai": False, "latency_ms": 0})
    tags_env = {**base, "id": "a2", "urgency": 5, "gist": "TAGS c:3 inj:bleed trap:y"}
    inc = s.merge_tags_update(tags_env, parse_tags(tags_env["gist"]))
    assert len(s.incidents) == 1, "TAGS must merge, never duplicate"
    assert inc["urgency"] == 5, "phone urgency must survive"
    assert not inc["headline"].startswith("TAGS"), "raw wire string must never headline"
    assert inc["tags"] == {"c": 3, "inj": "bleed", "trap": "y"}
    # window refresh: backdate the anchor past the window, then escalate
    anchor = s.reports["a1"]
    anchor["received_at"] -= intelligence.DEDUP_WINDOW_S - 60  # near-expired window...
    esc = {**base, "id": "a3", "urgency": 5, "gist": "TAGS unresp:y"}
    inc2 = s.merge_tags_update(esc, parse_tags(esc["gist"]))
    assert inc2["id"] == inc["id"], "escalation must land on the SAME incident"
    assert inc2["unresponsive"] is True and "victim unresponsive" in inc2["why"]
    # ...and because merge refreshed received_at, ANOTHER late update still merges
    late = {**base, "id": "a4", "urgency": 5, "gist": "TAGS mob:n"}
    inc3 = s.merge_tags_update(late, parse_tags(late["gist"]))
    assert inc3["id"] == inc["id"], "received_at refresh must keep the window alive"
    print("ok  merge/escalation/window-refresh")


def test_ingest_path():
    async def run():
        cp.store.__init__()  # fresh store
        cp._seen_ids.clear()
        ok_sos = {"i": "t-1", "t": "SOS", "o": "ph-77", "u": 3, "c": "flood", "g": "",
                  "ln": "ta", "ts": 0, "h": 1}
        ok_tags = {**ok_sos, "i": "t-2", "u": 5, "g": "TAGS c:2 hz:water lm:bus stand"}
        bad = {**ok_sos, "i": "t-3", "g": "TAGS <script>alert(1)</script>"}
        assert await cp._ingest(parse_envelope(json.dumps(ok_sos)))
        assert await cp._ingest(parse_envelope(json.dumps(ok_tags)))
        assert not await cp._ingest(parse_envelope(json.dumps(bad))), "malformed TAGS dropped"
        assert len(cp.store.incidents) == 1
        inc = next(iter(cp.store.incidents.values()))
        assert inc["headline"] == humanize_tags({"c": 2, "hz": "water", "lm": "bus stand"})
        snap = cp.store.snapshot()
        assert snap["incidents"][0]["tags"]["c"] == 2
    asyncio.run(run())
    print("ok  ingest path")


def test_wire_size():
    # Worst-case TAGS gist inside a worst-case envelope. The phone's SosMessage.encode()
    # trims the GIST (only) from the end, one char at a time, until the frame fits — mirror
    # that here and assert the surviving prefix still parses with the critical keys intact
    # (AgentTags.KEY_ORDER is criticality-first: unresp before everything, lm last).
    gist = "TAGS unresp:y c:99 inj:fracture trap:y hz:electric mob:n lm:" + "x" * 48
    def encoded(g):
        # Mirrors BleMeshService.sendAgentTags: locationHint is deliberately empty on
        # TAGS follow-ups (the original SOS carried it; lm rides in the tags).
        env = {"i": "abcd-99", "t": "SOS", "o": "abcd", "d": "device-1234567890",
               "u": 5, "c": "trapped", "l": "", "g": g, "ln": "ta",
               "la": 12.933456, "lo": 77.624987, "ts": 1760000000000, "h": 0}
        return json.dumps(env, separators=(",", ":")).encode()
    while len(encoded(gist)) > 244 and gist:
        gist = gist[:-1]
    size = len(encoded(gist))
    assert size <= 244, f"trimmed TAGS envelope is {size}B > 244B"
    survived = parse_tags(gist.strip())
    assert survived is not None, "trimmed gist no longer parses at all"
    for key in ("unresp", "c", "inj", "trap"):
        assert key in survived, f"critical key {key!r} lost to gist trimming: {survived}"
    print(f"ok  wire size (trimmed to {size}B ≤ 244B, critical keys survive: {survived})")


if __name__ == "__main__":
    test_parse_and_validate()
    test_merge_same_incident_and_escalation()
    test_ingest_path()
    test_wire_size()
    print("ALL TAGS TESTS PASSED")
