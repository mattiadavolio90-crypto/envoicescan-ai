"""Verifica a freddo di TUTTE le righe categorizzate: confronta categoria attuale
con quella che regole forti + dizionario propongono indipendentemente.
Isola SOLO le divergenze (potenziali errori) per esame manuale/GPT.

Uso: python scripts/verifica_categorie_tutte.py
Output: stampa riepilogo + scrive _divergenze_categorie.json
"""
import os
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

# Permetti import di `services.*` anche se lanciato senza PYTHONPATH=.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding='utf-8')  # evita crash su emoji in console Windows
except Exception:
    pass

# Carica .env
envp = Path(__file__).resolve().parent.parent / '.env'
if envp.exists():
    for ln in envp.read_text(encoding='utf-8').splitlines():
        if '=' in ln and not ln.strip().startswith('#'):
            k, _, v = ln.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client
from services.ai_service import applica_regole_categoria_forti, applica_correzioni_dizionario, _is_fornitore_utenze_sempre

sb = create_client(
    os.environ['SUPABASE_URL'],
    os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY'],
)

# Categorie "spese generali" e neutre: una divergenza food<->food conta più di altre
SPESE = {'SERVIZI E CONSULENZE', 'UTENZE E LOCALI', 'MANUTENZIONE E ATTREZZATURE'}

# Estrai tutte le coppie (user, descrizione, categoria) con conteggio righe
rows = []
offset = 0
while True:
    r = (sb.table('fatture')
         .select('user_id,descrizione,categoria,fornitore')
         .is_('deleted_at', 'null')
         .range(offset, offset + 999)
         .execute().data or [])
    rows += r
    if len(r) < 1000:
        break
    offset += 1000

print(f"Righe attive totali: {len(rows)}")

# Raggruppa per (user, descrizione) -> categoria attuale (la più frequente) + conteggio
agg = defaultdict(lambda: {'cats': Counter(), 'forn': Counter(), 'righe': 0})
for row in rows:
    desc = (row.get('descrizione') or '').strip()
    if not desc:
        continue
    key = (row['user_id'], desc)
    agg[key]['cats'][row.get('categoria') or ''] += 1
    if row.get('fornitore'):
        agg[key]['forn'][row['fornitore']] += 1
    agg[key]['righe'] += 1

print(f"Descrizioni uniche per cliente: {len(agg)}")

divergenze = []
concordi = 0
no_segnale = 0  # regole/dizionario non dicono nulla -> non posso giudicare a freddo

for (user_id, desc), info in agg.items():
    cat_attuale = info['cats'].most_common(1)[0][0]
    # ricalcolo a freddo
    cat_dict = applica_correzioni_dizionario(desc, 'Da Classificare')
    cat_freddo, motivo_freddo = applica_regole_categoria_forti(desc, cat_dict)
    # override: le regole forti vogliono cambiare la categoria attuale?
    cat_override, motivo_override = applica_regole_categoria_forti(desc, cat_attuale)

    proposta = None
    forza = None
    if motivo_override and cat_override != cat_attuale:
        proposta, forza = cat_override, f'regola_forte:{motivo_override}'
    elif cat_freddo != 'Da Classificare' and cat_freddo != cat_attuale:
        proposta, forza = cat_freddo, 'ricalcolo_freddo'

    if proposta is None:
        if cat_freddo == 'Da Classificare':
            no_segnale += 1
        else:
            concordi += 1
        continue

    # FILTRO Segnale 0: se il fornitore e' utility e la riga e' (giustamente) in UTENZE,
    # la divergenza verso SERVIZI e' un falso positivo del dizionario -> ignora.
    forn_top = info['forn'].most_common(1)[0][0] if info['forn'] else ''
    is_util, _ = _is_fornitore_utenze_sempre(forn_top) if forn_top else (False, None)
    if is_util and cat_attuale == 'UTENZE E LOCALI':
        concordi += 1
        continue

    # incoerenza interna?
    incoerente = len([c for c in info['cats'] if c]) > 1

    divergenze.append({
        'user_id': user_id,
        'descrizione': desc,
        'cat_attuale': cat_attuale,
        'proposta': proposta,
        'forza': forza,
        'righe': info['righe'],
        'incoerente_interna': incoerente,
        'fornitore': info['forn'].most_common(1)[0][0] if info['forn'] else '',
        'food_to_food': (cat_attuale not in SPESE and proposta not in SPESE),
    })

# Ordina: regole forti prima, poi per righe impattate
divergenze.sort(key=lambda d: (0 if d['forza'].startswith('regola_forte') else 1, -d['righe']))

print()
print("=" * 70)
print(f"CONCORDI (categoria attuale = ricalcolo):       {concordi}")
print(f"NESSUN SEGNALE a freddo (non giudicabile cosi'): {no_segnale}")
print(f"DIVERGENZE (potenziali errori):                  {len(divergenze)}")
print("=" * 70)

# Riepilogo divergenze per transizione
trans = Counter((d['cat_attuale'], d['proposta']) for d in divergenze)
print("\nTop 25 transizioni divergenti (attuale -> proposta):")
for (a, b), n in trans.most_common(25):
    print(f"  {n:>4}  {a}  ->  {b}")

print(f"\nDivergenze da regola FORTE (alta confidenza): "
      f"{sum(1 for d in divergenze if d['forza'].startswith('regola_forte'))}")
print(f"Divergenze food->food (piu' critiche): "
      f"{sum(1 for d in divergenze if d['food_to_food'])}")

out = Path(__file__).resolve().parent.parent / '_divergenze_categorie.json'
out.write_text(json.dumps(divergenze, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"\nDettaglio scritto in: {out.name}")
