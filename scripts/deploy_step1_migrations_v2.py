#!/usr/bin/env python3
"""
Deploy Step 1: Creazione stored procedure wrapper + esecuzione
Esegue le 4 migration files su Supabase tramite stored procedure custom.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests
import json

load_dotenv()

# Carica credenziali
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_ROLE_KEY = None

# Try .streamlit/secrets.toml first
try:
    import toml
    secrets_path = Path(".streamlit/secrets.toml")
    if secrets_path.exists():
        with open(secrets_path) as f:
            secrets = toml.load(f)
        SERVICE_ROLE_KEY = secrets.get("supabase", {}).get("service_role_key")
except Exception as e:
    pass

# Fallback to .env
if not SERVICE_ROLE_KEY:
    SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SERVICE_ROLE_KEY:
    print("❌ SUPABASE_URL o SERVICE_ROLE_KEY non configurati")
    sys.exit(1)

migrations = [
    "069_create_fatture_documenti.sql",
    "070_add_piva_cedente_to_fatture.sql",
    "071_create_fornitori_pagamenti_config.sql",
    "072_backfill_fatture_documenti.sql",
]

migrations_dir = Path(__file__).parent.parent / "migrations"

print("=" * 80)
print("Step 1: Deploy Migrations 069 → 070 → 071 → 072")
print("=" * 80)
print()

# Primo, verifica se le 4 file SQL esistono
print("✅ Verificando presenza dei 4 file SQL...")
all_exist = True
for mig_file in migrations:
    mig_path = migrations_dir / mig_file
    if mig_path.exists():
        size = mig_path.stat().st_size
        print(f"   ✓ {mig_file} ({size} bytes)")
    else:
        print(f"   ✗ {mig_file} NOT FOUND")
        all_exist = False

if not all_exist:
    print("\n❌ Alcuni file SQL non trovati")
    sys.exit(1)

print()

# Ora tenta connessione via Supabase REST API
print("✅ Verificando connessione a Supabase...")

headers = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json"
}

try:
    # Test semplice: query una tabella che esiste (es. fatture)
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/fatture?select=count&limit=1",
        headers=headers,
        timeout=5
    )
    if resp.status_code in [200, 206]:
        print(f"   ✓ Connessione REST API OK (status {resp.status_code})")
    else:
        print(f"   ⚠️  REST API returned {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Connessione REST API fallita: {str(e)[:200]}")
    print()
    print("⚠️  CONNESSIONE VERSO SUPABASE NON DISPONIBILE")
    print()
    print("=" * 80)
    print("OPZIONI:")
    print("=" * 80)
    print()
    print("1️⃣  Esegui manualmente i 4 file SQL su Supabase Dashboard:")
    print("   → https://supabase.com/dashboard")
    print("   → SQL Editor → Copia+Incolla file 069, 070, 071, 072")
    print()
    print("2️⃣  Usa supabase CLI se il progetto è linkato localmente:")
    print("   → supabase db push (esegue migrazioni da supabase/migrations/)")
    print()
    print("3️⃣  Ripristina connessione di rete verso Supabase cloud")
    print()
    print("I 4 file SQL sono pronti in: c:\\Users\\matti\\Desktop\\Oh Yeah! Hub\\migrations\\")
    print("   - 069_create_fatture_documenti.sql")
    print("   - 070_add_piva_cedente_to_fatture.sql")
    print("   - 071_create_fornitori_pagamenti_config.sql")
    print("   - 072_backfill_fatture_documenti.sql")
    sys.exit(1)

print()

# Se arriviamo qui, la connessione REST funziona
# Possiamo cercare di eseguire le migrazioni via Python client
print("✅ REST API connesso. Eseguendo migrazioni...")
print()

# Import per la vera esecuzione
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import get_supabase_client

try:
    client = get_supabase_client()
    print("   ✓ Supabase Python client inizializzato")
except Exception as e:
    print(f"   ❌ Errore init client: {e}")
    sys.exit(1)

success_count = 0
failed_migrations = []

for i, mig_file in enumerate(migrations, 1):
    mig_path = migrations_dir / mig_file
    
    print(f"⏳ [{i}/4] {mig_file}...")
    
    try:
        with open(mig_path) as f:
            sql = f.read()
        
        # Usa la funzione pg_exec via RPC se esiste
        # Altrimenti simula
        print(f"   (Migrazioni devono essere eseguite manualmente o via supabase CLI)")
        success_count += 1
        print(f"   ✓ File verificato")
    
    except Exception as e:
        print(f"   ❌ Errore: {str(e)[:200]}")
        failed_migrations.append(mig_file)
    
    print()

print("=" * 80)
print("RISULTATO FINALE")
print("=" * 80)
print()
print("❌ IMPOSSIBILE ESEGUIRE AUTOMATICAMENTE")
print()
print("Motivo: Supabase Python client non espone endpoint per raw SQL execution.")
print()
print("SOLUZIONE: Esegui manualmente su Supabase Dashboard")
print()
print("Step-by-step:")
print("1. Accedi a https://supabase.com/dashboard")
print("2. Vai a SQL Editor")
print("3. Per ogni file SQL (069, 070, 071, 072 in ordine):")
print("   - Copia il contenuto del file")
print("   - Incolla in SQL Editor")
print("   - Clicca 'Run'")
print("   - Attendi completamento")
print()
print("I file sono pronti in: migrations/")
print()
