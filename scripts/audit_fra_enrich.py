"""Arricchisce audit: trova fornitore, totale e categoria attuale in fatture per ogni descrizione modificata."""
import os, sys, json
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / '.env'
for line in env_path.read_text(encoding='utf-8').splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY'])

USER_ID = '79920814-082f-4d93-bf64-54bafbfbb708'

dump = json.loads((Path(__file__).resolve().parent.parent / 'data' / 'audit_fra_diclemente.json').read_text(encoding='utf-8'))

print(f"{'Descrizione':<45} {'Cat manuale':<28} {'Forn.':<25} {'#righe':>6} {'Tot€':>10}")
print("-" * 120)
report = []
for r in dump:
    desc = r['descrizione']
    cat_manuale = r['categoria']
    # cerca righe fattura
    fatt = sb.table('fatture').select(
        'fornitore, totale_riga, categoria, file_origine, data_documento'
    ).eq('user_id', USER_ID).eq('descrizione', desc).is_('deleted_at', 'null').limit(50).execute().data
    fornitori = sorted({(f.get('fornitore') or '')[:24] for f in fatt})
    tot = sum(float(f.get('totale_riga') or 0) for f in fatt)
    forn_str = ", ".join(fornitori) if fornitori else "(no match)"
    print(f"{desc[:44]:<45} {cat_manuale:<28} {forn_str[:24]:<25} {len(fatt):>6} {tot:>10.2f}")
    report.append({
        'descrizione': desc,
        'categoria_manuale': cat_manuale,
        'updated_at': r.get('updated_at'),
        'fornitori': fornitori,
        'n_righe': len(fatt),
        'totale_euro': round(tot, 2),
        'categoria_attuale_in_fatture': sorted({f.get('categoria') for f in fatt}),
    })

out = Path(__file__).resolve().parent.parent / 'data' / 'audit_fra_arricchito.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(f"\n💾 {out}")
