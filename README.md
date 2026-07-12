# Sankat-Mochan — Off-Grid Disaster Rescue Mesh

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Works 100% offline](https://img.shields.io/badge/works-100%25%20offline-e4572e)
![AI on-device NPU](https://img.shields.io/badge/AI-on--device%20Snapdragon%20NPU-2a78d6)
[![Models & dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-kesav2k04-ffd21e)](https://huggingface.co/kesav2k04)
![Tests](https://img.shields.io/badge/tests-120%20passing-brightgreen)

> When floods, earthquakes, or blackouts knock out cell towers and the internet, phones and
> small radio nodes form their **own network** to get SOS calls out — no towers, no internet,
> no subscriptions. An **offline AI command post** triages, translates, and dispatches help.
>
> Built for the **Snapdragon Multiverse Hackathon**, Bengaluru (11–12 July 2026).

---

## What it does — in one story

1. **A victim speaks an SOS** into their phone, in their own language (Hindi, Tamil, Malayalam…).
2. The phone **transcribes the voice on-device** (no internet), packs it into a tiny
   ≤ 244-byte envelope, and relays it **phone-to-phone over Bluetooth LE** — every phone
   running the app is a mesh node that stores and forwards.
3. Where phones run out of reach, a **LoRa radio (433 MHz)** carries the SOS across the
   kilometre-scale gaps — from an Arduino UNO Q field node to a Raspberry Pi gateway.
4. The Pi uplinks it to the **offline AI command post**: a Snapdragon laptop running a local
   LLM on its **NPU**. It scores urgency, translates to English, plots the victim on an
   **offline map**, and ranks the incident queue.
5. An operator dispatches the **nearest responder**, who accepts with one tap — and the
   acknowledgement travels all the way back so the **victim hears, in their own language,
   that help is on the way**.

Everything above works with **zero internet and zero cell coverage**. The through-line:
legal, subscription-free, offline SOS coordination for India, where satellite messengers are
illegal and cell networks fail within hours of a disaster.

## How the pieces connect

```
 victim phone          relay phones           field node              gateway              command post
┌────────────┐  BLE   ┌────────────┐  BLE   ┌─────────────┐  LoRa   ┌────────────┐  WiFi/ ┌──────────────────┐
│ speak SOS  │ ─────► │ store &    │ ─────► │ Arduino     │ ~~~~~~► │ Raspberry  │  LAN   │ Snapdragon AI PC │
│ on-device  │  mesh  │ forward    │  mesh  │ UNO Q       │ 433MHz  │ Pi         │ ─────► │ triage · translate│
│ STT        │        │            │        │ (STM32+Linux)│  5 km  │            │        │ map · dispatch   │
└────────────┘        └────────────┘        └─────────────┘         └────────────┘        └──────────────────┘
      ▲                                                                                        │
      └────────────────────── "help is coming" travels back the same chain ◄──────────────────┘
```

## Measured, not claimed

<table>
  <tr>
    <td align="center"><h3>98.9%</h3><b>voice language ID</b><br><sub>FLEURS · 178/180 clips · 12 Indic languages</sub><br><sub>↑ +8.3 pts vs the mass scorer</sub></td>
    <td align="center"><h3>81.6%</h3><b>fine-tune eval accuracy</b><br><sub>49-item held-out set · strict 1/0.5/0 rubric</sub><br><sub>↑ 2.0× the base model (41.0%)</sub></td>
    <td align="center"><h3>9.0/10 @ 15.6 tok/s</h3><b>Sahayak on the phone NPU</b><br><sub>OnePlus 15 · every layer on Hexagon v81</sub><br><sub>E4B-class quality · E2B speed & size</sub></td>
    <td align="center"><h3>84.5 ms</h3><b>speech-to-text on the laptop NPU</b><br><sub>encoder + CTC decoder · AI Hub profile</sub><br><sub>1,802 / 1,802 layers on NPU</sub></td>
  </tr>
</table>

Every number below was **measured on the hardware it ships on** — greedy decoding, production
code paths, and a reproduce command in each source doc.

| What | Result | Where it ran | Evidence |
| --- | --- | --- | --- |
| Voice language ID (12 Indic languages, FLEURS) | **98.9%** (178/180 clips) | X Elite, CPU (~900 ms/clip) | [`backend/LID-BENCHMARK.md`](backend/LID-BENCHMARK.md) |
| Sahayak fine-tune vs base Gemma (held-out eval) | **41.0% → 81.6%** accuracy; all 3 adversarial safety failures fixed | Kaggle T4 eval, greedy | [`docs/evals/eval_comparison.md`](docs/evals/eval_comparison.md) |
| Sahayak on the **phone NPU** (Hexagon v81, all layers) | **9.0/10** answer quality at **15.6 tok/s** — E4B-class quality at E2B speed & size | OnePlus 15 | [`docs/BENCHMARK-NPU-MODELS.md`](docs/BENCHMARK-NPU-MODELS.md) |
| Speech-to-text pipeline compiled to the **laptop NPU** | **~84.5 ms**, 1,802/1,802 layers on NPU | X Elite, AI Hub profile | [`docs/AI-Hub-Compile-Guide.md`](docs/AI-Hub-Compile-Guide.md) |
| Command-post triage model bake-off (5 candidates) | Gemma 4 E4B: **6/6 faithful, 2–8 s/query** — 30–80× faster than Sarvam-M 24B, zero mistranslations | X Elite, GenieX | [`docs/BENCHMARK-NPU-MODELS.md`](docs/BENCHMARK-NPU-MODELS.md) |

The full interactive stats page lives at [`docs/benchmark-ledger.html`](docs/benchmark-ledger.html)
— open it in any browser (works offline, like everything else here).

## The components

| Folder | Hardware it runs on | What it is |
| --- | --- | --- |
| **`mobile-application/`** | Android phones | Native **Kotlin** BLE mesh app. Roles: **Victim** (speak/send SOS), **Responder** (accept dispatches), **Relay** (just forward). Every phone is a full mesh node (GATT server + scanner) with store-and-forward, dedup, offline map tiles, on-device speech-to-text (compiled for the Snapdragon NPU), and **Sahayak** — a fine-tuned Gemma 4 first-aid assistant that talks to the victim after the SOS is sent. |
| **`raspberrypi/`** | Raspberry Pi | The **LoRa gateway**. Speaks BLE to nearby phones, LoRa (SX1278/Ra-02, 433 MHz) across the long gaps, and uplinks accepted envelopes to the command post over the LAN. `server.sh` is the one-command supervisor (gateway, local command post, or both). |
| **`arduino-uno-q/`** | Arduino UNO Q | The **field node** at the disaster edge. The STM32 side runs the LoRa modem sketch (`sketch/`, `lora_modem/`, or the self-contained `field_beacon/`); the board's Linux side runs `field-node/` — a synced copy of the `raspberrypi/` mesh code — so victims' phones can connect to it over Bluetooth exactly like to the Pi. |
| **`backend/`** | Snapdragon X Elite "AI PC" | The **offline AI command post**: a **FastAPI** server + **React** dashboard. Ingests envelopes and voice clips, transcribes Indic speech (AI4Bharat IndicConformer, CPU), runs triage + translation on a local **Gemma 4** LLM served by **GenieX on the Hexagon NPU**, stores sessions in PostgreSQL, and serves a fully offline Protomaps basemap. Also holds `finetune/` (training Sahayak) and `deploy/npu/` (packaging the model for the phone NPU). |
| **`app-simulator/`** | any browser | A **React demo simulator** that plays the whole victim → mesh → LoRa → triage → dispatch story on the real Wayanad basemap — same envelope format, real LoRa airtime math. Used for the pitch and for testing at scale. |
| **`docs/`** | — | Everything written: architecture, specs, research, planning, the pitch deck (`docs/deck/`), eval results (`docs/evals/`), and assets. |

### Tech stack at a glance

- **Phones:** Kotlin, Jetpack Compose, BLE GATT mesh, ONNX Runtime + QNN (NPU speech-to-text), llama.cpp/GenieX for the on-device assistant, offline MBTiles maps.
- **Radios:** LoRa SX1278 (Ra-02) @ 433 MHz SF9 — legal, license-free in India; Python (`bleak`, `pyserial`, `msgpack`) on the Pi/UNO Q Linux side; Arduino C++ sketches on the STM32.
- **Command post:** FastAPI + uvicorn, React + Vite + MapLibre dashboard, AI4Bharat IndicConformer-600M (STT), Gemma 4 via GenieX on the Snapdragon NPU (triage/translate), PostgreSQL, Protomaps PMTiles.
- **Python everywhere is managed with [uv](https://docs.astral.sh/uv/)** — each Python folder has a `pyproject.toml`; `uv sync` / `uv run` do the rest (board scripts keep a pip fallback for offline hardware).

## Run it

**Command post (works with no hardware at all):**

```bash
cd backend
uv sync                    # one-time: installs everything
uv run uvicorn app:app --host 0.0.0.0 --port 9000
```

Open <http://localhost:9000> and click **Inject test SOS** — the full triage loop runs with a
rule-based fallback even with no LLM configured. For the whole dev stack (backend + live
dashboard + NPU LLM): `./dev.sh` (macOS/Linux) or `.\dev.ps1` (Windows) from `backend/`.

**Mesh app (needs 2+ physical Android phones — BLE doesn't work in emulators):**

```bash
cd mobile-application
./gradlew assembleDebug    # or open in Android Studio and Run
```

Pick a role on each phone, send an SOS from the Victim, and watch it hop.

**Radios:**

```bash
./raspberrypi/server.sh    # on the Pi: radios + uplink (post/local modes available)
```

For the UNO Q field node, see `arduino-uno-q/README.md` (flash the sketch, then
`field-node/run.sh`).

**Demo simulator:**

```bash
cd app-simulator && npm install && npm run dev
```

**Pitch deck:** open `docs/deck/index.html` in any browser.

## Tests

120 tests across the Python/JS components (`uv run pytest` in `backend/` and
`raspberrypi/`, `npm test` in `app-simulator/`), plus the Android JVM suite
(`./gradlew test`). See [`docs/TESTING.md`](docs/TESTING.md) for the full map.

## Fine-tune Sahayak yourself — fully reproducible

**Sahayak** is our QLoRA fine-tune of **Gemma 4 E2B** that turns the base model into a calm,
terse disaster first-responder: correct `SOS|WHO:|LOC:|NEED:` relay packets, opsec discipline
(refuses to broadcast raw GPS or relay false claims), and field-usable first aid. Everything
you need to retrain it from scratch is in this repo and on Hugging Face under
**[huggingface.co/kesav2k04](https://huggingface.co/kesav2k04)** — check that username for
every artifact (models, GGUF + NPU runtime, dataset) if a link below moves.

| Artifact | Where |
| --- | --- |
| Training + validation scripts | [`backend/finetune/`](backend/finetune/) — `sahayak_finetune.py`, `validate_dataset.py` (Apache-2.0) |
| Ready-to-run notebooks | `backend/finetune/kaggle_gemma4_e2b_finetune.ipynb` (free Kaggle **T4 ×2**), `colab_gemma4_finetune.ipynb` |
| Dataset (train / val / held-out eval) | [`backend/finetune/data/`](backend/finetune/data/) — built per [`docs/SAHAYAK_DATASET_SPEC.md`](docs/SAHAYAK_DATASET_SPEC.md) |
| Deployed model (merged fp16) | [`kesav2k04/sahayak-e2b`](https://huggingface.co/kesav2k04/sahayak-e2b) — gated: accept Google's Gemma Terms first |
| Phone-ready Q4_0 GGUF + prebuilt Hexagon NPU runtime | [`kesav2k04/sahayak-e2b-gguf`](https://huggingface.co/kesav2k04/sahayak-e2b-gguf) |

**The five-step retry recipe:**

```bash
cd backend/finetune

# 0) one-time: accept the Gemma terms on HF, then export HF_TOKEN=hf_...
# 1) validate the dataset (schema, dedup, length budgets — exit 0 = clean)
uv run validate_dataset.py data/train.jsonl

# 2) train — free path: upload the Kaggle notebook, set accelerator to GPU T4 x2,
#    attach data/train.jsonl + data/val.jsonl; or on your own CUDA box:
uv run sahayak_finetune.py --train data/train.jsonl --eval data/eval_holdout.jsonl \
    --model unsloth/gemma-4-E2B-it --out out/sahayak-e2b --export-gguf q4_0

# 3) eval against the held-out set (the 41.0% → 81.6% table comes from this)
#    → grading rubric and per-question results: docs/evals/eval_comparison.md

# 4) quantize + package for the phone NPU (Q4_0 — the quant Hexagon wants)
cd ../deploy/npu && python build_gemma_gguf.py --merged-checkpoint <merged> --llama-cpp <path>

# 5) run it on-device (all layers on the Hexagon NPU, verified in the load logs)
bash run_gemma_npu.sh out/sahayak-gemma-Q4_0.gguf "first-aid for a deep cut?"
```

Details, hardware fallbacks (it trains on CUDA, validates on any laptop), and the T4 dtype
gotcha we already patched: [`backend/finetune/README.md`](backend/finetune/README.md).

## Team

| Member | Email |
| --- | --- |
| Krishna (lead) | _TODO_ |
| Isha | _TODO_ |
| Karthi | _TODO_ |
| Keshav | _TODO_ |
| Siva | _TODO_ |

> **Note:** the official hackathon submission requires the full name **and email** of every
> member in the README. Fill the emails above before submitting.

## License

[MIT](LICENSE). All code is open source, per hackathon rules. AI-tool usage rules for this
repo (permissive-license deps only, no secrets, prompt-injection discipline) live in
`CLAUDE.md` / `AGENTS.md`.

---

*This is the team's private working repo (includes internal strategy/research under `docs/`).
The official hackathon submission must be a **public** repo — when you create it, publish only
the code, `docs/deck/`, and a clean README, and leave the internal strategy/critique docs out.*
