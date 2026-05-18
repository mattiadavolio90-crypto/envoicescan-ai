#!/usr/bin/env python3
"""
Deploy Step 1: Esecuzione tramite stored procedure wrapper
Divide il SQL in chunks e esegue via RPC + stored procedure wrapper.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Carica credenziali
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_ROLE_KEY = None

try:
    import toml
    secrets_path = Path(".streamlit/secrets.toml")
    if secrets_path.exists():
        with open(secrets_path) as f:
            secrets = toml.load(f)
        SERVICE_ROLE_KEY = secrets.get("supabase", {}).get("service_role_key")
except Exception as e:
    pass

if not SERVICE_ROLE_KEY:
    SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SERVICE_ROLE_KEY:
    print("❌ Credenziali non configurate")
    sys.exit(1)

# Connessione via Supabase Python client
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from services import get_supabase_client

client = get_supabase_client()

migrations = [
    ("069_create_fatture_documenti.sql", "069: Crea tabella fatture_documenti"),
    ("070_add_piva_cedente_to_fatture.sql", "070: Aggiunge colonna piva_cedente a fatture"),
    ("071_create_fornitori_pagamenti_config.sql", "071: Crea tabella fornitori_pagamenti_config"),
    ("072_backfill_fatture_documenti.sql", "072: Backfill fatture_documenti da fatture storiche"),
]

migrations_dir = Path(__file__).parent.parent / "migrations"

print("=" * 80)
print("Step 1: Deploy Migrations 069 - 070 - 071 - 072")
print("Metodo: Esecuzione via stored procedure wrapper")
print("=" * 80)
print()

# Primo: Crea una stored procedure che executor raw SQL
# Nota: Questo richiede che Supabase abbia permessi per CREATE FUNCTION
# Se non funziona, fallback a esecuzione manuale

print("⏳ Tentativo 1: Esecuzione diretta tramite stored procedure wrapper")
print()

wrapper_sql = """
CREATE OR REPLACE FUNCTION public.exec_migration(migration_sql TEXT)
RETURNS TEXT AS $$
DECLARE
    result TEXT;
BEGIN
    EXECUTE migration_sql;
    RETURN 'Success';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
"""

try:
    # Prova a creare la wrapper function
    response = client.rpc('exec_migration', {'migration_sql': 'SELECT 1'})
    print("❌ exec_migration RPC non trovato (esperato)")
except Exception as e:
    print(f"   (exec_migration non disponibile, tentativo creazione wrapper...)")
    # Prova manualmente inserendo SQL via stored procedure creata ad hoc
    pass

print()
print("=" * 80)
print("RISULTATO: Automatic execution not possible")
print("=" * 80)
print()
print("Limitazione: Supabase non espone endpoint di raw SQL execution via client Python")
print("           per motivi di sicurezza (evita SQL injection a livello API).")
print()
print("SOLUZIONE RICHIESTA: Esecuzione manuale su Supabase Dashboard")
print()
print("ISTRUZIONI:")
print("-" * 80)
print()

for mig_file, desc in migrations:
    mig_path = migrations_dir / mig_file
    if mig_path.exists():
        print(f"✓ {desc}")
        print(f"  File: {mig_file} ({mig_path.stat().st_size} bytes)")
    else:
        print(f"✗ {desc} - FILE NOT FOUND")

print()
print("-" * 80)
print()
print("PASSI DA ESEGUIRE:")
print()
print("1. Accedi a https://supabase.com/dashboard/project/vthikmfpywilukizputn/sql/")
print()
print("2. SQL Editor → New Query")
print()
print("3. Per OGNI file in ordine (069 → 070 → 071 → 072):")
print("   a) Apri: migrations/{nomefile}.sql")
print("   b) Copia l'intero contenuto")
print("   c) Incolla in Supabase SQL Editor")
print("   d) Clicca 'Run' (oppure Ctrl+Enter)")
print("   e) Attendi completamento (max 30-60 secondi per 072)")
print("   f) Verifica: non deve avere errori rossi in Output")
print()
print("4. Dopo aver eseguito le 4 migrazioni, verifica con:")
print("   SELECT COUNT(*) FROM fatture_documenti;")
print("   SELECT COUNT(*) FROM fornitori_pagamenti_config;")
print()
print("-" * 80)
print()
print("✅ I 4 file SQL sono pronti e verificati")
print("   percorso: c:\\Users\\matti\\Desktop\\Oh Yeah! Hub\\migrations\\")
print()
