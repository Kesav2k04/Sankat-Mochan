# STAGE SCRIPT — Sankat-Mochan as a live 3-person drama (≤5 min)

> The punch: don't present the system — PERFORM it. Three teammates embody the three people in a
> real disaster; the judges live it from each POV. The tech does real work behind the actors; the
> deck (docs/deck/index.html) is the cinematic backdrop that cues each act. Under 5 minutes, total.

## Cast & staging
- **VICTIM** — teammate (Tamil-speaking). Off to one side, phone in hand, crouched/low. Their phone
  screen is projected (or mirrored) so judges see "Sending…" → "help is on the way".
- **OPERATOR (Siva)** — at the "forward relief camp": the Surface AI PC + the command-post dashboard
  projected big (center screen). This is the brain.
- **RESPONDER** — teammate with the responder app (phone projected). Stands apart from the victim.
- **NARRATOR + TECH (2 remaining)** — one narrates the 3 act-cards and works the kill-switch live;
  one runs/watches the tech and is ready to trigger fallbacks. Krishna conducts.

Three screens the judges can see: **victim phone · command-post dashboard · responder phone.**
The physical rig (phones + Pi + UNO Q + laptop) sits visible on the table — the kill-switch is done
in the open.

---

## COLD OPEN — you are the victim (0:00–0:30) ★ the hook
- **Backdrop:** stark. One line fades in: *"1:40 AM. The tower is already dead."*
- **VICTIM** (aloud, shaking, Tamil): *"Veedu moodhi irukku… thanni varudhu… yaaraavathu kaappaathunga—"*
  (*"The house is flooding… water is rising… somebody please save me—"*) — tries to call, holds the
  phone up: screen shows **"No network."**
- **NARRATOR:** "This is the exact moment every rescue app on earth fails. The network you'd call for
  help on is the first thing a disaster takes. Watch what happens next — from three pairs of shoes."
- *(No title slide. Open inside the emergency. This 30s is the whole punch — rehearse it cold.)*

## ACT I — the victim's shoes: the SOS escapes a dead network (0:30–1:20)
- **Backdrop card:** *"ACT I · YOU ARE THE VICTIM"*
- **VICTIM:** taps the one big SOS button, speaks. Phone shows **"Sending…"**. "I don't type. I don't
  choose a language. I just speak."
- **TECH:** "Everything here is offline — watch." Holds up the rig; **kill-switch is already live**
  (airplane mode on all devices — show it). The message hops phone→phone (mesh), then the LoRa link
  carries it the last kilometre. LEDs / dashboard blink as it moves.
- **VICTIM phone flips:** **"Message reached the control room"** — *in Tamil.*
- **NARRATOR:** "No tower. No internet. It still got out."

## ACT II — the operator's shoes (Siva) (1:20–2:35) ★ the technical core
- **Backdrop card:** *"ACT II · YOU ARE THE OPERATOR — the forward relief camp"*
- **OPERATOR (Siva):** "I'm at the camp at the edge of the dead zone. Forty of these just landed —
  Tamil, Hindi, Garhwali — and I have three teams. I cannot read them fast enough." *(beat)* "So the
  AI does." — points to the dashboard, live:
  - Whisper transcribes the victim's ramble → **Qwen3-4B on the Snapdragon NPU** scores urgency,
    translates to English, and **compresses it to a 255-byte packet** for the radio.
  - The victim drops onto the **offline map**; a **UNO Q sensor alert** (water + tilt) rings the same
    sector — *"a machine and a human, agreeing, with no one telling either to."*
  - Queue re-ranks: this one goes RED, top.
- **OPERATOR:** taps **Dispatch** on the top card. "Nearest responder — go."
- *(This is where the 40-point technical story lives — but shown as a person USING it, not a feature tour.)*

## ACT III — the responder's shoes + the loop closes (2:35–3:25) ★ the payoff
- **Backdrop card:** *"ACT III · YOU ARE THE RESPONDER"*
- **RESPONDER phone buzzes** — a **Rapido-style pop-up**: victim, urgency, sector, one-line gist.
  **RESPONDER:** "I'm 300 metres away. I've got it." — taps **Accept.**
- On the OPERATOR's screen: status flips to *assigned → en route.* Other teams see the sector is taken
  — no one double-searches.
- **VICTIM phone flips:** **"Help is on the way"** — *in Tamil.* The victim exhales. (Let this land — a beat of silence.)
- **NARRATOR:** "Out, understood, prioritized, answered — and she knows, in her own language, that
  someone is coming. All of it across a network that doesn't exist."

## THE PROOF — this isn't a story we made up (3:25–4:00)
- **Backdrop:** fast montage of the verified clippings (one every ~2s): Wayanad 2024 (over 420 dead) ·
  Wayanad *this week* · Kerala 2018 five networks down · Myanmar "three days to make a call."
- **NARRATOR:** "Wayanad — over 420 dead last year, and it happened AGAIN this week. And in 2018
  Kerala, **300 volunteers with radios found 15,000 people** by hand when the network died. We just
  made that a system — offline, in every language."

## THE NUMBERS + HONEST CLOSE (4:00–4:45)
- **Backdrop:** the metrics (NPU vs CPU, latency, RSSI, "40 ranked in seconds"), then the close.
- **OPERATOR/Krishna:** "It's all on-device on the Snapdragon NPU — here are the real numbers. We
  don't replace towers or fix governance; we cover the hours before help arrives, in the one country
  where a satellite messenger will get you arrested. It's open source. Run it yourself." *(repo QR)*
- **Final line (all, or Krishna):** "When the network dies — Sankat-Mochan doesn't."

---

## Why this wins (the reasoning)
- **Emotional + technical at once:** judges FEEL the victim's helplessness and the responder's relief,
  AND see the NPU/latency/map do real work — the 40-pt bucket delivered through a human using it.
- **Three POVs = the multi-device story told as people, not boxes** — directly answers the Multi-Device
  rubric (coordination, closed loop) without saying "orchestration."
- **The kill-switch is the spine, not a trick** — done in the open, early, so everything after is
  obviously real.
- **Peer-vote friendly:** a scene people remember beats a feature list they don't.

## Contingencies (so the drama survives a hiccup)
- Every live screen has a **pre-canned screenshot/recording** in the backdrop — if a device stalls,
  the narrator keeps the scene moving and the backdrop shows the beat. The performance never stops for tech.
- Victim audio is **pre-recorded + validated** (never gamble on live panicked Tamil STT); the operator
  can also read the transcript aloud if needed.
- If the NPU port failed, the same scene runs on the CPU fallback — the audience can't tell; the
  operator just doesn't claim the NPU speedup slide.
