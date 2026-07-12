# dev.ps1 — run the whole stack: FastAPI backend (:9000) + Vite frontend (:5173).
# If a port is already in use, the process holding it is killed, then we (re)start.
# Native Windows PowerShell port of dev.sh.
#
# Usage:
#   .\dev.ps1            # start both, stream logs, Ctrl-C stops both
#
# If script execution is blocked, run once (per user):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = 'Stop'

$Root        = $PSScriptRoot
$BackendDir  = Join-Path $Root 'command-post'
$WebDir      = Join-Path $Root 'command-post\web'
$BackendPort = 9000
$FrontendPort = 5173

# --- kill whatever is listening on a TCP port --------------------------------
function Stop-Port {
    param([int]$Port)

    $pids = @()
    try {
        # Get-NetTCPConnection is available on Windows 8+/Server 2012+.
        $pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        # Fall back to parsing netstat if the cmdlet is unavailable.
        $pids = netstat -ano -p tcp |
                Select-String -Pattern "LISTENING" |
                Select-String -Pattern ":$Port\s" |
                ForEach-Object { ($_ -split '\s+')[-1] } |
                Sort-Object -Unique
    }

    foreach ($processId in $pids) {
        if ([string]::IsNullOrWhiteSpace($processId) -or $processId -eq '0') { continue }
        Write-Host "  killing PID $processId on port $Port"
        try { Stop-Process -Id $processId -Force -ErrorAction Stop } catch {}
    }
}

# --- resolve the backend venv python -----------------------------------------
$WinVenv  = Join-Path $BackendDir '.venv\Scripts\python.exe'
$UnixVenv = Join-Path $BackendDir '.venv\bin\python'
if (Test-Path $WinVenv) {
    $Python = $WinVenv
} elseif (Test-Path $UnixVenv) {
    $Python = $UnixVenv
} else {
    $Python = 'python'
    Write-Host "WARN: no command-post/.venv found - using system 'python'"
}

# --- LLM backends (GenieX on the NPU) ----------------------------------------
# The command post runs TWO models on the NPU, each its own task:
#   - Gemma 4 E4B (:18181) - triage + translation (the safety-critical reasoning)
#   - Gemma 4 E2B (:18182) - fast structured tag extraction (triage.extract_tags)
# They run as SEPARATE `geniex serve` instances so the NPU keeps both resident at once:
# a single server reloads ~15 s on every model switch, but two servers stay warm (~1 s
# each, measured on the X Elite). dev.ps1 must guarantee both are up, else triage/tagging
# fails with a connection error. Endpoints + model ids come straight from command-post/.env
# so this never drifts from what the backend expects.
$EnvFile   = Join-Path $BackendDir '.env'
$GenieXBase  = 'http://127.0.0.1:18181/v1'
$GenieXModel = 'bartowski/google_gemma-4-E4B-it-GGUF:Q4_K_M'
$TagsBase    = 'http://127.0.0.1:18182/v1'
$TagsModel   = 'bartowski/google_gemma-4-E2B-it-GGUF:Q4_K_M'
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*LLM_BASE_URL\s*=\s*(.+?)\s*$')      { $GenieXBase  = $Matches[1].Trim('"').Trim("'") }
        if ($line -match '^\s*LLM_MODEL\s*=\s*(.+?)\s*$')         { $GenieXModel = $Matches[1].Trim('"').Trim("'") }
        if ($line -match '^\s*TAGS_LLM_BASE_URL\s*=\s*(.+?)\s*$') { $TagsBase    = $Matches[1].Trim('"').Trim("'") }
        if ($line -match '^\s*TAGS_LLM_MODEL\s*=\s*(.+?)\s*$')    { $TagsModel   = $Matches[1].Trim('"').Trim("'") }
    }
}

function Test-Http {
    param([string]$Url)
    try { Invoke-RestMethod -Uri $Url -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

# Start `geniex serve` if it is not already answering. We deliberately do NOT track it
# in $script:Procs, so Ctrl-C leaves it running — a cold GenieX load costs ~30 s, so
# reusing it across dev restarts keeps the loop fast. Stop it manually when done:
#   Get-Process geniex | Stop-Process
# Start one `geniex serve` bound to $Base's host:port if it isn't already answering. Called
# once per model so each server only ever serves its own model and never reloads. $Label is
# a short filename-safe tag (e4b/e2b) used for the per-server log files.
function Ensure-GenieX {
    param([string]$Base, [string]$Label)
    $modelsUrl = "$Base/models"
    if (Test-Http $modelsUrl) { Write-Host "  GenieX ($Label) already serving on $Base"; return }

    $geniex = (Get-Command geniex -ErrorAction SilentlyContinue).Source
    if (-not $geniex) {
        $cand = Join-Path $env:LOCALAPPDATA 'GenieX CLI\geniex.exe'
        if (Test-Path $cand) { $geniex = $cand }
    }
    if (-not $geniex) {
        Write-Host "  WARN: GenieX not found on PATH or in %LOCALAPPDATA%\GenieX CLI." -ForegroundColor Yellow
        Write-Host "        The LLM ($Label) will be unavailable. Install it, then re-run." -ForegroundColor Yellow
        return
    }

    $bind = $Base -replace '^https?://', '' -replace '/v1/?$', ''   # 'http://127.0.0.1:18182/v1' -> '127.0.0.1:18182'
    $logDir = Join-Path $BackendDir 'logs'
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    Write-Host "  starting 'geniex serve --host $bind' ($Label on the NPU)..."
    Start-Process -FilePath $geniex -ArgumentList @('serve', '--host', $bind) `
        -RedirectStandardOutput (Join-Path $logDir "geniex.$Label.out.log") `
        -RedirectStandardError  (Join-Path $logDir "geniex.$Label.err.log") `
        -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Http $modelsUrl) { Write-Host "  GenieX ($Label) up on $Base"; return }
    }
    Write-Host "  WARN: GenieX ($Label) did not answer within 30s; see command-post\logs\geniex.$Label.err.log" -ForegroundColor Yellow
}

# Fire a tiny completion so GenieX loads the model onto the NPU now (~30 s cold), instead of
# stalling the first real SOS during the demo. Runs in the background; we do not wait.
function Warm-LLM {
    param([string]$Base, [string]$Model, [string]$Label)
    if (-not (Test-Http "$Base/models")) { return }
    Write-Host "  warming $Label (loading onto the NPU in the background)..."
    $body = @{ model = $Model; messages = @(@{ role = 'user'; content = 'ping' }); max_tokens = 1; temperature = 0 } | ConvertTo-Json -Depth 5
    Start-Job -Name "geniex-warm-$Label" -ScriptBlock {
        param($u, $b)
        try { Invoke-RestMethod -Uri "$u/chat/completions" -Method Post -ContentType 'application/json' -Body $b -TimeoutSec 120 | Out-Null } catch {}
    } -ArgumentList $Base, $body | Out-Null
}

# --- track child processes for cleanup ---------------------------------------
$script:Procs = @()

function Cleanup {
    Write-Host ""
    Write-Host "Shutting down..."
    foreach ($p in $script:Procs) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {}
        }
    }
    # also free the ports in case children spawned grandchildren
    Stop-Port $BackendPort
    Stop-Port $FrontendPort
}

try {
    Write-Host "==> Freeing ports"
    Stop-Port $BackendPort
    Stop-Port $FrontendPort

    Write-Host "==> Ensuring LLM backends (GenieX / NPU) are up - E4B (triage) + E2B (tags)"
    Ensure-GenieX -Base $GenieXBase -Label 'e4b'
    Ensure-GenieX -Base $TagsBase   -Label 'e2b'
    Warm-LLM -Base $GenieXBase -Model $GenieXModel -Label 'Gemma 4 E4B (triage)'
    Warm-LLM -Base $TagsBase   -Model $TagsModel   -Label 'Gemma 4 E2B (tags)'

    Write-Host "==> Starting backend (FastAPI) on :$BackendPort"
    $backend = Start-Process -FilePath $Python `
        -ArgumentList @('-m', 'uvicorn', 'app:app', '--host', '0.0.0.0', '--port', "$BackendPort", '--reload') `
        -WorkingDirectory $BackendDir -NoNewWindow -PassThru
    $script:Procs += $backend

    Write-Host "==> Starting frontend (Vite) on :$FrontendPort"
    if (-not (Test-Path (Join-Path $WebDir 'node_modules'))) {
        Write-Host "  node_modules missing - running npm install first"
        Push-Location $WebDir
        try { & npm install } finally { Pop-Location }
    }
    # npm is a .cmd shim on Windows; launch it through cmd so Start-Process resolves it.
    $frontend = Start-Process -FilePath 'cmd.exe' `
        -ArgumentList @('/c', 'npm', 'run', 'dev', '--', '--port', "$FrontendPort") `
        -WorkingDirectory $WebDir -NoNewWindow -PassThru
    $script:Procs += $frontend

    Write-Host ""
    Write-Host "Backend : http://localhost:$BackendPort   (dashboard served by FastAPI)"
    Write-Host "Frontend: http://localhost:$FrontendPort  (Vite dev server, live UI)"
    Write-Host "LLM     : $GenieXBase  (E4B / triage)  +  $TagsBase  (E2B / tags)  - both on the NPU"
    Write-Host "STT     : AI4Bharat IndicConformer-600M on CPU (loads on first voice clip)"
    Write-Host "Press Ctrl-C to stop the backend + frontend (GenieX keeps running)."
    Write-Host ""

    # wait on both; if either dies, keep going until Ctrl-C
    while ($true) {
        Start-Sleep -Seconds 1
        if ($backend.HasExited -and $frontend.HasExited) { break }
    }
} finally {
    Cleanup
}
