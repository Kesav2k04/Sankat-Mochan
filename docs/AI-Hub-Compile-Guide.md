# Qualcomm AI Hub — Compile & Deploy Guide (Sankat-Mochan)

Knowledge transfer for compiling models on **Qualcomm AI Hub** and running them on-device
(Snapdragon 8 Elite Gen 5 phone = OnePlus 15, and Snapdragon X Elite command-post). Written from
the working IndicConformer STT deployment; the same recipe generalizes to other ONNX models and
to the X Elite (change one device string).

> TL;DR pipeline: **plain ONNX → package for AI Hub → `submit_compile_job` (QNN) → download
> context binary → deploy via ONNX Runtime QNN EP on-device.** The devil is entirely in a handful
> of version/packaging gotchas, all listed under "Gotchas" — read those first.

---

## 0. What we compiled and why

- **Model:** AI4Bharat **IndicConformer-600M** (MIT), CTC path. It ships pre-exported ONNX in its
  HF repo (`assets/encoder.onnx` + `assets/ctc_decoder.onnx` + `preprocessor.ts` + `vocab.json` +
  `language_masks.json`). We compile the two heavy graphs (encoder + ctc_decoder); mel
  preprocessing and CTC decode run in app code.
- **Target NPU:** Snapdragon 8 Elite Gen 5 (`SM8850`, Hexagon **V81**). Result: encoder 35.8 ms +
  ctc 0.47 ms, **100% on NPU**, ~36 ms/clip.
- **Runtime on-device:** ONNX Runtime with the **QNN Execution Provider** (`onnxruntime-android-qnn`).

## 1. Prerequisites

```bash
# Python env (we used command-post/.venv, Python 3.11)
pip install "qai-hub==0.52.0" onnx onnxruntime soundfile numpy
# One-time AI Hub auth — get the token from https://app.aihub.qualcomm.com/ (Account → Settings)
qai-hub configure --api_token <YOUR_TOKEN>     # writes ~/.qai_hub/client.ini
```

Verify: `python -c "import qai_hub as h; print(h.Device('Snapdragon 8 Elite Gen 5 QRD').name)"`

**Device strings** (from `aihub_out/devices.txt`; full list via the AI Hub web UI):
| Target | AI Hub device string |
|---|---|
| OnePlus 15 phone | `Snapdragon 8 Elite Gen 5 QRD` |
| (older phone) | `Snapdragon 8 Elite QRD` |
| **X Elite command-post PC** | `Snapdragon X Elite CRD` |
| (next-gen laptop) | `Snapdragon X2 Elite CRD` |

## 2. The compile pipeline (what the scripts do)

Scripts live in `command-post/`:
- `aihub_precompiled_stt.py` — compile both graphs as `precompiled_qnn_onnx` and download.
- `aihub_compile_stt.py` / `aihub_resubmit_stt.py` — earlier `qnn_context_binary` variants + the
  external-data packaging helper.
- `aihub_poll_profile.py` — wait for a compile job, profile on-device, download artifacts.

### 2a. Package an ONNX that uses external data
AI Hub needs a **directory named `<model>.onnx`** containing `<model>.onnx` + `<model>.onnx.data`
(the EPContext/weights reference is relative). If you pass the bare `.onnx` file, only the graph
uploads and the compile fails on missing weights. Consolidate scattered external tensors first:

```python
import onnx
m = onnx.load("assets/encoder.onnx", load_external_data=True)   # pulls all weight blobs
onnx.save(m, "stage/encoder.onnx", save_as_external_data=True,
          all_tensors_to_one_file=True, location="encoder.onnx.data")
# then submit the DIRECTORY that holds encoder.onnx + encoder.onnx.data
```

### 2b. Submit the compile job
```python
import qai_hub as hub
DEVICE = hub.Device("Snapdragon 8 Elite Gen 5 QRD")   # ← change for X Elite etc.
OPTS = "--target_runtime precompiled_qnn_onnx --qairt_version=default --truncate_64bit_io"
job = hub.submit_compile_job(
    model="stage/encoder.onnx",                       # dir path for external-data models
    device=DEVICE,
    input_specs={"audio_signal": ((1, 80, 1501), "float32"),
                 "length": ((1,), "int64")},          # STATIC shapes (AI Hub pins the dynamic axes)
    options=OPTS,
)
job.wait()
job.download_target_model("out/encoder")              # writes a .zip (model.onnx + model.bin)
```

- `--target_runtime`: use **`precompiled_qnn_onnx`** for ORT-QNN on-device (a small EPContext
  `.onnx` wrapping a QNN context `.bin`). `qnn_context_binary` gives the bare `.bin` (needs the raw
  QNN API). `qnn_dlc` is portable across QAIRT versions (JIT-compiled on device) — use if you hit
  context-binary version mismatches.
- **Static input specs are required** — pick a fixed window (we used 15 s → 1501 mel frames) and
  pad shorter audio in app code; pass the real valid length so the encoder masks the pad.
- Derive exact static shapes empirically by running the preprocessor once (see
  `command-post/dump_mel_golden.py`).

### 2c. Profile + download
```python
pj = hub.submit_profile_job(model=job.get_target_model(), device=DEVICE, options=OPTS)
pj.wait(); prof = pj.download_profile()
# prof["execution_summary"]["estimated_inference_time"] (µs), ["inference_memory_peak_range"],
# and per-layer compute_unit (want all "NPU", zero CPU/GPU fallback).
```

## 3. Gotchas (every one of these cost real time — READ THIS)

| # | Symptom | Fix |
|---|---|---|
| G1 | Compile dies instantly: `QAIRT version 2.43 is not supported` | qai-hub-models pins 2.43; Workbench needs ≥2.45. Add `--qairt_version=default` (=2.45) to compile **and** profile options. |
| G2 | Compile fails: only tiny graph uploaded, missing weights | External-data ONNX must be a **`<model>.onnx` directory** (`.onnx` + `.onnx.data` inside), not the bare file. See 2a. |
| G3 | `QAIRT SDK version is not applicable to selected runtime` | You set `--qairt_version` without a QNN runtime. Add `--target_runtime qnn_context_binary` (or `precompiled_qnn_onnx`). |
| G4 | `Must use --truncate_64bit_io when input tensors have type int64` | The graph has an int64 input (`length`). Add `--truncate_64bit_io`. This makes that IO **int32** on-device — feed int32 from the app (see G7). |
| G5 | Big fp32 encoder = ~1.2 GB context binary (or 2.4 GB raw) | Too big for the APK → **side-load** it (adb push / download at runtime). Quantize to **W8A16** (~4× smaller) with AIMET — but AIMET-ONNX is **Linux/WSL only**, not macOS. |
| S3.5 | Two big models won't fit the NPU | A Hexagon session caps **~3.5 GB** and maps to one HTP device. Don't co-locate two large NPU models (see the crash notes in the repo). |

## 4. On-device deployment (Android / ORT-QNN) — gotchas

| # | Symptom | Fix |
|---|---|---|
| G6a | `Unsupported model IR version: 13, max supported IR version: 10` | AI Hub emits the EPContext wrapper at IR 13; `onnxruntime-android` accepts ≤10. Downgrade: `m=onnx.load(f); m.ir_version=10; onnx.save(m,f)` (its ops are IR-10 safe). |
| G6b | `EPContext node ... NOT_IMPLEMENTED` | QNN EP not active. Add it: `sessionOptions.addQnn(mapOf("backend_path" to "libQnnHtp.so", "htp_performance_mode" to "burst", "qnn_context_priority" to "high"))`. |
| G6c | `QNN_DEVICE_ERROR_INVALID_CONFIG` + missing `libQnnHtpV81Skel.so` | Your ORT-QNN is too old for the SoC. **`onnxruntime-android-qnn:1.22` (QAIRT 2.33) does NOT support SM8850/V81.** Use **1.27.0** (QAIRT 2.42) or newer. |
| G6d | Gradle: `2 files found with path .../libQnnHtp.so` | Two AARs ship QNN libs (e.g. GenieX + ORT-QNN). `packaging { jniLibs.pickFirsts += listOf("**/libQnn*.so","**/libHexagon*.so") }` (first-declared dep wins — order it to the version matching your context binary). |
| G7 | `Unexpected input data type. Actual: tensor(int64), expected: tensor(int32)` | After `--truncate_64bit_io`, feed `length` (and read `encoded_lengths`) as **int32** (`IntBuffer`, not `LongBuffer`). |
| G8 | `IllegalStateException: missing output 'outputs'` | AI-Hub wrappers **rename outputs** to `output_0`, `output_1` (inputs keep names). Encoder: `output_0`=features, `output_1`=encoded_lengths; ctc: `output_0`=logprobs. |
| G9 | `OrtSession.Result.get(name)` cast crash | It returns `Optional<OnnxValue>`, not `OnnxValue`: `res.get(name).orElseThrow() as OnnxTensor`. |
| G10 | Side-loaded model unreadable (`Permission denied`) | Dirs created by `adb shell mkdir` are `shell`-owned; the app can't traverse them. The **app** must create the dirs (owned by its UID), then `adb push` files in. `adb install -r` preserves them; a full uninstall wipes them. |

**ORT-QNN dependency (Android):** `implementation("com.microsoft.onnxruntime:onnxruntime-android-qnn:1.27.0")`
**Session load:** load from a file **path** (not bytes) so the EPContext `.bin` resolves relative
to the `.onnx`; keep both in the same folder.

## 5. Deploying the model files
`mesh-app/tools/push_stt_model.sh` — extracts the AI Hub zips, downgrades IR to 10, and
`adb push`es `model.onnx`+`model.bin` per graph into the **app-created** external dir
(`Android/data/<pkg>/files/stt/<graph>/`). Open the app once first so `SttEngine`'s ctor creates
the (app-owned) dirs.

## 6. Extending this

- **Compile for the X Elite command-post:** change `DEVICE = hub.Device("Snapdragon X Elite CRD")`.
  Everything else is identical. On Windows-on-ARM run it via ORT-QNN or onnxruntime-genai/QNN.
  (The command-post already does STT on CPU fine, so NPU there is a nice-to-have.)
- **LLMs (e.g. Gemma 4 4B) via AI Hub:** a *different* path — AI Hub exports LLMs to the **Genie /
  QAIRT** runtime (W4A16), not ONNX. Caveat: the export loads the full FP checkpoint **locally**
  and OOMs on a laptop (3B wanted ~80 GB RAM+swap) — **compile LLMs on a big-RAM Linux box or the
  X Elite**, not a Mac. Use Qualcomm's published perf numbers (`qai_hub_models/models/<m>/perf.yaml`)
  for the deck if you can't re-profile. NOTE: the phone app currently runs Gemma via **GenieX**
  (llama.cpp `ggml-hexagon`, GGUF) — a separate, experimental runtime; the Genie path is more
  mature and worth evaluating if GenieX proves unstable.

## 7. Reference links
- AI Hub docs: https://workbench.aihub.qualcomm.com/docs/ (compile_examples.html, api.html)
- QNN EP (ONNX Runtime): https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html
- IndicConformer: https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual
- GenieX chat reference app: github.com/qualcomm/ai-hub-apps → `apps/geniex_chat_android`
- `qai-hub` 0.52.0, `qai-hub-models` 0.48.0; prior profiling in `command-post/aihub_out/RESULTS.md`
