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

$BackendDir  = $PSScriptRoot
$WebDir      = Join-Path $BackendDir 'web'
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

# --- resolve how to run the backend python ------------------------------------
# uv is the project standard: `uv run` resolves backend/pyproject.toml, creating and
# syncing backend/.venv on first use. An already-populated .venv is the fallback so the
# stack still starts on a machine without uv installed.
$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
$WinVenv  = Join-Path $BackendDir '.venv\Scripts\python.exe'
$UnixVenv = Join-Path $BackendDir '.venv\bin\python'
if ($Uv) {
    $Python = $null   # backend is launched through `uv run`
} elseif (Test-Path $WinVenv) {
    $Python = $WinVenv
    Write-Host "WARN: uv not found - falling back to backend/.venv (install uv: https://docs.astral.sh/uv/)"
} elseif (Test-Path $UnixVenv) {
    $Python = $UnixVenv
    Write-Host "WARN: uv not found - falling back to backend/.venv (install uv: https://docs.astral.sh/uv/)"
} else {
    $Python = 'python'
    Write-Host "WARN: neither uv nor backend/.venv found - using system 'python'"
}

# --- LLM backend (GenieX on the NPU) -----------------------------------------
# The command post's triage/translate LLM (Gemma 4 E4B) is served by GenieX over an
# OpenAI-compatible API. dev.ps1 must guarantee it is up, otherwise every triage call
# fails with a connection error and the flow stalls. We read the endpoint + model id
# straight from backend/.env so this never drifts from what the backend expects.
$EnvFile   = Join-Path $BackendDir '.env'
$GenieXBase  = 'http://127.0.0.1:18181/v1'
$GenieXModel = 'bartowski/google_gemma-4-E4B-it-GGUF:Q4_K_M'
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*LLM_BASE_URL\s*=\s*(.+?)\s*$') { $GenieXBase  = $Matches[1].Trim('"').Trim("'") }
        if ($line -match '^\s*LLM_MODEL\s*=\s*(.+?)\s*$')    { $GenieXModel = $Matches[1].Trim('"').Trim("'") }
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
function Ensure-GenieX {
    $modelsUrl = "$GenieXBase/models"
    if (Test-Http $modelsUrl) { Write-Host "  GenieX already serving on $GenieXBase"; return }

    $geniex = (Get-Command geniex -ErrorAction SilentlyContinue).Source
    if (-not $geniex) {
        $cand = Join-Path $env:LOCALAPPDATA 'GenieX CLI\geniex.exe'
        if (Test-Path $cand) { $geniex = $cand }
    }
    if (-not $geniex) {
        Write-Host "  WARN: GenieX not found on PATH or in %LOCALAPPDATA%\GenieX CLI." -ForegroundColor Yellow
        Write-Host "        The LLM (triage/translate) will be unavailable. Install it, then re-run." -ForegroundColor Yellow
        return
    }

    $logDir = Join-Path $BackendDir 'logs'
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    Write-Host "  starting 'geniex serve' (LLM on the NPU)..."
    Start-Process -FilePath $geniex -ArgumentList 'serve' `
        -RedirectStandardOutput (Join-Path $logDir 'geniex.out.log') `
        -RedirectStandardError  (Join-Path $logDir 'geniex.err.log') `
        -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Http $modelsUrl) { Write-Host "  GenieX up on $GenieXBase"; return }
    }
    Write-Host "  WARN: GenieX did not answer within 30s; see command-post\logs\geniex.err.log" -ForegroundColor Yellow
}

# Fire a tiny completion so GenieX loads Gemma onto the NPU now (~30 s cold), instead of
# stalling the first real SOS during the demo. Runs in the background; we do not wait.
function Warm-LLM {
    if (-not (Test-Http "$GenieXBase/models")) { return }
    Write-Host "  warming the LLM (loading Gemma onto the NPU in the background)..."
    $body = @{ model = $GenieXModel; messages = @(@{ role = 'user'; content = 'ping' }); max_tokens = 1; temperature = 0 } | ConvertTo-Json -Depth 5
    Start-Job -Name geniex-warm -ScriptBlock {
        param($u, $b)
        try { Invoke-RestMethod -Uri "$u/chat/completions" -Method Post -ContentType 'application/json' -Body $b -TimeoutSec 120 | Out-Null } catch {}
    } -ArgumentList $GenieXBase, $body | Out-Null
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

    Write-Host "==> Ensuring LLM backend (GenieX / NPU) is up"
    Ensure-GenieX
    Warm-LLM

    Write-Host "==> Starting backend (FastAPI) on :$BackendPort"
    if ($Uv) {
        $backend = Start-Process -FilePath $Uv `
            -ArgumentList @('run', 'uvicorn', 'app:app', '--host', '0.0.0.0', '--port', "$BackendPort", '--reload') `
            -WorkingDirectory $BackendDir -NoNewWindow -PassThru
    } else {
        $backend = Start-Process -FilePath $Python `
            -ArgumentList @('-m', 'uvicorn', 'app:app', '--host', '0.0.0.0', '--port', "$BackendPort", '--reload') `
            -WorkingDirectory $BackendDir -NoNewWindow -PassThru
    }
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
    Write-Host "LLM     : $GenieXBase  (GenieX / Gemma 4 E4B on the NPU)"
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
