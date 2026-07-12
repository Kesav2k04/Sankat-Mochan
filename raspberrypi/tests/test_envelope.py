"""Unit tests for envelope.py — CONTRACT 1 (the SOS wire format) plus the binary
voice frames. Every decode() input is untrusted mesh data (rule #8), so the
rejection paths matter as much as the round-trips."""
from __future__ import annotations

import json

import pytest

import envelope as env
from envelope import (DECODE_TOLERANCE, MAX_BYTES, MAX_HOPS, MAX_VOICE_CHUNK,
                      Envelope, VoiceChunk, VoiceNack, decode, digest,
                      message_text, preview)

TAMIL = "தண்ணீர் வேகமாக ஏறுகிறது, நாங்கள் மாடியில் சிக்கிக்கொண்டோம், சீக்கிரம் வாருங்கள்"


def _sos(**over) -> Envelope:
    base = dict(id="c363-0", type="SOS", origin="c363", urgency=4,
                category="flood", location_hint="Block C stairwell",
                gist="water rising fast", lang="en", lat=12.9332, lng=77.6248,
                ts=1752100000, hops=2)
    base.update(over)
    return Envelope(**base)


# ---- encode -----------------------------------------------------------------

def test_encode_round_trips_through_decode():
    e = _sos()
    d = decode(e.encode())
    assert d == e


def test_encode_always_fits_the_wire_even_for_indic_text():
    e = _sos(gist=TAMIL * 4, lang="ta")
    raw = e.encode()
    assert len(raw) <= MAX_BYTES
    d = decode(raw)
    assert d is not None
    # the trim must keep a usable prefix of the victim's words, not wipe them
    assert d.gist and TAMIL.startswith(d.gist[:10])


def test_encode_honours_a_smaller_link_budget():
    raw = _sos(gist="x" * 200).encode(max_bytes=234)   # UNO Q router-bridge cap
    assert len(raw) <= 234
    assert decode(raw) is not None


def test_trim_backs_off_to_a_word_boundary():
    e = _sos(gist=("word " * 60).strip())
    raw = e.encode()
    assert len(raw) <= MAX_BYTES
    assert not decode(raw).gist.endswith("wor")   # never a mid-word stump


def test_bumped_clamps_hops():
    assert _sos(hops=3).bumped().hops == 4
    assert _sos(hops=MAX_HOPS).bumped().hops == MAX_HOPS


# ---- decode: rejection (untrusted input) ---------------------------------------

@pytest.mark.parametrize("raw", [
    b"",
    b"\xff\xfe\x00garbage",
    b"[1,2,3]",
    b"{not json",
    json.dumps({"i": "x", "t": "SOS"}).encode(),          # missing origin
    json.dumps({"i": "x", "t": "EVIL", "o": "y"}).encode(),
    b"{" + b" " * (MAX_BYTES + DECODE_TOLERANCE) + b"}",  # oversized
])
def test_decode_drops_garbage(raw):
    assert decode(raw) is None


def test_decode_clamps_untrusted_ranges():
    # split across two frames so each stays inside the 252-byte decode gate
    a = {"i": "a" * 40, "t": "SOS", "o": "b" * 40, "u": 99, "h": 99,
         "la": 123.0, "lo": 77.0, "ts": -5}
    d = decode(json.dumps(a, separators=(",", ":")).encode())
    assert d is not None
    assert len(d.id) == 32 and len(d.origin) == 32
    assert d.urgency == 5 and d.hops == MAX_HOPS
    assert d.lat is None          # 123 is out of range -> dropped, not clamped
    assert d.ts == 0              # negative timestamps are meaningless

    b = {"i": "x", "t": "SOS", "o": "y", "c": "c" * 60, "l": "l" * 70, "ln": "x" * 20}
    d = decode(json.dumps(b, separators=(",", ":")).encode())
    assert d is not None
    assert len(d.category) == 48 and len(d.location_hint) == 64
    assert d.lang == "x" * 8


def test_decode_rejects_bool_masquerading_as_numbers():
    wire = {"i": "x", "t": "SOS", "o": "y", "u": True, "h": True, "la": True, "lo": 77.0}
    d = decode(json.dumps(wire).encode())
    assert d.urgency == 3 and d.hops == 0 and d.lat is None


# ---- voice chunks ----------------------------------------------------------------

def test_voice_chunk_round_trip():
    c = VoiceChunk(origin="ph1", seq=7, index=3, total=9,
                   payload=b"\x01\x02" * 50, hops=2, codec=2, attempt=1)
    d = decode(c.encode())
    assert d == c
    assert d.clip_id == "ph1-v7"
    assert d.id == "ph1-v7-3#1"


def test_voice_ids_differ_per_attempt_so_retries_survive_dedup():
    a = VoiceChunk(origin="ph1", seq=1, index=0, total=2, payload=b"x")
    b = VoiceChunk(origin="ph1", seq=1, index=0, total=2, payload=b"x", attempt=1)
    assert a.id != b.id and a.clip_id == b.clip_id


def test_voice_frame_never_confused_with_json():
    c = VoiceChunk(origin="ph1", seq=1, index=0, total=1, payload=b"data")
    raw = c.encode()
    assert raw[0] == env.VOICE_MAGIC
    assert _sos().encode()[0] == ord("{")


def test_oversized_voice_payload_refused_at_pack_time():
    with pytest.raises(ValueError):
        VoiceChunk(origin="ph1", seq=1, index=0, total=1,
                   payload=b"x" * (MAX_VOICE_CHUNK + 1)).encode()


@pytest.mark.parametrize("mutate", [
    lambda r: b"\xa4" + r[1:],                      # wrong magic -> not voice, bad utf8
    lambda r: r[:1] + b"\x09" + r[2:],              # wrong version
    lambda r: r + b"extra",                          # declared length mismatch
    lambda r: r[:-1],                                # truncated payload
])
def test_corrupted_voice_frames_are_dropped(mutate):
    raw = VoiceChunk(origin="ph1", seq=1, index=0, total=2, payload=b"abcd").encode()
    assert decode(mutate(raw)) is None


def test_voice_frame_field_range_gates():
    good = dict(origin="ph1", seq=1, index=0, total=2, payload=b"abcd")
    assert decode(VoiceChunk(**{**good, "codec": 9}).encode()) is None       # unknown codec
    assert decode(VoiceChunk(**{**good, "index": 2}).encode()) is None       # index >= total
    assert decode(VoiceChunk(**{**good, "attempt": 7}).encode()) is None     # retries exhausted


# ---- voice NACK -------------------------------------------------------------------

def test_nack_round_trip_and_bitmap():
    n = VoiceNack(origin="rsp1", clip_origin="ph1", seq=7, total=11, missing=(0, 3, 10))
    d = decode(n.encode())
    assert isinstance(d, VoiceNack)
    assert d.missing == (0, 3, 10)
    assert d.clip_id == "ph1-v7"
    assert "rsp1" in d.id            # the REQUESTER owns the id


def test_nack_for_nothing_is_malformed():
    n = VoiceNack(origin="rsp1", clip_origin="ph1", seq=7, total=8, missing=())
    assert decode(n.encode()) is None


def test_two_responders_produce_distinct_nack_ids():
    a = VoiceNack(origin="rsp1", clip_origin="ph1", seq=7, total=8, missing=(1,))
    b = VoiceNack(origin="rsp2", clip_origin="ph1", seq=7, total=8, missing=(1,))
    assert a.id != b.id


# ---- log rendering (rule #8/#9: untrusted text on log lines) ------------------------

def test_digest_is_stable_and_short():
    raw = _sos().encode()
    assert digest(raw) == digest(raw)
    assert len(digest(raw)) == 12
    assert digest(raw) != digest(raw + b" ")


def test_preview_strips_log_forgery_control_chars():
    forged = "help\n02:09:13 INFO sankat: probe OK\r\x1b[31m"
    line = preview(forged)
    assert "\n" not in line and "\r" not in line and "\x1b" not in line
    assert line.startswith("help")


def test_preview_caps_length_with_ellipsis():
    assert len(preview("x" * 500, limit=60)) == 60
    assert preview("x" * 500).endswith("…")


def test_message_text_quotes_and_labels_language():
    assert message_text(_sos(gist="help us", lang="ta")) == '"help us" [ta]'
    assert message_text(_sos(gist="help us", lang="en")) == '"help us"'
    assert message_text(VoiceChunk(origin="p", seq=1, index=0, total=1, payload=b"x")) == ""
