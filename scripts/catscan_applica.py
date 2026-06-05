"""Applica le correzioni nette finali: UPDATE fatture + upsert prodotti_utente,
escludendo i falsi positivi residui identificati con giudizio umano.
Usa il client supabase (trigger logga, cache invalidata).
"""
import os, json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
envp = Path(__file__).resolve().parent.parent / '.env'
if envp.exists():
    for ln in envp.read_text(encoding='utf-8').splitlines():
        if '=' in ln and not ln.strip().startswith('#'):
            k,_,v=ln.partition('='); os.environ.setdefault(k.strip(),v.strip())
from supabase import create_client
from datetime import datetime, timezone
sb = create_client(os.environ['SUPABASE_URL'], os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY'])

f = json.load(open('_da_correggere_final.json', encoding='utf-8'))
U = str.upper

def scarta(d):
    a,p,desc=d['cat_attuale'],d['proposta'],U(d['descrizione'])
    if 'XYL' in desc or 'WHITE PEPP' in desc: return True   # gomme -> resta SHOP
    if 'SKIPPER' in desc: return True                        # succhi -> resta BEVANDE
    if 'INSALATA MARE' in desc: return True                  # resta PESCE
    if 'PATATINA' in desc and 'CHIPS' in desc: return True   # resta SHOP
    if 'LINDOR' in desc: return True                         # cioccolatini -> resta SHOP
    if 'AMICA CHIPS' in desc: return True
    return False

final = [d for d in f if not scarta(d)]
now = datetime.now(timezone.utc).isoformat()
applied = 0
for d in final:
    uid, desc, nuova = d['user_id'], d['descrizione'], d['proposta']
    try:
        r = sb.table('fatture').update({'categoria': nuova, 'needs_review': False})\
            .eq('user_id', uid).is_('deleted_at','null').eq('descrizione', desc).neq('categoria', nuova).execute()
        sb.table('prodotti_utente').upsert({
            'user_id': uid, 'descrizione': desc, 'categoria': nuova, 'volte_visto': 1,
            'classificato_da': 'Manuale (reviewer-agent)', 'created_at': now, 'updated_at': now
        }, on_conflict='user_id,descrizione').execute()
        sb.table('review_confirmed').insert({
            'descrizione': desc, 'categoria_finale': nuova, 'is_correct': True,
            'confirmed_by': 'reviewer-agent', 'confirmed_at': now, 'note': 'verifica esaustiva DB'
        }).execute()
        applied += 1
    except Exception as e:
        print(f"ERRORE su '{desc[:40]}': {str(e)[:80]}")

print(f"Applicate {applied}/{len(final)} correzioni (scartati {len(f)-len(final)} falsi positivi)")
