"""Controlla con GPT le descrizioni 'senza segnale' a freddo (regole/dizionario mute):
sono il punto cieco della scansione. Isola dove GPT diverge dalla categoria attuale.
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
            k,_,v=ln.partition('='); os.environ.setdefault(k.strip(),v.strip())
from supabase import create_client
from collections import Counter, defaultdict
from services.ai_service import applica_regole_categoria_forti, applica_correzioni_dizionario, _is_fornitore_utenze_sempre, classifica_con_ai
sb = create_client(os.environ['SUPABASE_URL'], os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY'])

rows=[]; off=0
while True:
    r=(sb.table('fatture').select('user_id,descrizione,categoria,fornitore').is_('deleted_at','null').range(off,off+999).execute().data or [])
    rows+=r
    if len(r)<1000: break
    off+=1000

agg=defaultdict(lambda:{'cats':Counter(),'forn':Counter(),'righe':0})
for row in rows:
    desc=(row.get('descrizione') or '').strip()
    if not desc: continue
    k=(row['user_id'],desc); agg[k]['cats'][row.get('categoria') or '']+=1
    if row.get('fornitore'): agg[k]['forn'][row['fornitore']]+=1
    agg[k]['righe']+=1

# identifica i 'senza segnale'
senza=[]
for (uid,desc),info in agg.items():
    cat=info['cats'].most_common(1)[0][0]
    cd=applica_correzioni_dizionario(desc,'Da Classificare')
    cf,_=applica_regole_categoria_forti(desc,cd)
    co,mo=applica_regole_categoria_forti(desc,cat)
    if (mo and co!=cat) or (cf!='Da Classificare' and cf!=cat):
        continue  # divergenza (gia' gestita)
    if cf=='Da Classificare':  # senza segnale
        senza.append({'user_id':uid,'descrizione':desc,'cat':cat,'righe':info['righe'],
                      'forn':info['forn'].most_common(1)[0][0] if info['forn'] else ''})

print(f"Senza segnale: {len(senza)}")
descs=[s['descrizione'] for s in senza]; forn=[s['forn'] for s in senza]
# chunk piccoli: isola eventuali errori di parsing GPT su batch lunghi
gpt=[]
for i in range(0,len(descs),20):
    try:
        gpt += classifica_con_ai(descs[i:i+20], lista_fornitori=forn[i:i+20])
    except Exception as e:
        print(f"  (chunk {i} fallito: {str(e)[:50]})")
        gpt += ['Da Classificare']*len(descs[i:i+20])
div=[]
for s,g in zip(senza,gpt):
    if g and g!='Da Classificare' and g!=s['cat']:
        s['gpt']=g; div.append(s)
print(f"GPT diverge dall'attuale su: {len(div)}")
print("\nTop transizioni (attuale -> gpt):")
for (a,b),n in Counter((d['cat'],d['gpt']) for d in div).most_common(20):
    print(f"  {n:>3}  {a} -> {b}")
json.dump(div, open('_senza_segnale_div.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print("\nScritto _senza_segnale_div.json")
