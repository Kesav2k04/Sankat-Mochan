#!/usr/bin/env python3
"""
Sahayak → mobile-NPU pipeline: quantize + compile a finetuned LLM to a Genie bundle
that runs on the Snapdragon 8 Elite Gen 5 Hexagon NPU (OnePlus 15).

This is a thin, auditable orchestrator around Qualcomm's own `qai-hub-models` CLI
(BSD-3-Clause). It runs the two AI-Hub stages back-to-back:

  1. `.quantize`  — local AIMET post-training quantization (w4a16) of YOUR merged
                    finetuned weights, calibrated in-toolchain → a "calibrated checkpoint".
  2. `.export`    — submits a COMPILE JOB to Qualcomm AI Hub (cloud) that turns the
                    calibrated checkpoint into QAIRT context binaries for the target
                    Hexagon version, and assembles a Genie bundle you push to the phone.

Command shapes are taken verbatim from Qualcomm's public docs (Apache/BSD, CLAUDE.md #3):
  - ai-hub-apps/tutorials/llm_on_genie/{README,export}.md
  - qai_hub_models/models/_shared/llm/{quantize,export}.py  (the argparse is the contract)

WHY NOT GEMMA (important):
  The Sahayak adapter was trained on Gemma, but on Qualcomm AI Hub `gemma_4_e2b_it`
  only ships the llama.cpp/GGUF runtime (`geniex_llamacpp`, q4_0) — that does NOT use
  the optimized QNN Hexagon path. Qwen3-4B (Apache-2.0) and Llama-3.2-3B DO expose the
  QNN path (`geniex_qairt`/`genie`, w4a16). So the finetune is re-based onto Qwen3-4B —
  a one-flag change to sahayak_finetune.py (`--model Qwen/Qwen3-4B`), because the LoRA
  targets (q/k/v/o/gate/up/down_proj) exist identically in Qwen. See backend/deploy/npu/README.md.

This script does NOT download weights or train. Its input is a local directory of
*merged* finetuned weights (LoRA already merged into the Qwen3-4B base). Produce that
with:  python backend/finetune/sahayak_finetune.py --model Qwen/Qwen3-4B ... --export-merged

Prereqs (see README.md for the long version):
  * A CUDA GPU for the quantize step (AIMET calibration of a 4B model is not a CPU job).
  * `uv pip install -U "qai-hub-models[qwen3-4b]"`  (extras name matches the model id, dashes)
  * A configured AI Hub token for the export/compile step:  qai-hub configure --api_token …
    (never hardcode it — CLAUDE.md #2; the token lives in ~/.qai_hub/client.ini)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Files that make a directory a loadable HF checkpoint. The AI Hub quantizer needs the
# model config alongside the weights; its own docs remind you to copy the config into the
# calibrated output dir for custom weights, which we automate in _copy_model_config().
_CONFIG_FILES = (
    "config.json",
    "generation_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "tokenizer.model",
    "special_tokens_map.json",
    "vocab.json",
    "merges.txt",
)


def _run(cmd: list[str], *, dry_run: bool) -> None:
    """Echo then run a subprocess step, failing loudly (a half-built bundle is worse
    than a clear stop). We never shell=True — args are passed as a list."""
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print(f"\n$ {printable}\n", flush=True)
    if dry_run:
        print("[dry-run] not executed")
        return
    result = subprocess.run(cmd)  # inherits stdout/stderr so AI Hub job links stream live
    if result.returncode != 0:
        sys.exit(f"[error] step failed (exit {result.returncode}): {cmd[:3]} ...")


def _copy_model_config(src: Path, dst: Path) -> None:
    """Copy tokenizer/config files from the merged checkpoint into the calibrated dir.
    Qualcomm's quantize.py prints this exact reminder for custom weights: the demo/eval/
    export steps reload the config from the checkpoint folder."""
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in _CONFIG_FILES:
        f = src / name
        if f.exists():
            shutil.copy2(f, dst / name)
            copied.append(name)
    if copied:
        print(f"[config] copied {len(copied)} config file(s) into {dst}: {', '.join(copied)}")


def preflight(args) -> None:
    """Fail early on the mistakes that waste a long GPU run or a cloud compile job."""
    ckpt = Path(args.merged_checkpoint)
    if not ckpt.is_dir():
        sys.exit(f"[error] --merged-checkpoint is not a directory: {ckpt}\n"
                 "        Produce it first: python backend/finetune/sahayak_finetune.py "
                 "--model Qwen/Qwen3-4B ... --export-merged  (use the out/*/merged dir)")
    if not (ckpt / "config.json").exists():
        sys.exit(f"[error] {ckpt} has no config.json — not a merged HF checkpoint. "
                 "Point --merged-checkpoint at the 'merged' dir, not the LoRA-adapter dir.")

    if not args.dry_run:
        try:
            import qai_hub_models  # noqa: F401
        except Exception:
            sys.exit('[error] qai-hub-models not installed. Run:\n'
                     f'        uv pip install -U "qai-hub-models[{args.model.replace("_", "-")}]"')

    # The export/compile step needs a configured AI Hub token. We only CHECK for it; we
    # never read or print it (CLAUDE.md #2). Absence is a warning, not a hard stop, so
    # --stop-after quantize still works on a box with no token.
    token_ini = Path.home() / ".qai_hub" / "client.ini"
    if not token_ini.exists() and args.stop_after != "quantize":
        print("[warn] no AI Hub token found (~/.qai_hub/client.ini). The compile/export "
              "step will fail until you run:  qai-hub configure --api_token <token>")


def build_quantize_cmd(args, out_calibrated: Path) -> list[str]:
    cmd = [
        sys.executable, "-m", f"qai_hub_models.models.{args.model}.quantize",
        "--checkpoint", str(Path(args.merged_checkpoint).resolve()),
        "--precision", args.precision,
        "--context-length", str(args.context_length),
        "--calibration-sequence-length", str(args.calibration_seq_len),
        "--num-samples", str(args.num_samples),
        "--output-dir", str(out_calibrated),
    ]
    if args.use_seq_mse:
        # Sequential-MSE calibration: slower, meaningfully better at 4-bit. Worth it for a
        # task-specific model where a quantization regression could drop a first-aid answer.
        cmd.append("--use-seq-mse")
    return cmd


def build_export_cmd(args, in_calibrated: Path, out_bundle: Path) -> list[str]:
    return [
        sys.executable, "-m", f"qai_hub_models.models.{args.model}.export",
        "--checkpoint", str(in_calibrated.resolve()),
        "--chipset", args.chipset,
        "--context-length", str(args.context_length),
        "--skip-profiling",     # we want the bundle, not an on-device perf run
        "--skip-inferencing",   # skip the AI-Hub-side inference job (adds time/quota)
        "--output-dir", str(out_bundle),
    ]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Quantize (w4a16) + compile a merged finetuned LLM to a Genie bundle "
                    "for the Snapdragon 8 Elite Gen 5 Hexagon NPU, via Qualcomm AI Hub.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--merged-checkpoint", required=True,
                   help="Local dir of MERGED finetuned weights (LoRA merged into the base). "
                        "Must be the same base as --model (e.g. Qwen/Qwen3-4B).")
    p.add_argument("--model", default="qwen3_4b",
                   help="qai-hub-models package id. Must expose the QNN path (geniex_qairt/"
                        "genie): qwen3_4b (Apache-2.0, recommended) or llama_v3_2_3b_instruct. "
                        "NOT gemma_4_e2b_it — that is llama.cpp-only, no optimized NPU path.")
    p.add_argument("--precision", default="w4a16",
                   help="Weight/activation precision. w4a16 is the QNN-NPU default for these "
                        "models; confirm with `python -m qai_hub_models.models.<model>.quantize --help`.")
    p.add_argument("--chipset", default="qualcomm-snapdragon-8-elite-gen5",
                   help="Compile target. OnePlus 15 = qualcomm-snapdragon-8-elite-gen5. "
                        "(X Elite laptop later: qualcomm-snapdragon-x-elite — same source, "
                        "re-run .export only.)")
    p.add_argument("--context-length", type=int, default=2048,
                   help="KV-cache context. 2048 keeps memory modest on a phone; raise if the "
                        "device has headroom (docs: 12GB+ for 3B-class at 4096).")
    p.add_argument("--calibration-seq-len", type=int, default=2048,
                   help="Sequence length used only during calibration.")
    p.add_argument("--num-samples", type=int, default=128,
                   help="Calibration samples. More = steadier 4-bit encodings, slower quantize.")
    p.add_argument("--use-seq-mse", action="store_true", default=True,
                   help="Sequential-MSE calibration (recommended for accuracy at 4-bit).")
    p.add_argument("--no-seq-mse", dest="use_seq_mse", action="store_false",
                   help="Disable sequential-MSE (faster, slightly worse 4-bit quality).")
    p.add_argument("--work-dir", default="backend/deploy/npu/out",
                   help="Where the calibrated checkpoint and Genie bundle are written.")
    p.add_argument("--stop-after", choices=["quantize", "export"], default="export",
                   help="Stop after the quantize stage (no AI Hub token / offline) or run through export.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the exact commands without running them (audit the pipeline first).")
    args = p.parse_args(argv)

    # The demo target is a Windows box whose console defaults to cp1252; keep stdout on
    # UTF-8 so a stray non-ASCII byte in a model path or AI Hub message can't crash a build.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # py3.7+; no-op if already utf-8
        except (AttributeError, ValueError):
            pass

    preflight(args)

    work = Path(args.work_dir)
    calibrated = work / f"{args.model}_{args.precision}_calibrated"
    bundle = work / f"{args.model}_{args.precision}_genie_bundle"

    print("=== Sahayak mobile-NPU build ===")
    print(f" base model  : {args.model}  (precision {args.precision})")
    print(f" source      : {args.merged_checkpoint}")
    print(f" target      : {args.chipset}")
    print(f" context len : {args.context_length}")
    print(f" outputs     : {calibrated}  ->  {bundle}")
    print("=" * 32)

    # Stage 1 — quantize (local, GPU): merged fp16 weights → calibrated w4a16 checkpoint.
    _run(build_quantize_cmd(args, calibrated), dry_run=args.dry_run)
    if not args.dry_run:
        _copy_model_config(Path(args.merged_checkpoint), calibrated)

    if args.stop_after == "quantize":
        print(f"\n[done] calibrated checkpoint at {calibrated}")
        print("Sanity-check it before compiling:")
        print(f"  python -m qai_hub_models.models.{args.model}.demo "
              f"--checkpoint {calibrated} --prompt 'A wall collapsed, someone is bleeding. What do I do?'")
        return 0

    # Stage 2 — export (cloud compile on AI Hub): calibrated checkpoint → Genie bundle.
    _run(build_export_cmd(args, calibrated, bundle), dry_run=args.dry_run)

    print(f"\n[done] Genie bundle at {bundle}")
    print("Push and run on the OnePlus 15:  bash backend/deploy/npu/alt-aihub-qwen/run_on_device.sh "
          f"{bundle} \"What are the first-aid steps for a deep cut?\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
