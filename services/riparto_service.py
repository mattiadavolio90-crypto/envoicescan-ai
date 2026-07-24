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

from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("fastapi_worker")


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
