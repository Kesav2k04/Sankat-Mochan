# Sahayak — Kaggle Fine-Tune Guide (Gemma 4 E4B, best-accuracy settings)

End-to-end: dataset → QLoRA fine-tune on Kaggle → merged checkpoint + GGUF → artifacts
downloaded locally → handoff to Qualcomm AI Hub for NPU. Companion to
`docs/SAHAYAK_DATASET_SPEC.md` (dataset) and `finetune/` (code).

---

## 0. Why these choices

- **Kaggle accelerator: "GPU T4 x2", never P100.** Unsloth requires CUDA compute capability
  ≥ 7.0; the T4 is 7.5, the P100 is 6.0 (Pascal, no tensor cores). On P100 the trainer drops to
  the slow transformers fallback — which trains WITHOUT response masking and must not produce a
  shipped model. The script is single-GPU; the second T4 idles (harmless).
- **E4B QLoRA, not E2B:** per Unsloth's Gemma 4 guide, E4B QLoRA beats E2B LoRA at similar
  memory — quantization costs less accuracy than the smaller model does. T4's 16GB fits it.
- **Accuracy comes from the dataset first.** Every hyperparameter below is worth less than a
  clean, deduplicated, critiqued dataset (spec §8). Don't tune knobs to compensate for data.

## 1. Kaggle setup (5 min)

1. New Notebook → **Settings**: Accelerator **GPU T4 x2** · Internet **On** ·
   Persistence **Files only**.
2. **Add-ons → Secrets**: add `HF_TOKEN` = a Hugging Face token whose account has accepted the
   Gemma license (huggingface.co/google/gemma-4-E4B-it → agree). Never paste the token in a cell.
3. Session quota: this run uses ~1–1.5h of your ~30 GPU-hrs/week — you can afford 3–4 full runs.

## 2. Notebook cells

```python
# ── Cell 1: code + deps ────────────────────────────────────────────────
!git clone https://github.com/SivaNithishKumar/sankat-mochan.git
%cd sankat-mochan/finetune
!pip install -q -r requirements.txt
# If pip warns about preinstalled-package conflicts: Runtime → Restart, rerun this cell.

# ── Cell 2: auth ───────────────────────────────────────────────────────
import os
from kaggle_secrets import UserSecretsClient
os.environ["HF_TOKEN"] = UserSecretsClient().get_secret("HF_TOKEN")

# ── Cell 3: dataset in + gate ──────────────────────────────────────────
# Upload the dataset (Kaggle: "Add Input" → your dataset, or upload files to data/).
# The validator is a HARD GATE — do not train on a file that doesn't pass.
!python validate_dataset.py data/train/all.jsonl
!python validate_dataset.py data/val/val.jsonl      # the 10% validation split (NOT the holdout)

# ── Cell 4: train (see §3 for why each value) ─────────────────────────
!python sahayak_finetune.py \
    --train data/train/all.jsonl \
    --eval  data/val/val.jsonl \
    --model unsloth/gemma-4-E4B-it \
    --out   /kaggle/working/sahayak-e4b \
    --epochs 3 --lr 2e-4 \
    --batch-size 2 --grad-accum 4 \
    --lora-r 32 --lora-alpha 32 \
    --max-seq-len 1024 \
    --export-merged --export-gguf q4_k_m

# ── Cell 5: ship artifacts to a private HF repo ───────────────────────
from huggingface_hub import HfApi
api = HfApi(token=os.environ["HF_TOKEN"])
repo = "SivaNithishKumar/sahayak-e4b"
api.create_repo(repo, private=True, exist_ok=True)
api.upload_folder(folder_path="/kaggle/working/sahayak-e4b", repo_id=repo)
print("done — pull locally with: huggingface-cli download", repo, "--local-dir ./sahayak-e4b")
```

**Watch during training:** the loss should fall and *keep falling* on eval. Gemma 4 E2B/E4B
starting losses of 13–15 are normal (per Unsloth) — judge the *trend*, not the absolute number.

## 3. Hyperparameters — what and why

| Param | Value | Why |
|---|---|---|
| `--lora-r` / `--lora-alpha` | **32 / 32** | Unsloth's Gemma 4 guide uses r=32 ("larger = higher accuracy"); alpha=r is the standard 1:1. With ~1,800 curated examples this is the accuracy setting. If eval loss climbs while train loss falls (overfit), drop to 16/16. |
| `--lr` | **2e-4** | QLoRA standard and Unsloth's Gemma 4 default. First knob if overfitting: halve to 1e-4. |
| `--epochs` | **3, pick best by eval** | Unsloth: 1–3 epochs; >3 = diminishing returns + overfit risk on instruction data. `eval_strategy="epoch"` logs eval loss each epoch — if epoch 3's eval loss is worse than epoch 2's, use the epoch-2 checkpoint from `checkpoints/`. |
| `--batch-size` × `--grad-accum` | **2 × 4 (effective 8)** | Fits T4 16GB with headroom for E4B QLoRA. Effective batch 8 ≈ 450 steps/epoch on 1,800 rows — enough steps to converge. OOM? → `1 × 8` (identical math, less memory). |
| `--max-seq-len` | **1024** | Spec-compliant records are ≤ ~600 output chars + short inputs; nothing legitimate approaches 1024 tokens. Halving from 2048 speeds training and wastes no accuracy. Keep 2048 only if two-turn examples run long. |
| warmup / schedule / optim | 0.05 / linear / adamw_8bit *(fixed in script)* | Unsloth defaults; nothing to gain changing them at this scale. |
| weight decay | 0.01 *(fixed)* | Mild regularizer, standard. |
| `--seed` | 3407 *(default)* | Fixed seed → runs comparable across hyperparameter changes. |
| Response masking | automatic | `train_on_responses_only` with template-derived markers — loss only on assistant turns. Confirm the `[markers]` log line prints Gemma 4 markers at startup. |
| 4-bit (QLoRA) | on (default) | Do NOT pass `--no-4bit` on a T4 — 16-bit LoRA on E4B needs ~17GB and will OOM. |

**Best-accuracy protocol (uses ~3 of your weekly GPU-hours):**
1. **Run A:** the Cell-4 command exactly (r=32, lr 2e-4, 3 epochs).
2. Compare per-epoch eval losses; select the best epoch's checkpoint.
3. Only if Run A overfits (eval loss rises after epoch 1): **Run B** with `--lora-r 16
   --lora-alpha 16 --lr 1e-4 --epochs 2`. Otherwise skip.
4. Judge the winner on the **held-out** `eval_holdout.jsonl` by hand — spot-check ~30 outputs:
   packet-format compliance (`SOS|` grammar, no invented fields), refusal calibration (§1.6 of
   the spec), length budget, language consistency. Eval loss picks the checkpoint; the holdout
   review decides if it ships.

**Inference settings (bake into the app — must match at demo):** Gemma 4's recommended
sampling is `temperature=1.0, top_p=0.95, top_k=64`. And the runtime must apply the *same
chat template* used in training, with the byte-identical system prompt from the spec.

## 4. Getting artifacts local

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli download SivaNithishKumar/sahayak-e4b --local-dir ./sahayak-e4b
```

You get three artifacts — keep all three:
- `gguf/*.gguf` (~4GB, q4_k_m) → straight into the app's model import (llama.cpp CPU/GPU path).
- `merged-16bit/` (~16GB safetensors) → the **AI Hub input** for NPU compilation.
- adapter files at the root (~100–200MB) → re-merge anywhere later without retraining.

## 5. NPU handoff (Qualcomm AI Hub) — NOT on Kaggle

AI Hub's LLM flow consumes the **HF checkpoint** (`merged-16bit/`), never GGUF. Per the
qai-hub-models LLM tutorial the flow is quantize (AIMET, local, **Linux/WSL + ~40GB-VRAM GPU**
for a 3–4B model) → export (compiles in AI Hub cloud → QNN context binaries / Genie bundle):

```bash
pip install qai-hub-models && qai-hub configure --api_token <AI_HUB_TOKEN>
python -m qai_hub_models.models.<gemma_4_e4b_recipe>.quantize \
    --checkpoint ./sahayak-e4b/merged-16bit -o ./quantized
python -m qai_hub_models.models.<gemma_4_e4b_recipe>.export \
    --checkpoint ./quantized --device "Snapdragon X Elite CRD"
```

- Kaggle can't run the quantize step (VRAM + AIMET-Linux constraints) — use the venue
  X Elite / Linux box, per the existing plan in `PLAN.md`.
- Venue gotchas (from `command-post/aihub_out/RESULTS.md` prep): add
  `--compile-options="--qairt_version=default" --profile-options="--qairt_version=default"`;
  device strings are `Snapdragon X Elite CRD` / `Snapdragon 8 Elite Gen 5 QRD`.
- **Verify tonight (5 min):** `pip install qai-hub-models` then
  `python -c "import qai_hub_models.models as m; print([x for x in dir(m) if 'gemma' in x.lower()])"`
  to confirm the exact Gemma 4 recipe name and that it accepts `--checkpoint` (the catalog
  lists Gemma-4-E4B-it; the bring-your-own-weights tutorial was written for Llama).

## 6. Demo-day sequencing

1. Dataset finishes → validator green → Kaggle Run A (~1.5h including exports).
2. GGUF into the app same day → **working demo on CPU/GPU regardless of NPU progress**.
3. Holdout spot-check (§3 step 4) → retrain only if a category is broken.
4. At venue: AI Hub quantize+export from `merged-16bit/` → NPU demo as the upgrade, GGUF as
   the safety net.
