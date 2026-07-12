# Sankat-Mochan — Command Post ("AI PC")

The laptop-side dashboard that SOS envelopes land on. Receives them (from the
LoRa gateway via `POST /sos`, or the test button), runs **AI triage**
(urgency + Indic→English translation), and shows a live, ranked triage queue
with dispatch. Backend-agnostic AI so we can benchmark and pick the fastest.

## Folder map

| Path | What it is |
| --- | --- |
| `*.py` (root) | The runtime: `app.py` (FastAPI), `intelligence.py`, `triage.py`, `stt.py`, `indic_stt.py`, `models.py`, `database.py`, `npu_server.py`. |
| `web/` | The React (Vite) dashboard; FastAPI serves its `dist/`. |
| `static/` | Offline basemaps (PMTiles) + vendored map fonts/sprites. |
| `scripts/` | One-off dev tools: AI-Hub STT compiles, basemap extracts, mel-golden dump, FLEURS download. |
| `benchmarks/` | `bench.py` (LLM backends), STT/LID benches, extraction bench, model ranking. |
| `tests/` | `test_tags.py` — TAGS parse/merge/wire-size checks (`uv run python tests/test_tags.py`). |
| `finetune/` | Sahayak (Gemma 4) QLoRA training + dataset; eval result CSVs live in `docs/evals/`. |
| `deploy/npu/` | Package the finetuned model for the phone NPU (GGUF → llama.cpp/Hexagon). |
| `aihub_out/` | AI-Hub job records + compiled STT artifacts (consumed by `mobile-application/tools/push_stt_model.sh`). |

## Run

```bash
cd backend
./setup-postgres.sh           # one-time: generated local secret + PostgreSQL container
uv sync                       # creates .venv from pyproject.toml (uv: https://docs.astral.sh/uv/)
cp .env.example .env          # optional: set LLM_BASE_URL to enable AI
uv run uvicorn app:app --host 0.0.0.0 --port 9000
```

Or just `./dev.sh` (macOS/Linux) / `.\dev.ps1` (Windows) from this folder — they start
the backend and the Vite dashboard together, using uv when it is installed.

Open <http://localhost:9000>. Click **Inject test SOS** to see the loop with no
hardware. Works with **no LLM** (rule-based fallback) until you set a backend.

## Run sessions and voice storage

Every backend process start creates a new UUID session and an empty live dashboard.
PostgreSQL keeps the previous sessions for audit/history; it does not reload them into
the new run. Completed mesh voice clips are reassembled durably on the Pi, stored as
PostgreSQL `BYTEA`, transcribed, and attached to their original SOS report.

- `GET /sessions` lists stored runs.
- `GET /sessions/{uuid}` returns a run's final/latest snapshot.
- `GET /sessions/{uuid}/audio/{clip}` streams historical audio.

`setup-postgres.sh` writes the generated password only to `.postgres.env` (mode 600,
gitignored). To require an external PostgreSQL instead, set `DATABASE_URL` and
`SANKAT_DATABASE_REQUIRED=true` in the environment.

## AI backend (any OpenAI-compatible server)

Set in `.env` — swap freely, no code change:

| backend   | LLM_BASE_URL                | notes                        |
|-----------|-----------------------------|------------------------------|
| LM Studio | http://localhost:1234/v1    | best on Mac (MLX)            |
| Ollama    | http://localhost:11434/v1   | easy local                   |
| vLLM      | http://localhost:8000/v1    | needs NVIDIA GPU (not Mac)   |
| llama.cpp | http://localhost:8080/v1    | portable                     |

## Pick the fastest

Start the backends you have, then:

```bash
uv run python benchmarks/bench.py   # reads backends.json (copy from backends.example.json)
```

It runs the same triage task on each and prints a ranked table (avg ms, p50, tok/s)
plus the `.env` line for the winner.

## The ingest contract (what the Pi gateway calls)

`POST /sos` with the CONTRACT-1 JSON envelope (see ../HANDOFF.md). Same dedup-by-id.
`POST /accept/{id}` marks a victim en-route (return-path to the mesh wired when the gateway is up).

## Endpoints
- `GET  /`            dashboard
- `POST /sos`         ingest one envelope (gateway / test)
- `POST /inject`      push a realistic test SOS
- `POST /accept/{id}` dispatch a responder
- `GET  /health`      status
- `GET  /sessions`    stored run history
- `WS   /ws`          live feed to the dashboard
