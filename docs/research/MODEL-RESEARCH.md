# Sankat-Mochan — Model & Inference Pipeline Research

> Deep-research deliverable for the AI-pipeline owner. Verified against July 2026 sources.
> Focus: on-device triage + translation + LoRa-envelope compression on Snapdragon X Elite (Surface Laptop 7).
> Every benchmark number is sourced or explicitly marked as an estimate. Do not quote unmarked estimates to judges.

---

## Executive summary — the recommended stack

**Primary stack (keep it, with two corrections to the current plan):**

- **LLM: Qwen3-4B, Qualcomm-precompiled QNN/Genie bundle, W4A16 quantization, run on the Hexagon NPU via `genie-t2t-run` (QAIRT SDK).**
  This remains the right pick and the plan's instinct is correct: it is the *only* general-purpose LLM Qualcomm ships with ready-made downloadable NPU assets for Snapdragon X Elite (`huggingface.co/qualcomm/Qwen3-4B`), it is strong on Indic languages (beats Gemma 3 4B on the IndicParam benchmark), and it carries the AI Hub scoring bonus. Zero export work.
- **Expected performance (estimate, see Q1/Q3): ~10-15 tok/s decode, ~1-3 s time-to-first-token on short prompts, on the NPU.** No X-Elite-specific published Qwen3-4B number exists; this is extrapolated from Llama-3.2-3B ≈ 10 tok/s W4A16 on Snapdragon NPU. Treat as an estimate until you measure it in the Saturday smoke test.
- **STT: Whisper-Small (or Base) from AI Hub, W8A16 quantized, NPU.** Precompiled compute assets exist. Evaluate Sarvam on-site but do not depend on it (see Q5).

**Two corrections the research forces on the current plan:**

1. **`llama.cpp` does NOT run on the NPU — it is CPU-only on Windows-on-ARM.** The PREP-PLAN's "same runtime on CPU now and Snapdragon later, so the swap is a config change" is only true if you stay on CPU. The NPU path is a *different runtime* (ONNX Runtime QNN EP, or Genie/QAIRT), not llama.cpp. Build the CPU prototype behind a clean `triage(text) -> dict` seam so the engine swap is contained, but know it is a real backend swap, not a config flag. (Sources: the Surface Laptop 7 field write-up and the llama.cpp Snapdragon discussion both confirm llama.cpp has no Hexagon backend.)
2. **Genie has no built-in grammar/JSON-schema constrained decoding.** Its sampler exposes only `temperature`, `top-k`, `top-p`, `seed`. Guaranteed-valid JSON must come from prompt design + a robust parser + one repair retry, NOT from constrained decoding on the NPU. Grammar-constrained decoding only exists on the llama.cpp (CPU) path. This is a genuine trade-off between "fast NPU, best-effort JSON" and "slower CPU, guaranteed-valid JSON." Recommendation below is NPU + defensive parsing.

**Fallback stack (if the NPU path won't come up in the Saturday smoke window):**

- **Qwen3-4B (or Qwen2.5-3B / Phi-4-mini) GGUF Q4_K_M on `llama.cpp`, CPU only, with Qualcomm QMX kernels.** Qualcomm's April 2026 QMX work meaningfully accelerates llama.cpp on Snapdragon *CPU*; this is a credible, no-NPU fallback that still runs fast and still supports grammar-constrained JSON. Then the rule-based scorer remains tier 4, unchanged.
- **Smaller-model option for burst throughput: Qwen3-1.7B** as the triage-only classifier if 4B decode proves too slow under load (see Q1/Q6).

**One-line recommendation for the evening call:** keep Qwen3-4B as primary, but tell the team (a) the NPU runtime is Genie/QAIRT + ONNX-QNN, not llama.cpp; (b) JSON validity is our job in the prompt + parser, not the sampler's; (c) LoRA *is* supported on-device if we ever want it (we won't need it — see Q4).

---

## Q1 — Model architecture: best performance-per-latency for triage + translation + compression

**Verdict: Qwen3-4B primary; Qwen3-1.7B as the burst/triage-only alternative; do NOT split into two models unless burst latency forces it.**

### The candidates, ranked for THIS job

| Model | On AI Hub / precompiled NPU assets? | Indic quality | Fit for the 3 jobs | Verdict |
|---|---|---|---|---|
| **Qwen3-4B** | **Yes — downloadable assets for X Elite, X2 Elite, 8 Elite, 8 Elite Gen 5** | Strong; beats Gemma 3 4B on IndicParam | Excellent at all three | **Primary** |
| Qwen3-1.7B | On AI Hub family; smaller, faster | Good (same training recipe) | Triage yes; translation slightly weaker | **Burst fallback / phone-side** |
| Qwen3-0.6B | On AI Hub family | Usable for classification only | Triage-hint only | Phone-side pre-triage |
| Phi-4-Mini-Instruct | Yes (AI Hub, `phi_4_mini_instruct`) | Weaker on Indic than Qwen | Good English; weaker Hindi/Tamil | Backup only |
| Ministral-3-3B-Instruct-2512 | Yes (AI Hub) | Mistral-lineage, decent multilingual | Good | Second backup |
| Gemma 3 4B / 1B | On AI Hub family | 140+ langs, but loses to Qwen3-4B on IndicParam MCQ/fill-in tasks | Good, multimodal not needed | Not worth switching |
| Llama 3.2 3B | **No ready assets — gated HF + self-export** | Moderate Indic | Fine | Tier-3 CPU fallback only |
| Sarvam-1 (2B) / Sarvam-M (24B) | See Q5 — device-OEM gated / API | Best-in-class Indic | Sarvam-M too big (24B); Sarvam-1 promising but not freely deployable on X Elite | Evaluate on-site, don't depend |

Key evidence: on the **IndicParam** benchmark Qwen3-4B outperforms Gemma3-4B across the majority of Indic question formats. Qwen's training explicitly covers 10+ Indian languages well. That, plus being Qualcomm's own documented Genie example with zero-export assets, makes Qwen3-4B the clear win — you get best Indic-per-latency *and* the least porting risk simultaneously.

### Would a smaller model beat 4B?

For **triage alone** (urgency score + category), a 1.7B or even 0.6B is plenty — classification is easy. But **translation quality** (Tamil/Hindi ↔ English) degrades noticeably below ~3-4B for low-resource Indic languages. Since translation is a hard requirement and a live demo beat, **do not drop below 4B for the main model.** Reserve 1.7B for the "burst is throttling us" contingency (Q6).

### One model or two?

Recommendation: **one model (Qwen3-4B) doing all three jobs in a single structured-output call.** Rationale: (1) the burst is only 5-50 short messages over minutes — that is not throughput-bound enough to justify a second model's memory and complexity; (2) loading two NPU context binaries eats your 32 GB and your setup hours; (3) a single prompt that returns `{urgency, category, translated_en, envelope}` is one NPU round-trip instead of three. The two-model split (tiny classifier + big translator) is a *documented option to keep in your back pocket*, not the default. The phone-side tiny model (Q6) is a separate, additive story for the Multi-Device prize, not a split of the command-post pipeline.

Sources: [Qwen3-4B on AI Hub](https://aihub.qualcomm.com/models/qwen3_4b) · [IndicParam benchmark](https://arxiv.org/pdf/2512.00333) · [Gemma 3 vs Qwen 3 comparison](https://codersera.com/blog/gemma-3-vs-qwen-3-in-depth-comparison-of-two-leading-open-source-llms/) · [Best SLMs 2026 (BentoML)](https://www.bentoml.com/blog/the-best-open-source-small-language-models) · [Phi-4-Mini on AI Hub](https://aihub.qualcomm.com/mobile/models/phi_4_mini_instruct) · [All AI Hub models](https://aihub.qualcomm.com/models)

---

## Q2 — Quantization

**Verdict: use the precompiled W4A16 assets as-is. Do not attempt your own quant flow in 24h.**

- The Qualcomm precompiled LLM bundles for Snapdragon NPU use **W4A16 (4-bit weights, 16-bit activations)** — confirmed for the documented Llama-3.2-3B / Llama-3.1-8B Genie bundles, and this is the standard AI Hub LLM recipe. The Qwen3-4B `qualcomm/` assets follow the same flow. You inherit this; you do not choose it.
- **Whisper** on AI Hub uses **W8A16** (`whisper_small_quantized`).
- **Indic quality under INT4:** W4A16 (16-bit activations) is much safer for multilingual text than a naive W4A8 or INT4-everything scheme, because the 16-bit activations preserve the dynamic range that low-resource-language tokens need. The known INT4 "quality cliff" for multilingual output is mostly a W4A8 / activation-quantization problem — W4A16 largely avoids it. Still, **validate Tamil/Hindi output quality in the smoke test**; if you see garbling, that is the first thing to blame.
- AWQ/GPTQ vs Qualcomm's flow: irrelevant to you. The precompiled assets already encode Qualcomm's own quantization; bringing an AWQ checkpoint means re-exporting through `qai-hub-models`, which is exactly the friction to avoid. Only relevant if you go off-menu to a model with no ready assets (don't).

Sources: [grapeup — W4A16 on Snapdragon 8 Elite](https://grapeup.com/blog/running-llms-on-device-with-qualcomm-snapdragon-8-elite) · [Whisper-Small-Quantized W8A16](https://aihub.qualcomm.com/models/whisper_small_quantized) · [ORT build-models-for-Snapdragon](https://onnxruntime.ai/docs/genai/howto/build-models-for-snapdragon.html)

---

## Q3 — Inference pipeline optimizations

Ranked by payoff-for-effort for a 24h build.

**High payoff, low effort — do these:**

1. **Minimize the prompt / context length.** Prefill dominates TTFT and prefill cost scales with prompt tokens. Keep the system prompt tight, keep each SOS message short (it already is, 1-3 sentences), and cap context at the smallest that fits the job (e.g. request a 1024- or 2048-token context bundle, not 4096). Qualcomm's own memory guidance: 12 GB+ for 3B models, 16 GB+ for 4096-context — a shorter context also loosens memory. This is your single biggest lever on TTFT.
2. **Constant system prompt → prefix/KV reuse.** Genie keeps a KV cache within a dialog session. Keep one long-lived Genie dialog process and feed messages into it so the constant system-prompt prefix is not re-prefilled every message. Do NOT spin up a fresh `genie-t2t-run` per SOS — process reuse alone is a large latency win on a bursty queue. (Cross-request prefix caching across *independent* prompts is not a documented Genie feature; the practical win is keeping the session warm.)
3. **Short, capped output.** The envelope is ≤255 bytes and the JSON is small — set a low max-tokens. Decode time is linear in output tokens, so a tight output schema directly buys latency.
4. **Streaming output** on the dashboard so perceived latency (first token visible) beats wall-clock — good for the judge-facing demo even if total time is unchanged.

**Medium payoff:**

5. **Chunked prefill** (128-token prefill chunks) — the sustained-load research used exactly this to avoid thermal spikes on long prompts. Your prompts are short so this matters less, but it is a free knob if Genie exposes it.
6. **Sequential, not batched.** Genie/QAIRT LLM inference is single-stream on the NPU; there is no server-style continuous batching here. Handle the burst with a **queue**, not a batch (see Q6). Do not waste time trying to batch.

**Do NOT rely on / not available:**

7. **Speculative decoding** — not a documented Genie feature on this hardware. Do not plan around it.
8. **Grammar/JSON-constrained decoding on NPU** — not available in Genie (sampler is temperature/top-k/top-p/seed only). Only on the llama.cpp CPU path. **Get valid JSON via: a rigidly-specified output schema in the prompt + `json.loads` with a one-shot "reformat to valid JSON" repair retry + a regex/field extractor as last resort.** This is the correct pattern for NPU serving; budget for it.
9. **KV-cache quantization** — inherited from the bundle if present; not a knob you tune in 24h.

**CPU vs NPU vs GPU — measured reality (all estimates for X Elite specifically; X Elite Qwen3-4B has no published number):**

- **NPU (Genie/QNN):** best energy-per-token, ~10 tok/s for 3B-class W4A16 (extrapolate ~8-13 tok/s for 4B). NPU usage hits 95-100% during inference; laptop stays quiet/cool — a *good energy story for the dashboard*.
- **CPU (llama.cpp + QMX):** Qualcomm's April 2026 QMX kernels make CPU llama.cpp on Snapdragon genuinely usable and often competitive with the NPU on decode for small models — and it is far easier to set up. This is why it is the fallback, not a last resort.
- **GPU (Adreno):** generally not the win for LLM decode here; skip.
- **NPU vs CPU caveat (important):** there are documented reports that the X Elite NPU can be *slower* than the CPU for some 3B workloads and that Windows memory management causes 2-3 s stalls under sustained NPU+CPU load. This is exactly why the Saturday smoke test must *measure* NPU vs CPU on your actual prompt, not assume the NPU wins. If the NPU underperforms, the QMX-CPU path is a legitimate primary, not a demotion.

**Thermal / sustained-load behavior:**

- No X-Elite-specific sustained-LLM number is published. The best proxy: on Snapdragon 8 Gen 3 (S24 Ultra) sustained decode degraded ~15% from peak (12.2 → 10.4 tok/s) and plateaued stably; a dedicated NPU (Hailo) showed *zero* throttling. A laptop-class X Elite with active cooling should throttle *less* than a phone. Independent reports put an unthrottled 20B model at ~30 tok/s dropping to ~10 tok/s when throttled — but that is a much bigger model than yours.
- **Practical implication for your 5-50 message burst over minutes:** you are unlikely to hit hard thermal throttling with a 4B model in a few-minute demo on a cooled laptop. Mitigations if you do: shorter context, chunked prefill, and pacing the queue (you control ingestion). Mark any throttling claim to judges as "we observed X" only if you actually measured it.

Sources: [Genie config JSON sampler](https://docs.qualcomm.com/nav/home/json.html?product=1601111740062489) · [genie-t2t-run + --profile KPIs](https://docs.qualcomm.com/bundle/publicresource/topics/80-63442-10/genie-t2t-run.html) · [llama.cpp grammar/structured output](https://deepwiki.com/ggml-org/llama.cpp/7.3-grammar-and-structured-output) · [QMX CPU acceleration blog](https://www.qualcomm.com/developer/blog/2026/04/llama-models-acceleration-on-cpu-qmx) · [Edge sustained-load paper](https://arxiv.org/html/2603.23640v2) · [X Elite NPU slower-than-CPU report](https://mysupport.qualcomm.com/supportforums/s/question/0D5dK00000AXy2vSAD/) · [llama.cpp on X Elite discussion](https://github.com/ggml-org/llama.cpp/discussions/8273)

---

## Q4 — LoRA / adapters

**Verdict: on-device LoRA IS supported — and you should NOT use it. No fine-tuning is the right call.**

- Qualcomm supports on-device LoRA via **QAIRT LoRA v3** and the **Genie LoRA API** (`QnnContext_applyBinarySection()`, `qairt-lora-model-creator`). Multiple adapters can be baked into one graph and switched on-target. So the capability exists if the team ever productionizes.
- **For the hackathon: skip it.** The base Qwen3-4B is already strong at triage, Indic translation, and structured output. A LoRA buys you nothing decisive here and costs you: a QLoRA training run on a rented GPU, then re-export of the adapter through the QAIRT LoRA flow onto the precompiled base — a multi-hour, error-prone path with no ready-made asset. That is a **trap** in a 24h budget.
- No pre-existing, drop-in Indic-translation or SOS-classification LoRA adapter exists in Qualcomm-deployable form. The Thursday-night QLoRA idea is not worth it: even if training succeeds, the QAIRT adapter export + validation would eat Saturday hours for a marginal quality gain over base Qwen3-4B.

Sources: [QAIRT LoRA v3 overview](https://docs.qualcomm.com/doc/80-63442-10/topic/lora_v3_overview.html) · [Genie LoRA API tutorial](https://docs.qualcomm.com/bundle/publicresource/topics/80-63442-50/tutorial_lora_v2_22_online_genie_lora_api.html)

---

## Q5 — STT layer

**Verdict: Whisper-Small (AI Hub, W8A16, NPU) as the known path. Whisper-Base if you need it faster. Evaluate Sarvam live but treat it as a bonus, not a dependency.**

- **Whisper on AI Hub:** precompiled variants exist — `whisper_tiny`, `whisper_base`, `whisper_small`, `whisper_small_quantized` (W8A16), `whisper_large_v3_turbo`, `distil_whisper`. Optimized for edge (MHA→SHA, linear→conv), 30 s clips. The reference repo `thatrandomfrenchdude/simple-whisper-transcription` gives you a working starting point.
- **Multilingual/Indic quality by size:** tiny/base multilingual Whisper are weak on Hindi and *quite* weak on Tamil/Telugu; **small is the practical floor for usable Indic transcription**, and large-v3-turbo is markedly better if latency allows. Recommendation: **Whisper-Small as default; keep Base as the "if small is too slow" lever; large-v3-turbo only if the NPU handles it comfortably.** Validate Tamil specifically in the smoke test — it is the weakest common case.
- **Sarvam:** Sarvam-1 (2B) and the Sarvam Edge speech stack are purpose-built for Indian languages and clearly better than Whisper on Indic — but **Sarvam Edge is being rolled out "in collaboration with global device manufacturers"** and does not have an open, downloadable X-Elite NPU asset you can grab and run. Their published on-device numbers (~200 ms first token, ~30 tok/s) are on **Snapdragon 8 Gen 3 phones**, not the X Elite laptop. Sarvam's *cloud REST API* (STT, translate, TTS) is easy to use but is **online**, which violates the offline requirement for the critical path. **Plan: Whisper on-device for the demo's offline chain; at their 11:30 talk ask directly (a) is there a downloadable on-device Sarvam speech asset for Snapdragon X Elite / 8 Elite, and (b) can we run it fully offline. If yes and it's fast to wire, use it for the phone-side capture as a differentiator. If no, Whisper stays.**

Sources: [Whisper-Small AI Hub](https://aihub.qualcomm.com/models/whisper_small) · [Whisper-Small-Quantized](https://aihub.qualcomm.com/models/whisper_small_quantized) · [Sarvam Edge announcement](https://www.sarvam.ai/blogs/sarvam-edge) · [Sarvam Edge product page](https://www.sarvam.ai/products/edge) · [Sarvam-1](https://www.sarvam.ai/blogs/sarvam-1) · [Sarvam Edge on 8 Gen 3, ~200ms/30tps](https://www.adwaitx.com/sarvam-edge-on-device-ai-india/)

---

## Q6 — Pipeline architecture for this scale

**Recommended serving design: single long-lived process, one warm Genie dialog session, a priority queue, two-pass triage-first processing, and overlapped stages.**

```
                 ┌─────────────────────────────────────────────┐
   SOS in  ──▶   │  Ingest + validate (size, coords, audio caps) │
 (LoRa/BLE/mic)  └───────────────┬─────────────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │  PRIORITY QUEUE          │  (dedupe by source ID,
                    │  keyed by quick-signal   │   per-source rate limit)
                    └───────────┬──────────────┘
        ┌───────────────────────┼───────────────────────────┐
        ▼                       ▼                            ▼
  STT worker            LLM worker (single NPU stream)   Metrics wrapper
  (Whisper NPU,         warm Genie session:              (per-stage ms,
   overlaps LLM of      Pass 1: {urgency,category}  ◀──  tokens/s, logs JSONL)
   next msg)            Pass 2: {translated_en, envelope}
```

**Design decisions:**

- **Single process, one warm Genie session.** The NPU is a single LLM stream; do not fork per message. Keeping the session warm preserves the system-prompt prefix in KV cache (Q3 #2).
- **Priority queue, not batch.** During a flood, order matters more than raw throughput. Compute a cheap first-pass urgency (keyword/regex or the tiny model) at ingest to *order the queue*, then let the 4B do the authoritative triage. This means the most-urgent SOS is triaged first even if 50 arrive at once.
- **Two-pass (triage-first, translate-later).** Pass 1 returns just `{urgency, category}` (few output tokens → fast) for *every* queued message, so the dashboard populates a ranked list almost immediately. Pass 2 fills in `{translated_en, envelope}` for messages in priority order. This makes the dashboard feel instant under load — a strong judge moment — and means a low-priority message's translation never blocks a high-priority one's triage. If wall-clock is tight you can fuse into one call; keep two-pass as the "burst is here" mode.
- **Overlap stages.** Run Whisper STT of message N+1 on the NPU/CPU while the LLM handles message N. Since Whisper (encoder-heavy, W8A16) and the LLM (decode-heavy) stress the NPU differently, and the CPU-QMX path is available, you can pin STT and LLM to different compute units to actually overlap rather than contend. Measure contention in the smoke test.
- **Phone NPU (OnePlus 15, 8 Elite Gen 5).** Best use: **on-phone Whisper-Base or Qwen3-0.6B for a pre-triage urgency hint and/or STT at the victim's device**, so the envelope that crosses LoRa is *already* structured and pre-scored. This is the Multi-Device prize story — "intelligence at every hop, not just the command post" — and it also shrinks the LoRa payload (compressed at source). Keep it additive; the command post must work without it.

**Recommended latency budget per stage (targets, not measured — put measured numbers on the dashboard):**

| Stage | Target | "Good" number to show judges |
|---|---|---|
| Ingest + validate | < 5 ms | negligible |
| Whisper STT (small, ~5 s clip) | 0.5-2 s | "voice → text in ~1 s on NPU" |
| LLM Pass 1 (triage, ~20 out tokens) | 0.3-1 s | "urgency scored in < 1 s" |
| LLM Pass 2 (translate+envelope, ~80 tokens) | 1-4 s | "translated + compressed in ~2-3 s" |
| End-to-end per message | ~3-6 s | "SOS → triaged, translated, mapped in ~4 s, offline" |
| Burst (20 msgs) | ranked list < 5 s; all fully processed < 60 s | "20 SOS triaged and ranked in seconds" |

All stage numbers are targets/estimates; the *point* is that `metrics.py` shows the real measured values live, across 3 runs.

---

## Q7 — Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **NPU stack won't come up in the smoke window** | High | This is why the plan front-loads the 9:30 AM smoke test. Have the QMX-CPU llama.cpp fallback pre-tested on your own machine so the pivot is instant. |
| **Windows-on-ARM Python is x64-emulated; `onnxruntime-qnn` needs native ARM64 Python** | High | You MUST install **native ARM64 Python** on the Surface, not x64. `onnxruntime-qnn` / QNN EP require ARM64; running under x64 emulation silently disables the NPU or fails to load the QNN backend. Verify `platform.machine()` returns ARM64 on the actual device first thing. |
| **NPU slower than CPU for 3B/4B (documented on some X Elite units)** | Medium | Measure both in the smoke test; if NPU underperforms, QMX-CPU is a legitimate primary. Do not assume NPU wins. |
| **Memory on 32 GB: Qwen3-4B (W4A16 ≈ 2.5-3 GB weights + KV) + Whisper-Small + Windows + Streamlit + dashboard** | Low-Med | 32 GB is comfortable for ONE 4B + Whisper. It is NOT comfortable for two 4B models or a 7B+; keep to one LLM. Use a 1024-2048 context bundle to cap KV memory. |
| **Genie SDK maturity on Surface Laptop 7 specifically** | Medium | Precompiled Qwen3-4B assets explicitly list Snapdragon X Elite; the documented path is real. But field reports show driver/tooling friction (AnythingLLM + ONNX-QNN was the combo that reliably lit up the NPU for one user; Ollama/LM Studio did not because they are llama.cpp). Fork `simple_npu_chatbot` / use AnythingLLM's ONNX path as a known-good reference. |
| **JSON validity from NPU (no constrained decoding)** | Medium | Rigid prompt schema + `json.loads` + one repair retry + regex fallback. Test with adversarial/garbled input. |
| **Admin/install rights on the loaner Surface** | High (open blocker) | Already flagged in PREP-PLAN — resolve on Discord now. Installing QNN drivers / ARM64 Python / QAIRT SDK needs admin. If locked down, the whole NPU plan needs the CPU fallback. |
| **Indic quality under W4A16** | Low-Med | W4A16 (16-bit activations) largely avoids the multilingual INT4 cliff; still validate Tamil/Hindi output in the smoke test. |

Sources: [Surface Laptop 7 NPU journey — AnythingLLM/ONNX worked, llama.cpp didn't](https://vcfvct.wordpress.com/2025/12/31/running-local-llms-on-a-snapdragon-x-elite-surface-laptop-7-my-journey-to-real-npu-acceleration/) · [QNN Execution Provider docs](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html) · [llama_on_genie memory reqs](https://github.com/qualcomm/ai-hub-apps/blob/main/tutorials/llm_on_genie/README.md)

---

## Do this Thursday / Friday (before Saturday)

Download and pre-stage everything so Saturday is wiring, not downloading (venue Wi-Fi will be chaos):

1. **Download the Qwen3-4B Qualcomm precompiled bundle** from `huggingface.co/qualcomm/Qwen3-4B` — grab the **Snapdragon X Elite** asset specifically (and the 8 Elite Gen 5 one for the phone if relevant). These are large; do it on good Wi-Fi Thursday.
2. **Download Whisper-Small (and Base) AI Hub assets** + clone `thatrandomfrenchdude/simple-whisper-transcription`.
3. **Download the QAIRT SDK** (contains `genie-t2t-run`) and note the ARM64 Windows install steps. Download **AnythingLLM** (the ONNX-QNN NPU path that is known to work) and clone `simple_npu_chatbot`.
4. **Pre-stage the CPU fallback:** Qwen3-4B (or Qwen2.5-3B) **GGUF Q4_K_M** for llama.cpp, plus a recent llama.cpp build (ideally one with QMX/Snapdragon CPU support). Confirm grammar-constrained JSON works here as your "guaranteed-valid JSON" fallback.
5. **Build the CPU prototype (Deliverable A)** with the clean seam: `triage(text) -> dict`. Write the system prompt now (data-tagged `<incoming_sos_message>`, rigid JSON schema for `{urgency, category, translated_en, envelope}`, ≤255-byte envelope rule). Test the same prompt on both Qwen3-4B and Phi-4-mini so the swap is a config change on the CPU path.
6. **Write `metrics.py` from message #1** — per-stage ms, tokens/s (parse `genie-t2t-run --profile` output on Saturday), JSONL log, 3-run history. This is 40 points.
7. **Write the JSON-repair path** (parse → one reformat retry → regex extractor) — because the NPU won't guarantee valid JSON for you.
8. **Confirm admin rights** on the loaner Surface via Discord (open blocker). If no admin, escalate — the plan changes.
9. **Verify ARM64 Python** is what you'll install on the Surface (not x64) so `onnxruntime-qnn` can see the NPU.

---

## What to show judges (optimizations → dashboard numbers / talking points)

- **"We run on the Hexagon NPU, not the CPU"** → live NPU utilization meter at 95-100%, CPU low. Energy story: on-device inference draws far less than a network round-trip; log approximate mAh/message.
- **"NPU vs CPU measured speedup"** → if the QNN port lands, show Qwen3-4B tok/s on NPU vs CPU side by side. This is the single most credible technical-implementation slide. (Only claim the number you measured.)
- **"W4A16 quantization"** → "we run a 4-bit-weight model so a 4B fits and runs fast on a laptop NPU, fully offline" — a concrete optimization judges can score.
- **"Triage-first priority queue under load"** → demo a 20-message flood; show the ranked list appear in seconds while translations backfill. Proves you engineered for the *flood*, not one message.
- **"Message compression for LoRa"** → show the raw SOS vs the ≤255-byte structured envelope the LLM produced. This is a real, technical justification for using an LLM (not decoration) and ties AI directly to the mesh constraint.
- **"Prefix/KV reuse via a warm session"** → "the constant system prompt is prefilled once, not per message" — a real latency optimization to name.
- **"3 repeated runs"** → latency numbers across 3 runs on screen, per the rubric.
- **"Graceful degradation ladder"** → NPU Genie → CPU QMX llama.cpp (still grammar-valid JSON) → rule-based scorer, same UI. Name your own biggest risk (on-device LLM on unfamiliar hardware) and show the fallback live.
- **Phone-side pre-triage (if built)** → "intelligence at every hop" for the Multi-Device award.

---

## Honesty notes / where data is thin

- **No published Qwen3-4B tokens/sec on Snapdragon X Elite specifically exists** as of this research. The ~10-15 tok/s figure is an extrapolation from Llama-3.2-3B (≈10 tok/s, W4A16) and the qualitative "responses came fairly quickly, NPU at 95%" report for Qwen3-4B-Thinking on X Elite. **Measure it Saturday; do not quote the estimate as fact.**
- **No X-Elite sustained-throttling number exists;** the 15% degradation figure is from Snapdragon 8 Gen 3 (a phone), used as a conservative proxy — a cooled laptop should do better.
- **Sarvam Edge on-device availability for X Elite is unconfirmed** — OEM-gated rollout, phone benchmarks only. Verify at their on-site talk before depending on it.
- Genie feature claims (no speculative decoding, no grammar decoding, sampler = temp/top-k/top-p/seed) are from the current QAIRT/Genie docs; if a newer QAIRT release adds these, re-check on-site.
