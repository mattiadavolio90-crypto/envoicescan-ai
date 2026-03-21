$ErrorActionPreference = 'Stop'

# Carica WEBHOOK_SECRET dal .env
$lines = Get-Content "supabase\functions\.env"
foreach ($l in $lines) {
    if ($l -match "^INVOICETRONIC_WEBHOOK_SECRET=(.+)$") {
        $env:WEBHOOK_SECRET = $Matches[1]
        break
    }
}

if (-not $env:WEBHOOK_SECRET) {
    Write-Error "WEBHOOK_SECRET non trovato nel .env"
    exit 1
}

Write-Host "Secret caricato (len=$($env:WEBHOOK_SECRET.Length))" -ForegroundColor Green

# Esegui i test con Deno
$denoExe = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe\deno.exe"
& $denoExe run --allow-net --allow-env "supabase\functions\invoicetronic-webhook\test.ts"
exit $LASTEXITCODE
