# BUILD PLAN — pre-build everything, port the rest at the venue

> Strategy (locked 8 July): build EVERYTHING possible on our own hardware before the hackathon
> (Pi + own Ra-02 LoRa + own Android phones + own laptops), so Saturday is a PORT + INTEGRATE +
> REHEARSE day, not a build day. Reuse of own prior code is explicitly allowed (orientation call).
> Companion to DESIGN.md (architecture), PREP-PLAN.md (schedule), MODEL-RESEARCH.md (AI stack).

## The core principle: build behind clean seams

Everything AI runs behind a swappable interface — `transcribe(audio) → text`, `extract(text) →
envelope`, `triage(envelope) → ranked+translated`. Build the CPU implementation now; at the venue
swap ONLY the inference backend to the NPU (Genie/QNN on the Surface, Sarvam/ONNX-QNN on the
OnePlus). The surrounding 90% (UI, protocol, mesh, LoRa, dashboard, map, prompts, schema, metrics)
never changes. Per MODEL-RESEARCH: the NPU port is a real backend swap (llama.cpp has no NPU
backend), so the seam is what makes the swap cheap.

---

## BUILD BEFORE (this week, own hardware) — ~90% of the system

| # | Component | Own hardware it runs on | Notes |
| --- | --- | --- | --- |
| 1 | **Shared message envelope + protocol** (≤255B; types: SOS/SENSOR/FOUND/DISPATCH/ACK/CLEARED) | any | Build FIRST — everything depends on it. |
| 2 | **AI command post pipeline (CPU)** — STT→triage→translate→cluster→dashboard→map→instrumentation, JSON-repair, prompt-injection defense | own laptop (CPU, llama.cpp + Whisper) | Deliverable A. The whole app + logic + prompts. Only the NPU backend waits. |
| 3 | **BLE phone mesh** — store-and-forward, chunking, ack-per-chunk, foreground service, Android-12+ permissions | own Android phones | Build against plain GATT (not BLE-6.0 features) so it runs on every phone incl. OnePlus. |
| 4 | **Victim app** — one-tap SOS, status ladder ("sending"→"reached control room"→"help on the way") in native language | own Android phones | Shell + all non-inference logic. On-phone STT/extraction is the only NPU-dependent part. |
| 5 | **First-responder app** — Rapido-style accept popup, cleared/in-progress, "victim found" report | own Android phones | Same transport as #3. |
| 6 | **LoRa transport (Pi gateway)** — envelope TX/RX, ack+retry, RSSI logging, Pi↔laptop Wi-Fi bridge | Raspberry Pi + 2× Ra-02 | Deliverable B. On Saturday one Ra-02 → UNO Q; code/protocol carry over. |
| 7 | **Sensor auto-fire logic** — 2-sensor-agreement, auto SOS | Pi GPIO + sensors | Port to UNO Q at venue. |
| 8 | **On-phone STT + extraction LOGIC (CPU/prototype)** — Sarvam/Whisper + tiny extraction LLM behind the seam | own laptop / any flagship phone | Logic + prompts now; NPU port on OnePlus at venue. |
| 9 | **Repo, README, MIT license, CLAUDE.md/AGENTS.md rules, demo-script draft** | any | Cheap, do early. |
| 10 | **Offline first-aid chatbot + tiny card-RAG (T2)** — logic only | own laptop | Prototype now; port to phone NPU only if core is green. |

**Milestone by Friday night:** a FULL end-to-end run on own gear —
own-phone mesh → Pi LoRa → laptop command post → responder phone → ack back — with the dashboard
showing live latency. This working own-hardware version IS the fallback demo if the NPU ports fail.

---

## BUILD AT VENUE (needs provided devices) — the remaining ~10%

| # | Task | Device (arrives Sat 9 AM–1 PM) | It's a... |
| --- | --- | --- | --- |
| A | **NPU port of the command-post pipeline** — Qwen3-4B + Whisper via Genie/QNN | Surface Laptop 7 (X Elite) | backend swap of #2. The 9:30 AM smoke test. |
| B | **On-phone NPU port** — Sarvam Edge STT + Qwen3-0.6B extraction | OnePlus 15 (8 Elite Gen 5) | backend swap of #8. |
| C | **UNO Q hardware bring-up** — flash, wire field-side Ra-02 + sensors, load Pi-tested code | Arduino UNO Q | hardware bring-up of #6/#7. |
| D | **Cloud AI 100 post-incident report (T2)** | Cloud AI 100 | only if everything green at hour 20. |
| E | **Integrate on real devices + rehearse kill-switch ×3** | all | the actual 24h work. |

**Why this wins:** if A or B fails (NPU risk is real + unfalsifiable until Sat morning), you fall
back to the pre-built CPU version — which also runs on the Surface's ARM CPU (llama.cpp + QMX
kernels, per MODEL-RESEARCH). You are never left with nothing.

---

## Suggested pre-build order (Wed eve → Fri), work-first (assign once roles settle)

1. **Envelope/protocol spec** (#1) — whole team agrees it Day 1; it's the contract between all parts.
2. **In parallel:**
   - AI command post CPU pipeline + dashboard (#2) — Siva (highest risk/value).
   - BLE mesh + app shells (#3/#4/#5) — app owner.
   - LoRa on Pi + sensor logic (#6/#7) — hardware owner.
   - Repo/README/license (#9) — 30 min, anyone.
3. **Thu–Fri:** wire them together on own hardware; hit the Friday end-to-end milestone.
4. **Fri:** on-phone STT/extraction logic (#8) prototyped; demo-script draft; pack list.

## Guardrails
- Build to the T0/T1/T2 tiers in DESIGN.md §7 — T0 core must run before any T1/T2.
- Keep the inference seam clean or the venue swap gets expensive.
- Bringing the Pi + own phones to the venue is explicitly allowed ("bring your own devices").
- Don't gold-plate own-hardware polish — its job is to be the working skeleton + fallback, not the final demo.
