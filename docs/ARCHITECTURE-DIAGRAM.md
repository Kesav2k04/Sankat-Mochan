# Sankat-Mochan — Single System Architecture

> One picture of everything in this repo: the Android BLE mesh app (`mobile-application/`),
> the Pi LoRa gateway (`raspberrypi/`), the AI-PC command post (`backend/`),
> and the flow simulator (`app-simulator/`) — plus the frozen wire contracts that glue them.
> Use the Mermaid blocks directly (GitHub / Obsidian / mermaid.live render them),
> or use this doc as the source spec for a drawn (Figma/Excalidraw) diagram.

---

## 0. The one-line story

```
victim speaks → phone transcribes + compresses on-device → BLE mesh hops phone-to-phone
→ LoRa bridges the kilometre gap → Pi gateway → private LAN → AI PC command post
(NPU LLM: triage + Indic→English translate; STT) → ranked triage board → dispatch nearest
responder → return path back through the same chain → victim hears "help is on the way"
in their own language. No towers. No internet. Nothing leaves the mesh.
```

---

## 1. Master diagram (all tiers, both directions)

```mermaid
flowchart LR
    subgraph DZ["🌊 DISASTER ZONE — offline (kill-switch: airplane mode, BLE only)"]
        direction TB
        V["📱 Victim phone<br/><i>mobile-application (Kotlin)</i><br/>speak SOS → on-device STT →<br/>CONTRACT-1 envelope ≤244 B<br/>+ voice chunks (AMR)"]
        R1["📱 Relay phone(s)<br/>GATT server + scanner<br/>dedup by id · hop+1 ·<br/>store-and-forward"]
        RP["📱 Responder phone<br/>one-tap Accept ·<br/>status ladder in native language"]
        S["📟 UNO Q sensor node<br/>(event hw) water/tilt<br/>auto-alerts, category=sensor"]
        V -- "CONTRACT 2: BLE GATT<br/>WRITE + NOTIFY" --> R1
        R1 -- BLE --> RP
    end

    subgraph BR["📡 BRIDGE — the kilometre gap"]
        direction TB
        FN["Pi radio A — <b>field node</b><br/>MeshNode(lora_A, ble_phone_A)"]
        GN["Pi radio B — <b>gateway node</b><br/>MeshNode(lora_B, ble_phone_B)"]
        UP["uplink.py — EdgeUplink<br/>durable SQLite outbox<br/>(delete only on ACK)"]
        FN == "433 MHz LoRa (Ra-02 ×2)<br/>SF7–SF12 · ~310 ms/frame @SF7<br/>chainlog: TX/RX hash + RSSI/SNR" ==> GN
        GN --> UP
    end

    subgraph CP["🖥️ COMMAND POST — AI PC (Snapdragon X Elite) · connected edge"]
        direction TB
        API["app.py — FastAPI :9000<br/>POST /sos · POST /inject ·<br/>POST /accept/{id} · WS /gateway · WS /ws"]
        INT["intelligence.py — deterministic brain<br/>C1 cluster · C2 dedup/corroborate ·<br/>C3 rank · C4 registry · C5 nearest ·<br/>C6 de-conflict · C9 state machine ·<br/>C13 audit log + metrics"]
        LLM["triage.py — scoped LLM tools<br/>assess / same_incident /<br/>summarize_cluster / draft_reply<br/><i>OpenAI-compatible: GenieX (NPU) |<br/>LM Studio | Ollama | rule-based fallback</i>"]
        STT["stt.py / indic_stt.py<br/>Whisper / Indic-Conformer<br/>voice clip → transcript"]
        DB[("PostgreSQL (optional)<br/>sessions · audio BYTEA<br/>DB-less mode = in-memory + files")]
        DASH["web/ — React dashboard<br/>offline PMTiles Wayanad map ·<br/>ranked queue · clusters · dispatch ·<br/>AI activity log · NPU metrics"]
        API --> INT
        INT -- "fuzzy parts only<br/>(never control flow)" --> LLM
        API --> STT
        API --> DB
        API -- "WS /ws live feed" --> DASH
    end

    subgraph SIM["🎬 DEMO LAYER — app-simulator/ (React flow simulator)"]
        direction TB
        SENG["engine.js — journeys over the real<br/>topology · real envelope bytes ·<br/>real LoRa airtime (Semtech formula) ·<br/>mirrors intelligence.py tunables"]
        SMODE["Trace mode: 1 Tamil SOS, every hop<br/>Surge mode: 40 multilingual SOS / 24 h compressed"]
        SENG --- SMODE
    end

    R1 -- "CONTRACT 2: BLE" --> FN
    S -. "envelope via mesh" .-> FN
    UP == "CONTRACT 3: WS /gateway over<br/>private LAN (Ethernet 10.55.0.x<br/>or Pi hotspot) · ACK-by-id ·<br/>HTTP POST /sos fallback" ==> API

    API == "⬇ return path: {type:dispatch}<br/>ACCEPTED envelope" ==> UP
    UP --> GN
    GN == LoRa ==> FN
    FN -- BLE --> V

    SIM -. "same contracts, same tunables,<br/>cached triage — visualizes this pipeline" .-> CP
```

---

## 2. The four sub-projects at a glance

| Tier | Path | Runtime | Role |
|---|---|---|---|
| **Field mesh** | `mobile-application/` | Native Android (Kotlin, Compose) | One app, 3 roles (Victim / Responder / Relay). Every phone is a full BLE mesh node: GATT server **and** scanner, dedup + store-and-forward, optional GPS, voice SOS recording + chunking, victim status ladder, LoRa-only toggle, offline map tiles. |
| **Bridge** | `raspberrypi/` | Raspberry Pi (Python) | Two Ra-02 LoRa radios as **two isolated `MeshNode`s** (field + gateway) — the only edge between them is RF, provable via `chainlog.py` (payload hash on TX radio + RX radio + real RSSI/SNR). BLE central (`bleak`) toward phones; `uplink.py` durable outbox toward the AI PC. |
| **Command post** | `backend/` | FastAPI + React (Mac dev → Snapdragon X Elite at event) | Ingest + dedup, deterministic intelligence services (cluster/rank/dispatch/de-conflict/audit), backend-agnostic LLM triage + translation (NPU via GenieX), Whisper/Indic-Conformer STT, live WebSocket dashboard on an offline basemap, session persistence. |
| **Demo layer** | `app-simulator/` | Standalone React (Vite) | Plays the whole flow on the real Wayanad basemap. Honest simulation: real envelope wire format + 244-byte budget, real LoRa airtime math, roster/tunables copied from `intelligence.py`, cached triage per the SIMULATION-DEMO decision. Trace + Surge modes. |

---

## 3. The three frozen contracts (the glue)

```mermaid
flowchart TB
    C1["<b>CONTRACT 1 — Envelope</b><br/>compact JSON ≤ 244 bytes<br/>keys: i,t,o,r,u,c,l,g,ln,la,lo,ts,h<br/>dedup by i · h+1 per relay hop<br/>source of truth: model/SosMessage.kt<br/>ports: raspberrypi/envelope.py · app-simulator/src/sim/envelope.js"]
    C2["<b>CONTRACT 2 — BLE GATT</b><br/>service 6b1d0a01-… · char 6b1d0a02-…<br/>(WRITE + NOTIFY) · CCCD 00002902-…<br/>implemented: mobile-application BleMeshService ·<br/>raspberrypi/ble_link.py"]
    C3["<b>CONTRACT 3 — Edge link (Pi ⇄ AI PC)</b><br/>WS /gateway, ACK-by-id, heartbeat/pong<br/>up: {type:envelope, env:{…}}<br/>down: {type:dispatch, env:{t:ACCEPTED,…}}<br/>durable SQLite outbox both ends ·<br/>HTTP POST /sos fallback"]
    C1 --> C2 --> C3
```

Same validate → dedup → forward semantics on **every** tier (phone, Pi, PC) — that's
what lets a transport swap (e.g. radio A moving to the UNO Q) change nothing above it.

---

## 4. End-to-end sequence (SOS out, help back)

```mermaid
sequenceDiagram
    participant V as Victim phone
    participant M as BLE mesh (relays)
    participant P as Pi gateway (2 radios)
    participant A as AI PC :9000
    participant D as Dashboard
    participant R as Responder

    V->>V: speak → on-device STT → envelope ≤244 B (+ voice chunks)
    V->>M: BLE GATT write (CONTRACT 2)
    M->>M: dedup by id · hop+1 · store-and-forward
    M->>P: BLE → field node
    P->>P: field node ══ 433 MHz LoRa ══ gateway node (chainlog proves RF)
    P->>A: WS /gateway {type:envelope} → ack (outbox deletes on ACK)
    A->>A: STT (voice) → assess[LLM] → cluster[code] → dedup[code]<br/>→ rank[code] → nearest[code] → propose
    A->>D: WS /ws — card + map pin + audit log line
    D->>R: proposed: nearest crew + cluster brief
    R->>A: one-tap Accept → POST /accept/{id} (first-write-wins lock)
    A->>P: WS /gateway {type:dispatch, ACCEPTED} (downlink buffer)
    P->>M: node.originate → LoRa → BLE
    M->>V: "help is on the way" — in the victim's language
```

---

## 5. Inside the command post brain (C1–C18)

Governing rule (LOCKED): **deterministic code owns orchestration, state, and every
commit; the LLM is a scoped tool for fuzzy judgments only** — it never selects a
responder, emits coordinates, or drives control flow. SOS text is always wrapped
as data (prompt-injection structural defense, C12).

```mermaid
flowchart LR
    IN["envelope in<br/>(WS /gateway · POST /sos · /inject)"] --> VAL["validate + clamp<br/>(untrusted input, rule 8)"]
    VAL --> STT2["voice? → STT<br/>Whisper / Indic-Conformer"]
    STT2 --> AS["assess ⚙️LLM<br/>urgency · category ·<br/>English translation · confidence<br/>(fallback: rule-based)"]
    AS --> CL["C1 geo-cluster [code]<br/>union-find, eps≈100 m,<br/>split-biased, 2 lanes (GPS / no-GPS)"]
    CL --> DD["C2 dedup + corroborate [code]<br/>same-source merge · cross-source boost<br/>(+ same_incident ⚙️LLM confirm)"]
    DD --> RK["C3 rank [code]<br/>severity tier first · FIFO +<br/>bounded aging · corroboration boost"]
    RK --> NR["C5 nearest responder [code]<br/>greedy-by-priority · haversine ETA ·<br/>C4 registry (staleness, capacity=1)"]
    NR --> PR["propose + summarize_cluster ⚙️LLM<br/>→ responder Accept (human in the loop)"]
    PR --> DC["C6 de-conflict lock [code]<br/>first-write-wins · re-open on<br/>stuck timeout (C4/C18 watchdog)"]
    DC --> RPY["draft_reply ⚙️LLM<br/>native-language, honest, plain text"]
    RPY --> OUT["dispatch down the return path"]
    VAL -.-> AUD["C13 audit log + metrics<br/>append-only 'why' per decision ·<br/>per-stage latency · NPU tok/s"]
    AS -.-> AUD
    CL -.-> AUD
    RK -.-> AUD
    DC -.-> AUD
```

- Implemented today (`intelligence.py`): C1–C9 + C13 at demo scale, in-memory.
- LLM tool family (C10): `assess`, `same_incident`, `summarize_cluster`, `draft_reply` —
  forced JSON, data-tag wrapping, clamped outputs, per-call timeout, cached per SOS.
- Expansion drafted (C14–C18): needs extraction, gazetteer location resolution,
  reunification, resource-aware dispatch (offline routing), proactive watchdog.
  See `docs/INTELLIGENCE-DESIGN.md`.

---

## 6. AI runtime ladder (why "Snapdragon" is in the title)

```mermaid
flowchart TB
    subgraph PC["AI PC — Snapdragon X Elite (Hexagon NPU)"]
        G["GenieX serve :18181/v1<br/>Llama-3.1-8B heretic Q4_0 — <b>NPU</b> ✅ default"]
        A2["AnythingLLM (NPU, turnkey)"]
        L["LM Studio / Ollama (CPU — dev on Mac)"]
        RB["rule-based fallback (no LLM at all)"]
        G -->|fails| A2 -->|fails| L -->|fails| RB
    end
    subgraph PH["Victim phone — Snapdragon 8 Elite Gen 5 (event)"]
        S1["Sarvam Edge STT (NPU, best Indic)"]
        S2["ORT-genai QNN (NPU) → MLC-LLM (GPU) → llama.cpp (CPU)"]
        S3["rule-based self-report (T0 guarantee)"]
        S1 --> S2 --> S3
    end
    NOTE["All PC backends are OpenAI-compatible →<br/>swapping = one LLM_BASE_URL line in .env<br/>(backends.json + bench.py picks the fastest)"]
    PC --- NOTE
```

Key point for the diagram: **the pipeline is backend-agnostic**; the NPU is a
plug-in accelerator, not a dependency. Every AI stage has a graceful fallback,
down to fully rule-based — the SOS always gets through.

---

## 7. Network / deployment view (event day, fully offline)

```mermaid
flowchart LR
    subgraph AIR["Radio (no infrastructure)"]
        P1["Phones ⇄ phones: BLE<br/>(works in airplane mode + BT)"]
        P2["Pi field ⇄ Pi gateway: 433 MHz LoRa<br/>(km-scale, SF/power tunable)"]
    end
    subgraph LAN["Private LAN (never venue WiFi)"]
        E1["PRIMARY: direct Ethernet<br/>Pi 10.55.0.1 ⇄ PC 10.55.0.2"]
        E2["FALLBACK: Pi WiFi hotspot<br/>ssid sankat · 10.42.0.x"]
    end
    P1 --> P2 --> E1
    P2 --> E2
    E1 --> PC9["AI PC — uvicorn app:app :9000<br/>serves dashboard + WS + ingest"]
    E2 --> PC9
```

Loss protection stack (no SOS ever lost): durable SQLite outbox on both ends of
the edge link → delete only on ACK → auto-reconnect with backoff → HTTP fallback
→ two independent physical links → idempotent dedup-by-id makes replays safe.

---

## 8. Where the simulator fits (honest by construction)

The sim is **a driver + playback UI on top of the real design, not a parallel fake**:

| Sim element | Real counterpart it reuses |
|---|---|
| `app-simulator/src/sim/envelope.js` | CONTRACT-1 short-key wire format + 244-byte budget (`SosMessage.kt` / `envelope.py`) |
| LoRa hop timing | Semtech airtime formula (SF9/BW125 ≈ 1.2 s per full envelope) |
| Cluster / rank / dispatch tunables | Copied 1:1 from `backend/intelligence.py` (eps 100 m, aging cap 0.5, 12 km/h ETA…) |
| Wayanad basemap | The same offline PMTiles extract the command post serves (`copy-assets.mjs`) |
| Triage outputs | Pre-computed/cached per the SIMULATION-DEMO hybrid decision — with one **live** SOS dropped mid-demo through the real NPU to prove it's not a recording |

Two modes = the two halves of the pitch: **Trace** (one Tamil SOS, every hop
visible, incl. a lost voice chunk repaired by NACK) proves the plumbing;
**Surge** (40 multilingual SOS over a compressed 24 h) proves scale + the AI's
decisions — clustering, ranked dispatch, de-confliction, staffing pressure.

---

## 9. Cheat-sheet for the diagram author

If you're redrawing this as one poster-style diagram, the load-bearing elements are:

1. **Four vertical tiers, left → right:** Disaster zone (phones) → Bridge (LoRa/Pi) → Command post (AI PC) → Screens (dashboard + sim).
2. **Two arrows through every tier:** SOS **up** and dispatch/“help is coming” **down** — the return path is a differentiator, draw it explicitly.
3. **Three contract badges** on the seams: CONTRACT 1 (envelope) everywhere, CONTRACT 2 (BLE) phone⇄phone and phone⇄Pi, CONTRACT 3 (WS /gateway + ACK) Pi⇄PC.
4. **One "code owns control flow, LLM answers scoped questions" callout** on the command post — it's the safety story and the judges' explainability story.
5. **The kill-switch beat:** airplane mode ON, Bluetooth only — the SOS still crosses. Mark where each radio survives that.
6. **Provability details** worth a footnote: chainlog RF proof (hash + RSSI/SNR across two radios), durable ACK outbox, audit log "why" per decision, NPU tok/s metrics panel.

Source docs for deeper detail: `PLAN.md` (hardware + day plan) ·
`docs/INTELLIGENCE-DESIGN.md` (C1–C18) · `docs/EDGE-LINK.md` (CONTRACT 3) ·
`docs/HANDOFF-AIPC.md` (X Elite / GenieX setup) · `raspberrypi/README.md` (LoRa proof) ·
`app-simulator/README.md` (demo layer).
