# Sahayak fine-tuning

Fine-tune **Gemma 4 (E2B/E4B)** into the offline emergency-response assistant, per
[`SAHAYAK_DATASET_SPEC.md`](../../SAHAYAK_DATASET_SPEC.md). Two files:

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
