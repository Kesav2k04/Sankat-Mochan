# Testing

Every component has its own suite, colocated with the code it tests. All Python suites
run through **uv**; the Android suite runs through Gradle; the simulator through Vitest.

| Component | Where the tests live | Run with | Count |
| --- | --- | --- | --- |
| `backend/` | `tests/unit/` (models, TAGS gate, triage fallback + parsers) and `tests/integration/` (FastAPI API via TestClient, TAGS pipeline) | `cd backend && uv run pytest` | 54 |
| `raspberrypi/` | `tests/` (envelope wire contract + voice frames, chain-log proof, SOS-priority intake lanes, voice reassembly) | `cd raspberrypi && uv run pytest` | 43 |
| `app-simulator/` | `tests/` (wire-format parity with envelope.py, Semtech airtime math, mesh routing honesty) | `cd app-simulator && npm test` | 19 |
| `backend/finetune/` | `tests/` (dataset validator gate, stdlib-only) | `cd backend/finetune && uv run --no-project --with pytest pytest tests` | 4 |
| `mobile-application/` | `app/src/test/` (JVM: envelope, TAGS, mesh dedup/rate-limit/policy, geo, tiles) and `app/src/androidTest/` (on-device: STT smoke, mel parity) | `cd mobile-application && ./gradlew test` (needs the Android SDK; androidTest needs a device) | 10 classes |

Conventions:

- **`unit/` vs `integration/`** (backend): unit tests import one module and hit no I/O;
  integration tests drive the real ASGI app. Neither needs a network, an LLM, or
  PostgreSQL — `tests/conftest.py` clears `LLM_BASE_URL` / `DATABASE_URL` so every run
  exercises the offline fallback path the venue box must survive on.
- **Untrusted-input first**: the suites bias toward rejection paths (rule #8) — malformed
  envelopes, corrupted voice frames, TAGS injection, path tricks on `/audio/{name}`,
  prompt-injection breakout attempts on the triage tag.
- **Wire-contract parity**: `raspberrypi/tests/test_envelope.py` and
  `app-simulator/tests/envelope.test.js` assert the same 244-byte budget, key order,
  trim rules, and voice-frame layout, so the three ports (Kotlin / Python / JS) cannot
  drift silently. Kotlin's side is covered by `SosMessageTest` / `VoiceChunkTest`.
- The two files in `raspberrypi/tests/` that predate this suite
  (`test_intake_lanes.py`, `test_voice_assembler.py`) still run standalone on a board:
  `python tests/test_intake_lanes.py`.
