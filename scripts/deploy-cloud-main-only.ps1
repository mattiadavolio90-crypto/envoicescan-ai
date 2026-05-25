Param(
    [string]$ServiceName = "frontend"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Host "" -ForegroundColor Red
    Write-Host "BLOCCO DEPLOY: $Message" -ForegroundColor Red
    Write-Host "" -ForegroundColor Red
    exit 1
}

# Verifica repository Git
$insideRepo = (git rev-parse --is-inside-work-tree 2>$null)
if ($insideRepo -ne "true") {
    Fail "cartella non dentro un repository Git."
}

$currentBranch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($currentBranch -ne "main") {
    Fail "deploy consentito solo da branch 'main'. Branch corrente: '$currentBranch'."
}

# Richiede working tree pulita per evitare deploy non riproducibili
$dirty = git status --porcelain
if ($dirty) {
    Fail "working tree non pulita. Committa/stasha prima di deployare."
}

# Richiede main locale allineato a origin/main
git fetch origin main --quiet
$localMain = (git rev-parse main).Trim()
$originMain = (git rev-parse origin/main).Trim()
if ($localMain -ne $originMain) {
    Fail "main locale non allineato a origin/main. Esegui push/pull prima del deploy."
}

Write-Host "Branch OK: main" -ForegroundColor Green
Write-Host "Repo pulita e allineata a origin/main" -ForegroundColor Green

# Verifica login Railway
$who = (railway whoami 2>$null)
if (-not $who) {
    Fail "Railway CLI non autenticata. Esegui 'railway login'."
}

Write-Host "Railway login OK: $who" -ForegroundColor Green
Write-Host "Link servizio Railway: $ServiceName" -ForegroundColor Cyan
railway service link $ServiceName | Out-Host

Write-Host "Deploy Railway in corso..." -ForegroundColor Cyan
railway up | Out-Host

Write-Host "Verifica stato deploy..." -ForegroundColor Cyan
railway service status | Out-Host

Write-Host "" -ForegroundColor Green
Write-Host "DEPLOY COMPLETATO (main-only policy rispettata)." -ForegroundColor Green
Write-Host "" -ForegroundColor Green
