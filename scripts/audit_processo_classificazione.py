"""Statistiche errori categorizzazione - aggregate."""
import os
from pathlib import Path
from collections import Counter, defaultdict

env_path = Path(__file__).resolve().parent.parent / '.env'
for line in env_path.read_text(encoding='utf-8').splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY'])

print("="*90)
print("📊 STATISTICHE GLOBALI prodotti_utente")
print("="*90)

# Tutte le righe paginate
def fetch_all(table, select, **filters):
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select)
        for k, v in filters.items():
            q = q.eq(k, v)
        r = q.range(offset, offset+999).execute().data or []
        rows += r
        if len(r) < 1000:
            break
        offset += 1000
    return rows

pu = fetch_all('prodotti_utente', 'user_id,descrizione,categoria,classificato_da,updated_at,created_at,volte_visto')
print(f"Totale righe prodotti_utente: {len(pu)}")

src_counter = Counter()
for r in pu:
    cd = r.get('classificato_da') or '(null)'
    if cd.startswith('Manuale'):
        src_counter['Manuale (cliente)'] += 1
    elif cd == 'keyword-auto':
        src_counter['keyword-auto'] += 1
    elif cd == 'AI (auto)':
        src_counter['AI (auto)'] += 1
    else:
        src_counter[cd] += 1
print("\nDistribuzione per sorgente:")
for s, n in src_counter.most_common():
    print(f"  {n:>6}  {s}")

# === Manuale per utente ===
manuali = [r for r in pu if (r.get('classificato_da') or '').startswith('Manuale')]
print(f"\nTotale modifiche MANUALI: {len(manuali)}")

per_user = Counter()
for r in manuali:
    per_user[r['user_id'][:8]] += 1
print(f"Utenti distinti che hanno modificato manualmente: {len(per_user)}")
print("Top 10 utenti per # modifiche manuali:")
for u, n in per_user.most_common(10):
    print(f"  {n:>4}  user={u}...")

# Distribuzione categorie manuali
cat_manuali = Counter(r['categoria'] for r in manuali)
print("\nTop categorie scelte manualmente (= categorie 'corrette'):")
for c, n in cat_manuali.most_common():
    print(f"  {n:>5}  {c}")

# === BRAND AMBIGUI ===
print("\n" + "="*90)
print("📊 brand_ambigui (correzioni tracciate)")
print("="*90)
try:
    ba = fetch_all('brand_ambigui', '*')
    print(f"Righe brand_ambigui: {len(ba)}")
    if ba:
        print("\nTop 20 brand con più conflitti:")
        # Ogni riga: brand, vecchia_categoria, nuova_categoria, count?
        from operator import itemgetter
        cnt = Counter()
        cross = defaultdict(Counter)
        for r in ba:
            brand = r.get('brand') or r.get('descrizione') or '(?)'
            cnt[brand] += int(r.get('volte_corretto') or r.get('count') or 1)
            v = r.get('vecchia_categoria') or '?'
            n = r.get('nuova_categoria') or '?'
            cross[(v, n)][brand] += 1
        for b, n in cnt.most_common(20):
            print(f"  {n:>4}  {b}")
        print("\nTop 20 transizioni (vecchia → nuova):")
        trans = Counter()
        for r in ba:
            v = r.get('vecchia_categoria') or '?'
            n = r.get('nuova_categoria') or '?'
            trans[(v, n)] += 1
        for (v, n), c in trans.most_common(20):
            print(f"  {c:>4}  {v} → {n}")
except Exception as e:
    print(f"⚠️ brand_ambigui non leggibile: {e}")

# === Cross check: quante manuali sovrascrivono righe già esistenti? ===
# (sappiamo solo l'ultima cat: ma se updated_at != created_at significa modifica)
modificati = [r for r in pu if r.get('updated_at') and r.get('created_at') and r['updated_at'] != r['created_at']]
print(f"\nRighe prodotti_utente con updated_at != created_at: {len(modificati)} / {len(pu)}")

# === prodotti_master statistiche ===
print("\n" + "="*90)
print("📊 prodotti_master")
print("="*90)
pm = fetch_all('prodotti_master', 'descrizione,categoria,confidence,verified,volte_visto')
print(f"Righe prodotti_master: {len(pm)}")
conf = Counter(r.get('confidence') or '(null)' for r in pm)
ver = Counter(bool(r.get('verified')) for r in pm)
print("Distribuzione confidence:", dict(conf))
print("Distribuzione verified:", dict(ver))

# === fatture: categorie attuali ===
print("\n" + "="*90)
print("📊 fatture (top categorie)")
print("="*90)
# Solo conteggio aggregato per evitare grandi pagine
try:
    # Trick: paginazione manuale  
    cat_fatture = Counter()
    offset = 0
    while True:
        r = sb.table('fatture').select('categoria').is_('deleted_at','null').range(offset, offset+999).execute().data or []
        for row in r:
            cat_fatture[row.get('categoria') or '(null)'] += 1
        if len(r) < 1000:
            break
        offset += 1000
    print(f"Totale righe fatture (live): {sum(cat_fatture.values())}")
    print("\nTop 15 categorie nelle fatture live:")
    for c, n in cat_fatture.most_common(15):
        print(f"  {n:>6}  {c}")
except Exception as e:
    print(f"errore: {e}")
