Backend (FastAPI command post → port 9000):
cd "/Users/sivadnithish/dev/personal/projects/Qualcomn hackathon "
./server.sh post          # command post only, no radios/Bluetooth — the usual dev case
Or run uvicorn directly (skips the venv/requirements bootstrap):
cd "/Users/sivadnithish/dev/personal/projects/Qualcomn hackathon /command-post"
uvicorn app:app --host 0.0.0.0 --port 9000
Then open http://localhost:9000 — the built dashboard is served by FastAPI itself. Works with no LLM (rule-based fallback) and has an Inject test SOS button.

Frontend (Vite dev server — only needed for live UI dev):
cd "/Users/sivadnithish/dev/personal/projects/Qualcomn hackathon /command-post/web"
npm install   # first time only
npm run dev
