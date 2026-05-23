#!/usr/bin/env python3
"""
run_migration_079.py
Esegue la migration 079 (privacy_accepted_at) su Supabase.
Usa l'API Management di Supabase con il service_role_key.
"""
import sys
import os
import requests
import toml
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Leggi credenziali da secrets.toml ──────────────────────────────────────
secrets_path = ROOT / ".streamlit" / "secrets.toml"
if not secrets_path.exists():
    print("❌ .streamlit/secrets.toml non trovato")
    sys.exit(1)

with open(secrets_path) as f:
    secrets = toml.load(f)

SUPABASE_URL = secrets["supabase"]["url"]
SERVICE_ROLE_KEY = secrets["supabase"]["service_role_key"]
PROJECT_REF = SUPABASE_URL.split("//")[1].split(".")[0]

SQL = """
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS privacy_accepted_at TIMESTAMPTZ;

COMMENT ON COLUMN users.privacy_accepted_at IS
  'Timestamp UTC accettazione Privacy Policy (GDPR Art. 7.1). '
  'Valorizzato al primo accesso tramite checkbox nel form di attivazione.';
"""

print(f"🔑 Project ref: {PROJECT_REF}")
print(f"📋 SQL: {SQL.strip()}")
print()

# ── Tentativo 1: Management API  ──────────────────────────────────────────
print("⏳ Tentativo via Management API...")
mgmt_url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
headers_mgmt = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}
try:
    resp = requests.post(mgmt_url, json={"query": SQL}, headers=headers_mgmt, timeout=15)
    if resp.status_code in (200, 201):
        print(f"✅ Migration 079 eseguita via Management API (status {resp.status_code})")
        print(resp.json())
        sys.exit(0)
    else:
        print(f"   ⚠️  Management API status {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"   ⚠️  Management API non raggiungibile: {e}")

# ── Tentativo 2: RPC exec_migration (se esiste) ───────────────────────────
print()
print("⏳ Tentativo via RPC exec_migration...")
rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/exec_migration"
headers_rpc = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "apikey": SERVICE_ROLE_KEY,
    "Content-Type": "application/json",
}
try:
    resp = requests.post(rpc_url, json={"migration_sql": SQL}, headers=headers_rpc, timeout=15)
    if resp.status_code in (200, 201):
        print(f"✅ Migration 079 eseguita via RPC (status {resp.status_code})")
        sys.exit(0)
    elif resp.status_code == 404:
        print("   ⚠️  RPC exec_migration non esiste")
    else:
        print(f"   ⚠️  RPC status {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"   ⚠️  RPC non raggiungibile: {e}")

# ── Tentativo 3: verifica se la colonna esiste già ────────────────────────
print()
print("⏳ Verifico se la colonna esiste già...")
sys.path.insert(0, str(ROOT))
try:
    from services import get_supabase_client
    sb = get_supabase_client()
    sb.table("users").select("privacy_accepted_at").limit(0).execute()
    print("✅ Colonna privacy_accepted_at esiste già — migration non necessaria!")
    sys.exit(0)
except Exception as e:
    err = str(e)
    if "privacy_accepted_at" in err or "column" in err.lower():
        print("   ℹ️  Colonna non presente — migration necessaria")
    else:
        print(f"   ⚠️  Errore verifica colonna: {err[:200]}")

# ── Fallback: istruzioni manuali ─────────────────────────────────────────
print()
print("=" * 60)
print("❌ IMPOSSIBILE ESEGUIRE AUTOMATICAMENTE")
print("=" * 60)
print()
print("Esegui manualmente su Supabase SQL Editor:")
print("  https://supabase.com/dashboard/project/vthikmfpywilukizputn/sql/new")
print()
print("SQL da eseguire:")
print("-" * 60)
print(SQL.strip())
print("-" * 60)
sys.exit(1)
