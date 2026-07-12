#!/usr/bin/env python3
"""
Load-only test: can Gemma 4 E4B be loaded on this GPU in a given dtype without OOM,
and where does the memory go?

Motivation: on a T4 (compute capability 7.5) Unsloth gates bf16 on cc >= 8.0, so it refuses
bf16, then refuses fp16 for Gemma ("won't work"), and falls back to fp32 (4 bytes) — which OOMs
E4B at load. But `torch.cuda.is_bf16_supported()` is True on the T4 (emulated), and bf16 is only
2 bytes with a wide range that doesn't overflow. So forcing dtype=bfloat16 may halve the load
footprint and fit.

This script ONLY loads the model (no training), reports peak VRAM, and prints a per-dtype byte
histogram + the largest fp32 modules, so you can see the vision/conv fp32 mass directly.

Usage:
    python t4_load_test.py                       # E4B, dtype=bfloat16
    python t4_load_test.py --dtype float32       # reproduce the OOM baseline
    python t4_load_test.py --model unsloth/gemma-4-E2B-it-unsloth-bnb-4bit
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict


def parse_args():
    p = argparse.ArgumentParser(description="Gemma 4 load-only VRAM probe.")
    p.add_argument("--model", default="unsloth/gemma-4-E4B-it-unsloth-bnb-4bit")
    p.add_argument("--dtype", default="bfloat16",
                   choices=["bfloat16", "float16", "float32", "auto"])
    p.add_argument("--max-seq-len", type=int, default=1024)
    p.add_argument("--no-4bit", action="store_true", help="Disable 4-bit (QLoRA) loading.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    import torch
    from unsloth import FastModel

    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
        "auto": None,
    }
    dtype = dtype_map[args.dtype]

    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {torch.cuda.get_device_name(0)} | VRAM {total:.1f} GB")
    print(f"loading {args.model}")
    print(f"  dtype={args.dtype}  4bit={not args.no_4bit}  max_seq_len={args.max_seq_len}\n")

    torch.cuda.reset_peak_memory_stats()
    try:
        model, tok = FastModel.from_pretrained(
            model_name=args.model,
            max_seq_length=args.max_seq_len,
            dtype=dtype,                       # <-- the lever: force bf16 instead of fp32
            load_in_4bit=not args.no_4bit,
            full_finetuning=False,
            token=os.environ.get("HF_TOKEN"),
        )
    except torch.cuda.OutOfMemoryError as e:
        print("OOM AT LOAD with dtype=" + args.dtype)
        print(" ", str(e)[:200])
        print("\n-> try a lower-byte dtype (bfloat16) or the E2B model.")
        return 1

    peak = torch.cuda.max_memory_allocated() / 1e9
    print(f"\nLOADED OK. peak VRAM at load: {peak:.2f} GB / {total:.1f} GB\n")

    # Per-dtype byte histogram over parameters + buffers.
    by_dtype: dict = defaultdict(lambda: [0, 0])  # dtype -> [count, bytes]
    fp32_modules: list = []
    for name, t in list(model.named_parameters()) + list(model.named_buffers()):
        b = t.numel() * t.element_size()
        by_dtype[str(t.dtype)][0] += 1
        by_dtype[str(t.dtype)][1] += b
        if t.dtype == torch.float32 and b > 5_000_000:  # >5 MB fp32 tensors
            fp32_modules.append((b, name, tuple(t.shape)))

    print("-- parameter/buffer bytes by dtype --")
    for dt, (cnt, b) in sorted(by_dtype.items(), key=lambda kv: -kv[1][1]):
        print(f"  {dt:18} {b/1e9:6.2f} GB  ({cnt} tensors)")

    if fp32_modules:
        fp32_modules.sort(reverse=True)
        print("\n-- largest fp32 tensors (the ones that don't shrink with weight quant) --")
        for b, name, shape in fp32_modules[:12]:
            print(f"  {b/1e6:8.1f} MB  {name}  {shape}")
    else:
        print("\n(no large fp32 tensors — good; nothing forced to fp32 at this dtype)")

    print("\nDone. If this fit in bf16 but OOMs in float32, forcing dtype=bfloat16 is the fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
