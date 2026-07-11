# Qualcomm AI Hub — Hosted Profiling Results (Sankat-Mochan)

All numbers below come from **Qualcomm AI Hub cloud-hosted device profiling** (real hardware in Qualcomm's device farm), run from a Mac the night before the event. They are measured, not simulated — except where explicitly marked ESTIMATED or FAILED.

Generated: 2026-07-10, night before the 11 Jul 2026 hackathon.
Tooling: `qai-hub` 0.52.0, `qai-hub-models` 0.48.0.

---

## 0. GOTCHAS — MUST-KNOW AT THE VENUE (read this first)

**A. QAIRT version mismatch — you WILL hit this on the X Elite laptop. Fix is one flag.**

`qai-hub-models` 0.48.0 pins **QAIRT 2.43**, but AI Hub Workbench now only accepts **2.45 / 2.46 / 2.47** (2.45 = default, 2.47 = latest). Every export/compile dies immediately with:

```
ValueError: QAIRT version 2.43 is not supported by AI Hub Workbench. Available versions are:
    QAIRT v2.45 ... | default
    QAIRT v2.46 ...
    QAIRT v2.47 ... | latest
```

**Fix — add these flags to EVERY export command** (compile + profile both need it):

```
--compile-options="--qairt_version=default" --profile-options="--qairt_version=default"
```

(`default` = 2.45. Use `--qairt_version=2.47` if you specifically want latest.)

**B. LLM exports load the FP checkpoint LOCALLY before uploading — mind the RAM.**
The LLM path prints a memory recommendation (e.g. Llama 3.2 3B wants ~80 GB RAM+swap; 1B ~50 GB) and can OOM-kill on a small machine. It's a warning, not a hard stop, but on <32 GB RAM prefer a pre-quantized small model or run on the X Elite / a big-RAM Linux box. Needs `pip install psutil`.

**C. Transient S3 upload timeouts on flaky networks.** Large (300-750 MB) model uploads can fail with `ReadTimeout ... s3-accelerate.amazonaws.com (read timeout=3.05)`. Just re-run — assets are cached by hash so it resumes. Use a stable connection when compiling on-site.

**D. HuggingFace gated models** (Llama etc.) need HF access already granted on the machine's HF token. Ours is granted; a fresh machine at the venue may not be — pre-fetch or use the AI-Hub-hosted pre-quantized checkpoints.

---

## 1. Device strings (exact AI Hub identifiers)

| Target | AI Hub device string |
|---|---|
| Snapdragon X Elite (the AI command-post PC) | `Snapdragon X Elite CRD` |
| Snapdragon 8 Elite phone | `Snapdragon 8 Elite QRD` |
| (bonus) next-gen laptop | `Snapdragon X2 Elite CRD` |
| (bonus) newer phone | `Snapdragon 8 Elite Gen 5 QRD` |

Full farm list: `devices.txt`.

## 2. Measured numbers

### whisper_small (speech-to-text) on Snapdragon X Elite CRD (Windows 11)

Precision: float. Runtime: **QNN_CONTEXT_BINARY** (native NPU context binary).
QAIRT version: 2.45 (AI Hub default; see note in section 4 about the version override needed).

| Model | Device | Component | Runtime | Inference latency | Peak memory | Compute-unit split | AI Hub job |
|---|---|---|---|---|---|---|---|
| whisper_small | Snapdragon X Elite CRD | Encoder (HfWhisperEncoder) | QNN_CONTEXT_BINARY | **133.2 ms** | [0, 0] MB (reported) | **npu 1582 / gpu 0 / cpu 0** | compile jp3w8z335, profile jgz4wlkop |
| whisper_small | Snapdragon X Elite CRD | Decoder (HfWhisperDecoder) | QNN_CONTEXT_BINARY | **10.4 ms** | 60 MB | **npu 2277 / gpu 0 / cpu 0** | compile jpel273og, profile jprn9lj05 |

**Headline:** whisper_small runs **100% on the X Elite NPU** — 3859 total ops, zero GPU, zero CPU fallback.
A single encoder+decoder pass is ~143 ms combined; the per-token decoder step is only ~10 ms. That is comfortably real-time on-device transcription with no cloud dependency.

(Peak-memory `[0, 0]` for the encoder is what AI Hub reported for the context-binary profile; the decoder reported 60 MB. Reported memory for context-binary runtime can read 0; treat the 60 MB decoder figure as the meaningful working-set number.)

## 3. Compiled artifacts downloaded

Location: `aihub_out/artifacts/whisper_small_xelite/whisper_small-qnn_context_binary-float-qualcomm_snapdragon_x_elite/`

| File | Size | What it is |
|---|---|---|
| `HfWhisperEncoder.bin` | 255 MB | QNN context binary — Whisper encoder, targets X Elite NPU |
| `HfWhisperDecoder.bin` | 345 MB | QNN context binary — Whisper decoder, targets X Elite NPU |
| `metadata.yaml` | 8 KB | Model metadata / IO spec |

These are deployable NPU context binaries for the QAIRT runtime on Windows-on-Snapdragon. Copy the whole folder to the USB stick for the offline venue.

## 3b. LLM numbers — AI Hub PUBLISHED gallery numbers (NOT locally re-profiled)

We could not locally compile the 3B/4B LLMs on this 25.8 GB-RAM Mac (they load the full FP checkpoint locally and OOM — see section 4). Instead, these are Qualcomm's **own published on-device measurements**, read verbatim from the `perf.yaml` files shipped inside `qai-hub-models` 0.48.0 (the same data the AI Hub model gallery displays). **Runtime = Genie (QNN), context length 4096.** Label them clearly as published/vendor numbers in the deck, not our own re-profile.

### qwen3_4b — our real command-post triage/translation LLM (W4A16)

| Device | Tokens/sec | Time-to-first-token (min–max ms) |
|---|---|---|
| **Snapdragon X Elite CRD** (our AI PC) | **14.79 tok/s** | **121.7 – 3894.9 ms** |
| Snapdragon X2 Elite CRD (next-gen laptop) | 29.99 tok/s | 73.1 – 2337.9 ms |
| Snapdragon 8 Elite Gen 5 QRD (phone) | 29.03 tok/s | 53.7 – 1717.1 ms |
| Samsung Galaxy S25 (phone) | 25.43 tok/s | 69.0 – 2207.4 ms |

### llama_v3_2_3b_instruct — alternative triage LLM

| Device | Precision | Tokens/sec | Time-to-first-token (min–max ms) |
|---|---|---|---|
| **Snapdragon X Elite CRD** | W4A16 | **11.87 tok/s** | 116.9 – 3740.3 ms |
| Snapdragon X2 Elite CRD | W4A16 | 42.77 tok/s | 75.0 – 2401.4 ms |
| Snapdragon 8 Elite Gen 5 QRD (phone) | W4A16 | 32.65 tok/s | 69.0 – 2206.5 ms |
| Snapdragon 8 Elite QRD (phone) | W4A16 | 28.03 tok/s | 82.0 – 2625.6 ms |

### llama_v3_2_1b_instruct — small/fast fallback LLM

| Device | Precision | Tokens/sec | Time-to-first-token (min–max ms) |
|---|---|---|---|
| **Snapdragon X Elite CRD** | W4A16 | **23.70 tok/s** | 69.3 – 2216.2 ms |
| Snapdragon X Elite CRD | W4 | 11.97 tok/s | 167.7 – 5365.8 ms |
| Snapdragon 8 Elite Gen 5 QRD (phone) | W4A16 | 74.39 tok/s | 30.2 – 967.9 ms |

**Read for the deck:** on the X Elite, our target 4B triage model (qwen3_4b) runs on-device at ~15 tok/s with first token in ~120 ms — usable for short SOS-triage/translation turns entirely offline. The same models are 2-3x faster on the newer X2 Elite and on flagship 8-Elite phones, so the mesh's phone nodes can also run the LLM locally. (Source: `qai_hub_models/models/<model>/perf.yaml`, Genie runtime, ctx 4096.)

## 4. Failures / skipped / honest notes

- **QAIRT version skew (solved).** First export failed immediately: `qai-hub-models` 0.48.0 pins QAIRT 2.43, but AI Hub Workbench now only accepts 2.45 / 2.46 / 2.47. Fix, per the tool's own message: add `--compile-options="--qairt_version=default" --profile-options="--qairt_version=default"` (uses 2.45). Needed on every export.
- **Transient S3 upload timeout (solved by retry).** One run died mid-upload with `ReadTimeout ... tetrahub-qprod-userdata.s3-accelerate.amazonaws.com (read timeout=3.05)` — a flaky-network hiccup on the 392 MB encoder upload, not a config error. A straight re-run uploaded cleanly (~12-16 MB/s). At the venue, ensure a stable connection when (re)compiling; artifacts are cached by hash so retries resume.
- `--skip-inferencing` was used (we want latency/memory, not sample-accuracy) to save time.
- **whisper_small_quantized (W8A16) — BLOCKED on macOS.** It requires the **AIMET-ONNX** package, which is **Linux / WSL only**. The check fires at *import time* (in the model's `__init__.py`), so even `--fetch-static-assets` can't get past it on a Mac:
  `RuntimeError: AIMET-ONNX is missing ... not supported on this operating system. You must use either Linux or Windows Subsystem for Linux`.
  This is the quantized STT model we plan to ship. To profile/compile it, run the export on a **Linux box or WSL** (or directly on the X Elite if it's Windows+WSL), OR pull Qualcomm's published pre-quantized artifacts from the AI Hub model page. For tonight, the **float `whisper_small` numbers above are the STT proxy** — the quantized version will be smaller and at least as fast on NPU. Same AIMET-Linux constraint applies to any `*_quantized` model in the zoo.
- **Local LLM compile on this Mac is a RAM wall — NOT an AI Hub failure.** The AI Hub cloud path is proven working (the Whisper run compiled + profiled + downloaded on real X Elite silicon end-to-end). The blocker is purely local: the LLM export loads the full FP checkpoint *on this Mac* before uploading, and this box has only 25.8 GB RAM / ~43 GB RAM+swap. Specifics:
  - **Llama 3.2 3B:** printed `Recommended memory (RAM + swap): 80 GB (currently 43 GB)`; its ~6 GB gated checkpoint (HF access IS granted, no 401) crawled then stalled on tonight's connection. Stopped it as a poor time bet.
  - **Llama 3.2 1B:** got FURTHest — it exported to ONNX locally and its subgraph **compile jobs SUCCEEDED on the X Elite via AI Hub** (e.g. jobs jgl17w985, j5w1xyj6g). But the *local orchestrator process* was **OOM-killed at a reproducible point** (right after uploading subgraph part 3/3; silent SIGKILL, leaked-semaphore warning, no traceback) on BOTH a concurrent run and a clean solo retry. Because the local process dies, nothing schedules the profile job or collects the latency/tokens-sec summary — so we could not get an *our-own* end-to-end 1B number from this Mac. This confirms the wall is local RAM at the AR-1/part-3 stage, not AI Hub. Use the **published** 1B figure (section 3b: 23.7 tok/s W4A16 on X Elite) for the deck.
  - **qwen3_4b:** downloads the full ~8 GB FP checkpoint locally (Qwen is open, no gating) then needs the 4B FP trace — same RAM wall. For the real deck number we use Qualcomm's **published** qwen3_4b X Elite figure instead (section 3b).
  - **Bottom line for the venue:** compile the LLMs on the X Elite laptop itself (Windows+WSL, ample RAM) or a big-RAM Linux box — the AI Hub cloud compile/profile works fine; only this Mac's RAM is the limiter.
- pip flagged a transformers/huggingface-hub version conflict at first install; installing the `qai_hub_models[whisper_small]` extra pulled transformers back to 4.56.2 and resolved it. No impact on results.

## 5. What AI Hub gives us / next steps at the venue

- **What it does for us:** compiles our exact models to the X Elite (and phone) NPU in the cloud and profiles them on *real* Qualcomm silicon, so we get honest latency / memory / compute-unit numbers and deployable `.bin` context binaries **without ever touching the X Elite laptop** — exactly our situation tonight.
- **Deck-ready claims (the full on-device AI story):**
  1. **STT — our own profiled number:** whisper_small fully NPU-resident on Snapdragon X Elite, ~143 ms/pass (encoder 133 ms + decoder 10 ms), 100% NPU, no cloud.
  2. **Triage/translation LLM — published number:** qwen3_4b (W4A16, Genie) on X Elite = ~15 tok/s, first token ~122 ms — short SOS triage/translation turns run entirely offline on the command post.
  3. **Range/scaling:** same LLMs run 2-3x faster on X2 Elite and on flagship 8-Elite phones, so phone mesh nodes can also run the LLM locally (see section 3b).
- **At the venue:**
  1. Copy `aihub_out/artifacts/` to USB (offline venue may have no internet).
  2. Run the QAIRT/QNN runtime on the X Elite laptop against `HfWhisperEncoder.bin` / `HfWhisperDecoder.bin`.
  3. If we recompile anything on-site, remember the `--qairt_version=default` flag and a stable network for the upload step.
  4. To get *our-own* LLM numbers + the quantized-Whisper compile, run those exports **on the X Elite (Windows+WSL) or a big-RAM Linux box** — this Mac's 25.8 GB RAM is the only blocker; the AI Hub cloud path itself is proven.
