# On-device STT (IndicConformer CTC on the Hexagon NPU)

This package runs speech-to-text **on the OnePlus 15** (Snapdragon 8 Elite Gen 5), fully
offline. It is the "AI mobile" node's local transcription path — cheap relay phones stay dumb.

## Pipeline

```
mic → PCM 16 kHz → MelFrontend (1,80,1501) → encoder.onnx  (QNN/NPU) → (1,1024,188)
                                            → ctc_decoder.onnx (QNN/NPU) → (1,188,5633)
                                            → CtcDecoder (CPU) → native-script text
```

- **SttEngine** — ORT-QNN wrapper (mirrors `chat/GenieXEngine`). Owns the two NPU sessions + IO.
- **MelFrontend** — log-mel features. ⚠️ parity-critical (see below).
- **CtcDecoder** — greedy CTC decode, ported 1:1 from the model's `model_onnx.py`. Correct + cheap.

## Status: wired end-to-end in code; needs on-device verification

Done: ORT-QNN wrapper (`SttEngine`), mic capture (`PcmVoiceRecorder`), CTC decode (`CtcDecoder`),
mel front-end (`MelFrontend`), and the chatbot voice button (`ui/ChatScreen` + `chat/ChatViewModel`)
— voice → transcribe → the same `send()` the keyboard uses → LLM reply. `vocab.json` +
`language_masks.json` ship in `assets/stt/`. Depends on `onnxruntime-android-qnn:1.22.0`.

Remaining before it actually transcribes on the phone:

### 1. Install the model (side-loaded — it's ~1.2 GB, not in the APK)
```
# on the Mac, in command-post/ — reuses the cached uploads, produces precompiled_qnn_onnx:
python aihub_precompiled_stt.py         # → aihub_out/artifacts/indic_ctc_precompiled/{encoder,ctc_decoder}/*.zip
# then, with the OnePlus 15 connected over adb + app installed once:
mesh-app/tools/push_stt_model.sh        # extracts + pushes model.onnx/model.bin per graph
```
This lands the files at `files/stt/{encoder,ctc_decoder}/model.{onnx,bin}`. The mic button
appears automatically once `SttEngine.modelsInstalled()` sees them (checked on screen open).

> Why side-loaded not bundled: the float encoder context binary is ~1.2 GB. Quantizing to W8A16
> (AIMET, Linux/WSL only) would cut it ~4× — the real ship-time optimization.
> Why `precompiled_qnn_onnx` not the bare `.bin`: it wraps the QNN context binary in a small
> ONNX EPContext graph that ORT-QNN loads directly; the `.onnx` references its `.bin` by relative
> name, so each graph lives in its own folder and both files keep their names.

### 2. QAIRT coexistence with GenieX (real risk)
The APK already ships QAIRT/QNN native libs via `com.qualcomm.qti:geniex-android`. The
ORT-QNN AAR also carries QNN libs. Two QAIRT versions in one process can clash. Confirm on
device that `libQnnHtp.so` loads for ORT; if it clashes, align both to one QAIRT version or
point ORT's `backend_path` at the single shipped copy. Until confirmed, test STT in isolation
(a debug build without the assistant loaded).

### 3. Verify tensor IO on-device
Names assumed: encoder `audio_signal`,`length` → `outputs`; ctc `encoder_output` → `logprobs`.
`--truncate_64bit_io` means `length` may present as int32 at the QNN boundary — adjust the
`LongBuffer` feed if ORT reports a dtype mismatch.

### 4. MelFrontend parity gate — DONE (verified)
The encoder was trained on NeMo features; a mismatched mel collapses accuracy. `MelFrontend` is
a bit-for-bit port of `preprocessor.ts`, using the model's REAL window512 + mel filterbank
(`assets/stt/mel_window512.f32`, `mel_fb.f32`, extracted by `command-post/dump_mel_golden.py`).
Python reconstruction matched the scripted preprocessor to ~8e-5; `androidTest/MelParityTest`
re-checks the Kotlin against golden vectors on-device (`./gradlew connectedDebugAndroidTest`).

### 5. Language ID — DONE (no separate model)
IndicConformer doesn't auto-detect, but its encoder is language-agnostic, so `CtcDecoder.pickLanguage`
scores each language's confidence straight from the CTC logits and picks the best — **100% on FLEURS
(10/10, open 22-language set), beating a VoxLingua107 SLID (90%) at zero extra latency.** The voice
button uses this (auto); `voiceLang` can force a language. (So the planned VoxLingua107 graph is
unnecessary.)

### 6. Capture wiring — DONE
`PcmVoiceRecorder` (AudioRecord, 16 kHz mono PCM) feeds `SttEngine.transcribe(pcm)`. The mesh
`VoiceRecorder` (AMR) is untouched — different job (bytes-over-mesh vs local model fidelity).

## Translation (native language → English)
Not this package's job — the ASR model only transcribes. The phone already runs an on-device
LLM (`chat/GenieXEngine`, NPU); reuse it with a translation prompt to turn the native-script
transcript into English locally. (The command post also does this in `command-post/triage.py`.)
Optional upgrade: a dedicated IndicTrans2 (MIT) MT graph if the small LLM's translation drifts.
