"""Prodotti di un tag di catena (gruppo_tag_prodotti): aggiunte e rimozioni in una chiamata.

Stesso contratto della sede (`tag_organizza_service.applica_modifiche_prodotti`)
e stessi controlli, ma sulla tabella di catena: chiave solo `user_id`, nessuna
cache, chiave della descrizione calcolata qui (la tabella di catena non ha il
trigger della sede). Il chiamante verifica PRIMA che il tag sia dell'account
(`_assert_gruppo_tag` nel router); le rimozioni filtrano comunque tag e utente.
"""
from typing import Any, Dict, List, Optional

from services import db_service
from services.tag_organizza_service import chiavi_da_togliere_coerenti, togli_prodotti

TABELLA = "gruppo_tag_prodotti"


def record_prodotti_catena(tag_id: int, user_id: str, descrizioni: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le righe da scrivere: descrizione pulita, chiave normalizzata, niente doppioni."""
    records: List[Dict[str, Any]] = []
    visti = set()
    for item in descrizioni:
        desc = (item.get("descrizione") or "").strip()
        if not desc:
            continue
        key = db_service._normalize_custom_tag_key(desc)
        if not key or key in visti:
            continue
        visti.add(key)
        records.append({
            "tag_id": int(tag_id), "user_id": user_id,
            "descrizione": desc, "descrizione_key": key, "fattore_kg": item.get("fattore_kg"),
        })
    return records


def applica_modifiche_prodotti_catena(
    tag_id: int,
    user_id: str,
    aggiungi: Optional[List[Dict[str, Any]]],
    togli: Optional[List[str]],
) -> Dict[str, Any]:
    """Aggiunge e toglie prodotti da un tag di catena. Ritorna {aggiunte, tolte, associazioni}.

    ValueError per una richiesta incoerente; RimozioniNonRiuscite se le
    rimozioni falliscono dopo che le aggiunte sono state scritte.
    """
    aggiungi = list(aggiungi or [])
    togli = list(togli or [])
    chiavi_togli = chiavi_da_togliere_coerenti(aggiungi, togli)

    from services import get_supabase_client
    sb = get_supabase_client()

    associazioni: List[Dict[str, Any]] = []
    records = record_prodotti_catena(tag_id, user_id, aggiungi)
    if records:
        res = sb.table(TABELLA).upsert(records, on_conflict="tag_id,descrizione_key").execute()
        associazioni = res.data or []

    tolte = 0
    if chiavi_togli:
        tolte = togli_prodotti(sb, TABELLA, tag_id, {"user_id": user_id}, chiavi_togli, len(associazioni))
    return {"aggiunte": len(associazioni), "tolte": tolte, "associazioni": associazioni}
