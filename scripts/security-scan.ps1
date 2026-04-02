# Security Scan PowerShell Script
# Esegui: .\scripts\security-scan.ps1
# Uso: verifica il repo per pattern di segreti esposti

param(
    [switch]$Verbose,
    [switch]$QuickScan,  # Solo errori critici
    [string]$LogFile = "$PSScriptRoot\..\SECURITY_SCAN_LOG.txt"
)

Write-Host "Security Scan Tool v1.0" -ForegroundColor Cyan
Write-Host "======================" -Foreground Cyan

$startTime = Get-Date
$issues = @()
$warnings = @()

# Patterns pericolosi da cercare
$dangerPatterns = @(
    "sk-[A-Za-z0-9]{20,}",                    # OpenAI API key
    "xkeysib-[A-Za-z0-9]{20,}",               # Brevo API key
    "Bearer\s+[A-Za-z0-9\-_\.]{20,}",         # JWT/Bearer token
    "['\"]password['\"]?\s*:\s*['\"][^'\"]+" # Password string
    "['\"]token['\"]?\s*:\s*['\"][^'\"]+"    # Token string
    "SUPABASE_KEY.*=[A-Za-z0-9]+"             # Supabase key
)

Write-Host "[1/4] Verifica .gitignore compliance..." -ForegroundColor Yellow

$criticalFiles = @(".env", "secrets.toml", ".env.local")
foreach ($file in $criticalFiles) {
    $ignored = & git check-ignore $file 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $file è ignorato" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] $file NON è ignorato!" -ForegroundColor Red
        $issues += "[CRITICAL] File $file non è in .gitignore"
    }
}

Write-Host "`n[2/4] Verifica pattern segreti..." -ForegroundColor Yellow

if (-not $QuickScan) {
    foreach ($pattern in $dangerPatterns) {
        $matches = @()
        try {
            $matches = git grep -E $pattern 2>&1 | Where-Object { $_ -notlike "*test*" -and $_ -notlike "*example*" }
        } catch {}
        
        if ($matches) {
            foreach ($match in $matches) {
                Write-Host "  [WARN] Pattern detected: $pattern" -ForegroundColor Yellow
                if ($Verbose) {
                    Write-Host "    -> $match"
                }
                $warnings += "Pattern: $pattern"
            }
        }
    }
}

Write-Host "`n[3/4] Verifica credenziali dure in Python..." -ForegroundColor Yellow

$pythonFiles = @(Get-ChildItem -Path . -Filter "*.py" -Recurse)
$unsafePatterns = @(
    "api_key\s*=\s*['\"]sk-",
    "password\s*=\s*['\"][^'\"]+"
)

foreach ($pyFile in $pythonFiles) {
    $content = Get-Content $pyFile.FullName -ErrorAction SilentlyContinue
    foreach ($pattern in $unsafePatterns) {
        if ($content -match $pattern) {
            Write-Host "  [WARN] Unsafe pattern in $($pyFile.Name)" -ForegroundColor Yellow
            $warnings += "File: $($pyFile.Name)"
        }
    }
}

Write-Host "`n[4/4] Verifica autenticazione servizi..." -ForegroundColor Yellow

# Verifiche CLI
$cliChecks = @{
    "GitHub" = { & "C:\Program Files\GitHub CLI\gh.exe" auth status 2>&1 }
    "Railway" = { railway whoami 2>&1 }
    "Supabase" = { supabase projects list 2>&1 }
}

foreach ($service in $cliChecks.Keys) {
    try {
        $result = & $cliChecks[$service]
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] $service autenticato" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] $service: $result" -ForegroundColor Yellow
            $warnings += "$service non autenticato"
        }
    } catch {
        Write-Host "  [ERROR] Errore verificando $service" -ForegroundColor Red
        $issues += "Errore con CLI: $service"
    }
}

# Summary
Write-Host "`n═══════════════════════════════" -ForegroundColor Cyan
Write-Host "RISULTATI:" -ForegroundColor Cyan
Write-Host "  Errori critici: $($issues.Count)" -ForegroundColor $(if ($issues.Count -gt 0) { "Red" } else { "Green" })
Write-Host "  Avvisi: $($warnings.Count)" -ForegroundColor $(if ($warnings.Count -gt 0) { "Yellow" } else { "Green" })
Write-Host "═══════════════════════════════" -ForegroundColor Cyan

if ($issues.Count -gt 0) {
    Write-Host "`n🚨 CRITICAL ISSUES:" -ForegroundColor Red
    $issues | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
} elseif ($warnings.Count -gt 0) {
    Write-Host "`n⚠️  WARNINGS:" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    exit 0
} else {
    Write-Host "`n✅ SECURITY STATUS: PASS" -ForegroundColor Green
    exit 0
}
