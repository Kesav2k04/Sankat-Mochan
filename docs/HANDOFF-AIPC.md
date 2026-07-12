# Handoff — AI PC (command post) on QCWorkshop

Everything needed to run the **command post** on the Snapdragon X Elite laptop
(QCWorkshop, Windows-on-ARM), with the LLM on the **Hexagon NPU via GenieX**.

This PC's job: receive SOS + voice from the Pi gateway over Wi-Fi, run triage +
faithful translation (NPU LLM) and Indic speech-to-text, and serve the live
dashboard. The Pi + radios + phones are a separate handoff (`raspberrypi/`, phones).

```
victim phone ──BLE──► Pi gateway ──433 MHz──► Pi ──Wi-Fi (WS/HTTP)──► THIS PC (command post)
                                                                         ├─ GenieX LLM  (NPU)  triage + translate
                                                                         ├─ Indic-Conformer     speech-to-text
                                                                         └─ dashboard :9000     live triage board
```

---

## 0. Prerequisites (install once)

| Need | Why | Install |
|---|---|---|
| **Git** | pull the repo | winget install Git.Git |
| **Python 3.11+ (ARM64)** | the command post | python.org ARM64 build (`python --version` → arm64) |
| **ffmpeg** on PATH | voice: decode AMR + make WAV | winget install Gyan.FFmpeg (confirm `ffmpeg -version`) |
| **GenieX** | LLM on the NPU | `geniex-cli-setup.exe` from github.com/qualcomm/GenieX |
| Node.js 20+ | rebuild dashboard (only if UI changed) | winget install OpenJS.NodeJS.LTS |
| Docker Desktop | *optional* — only if you want PostgreSQL persistence | else run DB-less |

> Use **PowerShell** for everything below. `server.sh` / `setup-postgres.sh` are the
> Mac/bash path — on Windows run `uvicorn` directly as shown.

---

## 1. Get the code
```powershell
cd C:\src   # wherever you keep repos
git clone https://github.com/SivaNithishKumar/sankat-mochan.git
cd sankat-mochan
# already cloned? just:  git pull
```

## 2. LLM on the NPU (GenieX)
From `backend\`:
```powershell
cd backend
./setup-geniex.ps1        # pulls heretic 8B @ Q4_0, serves NPU on :18181, writes .env
```
This pulls `bartowski/p-e-w_Llama-3.1-8B-Instruct-heretic-GGUF` at **Q4_0** (best Hexagon-NPU
support), starts `geniex serve` at `http://127.0.0.1:18181/v1`, health-checks it, and writes
`LLM_BASE_URL/LLM_MODEL/LLM_TIMEOUT_S` into `.env`. Full detail + quant options:
`docs/reference/GENIEX-SETUP.md`. Leave that terminal/job running.

> Dev-preview CLI: if a `geniex pull/serve` flag differs, the script echoes each command and
> falls back to guidance — check `geniex serve --help`, then re-run with `-NoServe`.

## 3. Python env + deps
```powershell
# still in backend\
uv sync                                  # creates .venv from pyproject.toml (FastAPI, uvicorn, httpx, numpy, soundfile, websockets…)
.\.venv\Scripts\Activate.ps1

# Voice speech-to-text (Indic-Conformer) — heavy, but needed for voice TRANSCRIPTS:
pip install torch transformers           # CPU build is fine; first run downloads the model
```
Without `torch`/`transformers` the server still starts and everything works **except** voice
transcription (audio still plays; text SOS + translation still work).

## 4. Configure `.env`
`setup-geniex.ps1` already wrote the `LLM_*` lines. Confirm `backend\.env` has:
```
LLM_BASE_URL=http://127.0.0.1:18181/v1
LLM_MODEL=bartowski/p-e-w_Llama-3.1-8B-Instruct-heretic-GGUF
LLM_API_KEY=not-needed
LLM_TIMEOUT_S=60
```
**Database — pick one:**
- **DB-less (simplest for the demo):** do nothing. Leave `DATABASE_URL` unset and do **not**
  set `SANKAT_DATABASE_REQUIRED=true`. Sessions are in-memory; voice/audio is stored as files
  under `backend\audio_store\`. Everything works.
- **PostgreSQL (persistent sessions/audio):** needs Docker. Bring up the container and put its
  `DATABASE_URL` in `.env` (`SANKAT_DATABASE_REQUIRED=true`). See `setup-postgres.sh` for the
  values; on Windows run the equivalent `docker compose -f compose.yaml up -d postgres`.

## 5. (Recommended) rebuild the dashboard
The committed `web/dist` may predate the latest UI (the new **VOICE (EN)** label + web-audio
player). Rebuild once:
```powershell
cd web
npm install        # first time
npm run build      # emits web/dist, which FastAPI serves
cd ..
```

## 6. Run the command post
```powershell
# in backend\ with the venv active and GenieX serving
uvicorn app:app --host 0.0.0.0 --port 9000
```
Open **http://localhost:9000** — the dashboard is served by FastAPI itself. It has an
**Inject test SOS** button, so you can verify the board before the Pi is connected.

## 7. Point the Pi at this PC
On the **Pi** (not here), set the uplink to THIS PC's LAN IP and enable it:
```bash
# find this PC's IP first (on the PC):  ipconfig   → IPv4 address, e.g. 10.55.0.42
SANKAT_UPLINK__ENABLED=true SANKAT_UPLINK__URL=http://10.55.0.42:9000/sos ./run.sh
```
The Pi derives the `/gateway` WebSocket from that URL automatically.
Open port 9000 inbound on this PC if the Pi can't connect:
```powershell
New-NetFirewallRule -DisplayName "Sankat 9000" -Direction Inbound -LocalPort 9000 -Protocol TCP -Action Allow
```

## 8. Verify end-to-end
1. Dashboard loads at `:9000`; **Inject test SOS** shows a card. ✓
2. Pi connects — status bar shows the gateway link + the on-device LLM indicator.
3. Send a **text SOS** from a phone → card appears, translated to English.
4. Send a **Tamil voice SOS** ("hello mic testing one two three"):
   - transcript in Tamil, **English faithful** ("hello, mic testing, one two three") — **not**
     "trapped under debris",
   - the audio **plays** in the browser (WAV transcode of the phone's AMR),
   - `VOICE (EN) ·` label shows the translation matching the audio.

---

## What runs without each piece (fail-soft by design, project rule #10)
| Missing | Effect |
|---|---|
| GenieX / `LLM_BASE_URL` unset | rule-based triage; victim's own fields used; no translation |
| ffmpeg | voice won't transcode/decode → no playback/transcript; text SOS unaffected |
| torch/transformers | no voice transcript; audio still plays; text SOS unaffected |
| Postgres | DB-less; sessions in memory, audio on disk |
| rebuilt dashboard | old UI (no VOICE(EN) label), but data still flows |

## Troubleshooting
- **No AI / everything rule-based:** GenieX not serving or `LLM_BASE_URL` wrong. Check the
  `geniex serve` job answers `http://127.0.0.1:18181/v1/models`.
- **404 model-not-found:** `LLM_MODEL` must equal what `geniex serve` loaded.
- **First triage call times out:** 8B cold-load; `LLM_TIMEOUT_S=60` covers it — one-time warm-up.
- **Voice card but no transcript:** ffmpeg and/or torch+transformers not installed.
- **Pi can't reach the post:** firewall (step 7), wrong IP, or both not on the same Wi-Fi.
- Errors go to the server log, never the dashboard — check the uvicorn console.

## More detail
- LLM/NPU setup + quant options: `docs/reference/GENIEX-SETUP.md`
- Pi ↔ command-post wire protocol: `docs/EDGE-LINK.md`
- Triage/translation + voice design: `docs/INTELLIGENCE-DESIGN.md`, `docs/specs/voice-pipeline.md`
- Pi gateway reliability (SOS-first, DoS): `docs/specs/mesh-transmission.md`
