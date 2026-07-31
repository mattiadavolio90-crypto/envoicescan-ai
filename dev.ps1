# Avvia l'ambiente di sviluppo locale: worker FastAPI + frontend Next.js.
#
#   .\dev.ps1
#
# Apre due finestre PowerShell (una per servizio) e il browser su localhost:3000.
# Ctrl+C in una finestra ferma quel servizio; chiudere le finestre ferma tutto.
#
# ATTENZIONE: il locale punta al DB cloud REALE. Le modifiche che fai qui
# scrivono sui dati veri dei clienti.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host ""
Write-Host "  ONEFLUX - ambiente locale" -ForegroundColor Cyan
Write-Host "  ATTENZIONE: connesso al DB cloud REALE dei clienti." -ForegroundColor Yellow
Write-Host ""

# ── Preflight: senza queste il worker muore all'avvio e il frontend risponde
#    "Servizio momentaneamente non disponibile" dopo il login.
$envRoot = Join-Path $root ".env"
$envWeb  = Join-Path $root "apps\web\.env.local"
$problemi = @()

if (-not (Test-Path $envRoot)) { $problemi += "manca .env nella root" }
if (-not (Test-Path $envWeb))  { $problemi += "manca apps\web\.env.local" }

if ($problemi.Count -eq 0) {
    function Get-EnvValue($file, $name) {
        $riga = Select-String -Path $file -Pattern "^$name=" | Select-Object -First 1
        if ($null -eq $riga) { return $null }
        return $riga.Line.Substring($name.Length + 1).Trim()
    }

    $keyWorker = Get-EnvValue $envRoot "WORKER_SECRET_KEY"
    $keyWeb    = Get-EnvValue $envWeb  "WORKER_SECRET_KEY"

    if ([string]::IsNullOrWhiteSpace($keyWorker)) {
        $problemi += "WORKER_SECRET_KEY manca nel .env root -> il worker non parte (fail-closed)"
    }
    if ([string]::IsNullOrWhiteSpace($keyWeb)) {
        $problemi += "WORKER_SECRET_KEY manca in apps\web\.env.local -> il worker rifiuta le chiamate (401)"
    }
    if ($keyWorker -and $keyWeb -and $keyWorker -ne $keyWeb) {
        $problemi += "le due WORKER_SECRET_KEY sono diverse -> il worker risponde 401 a ogni chiamata"
    }
    if (-not (Get-EnvValue $envWeb "WORKER_URL")) {
        $problemi += "WORKER_URL manca in apps\web\.env.local (atteso http://127.0.0.1:8000)"
    }
}

if ($problemi.Count -gt 0) {
    Write-Host "  Configurazione incompleta:" -ForegroundColor Red
    foreach ($p in $problemi) { Write-Host "    - $p" -ForegroundColor Red }
    Write-Host ""
    exit 1
}

if (-not (Test-Path (Join-Path $root "apps\web\node_modules"))) {
    Write-Host "  node_modules assente: installo le dipendenze (una volta sola)..." -ForegroundColor Yellow
    Push-Location (Join-Path $root "apps\web")
    npm install
    Pop-Location
}

# ── Worker FastAPI. --reload perche' senza di esso resta in memoria il codice
#    vecchio e sembra che le modifiche non abbiano effetto.
Write-Host "  Avvio worker    -> http://127.0.0.1:8000" -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root'; `$host.UI.RawUI.WindowTitle='ONEFLUX worker :8000'; python -m uvicorn services.fastapi_worker:app --host 127.0.0.1 --port 8000 --reload"
)

# ── Il frontend chiama il worker gia' durante il primo render: se parte prima,
#    la home mostra "Servizio non disponibile" finche' non ricarichi.
Write-Host "  Attendo che il worker risponda..." -ForegroundColor DarkGray
$pronto = $false
foreach ($i in 1..40) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $pronto = $true; break }
    } catch { }
}

if ($pronto) {
    Write-Host "  Worker pronto." -ForegroundColor Green
} else {
    Write-Host "  Il worker non risponde dopo 40s: guarda la sua finestra per l'errore." -ForegroundColor Yellow
    Write-Host "  Avvio comunque il frontend." -ForegroundColor Yellow
}

Write-Host "  Avvio frontend  -> http://localhost:3000" -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\apps\web'; `$host.UI.RawUI.WindowTitle='ONEFLUX web :3000'; npm run dev"
)

Start-Sleep -Seconds 6
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "  Fatto. Due finestre aperte: worker e frontend." -ForegroundColor Cyan
Write-Host "  Il tab Personale e' su http://localhost:3000/workspace" -ForegroundColor DarkGray
Write-Host ""
