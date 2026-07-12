# AI PC LLM backend — GenieX on Snapdragon X Elite

How to run the command post's triage + translation model on the Hexagon NPU via
**GenieX**, Qualcomm's on-device runtime (`github.com/qualcomm/GenieX`, dev preview
Jun 2026). Target box: **QCWorkshop** — Snapdragon X1E80100 (X Elite), Adreno X1-85,
32 GB RAM, Windows-on-ARM.

## Why this drops in with no code change
The command post talks plain **OpenAI `/v1/chat/completions`** (`triage.py`), chosen by
env vars. `geniex serve` exposes an OpenAI-compatible API at **`http://127.0.0.1:18181/v1`**.
So switching from Ollama → GenieX is **one `.env` change**. GenieX runs **GGUF** models
(llama.cpp runtime → NPU/GPU/CPU) *or* QNN bundles (qairt runtime → NPU). We use the GGUF
path with the model below. (This is the "GenieX / AnythingLLM" turnkey NPU option already
noted in `npu_server.py` and `PLAN.md` — it supersedes the manual ORT-genai shim and the
earlier Qwen3-4B PC pick.)

## Model
**`bartowski/p-e-w_Llama-3.1-8B-Instruct-heretic-GGUF`** — bartowski's GGUF build of the
canonical **p-e-w "heretic"** (abliterated/decensored) Llama-3.1-8B Instruct. For our use
(faithful translation + triage of distressing SOS text) decensoring is a plus: it won't
refuse on graphic emergency content. 8B fits 32 GB comfortably. (We switched off the
mradermacher `Llama-3.3-8B` repo because it ships no Q4_0 and "Llama-3.3-8B" isn't an
official base; this repo has a ready Q4_0 and is the well-known heretic 8B.)

### Quant choice — DECIDED: Q4_0 on the NPU
For GenieX's GGUF/NPU runtime, **`Q4_0` has the best Hexagon-NPU support**, and this repo
ships one — so that's the default. No self-quantize needed.

| Quant | Size | Runs on | Notes |
|---|---|---|---|
| **Q4_0** | 4.68 GB | **NPU (best)** | **Default.** `p-e-w_Llama-3.1-8B-Instruct-heretic-Q4_0.gguf` |
| Q4_K_M | 4.92 GB | GPU/CPU | Slightly better quality, not NPU-optimal |
| Q8_0 ("int8") | 8.54 GB | GPU/CPU | Highest quality, heaviest |

Default is **Q4_0 + `--device npu`**. Only drop to Q8_0 if you specifically want max quality
and don't mind GPU/CPU placement (translation latency is already fine for our short outputs).

## Steps

### 1. Install GenieX (once)
Download and run `geniex-cli-setup.exe` from `github.com/qualcomm/GenieX`, then open a **new**
terminal so `geniex` is on PATH.

### 2. Pull + serve + wire the command post (one script)
From `backend/` (PowerShell):
```powershell
./setup-geniex.ps1                     # heretic 8B @ Q4_0 on the NPU, serves :18181, writes .env
./setup-geniex.ps1 -Precision Q8_0     # int8 instead (GPU/CPU)
./setup-geniex.ps1 -Device hybrid      # let GenieX mix NPU/GPU/CPU
```
The script pulls the model, starts `geniex serve` as a background job, health-checks
`/v1/models`, smoke-tests `/v1/chat/completions`, and writes `LLM_BASE_URL/LLM_MODEL/
LLM_TIMEOUT_S` into `backend/.env`. (Flags echo before running — the dev-preview CLI
may rename them; confirm with `geniex pull --help` / `geniex serve --help`.)

### 2-alt. Manual
```powershell
geniex pull bartowski/p-e-w_Llama-3.1-8B-Instruct-heretic-GGUF --precision Q4_0
geniex serve --device npu            # → http://127.0.0.1:18181/v1
```
Then set in `backend/.env`:
```
LLM_BASE_URL=http://127.0.0.1:18181/v1
LLM_MODEL=bartowski/p-e-w_Llama-3.1-8B-Instruct-heretic-GGUF
LLM_API_KEY=not-needed
LLM_TIMEOUT_S=60
```

### 3. (Only if you pick a repo without Q4_0) self-quantize
Not needed for the default model — it already ships Q4_0. If you ever switch to a repo that
lacks Q4_0, build one from its f16 with llama.cpp and load the local file:
```powershell
llama-quantize --pure model.f16.gguf heretic.Q4_0.gguf Q4_0
geniex pull local/heretic-q4_0 --model-hub localfs --local-path .\heretic.Q4_0.gguf
geniex serve --device npu
```

### 4. Run the command post
Start it as usual — it reads `.env` and uses GenieX. First triage call includes model load
(hence `LLM_TIMEOUT_S=60`); subsequent calls are fast.

## Verify
- `Invoke-RestMethod http://127.0.0.1:18181/v1/models` lists the served model.
- Replay the Tamil voice clip: transcript unchanged, card English **faithful**
  ("hello, mic testing, one two three"), audio plays.
- Confirm placement: `geniex serve --device npu` (Q4_0) vs the default `hybrid`.

## Troubleshooting (keep failures off the dashboard — project rule #10)
- **No AI output / falls back to rule-based:** `LLM_BASE_URL` unset or server down. Check
  `Receive-Job -Name geniex-serve`.
- **404 / model-not-found:** the `model` field must equal what `geniex serve` loaded; set
  `LLM_MODEL` to that exact id.
- **First call times out:** raise `LLM_TIMEOUT_S` (8B cold load); it's a one-time warm-up.
- **Slow / not on NPU:** you're on Q4_K_M/Q8_0 (GPU/CPU). Use a Q4_0 build + `--device npu`.
- The translation faithfulness fix is the `translate()` prompt (temp 0), independent of the
  model — an 8B just follows it better than the 3B.
