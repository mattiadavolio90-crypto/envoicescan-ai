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


# ─── Cartelle e preferiti (Fase 2) ────────────────────────────────────────────
# Pura visualizzazione: niente di questo entra in analizza_tag, nel briefing,
# nella catena o nei margini. Tutto e' per sede (user_id + ristorante_id) come i
# tag; la FK composta custom_tags -> custom_tag_cartelle fa da seconda rete.

CAMPI_TAG = "id,nome,emoji,colore,created_at,cartella_id,preferito"
CAMPI_CARTELLA = "id,nome,ordine,created_at"
CAMPI_TAG_MODIFICABILI = ("nome", "emoji", "colore", "cartella_id", "preferito")
# Stesso tetto del campo nel browser (`maxLength={60}` in pannello-tag.tsx):
# una chiamata diretta non deve poter salvare un nome che la barra non mostra.
MAX_NOME_CARTELLA = 60


class NonTrovato(Exception):
    """Il tag o la cartella non sono della sede del chiamante (-> 404)."""


class Conflitto(Exception):
    """Nome gia' usato nella sede, o elenco da riordinare non aggiornato (-> 409)."""


class ScritturaParziale(Exception):
    """Riordino interrotto a meta': sul DB resta un ordine misto (-> 502, il client ricarica)."""


def _client():
    from services import get_supabase_client
    return get_supabase_client()


def _codice(e: Exception) -> str:
    return str(getattr(e, "code", "") or "")


def _e_duplicato(e: Exception) -> bool:
    return _codice(e) == "23505" or "duplicate key" in str(e).lower()


def _e_chiave_esterna(e: Exception) -> bool:
    return _codice(e) == "23503" or "foreign key" in str(e).lower()


def _e_vincolo_check(e: Exception) -> bool:
    return _codice(e) == "23514" or "check constraint" in str(e).lower()


def _nome_obbligatorio(nome: Optional[str], cosa: str) -> str:
    pulito = (nome or "").strip()
    if not pulito:
        raise ValueError(f"Nome {cosa} obbligatorio")
    if cosa == "cartella" and len(pulito) > MAX_NOME_CARTELLA:
        raise ValueError(f"Il nome della cartella non puo' superare {MAX_NOME_CARTELLA} caratteri")
    return pulito


def _tag_normalizzato(riga: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: riga.get(k) for k in CAMPI_TAG.split(",")}
    cartella = out.get("cartella_id")
    out["cartella_id"] = int(cartella) if cartella is not None else None
    out["preferito"] = bool(out.get("preferito"))
    return out


def _cartella_normalizzata(riga: Dict[str, Any]) -> Dict[str, Any]:
    return {k: riga.get(k) for k in CAMPI_CARTELLA.split(",")}


def lista_tag_organizzati(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    """I tag della sede con cartella e stella, in ordine di nome.

    Non passa da `db_service.get_custom_tags` (cachata, select senza le colonne
    nuove). Un errore di lettura sale: una lista vuota direbbe «nessun tag».
    """
    response = (
        _client().table("custom_tags")
        .select(CAMPI_TAG)
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .order("nome")
        .execute()
    )
    return [_tag_normalizzato(r) for r in (response.data or [])]


def lista_cartelle(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    response = (
        _client().table("custom_tag_cartelle")
        .select(CAMPI_CARTELLA)
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .order("ordine")
        .order("id")
        .execute()
    )
    return [_cartella_normalizzata(r) for r in (response.data or [])]


def _cartella_della_sede(sb, cartella_id: int, user_id: str, ristorante_id: str) -> Optional[Dict[str, Any]]:
    response = (
        sb.table("custom_tag_cartelle")
        .select(CAMPI_CARTELLA)
        .eq("id", int(cartella_id))
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .limit(1)
        .execute()
    )
    righe = response.data or []
    return righe[0] if righe else None


def crea_cartella(user_id: str, ristorante_id: str, nome: Optional[str]) -> Dict[str, Any]:
    """Nuova cartella in fondo alla barra (ordine = massimo della sede + 1)."""
    pulito = _nome_obbligatorio(nome, "cartella")
    esistenti = lista_cartelle(user_id, ristorante_id)
    ordine = max((int(c.get("ordine") or 0) for c in esistenti), default=-1) + 1
    try:
        response = (
            _client().table("custom_tag_cartelle")
            .insert({
                "user_id": user_id,
                "ristorante_id": ristorante_id,
                "nome": pulito,
                "ordine": ordine,
            })
            .execute()
        )
    except Exception as e:
        if _e_duplicato(e):
            raise Conflitto(f"Esiste gia' una cartella «{pulito}»") from e
        raise
    finally:
        db_service.clear_tags_cache()
    righe = response.data or []
    if not righe:
        raise RuntimeError("Cartella non creata: nessuna riga restituita")
    return _cartella_normalizzata(righe[0])


def rinomina_cartella(cartella_id: int, user_id: str, ristorante_id: str, nome: Optional[str]) -> Dict[str, Any]:
    pulito = _nome_obbligatorio(nome, "cartella")
    sb = _client()
    if not _cartella_della_sede(sb, cartella_id, user_id, ristorante_id):
        raise NonTrovato("Cartella non trovata")
    try:
        response = (
            sb.table("custom_tag_cartelle")
            .update({"nome": pulito})
            .eq("id", int(cartella_id))
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .execute()
        )
    except Exception as e:
        if _e_duplicato(e):
            raise Conflitto(f"Esiste gia' una cartella «{pulito}»") from e
        raise
    finally:
        db_service.clear_tags_cache()
    righe = response.data or []
    if not righe:
        raise NonTrovato("Cartella non trovata")
    return _cartella_normalizzata(righe[0])


def elimina_cartella(cartella_id: int, user_id: str, ristorante_id: str) -> None:
    """Elimina la cartella; i suoi tag tornano in «Senza cartella».

    I tag non si toccano qui: lo fa la FK `ON DELETE SET NULL (cartella_id)`,
    nella stessa istruzione del DELETE.
    """
    sb = _client()
    if not _cartella_della_sede(sb, cartella_id, user_id, ristorante_id):
        raise NonTrovato("Cartella non trovata")
    try:
        (
            sb.table("custom_tag_cartelle")
            .delete()
            .eq("id", int(cartella_id))
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .execute()
        )
    finally:
        db_service.clear_tags_cache()


def riordina_cartelle(user_id: str, ristorante_id: str, ids: List[int]) -> None:
    """Riscrive l'ordine di TUTTE le cartelle della sede: ordine = posizione in `ids`.

    Prima si controlla l'elenco intero, poi si scrive: un id che non e' della
    sede (NonTrovato) o un elenco che non coincide con le cartelle di adesso
    (Conflitto: un'altra scheda ne ha create o eliminate) non scrivono niente.

    Le scritture sono un UPDATE per cartella spostata, non una transazione: se
    una fallisce a meta' sul DB resta un ordine misto. Sale ScritturaParziale,
    cosi' il client ricarica invece di mostrare l'ordine di prima.
    """
    richiesti = [int(i) for i in ids]
    attuali = {int(c["id"]): int(c.get("ordine") or 0) for c in lista_cartelle(user_id, ristorante_id)}
    if any(i not in attuali for i in richiesti):
        raise NonTrovato("Cartella non trovata")
    if len(richiesti) != len(set(richiesti)) or set(richiesti) != set(attuali):
        raise Conflitto("Elenco delle cartelle non aggiornato: ricarica la pagina")
    sb = _client()
    try:
        for posizione, cartella_id in enumerate(richiesti):
            if attuali[cartella_id] == posizione:
                continue
            try:
                (
                    sb.table("custom_tag_cartelle")
                    .update({"ordine": posizione})
                    .eq("id", cartella_id)
                    .eq("user_id", user_id)
                    .eq("ristorante_id", ristorante_id)
                    .execute()
                )
            except Exception as e:
                raise ScritturaParziale("Riordino salvato solo in parte: ricarica la pagina") from e
    finally:
        db_service.clear_tags_cache()


def _leggi_tag(sb, tag_id: int, user_id: str, ristorante_id: str) -> Dict[str, Any]:
    response = (
        sb.table("custom_tags")
        .select(CAMPI_TAG)
        .eq("id", int(tag_id))
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .limit(1)
        .execute()
    )
    righe = response.data or []
    if not righe:
        raise NonTrovato("Tag non trovato")
    return _tag_normalizzato(righe[0])


def aggiorna_tag_parziale(tag_id: int, user_id: str, ristorante_id: str, campi: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna SOLO i campi presenti in `campi` (le chiavi inviate nel body).

    `cartella_id: None` = «Senza cartella». Una cartella che non e' della sede e'
    NonTrovato, prima di scrivere; la FK composta rifiuterebbe comunque.
    """
    sb = _client()
    payload: Dict[str, Any] = {}
    if "nome" in campi:
        payload["nome"] = _nome_obbligatorio(campi["nome"], "tag")
    if "emoji" in campi:
        payload["emoji"] = campi["emoji"] or None
    if "colore" in campi:
        payload["colore"] = campi["colore"] or None
    if "preferito" in campi:
        if campi["preferito"] is None:
            raise ValueError("Preferito deve essere vero o falso")
        payload["preferito"] = bool(campi["preferito"])
    if "cartella_id" in campi:
        cartella_id = campi["cartella_id"]
        if cartella_id is not None and not _cartella_della_sede(sb, cartella_id, user_id, ristorante_id):
            raise NonTrovato("Cartella non trovata")
        payload["cartella_id"] = int(cartella_id) if cartella_id is not None else None

    if not payload:
        return _leggi_tag(sb, tag_id, user_id, ristorante_id)

    try:
        response = (
            sb.table("custom_tags")
            .update(payload)
            .eq("id", int(tag_id))
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .execute()
        )
    except Exception as e:
        if _e_duplicato(e):
            raise Conflitto(f"Esiste gia' un tag «{payload.get('nome', '')}»") from e
        if _e_chiave_esterna(e):
            raise NonTrovato("Cartella non trovata") from e
        if _e_vincolo_check(e):
            raise ValueError("Valore non valido per il tag") from e
        raise
    finally:
        db_service.clear_tags_cache()
    righe = response.data or []
    if not righe:
        raise NonTrovato("Tag non trovato")
    return _tag_normalizzato(righe[0])
