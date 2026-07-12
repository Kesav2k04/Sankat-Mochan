#!/usr/bin/env python3
"""
Sahayak (Gemma) → custom Q4_0 GGUF for the Snapdragon Hexagon NPU.

Keeps the Gemma finetune as-is (no re-base) and takes the GGUF route, because that is how
Gemma reaches the NPU on Qualcomm: llama.cpp's Hexagon backend (`GGML_HEXAGON=ON`) and the
GenieX `geniex_llamacpp` runtime both run GGUF on the HTP. The catch that dictates the whole
recipe: **the HTP wants Q4_0 (or Q8_0)**. Qualcomm's own GenieX notes say "Q4_K_M is a
suboptimal quant for HTP — it prefers Q4_0 / Q8_0", and llama.cpp's Snapdragon docs use Q4_0
exclusively (it repacks Q4_0 internally for the NPU). So we quantize to Q4_0, not the usual
Q4_K_M.

Pipeline (all local, llama.cpp — MIT, CLAUDE.md #1):
  1. convert_hf_to_gguf.py  : merged Gemma HF weights → f16 GGUF
  2. llama-imatrix (optional): importance matrix from an IN-DOMAIN corpus built from the
                               training data — meaningfully steadier low-bit quality for a
                               task-specific model. Uses backend/finetune/data/train.jsonl.
  3. llama-quantize         : f16 GGUF → Q4_0 GGUF (the HTP-preferred format)

Input is a directory of MERGED finetuned Gemma weights (LoRA already merged into the base):
  python backend/finetune/sahayak_finetune.py --model google/gemma-4-E2B-it ... --export-merged
  (feed the out/*/merged dir to --merged-checkpoint here)

Then run on device: see backend/deploy/npu/run_gemma_npu.sh (llama.cpp HTP) or `geniex infer <gguf>
--device npu` (GenieX). BASE CONFIRMED (HF repo kesav2k04/sahayak-e2b): google/gemma-4-E2B-it,
model_type=gemma4 (NOT Gemma 3n), so convert_hf_to_gguf.py supports it. The checkpoint is
Gemma4ForConditionalGeneration (multimodal); for this text-only assistant the converter emits
the LLM GGUF (vision/audio mmproj not needed). The repo already ships merged weights under
merged/ — download that dir and pass it as --merged-checkpoint (no re-merge required).

Command shapes from public docs (CLAUDE.md #3), all open-license:
  - llama.cpp docs/backend/snapdragon/README.md, tools/quantize/README.md  (MIT)
  - Qualcomm GenieX notes/run.md                                           (BSD/Apache)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, dry_run: bool) -> None:
    printable = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    print(f"\n$ {printable}\n", flush=True)
    if dry_run:
        print("[dry-run] not executed")
        return
    if subprocess.run([str(c) for c in cmd]).returncode != 0:
        sys.exit(f"[error] step failed: {cmd[:2]} ...")


def _find(llama_dir: Path, names: list[str], kind: str) -> Path:
    """Locate a llama.cpp tool across the layouts cmake produces (build/bin, build/, root)."""
    roots = [llama_dir, llama_dir / "build" / "bin", llama_dir / "build",
             llama_dir / "build-snapdragon" / "bin"]
    for r in roots:
        for n in names:
            for cand in (r / n, r / f"{n}.exe"):
                if cand.exists():
                    return cand
    sys.exit(f"[error] could not find {kind} ({'/'.join(names)}) under {llama_dir}. "
             "Build llama.cpp first (see backend/deploy/npu/README.md).")


def build_calibration_corpus(train_jsonl: Path, out_txt: Path, max_records: int) -> Path:
    """Flatten the messages-format training data into a plain-text corpus for llama-imatrix.

    In-domain calibration: the importance matrix reflects the emergency-response distribution
    the model is actually quantized for, not generic web text. Untrusted-input hygiene still
    applies (CLAUDE.md #8) — we only READ the local training file and emit text, no execution.
    """
    n = 0
    with train_jsonl.open("r", encoding="utf-8") as fin, out_txt.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                msgs = rec.get("messages", [])
            except json.JSONDecodeError:
                continue  # skip malformed lines rather than abort the whole build
            text = "\n".join(m.get("content", "") for m in msgs if isinstance(m, dict))
            if text.strip():
                fout.write(text.strip() + "\n\n")
                n += 1
            if n >= max_records:
                break
    if n == 0:
        sys.exit(f"[error] no usable records in {train_jsonl} for calibration corpus")
    print(f"[imatrix] built calibration corpus from {n} records -> {out_txt}")
    return out_txt


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Convert + quantize a merged Gemma finetune to a Q4_0 GGUF for the "
                    "Snapdragon Hexagon NPU (llama.cpp / GenieX).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--merged-checkpoint", required=True,
                   help="Local dir of MERGED finetuned Gemma weights (LoRA merged into base).")
    p.add_argument("--llama-cpp", required=True,
                   help="Path to a built llama.cpp checkout (has convert_hf_to_gguf.py + "
                        "llama-quantize/llama-imatrix binaries).")
    p.add_argument("--out-dir", default="backend/deploy/npu/out",
                   help="Where GGUF artifacts are written.")
    p.add_argument("--name", default="sahayak-gemma",
                   help="Basename for the output GGUF files.")
    p.add_argument("--quant", default="Q4_0", choices=["Q4_0", "Q8_0"],
                   help="HTP-friendly quant. Q4_0 = smallest/fastest on NPU; Q8_0 = higher "
                        "fidelity. Do NOT use Q4_K_M for the HTP (suboptimal per Qualcomm).")
    p.add_argument("--imatrix", action="store_true", default=True,
                   help="Build an in-domain importance matrix from the training data first.")
    p.add_argument("--no-imatrix", dest="imatrix", action="store_false",
                   help="Skip the importance matrix (faster; slightly worse low-bit quality).")
    p.add_argument("--train-jsonl", default="backend/finetune/data/train.jsonl",
                   help="Training data used to build the imatrix calibration corpus.")
    p.add_argument("--imatrix-samples", type=int, default=512,
                   help="Max training records to include in the calibration corpus.")
    p.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = p.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
        except (AttributeError, ValueError):
            pass

    merged = Path(args.merged_checkpoint)
    llama = Path(args.llama_cpp)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not (merged / "config.json").exists():
        sys.exit(f"[error] {merged} is not a merged HF checkpoint (no config.json). Point "
                 "--merged-checkpoint at the 'merged' dir, not the LoRA-adapter dir.")
    convert_py = llama / "convert_hf_to_gguf.py"
    if not convert_py.exists() and not args.dry_run:
        sys.exit(f"[error] {convert_py} not found — is --llama-cpp a real llama.cpp checkout?")

    f16 = out / f"{args.name}-f16.gguf"
    quant_out = out / f"{args.name}-{args.quant}.gguf"

    print("=== Sahayak Gemma -> Q4_0 GGUF (Hexagon NPU) ===")
    print(f" source : {merged}")
    print(f" quant  : {args.quant}  (imatrix={'on' if args.imatrix else 'off'})")
    print(f" outputs: {f16}  ->  {quant_out}")
    print("=" * 48)

    # 1. HF -> f16 GGUF
    _run([sys.executable, str(convert_py), str(merged),
          "--outfile", str(f16), "--outtype", "f16"], dry_run=args.dry_run)

    # 2. optional in-domain importance matrix
    quantize_cmd = [str(_find(llama, ["llama-quantize", "quantize"], "llama-quantize"))
                    if not args.dry_run else "llama-quantize"]
    if args.imatrix:
        corpus = out / f"{args.name}-calib.txt"
        if not args.dry_run:
            build_calibration_corpus(Path(args.train_jsonl), corpus, args.imatrix_samples)
        imat = out / f"{args.name}-imatrix.dat"
        imatrix_bin = (str(_find(llama, ["llama-imatrix", "imatrix"], "llama-imatrix"))
                       if not args.dry_run else "llama-imatrix")
        _run([imatrix_bin, "-m", str(f16), "-f", str(corpus), "-o", str(imat)],
             dry_run=args.dry_run)
        quantize_cmd += ["--imatrix", str(imat)]

    # 3. f16 GGUF -> Q4_0 GGUF
    _run(quantize_cmd + [str(f16), str(quant_out), args.quant], dry_run=args.dry_run)

    print(f"\n[done] NPU-ready GGUF: {quant_out}")
    print("Review quality before shipping (CLAUDE.md #6):")
    print(f"  python backend/deploy/npu/eval_gguf.py --gguf {quant_out} --llama-cpp {args.llama_cpp}")
    print("Run on the OnePlus 15 (Hexagon NPU):")
    print(f"  bash backend/deploy/npu/run_gemma_npu.sh {quant_out} \"first-aid for a deep cut?\"")
    print("Or via GenieX:")
    print(f"  geniex infer {quant_out} --device npu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
