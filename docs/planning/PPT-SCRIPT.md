# PITCH DECK SCRIPT — Sankat-Mochan (for approval before building)

> Approve this first; then I build it with Claude (HTML slide deck, light theme).
> All facts are from VERIFIED-FACTS.md (cite-safe only). Nothing from the DO-NOT-USE list.
> Target: the **5-minute hard-ceiling** demo slot. Fast-paced — one idea per slide, big visuals,
> minimal text on screen (the words below the line are what you SAY, not what's printed).

## Deck meta
- **Format:** HTML slide deck (reveal.js-style) built with the frontend-design skill — gives us the
  newspaper-clipping aesthetic, precise placeholders, and subtle motion. Screen-recordable / exportable
  to PDF. (If you'd rather have a real .pptx, say so — HTML is more controllable for this look.)
- **Theme:** light, professional, editorial. Off-white paper background, near-black text, ONE accent
  (deep saffron/red for urgency). Serif for headlines (editorial feel), clean sans for data/UI.
- **Motion:** fast cuts, one reveal per beat. No slide sits > ~30s. Newspaper clippings slide/tilt in.
- **Proof device:** verified facts shown as **newspaper/online-news clippings** (headline + outlet +
  date), not bullet points. Every clipping maps to a real sourced fact.
- **Live beats:** two live-demo blocks; every live moment has a screenshot/photo PLACEHOLDER as backup
  so the deck stands alone if the live demo hiccups.

---

## Slide-by-slide (8 slides + 2 live blocks ≈ 4:40, ~20s buffer)

### 1 — HOOK (0:00–0:12)
- **On screen:** one line, big — *"When disaster strikes, the first thing to die is the network."*
  Then the name fades in: **Sankat-Mochan** · off-grid disaster rescue, fully offline.
- **Say:** "In every disaster, the phones go dark exactly when people need to call for help. That's the gap we built for."
- **Visual:** light paper bg; a faint, light-treated disaster photo [PLACEHOLDER: subtle hero image].

### 2 — THE PROBLEM IS REAL, AND IT'S NOW (0:12–0:45)
- **On screen:** 3 newspaper clippings cascading in:
  - *"Over 420 dead in Wayanad landslides"* — Kerala, July 2024
  - *"Wayanad landslide again: 3 dead, ~30 feared trapped"* — **July 2026** (this week)
  - *"All 14 districts hit; five networks down, couldn't send an SMS"* — Kerala floods, 2018
- **Say:** "This isn't hypothetical. Wayanad, 2024 — over 420 dead. It happened AGAIN this week. And when it hits, the network is the first casualty — in 2018 Kerala, five operators failed at once."
- **Sources (tiny footer):** Kerala govt / Onmanorama; TelecomLead.

### 3 — THE GAP + THE PRECEDENT (0:45–1:20)
- **On screen (left):** clipping — *"Migrant workers last to be rescued — missed Malayalam-only warnings"* (Kerala 2018). Clipping — *"Govt imports 25 satellite phones from Hong Kong mid-rescue"* (India Today, 2013).
- **On screen (right):** the ham-radio clipping — *"300 volunteers with radios locate 15,000+ stranded, aid 1,800 rescues"* (ARRL, 2018).
- **Say:** "Two failures repeat: coordination collapses, and people who don't speak the local language die waiting. But in 2018, 300 volunteers with radios did by hand what we're systematizing — they found 15,000 people. We add the AI they didn't have."
- **Purpose:** grounds us in reality + sets up the solution as proven, not sci-fi.

### 4 — THE SOLUTION + ARCHITECTURE DIAGRAM (lead with the brain) (1:20–1:50)
- **On screen:** the **full architecture diagram** (from DESIGN.md §0.5), animated left→right so it
  builds as you speak: Disaster zone (victim phone → relay phones → UNO Q sensors+LoRa bridge) →
  LoRa hop → Connected edge (Pi gateway → **AI Command Post on Snapdragon NPU**, glowing as the star)
  → reverse arrows (dispatch → responder, "help on the way" → victim). Cloud AI 100 dashed/off-path.
  Labels call out on-device inference at each hop (phone STT+extraction, UNO Q sensing, PC triage).
- **Say:** "A victim just speaks. Their phone transcribes and compresses on-device, passes it hand-to-hand; LoRa jumps the kilometre gaps; and an offline AI command post turns panicked, multilingual voices into a ranked, translated, mapped action list — then dispatches the nearest responder and tells the victim, in her language, that help is coming. No towers. No internet. Nothing leaves the mesh."
- **One-liner on screen:** *"Raw multilingual voice in → prioritized, translated, mapped rescue list out. Fully offline."*
- **Note:** I'll render this as a polished light-theme SVG in the deck (not raw mermaid), matching the editorial style; the mermaid in DESIGN.md §0.5 is the content source of truth.

### 5 — LIVE DEMO ① : the SOS journey + KILL-SWITCH (1:45–2:50) ★ centerpiece
- **[LIVE]** Victim speaks a Tamil SOS on the phone → hops across the mesh → **KILL-SWITCH: airplane-mode everything on stage** → SOS still arrives via LoRa → lands on the command-post dashboard.
- **Placeholders (backup):** [PHOTO: physical rig — phones + Pi + UNO Q + laptop]; [SCREENSHOT: dashboard receiving the SOS]; [SCREENSHOT: kill-switch — airplane mode on + message still arriving + RSSI].
- **Say:** "Watch — I'm killing all connectivity now. No WiFi, no cell. …And the SOS still arrives. That's the whole promise, live."

### 6 — LIVE DEMO ② : the AI brain + Rapido-style dispatch (2:50–3:40) ★
- **[LIVE]** Dashboard: transcription + urgency score + Indic→English translation + the victim pinned on the offline map; a second (sensor) alert corroborates. Responder app **pops the nearest victim, Rapido-style**; tap **Accept** → victim's phone flips to **"help is on the way"** in Tamil.
- **Placeholders:** [SCREENSHOT: triage queue ranked + map]; [SCREENSHOT: responder accept popup]; [SCREENSHOT: victim phone status in Tamil].
- **Say:** "The AI triages, translates, and ranks. The nearest responder gets a one-tap alert — like a Rapido ride. He accepts, and the victim instantly hears, in her own language: help is coming."

### 7 — THE NUMBERS + WHY IT'S HARD (3:40–4:10)
- **On screen:** live-ish metrics panel [SCREENSHOT PLACEHOLDER]: per-stage latency, **NPU vs CPU tokens/s**, RSSI, energy; **LoRa envelope viewer** (transcript → ≤255B packet + retries/ACK — the engineering tradeoff judges love); **fallback-ladder card** (NPU Qwen → CPU model → rule-based, all ready); **3-run history table**; headline stat — *"40 multilingual SOS ranked in seconds — vs one every 30–60s by hand."* Small: "3 devices, distinct roles, impossible on one." *(dashboard element list from DESIGN + validated peer-review additions)*
- **Say:** "Everything runs on-device on the Snapdragon NPU — Qwen3-4B for triage, Sarvam's Indic speech model on the phone. Here are the real latency and energy numbers. Three devices, each doing what only it can."

### 8 — HONEST LIMITS + REAL DEPLOYMENT + CLOSE (4:10–4:40)
- **On screen (left):** clipping — *"Foreigners arrested at Indian airports for carrying satellite messengers"* (2025). Line: *"In India there is no legal, affordable off-grid alternative."*
- **On screen (right):** *"We don't fix governance or replace towers. We equip responders for the hours before help arrives."* + NDMA's own line: *"terrestrial networks are prone to failure during disaster."*
- **Close line (big):** *"In 2018, 300 volunteers found 15,000 people. We made it a system — offline, in every language."* + repo QR / "install it yourself" + 5 member names.
- **Say:** "We're honest about the limit — adoption is the hard part, so we pre-equip responders and communities. Satellite is banned here; we're the legal, offline, rupee-cheap answer. Here's the repo — run it yourself. Thank you."

---

## Asset list (what I'll need to source/mock + placeholders)

**Newspaper/news clippings to render (verified — I'll style as light editorial clippings):**
1. Wayanad 2024 "over 420 dead" · 2. Wayanad July 2026 recurrence · 3. Kerala 2018 five-networks-down
4. Migrant workers last-priority / Malayalam warnings · 5. Kedarnath 2013 "25 satphones from Hong Kong" (attrib. India Today) · 6. Kerala 2018 ham radio 15,000/1,800 (ARRL) · 7. Satellite-messenger arrests 2025
- *(Optional slide, your call:)* Myanmar "three days to make a phone call" — flagged foreign/sensitive; only if you want the strongest single comms-collapse image.

**Live-result placeholders (you drop real screenshots/photos in before demo day):**
- [A] physical rig photo · [B] dashboard receiving SOS · [C] kill-switch (airplane mode + arrival) ·
  [D] triage queue + offline map · [E] responder accept popup · [F] victim phone status in Tamil ·
  [G] NPU-vs-CPU latency/energy panel · [H] hero disaster image (light-treated)

---

## Decisions I need before building
1. **Format:** HTML deck (recommended, best for this look) or a real .pptx?
2. **Myanmar slide:** include the one optional foreign clipping, or stay fully India?
3. **Length:** lock to 5 min (8 slides as above), or do you want a longer ~8–10 min backup version too?
4. **Clippings:** stylized "newspaper" mockups with real verified headlines + outlet names (recommended — we control layout and avoid copyright/paywall images), or do you want me to link/screenshot the actual articles?
