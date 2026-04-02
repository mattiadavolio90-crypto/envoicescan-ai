# Bootstrap CLI Status - Verifica rapida connessioni GitHub, Railway, Supabase
# Tempo di esecuzione: ~3-5 secondi

param(
    [switch]$Verbose,
    [switch]$FixPath
)

$ErrorActionPreference = "SilentlyContinue"
$results = @{
    github   = $false
    railway  = $false
    supabase = $false
}

Write-Host "Verifica CLI connessioni..." -ForegroundColor Cyan

# Fix PATH se richiesto
if ($FixPath) {
    $ghPath = "C:\Program Files\GitHub CLI"
    if ((Test-Path $ghPath) -and ($env:PATH -notlike "*$ghPath*")) {
        $env:PATH = "$ghPath;$env:PATH"
        Write-Host "[OK] PATH aggiornato per GitHub CLI" -ForegroundColor Green
    }
}

# GitHub Check
Write-Host "[CHECK] GitHub CLI..." -NoNewline
$gh = & "C:\Program Files\GitHub CLI\gh.exe" auth status 2>&1
if ($LASTEXITCODE -eq 0) {
    $user = $gh | Select-String "Logged in" | ForEach-Object { $_ -replace '.*to github.com account ', '' -replace ' .*','' }
    Write-Host " [OK] ($user)" -ForegroundColor Green
    $results.github = $true
} else {
    Write-Host " [NO] Non autenticato" -ForegroundColor Red
}

# Railway Check
Write-Host "[CHECK] Railway CLI..." -NoNewline
$railway = railway whoami 2>&1
if ($LASTEXITCODE -eq 0) {
    $user = $railway | Select-String "Logged in as" -ErrorAction SilentlyContinue | ForEach-Object { $_ -replace '.*Logged in as ', '' }
    if (-not $user) { $user = "Account attivo" }
    Write-Host " [OK] ($user)" -ForegroundColor Green
    $results.railway = $true
} else {
    Write-Host " [NO] Non autenticato" -ForegroundColor Red
}

# Supabase Check
Write-Host "[CHECK] Supabase CLI..." -NoNewline
$supabase = supabase projects list 2>&1
if ($LASTEXITCODE -eq 0) {
    $projectCount = ($supabase | Select-String "LINKED" | Measure-Object).Count
    Write-Host " [OK] ($projectCount progetto/i)" -ForegroundColor Green
    $results.supabase = $true
} else {
    Write-Host " [NO] Non autenticato/connesso" -ForegroundColor Red
}

# Summary
$allOk = $results.Values | Where-Object { $_ -eq $true } | Measure-Object | Select-Object -ExpandProperty Count
$total = $results.Count

Write-Host "`nRISULTATO: $allOk/$total servizi connessi" -ForegroundColor $(if ($allOk -eq $total) { "Green" } else { "Yellow" })

if ($Verbose) {
    Write-Host "`nDettagli completi:`n"
    & "C:\Program Files\GitHub CLI\gh.exe" auth status
    Write-Host ""
    railway whoami
    Write-Host ""
    supabase projects list
}

exit $(if ($allOk -lt $total) { 1 } else { 0 })
