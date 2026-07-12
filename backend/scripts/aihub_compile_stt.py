"""
Compile IndicConformer (CTC path) for the phone NPU via Qualcomm AI Hub.

Our chosen STT (benchmark winner) is AI4Bharat IndicConformer, CTC decoding.
The CTC path is pure feed-forward — NO RNN-T autoregressive loop — so it maps
cleanly to the Hexagon NPU. Two graphs do the heavy lifting:

    encoder.onnx      (1,80,1501)+(1,)  -> (1,1024,188)   ~2.4 GB fp32 (the model)
    ctc_decoder.onnx  (1,1024,188)      -> (1,188,5633)    23 MB (vocab projection)

Preprocessor (mel) + argmax/collapse/vocab stay on CPU (trivial).

Static shapes derived empirically from a 15 s window (see chat notes):
most SOS clips are far shorter; we pad to 15 s.

Target: Snapdragon 8 Elite Gen 5 QRD  ==  the OnePlus 15's chip.
Gotcha (from aihub_out/RESULTS.md): qai-hub-models pins QAIRT 2.43 but Workbench
needs 2.45+, so every job passes --qairt_version=default.

Run:  python aihub_compile_stt.py           # submits both compile jobs (async)
Writes job ids/urls to aihub_out/indic_ctc_jobs.json for the poller.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import onnx
import qai_hub as hub

SNAP = Path(
    os.path.expanduser(
        "~/.cache/huggingface/hub/models--ai4bharat--indic-conformer-600m-multilingual/"
        "snapshots/e9b71b369c048e2c6b634d4c131061c34e441179"
    )
)
ASSETS = SNAP / "assets"
STAGE = Path(__file__).parents[1] / "aihub_out" / "indic_ctc_stage"
OUT = Path(__file__).parents[1] / "aihub_out" / "indic_ctc_jobs.json"
DEVICE = hub.Device("Snapdragon 8 Elite Gen 5 QRD")  # OnePlus 15 chip
OPTS = "--qairt_version=default"  # RESULTS.md gotcha A

# Static input specs (15 s window). AI Hub pins the dynamic axes to these.
ENC_SPECS = {"audio_signal": ((1, 80, 1501), "float32"), "length": ((1,), "int64")}
CTC_SPECS = {"encoder_output": ((1, 1024, 188), "float32")}


def consolidate(src_name: str, dst_dir: Path) -> Path:
    """Load an ONNX (external data resolved from ASSETS) and re-save with all
    weights in ONE sibling .data file — a clean 2-file package for upload."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src_name
    model = onnx.load(str(ASSETS / src_name), load_external_data=True)  # pulls the ~350 blobs
    onnx.save(
        model, str(dst),
        save_as_external_data=True, all_tensors_to_one_file=True,
        location=f"{src_name}.data",
    )
    return dst


def main():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    print("→ consolidating encoder.onnx (2.4 GB — this loads all weights into RAM)…", flush=True)
    enc_path = consolidate("encoder.onnx", STAGE)
    print(f"   staged {enc_path} ({enc_path.stat().st_size / 1e6:.1f} MB graph + .data)", flush=True)
    print("→ consolidating ctc_decoder.onnx…", flush=True)
    ctc_path = consolidate("ctc_decoder.onnx", STAGE)

    jobs = {}
    print(f"→ submitting CTC-decoder compile → {DEVICE.name} …", flush=True)
    j_ctc = hub.submit_compile_job(
        model=str(ctc_path), device=DEVICE, name="indic_ctc_decoder-sd8eg5",
        input_specs=CTC_SPECS, options=OPTS,
    )
    jobs["ctc_decoder"] = {"job_id": j_ctc.job_id, "url": j_ctc.url}
    print(f"   ctc_decoder job {j_ctc.job_id}  {j_ctc.url}", flush=True)

    print(f"→ submitting ENCODER compile (2.4 GB upload) → {DEVICE.name} …", flush=True)
    j_enc = hub.submit_compile_job(
        model=str(enc_path), device=DEVICE, name="indic_encoder-sd8eg5",
        input_specs=ENC_SPECS, options=OPTS,
    )
    jobs["encoder"] = {"job_id": j_enc.job_id, "url": j_enc.url}
    print(f"   encoder job {j_enc.job_id}  {j_enc.url}", flush=True)

    OUT.write_text(json.dumps(jobs, indent=2))
    print(f"\n✓ submitted. job ids → {OUT}")


if __name__ == "__main__":
    main()
