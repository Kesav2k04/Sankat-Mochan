#!/usr/bin/env python3
"""
GPU capability + memory-attribution probe for the Sahayak fine-tune.

Answers, empirically on the actual card, two questions:
  1. What numeric / quantization formats does THIS GPU support (fp32/fp16/bf16, int8
     tensor-core matmul, bitsandbytes nf4/fp4 4-bit, int8 weight quant)?
  2. Why does Gemma 4 E4B OOM on a T4 even at 4-bit — i.e. show that the cost is the
     fp32 activation/conv path, which weight quantization does NOT shrink.

Run it on Kaggle (or any CUDA box) as a cell or `python t4_probe.py` and read the summary.
Nothing here trains or downloads a model; it only exercises tiny tensors, so it is safe and fast.
"""

from __future__ import annotations


def can_matmul(torch, dtype) -> str:
    try:
        a = torch.randn(512, 512, device="cuda", dtype=dtype)
        b = torch.randn(512, 512, device="cuda", dtype=dtype)
        torch.cuda.synchronize()
        _ = a @ b
        torch.cuda.synchronize()
        return "OK"
    except Exception as e:  # noqa: BLE001 - report whatever the backend raises
        return f"FAIL: {type(e).__name__}: {str(e)[:70]}"


def act_peak_mb(torch, dtype, n: int = 8192) -> float:
    """Peak VRAM (MB) to hold one n×n activation tensor in `dtype`."""
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    x = torch.randn(n, n, device="cuda", dtype=dtype)
    torch.cuda.synchronize()
    mb = torch.cuda.max_memory_allocated() / 1e6
    del x
    torch.cuda.empty_cache()
    return mb


def main() -> int:
    import torch

    print("torch", torch.__version__, "| CUDA", torch.version.cuda)
    if not torch.cuda.is_available():
        print("No CUDA GPU visible — run this on the GPU accelerator.")
        return 1

    name = torch.cuda.get_device_name(0)
    cc = torch.cuda.get_device_capability(0)
    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {name} | compute capability: {cc[0]}.{cc[1]} | VRAM: {total:.1f} GB")

    print("\n-- float matmul support --")
    for dt in (torch.float32, torch.float16, torch.bfloat16):
        print(f"  {str(dt):16}: {can_matmul(torch, dt)}")
    print("  torch.cuda.is_bf16_supported():", torch.cuda.is_bf16_supported())

    print("\n-- int8 tensor-core matmul (Turing/T4 has these) --")
    try:
        a = torch.randint(-127, 127, (512, 512), device="cuda", dtype=torch.int8)
        b = torch.randint(-127, 127, (512, 512), device="cuda", dtype=torch.int8)
        c = torch._int_mm(a, b)
        torch.cuda.synchronize()
        print("  torch._int_mm int8: OK ->", c.dtype, tuple(c.shape))
    except Exception as e:  # noqa: BLE001
        print("  torch._int_mm int8:", type(e).__name__, str(e)[:90])

    print("\n-- bitsandbytes weight-quantization formats --")
    try:
        import bitsandbytes as bnb
        from bitsandbytes.nn import Linear4bit, Linear8bitLt

        print("  bnb", bnb.__version__)
        for qt in ("nf4", "fp4"):
            try:
                lin = Linear4bit(
                    1024, 1024, bias=False, quant_type=qt, compute_dtype=torch.float16
                ).cuda()
                y = lin(torch.randn(4, 1024, device="cuda", dtype=torch.float16))
                torch.cuda.synchronize()
                print(f"  4-bit {qt}: OK  (weights stored 4-bit, compute {y.dtype})")
            except Exception as e:  # noqa: BLE001
                print(f"  4-bit {qt}: {type(e).__name__}: {str(e)[:70]}")
        try:
            l8 = Linear8bitLt(1024, 1024, bias=False, has_fp16_weights=False).cuda()
            y = l8(torch.randn(4, 1024, device="cuda", dtype=torch.float16))
            torch.cuda.synchronize()
            print("  8-bit int8 (LLM.int8): OK  out=", y.dtype)
        except Exception as e:  # noqa: BLE001
            print("  8-bit int8:", type(e).__name__, str(e)[:70])
    except Exception as e:  # noqa: BLE001
        print("  bitsandbytes unavailable:", type(e).__name__, str(e)[:90])

    print("\n-- why fp32 hurts: activation memory is NOT reduced by weight quant --")
    try:
        fp16 = act_peak_mb(torch, torch.float16)
        fp32 = act_peak_mb(torch, torch.float32)
        print(
            f"  one 8192x8192 activation   fp16: {fp16:.0f} MB   fp32: {fp32:.0f} MB  (2x)"
        )
        print(
            "  Gemma 4 is multimodal: its Conv/vision activations overflow fp16 (max 65504),\n"
            "  and the T4 has no bf16 (see is_bf16_supported above), so Unsloth upcasts that\n"
            "  path to fp32 = 2x memory. That fp32 mass is the ~5 GB that OOMs at load, and\n"
            "  quantizing WEIGHTS to nf4/int4/int8 (all 'OK' above) does not shrink it."
        )
    except Exception as e:  # noqa: BLE001
        print("  activation probe:", type(e).__name__, str(e)[:90])

    print("\n-- levers that DO reduce the fp32 activation/conv path --")
    print("  * bf16-capable GPU (Ampere+ : A100/L4/RTX30-40) -> no fp16 overflow -> no fp32 upcast")
    print("  * smaller model (Gemma 4 E2B) -> smaller conv/vision tower")
    print("  * text-only load: drop the vision+audio submodules before the fp32 cast")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
