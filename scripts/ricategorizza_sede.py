"""Ricategorizza le righe gia' caricate di una sede applicando la pipeline
aggiornata (regole forti + dizionario, e opzionalmente AI sul residuo), SENZA
ri-caricare i file.

Causa radice cert. SUSHILAND 26/06: l'upload via worker non faceva girare l'AI,
e molti prodotti banali restavano Da Classificare o male assegnati perche' le
regole non li coprivano. Dopo aver aggiunto le regole + agganciato l'AI al worker,
questo script porta i dati gia' in DB allo stato corretto.

Passate:
  1) DETERMINISTICA (gratis): applica_correzioni_dizionario + applica_regole_categoria_forti
     su ogni descrizione. Corregge sia i Da Classificare sia gli errori grossolani
     (le regole forti battono anche una categoria sbagliata).
  2) AI (--ai): solo sulle descrizioni ancora Da Classificare dopo la passata 1.

Uso:
  python scripts/ricategorizza_sede.py SAN_GIULIANO            # dry-run passata 1
  python scripts/ricategorizza_sede.py SAN_GIULIANO --commit   # scrive passata 1
  python scripts/ricategorizza_sede.py SAN_GIULIANO --ai --commit  # + AI sul residuo
"""
import sys, tomllib
from pathlib import Path

secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text(encoding="utf-8"))
sup = secrets.get("supabase", {})
import os
# OpenAI dalla sezione secrets per la passata AI in locale
os.environ.setdefault("OPENAI_API_KEY", secrets.get("OPENAI_API_KEY", ""))

from supabase import create_client
from services.ai_service import (
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
    _applica_tutti_guardrail,
    descrizione_e_dubbia,
    set_global_memory_enabled,
)

sb = create_client(sup.get("url", ""), sup.get("service_role_key", ""))

SEDI = {
    "SAN_GIULIANO": "5444e918-8616-464c-a109-5d8aba226805",
    "MARIANO": "0dca4d1f-0caa-419a-b869-25bd98f424e1",
    "VILLA_GUARDIA": "cc016821-e749-4323-9568-3781c69384d3",
}

if len(sys.argv) < 2 or sys.argv[1] not in SEDI:
    print("Uso: python scripts/ricategorizza_sede.py {SAN_GIULIANO|MARIANO|VILLA_GUARDIA} [--commit] [--ai]")
    sys.exit(1)

sede = sys.argv[1]
rid = SEDI[sede]
COMMIT = "--commit" in sys.argv
USE_AI = "--ai" in sys.argv

# La passata deterministica deve riflettere SOLO regole+dizionario, non la cache
# globale (che puo' contenere gli errori vecchi). La passata AI invece usa la memoria.
set_global_memory_enabled(False)


def pipeline_deterministica(desc, cat_attuale):
    """Regole forti + dizionario, con guardrail note. Ritorna categoria nuova."""
    cat = applica_correzioni_dizionario(desc, "Da Classificare")
    cat, _ = applica_regole_categoria_forti(desc, cat)
    return cat


def carica_righe():
    rows, last = [], 0
    while True:
        b = (sb.table("fatture")
             .select("id,descrizione,fornitore,categoria,needs_review,prezzo_unitario,totale_riga,iva_percentuale")
             .eq("ristorante_id", rid).is_("deleted_at", "null")
             .gt("id", last).order("id").limit(1000).execute().data)
        if not b:
            break
        rows += b
        last = b[-1]["id"]
        if len(b) < 1000:
            break
    return rows


rows = carica_righe()
print(f"[{sede}] righe attive: {len(rows)}")

# Passata 1 deterministica: calcola la categoria nuova per ogni riga
updates = {}   # id -> (cat_nuova, needs_review_nuovo)
n_corrette = 0
n_da_class_prima = sum(1 for r in rows if str(r.get("categoria")) == "Da Classificare")
diff_cat = {}

for r in rows:
    desc = str(r.get("descrizione") or "")
    cat_old = str(r.get("categoria") or "")
    if not desc.strip():
        continue
    cat_new = pipeline_deterministica(desc, cat_old)
    # guardrail note con importo
    try:
        iva = float(r.get("iva_percentuale") or 0)
    except (TypeError, ValueError):
        iva = 0.0
    try:
        prezzo = float(r.get("prezzo_unitario") or 0)
    except (TypeError, ValueError):
        prezzo = 0.0
    cat_new = _applica_tutti_guardrail(desc, cat_new, prezzo, iva)

    if cat_new != "Da Classificare" and cat_new != cat_old:
        # needs_review: false se non dubbia
        nr = descrizione_e_dubbia(desc, r.get("fornitore"), cat_new)
        updates[r["id"]] = (cat_new, bool(nr))
        n_corrette += 1
        k = f"{cat_old or 'Da Classificare'} -> {cat_new}"
        diff_cat[k] = diff_cat.get(k, 0) + 1

n_da_class_dopo = n_da_class_prima - sum(
    1 for r in rows if str(r.get("categoria")) == "Da Classificare" and r["id"] in updates
)

print(f"  Da Classificare prima: {n_da_class_prima}")
print(f"  Righe che cambiano categoria (passata deterministica): {n_corrette}")
print(f"  Da Classificare dopo passata 1: {n_da_class_dopo}")
print("  Top cambi:")
for k, v in sorted(diff_cat.items(), key=lambda x: -x[1])[:20]:
    print(f"    {v:4d}  {k}")

if COMMIT and updates:
    # raggruppa per (cat, nr) e fai update batch
    groups = {}
    for rid_, (cat, nr) in updates.items():
        groups.setdefault((cat, nr), []).append(rid_)
    tot = 0
    for (cat, nr), ids in groups.items():
        for i in range(0, len(ids), 500):
            chunk = ids[i:i+500]
            sb.table("fatture").update({"categoria": cat, "needs_review": nr}).in_("id", chunk).execute()
            tot += len(chunk)
    print(f"  COMMIT passata 1: {tot} righe aggiornate")
elif updates:
    print("  (dry-run: nessuna scrittura — aggiungi --commit per applicare)")
