# Sankat-Mochan — Off-Grid Disaster Rescue Mesh

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
