# Sahayak on the mobile NPU — llama.cpp / Hexagon (Snapdragon 8 Elite Gen 5)

Run the Sahayak emergency assistant on the **Hexagon NPU** of the OnePlus 15
(Snapdragon 8 Elite Gen 5) using **llama.cpp** end to end. The finetune stays as **Gemma 4
E2B** — no re-base. The route is a **custom Q4_0 GGUF** on llama.cpp's Snapdragon Hexagon
backend (`GGML_HEXAGON=ON`); GenieX can run the same GGUF as an alternative front-end.

> Not using Qualcomm AI Hub's quantize/compile. Gemma has no QNN compile on AI Hub
> (`gemma_4_e2b_it` is `skip_export: true`, `geniex_llamacpp` runtime only). llama.cpp is the
> path that puts *your finetuned Gemma* on the NPU. (An AI-Hub QNN path exists only if you
> re-base to Qwen3-4B — kept for reference in `alt-aihub-qwen/`.)

## The one rule: quantize to Q4_0, not Q4_K_M

The Hexagon backend (HTP) wants **Q4_0** or **Q8_0**. Qualcomm's GenieX notes: *"Q4_K_M is a
suboptimal quant for HTP — it prefers Q4_0 / Q8_0."* llama.cpp's Snapdragon docs use Q4_0
exclusively and repack it for the NPU internally. So the whole pipeline targets **Q4_0**.

## Model facts (confirmed from `kesav2k04/sahayak-e2b`)

- Base: **`google/gemma-4-E2B-it`**, `model_type: gemma4`, arch `Gemma4ForConditionalGeneration`
  (multimodal text+image+audio). It is **Gemma 4, not Gemma 3n** → `convert_hf_to_gguf.py`
  supports it (public Gemma-4-E2B GGUFs already exist). We convert the **text tower** only;
  vision/audio aren't needed for the assistant.
- LoRA: r=32 / α=32 on the language tower (`q/k/v/o/gate/up/down_proj`); vision/audio frozen.
- **Merged weights already published** in the repo under `merged/` — no re-merge/re-train.

## Pipeline

```
kesav2k04/sahayak-e2b :: merged/         (download; already merged)
        ▼
deploy/npu/build_gemma_gguf.py           convert → imatrix → llama-quantize Q4_0
        ▼
deploy/npu/eval_gguf.py                   host-side quality review (CLAUDE.md #6)
        ▼
deploy/npu/run_gemma_npu.sh               adb push + llama.cpp on D=HTP0  (Hexagon NPU)
```

## Step 0 — build llama.cpp

> **Already installed on the X Elite dev box** at `C:\Users\qcwor\llama.cpp` — prebuilt
> win-arm64 binaries (build b9966: `llama-quantize/llama-imatrix/llama-cli` under
> `build\bin\`) plus the Python converter deps (torch 2.11.0+cpu, transformers, gguf) in the
> Python 3.12 at `...\Programs\Python\Python312`. Gemma 4 conversion support verified
> (`conversion/gemma.py` registers `Gemma4ForConditionalGeneration`). Pass
> `--llama-cpp C:\Users\qcwor\llama.cpp` to the scripts below. The instructions here are for
> reproducing that install on the phone / another box.

Two builds: a **host** build (to convert/quantize/eval on your laptop) and an **Android
Snapdragon** build (to run on the phone). On this X Elite box the host side used the prebuilt
win-arm64 release (no compiler needed); the phone still needs the Android Snapdragon build.

```bash
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp     # MIT
pip install -r requirements/requirements-convert_hf_to_gguf.txt      # converter deps

# Host build (CPU is fine — convert & quantize are CPU ops):
cmake -B build && cmake --build build -j

# Android Snapdragon build (Hexagon NPU backend), from the Android NDK toolchain:
cmake --preset arm64-android-snapdragon-release -B build-snapdragon   # sets GGML_HEXAGON=ON
cmake --build build-snapdragon
```

## Step 1 — get the merged weights

```bash
# Gated repo — use your HF token (accept Gemma terms on HF first). Do NOT hardcode it.
huggingface-cli download kesav2k04/sahayak-e2b --include 'merged/*' --local-dir out/sahayak-e2b
# → out/sahayak-e2b/merged/{model.safetensors,config.json,chat_template.jinja,tokenizer*}
```

## Step 2 — convert + quantize to Q4_0

```bash
python deploy/npu/build_gemma_gguf.py \
    --merged-checkpoint out/sahayak-e2b/merged \
    --llama-cpp /path/to/llama.cpp
# → deploy/npu/out/sahayak-gemma-Q4_0.gguf   (with an in-domain imatrix from train.jsonl)

# audit the exact commands without running:  add --dry-run
# higher fidelity option:                    --quant Q8_0
# skip the importance matrix (faster):       --no-imatrix
```

The importance matrix is built from `finetune/data/train.jsonl`, so the 4-bit encodings are
calibrated on the emergency-response distribution rather than generic text.

## Step 3 — review the quantized model (do not skip)

```bash
python deploy/npu/eval_gguf.py \
    --gguf deploy/npu/out/sahayak-gemma-Q4_0.gguf \
    --llama-cpp /path/to/llama.cpp \
    --eval finetune/data/eval_holdout.jsonl --limit 10
```

Prints model answer vs reference per holdout prompt, auto-flagging empty/degraded outputs.
A human confirms first-aid answers are still correct and safe before shipping (CLAUDE.md #6).

## Step 4 — run on the phone (Hexagon NPU)

```bash
export LLAMA_CPP=/path/to/llama.cpp
bash deploy/npu/run_gemma_npu.sh \
    deploy/npu/out/sahayak-gemma-Q4_0.gguf \
    "A wall collapsed and someone is bleeding badly. What do I do?"
```

`run_gemma_npu.sh` pushes the GGUF, runs llama.cpp with `M=<model> D=HTP0 NDEV=1` (one NPU
session suits a 2B-class model), injects Sahayak's system prompt, and keeps user text inside
the user turn only (CLAUDE.md #7). GenieX alternative: `geniex infer <gguf> --device npu`.

### Confirm it's actually on the NPU

```bash
GGML_HEXAGON_VERBOSE=1 bash deploy/npu/run_gemma_npu.sh <gguf> "test"
```

The Hexagon backend has limited op coverage; unsupported ops fall back to CPU. Check the log
shows layers on HTP. Also benchmark GenieX's **default hybrid** (NPU+GPU+CPU) — Qualcomm has
measured it faster than pinned-NPU on some models (~90 vs ~60 tok/s prefill).

## Files

| File | Role |
|------|------|
| `build_gemma_gguf.py` | convert → imatrix → llama-quantize **Q4_0** |
| `eval_gguf.py`        | host-side quality review of the quantized GGUF |
| `run_gemma_npu.sh`    | adb push + run on the Hexagon NPU |
| `alt-aihub-qwen/`     | reference-only: AI Hub QNN path (requires re-base to Qwen3-4B) |

## Sources (all open-license, per CLAUDE.md #3)

- llama.cpp Snapdragon/Hexagon backend — https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md
- llama.cpp quantize tool — https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md
- Qualcomm GenieX (custom GGUF, NPU/GPU/CPU, Q4_0 for HTP) — https://github.com/qualcomm/GenieX
