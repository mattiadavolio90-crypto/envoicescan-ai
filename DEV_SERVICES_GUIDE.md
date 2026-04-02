# 🚀 Dev Services Integration Guide

**Data setup**: 2 aprile 2026  
**Status**: ✅ GitHub CLI, Railway CLI, Supabase CLI - ALL CONNECTED

---

## Quick Status Check

```powershell
# Verifica connessione a tutti e tre i servizi in 5 secondi
.\scripts\bootstrap-cli-status.ps1

# Con dettagli completi
.\scripts\bootstrap-cli-status.ps1 -Verbose
```

---

## GitHub Operations

**Connessione**: mattiadavolio90-crypto

### Repo Management
```powershell
# Lista repo
gh repo list

# Clone repo
gh repo clone <owner/repo>

# Crea nuovo issue
gh issue create --title "My issue" --body "Description"

# Visualizza PR
gh pr list
gh pr view <pr-number>

# Merge PR
gh pr merge <pr-number>
```

### Workflow & Actions
```powershell
# Visualizza workflow runs
gh run list

# Guarda log di un run
gh run view <run-id> --log

# Rilancia un workflow
gh run rerun <run-id>
```

### Tags & Releases
```powershell
# Crea release
gh release create v1.0.0 --generate-notes

# Lista release
gh release list

# Upload artifact
gh release upload v1.0.0 ./file.zip
```

---

## Railway Operations

**Connessione**: mattiadavolio90@gmail.com  
**Progetti**: ingenious-fascination, exemplary-creation

### Project Management
```powershell
# Lista progetti
railway project list

# Seleziona progetto
railway project select

# Visualizza info progetto
railway info
```

### Services & Deployment
```powershell
# Lista servizi
railway service list

# Visualizza log servizio
railway logs <service-name> --tail 100

# Deploy
railway up

# Status servizi
railway status
```

### Environment Variables
```powershell
# Visualizza env vars
railway variables

# Set env var
railway variables set KEY=value

# Gestione secrets
railway variables unset SECRET_NAME
```

---

## Supabase Operations

**Connessione**: ijimhrkdskxafxvejbae (org)  
**Progetto**: SCai Project (vthikmfpywilukizputn) - North EU

### Database Management
```powershell
# Visualizza stato progetto
supabase projects list

# Link progetto locale
supabase link --project-ref vthikmfpywilukizputn

# Pull schema remoto
supabase db pull

# Push migrazioni
supabase db push
```

### Migrations
```powershell
# Crea nuova migrazione
supabase migration new migration_name

# Visualizza migrazioni
supabase migration list

# Rollback (local)
supabase db reset
```

### Functions & Triggers
```powershell
# Crea funzione
supabase functions new my-function

# Deploy funzione
supabase functions deploy

# Visualizza log funzione
supabase functions logs --name my-function
```

### Testing & Local Dev
```powershell
# Avvia Supabase locale
supabase start

# Ferma Supabase locale
supabase stop

# Reset database locale
supabase db reset
```

---

## Common Workflows

### Deploy a Release
```powershell
# 1. Verifica connessioni
.\scripts\bootstrap-cli-status.ps1

# 2. Crea tag e release su GitHub
gh release create v1.0.0 --generate-notes

# 3. Deploy su Railway
railway project select
railway up

# 4. Verifica status
railway status
railway logs <service-name> --tail 50
```

### Database Migration
```powershell
# 1. Crea migrazione
supabase migration new add_new_table

# 2. Edita file /migrations/[timestamp]_add_new_table.sql

# 3. Test locale
supabase db reset

# 4. Push a production
supabase db push --linked

# 5. Verifica
supabase projects list
```

### Emergency Rollback
```powershell
# GitHub: revert commit
gh run list
gh run rerun <run-id>

# Railway: check previous deployment
railway service logs <service>
# Rollback manual da Railway dashboard

# Supabase: database snapshot
# Backup disponibili in dashboard Supabase
```

---

## Troubleshooting

### CLI Not Recognized
```powershell
# GitHub
.\scripts\bootstrap-cli-status.ps1 -FixPath

# Railway / Supabase
# Apri nuovo terminale (PATH refresh)
```

### Authentication Issues
```powershell
# Re-login GitHub
& "C:\Program Files\GitHub CLI\gh.exe" auth logout
& "C:\Program Files\GitHub CLI\gh.exe" auth login --web

# Re-login Railway
railway logout
railway login

# Re-login Supabase
supabase logout
supabase login
```

### Check Active Credentials
```powershell
& "C:\Program Files\GitHub CLI\gh.exe" auth status
railway whoami
supabase projects list
```

---

## Security Notes

✅ **All tokens stored locally**: keyring (GitHub), ~/.railway (Railway), ~/.supabase (Supabase)  
✅ **Scope minimization**: GitHub token limited to repo, workflow, read:org  
✅ **No credentials in code**: All .env and secrets in .gitignore  

⚠️ **Do NOT**:
- Commit .env files
- Expose API keys in logs
- Use personal access tokens in scripts (use GitHub Actions/Railway natives)

---

## Last Update
- GitHub CLI v2.89.0 (2026-03-26)
- Railway CLI v4.36.0
- Supabase CLI v2.78.1 (update available: v2.84.2)

**Next**: `supabase self-update` (recommended for latest features)
