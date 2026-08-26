"""Passata AI reale sulle righe ancora 'Da Classificare' di una sede, DOPO che
scripts/ricategorizza_sede.py ha gia' esaurito la passata 1 (deterministica).

Causa: scripts/ricategorizza_sede.py dichiara nel docstring una "passata 2 (AI)"
dietro il flag --ai, ma quel flag e' dead code — letto e mai piu' usato. Le righe
che il dizionario/regole forti non coprono (es. "PIZZA MARGHERITA RISTORANTE
MONOPOLI SRL", "POPCORN METRO") restano quindi Da Classificare anche se l'AI,
ora attiva nel queue-worker (cert. 25/08 — force_local_worker_path/set_ai_context),
le classificherebbe senza difficolta'.

Questo script replica ESATTAMENTE il blocco di classificazione di produzione
(worker/queue_processor.py::_auto_classify_saved_rows) — stessa funzione AI,
stesso gate di affidabilita' (conferma runtime o GPT 'alta' + non dubbia),
stesso guardrail NOTE E DICITURE — ma filtra per ristorante_id invece che per
singolo file_origine, perche' qui le righe residue appartengono a file diversi.

Uso:
  python -m scripts.ricategorizza_sede_ai COSTI_GRUPPO            # dry-run
  python -m scripts.ricategorizza_sede_ai COSTI_GRUPPO --commit   # scrive
"""
import sys, time, tomllib
from pathlib import Path

secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text(encoding="utf-8"))
sup = secrets.get("supabase", {})
import os
os.environ.setdefault("OPENAI_API_KEY", secrets.get("OPENAI_API_KEY", ""))
# Il tracking costi/quota AI (services/ai_service.py) usa un client Supabase
# globale separato da quello di questo script: senza queste env var il ledger
# fallisce silenziosamente ("Credenziali Supabase non trovate") e il costo
# della passata non viene registrato in ai_usage_events.
os.environ.setdefault("SUPABASE_URL", sup.get("url", ""))
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", sup.get("service_role_key", ""))

from supabase import create_client
from services.db_service import filter_active
from services.invoice_service import _to_int_safe
from services.worker_client import classifica_via_worker_con_confidenza, force_local_worker_path
from services.ai_service import (
    set_ai_context,
    ai_degradata,
    reset_ai_degradata,
    aggiorna_streak_classificazione,
    _STREAK_NON_PRECARICATO,
    enforce_no_unclassified_category,
    descrizione_e_dubbia,
    _applica_guardrail_note_con_importo,
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
    set_global_memory_enabled,
)

sb = create_client(sup.get("url", ""), sup.get("service_role_key", ""))

SEDI = {
    "SAN_GIULIANO": "5444e918-8616-464c-a109-5d8aba226805",
    "MARIANO": "0dca4d1f-0caa-419a-b869-25bd98f424e1",
    "VILLA_GUARDIA": "cc016821-e749-4323-9568-3781c69384d3",
    "COSTI_GRUPPO": "f7bba05f-90a8-4f12-94ed-4d8a08a0bbae",
}

if len(sys.argv) < 2 or sys.argv[1] not in SEDI:
    print("Uso: python -m scripts.ricategorizza_sede_ai {SAN_GIULIANO|MARIANO|VILLA_GUARDIA|COSTI_GRUPPO} [--commit]")
    sys.exit(1)

sede = sys.argv[1]
rid = SEDI[sede]
COMMIT = "--commit" in sys.argv

# Memoria globale ATTIVA (a differenza della passata 1): e' cosi' che si comporta
# la produzione — classifica_via_worker_con_confidenza consulta prodotti_utente.
set_global_memory_enabled(True)
force_local_worker_path(True)
set_ai_context(ristorante_id=rid, user_id=None)

_MAX_CLASSIFY_RETRY = 3
_CLASSIFY_RETRY_BACKOFF = 2.0


def _categoria_deterministica_runtime(descrizione):
    try:
        cat_dz = applica_correzioni_dizionario(descrizione, "Da Classificare")
        cat_rf, _motivo = applica_regole_categoria_forti(descrizione, cat_dz)
        finale = (cat_rf or cat_dz or "").strip()
    except Exception:
        return None
    if not finale or finale.upper() == "DA CLASSIFICARE":
        return None
    return finale


def _runtime_conferma_categoria(descrizione, categoria) -> bool:
    cat = str(categoria or "").strip()
    if not cat or cat.upper() == "DA CLASSIFICARE":
        return False
    finale = _categoria_deterministica_runtime(descrizione)
    if not finale:
        return False
    return finale.upper() == cat.upper()


unresolved = (
    filter_active(
        sb.table("fatture")
        .select("id, descrizione, fornitore, iva_percentuale, totale_riga")
        .eq("ristorante_id", rid)
    )
    .or_("categoria.is.null,categoria.eq.Da Classificare,categoria.eq.")
    .limit(10000)
    .execute()
)
rows = unresolved.data or []
print(f"[{sede}] righe Da Classificare: {len(rows)}")
if not rows:
    sys.exit(0)

desc_map = {}
desc_to_ids = {}
desc_importo = {}
for row in rows:
    desc = str(row.get("descrizione") or "").strip()
    if not desc:
        continue
    row_id = row.get("id")
    if row_id is not None:
        desc_to_ids.setdefault(desc, []).append(row_id)
    try:
        importo = abs(float(row.get("totale_riga") or 0))
    except (TypeError, ValueError):
        importo = 0.0
    if importo > desc_importo.get(desc, 0.0):
        desc_importo[desc] = importo
    if desc in desc_map:
        continue
    fornitore = str(row.get("fornitore") or "")
    iva = _to_int_safe(row.get("iva_percentuale"), 0)
    desc_map[desc] = (fornitore, iva)

descrizioni = list(desc_map.keys())
print(f"  descrizioni distinte: {len(descrizioni)}")

updates = {}   # id -> (categoria, needs_review)
diff_cat = {}
n_ai_muta_tot = 0
chunk_size = 50

for i in range(0, len(descrizioni), chunk_size):
    chunk = descrizioni[i:i + chunk_size]
    fornitori = [desc_map[d][0] for d in chunk]
    iva_list = [desc_map[d][1] for d in chunk]
    categorie = None
    confidenze = None
    _ai_muta = False
    for _tentativo in range(_MAX_CLASSIFY_RETRY):
        try:
            reset_ai_degradata()
            categorie, confidenze = classifica_via_worker_con_confidenza(
                chunk, fornitori=fornitori, iva=iva_list, hint=None,
                user_id=None, ristorante_id=rid,
            )
            _ai_muta = ai_degradata()
            if isinstance(categorie, list) and len(categorie) == len(chunk) and not _ai_muta:
                break
            if _ai_muta:
                print(f"  [chunk {i}-{i+len(chunk)}] AI muta, tentativo {_tentativo+1}/{_MAX_CLASSIFY_RETRY}")
                if _tentativo < _MAX_CLASSIFY_RETRY - 1:
                    time.sleep(_CLASSIFY_RETRY_BACKOFF * (2 ** _tentativo))
                continue
            categorie = None
        except Exception as ai_exc:
            print(f"  [chunk {i}-{i+len(chunk)}] errore: {ai_exc}, tentativo {_tentativo+1}/{_MAX_CLASSIFY_RETRY}")
            categorie = None
            confidenze = None
        if _tentativo < _MAX_CLASSIFY_RETRY - 1:
            time.sleep(_CLASSIFY_RETRY_BACKOFF * (2 ** _tentativo))

    if not isinstance(categorie, list) or len(categorie) != len(chunk):
        print(f"  [chunk {i}-{i+len(chunk)}] AI non disponibile dopo {_MAX_CLASSIFY_RETRY} tentativi: {len(chunk)} righe restano Da Classificare")
        n_ai_muta_tot += len(chunk)
        continue
    if _ai_muta:
        print(f"  [chunk {i}-{i+len(chunk)}] AI muta dopo {_MAX_CLASSIFY_RETRY} tentativi: fallback deterministico")
        n_ai_muta_tot += len(chunk)

    if not isinstance(confidenze, list) or len(confidenze) != len(chunk):
        confidenze = ['media'] * len(chunk)

    for desc, cat, conf in zip(chunk, categorie, confidenze):
        categoria, fallback_forzato = enforce_no_unclassified_category(
            cat, desc, source="script_ricategorizza_sede_ai",
        )
        _forn = desc_map.get(desc, ("", 0))[0]
        _cat_runtime = _categoria_deterministica_runtime(desc)
        if _cat_runtime and _cat_runtime.upper() != str(categoria).strip().upper():
            categoria = _cat_runtime
        categoria = _applica_guardrail_note_con_importo(
            desc, categoria, desc_importo.get(desc, 0.0)
        )
        _confermata_runtime = _runtime_conferma_categoria(desc, categoria)
        _alta_affidabile = (
            conf == 'alta'
            and not fallback_forzato
            and not descrizione_e_dubbia(desc, _forn, categoria)
        )
        affidabile = _confermata_runtime or _alta_affidabile

        if affidabile:
            needs_review = False
        else:
            categoria = "Da Classificare"
            needs_review = True
        if str(categoria).strip() == "Da Classificare":
            needs_review = True

        # Esclusione manuale (cert. 26/08): uno storno/sconto e' una rettifica, non
        # un servizio/costo. GPT lo classifica 'alta' ma indovina il "di cosa" —
        # esattamente il caso che la regola di dominio #1 vieta. Resta in coda.
        if "STORNO FATTURA" in desc.upper() or desc.upper() == "SCONTO HOMY":
            continue
        if categoria != "Da Classificare":
            for row_id in desc_to_ids.get(desc, []):
                updates[row_id] = (categoria, needs_review, desc)
            diff_cat[categoria] = diff_cat.get(categoria, 0) + len(desc_to_ids.get(desc, []))

print(f"\n  Righe classificate dalla passata AI: {len(updates)}")
print(f"  Righe con AI muta/non disponibile: {n_ai_muta_tot}")
print("  Per categoria:")
for k, v in sorted(diff_cat.items(), key=lambda x: -x[1]):
    print(f"    {v:4d}  {k}")

if COMMIT and updates:
    groups = {}
    for row_id, (cat, nr, _desc) in updates.items():
        groups.setdefault((cat, nr), []).append(row_id)
    tot = 0
    for (cat, nr), ids in groups.items():
        for i in range(0, len(ids), 500):
            chunk_ids = ids[i:i+500]
            sb.table("fatture").update({"categoria": cat, "needs_review": nr}).in_("id", chunk_ids).execute()
            tot += len(chunk_ids)
    # Streak: solo dopo il commit, come in produzione
    for desc in {d for _c, _n, d in updates.values()}:
        cat_scritta = next(c for c, _n, d in updates.values() if d == desc)
        try:
            aggiorna_streak_classificazione(desc, cat_scritta, sb, record_precaricato=_STREAK_NON_PRECARICATO)
        except Exception as _e:
            print(f"  streak fallito per '{desc[:50]}': {_e}")
    print(f"  COMMIT: {tot} righe aggiornate")
elif updates:
    print("  (dry-run: nessuna scrittura — aggiungi --commit per applicare)")
