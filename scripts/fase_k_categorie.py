"""Fase K (10/10/2026): porta i dati GIA' caricati nel nuovo elenco delle categorie.

Decisioni di Mattia: SUSHI VARIE non esiste piu' (ogni prodotto nella sua
famiglia), tutto il sake e' VINI, il mirin e l'olio di sesamo sono condimenti, la
salsa unagi e' una salsa, e un pasto consumato in un altro locale e' RAPPRESENTANZA
(la fattura col coperto, tutta). La rinomina SHOP -> RIVENDITA la fa la migration
`supabase/migrations/20261010223829_categorie_fase_k_dati.sql`; qui resta come rete
per le righe che il worker VECCHIO scrive ancora fra la migration e il deploy
(passo `residui`).

Passi:
  giappone  righe SUSHI VARIE e delle famiglie toccate (sake, mirin, olio di
            sesamo, unagi) -> la categoria che oggi da' il nucleo deterministico;
            e la memoria (cliente, globale, admin, conferme) delle stesse voci.
            Scrive solo categorie che esistevano gia': si puo' lanciare col codice
            vecchio ancora in produzione.
  pasti     la fattura col coperto, tutta, e le righe "4 PASTI COMPLETI", "MENU
            FISSO"... -> RAPPRESENTANZA. Solo DOPO il deploy: col codice vecchio
            RAPPRESENTANZA non e' una spesa generale e finirebbe nel food cost.
  residui   SHOP rimaste (rinomina) e SUSHI VARIE rimaste (come `giappone`).
  tutto     i tre insieme.

Le righe gia' decise a mano NON si toccano (stessa regola di
`scripts/ricategorizza_sede.py`): si STAMPANO, perche' saltarle in silenzio
sposterebbe solo il problema. Fa eccezione la rinomina di SHOP: e' la stessa
scelta con un altro nome. Una riga che il nucleo deterministico non sa dire resta
com'e' e si elenca: mai "Da Classificare" forzato su un dato che oggi ha un valore.

Uso:
  python scripts/fase_k_categorie.py giappone            # dry-run
  python scripts/fase_k_categorie.py giappone --commit   # scrive
"""
import argparse
import re
import sys
import tomllib
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.constants import CATEGORIE_ABOLITE  # noqa: E402
from services.ai_service import decisione_deterministica, e_riga_coperto  # noqa: E402
from services.db_service import aggiorna_categoria_fatture  # noqa: E402

SOURCE = "script_fase_k"
NON_DECISA = "Da Classificare"

# Le famiglie che la Fase K ha spostato oltre a SUSHI VARIE. Il passo `giappone`
# guarda SOLO queste: altrove il nucleo deterministico puo' dissentire dalla riga
# per ragioni che non c'entrano (una memoria del cliente, l'AI), e riscriverle
# sarebbe uno script che decide per conto d'altri su categorie che nessuno ha
# cambiato. Misurato sulle 7.173 descrizioni reali: sono le sole che cambiano.
_FAMIGLIE_K = re.compile(r"\b(SAKE|MIRIN|UNAGI)\b|\bOLIO\b.*\bSESAM|\bSESAM\w*\b.*\bOLIO\b")


def _client():
    from supabase import create_client

    secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text(encoding="utf-8"))
    sup = secrets.get("supabase", {})
    return create_client(sup.get("url", ""), sup.get("service_role_key", ""))


def e_arbitrata(riga):
    """La riga porta la decisione di un umano (come in ricategorizza_sede)."""
    if str(riga.get("categoria_fonte") or "") == "correzione_cliente":
        return True
    return bool(riga.get("reviewed_at"))


def _importo(riga):
    try:
        return float(riga.get("totale_riga") or 0)
    except (TypeError, ValueError):
        return 0.0


def piano_giappone(righe):
    """Ritorna (aggiorna {id: categoria}, saltate, non_decise)."""
    aggiorna, saltate, non_decise = {}, [], []
    for r in righe:
        vecchia = str(r.get("categoria") or "")
        desc = str(r.get("descrizione") or "")
        if vecchia not in CATEGORIE_ABOLITE and not _FAMIGLIE_K.search(desc.upper()):
            continue
        nuova = decisione_deterministica(desc)[0]
        if nuova == vecchia:
            continue
        if nuova == NON_DECISA or nuova in CATEGORIE_ABOLITE:
            if vecchia in CATEGORIE_ABOLITE:
                non_decise.append(r)
            continue
        if e_arbitrata(r):
            saltate.append((r, nuova))
            continue
        aggiorna[r["id"]] = nuova
    return aggiorna, saltate, non_decise


def piano_pasti(righe):
    """Ritorna (aggiorna {id: (categoria, fonte)}, saltate).

    Un documento e' la coppia (utente, file): la fattura col coperto va tutta in
    RAPPRESENTANZA, tranne le righe a importo zero. Fuori da quei documenti, le
    righe che la regola di riga riconosce come pasto ("4 PASTI COMPLETI").
    """
    con_coperto = {
        (r.get("user_id"), r.get("file_origine"))
        for r in righe if e_riga_coperto(r.get("descrizione"))
    }
    aggiorna, saltate = {}, []
    for r in righe:
        if str(r.get("categoria") or "") == "RAPPRESENTANZA" or _importo(r) == 0:
            continue
        if (r.get("user_id"), r.get("file_origine")) in con_coperto:
            fonte = "L0_documento_pasto"
        elif decisione_deterministica(str(r.get("descrizione") or ""))[0] == "RAPPRESENTANZA":
            fonte = "L7_regola_forte"
        else:
            continue
        if e_arbitrata(r):
            saltate.append((r, "RAPPRESENTANZA"))
            continue
        aggiorna[r["id"]] = ("RAPPRESENTANZA", fonte)
    return aggiorna, saltate


# Una voce di memoria scritta da un CLIENTE porta la sua email ("Manuale (x@y)");
# "Manuale (reviewer-agent)" e' l'agente di categorizzazione, che lavora per Mattia.
_MANUALE_CLIENTE = re.compile(r"^\s*Manuale\s*\(.*@.*\)", re.I)


def piano_memoria(voci, campo="categoria", rinomina_shop=False):
    """Voci di memoria (cliente, globale, admin, conferme) delle famiglie toccate.

    Ritorna (aggiorna {id: categoria}, cancella [id], saltate [voce]). Una voce
    SUSHI VARIE che il nucleo deterministico non sa dire si cancella: la categoria
    non esiste piu', e senza la voce la prossima riga passa da dizionario e AI come
    una mai vista.

    Una voce scelta a mano da un cliente si SALTA (e si stampa) quando la sua
    categoria esiste ancora: e' la sua decisione. Su una categoria abolita o
    rinominata invece la scelta non puo' restare com'e', e la si traduce.

    `rinomina_shop` solo nel passo `residui`, DOPO migration e deploy: prima, il
    codice vecchio leggerebbe dalla memoria un RIVENDITA che non conosce.
    """
    aggiorna, cancella, saltate = {}, [], []
    for v in voci:
        vecchia = str(v.get(campo) or "")
        desc = str(v.get("descrizione") or "")
        if vecchia == "SHOP":
            if rinomina_shop:
                aggiorna[v["id"]] = "RIVENDITA"
            continue
        if vecchia not in CATEGORIE_ABOLITE and not _FAMIGLIE_K.search(desc.upper()):
            continue
        nuova = decisione_deterministica(desc)[0]
        if nuova == vecchia:
            continue
        if nuova == NON_DECISA or nuova in CATEGORIE_ABOLITE:
            if vecchia in CATEGORIE_ABOLITE:
                cancella.append(v["id"])
            continue
        if vecchia not in CATEGORIE_ABOLITE and _MANUALE_CLIENTE.search(str(v.get("classificato_da") or "")):
            saltate.append((v, nuova))
            continue
        aggiorna[v["id"]] = nuova
    return aggiorna, cancella, saltate


# ── I/O ──────────────────────────────────────────────────────────────────────

_COLONNE_FATTURE = ("id,user_id,ristorante_id,file_origine,fornitore,descrizione,categoria,"
                    "totale_riga,categoria_fonte,reviewed_at")

_MEMORIE = (
    ("prodotti_utente", "categoria", "id,user_id,descrizione,categoria,classificato_da"),
    ("prodotti_master", "categoria", "id,descrizione,categoria,classificato_da"),
    ("classificazioni_manuali", "categoria_corretta", "id,descrizione,categoria_corretta"),
    ("review_confirmed", "categoria_finale", "id,descrizione,categoria_finale"),
)


def _tutte(query_per_pagina):
    righe, ultimo = [], None
    while True:
        q = query_per_pagina()
        if ultimo is not None:
            q = q.gt("id", ultimo)
        blocco = q.order("id").limit(1000).execute().data or []
        righe += blocco
        if len(blocco) < 1000:
            return righe
        ultimo = blocco[-1]["id"]


def carica_fatture(sb):
    return _tutte(lambda: sb.table("fatture").select(_COLONNE_FATTURE).is_("deleted_at", "null"))


def _stampa_righe(titolo, coppie, limite=40):
    if not coppie:
        return
    print(f"  {titolo}: {len(coppie)}")
    for r, nuova in coppie[:limite]:
        print(f"    id={r['id']} {str(r.get('descrizione'))[:50]:<50} {r.get('categoria')} -> {nuova}"
              f"  {_importo(r):>9.2f} EUR  [{str(r.get('fornitore') or '')[:25]}]")
    if len(coppie) > limite:
        print(f"    ... e altre {len(coppie) - limite}")


def _riepilogo(righe_per_id, aggiorna):
    trans = Counter()
    euro = Counter()
    for rid, nuova in aggiorna.items():
        nuova = nuova[0] if isinstance(nuova, tuple) else nuova
        r = righe_per_id[rid]
        trans[(r.get("categoria"), nuova)] += 1
        euro[(r.get("categoria"), nuova)] += _importo(r)
    for (a, b), n in sorted(trans.items(), key=lambda x: -euro[x[0]]):
        print(f"    {n:4d} righe {euro[(a, b)]:>11.2f} EUR  {a} -> {b}")


def _scrivi_fatture(sb, aggiorna, lotto, salta_manuali=True):
    gruppi = {}
    for rid, valore in aggiorna.items():
        categoria, fonte = valore if isinstance(valore, tuple) else (valore, None)
        gruppi.setdefault((categoria, fonte), []).append(rid)
    scritte = 0
    for (categoria, fonte), ids in gruppi.items():
        extra = {"needs_review": False}
        if fonte:
            extra.update({"categoria_fonte": fonte, "categoria_fiducia": "certa"})
        for i in range(0, len(ids), 500):
            scritte += aggiorna_categoria_fatture(
                sb, ids=ids[i:i + 500], categoria=categoria, source=SOURCE,
                extra=extra, batch_id=lotto, salta_correzioni_manuali=salta_manuali,
            )
    return scritte


def _passo_fatture(sb, nome, righe, commit, lotto):
    per_id = {r["id"]: r for r in righe}
    if nome == "giappone":
        aggiorna, saltate, non_decise = piano_giappone(righe)
    elif nome == "pasti":
        aggiorna, saltate = piano_pasti(righe)
        non_decise = []
    else:  # residui
        shop = {r["id"]: "RIVENDITA" for r in righe if r.get("categoria") == "SHOP"}
        # Anche il sake o il mirin scritti dal worker vecchio dopo il passo giappone.
        aggiorna, saltate, non_decise = piano_giappone(righe)
        print(f"  SHOP rimaste da rinominare: {len(shop)}")
        if commit and shop:
            print(f"  COMMIT rinomina: {_scrivi_fatture(sb, shop, lotto, salta_manuali=False)} righe")
    print(f"  righe da spostare: {len(aggiorna)}")
    _riepilogo(per_id, aggiorna)
    _stampa_righe("da spostare (dettaglio)", [(per_id[i], v[0] if isinstance(v, tuple) else v)
                                               for i, v in aggiorna.items()])
    _stampa_righe("SALTATE perche' gia' decise a mano (restano come sono)", saltate)
    _stampa_righe("NON DECISE dal nucleo deterministico (restano come sono)",
                  [(r, "?") for r in non_decise])
    if commit and aggiorna:
        print(f"  COMMIT: {_scrivi_fatture(sb, aggiorna, lotto)} righe aggiornate (lotto {lotto})")


def _passo_memoria(sb, commit, rinomina_shop):
    for tabella, campo, colonne in _MEMORIE:
        voci = _tutte(lambda t=tabella, c=colonne: sb.table(t).select(c))
        aggiorna, cancella, saltate = piano_memoria(voci, campo, rinomina_shop=rinomina_shop)
        for v, nuova in saltate:
            print(f"  memoria {tabella}: SALTATA, decisa a mano dal cliente ({v.get('classificato_da')}): "
                  f"{str(v.get('descrizione'))[:50]} resta {v.get(campo)} (la regola dice {nuova})")
        if not aggiorna and not cancella:
            continue
        per_id = {v["id"]: v for v in voci}
        print(f"  memoria {tabella}: {len(aggiorna)} da aggiornare, {len(cancella)} da cancellare")
        for vid, nuova in list(aggiorna.items())[:40]:
            print(f"    {str(per_id[vid].get('descrizione'))[:55]:<55} {per_id[vid].get(campo)} -> {nuova}")
        for vid in cancella[:40]:
            print(f"    CANCELLA {str(per_id[vid].get('descrizione'))[:55]:<55} {per_id[vid].get(campo)}")
        if commit:
            for vid, nuova in aggiorna.items():
                sb.table(tabella).update({campo: nuova}).eq("id", vid).execute()
            for vid in cancella:
                sb.table(tabella).delete().eq("id", vid).execute()
            print(f"    COMMIT {tabella}: {len(aggiorna)} aggiornate, {len(cancella)} cancellate")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fase K: dati nel nuovo elenco delle categorie.")
    parser.add_argument("passo", choices=["giappone", "pasti", "residui", "tutto"])
    parser.add_argument("--commit", action="store_true", help="scrive davvero (senza, e' un dry-run)")
    args = parser.parse_args(argv)

    sb = _client()
    lotto = str(uuid.uuid4())
    righe = carica_fatture(sb)
    print(f"righe attive lette: {len(righe)} — {'COMMIT' if args.commit else 'DRY-RUN'}")
    passi = ["giappone", "pasti", "residui"] if args.passo == "tutto" else [args.passo]
    for passo in passi:
        print(f"\n== {passo} ==")
        _passo_fatture(sb, passo, righe, args.commit, lotto)
        if passo in ("giappone", "residui"):
            _passo_memoria(sb, args.commit, rinomina_shop=(passo == "residui"))
        if args.commit and passo != passi[-1]:
            righe = carica_fatture(sb)
    if not args.commit:
        print("\n(dry-run: nessuna scrittura — aggiungi --commit per applicare)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
