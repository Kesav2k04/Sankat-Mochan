# Sankat-Mochan — Voice + All-Comms Hardening: Implementation Plan

Synthesized from `mesh-transmission.md` (Mesh), `voice-pipeline.md` (Voice), and
`CRITIQUE.md` (Critic), after cross-owner debate. This is the agreed **must-ship** set.
Ranked; each item = file:function + change + why. Deferred items listed at the end.

**Goal:** all communications fast, parallel, reliable, never wedged, DDoS-resistant; an
accepted SOS is never lost; voice plays in the browser; displayed English faithfully
matches the audio.

**Locked product decisions:**
- **Overload:** never evict an accepted envelope. On outbox cap, refuse NEW low-urgency
  intake + raise an operator alarm; urgency-5 always protected.
- **Model:** `LLM_MODEL` default → `llama3.2` (env-driven). The faithful-translate prompt
  is the real fix, not the model.
- **Playback:** transcode AMR→**WAV** (universal, tiny clips); Opus/WebM deferred.

---

## A. Pi transmission + all-comms reliability (owner: Mesh) — `pi-code/`

### A1 (BLOCKER) Split voice upload off the SOS/WS path — `uplink.py`
- `_sender` does WS only: `_flush` (envelopes) → `_flush_peer_states` → `_flush_status`.
  Remove `_flush_voices` from it.
- New **single long-lived** `_voice_uploader(stop)` task created in `run()` beside
  reader/sender; waits on a dedicated `_voice_wake` event (set on clip-complete + on
  reconnect). **One consumer ⇒ no lock, no set-guard** (kills the racy C2/B1).
- Within a drain pass, upload up to N clips concurrently via `asyncio.gather`.

### A2 (BLOCKER) Dedicated voice thread pool — `uplink.py`
- Voice HTTP posts run on a private `ThreadPoolExecutor(max_workers=2)`, passed explicitly.
  The **default** executor is reserved for radio TX (`LoRaLink.send` `run_in_executor`).
- **Contract (signed off):** voice pool = 2 workers; radio never shares it. Documented so
  no future edit "fixes" throughput by widening it back into radio contention.
- `_post_voice` timeout → `(connect=5s, read=30s)` tuple; reuse one module-level
  `requests.Session`. Voice throughput→0 while AI-PC unreachable is acceptable (documented).

### A3 (BLOCKER) Bounded RX intake + global ingest cap — `ble_link.py`, `gateway.py`, `node.py`
- Replace per-notification `create_task` (ble_link.py:318) and per-packet
  `run_coroutine_threadsafe` (gateway.py:362) with a **bounded `asyncio.Queue` per MeshNode
  + one drainer** (preserves two-node loop-freedom isolation). Drop-and-log on overflow.
- **Spoof-proof GLOBAL frames/sec cap** at the drainer (origins are unauthenticated, so
  per-origin buckets are bypassable — global cap is the real defence). Per-origin fairness
  bucket is nice-to-have, not must-ship.

### A4 (MAJOR) Bound `_seen` — `node.py`
- `_seen` → `OrderedDict` ring, cap 4096, evict oldest (mesh TTL bounds dup lifetime).
  Keep the existing `threading.Lock`.

### A5 (MAJOR) Outbox cap, never-drop — `uplink.py: DurableOutbox`
- Cap row count. On overflow: refuse NEW low-urgency enqueue + log loudly + surface an
  alarm flag to the dashboard. **Never delete an already-accepted envelope.**

### A6 (MAJOR) Voice airtime — SOS-first on the air — `node.py`/`uplink.py` LoRa path
- Per-frame `tx_repeats` override: voice chunks = **repeats=1** (NACK loop repairs loss);
  SOS text frame keeps repeats>1 (must land fast). `set_repeats` is link-global today —
  add per-frame override.
- Small inter-chunk **yield** (release `_AIRWAVES` + `await`) so an SOS can grab the air
  mid-clip instead of waiting out ~45 chunks. Full priority-TX queue **deferred**.

### A7 (MAJOR) Liveness heartbeat — `gateway.py`/`uplink.py`
- `last_progress` timestamps on sender/uploader/RX drainers; watchdog **logs + alerts**
  only (no auto-restart for the event). Add WS `ping_timeout`.

### A8 (MINOR) `.tmp` startup sweep; orphan audio GC — `uplink.py: VoiceUploadOutbox`.

---

## B. Command-post voice pipeline (owner: Voice) — `command-post/`

### B1 (BLOCKER) Browser-playable audio — `stt.py`, `app.py`, `intelligence.py`
- New `stt.transcode_for_web(data)->(bytes,ctype)|None`: reuse the safe shell-free
  ffmpeg pattern (list-argv, `pipe:0/1`, `subprocess.run(timeout=15)`), output **WAV**
  (pcm_s16le, mono, 16k). Cache the ffmpeg-availability probe once.
- Transcode **eagerly in the existing background task** `_transcribe_mesh_voice`
  (after the Pi ACK — never blocks it). Store the web copy in a **new schema column**
  (`web_audio BYTEA`, `web_content_type TEXT` on `command_post_voice_messages`) — **not** a
  second `clip_id` row (protects the audit trail). Serve it via `/web_audio/{clip_id}`
  (file-mode: `AUDIO_DIR/{clip_id}.wav`).
- `attach_voice` carries the **web-playable** url → `report["audio"]` → `<audio>`.
- Graceful degrade: if transcode returns None, keep raw + quiet "audio not playable"
  status (no stack trace, rule #10).

### B2 (BLOCKER) Faithful translation, no urgency escalation — `triage.py`, `app.py`, `intelligence.py`
- New `triage.translate(text, lang)->{"english":...}`: translation-only system prompt,
  **temp 0**, "never add/infer/summarise/invent; empty→empty; already-English→unchanged",
  `<incoming_message>` data-tag (rule #7), never-raises (fallback = raw transcript).
- `_transcribe_mesh_voice`: **ONE** `translate` call for voice. **No second `triage.triage`
  call** (it escalated urgency 4-5 + category=trapped on benign speech).
- `attach_voice` (`intelligence.py`): when the report **already has typed gist**, only add
  `audio`/`voice_transcript`/`voice_english` — do **NOT** touch `urgency`/`rationale`/
  `ai`/`latency_ms` (M5). Urgency/rationale escalation only on voice-**only** reports, and
  even then not from a disaster-triage hallucination.

### B3 (MAJOR) Model swap — `triage.py:30`
- `MODEL = os.getenv("LLM_MODEL", "llama3.2")`; document tag + `LLM_BASE_URL` in run docs.
  Verify end-to-end with the Tamil "hello mic testing" clip: transcript unchanged, card
  English faithful, `<audio>` plays.

### B4 (MINOR) `/audio`/`/web_audio` name validation — explicit suffix allow-list; keep
`is_relative_to(AUDIO_DIR)`; JSX renders text nodes only (rules #8/#9).

### B5 (JSX) `IncidentDetail.jsx` — near the player, show `voice_english` labelled
`VOICE (EN) ·`, distinct from typed `AI ENGLISH ·`, so the operator sees the English that
matches the recording. Plain text only.

---

## Deferred (post-demo, explicitly cut to reduce demo risk)
- Full urgency-aware priority TX queue (A6 cheap mitigation ships instead).
- Outbox eviction (A5 refuse-new ships instead).
- Watchdog auto-restart (A7 heartbeat+log ships instead).
- Per-origin token bucket beyond the global cap (A3).
- Opus/WebM + startup probe/fallback (WAV ships).
- "Download original recording" affordance.

---

## Execution order (dependency-aware)
1. B3 (trivial) + B2 (faithful translate) — fixes the visible hallucination first.
2. B1 (transcode + schema column) — fixes playback.
3. A1+A2 (voice decoupling + pool) — the core reliability BLOCKER.
4. A3+A4+A5 (ingest cap, `_seen`, outbox cap) — DoS/reliability.
5. A6 (airtime) + A7 (heartbeat) + A8/B4/B5 polish.
Each domain landed as its own commit; **brutal Critic re-review of the actual diff before any PR** (CLAUDE.md gate).
