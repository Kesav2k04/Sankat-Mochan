"""
Resubmit the IndicConformer CTC compile jobs with the CORRECT packaging.

First attempt passed the bare .onnx file, so qai-hub uploaded only the graph
proto (42 MB / 746 B) and dropped the sibling .data — the compile would fail on
missing weights. Per AI Hub docs, an ONNX with external data must be a DIRECTORY
named `<model>.onnx` containing `<model>.onnx` + `<model>.onnx.data`, and you
pass the DIRECTORY path.

The 2.4 GB .data is already staged (aihub_out/indic_ctc_stage) — we just move the
files into .onnx directories, no reload.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import qai_hub as hub

STAGE = Path(__file__).parents[1] / "aihub_out" / "indic_ctc_stage"
PKG = Path(__file__).parents[1] / "aihub_out" / "indic_ctc_pkg"
OUT = Path(__file__).parents[1] / "aihub_out" / "indic_ctc_jobs.json"
DEVICE = hub.Device("Snapdragon 8 Elite Gen 5 QRD")  # OnePlus 15 chip
# qnn_context_binary = SOC-specific NPU deployment (the fully-NPU-resident target).
# --qairt_version only applies to a QNN runtime, hence the earlier failure with no
# target_runtime (it defaulted to TFLite). Upload is cached by hash → no 2.4 GB re-upload.
OPTS = "--target_runtime qnn_context_binary --qairt_version=default"

ENC_SPECS = {"audio_signal": ((1, 80, 1501), "float32"), "length": ((1,), "int64")}
CTC_SPECS = {"encoder_output": ((1, 1024, 188), "float32")}


def package(name: str) -> Path:
    """Move staged <name>.onnx + <name>.onnx.data into a <name>.onnx/ directory."""
    d = PKG / f"{name}.onnx"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copy(STAGE / f"{name}.onnx", d / f"{name}.onnx")
    shutil.copy(STAGE / f"{name}.onnx.data", d / f"{name}.onnx.data")
    return d


def main():
    enc_dir = package("encoder")
    ctc_dir = package("ctc_decoder")
    print(f"packaged:\n  {enc_dir}\n  {ctc_dir}", flush=True)

    jobs = {}
    print(f"→ ctc_decoder compile → {DEVICE.name}", flush=True)
    j_ctc = hub.submit_compile_job(
        model=str(ctc_dir), device=DEVICE, name="indic_ctc_decoder-sd8eg5",
        input_specs=CTC_SPECS, options=OPTS,
    )
    jobs["ctc_decoder"] = {"job_id": j_ctc.job_id, "url": j_ctc.url}
    print(f"   {j_ctc.job_id}  {j_ctc.url}", flush=True)

    print(f"→ encoder compile (2.4 GB upload) → {DEVICE.name}", flush=True)
    j_enc = hub.submit_compile_job(
        model=str(enc_dir), device=DEVICE, name="indic_encoder-sd8eg5",
        input_specs=ENC_SPECS, options=OPTS,
    )
    jobs["encoder"] = {"job_id": j_enc.job_id, "url": j_enc.url}
    print(f"   {j_enc.job_id}  {j_enc.url}", flush=True)

    OUT.write_text(json.dumps(jobs, indent=2))
    print(f"\n✓ resubmitted. {OUT}")


if __name__ == "__main__":
    main()
