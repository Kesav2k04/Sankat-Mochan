"""Unit tests for models.parse_envelope — the untrusted-ingest gate (rule #8)."""
from __future__ import annotations

import json

import pytest

from models import InvalidEnvelope, parse_envelope, sample_sos


def _minimal(**over):
    env = {"i": "m-1", "t": "SOS", "o": "ph-9"}
    env.update(over)
    return env


# ---- happy path -------------------------------------------------------------

def test_accepts_bytes_str_and_dict_equally():
    env = _minimal(g="water rising", u=4, la=12.9, lo=77.6)
    as_dict = parse_envelope(env)
    as_str = parse_envelope(json.dumps(env))
    as_bytes = parse_envelope(json.dumps(env).encode("utf-8"))
    assert as_dict == as_str == as_bytes
    assert as_dict["id"] == "m-1"
    assert as_dict["urgency"] == 4
    assert as_dict["lat"] == pytest.approx(12.9)
    assert as_dict["lng"] == pytest.approx(77.6)


def test_all_demo_samples_parse():
    for seq in range(8):
        parsed = parse_envelope(sample_sos(seq))
        assert parsed["type"] == "SOS"
        assert parsed["id"] == f"test-{seq}"
        assert 1 <= parsed["urgency"] <= 5
        assert 0 <= parsed["hops"] <= 15


def test_no_gps_sample_has_no_coords():
    parsed = parse_envelope(sample_sos(6))  # the deliberate no-GPS lane
    assert parsed["lat"] is None and parsed["lng"] is None


# ---- rejection --------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    b"\xff\xfe not json",                 # broken JSON
    b"[1,2,3]",                            # not an object
    json.dumps(_minimal(t="EVIL")).encode(),   # unknown type
    json.dumps({"t": "SOS", "o": "x"}).encode(),   # missing id
    json.dumps({"i": "x", "t": "SOS"}).encode(),   # missing origin
])
def test_rejects_malformed(bad):
    with pytest.raises(InvalidEnvelope):
        parse_envelope(bad)


def test_rejects_oversized_payload():
    big = json.dumps(_minimal(g="x" * 5000)).encode()
    assert len(big) > 4096
    with pytest.raises(InvalidEnvelope):
        parse_envelope(big)


# ---- clamping / normalization ------------------------------------------------

def test_urgency_and_hops_are_clamped():
    p = parse_envelope(_minimal(u=99, h=99))
    assert p["urgency"] == 5 and p["hops"] == 15
    p = parse_envelope(_minimal(u=-3, h=-3))
    assert p["urgency"] == 1 and p["hops"] == 0


def test_non_numeric_urgency_falls_back_to_default():
    p = parse_envelope(_minimal(u="loud", h="far"))
    assert p["urgency"] == 3 and p["hops"] == 0


def test_string_fields_are_length_capped():
    p = parse_envelope(_minimal(
        i="i" * 99, o="o" * 99, g="g" * 999, c="c" * 99, l="l" * 99, ln="tamiltamiltamil"))
    assert len(p["id"]) == 32
    assert len(p["origin"]) == 32
    assert len(p["gist"]) == 200
    assert len(p["category"]) == 48
    assert len(p["locationHint"]) == 64
    assert len(p["lang"]) == 8


@pytest.mark.parametrize("la,lo", [
    (91, 0), (-91, 0), (0, 181), (0, -181),      # out of range
    ("NaN", "NaN"), (float("inf"), 0),            # non-finite
    ("not-a-number", 5),
])
def test_bad_coordinates_become_none(la, lo):
    p = parse_envelope(_minimal(la=la, lo=lo))
    assert p["lat"] is None or p["lng"] is None


def test_boundary_coordinates_survive():
    p = parse_envelope(_minimal(la=-90, lo=180))
    assert p["lat"] == -90.0 and p["lng"] == 180.0


def test_bad_timestamp_becomes_zero():
    assert parse_envelope(_minimal(ts="soon"))["ts"] == 0
    assert parse_envelope(_minimal(ts="1.5"))["ts"] == 0
    assert parse_envelope(_minimal(ts=1752100000))["ts"] == 1752100000
