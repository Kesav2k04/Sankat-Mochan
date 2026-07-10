# Command-Post Intelligence — Build Spec

> The backend "brain" of the AI PC, designed component-by-component. This is the
> BUILD SPEC — decisions here drive the code in `command-post/`. It also defines
> what the time-compressed simulation ([[SIMULATION-DEMO]]) visualizes.
> Status: brainstorm in progress (started 10 Jul 2026). Components added as we go.

## Governing architecture (applies to every component)
- **Deterministic code owns orchestration + the source of truth**; the LLM
  (Qwen3-4B / Llama-3.2-3B) is a **tool for the fuzzy parts only** (understand text,
  translate, scoped semantic judgments, drafting). The LLM never emits an
  assignment or drives control flow directly.
- **Human-in-the-loop for life-safety**: agent *proposes*, responder *confirms*
  (one-tap Accept). Auto-act only on high-confidence, always with an audit log.
- **Untrusted input**: SOS text is DATA, never instructions — must never trigger or
  parametrize a tool call (CLAUDE.md #7). Load-bearing once the agent has dispatch tools.
- **Explainability**: every automated decision is logged with its *why* (audit log) —
  for trust, for the sim's AI-activity panel, and for judges.

Legend: `[code]` deterministic · `[LLM]` model tool · **LOCKED** / *PROPOSED* / OPEN.

---

## Component 1 — Geo-clustering `[code]`
**Purpose:** group SOS from one incident so 6 reports of one collapse = one incident
(one responder), not 6 pins. The unit that gets dispatched.

**Decisions:**
- *PROPOSED* **Two lanes for location** (GPS is optional → many SOS lack coords):
  - has GPS → geo-cluster.
  - no GPS → group by `locationHint` text / originating relay-node area, else an
    **"location unknown"** bucket (still triaged + dispatchable, just not map-pinned).
- *PROPOSED* **Algorithm:** distance-threshold **union-find** (O(n²), fine at demo
  scale, explainable) over DBSCAN. eps ≈ **75 m + the two fixes' GPS accuracies**
  (fallback flat 100 m).
- *PROPOSED* **Split-biased** — never merge two distinct emergencies; accept more
  map noise over under-serving a separate incident.
- **LOCKED** **Cluster ≠ collapse:** members keep individual urgency; **cluster
  priority = MAX urgency of members** (1 critical + 4 low ⇒ critical incident).
- *PROPOSED* **Dispatch unit = cluster** (one responder per incident), priced by its
  worst victim.

**Edge cases:**
- Stable cluster IDs — derive from the **earliest member** so joins don't reshuffle
  ids / flicker the map.
- **Chaining** — a bridging point can merge two clusters into a blob; the threshold
  controls it, watch for it.
- **Time** — cluster active-with-active only; never merge a **resolved** incident
  with an active one.
- **Null-island / out-of-region coords** — `(0,0)` passes range validation but is
  bogus; flag coords outside the configured operating bbox as "location suspect,"
  don't let them anchor a cluster.
- **Sim requirement:** clustering must be **incremental** (recomputed on each arrival)
  so "clustering visually happens" reads on screen; emit cluster geometry (hull/centroid).

---

## Component 2 — Dedup & Corroboration `[code]` + `[LLM]` confirm
**Purpose:** collapse redundant repeats WITHOUT destroying corroboration signal.

**The core rule (do NOT conflate these):**
- **Same source repeats → DEDUP / MERGE** (one emergency, not many).
- **Different sources, same incident → CORROBORATION** — keep both, **raise
  confidence/priority**, never delete. Deleting a second reporter loses rescue
  signal and hides how many are affected. (Cross-source grouping is Component 1's job.)

**Decisions:**
- *PROPOSED* Same-source dedup keys on **origin + short time window + similar
  category/text** — NOT origin alone (a source can send two *different* emergencies,
  e.g. flood then medical — must not merge those).
- *PROPOSED* **Merge policy = never discard:** keep **earliest id** (stability), take
  **MAX urgency**, **LATEST detail/text**, bump an **update/corroboration count**,
  and retain the list of contributing ids/origins for the audit trail.
- *PROPOSED* **Candidate flagging is cheap `[code]`** (same origin/cluster + time
  window + token-overlap); the **`[LLM]` `same_incident(a,b)` tool confirms** only
  those few pairs — never O(n²) LLM calls.
- *PROPOSED* **Corroboration payoff:** N independent reports + a UNO Q sensor on one
  cluster = the system's strongest signal → **boost cluster confidence/priority**,
  show it explicitly (great AI-log/sim beat).

**Edge cases:**
- Same origin, genuinely different emergencies (flood→medical) → must NOT merge.
- Escalation ("water at knees"→"water at neck") → merge but take max-urgency + latest text.
- Transport re-broadcast duplicates (same msg id) → already handled by id-dedup in the
  mesh + command post; this layer works on distinct ids on top of that.
- Corroboration vs double-dispatch — 3 reports of one collapse corroborate into ONE
  incident ⇒ ONE responder (the point of clustering feeding dispatch).

**OPEN — abuse handling:** per-origin rate-limit + burst-from-new-origins flag.
*PROPOSED:* **park as stretch** (matters for real deployment > the demo). Attacker
rotating origin ids defeats naive rate-limit → burst flag as the mitigation.

---

## Component 3 — Prioritization / Ranking `[code]`
**Purpose:** order the queue so responders act on the most important incident first
("40 SOS ranked in seconds"). Ranks **clusters/incidents**, not raw SOS.

**Decisions:**
- *PROPOSED* **Hard severity tier first** (cluster max-urgency 5→1). Everything else
  only reorders *within* a tier — a big cluster of LOW never outranks a single CRITICAL.
- *PROPOSED* **Within a tier:** older-first (FIFO) + **bounded aging** (effective
  priority creeps up the longer an incident waits) to prevent **starvation** — but
  aging is capped so it can never lift an item out of its severity tier.
- *PROPOSED* **Corroboration/size boost within tier** (more reports / bigger cluster /
  sensor-confirmed ranks higher among equals).
- *PROPOSED* **Low AI confidence ⇒ flag for human review, do NOT auto-down-rank**
  (a garbled critical must not get buried).
- *PROPOSED* **No category weights** — urgency already encodes severity; category is
  for responder *matching*, not ranking (avoids double-counting).

**Edge cases:**
- Assigned/en-route incidents drop out of the "needs action" sort but stay visible;
  resolved incidents archived.
- Ties (same urgency + age) broken by id → no UI flicker.
- Re-rank on every new SOS / status change / merge (cheap sort at demo scale).
- Each item carries its **why** ("urgency 5 · 3 reports · waited 12 m") → audit log +
  the sim's dramatic queue re-sort during the surge.

---

## Component 4 — Responder Registry `[code]`
**Purpose:** the roster assignment draws from — who's out there, where, status, capability.

**Decisions:**
- *PROPOSED* **Record fields:** id, callsign, location + **timestamp**, status, capability
  (soft), capacity = 1.
- *PROPOSED* **Fed by the return path** — responder app beacons location+status back
  through the mesh. Also pre-registered for the sim/demo. Both feed one registry.
- *PROPOSED* **Staleness:** keep last-known + timestamp; too-old ⇒ lower assignment
  confidence, then mark **offline** after a no-heartbeat timeout.
- *PROPOSED* **Capability = SOFT preference, never a hard filter** — never leave a
  critical unassigned because no "medic" is free; send the nearest available body.
- *PROPOSED* **Capacity = 1 incident** at a time (a cluster is one incident → one
  responder covers its multiple victims). Multi-responder teams = stretch.

**Edge cases:**
- **Stuck-assignment timeout (safety-critical):** responder accepts then goes silent
  (battery/range/forgot to clear) → no progress in **X min (≈10?) ⇒ auto re-open** for
  reassignment. A victim must never wait forever on a silent responder.
- Offline/dropped responder → mark offline on no-heartbeat + **re-open** their incident.
- Responder locations are PII-ish (rule #6 — flag; lower risk than victim data).
- Drives the sim's responder map markers + "deploying" animation.

---

## Component 5 — Nearest-Responder Assignment `[code]`
**Purpose:** pick which responder goes to which incident (Rapido-style dispatch). Pure
geometry — no LLM → reliable.

**Decisions:**
- *PROPOSED* **Greedy-by-priority, NOT global-optimal.** Walk the ranked queue; each
  incident gets the nearest *available* responder. The most critical always gets the
  nearest — never trade a critical's response time to optimize the average. (Global
  min-cost assignment = stretch.)
- *PROPOSED* **Offline distance = haversine straight-line + rough speed → approximate
  ETA**, flagged approximate. (No internet ⇒ no road routing. Straight-line ignores
  terrain — "500 m across a flooded river" is really far; terrain penalty = later.)
- *PROPOSED* **No responder free ⇒ incident stays "awaiting responder,"** surfaced
  prominently — a critical with no responder is the coordinator's #1 signal.
- *PROPOSED* **Proposes, responder confirms (Accept).** Auto-notify nearest for
  high-confidence criticals, still require the tap.

**Edge cases:**
- Re-opened (stuck) incident → reassign to next-nearest, **excluding** the silent responder.
- Capacity=1 naturally load-balances (assigned ⇒ busy ⇒ skipped) — no overload.
- Stale responder location → assign nearest-known but flag low ETA confidence.
- Couples with **de-confliction (C6)** so a later pass can't double-assign.
- Drives the sim's responder→incident line + deploy animation + ETA countdown.

---

## Component 6 — De-confliction `[code]`
**Purpose:** two responders never converge on one incident; "sector cleared" propagates
so no one double-searches. Core problem = distributed consistency over a laggy mesh.

**Decisions:**
- *PROPOSED* **Command post is the single arbiter** of who-holds-what. Assignment
  **locks** the incident (excluded from further assignment; hidden from other
  responders' available lists).
- *PROPOSED* **Accept race → first-write-wins at the command post.** Two responders
  both tap Accept before the lock propagates → loser gets a graceful "already taken —
  here's the next nearest" + auto-reassign. (Mesh latency makes this likely; must handle.)
- *PROPOSED* **"Cleared" is about the incident, not the place.** Clearing closes the
  incident + auto-closes its duplicate reports + broadcasts "sector cleared" — but a
  **NEW SOS from that area later is NOT suppressed** (could be a new victim).
- *PROPOSED* Coordinator can always **override** (release/reassign) — ties to C4 stuck-timeout.

**Edge cases / sim:** incident color arc red → amber (claimed) → green (cleared); other
responders' available set visibly shrinks — the "coordinated, no overlap" beat.

---

## Component 7 — Sensor-fusion / Corroboration boost `[code]`
**Purpose:** fuse UNO Q water/tilt sensor auto-alerts with human SOS — "a machine and a
human agreeing." Sensor node has **fixed, reliable coords** (good cluster anchor).
**Decisions:**
- *PROPOSED* Sensor alert = envelope (category "sensor") with reading + confidence;
  enters the same pipeline.
- *PROPOSED* **Lone sensor = "possible, investigate"** (moderate urgency) — sensors
  misfire (wind→tilt, rain→water). A human SOS in the same cluster **promotes** it.
- *PROPOSED* **Extreme readings trusted** even without human corroboration (victims may
  be trapped/fled).
- *PROPOSED* Sensor may fire **before** humans → early-warning / pre-position (inform,
  don't over-dispatch).
- **Sim:** sensor ring pulses, human SOS appears in the same area → cluster goes red.

## Component 8 — Capacity tracking `[code]`
**Purpose:** coordinator's at-a-glance "are we keeping up?" — DERIVED read-only view.
**Decisions:**
- *PROPOSED* Computed over registry + queue (no new state): responders
  available/busy/offline; incidents awaiting/assigned/resolved; backlog; avg wait;
  throughput (resolved/hr).
- *PROPOSED* **"Overwhelmed" flag** when backlog > available responders for a sustained
  window → "need more hands" signal + sim escalation beat.

## Component 9 — Status state machine `[code]`
**Purpose:** one lifecycle per incident, command-post-owned, every transition event-logged.
**Decisions:**
- *PROPOSED* States: `new → triaged → assigned → en route → on-scene → resolved`
  (+ terminal `cancelled`/false-alarm, `unreachable`).
- *PROPOSED* **Re-open** (C4 stuck-timeout / responder drop) → back to `awaiting responder`.
- *PROPOSED* Resolved → **archived** (out of active queue, kept for metrics/audit).
- *PROPOSED* **Victim ladder is a projection** of this state (Sending → reached control
  room → help on the way) — single source of truth, no divergence.

---

## Component 10 — LLM tools `[LLM]`
**Purpose:** the ONLY places the model touches the flow — four stateless, scoped functions.
**Cross-cutting guardrails (all four):** forced JSON schema · `reasoning_effort:none`
(Qwen) · **SOS text wrapped as DATA** (text can't change which tool runs or its args,
rule #7) · graceful fallback on failure (never stall) · per-call timeout · cache per SOS.
**Tools:**
- **`assess(sos)`** → `{urgency, category, needs, english, confidence}` — triage/translate
  (built). Fallback = victim's self-reported fields.
- **`same_incident(a,b)`** → `{same, reason}` — dedup confirm, only on code-flagged
  candidates. **Defaults to "not same" on uncertainty** (matches split-bias).
- **`summarize_cluster(members)`** → one-line responder brief. **Grounded** — only the
  given fields, invents nothing, surfaces the worst case.
- **`draft_reply(sos, status)`** → native-language message. **Honest** (no false promises),
  plain text (rule #9); instruction comes from responder/system, not the model.

## Component 11 — Supervised-autonomy agent loop `[code+LLM]`
**Purpose:** the orchestrator that ties it together. **Code-driven, event-triggered** —
the LLM never decides "what to do next" (small models drift in open loops).
**Per event:** `(voice→STT) → assess[LLM] → cluster[code] → dedup-cand[code]→same_incident[LLM]
→ rank[code] → nearest[code] → PROPOSE + summarize_cluster[LLM] → responder Accepts →
de-conflict lock[code] → draft_reply[LLM] → victim "help on the way" → audit-log each step.`
**Decisions:**
- *PROPOSED* **Autonomy levels:** L0 (default) propose→confirm; L1 auto-*notify* nearest
  for high-confidence criticals (still needs tap); **L2 auto-dispatch opt-in, guarded**
  (narrow high-confidence + audit + override).
- *PROPOSED* **Control flow is code** → immune to SOS-content injection; human override
  at every step.
- *PROPOSED* **Burst handling:** queue LLM calls, degrade gracefully, never stall.
- *PROPOSED* **Cache LLM outputs for the scripted sim** (deterministic, flawless playback).

## Component 12 — Prompt-injection / abuse guard `[code]`
**Purpose:** the safety layer for an agent that holds dispatch tools.
**Decisions:**
- **LOCKED (architecture) — structural defense:** code owns ALL control flow +
  assignment, so a hijacked LLM output can NEVER dispatch a responder; the model only
  answers scoped questions, never selects a tool or its args.
- *PROPOSED* Data-tag wrapping of all untrusted text (rule #7) on every tool.
- *PROPOSED* **Validate/clamp every tool output** to schema + ranges (reject bad urgency,
  no responder ids from the LLM).
- *PROPOSED* **PII / rule #10:** raw victim text/coords/errors → log file; only generic
  status on the dashboard; plain-text render (#9); security-sensitive code flagged (#6).
- OPEN: abuse rate-limiting per origin + burst flag = **stretch** (shared with C2).
- Empirical: inject-fire benchmark showed the models resist "ignore instructions."

## Component 13 — Metrics + audit log `[code]`
**Purpose:** instrumentation from hour 1 — deck numbers, explainability, sim AI-panel.
**Decisions:**
- *PROPOSED* **Audit log** — append-only; each automated decision with inputs + *why* +
  tool/code + confidence → feeds sim AI-activity panel, judge explainability, debugging,
  (stretch) Cloud-AI-100 post-incident report.
- *PROPOSED* **Metrics** — per-stage latency (STT/assess/cluster/total), **tokens/s
  NPU-vs-CPU** (provable-NPU numbers), queue depth, backlog, throughput, avg response
  time → `/metrics` endpoint → deck numbers panel.
- *PROPOSED* Cheap/async (never slows the pipeline); no secrets/PII to screen.

---

## Open decisions awaiting confirmation
- C1: two-lane no-GPS · split-bias · cluster-level dispatch — *PROPOSED, unconfirmed.*
- C2: dedup-vs-corroboration split · merge policy · abuse = stretch — *PROPOSED, unconfirmed.*
- C3: severity-tier-first · FIFO+bounded-aging · low-confidence=flag · no category weights — *PROPOSED, unconfirmed.*
- C4: fields · stale→offline · capability=soft · stuck-timeout re-open (X≈10m) · one-per-incident — *PROPOSED, unconfirmed.*
- C5: greedy-by-priority · haversine+approx-ETA · awaiting-responder surfaced · propose+confirm — *PROPOSED, unconfirmed.*
- C6: command-post-arbiter · first-write-wins · cleared≠suppress-area · coordinator override — *PROPOSED, unconfirmed.*
- C7: sensor envelope · lone=investigate · extreme=trust · early-warning — *PROPOSED, unconfirmed.*
- C8: derived view · overwhelmed flag — *PROPOSED, unconfirmed.*
- C9: state set · re-open · archive resolved · victim-ladder=projection — *PROPOSED, unconfirmed.*
- C10: 4 stateless tools · forced-JSON · data-tag · same_incident defaults not-same · grounded/honest — *PROPOSED, unconfirmed.*
- C11: code-driven event loop · autonomy L0/L1/L2(opt-in) · burst-graceful · cache-for-sim — *PROPOSED, unconfirmed.*
- C12: structural defense LOCKED · data-tag · clamp outputs · PII-to-file · abuse=stretch — *PROPOSED, unconfirmed.*
- C13: append-only audit log · latency+tokens/s+counts metrics · async — *PROPOSED, unconfirmed.*

## Status: ✅ all 13 components drafted (10 Jul 2026)
Full spec complete. **Next:** a quick thumbs-up / tweak on the C1–C13 "Open decisions"
above locks the foundation, then build the `[code]` services first (C1–C9, C13) —
they're deterministic, testable, and independent of the frontend + the LLM.
