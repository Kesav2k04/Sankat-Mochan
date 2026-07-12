"""Unit tests for chainlog.py — the append-only hop log and the `run.sh proof`
summary. The proof rule under test: a message counts as LoRa-delivered only when
the SAME payload hash appears in LORA_TX on one radio and LORA_RX on ANOTHER."""
from __future__ import annotations

import json

import chainlog as clog


def _emit_rows(path, rows):
    log = clog.ChainLog(path)
    for event, fields in rows:
        log.emit(event, "gateway", **fields)
    log.close()


def test_emit_writes_narrow_jsonl(tmp_path):
    path = tmp_path / "chain.jsonl"
    _emit_rows(path, [(clog.LORA_TX, {"msg_id": "m1", "sha": "abc", "radio": "A",
                                      "rssi_dbm": None})])
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["event"] == "LORA_TX"
    assert row["msg_id"] == "m1"
    assert "rssi_dbm" not in row            # unset optionals are dropped
    assert "t_wall" in row and "t_rel_ms" in row


def test_summarise_proves_only_a_real_air_crossing(tmp_path):
    path = tmp_path / "chain.jsonl"
    _emit_rows(path, [
        # m-yes: TX on radio A, RX of the same sha on radio B  -> proved
        (clog.LORA_TX, {"msg_id": "m-yes", "sha": "s1", "radio": "A"}),
        (clog.LORA_RX, {"msg_id": "m-yes", "sha": "s1", "radio": "B",
                        "rssi_dbm": -97, "snr_db": 7.5}),
        # m-loop: TX and RX on the SAME radio -> an in-process hand-off, not proof
        (clog.LORA_TX, {"msg_id": "m-loop", "sha": "s2", "radio": "A"}),
        (clog.LORA_RX, {"msg_id": "m-loop", "sha": "s2", "radio": "A"}),
        # m-mut: hashes differ -> different bytes, not proof
        (clog.LORA_TX, {"msg_id": "m-mut", "sha": "s3", "radio": "A"}),
        (clog.LORA_RX, {"msg_id": "m-mut", "sha": "s3x", "radio": "B"}),
        # m-never: only received via BLE, never on the air
        (clog.BLE_RX, {"msg_id": "m-never", "sha": "s4"}),
    ])
    out = clog.summarise(path)
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("m-")}
    assert "YES" in lines["m-yes"] and "A -> B" in lines["m-yes"]
    assert "-97 dBm" in lines["m-yes"]
    assert "NO" in lines["m-loop"]
    assert "NO" in lines["m-mut"]
    assert "never transmitted" in lines["m-never"]


def test_summarise_survives_a_corrupt_line(tmp_path):
    path = tmp_path / "chain.jsonl"
    _emit_rows(path, [(clog.LORA_TX, {"msg_id": "m1", "sha": "s1", "radio": "A"})])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{torn line after a crash\n")
    assert "m1" in clog.summarise(path)


def test_summarise_empty_log(tmp_path):
    path = tmp_path / "chain.jsonl"
    path.write_text("", encoding="utf-8")
    assert "No envelopes" in clog.summarise(path)
