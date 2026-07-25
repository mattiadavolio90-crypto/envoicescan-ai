"""Riparto costi di gruppo — esplosione delle quote PER CATEGORIA (Voce 6).

Contesto: una fattura di struttura ripartita sul gruppo genera, per ogni sede, una
quota (importo). Storicamente la quota era monolitica e l'intero documento veniva
etichettato con un solo `tipo` (fb|generale). Ma una fattura mista (es. METRO con
VERDURE + detersivi) così finisce tutta in un solo secchio del MOL, falsandolo.

Questo modulo esplode la quota di ogni sede nelle sue CATEGORIE, in proporzione a
come le categorie pesano sull'imponibile reale della fattura. Le categorie sono
quelle già assegnate alle righe in `fatture` (classificazione onesta:
dizionario/regole/AI, "Da Classificare" incluso). Il MOL instrada poi ogni porzione
via _riparto_categoria_is_fb (stesso mapping di config/constants.py).

Fonte UNICA della logica: usata sia dal router (POST /api/riparto/da-fattura, quando
le righe sono già in `fatture`) sia dal worker (all'atterraggio sulla sede tecnica,
per il flusso /api/riparto/da-coda dove la fattura non era ancora atterrata al momento
della ripartizione). Nessun I/O di rete: prende un client Supabase già pronto.

Retrocompatibilità: se la fattura non ha righe vive (storico purgato per GDPR), NON
tocca nulla → le quote restano monolitiche con categoria NULL e il MOL usa il `tipo`
legacy. Nessun riparto esistente cambia finché non lo si ri-esplode esplicitamente.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger("fastapi_worker")

# Campi di una riga fattura come li serve il funnel _fetch_fatture_rows (stessa
# selezione di _build_fatture_base_query). Le righe proiettate devono avere ESATTAMENTE
# queste chiavi per comportarsi come una riga reale in ogni consumatore (aggregati,
# pivot, grafici, trend). `ripartita_su_gruppo` è additivo: i consumatori esistenti lo
# ignorano, il tab Articoli lo userà per badge/filtro.
_CAMPI_RIGA = (
    "id", "file_origine", "numero_riga", "data_documento", "fornitore",
    "descrizione", "quantita", "unita_misura", "prezzo_unitario", "totale_riga",
    "categoria", "needs_review", "tipo_documento", "data_competenza",
    "piva_cedente", "created_at",
)


def _pesi_categoria_fattura(sb, user_id: str, file_origine: str) -> Optional[Dict[str, float]]:
    """Peso (0..1) di ogni categoria sull'imponibile della fattura, dalle righe reali.

    Ritorna None se la fattura non ha righe vive (nessuna base per esplodere: si resta
    sul modello legacy). Le righe con totale_riga==0 (es. note/diciture) non spostano
    pesi ma non fanno fallire nulla. Se il totale imponibile è 0 (fattura interamente a
    importo nullo, caso raro) → None: non c'è nulla da ripartire per categoria.
    """
    righe = (
        sb.table("fatture")
        .select("categoria, totale_riga")
        .eq("user_id", user_id)
        .eq("file_origine", file_origine)
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    if not righe:
        return None

    acc: Dict[str, float] = {}
    tot = 0.0
    for r in righe:
        cat = (r.get("categoria") or "").strip()
        if not cat:
            continue
        imp = float(r.get("totale_riga") or 0)
        acc[cat] = acc.get(cat, 0.0) + imp
        tot += imp

    # Somma per categoria può includere importi negativi (note di credito su una riga):
    # il peso è calcolato sul totale netto. Se il totale netto è 0 non si può ripartire
    # in proporzione → None (resta legacy). Se una singola categoria ha somma 0 ma altre
    # no, quella categoria semplicemente non riceve quota (peso 0), corretto.
    if abs(tot) < 0.01 or not acc:
        return None
    return {cat: (imp / tot) for cat, imp in acc.items()}


def _spezza_importo_per_pesi(importo: float, pesi: Dict[str, float]) -> List[Dict[str, Any]]:
    """Divide `importo` fra le categorie secondo i `pesi` (che sommano ~1). L'ultima
    categoria assorbe l'arrotondamento così la somma pareggia SEMPRE l'importo (nessun
    centesimo perso — stessa cura di _quote_equa nel router)."""
    voci = [(cat, p) for cat, p in pesi.items() if abs(p) > 1e-9]
    if not voci:
        return []
    out: List[Dict[str, Any]] = []
    acc = 0.0
    for i, (cat, p) in enumerate(voci):
        if i < len(voci) - 1:
            q = round(importo * p, 2)
        else:
            q = round(importo - acc, 2)  # l'ultima pareggia
        acc += q
        out.append({"categoria": cat, "quota_importo": q})
    return out


def esplodi_quote_per_categoria(
    sb, user_id: str, riparto_id: str, file_origine: str
) -> bool:
    """Sostituisce le quote monolitiche di un riparto con quote PER CATEGORIA.

    Per ogni quota-sede esistente (ristorante_id, quota_perc, quota_importo) genera N
    righe (una per categoria della fattura), spartendo quota_importo secondo i pesi
    delle categorie sull'imponibile reale. quota_perc è preservata su ogni porzione
    (identifica la % di sede, invariata). Operazione idempotente nell'effetto: ri-
    eseguirla ricalcola le stesse porzioni dalle stesse righe.

    Ritorna True se ha esploso (fattura con righe categorizzate), False se ha lasciato
    le quote come sono (nessuna riga viva → resta il modello legacy per-tipo).

    NON ricalcola le quote mensili: il chiamante lo fa (il router via
    _post_scrittura_riparto; il worker esplicitamente). Così una sola RPC per scrittura.
    """
    pesi = _pesi_categoria_fattura(sb, user_id, file_origine)
    if pesi is None:
        logger.info(
            "esplodi_quote_per_categoria: riparto %s file %s senza righe vive → resta legacy",
            riparto_id, file_origine,
        )
        return False

    quote = (
        sb.table("riparto_costi_catena_quote")
        .select("id, ristorante_id, quota_perc, quota_importo, categoria")
        .eq("riparto_id", riparto_id)
        .execute()
    ).data or []
    if not quote:
        return False

    # Se le quote sono GIÀ per-categoria (categoria valorizzata) non ri-esplodo: sono
    # già nel modello nuovo (evita di esplodere un'esplosione).
    if any((q.get("categoria") or "").strip() for q in quote):
        return True

    # Aggrega per sede: una sola quota-sede monolitica attesa, ma sommo per sicurezza.
    per_sede: Dict[str, Dict[str, float]] = {}
    for q in quote:
        rid = str(q["ristorante_id"])
        s = per_sede.setdefault(rid, {"perc": 0.0, "importo": 0.0})
        s["perc"] += float(q.get("quota_perc") or 0)
        s["importo"] += float(q.get("quota_importo") or 0)

    nuove: List[Dict[str, Any]] = []
    for rid, s in per_sede.items():
        porzioni = _spezza_importo_per_pesi(s["importo"], pesi)
        for p in porzioni:
            nuove.append({
                "riparto_id": riparto_id,
                "ristorante_id": rid,
                "quota_perc": round(s["perc"], 3),
                "quota_importo": p["quota_importo"],
                "categoria": p["categoria"],
            })

    if not nuove:
        return False

    # Rimpiazza le quote del riparto (delete + insert) in una transazione logica:
    # se l'insert fallisse dopo il delete, il chiamante è in un contesto che ritenta
    # (worker) o solleva (router) — ma per sicurezza inseriamo prima di cancellare NO:
    # PostgREST non dà transazione multi-statement qui. Ordine: cancella le vecchie poi
    # inserisci le nuove; l'operazione è ricostruibile dalle righe se interrotta.
    sb.table("riparto_costi_catena_quote").delete().eq("riparto_id", riparto_id).execute()
    sb.table("riparto_costi_catena_quote").insert(nuove).execute()
    logger.info(
        "esplodi_quote_per_categoria: riparto %s → %d quote per-categoria (%d sedi × %d cat)",
        riparto_id, len(nuove), len(per_sede), len(pesi),
    )
    return True


# ═══════════════════════════════════════════════════════════════════════════
# PROIEZIONE DELLE QUOTE COME RIGHE SUL PUNTO VENDITA (Lettura B)
# ═══════════════════════════════════════════════════════════════════════════
# Un PV di catena non possiede righe delle fatture di struttura (stanno sulla sede
# tecnica, marcate ripartita_su_gruppo). Vede solo due numeri mensili in
# margini_mensili. Per mostrargli la SUA quota come righe reali ("le mie verdure di
# gruppo": pomodori, patate...) proiettiamo — in SOLA LETTURA, senza mai scrivere in
# `fatture` — le righe della sede tecnica scalate per la percentuale della sua quota.
#
# Regole (decise, non configurabili — vedi piano Lettura B):
#   • scala QUANTITÀ e TOTALE per quota_perc/100; PREZZO UNITARIO resta reale (così i
#     trend prezzo restano onesti e qta×prezzo≈quota quadra);
#   • l'ultima riga di ogni (riparto, categoria) assorbe l'arrotondamento, così la somma
#     delle righe proiettate di una categoria pareggia AL CENTESIMO la sua quota_importo
#     (stessa cura di _spezza_importo_per_pesi);
#   • riparto senza righe vive (storico purgato GDPR) → una riga SINTETICA per categoria;
#   • fornitore REALE (METRO...), non un fornitore-ombra: è l'informazione che vogliamo
#     mostrare;
#   • id SINTETICO NEGATIVO: le righe proiettate non esistono in `fatture`, l'id<0 le
#     rende inerti alle batch operations (cambio categoria/cestino filtrano id>0).
#
# Il MOL NON passa da qui (legge margini_mensili con un percorso separato): nessun
# doppio conteggio possibile. Queste righe vivono solo nelle viste che leggono `fatture`
# del PV attraverso _fetch_fatture_rows.


def _fattore_quota(quota_perc: float) -> float:
    return float(quota_perc or 0) / 100.0


def _riga_proiettata_base(fonte: Dict[str, Any], rid_sint: int) -> Dict[str, Any]:
    """Copia i campi anagrafici di una riga reale, azzerando quelli che verranno
    riscalati (quantita/totale). Prezzo unitario e descrizione restano identici."""
    r = {k: fonte.get(k) for k in _CAMPI_RIGA}
    r["id"] = rid_sint
    r["ripartita_su_gruppo"] = True
    return r


def _proietta_riparto(
    righe_reali: List[Dict[str, Any]],
    quote_pv: List[Dict[str, Any]],
    quota_perc: float,
    id_gen,
) -> List[Dict[str, Any]]:
    """Proietta le righe reali di UNA fattura sul PV, categoria per categoria.

    `quote_pv`: le quote per-categoria del PV per questo riparto (per pareggiare al
    centesimo). Se una quota ha categoria NULL (legacy) o non ci sono righe reali per
    la sua categoria, si emette una riga sintetica aggregata.
    """
    out: List[Dict[str, Any]] = []
    fatt = _fattore_quota(quota_perc)

    # righe reali raggruppate per categoria (per lo scaling proporzionale)
    per_cat: Dict[str, List[Dict[str, Any]]] = {}
    for r in righe_reali:
        cat = (r.get("categoria") or "").strip()
        per_cat.setdefault(cat, []).append(r)

    # una riga sorgente qualsiasi come "stampo" per le righe sintetiche di fallback
    stampo = righe_reali[0] if righe_reali else None

    for q in quote_pv:
        cat = (q.get("categoria") or "").strip()
        quota_importo = round(float(q.get("quota_importo") or 0), 2)
        reali_cat = per_cat.get(cat) if cat else None

        if reali_cat:
            acc = 0.0
            n = len(reali_cat)
            for i, r in enumerate(reali_cat):
                nr = _riga_proiettata_base(r, id_gen())
                if i < n - 1:
                    tot = round(float(r.get("totale_riga") or 0) * fatt, 2)
                else:
                    tot = round(quota_importo - acc, 2)  # l'ultima pareggia la quota
                acc += tot
                nr["totale_riga"] = tot
                q_orig = float(r.get("quantita") or 0)
                nr["quantita"] = round(q_orig * fatt, 3) if q_orig else None
                out.append(nr)
        else:
            # nessuna riga reale per questa categoria (storico purgato, o quota legacy
            # senza categoria): riga sintetica aggregata, onesta e riconoscibile.
            nr = _riga_proiettata_base(stampo, id_gen()) if stampo else {
                k: None for k in _CAMPI_RIGA
            }
            nr["id"] = nr.get("id") or id_gen()
            nr["ripartita_su_gruppo"] = True
            nr["descrizione"] = (
                f"Quota di gruppo — {cat}" if cat else "Quota costi di gruppo"
            )
            nr["categoria"] = cat or None
            nr["quantita"] = 1
            nr["unita_misura"] = None
            nr["prezzo_unitario"] = quota_importo
            nr["totale_riga"] = quota_importo
            nr["needs_review"] = False
            out.append(nr)

    return out


def righe_ripartite_proiettate(
    sb,
    user_id: str,
    pv_ristorante_id: str,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Righe (dict) che rappresentano la quota di questo PV sui costi di gruppo del
    periodo, proiettate dalle fatture di struttura in SOLA LETTURA.

    Restituisce righe con le stesse chiavi di una riga reale (+ ripartita_su_gruppo=True,
    id<0). Vuoto se il PV non ha quote nel periodo (nessun costo se non è di catena).
    """
    # 1. Riparti che toccano questo PV, filtrati per periodo via anno/mese (indice).
    #    La finestra date del funnel è su data_documento; anno/mese del riparto la
    #    approssima (verificato: coincidono per tutti i riparti con righe vive). Il
    #    filtro fine per data_documento reale avviene sotto sulle righe proiettate.
    mesi = _mesi_nella_finestra(data_da, data_a)
    quote_q = (
        sb.table("riparto_costi_catena_quote")
        .select("riparto_id, quota_perc, quota_importo, categoria")
        .eq("ristorante_id", pv_ristorante_id)
    )
    quote = (quote_q.execute().data) or []
    if not quote:
        return []

    quote_per_riparto: Dict[str, List[Dict[str, Any]]] = {}
    perc_per_riparto: Dict[str, float] = {}
    for q in quote:
        rid = str(q["riparto_id"])
        quote_per_riparto.setdefault(rid, []).append(q)
        perc_per_riparto[rid] = float(q.get("quota_perc") or 0)

    riparti = (
        sb.table("riparto_costi_catena")
        .select("id, user_id, file_origine, fornitore, descrizione, anno, mese")
        .eq("user_id", user_id)
        .in_("id", list(quote_per_riparto.keys()))
        .execute()
    ).data or []
    if mesi is not None:
        riparti = [r for r in riparti if (int(r["anno"]), int(r["mese"])) in mesi]
    if not riparti:
        return []

    # 2. Righe reali delle fatture di struttura coinvolte, in un colpo solo.
    files = sorted({r["file_origine"] for r in riparti if r.get("file_origine")})
    righe_per_file: Dict[str, List[Dict[str, Any]]] = {}
    if files:
        reali = (
            sb.table("fatture")
            .select(",".join(_CAMPI_RIGA))
            .eq("user_id", user_id)
            .in_("file_origine", files)
            .is_("deleted_at", "null")
            .execute()
        ).data or []
        for r in reali:
            righe_per_file.setdefault(r.get("file_origine", ""), []).append(r)

    # 3. Proietta. id sintetico negativo decrescente, unico nella risposta.
    _counter = {"n": 0}

    def _next_id() -> int:
        _counter["n"] -= 1
        return _counter["n"]

    out: List[Dict[str, Any]] = []
    for rip in riparti:
        rid = str(rip["id"])
        righe_reali = righe_per_file.get(rip.get("file_origine") or "", [])
        proiettate = _proietta_riparto(
            righe_reali,
            quote_per_riparto.get(rid, []),
            perc_per_riparto.get(rid, 0.0),
            _next_id,
        )
        # Il fornitore/descrizione della riga sintetica ereditano dal riparto quando non
        # c'è una riga reale da cui copiarli.
        for nr in proiettate:
            if not nr.get("fornitore"):
                nr["fornitore"] = rip.get("fornitore") or "Costi di gruppo"
            if not nr.get("file_origine"):
                nr["file_origine"] = rip.get("file_origine") or f"riparto:{rid}"
            if nr.get("numero_riga") is None:
                nr["numero_riga"] = 0
            if not nr.get("data_documento"):
                nr["data_documento"] = _primo_giorno(rip["anno"], rip["mese"])
        out.extend(proiettate)

    # 4. Filtro fine per finestra date reale (le righe sintetiche usano il 1° del mese).
    if data_da:
        out = [r for r in out if (r.get("data_documento") or "") >= data_da]
    if data_a:
        out = [r for r in out if (r.get("data_documento") or "") <= data_a]
    return out


def _mesi_nella_finestra(
    data_da: Optional[str], data_a: Optional[str]
) -> Optional[set]:
    """Insieme di (anno, mese) coperti dalla finestra [data_da, data_a]. None se aperta
    su entrambi i lati (nessun filtro periodo → tutti i riparti)."""
    if not data_da and not data_a:
        return None
    try:
        d0 = date.fromisoformat(data_da) if data_da else date(2000, 1, 1)
        d1 = date.fromisoformat(data_a) if data_a else date(2100, 12, 31)
    except ValueError:
        return None
    mesi = set()
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        mesi.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return mesi


def _primo_giorno(anno: int, mese: int) -> str:
    return f"{int(anno):04d}-{int(mese):02d}-01"
