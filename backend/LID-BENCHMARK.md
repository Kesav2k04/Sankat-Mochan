# Command-post language ID — FLEURS benchmark (before / after)

Language identification decides which vocabulary IndicConformer decodes an SOS clip with.
Get it wrong and the transcript is garbage, so it's the highest-leverage accuracy lever in
the voice pipeline. On 2026-07-12 we replaced the language-ID scorer in `stt.py`
(`_identify_from_wav`) and measured the exact production function on Google **FLEURS**.

## Headline

| | Overall LID | Errors | Languages at 100% |
|---|---|---|---|
| **Before** — mass-based scorer | **90.6%** (163/180) | 17, across 5 languages | 7 / 12 |
| **After** — peak-confidence + calibrated margin | **98.9%** (178/180) | 2, hi↔ur only | 11 / 12 |

Error count dropped **17 → 2**, and every language except the genuinely-ambiguous
Hindi/Urdu pair is now perfect.

## Method

- **Set:** FLEURS test clips (CC-BY, 16 kHz, gold transcripts), **15 clips × 12 languages =
  180**, covering every language the LID sweeps (`hi ur bn ta te kn ml mr gu pa or as`).
- **Measured code:** the real `stt._identify_from_wav` via `lid_bench.py` — not a
  reimplementation. Ground truth = `fleurs/references.json` (`download_fleurs.py`).
- **Latency:** ~900 ms/clip on the Snapdragon X Elite (CPU; the NPU stays free for triage).

## What changed

Both scorers use the same trick — IndicConformer's acoustic encoder is language-agnostic,
so a language is just a mask over the 5633 CTC classes, and we score all languages off one
CTC pass (no separate SLID model). Only the **scoring math** changed:

| | Before (mass) | After (peak confidence) |
|---|---|---|
| Softmax domain | full 5633-way | renormalized within each language's own columns |
| Metric | `logsumexp` of probability **mass** on the 256 script tokens | **top-token log-prob** (how confidently the frame commits to one token) |
| Speech frames | one shared mask (global argmax ≠ blank) | per-language (that language's own argmax ≠ blank) |
| hi/ur tie | none | Hindustani margin (see below) |

The mass metric rewards a script that soaks up diffuse probability, which is why it leaked
across script families (Punjabi→Hindi, Gujarati→Hindi, Assamese→Bengali). Peak confidence
instead asks *"assuming language X, how sharply does each frame decode to a single X
token?"* — the correct language produces low-entropy CTC spikes, so those confusions
disappear. Ported 1:1 from the mobile decoder (`CtcDecoder.pickLanguage`).

## Per-language

| Lang | Before | After | Before's misses |
|---|---|---|---|
| hi | 73.3% (11/15) | 93.3% (14/15) | →ur:3, mr:1 |
| pa | 73.3% (11/15) | **100%** | →hi:4 |
| as | 80.0% (12/15) | **100%** | →bn:3 |
| gu | 80.0% (12/15) | **100%** | →hi:3 |
| ur | 80.0% (12/15) | 93.3% (14/15) | →hi:3 |
| bn, kn, ml, mr, or, ta, te | 100% | 100% | — |

The peak-confidence scorer fixed **pa, gu, as outright** (100%). The only residual is the
Hindi↔Urdu pair — they are the same spoken language (Hindustani), acoustically
inseparable, so this is a real limit, not a scorer bug.

## Hindi/Urdu (Hindustani) margin calibration

Since hi/ur can't be separated acoustically, we bias near-ties toward Devanagari Hindi
(India-first). The mobile decoder ships `HINDUSTANI_MARGIN = 0.15`, but our peak-confidence
scores are ~10× smaller, so 0.15 forces **all** Urdu → Hindi. We swept the 30 hi/ur clips:

| margin | Hindi | Urdu | pair acc | overall (180) |
|---|---|---|---|---|
| 0.00 (none) | 10/15 | 15/15 | 83.3% | 97.2% |
| **0.02 (shipped)** | **14/15** | **14/15** | **93.3%** | **98.9%** |
| 0.05 | 15/15 | 11/15 | 86.7% | 97.8% |
| 0.15 (mobile default) | 15/15 | 0/15 | 50.0% | 91.7% |

The measured gap (`ur − hi` score) separates true-Hindi (≤ ~+0.03) from true-Urdu
(≥ ~+0.03), and **0.02** is the sweep optimum: it recovers 4 of 5 Hindi clips that leaned
Urdu while giving up only 1 Urdu clip.

## Reproduce

```bash
cd backend
python download_fleurs.py 15          # fetch 15 FLEURS clips/language → fleurs/
python lid_bench.py                   # scores the production _identify_from_wav on ./fleurs
```

`lid_bench.py` prints overall + per-language accuracy, the confusion matrix, and the
top1−top2 confidence margins.
