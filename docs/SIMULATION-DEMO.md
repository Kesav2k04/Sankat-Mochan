# Idea — Time-Compressed Disaster Simulation (demo layer)

> Status: **PARKED** (idea captured 10 Jul 2026, pick up later). Not started.
> A cinematic "watch 24 hours of a disaster unfold" visualization that runs on
> top of the REAL command-post pipeline. Complements the live 3-phone demo.

## The concept
A time-accelerated simulation on the command-post dashboard: SOS blink onto a
map from many locations over a simulated 24 h, **clustering happens visually**
(pins group into incidents), **responders deploy** (markers move to incidents),
the **AI PC visibly triages/translates/decides**, and a **fast clock** at the
top compresses 24 h into ~3 minutes. Slow, watchable, narrative — a disaster
arc: a few calls → a surge (peak) → responders stretched → AI prioritizes →
resolution tapers.

## Why it belongs in the pitch
- The **live 3-phone demo proves it's REAL** (kill-switch, actual BLE/LoRa) — but
  can't show **scale or intelligence** (clustering, ranking 40 SOS, dispatch,
  de-confliction).
- The **simulation shows exactly that** — scale + the AI's decisions.
- Together = the complete story: *"it's real (live) AND it scales intelligently (sim)."*
- **Honest:** the sim feeds the SAME real pipeline (real triage, clustering,
  ranking) — just driven by a scripted disaster + a fast clock. Not a fake video.

## Key strategic call: cached vs live (recommended hybrid)
A demo must be flawless + repeatable (rehearse cold). If the surge fires 8 SOS in
one sim-second, running the LLM live on all → latency spikes + output variance =
stage risk. So:
- **Pre-compute the scenario's triage/translation once → cache → deterministic,
  perfectly smooth playback.**
- **Drop ONE genuinely live SOS mid-sim** (the kill-switch phone) through the real
  NPU live → proves it's not a recording.
- = cinematic reliability + a live proof beat.

## Phased build plan
**Phase 1 (shortest — makes the whole vision legible):**
- Scenario file — ~30–40 timed SOS (real lat/lng, multilingual text, a few sensor
  alerts + responders), escalating over sim-24 h.
- Sim driver (backend) — accelerated **sim clock** releasing each SOS at its
  sim-time through the existing ingest→triage→broadcast path (basically timed
  `/inject` + a clock broadcast). Minimal new code.
- Frontend — big **accelerated clock** + speed control; SOS **blink onto the map**
  and fill the queue as they "arrive."

**Phase 2:** visual **clustering** (hulls form as pins group) + an **AI activity
log** panel scrolling decisions ("clustered 3 reports · sector 4", "translated
Tamil", "dispatched R2").

**Phase 3:** **responder markers deploying** — move from base to incident,
assignment lines, sector-cleared de-confliction.

**Phase 4:** play/pause/**scrub**/speed; escalation-arc tuning; live metrics panel
(SOS/hr, responders busy, avg response time — the deck's numbers).

## Open decisions (answer before building)
1. **Region + disaster:** Wayanad landslide with real coords (matches deck) vs a
   generic city grid. (Lean: Wayanad.)
2. **Compression:** 24 h → on-screen length. (Lean: 24 h in ~3 min, scrubbable.)
3. **Scale + languages:** ~40 SOS (matches deck's "40 multilingual SOS ranked in
   seconds"), mixed Tamil/Hindi/Malayalam/Kannada.
4. **Cached vs live:** hybrid (cached cinematic + one live SOS) — confirm.

## Reuses what's already built
Command-post FastAPI (ingest, triage, WebSocket), React dashboard (MapPanel,
QueuePanel, Header), the envelope format, and the intelligence services being
built (clustering, ranking, assignment). The sim is a driver + a playback UI on
top — not a rewrite.

---

## Related: backend intelligence brainstorm (parked with this)

We began the per-component design that this sim will visualize. **Component 1 —
geo-clustering** was brainstormed; capture so we don't lose it:

**Clustering — decisions/edge cases raised (not yet finalized):**
- **No-GPS lane (the big one):** GPS is optional, many SOS will lack coords.
  Proposed two lanes — geo-cluster for GPS; text-`locationHint`/relay-node grouping
  or an "location unknown" bucket for the rest (still triaged + dispatchable).
- **Algorithm:** distance-threshold union-find (O(n²), fine at demo scale,
  explainable) over DBSCAN. eps ≈ 75 m + the two fixes' GPS accuracies, or flat 100 m.
- **Merge-bias vs split-bias:** lean **split-biased** — never merge two distinct
  emergencies; accept a bit more map noise.
- **Cluster ≠ collapse:** members keep individual urgency; cluster priority = **max**
  urgency of its members (1 critical + 4 low is a critical incident).
- **Stable cluster IDs** (derive from earliest member — avoid UI flicker on join).
- **Chaining** risk (a bridging point merging two clusters) — threshold controls it.
- **Time:** cluster active-with-active only; never merge resolved with active.
- **Null-island / out-of-region coords:** flag coords outside the operating bbox as
  "location suspect"; don't let them anchor a cluster.
- **Dispatch unit:** lean **cluster-level** (one responder per incident), priced by
  its worst victim.
- Full backend intelligence checklist (clustering, dedup, ranking, responder
  registry, nearest-assignment, de-confliction, sensor-fusion, capacity, status
  machine, metrics, audit log, agent loop, injection guard) — see chat / to be
  transcribed into a services plan when we resume.
