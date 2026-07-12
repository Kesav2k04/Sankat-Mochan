"""
Unit tests for the voice reassembly + NACK repair loop (uplink.VoiceAssembler).

No hardware, no network — pure state-machine tests with a fake clock so the quiet-period
timing is deterministic. Run directly (`python test_voice_assembler.py`) or under pytest.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raspberrypi/ modules

import envelope as env
import uplink


class Clock:
    """Stand-in for time.monotonic() so quiet-period gating is testable without sleeping."""
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _install_clock(monkeypatch_target=uplink) -> Clock:
    clock = Clock()
    monkeypatch_target.time.monotonic = clock  # type: ignore[attr-defined]
    return clock


def chunk(index: int, total: int, *, origin="3957", seq=0, attempt=0,
          payload: bytes | None = None) -> env.VoiceChunk:
    return env.VoiceChunk(origin=origin, seq=seq, index=index, total=total,
                          payload=payload if payload is not None else bytes([65 + index]),
                          attempt=attempt)


def test_clean_assembly_completes_in_order():
    _install_clock()
    a = uplink.VoiceAssembler()
    assert a.accept(chunk(0, 3)).started_clip is True
    assert a.accept(chunk(1, 3)).complete is None
    out = a.accept(chunk(2, 3))
    assert out.complete is not None
    assert out.complete.audio == b"ABC"
    assert a.count() == 0


def test_out_of_order_and_duplicate_frames():
    _install_clock()
    a = uplink.VoiceAssembler()
    assert a.accept(chunk(2, 3)).started_clip is True
    assert a.accept(chunk(0, 3)).filled_gap is True
    # a duplicate of an already-held index must not be counted as a new gap-fill
    assert a.accept(chunk(0, 3)).filled_gap is False
    out = a.accept(chunk(1, 3))
    assert out.complete is not None and out.complete.audio == b"ABC"


def test_stray_mismatched_chunk_does_not_destroy_good_clip():
    _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(0, 3))
    # same clip_id (origin+seq) but a different `total` — corruption/stray. Must be ignored,
    # not allowed to delete the clip we are carefully rebuilding.
    stray = a.accept(chunk(0, 5))
    assert stray.complete is None
    assert a.count() == 1
    a.accept(chunk(1, 3))
    out = a.accept(chunk(2, 3))
    assert out.complete is not None and out.complete.audio == b"ABC"


def test_no_nack_while_clip_is_still_active():
    clock = _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(0, 3))
    clock.advance(1.0)  # less than the quiet period
    nacks, abandoned = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert nacks == [] and abandoned == []


def test_no_nack_when_nothing_missing():
    clock = _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(0, 1))  # single-piece clip completes immediately, leaves no state
    clock.advance(10.0)
    nacks, abandoned = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert nacks == [] and abandoned == []


def test_stalled_clip_emits_nack_then_repairs():
    clock = _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(0, 3))
    a.accept(chunk(2, 3))          # piece 1 is lost
    clock.advance(5.0)             # go quiet past the 4s threshold
    nacks, abandoned = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert abandoned == [] and len(nacks) == 1
    nack = nacks[0]
    assert nack.origin == "PiG1"          # requester is the Pi
    assert nack.clip_origin == "3957"     # clip author, so the phone knows to resend
    assert nack.seq == 0 and nack.total == 3
    assert nack.missing == (1,)
    assert nack.attempt == 0
    # the phone honours it: resends piece 1 with a bumped attempt (a fresh mesh id)
    out = a.accept(chunk(1, 3, attempt=1))
    assert out.is_repair and out.filled_gap
    assert out.complete is not None and out.complete.audio == b"ABC"
    assert a.count() == 0


def test_renack_backs_off_by_one_quiet_period_and_increments_attempt():
    clock = _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(0, 2))          # piece 1 lost
    clock.advance(5.0)
    first, _ = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert len(first) == 1 and first[0].attempt == 0
    # immediately after asking, the clock has been reset — no repeat request yet
    again, _ = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert again == []
    clock.advance(5.0)
    second, _ = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert len(second) == 1 and second[0].attempt == 1


def test_clip_is_abandoned_after_the_attempt_budget():
    clock = _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(0, 2))          # piece 1 never arrives
    seen_attempts = []
    for _ in range(env.MAX_ATTEMPTS - 1):   # 6 requests, matching the phone's cap
        clock.advance(5.0)
        nacks, abandoned = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
        assert abandoned == [] and len(nacks) == 1
        seen_attempts.append(nacks[0].attempt)
    assert seen_attempts == list(range(env.MAX_ATTEMPTS - 1))  # 0..5
    # one more quiet period: budget spent -> drop it so the dashboard stops showing it stuck
    clock.advance(5.0)
    nacks, abandoned = a.due_for_nack(quiet_s=4.0, requester_origin="PiG1")
    assert nacks == []
    assert len(abandoned) == 1
    assert abandoned[0].clip_id == "3957-v0" and abandoned[0].missing == 1
    assert a.count() == 0


def test_nack_wire_roundtrip_is_decodable_by_the_phone_format():
    _install_clock()
    a = uplink.VoiceAssembler()
    a.accept(chunk(3, 8))          # only piece 3 arrived; 0,1,2,4,5,6,7 missing
    # force it due
    nacks, _ = a.due_for_nack(quiet_s=0.0, requester_origin="PiG1")
    assert len(nacks) == 1
    decoded = env.decode(nacks[0].encode())
    assert isinstance(decoded, env.VoiceNack)
    assert decoded.clip_origin == "3957"
    assert decoded.missing == (0, 1, 2, 4, 5, 6, 7)


def _run_all():
    import time as _time
    saved = _time.monotonic
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"  ok  {name}")
                passed += 1
    finally:
        uplink.time.monotonic = saved  # restore the real clock
    print(f"\n{passed} passed")


if __name__ == "__main__":
    _run_all()
