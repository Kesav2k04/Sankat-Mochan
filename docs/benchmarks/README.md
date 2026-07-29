# Sahayak-E2B — benchmarks

Evaluation and on-device measurement record for **Sahayak-E2B**, a QLoRA fine-tune of
`google/gemma-4-E2B-it` for offline disaster response, deployed as a Q4_0 GGUF on a
Snapdragon Hexagon NPU.

**📄 [Read the whole record as one page →](https://sahayak-e2b-benchmark.vercel.app/)** — the same
numbers, tiered and cross-linked, with the negative results and the reviewer critique in line.

This directory separates claims into three tiers, and never mixes them:

| Tier | Meaning | Where |
|---|---|---|
| **Reproducible** | Recomputed from released artefacts by `verify_benchmarks.py`. Anyone can rerun it and get the same number. | tagged **[R]** below |
| **Human-graded** | Assigned by the project team against a written rubric. Defensible, but not independently reproducible — the per-row grades are not stored in the released CSVs. | tagged **[H]** below |
| **Measured once** | A real hardware measurement, but a single run with no variance and no thermal control. | tagged **[M]** below |

Confusing those tiers is the most common way a small-team benchmark loses credibility, so
every table in this directory labels which one it is.

---

## Headline results

**Capability — 50 held-out prompts, base vs fine-tune, identical system prompt and greedy decoding.**

- **[H] Overall rubric accuracy: 41.0% → ~82%.** Graded by the project team on a 0 / 0.5 / 1.0 rubric.
  Reported as `~82%` rather than `81.6%` because the denominator is disputed — see correction 3 below.
  Unblinded, single grader, per-row grades not released.
- **[R] Relay-packet compliance: 0/4 → 4/4** on the prompts where a `SOS|WHO:|LOC:|NEED:` packet is the
  correct output — and **0/4 → 0/4** on the four relay prompts where emitting a packet would be *wrong*
  (ambiguous prompts must ask for the missing fields; adversarial prompts must refuse to broadcast).
  The base model produced **zero** valid packets. This is machine-validated by the `relay_packet_ok`
  column and is the single strongest reproducible result here.
- **[R] Response length: 420 → 235 mean characters (−43.9%).** Objective support for the "terse
  field-operator tone" claim.
- **[R] Train/eval contamination: zero.** No exact overlap and no near-duplicate (max 8-gram Jaccard
  **0.168**, far below a 0.55 near-duplicate threshold) between the 50 scored prompts and all 1,690
  training user-turns. The 50 prompts are a verified strict subset of the 150 held-out records.
- **[H] Three safety-critical base-model failures were fixed by fine-tuning** — see
  [`01-HELDOUT-CAPABILITY-EVAL.md`](01-HELDOUT-CAPABILITY-EVAL.md) §4.

**Deployment — one measured run, 12 July 2026, OnePlus 15 (Snapdragon 8 Elite Gen 5, Hexagon v81).**

- **[M] 15.6 tok/s** generation, all 35 layers on `HTP0`, greedy decoding. One run, no thermal control,
  no time-to-first-token, no energy measurement.
- **[R] 3.119 GiB (3.35 GB)** on disk — exactly 3,349,514,592 bytes.

Full detail: [`02-ON-DEVICE-NPU-RUNTIME.md`](02-ON-DEVICE-NPU-RUNTIME.md).

**What this does not establish** is as important as what it does. Read
[`03-LIMITS-AND-ROADMAP.md`](03-LIMITS-AND-ROADMAP.md) before citing any number here.

---

## Reproduce

```bash
python docs/benchmarks/verify_benchmarks.py
```

Recomputes every **[R]** claim from `finetune/` and writes
[`verification_report.json`](verification_report.json). Exits non-zero if any assertion fails.
No GPU, no network, no model download required — it reads the released CSV/JSONL artefacts.

Current status: **22/22 assertions pass.**

---

## Contents

| File | What it covers |
|---|---|
| [`01-HELDOUT-CAPABILITY-EVAL.md`](01-HELDOUT-CAPABILITY-EVAL.md) | The 50-prompt held-out evaluation: protocol, per-category results, safety findings, negative results |
| [`02-ON-DEVICE-NPU-RUNTIME.md`](02-ON-DEVICE-NPU-RUNTIME.md) | Throughput / size / latency on the Hexagon NPU, and the runtime caveats |
| [`03-LIMITS-AND-ROADMAP.md`](03-LIMITS-AND-ROADMAP.md) | Reviewer-grade critique: every gap, why it matters, and the specific experiment that closes it |
| [`verify_benchmarks.py`](verify_benchmarks.py) | Reproduces all **[R]** claims |
| [`verification_report.json`](verification_report.json) | Machine-readable output of the above |
| [`report-page/`](report-page/) | Source for the [single-page report](https://sahayak-e2b-benchmark.vercel.app/) |

## Underlying artefacts

| Path | Contents |
|---|---|
| `finetune/data/train.jsonl` | 1,628 training records |
| `finetune/data/val.jsonl` | 172 validation records |
| `finetune/data/eval_holdout.jsonl` | 150 held-out records (50 scored, 100 unscored) |
| `finetune/eval_questions.csv` | The 50 scored prompts + reference answers |
| `finetune/eval_results.csv` | Fine-tuned model outputs (50 rows) |
| `finetune/eval_results_base.csv` | Base model outputs (50 rows) |
| `finetune/eval_comparison.md` | The original human-graded write-up |

## Corrections applied in this directory

These fix errors found in earlier drafts. Cite the values here, not the older ones.

1. **Dataset split is 1,628 / 172 / 150** (= 1,950). Earlier docs said "1,800 train + 150 held-out";
   the 1,800 figure was the *dataset spec's target*, not the delivered split. **[R]**
2. **Size units.** The GGUF is **3.119 GiB = 3.35 GB**. `llama.cpp` prints GiB, so the benchmark doc's
   "3.11 GB" was actually GiB, and the model card's "3.35 GB" was decimal GB — the same file, two units.
   Likewise Gemma 4 E4B is **4.80 GiB (5.15 GB)**, and the difference is **1.69 GiB (1.82 GB)**. **[R]**
3. **`eval_comparison.md` says the fine-tuned run produced 49 rows** because `F-0318` dropped out.
   The released `eval_results.csv` contains **all 50 rows with non-empty answers**, including a 741-character
   answer for `F-0318`. The "matched-49" denominator is stale. **[R]**
4. **Relay is reported as "19% → 100% (8.0/8)"** in `eval_comparison.md`. That is a *rubric* score. The
   *machine* validator reports 4/8 packets emitted by the fine-tune — which is correct, because only 4 of
   the 8 relay prompts should produce a packet at all. Both numbers are right; stating only "100%" invites
   a reviewer to find the 4/8 and assume overclaiming. **[R]**
5. **Languages are English plus five Indian languages** — `en, hi, ta, bn, te, mr`, each with native-script
   and romanised variants. Not "6 Indian languages".
6. **"Best quality-per-watt" is withdrawn.** No power or energy measurement was taken. See
   [`03-LIMITS-AND-ROADMAP.md`](03-LIMITS-AND-ROADMAP.md) §2.
7. **The single-prompt 9.0/10 score is superseded** by the 50-prompt held-out evaluation and should no
   longer be used as a headline. It remains in `02-ON-DEVICE-NPU-RUNTIME.md` only as the qualitative
   illustration attached to the throughput run.

---

**Not a medical device.** Nothing in this directory is medical advice. Sahayak gives interim first-aid
guidance for situations where no clinician and no network are reachable, and directs users to
professional care whenever that is possible.

Model weights are a Gemma derivative governed by the
[Gemma Terms of Use](https://ai.google.dev/gemma/terms) (not OSI-approved). The bundled `llama.cpp`
binaries are MIT. The Sahayak Emergency Dataset v2 is Apache-2.0.
