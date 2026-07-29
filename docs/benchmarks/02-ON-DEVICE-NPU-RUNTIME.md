# 02 — On-device NPU runtime measurements

**What was measured:** whether Sahayak-E2B runs usefully on a phone's NPU with no network, and what it
costs in throughput and storage versus the stock models.

**Claim tiers:** **[R]** reproducible · **[H]** human-graded · **[M]** single measured run (real, but n=1).

---

## 1. Configuration

| | |
|---|---|
| Date | 2026-07-12 |
| Device | OnePlus 15 — `CPH2745`, `SM8850`, **Snapdragon 8 Elite Gen 5**, **Hexagon v81** NPU, 15.5 GB RAM |
| Runtime | `llama.cpp` **`ggml-hexagon`** backend, prebuilt `npu-hexagon-v81/` bundle (MIT) |
| Execution | `-ngl 99 --device HTP0 --no-mmap --ctx-size 2048 -t 6 --temp 0` |
| Decoding | greedy, temperature 0 → **deterministic, byte-identical outputs** |
| Quantisation | Q4_0 (the Hexagon HTP backend prefers `Q4_0`/`Q8_0` over K-quants) |

**NPU offload verified, not assumed.** Verbose load logs show every one of the 35 transformer layers
assigned to `HTP0`:

```
llama_prepare_model_devices: using device HTP0 (Hexagon)
load_tensors: layer   0 assigned to device HTP0
load_tensors: layer   1 assigned to device HTP0
...                       ( all 35 layers -> HTP0 )
```

If `HTP0` were unavailable the runtime aborts rather than silently falling back to CPU, so a successful
run is itself evidence of NPU execution.

---

## 2. Results **[M]** — one run per model, single session, one handset

| Model | Prompt eval | Generation | Latency¹ | On disk **[R]** | Quality² |
|---|---:|---:|---:|---:|---:|
| **Sahayak E2B** (tuned) | **470 tok/s** | 15.6 tok/s | ~8.3 s | **3.119 GiB** (3.35 GB) | 9.0 / 10 **[H]** |
| Gemma 4 E2B (stock) | 457 tok/s | **16.3 tok/s** | ~8.0 s | 3.119 GiB (3.35 GB) | 6.0 / 10 **[H]** |
| Gemma 4 E4B (stock) | 280–328 tok/s | 7.0 tok/s | ~18.6 s | 4.80 GiB (5.15 GB) | 8.5 / 10 **[H]** |

¹ **Latency is derived, not stopwatched** — a representative ~130-token answer at the measured generation
rate. Prompt-eval time is negligible (~0.12–0.20 s). The one-time model load under `--no-mmap` is
excluded and is *not* small.

² **The 9.0 / 6.0 / 8.5 scores are a single prompt** ("first-aid for a deep cut on the arm?"), self-scored
on a 5-axis rubric. **They are superseded by the 50-prompt held-out evaluation** in
[`01-HELDOUT-CAPABILITY-EVAL.md`](01-HELDOUT-CAPABILITY-EVAL.md) and should not be quoted as a headline.
They are retained here only because they were recorded alongside the throughput run.

### 2.1 Size discipline **[R]**

The published GGUF is **exactly 3,349,514,592 bytes**:

| Unit | Value |
|---|---|
| Bytes | 3,349,514,592 |
| **GiB** (2³⁰ — what `llama.cpp` prints) | **3.119** |
| **GB** (10⁹ — what the HF file listing shows) | **3.350** |

Earlier docs said "3.11 GB" (actually GiB) and the model card said "~3.35 GB" (decimal GB). Same file.
Always state the unit. Applying the same discipline: E4B is **4.80 GiB = 5.15 GB**, and the saving is
**1.69 GiB = 1.82 GB**.

### 2.2 The honest reading

- Sahayak is **second** on raw throughput, 0.7 tok/s behind stock E2B — the LoRA adapter is merged into
  the weights, so it adds no architectural cost, and the gap is within single-run noise.
- Against E4B: **2.2× the throughput** (15.6 vs 7.0 tok/s) and **1.69 GiB less** on disk, plus roughly
  **5.5 GB vs 3.5 GB RAM** to load. On a phone that difference decides whether the model loads at all.
- E4B scored marginally better than *stock* E2B on the single prompt, but it is not worth 2.2× the
  latency on-device.

---

## 3. Runtime caveats a reviewer will ask about

1. **This is the GGUF path, not the vendor NPU path.** Measurements come from `llama.cpp`'s
   `ggml-hexagon` backend. The QNN / QAIRT native route was unavailable: GenieX 0.3.5's `qairt` plugin
   has **no `gemma4` dispatch**, so Gemma-family models can only reach this NPU via GGUF today. Numbers
   are therefore **not** a ceiling for this silicon.
2. **The `[thinking]` block was left on.** All three Gemma 4 models emit a
   `[Start thinking] … [End thinking]` block before the answer, spending tokens and latency. These CLI
   runs did not suppress it; the app sets `enable_thinking = false`. **The reported latency is therefore
   pessimistic relative to app behaviour, and the two are not directly comparable.**
3. **n = 1, no thermal control.** No repeated trials, no confidence interval, no cooldown protocol, no
   fixed battery level. Sustained phone throughput drops as the SoC heats; a single run cannot show that.
4. **No time-to-first-token.** TTFT dominates perceived responsiveness and was not recorded separately.
5. **No energy measurement.** **The earlier "best quality-per-watt" claim is withdrawn** — no power,
   current, or energy-per-token figure was ever taken. See
   [`03-LIMITS-AND-ROADMAP.md`](03-LIMITS-AND-ROADMAP.md) §2.
6. **RAM figures are approximate**, read from load behaviour rather than a sampled RSS measurement.
7. **One device.** Hexagon v81 / SM8850 only. The model card also mentions Snapdragon X Elite, but **no
   X Elite benchmark exists in this repository** — do not cite one.

---

## 4. Reproduce

```bash
# Pull the model + prebuilt NPU runtime, push to the phone
huggingface-cli download kesav2k04/sahayak-e2b-gguf --local-dir sahayak
adb push sahayak/sahayak-gemma-Q4_0.gguf sahayak/npu-hexagon-v81 /data/local/tmp/sh/
adb shell "chmod +x /data/local/tmp/sh/npu-hexagon-v81/bin/*"

# Run with every layer forced onto HTP0 / Hexagon NPU
adb shell "cd /data/local/tmp/sh/npu-hexagon-v81 && sh run-npu.sh 'first-aid for a deep cut on the arm?'"
```

Needs ~3.5 GB free RAM — reboot or close apps first, or `--no-mmap` will thrash. Because decoding is
greedy at temperature 0, a correct reproduction returns byte-identical text.

Other Snapdragon parts: rebuild `llama.cpp` with the `arm64-android-snapdragon-release` preset for your
Hexagon version. See the
[llama.cpp Snapdragon docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md).

---

## 5. Licensing

Model weights are a Google Gemma derivative → **[Gemma Terms of Use](https://ai.google.dev/gemma/terms)**,
which is **not** OSI-approved; the Gemma Prohibited Use Policy applies. The `npu-hexagon-v81` `llama.cpp`
binaries are **MIT** (© ggml-org / llama.cpp contributors). The Sahayak Emergency Dataset v2 is
**Apache-2.0**. Three separate licences — none covers all three artefacts.
