#!/usr/bin/env bash
# Push a Genie bundle to an Android phone (OnePlus 15 / Snapdragon 8 Elite Gen 5) and run
# a prompt on the Hexagon NPU via genie-t2t-run. Mirrors Qualcomm's public llm_on_genie
# README (BSD/Apache, CLAUDE.md #3): https://github.com/qualcomm/ai-hub-apps
#
# Usage:  bash backend/deploy/npu/run_on_device.sh <genie_bundle_dir> "your prompt"
#
# Prereqs on the HOST:
#   * adb on PATH, phone in USB-debugging mode (`adb devices` shows it).
#   * QAIRT SDK downloaded from Qualcomm Software Center; set QAIRT_HOME below.
# Prereq on the PHONE: developer mode + USB debugging. Nothing is installed persistently;
# everything runs from /data/local/tmp and can be wiped with `adb shell rm -rf`.

set -euo pipefail

BUNDLE="${1:?usage: run_on_device.sh <genie_bundle_dir> \"prompt\"}"
PROMPT="${2:?usage: run_on_device.sh <genie_bundle_dir> \"prompt\"}"

# Point this at your unpacked QAIRT SDK. Do NOT commit an absolute machine path — override
# via the environment: QAIRT_HOME=/opt/qairt/2.x bash run_on_device.sh ...
QAIRT_HOME="${QAIRT_HOME:?set QAIRT_HOME to your QAIRT SDK root before running}"

# Hexagon version for Snapdragon 8 Elite Gen 5. Verify against your SDK's lib dir; the
# 8 Elite family is v79. (v73 = X Elite laptop, a different target.)
HEXAGON_VER="${HEXAGON_VER:-v79}"

DEVICE_DIR="/data/local/tmp/sahayak"
SDK_LIB="${QAIRT_HOME}/lib/aarch64-android"
SDK_BIN="${QAIRT_HOME}/bin/aarch64-android"
SDK_SKEL="${QAIRT_HOME}/lib/hexagon-${HEXAGON_VER}/unsigned"

if [[ ! -d "$BUNDLE" ]]; then echo "[error] bundle dir not found: $BUNDLE" >&2; exit 1; fi
if [[ ! -f "$BUNDLE/genie_config.json" ]]; then
  echo "[error] $BUNDLE has no genie_config.json — is this an exported Genie bundle?" >&2; exit 1
fi
command -v adb >/dev/null || { echo "[error] adb not on PATH" >&2; exit 1; }

echo "[push] runtime libs + skel → $DEVICE_DIR"
adb shell "mkdir -p ${DEVICE_DIR}"
adb push "$BUNDLE" "${DEVICE_DIR}/bundle" >/dev/null
adb push "${SDK_LIB}/." "${DEVICE_DIR}/" >/dev/null
adb push "${SDK_BIN}/genie-t2t-run" "${DEVICE_DIR}/" >/dev/null
adb push "${SDK_SKEL}/." "${DEVICE_DIR}/" >/dev/null

# Sahayak's fixed system prompt must match training byte-for-byte (see finetune spec §1.1).
# Kept here as a literal so the on-device prompt is reproducible.
SYSTEM_PROMPT="You are Sahayak, an offline emergency-response assistant running on a local device in a disaster zone. You help with first aid, message relay, resource allocation, and navigation. Be brief, calm, and practical. You are not a doctor; for medical guidance give first-aid steps only and tell the user to reach professional care when possible. Never transmit information that could endanger people if intercepted."

# Build the Qwen chat-formatted prompt. NOTE: untrusted end-user text (PROMPT) is placed
# only inside the user turn, never concatenated next to system instructions (CLAUDE.md #7).
FULL_PROMPT="<|im_start|>system
${SYSTEM_PROMPT}<|im_end|>
<|im_start|>user
${PROMPT}<|im_end|>
<|im_start|>assistant
"

echo "[run] genie-t2t-run on Hexagon (${HEXAGON_VER}) …"
adb shell "cd ${DEVICE_DIR} && \
  export LD_LIBRARY_PATH=${DEVICE_DIR} && \
  export ADSP_LIBRARY_PATH=${DEVICE_DIR} && \
  ./genie-t2t-run -c bundle/genie_config.json -p '$(printf '%s' "$FULL_PROMPT")'"
