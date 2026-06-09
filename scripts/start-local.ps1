# ═══════════════════════════════════════════════════════════════════════════════
# start-local.ps1 — Avvia l'ambiente locale ONEFLUX (worker FastAPI + frontend Next.js)
# ═══════════════════════════════════════════════════════════════════════════════
#
# USO:
#   .\scripts\start-local.ps1          → avvia worker (porta 8000) + Next.js (porta 3000)
#   .\scripts\start-local.ps1 -Stop    → ferma worker e Next.js
#   .\scripts\start-local.ps1 -Check   → verifica solo i prerequisiti, non avvia nulla
#
# COSA RISOLVE (problemi ricorrenti dell'avvio manuale):
#   • WORKER_SECRET_KEY mancante in apps/web/.env.local → frontend cade sul Railway di prod
#   • Processi worker/Next.js doppi sulle stesse porte
#   • Login lento per il bridge Supabase Auth inutile (SKIP_SUPABASE_AUTH)
#
# PREREQUISITI:
#   • .venv creato con le dipendenze Python
#   • apps/web con node_modules installati
#   • .env (root) con SUPABASE_*, WORKER_SECRET_KEY, SKIP_SUPABASE_AUTH=1
# ═══════════════════════════════════════════════════════════════════════════════
param(
    [switch]$Stop,
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$ROOT     = Split-Path -Parent $PSScriptRoot
$VENV_PY  = Join-Path $ROOT ".venv\Scripts\python.exe"
$WEB_DIR  = Join-Path $ROOT "apps\web"
$ENV_ROOT = Join-Path $ROOT ".env"
$ENV_WEB  = Join-Path $WEB_DIR ".env.local"

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
    # Next.js gira sotto npm: ferma anche i node figli rimasti
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

# .env.local del frontend deve avere WORKER_URL locale e WORKER_SECRET_KEY
if (-not (Test-Path $ENV_WEB)) {
    $problemi += "Manca apps/web/.env.local (serve WORKER_URL + WORKER_SECRET_KEY)"
} else {
    $web = Get-Content $ENV_WEB -Raw
    if ($web -notmatch "WORKER_SECRET_KEY=\S") {
        $problemi += "apps/web/.env.local: WORKER_SECRET_KEY mancante o vuota (il frontend cadrebbe sul worker di produzione)"
    }
    if ($web -notmatch "WORKER_URL=http://127\.0\.0\.1:8000|WORKER_URL=http://localhost:8000") {
        $problemi += "apps/web/.env.local: WORKER_URL non punta al worker locale (atteso http://127.0.0.1:8000)"
    }
}

if ($problemi.Count -gt 0) {
    Write-Host ""
    Write-Host "Prerequisiti non soddisfatti:" -ForegroundColor Red
    $problemi | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Suggerimento: copia WORKER_SECRET_KEY dal .env della root in apps/web/.env.local." -ForegroundColor Yellow
    exit 1
}

if ($Check) {
    Write-Host "Prerequisiti OK." -ForegroundColor Green
    exit 0
}

# ─── Evita processi doppi: libera le porte ─────────────────────────────────────
Write-Host "Libero le porte 8000 e 3000 da eventuali processi precedenti..." -ForegroundColor Cyan
Stop-OnPort 8000
Stop-OnPort 3000
Start-Sleep -Seconds 1

# ─── Avvia il worker FastAPI (porta 8000) ──────────────────────────────────────
Write-Host "Avvio worker FastAPI su http://127.0.0.1:8000 ..." -ForegroundColor Green
$worker = Start-Process -FilePath $VENV_PY `
    -ArgumentList "-m", "uvicorn", "services.fastapi_worker:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $ROOT -PassThru -WindowStyle Minimized

# Attendi che il worker risponda su /health
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if ($ready) {
    Write-Host "  Worker pronto (PID $($worker.Id))." -ForegroundColor Green
} else {
    Write-Host "  ATTENZIONE: il worker non risponde su /health dopo 30s. Controlla i log." -ForegroundColor Red
}

# ─── Avvia il frontend Next.js (porta 3000) ────────────────────────────────────
Write-Host "Avvio Next.js su http://localhost:3000 ..." -ForegroundColor Green
$next = Start-Process -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $WEB_DIR -PassThru -WindowStyle Minimized

Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Ambiente locale avviato:" -ForegroundColor Green
Write-Host "    Worker:   http://127.0.0.1:8000  (PID $($worker.Id))" -ForegroundColor Green
Write-Host "    Frontend: http://localhost:3000   (PID $($next.Id))" -ForegroundColor Green
Write-Host ""
Write-Host "  Nota: la prima visita a ogni pagina compila (Turbopack) ed e' lenta." -ForegroundColor Yellow
Write-Host "  Per fermare tutto:  .\scripts\start-local.ps1 -Stop" -ForegroundColor Yellow
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Green
