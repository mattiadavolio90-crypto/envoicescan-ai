"""Dry-run / apply: ricalcola needs_review sulle righe gia categorizzate delle sedi
SUSHILAND dopo il fix regola-forte (cert. 26/06). NON tocca le 'Da Classificare'.

Uso:
  python scripts/_recalc_review_sushiland.py            # dry-run (conta, non scrive)
  python scripts/_recalc_review_sushiland.py --apply    # scrive needs_review=false
"""
import sys, tomllib
from pathlib import Path

# Carica credenziali da .streamlit/secrets.toml (sezione [supabase])
secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text(encoding="utf-8"))
sup = secrets.get("supabase", {})
url = sup.get("url", "")
key = sup.get("service_role_key", "")

from supabase import create_client
from services.ai_service import descrizione_e_dubbia

sb = create_client(url, key)

SEDI = {
    "5444e918-8616-464c-a109-5d8aba226805": "SAN GIULIANO",
    "0dca4d1f-0caa-419a-b869-25bd98f424e1": "MARIANO",
}
APPLY = "--apply" in sys.argv

for rid, nome in SEDI.items():
    # pagina su id per evitare il limite 1000
    rows = []
    last = 0
    while True:
        q = (sb.table("fatture")
             .select("id,descrizione,fornitore,categoria")
             .eq("ristorante_id", rid)
             .is_("deleted_at", "null")
             .neq("categoria", "Da Classificare")
             .eq("needs_review", True)
             .gt("id", last).order("id").limit(1000).execute())
        batch = q.data or []
        if not batch: break
        rows.extend(batch); last = batch[-1]["id"]
        if len(batch) < 1000: break

    to_unlock = [r["id"] for r in rows
                 if not descrizione_e_dubbia(r.get("descrizione"), r.get("fornitore"), r.get("categoria"))]

    print(f"[{nome}] needs_review candidate={len(rows)}  -> sbloccabili={len(to_unlock)}  (restano={len(rows)-len(to_unlock)})")

    if APPLY and to_unlock:
        # update a blocchi di 500 id
        n = 0
        for i in range(0, len(to_unlock), 500):
            chunk = to_unlock[i:i+500]
            sb.table("fatture").update({"needs_review": False}).in_("id", chunk).execute()
            n += len(chunk)
        print(f"   APPLICATO: {n} righe needs_review -> false")
