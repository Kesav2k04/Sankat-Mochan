#!/usr/bin/env python3
"""
verify_benchmarks.py - reproduce every machine-checkable claim in docs/benchmarks/.

Run from the repository root:

    python docs/benchmarks/verify_benchmarks.py

Exits 0 if every assertion holds, 1 otherwise. Writes a JSON report to
docs/benchmarks/verification_report.json.

This script deliberately recomputes numbers from the released artifacts rather
than reading them from any markdown file. If a number in the docs cannot be
reproduced here, the docs mark it as human-graded rather than reproducible.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FT = ROOT / "finetune"
OUT = Path(__file__).resolve().parent / "verification_report.json"

# The Q4_0 GGUF published at huggingface.co/kesav2k04/sahayak-e2b-gguf
GGUF_BYTES = 3_349_514_592

failures: list[str] = []
report: dict = {}


def check(name: str, got, want, note: str = "") -> None:
    ok = got == want
    report[name] = {"got": got, "expected": want, "pass": ok, "note": note}
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}: got={got!r} expected={want!r}")
    if not ok:
        failures.append(f"{name}: got {got!r}, expected {want!r}")


def record(name: str, value, note: str = "") -> None:
    report[name] = {"value": value, "note": note}
    print(f"  [ .. ] {name}: {value!r}")


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalise(text: str) -> str:
    """Aggressive normalisation for contamination matching."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    # keep latin alphanumerics plus Devanagari..Malayalam ranges
    return re.sub(r"[^a-z0-9ऀ-ൿ]+", "", text)


def shingles(text: str, n: int = 8) -> set[str]:
    return {text[i : i + n] for i in range(max(0, len(text) - n + 1))}


def main() -> int:
    print("Sahayak-E2B benchmark verification")
    print("=" * 68)

    train = load_jsonl(FT / "data" / "train.jsonl")
    val = load_jsonl(FT / "data" / "val.jsonl")
    holdout = load_jsonl(FT / "data" / "eval_holdout.jsonl")
    questions = load_csv(FT / "eval_questions.csv")
    ft_rows = load_csv(FT / "eval_results.csv")
    base_rows = load_csv(FT / "eval_results_base.csv")

    # ---------------------------------------------------------------- split
    print("\n1. Dataset split")
    check("split.train", len(train), 1628)
    check("split.val", len(val), 172)
    check("split.holdout", len(holdout), 150)
    check("split.total", len(train) + len(val) + len(holdout), 1950)

    # ------------------------------------------------------- eval provenance
    print("\n2. Evaluation provenance")
    check("eval.n_questions", len(questions), 50)
    check("eval.n_rows_finetuned", len(ft_rows), 50)
    check("eval.n_rows_base", len(base_rows), 50)
    qids = {r["id"] for r in questions}
    hids = {r.get("id") for r in holdout}
    check("eval.is_subset_of_holdout", qids <= hids, True,
          "the 50 scored questions must come from the 150 held-out records")
    check("eval.holdout_unscored", len(hids - qids), 100,
          "held-out records that exist but were never scored")
    check("eval.empty_answers_finetuned",
          sum(1 for r in ft_rows if not (r["model_answer"] or "").strip()), 0)
    check("eval.empty_answers_base",
          sum(1 for r in base_rows if not (r["model_answer"] or "").strip()), 0)

    # ------------------------------------------------------- contamination
    print("\n3. Train/eval contamination")
    train_users = [
        normalise(m.get("content", ""))
        for rec in train
        for m in rec.get("messages", [])
        if m.get("role") == "user"
    ]
    train_set = set(train_users)
    record("contamination.train_user_turns", len(train_users))
    exact = [r["id"] for r in questions if normalise(r["question"]) in train_set]
    check("contamination.exact_overlap", len(exact), 0, f"ids={exact}")

    train_grams = [shingles(u) for u in train_set if len(u) > 40]
    worst_id, worst_j = None, 0.0
    for row in questions:
        qn = normalise(row["question"])
        if len(qn) < 40:
            continue
        qg = shingles(qn)
        for tg in train_grams:
            inter = len(qg & tg)
            if not inter:
                continue
            j = inter / len(qg | tg)
            if j > worst_j:
                worst_id, worst_j = row["id"], j
    record("contamination.max_jaccard", round(worst_j, 4),
           f"closest eval question to any training prompt: {worst_id}")
    check("contamination.near_dupes_over_0.55", worst_j >= 0.55, False,
          "8-gram Jaccard threshold for a near-duplicate")

    # --------------------------------------------- relay packet compliance
    print("\n4. Relay packet compliance (automatic validator)")
    truthy = lambda v: (v or "").strip().lower() in ("true", "1", "yes", "y")
    base_by_id = {r["id"]: r for r in base_rows}

    # A packet is the correct output only for basic/noisy relay prompts.
    # ambiguous -> ask for the missing fields; adversarial -> refuse to broadcast.
    expect_packet = {"basic", "noisy"}
    buckets = {
        "packet_expected": {"ids": [], "base": 0, "ft": 0},
        "packet_not_expected": {"ids": [], "base": 0, "ft": 0},
    }
    for row in ft_rows:
        if row["category"] != "relay":
            continue
        key = "packet_expected" if row["difficulty"] in expect_packet else "packet_not_expected"
        buckets[key]["ids"].append(row["id"])
        if truthy(row.get("relay_packet_ok")):
            buckets[key]["ft"] += 1
        if truthy(base_by_id[row["id"]].get("relay_packet_ok")):
            buckets[key]["base"] += 1

    check("relay.expected.n", len(buckets["packet_expected"]["ids"]), 4,
          str(buckets["packet_expected"]["ids"]))
    check("relay.expected.base_valid", buckets["packet_expected"]["base"], 0)
    check("relay.expected.finetuned_valid", buckets["packet_expected"]["ft"], 4)
    check("relay.not_expected.n", len(buckets["packet_not_expected"]["ids"]), 4,
          str(buckets["packet_not_expected"]["ids"]))
    check("relay.not_expected.base_emitted", buckets["packet_not_expected"]["base"], 0)
    check("relay.not_expected.finetuned_emitted", buckets["packet_not_expected"]["ft"], 0,
          "correctly abstaining is the right behaviour here")

    scored = sum(1 for r in ft_rows if (r.get("relay_packet_ok") or "").strip())
    check("relay.rows_with_validator", scored, 8,
          "only the 8 relay-category rows carry the flag; multilingual relay "
          "prompts are NOT machine-validated")

    # ------------------------------------------------------------ verbosity
    print("\n5. Answer length (proxy for operator-terse style)")
    base_len = [len(r["model_answer"] or "") for r in base_rows]
    ft_len = [len(r["model_answer"] or "") for r in ft_rows]
    record("verbosity.base_mean_chars", round(statistics.mean(base_len)))
    record("verbosity.finetuned_mean_chars", round(statistics.mean(ft_len)))
    record("verbosity.base_median_chars", round(statistics.median(base_len)))
    record("verbosity.finetuned_median_chars", round(statistics.median(ft_len)))
    reduction = 1 - statistics.mean(ft_len) / statistics.mean(base_len)
    record("verbosity.mean_reduction_pct", round(100 * reduction, 1))
    check("verbosity.finetuned_is_shorter", statistics.mean(ft_len) < statistics.mean(base_len), True)

    # ------------------------------------------------------------ artefacts
    print("\n6. Published artefact size (units discipline)")
    record("gguf.bytes", GGUF_BYTES, "huggingface.co/kesav2k04/sahayak-e2b-gguf")
    record("gguf.GiB", round(GGUF_BYTES / 2**30, 3))
    record("gguf.GB", round(GGUF_BYTES / 1e9, 3))
    check("gguf.GiB_is_3.119", round(GGUF_BYTES / 2**30, 2) == 3.12, True,
          "llama.cpp prints GiB; the model card's 3.35 GB is decimal GB - same file")

    # -------------------------------------------------------------- summary
    print("\n" + "=" * 68)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report written to {OUT.relative_to(ROOT)}")
    if failures:
        print(f"\n{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nAll {sum(1 for v in report.values() if 'pass' in v)} assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
