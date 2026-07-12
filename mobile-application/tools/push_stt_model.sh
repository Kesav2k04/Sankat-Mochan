#!/usr/bin/env bash
# Push the on-device STT model onto the phone (it's ~1.2 GB, so it is side-loaded, not bundled
# in the APK — same pattern as the GenieX LLM weights).
#
# Extracts the two AI Hub precompiled_qnn_onnx artifacts (encoder + ctc_decoder), each a folder
# of model.onnx + model.bin, and adb-pushes them into the app's external files dir with the
# subdir layout SttEngine expects:
#   files/stt/encoder/model.onnx      + model.bin
#   files/stt/ctc_decoder/model.onnx  + model.bin
#
# Prereqs: adb on PATH, phone connected + USB-debugging on, the app installed once.
# Usage:   ./push_stt_model.sh
set -euo pipefail

PKG="com.sankatmochan.mesh"
ART="$(cd "$(dirname "$0")/../../backend/aihub_out/artifacts/indic_ctc_precompiled" && pwd)"
DEST="/sdcard/Android/data/${PKG}/files/stt"
VENV_PY="$(cd "$(dirname "$0")/../../backend" && pwd)/.venv/bin/python"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

push_graph() {
  local name="$1"                       # encoder | ctc_decoder
  local zip
  zip="$(ls "$ART/$name"/*.onnx.zip 2>/dev/null | head -1 || true)"
  if [[ -z "$zip" ]]; then
    echo "!! missing artifact for '$name' in $ART/$name — run backend/scripts/aihub_precompiled_stt.py first"
    exit 1
  fi
  echo "→ $name: extracting $(basename "$zip")"
  rm -rf "$TMP/$name"; mkdir -p "$TMP/$name"
  unzip -qo "$zip" -d "$TMP/$name"
  # The zip holds a single job_*_optimized_onnx/ folder with model.onnx + model.bin.
  local onnx bin
  onnx="$(find "$TMP/$name" -name model.onnx | head -1)"
  bin="$(find "$TMP/$name" -name model.bin | head -1)"
  if [[ -z "$onnx" || -z "$bin" ]]; then echo "!! model.onnx/model.bin not found for $name"; exit 1; fi
  # AI Hub emits the EPContext wrapper at ONNX IR v13; downgrade to 10 (its ops are IR-10 safe) so
  # onnxruntime-android accepts it. Uses the backend venv's onnx.
  "$VENV_PY" - "$onnx" <<'PY'
import sys, onnx
m = onnx.load(sys.argv[1], load_external_data=False)
if m.ir_version > 10:
    m.ir_version = 10
    onnx.save(m, sys.argv[1])
PY
  # The app must have created $DEST/$name (app-OWNED) first — open the assistant screen once (the
  # SttEngine ctor mkdirs them). Dirs created by `adb shell mkdir` are shell-owned and the app
  # can't read files inside them, so we require the app-created dir and only push files into it.
  if ! adb shell "[ -d '$DEST/$name' ]"; then
    echo "!! $DEST/$name missing. Open the assistant screen once (creates app-owned dirs), then re-run."
    exit 1
  fi
  echo "→ $name: pushing to $DEST/$name/"
  adb push "$onnx" "$DEST/$name/model.onnx"
  adb push "$bin"  "$DEST/$name/model.bin"
}

echo "Device: $(adb get-serialno 2>/dev/null || echo 'NONE — connect the OnePlus 15')"
push_graph "ctc_decoder"
push_graph "encoder"
echo "✓ STT model installed. Relaunch the assistant; the mic button appears once files are present."
