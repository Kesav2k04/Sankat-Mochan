#!/usr/bin/env python3
"""
Sahayak emergency-assistant fine-tuner — Gemma 4 E2B QLoRA, pure transformers + PEFT.

No Unsloth, no TRL: just `transformers` + `peft` + `datasets` (+ `bitsandbytes` on CUDA),
all Apache-2.0 (CLAUDE.md #1). Gemma 4 is native in transformers >= 5.6, so nothing here
needs remote code or third-party kernels.

What it does (the training half of docs/SAHAYAK_DATASET_SPEC.md):
  * consumes the spec's messages-format JSONL,
  * renders each record with the model's OWN chat template (single source of truth — no
    hand-maintained template table to drift out of sync),
  * trains with loss on ASSISTANT turns only (spec §3), including the 2-assistant-turn
    multi-turn records, via character-offset label masking,
  * exports LoRA adapters (+ optional merged bf16/fp16 weights) for the on-device runtime.

Precision policy (learned the hard way on Kaggle T4s):
  * Ampere+ (compute capability >= 8.0): bf16 everywhere — the fast path.
  * Older CUDA (T4, cc 7.5): Gemma 4 has fp16-unsafe ops, so compute runs in float32 with
    4-bit weights. Slower, but it converges instead of NaN-ing or dtype-crashing.
  * CPU / Apple MPS: smoke-test fallback only — proves the pipeline, never ships a model.

Usage (typical, on a CUDA box):
    python sahayak_finetune.py \
        --train data/train.jsonl \
        --eval  data/val.jsonl \
        --model google/gemma-4-E2B-it \
        --out   out/sahayak-e2b

    python sahayak_finetune.py --train data/train.jsonl --validate-only   # data check, no GPU

Gemma weights are gated: export HF_TOKEN (an HF token whose account accepted the Gemma
license) before running. Run `python sahayak_finetune.py --help` for all knobs.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

# Must be set before torch initializes CUDA. float32 compute on a T4 runs close to the 16 GB
# ceiling; expandable segments stops fragmentation from turning "almost fits" into an OOM.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")  # torch >= 2.8 name

# The one fixed system prompt from SAHAYAK_DATASET_SPEC.md §1.1. Training must match on-device
# inference byte-for-byte; validate_dataset.py imports this as the canonical copy, so module
# import must stay stdlib-only (all heavy imports live inside functions).
SYSTEM_PROMPT = (
    "You are Sahayak, an offline emergency-response assistant running on a local device in a "
    "disaster zone. You help with first aid, message relay, resource allocation, and navigation. "
    "Be brief, calm, and practical. You are not a doctor; for medical guidance give first-aid "
    "steps only and tell the user to reach professional care when possible. Never transmit "
    "information that could endanger people if intercepted."
)

VALID_ROLES = {"system", "user", "assistant"}
MAX_RECORD_BYTES = 100_000  # CLAUDE.md #8: bound untrusted input size before processing.
LORA_TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


# ── Environment detection ─────────────────────────────────────────────────────

def detect_device() -> dict:
    """Figure out what we're running on so precision/backend choices are automatic."""
    info = {
        "os": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cuda": False,
        "mps": False,
        "device": "cpu",
        "bf16": False,
    }
    try:
        import torch

        if torch.cuda.is_available():
            info["cuda"] = True
            info["device"] = "cuda"
            info["gpu_name"] = torch.cuda.get_device_name(0)
            # Native bf16 needs compute capability >= 8.0 (Ampere+). Do NOT trust
            # torch.cuda.is_bf16_supported(): a T4 (cc 7.5) answers True via slow emulation.
            info["bf16"] = torch.cuda.get_device_capability(0)[0] >= 8
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["mps"] = True
            info["device"] = "mps"
    except Exception as exc:  # torch absent — fine for --validate-only
        info["torch_error"] = repr(exc)
    return info


# ── Dataset validation (CLAUDE.md #8: dataset lines are untrusted input) ─────────

def validate_jsonl(path: Path, label: str) -> int:
    """Structural validation with stdlib only, so --validate-only runs anywhere.

    Checks per record: size bound, messages list of {role, content} with known roles and
    non-empty string content, an optional single leading system turn, strict user/assistant
    alternation, and an assistant turn last (otherwise there is nothing to train on).
    Hard-errors with the line number — a bad record must never silently skew a long run.
    """
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            where = f"{label} {path.name}:{lineno}"
            if len(line.encode("utf-8", errors="replace")) > MAX_RECORD_BYTES:
                sys.exit(f"[error] {where}: record exceeds {MAX_RECORD_BYTES} bytes")
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                sys.exit(f"[error] {where}: invalid JSON ({exc})")
            msgs = rec.get("messages") if isinstance(rec, dict) else None
            if not isinstance(msgs, list) or not msgs:
                sys.exit(f"[error] {where}: missing/empty 'messages' list")
            for i, m in enumerate(msgs):
                if not isinstance(m, dict) or not isinstance(m.get("content"), str) \
                        or not m["content"].strip() or m.get("role") not in VALID_ROLES:
                    sys.exit(f"[error] {where}: messages[{i}] must be "
                             f"{{role: system|user|assistant, content: non-empty str}}")
            body = msgs[1:] if msgs[0]["role"] == "system" else msgs
            if any(m["role"] == "system" for m in body):
                sys.exit(f"[error] {where}: system role only allowed as the first message")
            expected = "user"
            for i, m in enumerate(body):
                if m["role"] != expected:
                    sys.exit(f"[error] {where}: expected '{expected}' at turn {i}, "
                             f"got '{m['role']}' (turns must alternate user/assistant)")
                expected = "assistant" if expected == "user" else "user"
            if not body or body[-1]["role"] != "assistant":
                sys.exit(f"[error] {where}: last message must be an assistant turn")
            n += 1
    if n == 0:
        sys.exit(f"[error] {label} {path}: no records")
    print(f"[data] {label}: {n} records OK ({path})")
    return n


# ── Rendering + assistant-only label masking ─────────────────────────────────────

def render_and_mask(messages: list, tokenizer, max_seq_len: int) -> dict | None:
    """Tokenize one conversation with labels only on assistant turns (incl. end-of-turn).

    Character-offset approach, robust to any turn delimiter the template uses:
      1. Render the FULL conversation once.
      2. For each assistant turn i, render messages[:i] with add_generation_prompt=True
         (ends exactly where the assistant's content begins) and messages[:i+1] without
         (ends just past the assistant's end-of-turn). Both must be string prefixes of the
         full render — verified, not assumed — giving exact [start, end) character spans.
      3. Tokenize the full render once with offset mapping; a token gets a label iff its
         character span overlaps an assistant span.
    This trains the end-of-turn token too (the model must learn to STOP), and handles the
    dataset's multi-turn records without special-casing.

    Returns None when truncation at max_seq_len leaves no supervised tokens (caller drops
    and counts those — silently training on a label-less example wastes a step).
    """
    full = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)

    spans = []
    for i, msg in enumerate(messages):
        if msg["role"] != "assistant":
            continue
        prefix = tokenizer.apply_chat_template(
            messages[:i], tokenize=False, add_generation_prompt=True
        )
        through = tokenizer.apply_chat_template(
            messages[: i + 1], tokenize=False, add_generation_prompt=False
        )
        if not (full.startswith(prefix) and full.startswith(through)):
            raise SystemExit(
                "[error] chat template is not prefix-stable — assistant spans can't be located "
                "and response masking would be wrong. Check the model/template pairing."
            )
        spans.append((len(prefix), len(through)))
    if not spans:
        raise SystemExit("[error] conversation has no assistant turn (validator should catch this)")

    # The rendered text already contains the BOS token text; add_special_tokens=False avoids
    # a double-BOS, which Gemma is sensitive to.
    enc = tokenizer(
        full,
        add_special_tokens=False,
        truncation=True,
        max_length=max_seq_len,
        return_offsets_mapping=True,
    )
    offsets = enc.pop("offset_mapping")
    labels = [
        tok_id if any(s < c_end and c_start < e for (s, e) in spans) else -100
        for tok_id, (c_start, c_end) in zip(enc["input_ids"], offsets)
    ]
    if all(l == -100 for l in labels):
        return None
    return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "labels": labels}


def build_dataset(path: Path, tokenizer, max_seq_len: int, label: str):
    """Load a messages-format JSONL and map it to masked token features."""
    from datasets import load_dataset

    ds = load_dataset("json", data_files=str(path), split="train")

    def _map(rec):
        out = render_and_mask(rec["messages"], tokenizer, max_seq_len)
        if out is None:
            # Emit an empty (filtered below) row rather than crash mid-map.
            return {"input_ids": [], "attention_mask": [], "labels": []}
        return out

    ds = ds.map(_map, remove_columns=ds.column_names, desc=f"tokenize {label}")
    before = len(ds)
    ds = ds.filter(lambda r: len(r["input_ids"]) > 0)
    if len(ds) != before:
        print(f"[data] {label}: dropped {before - len(ds)} example(s) fully truncated "
              f"at --max-seq-len {max_seq_len}")
    print(f"[data] {label}: {len(ds)} tokenized examples")
    return ds


class PadCollator:
    """Right-pad input_ids/attention_mask, pad labels with -100 (ignored by the loss)."""

    def __init__(self, pad_token_id: int):
        self.pad_token_id = pad_token_id

    def __call__(self, features):
        import torch

        width = max(len(f["input_ids"]) for f in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for f in features:
            pad = width - len(f["input_ids"])
            batch["input_ids"].append(list(f["input_ids"]) + [self.pad_token_id] * pad)
            batch["attention_mask"].append(list(f["attention_mask"]) + [0] * pad)
            batch["labels"].append(list(f["labels"]) + [-100] * pad)
        return {k: torch.tensor(v, dtype=torch.long) for k, v in batch.items()}


# ── Model loading ─────────────────────────────────────────────────────────────────

def load_tokenizer(model_id: str):
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_id, token=os.environ.get("HF_TOKEN"))
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    if not getattr(tok, "chat_template", None):
        raise SystemExit(
            f"[error] tokenizer for '{model_id}' ships no chat template — this trainer relies "
            "on the model's own template. Use an instruction-tuned (-it) checkpoint."
        )
    if not getattr(tok, "is_fast", False):
        raise SystemExit(
            "[error] a fast tokenizer is required (offset mapping drives label masking); "
            f"'{model_id}' returned a slow one."
        )
    return tok


def _from_pretrained_compat(cls, model_id: str, dtype, **kwargs):
    """transformers 5.x takes `dtype=`; keep a `torch_dtype=` retry so an older env in the
    supported window still loads instead of TypeError-ing an hour into a Kaggle session."""
    try:
        return cls.from_pretrained(model_id, dtype=dtype, **kwargs)
    except TypeError:
        return cls.from_pretrained(model_id, torch_dtype=dtype, **kwargs)


def load_model(args, env):
    import torch
    from transformers import AutoModelForCausalLM

    # Compute dtype: bf16 on Ampere+; float32 elsewhere. Never fp16 — Gemma 4 has
    # fp16-unsafe ops (the source of the old "float != c10::Half" step-0 crash on T4s).
    compute_dtype = torch.bfloat16 if env["bf16"] else torch.float32

    kwargs = dict(
        token=os.environ.get("HF_TOKEN"),
        # Gemma's own docs recommend eager attention for training-quality numerics.
        attn_implementation="eager",
    )
    quantized = env["cuda"] and not args.no_4bit
    if quantized:
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        kwargs["device_map"] = {"": 0}
    elif env["cuda"]:
        kwargs["device_map"] = {"": 0}

    print(f"[model] loading {args.model} (4bit={quantized}, compute dtype={compute_dtype}) …")
    model = _from_pretrained_compat(AutoModelForCausalLM, args.model, compute_dtype, **kwargs)
    if env["mps"]:
        model = model.to("mps")
    model.config.use_cache = False  # incompatible with gradient checkpointing
    return model, quantized


def attach_lora(model, args, quantized: bool):
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    if quantized:
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
        )
    else:
        model.enable_input_require_grads()

    # Text-only fine-tune (spec §3): if the checkpoint is multimodal, scope LoRA to the
    # language tower by regex so vision/audio layers stay frozen; else target by name.
    module_names = [n for n, _ in model.named_modules()]
    if any(".language_model." in n for n in module_names):
        targets = r".*language_model.*\.({})$".format("|".join(LORA_TARGETS))
        print("[lora] multimodal checkpoint detected — targeting language tower only")
    else:
        targets = list(LORA_TARGETS)

    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=targets,
        ),
    )
    model.print_trainable_parameters()
    return model


# ── Training ─────────────────────────────────────────────────────────────────────

def run_training(args, env) -> None:
    from transformers import Trainer, TrainingArguments

    tokenizer = load_tokenizer(args.model)
    train_ds = build_dataset(Path(args.train), tokenizer, args.max_seq_len, "train")
    eval_ds = None
    if args.eval and Path(args.eval).exists():
        eval_ds = build_dataset(Path(args.eval), tokenizer, args.max_seq_len, "eval")

    model, quantized = load_model(args, env)
    model = attach_lora(model, args, quantized)

    out = Path(args.out)
    training_args = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        per_device_train_batch_size=args.batch_size,
        # Eval batch stays at 1 regardless of train batch: eval runs without gradient
        # checkpointing, and the fp32 logits over Gemma's ~262k vocab (~1 GB per sequence at
        # seq-len 1024) make the Trainer's default of 8 an instant OOM on a 16 GB T4.
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="linear",
        warmup_ratio=0.05,
        weight_decay=0.01,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_ds is not None else "no",
        # bf16 autocast only on native-bf16 GPUs; everywhere else the model is already
        # float32, so both flags stay off (fp16 autocast is what used to crash Gemma 4).
        bf16=env["bf16"],
        fp16=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit" if quantized else "adamw_torch",
        seed=args.seed,
        report_to="none",
        remove_unused_columns=False,
        use_cpu=(env["device"] == "cpu"),
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=PadCollator(tokenizer.pad_token_id),
        processing_class=tokenizer,
    )

    if env["device"] == "cpu" or env["mps"]:
        print("=" * 78)
        print("[warn] no CUDA — this run is a pipeline SMOKE TEST (slow, unquantized).")
        print("[warn] do the real run on a CUDA GPU; do not ship weights trained here.")
        print("=" * 78)

    print("[train] starting …")
    trainer.train()

    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out))
    tokenizer.save_pretrained(str(out))
    print(f"[train] LoRA adapters saved -> {out}")

    if args.export_merged:
        export_merged(args, env, adapter_dir=out)


def export_merged(args, env, adapter_dir: Path) -> None:
    """Merge adapters into full weights. Reloads the base UNQUANTIZED on CPU — merging into
    4-bit weights is lossy/unsupported, and CPU sidesteps GPU OOM during the merge."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    dtype = torch.bfloat16 if env["bf16"] else torch.float16  # storage dtype only, no compute
    merged_dir = adapter_dir / "merged"
    print(f"[merge] reloading base on CPU in {dtype} and merging adapters …")
    base = _from_pretrained_compat(
        AutoModelForCausalLM, args.model, dtype, token=os.environ.get("HF_TOKEN")
    )
    merged = PeftModel.from_pretrained(base, str(adapter_dir)).merge_and_unload()
    merged.save_pretrained(str(merged_dir))
    load_tokenizer(args.model).save_pretrained(str(merged_dir))
    print(f"[merge] merged weights saved -> {merged_dir}")
    print("[merge] for on-device GGUF, convert with llama.cpp's convert_hf_to_gguf.py "
          "(MIT-licensed) pointed at the merged dir.")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def preflight(args) -> None:
    """Fail early and clearly on the mistakes that waste a long run."""
    train = Path(args.train)
    if not train.exists():
        sys.exit(f"[error] training file not found: {train}")
    validate_jsonl(train, "train")
    if args.eval:
        p = Path(args.eval)
        if p.exists():
            validate_jsonl(p, "eval")
        else:
            print(f"[warn] eval file not found, training without it: {args.eval}")
    if "HF_TOKEN" not in os.environ:
        print("[warn] HF_TOKEN not set. Gemma weights are gated — export a Hugging Face "
              "token (whose account accepted the Gemma terms) or the download will 401.")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Fine-tune Gemma 4 E2B for the Sahayak offline emergency assistant "
                    "(pure transformers + PEFT, no Unsloth).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--train", required=True, help="Training .jsonl (messages format).")
    p.add_argument("--eval", default=None, help="Optional held-out eval .jsonl.")
    p.add_argument("--model", default="google/gemma-4-E2B-it",
                   help="Base model id. Any instruction-tuned Gemma id works.")
    p.add_argument("--out", default="out/sahayak-e2b", help="Output dir for adapters/exports.")
    p.add_argument("--epochs", type=float, default=2.0)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--max-seq-len", type=int, default=2048)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=16)
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--no-4bit", action="store_true",
                   help="Disable 4-bit QLoRA loading (CUDA default is 4-bit).")
    p.add_argument("--export-merged", action="store_true",
                   help="After training, also save merged full weights (CPU merge).")
    p.add_argument("--validate-only", action="store_true",
                   help="Validate the dataset files and exit — stdlib only, runs anywhere.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.validate_only:
        preflight(args)
        print("[ok] validation passed")
        return 0

    env = detect_device()
    print("── Sahayak fine-tune (transformers + PEFT) ───────────────────")
    print(f" host      : {env['os']} / {env['machine']} / py{env['python']}")
    print(f" device    : {env['device']}"
          + (f" ({env.get('gpu_name')})" if env.get("gpu_name") else ""))
    print(f" precision : {'bf16' if env['bf16'] else 'float32'}")
    print("──────────────────────────────────────────────────────────────")
    if env.get("torch_error"):
        sys.exit(f"[error] torch not importable: {env['torch_error']} — "
                 "install requirements.txt first (or run with --validate-only).")
    preflight(args)
    run_training(args, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
