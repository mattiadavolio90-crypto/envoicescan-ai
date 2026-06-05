"""Arbitro GPT sulle divergenze: per ogni divergenza, chiede a GPT la categoria
indipendente e la confronta con attuale + proposta-regola. Classifica l'esito.

Uso: PYTHONPATH=. python scripts/arbitro_divergenze.py
"""
import os, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

envp = Path(__file__).resolve().parent.parent / '.env'
if envp.exists():
    for ln in envp.read_text(encoding='utf-8').splitlines():
        if '=' in ln and not ln.strip().startswith('#'):
            k, _, v = ln.partition('='); os.environ.setdefault(k.strip(), v.strip())

from services.ai_service import classifica_con_ai

div = json.load(open('_divergenze_categorie.json', encoding='utf-8'))
descs = [d['descrizione'] for d in div]
forn = [d.get('fornitore') or '' for d in div]

# GPT in chunk piccoli: un eventuale errore di parsing JSON isola pochi casi
# invece di compromettere l'intero set (problema visto su batch lunghi).
cats_gpt = []
CHUNK = 20
for i in range(0, len(descs), CHUNK):
    try:
        cats_gpt += classifica_con_ai(descs[i:i+CHUNK], lista_fornitori=forn[i:i+CHUNK])
    except Exception as e:
        print(f"  (chunk {i}-{i+CHUNK} fallito: {str(e)[:60]} -> Da Classificare)")
        cats_gpt += ['Da Classificare'] * len(descs[i:i+CHUNK])

esiti = {'gpt=proposta (ERRORE probabile)': [], 'gpt=attuale (falso positivo regola)': [],
         'gpt=terza via (incerto)': []}
for d, g in zip(div, cats_gpt):
    if g == d['proposta']:
        cat = 'gpt=proposta (ERRORE probabile)'
    elif g == d['cat_attuale']:
        cat = 'gpt=attuale (falso positivo regola)'
    else:
        cat = 'gpt=terza via (incerto)'
    d['gpt'] = g
    esiti[cat].append(d)

print("=" * 70)
for k, v in esiti.items():
    print(f"{k}: {len(v)}")
print("=" * 70)

print("\n### ERRORI PROBABILI (GPT conferma la proposta-regola) ###")
for d in sorted(esiti['gpt=proposta (ERRORE probabile)'], key=lambda x: -x['righe']):
    print(f"  [{d['righe']:>2}r] {d['cat_attuale'][:20]:20} -> {d['proposta'][:20]:20} | {d['descrizione'][:48]}")

print("\n### INCERTI (3 categorie diverse: attuale/regola/gpt) ###")
for d in sorted(esiti['gpt=terza via (incerto)'], key=lambda x: -x['righe']):
    print(f"  [{d['righe']:>2}r] att={d['cat_attuale'][:16]:16} reg={d['proposta'][:16]:16} gpt={d['gpt'][:16]:16} | {d['descrizione'][:42]}")

json.dump(esiti, open('_arbitro_esiti.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print("\nScritto _arbitro_esiti.json")
