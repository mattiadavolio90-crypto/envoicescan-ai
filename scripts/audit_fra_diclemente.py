"""Audit modifiche manuali categorie - utente fra.diclemente@gmail.com."""
import os, sys, json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Carica .env
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client
url = os.environ['SUPABASE_URL']
key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY']
sb = create_client(url, key)

TARGET_EMAIL = 'fra.diclemente@gmail.com'

# 1. Recupera user_id
users = sb.table('users').select('id, email').ilike('email', TARGET_EMAIL).execute().data
if not users:
    print(f"❌ Utente {TARGET_EMAIL} non trovato")
    sys.exit(1)
user = users[0]
user_id = user['id']
print(f"✅ Utente: {user['email']} (id={user_id})")
print()

# 2. Manual changes in prodotti_utente (classificato_da contains "Manuale")
print("=" * 80)
print("📋 MODIFICHE MANUALI in prodotti_utente (ordine: updated_at DESC)")
print("=" * 80)

rows = sb.table('prodotti_utente').select(
    'descrizione, categoria, classificato_da, volte_visto, updated_at, created_at'
).eq('user_id', user_id).ilike('classificato_da', '%Manuale%').order(
    'updated_at', desc=True
).limit(200).execute().data

print(f"Totale modifiche manuali trovate: {len(rows)}\n")

# Group by categoria
from collections import Counter
cat_counter = Counter(r['categoria'] for r in rows)
print("Distribuzione per categoria scelta manualmente:")
for cat, n in cat_counter.most_common():
    print(f"  {n:>4}  {cat}")
print()

# Mostra ultime 80
print("Ultime 80 (più recenti in cima):")
print(f"{'updated_at':<22} {'categoria':<28} descrizione")
print("-" * 100)
for r in rows[:80]:
    ts = (r.get('updated_at') or '')[:19]
    print(f"{ts:<22} {r['categoria']:<28} {r['descrizione'][:60]}")

# Salva JSON completo
out = Path(__file__).parent.parent / 'data' / 'audit_fra_diclemente.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(f"\n💾 Dump completo: {out}")
