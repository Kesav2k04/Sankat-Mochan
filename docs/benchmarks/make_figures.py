#!/usr/bin/env python3
"""
make_figures.py - emit the report page's figures as inline SVG.

    python docs/benchmarks/compute_chart_data.py   # first: derive the numbers
    python docs/benchmarks/make_figures.py         # then: draw them

Writes docs/benchmarks/figures.svg.html - a fragment per figure, pasted into
report-page/index.html. The page stays a single self-contained file with no
chart library and no runtime data fetch; this script is how the shapes in it
stay honest, because every coordinate comes from chart_data.json.

Colours are never written here. Every fill and stroke is a CSS class the page
defines from its own design tokens, so the figures cannot drift from the theme
and no colour value is hard-coded into markup.

Regenerating after the artefacts change:
    python docs/benchmarks/compute_chart_data.py && python docs/benchmarks/make_figures.py
then replace the marked blocks in report-page/index.html.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "chart_data.json"
OUT = HERE / "figures.svg.html"


def esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def n(x: float) -> str:
    """Trim float noise out of the markup."""
    r = round(float(x), 2)
    return str(int(r)) if r == int(r) else str(r)


# ---------------------------------------------------------------------------
def fig_contamination(d: dict) -> str:
    c = d["contamination"]
    h = c["histogram"]
    counts = h["counts"]
    hi = h["hi"]
    top = max(counts)
    # round the y axis up to a clean multiple of 8
    ymax = ((top + 7) // 8) * 8

    X0, X1 = 46.0, 624.0
    Y0, Y1 = 176.0, 24.0          # Y0 = baseline, Y1 = top of plot
    W = X1 - X0
    H = Y0 - Y1
    bw = W / len(counts)

    def x(v: float) -> float:
        return X0 + (v / hi) * W

    def y(k: float) -> float:
        return Y0 - (k / ymax) * H

    p: list[str] = []
    p.append(
        '<svg class="chart" viewBox="0 0 660 232" role="img" '
        f'aria-label="Histogram of maximum 8-gram Jaccard similarity between each of '
        f'{c["n_prompts_measured"]} held-out prompts and the training set. '
        f'{counts[0]} prompts fall in the lowest bin, the maximum observed value is '
        f'{c["max"]}, and no prompt reaches the {c["near_dupe_threshold"]} '
        f'near-duplicate threshold.">'
    )
    # y gridlines + labels
    step = ymax // 3
    for k in range(0, ymax + 1, step):
        p.append(f'<line class="ch-grid" x1="{n(X0)}" y1="{n(y(k))}" x2="{n(X1)}" y2="{n(y(k))}"/>')
        p.append(f'<text class="ch-tick ch-tick--y" x="{n(X0 - 8)}" y="{n(y(k) + 3.5)}">{k}</text>')
    # bars
    for i, k in enumerate(counts):
        if k == 0:
            continue
        bx = X0 + i * bw + 2
        p.append(
            f'<rect class="ch-bar" x="{n(bx)}" y="{n(y(k))}" '
            f'width="{n(bw - 4)}" height="{n(Y0 - y(k))}"/>'
        )
        p.append(
            f'<text class="ch-val" x="{n(bx + (bw - 4) / 2)}" y="{n(y(k) - 6)}">{k}</text>'
        )
    # threshold
    tx = x(c["near_dupe_threshold"])
    p.append(f'<line class="ch-threshold" x1="{n(tx)}" y1="{n(Y1 - 6)}" x2="{n(tx)}" y2="{n(Y0)}"/>')
    p.append(
        f'<text class="ch-note ch-note--end" x="{n(tx - 6)}" y="{n(Y1 - 10)}">'
        f'near-duplicate threshold {c["near_dupe_threshold"]}</text>'
    )
    # observed max
    mx = x(c["max"])
    p.append(f'<line class="ch-marker" x1="{n(mx)}" y1="{n(Y1 - 6)}" x2="{n(mx)}" y2="{n(Y0)}"/>')
    p.append(f'<text class="ch-note" x="{n(mx + 6)}" y="{n(Y1 - 10)}">observed max {c["max"]}</text>')
    # axis
    p.append(f'<line class="ch-axis" x1="{n(X0)}" y1="{n(Y0)}" x2="{n(X1)}" y2="{n(Y0)}"/>')
    for v in [i / 10 for i in range(0, int(hi * 10) + 1)]:
        p.append(f'<text class="ch-tick" x="{n(x(v))}" y="{n(Y0 + 18)}">{v:.1f}</text>')
    p.append(f'<text class="ch-axis-label" x="{n((X0 + X1) / 2)}" y="{n(Y0 + 40)}">'
             "maximum 8-gram Jaccard similarity to any training prompt</text>")
    p.append(f'<text class="ch-axis-label ch-axis-label--y" x="0" y="0" '
             f'transform="translate(12 {n((Y0 + Y1) / 2)}) rotate(-90)">held-out prompts</text>')
    p.append("</svg>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def fig_length(d: dict) -> str:
    l = d["length"]
    pairs = l["pairs"]
    hi = max(max(p["base"], p["finetuned"]) for p in pairs)
    ymax = ((hi + 99) // 100) * 100

    XA, XB = 176.0, 484.0
    Y0, Y1 = 208.0, 24.0
    H = Y0 - Y1

    def y(v: float) -> float:
        return Y0 - (v / ymax) * H

    up = [p for p in pairs if p["finetuned"] > p["base"]]
    down = [p for p in pairs if p["finetuned"] < p["base"]]
    same = [p for p in pairs if p["finetuned"] == p["base"]]

    p: list[str] = []
    p.append(
        '<svg class="chart" viewBox="0 0 660 264" role="img" '
        f'aria-label="Paired response length for {l["n_pairs"]} held-out prompts. '
        f'The base model mean is {l["base"]["mean"]} characters and the fine-tune mean is '
        f'{l["finetuned"]["mean"]}. The fine-tune is shorter on {l["shorter_on_n_prompts"]} '
        f'prompts and longer on {l["longer_on_n_prompts"]}.">'
    )
    step = ymax // 4
    for v in range(0, ymax + 1, step):
        p.append(f'<line class="ch-grid" x1="{n(XA)}" y1="{n(y(v))}" x2="{n(XB)}" y2="{n(y(v))}"/>')
        p.append(f'<text class="ch-tick ch-tick--y" x="{n(XA - 10)}" y="{n(y(v) + 3.5)}">{v}</text>')
    # slopes: the 15 that got longer are the point of this figure, so draw them last
    for grp, cls in ((down, "ch-slope"), (same, "ch-slope"), (up, "ch-slope ch-slope--up")):
        for q in grp:
            p.append(
                f'<line class="{cls}" x1="{n(XA)}" y1="{n(y(q["base"]))}" '
                f'x2="{n(XB)}" y2="{n(y(q["finetuned"]))}"/>'
            )
    # means
    for xx, key in ((XA, "base"), (XB, "finetuned")):
        m = l[key]["mean"]
        p.append(f'<line class="ch-mean" x1="{n(xx - 26)}" y1="{n(y(m))}" x2="{n(xx + 26)}" y2="{n(y(m))}"/>')
    # Anchored to the right of each column, not centred on it: a centred label
    # sits on top of the y-axis tick it happens to line up with.
    p.append(f'<text class="ch-val ch-val--mean" x="{n(XA + 32)}" y="{n(y(l["base"]["mean"]) - 8)}">'
             f'mean {n(l["base"]["mean"])}</text>')
    p.append(f'<text class="ch-val ch-val--mean" x="{n(XB + 32)}" y="{n(y(l["finetuned"]["mean"]) - 8)}">'
             f'mean {n(l["finetuned"]["mean"])}</text>')
    # axis captions
    p.append(f'<text class="ch-axis-label" x="{n(XA)}" y="{n(Y0 + 22)}">base model</text>')
    p.append(f'<text class="ch-axis-label" x="{n(XB)}" y="{n(Y0 + 22)}">Sahayak</text>')
    p.append(f'<text class="ch-axis-label ch-axis-label--y" x="0" y="0" '
             f'transform="translate(12 {n((Y0 + Y1) / 2)}) rotate(-90)">answer length, characters</text>')
    # legend
    p.append(f'<line class="ch-slope" x1="536" y1="60" x2="566" y2="60"/>')
    p.append(f'<text class="ch-legend" x="574" y="63.5">shorter ({len(down)})</text>')
    p.append(f'<line class="ch-slope ch-slope--up" x1="536" y1="82" x2="566" y2="82"/>')
    p.append(f'<text class="ch-legend" x="574" y="85.5">longer ({len(up)})</text>')
    p.append("</svg>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def fig_relay(d: dict) -> str:
    r = d["relay"]
    groups = [
        ("packet_required", "A packet is the correct answer"),
        ("packet_wrong", "A packet would be wrong"),
    ]
    X0, X1 = 232.0, 600.0
    W = X1 - X0
    rowh = 34.0
    top = 44.0
    group_gap = 16.0          # breathing room above each group heading
    SLOT_X = X0 - 100         # dot matrix starts here...
    SLOT_STEP = 13.0
    COUNT_X = X0 - 8          # ...and the k/n label is right-anchored here.
    LAB_X = X0 - 112          # row label, right-anchored, clear of the matrix
    # SLOT_X + 4*STEP must stay well clear of COUNT_X minus the label's own
    # width, or "4/4" lands on top of the fourth square.

    def x(f: float) -> float:
        return X0 + f * W

    p: list[str] = []
    height = int(top + rowh * 4 + group_gap + 52)
    p.append(
        f'<svg class="chart" viewBox="0 0 660 {height}" role="img" '
        'aria-label="Relay-packet compliance with exact Clopper-Pearson 95% intervals. '
        "On the four prompts requiring a packet the base model scores 0 of 4 and the "
        "fine-tune 4 of 4. On the four where a packet would be wrong both score 4 of 4. "
        'At n=4 every interval is wide: a perfect 4 of 4 spans 0.40 to 1.00.">'
    )
    last_row_y = top + group_gap + rowh * 3
    # scale
    for f in (0, 0.25, 0.5, 0.75, 1.0):
        p.append(f'<line class="ch-grid" x1="{n(x(f))}" y1="{n(top - 14)}" '
                 f'x2="{n(x(f))}" y2="{n(last_row_y + 14)}"/>')
        p.append(f'<text class="ch-tick" x="{n(x(f))}" y="{n(last_row_y + 32)}">'
                 f'{int(f * 100)}%</text>')

    yy = top
    for key, label in groups:
        g = r[key]
        p.append(f'<text class="ch-group" x="0" y="{n(yy - 16)}">{esc(label)} '
                 f'<tspan class="ch-group-n">n={g["n"]}</tspan></text>')
        for arm, nice in (("base", "base"), ("finetuned", "Sahayak")):
            k = g[f"{arm}_correct"]
            lo, hi = g[f"{arm}_ci95"]
            frac = k / g["n"]
            cls = "ch-ci--ft" if arm == "finetuned" else "ch-ci--base"
            p.append(f'<text class="ch-rowlab" x="{n(LAB_X)}" y="{n(yy + 4)}">{nice}</text>')
            # dot matrix: one square per prompt, filled when answered correctly
            for s in range(g["n"]):
                filled = "ch-slot--on" if s < k else "ch-slot--off"
                p.append(f'<rect class="ch-slot {filled}" x="{n(SLOT_X + s * SLOT_STEP)}" '
                         f'y="{n(yy - 5)}" width="9" height="9" rx="1.5"/>')
            p.append(f'<text class="ch-count" x="{n(COUNT_X)}" y="{n(yy + 4)}">{k}/{g["n"]}</text>')
            # interval
            p.append(f'<line class="ch-ci {cls}" x1="{n(x(lo))}" y1="{n(yy)}" '
                     f'x2="{n(x(hi))}" y2="{n(yy)}"/>')
            for e in (lo, hi):
                p.append(f'<line class="ch-ci-cap {cls}" x1="{n(x(e))}" y1="{n(yy - 5)}" '
                         f'x2="{n(x(e))}" y2="{n(yy + 5)}"/>')
            p.append(f'<circle class="ch-point {cls}" cx="{n(x(frac))}" cy="{n(yy)}" r="4"/>')
            yy += rowh
        yy += group_gap
    p.append(f'<text class="ch-axis-label" x="{n((X0 + X1) / 2)}" y="{n(last_row_y + 56)}">'
             "share of prompts answered correctly, with exact 95% interval</text>")
    p.append("</svg>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def fig_composition(d: dict) -> str:
    comp = d["composition"]
    blocks = [("category", "Task category"), ("difficulty", "Difficulty tier"), ("language", "Language")]
    X0 = 128.0
    W = 420.0
    barh, gap = 15.0, 6.0
    top = 26.0

    rows = sum(len(comp[k]) for k, _ in blocks)
    height = int(top + rows * (barh + gap) + len(blocks) * 30 + 16)
    biggest = max(max(comp[k].values()) for k, _ in blocks)

    p: list[str] = []
    p.append(
        f'<svg class="chart" viewBox="0 0 660 {height}" role="img" '
        f'aria-label="Composition of the {comp["n"]} scored held-out prompts by task '
        "category, difficulty tier and language. English accounts for 42 of 50; every "
        'other language variant appears exactly once.">'
    )
    yy = top
    for key, label in blocks:
        p.append(f'<text class="ch-group" x="0" y="{n(yy)}">{esc(label)}</text>')
        yy += 16
        for name, count in comp[key].items():
            w = (count / biggest) * W
            p.append(f'<text class="ch-rowlab ch-rowlab--wide" x="{n(X0 - 10)}" '
                     f'y="{n(yy + barh - 4)}">{esc(name)}</text>')
            p.append(f'<rect class="ch-bar ch-bar--h" x="{n(X0)}" y="{n(yy)}" '
                     f'width="{n(max(w, 1.5))}" height="{n(barh)}"/>')
            p.append(f'<text class="ch-count ch-count--h" x="{n(X0 + max(w, 1.5) + 8)}" '
                     f'y="{n(yy + barh - 4)}">{count}</text>')
            yy += barh + gap
        yy += 14
    p.append("</svg>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def main() -> int:
    if not DATA.exists():
        print(f"missing {DATA}. Run compute_chart_data.py first.", file=sys.stderr)
        return 1
    d = json.loads(DATA.read_text(encoding="utf-8"))

    figures = [
        ("FIG-CONTAMINATION", fig_contamination(d)),
        ("FIG-LENGTH", fig_length(d)),
        ("FIG-RELAY", fig_relay(d)),
        ("FIG-COMPOSITION", fig_composition(d)),
    ]
    out = [
        "<!-- Generated by docs/benchmarks/make_figures.py from chart_data.json.",
        "     Do not hand-edit the coordinates: regenerate instead. -->",
        "",
    ]
    for name, svg in figures:
        out.append(f"<!-- {name} start -->")
        out.append(svg)
        out.append(f"<!-- {name} end -->")
        out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print("wrote", OUT.relative_to(HERE.parents[1]))
    for name, svg in figures:
        print(f"  {name:20s} {len(svg):6d} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
