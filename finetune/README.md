# Sahayak fine-tuning

Fine-tune **Gemma 4 (E2B/E4B)** into the offline emergency-response assistant, per
[`SAHAYAK_DATASET_SPEC.md`](../docs/SAHAYAK_DATASET_SPEC.md). Two files:

| File | What it does |
|------|--------------|
| `sahayak_finetune.py` | Trains a QLoRA adapter (Unsloth on CUDA; transformers+PEFT fallback elsewhere), exports LoRA / merged / GGUF. |
| `validate_dataset.py` | Mechanical validator for a generated batch (spec §8.1 step 2). Exit 0 = clean. |

Everything here is **Apache-2.0**. The Gemma **weights** are gated under Google's Gemma Terms of
Use (not OSI-approved) — accept the terms on Hugging Face and set `HF_TOKEN` before training.

## Cross-platform (Windows / Linux / Surface, x86-64 or ARM)

The trainer detects your hardware and picks a backend automatically (`--backend auto`):

- **NVIDIA CUDA present →** Unsloth QLoRA — the fast, spec-recommended path.
- **No CUDA (CPU / Apple MPS / Windows-on-ARM / Surface) →** a transformers + PEFT LoRA fallback.
  It *runs everywhere* so you can validate the whole pipeline on a laptop, but it's slow — do the
  real run on a CUDA GPU.

All paths use `pathlib`, so the identical command line works in PowerShell, bash, or zsh.

## Setup

```bash
# 1) Install torch for YOUR platform first (see https://pytorch.org). Then:
pip install -r requirements.txt
# 2) Gemma is gated — accept its terms on HF, then:
#    PowerShell:  $env:HF_TOKEN = "hf_..."
#    bash/zsh:    export HF_TOKEN=hf_...
```

## Validate a batch (no GPU / no torch needed)

```bash
python validate_dataset.py data/sample.jsonl
python validate_dataset.py data/staging/batch_02.jsonl --fingerprints data/fingerprints.txt
```

Checks: JSON parses · schema in-vocab · system prompt byte-identical · assistant length budget
(≤600, ≤200 for `relay`) · unique ids · near-duplicate user messages (token overlap > 0.85).

## Train

```bash
python sahayak_finetune.py \
  --train data/train/all.jsonl \
  --eval  data/eval_holdout.jsonl \
  --model unsloth/gemma-3n-E4B-it \
  --out   out/sahayak-e4b \
  --export-gguf q4_k_m
```

Notes:
- `--model` — the spec calls the target "Gemma 4 E4B"; pass the E2B id to train the smaller one.
  Override with any Unsloth/HF Gemma id you've been granted.
- Loss is computed on assistant turns only (`train_on_responses_only`), vision layers stay frozen.
- **Whatever chat template you train with must match on-device inference**, or quality craters
  (spec §3). Default `--chat-template gemma-4`, auto-falling back to `gemma-3`/`gemma`.
- `--export-gguf q4_k_m` emits a GGUF the app's llama.cpp runtime loads directly (Unsloth path).
  On the CPU fallback, convert the merged model with llama.cpp's `convert_hf_to_gguf.py`.

Run `python sahayak_finetune.py --help` for every knob (epochs, lr, LoRA rank, batch size, …).

## Train E4B on Kaggle (recommended — free GPU T4 ×2)

E4B QLoRA needs ~10 GB VRAM, which a Kaggle **T4** (16 GB, compute capability 7.5) fits but an
8 GB laptop card does not. Use the ready-to-run notebook:

**[`kaggle_gemma4_e4b_finetune.ipynb`](kaggle_gemma4_e4b_finetune.ipynb)**

It installs the stack, **guards the GPU** (hard-fails on a P100 — cc 6.0 < 7.0, where Unsloth
silently drops to the maskless fallback), reads `HF_TOKEN` from **Kaggle Secrets** (never a cell),
runs the validator as a **hard gate**, trains E4B with the best-accuracy settings
(r=32 / α=32, lr 2e-4, 3 epochs, seq-len 1024), exports merged-fp16 + GGUF, and uploads the
artifacts to a private HF repo. Set the accelerator to **`GPU T4 x2`** and attach your dataset
(`train.jsonl` + `val.jsonl`) as an input.

> **Memory Note:** If you see a `RuntimeError: expected mat1 and mat2 to have the same dtype, but got: float != c10::Half` crash on step 0, it is because Unsloth forces `float32` on non-native-bf16 GPUs (like the T4) but occasionally misses a `float16` linear projection. Our `sahayak_finetune.py` script automatically patches this via an internal `_align_model_dtype` pass (which upcasts stray `float16` tensors to match the `float32` embeddings), permanently fixing the crash so it doesn't bite the team again.
