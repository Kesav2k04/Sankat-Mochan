#!/usr/bin/env python3
"""
verify_page_numbers.py - assert the report page states only what the data says.

    python docs/benchmarks/compute_chart_data.py
    python docs/benchmarks/verify_page_numbers.py

Exits 0 if every checked number on the page matches the value computed from the
released artefacts, 1 otherwise.

Why this exists
---------------
verify_benchmarks.py proves the artefacts support the claims. It does not prove
the *page* quotes those claims correctly - a typo, a stale copy-paste, or an
optimistic rounding could put a number on screen that no artefact backs. A
report whose headline figure has silently drifted from its own data is worse
than one with no figures at all.

So this script parses report-page/index.html and checks each load-bearing
number against chart_data.json. Every figure on the page is generated from the
same JSON by make_figures.py, so the geometry is already tied to the data; this
covers the prose, the tables and the figure captions, which are written by hand.

Scope: numbers that must match an artefact. Human-graded [H] values are checked
for presence and consistency between the places they appear, not against a
computed source - by definition there is no artefact to check them against, and
that is exactly what their tier badge says.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAGE = HERE / "report-page" / "index.html"
CHART = HERE / "chart_data.json"

failures: list[str] = []
checks = 0


def norm(html: str) -> str:
    """Strip tags and normalise entities and whitespace so prose can be matched."""
    t = re.sub(r"<[^>]+>", " ", html)
    for a, b in (
        ("&minus;", "-"), ("&ndash;", "-"), ("&mdash;", "--"), ("&nbsp;", " "),
        ("&amp;", "&"), ("&ldquo;", '"'), ("&rdquo;", '"'), ("&ge;", ">="),
        ("&rarr;", "->"), ("&middot;", "."), ("&Delta;", "D"), ("&alpha;", "a"),
        ("&kappa;", "k"), ("&times;", "x"), ("&lt;", "<"), ("&gt;", ">"),
    ):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t)


def want(label: str, needle: str, text: str) -> None:
    """The page must contain this exact string."""
    global checks
    checks += 1
    ok = needle in text
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {needle!r}")
    if not ok:
        failures.append(f"{label}: page does not contain {needle!r}")


def forbid(label: str, needle: str, text: str) -> None:
    """The page must NOT contain this string - a withdrawn or superseded claim."""
    global checks
    checks += 1
    ok = needle not in text
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: absent {needle!r}")
    if not ok:
        failures.append(f"{label}: page still contains {needle!r}")


def only_as_correction(label: str, stale: str, context: str, text: str) -> None:
    """A superseded number may appear once, and only where it is being corrected.

    Deleting the old value outright would hide the correction; leaving it loose
    would let a reader quote it. So the rule is: exactly one occurrence, inside
    the sentence that retracts it.
    """
    global checks
    checks += 1
    hits = text.count(stale)
    ok = hits == 1 and context in text
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {stale!r} appears {hits}x, "
          f"retracted={context in text}")
    if not ok:
        failures.append(
            f"{label}: {stale!r} appears {hits} time(s) and the retracting "
            f"context {context!r} was {'found' if context in text else 'NOT found'}"
        )


def main() -> int:
    if not PAGE.exists():
        print(f"missing {PAGE}", file=sys.stderr)
        return 1
    if not CHART.exists():
        print(f"missing {CHART}. Run compute_chart_data.py first.", file=sys.stderr)
        return 1

    html = PAGE.read_text(encoding="utf-8")
    text = norm(html)
    d = json.loads(CHART.read_text(encoding="utf-8"))

    c = d["contamination"]
    l = d["length"]
    r = d["relay"]
    comp = d["composition"]

    print("Report page number check")
    print("=" * 68)

    # ---------------------------------------------------------- contamination
    print("\n1. Contamination")
    want("max Jaccard", str(c["max"]), text)
    want("median Jaccard", f'{c["median"]:.3f}', text)
    want("near-duplicate threshold", str(c["near_dupe_threshold"]), text)
    want("prompts measured",
         f'{c["n_prompts_measured"]} of the {c["n_prompts_measured"] + c["n_prompts_too_short_to_measure"]}',
         text)
    want("training turns shingled", f'{c["train_turns_long_enough_to_shingle"]:,}', text)
    want("unique training turns", f'{c["train_user_turns_compared"]:,}', text)

    # ---------------------------------------------------------------- length
    print("\n2. Response length")
    want("base mean", str(l["base"]["mean"]), text)
    want("finetuned mean", str(l["finetuned"]["mean"]), text)
    want("base median", str(l["base"]["median"]), text)
    want("finetuned median", str(l["finetuned"]["median"]), text)
    want("shorter count", f'shorter on {l["shorter_on_n_prompts"]} of {l["n_pairs"]}', text)
    want("longer count", f'longer on {l["longer_on_n_prompts"]}', text)

    fr = l["bootstrap_fractional_reduction"]
    want("reduction point", f'{100 * fr["point"]:.1f}%', text)
    want("reduction CI lo", f'{100 * fr["ci95_lo"]:.1f}%', text)
    want("reduction CI hi", f'{100 * fr["ci95_hi"]:.1f}%', text)

    md = l["bootstrap_mean_diff_chars"]
    want("mean diff", str(round(abs(md["point"]))), text)
    # The page prints the interval as negatives in increasing order
    # (-259 to -112), which is the conventional ordering for a reduction.
    want("mean diff CI",
         f'-{round(abs(md["ci95_lo"]))} to -{round(abs(md["ci95_hi"]))}', text)

    # ---------------------------------------------------------------- relay
    print("\n3. Relay packets")
    req, wrong = r["packet_required"], r["packet_wrong"]
    want("required base", f'{req["base_correct"]} / {req["n"]}', text)
    want("required tuned", f'{req["finetuned_correct"]} / {req["n"]}', text)
    want("wrong-group tuned", f'{wrong["finetuned_correct"]} / {wrong["n"]}', text)
    lo = req["finetuned_ci95"][0]
    want("exact CI lower bound", f"{lo:.2f}", text)

    # ---------------------------------------------------------- composition
    print("\n4. Eval-set composition")
    want("n scored", str(comp["n"]), text)
    want("English count", str(comp["language"]["en"]), text)
    for cat, k in list(comp["category"].items())[:3]:
        want(f"category {cat}", str(k), text)

    # ------------------------------------------------- withdrawn / superseded
    print("\n5. Withdrawn and superseded claims")
    forbid("quality-per-watt as a live claim", "best quality-per-watt.", text)
    forbid("X Elite performance claim", "X Elite at", text)
    only_as_correction("stale 81.6% headline", "81.6%", "not 81.6%", text)
    only_as_correction("stale 3.11 GB", "3.11 GB", "GiB\nmislabelled".replace("\n", " "), text)

    # ------------------------------------------------------ tier discipline
    print("\n6. Tier discipline")
    for tier in ("tier--r", "tier--h", "tier--m"):
        global checks
        checks += 1
        k = html.count(tier)
        ok = k > 0
        print(f"  [{'PASS' if ok else 'FAIL'}] {tier} used: {k}")
        if not ok:
            failures.append(f"{tier} never used")

    # every figure must be generated, aria-labelled and inside a scroll region
    figs = re.findall(r"<!-- FIG-([A-Z]+) start -->(.*?)<!-- FIG-\1 end -->", html, re.S)
    checks += 1
    ok = len(figs) == 4
    print(f"  [{'PASS' if ok else 'FAIL'}] generated figure blocks: {len(figs)} (expected 4)")
    if not ok:
        failures.append(f"expected 4 generated figure blocks, found {len(figs)}")
    for name, body in figs:
        checks += 1
        good = 'role="img"' in body and "aria-label=" in body and "chart-scroll" in body
        print(f"  [{'PASS' if good else 'FAIL'}] FIG-{name} is labelled and scrollable")
        if not good:
            failures.append(f"FIG-{name} missing role/aria-label/scroll region")
        checks += 1
        inline = re.findall(r'<(?:rect|line|circle|text|tspan)[^>]*\s(?:fill|stroke)=', body)
        if inline:
            print(f"  [FAIL] FIG-{name} has {len(inline)} inline colour attribute(s)")
            failures.append(f"FIG-{name} hard-codes colour instead of using a class")
        else:
            print(f"  [PASS] FIG-{name} carries no inline colour")

    print("\n" + "=" * 68)
    if failures:
        print(f"{len(failures)} of {checks} CHECK(S) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"All {checks} page-number checks passed.")
    print("Every figure on the page is generated from chart_data.json, and every")
    print("number checked above traces to a value computed from the artefacts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
