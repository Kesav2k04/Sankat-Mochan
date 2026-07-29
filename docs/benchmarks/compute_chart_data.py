#!/usr/bin/env python3
"""
compute_chart_data.py - derive every figure on the evaluation report page.

Run from the repository root:

    python docs/benchmarks/compute_chart_data.py

Writes docs/benchmarks/chart_data.json. Every number in that file is computed
here from the released artefacts in finetune/; nothing is transcribed from a
markdown file and nothing is estimated.

Companion to verify_benchmarks.py, which asserts the headline claims. This
script produces the *distributions* behind them, so the report page can plot
real data instead of a summary bar.

Determinism: the bootstrap uses a fixed seed, so two runs on the same artefacts
produce byte-identical output.

What is deliberately NOT computed here
--------------------------------------
Confidence intervals for the per-category rubric accuracies. Those grades exist
only as prose in finetune/eval_comparison.md - there is no per-item score
column in either CSV - so there is no sample to interval. Drawing error bars
from a category mean and an n would be inventing the variance. The page plots
those categories as points with n annotated and says why they carry no bars.
See 03-LIMITS-AND-ROADMAP.md G1 and G3.
"""

from __future__ import annotations

import csv
import json
import random
import re
import statistics
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FT = ROOT / "finetune"
OUT = Path(__file__).resolve().parent / "chart_data.json"

SEED = 20260729
BOOTSTRAP_N = 20000
NEAR_DUPE_THRESHOLD = 0.55


# --------------------------------------------------------------------- loaders
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
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[^a-z0-9ऀ-ൿ]+", "", text)


def shingles(text: str, n: int = 8) -> set[str]:
    return {text[i : i + n] for i in range(max(0, len(text) - n + 1))}


# ------------------------------------------------------------------ statistics
def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval. Valid at n=4, which Wald and Wilson are not.

    Uses the Beta quantile relation without SciPy: invert the Beta CDF by
    bisection on the regularised incomplete beta function, which we get from
    the binomial tail sum. For the tiny n here this is exact to float
    precision and costs nothing.
    """
    if n == 0:
        return (0.0, 1.0)

    def binom_cdf_at_least(p: float, k0: int) -> float:
        # P(X >= k0) for X ~ Bin(n, p)
        total = 0.0
        for i in range(k0, n + 1):
            total += _choose(n, i) * p**i * (1 - p) ** (n - i)
        return total

    def binom_cdf_at_most(p: float, k0: int) -> float:
        total = 0.0
        for i in range(0, k0 + 1):
            total += _choose(n, i) * p**i * (1 - p) ** (n - i)
        return total

    lo = 0.0
    if k > 0:
        a, b = 0.0, 1.0
        for _ in range(200):
            m = (a + b) / 2
            if binom_cdf_at_least(m, k) < alpha / 2:
                a = m
            else:
                b = m
        lo = (a + b) / 2

    hi = 1.0
    if k < n:
        a, b = 0.0, 1.0
        for _ in range(200):
            m = (a + b) / 2
            if binom_cdf_at_most(m, k) > alpha / 2:
                a = m
            else:
                b = m
        hi = (a + b) / 2

    return (lo, hi)


def _choose(n: int, k: int) -> float:
    from math import comb

    return float(comb(n, k))


def bootstrap_paired_mean_diff(
    a: list[float], b: list[float], reps: int, seed: int
) -> dict:
    """Percentile bootstrap on the paired mean difference (b - a).

    Paired, because both models answered the same 50 prompts. Resampling
    prompts rather than responses is what keeps the pairing intact.
    """
    assert len(a) == len(b)
    n = len(a)
    diffs = [b[i] - a[i] for i in range(n)]
    rng = random.Random(seed)
    means = []
    idx = range(n)
    for _ in range(reps):
        sample = [diffs[rng.choice(idx)] for _ in idx]
        means.append(sum(sample) / n)
    means.sort()
    return {
        "point": statistics.mean(diffs),
        "ci95_lo": means[int(0.025 * reps)],
        "ci95_hi": means[int(0.975 * reps)],
        "reps": reps,
        "seed": seed,
    }


def bootstrap_ratio(a: list[float], b: list[float], reps: int, seed: int) -> dict:
    """Percentile bootstrap on 1 - mean(b)/mean(a): the fractional reduction."""
    assert len(a) == len(b)
    n = len(a)
    rng = random.Random(seed)
    vals = []
    idx = range(n)
    for _ in range(reps):
        pick = [rng.choice(idx) for _ in idx]
        ma = sum(a[i] for i in pick) / n
        mb = sum(b[i] for i in pick) / n
        if ma > 0:
            vals.append(1 - mb / ma)
    vals.sort()
    m = len(vals)
    return {
        "point": 1 - statistics.mean(b) / statistics.mean(a),
        "ci95_lo": vals[int(0.025 * m)],
        "ci95_hi": vals[int(0.975 * m)],
        "reps": reps,
        "seed": seed,
    }


def histogram(values: list[float], lo: float, hi: float, bins: int) -> dict:
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        if v < lo:
            continue
        b = min(int((v - lo) / width), bins - 1)
        counts[b] += 1
    return {
        "lo": lo,
        "hi": hi,
        "bins": bins,
        "bin_width": width,
        "counts": counts,
        "edges": [round(lo + i * width, 4) for i in range(bins + 1)],
    }


# ------------------------------------------------------------------------ main
def main() -> int:
    train = load_jsonl(FT / "data" / "train.jsonl")
    questions = load_csv(FT / "eval_questions.csv")
    ft_rows = load_csv(FT / "eval_results.csv")
    base_rows = load_csv(FT / "eval_results_base.csv")

    data: dict = {
        "_provenance": {
            "generated_by": "docs/benchmarks/compute_chart_data.py",
            "inputs": [
                "finetune/data/train.jsonl",
                "finetune/eval_questions.csv",
                "finetune/eval_results.csv",
                "finetune/eval_results_base.csv",
            ],
            "seed": SEED,
            "note": "Every value here is computed from the listed inputs. "
            "No value is transcribed from prose and none is estimated.",
        }
    }

    # ------------------------------------------------ 1. contamination spread
    # The verifier reports only the maximum. The shape of the whole distribution
    # is the actual evidence: if the eval set were contaminated, this histogram
    # would have a right tail. It has none.
    train_users = {
        normalise(m.get("content", ""))
        for rec in train
        for m in rec.get("messages", [])
        if m.get("role") == "user"
    }
    train_grams = [shingles(u) for u in train_users if len(u) > 40]

    per_prompt = []
    for row in questions:
        qn = normalise(row["question"])
        if len(qn) < 40:
            per_prompt.append({"id": row["id"], "max_jaccard": None, "skipped": True})
            continue
        qg = shingles(qn)
        best = 0.0
        for tg in train_grams:
            inter = len(qg & tg)
            if not inter:
                continue
            j = inter / len(qg | tg)
            if j > best:
                best = j
        per_prompt.append(
            {"id": row["id"], "max_jaccard": round(best, 4), "skipped": False}
        )

    scored_j = [p["max_jaccard"] for p in per_prompt if not p["skipped"]]
    data["contamination"] = {
        "train_user_turns_compared": len(train_users),
        "train_turns_long_enough_to_shingle": len(train_grams),
        "n_prompts_measured": len(scored_j),
        "n_prompts_too_short_to_measure": len(per_prompt) - len(scored_j),
        "near_dupe_threshold": NEAR_DUPE_THRESHOLD,
        "max": max(scored_j),
        "median": round(statistics.median(scored_j), 4),
        "mean": round(statistics.mean(scored_j), 4),
        "over_threshold": sum(1 for j in scored_j if j >= NEAR_DUPE_THRESHOLD),
        "histogram": histogram(scored_j, 0.0, 0.60, 12),
        "per_prompt": per_prompt,
    }

    # ------------------------------------------------------ 2. answer lengths
    # Paired: both arms answered the same 50 prompts, matched on id.
    ft_by_id = {r["id"]: r for r in ft_rows}
    base_by_id = {r["id"]: r for r in base_rows}
    ids = [r["id"] for r in questions if r["id"] in ft_by_id and r["id"] in base_by_id]

    base_len = [len(base_by_id[i]["model_answer"] or "") for i in ids]
    ft_len = [len(ft_by_id[i]["model_answer"] or "") for i in ids]

    data["length"] = {
        "n_pairs": len(ids),
        "base": {
            "mean": round(statistics.mean(base_len), 1),
            "median": statistics.median(base_len),
            "min": min(base_len),
            "max": max(base_len),
            "p25": round(statistics.quantiles(base_len, n=4)[0], 1),
            "p75": round(statistics.quantiles(base_len, n=4)[2], 1),
        },
        "finetuned": {
            "mean": round(statistics.mean(ft_len), 1),
            "median": statistics.median(ft_len),
            "min": min(ft_len),
            "max": max(ft_len),
            "p25": round(statistics.quantiles(ft_len, n=4)[0], 1),
            "p75": round(statistics.quantiles(ft_len, n=4)[2], 1),
        },
        "shorter_on_n_prompts": sum(1 for i in range(len(ids)) if ft_len[i] < base_len[i]),
        "longer_on_n_prompts": sum(1 for i in range(len(ids)) if ft_len[i] > base_len[i]),
        "bootstrap_mean_diff_chars": bootstrap_paired_mean_diff(
            base_len, ft_len, BOOTSTRAP_N, SEED
        ),
        "bootstrap_fractional_reduction": bootstrap_ratio(
            base_len, ft_len, BOOTSTRAP_N, SEED
        ),
        "pairs": [
            {"id": ids[i], "base": base_len[i], "finetuned": ft_len[i]}
            for i in range(len(ids))
        ],
    }

    # ------------------------------------------------ 3. relay packets, exact
    truthy = lambda v: (v or "").strip().lower() in ("true", "1", "yes", "y")
    expect_packet = {"basic", "noisy"}
    groups = {"packet_required": [], "packet_wrong": []}
    for row in ft_rows:
        if row["category"] != "relay":
            continue
        key = "packet_required" if row["difficulty"] in expect_packet else "packet_wrong"
        groups[key].append(row["id"])

    relay = {}
    for key, gids in groups.items():
        n = len(gids)
        b = sum(1 for i in gids if truthy(base_by_id[i].get("relay_packet_ok")))
        f = sum(1 for i in gids if truthy(ft_by_id[i].get("relay_packet_ok")))
        # For packet_required a packet is correct, so k = emitted.
        # For packet_wrong the correct count is n - emitted.
        b_ok = b if key == "packet_required" else n - b
        f_ok = f if key == "packet_required" else n - f
        relay[key] = {
            "ids": gids,
            "n": n,
            "base_emitted": b,
            "finetuned_emitted": f,
            "base_correct": b_ok,
            "finetuned_correct": f_ok,
            "base_ci95": [round(x, 4) for x in clopper_pearson(b_ok, n)],
            "finetuned_ci95": [round(x, 4) for x in clopper_pearson(f_ok, n)],
        }
    relay["_note"] = (
        "Clopper-Pearson exact intervals. At n=4 a perfect 4/4 still has a lower "
        "bound near 0.40 - the point estimate is real, the precision is not."
    )
    data["relay"] = relay

    # -------------------------------------------- 4. eval-set composition
    def tally(rows: list[dict], field: str) -> dict:
        out: dict[str, int] = {}
        for r in rows:
            out[r[field]] = out.get(r[field], 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    data["composition"] = {
        "n": len(questions),
        "category": tally(questions, "category"),
        "difficulty": tally(questions, "difficulty"),
        "language": tally(questions, "language"),
    }

    # ------------------------------------------------------------------ write
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    c = data["contamination"]
    l = data["length"]
    print("chart data written to", OUT.relative_to(ROOT))
    print()
    print(f"contamination  n={c['n_prompts_measured']} measured, "
          f"max={c['max']}, median={c['median']}, "
          f"over {NEAR_DUPE_THRESHOLD}: {c['over_threshold']}")
    print(f"length         base mean {l['base']['mean']} -> "
          f"finetuned {l['finetuned']['mean']} chars")
    fr = l["bootstrap_fractional_reduction"]
    print(f"               reduction {100*fr['point']:.1f}% "
          f"(95% CI {100*fr['ci95_lo']:.1f}% to {100*fr['ci95_hi']:.1f}%)")
    print(f"               shorter on {l['shorter_on_n_prompts']}/{l['n_pairs']} prompts")
    for k in ("packet_required", "packet_wrong"):
        r = data["relay"][k]
        print(f"relay {k:16s} base {r['base_correct']}/{r['n']} "
              f"CI[{r['base_ci95'][0]:.2f},{r['base_ci95'][1]:.2f}]  "
              f"tuned {r['finetuned_correct']}/{r['n']} "
              f"CI[{r['finetuned_ci95'][0]:.2f},{r['finetuned_ci95'][1]:.2f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
