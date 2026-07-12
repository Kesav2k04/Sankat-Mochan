"""
Wait for the IndicConformer CTC compile jobs, then profile them on the phone NPU
and download the compiled QNN artifacts.

Reads job ids from aihub_out/indic_ctc_jobs.json (written by aihub_resubmit_stt.py).
For each compiled graph: wait → report status → submit a profile job on
Snapdragon 8 Elite Gen 5 QRD → print NPU latency / memory / compute-unit split
(the numbers for the deck) → download the .bin QNN context binary.
"""
from __future__ import annotations

import json
from pathlib import Path

import qai_hub as hub

BASE = Path(__file__).parent / "aihub_out"
JOBS = json.loads((BASE / "indic_ctc_jobs.json").read_text())
ART = BASE / "artifacts" / "indic_ctc_sd8eg5"
DEVICE = hub.Device("Snapdragon 8 Elite Gen 5 QRD")
OPTS = "--qairt_version=default"
ART.mkdir(parents=True, exist_ok=True)


def profile(tag: str, compile_job_id: str) -> dict:
    cj = hub.get_job(compile_job_id)
    print(f"\n=== {tag} · compile {compile_job_id} ===", flush=True)
    cj.wait()
    st = cj.get_status()
    print(f"compile status: {st.code} {'(success)' if st.success else st.message}", flush=True)
    if not st.success:
        cj.download_job_logs(str(ART / f"{tag}_compile_fail.log"))
        return {"tag": tag, "compiled": False, "message": st.message}

    target = cj.get_target_model()
    dst = ART / f"{tag}.bin"
    try:
        cj.download_target_model(str(dst))
        art = str(dst)
    except Exception as e:  # download is best-effort; profiling is the point
        art = f"(download skipped: {type(e).__name__})"

    pj = hub.submit_profile_job(model=target, device=DEVICE, name=f"{tag}-profile", options=OPTS)
    print(f"profile job {pj.job_id}  {pj.url}", flush=True)
    pj.wait()
    pst = pj.get_status()
    if not pst.success:
        print(f"profile FAILED: {pst.message}", flush=True)
        return {"tag": tag, "compiled": True, "profiled": False, "artifact": art}

    prof = pj.download_profile()
    ex = prof["execution_summary"]
    lat_us = ex.get("estimated_inference_time", 0)
    peak = ex.get("inference_memory_peak_range", [0, 0])
    layers = prof.get("execution_detail", [])
    units = {}
    for ld in layers:
        u = ld.get("compute_unit", "?")
        units[u] = units.get(u, 0) + 1
    print(f"  inference: {lat_us / 1000:.2f} ms   peak mem: {peak}   ops-by-unit: {units}", flush=True)
    return {
        "tag": tag, "compiled": True, "profiled": True, "artifact": art,
        "latency_ms": round(lat_us / 1000, 2), "peak_mem_bytes": peak,
        "ops_by_unit": units, "profile_job": pj.job_id,
    }


def main():
    results = []
    for tag in ("ctc_decoder", "encoder"):
        if tag in JOBS:
            results.append(profile(tag, JOBS[tag]["job_id"]))
    (BASE / "indic_ctc_profile.json").write_text(json.dumps(results, indent=2))

    print("\n" + "#" * 70 + "\nPHONE-NPU SUMMARY (Snapdragon 8 Elite Gen 5 = OnePlus 15)\n" + "#" * 70)
    total = 0.0
    for r in results:
        if r.get("profiled"):
            total += r["latency_ms"]
            print(f"  {r['tag']:<14} {r['latency_ms']:>8.2f} ms   {r['ops_by_unit']}")
        else:
            print(f"  {r['tag']:<14} not profiled ({r.get('message', 'see logs')})")
    if total:
        print(f"  {'TOTAL (enc+ctc)':<14} {total:>8.2f} ms/clip on NPU")


if __name__ == "__main__":
    main()
