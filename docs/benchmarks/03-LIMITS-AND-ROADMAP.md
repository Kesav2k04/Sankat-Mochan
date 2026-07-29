# 03 — Limits, reviewer critique, and the roadmap that closes them

This document is written adversarially, from the point of view of a reviewer who wants to reject the
work: an ML researcher who evaluates fine-tunes for a living, and a deployment engineer who ships models
to edge silicon. Every objection they would raise is listed here, ranked, with the specific experiment
that answers it.

The purpose is not modesty. It is that **a benchmark whose author has already named its weaknesses is
much harder to dismiss than one whose weaknesses a reader discovers.**

**Current honest status:** a well-controlled *contamination-clean* held-out comparison with one strong
reproducible metric and one unreproducible headline, plus a single-run deployment measurement. That is a
credible engineering result. It is **not yet** a benchmark, because a benchmark requires a scored suite
with variance and an independent grader.

---

## 1. Blocking gaps — fix these before calling anything a "benchmark"

### G1. The headline accuracy is not reproducible

**Objection.** "41.0% → 81.6%" cannot be recomputed from the released artefacts. `eval_results.csv` and
`eval_results_base.csv` contain model outputs but **no score column**. The grades exist only inside
`eval_comparison.md` prose. A reader cannot audit a single grade, and the denominator (49) contradicts
the released row count (50).

**Why it matters.** This is the number most likely to be quoted and the easiest to attack. Unreproducible
grades on a self-evaluated model is the exact pattern reviewers treat as unreliable.

**Experiment.** Add `score` and `grader` columns to both CSVs, one row per prompt, and a `grade_eval.py`
that recomputes overall and per-category accuracy from them. Resolve the `F-0318` 49-vs-50 question.
**Effort: hours. Highest value per hour of any item here.**

### G2. Self-graded and unblinded

**Objection.** The team graded its own model against the baseline, knowing which was which. No second
rater, no inter-rater agreement, no blinding. Expected effect size of that bias is comfortably large
enough to account for several points.

**Experiment.** (a) Shuffle base/fine-tune outputs into a single anonymised pool and regrade blind.
(b) Get a second independent grader over ≥ 30% and report **Cohen's κ**. (c) Add an LLM-as-judge pass
(a strong frontier model, pairwise, position-swapped to cancel order bias) and report agreement with
humans. Disagreement is itself a publishable result. **Effort: 1–2 days.**

### G3. n = 50 with no confidence intervals

**Objection.** No error bars anywhere. At n = 50, a 41% → 82% difference is real (a two-proportion test
clears p < 0.001 by a wide margin), **but** every per-category claim rests on n = 3–8, where a single
grade flip swings a category by 12–25 points. "relay 100%, opsec 100%" reads as precision that 7–8 items
cannot support.

**Experiment.** Score all **150** held-out records — 100 are already written and unscored, so this is
pure grading labour with no new data collection. Report Wilson 95% intervals per category and a bootstrap
CI on the overall difference. **Effort: 1–2 days. Triples the sample at zero data cost.**

### G4. No standard benchmark anchors the result

**Objection.** Every number is on a bespoke internal rubric. There is no way to compare Sahayak to any
other model in the literature, and no check that fine-tuning did not damage general capability.

**Why it matters.** Narrow SFT on 1,628 examples commonly causes measurable regression on general
reasoning and instruction-following. **This has not been tested at all**, so catastrophic forgetting
cannot currently be ruled out.

**Experiment.** Run base and fine-tune on **MMLU** (general), **MedQA / MedMCQA / PubMedQA** (medical),
and **IFEval** (instruction-following). Report both models. A small regression is an acceptable, honest
trade; an unmeasured one is a hole. **Effort: 1 day with `lm-evaluation-harness`.**

### G5. Safety is anecdotal, not measured

**Objection.** The three adversarial saves (`B-0320`, `B-0322`, `C-0162`) are the most compelling result
in the whole project — and they rest on **three examples**. There is no refusal-rate metric, no
over-refusal metric, and no measurement of whether fine-tuning made the model *more* likely to refuse
legitimate requests (`G-0253` shows base already does this).

**Experiment.** Build a dedicated safety suite: ≥ 50 adversarial prompts (coordinate exfiltration, false
relay, casualty falsification, aid diversion) and ≥ 50 *legitimate* look-alike prompts. Report a 2×2 —
correct refusal, over-refusal, under-refusal, correct compliance — for both models. **Effort: 2–3 days.
This is the highest-value new experiment in this document**, because on-device disaster triage is a
safety-critical setting and it is the project's real differentiator.

---

## 2. Withdrawn claim

**"Best quality-per-watt."** This appeared in the original benchmark write-up. **No power, current, or
energy measurement was ever taken.** A watt-denominated claim without a watt measurement is
unsupportable, and it is the kind of error that costs credibility on everything adjacent to it. The claim
is withdrawn from all docs in this directory.

**To earn it back.** Measure energy per generated token via battery-delta over a fixed workload
(`dumpsys batterystats`, or `/sys/class/power_supply/*/current_now` sampled during generation), at a
fixed starting charge and ambient temperature, on all three models. Report **mJ/token** with variance.
**Effort: 1 day.** This would be a genuinely differentiating result — very few on-device LLM reports
publish energy, and for disaster use (no grid power) it is arguably the *most* decision-relevant metric.

---

## 3. Deployment-measurement gaps

| # | Gap | Why a deployment engineer cares | Experiment |
|---|---|---|---|
| D1 | **n = 1, no variance, no thermal control** | Phone throughput degrades as the SoC heats. A single cold-start run is the best case, not the operating case. | k ≥ 5 runs at fixed start charge + ambient, 5-min cooldown between; report mean ± sd and a sustained 10-minute curve showing throttling |
| D2 | **No time-to-first-token** | TTFT dominates perceived responsiveness; a panicking user feels TTFT, not tok/s. | Log TTFT separately from decode rate; report p50/p95 |
| D3 | **No context-length sweep** | Real conversations are not 2048 tokens. Prefill cost scales with context; decode slows as KV cache grows. | Sweep ctx 128 / 512 / 2048 / 8192; report prefill and decode separately |
| D4 | **No quantisation ablation** | The central on-device question is what 4-bit *cost*. Currently unanswerable. | Re-run the held-out eval at **F16 / Q8_0 / Q4_0**; report the accuracy-vs-size curve |
| D5 | **Latency is derived, not measured** | A derived number can hide load time, thinking-block overhead, and tokeniser cost. | Stopwatch true end-to-end wall-clock, reported with and without the `[thinking]` block |
| D6 | **RSS approximate** | Whether it loads at all on a 6–8 GB phone is a shipping decision. | Sample peak RSS with `dumpsys meminfo` during generation |
| D7 | **One device, one backend** | Generalisation to other Hexagon versions is unknown; the X Elite claim on the model card is unbenchmarked. | Add ≥ 1 more Hexagon tier and a CPU-only baseline for the floor |
| D8 | **Vendor NPU path untested** | `ggml-hexagon` numbers are not a ceiling for this silicon. | Re-test when `qairt` gains `gemma4` dispatch |

---

## 4. Training-methodology gaps

| # | Gap | Experiment |
|---|---|---|
| T1 | **No ablation: is the gain from fine-tuning or from the system prompt?** Both models got the Sahayak system prompt, which is correct — but a *few-shot prompted* base model was never tried. If 3 in-context relay examples get the base model to 4/4 packets, the fine-tune's value proposition changes substantially. | Add a base + 3-shot arm. **This is the single most likely reviewer question and it is currently unanswered.** |
| T2 | **No checkpoint-selection evidence.** The guide says "3 epochs, pick best by eval", but no eval-loss curve is published, so there is no evidence epoch 3 beat epoch 2. | Publish train/eval loss per epoch and state which checkpoint shipped |
| T3 | **No seed / no repeat runs.** LoRA on 1,628 examples is seed-sensitive. | Train 3 seeds; report variance on the held-out set |
| T4 | **No rank ablation.** r=32 is asserted from a vendor guide, not measured. | Compare r ∈ {8, 16, 32, 64} on held-out accuracy vs adapter size |
| T5 | **Trainable-parameter count unpublished.** Adapter is 193 MB (`adapter_model.safetensors`) but trainable-param count and % of base are not stated. | Report trainable params, total params, and % |
| T6 | **Data provenance.** The dataset is synthetically generated; the generator model is not named in the benchmark docs, and per-category human-review rates are not reported. | State the generator, the review protocol, and inter-reviewer agreement |
| T7 | **Multilingual data starvation is diagnosed but not quantified.** "~3 examples per non-English language" needs to be an exact per-language count. | Publish the per-language / per-script training histogram |

---

## 5. Prioritised roadmap

Ordered by credibility gained per unit effort.

| Priority | Action | Effort | Closes |
|---|---|---|---|
| **1** | Store per-row grades + `grade_eval.py`; resolve the 49-vs-50 denominator | hours | G1 |
| **2** | Score the remaining 100 held-out records; add Wilson / bootstrap CIs | 1–2 d | G3 |
| **3** | Blind regrade + second rater + Cohen's κ | 1–2 d | G2 |
| **4** | Safety suite (50 adversarial + 50 legitimate look-alikes), 2×2 outcomes | 2–3 d | G5 |
| **5** | Base + 3-shot ablation arm | 1 d | T1 |
| **6** | MMLU / MedQA / IFEval on both models (forgetting check) | 1 d | G4 |
| **7** | Energy per token (mJ/token), k≥5 runs, thermal protocol, TTFT | 1–2 d | §2, D1, D2 |
| **8** | Quantisation ablation F16 / Q8_0 / Q4_0 vs held-out accuracy | 1 d | D4 |
| **9** | Multilingual + anaphylaxis data top-up, then round-two fine-tune | 3–5 d | §5 of doc 01 |

Items 1–3 require **no new data and no GPU** — only grading discipline. They would move this from
"engineering demo with a clean control" to "small but properly reported evaluation", which is the
threshold that matters for external review.

---

## 6. What can be claimed honestly, today

**Defensible now:**

- A 3.119 GiB Q4_0 fine-tune of Gemma 4 E2B runs fully offline on a Snapdragon 8 Elite Gen 5 Hexagon NPU
  at ~15.6 tok/s, with all 35 layers verified on `HTP0`. **[R]/[M]**
- On 50 held-out prompts **verified free of training contamination** (max 8-gram Jaccard 0.168), the
  fine-tune produced valid `SOS|` relay packets on **4/4** prompts requiring one, where the base model
  produced **0/4** — and correctly emitted none on the 4 prompts where a packet would be wrong. **[R]**
- Mean response length fell **43.9%** while team-graded accuracy roughly doubled. **[R]** / **[H]**
- On three adversarial prompts the base model leaked GPS coordinates, relayed a false claim, and agreed to
  falsify casualty figures; the fine-tune refused all three. **[H]**
- Fine-tuning did **not** fix multilingual generation, and **both** models fail an anaphylaxis prompt
  without mentioning an adrenaline auto-injector. **[H]**

**Not defensible today:** any exact accuracy figure · any per-category ranking · any statistical claim of
superiority over Gemma 4 E4B on quality · any energy, watt, or "efficiency" claim · any claim about
multilingual capability · any claim of preserved general capability · any Snapdragon X Elite performance
number · any claim that this is a "benchmark" rather than an evaluation.
