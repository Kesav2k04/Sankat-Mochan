# Brutal Brainstorm — Sankat-Mochan (8 July 2026)

> Working notes from the strategy session. Companion to PREP-PLAN.md and hackathon-info.md.
> Rule of this doc: no cheerleading. If it's weak, it's written down as weak.

> **RULE (updated 8 July): pick examples ONLY by "does it show our app working better?"**
> - We are NOT framing the project as fighting internet shutdowns. Drop the anti-shutdown /
>   weaponized-connectivity political angle entirely. The CAUSE of the comms failure doesn't matter;
>   what matters is comms were unavailable and our app would have demonstrably helped.
> - Choose showcases purely on demonstration strength. **India preferred** (Indian judges, India-
>   grounded brief): Wayanad 2024, Kerala 2018 (ham-radio precedent), Kedarnath 2013, Chennai 2015,
>   Sikkim GLOF 2023, Himachal 2023, live July 2026 monsoon. **Myanmar is allowed** where it's the
>   stronger showcase (total comms collapse, days-long delayed help; nearby + similar region is a
>   bonus). Other foreign events only if clearly the best available demonstration.
> - Sources: RESEARCH-india.md + RESEARCH-intl-comms.md / RESEARCH-recent-stories.md (Myanmar).

---

## 1. The idea in three layers (walkthrough)

1. **Phone mesh (BLE store-and-forward)** — victims' phones relay SOS hand-to-hand, ~50–100m/hop, voice or text, no tower.
2. **LoRa bridge (UNO Q + Ra-02 → Pi gateway)** — carries a compact SOS envelope (≤255 bytes) across km-scale gaps between phone clusters.
3. **AI command post (Snapdragon X Elite NPU)** — STT (Whisper/Sarvam) → LLM: urgency triage + Indic↔English translation + compression → offline map, prioritized queue for rescuers. Cloud AI 100 = post-incident report only, off critical path.

Pitch: none of the pieces are new — the fusion is. Raw panicked multilingual voice in → prioritized, translated, mapped action list out, zero infrastructure.

---

## 2. What genuinely wins

| Strength | Why it converts to points |
| --- | --- |
| Inherently multi-device (phones sense, UNO Q bridges, PC thinks — impossible on one device) | Multi-Device prize has its own 100-pt rubric; most teams will be PC-centric |
| Kill-switch demo moment | 50+ teams × 5-min demos = saturated judges; one visible proof beats ten claims |
| Qualcomm judges want their own stack reflected back | NPU load graphs, AI Hub models, Genie, CPU-vs-NPU speedups → the 40-pt Technical bucket |
| Emotional, India-grounded story (920 shutdowns since 2016; Myanmar 2025 quake-during-blackout) | Feeds both judge narrative and peer vote |

---

## 3. Brutal weaknesses (beyond the team doc's own SWOT)

1. **7 subsystems in 24h** — Android app, BLE mesh, LoRa firmware, Pi gateway, NPU pipeline, STT, dashboard/map/instrumentation. Each must work ~first try. Fallback ladder is a parachute, not a plan.
2. **Mesh = highest risk, lowest unique points.** Multi-hop BLE on mixed-vendor Androids in a 2.4GHz-saturated hall is the most likely on-stage death, and judges have all seen mesh chat. It consumes the two strongest builders while the NOVEL layer is the AI.
3. **"AI triage" can look thin** ("so… two prompts?"). Needs visible depth: on-phone NPU pre-triage, voice-stress signal, byte-budget compression, structured-output guarantees, prompt-injection defense, measured NPU numbers.
4. **Panicked Hindi/Tamil speech vs Whisper-small = live-demo landmine.** Curated rehearsed utterances mandatory; evaluate Sarvam at their 11:30 Day-1 talk.
5. **Offline map + victim location is unowned.** GPS works offline; map TILES must be pre-downloaded. Assign an owner tonight.
6. **UNO Q risks being a prop.** Needs one concrete autonomous beat (shake/water sensor auto-fires an SOS, no human) or judges see a decoration.
7. **"App-store deployable" is a stated submission requirement** — frame the Android app as the shippable artifact in the README.
8. **Team shape:** two AI-strong people (me + original doc author), zero explicit owner for map/dashboard polish. Settle the split tonight.

---

## 4. Strategic levers

1. **Pre-build everything this week — reuse of own prior code is explicitly allowed** (orientation-call confirmed). Android skeleton, dashboard, pipeline, prompts, LoRa scripts can all exist by Friday. Saturday = integration + NPU porting day, not a build day. This converts 24h into a week. Biggest single edge available.
2. **Demo-first design.** Script the 5 minutes now; build backwards; anything not on screen in those 5 minutes (or in the README) is cut by default.
3. **Prize targeting.** Build for Top Prize (instrumentation bucket is cheap to win from hour 1); architecture naturally catches Multi-Device as fallback; one-prize rule means judges slot you where strongest.
4. **Peer-vote play.** Sideload the app on spare phones; let NEIGHBORING TEAMS send an SOS through the mesh during demo hours. People vote for what they experienced.
5. **Ruthless cuts:** Wi-Fi Direct → cut (BLE only, one transport done well). Multi-hop >2 → cut if flaky (one relay hop tells the story). Map → pre-downloaded Leaflet tiles + pins. Cloud AI 100 → only if green at hour 20.

---

## 5. Five-minute demo script skeleton (build backwards from this)

| Time | Beat | On screen |
| --- | --- | --- |
| 0:00–0:30 | Hook: "In 2025 India had 65 internet shutdowns. When the network dies, so do rescue apps." | Title + one stat |
| 0:30–1:30 | Victim speaks SOS in Tamil/Hindi on phone A → hops via phone B → arrives at command post | Live dashboard: message appears, per-hop latency |
| 1:30–2:30 | **Kill-switch**: airplane-mode/hotspot off, everything. Second SOS goes phone → UNO Q → LoRa → Pi → command post | RSSI, hop latency, "zero infrastructure" banner |
| 2:30–3:30 | AI beat: transcription, urgency score, translation, map pin — THEN UNO Q's sensor auto-fires its own SOS (no human) | Triage queue reorders live; NPU load meter; 3-run latency history |
| 3:30–4:15 | Numbers: CPU vs NPU tokens/s, mAh per node, end-to-end latencies across 3 runs | Instrumentation panel |
| 4:15–5:00 | Honest limits (jamming, scale) + fallback ladder + "here's the repo, install it yourself" | README/QR |

---

## 5.5 POST-CRITIQUE PIVOTS (decisive — see CRITIQUE.md, 8 July)

The brutal critique surfaced five things that change the strategy. Ranked by leverage:

1. **Pre-can the bilingual STT — do NOT capture live.** Whisper-small Tamil WER is catastrophic
   (~93% raw; can't code-switch mid-utterance), and a noisy 50-team hall makes live capture a coin
   flip on top. Record + validate the Tamil/Hindi clip in advance, play it, and **foreground the
   confidence + `stt_quality` + ambiguity flags as the honesty feature.** Converts the #1 faceplant
   risk into a maturity signal. NON-NEGOTIABLE.
2. **NPU-on-locked-Surface is the true single point of failure** — unfalsifiable until Sat 9:30 AM
   and gated on the unanswered admin-rights question. Get that answer IN WRITING from an organizer
   before Saturday. Decided Plan B if locked down: pivot the "runs on the NPU" story to the OnePlus
   15 phone NPU (device we control), not the Surface.
3. **Make the loop BIDIRECTIONAL — this is the make-or-break pivot.** A one-way relay is a *pipe*,
   not orchestration; it loses the Multi-Device prize we wrongly called "ours to lose." Fix: an ack
   flows back to the victim's phone ("reached command post") AND the command post dispatches a task
   back to a responder's phone. This single change (a) turns a bucket-brigade into real orchestration
   for the 100-pt rubric, and (b) fixes the "did it send?" UX silence that was Meena's agony in the
   story. Two liabilities, one fix.
4. **Reframe the pitch spine** to the ONE claim that survives scrutiny: **"legal, subscription-free,
   offline, India-specific."** Satellite messengers (Garmin inReach etc.) are illegal to own in India
   — that's why "nothing else could" is genuinely defensible HERE. Drop vague "multi-device
   orchestration" and "when nothing else could" language. Aim the win at Technical (40) + this story.
5. **Cut the burst demo from 20 messages to ~5.** Single-stream NPU triage at ~11–15s/message means
   10 messages = ~110–150s to drain; the dashboard would show 45–120s-stale triage. The flood beat
   demonstrates the CHOKE, not the engineering. A warm-session 5-message burst with a ranked list
   looks impressive; a big one exposes the single-queue bottleneck.

**Depth-vs-breadth ruling:** we can't pivot to single-device (proposal locked, LoRa hardware owned).
So mesh/LoRa become rehearsed supporting cast that works ONCE; pour the depth into the two things
that can be genuinely excellent — the AI triage layer and the sensor-fusion beat (autonomous hazard
alert corroborating a human SOS is the novel, defensible core).

**Honest calibration:** the "4% real-world success" attack is about DEPLOYMENT, not the DEMO. We
control and rehearse the demo; that can hit 95%+. Keep the demo tight and the *claims* humble.

## 6. Open decisions for tonight's call

- [ ] Role split: who owns AI pipeline vs instrumentation/dashboard vs map (two AI-strong people must divide, not overlap)
- [ ] Confirm model direction: Qwen3-4B primary (pre-compiled Genie assets), await MODEL-RESEARCH.md findings
- [ ] Approve the cut list (§4.5) — especially Wi-Fi Direct → BLE-only
- [ ] UNO Q's concrete sensor beat: which sensor, which trigger
- [ ] Who brings spare phones for the peer-vote play; who owns offline map tiles
- [ ] Pre-build assignments for Wed–Fri (lever 1) per person
- [ ] **URGENT: post the admin-rights question on Discord TODAY** (§5.5 #2 — the SPOF)
- [ ] Approve the §5.5 pivots — especially bidirectional loop (#3) and pre-canned STT (#1)
- [ ] Assign the bidirectional ack/dispatch work (§5.5 #3) — needs an owner on both app + PC side
