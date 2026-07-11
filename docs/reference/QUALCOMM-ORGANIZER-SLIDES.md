# Qualcomm Organizer Slides — extracted reference

> Source: official organizer presentation slides shown at the Snapdragon Multiverse Hackathon (Bengaluru, 11–12 Jul 2026). Transcribed from screenshots on 10 Jul 2026. This is the sponsor's *recommended* tooling — align our stack to it where sensible, it signals we followed their guidance.

---

## 1. Qualcomm AI Hub — three pillars

*"Ship intelligent experiences across devices with Qualcomm AI Hub."*

| Pillar | What it does | Headline |
|---|---|---|
| **AI Hub Models** | Explore a gallery of models + metrics, tested and ready to run on device. | **300+ pre-optimized models** |
| **AI Hub Workbench** | Optimize your own model, run inference on hosted devices, iterate on performance. | **Compile, quantize, validate and profile** your model |
| **AI Hub Apps** | Leverage sample app code to match model performance on Qualcomm SoCs. | Sample apps to bring your model **on-device** |

> Directly relevant to our P0: Workbench = the cloud compile + profile path (no X Elite / OnePlus 15 in hand needed). 300+ models = check if Qwen3 / Whisper are already pre-optimized before compiling from scratch.

---

## 2. "Any model. Any framework. Any runtime. Any OS."

Supported frameworks feeding into **Qualcomm® AI Engine Direct**:
- TensorFlow
- PyTorch
- ONNX
- ONNX Runtime
- LiteRT
- LLaMA.cpp

Tagline: **"Within 5 minutes, with a few lines of code."**

---

## 3. QAIRT Workflow (the on-device compile pipeline)

```
ONNX  (model + graph)
  ↓
QAIRT — INT8 Model Quantization
  ↓
QNN — Model Conversion
  ↓
Context BIN — QNN Context Binary   ← the device-specific artifact that runs on the NPU
```

> This is exactly the artifact chain behind our `.bin` files. The "Context BIN is device-specific" line in PLAN.md §6 is confirmed here — compile separately per target (X Elite AND 8 Elite Gen 5).

---

## 4. Suggested Software Stack (Qualcomm's recommendation)

### Computer (AI PC — Snapdragon X Elite)
- **Frontend:** Streamlit (Python) **or** JS/TS w/ Electron
- **Backend:** Python (use **x64 Python** for QNN access)
- **ML Runtime:** **ONNXRuntime-QNN** — note: use the `onnxruntime-qnn` package
- **Tools:** Llama.cpp

### Phones
- **Frontend/Backend:** Kotlin
- **ML Runtime:** **Onnxruntime-Android**, LiteRT, ExecuTorch
- **Dev Tools:** Android SDK, Llama.cpp
- **IDE:** Android Studio

### IoT (Arduino UNO Q)
- **Platform:** Arduino UnoQ
- **IDE:** App Lab
- **Tooling:** EdgeImpulse

> **Validation of our plan:** our PLAN.md already picks ORT + QNN-EP as the primary runtime on both targets — this slide confirms Qualcomm recommends the same (`onnxruntime-qnn` on PC, `onnxruntime-android` on phone). Our React dashboard is an alternative to their Streamlit/Electron suggestion — fine, but be ready to justify. IoT note: **App Lab + EdgeImpulse** for the UNO Q — we haven't touched EdgeImpulse; worth a look for the sensor/auto-alert path (Isha).

---

## 5. Resources — official links

| Resource | Link |
|---|---|
| Qualcomm Developer Homepage | https://qualcomm.com/developer |
| Qualcomm AI Developer Workflow Docs | https://docs.qualcomm.com/bundle/publicresource/topics/80-62010-1/welcome.html?product=1601111740057789 |
| Qualcomm AI Hub | https://aihub.qualcomm.com |
| NPU Chatbot w/ AnythingLLM (repo) | https://github.com/thatrandomfrenchdude/simple-npu-chatbot |
| Local Agent w/ LM Studio (repo) | https://github.com/thatrandomfrenchdude/local-agent |
| Live Transcription with Whisper + AI Hub | https://github.com/thatrandomfrenchdude/simple-whisper-transcription |
| Pose Detection with HRPoseNet + AI Hub | https://github.com/quic/Pose-Detection-with-HRPoseNet |
| Executable Packaging Guide | https://github.com/carrycooldude/onnx-msix-samples |
| Qualcomm Hackathon Projects (awesome list) | https://qualcomm.github.io/awesome-qualcomm-developer/ |

> High-value for us:
> - **simple-whisper-transcription** — reference impl for our Whisper STT on the NPU via AI Hub. Directly reusable for the voice-SOS pipeline.
> - **simple-npu-chatbot (AnythingLLM)** — our documented AI-PC fallback ladder (ORT-genai → AnythingLLM). Sample code to lean on.
> - **onnx-msix-samples** — packaging the command post as a runnable Windows executable = helps the *Deployment & Accessibility* score (20 pts).
> - **awesome-qualcomm-developer** — scan for anything else pre-built we can stand on.

---

## 6. Event Schedule — Day 2 (Sun 12 Jul 2026)

| Time | Item |
|---|---|
| 7:00 AM – 9:00 AM | Breakfast |
| 12:00 PM – 1:00 PM | Lunch |
| **1:00 PM** | **Application submission deadline** |
| **1:00 PM – 4:00 PM** | **Team demonstrations** |
| 4:00 PM – 4:15 PM | Break |
| 4:15 PM – 4:30 PM | Judging & finalization of winners |
| 4:30 PM – 5:00 PM | Felicitation ceremony |
| 5:00 PM – 7:00 PM | Social reception on campus |
| 7:00 PM onwards | Event close & wrap-up |

> **Hard gate:** repo + Microsoft Form submitted by **1:00 PM Sunday**. Demos are the 1–4 PM window — the 3-min rehearsed demo has to be airtight by 1 PM. Build like the deadline is 1 PM, not 7 PM (matches PLAN/hackathon-info).

---

### Takeaways worth acting on
1. **P0 unchanged and confirmed:** AI Hub Workbench does cloud compile + profile → real NPU numbers without the hardware in hand. Check the 300+ model gallery first (Qwen3/Whisper may be pre-done).
2. **Our runtime choice is Qualcomm-endorsed:** `onnxruntime-qnn` (PC) / `onnxruntime-android` (phone). Say this out loud to judges.
3. **Steal the reference repos:** `simple-whisper-transcription` for STT, `simple-npu-chatbot` for the AnythingLLM fallback, `onnx-msix-samples` for packaging.
4. **IoT gap:** we've not used App Lab / EdgeImpulse for the UNO Q — the sponsor expects that path for the board's sensing/auto-alert story.
5. **Submission is 1 PM Sunday, demos 1–4 PM.** Freeze features earlier than that.
