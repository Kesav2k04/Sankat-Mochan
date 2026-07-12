#!/usr/bin/env python3
"""
Quality-review harness for the quantized Sahayak GGUF.

4-bit quantization shifts outputs, and Sahayak gives first-aid guidance — so before a Q4_0
GGUF goes near the phone, a human must read what it now says on held-out prompts (CLAUDE.md
#6: security-sensitive output gets human review). This runs each eval record through the
quantized model with `llama-cli` (MIT) and prints the model's answer next to the reference,
plus cheap automatic flags (empty output, truncation, big length blow-ups) to triage which
ones to read first.

This is a review AID, not an automatic grader — it does not decide pass/fail for you.

Usage:
  python deploy/npu/eval_gguf.py \
      --gguf deploy/npu/out/sahayak-gemma-Q4_0.gguf \
      --llama-cpp /path/to/llama.cpp \
      --eval finetune/data/eval_holdout.jsonl --limit 10
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Sahayak's fixed system prompt — must match training/inference byte-for-byte (finetune spec
# §1.1). Imported concept mirrors finetune/sahayak_finetune.py SYSTEM_PROMPT.
SYSTEM_PROMPT = (
    "You are Sahayak, an offline emergency-response assistant running on a local device in a "
    "disaster zone. You help with first aid, message relay, resource allocation, and navigation. "
    "Be brief, calm, and practical. You are not a doctor; for medical guidance give first-aid "
    "steps only and tell the user to reach professional care when possible. Never transmit "
    "information that could endanger people if intercepted."
)


def find_llama_cli(llama_dir: Path) -> Path:
    for r in (llama_dir / "build" / "bin", llama_dir / "build-snapdragon" / "bin",
              llama_dir / "build", llama_dir):
        for n in ("llama-cli", "main"):
            for cand in (r / n, r / f"{n}.exe"):
                if cand.exists():
                    return cand
    sys.exit(f"[error] llama-cli not found under {llama_dir} — build llama.cpp first.")


def gemma_prompt(user_text: str) -> str:
    """Gemma chat template. Gemma has no separate system role, so the system prompt is folded
    into the first user turn — the same shape run_gemma_npu.sh uses on-device, so host eval
    and phone inference see identical formatting."""
    return (f"<start_of_turn>user\n{SYSTEM_PROMPT}\n\n{user_text}<end_of_turn>\n"
            f"<start_of_turn>model\n")


def first_user_and_reference(messages: list) -> tuple[str, str] | None:
    """Pull the first user turn and its reference assistant answer from a messages record."""
    body = [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]
    user = next((m["content"] for m in body if m.get("role") == "user"), None)
    ref = next((m["content"] for m in body if m.get("role") == "assistant"), None)
    if not user or not ref:
        return None
    return user, ref


def run_one(cli: Path, gguf: Path, prompt: str, n_predict: int, ctx: int) -> str:
    """Single deterministic completion. -no-cnv = one-shot (no interactive chat loop)."""
    cmd = [str(cli), "-m", str(gguf), "-p", prompt, "-n", str(n_predict),
           "-c", str(ctx), "--temp", "0", "-no-cnv", "--no-display-prompt"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return f"[llama-cli error {out.returncode}] {out.stderr.strip()[-300:]}"
    # --no-display-prompt keeps the echoed prompt out of stdout; strip any trailing end-of-turn.
    return out.stdout.replace("<end_of_turn>", "").strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Human-review harness for the quantized Sahayak GGUF.")
    p.add_argument("--gguf", required=True, help="The quantized GGUF to review.")
    p.add_argument("--llama-cpp", required=True, help="Built llama.cpp checkout (host build).")
    p.add_argument("--eval", default="finetune/data/eval_holdout.jsonl")
    p.add_argument("--limit", type=int, default=10, help="How many records to run.")
    p.add_argument("--n-predict", type=int, default=256)
    p.add_argument("--ctx", type=int, default=2048)
    args = p.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    gguf = Path(args.gguf)
    if not gguf.exists():
        sys.exit(f"[error] GGUF not found: {gguf}")
    cli = find_llama_cli(Path(args.llama_cpp))
    eval_path = Path(args.eval)
    if not eval_path.exists():
        sys.exit(f"[error] eval file not found: {eval_path}")

    print(f"=== Sahayak GGUF review: {gguf.name} ===")
    print(f" model : {gguf}")
    print(f" via   : {cli}")
    print("=" * 48)

    flagged = 0
    shown = 0
    with eval_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if shown >= args.limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            pair = first_user_and_reference(rec.get("messages", []))
            if pair is None:
                continue
            user, ref = pair
            answer = run_one(cli, gguf, gemma_prompt(user), args.n_predict, args.ctx)
            shown += 1

            # Cheap automatic triage flags — cues for what to read, not a verdict.
            flags = []
            if not answer or answer.startswith("[llama-cli error"):
                flags.append("EMPTY/ERROR")
            elif len(answer) > 3 * len(ref) + 200:
                flags.append("MUCH-LONGER-THAN-REF")
            if flags:
                flagged += 1

            print(f"\n[{shown}] {'  ⚠ ' + ','.join(flags) if flags else ''}")
            print(f"  USER      : {user.strip()[:300]}")
            print(f"  REFERENCE : {ref.strip()[:400]}")
            print(f"  MODEL(Q4) : {answer[:400]}")

    print("\n" + "=" * 48)
    print(f"[done] reviewed {shown} record(s); {flagged} auto-flagged for a closer read.")
    print("Human review required before shipping (CLAUDE.md #6): confirm first-aid steps are "
          "correct, safe, and not degraded vs the reference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
