# CRITIQUE — mesh-transmission.md & voice-pipeline.md

Reviewer: Critic. Both specs treated as guilty until proven. Claims verified against
actual code (`pi-code/uplink.py`, `node.py`, `ble_link.py`, `gateway.py`, `envelope.py`;
`command-post/app.py`, `intelligence.py`, `triage.py`, `stt.py`, `database.py`,
`web/src/components/IncidentDetail.jsx`). Findings ranked BLOCKER / MAJOR / MINOR.
Line refs are from the code as read today.

---

## What the specs got RIGHT (verified, no action)

- **Mesh C6 path-traversal SAFE — CONFIRMED.** `clip_id = f"{origin}-v{seq}"` (envelope.py:164),
  `origin` forced alnum (`_origin_of`, envelope.py:214), `seq` a struct int. `audio_name`
  (uplink.py:196-208) can only be `[A-Za-z0-9]+-v<int>.(3gp|ogg)`. No `/`, `..`, NUL. Correct.
- **Mesh C1 diagnosis — CONFIRMED.** `_sender` (uplink.py:372) does serial
  `_flush → _flush_voices → _flush_peer_states → _flush_status` per wake, and `_flush_voices`
  (uplink.py:393) holds `_voice_flush_lock` and awaits `_post_voice` (timeout=120, uplink.py:416)
  one clip at a time. A fresh SOS in the outbox genuinely waits behind voice HTTP. Real bug.
- **Mesh D1 unbounded task spawn — CONFIRMED.** ble_link.py:318-319 `create_task(on_bytes(...))`
  per notification, no bound. gateway.py:363 `run_coroutine_threadsafe` per LoRa pkt, no bound. Real DoS.
- **Mesh C5 `_seen` unbounded — CONFIRMED.** node.py:146 `self._seen: set[str]`, only ever `.add`. Grows forever.
- **Voice BUG1 playback — CONFIRMED.** `/audio` serves raw `audio/3gpp` (app.py:418); AMR unplayable in browsers.
- **Voice BUG2 hallucination — CONFIRMED.** `_transcribe_mesh_voice` (app.py:380) feeds transcript
  into `triage.triage`, whose disaster prompt (triage.py:34-49) pattern-completes to disaster content;
  `attach_voice` (intelligence.py:244,249) promotes that `english` to primary text for voice-only reports.
- **Voice ffmpeg pattern SAFE — CONFIRMED.** `_ffmpeg_to_wav16k` (stt.py:47-58) is list-argv,
  `pipe:0`/`pipe:1`, no `shell=True`. Reusing it for `transcode_for_web` is injection-safe.

---

## BLOCKER

### B1 — Mesh C2 set-guard is racy AND drops the lock's real job (uplink.py `_flush_voices`)
Spec §2 C2 says "prefer the set-guard over `_voice_flush_lock`, add clips to `_inflight_clips`."
But it never says the guard must be **checked-and-added atomically before the `await`, then removed
in `finally`**. If written naively (`if clip in inflight: skip; ... await post; inflight.discard`)
two uploader passes (C7 reconnect wake + a `send_voice_chunk` wake firing during a long post)
can both read `pending()`, both see the same clip absent from the set, and **double-POST it**.
That is not just wasted work: the AI-PC dedups voice by `clip_id`, so a duplicate is *tolerable*,
but `voice_outbox.ack` (uplink.py:225) `unlink`s the file — if pass A acks/unlinks while pass B is
mid-post reading that file, pass B's `read_bytes()` in `pending()` already happened, so B posts
stale bytes then acks an already-gone file (suppressed OSError, uplink.py:226) — benign — BUT the
real hazard is B re-enqueue racing a *new* clip with the same id after a NACK repair completes.
**Fix:** keep it single-consumer instead. The whole reason C1 makes `_voice_uploader` a *long-lived
single task* is that one consumer needs no lock and no set. Drop BOTH the lock and the set; the one
uploader task drains serially-per-pass but concurrently-within-a-pass via the semaphore (C2), and
nothing else ever calls `_flush_voices`. Spec's "OR" muddies this — **decide: one uploader task, no
lock, no set.** (This also resolves Open Q2's re-entrancy worry for free.)

### B2 — Mesh C2 semaphore + `to_thread` on default executor can starve LoRa TX (uplink.py + node.py:138)
Spec §5 flags this as a MAJOR "pick one" but it is a **BLOCKER**: `LoRaLink.send`
(node.py:138) does `run_in_executor(None, ...)` — the **default** ThreadPoolExecutor. Voice
`asyncio.to_thread` (uplink.py:398) also uses the default executor. On a Pi the default pool is
`min(32, cpu+4)` = ~8 on a 4-core Pi, fewer on a Pi Zero. `Semaphore(3)` voice posts each blocked
120 s (or even the fixed C4 30 s) can occupy 3 workers; a burst of LoRa TX (a 45-chunk voice clip
being *forwarded* is 45 executor jobs) plus dispatch/NACK can exhaust the remainder → **radio TX
literally cannot get a thread → SOS re-broadcast stalls.** This defeats the entire point of C1.
**Fix (mandatory, not "pick one"):** give voice its own bounded `ThreadPoolExecutor(max_workers=N)`
and pass it explicitly to the voice posts; leave the default pool exclusively for radio. Adjudicates
Open Q2 → **dedicated voice pool, not a shared-pool semaphore.**

### B3 — Voice BUG2 fix still lets urgency come from the disaster prompt on unrelated speech
Spec §2 BUG2 step 3 keeps calling `triage.triage(voice_english)` for urgency/category and only
discards its `english`. But the disaster prompt (triage.py:34) will still assign **urgency 4-5 and
category=trapped to "mic testing one two three"**, and `attach_voice` (intelligence.py:250)
does `report["urgency"] = max(report["urgency"], ai.urgency)` — so a benign voice clip **escalates
the incident's urgency** even though the hallucinated *text* is suppressed. The card no longer shows
the lie in prose, but the triage bar/rank still reflects it. **Fix:** for voice-only or clearly
non-emergency transcripts, do not let a second disaster-triage call *raise* urgency. Either (a) run
translate-only and reuse the *original SOS's* urgency (the typed SOS already carried the real
urgency), or (b) if you must re-triage, cap: voice may *corroborate* but not *raise* urgency above
the typed report's own AI urgency. Recommend (a): **one translate call, no second triage call for
voice.** This also adjudicates Open Q3 → **one call (translate), not two.**

### B4 — Voice `.web` DB scheme collides with a real future clip_id and pollutes provenance
Spec BUG1 stores the transcoded copy as a second row keyed `clip_id=f"{clip_id}.web"`
(voice-pipeline.md:39). `clip_id` on the wire is `f"{origin}-v{seq}"` (envelope.py:165). The DB
unique key is `(session_id, clip_id)` (database.py:42). `"abc-v7.web"` is not currently a legal wire
clip_id (seq is an int, no dot), so **no collision today** — but this silently overloads the clip_id
namespace with a derived value, and `store_voice` (database.py:119) records it with `origin`, `codec`,
`report_id` as if it were a *received clip*, so `list_sessions` voice counts (database.py:162) and any
audit/replay-to-responder now double-count and can replay a *transcoded* artefact as if it were the
original recording — a provenance corruption in a life-safety audit trail.
**Fix:** do NOT create a second clip_id row. Add `web_audio BYTEA` + `web_content_type TEXT` columns
to `command_post_voice_messages` and serve them via a distinct route (e.g. `/audio/{clip_id}?web=1`
or `/web_audio/{clip_id}`). Adjudicates Open Q2(voice) → **schema column, not a `.web` row.** Yes it's
a migration, but the table is `CREATE TABLE IF NOT EXISTS` and sessions are ephemeral per-run, so the
migration cost is near-zero pre-demo.

---

## MAJOR

### M1 — Mesh C4 timeout tuple still pins a voice-pool worker; needs the pool bound too
C4 (30 s read) is right but insufficient alone: with B2's dedicated pool of size N, N dead-AI-PC
posts pin the whole voice pool for 30 s and no voice moves. Fine (voice is not life-safety-critical),
but **document that voice throughput degrades to zero while the AI-PC is unreachable and that this is
acceptable** — do not let a future reader "fix" it by enlarging the pool back into radio contention.

### M2 — Mesh D3 priority TX queue is the single biggest demo risk; SCOPE IT DOWN
Replacing `_AIRWAVES` (node.py:35) — a `threading.Lock` taken from `_send_blocking` running in an
executor thread — with a "single consumer task owns the radio + priority queue" is a **substantial
re-architecture** of the hot path that currently works. `_send_blocking` also does CSMA, radio
recovery (`_recover`, node.py:88), and `_repeats` retries inside the lock. Moving all that into a
consumer task, marshalling producers' results back (the callers `await link.send()` and branch on the
bool return — node.py:246), and getting cancellation right under disconnect is easy to get subtly
wrong under time pressure. **Real trade-off, real risk.** Recommend: **do NOT build the full priority
queue for the demo.** Cheaper 80% fix that keeps the existing lock: make voice-chunk forwarding
*yield* — enqueue voice TX at low priority only by having the voice path acquire `_AIRWAVES` with a
"defer if an SOS is waiting" flag is still complex; simplest safe win is **transmit SOS/dispatch with
`tx_repeats` but transmit voice chunks with repeats=1 and a small inter-chunk sleep**, so a voice
clip cannot monopolise the air for 45×N frames back-to-back. Keep D3-full as a post-demo item.

### M3 — Mesh D4 outbox eviction can drop an SOS the operator believes is queued
D4 evicts "lowest-urgency, oldest" at a row cap. But the spec's own Open Q9 correctly notes this is a
**product decision for a life-safety system**. Silent eviction + the reconnect `_flush` (uplink.py:368)
means an operator sees "N queued" that quietly shrinks. **Adjudication:** for the demo, **do not evict.
Cap the outbox and, on overflow, refuse NEW low-urgency enqueue and log loudly (never drop an
already-accepted envelope).** D2 rate-limiting upstream is the real defence; D4 eviction is
over-engineering that introduces a data-loss path into the one thing that must never lose data.

### M4 — Mesh D2 rate-limit-after-dedup is right, but token buckets keyed on `origin` are spoofable
Open Q7 leans "after dedup" — correct (before dedup punishes legit retransmits). BUT the spec's own
security note (D2) says origins are *unauthenticated* — an attacker forges a fresh `origin` per frame
(alnum, ≤ chars) and **every frame gets its own fresh full bucket**, so per-origin limiting does
nothing against the actual flood vector. The LRU cap (~256 origins) just means the attacker churns the
bucket table. **Fix:** keep per-origin as a fairness measure, but the real backstop must be a
**global ingest rate cap** (frames/sec across all origins) at the D1 intake worker — that one cannot
be spoofed because it doesn't trust any identity field. Make the global cap the BLOCKER-grade control
and per-origin the nice-to-have.

### M5 — Voice: `attach_voice` overwrites `report["ai"]`/`rationale`/`latency_ms` from the voice call
Even after BUG2, `attach_voice` (intelligence.py:253-255) unconditionally sets `rationale`, `ai`,
`latency_ms` from the voice `ai` dict, **clobbering the typed SOS's original triage rationale** when
a voice clip arrives for a report that already had typed text. So the card's rationale flips from the
real typed-SOS reasoning to the voice-derived one. With B3's "one translate call, no triage", there is
no voice `ai` dict at all — good — but then the code path `report["rationale"] = (ai or {}).get(...)`
would blank it. **Fix:** when a report already has a typed gist, `attach_voice` must NOT touch
`urgency`/`rationale`/`ai`/`latency_ms` — only add `audio`, `voice_transcript`, `voice_english`.
Restrict the mutation block to the voice-only branch.

### M6 — Mesh D6 watchdog auto-restart risks masking a hard fault
Open Q8 leans "restart with backoff + capped attempts" — accept, but the demo risk is a restart loop
hiding a genuinely wedged radio. Adjudication: **implement the heartbeat/`last_progress` timestamps
(cheap, high value) but make the watchdog LOG-AND-ALERT only for the demo**, not auto-restart. A human
is in the room. Auto-restart is post-demo. This is over-engineering for the event window.

---

## MINOR

- **Mesh MINOR (real):** `.tmp` leak — `VoiceUploadOutbox.enqueue` (uplink.py:204) writes
  `.{name}.tmp`; a crash between the two `replace()` calls (audio at :208, meta at :209) can leave an
  orphan `.3gp` with no `.json` (or vice-versa). `pending()` globs `*.json` so an orphan audio is
  invisible but never GC'd. Add a startup sweep of `*.tmp` and audio files with no matching `.json`.
- **Mesh MINOR:** `_post_voice` (uplink.py:408) makes a new `requests.Session()` per call. Under a
  dedicated pool this is connection churn; reuse one module-level session. Trivial.
- **Voice MINOR — `/audio` validator is fragile, not wrong.** app.py:408
  `name.replace("-","").replace(".","").replace("webm","").isalnum()` currently *does* accept `.web`,
  `.webm`, `.wav` (verified). But the `.replace("webm","")` hack means a clip literally containing
  "webm" in its id would pass odd strings. If B4's schema-column fix lands, `.web`/`.webm` names never
  hit `/audio` at all and this validator can stay unchanged. If you keep file-mode `.webm`/`.wav`,
  **add `wav` to the strip and prefer an explicit allow-list suffix check** over the replace-chain.
- **Voice MINOR:** `transcode_for_web` `timeout=15` (voice-pipeline.md:34) is good; also assert
  `stt.py` startup probe caches `_web_format()` result so we don't fork ffmpeg per clip to re-probe.

---

## OPEN QUESTIONS — adjudicated

**Mesh**
1. Voice while WS down? → **Gate on uplink-up.** If the PC is down, HTTP voice fails too; don't hammer.
2. Concurrency bound / dedicated pool? → **Dedicated voice pool (B2). Mandatory, not optional.**
3. `_seen` cap? → **`OrderedDict` ring, N=4096, evict oldest.** Mesh TTL (MAX_HOPS) bounds dup lifetime; 4096 » any real loop window.
4. clip_id sanitisation → already resolved, agree.
5. Voice-vs-SOS air → see M2: **ship the cheap repeats=1+inter-chunk-sleep mitigation, defer full D3.**
6. RX intake granularity → **one bounded queue per MeshNode.** Preserves the two-node loop-freedom isolation (node.py docstring). Agree with spec lean.
7. Rate-limit policy → **after dedup, per-origin generous bucket + a spoof-proof GLOBAL frames/sec cap (M4).**
8. Watchdog → **heartbeat yes; log-and-alert only for demo (M6), auto-restart post-demo.**
9. Outbox eviction → **never evict an accepted envelope (M3); cap + refuse new low-urgency instead.**

**Voice**
1. Opus vs WAV? → **Hard-pick WAV for the demo.** Skip the probe/fallback complexity; WAV is
   bulletproof, universal, and clip lengths are tiny. Opus is post-demo optimisation.
2. `.web` scheme? → **Schema column (B4), not a second clip_id row.**
3. One LLM call or two? → **One (translate-only), no second triage call for voice (B3).**
4. Eager vs lazy transcode? → **Eager, in the existing background task** (read path stays fast). Agree.
5. Llama 3.2 tag? → **`llama3.2` (3B); env-driven default only.** Note BUG3: `triage.py:30` currently
   defaults to `qwen2.5-3b-instruct`, not the spec's stated line — the swap is a one-line default
   change but **the model is NOT the fix; the translate prompt is (B3).** Keep temperature 0.

---

## MINIMAL MUST-SHIP vs NICE-TO-HAVE

**Must-ship (life-safety + demo-critical, low risk):**
- Mesh C1 (split voice into its own long-lived uploader task) + **B1** (single consumer, no lock/set).
- Mesh B2 (dedicated voice ThreadPoolExecutor) — without it C1 is defeated.
- Mesh C4 (timeout tuple).
- Mesh D1 (bounded RX intake queue) + **M4 global ingest cap** — the real DoS defence.
- Mesh C5 (bounded `_seen`).
- Voice BUG1 (WAV transcode, served copy) + **B4** (schema column).
- Voice BUG2 as **B3** (single translate-only call, no urgency escalation) + **M5** (don't clobber typed triage).
- Voice BUG3 (env-default model swap) — trivial.

**Nice-to-have / defer post-demo:**
- Mesh D3 full priority TX queue (ship M2 cheap mitigation instead).
- Mesh D4 outbox eviction (ship M3 refuse-new instead).
- Mesh D6 watchdog auto-restart (ship heartbeat + log only).
- Mesh per-origin token bucket beyond the global cap.
- Voice Opus/WebM + startup probe (WAV only for demo).
- Voice second "download original" affordance.

---

## WHERE MESH AND VOICE SHOULD DEBATE (real trade-offs)

1. **Shared executor contention (B2).** Voice owns `to_thread` posts; Mesh owns `run_in_executor`
   LoRa TX. They currently share the default pool. They must jointly agree the pool split and the
   voice `max_workers` so voice throughput vs radio latency is a deliberate, documented number — not
   an accident. This is a genuine cross-owner resource contract.
2. **D3 priority TX vs voice airtime (M2).** Mesh wants SOS-first on the air; Voice's 45-chunk clips
   are the thing that starves it. The cheap mitigation (voice repeats=1 + inter-chunk yield) is a
   *Voice-side* behaviour change on the LoRa path Mesh owns — they must agree who implements it and
   that reduced voice repeats is acceptable for reliability of voice repair (NACK loop already handles
   loss, so repeats=1 is defensible — but that's a joint call).

---

## DIFF REVIEW — command-post (Voice's actual implementation)

Reviewed the uncommitted working-tree diff (`git diff -- command-post/`) file-by-file
against the running code, not the summary. Verdict: **the four command-post BLOCKERs
(B1/B3/B4 + M5) are correctly and cleanly implemented; no new BLOCKER introduced.**
Findings below are MAJOR/MINOR polish + one behaviour change worth a conscious sign-off.

### Confirmed CORRECT (verified line-by-line)
- **B3 (one translate call, no triage) — DONE.** `_transcribe_mesh_voice` (app.py:388-396)
  drops `triage.triage`, calls `triage.translate`, and builds `ai = {english, ai, latency_ms}`
  only. The disaster prompt can no longer touch a voice clip. `translate()` (triage.py) has a
  temp-0, data-tagged, faithful prompt with a never-raises fallback to the raw transcript.
- **M5 (don't clobber typed triage) — DONE and correct.** intelligence.py:245-258: the
  `urgency=max(...)`, `rationale`, `ai`, `latency_ms` writes are now **inside** the
  `if not report["gist"]:` branch. A typed-gist report gets only `audio` + `voice_transcript`
  + `voice_english`; its urgency/rationale/ai are untouched. Traced both branches — correct.
- **B4 (schema column, not a `.web` clip_id row) — DONE.** database.py adds `web_audio`/
  `web_content_type` columns + idempotent `ALTER ... ADD COLUMN IF NOT EXISTS`, a
  `get_web_audio`, and COALESCE on both web fields so a transcript-only update never wipes the
  web copy (and vice-versa). No second clip_id row; audit trail intact. `/web_audio/{clip_id}`
  route serves it. This is exactly the fix I recommended.
- **B1 (browser playback) — DONE.** `stt.transcode_for_web` reuses the safe pattern:
  list-argv, `pipe:0`/`pipe:1`, `-v error`, `timeout=15`, cached ffmpeg probe, returns None on
  any failure → caller keeps raw url (graceful degrade, rule #10). Injection-safe: no attacker
  bytes reach the argv or a path. WAV-only (my Open-Q1 adjudication). Good.
- **Validator allow-list — DONE and stricter than before.** `_valid_audio_name`
  (app.py:_valid_audio_name) replaces the fragile `.replace("webm","")` hack with a real
  suffix allow-list (`{.3gp,.ogg,.webm,.wav}`) + `len<=64` + alnum-with-dashes stem. Both
  `/audio` and `/web_audio` gate through it before any FS/DB touch. Traversal-safe (also still
  `is_relative_to(AUDIO_DIR)` on the file path). Rejects `..` (dot not in stem, and `..webm`
  → stem `.` → `"".isalnum()` False). Verified.
- **Prompt-injection (#7)** replicated correctly in `translate`; **#9 plain-text render**
  preserved (JSX `{primary.voice_english}` auto-escapes, no dangerouslySetInnerHTML);
  **#10** no raw errors surfaced (transcode logs `type(exc).__name__` only).

### MAJOR

- **MJ1 — behaviour change: a voice-only SOS now NEVER gets AI urgency at all.**
  Before, a voice-only report (no typed gist) ran the transcript through `triage.triage`,
  which could *raise* urgency to reflect a genuine spoken emergency. Now the voice-only
  branch (intelligence.py:251-256) does `urgency = max(report["urgency"], (ai or {}).get("urgency", report["urgency"]))`
  but `ai` from `translate()` has **no `urgency` key** → it always resolves to the report's
  own self-reported urgency. Same for `rationale`/`category`. So a victim who *only* speaks
  ("I'm trapped, water rising") gets **no AI urgency escalation** — the card shows the raw
  envelope urgency. This is the *safe* direction (no hallucinated escalation) and is arguably
  correct per B3's spirit, but it is a real capability regression for the legitimate
  voice-only-emergency case, and it is silent. **Not a blocker** (safe-fails), but the lead
  should consciously accept it, or add a *faithful* urgency pass (triage on the already-
  translated faithful English, urgency-only, still gated to voice-only) if genuine spoken
  emergencies must escalate. Flagging so it's a decision, not an accident.

- **MJ2 — raw-AMR url is broadcast first, then swapped — ACCEPTABLE, with one caveat.**
  `/mesh_voice` calls `attach_voice(ref_id, audio_url=/audio/{clip_id}, None, None)` and
  broadcasts (app.py:356-359) BEFORE the background task transcodes and re-attaches the
  `/web_audio` url. So for the ~1-15 s transcode window the card's `primary.audio` points at
  raw AMR the browser can't decode. Impact: if an operator hits play in that window, silent
  failure (no error, `<audio>` just won't play), then the next snapshot swaps `src` to the
  WAV and it works. This is acceptable for the demo (the eager transcode is fast and the ACK-
  first ordering is deliberately protecting the Pi timeout). **Caveat:** the pre-transcode
  broadcast means the very first render shows a playable-looking control that isn't yet
  playable — a MINOR UX lie, not a data problem. Fine to ship; note it.

### MINOR

- **MN1 — DB-mode pre-transcode `store_voice` writes web_audio=NULL, relies on COALESCE.**
  The initial `/mesh_voice` store (app.py:342-345) inserts the row with no web columns; the
  later background `store_voice` (app.py:388-393) fills them via COALESCE UPDATE. Correct, but
  it means `/web_audio/{clip_id}` returns 404 until the background task completes — matches
  MJ2's window. The route degrades to raw correctly. No action; just the same window.
- **MN2 — `transcode_for_web` catches bare `Exception` and prints.** Fine (rule #10 says log,
  don't surface), but `subprocess.run(timeout=15)` raising `TimeoutExpired` does NOT kill the
  child on all platforms unless `run` reaps it — CPython's `run` does terminate on timeout, so
  OK. Confirmed no orphaned ffmpeg. No action.
- **MN3 — file-mode WAV write not atomic.** `(AUDIO_DIR / f"{clip_id}.wav").write_bytes(web_audio)`
  (app.py) is a direct write; a crash mid-write could leave a truncated `.wav`. Low-value edge
  (background task, non-life-safety artefact), but a tmp+replace would match the Pi outbox
  discipline. MINOR / optional.
- **MN4 — `_valid_audio_name` allows a bare dot-free clip_id up to 64 chars containing only
  dashes** (e.g. `"----"` → stem `"----"`, `.replace("-","")` → `""` → `False`). Actually
  rejected. Verified no bypass. Note only.

### Net
No BLOCKER in the diff. Ship after the lead consciously signs off MJ1 (voice-only urgency
regression) — everything else is MINOR polish. The B1/B3/B4/M5 fixes are implemented as
specified and I could not find a correctness, injection, traversal, or render defect in them.

---

## DIFF REVIEW — pi-code (Mesh's actual implementation)

Reviewed the uncommitted pi-code diff (`git diff -- pi-code/`, 6 files) line-by-line against
the running code, with focus on threading/loop-safety of the new RX intake path. Verdict:
**the #1 risk (thread-safety of the intake queue) is handled CORRECTLY — no BLOCKER found.**
The threading is right. Findings are two MAJORs (a life-safety semantics gap + a forwarding
throughput/latency regression) and several MINORs.

### #1 THREADING — verified CORRECT
- **LoRa path is thread-safe.** `submit_lora` (node.py:submit_lora) does
  `loop.call_soon_threadsafe(self._offer, q, item)` — the radio RX thread hands off to the
  loop thread; `_offer`'s `q.put_nowait` then runs ON the loop. This is the correct fix; a raw
  cross-thread `put_nowait` would have been the BUG the brief warned about, and it is NOT here.
- **BLE path is on the loop.** The bleak notification `handler` (ble_link.py:handler) now calls
  `on_bytes(bytes(data))` synchronously, and `on_bytes` → `submit_ble` → `_offer` → `put_nowait`.
  bleak invokes notification callbacks on the event loop thread (BlueZ/CoreBluetooth both marshal
  onto the loop bleak was created on), so calling `_offer`/`put_nowait` directly (no
  `call_soon_threadsafe`) is correct. If a future backend ran the callback off-loop this would
  break, but for the shipped bleak path it is safe. **Confirmed correct.**
- **Queue created on the loop.** `start_intake` (node.py) is called from `run()` (gateway.py,
  on the loop) before `radios[].start_receiving`, so the `asyncio.Queue` exists before any
  producer fires. Ordering verified. The `submit_*` methods no-op if `_rx_q is None` (pre-start
  race guard) — good.
- **Loop-freedom preserved.** One queue + one drainer PER MeshNode (node.py `start_intake`,
  gateway.py loops over NODE_NAMES). The two nodes still share no queue, no drainer, no dedup
  ring. The module docstring's isolation invariant holds. Confirmed.
- **`_seen` OrderedDict LRU under the existing lock — correct.** `_mark_seen` (node.py) keeps
  the `threading.Lock` (still taken from both loop and — via nothing now, since RX is loop-only —
  but originate() can be called on the loop; lock is harmless), `move_to_end` on hit,
  `self._seen[id]=None` + `popitem(last=False)` on miss-overflow. move_to_end/popitem semantics
  are correct for LRU. No race: all mutation is under the lock. Good.

### MAJOR

- **MJ1 — the global token bucket drops SOS frames indiscriminately under a flood (life-safety).**
  `_drain` (node.py) calls `_allow()` (a global, urgency-BLIND token bucket) for every frame; on
  over-budget it `_drop(...,"rate_limited")` and `continue` — **before** dedup and before the
  envelope is even decoded (payload may be raw bytes for BLE). So during a genuine flood a real
  urgency-5 SOS arriving in the same second as the flood is silently dropped, never uplinked,
  never re-broadcast. This is exactly the "an SOS must never be silently lost" invariant. The
  global cap is the right DoS defence (M4), but it must not be able to eat an SOS. **Fix options:**
  (a) decode-cheaply / peek type before the rate gate and always admit `SOS`/`u5` (bypass the
  bucket for criticals, count them but never drop), or (b) two-tier bucket: a reserved critical
  lane. Since decode is cheap and already happens in `on_lora_frame`/`on_ble_bytes`, moving a
  lightweight type/urgency check ahead of `_allow()` is feasible. **This is the one finding I'd
  hold the PR on** — it converts a DoS mitigation into an SOS-loss path. (Severity is MAJOR not
  BLOCKER only because it requires an active flood to trigger; but for this system treat as must-fix.)

- **MJ2 — RX forwarding is now serialized per node (throughput/re-broadcast latency regression).**
  Previously each LoRa frame was `run_coroutine_threadsafe(on_lora_frame)` — separate concurrent
  tasks, so N frames' `_forward` (LoRa TX in executor) overlapped. Now the single `_drain` task
  `await`s each `on_lora_frame` fully (including `_forward` → `gather` over links → `run_in_executor`
  TX, ~400 ms/frame, PLUS the new `post_delay_s` sleep for voice) before pulling the next queue
  item. The loop is NOT blocked (it's all `await`), but per-node RX-to-rebroadcast is now
  serialized to TX speed. For a 45-chunk voice clip at repeats=1 + 20 ms yield that's ~45×(TX+20ms)
  serially, and any SOS *received* (not originated) during that drains behind the queued voice
  chunks. The A6 `_tx_policy` (voice repeats=1 + yield) mitigates *air* contention but the
  *drainer* still processes voice chunks ahead of a later-queued SOS in FIFO order. This is a real
  behaviour change from the concurrent model. **Acceptable for the demo IF** MJ1 is fixed (so the
  SOS at least isn't dropped) and clip volumes are low, but note it: the bounded queue + serial
  drain means sustained voice can delay re-broadcast of a received SOS. A per-node **priority**
  drain (SOS-first out of the queue) would close it — but that's the D3-class work we deferred.
  Flagging as a conscious trade-off, not a silent one.

### MINOR

- **MN1 — selftest_lora.py bypasses the new intake path (untested hot path).** selftest_lora.py:108
  still calls `run_coroutine_threadsafe(n.on_lora_frame(link, pkt))` directly and never calls
  `start_intake`. `on_lora_frame` is unchanged so the selftest still PASSES — no regression — but
  it means the new queue/rate-limit/drainer (the highest-risk code) is exercised by NOTHING
  automated. Recommend a tiny test that drives `submit_lora` + a running `_drain` and asserts
  overflow-drop + rate-drop counters. Not a blocker for the demo.
- **MN2 — `_allow()` refill cap = one second's burst.** `min(self._rate, ...)` caps stored tokens
  at `rate` (1 s of burst). Reasonable, but a legitimate brief spike (two phones + a responder
  retransmitting) just above 50/s will drop. Default 50 fps is generous vs real mesh volume, so
  fine — just confirm the number with real traffic. Config-driven, so tunable.
- **MN3 — BleLink.send swallows `repeats`/`post_delay_s` via `del` — correct but silent.** The
  uniform-signature approach is right (MeshNode calls all links the same way). `del repeats,
  post_delay_s` is fine. No issue; noted for completeness.
- **MN4 — voice pool + session lifecycle is correct.** `_voice_pool` is a dedicated bounded
  `ThreadPoolExecutor` (thread_name_prefix good), default executor left for radio TX (LoRaLink
  uses `run_in_executor(None,...)`), `_post_voice`/`_http_fallback` both use `_voice_pool`,
  `timeout=self._voice_timeout` tuple, one reused `Session(trust_env=False)`, and `edge.close()`
  is called in gateway.py's finally (shutdown wait=False, cancel_futures=True + session.close()).
  No leak on reconnect (pool/session are instance-level, created once, not per-connection).
  `ping_timeout=10` added. All correct — this is the cleanest part of the diff.
- **MN5 — `_voice_uploader` single-consumer is correct.** Only caller of `_flush_voices`; no lock,
  no in-flight set (B1 resolved as recommended). `_voice_wake` set on clip-complete AND on
  reconnect (uplink.py run() `self._voice_wake.set()`); cleared-then-drained so a clip completing
  mid-drain re-sets the wake → next pass drains it (no lost wake). Cancelled with reader/sender via
  the `asyncio.wait(..., FIRST_COMPLETED)` + `t.cancel()`. Within a pass, `gather` over
  `pending()` with `Semaphore(concurrency)` — distinct `*.json` globs, no double-post. Correct.
- **MN6 — OutboxFull handling is correct.** `enqueue` refuses only NEW low-urgency
  (urgency < 5 AND id not already present) at cap; u5 and idempotent re-enqueue always pass;
  `send_envelope` catches `OutboxFull`, sets `outbox_alarm`, logs (no stack trace to dashboard,
  rule #10), surfaces the alarm on the status frame, and RETURNS — never propagates to crash
  `on_accept`. `on_accept` in gateway is also wrapped in MeshNode `_accept`'s try/except anyway.
  Correct and matches the D4 "never drop an accepted one" adjudication.
- **MN7 — `.tmp` orphan sweep (A8) is correct** and runs once at `VoiceUploadOutbox.__init__`.
  Reclaims `.tmp`, metas with missing audio, audio with missing/unreadable meta. Good; closes the
  MINOR leak I flagged in the original spec review.
- **MN8 — config validation is solid.** New `ingest.*`, `voice.upload_*`, `uplink.outbox_max` all
  range-checked with the bool-isn't-int guard (`isinstance(x, bool)` rejection). `_validate` now
  uses `if key in v` so the fields are optional with code defaults — backward compatible with an
  existing config.json. Good.

### Net
No BLOCKER. Threading — the stated #1 risk — is correct: LoRa via `call_soon_threadsafe`, BLE on
the loop, per-node queue+drainer preserving loop-freedom, LRU under lock. **Hold for MJ1** (the
global rate limiter can silently drop a real SOS under flood — must exempt criticals), and get a
conscious sign-off on **MJ2** (serialized per-node forwarding delays a received SOS behind queued
voice — the deferred priority-drain would close it). Everything else is correct or MINOR polish;
the voice-pool/session/uploader/outbox-cap work is clean and matches the adjudicated design.

---

## RE-VERIFY — two-lane intake (MJ1 + MJ2 fix)

Re-verified the two-lane rewrite in node.py + the alarm wiring in gateway.py/uplink.py +
the new test_intake_lanes.py against the real code. **CLEAN — no BLOCKER. Both MJ1 and MJ2
are genuinely fixed.** I ran the test: `4 passed`.

1. **SOS is truly rate-EXEMPT and drained first — CONFIRMED.** `_is_critical`
   (node.py:232) = `isinstance(msg, env.Envelope) and type=="SOS"`, ANY urgency. Critical
   frames go to `_crit_q` via `_offer_critical`, which NEVER consults `_allow()`. `_drain`
   (node.py:333) empties `_crit_q` fully with a `get_nowait` loop BEFORE it touches `_norm_q`,
   and `_allow()` (the global bucket) is only called on the normal lane. There is no code path
   where an SOS reaches the rate gate. The `crit-0..crit-4` test at 1 frame/s proves all 5 SOS
   are admitted under a 100-chunk flood.
2. **Decode-once on the loop; crc/malformed dropped at classification; rssi/snr preserved —
   CONFIRMED.** `submit_lora` still uses `call_soon_threadsafe(self._classify_and_offer, ...)`
   (node.py:244) so decode runs ON the loop; `submit_ble` calls it directly (already on loop).
   `_classify_and_offer` (node.py:252) drops `crc_error` and `malformed` right there and returns
   — they never enter a lane. `_RxItem` carries `pkt`, so `_handle_lora` (node.py:419) still
   emits `LORA_RX` with `pkt.rssi_dbm/snr_db` — proof-of-flight log unchanged.
3. **Critical overflow alarms + loud log, never silent — CONFIRMED.** `_offer_critical`
   (node.py:281) on `QueueFull` increments `_critical_overflow`, sets `critical_alarm=True`, and
   `log.error(...)` (explicitly NOT rule-10-suppressed, comment says so). Surfaced two ways:
   the software watchdog logs it (gateway.py:181), and `edge.status_extra` (gateway.py:399) is
   wired to `{"critical_intake_alarm": gw_node.critical_alarm}`, merged into the status frame in
   `_flush_status` (uplink.py:539, guarded by try/except so a provider glitch can't break status).
   `status_extra` is initialised to None in `__init__` (uplink.py:328) — no AttributeError. It
   never silently drops.
4. **No NEW bug — CONFIRMED with one noted trade-off (not a bug):**
   - Both lanes bounded (`maxsize=queue_max`, node.py:227-228). Cancellation clean: `_drain`
     loops on `not stop.is_set()` and both `get_nowait`/`wait_for(get, 0.05)` return promptly, so
     the task exits on stop; it's the same `asyncio.wait(FIRST_COMPLETED)` cancellation as before.
   - **Normal-lane starvation is bounded and safe.** `_drain` does ALL-critical-then-ONE-normal.
     A sustained SOS flood could delay normal-lane items — but the normal lane carries only
     *inbound RX* (voice chunks, phone DELIVERED/ACCEPTED, phone NACKs). The dispatch return path
     and the voice-NACK sweeper both go through `gw.originate` → `_forward` (egress), NOT the RX
     intake, so they are unaffected by drainer ordering. Real SOS volume is tiny, so starvation is
     theoretical. Acceptable — SOS-first is the intended guarantee.
   - **selftest_lora.py still works.** `on_lora_frame`/`on_ble_bytes` are kept as public wrappers
     (node.py:397/410) that decode + route to `_handle_lora`/`_handle_ble`. The selftest calls
     `on_lora_frame` directly (never `start_intake`), so it is unchanged and green. (Same MN1 as
     before: the selftest still doesn't exercise the intake lanes — but test_intake_lanes.py now
     does, which closes that gap.)
   - **Loop-freedom preserved.** Each node has its own `_crit_q`, `_norm_q`, `_drainer`
     (start_intake, node.py:223); the two nodes share nothing. Invariant intact.
5. **test_intake_lanes.py asserts the real guarantees — NOT vacuous.**
   - `_test_sos_first`: 45 voice chunks queued, then 1 SOS; asserts `sos_pos <= 1` — proves the
     SOS jumps the queue (MJ2). (Observed position 0.)
   - `_test_sos_never_rate_dropped`: rate=1/s, 100 chunks + 5 SOS; asserts all 5 `crit-*` ids are
     accepted AND `critical_alarm` is False — proves rate-exemption (MJ1).
   - `_test_malformed_dropped_at_intake`: undecodable bytes never reach `on_accept`.
   - `_test_classify`: SOS→critical, voice/DELIVERED→normal.
   Hardware is stubbed (RPi.GPIO/spidev) so it runs off-Pi. Assertions are specific and would
   fail if the guarantee regressed. Good coverage of exactly the two fixed defects.

### Verdict: CLEAN. Commit it. Threading still correct, MJ1/MJ2 fixed, alarm surfaced, test real.
