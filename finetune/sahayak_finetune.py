#!/usr/bin/env python3
"""
Sahayak emergency-assistant fine-tuner (Unsloth QLoRA for Gemma 4 E2B/E4B).

Implements the training half of docs/SAHAYAK_DATASET_SPEC.md: it consumes the messages-format
JSONL the spec produces, applies the Gemma chat template, trains only on assistant turns, and
exports LoRA adapters (+ optional merged / GGUF) for the on-device runtime.

Cross-platform by design (Windows / Linux / Surface, x86-64 or ARM):
  * Detects the accelerator at runtime and picks a backend automatically:
      - NVIDIA CUDA present  -> Unsloth QLoRA  (the fast, spec-recommended path)
      - otherwise            -> transformers + PEFT LoRA fallback (CPU/MPS; slow but it runs,
                                so you can smoke-test the whole pipeline on a laptop/Surface)
  * No shell-isms, no hardcoded slashes: all paths go through pathlib, so the same command
    line works in PowerShell, bash, or zsh.

Licensing (CLAUDE.md #1): Unsloth is Apache-2.0, transformers/peft/trl/datasets are Apache-2.0.
The Gemma *weights* ship under Google's Gemma Terms of Use (not OSI-approved) and are gated on
Hugging Face — a human must accept those terms and provide an HF token (env HF_TOKEN) before the
base model will download. The generated dataset and this script are Apache-2.0.

Usage (typical, on a CUDA box):
    python sahayak_finetune.py \
        --train data/train/all.jsonl \
        --eval  data/eval_holdout.jsonl \
        --model unsloth/gemma-3n-E4B-it \
        --out   out/sahayak-e4b \
        --export-gguf q4_k_m

Run `python sahayak_finetune.py --help` for the full set of knobs.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

# The one fixed system prompt from SAHAYAK_DATASET_SPEC.md §1.1. Training must match on-device
# inference byte-for-byte, so it lives here as the single source of truth for validation too.
SYSTEM_PROMPT = (
    "You are Sahayak, an offline emergency-response assistant running on a local device in a "
    "disaster zone. You help with first aid, message relay, resource allocation, and navigation. "
    "Be brief, calm, and practical. You are not a doctor; for medical guidance give first-aid "
    "steps only and tell the user to reach professional care when possible. Never transmit "
    "information that could endanger people if intercepted."
)


# ── Environment detection ─────────────────────────────────────────────────────

def detect_device() -> dict:
    """Figure out what we're running on, so the backend choice is automatic, not guesswork."""
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
        import torch  # noqa: WPS433 (local import: torch may be heavy / absent)

        if torch.cuda.is_available():
            info["cuda"] = True
            info["device"] = "cuda"
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["bf16"] = torch.cuda.is_bf16_supported()
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["mps"] = True
            info["device"] = "mps"
    except Exception as exc:  # torch not installed yet, etc.
        info["torch_error"] = repr(exc)
    return info


def choose_backend(requested: str, env: dict) -> str:
    """Resolve --backend auto into a concrete choice given the detected hardware."""
    if requested != "auto":
        return requested
    if env["cuda"]:
        try:
            import unsloth  # noqa: F401
            return "unsloth"
        except Exception:
            print("[warn] CUDA present but Unsloth not importable — falling back to transformers.")
            return "transformers"
    return "transformers"


# ── Dataset loading ───────────────────────────────────────────────────────────

def load_messages_dataset(train_path: Path, eval_path: Path | None):
    """Load the spec's messages-format JSONL directly (no ShareGPT/Alpaca conversion)."""
    from datasets import load_dataset

    data_files = {"train": str(train_path)}
    if eval_path and eval_path.exists():
        data_files["eval"] = str(eval_path)
    ds = load_dataset("json", data_files=data_files)
    return ds


def build_text_mapper(tokenizer):
    """Render each record's `messages` into a single training string via the chat template."""

    def _map(batch):
        texts = []
        for messages in batch["messages"]:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            texts.append(text)
        return {"text": texts}

    return _map


# ── Unsloth (CUDA) backend ──────────────────────────────────────────────────────

def run_unsloth(args, env):
    from unsloth import FastModel
    from unsloth.chat_templates import train_on_responses_only

    max_seq = args.max_seq_len
    template = resolve_template(args.model, args.chat_template)
    print(f"[unsloth] model={args.model} chat_template={template}")
    print(f"[unsloth] loading {args.model} (4bit={not args.no_4bit}) …")
    model, tokenizer = FastModel.from_pretrained(
        model_name=args.model,
        max_seq_length=max_seq,
        load_in_4bit=not args.no_4bit,   # QLoRA by default (spec: prefer E4B QLoRA)
        full_finetuning=False,
        token=os.environ.get("HF_TOKEN"),
    )

    # Text-only fine-tune — keep vision layers frozen (spec §3 notes).
    model = FastModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.0,
        bias="none",
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        random_state=args.seed,
    )

    tokenizer = apply_chat_template(tokenizer, template)

    ds = load_messages_dataset(Path(args.train), Path(args.eval) if args.eval else None)
    mapper = build_text_mapper(tokenizer)
    train_ds = ds["train"].map(mapper, batched=True, remove_columns=ds["train"].column_names)
    eval_ds = None
    if "eval" in ds:
        eval_ds = ds["eval"].map(mapper, batched=True, remove_columns=ds["eval"].column_names)

    # NOTE: this is trainer-side validation loss only. The spec's eval_holdout.jsonl is for
    # demo/judge time — running it here is fine; *training* on it never is.
    sft_config = make_sft_config(
        dataset_text_field="text",
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_ratio=0.05,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=args.seed,
        output_dir=str(Path(args.out) / "checkpoints"),
        report_to="none",
        max_seq_length=max_seq,
        bf16=env["bf16"],
        fp16=not env["bf16"],
        eval_strategy="epoch" if eval_ds is not None else "no",
    )

    trainer = make_sft_trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=sft_config,
    )

    # Loss on assistant turns only (spec §3): markers derived from the applied template so
    # masking can't silently break on a Gemma-version delimiter change.
    instr, resp = derive_turn_markers(tokenizer)
    trainer = train_on_responses_only(trainer, instruction_part=instr, response_part=resp)

    print("[unsloth] training …")
    trainer.train()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"[unsloth] saving LoRA adapters -> {out}")
    model.save_pretrained(str(out))
    tokenizer.save_pretrained(str(out))

    if args.export_merged:
        merged = out / "merged-16bit"
        print(f"[unsloth] saving merged fp16 -> {merged}")
        model.save_pretrained_merged(str(merged), tokenizer, save_method="merged_16bit")

    if args.export_gguf:
        print(f"[unsloth] exporting GGUF ({args.export_gguf}) -> {out / 'gguf'}")
        model.save_pretrained_gguf(
            str(out / "gguf"), tokenizer, quantization_method=args.export_gguf
        )
    print("[unsloth] done.")


# ── transformers + PEFT fallback (CPU / MPS / no-CUDA) ────────────────────────────

def run_transformers(args, env):
    print("=" * 78)
    print("[fallback] No CUDA/Unsloth — transformers + PEFT LoRA (SMOKE TEST ONLY).")
    print("[fallback] WARNING: this path trains with FULL-SEQUENCE loss — NO response masking.")
    print("[fallback] It teaches the model the user turns + system prompt too, so DO NOT ship a")
    print("[fallback] model trained here. Use it only to prove the data/pipeline runs, then do")
    print("[fallback] the real run on a CUDA GPU (Unsloth path). E4B in fp32 needs ~30GB+ RAM —")
    print("[fallback] on a laptop/Surface point --model at a tiny model (e.g. sshleifer/tiny-gpt2)")
    print("[fallback] just to exercise the loop.")
    print("=" * 78)
    import torch
    from datasets import load_dataset  # noqa: F401  (kept for parity / clarity)
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model

    tokenizer = AutoTokenizer.from_pretrained(args.model, token=os.environ.get("HF_TOKEN"))
    tokenizer = apply_chat_template(tokenizer, resolve_template(args.model, args.chat_template))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float32
    if env["device"] == "mps":
        dtype = torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=dtype, token=os.environ.get("HF_TOKEN")
    )
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()

    ds = load_messages_dataset(Path(args.train), Path(args.eval) if args.eval else None)
    mapper = build_text_mapper(tokenizer)
    train_ds = ds["train"].map(mapper, batched=True, remove_columns=ds["train"].column_names)

    def tok(batch):
        return tokenizer(
            batch["text"], truncation=True, max_length=args.max_seq_len
        )

    train_tok = train_ds.map(tok, batched=True, remove_columns=["text"])
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    out = Path(args.out)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(out / "checkpoints"),
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            logging_steps=10,
            save_strategy="epoch",
            report_to="none",
            seed=args.seed,
            use_cpu=(env["device"] == "cpu"),
        ),
        train_dataset=train_tok,
        data_collator=collator,
    )
    print("[fallback] training …")
    trainer.train()
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out))
    tokenizer.save_pretrained(str(out))
    print(f"[fallback] saved LoRA adapters -> {out}")
    if args.export_gguf:
        print(
            "[fallback] GGUF export is only wired up on the Unsloth path. Convert the merged model "
            "with llama.cpp's convert_hf_to_gguf.py, or re-run this on a CUDA box with Unsloth."
        )


# ── Shared helpers: model / template / marker matched set ─────────────────────────
#
# Model, chat template, and turn markers must agree or the run silently breaks: a mismatched
# template renders wrong tokens, and wrong turn markers make train_on_responses_only mask
# nothing (loss lands on the user turns + the system prompt repeated ~1,800x — the exact
# scaffold-memorization the spec §1.3 warns against). So: the template is looked up by model
# family, an unknown one is a HARD ERROR, and the turn markers are *derived from the template
# that's actually applied* rather than hardcoded — correct across Gemma 3 / 3n / 4 without us
# guessing a version-specific string.

MODEL_PROFILES = {
    # substring in the model id  ->  chat_template name for Unsloth's get_chat_template
    "gemma-4": "gemma-4",
    "gemma-3n": "gemma-3",
    "gemma-3": "gemma-3",
    "gemma-2": "gemma-2",
}


def resolve_template(model_id: str, requested: str) -> str:
    """Pick the chat template: honour --chat-template unless 'auto', else infer from model id."""
    if requested and requested != "auto":
        return requested
    low = model_id.lower()
    for family, template in MODEL_PROFILES.items():
        if family in low:
            return template
    raise SystemExit(
        f"[error] can't infer a chat template for '{model_id}'. Pass --chat-template explicitly "
        f"(known families: {', '.join(sorted(MODEL_PROFILES))})."
    )


def apply_chat_template(tokenizer, name: str):
    """Apply Unsloth's chat template. Hard error if the name is unknown — never a silent
       fallback. With plain transformers (no Unsloth) the tokenizer's own template is used."""
    try:
        from unsloth.chat_templates import get_chat_template
    except Exception:
        # transformers path: the model's tokenizer already carries its correct template.
        return tokenizer
    try:
        return get_chat_template(tokenizer, chat_template=name)
    except Exception as exc:
        raise SystemExit(
            f"[error] chat template '{name}' is not recognized by the installed Unsloth "
            f"({exc}). Upgrade Unsloth or pass a supported --chat-template."
        )


# Zero-width-surrounded sentinels that can't collide with real template markup.
_P_U1 = "⁣SAHAYAK_U1⁣"
_P_A1 = "⁣SAHAYAK_A1⁣"
_P_U2 = "⁣SAHAYAK_U2⁣"


def derive_turn_markers(tokenizer):
    """Extract the exact (instruction_part, response_part) delimiters from the *applied*
       template by rendering a probe conversation and reading the literal text the template
       inserts between turns. No system turn in the probe — Gemma folds system into the first
       user turn, which would pollute the marker."""
    probe = [
        {"role": "user", "content": _P_U1},
        {"role": "assistant", "content": _P_A1},
        {"role": "user", "content": _P_U2},
    ]
    text = tokenizer.apply_chat_template(probe, tokenize=False, add_generation_prompt=False)
    i_u1, i_a1, i_u2 = text.find(_P_U1), text.find(_P_A1), text.find(_P_U2)
    if -1 in (i_u1, i_a1, i_u2) or not (i_u1 < i_a1 < i_u2):
        raise SystemExit(
            "[error] could not derive turn markers from the chat template — response masking "
            "would be wrong. Check the template/model pairing."
        )
    response_part = text[i_u1 + len(_P_U1):i_a1]      # delimiter that begins the assistant turn
    instruction_part = text[i_a1 + len(_P_A1):i_u2]   # delimiter that begins a user turn
    if not response_part.strip() or not instruction_part.strip():
        raise SystemExit("[error] derived empty turn markers — aborting to avoid a broken run.")
    print(f"[markers] instruction_part={instruction_part!r} response_part={response_part!r}")
    return instruction_part, response_part


def make_sft_config(**kwargs):
    """Build SFTConfig tolerant of TRL's rename max_seq_length -> max_length."""
    from trl import SFTConfig
    try:
        return SFTConfig(**kwargs)
    except TypeError:
        if "max_seq_length" in kwargs:
            kwargs["max_length"] = kwargs.pop("max_seq_length")
            return SFTConfig(**kwargs)
        raise


def make_sft_trainer(**kwargs):
    """Build SFTTrainer tolerant of TRL's rename tokenizer -> processing_class."""
    from trl import SFTTrainer
    try:
        return SFTTrainer(**kwargs)
    except TypeError:
        if "tokenizer" in kwargs:
            kwargs["processing_class"] = kwargs.pop("tokenizer")
            return SFTTrainer(**kwargs)
        raise


def preflight(args) -> None:
    """Fail early and clearly on the mistakes that waste a long run."""
    train = Path(args.train)
    if not train.exists():
        sys.exit(f"[error] training file not found: {train}")
    if args.eval and not Path(args.eval).exists():
        print(f"[warn] eval file not found, training without it: {args.eval}")
    if "HF_TOKEN" not in os.environ:
        print(
            "[warn] HF_TOKEN not set. Gemma weights are gated — export a Hugging Face token "
            "(that has accepted the Gemma terms) as HF_TOKEN or the download will 401."
        )


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Fine-tune Gemma 4 (E2B/E4B) for the Sahayak offline emergency assistant.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--train", required=True, help="Path to training .jsonl (messages format).")
    p.add_argument("--eval", default=None, help="Optional held-out eval .jsonl.")
    p.add_argument("--model", default="unsloth/gemma-4-E4B-it",
                   help="Base model id (Gemma 4 E4B). For E2B pass the E2B id; any Gemma id works.")
    p.add_argument("--out", default="out/sahayak", help="Output dir for adapters/exports.")
    p.add_argument("--backend", choices=["auto", "unsloth", "transformers"], default="auto",
                   help="Training backend. 'auto' = Unsloth on CUDA, transformers otherwise.")
    p.add_argument("--chat-template", default="auto",
                   help="Chat template name. 'auto' infers it from the model family (see "
                        "MODEL_PROFILES). An unrecognized name is a hard error, never a silent "
                        "fallback — a wrong template silently ruins the run.")
    p.add_argument("--epochs", type=float, default=2.0)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--max-seq-len", type=int, default=2048)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=16)
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--no-4bit", action="store_true", help="Disable 4-bit (QLoRA) loading.")
    p.add_argument("--export-merged", action="store_true", help="Also save merged fp16 weights.")
    p.add_argument("--export-gguf", default=None,
                   help="GGUF quant to export (e.g. q4_k_m, q8_0). Unsloth backend only.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    env = detect_device()
    print("── Sahayak fine-tune ─────────────────────────────────────────")
    print(f" host      : {env['os']} / {env['machine']} / py{env['python']}")
    print(f" device    : {env['device']}"
          + (f" ({env.get('gpu_name')})" if env.get("gpu_name") else ""))
    preflight(args)

    backend = choose_backend(args.backend, env)
    print(f" backend   : {backend}")
    print("──────────────────────────────────────────────────────────────")

    if backend == "unsloth":
        run_unsloth(args, env)
    else:
        run_transformers(args, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
