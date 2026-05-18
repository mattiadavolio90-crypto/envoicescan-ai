#!/usr/bin/env python3
"""
Deploy Step 1: Status Report
Mostra lo stato della preparazione delle 4 migrations.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Set encoding to UTF-8 for output
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

migrations_dir = Path(__file__).parent.parent / "migrations"

print("=" * 80)
print("Step 1: Deploy Migrations 069 - 070 - 071 - 072")
print("=" * 80)
print()

print("Status: READY FOR DEPLOYMENT")
print()

migrations = [
    ("069_create_fatture_documenti.sql", "Create fatture_documenti table"),
    ("070_add_piva_cedente_to_fatture.sql", "Add piva_cedente column to fatture"),
    ("071_create_fornitori_pagamenti_config.sql", "Create fornitori_pagamenti_config table"),
    ("072_backfill_fatture_documenti.sql", "Backfill fatture_documenti from fatture"),
]

print("Files ready:")
print()

all_ok = True
for mig_file, desc in migrations:
    mig_path = migrations_dir / mig_file
    if mig_path.exists():
        size = mig_path.stat().st_size
        print("[OK] {}: {} ({} bytes)".format(mig_file, desc, size))
    else:
        print("[FAIL] {}: FILE NOT FOUND".format(mig_file))
        all_ok = False

print()
print("=" * 80)
print()

if not all_ok:
    print("[ERROR] Some migration files not found")
    sys.exit(1)

print("HOW TO EXECUTE:")
print()
print("OPTION 1: Manual execution on Supabase Dashboard")
print("-" * 80)
print("1. Go to: https://supabase.com/dashboard/project/vthikmfpywilukizputn/sql/")
print("2. For each migration file in order (069, 070, 071, 072):")
print("   - Open the SQL file from: migrations/{filename}")
print("   - Copy all content")
print("   - Paste into Supabase SQL Editor")
print("   - Click 'Run' or press Ctrl+Enter")
print("   - Wait for completion (30-60 seconds)")
print("   - Verify: no red errors in Output")
print()
print("3. Verify after all 4 migrations:")
print("   SELECT COUNT(*) FROM fatture_documenti;")
print("   SELECT COUNT(*) FROM fornitori_pagamenti_config;")
print()

print("OPTION 2: Use Supabase CLI (if project is linked locally)")
print("-" * 80)
print("Command: supabase db push")
print("Note: Requires PostgreSQL connection working (DNS resolution needed)")
print()

print("=" * 80)
print("RESULT: READY")
print("4 migrations prepared and ready for deployment")
print("Next: Execute manually on Supabase Dashboard")
print("=" * 80)
print()
