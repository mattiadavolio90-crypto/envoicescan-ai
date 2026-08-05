# ═══════════════════════════════════════════════════════════════════════════════
# start-local.ps1 — Avvia l'ambiente locale ONEFLUX (worker FastAPI + frontend Next.js)
# ═══════════════════════════════════════════════════════════════════════════════
#
# USO:
#   .\scripts\start-local.ps1              → avvia (o, se già su, apre solo il browser)
#   .\scripts\start-local.ps1 -Stop        → ferma worker e Next.js
#   .\scripts\start-local.ps1 -Check       → verifica solo i prerequisiti, non avvia nulla
#   .\scripts\start-local.ps1 -Visible     → come sopra ma con le finestre PowerShell visibili
#   .\scripts\start-local.ps1 -NoBrowser   → avvia senza aprire il browser
#   .\scripts\start-local.ps1 -Path "/agenda?layer=personale"   → apre una route diversa da /dashboard
#
# SCRIPT UNICO: dev.ps1 e apri-oneflux-locale.ps1 sono stati assorbiti qui ed eliminati.
# Se coesistessero di nuovo, tornerebbero a scollarsi: le correzioni fatte in uno non si
# propagavano agli altri, ed è così che il problema "risolto una volta" si ripresentava.
#
# COSA RISOLVE (problemi ricorrenti dell'avvio manuale):
#   • WORKER_SECRET_KEY diversa tra .env (root) e apps/web/.env.local → il worker
#     risponde 401 a ogni chiamata dopo il login. Root è la fonte: questo script
#     allinea apps/web/.env.local ad ogni avvio, non serve più editarla a mano.
#   • WORKER_URL assente/malformata → il frontend locale cade sul worker di
#     produzione Railway, in silenzio. Bloccante se non punta al worker locale.
#   • Processi worker/Next.js doppi sulle stesse porte.
#   • Frontend che parte prima del worker → "Servizio non disponibile" al primo giro.
#
# PREREQUISITI:
#   • .venv creato con le dipendenze Python
#   • apps/web con node_modules installati
#   • .env (root) con SUPABASE_*, WORKER_SECRET_KEY, SKIP_SUPABASE_AUTH=1
# ═══════════════════════════════════════════════════════════════════════════════
param(
    [switch]$Stop,
    [switch]$Check,
    [switch]$Visible,
    [switch]$NoBrowser,
    [string]$Path = "/dashboard"
)

$ErrorActionPreference = "Stop"
$ROOT     = Split-Path -Parent $PSScriptRoot
$VENV_PY  = Join-Path $ROOT ".venv\Scripts\python.exe"
$WEB_DIR  = Join-Path $ROOT "apps\web"
$ENV_ROOT = Join-Path $ROOT ".env"
$ENV_WEB  = Join-Path $WEB_DIR ".env.local"
$PAGINA   = "http://localhost:3000$Path"

function Get-EnvValue($file, $name) {
    if (-not (Test-Path $file)) { return $null }
    $riga = Select-String -Path $file -Pattern "^$name=" | Select-Object -First 1
    if ($null -eq $riga) { return $null }
    return $riga.Line.Substring($name.Length + 1).Trim()
}

function Set-EnvValue($file, $name, $value) {
    $righe = Get-Content $file
    $pattern = "^$name="
    $trovata = $false
    $nuove = foreach ($riga in $righe) {
        if ($riga -match $pattern) {
            $trovata = $true
            "$name=$value"
        } else {
            $riga
        }
    }
    if (-not $trovata) { $nuove += "$name=$value" }
    Set-Content -Path $file -Value $nuove
}

function Test-Servizio($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Stop-OnPort($port) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "  Fermato processo PID $($c.OwningProcess) sulla porta $port" -ForegroundColor Yellow
    }
}

# ─── Branch: Stop ──────────────────────────────────────────────────────────────
if ($Stop) {
    Write-Host "Fermo l'ambiente locale..." -ForegroundColor Cyan
    Stop-OnPort 8000
    Stop-OnPort 3000
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match "next dev|fastapi_worker:app"
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Fatto." -ForegroundColor Green
    exit 0
}

# ─── Verifica prerequisiti ─────────────────────────────────────────────────────
$problemi = @()

if (-not (Test-Path $VENV_PY))  { $problemi += "Manca il venv Python: $VENV_PY" }
if (-not (Test-Path $WEB_DIR))  { $problemi += "Manca apps/web: $WEB_DIR" }
if (-not (Test-Path $ENV_ROOT)) { $problemi += "Manca il .env nella root del progetto" }

$keyRoot = if (Test-Path $ENV_ROOT) { Get-EnvValue $ENV_ROOT "WORKER_SECRET_KEY" } else { $null }
if ([string]::IsNullOrWhiteSpace($keyRoot)) {
    $problemi += "WORKER_SECRET_KEY manca nel .env root -> il worker non parte (fail-closed)"
}

if ($problemi.Count -gt 0) {
    Write-Host ""
    Write-Host "Prerequisiti non soddisfatti:" -ForegroundColor Red
    $problemi | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    exit 1
}

# ─── Sync automatica WORKER_SECRET_KEY: root è la fonte, apps/web si allinea ───
if (-not (Test-Path $ENV_WEB)) {
    Write-Host "Creo apps/web/.env.local (mancante) con WORKER_SECRET_KEY dalla root..." -ForegroundColor Yellow
    Set-Content -Path $ENV_WEB -Value @(
        "WORKER_URL=http://127.0.0.1:8000"
        "WORKER_SECRET_KEY=$keyRoot"
    )
} else {
    $keyWeb = Get-EnvValue $ENV_WEB "WORKER_SECRET_KEY"
    if ($keyWeb -ne $keyRoot) {
        Write-Host "Sincronizzata WORKER_SECRET_KEY in apps/web/.env.local (era $(if ([string]::IsNullOrWhiteSpace($keyWeb)) { 'mancante' } else { 'diversa' }))." -ForegroundColor Yellow
        Set-EnvValue $ENV_WEB "WORKER_SECRET_KEY" $keyRoot
    }
}

# ─── WORKER_URL: deve puntare al worker locale, mai un fallback silenzioso ─────
$workerUrl = Get-EnvValue $ENV_WEB "WORKER_URL"
if ([string]::IsNullOrWhiteSpace($workerUrl) -or $workerUrl -notmatch "^http://(127\.0\.0\.1|localhost):8000") {
    Write-Host ""
    Write-Host "apps/web/.env.local: WORKER_URL non punta al worker locale (valore attuale: '$workerUrl')." -ForegroundColor Red
    Write-Host "Senza questo, il frontend locale chiamerebbe il worker di produzione Railway." -ForegroundColor Red
    Write-Host "Atteso: WORKER_URL=http://127.0.0.1:8000" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

if ($Check) {
    Write-Host "Prerequisiti OK." -ForegroundColor Green
    exit 0
}

# ─── Idempotenza: se già tutto su, apri solo il browser ────────────────────────
$workerSu   = Test-Servizio "http://127.0.0.1:8000/health"
$frontendSu = Test-Servizio "http://localhost:3000"

if ($workerSu -and $frontendSu) {
    Write-Host "Ambiente già attivo." -ForegroundColor DarkGray
    if (-not $NoBrowser) { Start-Process $PAGINA }
    exit 0
}

# ─── Libera le porte da eventuali processi zombie ──────────────────────────────
Write-Host "Libero le porte 8000 e 3000 da eventuali processi precedenti..." -ForegroundColor Cyan
Stop-OnPort 8000
Stop-OnPort 3000
Start-Sleep -Seconds 1

# ─── Avvia il worker FastAPI (porta 8000) ──────────────────────────────────────
Write-Host "Avvio worker FastAPI su http://127.0.0.1:8000 ..." -ForegroundColor Green
if ($Visible) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$ROOT'; `$host.UI.RawUI.WindowTitle='ONEFLUX worker :8000'; `$env:ENABLE_INLINE_QUEUE_PROCESSOR='0'; python -m uvicorn services.fastapi_worker:app --host 127.0.0.1 --port 8000 --reload"
    )
} else {
    $env:ENABLE_INLINE_QUEUE_PROCESSOR = "0"
    Start-Process -FilePath $VENV_PY `
        -ArgumentList "-m", "uvicorn", "services.fastapi_worker:app", "--host", "127.0.0.1", "--port", "8000", "--reload" `
        -WorkingDirectory $ROOT -WindowStyle Minimized | Out-Null
}

# Attendi che il worker risponda su /health
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    if (Test-Servizio "http://127.0.0.1:8000/health") { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if ($ready) {
    Write-Host "  Worker pronto." -ForegroundColor Green
} else {
    Write-Host "  ATTENZIONE: il worker non risponde su /health dopo 40s. Controlla i log." -ForegroundColor Red
}

# ─── Avvia il frontend Next.js (porta 3000) ────────────────────────────────────
Write-Host "Avvio Next.js su http://localhost:3000 ..." -ForegroundColor Green
if ($Visible) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$WEB_DIR'; `$host.UI.RawUI.WindowTitle='ONEFLUX web :3000'; npm run dev"
    )
} else {
    # -FilePath "npm" fallisce silenziosamente ("non e' un'applicazione Win32
    # valida"): su Windows npm risolve a npm.ps1/npm.cmd, non a un eseguibile
    # diretto. cmd /c lo risolve sempre correttamente.
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev" `
        -WorkingDirectory $WEB_DIR -WindowStyle Minimized | Out-Null
}

# Attendi che anche il frontend risponda prima di aprire il browser: se il
# frontend chiama il worker durante il primo render prima che sia pronto,
# la home mostra "Servizio non disponibile" finché non si ricarica a mano.
$pronto = $false
for ($i = 0; $i -lt 40; $i++) {
    if (Test-Servizio "http://localhost:3000") { $pronto = $true; break }
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Ambiente locale avviato:" -ForegroundColor Green
Write-Host "    Worker:   http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "    Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "  Per fermare tutto:  .\scripts\start-local.ps1 -Stop" -ForegroundColor Yellow
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Green

if ($pronto -and -not $NoBrowser) {
    Start-Process $PAGINA
} elseif (-not $pronto) {
    Write-Host "  Il frontend non risponde ancora dopo 40s: apri $PAGINA a mano tra poco." -ForegroundColor Yellow
}
