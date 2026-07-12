# Quick run cheatsheet

**Backend (FastAPI command post → port 9000)**

```bash
cd backend
uv run uvicorn app:app --host 0.0.0.0 --port 9000
```

Or the supervised route from the Pi / a Mac with the repo checked out:

```bash
./raspberrypi/server.sh post      # command post only, no radios/Bluetooth — the usual dev case
```

Then open <http://localhost:9000> — the built dashboard is served by FastAPI itself.
Works with no LLM (rule-based fallback) and has an **Inject test SOS** button.

**Frontend (Vite dev server — only needed for live UI dev)**

```bash
cd backend/web
npm install     # first time only
npm run dev
```

**Whole dev stack (backend + frontend, one command)**

```bash
cd backend && ./dev.sh          # macOS/Linux
cd backend; .\dev.ps1           # Windows (also boots GenieX / the NPU LLM)
```
