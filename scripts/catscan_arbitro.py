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
from services.settore_service import settore_utente

div = json.load(open('_divergenze_categorie.json', encoding='utf-8'))
descs = [d['descrizione'] for d in div]
forn = [d.get('fornitore') or '' for d in div]

# Il settore va passato, o un negozio riceve il prompt dei ristoranti e la
# diagnosi a video accusa righe giuste. Il JSON porta lo `user_id` per riga
# (catscan_freddo.py:108), quindi si RAGGRUPPA per settore prima di chiamare:
# un chunk misto avrebbe un solo prompt per clienti di settori diversi.
# Lo script e' di sola lettura — `classifica_con_ai` qui non scrive.
_settori = {}
for d in div:
    uid = d.get('user_id')
    if uid not in _settori:
        _settori[uid] = settore_utente(uid) if uid else None

cats_gpt = [None] * len(div)
CHUNK = 20
_per_settore = {}
for idx, d in enumerate(div):
    _per_settore.setdefault(_settori.get(d.get('user_id')), []).append(idx)

for settore, indici in _per_settore.items():
    for i in range(0, len(indici), CHUNK):
        blocco = indici[i:i+CHUNK]
        try:
            esiti = classifica_con_ai(
                [descs[j] for j in blocco],
                lista_fornitori=[forn[j] for j in blocco],
                settore=settore,
            )
        except Exception as e:
            print(f"  (chunk {i}-{i+CHUNK} settore={settore} fallito: {str(e)[:60]} -> Da Classificare)")
            esiti = ['Da Classificare'] * len(blocco)
        for j, cat in zip(blocco, esiti):
            cats_gpt[j] = cat

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
