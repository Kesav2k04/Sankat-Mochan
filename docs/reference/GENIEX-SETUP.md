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
**`mradermacher/Llama-3.3-8B-Instruct-heretic-GGUF`** — Llama-3.3 8B, "heretic" =
abliterated/decensored instruct tune. For our use (faithful translation + triage of
distressing SOS text) decensoring is a plus: it won't refuse on graphic emergency content.
8B fits 32 GB comfortably.

### Quant choice — READ THIS
For GenieX's GGUF/NPU runtime, **`Q4_0` has the best Hexagon-NPU support**. This repo does
**not** ship a Q4_0 file, so there's a trade-off:

| Quant | Size | Runs on | Notes |
|---|---|---|---|
| **Q4_0** | ~4.6 GB | **NPU (best)** | Not in this repo → self-quantize (below) for full NPU speed |
| **Q4_K_M** | 5.0 GB | GPU/CPU (fast on X Elite) | **Default** — one-command pull, good quality, runs now |
| **Q8_0** ("int8") | 8.6 GB | GPU/CPU | Highest quality, heaviest; what you first asked for |

Recommendation: start on **Q4_K_M** to be running in minutes; move to **Q4_0** only if you
want the model pinned on the NPU (translation latency is already fine for our short outputs).

## Steps

### 1. Install GenieX (once)
Download and run `geniex-cli-setup.exe` from `github.com/qualcomm/GenieX`, then open a **new**
terminal so `geniex` is on PATH.

### 2. Pull + serve + wire the command post (one script)
From `command-post/` (PowerShell):
```powershell
./setup-geniex.ps1                     # heretic 8B @ Q4_K_M, serves :18181, writes .env
./setup-geniex.ps1 -Precision Q8_0     # int8 instead
./setup-geniex.ps1 -Device npu         # force NPU placement (use with a Q4_0 model)
```
The script pulls the model, starts `geniex serve` as a background job, health-checks
`/v1/models`, smoke-tests `/v1/chat/completions`, and writes `LLM_BASE_URL/LLM_MODEL/
LLM_TIMEOUT_S` into `command-post/.env`. (Flags echo before running — the dev-preview CLI
may rename them; confirm with `geniex pull --help` / `geniex serve --help`.)

### 2-alt. Manual
```powershell
geniex pull mradermacher/Llama-3.3-8B-Instruct-heretic-GGUF --precision Q4_K_M
geniex serve            # → http://127.0.0.1:18181/v1
```
Then set in `command-post/.env`:
```
LLM_BASE_URL=http://127.0.0.1:18181/v1
LLM_MODEL=mradermacher/Llama-3.3-8B-Instruct-heretic-GGUF
LLM_API_KEY=not-needed
LLM_TIMEOUT_S=60
```

### 3. (Optional) Q4_0 for full NPU
The repo has no Q4_0. Build one from the f16 with llama.cpp, then load the local file:
```powershell
# needs llama.cpp's llama-quantize + the f16 GGUF (16.2 GB) from the same HF repo
llama-quantize --pure Llama-3.3-8B-Instruct-heretic.f16.gguf heretic.Q4_0.gguf Q4_0
geniex pull local/heretic-q4_0 --model-hub localfs --local-path .\heretic.Q4_0.gguf
geniex serve --device npu
```
(`--pure` forces every tensor to Q4_0, which the Adreno/Hexagon path wants.)

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
