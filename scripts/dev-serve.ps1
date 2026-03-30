# ═══════════════════════════════════════════════════════════════════════════════
# dev-serve.ps1 — Avvia l'Edge Function localmente senza Docker
# ═══════════════════════════════════════════════════════════════════════════════
#
# USO:
#   .\dev-serve.ps1              → avvia la funzione (Terminale 1)
#   .\dev-serve.ps1 -Test        → esegue i test (Terminale 2, dopo serve)
#   .\dev-serve.ps1 -Deploy      → deploy su Supabase Cloud
#
# PREREQUISITI:
#   • Compilare supabase/functions/.env con i segreti reali
#   • Deno installato (già fatto)
# ═══════════════════════════════════════════════════════════════════════════════
param(
    [switch]$Test,
    [switch]$Deploy
)

# ─── Percorsi strumenti (installati nella sessione precedente) ─────────────────
$DENO      = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe\deno.exe"
$SUPABASE  = "$PSScriptRoot\..\tools\supabase.exe"
$ENV_FILE  = "$PSScriptRoot\..\supabase\functions\.env"
$FUNC_FILE = "$PSScriptRoot\..\supabase\functions\invoicetronic-webhook\index.ts"
$TEST_FILE = "$PSScriptRoot\..\supabase\functions\invoicetronic-webhook\test.ts"

# ─── Verifica strumenti ────────────────────────────────────────────────────────
if (-not (Test-Path $DENO)) {
    Write-Error "Deno non trovato a: $DENO"
    Write-Host "Installa con: winget install DenoLand.Deno"
    exit 1
}

# ─── Verifica .env compilato ──────────────────────────────────────────────────
if (-not (Test-Path $ENV_FILE)) {
    Write-Error "File .env non trovato: $ENV_FILE"
    exit 1
}
$envContent = Get-Content $ENV_FILE -Raw
if ($envContent -match 'INSERISCI_QUI') {
    Write-Error @"

.env contiene ancora valori placeholder!
Apri  supabase\functions\.env  e sostituisci:
  SUPABASE_SERVICE_ROLE_KEY    → Supabase Dashboard → Settings → API
  INVOICETRONIC_WEBHOOK_SECRET → Dashboard Invoicetronic → Webhooks
  INVOICETRONIC_API_KEY        → Dashboard Invoicetronic → API Keys
"@
    exit 1
}

# ─── Leggi WEBHOOK_SECRET per i test ─────────────────────────────────────────
$webhookSecret = ($envContent -split "`n" |
    Where-Object { $_ -match '^INVOICETRONIC_WEBHOOK_SECRET=' } |
    Select-Object -First 1) -replace '^INVOICETRONIC_WEBHOOK_SECRET=', ''

# ─── Branch: Test ─────────────────────────────────────────────────────────────
if ($Test) {
    Write-Host ""
    Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  Esecuzione test.ts (porta 54321)        " -ForegroundColor Cyan
    Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  Assicurati che dev-serve.ps1 sia        " -ForegroundColor Yellow
    Write-Host "  in esecuzione nell'altro terminale.     " -ForegroundColor Yellow
    Write-Host ""

    $env:WEBHOOK_SECRET = $webhookSecret
    & $DENO run --allow-net --allow-env $TEST_FILE
    exit $LASTEXITCODE
}

# ─── Branch: Deploy su Cloud ──────────────────────────────────────────────────
if ($Deploy) {
    if (-not (Test-Path $SUPABASE)) {
        Write-Error "Supabase CLI non trovato: $SUPABASE"
        exit 1
    }
    Write-Host "Deploy in corso..." -ForegroundColor Cyan
    & $SUPABASE functions deploy invoicetronic-webhook `
        --project-ref vthikmfpywilukizputn `
        --no-verify-jwt
    exit $LASTEXITCODE
}

# ─── Default: Avvia funzione in locale ────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  invoicetronic-webhook → http://localhost:54321  " -ForegroundColor Green
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Nel Terminale 2 esegui: .\dev-serve.ps1 -Test  " -ForegroundColor Yellow
Write-Host "  Per interrompere: Ctrl+C                       " -ForegroundColor Yellow
Write-Host ""

& $DENO run `
    --allow-net `
    --allow-env `
    --allow-read `
    "--env-file=$ENV_FILE" `
    $FUNC_FILE
