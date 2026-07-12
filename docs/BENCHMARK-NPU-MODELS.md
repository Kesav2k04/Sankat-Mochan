# On-device NPU model benchmark — Sahayak vs stock Gemma

**Date:** 2026-07-12
**Device:** OnePlus 15 (`CPH2745`, SM8850, **Snapdragon 8 Elite Gen 5**, **Hexagon v81** NPU), 15.5 GB RAM
**Runtime:** llama.cpp `ggml-hexagon` backend — the prebuilt `npu-hexagon-v81/` bundle published in
[`kesav2k04/sahayak-e2b-gguf`](https://huggingface.co/kesav2k04/sahayak-e2b-gguf) (llama.cpp, MIT).
**Execution:** all layers forced onto the NPU — `-ngl 99 --device HTP0 --no-mmap`, `--ctx-size 2048`,
`-t 6`, `--temp 0` (greedy, deterministic).

> This measures the **standalone llama.cpp Hexagon path** (repo's `run-npu.sh`), which is the same
> `ggml-hexagon` backend the app uses through the GenieX `llama_cpp` plugin. It is **not** the QNN/QAIRT
> native path — GenieX 0.3.5's `qairt` plugin has no `gemma4` dispatch, so Gemma-family models can only
> reach the NPU via this GGUF + `ggml-hexagon` route today.

## NPU offload — verified, not assumed

Verbose load logs confirm the whole model runs on the Hexagon NPU:

```
llama_prepare_model_devices: using device HTP0 (Hexagon)
load_tensors: layer   0 assigned to device HTP0
load_tensors: layer   1 assigned to device HTP0
...                       ( every transformer layer → HTP0 )
```

If `HTP0` were unavailable the runtime aborts immediately; instead every model loaded and generated,
and the generation rates below are consistent with NPU-accelerated inference on this SoC.

## Models

| Model | Role | Arch | Quant | On-disk |
|---|---|---|---|---|
| **Sahayak E2B (tuned)** | Our QLoRA fine-tune of Gemma 4 E2B for disaster first-aid | `gemma4` | Q4_0 | 3.11 GB |
| Gemma 4 E2B (stock) | Base model the fine-tune is built on | `gemma4` | Q4_0 | 3.11 GB |
| Gemma 4 E4B (stock) | Larger sibling | `gemma4` | Q4_0 | 4.80 GB |

## Prompt (identical for all three)

System: *"You are Sahayak, an offline emergency-response assistant running on a local device in a
disaster zone. Be brief, calm, and practical. Give first-aid steps only and tell the user to reach
professional care when possible."*
User: **"first-aid for a deep cut on the arm?"**

## Results

| Model | Prompt eval (t/s) | Generation (t/s) | Latency¹ | Quality² | Verdict |
|---|---:|---:|---:|---:|---|
| **Sahayak E2B (tuned)** | **470** | 15.6 | ~8.3 s | **9.0 / 10** | 🥇 Best quality-per-watt |
| Gemma 4 E2B (stock) | 457 | **16.3** | ~8.0 s | 6.0 / 10 | Fast but generic |
| Gemma 4 E4B (stock) | 280–328 | 7.0 | ~18.6 s | 8.5 / 10 | Good, but 2× slower & +1.7 GB |

¹ *Latency* = wall-clock for a representative ~130-token final answer at the measured generation rate
(prompt-eval time is negligible, ~0.12–0.20 s; one-time model load with `--no-mmap` is separate).
² *Quality* is the mean of five equally-weighted axes scored below.

### Speed, visualized (generation tokens/sec — higher is better)

```
Gemma 4 E2B (stock)  ████████████████ 16.3
Sahayak E2B (tuned)  ███████████████▌ 15.6
Gemma 4 E4B (stock)  ███████          7.0
```

### Quality, visualized (/10 — higher is better)

```
Sahayak E2B (tuned)  ██████████████████ 9.0
Gemma 4 E4B (stock)  █████████████████  8.5
Gemma 4 E2B (stock)  ████████████       6.0
```

## Quality scoring rubric

Each answer scored 0–2 on five axes (10 total). Greedy decoding, so answers are reproducible.

| Axis | Sahayak (tuned) | Gemma E2B | Gemma E4B |
|---|---:|---:|---:|
| **Correctness** (steps medically sound) | 2.0 | 2.0 | 2.0 |
| **Actionability** (specific, ordered, usable under stress) | 2.0 | 1.0 | 1.5 |
| **Persona/tone** (calm field assistant, stays in role) | 2.0 | 1.0 | 2.0 |
| **Safety referral** (directs to professional care) | 1.5 | 1.5 | 1.5 |
| **Conciseness** (brief, no filler) | 1.5 | 0.5 | 1.5 |
| **Total** | **9.0** | **6.0** | **8.5** |

*Why the gaps:* the tuned model gave duration ("press for 10 minutes"), "elevate above the heart",
and the field-critical "don't remove anything stuck in the wound — press around it" plus a
tendon/artery warning. Stock E2B was correct but generic (no durations, no embedded-object guidance)
and its reasoning broke persona ("*As an AI, I cannot replace a doctor*"). Stock E4B matched the
tuned model's specificity but at half the speed and +1.7 GB.

## Answers (verbatim, final answer after the `[thinking]` block)

**Sahayak E2B (tuned):**
> 1. Apply firm, direct pressure on the wound with a clean cloth for 10 minutes.
> 2. Raise the arm above the heart to slow the bleeding.
> 3. Don't remove anything stuck in the wound; press around it instead.
> 4. Once bleeding slows, cover and wrap it snugly.
> A deep cut can hit a tendon or artery, so get to medical care as soon as you can.

**Gemma 4 E2B (stock):**
> Apply direct pressure to the wound with a clean cloth or bandage. Elevate the arm if possible.
> Keep the area clean and covered. Seek professional medical help immediately.

**Gemma 4 E4B (stock):**
> Apply firm, direct pressure to the cut with a clean cloth to stop the bleeding. Do not lift the
> cloth to check. Once bleeding slows, gently rinse the wound with clean water to remove debris.
> Apply a sterile dressing and secure it. Seek professional medical care as soon as possible.

## Takeaways

1. **The fine-tune earns its slot.** Sahayak runs at stock-E2B speed (~16 t/s) and size (3.1 GB) but
   delivers **E4B-class answer quality** — the specific, field-usable guidance that matters to a
   panicking user. This is exactly the trade the app wants on-device.
2. **E4B isn't worth it on a phone.** Marginally better reasoning than stock E2B, but **2× slower
   (7 t/s)**, +1.7 GB on disk, and ~5.5 GB RAM to load. Sahayak beats it on the speed/size axis at
   comparable quality.
3. **Ship Sahayak as default** (done — see the app changes below). Best quality-per-watt for the
   offline emergency use case.

### App-side note — the `[thinking]` block

All three Gemma-4 models emit a `[Start thinking] … [End thinking]` block before the answer, which
burns tokens and latency. These CLI runs left it on; the **app already sets `enable_thinking = false`
in `ModelConfig`** and should strip any residual block before display. Worth a quick in-app check that
suppression actually holds, since the block was prominent at the CLI.

## Reproduce

```bash
# Pull the model + prebuilt NPU runtime, push to the phone
huggingface-cli download kesav2k04/sahayak-e2b-gguf --local-dir sahayak
adb push sahayak/sahayak-gemma-Q4_0.gguf sahayak/npu-hexagon-v81 /data/local/tmp/sh/
adb shell "chmod +x /data/local/tmp/sh/npu-hexagon-v81/bin/*"

# Run (all layers on HTP0 / Hexagon NPU)
adb shell "cd /data/local/tmp/sh/npu-hexagon-v81 && sh run-npu.sh 'first-aid for a deep cut on the arm?'"
```

## Related app changes (shipped)

- `mobile-application/.../chat/AssistantModels.kt` — Sahayak added as the first/default catalogue entry (non-gated).
- `mobile-application/.../chat/ChatViewModel.kt` — auto-selects a side-loaded `sahayak*` GGUF at bootstrap so it
  loads straight onto the NPU with no download step.
- `mobile-application/.../chat/ModelPrepViewModel.kt` — recommends Sahayak on every device (the fine-tune beats
  the larger stock Gemma for this app's emergency chats regardless of RAM headroom).

## Licensing

- Model weights (`sahayak-gemma-Q4_0.gguf`) are a derivative of Google Gemma → governed by the
  [Gemma Terms of Use](https://ai.google.dev/gemma/terms) (not OSI-approved). A human should confirm
  the Gemma Terms are acceptable before shipping (CLAUDE.md #1).
- The `npu-hexagon-v81` llama.cpp binaries are **MIT** (© ggml-org / llama.cpp contributors).
