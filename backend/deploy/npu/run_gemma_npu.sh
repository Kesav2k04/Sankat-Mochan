#!/usr/bin/env bash
# Run a Q4_0 Gemma GGUF on the Snapdragon 8 Elite Gen 5 Hexagon NPU (OnePlus 15) via
# llama.cpp's Hexagon backend. Mirrors llama.cpp's public Snapdragon docs (MIT, CLAUDE.md #3):
# https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md
#
# Usage:  bash backend/deploy/npu/run_gemma_npu.sh <model-Q4_0.gguf> "your prompt"
#
# Prereqs:
#   * llama.cpp built with the Snapdragon preset AND pushed to the phone:
#       cmake --preset arm64-android-snapdragon-release -B build-snapdragon   # GGML_HEXAGON=ON
#       cmake --build build-snapdragon
#     Set LLAMA_CPP to that checkout root.
#   * adb; phone in USB-debugging mode; QAIRT/Hexagon libs bundled by the preset install.
#
# The HTP wants Q4_0/Q8_0 — build the GGUF with backend/deploy/npu/build_gemma_gguf.py, not Q4_K_M.

set -euo pipefail

MODEL="${1:?usage: run_gemma_npu.sh <model-Q4_0.gguf> \"prompt\"}"
PROMPT="${2:?usage: run_gemma_npu.sh <model-Q4_0.gguf> \"prompt\"}"
LLAMA_CPP="${LLAMA_CPP:?set LLAMA_CPP to your built llama.cpp checkout (Snapdragon preset)}"

# HTP session count: 1 for models <4B params (Gemma E2B qualifies). See GGML_HEXAGON_NDEV.
NDEV="${NDEV:-1}"
# HTP0 = first NPU session. Use "HTP0,HTP1" with NDEV=2 for ~8B models.
DEV="${DEV:-HTP0}"

[[ -f "$MODEL" ]] || { echo "[error] GGUF not found: $MODEL" >&2; exit 1; }
command -v adb >/dev/null || { echo "[error] adb not on PATH" >&2; exit 1; }

RUN_SCRIPT="${LLAMA_CPP}/scripts/snapdragon/adb/run-completion.sh"
[[ -f "$RUN_SCRIPT" ]] || { echo "[error] $RUN_SCRIPT missing — build/pull llama.cpp Snapdragon preset" >&2; exit 1; }

# Sahayak's fixed system prompt (must match training — finetune spec §1.1). Untrusted user
# text goes ONLY in the user turn, never spliced next to system instructions (CLAUDE.md #7).
SYSTEM_PROMPT="You are Sahayak, an offline emergency-response assistant running on a local device in a disaster zone. You help with first aid, message relay, resource allocation, and navigation. Be brief, calm, and practical. You are not a doctor; for medical guidance give first-aid steps only and tell the user to reach professional care when possible. Never transmit information that could endanger people if intercepted."

# Gemma chat template turns.
FULL_PROMPT="<start_of_turn>user
${SYSTEM_PROMPT}

${PROMPT}<end_of_turn>
<start_of_turn>model
"

MODEL_NAME="$(basename "$MODEL")"
echo "[push] $MODEL_NAME -> phone"
adb push "$MODEL" "/data/local/tmp/${MODEL_NAME}" >/dev/null

echo "[run] llama.cpp on Hexagon (D=${DEV}, NDEV=${NDEV}) ..."
# run-completion.sh reads M (model basename), D (HTP device list), NDEV (session count).
M="$MODEL_NAME" D="$DEV" NDEV="$NDEV" GGML_HEXAGON_VERBOSE="${GGML_HEXAGON_VERBOSE:-0}" \
  "$RUN_SCRIPT" -p "$FULL_PROMPT"
