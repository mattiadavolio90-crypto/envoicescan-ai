# Apre ONEFLUX in locale, avviando i servizi solo se non girano gia'.
#
# Pensato per essere lanciato dal collegamento sul desktop: puoi cliccarlo
# quante volte vuoi, non duplica nulla. Se worker e frontend sono gia' su,
# apre solo il browser (istantaneo).
#
# ATTENZIONE: il locale punta al DB cloud REALE dei clienti.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# localhost:3000 e' la landing pubblica, non l'app: si apre la pagina su cui si
# sta lavorando. Cambiala quando cambia la feature in corso.
$paginaDaAprire = "http://localhost:3000/agenda?layer=personale"

function Test-Servizio($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

$workerSu   = Test-Servizio "http://127.0.0.1:8000/health"
$frontendSu = Test-Servizio "http://localhost:3000"

if ($workerSu -and $frontendSu) {
    Start-Process $paginaDaAprire
    exit 0
}

Write-Host ""
Write-Host "  ONEFLUX - avvio ambiente locale" -ForegroundColor Cyan
Write-Host "  ATTENZIONE: connesso al DB cloud REALE dei clienti." -ForegroundColor Yellow
Write-Host ""

# Preflight: senza queste il worker muore all'avvio (guard fail-closed) e il
# frontend risponde "Servizio momentaneamente non disponibile" dopo il login.
$envRoot = Join-Path $root ".env"
$envWeb  = Join-Path $root "apps\web\.env.local"

function Get-EnvValue($file, $name) {
    if (-not (Test-Path $file)) { return $null }
    $riga = Select-String -Path $file -Pattern "^$name=" | Select-Object -First 1
    if ($null -eq $riga) { return $null }
    return $riga.Line.Substring($name.Length + 1).Trim()
}

$keyWorker = Get-EnvValue $envRoot "WORKER_SECRET_KEY"
$keyWeb    = Get-EnvValue $envWeb  "WORKER_SECRET_KEY"
$problemi  = @()

if ([string]::IsNullOrWhiteSpace($keyWorker)) {
    $problemi += "WORKER_SECRET_KEY manca nel .env root -> il worker non parte (fail-closed)"
}
if ([string]::IsNullOrWhiteSpace($keyWeb)) {
    $problemi += "WORKER_SECRET_KEY manca in apps\web\.env.local -> il worker rifiuta le chiamate (401)"
}
if ($keyWorker -and $keyWeb -and $keyWorker -ne $keyWeb) {
    $problemi += "le due WORKER_SECRET_KEY sono diverse -> il worker risponde 401 a ogni chiamata"
}

if ($problemi.Count -gt 0) {
    Write-Host "  Configurazione incompleta:" -ForegroundColor Red
    foreach ($p in $problemi) { Write-Host "    - $p" -ForegroundColor Red }
    Write-Host ""
    Read-Host "  Premi INVIO per chiudere"
    exit 1
}

if (-not $workerSu) {
    Write-Host "  Avvio worker    -> http://127.0.0.1:8000" -ForegroundColor Green
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root'; `$host.UI.RawUI.WindowTitle='ONEFLUX worker :8000'; `$env:ENABLE_INLINE_QUEUE_PROCESSOR='0'; python -m uvicorn services.fastapi_worker:app --host 127.0.0.1 --port 8000 --reload"
    )
} else {
    Write-Host "  Worker gia' attivo." -ForegroundColor DarkGray
}

if (-not $frontendSu) {
    if (-not (Test-Path (Join-Path $root "apps\web\node_modules"))) {
        Write-Host "  Installo le dipendenze (una volta sola)..." -ForegroundColor Yellow
        Push-Location (Join-Path $root "apps\web")
        npm install
        Pop-Location
    }
    Write-Host "  Avvio frontend  -> http://localhost:3000" -ForegroundColor Green
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root\apps\web'; `$host.UI.RawUI.WindowTitle='ONEFLUX web :3000'; npm run dev"
    )
} else {
    Write-Host "  Frontend gia' attivo." -ForegroundColor DarkGray
}

# Il frontend chiama il worker gia' al primo render: aprire il browser troppo
# presto mostra "Servizio non disponibile" finche' non ricarichi a mano.
Write-Host "  Attendo che i servizi rispondano..." -ForegroundColor DarkGray
$pronti = $false
foreach ($i in 1..60) {
    Start-Sleep -Seconds 1
    if ((Test-Servizio "http://127.0.0.1:8000/health") -and (Test-Servizio "http://localhost:3000")) {
        $pronti = $true
        break
    }
}

if ($pronti) {
    Write-Host "  Pronto -> $paginaDaAprire" -ForegroundColor Green
    Start-Process $paginaDaAprire
    Start-Sleep -Seconds 2
} else {
    Write-Host ""
    Write-Host "  I servizi non rispondono dopo 60s." -ForegroundColor Yellow
    Write-Host "  Guarda le due finestre appena aperte: l'errore e' li'." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  Premi INVIO per chiudere"
}
