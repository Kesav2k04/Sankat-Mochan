# Mesh Transmission Spec — Pi uplink priority + parallelism

**Scope:** `raspberrypi/uplink.py`, `node.py`, `ble_link.py`, `gateway.py` — ALL Pi-side comms
(RX ingest, envelope uplink, dispatch/NACK return path, voice, peer/status).
**Goal:** every channel is parallel, fast, RELIABLE ("always gets through, never wedged")
and DoS-resistant ("degrades gracefully under flood"); SOS is always first; no regressions.

§1–3 = the voice-vs-SOS head-of-line bug (original scope). §4 = all-comms reliability +
DoS hardening (broadened scope). §5 = risks, then open questions.

---

## 1. The core bug (must fix)

`EdgeUplink._sender` (`uplink.py:372`) runs one serial flush loop per wake:

```
_flush (envelopes/WS) → _flush_voices (blocking HTTP, to_thread) → _flush_peer_states → _flush_status
```

`_flush_voices` (`uplink.py:393`) holds `_voice_flush_lock`, iterates every pending clip,
and awaits a **120 s-timeout blocking HTTP POST** (`_post_voice`, `uplink.py:404`) one clip
at a time. Until that returns, the *next* `_wake` is not serviced — so a newly-enqueued
**urgency-5 SOS sits in SQLite undelivered behind a slow/large voice upload.** This
directly violates requirement (1): the SOS channel is not guaranteed.

Note the envelopes themselves are already durable + WS-fast (`send_envelope` → SQLite →
`_wake`); the only thing starving them is sharing the sender coroutine with voice.

---

## 2. Ranked changes

### C1 — Split voice upload into its own task (BLOCKER)
**`uplink.py: EdgeUplink.run` + new `_voice_uploader` task; `_sender` loses `_flush_voices`.**
- `_sender` becomes: `_flush(ws)` → `_flush_peer_states(ws)` → `_flush_status(ws)` only.
  These are small JSON WS sends; the SOS path is now never behind HTTP.
- Add a **long-lived** `_voice_uploader(stop)` task, created once in `run()` alongside
  `reader`/`sender` and cancelled with them on disconnect. It waits on a dedicated
  `asyncio.Event` (`_voice_wake`) — set by `send_voice_chunk` on clip-complete and by the
  reconnect path — then drains `voice_outbox.pending()`.
- **Why:** physically decouples the blocking HTTP path from the WS/envelope path on the
  event loop. Voice is HTTP-to-a-different-endpoint (`/mesh_voice`) already, so no ordering
  contract is broken by separating them.

### C2 — Bounded parallel voice uploads (BLOCKER, pairs with C1) — ADJUDICATED
**`uplink.py: _flush_voices` → single consumer, dedicated pool, semaphore. NO lock, NO set.**
- **Single consumer (Critic B1):** the C1 `_voice_uploader` is the *only* caller of
  `_flush_voices`. A single long-lived consumer needs neither `_voice_flush_lock` nor an
  `_inflight_clips` set — **drop both.** The earlier "lock OR set-guard" was racy (double-POST
  + ack/unlink race vs a NACK-repaired clip reusing an id). One consumer removes the hazard by
  construction.
- Within one pass, drain concurrently under `Semaphore(cfg.voice.upload_concurrency)`; ack
  each clip on its own 2xx; failures leave that clip queued (unchanged durability).
- **Dedicated thread pool (Critic B2 — MANDATORY, see C4b):** the voice posts run on a
  dedicated `ThreadPoolExecutor`, NOT the default pool. Semaphore size == pool `max_workers`.
- **Why:** requirement (2)/(3) fast; multiple victims' clips upload concurrently. Single
  consumer + dedicated pool is what makes C1's decoupling real rather than cosmetic.

### C3 — Priority ordering within the envelope flush (MAJOR)
**`uplink.py: DurableOutbox.pending` already `ORDER BY urgency DESC, ts ASC`** — good, keep.
- Confirm `_flush` sends in that order (it does — iterates `pending()`). No change needed
  beyond a comment asserting urgency-5-first is load-bearing.
- **Edge:** on a *fresh* enqueue mid-flush, `_wake` is re-set and the next pass re-reads
  `pending()` (freshly ordered). Since `_flush` re-queries each pass, a new urgency-5
  overtakes queued lower-urgency envelopes on the following pass — acceptable (sub-second).

### C4 — Per-upload timeout is far too long (MAJOR)
**`uplink.py: _post_voice` timeout=120 → connect+read tuple e.g. `(5, 30)`.**
- 120 s on a LAN command post means one dead/slow AI-PC pins an uploader worker for two
  minutes. With C1 that no longer blocks SOS, but it still stalls *other voice*. Use
  `requests` `timeout=(connect_s, read_s)` from `cfg.voice`. Clip stays queued on timeout
  (already handled).
- **Accepted degradation (Critic M1):** with the dedicated pool of N workers, N dead-AI-PC
  posts pin the whole voice pool for `read_s` and voice throughput → 0 while the AI-PC is
  unreachable. This is ACCEPTABLE (voice is not life-safety-critical; SOS is on its own
  path). Documented so nobody "fixes" it by enlarging the pool back into radio contention.

### C4b — Dedicated voice thread pool (BLOCKER — Critic B2) — CROSS-OWNER CONTRACT
**New `ThreadPoolExecutor` for voice posts; default executor reserved for radio.**
- `LoRaLink.send` (`node.py:138`) uses `run_in_executor(None, ...)` = the **default** pool
  (`min(32, cpu+4)`, ~8 on a 4-core Pi). Voice `to_thread` (`uplink.py:398`) also uses the
  default pool. A forwarded 45-chunk voice clip = 45 executor jobs; add semaphored voice
  posts each blocked up to `read_s` and the default pool is exhausted → **radio TX cannot
  get a thread → SOS re-broadcast stalls.** This DEFEATS C1, so it's a BLOCKER not a MAJOR.
- Fix: create a bounded `ThreadPoolExecutor(max_workers=cfg.voice.upload_concurrency)`; pass
  it explicitly to the voice posts (`loop.run_in_executor(voice_pool, ...)` instead of
  `to_thread`). Leave the default pool exclusively for radio `run_in_executor`.
- **CONVERGED NUMBERS (contract 1) — SIGNED OFF by Mesh + Voice:** default pool = radio
  only; dedicated voice pool `max_workers = 2`; semaphore = 2 (== pool size). Rationale: 2
  gives voice parallelism (enough for the STT+translate legs, per Voice) without starving an
  ~8-worker default pool that must absorb 45-job voice-clip forwards + dispatch/NACK + SOS
  re-broadcast. `/voice_sos` ACKs the Pi before STT/triage and treats voice as best-effort,
  so the throughput→0-while-AI-PC-down degradation is confirmed acceptable. Documented so
  the split is deliberate, not accidental.

### C5 — `MeshNode._seen` is unbounded (MAJOR — DoS / memory)
**`node.py: MeshNode._seen: set[str]`** grows forever; every distinct envelope id (incl.
attacker-forged ids over BLE/LoRa, untrusted per CLAUDE.md #8) is retained for the
process lifetime.
- Bound it: LRU/ring (e.g. `OrderedDict` capped at N=4096, evict oldest) or age-based
  prune. Dedup only needs a recent window — mesh TTL/hops bound how long a dup can loop.
- **Why:** long-running gateway + hostile RF = memory exhaustion. Also `_seen_lock` is a
  `threading.Lock` taken from the loop thread + radio callback thread — keep the lock,
  just cap the container.

### C6 — Voice upload input already validated; tighten (MINOR, confirm)
- `VoiceUploadOutbox.pending` (`uplink.py:211`) skips `len(audio) > 110_000` and empty —
  good (size bound). `VoiceAssembler` caps `MAX_IN_FLIGHT=8` and drops shape-mismatched
  frames — good.
- **Path traversal — checked, SAFE, no action.** `audio_name` derives from `clip_id`
  (`uplink.py:196-208`) which is `f"{origin}-v{seq}"` (`envelope.py:164`). `origin` is
  forced alnum by `_origin_of` (`envelope.py:214`) and `seq` is a `struct`-unpacked int, so
  `clip_id` can only be `[A-Za-z0-9]+-v<int>` — no `/`, `..`, or NUL reaches the filesystem.
  Nothing to sanitise. (Documented so a future refactor that loosens `clip_id` re-triggers
  the review — CLAUDE.md #6.)

### C7 — Voice uploader wake on reconnect (MINOR)
**`uplink.py: run` reconnect block** currently calls `_flush_voices()` inline after connect
(`uplink.py:340`). After C1 that's gone — instead `set()` `_voice_wake` on connect so the
new uploader task drains anything that queued while offline. **ADJUDICATED (open Q1): gate
voice on uplink-up** — if the PC is unreachable, HTTP voice fails too, so don't hammer a
dead host. The `_voice_uploader` only runs while the WS is connected; on reconnect, `set()`
`_voice_wake` to drain the backlog.

---

## 3. Fan-out (requirement 2) — already correct, no change

`gateway.on_accept` → `edge.send_envelope` (instant, non-blocking SQLite enqueue) fans the
SOS to the AI PC; `node._forward` (`node.py:235`) does `asyncio.gather` across all links
except source — LoRa responder fan-out is already parallel and off the accept path. The
only shared cost is `_AIRWAVES` (`node.py:35`), a single TX lock (physically required —
both antennas one channel). That serialises *air time*, not the accept path. **Leave it.**

Risk to note: a large voice clip (45+ chunks) forwarded over LoRa holds `_AIRWAVES`
repeatedly and can delay an SOS *re-broadcast* on the same radio. This is now **in scope**
(user wants all-air reliability) — see D3 in §4.

---

## 4. All-comms reliability + DoS hardening

Reliability target across EVERY channel: *always gets through, never wedged, degrades
gracefully under flood*. The five channels are: (A) RX ingest BLE/LoRa, (B) envelope
uplink WS→AI-PC, (C) dispatch/NACK return path, (D) voice, (E) peer/status. Voice (D) is
covered by C1–C7. Below are the rest, ranked.

### D1 — RX ingest flood: unbounded task spawn per BLE notification (BLOCKER)
**`ble_link.py: BleManager._keep_connected.handler` (`ble_link.py:318`)** does
`asyncio.create_task(on_bytes(bytes(data)))` on **every** notification with no bound. A
phone (or spoofed peripheral) firing notifications in a tight loop spawns unbounded tasks
→ event-loop + memory DoS; each task also races into `_accept`/`_forward`.
- Fix: feed RX into a **bounded `asyncio.Queue` per MeshNode** (`maxsize` e.g. 256; one
  queue per node preserves the two-node loop-freedom isolation — `node.py` docstring)
  drained by a single worker; drop-newest when full and count the drop (chainlog
  `DROP reason=rx_overrun`). Never `create_task`-per-frame.
- **Global ingest cap (Critic M4 — the real DoS defence):** at the intake worker, enforce a
  **spoof-proof global frames/sec cap across ALL origins**. This cannot be evaded because it
  trusts no identity field. This is the BLOCKER-grade control; per-origin (D2) is fairness
  on top, not the backstop.
- **Why:** decouples radio/BLE callback rate from accept-loop capacity; a spammer can fill
  a bounded queue but cannot exhaust memory or the task scheduler. Same pattern protects
  the LoRa RX path (`gateway.py:362-364` `run_coroutine_threadsafe` per packet — also
  unbounded; route both through the same bounded intake).

### D2 — Per-origin rate cap (MAJOR — demoted below D1's global cap, Critic M4)
**New guard in the D1 intake worker, keyed on `msg.origin`, applied AFTER dedup.**
- Token-bucket per `origin` (generous N msgs / window), applied **after dedup** (Critic Q7:
  before-dedup punishes legit retransmits). Over-budget → `DROP reason=rate_limited`, not
  forwarded. Bucket table bounded (LRU, ~256 origins).
- **Not the backstop:** `origin` is unauthenticated — an attacker forges a fresh alnum
  `origin` per frame and each gets its own full bucket, so per-origin alone does nothing
  against a spoofed flood. The **global cap in D1 is the real control**; per-origin is a
  fairness measure so one *honest* origin can't crowd others. (Critic M4.)
- Size is already bounded (`envelope.decode` caps `MAX_BYTES` + field clamps; voice
  `MAX_VOICE_CHUNK`/`MAX_VOICE_CHUNKS`); malformed dropped pre-dedup (`node.py:187`) — keep.
- **Security-sensitive (CLAUDE.md #6, #8) — human review.**

### D3 — Voice-vs-SOS air contention (MAJOR — CONVERGED CONTRACT w/ Voice owner)
**`node.py: LoRaLink` + `_AIRWAVES` (`node.py:35`); voice repeats via `LoRaLink.set_repeats`
(`gateway.py:355`).** Today every `send()` grabs `_AIRWAVES` first-come; a 45-chunk voice
clip or a burst of dispatches/NACKs can hold the air while a fresh urgency-5 SOS
re-broadcast waits behind it. Agreed split of ownership: **Mesh owns the LoRa-path fix;
Voice owns reassembly/consumption only** (consumes at `/voice_sos`, unchanged).

Converged two-part contract:
1. **`tx_repeats=1` for voice chunks (NOW).** Voice's NACK repair loop already re-requests
   any dropped chunk, so blind LoRa repeats are redundant airtime for voice. Keep
   `tx_repeats>1` **only for the SOS text frame** (must land fast, no round-trip). Impl:
   voice chunks must send with repeats=1 regardless of `cfg.lora.tx_repeats` — either a
   per-message repeat override on `LoRaLink.send`, or the gateway sets repeats per frame
   type. (`set_repeats` is currently link-global — needs a per-frame path.)
2. **Small inter-chunk yield (NOW).** Between voice chunks, release `_AIRWAVES` and yield so
   an incoming SOS can grab the air mid-clip rather than waiting out all 45 chunks. A short
   `await asyncio.sleep(0)`/tiny delay between chunk sends is enough for the demo.
3. **Full urgency-aware priority TX queue — DEFERRED (agreed).** The complete fix (single
   consumer per radio, `(urgency, seq, raw)` priority heap, SOS jumps voice/NACK, bounded
   with drop-lowest-oldest) is the production answer but out of scope for now; 1+2 give the
   guarantee cheaply. Flagged as the follow-up.
- **Why:** 1 cuts voice airtime ~Nx with zero reliability loss (NACK covers gaps); 2 stops
  a clip head-of-line-blocking an SOS on the air. Both preserve loop-freedom and the "one
  radio keys at a time" invariant. Confirmed converged with Voice owner.

### D4 — Outbox disk DoS: cap + refuse-new, NEVER evict (MAJOR) — ADJUDICATED (Critic M3)
**`uplink.py: DurableOutbox.enqueue` (`uplink.py:53`).** `INSERT OR REPLACE` keys on
`type:id`, so retries of the *same* SOS are idempotent (good) — but a spammer forging
distinct `i` values creates unbounded rows → SD-card DoS, and `_flush` replays them all on
reconnect.
- **NEVER evict an already-accepted envelope.** Silent eviction + reconnect `_flush` means
  an operator watches "N queued" quietly shrink — a data-loss path in the one thing that
  must never lose data. Instead: **cap the outbox; on overflow, REFUSE new low-urgency
  enqueue and log loudly** (`send_envelope` returns/records a rejection). An accepted SOS is
  never dropped.
- D1's global ingest cap + D2 upstream are the real defence; D4 is just a bounded backstop
  that fails safe (refuse-new) rather than lossy (evict-old).
- **Why:** durability must not become an attacker's unbounded write primitive, but the fix
  must not itself introduce SOS loss. Confirm AI-PC dedups by id so replay is safe (§5).

### D5 — Dispatch/NACK return path reliability (MAJOR)
**`gateway.py: on_dispatch` (`gateway.py:308`) → `gw.originate` (`node.py:255`); voice
NACK via `voice_nack_sweeper` → `gw.originate` (`gateway.py:255`).**
- `on_dispatch` already null-checks the decode and swallows nothing silently — good. But
  `originate` → `_forward` → LoRa `send` inherits the same air-contention as D3. With the
  full priority queue DEFERRED (D3.3), dispatch/NACK just live under the same cheap D3
  mitigation (they're small, and NACK is already low-value); no queue re-arch for the demo.
- **Rate-safety:** a flood of dispatches from a compromised/buggy AI-PC could saturate the
  air. Apply a modest send-side rate cap on the return path (dispatches/sec) with the
  same drop-and-log discipline.
- **Reliability gap:** the downlink ACK to the AI-PC (`_reader`, `uplink.py:441`) only
  fires after `on_dispatch` completes; if `originate` throws it's caught in `_accept`
  (`node.py:229`) so the mesh survives, but confirm the AI-PC re-sends unacked dispatches
  (its buffer clears only on our ACK — good, symmetric with the outbox).

### D6 — Liveness / watchdog: heartbeat + LOG-ONLY for demo (MAJOR) — ADJUDICATED (Critic M6)
Radios already have `radio_watchdog` (`gateway.py:102`). The *software* pipelines do not.
- Add the cheap, high-value half NOW: `_sender`, `_voice_uploader`, and each RX intake
  worker bump a monotonic `last_progress` timestamp; a supervisor (or extend
  `radio_watchdog`) **logs and alerts** when a loop hasn't ticked in T seconds.
- **Auto-restart DEFERRED (post-demo).** A restart loop can mask a genuinely wedged radio,
  and a human is in the room for the demo. Log-and-alert only; cancel+recreate is post-demo.
- WS `ping_interval=15` already exists (`uplink.py:335`); add `ping_timeout` so a half-open
  socket is torn down promptly.
- **Why:** detect the wedge cases without a restart loop hiding a hard fault during the event.

### D7 — Global resource bounds (MAJOR — audit)
Single checklist so no input pattern OOMs/hangs the gateway:
- `MeshNode._seen` — cap (C5). `_sos_context` — already capped 64 (`uplink.py:268`), good.
  `_peer_states` — bounded by `set_peer_state` validation (`uplink.py:317`), good.
- RX intake queues — bounded (D1). Outbox rows — bounded, refuse-new (D4). TX priority
  queue — DEFERRED (D3.3). `voice_outbox` disk — bounded (§5 backpressure). Rate-limiter
  tables — bounded (D2). Global ingest cap (D1/M4).
- Thread pool — dedicated bounded voice pool (spec §4) so `to_thread` can't starve LoRa.
- Sockets — one WS; `requests.Session` per `_post_voice` is created per call
  (`uplink.py:408`), fine but reuse a module-level session under the voice pool to avoid
  connection churn under load (MINOR).

---

## 5. Risks / edge cases

- **Event-loop starvation via `to_thread` — RESOLVED as C4b:** dedicated voice pool
  (`max_workers=2`), default pool reserved for radio. No longer a "pick one".
- **Ordering:** voice clips are independent; no cross-clip order contract. Within a clip,
  reassembly is index-based, not arrival-order — safe to parallelise across clips.
- **Partial upload:** `_post_voice` acks only on 2xx; tmp-file + `replace()` in
  `enqueue` is atomic — a crash mid-write leaves a `.tmp` ignored by `pending()`'s `*.json`
  glob. Good. Confirm `.tmp` files are eventually GC'd (currently they aren't — MINOR leak
  on repeated crashes).
- **Reconnect:** envelope replay (`_flush`) is idempotent (Mac dedups by id); voice ack is
  local-only (file unlink on 2xx) so a lost ACK re-uploads a clip — AI-PC must dedup voice
  by `clip_id`/`ref_id` (confirm receive side does).
- **Backpressure:** `voice_outbox` is unbounded on disk. A flood of chunks (or NACK repair
  storms) could fill the SD card. Bound `voice_outbox.count()` or reject enqueue past a cap
  (MAJOR for production; MINOR for demo).

---

## OPEN QUESTIONS — ALL ADJUDICATED (Critic CRITIQUE.md + cross-owner convergence)

1. **Voice while WS down?** → **Gate on uplink-up** (C7). If PC down, HTTP voice fails too.
2. **Concurrency / pool?** → **Dedicated voice pool, `max_workers=2`** (C4b/B2). Mandatory.
3. **`_seen` cap?** → **`OrderedDict` ring, N=4096, evict oldest** (C5). MAX_HOPS bounds dup lifetime.
4. ~~`clip_id` sanitisation~~ → RESOLVED: `envelope.py` constrains it; not exploitable.
5. ~~Voice-vs-SOS on the LoRa air~~ → **cheap mitigation (repeats=1 + inter-chunk yield); full priority queue DEFERRED** (D3/M2).
6. **RX intake granularity?** → **One bounded queue per MeshNode** (D1). Preserves loop-freedom.
7. **Rate-limit policy?** → **After dedup, per-origin generous bucket + spoof-proof GLOBAL frames/sec cap** (D1/D2/M4). Global cap is the real defence.
8. **Watchdog?** → **Heartbeat + log-and-alert only for demo; auto-restart post-demo** (D6/M6).
9. **Outbox eviction?** → **NEVER evict an accepted envelope; cap + refuse new low-urgency** (D4/M3). Product call made.

No open questions remain. Ranking → see §6.

---

## 6. Must-ship (demo) vs deferred (post-demo)

**Must-ship — Mesh (life-safety + demo-critical, low risk):**
- C1 split voice into a long-lived single-consumer uploader **+ B1 (no lock, no set)**.
- C4b dedicated voice `ThreadPoolExecutor(max_workers=2)` — without it C1 is defeated.
- C2 bounded parallel uploads (semaphore=2, ack per 2xx). C4 timeout tuple `(5,30)`.
- D1 bounded RX intake queue per MeshNode **+ M4 global ingest cap** — the real DoS defence.
- C5 bounded `_seen` (OrderedDict N=4096). C7 gate voice on WS-up.
- D3 cheap air mitigation: voice `tx_repeats=1` + inter-chunk yield (cross-owner w/ Voice).
- D4 outbox cap + refuse-new-low-urgency (never evict). D6 heartbeat + log-only.

**Deferred — post-demo:** D3 full priority TX queue; D4 eviction (shipped refuse-new instead);
D6 auto-restart; D2 per-origin bucket beyond the global cap; `.tmp` startup sweep + shared
`requests.Session` (both MINOR).
