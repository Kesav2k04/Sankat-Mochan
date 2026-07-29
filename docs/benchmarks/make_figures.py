#!/usr/bin/env python3
"""
make_figures.py - emit the report page's figures as responsive HTML.

    python docs/benchmarks/compute_chart_data.py   # first: derive the numbers
    python docs/benchmarks/make_figures.py         # then: draw them

Writes docs/benchmarks/figures.html - a fragment per figure, pasted into
report-page/index.html. The page stays a single self-contained file with no
chart library and no runtime data fetch; this script is how the shapes in it
stay honest, because every coordinate comes from chart_data.json.

Why HTML and not SVG
--------------------
These figures used to be hand-built SVG with a fixed 660-unit viewBox. An SVG
scales its type along with its geometry, so on a 360px phone the axis labels
rendered at about 5px and the only fix available was to give every figure its
own horizontal scrollbar. That is a chart you cannot read rather than a chart
that fits.

Built as HTML the text is real text at real font sizes at every viewport, bars
are percentage widths, and nothing needs a nested scroll region. This script
therefore emits geometry only - percentages and counts - while every colour,
size and weight stays in the page's own CSS classes, so a figure can never
hard-code a hue or drift from the theme.

Regenerating after the artefacts change:
    python docs/benchmarks/compute_chart_data.py && python docs/benchmarks/make_figures.py
then replace the marked blocks in report-page/index.html and re-run
verify_page_numbers.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "chart_data.json"
OUT = HERE / "figures.html"


def esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def pct(x: float) -> str:
    """A percentage with just enough precision to be exact on screen."""
    r = round(float(x), 3)
    return f"{int(r)}" if r == int(r) else f"{r}"


def num(x: float) -> str:
    r = round(float(x), 2)
    return str(int(r)) if r == int(r) else str(r)


# ---------------------------------------------------------------------------
def fig_composition(d: dict) -> str:
    """Figure 1 - what the 50 scored prompts are made of.

    Three independent breakdowns of the same 50 prompts, each drawn against a
    shared 0-50 track so the three are directly comparable and the track itself
    supplies the scale that a bare bar list lacks.

    The language block folds its singletons. Drawing eight separate one-count
    bars produced eight 10px stubs that read as a rendering fault, and the
    finding those rows carry is not "Tamil appears once" - it is "everything
    that is not English appears once", which is one row, stated once.
    """
    comp = d["composition"]
    total = comp["n"]
    blocks = [
        ("category", "Task category", "task categories"),
        ("difficulty", "Difficulty tier", "difficulty tiers"),
        ("language", "Language", "language variants"),
    ]

    p: list[str] = []
    p.append(
        '<div class="fg fg--rows" role="img" aria-label="Composition of the '
        f"{total} scored held-out prompts, broken down three ways. By task category: "
        + ", ".join(f"{k} {v}" for k, v in comp["category"].items())
        + ". By difficulty tier: "
        + ", ".join(f"{k} {v}" for k, v in comp["difficulty"].items())
        + f'. By language: English {comp["language"]["en"]}, and eight other language '
        'variants with one prompt each.">'
    )
    # The scale row mirrors .fg__row's grid so its ticks land over the track
    # column rather than over the whole figure.
    p.append(
        '<div class="fg__scalerow"><span></span>'
        '<span class="fg__ticks"><b>0</b>'
        f"<b>{total // 2}</b><b>{total}</b></span>"
        "<span></span></div>"
        f'<p class="fg__axislab fg__axislab--top">Every bar is a share of the same '
        f"{total} scored prompts, so the three breakdowns are directly comparable.</p>"
    )

    for key, label, noun in blocks:
        items = list(comp[key].items())
        singles = [k for k, v in items if v == 1]
        note = ""
        if len(singles) >= 3:
            items = [(k, v) for k, v in items if v > 1]
            items.append((f"{len(singles)} other {noun}", len(singles)))
            note = (
                f'<p class="fg__note">One prompt each: {esc(", ".join(singles))}. '
                "No per-variant claim on this set could be anything but anecdotal.</p>"
            )

        p.append('<div class="fg__block">')
        p.append(
            f'<p class="fg__blockhead">{esc(label)} '
            f'<span>{len(comp[key])} distinct</span></p>'
        )
        p.append('<div class="fg__rows">')
        for name, count in items:
            w = 100.0 * count / total
            p.append(
                '<div class="fg__row">'
                f'<span class="fg__lab">{esc(name)}</span>'
                '<span class="fg__track">'
                f'<span class="fg__bar" style="inline-size:{pct(w)}%"></span>'
                "</span>"
                f'<span class="fg__v">{count}</span>'
                "</div>"
            )
        p.append("</div>")
        if note:
            p.append(note)
        p.append("</div>")

    p.append("</div>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def fig_contamination(d: dict) -> str:
    """Figure 2 - the whole similarity distribution, not just the maximum.

    The argument this figure makes is about the bins that are empty, so the
    empty bins are drawn: every one of the twelve gets a column, and the eight
    that hold nothing get a baseline stub. Previously they were simply absent,
    which left two thirds of the plot as blank space that read as a broken
    render rather than as the finding.
    """
    c = d["contamination"]
    h = c["histogram"]
    counts = h["counts"]
    hi = h["hi"]
    nbins = len(counts)
    top = max(counts)
    ymax = ((top + 7) // 8) * 8 or 8
    step = ymax // 3

    def xf(v: float) -> float:
        return 100.0 * v / hi

    p: list[str] = []
    p.append(
        '<div class="fg fg--hist" role="img" aria-label="Histogram of the maximum '
        f"character 8-gram Jaccard similarity between each of {c['n_prompts_measured']} "
        "held-out prompts and the training set, in bins of 0.05 across a 0 to "
        f"{hi} axis. {counts[0]} prompts fall in the lowest bin, {counts[1]} in the "
        f"next, {counts[2]} in the next and {counts[3]} in the next. The remaining "
        f"{nbins - 4} bins are empty. The maximum observed value is {c['max']} and no "
        f'prompt reaches the {c["near_dupe_threshold"]} near-duplicate threshold.">'
    )
    p.append('<div class="fg__plot">')
    p.append('<div class="fg__area">')

    # y gridlines, drawn first so the marks sit over them
    for k in range(0, ymax + 1, step):
        y = 100.0 * k / ymax
        p.append(
            f'<span class="fg__grid" style="inset-block-end:{pct(y)}%">'
            f'<b class="fg__gridv">{k}</b></span>'
        )

    # the two reference markers, behind the columns
    mx = xf(c["max"])
    tx = xf(c["near_dupe_threshold"])
    p.append(f'<span class="fg__mark fg__mark--max" style="inset-inline-start:{pct(mx)}%"></span>')
    p.append(f'<span class="fg__mark fg__mark--thresh" style="inset-inline-start:{pct(tx)}%"></span>')

    # columns: every bin, including the empty ones
    bw = 100.0 / nbins
    for i, k in enumerate(counts):
        left = i * bw
        cls = "fg__col" if k else "fg__col fg__col--empty"
        hgt = 100.0 * k / ymax
        p.append(
            f'<span class="{cls}" style="inset-inline-start:{pct(left)}%;'
            f"inline-size:calc({pct(bw)}% - 3px);"
            f'block-size:{pct(hgt)}%">'
            + (f'<b class="fg__colv">{k}</b>' if k else "")
            + "</span>"
        )

    p.append("</div>")  # .fg__area
    p.append("</div>")  # .fg__plot

    # x axis
    p.append('<p class="fg__xaxis">')
    ticks = [i / 10 for i in range(0, int(round(hi * 10)) + 1)]
    for v in ticks:
        p.append(f'<span style="inset-inline-start:{pct(xf(v))}%">{v:.1f}</span>')
    p.append("</p>")
    p.append(
        '<p class="fg__axislab">maximum <b>character</b> 8-gram Jaccard similarity '
        "to any training prompt</p>"
    )
    p.append(
        '<p class="fg__key">'
        f'<span class="fg__ki"><span class="fg__key-i fg__key-i--max"></span>'
        f'observed maximum {c["max"]}</span>'
        f'<span class="fg__ki"><span class="fg__key-i fg__key-i--thresh"></span>'
        f'near-duplicate threshold {c["near_dupe_threshold"]}</span>'
        f'<span class="fg__ki"><span class="fg__key-i fg__key-i--empty"></span>'
        f"empty bin &mdash; {sum(1 for k in counts if not k)} of {nbins}</span>"
        "</p>"
    )
    p.append("</div>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def fig_relay(d: dict) -> str:
    """Figure 3 - relay-packet compliance with exact intervals.

    Both groups are stated as "answered correctly" so the two halves share one
    axis. That conflicts with the summary table, which counts the second group
    the other way round - as packets wrongly emitted, 0 of 4 - so each row in
    that group also carries the raw emission count. A reader moving between the
    table and the figure should never have to work out that 0 emitted and 4
    correct are the same fact.
    """
    r = d["relay"]
    groups = [
        ("packet_required", "A packet is the correct answer", "emitted"),
        ("packet_wrong", "A packet would be wrong", "emitted"),
    ]

    p: list[str] = []
    p.append(
        '<div class="fg fg--ci" role="img" aria-label="Relay-packet compliance with '
        "exact Clopper-Pearson 95% intervals. On the four prompts requiring a packet "
        "the base model answers 0 of 4 correctly and the fine-tune 4 of 4. On the four "
        "prompts where a packet would be wrong neither model emits one, so both answer "
        "4 of 4 correctly. At n=4 every interval is wide: a perfect 4 of 4 spans 0.40 "
        'to 1.00.">'
    )
    p.append(
        '<div class="fg__crow fg__crow--scale"><span></span><span></span><span></span>'
        '<span class="fg__ciwrap"><span class="fg__ticks"><b>0%</b><b>50%</b>'
        "<b>100%</b></span></span></div>"
    )

    for key, label, _ in groups:
        g = r[key]
        wrong_group = key == "packet_wrong"
        p.append('<div class="fg__block">')
        p.append(
            f'<p class="fg__blockhead">{esc(label)} <span>n={g["n"]}</span></p>'
        )
        p.append('<div class="fg__rows">')
        for arm, nice in (("base", "base"), ("finetuned", "Sahayak")):
            k = g[f"{arm}_correct"]
            emitted = g[f"{arm}_emitted"]
            lo, hi = g[f"{arm}_ci95"]
            frac = 100.0 * k / g["n"]
            tone = "fg--ft" if arm == "finetuned" else "fg--base"
            # The base model earns the second group by never emitting a packet
            # at all, which is the right output for the wrong reason. Flagged
            # here rather than left for the reader to infer from the caption.
            dagger = (
                '<abbr class="fg__flag" title="Correct only because this model '
                'never emits a packet at all, anywhere in the set.">&dagger;</abbr>'
                if wrong_group and arm == "base"
                else ""
            )
            p.append(f'<div class="fg__crow {tone}">')
            p.append(f'<span class="fg__lab">{nice}{dagger}</span>')
            p.append('<span class="fg__slots">')
            for s in range(g["n"]):
                on = "fg__slot fg__slot--on" if s < k else "fg__slot"
                p.append(f'<span class="{on}"></span>')
            p.append("</span>")
            p.append(
                f'<span class="fg__v">{k}/{g["n"]}'
                f'<b class="fg__sub">{emitted} emitted</b></span>'
            )
            p.append('<span class="fg__ciwrap"><span class="fg__ciarea">')
            p.append(
                f'<span class="fg__ci" style="inset-inline-start:{pct(100 * lo)}%;'
                f'inline-size:{pct(100 * (hi - lo))}%"></span>'
            )
            p.append(f'<span class="fg__dot" style="inset-inline-start:{pct(frac)}%"></span>')
            p.append("</span></span>")
            p.append("</div>")
        p.append("</div></div>")

    p.append(
        '<p class="fg__axislab">share of prompts answered correctly, with the exact '
        "95% interval &mdash; the bar is the interval, the dot is the point estimate</p>"
    )
    p.append(
        '<p class="fg__note">&dagger; The base model clears the second group only '
        "because it never produces the packet format at all. Right output, wrong "
        "reason, and the reason is the first group.</p>"
    )
    p.append("</div>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def fig_length(d: dict) -> str:
    """Figure 4 - paired response length, as a scatter against the identity line.

    This was a slope chart: fifty lines crossing inside a 308x184 box, which is
    unreadable at any size and was the single worst-looking thing on the page.
    Plotted as base-versus-fine-tune against y=x the same fifty pairs stop
    overlapping, and the finding the caption argues for - that the effect is
    real but not uniform - becomes the geometry rather than a colour count:
    every point below the line got shorter, every point above it got longer.

    Position is the primary encoding here, so the two hues only restate what
    the diagonal already says. That is deliberate: it is the colourblind-safe
    ordering, not redundancy for its own sake.
    """
    l = d["length"]
    pairs = l["pairs"]
    hi = max(max(q["base"], q["finetuned"]) for q in pairs)
    axmax = ((hi + 249) // 250) * 250

    up = [q for q in pairs if q["finetuned"] > q["base"]]
    down = [q for q in pairs if q["finetuned"] < q["base"]]
    same = [q for q in pairs if q["finetuned"] == q["base"]]

    bmean = l["base"]["mean"]
    fmean = l["finetuned"]["mean"]

    p: list[str] = []
    p.append(
        '<div class="fg fg--scatter" role="img" aria-label="Scatter plot of response '
        f'length for {l["n_pairs"]} held-out prompts, base model on the horizontal '
        "axis against the Sahayak fine-tune on the vertical axis, both from 0 to "
        f"{axmax} characters, with a diagonal marking equal length. "
        f'{len(down)} prompts fall below the diagonal, meaning the fine-tune answered '
        f"more briefly, and {len(up)} fall above it, meaning it answered at greater "
        f'length. The base mean is {bmean} characters and the fine-tune mean is '
        f'{fmean}.">'
    )
    p.append('<div class="fg__sqwrap">')
    p.append(
        '<p class="fg__ylab">Sahayak answer length, characters</p>'
    )
    p.append('<p class="fg__yticks">')
    for v in range(0, axmax + 1, axmax // 4):
        p.append(f'<span style="inset-block-end:{pct(100 * v / axmax)}%">{v}</span>')
    p.append("</p>")

    p.append('<div class="fg__square">')
    for v in range(axmax // 4, axmax, axmax // 4):
        y = pct(100 * v / axmax)
        p.append(f'<span class="fg__grid fg__grid--h" style="inset-block-end:{y}%"></span>')
        p.append(f'<span class="fg__grid fg__grid--v" style="inset-inline-start:{y}%"></span>')
    p.append('<span class="fg__diag"></span>')
    # mean reference lines
    p.append(
        f'<span class="fg__mean fg__mean--v" style="inset-inline-start:'
        f'{pct(100 * bmean / axmax)}%"></span>'
    )
    p.append(
        f'<span class="fg__mean fg__mean--h" style="inset-block-end:'
        f'{pct(100 * fmean / axmax)}%"></span>'
    )
    for grp, cls in ((same, "fg__pt"), (down, "fg__pt fg__pt--down"), (up, "fg__pt fg__pt--up")):
        for q in grp:
            delta = q["finetuned"] - q["base"]
            sign = "+" if delta > 0 else ""
            p.append(
                f'<span class="{cls}" style="inset-inline-start:'
                f'{pct(100 * q["base"] / axmax)}%;inset-block-end:'
                f'{pct(100 * q["finetuned"] / axmax)}%" '
                f'title="{esc(q["id"])}: base {q["base"]} chars, '
                f'Sahayak {q["finetuned"]} chars ({sign}{delta})"></span>'
            )
    p.append("</div>")  # .fg__square

    p.append('<p class="fg__xticks">')
    for v in range(0, axmax + 1, axmax // 4):
        p.append(f'<span style="inset-inline-start:{pct(100 * v / axmax)}%">{v}</span>')
    p.append("</p>")
    p.append('<p class="fg__axislab">base model answer length, characters</p>')
    p.append("</div>")  # .fg__sqwrap

    p.append('<div class="fg__side">')
    p.append(
        '<p class="fg__key fg__key--stack">'
        f'<span class="fg__ki"><span class="fg__key-i fg__key-i--down"></span>'
        f"<b>shorter</b> than base &mdash; {len(down)} prompts, below the line</span>"
        f'<span class="fg__ki"><span class="fg__key-i fg__key-i--up"></span>'
        f"<b>longer</b> than base &mdash; {len(up)} prompts, above the line</span>"
        f'<span class="fg__ki"><span class="fg__key-i fg__key-i--diag"></span>'
        "equal length &mdash; the diagonal</span>"
        "</p>"
    )
    p.append(
        '<p class="fg__note">The hairline crosshair marks the two means: '
        f"<b>{num(bmean)}</b> characters for the base model, <b>{num(fmean)}</b> for "
        "the fine-tune. Each point is one prompt answered by both models; hover a "
        "point for its identifier and both lengths, or read the table below.</p>"
    )
    p.append("</div>")
    p.append("</div>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
def main() -> int:
    if not DATA.exists():
        print(f"missing {DATA}. Run compute_chart_data.py first.", file=sys.stderr)
        return 1
    d = json.loads(DATA.read_text(encoding="utf-8"))

    figures = [
        ("FIG-COMPOSITION", fig_composition(d)),
        ("FIG-CONTAMINATION", fig_contamination(d)),
        ("FIG-RELAY", fig_relay(d)),
        ("FIG-LENGTH", fig_length(d)),
    ]
    out = [
        "<!-- Generated by docs/benchmarks/make_figures.py from chart_data.json.",
        "     Geometry only: every colour is a CSS class the page owns.",
        "     Do not hand-edit the percentages: regenerate instead. -->",
        "",
    ]
    for name, frag in figures:
        out.append(f"<!-- {name} start -->")
        out.append(frag)
        out.append(f"<!-- {name} end -->")
        out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print("wrote", OUT.relative_to(HERE.parents[1]))
    for name, frag in figures:
        print(f"  {name:20s} {len(frag):6d} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
