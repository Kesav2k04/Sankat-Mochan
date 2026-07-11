<#
  setup-geniex.ps1 — stand up GenieX as the command post's LLM backend on a
  Snapdragon X Elite (Windows-on-ARM), then wire the command post to it.

  GenieX (https://github.com/qualcomm/GenieX) runs GGUF models on the Hexagon NPU /
  Adreno GPU / CPU and exposes an OpenAI-compatible API at http://127.0.0.1:18181/v1,
  so the command post needs no code change — only the .env this script writes.

  Prereq: install GenieX first (download + run geniex-cli-setup.exe from the repo),
  then open a NEW terminal so `geniex` is on PATH.

  Usage (from command-post/):
    ./setup-geniex.ps1                      # default: heretic 8B, Q4_K_M (runs immediately)
    ./setup-geniex.ps1 -Precision Q8_0      # highest quality, heavier (8.6 GB)
    ./setup-geniex.ps1 -Model <hf/repo-GGUF> -Precision Q4_0   # Q4_0 = best NPU support

  NOTE: the exact `geniex pull/serve` flags are from the GenieX dev preview and may shift
  between releases — this script echoes each command before running it so you can confirm.
#>
[CmdletBinding()]
param(
  [string]$Model     = "mradermacher/Llama-3.3-8B-Instruct-heretic-GGUF",
  [string]$Precision = "Q4_K_M",   # Q4_0 best for NPU (not in this repo); Q4_K_M/Q8_0 = GPU/CPU
  [int]   $Port      = 18181,
  [string]$Device    = "hybrid",   # hybrid (default, fastest) | npu | gpu | cpu
  [switch]$NoServe                 # only write .env + health-check an already-running server
)

$ErrorActionPreference = "Stop"
$Base = "http://127.0.0.1:$Port/v1"

function Info($m) { Write-Host "[geniex-setup] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[geniex-setup] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[geniex-setup] $m" -ForegroundColor Red; exit 1 }

# 1. GenieX present?
if (-not (Get-Command geniex -ErrorAction SilentlyContinue)) {
  Die "geniex not on PATH. Install geniex-cli-setup.exe from https://github.com/qualcomm/GenieX, open a NEW terminal, and re-run."
}
Info "geniex found: $((Get-Command geniex).Source)"

if ($Precision -ne "Q4_0") {
  Warn "Precision '$Precision' runs on GPU/CPU. For best Hexagon-NPU acceleration use Q4_0 (this repo has none — see GENIEX-SETUP.md to self-quantize)."
}

if (-not $NoServe) {
  # 2. Pull the model at the chosen precision. GenieX selects the quant file by precision.
  Info "Pulling $Model ($Precision) — first run downloads several GB..."
  Write-Host "  > geniex pull $Model --precision $Precision" -ForegroundColor DarkGray
  geniex pull $Model --precision $Precision
  if ($LASTEXITCODE -ne 0) { Die "geniex pull failed. Check the model id/precision exists on Hugging Face, and confirm the pull flags for your GenieX version (geniex pull --help)." }

  # 3. Serve (OpenAI-compatible) in a background job so this script can health-check it.
  Info "Starting 'geniex serve' on $Base (device=$Device) in a background job..."
  Write-Host "  > geniex serve --model $Model --port $Port --device $Device" -ForegroundColor DarkGray
  Start-Job -Name geniex-serve -ScriptBlock {
    param($m,$p,$d) geniex serve --model $m --port $p --device $d
  } -ArgumentList $Model,$Port,$Device | Out-Null
}

# 4. Health-check: wait for /v1/models (an 8B cold start can take 30-60s to load).
Info "Waiting for the OpenAI endpoint at $Base (up to 120s for model load)..."
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    Invoke-RestMethod -Uri "$Base/models" -TimeoutSec 3 | Out-Null
    $ok = $true; break
  } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) {
  Warn "Endpoint not answering yet. Check the job:  Receive-Job -Name geniex-serve"
  Warn "If serve flags differ in your version, run it manually:  geniex serve   (then re-run with -NoServe)"
} else {
  Info "GenieX is serving at $Base"
}

# 5. Wire the command post: write LLM_* into command-post/.env (preserving other keys).
$envPath = Join-Path $PSScriptRoot ".env"
$want = @{
  "LLM_BASE_URL"  = $Base
  "LLM_MODEL"     = $Model
  "LLM_API_KEY"   = "not-needed"
  "LLM_TIMEOUT_S" = "60"          # 8B first-call includes model load; keep this generous
}
if (Test-Path $envPath) { $lines = @(Get-Content $envPath) } else { $lines = @() }
foreach ($k in $want.Keys) {
  $set = "$k=$($want[$k])"
  if ($lines -match "^$k=") { $lines = $lines -replace "^$k=.*", $set }
  else { $lines += $set }
}
Set-Content -Path $envPath -Value $lines -Encoding UTF8
Info "Wrote LLM_* to $envPath (LLM_MODEL=$Model)"

# 6. Smoke test the actual chat path the command post uses.
if ($ok) {
  Info "Smoke-testing /v1/chat/completions ..."
  $body = @{ model = $Model; messages = @(@{ role = "user"; content = "Reply with the single word: ready" }); max_tokens = 8 } | ConvertTo-Json -Depth 5
  try {
    $r = Invoke-RestMethod -Uri "$Base/chat/completions" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 90
    Info "Model replied: $($r.choices[0].message.content.Trim())"
    Info "DONE. Start the command post; it will use GenieX. (Stop server later: Stop-Job geniex-serve)"
  } catch {
    Warn "Chat test failed: $($_.Exception.Message). The server is up but the chat route errored — check the model id matches what 'geniex serve' loaded."
  }
}
