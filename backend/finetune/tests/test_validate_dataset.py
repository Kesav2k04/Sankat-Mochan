"""Tests for the dataset gate (validate_dataset.py) — run as a subprocess exactly
the way Kaggle/Colab cells run it. stdlib-only: no torch/transformers needed."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(FT / "validate_dataset.py"), *args],
        capture_output=True, text=True, cwd=FT, timeout=120,
    )


def test_committed_sample_batch_passes():
    r = _run("data/sample.jsonl", "--allow-no-prompt-check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_committed_train_set_passes():
    r = _run("data/train.jsonl", "--allow-no-prompt-check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_corrupt_jsonl_fails_loudly(tmp_path):
    bad = tmp_path / "bad.jsonl"
    good_line = (FT / "data" / "sample.jsonl").read_text(encoding="utf-8").splitlines()[0]
    bad.write_text(good_line + "\n{not json at all\n", encoding="utf-8")
    r = _run(str(bad), "--allow-no-prompt-check")
    assert r.returncode != 0


def test_schema_violation_fails(tmp_path):
    row = json.loads((FT / "data" / "sample.jsonl").read_text(encoding="utf-8").splitlines()[0])
    row["messages"] = []            # empty conversation cannot be a training record
    bad = tmp_path / "empty.jsonl"
    bad.write_text(json.dumps(row) + "\n", encoding="utf-8")
    r = _run(str(bad), "--allow-no-prompt-check")
    assert r.returncode != 0
