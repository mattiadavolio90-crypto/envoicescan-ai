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

Le righe gia' arbitrate da un umano NON si toccano
==================================================
Precedente del 26/08: questo script avrebbe sovrascritto 19 correzioni manuali,
e fu trovato per caso leggendo il codice. Misurato il 09/09/2026 il caso era
ancora vivo: la riga 128426 di VILLA GUARDIA ("INVOLTINO VIETNAM (POLLO)",
decisa a mano come CARNE il 25/06) passata in `pipeline_deterministica` ne esce
"PASTA E CEREALI" — un involtino di pollo fra la pasta.

La regola: cio' che un cliente decide vale per LUI. Uno script massivo scrive
per conto d'altri, quindi si ferma davanti a `categoria_fonte='correzione_cliente'`
e a `reviewed_at` valorizzato. Le righe saltate si STAMPANO: saltarle in silenzio
sposterebbe solo il problema.

La struttura sta dietro `main()` per una ragione precisa: finche' `create_client`
girava a import time, nessun test poteva importare questo file, e il presidio era
una REPLICA della pipeline che restava verde qualunque cosa cambiasse qui.

Uso:
  python scripts/ricategorizza_sede.py SAN_GIULIANO            # dry-run passata 1
  python scripts/ricategorizza_sede.py SAN_GIULIANO --commit   # scrive passata 1
  python scripts/ricategorizza_sede.py SAN_GIULIANO --ai --commit  # + AI sul residuo
"""
import argparse
import os
import sys
import tomllib
import uuid
from pathlib import Path

# La radice del repo va nel path PRIMA di importare `services`: questo file si
# lancia come `python scripts/ricategorizza_sede.py` (cosi' e' documentato
# sopra), e in quel modo Python mette in sys.path `scripts/`, non la radice.
# Finche' gli import stavano dopo la lettura dei secrets il caso non si vedeva.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ai_service import (
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
    _applica_tutti_guardrail,
    _is_fornitore_utenze_sempre,
    descrizione_e_dubbia,
    set_global_memory_enabled,
)
from services.db_service import aggiorna_categoria_fatture

SEDI = {
    "SAN_GIULIANO": "5444e918-8616-464c-a109-5d8aba226805",
    "MARIANO": "0dca4d1f-0caa-419a-b869-25bd98f424e1",
    "VILLA_GUARDIA": "cc016821-e749-4323-9568-3781c69384d3",
    # Sede tecnica "Costi comuni di gruppo" (catena OFFSIDE/OVERTIME): ci atterrano
    # le fatture di struttura ripartite. E' la sede con l'incidenza piu' alta di
    # righe non classificate (cert. 24/08).
    "COSTI_GRUPPO": "f7bba05f-90a8-4f12-94ed-4d8a08a0bbae",
}

SOURCE = "script_ricategorizza_sede"


def _client():
    """Il client sta dietro una funzione, non a import time: cosi' il file e'
    importabile da un test senza che parta l'I/O sui secrets."""
    from supabase import create_client

    secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text(encoding="utf-8"))
    sup = secrets.get("supabase", {})
    # OpenAI dalla sezione secrets per la passata AI in locale
    os.environ.setdefault("OPENAI_API_KEY", secrets.get("OPENAI_API_KEY", ""))
    return create_client(sup.get("url", ""), sup.get("service_role_key", ""))


def pipeline_deterministica(desc, cat_attuale, fornitore=None):
    """Regole forti + dizionario, con guardrail note. Ritorna categoria nuova.

    Il fornitore NON va concatenato alla descrizione: entrerebbe nel dizionario e
    in TUTTE le regole forti, non solo in quella telecom. Misurato su 3.376 coppie
    reali: 51 divergenze rispetto al percorso di produzione — "LINEA MARE SRL" fa
    scattare _SERVIZI_CANONI_RE su "LINEA" e manda i gamberi in SERVIZI, "COMO
    ACQUA S.R.L" fa scattare _ACQUA_CONFEZIONATA_RE e manda una bolletta idrica
    fra le bevande; all'opposto "RISTORANTE MONOPOLI SRL" davanti a "QUATTRO
    FORMAGGI" rompe il match del dizionario e degrada a Da Classificare.

    Il fornitore si usa come fa la produzione (ai_service.py:4564, LIVELLO 0):
    hard override utility/telecom PRIMA di tutto, descrizione lasciata pulita per
    dizionario e regole. Cosi' lo script riproduce l'ingest automatico invece di
    divergerne.
    """
    if fornitore:
        is_utility, _ = _is_fornitore_utenze_sempre(fornitore)
        if is_utility:
            return "UTENZE E LOCALI"
    cat = applica_correzioni_dizionario(desc, "Da Classificare")
    cat, _ = applica_regole_categoria_forti(desc, cat)
    return cat


def e_arbitrata(riga):
    """La riga porta la decisione di un umano?

    Le due condizioni sono DISGIUNTE sul live (misurato il 09/09: 12 righe per
    `categoria_fonte`, 318 per `reviewed_at`, unione 330): controllarne una sola
    lascerebbe scoperta l'altra meta' del perimetro.
    """
    if str(riga.get("categoria_fonte") or "") == "correzione_cliente":
        return True
    return bool(riga.get("reviewed_at"))


def seleziona_aggiornamenti(rows):
    """Decide cosa riscrivere, e cosa lasciare stare.

    Ritorna `(updates, saltate, diff_cat)`: `updates` e' {id: (categoria, needs_review)},
    `saltate` le righe arbitrate che la pipeline avrebbe cambiato.

    E' separata dall'I/O apposta: e' la funzione che il test esegue davvero, con
    le righe reali di VILLA GUARDIA come fixture.
    """
    updates = {}
    saltate = []
    diff_cat = {}

    for r in rows:
        desc = str(r.get("descrizione") or "")
        cat_old = str(r.get("categoria") or "")
        if not desc.strip():
            continue
        cat_new = pipeline_deterministica(desc, cat_old, r.get("fornitore"))
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
            # La guardia sta QUI, prima di costruire l'update: una riga arbitrata
            # non entra nemmeno nel piano, cosi' il dry-run mostra gia' cosa
            # verrebbe saltato invece di prometterlo e non farlo.
            if e_arbitrata(r):
                saltate.append((r["id"], desc, cat_old, cat_new))
                continue
            # needs_review: false se non dubbia
            nr = descrizione_e_dubbia(desc, r.get("fornitore"), cat_new)
            updates[r["id"]] = (cat_new, bool(nr))
            k = f"{cat_old or 'Da Classificare'} -> {cat_new}"
            diff_cat[k] = diff_cat.get(k, 0) + 1

    return updates, saltate, diff_cat


def carica_righe(sb, rid):
    rows, last = [], 0
    while True:
        b = (sb.table("fatture")
             .select("id,descrizione,fornitore,categoria,needs_review,prezzo_unitario,"
                     "totale_riga,iva_percentuale,categoria_fonte,reviewed_at")
             .eq("ristorante_id", rid).is_("deleted_at", "null")
             .gt("id", last).order("id").limit(1000).execute().data)
        if not b:
            break
        rows += b
        last = b[-1]["id"]
        if len(b) < 1000:
            break
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ricategorizza le righe gia' caricate di una sede."
    )
    parser.add_argument("sede", choices=sorted(SEDI))
    parser.add_argument("--commit", action="store_true",
                        help="scrive davvero (senza, e' un dry-run)")
    parser.add_argument("--ai", action="store_true",
                        help="passata AI sul residuo Da Classificare")
    args = parser.parse_args(argv)

    sede = args.sede
    rid = SEDI[sede]

    # La passata deterministica deve riflettere SOLO regole+dizionario, non la cache
    # globale (che puo' contenere gli errori vecchi). La passata AI invece usa la memoria.
    set_global_memory_enabled(False)

    sb = _client()
    rows = carica_righe(sb, rid)
    print(f"[{sede}] righe attive: {len(rows)}")

    n_da_class_prima = sum(1 for r in rows if str(r.get("categoria")) == "Da Classificare")
    updates, saltate, diff_cat = seleziona_aggiornamenti(rows)
    n_da_class_dopo = n_da_class_prima - sum(
        1 for r in rows
        if str(r.get("categoria")) == "Da Classificare" and r["id"] in updates
    )

    print(f"  Da Classificare prima: {n_da_class_prima}")
    print(f"  Righe che cambiano categoria (passata deterministica): {len(updates)}")
    print(f"  Da Classificare dopo passata 1: {n_da_class_dopo}")
    print("  Top cambi:")
    for k, v in sorted(diff_cat.items(), key=lambda x: -x[1])[:20]:
        print(f"    {v:4d}  {k}")

    if saltate:
        print(f"  SALTATE perche' gia' decise a mano: {len(saltate)}")
        for rid_, desc, cat_old, cat_new in saltate[:20]:
            print(f"    id={rid_} {desc[:45]:<45s} resta {cat_old} (la pipeline diceva {cat_new})")
        if len(saltate) > 20:
            print(f"    ... e altre {len(saltate) - 20}")

    if args.commit and updates:
        # raggruppa per (cat, nr) e fai update batch
        groups = {}
        for rid_, (cat, nr) in updates.items():
            groups.setdefault((cat, nr), []).append(rid_)
        lotto = str(uuid.uuid4())
        tot = 0
        for (cat, nr), ids in groups.items():
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                # `salta_correzioni_manuali` e' la seconda cintura: `seleziona_aggiornamenti`
                # ha gia' escluso le arbitrate, ma se quella selezione sbagliasse
                # la RPC non le scriverebbe comunque.
                tot += aggiorna_categoria_fatture(
                    sb,
                    ids=chunk,
                    categoria=cat,
                    source=SOURCE,
                    extra={"needs_review": nr},
                    batch_id=lotto,
                    ristorante_id=rid,
                    salta_correzioni_manuali=True,
                )
        print(f"  COMMIT passata 1: {tot} righe aggiornate (lotto {lotto})")
    elif updates:
        print("  (dry-run: nessuna scrittura — aggiungi --commit per applicare)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
