"""
Recompile IndicConformer CTC as precompiled_qnn_onnx (ORT-QNN loadable) and download.

Same uploaded models as before (cached by hash — no re-upload), but target_runtime
= precompiled_qnn_onnx: each graph becomes a small .onnx EPContext wrapper + a QNN
context .bin that ONNX Runtime's QNN EP loads directly on the phone. That's what the
Android mobile-application SttEngine consumes.

encoder keeps --truncate_64bit_io (its `length` input is int64).
"""
from __future__ import annotations

import json
from pathlib import Path

import qai_hub as hub

PKG = Path("aihub_out/indic_ctc_pkg")
ART = Path("aihub_out/artifacts/indic_ctc_precompiled")
OUT = Path("aihub_out/indic_ctc_precompiled_jobs.json")
DEVICE = hub.Device("Snapdragon 8 Elite Gen 5 QRD")
BASE = "--target_runtime precompiled_qnn_onnx --qairt_version=default"
ART.mkdir(parents=True, exist_ok=True)

GRAPHS = [
    ("ctc_decoder", {"encoder_output": ((1, 1024, 188), "float32")}, BASE),
    ("encoder", {"audio_signal": ((1, 80, 1501), "float32"), "length": ((1,), "int64")},
     BASE + " --truncate_64bit_io"),
]


def main():
    jobs = {}
    for name, specs, opts in GRAPHS:
        print(f"→ compile {name} (precompiled_qnn_onnx) → {DEVICE.name}", flush=True)
        j = hub.submit_compile_job(
            model=str(PKG / f"{name}.onnx"), device=DEVICE,
            name=f"indic_{name}-sd8eg5-precompiled", input_specs=specs, options=opts,
        )
        print(f"   {j.job_id}  {j.url}", flush=True)
        j.wait()
        st = j.get_status()
        if not st.success:
            print(f"   FAILED: {st.message}", flush=True)
            jobs[name] = {"job_id": j.job_id, "compiled": False, "message": st.message}
            continue
        # Download the target model into ART; the API names the file itself and returns the path.
        graph_dir = ART / name
        graph_dir.mkdir(parents=True, exist_ok=True)
        try:
            saved = j.download_target_model(str(graph_dir))
        except Exception as e:  # noqa: BLE001 — don't let one graph kill the other
            print(f"   download error: {type(e).__name__}: {e}", flush=True)
            jobs[name] = {"job_id": j.job_id, "compiled": True, "downloaded": False}
            continue
        saved_path = saved if isinstance(saved, str) else str(saved)
        try:
            sz = Path(saved_path).stat().st_size / 1e6
        except Exception:
            sz = -1
        print(f"   ✓ downloaded {saved_path} ({sz:.1f} MB)", flush=True)
        jobs[name] = {"job_id": j.job_id, "compiled": True, "artifact": saved_path}

    OUT.write_text(json.dumps(jobs, indent=2))
    print(f"\n✓ {OUT}")


if __name__ == "__main__":
    main()
