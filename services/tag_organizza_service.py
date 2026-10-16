"""Modifica in blocco dei prodotti di un tag e organizzazione dei tag (cartelle, stella).

Il chiamante verifica PRIMA che il tag sia dell'utente e della sede
(`_assert_tag_ownership` nel router): le rimozioni filtrano comunque tag, utente
e sede, cosi' una chiave presente anche in un altro tag o in un'altra sede non
viene mai toccata. Cartelle e stella servono anche i tag di catena
(`AMBITO_CATENA`); i prodotti di un tag di catena li modifica
`services/gruppo_tag_organizza_service.py` coi controlli e le rimozioni di qui.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

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


def _righe_prodotti(supabase_client, tabella: str, tag_id: int, chiave: Dict[str, str]) -> List[Dict[str, Any]]:
    righe: List[Dict[str, Any]] = []
    inizio = 0
    while True:
        query = supabase_client.table(tabella).select("id,descrizione_key").eq("tag_id", int(tag_id))
        for colonna, valore in chiave.items():
            query = query.eq(colonna, valore)
        response = query.order("id").range(inizio, inizio + PAGINA_LETTURA - 1).execute()
        pagina = response.data or []
        righe.extend(pagina)
        if len(pagina) < PAGINA_LETTURA:
            return righe
        inizio += PAGINA_LETTURA


def _righe_del_tag(supabase_client, tag_id: int, user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    return _righe_prodotti(
        supabase_client, "custom_tag_prodotti", tag_id, {"user_id": user_id, "ristorante_id": ristorante_id}
    )


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


def chiavi_da_togliere_coerenti(
    aggiungi: List[Dict[str, Any]], togli: List[Optional[str]]
) -> List[str]:
    """Le chiavi da togliere, dopo aver rifiutato le richieste incoerenti.

    ValueError se una lista supera MAX_ELEMENTI_PER_LISTA o se lo stesso prodotto
    e' sia da aggiungere sia da togliere: non si sceglie a caso quale vince.
    """
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
    return chiavi_togli


def togli_prodotti(
    supabase_client, tabella: str, tag_id: int, chiave: Dict[str, str], chiavi_togli: List[str], aggiunte: int
) -> int:
    """Toglie dal tag le righe delle chiavi date, a lotti per id. Ritorna quante.

    RimozioniNonRiuscite se la lettura o un lotto falliscono: le aggiunte (gia'
    scritte) restano, e il messaggio dice quante.
    """
    try:
        ids = _id_da_togliere(_righe_prodotti(supabase_client, tabella, tag_id, chiave), chiavi_togli)
    except Exception as e:
        raise RimozioniNonRiuscite(f"aggiunte={aggiunte} lettura: {e}") from e
    tolte = 0
    for inizio in range(0, len(ids), LOTTO_RIMOZIONI):
        lotto = ids[inizio:inizio + LOTTO_RIMOZIONI]
        query = supabase_client.table(tabella).delete().eq("tag_id", int(tag_id))
        for colonna, valore in chiave.items():
            query = query.eq(colonna, valore)
        try:
            response = query.in_("id", lotto).execute()
        except Exception as e:
            raise RimozioniNonRiuscite(f"aggiunte={aggiunte} tolte={tolte}: {e}") from e
        tolte += len(response.data or [])
    return tolte


def applica_modifiche_prodotti(
    tag_id: int,
    user_id: str,
    ristorante_id: str,
    aggiungi: Optional[List[Dict[str, Any]]],
    togli: Optional[List[str]],
) -> Dict[str, Any]:
    """Aggiunge e toglie prodotti da un tag. Ritorna {aggiunte, tolte, associazioni}.

    ValueError per una richiesta incoerente (chiavi_da_togliere_coerenti).
    PermissionError (da aggiungi_associazioni) se il tag non e' dell'utente.
    """
    aggiungi = list(aggiungi or [])
    togli = list(togli or [])
    chiavi_togli = chiavi_da_togliere_coerenti(aggiungi, togli)

    associazioni: List[Dict[str, Any]] = []
    if aggiungi:
        associazioni = db_service.aggiungi_associazioni(int(tag_id), aggiungi, user_id=user_id)

    tolte = 0
    try:
        if chiavi_togli:
            tolte = togli_prodotti(
                _client(), "custom_tag_prodotti", tag_id,
                {"user_id": user_id, "ristorante_id": ristorante_id}, chiavi_togli, len(associazioni),
            )
    finally:
        if aggiungi or chiavi_togli:
            db_service.clear_tags_cache()

    return {"aggiunte": len(associazioni), "tolte": tolte, "associazioni": associazioni}


# ─── Cartelle e preferiti (Fase 2) ────────────────────────────────────────────
# Pura visualizzazione: niente di questo entra in analizza_tag, nel briefing,
# nell'analisi di catena o nei margini. Le stesse funzioni servono due AMBITI:
# la sede (custom_tags, chiave user_id + ristorante_id) e la catena
# (gruppo_tags, chiave user_id). In tutti e due la FK composta tag -> cartella
# fa da seconda rete. Le firme pubbliche senza ambito sono quelle della sede.

CAMPI_TAG = "id,nome,emoji,colore,created_at,cartella_id,preferito,ordine"
CAMPI_CARTELLA = "id,nome,ordine,created_at"
CAMPI_TAG_MODIFICABILI = ("nome", "emoji", "colore", "cartella_id", "preferito")
# Stesso tetto del campo nel browser (`maxLength={60}` in pannello-tag.tsx):
# una chiamata diretta non deve poter salvare un nome che la barra non mostra.
MAX_NOME_CARTELLA = 60


class NonTrovato(Exception):
    """Il tag o la cartella non sono dell'ambito del chiamante (-> 404)."""


class Conflitto(Exception):
    """Nome gia' usato nell'ambito, o elenco da riordinare non aggiornato (-> 409)."""


class ScritturaParziale(Exception):
    """Riordino interrotto a meta': sul DB resta un ordine misto (-> 502, il client ricarica)."""


@dataclass(frozen=True)
class Ambito:
    """Dove vivono tag e cartelle, e con quale chiave si filtrano.

    `chiave` elenca le colonne che ogni lettura e scrittura filtra (e che ogni
    INSERT scrive). `cartella_propria` e `svuota_cache` passano per nome dal
    modulo, cosi' un test che le sostituisce le sostituisce davvero.
    """
    tabella_tag: str
    tabella_cartelle: str
    chiave: Tuple[str, ...]
    cartella_propria: Callable[[Any, int, Dict[str, str]], Optional[Dict[str, Any]]]
    svuota_cache: Callable[[], None]


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
    out["ordine"] = int(out.get("ordine") or 0)
    return out


def _cartella_normalizzata(riga: Dict[str, Any]) -> Dict[str, Any]:
    return {k: riga.get(k) for k in CAMPI_CARTELLA.split(",")}


def _filtra(query, chiave: Dict[str, str]):
    for colonna, valore in chiave.items():
        query = query.eq(colonna, valore)
    return query


def _chiave(ambito: Ambito, chiave: Dict[str, str]) -> Dict[str, str]:
    """La chiave con TUTTE e sole le colonne dell'ambito, mai vuote."""
    if set(chiave) != set(ambito.chiave) or not all(chiave.values()):
        raise ValueError(f"Chiave {sorted(chiave)} non valida per {ambito.tabella_tag}")
    return {c: chiave[c] for c in ambito.chiave}


def _cartella_propria(sb, ambito: Ambito, cartella_id: int, chiave: Dict[str, str]) -> Optional[Dict[str, Any]]:
    response = (
        _filtra(sb.table(ambito.tabella_cartelle).select(CAMPI_CARTELLA).eq("id", int(cartella_id)), chiave)
        .limit(1)
        .execute()
    )
    righe = response.data or []
    return righe[0] if righe else None


def _cartella_della_sede(sb, cartella_id: int, user_id: str, ristorante_id: str) -> Optional[Dict[str, Any]]:
    return _cartella_propria(sb, AMBITO_SEDE, cartella_id, {"user_id": user_id, "ristorante_id": ristorante_id})


def _cartella_dell_account(sb, cartella_id: int, user_id: str) -> Optional[Dict[str, Any]]:
    return _cartella_propria(sb, AMBITO_CATENA, cartella_id, {"user_id": user_id})


AMBITO_SEDE = Ambito(
    tabella_tag="custom_tags",
    tabella_cartelle="custom_tag_cartelle",
    chiave=("user_id", "ristorante_id"),
    cartella_propria=lambda sb, cid, k: _cartella_della_sede(sb, cid, k["user_id"], k["ristorante_id"]),
    svuota_cache=lambda: db_service.clear_tags_cache(),
)

# I tag di catena non hanno cache: la lista si rilegge a ogni GET.
AMBITO_CATENA = Ambito(
    tabella_tag="gruppo_tags",
    tabella_cartelle="gruppo_tag_cartelle",
    chiave=("user_id",),
    cartella_propria=lambda sb, cid, k: _cartella_dell_account(sb, cid, k["user_id"]),
    svuota_cache=lambda: None,
)


def lista_tag_organizzati_in(ambito: Ambito, chiave: Dict[str, str]) -> List[Dict[str, Any]]:
    """I tag dell'ambito con cartella, stella e posizione, in ordine (ordine, nome, id).

    Per la sede non passa da `db_service.get_custom_tags` (cachata, select senza
    le colonne nuove). Un errore di lettura sale: una lista vuota direbbe
    «nessun tag».
    """
    chiave = _chiave(ambito, chiave)
    response = (
        _filtra(_client().table(ambito.tabella_tag).select(CAMPI_TAG), chiave)
        .order("ordine")
        .order("nome")
        .order("id")
        .execute()
    )
    return [_tag_normalizzato(r) for r in (response.data or [])]


def lista_cartelle_in(ambito: Ambito, chiave: Dict[str, str]) -> List[Dict[str, Any]]:
    chiave = _chiave(ambito, chiave)
    response = (
        _filtra(_client().table(ambito.tabella_cartelle).select(CAMPI_CARTELLA), chiave)
        .order("ordine")
        .order("id")
        .execute()
    )
    return [_cartella_normalizzata(r) for r in (response.data or [])]


def crea_cartella_in(ambito: Ambito, chiave: Dict[str, str], nome: Optional[str]) -> Dict[str, Any]:
    """Nuova cartella in fondo alla barra (ordine = massimo dell'ambito + 1)."""
    chiave = _chiave(ambito, chiave)
    pulito = _nome_obbligatorio(nome, "cartella")
    esistenti = lista_cartelle_in(ambito, chiave)
    ordine = max((int(c.get("ordine") or 0) for c in esistenti), default=-1) + 1
    try:
        response = (
            _client().table(ambito.tabella_cartelle)
            .insert({**chiave, "nome": pulito, "ordine": ordine})
            .execute()
        )
    except Exception as e:
        if _e_duplicato(e):
            raise Conflitto(f"Esiste gia' una cartella «{pulito}»") from e
        raise
    finally:
        ambito.svuota_cache()
    righe = response.data or []
    if not righe:
        raise RuntimeError("Cartella non creata: nessuna riga restituita")
    return _cartella_normalizzata(righe[0])


def rinomina_cartella_in(
    ambito: Ambito, chiave: Dict[str, str], cartella_id: int, nome: Optional[str]
) -> Dict[str, Any]:
    chiave = _chiave(ambito, chiave)
    pulito = _nome_obbligatorio(nome, "cartella")
    sb = _client()
    if not ambito.cartella_propria(sb, cartella_id, chiave):
        raise NonTrovato("Cartella non trovata")
    try:
        response = _filtra(
            sb.table(ambito.tabella_cartelle).update({"nome": pulito}).eq("id", int(cartella_id)), chiave
        ).execute()
    except Exception as e:
        if _e_duplicato(e):
            raise Conflitto(f"Esiste gia' una cartella «{pulito}»") from e
        raise
    finally:
        ambito.svuota_cache()
    righe = response.data or []
    if not righe:
        raise NonTrovato("Cartella non trovata")
    return _cartella_normalizzata(righe[0])


def elimina_cartella_in(ambito: Ambito, chiave: Dict[str, str], cartella_id: int) -> None:
    """Elimina la cartella; i suoi tag tornano in «Senza cartella».

    I tag non si toccano qui: lo fa la FK `ON DELETE SET NULL (cartella_id)`,
    nella stessa istruzione del DELETE.
    """
    chiave = _chiave(ambito, chiave)
    sb = _client()
    if not ambito.cartella_propria(sb, cartella_id, chiave):
        raise NonTrovato("Cartella non trovata")
    try:
        _filtra(sb.table(ambito.tabella_cartelle).delete().eq("id", int(cartella_id)), chiave).execute()
    finally:
        ambito.svuota_cache()


def riordina_cartelle_in(ambito: Ambito, chiave: Dict[str, str], ids: List[int]) -> None:
    """Riscrive l'ordine di TUTTE le cartelle dell'ambito: ordine = posizione in `ids`.

    Prima si controlla l'elenco intero, poi si scrive: un id che non e'
    dell'ambito (NonTrovato) o un elenco che non coincide con le cartelle di
    adesso (Conflitto: un'altra scheda ne ha create o eliminate) non scrivono
    niente.

    Le scritture sono un UPDATE per cartella spostata, non una transazione: se
    una fallisce a meta' sul DB resta un ordine misto. Sale ScritturaParziale,
    cosi' il client ricarica invece di mostrare l'ordine di prima.
    """
    chiave = _chiave(ambito, chiave)
    richiesti = [int(i) for i in ids]
    attuali = {int(c["id"]): int(c.get("ordine") or 0) for c in lista_cartelle_in(ambito, chiave)}
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
                _filtra(
                    sb.table(ambito.tabella_cartelle).update({"ordine": posizione}).eq("id", cartella_id), chiave
                ).execute()
            except Exception as e:
                raise ScritturaParziale("Riordino salvato solo in parte: ricarica la pagina") from e
    finally:
        ambito.svuota_cache()


def _posizioni_tag(sb, ambito: Ambito, chiave: Dict[str, str]) -> Dict[int, Tuple[Optional[int], int]]:
    """{id: (cartella_id, ordine)} di tutti i tag dell'ambito."""
    response = _filtra(sb.table(ambito.tabella_tag).select("id,cartella_id,ordine"), chiave).execute()
    out: Dict[int, Tuple[Optional[int], int]] = {}
    for r in response.data or []:
        cartella = r.get("cartella_id")
        out[int(r["id"])] = (int(cartella) if cartella is not None else None, int(r.get("ordine") or 0))
    return out


def _in_fondo(posizioni: Dict[int, Tuple[Optional[int], int]], cartella_id: Optional[int], escludi: int) -> int:
    """La posizione dopo l'ultimo tag del gruppo (stesso criterio del trigger sull'INSERT)."""
    nel_gruppo = [o for i, (c, o) in posizioni.items() if c == cartella_id and i != escludi]
    return max(nel_gruppo, default=-1) + 1


def riordina_tag_in(
    ambito: Ambito, chiave: Dict[str, str], cartella_id: Optional[int], ids: List[int]
) -> None:
    """Riscrive l'ordine dei tag di UN gruppo (una cartella o «Senza cartella»).

    `ids` e' il gruppo come deve risultare, dall'alto: tutti i tag che oggi ci
    sono, piu' quelli che ci arrivano da un'altra cartella (spostati qui con la
    loro posizione, in una chiamata sola). Prima si controlla, poi si scrive: un
    id o una cartella che non sono dell'ambito (NonTrovato), un doppione o un
    tag del gruppo che manca dall'elenco (Conflitto: un'altra scheda ha
    cambiato il gruppo) non scrivono niente.

    Un UPDATE per tag che cambia posto o cartella, non una transazione: se uno
    fallisce a meta' sale ScritturaParziale e il client ricarica, come per il
    riordino delle cartelle. Il gruppo di partenza di un tag spostato resta con
    un buco nella numerazione: l'ordine relativo non cambia.
    """
    chiave = _chiave(ambito, chiave)
    richiesti = [int(i) for i in ids]
    if len(richiesti) > MAX_ELEMENTI_PER_LISTA:
        raise ValueError(f"Troppi tag in un solo riordino (massimo {MAX_ELEMENTI_PER_LISTA})")
    sb = _client()
    destinazione = int(cartella_id) if cartella_id is not None else None
    if destinazione is not None and not ambito.cartella_propria(sb, destinazione, chiave):
        raise NonTrovato("Cartella non trovata")
    posizioni = _posizioni_tag(sb, ambito, chiave)
    if any(i not in posizioni for i in richiesti):
        raise NonTrovato("Tag non trovato")
    del_gruppo = {i for i, (c, _) in posizioni.items() if c == destinazione}
    if len(richiesti) != len(set(richiesti)) or not del_gruppo.issubset(richiesti):
        raise Conflitto("Elenco dei tag non aggiornato: ricarica la pagina")
    try:
        for posizione, tag_id in enumerate(richiesti):
            cartella_attuale, ordine_attuale = posizioni[tag_id]
            payload: Dict[str, Any] = {}
            if ordine_attuale != posizione:
                payload["ordine"] = posizione
            if cartella_attuale != destinazione:
                payload["cartella_id"] = destinazione
            if not payload:
                continue
            try:
                _filtra(sb.table(ambito.tabella_tag).update(payload).eq("id", tag_id), chiave).execute()
            except Exception as e:
                raise ScritturaParziale("Riordino salvato solo in parte: ricarica la pagina") from e
    finally:
        ambito.svuota_cache()


def _leggi_tag(sb, ambito: Ambito, tag_id: int, chiave: Dict[str, str]) -> Dict[str, Any]:
    response = (
        _filtra(sb.table(ambito.tabella_tag).select(CAMPI_TAG).eq("id", int(tag_id)), chiave)
        .limit(1)
        .execute()
    )
    righe = response.data or []
    if not righe:
        raise NonTrovato("Tag non trovato")
    return _tag_normalizzato(righe[0])


def aggiorna_tag_parziale_in(
    ambito: Ambito, chiave: Dict[str, str], tag_id: int, campi: Dict[str, Any]
) -> Dict[str, Any]:
    """Aggiorna SOLO i campi presenti in `campi` (le chiavi inviate nel body).

    `cartella_id: None` = «Senza cartella». Una cartella che non e' dell'ambito
    e' NonTrovato, prima di scrivere; la FK composta rifiuterebbe comunque. Un
    tag che cambia cartella va in fondo a quella nuova.
    """
    chiave = _chiave(ambito, chiave)
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
        if cartella_id is not None and not ambito.cartella_propria(sb, cartella_id, chiave):
            raise NonTrovato("Cartella non trovata")
        payload["cartella_id"] = int(cartella_id) if cartella_id is not None else None
        posizioni = _posizioni_tag(sb, ambito, chiave)
        if int(tag_id) in posizioni and posizioni[int(tag_id)][0] != payload["cartella_id"]:
            payload["ordine"] = _in_fondo(posizioni, payload["cartella_id"], int(tag_id))

    if not payload:
        return _leggi_tag(sb, ambito, tag_id, chiave)

    try:
        response = _filtra(sb.table(ambito.tabella_tag).update(payload).eq("id", int(tag_id)), chiave).execute()
    except Exception as e:
        if _e_duplicato(e):
            raise Conflitto(f"Esiste gia' un tag «{payload.get('nome', '')}»") from e
        if _e_chiave_esterna(e):
            raise NonTrovato("Cartella non trovata") from e
        if _e_vincolo_check(e):
            raise ValueError("Valore non valido per il tag") from e
        raise
    finally:
        ambito.svuota_cache()
    righe = response.data or []
    if not righe:
        raise NonTrovato("Tag non trovato")
    return _tag_normalizzato(righe[0])


# ─── Firme della sede (router tag.py) ─────────────────────────────────────────
def _sede(user_id: str, ristorante_id: str) -> Dict[str, str]:
    return {"user_id": user_id, "ristorante_id": ristorante_id}


def lista_tag_organizzati(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    return lista_tag_organizzati_in(AMBITO_SEDE, _sede(user_id, ristorante_id))


def lista_cartelle(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    return lista_cartelle_in(AMBITO_SEDE, _sede(user_id, ristorante_id))


def crea_cartella(user_id: str, ristorante_id: str, nome: Optional[str]) -> Dict[str, Any]:
    return crea_cartella_in(AMBITO_SEDE, _sede(user_id, ristorante_id), nome)


def rinomina_cartella(cartella_id: int, user_id: str, ristorante_id: str, nome: Optional[str]) -> Dict[str, Any]:
    return rinomina_cartella_in(AMBITO_SEDE, _sede(user_id, ristorante_id), cartella_id, nome)


def elimina_cartella(cartella_id: int, user_id: str, ristorante_id: str) -> None:
    elimina_cartella_in(AMBITO_SEDE, _sede(user_id, ristorante_id), cartella_id)


def riordina_cartelle(user_id: str, ristorante_id: str, ids: List[int]) -> None:
    riordina_cartelle_in(AMBITO_SEDE, _sede(user_id, ristorante_id), ids)


def riordina_tag(user_id: str, ristorante_id: str, cartella_id: Optional[int], ids: List[int]) -> None:
    riordina_tag_in(AMBITO_SEDE, _sede(user_id, ristorante_id), cartella_id, ids)


def aggiorna_tag_parziale(tag_id: int, user_id: str, ristorante_id: str, campi: Dict[str, Any]) -> Dict[str, Any]:
    return aggiorna_tag_parziale_in(AMBITO_SEDE, _sede(user_id, ristorante_id), tag_id, campi)
