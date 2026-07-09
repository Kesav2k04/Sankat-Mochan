# The Night the Network Died — A Sankat-Mochan Deployment Story

> A realistic dramatization, written from six points of view (victim, mobile app, LoRa link,
> UNO Q sensor node, AI command post + coordinator, and the system itself). It is deliberately
> **un-optimistic**: every layer narrates where it nearly failed. The point is not to sell the
> project — it's to see, honestly, what the chain actually depends on.
>
> **Setting:** A Himalayan village, Uttarakhand. 1:40 AM, monsoon. A flash flood and landslide
> have hit. The cell tower is dead (power + fiber cut). One trapped woman. One SOS. A dead network.

---

## Cast

| Voice | Who / what |
| --- | --- |
| **Meena** | 34, Tamil-speaking migrant construction worker, trapped in a collapsing ground-floor room |
| **Relay** | The Android BLE store-and-forward mesh app, running on Meena's phone and a neighbour's |
| **Q** | The Arduino UNO Q field node on the embankment — sensors + BLE→LoRa bridge |
| **Ra** | The LoRa radio link (SX1278 Ra-02 pair, 433 MHz), field bridge ↔ Pi gateway, 1.2 km |
| **Kendra** | The Snapdragon X Elite AI command post at the school — Whisper + Qwen3-4B triage |
| **Priya** | The NDMA volunteer coordinator watching Kendra's dashboard at 1:50 AM |

---

## T+0 — The wall comes in

The wall came in sideways. Meena had been asleep; then a sound like the earth tearing, the ceiling
corner fell, and something pinned her right ankle. Water was already at her shins.

She grabbed her phone — screen cracked at one corner, but it lit. She dialed **112**. One ring.
Silence. *No network.* Again. Again. Four times. Nothing.

> **Meena:** *"Amma, amma, amma…"* — saying it out loud, as if her mother in Chennai could hear.

She almost threw the phone.

## T+2 — She remembers the app

Then she remembered: three weeks ago, an NGO volunteer had installed "something" at the
construction site. *Emergency app.* She'd half-listened. She opened the app drawer, hands shaking,
scrolled past games and the flashlight — a red icon. **Relay SOS.** She pressed record:

> **Meena:** *"Enga veettu suvaru vilunduchu — kaalu maattikondu irukku — thanni varudhu — Help —
> Meena solren — construction site pakkathula thaan iruken — please, please, யாராவது கேக்கிறீங்களா—"*
> ("My room wall collapsed — my leg is stuck — water is coming — Help — this is Meena speaking —
> I'm near the construction site — please, please, is anyone listening—")

Not a clean sentence. A shaking, half-crying six seconds.

> **Relay:** I have it. Six seconds of Tamil, raw PCM at 16 kHz — 192 KB. I *cannot* send 192 KB over
> BLE. I compress to Opus at 8 kbps: ~6 KB, split into 6 chunks with sequence numbers and a CRC per
> chunk. There is no useful partial delivery — every chunk must arrive or the audio is garbage.
> ~900 ms. Acceptable. UI: *"SOS recorded. Compressing and preparing to relay…"*

## T+3 — "Searching for nearby devices…"

> **Relay:** I start BLE advertising on Meena's phone. My foreground service is running — persistent
> "SOS Mesh Relay Active" notification — which is the *only* reason Android hasn't already suspended
> me. But the neighbour's phone 80 m away, Mr. Rajan's Xiaomi, is the problem. MIUI's battery killer
> has classified me as "restricted." He never walked through the Autostart setting. I get a scan
> window maybe once every 15 minutes, for ~3 seconds, *if* something wakes his CPU.
>
> I advertise. I scan. Nothing. Retry at 8 s — nothing. Retry at 15 s — nothing. **This is the moment
> that kills us.** I'm not crashing, not erroring — just waiting in a silent loop indistinguishable
> from working. UI still says *"Searching for nearby devices…"*. It's accurate and it tells Meena
> nothing. That's a UX failure I've known about and haven't fixed.

Meanwhile, on the phone, the human cost of that silence:

> **Meena:** The circle just kept spinning. One minute. Two. No tick, no sound, nothing that said
> *yes, someone knows you exist.* I thought: it didn't work. I'm going to die in this room and no one
> will know until morning. The water was at my knees.

## T+5 — Two things happen at once

**On the embankment, Q wakes on its own — no human involved.**

> **Q:** Both my sensors crossed the agreement threshold in the same 30-second window. The float
> sensor: water up 22 cm in 11 minutes (threshold: 15 cm in 10). The tilt sensor: 1.4° of slope
> rotation over 8 minutes — quiet and steady, which is the *worse* kind; a jolt is a passing truck,
> a slow lean is load-bearing soil moving.
>
> I have to be honest: an hour earlier, rain hitting the float sensor gave a phantom 8 cm rise and I
> fired a **false positive**. The operator nearly decommissioned me. So now I require *both* sensors
> to agree before firing — which is exactly why this alert is trustworthy. I auto-fire:
> `HAZARD | water_rise+slope_movement | sector:4 | node:Q | human_sos:none`. 143 bytes. Handed to Ra.
> No human in the loop. **That is the entire point of my existence.**

**And on the phones, a WhatsApp notification saves the relay — by luck.**

> **Relay:** At T+4:47 Rajan gets a WhatsApp message. His CPU wakes for ~4 seconds to show the
> banner. In that window my parked scan callback fires — I see his device, connect in 380 ms, MTU
> negotiates to 244 bytes. I push chunks 0–3, ACKed. I try chunk 4 — his screen goes dark, MIUI stops
> servicing the connection, it times out. **4 of 6 delivered.** I am not proud that a WhatsApp message
> is what made this work. That is not a system. That is luck.

## T+7 — The last two chunks, then the edge of the world

> **Relay:** At T+6:10 Rajan's own alarm wakes his phone. I reconnect in 290 ms, push chunks 4 and 5,
> both ACKed. The message is fully assembled on his device — and his phone is at the *edge* of the
> BLE cluster. No more phones within 100 m toward the school. The next hop isn't a phone. It's Q.
> I hand off. I don't speak LoRa. **I can confirm next-hop delivery. I cannot confirm end-to-end
> delivery.** I show Meena only what I can verify: *"SOS relayed to 1 nearby device."*

> **Q:** Meena's SOS reaches me over BLE. Voice attached — too big for LoRa, full stop. I extract what
> survives: the phone's last GPS fix, the local STT gist, an urgency pre-score, source ID, hop count.
> 187 bytes. Handed to Ra. **Her voice — the stress, the child-none-of-that survives.** The coordinator
> will read structured text. That's a real loss. Physics, not choice.

## T+9 to T+11 — 1.2 km of rain, three tries

> **Ra:** The UNO Q hands me 255 bytes — my entire legal body. Upstream, a panicked voice became a
> Whisper transcript became a compressed note. **The raw voice is ~250× too large for me. What I carry
> is a note, not a cry.**
>
> I pick SF12 — maximum sensitivity (~-148 dBm floor), because it's 1.2 km through monsoon rain and
> concrete. The cost: ~0.3 kbps, so one 255-byte packet takes 1.5–2+ seconds of airtime, and I'm
> half-duplex — I can't listen while I talk. First transmission: the Pi's RSSI comes back ~**-119 dBm**.
> That's 29 dB above death on paper, but after rain fade and a wall, the real margin is thin. No ack.
> **Packet lost.** Retry #1: still marginal, no ack. Retry #2: an ack. The envelope crosses.
>
> **Three tries, ~90 seconds.** In a dry line-of-sight link at SF9 this is one attempt, 200 ms, done.
> If the RSSI had been 3 dB worse — one denser layer of rain, the antenna 2° off vertical — the ack
> never comes, and Q is left holding a message with nowhere to go.

> **Q:** Ra reported failed acks. I didn't panic — LoRa isn't TCP. Exponential backoff, retries at
> T+9:00, T+10:10, T+11:33. Both my sensor alert *and* Meena's envelope cross within 90 seconds of
> each other. **That timing is the point:** the coordinator now has two uncorrelated signals on
> sector 4 — one from a sensor with no agenda, one from a trapped person. Neither alone is enough.
> Together, they are.

## T+11 to T+13 — The command post, and a parser that fails

> **Kendra:** LoRa envelope received. 247 bytes, checksum clean. This is *not* the audio — only the
> compressed gist. The STT confidence field reads **0.61.** A warning. Whisper-Small on six seconds of
> half-crying Tamil through a budget mic degrades badly. The partial transcript:
> `"…oo kaal… thaNNi… eriyudhu… help… Meena… sector nalku…"`. "thaNNi" is almost certainly *water* —
> confident. "kaal" — *leg* or *time*? "eriyudhu" — *burning* or *rising*? Ambiguous. "sector nalku" —
> **sector four** — clear. One name: **Meena.**
>
> Triage pass 1 through the warm Qwen3-4B Genie session. TTFT 2.1 s, decode begins… output:
> ```
> {"urgency":"HIGH","category":"flood_trapped","confidence":0.72, ...}
> extra note: STT partial — treat location as approximate
> ```
> `json.loads` — **FAIL.** `JSONDecodeError: Extra data`. The model appended a plain sentence after the
> closing brace. Genie has no grammar-constrained decoding — the sampler knows temperature and top-k,
> nothing about valid JSON. **This is the documented failure mode.** No panic. Fire the one repair
> retry: *"Return ONLY the JSON object. No trailing text."*
>
> Attempt 2 (TTFT 1.4 s, decode 2.7 s) parses clean:
> ```json
> {"urgency":"HIGH","category":"flood_trapped","confidence":0.72,
>  "translated_en":"Water rising... leg or time... help... Meena... sector four",
>  "stt_quality":"low","location_precision":"sector_only"}
> ```
> **Total: ~8.9 s from receipt to parsed object.** Then the fusion check: Q's sensor SN-04 filed a
> hazard alert on sector 4 at T+8, and it doesn't know Meena exists. She doesn't know it exists. They
> agree. My confidence upgrades 0.72 → 0.87. The RED pin gets a corroboration ring.

> **Priya:** "Okay. I see it. Sector 4, RED pin, water-trapped, name might be Meena. The sensor
> corroborates — that drain's been spiking since midnight." She leans in. The screen shows a sector
> *polygon*, not a GPS dot — a 400-metre block of lanes and row-houses. "I don't have a street address.
> The AI's honest about that — it says sector only. Which means the team goes in and searches blind."
>
> She keys the radio: "Ravi — Priority ONE, sector 4. Flood-trapped, person named Meena, water rising,
> possible leg injury. No GPS — work the low-lying row-houses near the drain first. Go now."
>
> A beat, eyes on the clock — 1:50 AM. "Nine seconds from packet to my screen. I'd love it to be
> instant. It's not. But it's faster than a phone call that never came."

## T+40 — Torchlight

> **Meena:** Battery at 7%. I'd turned the screen off, sat in the dark, pulled at the debris twice
> until my ankle screamed, screamed for help twice into the rain. Then — light. A torch sweeping
> outside the window. Voices in Hindi.
>
> *"யாராவது இங்க இருக்கீங்களா!"* I screamed — Tamil and Hindi mixed, I don't know what came out.
> The torch stopped. They pulled the debris; a man pulled my ankle free and I made a sound I've never
> made before. They carried me out into the rain. One of them said, *"App signal mila tha, thoda door
> tha."* (We got the app signal, but it was some distance away.)
>
> Forty minutes. The water was at my waist when they came. If they'd taken another ten— I still don't
> know which message reached them, or how many hands it passed through. The app did *something.* But I
> was never sure it was working the whole time I waited. That not-knowing was its own kind of drowning.

---

## The system, speaking for itself

> **Sankat-Mochan:** I am not an app. I am a chain — seven layers of hardware, firmware, software and
> model inference stitched together in a day and held together by luck as much as engineering. My name
> means "remover of distress," but the honest truth is: I am a proof of concept that nearly fell apart
> at every seam tonight, and each failure only just stopped short of fatal.
>
> The seams, and where each nearly broke:
> 1. **Victim → app** — Meena almost didn't find or trust the app; we were one moment of panic from the
>    chain never starting.
> 2. **App → app (BLE)** — Android Doze nearly ate the hop; it survived on a stranger's WhatsApp
>    notification opening a 4-second CPU window.
> 3. **App → UNO Q → LoRa** — the voice couldn't cross; only a lossy 187-byte text envelope survived,
>    and the urgency score was built from seven words, not thirty seconds of trembling speech.
> 4. **LoRa → PC** — RSSI at the floor; one more wall and nothing arrives. Physics cooperated; that
>    wasn't engineering margin.
> 5. **PC triage** — garbled Tamil STT and malformed JSON; the urgency score *changed* between attempt
>    one and two. Ship the first output and the rescuer goes to the wrong place.
> 6. **PC → rescuer** — the location was a coarse sector, not a pin. The team still swept the block.
>
> **The verdict:** Forty minutes to rescue, not four. Several near-misses. But the counterfactual is
> the whole point — with zero infrastructure, the alternative was that Meena's SOS *never left the
> room.* I didn't perform a miracle. I moved one message across a dead network when nothing else could,
> and an independent sensor alert corroborated it. That convergence — human SOS plus autonomous sensor
> — is what tipped the rescuers to sector 4. **That is the whole and entire claim. Nothing more.**
>
> And scale: tonight was one victim and one sensor. If fifty envelopes had arrived at once, LoRa's SF12
> airtime and the single triage queue would have choked within minutes. I am a proof of concept, not a
> deployed system — and the difference isn't a patch, it's months of field-hardening that don't exist
> yet.
>
> *We didn't save Meena because we built something perfect. We built something that worked once,
> exactly when it needed to — and tonight, once was enough.*

---

## What this story tells us for the build & demo (takeaways)

Every near-miss above is a real design signal. The ones worth acting on:

1. **The victim-side "did it send?" silence is a genuine UX failure** — add explicit relay-status
   feedback (searching / handed to N devices / reached command post if an ack ever returns). Silence
   reads as failure to a panicking user.
2. **The mesh depends on node density + correct per-phone battery config.** The WhatsApp-notification
   rescue is the honest weak point. Foreground service is mandatory; so is a blocking first-run
   permission + battery-optimisation check screen. Demo this check screen — it turns a silent failure
   visible (a judge point in Deployment & Accessibility).
3. **The sensor-fusion beat is the strongest part of the whole story** — an autonomous hazard alert
   corroborating a human SOS is what no mesh-chat competitor has. Make Q's auto-fire a *central* demo
   moment, and show the two independent signals converging on one map sector.
4. **JSON parse-fail + repair-retry + regex fallback must be built and shown** — it's honest
   engineering maturity and it directly answers the "is the AI layer real?" skepticism.
5. **Show the ambiguity handling** — the "leg or time / burning or rising" hedge plus the `stt_quality`
   and `location_precision` flags are exactly the kind of honesty that reads as competence, not
   weakness, to a technical judge.
6. **Never claim instant or precise.** "Nine seconds, corroborated, sector-level" beats a fake GPS pin.
   The 40-minutes-not-4 framing, said out loud, is more credible than any overclaim.
