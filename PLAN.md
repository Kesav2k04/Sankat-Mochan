# Sankat-Mochan — One-Day Pre-Hackathon Plan

> Last updated: 10 July 2026 (hackathon 11–12 July, Bengaluru).
> Goal of this doc: exactly what to do NOW, with what we have, so it translates
> 1:1 to the event. Companion to `docs/DESIGN.md` (architecture) and the Pi's
> `HANDOFF.md` (wire contracts). Team: Krishna (lead), Isha (hw), Karthi (app),
> Keshav (AI), Siva (AI pipeline + instrumentation).

---

## 1. Hardware reality

| Have NOW | Target AT EVENT |
|---|---|
| Mac (dev) | AI PC = **Snapdragon X Elite** (Windows-on-ARM, Hexagon NPU) |
| **Snapdragon 7s Gen 3** phone (has a Hexagon NPU) | Phone = **OnePlus 15** (Snapdragon 8 Elite Gen 5) |
| **MediaTek** phone (no Qualcomm NPU) | — |
| Raspberry Pi (`lora@lorapi`, 10.148.169.23) + 2× Ra-02 LoRa | + Arduino UNO Q |

**Key unlock:** AI Hub **compiles and profiles in the cloud** — we do NOT need the
X Elite / OnePlus 15 in hand to pre-compile models or get real NPU numbers
(Qualcomm Device Cloud, qdc.qualcomm.com). This kills our biggest risk today.

---

## 2. Status snapshot (what's already built)

- **Android app** (`mesh-app/`, native Kotlin): one app, 3 roles (Victim/Responder/
  Relay). Full BLE mesh (peripheral+central), dedup + store-and-forward hops,
  optional GPS coords, victim status ladder, **LoRa-only toggle**. Compiles, installs,
  runs on ANY Android (chip-agnostic). ✅
- **Command post** (`command-post/`, FastAPI): `POST /sos` ingest + dedup, WebSocket
  live dashboard (ranked triage queue, coords, dispatch), **backend-agnostic AI triage**
  (OpenAI-compatible → any of vLLM/LM Studio/Ollama/GenieX), `bench.py` to rank backends.
  Runs on Mac now; rule-based fallback when no LLM. ✅
- **Pi** (`~/project-mesh/` on the board): context + contracts pushed (`HANDOFF.md`).
  SPI not enabled yet; LoRa gateway not built. Teammates wiring dual Ra-02. ⏳

---

## 3. Decisions locked

**Frameworks (run LLMs on the NPU, both targets):**
- **Primary runtime = ONNX Runtime + QNN-EP + `onnxruntime-genai`** — same code on
  Windows-ARM (X Elite) and Android (8 Elite Gen 5), NPU on both, LLM loop included.
- **AI PC fallback ladder:** ORT-genai(NPU) → **AnythingLLM** (NPU + OpenAI REST, turnkey)
  → **LM Studio/Ollama** (CPU). All OpenAI-compatible = one `.env` line to swap.
- **Phone fallback ladder:** ORT-genai QNN (NPU) → **MLC-LLM** (Adreno GPU) →
  **llama.cpp** (CPU) → rule-based (T0 guarantee).
- **Dev on Mac:** LM Studio (MLX) / Ollama — for building logic + model-quality selection.

**Models (compile per-device on AI Hub):**
- **Qwen3-4B** → PC triage + Indic→English translation (`Snapdragon X Elite CRD`).
- **Qwen3-1.7B / 0.6B** → phone extraction (`Snapdragon 8 Elite Gen 5`).
- **Whisper-Small-Quantized (W8A16, multilingual)** → STT, both targets.
- **Sarvam Edge** → phone STT (own SDK, best Indic; needs flagship NPU — OnePlus 15 ok).

**Why not the popular tools on the NPU:** LM Studio/Ollama/llama.cpp/vLLM are CPU/GPU
only — they never touch the Hexagon NPU. NPU = Qualcomm stack (AI Hub → QNN/GenieX).

---

## 4. DO NOW — prioritized (before the venue)

Legend: 🟢 translates 1:1 · 🟡 code-path validates · 🔴 internet-only, do first.

### P0 — 🔴 Kill the pre-compile risk (owner: Siva/Keshav, needs internet)
- [ ] Create AI Hub account (`aihub.qualcomm.com`) + API token.
- [ ] Compile **Qwen3-4B** for `Snapdragon X Elite CRD`; download `.bin`.
- [ ] Compile **Qwen3-1.7B/0.6B** for `Snapdragon 8 Elite Gen 5`; download.
- [ ] Compile **Whisper-Small-Quantized** for both targets; download.
- [ ] Profile each on **Device Cloud** → record real NPU latency/tok-s (deck numbers).
- [ ] Store all artifacts in a shared folder + on a USB (offline event!).
- *Script: `command-post/aihub_precompile.py` (to be written).*

### P1 — 🟢 Command post + model selection (owner: Siva, Mac)
- [ ] `bench.py` across LM Studio/Ollama on the Tamil/Hindi SOS samples → pick the
      model that TRANSLATES BEST (quality is chip-independent → same model for NPU).
- [ ] Enhance `bench.py` to print each model's English translation + urgency.
- [ ] Polish dashboard for projection (metrics panel: NPU-vs-CPU, latency, count).

### P2 — 🟢 ORT-genai → OpenAI shim (owner: Siva, Mac; runs on X Elite)
- [ ] Write `command-post/npu_server.py` — FastAPI OpenAI-compatible shim around
      `onnxruntime-genai` (QNN). At event: `pip install` → run → `LLM_BASE_URL` → done.

### P3 — 🟡 Android on-device LLM path (owner: Karthi/Siva, on 7s Gen 3)
- [ ] Add `onnxruntime-genai` (QNN) AAR to the app; `OnDeviceLlm` Kotlin class.
- [ ] Load a small Qwen3 on the 7s Gen 3 NPU (or CPU fallback) — validates the SAME
      code for the OnePlus 15. Wire to the phone extraction step (DESIGN §5).

### P4 — ⏳ Pi LoRa gateway (owner: teammates + Siva when Pi reachable)
- [ ] Enable SPI (`sudo raspi-config nonint do_spi 0`; reboot).
- [ ] Wire dual Ra-02 (CE0/CE1 — see HANDOFF); venv; `adafruit-rfm9x` + `bleak`.
- [ ] TX↔RX loopback; then BLE-central reads phone → LoRa → `POST /sos` to dashboard.

### P5 — 🟢 BLE mesh rehearsal (owner: all, 2 phones today)
- [ ] Install app on MediaTek + 7s Gen 3; Victim/Responder; SEND → Accept loop.
- [ ] Rehearse the **kill-switch** (airplane mode, BT only) until it's boring.

---

## 5. Hackathon-day integration flow

```
OnePlus 15 (SOS + Sarvam STT + Qwen3-0.6B extract, NPU)
   └─BLE→ relay phone ─BLE→ UNO Q ═LoRa═► Pi gateway ─LAN→ AI PC command post
                                                              (Qwen3-4B triage+translate on X Elite NPU)
                                                              → dashboard → dispatch ─back→ victim "help on the way"
```
Kill-switch = airplane mode on, BLE only; SOS still crosses. Two live blocks:
(1) SOS journey + kill-switch, (2) AI brain + Rapido-style dispatch.

**Day schedule (parallel):**
- **Now (internet):** P0 pre-compile — everyone unblocks on this.
- **Hrs 0–4:** Siva → P1/P2 (command post + shim + benchmark); Karthi → P3 (phone LLM);
  Isha/Krishna → P4 (Pi/LoRa); Keshav → Sarvam STT.
- **Hrs 4–8:** integrate phone→LoRa→command-post; NPU triage on screen; rehearse.
- **Hrs 8+:** T1 depth (clustering, sensor-fusion), polish deck numbers, 3× dry runs.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **AI Hub pre-compile is internet-only; event offline** | Do P0 TODAY; artifacts on USB |
| GenieX is a June-2026 dev preview (unstable) | ORT-genai primary; AnythingLLM turnkey fallback |
| On-phone NPU LLM hard in 24h | It's T1/stretch; T0 = Sarvam STT + rules; PC NPU is the star |
| `.bin` is device-specific | Compile separately for X Elite AND 8 Elite Gen 5 |
| LoRa link untested | Dual-Ra-02-on-one-Pi proves it before UNO Q arrives |
| Sarvam needs flagship NPU | Fine on OnePlus 15; don't rely on it on the 7s Gen 3 |

---

## 7. Contracts (do NOT diverge — see Pi `HANDOFF.md` for full detail)
- **Envelope:** compact JSON ≤244 B, keys `i,t,o,r,u,c,l,g,ln,la,lo,ts,h`; dedup by `i`; `h+1` on relay.
- **BLE:** service `6b1d0a01-…`, char `6b1d0a02-…` (WRITE+NOTIFY), CCCD `00002902-…`.
- **Command-post ingest:** `POST /sos` with the envelope JSON; `POST /accept/{id}` dispatch.

---

## 8. Open items / next
- [ ] AI Hub account + token (blocks P0).
- [ ] Confirm which teammate owns Sarvam STT vs on-phone LLM.
- [ ] Decide app name (parked — currently "Sankat-Mochan").
- [ ] X Elite laptop + OnePlus 15: only at event → P0 makes them plug-and-run.
