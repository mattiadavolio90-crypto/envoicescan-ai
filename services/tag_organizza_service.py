"""Modifica in blocco dei prodotti di un tag di sede: aggiunte e rimozioni in una chiamata.

Il chiamante verifica PRIMA che il tag sia dell'utente e della sede
(`_assert_tag_ownership` nel router): le rimozioni filtrano comunque tag, utente
e sede, cosi' una chiave presente anche in un altro tag o in un'altra sede non
viene mai toccata.
"""
from typing import Any, Dict, List, Optional

from services import db_service

MAX_ELEMENTI_PER_LISTA = 2000
# Si cancella per id, non per chiave: postgrest-py mette fra virgolette i valori
# di `in.(...)` che contengono `,:()` ma NON fa l'escape delle `"` interne, cosi'
# `MOZZARELLA "FIOR DI LATTE" 1,5KG` si spezza sulla virgola e non trova la riga
# (200, zero tolte, prodotto ancora nel tag). Gli id restano comunque nella URL:
# a lotti, sotto il limite del gateway.
LOTTO_RIMOZIONI = 100
PAGINA_LETTURA = 1000


class RimozioniNonRiuscite(Exception):
    """Le aggiunte sono state scritte, le rimozioni (o parte) no."""


def _chiavi_aggiunte(aggiungi: List[Dict[str, Any]]) -> set:
    chiavi = set()
    for item in aggiungi:
        for testo in (item.get("descrizione"), item.get("descrizione_key")):
            chiave = db_service._normalize_custom_tag_key(testo or "")
            if chiave:
                chiavi.add(chiave)
    return chiavi


def _chiavi_da_togliere(togli: List[Optional[str]]) -> List[str]:
    viste: List[str] = []
    for testo in togli:
        grezza = (testo or "").strip()
        if grezza and grezza not in viste:
            viste.append(grezza)
    return viste


def _righe_del_tag(supabase_client, tag_id: int, user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    righe: List[Dict[str, Any]] = []
    inizio = 0
    while True:
        response = (
            supabase_client.table("custom_tag_prodotti")
            .select("id,descrizione_key")
            .eq("tag_id", int(tag_id))
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .order("id")
            .range(inizio, inizio + PAGINA_LETTURA - 1)
            .execute()
        )
        pagina = response.data or []
        righe.extend(pagina)
        if len(pagina) < PAGINA_LETTURA:
            return righe
        inizio += PAGINA_LETTURA


def _id_da_togliere(righe: List[Dict[str, Any]], chiavi: List[str]) -> List[int]:
    """Gli id delle righe che corrispondono alle chiavi richieste.

    La chiave salvata la calcola il trigger con `public.normalize_custom_tag_key`,
    che fuori dall'ASCII (`ß`, spazi Unicode, legature) non coincide con la
    versione Python: il riquadro rimanda la chiave letta dal DB, che si confronta
    cosi' com'e'. La normalizzazione Python serve solo a chi manda il testo
    grezzo, e solo se la chiave non ha gia' trovato la sua riga esatta: cosi' due
    righe che Python renderebbe uguali non si portano via a vicenda.
    """
    per_chiave: Dict[str, List[int]] = {}
    per_normalizzata: Dict[str, List[int]] = {}
    for r in righe:
        chiave = str(r.get("descrizione_key") or "")
        per_chiave.setdefault(chiave, []).append(int(r["id"]))
        per_normalizzata.setdefault(db_service._normalize_custom_tag_key(chiave), []).append(int(r["id"]))
    ids: List[int] = []
    for chiave in chiavi:
        trovati = per_chiave.get(chiave) or per_normalizzata.get(db_service._normalize_custom_tag_key(chiave), [])
        for i in trovati:
            if i not in ids:
                ids.append(i)
    return ids


def applica_modifiche_prodotti(
    tag_id: int,
    user_id: str,
    ristorante_id: str,
    aggiungi: Optional[List[Dict[str, Any]]],
    togli: Optional[List[str]],
) -> Dict[str, Any]:
    """Aggiunge e toglie prodotti da un tag. Ritorna {aggiunte, tolte, associazioni}.

    ValueError se una lista supera MAX_ELEMENTI_PER_LISTA o se lo stesso prodotto
    e' sia da aggiungere sia da togliere: la richiesta e' incoerente e non si
    sceglie a caso quale delle due vince. PermissionError (da
    aggiungi_associazioni) se il tag non e' dell'utente.
    """
    aggiungi = list(aggiungi or [])
    togli = list(togli or [])
    if len(aggiungi) > MAX_ELEMENTI_PER_LISTA or len(togli) > MAX_ELEMENTI_PER_LISTA:
        raise ValueError(
            f"Troppi prodotti in una sola modifica (massimo {MAX_ELEMENTI_PER_LISTA} per lista)"
        )

    chiavi_togli = _chiavi_da_togliere(togli)
    in_conflitto = _chiavi_aggiunte(aggiungi).intersection(
        db_service._normalize_custom_tag_key(c) for c in chiavi_togli
    )
    if in_conflitto:
        esempio = sorted(in_conflitto)[0]
        raise ValueError(
            f"Lo stesso prodotto e' sia da aggiungere sia da togliere: {esempio}"
        )

    associazioni: List[Dict[str, Any]] = []
    if aggiungi:
        associazioni = db_service.aggiungi_associazioni(int(tag_id), aggiungi, user_id=user_id)

    tolte = 0
    try:
        if chiavi_togli:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
            try:
                ids = _id_da_togliere(
                    _righe_del_tag(supabase_client, tag_id, user_id, ristorante_id), chiavi_togli
                )
            except Exception as e:
                raise RimozioniNonRiuscite(f"aggiunte={len(associazioni)} lettura: {e}") from e
            for inizio in range(0, len(ids), LOTTO_RIMOZIONI):
                lotto = ids[inizio:inizio + LOTTO_RIMOZIONI]
                try:
                    response = (
                        supabase_client.table("custom_tag_prodotti")
                        .delete()
                        .eq("tag_id", int(tag_id))
                        .eq("user_id", user_id)
                        .eq("ristorante_id", ristorante_id)
                        .in_("id", lotto)
                        .execute()
                    )
                except Exception as e:
                    raise RimozioniNonRiuscite(
                        f"aggiunte={len(associazioni)} tolte={tolte}: {e}"
                    ) from e
                tolte += len(response.data or [])
    finally:
        if aggiungi or chiavi_togli:
            db_service.clear_tags_cache()

    return {"aggiunte": len(associazioni), "tolte": tolte, "associazioni": associazioni}
