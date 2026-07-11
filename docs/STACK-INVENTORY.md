# Sankat-Mochan — Full Stack Inventory

A complete catalog of every library, technology, device, hardware component, and AI model
used across the project, grouped by the four sub-systems:

- **`mesh-app/`** — native Android (Kotlin) BLE mesh app
- **`command-post/`** — offline AI command post (FastAPI backend + React dashboard)
- **`pi-code/`** — Raspberry Pi LoRa ↔ BLE gateway
- **`finetune/`** — Sahayak on-device model fine-tuning
- **`sim/` & `deck/`** — flow simulator and pitch deck

> Sourced from `build.gradle.kts`, `requirements.txt`, `package.json`, config files, and code.
> License notes reflect CLAUDE.md rule #1 (MIT / Apache-2.0 / BSD only; non-OSI deps flagged).

---

## 1. Software Libraries & Frameworks

### 1.1 Android mesh app (`mesh-app/` — Kotlin)
| Library | Version | License | Purpose |
| --- | --- | --- | --- |
| Kotlin (Android + Compose plugins) | 2.0.20 | Apache-2.0 | Language |
| Android Gradle Plugin | 8.5.2 | Apache-2.0 | Build |
| Jetpack Compose (BOM) | 2024.09.03 | Apache-2.0 | UI toolkit (ui, foundation, material3, material-icons-extended, tooling) |
| androidx.activity:activity-compose | 1.9.2 | Apache-2.0 | Compose activity host |
| androidx.core:core-ktx | 1.13.1 | Apache-2.0 | Core KTX |
| androidx.lifecycle (runtime-ktx, viewmodel-compose) | 2.8.6 | Apache-2.0 | Lifecycle / ViewModel |
| kotlinx-coroutines-android | 1.8.1 | Apache-2.0 | Concurrency |
| kotlinx-serialization-json | 1.6.3 | Apache-2.0 | JSON (GenieX data beans) |
| osmdroid-android | 6.1.20 | Apache-2.0 | Offline map rendering (local tiles only) |
| **GenieX Android SDK** (`com.qualcomm.qti:geniex-android`) | 0.3.5 | BSD-3-Clause | On-device LLM runtime (Snapdragon NPU/GPU/CPU) |
| **play-services-location** (`com.google.android.gms`) | 21.3.0 | ⚠️ Proprietary (Google APIs ToS) | One-tap "turn on GPS" dialog only — flagged per CLAUDE.md #1 |

### 1.2 Command post — backend (`command-post/` — Python)
| Library | Version | License | Purpose |
| --- | --- | --- | --- |
| FastAPI | 0.115.0 | MIT | Web/API framework |
| Uvicorn (standard) | 0.30.6 | BSD | ASGI server |
| httpx | 0.27.2 | BSD | OpenAI-compatible LLM client |
| python-dotenv | 1.0.1 | BSD | Env/secret loading |
| python-multipart | 0.0.12 | BSD | Form/file uploads |
| NumPy | 2.1.1 | BSD-3 | Audio/array math |
| soundfile | 0.12.1 | BSD-3 | Audio I/O (bundles libsndfile) |
| websockets | 13.1 | BSD-3 | `/gateway` WebSocket for Pi uplink |
| asyncpg | 0.30.0 | Apache-2.0 | PostgreSQL session/audio persistence |
| pmtiles | 3.4.0 | BSD-3 | Offline basemap endpoint |
| transformers | (Hugging Face) | Apache-2.0 | IndicConformer STT loading |
| torch / torchaudio | (PyTorch) | BSD-3 | STT tensor ops / resampling |
| faster-whisper | (benchmark) | MIT | Whisper STT benchmark backend |
| onnxruntime-genai (+ `-qnn`) | (NPU server) | MIT | QNN/Hexagon NPU LLM inference shim |

### 1.3 Command post — dashboard (`command-post/web/` — React)
| Library | Version | License | Purpose |
| --- | --- | --- | --- |
| React / react-dom | 19.0.0 | MIT | UI |
| Vite | 7.0.0 | MIT | Build/dev server |
| @vitejs/plugin-react | 5.0.0 | MIT | React plugin |
| Tailwind CSS + @tailwindcss/vite | 4.0.0 | MIT | Styling |
| tw-animate-css | 1.4.0 | MIT | Animations |
| MapLibre GL JS | 5.0.0 | BSD-3 | Offline vector map rendering |
| @protomaps/basemaps | 5.7.2 | BSD | Basemap styles |
| pmtiles | 4.4.1 | BSD-3 | Tile archive reader |
| Radix UI (scroll-area, separator, slot, tooltip) | 1.x | MIT | Headless UI primitives |
| framer-motion | 12.0.0 | MIT | Animation |
| lucide-react | 1.24.0 | ISC | Icons |
| class-variance-authority / clsx / tailwind-merge | — | MIT | Class utilities |
| @fontsource/fraunces, @fontsource/ibm-plex-mono | 5.1.0 | OFL (fonts) | Bundled offline fonts |

### 1.4 Flow simulator (`sim/` — React)
React 19, react-dom, Vite 7, @vitejs/plugin-react, MapLibre GL 5.24, @protomaps/basemaps 5.7.2, pmtiles 4.4.1 — all MIT/BSD.

### 1.5 Raspberry Pi gateway (`pi-code/` — Python)
| Library | License | Purpose |
| --- | --- | --- |
| spidev | MIT | SPI access to SX127x radios |
| RPi.GPIO | MIT | GPIO (RST/DIO0 pins) |
| bleak | MIT | BLE central (phone ↔ Pi) |
| requests | Apache-2.0 | HTTP uplink to command post |
| websockets | BSD-3 | Uplink transport |

### 1.6 Fine-tuning (`finetune/` — Python)
| Library | Version range | License | Purpose |
| --- | --- | --- | --- |
| Unsloth | ≥2025.1,<2025.9 | Apache-2.0 | Fast QLoRA training (CUDA) |
| transformers | ≥4.44,<4.49 | Apache-2.0 | Model/trainer (CPU/MPS fallback) |
| datasets | ≥2.20,<3.3 | Apache-2.0 | Dataset loading |
| peft | ≥0.12,<0.15 | Apache-2.0 | LoRA adapters |
| trl | ≥0.9,<0.15 | Apache-2.0 | SFT trainer |
| accelerate | ≥0.33,<1.4 | Apache-2.0 | Device orchestration |
| bitsandbytes | (with Unsloth) | MIT | 4-bit QLoRA (CUDA-only) |
| torch | platform build | BSD-3 | Tensor backend |

---

## 2. AI / ML Models

### 2.1 Speech-to-Text (STT)
| Model | Where used | License | Notes |
| --- | --- | --- | --- |
| **AI4Bharat IndicConformer-600M (multilingual)** (`ai4bharat/indic-conformer-600m-multilingual`) | Command post `stt.py` / `indic_stt.py` | MIT | Primary STT — 22 Indian languages, CTC + RNNT modes, runs on CPU. ~6.8% CER |
| **Whisper** (tiny / base / small / medium / large) | STT benchmark (`stt_bench.py`, via faster-whisper) | MIT | Benchmark baseline; on-device Whisper for phone STT |
| VoxLingua107 LID | Planned (auto language-ID front-end) | — | Not yet integrated |

### 2.2 Large Language Models (triage / translate / assistant)
| Model | Where used | License | Notes |
| --- | --- | --- | --- |
| **Qwen3-4B** | NPU server (`npu_server.py`, onnxruntime-genai / QNN) | Apache-2.0 | On-device triage LLM on Snapdragon X Elite NPU |
| **Qwen2.5-3B-Instruct** (`qwen2.5:3b`, LM Studio/Ollama/vLLM) | Command post backend fallbacks (`backends.example.json`) | Apache-2.0 | OpenAI-compatible dev backends |
| **Gemma 4 E2B** (`google/gemma-4-E2B-it-qat-q4_0-gguf`) | Android on-device assistant (GenieX/llama.cpp), default | ⚠️ Gemma Terms of Use (non-OSI, HF-gated) | Q4_0 GGUF; flagged |
| **Gemma 4 E4B** (`google/gemma-4-E4B-it-qat-q4_0-gguf`) | Android on-device assistant | ⚠️ Gemma Terms of Use | Larger variant |
| **Gemma 3n E2B/E4B** (`unsloth/gemma-3n-E4B-it`) | Sahayak fine-tuning base | ⚠️ Gemma Terms of Use | QLoRA target |
| **IBM Granite 4.0 Micro** (`ibm-granite/granite-4.0-micro-GGUF`) | Android assistant fallback | Apache-2.0 | Permissive, non-gated |
| **Microsoft Phi-4-mini-instruct** (`bartowski/microsoft_Phi-4-mini-instruct-GGUF`) | Android assistant fallback | MIT | No sign-in needed |
| Llama 3 / Mistral / Phi-3 | Research/comparison docs only | various | Evaluated, not shipped |

---

## 3. Hardware, Devices & Components

### 3.1 Compute / edge devices
| Device | Role |
| --- | --- |
| **Snapdragon X Elite** (Surface Laptop / CRD, Windows-on-ARM) | AI command post — runs NPU LLM (Qwen3-4B) via QNN |
| **Qualcomm Hexagon NPU** | On-device inference accelerator (phone + X Elite) |
| **OnePlus 15** (arm64, Snapdragon) | Demo Android phone / mesh node |
| Android phones (min SDK 31 / Android 12, arm64-v8a) | Victim / Responder / Relay mesh nodes |
| **Raspberry Pi** | LoRa ↔ BLE gateway host |
| **Arduino UNO Q** | Field edge node (radio A migrates to it) |

### 3.2 Radio / RF components
| Component | Details |
| --- | --- |
| **Ra-02 LoRa module** (Ai-Thinker) | Two units — field radio A + gateway radio B |
| **Semtech SX1276 / SX1278** | LoRa transceiver chip on the Ra-02 (driver: `sx127x.py`) |
| LoRa RF link | 433 MHz ISM, SF7 (up to SF12), BW 125 kHz, CR 4/5, 5–20 dBm, sync word 0x12 |
| Antennas (433 MHz) | Required — never transmit without |
| **Bluetooth LE (BLE GATT)** | Phone ↔ phone and phone ↔ Pi transport |
| SPI bus + GPIO (RST/DIO0) | Pi ↔ radio wiring |

### 3.3 Sensors
| Sensor | Use |
| --- | --- |
| **WLS-1 water-level sensor** | Demo flood sensor cluster (rising-water corroboration) |
| Phone GPS / LocationManager | Victim geolocation |
| Accelerometer (shake detection) | Shake-to-SOS trigger (`ShakeSosService.kt`) |
| Microphone | Voice SOS capture |

---

## 4. Protocols, Formats & Platform Technologies
| Technology | Where |
| --- | --- |
| **BLE mesh** (GATT server + scanner, store-and-forward) | mesh-app |
| **LoRa** (custom ≤244-byte JSON envelope, CONTRACT 1) | pi-code / mesh |
| **CSMA/CA** channel access, dedup ring, hop forwarding | mesh transport |
| **WebSocket** (Pi → command-post uplink) | pi-code / backend |
| **PostgreSQL** | Command-post session/audio persistence (asyncpg) |
| **PMTiles / MBTiles** offline map archives | dashboard, sim, Android |
| **GGUF** model format + **llama.cpp** runtime | Android on-device LLM (via GenieX) |
| **QNN / QAIRT** (Qualcomm AI Runtime) | Snapdragon NPU inference |
| **ONNX Runtime GenAI** | X Elite NPU LLM server |
| **OpenAI-compatible `/v1/chat/completions`** API | Backend abstraction (vLLM, LM Studio, Ollama, GenieX, AnythingLLM) |
| **ffmpeg** | Audio transcode to 16 kHz mono WAV for STT |
| Opus / WAV / WebM / M4A audio | Voice SOS clips |
| QLoRA / LoRA (4-bit) fine-tuning | finetune |

---

## 5. Build & Dev Tooling
Gradle 8.9, Android Studio, Node.js + npm, Vite, Docker Compose (`compose.yaml`), Python venv,
Arduino IDE 2, ProGuard (release), FLEURS dataset (STT benchmarking).

---

*Generated by scanning dependency manifests and source. ⚠️ = non-OSI / proprietary dependency
flagged per CLAUDE.md rule #1 — a human should confirm before shipping.*
