"""Router dominio ACCOUNT — profilo, piano, contatori, cambio password, preferenze.

Estratto da fastapi_worker.py. Path, gate e response invariati.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("fastapi_worker")

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint. _verify_worker_key resta esplicito perche' usato in
# Depends() a import-time (firma identica per l'iniezione FastAPI).
def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _resolve_ristorante_id(*args, **kwargs):
    return _fw()._resolve_ristorante_id(*args, **kwargs)


def _resolve_piano_effettivo(*args, **kwargs):
    return _fw()._resolve_piano_effettivo(*args, **kwargs)


def _chat_domande_oggi(*args, **kwargs):
    return _fw()._chat_domande_oggi(*args, **kwargs)


def _chat_limite_per_piano(*args, **kwargs):
    return _fw()._chat_limite_per_piano(*args, **kwargs)


def _chat_quota_view(*args, **kwargs):
    return _fw()._chat_quota_view(*args, **kwargs)


def _is_admin_email(*args, **kwargs):
    return _fw()._is_admin_email(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


def _verify_admin(
    authorization: Optional[str] = Header(None),
    x_worker_key: Optional[str] = Header(None),
) -> dict:
    """Gate admin: delega a routers.admin._verify_admin (firma identica per
    l'iniezione FastAPI degli header). Import lazy per evitare cicli a import-time."""
    from services.routers.admin import _verify_admin as _va
    return _va(authorization=authorization, x_worker_key=x_worker_key)

router = APIRouter()

_PIANO_LIMITI: Dict[str, int] = {
    "free": 50,
    "base": 50,
    "plus": 100,
    "pro": 200,
}


@router.get("/api/account/me", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_me(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dati account estesi: profilo, piano, contatori utilizzo."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    # Dati utente freschi dal DB (piano, price_alert_threshold, created_at)
    user_row = (
        sb.table("users")
        .select("id, email, nome_ristorante, ragione_sociale, partita_iva, piano, "
                "price_alert_threshold, tema, created_at, last_login")
        .eq("id", user_id)
        .single()
        .execute()
    )
    row = user_row.data or {}

    # Sede attiva: nel modello piano-per-sede il piano e i dati anagrafici (nome,
    # P.IVA, ragione) mostrati al cliente sono quelli della SEDE selezionata, non
    # dell'account. Fallback ai valori account quando la sede non li ha (mono-sede
    # storici / transizione). Una sola lettura della riga sede.
    ristorante_id = _resolve_ristorante_id(user, sb)
    sede = {}
    if ristorante_id:
        try:
            sede_resp = (
                sb.table("ristoranti")
                .select("nome_ristorante, partita_iva, ragione_sociale, piano")
                .eq("id", ristorante_id)
                .single()
                .execute()
            )
            sede = sede_resp.data or {}
        except Exception:
            sede = {}

    # Piano effettivo: sede.piano, altrimenti users.piano, altrimenti 'base'.
    piano_raw = (sede.get("piano") or row.get("piano") or "base").lower().strip()
    limite_fatture = _PIANO_LIMITI.get(piano_raw, 50)

    # Contatore fatture del mese corrente (documenti unici, non righe)
    now = datetime.now(timezone.utc)
    mese_inizio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    fatture_mese = 0
    if ristorante_id:
        try:
            # Conta file_origine distinti nel mese corrente
            fd_resp = (
                sb.table("fatture_documenti")
                .select("file_origine")
                .eq("ristorante_id", ristorante_id)
                .gte("data_documento", mese_inizio[:10])
                .execute()
            )
            file_origini = {r["file_origine"] for r in (fd_resp.data or [])}
            fatture_mese = len(file_origini)
        except Exception:
            pass

    # Contatore domande Chat AI di oggi (per il rate limit visibile al cliente).
    # Account multi-sede → pool condiviso del gruppo (stesso contatore in ogni PV e
    # in catena); sede singola → limite del piano sulla sede.
    chat_limite_g, chat_oggi, chat_pool = _chat_quota_view(user, sb, ristorante_id)

    return {
        "email": row.get("email", user.get("email", "")),
        "nome_ristorante": sede.get("nome_ristorante") or row.get("nome_ristorante") or user.get("nome_ristorante", ""),
        "ragione_sociale": sede.get("ragione_sociale") or row.get("ragione_sociale"),
        "partita_iva": sede.get("partita_iva") or row.get("partita_iva"),
        "piano": piano_raw,
        "limite_fatture_mese": limite_fatture,
        "fatture_usate_mese": fatture_mese,
        "chat_usate_oggi": chat_oggi,
        "chat_limite_giorno": chat_limite_g,
        "chat_pool": chat_pool,
        "price_alert_threshold": row.get("price_alert_threshold"),
        "tema": (row.get("tema") or "dark"),
        "membro_dal": row.get("created_at"),
        "ultimo_accesso": row.get("last_login"),
        "is_admin": _is_admin_email(row.get("email")),
    }


class CambioPasswordBody(BaseModel):
    password_attuale: str
    nuova_password: str


@router.post("/api/account/cambia-password", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_cambia_password(
    body: CambioPasswordBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Cambia password con verifica dell'attuale."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    # Carica hash attuale
    row = (
        sb.table("users")
        .select("id, password_hash, email")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    from services.auth_service import verify_and_migrate_password, ph
    if not verify_and_migrate_password(row.data, body.password_attuale):
        raise HTTPException(status_code=400, detail="La password attuale non è corretta")

    if len(body.nuova_password) < 8:
        raise HTTPException(status_code=400, detail="La nuova password deve essere di almeno 8 caratteri")

    new_hash = ph.hash(body.nuova_password)
    sb.table("users").update({
        "password_hash": new_hash,
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", user_id).execute()

    # Cambio password = logout dagli ALTRI dispositivi (la sessione corrente resta
    # attiva, così l'utente non viene sloggato subito dopo il cambio). Best-effort.
    try:
        from services.session_service import revoca_tutte_sessioni
        token_corrente = (authorization or "").split(" ", 1)[-1].strip() or None
        revoca_tutte_sessioni(user_id, sb, escludi_token=token_corrente)
    except Exception:
        pass

    return {"ok": True}


class PreferenzeBody(BaseModel):
    tema: str


@router.post("/api/account/preferenze", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_preferenze(
    body: PreferenzeBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Salva le preferenze di aspetto del cliente (tema). Segue l'account."""
    user = _resolve_user_from_token(authorization)
    tema = (body.tema or "").strip().lower()
    if tema not in ("dark", "light"):
        raise HTTPException(status_code=400, detail="Tema non valido")
    sb = _get_supabase_client()
    sb.table("users").update({"tema": tema}).eq("id", str(user["id"])).execute()
    return {"ok": True, "tema": tema}


class SvuotaDatiBody(BaseModel):
    conferma: str


# Tabelle figlie di `users`/`ristoranti` SENZA FK ON DELETE CASCADE: vanno
# cancellate ESPLICITAMENTE per user_id, altrimenti la sola delete di `ristoranti`
# (che propaga il cascade) le lascerebbe orfane. Verificato sullo schema live.
# NB: `classificazioni_manuali` NON e' qui: nel DB ha righe globali con
# user_id NULL e non va filtrata per user → la lasciamo intatta.
_SVUOTA_TABELLE_NO_CASCADE = [
    ("fatture_documenti", "user_id"),
    ("fatture_queue", "user_id"),
    ("upload_events", "user_id"),
    ("upload_locks", "user_id"),
    ("prodotti_utente", "user_id"),
]


@router.post("/api/account/svuota-dati", tags=["Account"])
def account_svuota_dati(
    body: SvuotaDatiBody,
    admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """ADMIN ONLY — svuota TUTTI i dati dell'account admin che chiama, per
    ripartire da zero nei test. Cancella SOLO i dati del chiamante:

      - l'id target e' SEMPRE admin_user["id"] (dal token verificato), mai un
        parametro esterno → impossibile colpire un altro account;
      - le delete usano .eq("user_id", admin_id) con un id concreto → le righe
        globali con user_id NULL (es. classificazioni_manuali) restano intatte;
      - cancella i ristoranti del chiamante: il loro ON DELETE CASCADE porta via
        fatture, ricavi, margini, tag, scadenziario, notifiche, diario, ecc.

    NON tocca: la memoria AI globale (prodotti_master, memoria_ai_categorie),
    l'account `users`, le sessioni (resti loggato), e nessun dato di altri utenti.
    """
    if (body.conferma or "").strip() != "SVUOTA":
        raise HTTPException(status_code=400, detail="Conferma non valida")

    admin_id = str(admin_user.get("id") or "").strip()
    # Guard difensivo: senza un id concreto NON eseguiamo alcuna delete.
    if not admin_id:
        raise HTTPException(status_code=400, detail="Utente non risolto")

    sb = _get_supabase_client()
    deleted: Dict[str, int] = {}

    # 1) Tabelle senza cascade: delete esplicita per user_id del chiamante.
    for table, col in _SVUOTA_TABELLE_NO_CASCADE:
        try:
            r = sb.table(table).delete().eq(col, admin_id).execute()
            deleted[table] = len(r.data or [])
        except Exception as exc:
            logger.warning("svuota-dati: errore su %s: %s", table, exc)

    # 2) Ristoranti del chiamante → il cascade propaga su tutto il resto.
    try:
        r = sb.table("ristoranti").delete().eq("user_id", admin_id).execute()
        deleted["ristoranti(+cascade)"] = len(r.data or [])
    except Exception as exc:
        logger.warning("svuota-dati: errore su ristoranti: %s", exc)

    logger.warning(
        "SVUOTA_DATI_ADMIN: admin=%s | id=%s | deleted=%s",
        admin_user.get("email"), admin_id, deleted,
    )
    return {"ok": True, "deleted": deleted}


# ─────────────────────────────────────────────────────────────────────────────
# GDPR — diritti dell'interessato self-service (Art. 17 cancellazione, Art. 20 portabilità)
# ─────────────────────────────────────────────────────────────────────────────
# Esercitabili dall'utente stesso dalle Impostazioni, senza passare dall'admin.
# L'id target è SEMPRE quello del token verificato (mai un parametro client), quindi
# un utente può esportare/cancellare SOLO sé stesso.

class EliminaAccountBody(BaseModel):
    conferma: Optional[str] = None


@router.get("/api/account/esporta-dati", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_esporta_dati(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """GDPR Art. 20 (portabilità) — esporta in JSON strutturato tutti i dati
    personali e operativi dell'utente che chiama. Mai password/hash, mai token.
    L'id è quello del token: si esporta solo sé stessi."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()

    export: Dict[str, Any] = {
        "esportato_il": datetime.now(timezone.utc).isoformat(),
        "titolare_trattamento": "Recoma System S.r.l. (P.IVA IT09599210961)",
        "nota": "Export dati personali ai sensi dell'art. 20 GDPR. Non include password (solo hash, non esportabile) né token di sessione.",
    }

    # Profilo (whitelist di campi: niente password_hash, reset_code, token)
    try:
        prof = sb.table("users").select(
            "id,email,nome_ristorante,nome_referente,partita_iva,ragione_sociale,"
            "tema,piano,privacy_accepted_at,created_at"
        ).eq("id", user_id).limit(1).execute()
        export["profilo"] = (prof.data or [None])[0]
    except Exception as exc:
        logger.warning("esporta-dati: profilo: %s", exc)
        export["profilo"] = None

    # Tabelle dati dell'utente. (tabella, colonna_user, etichetta_export)
    _TABELLE = [
        ("ristoranti", "user_id", "ristoranti"),
        ("fatture", "user_id", "fatture"),
        ("margini_mensili", "user_id", "margini_mensili"),
        ("ricavi_giornalieri", "user_id", "ricavi_giornalieri"),
        ("spese_extra", "user_id", "spese_extra"),
        ("ricette", "userid", "ricette"),
        ("ingredienti_utente", "userid", "ingredienti_utente"),
        ("inventario_voci", "user_id", "inventario_voci"),
        ("diario_eventi", "user_id", "diario_eventi"),
        ("turni_personale", "user_id", "turni_personale"),
        ("notification_inbox", "user_id", "notifiche"),
    ]
    for tabella, col, label in _TABELLE:
        try:
            r = sb.table(tabella).select("*").eq(col, user_id).execute()
            export[label] = r.data or []
        except Exception as exc:
            logger.warning("esporta-dati: %s: %s", tabella, exc)
            export[label] = []

    return export


@router.post("/api/account/elimina", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_elimina(
    body: EliminaAccountBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """GDPR Art. 17 (cancellazione) — l'utente elimina il PROPRIO account e tutti i
    dati collegati, in modo permanente. L'id è quello del token verificato: si può
    cancellare solo sé stessi. Gli account admin non sono cancellabili da qui (guard).

    La cancellazione della riga `users` propaga via ON DELETE CASCADE a fatture,
    ristoranti, ricette, sessioni, ricavi, margini, tag, notifiche, ecc. La memoria
    AI globale (prodotti_master) NON è dato personale del singolo e resta.
    """
    if (body.conferma or "").strip().upper() != "ELIMINA":
        raise HTTPException(status_code=400, detail="Scrivi ELIMINA per confermare")

    user = _resolve_user_from_token(authorization)
    user_id = str(user.get("id") or "").strip()
    email = str(user.get("email") or "").lower()
    if not user_id:
        raise HTTPException(status_code=400, detail="Utente non risolto")

    # Guard: gli account admin non si auto-eliminano da questa route (evita lock-out
    # accidentale dell'amministrazione). L'eventuale rimozione admin passa altrove.
    if _is_admin_email(email):
        raise HTTPException(status_code=403, detail="Gli account amministratore non possono essere eliminati da qui")

    sb = _get_supabase_client()
    # La cancellazione di users propaga in cascata (FK ON DELETE CASCADE). Una manciata
    # di tabelle storiche con user_id TEXT/senza FK vengono ripulite esplicitamente prima.
    deleted_extra: Dict[str, int] = {}
    for tabella, col in [("upload_events", "user_id"), ("classificazioni_manuali", "user_id")]:
        try:
            r = sb.table(tabella).delete().eq(col, user_id).execute()
            deleted_extra[tabella] = len(r.data or [])
        except Exception as exc:
            logger.warning("elimina-account: %s: %s", tabella, exc)

    sb.table("users").delete().eq("id", user_id).execute()
    logger.warning("ELIMINA_ACCOUNT_SELF: email=%s | id=%s | extra=%s", email, user_id, deleted_extra)
    return {"ok": True, "messaggio": "Account e dati eliminati in modo permanente."}


# ─────────────────────────────────────────────────────────────────────────────
# SEDI — switch fra ristoranti dello stesso account (clienti multi-sede)
# ─────────────────────────────────────────────────────────────────────────────
# Un cliente con una sola P.IVA può avere più ristoranti (sedi). La sede attiva è
# persistita su users.ultimo_ristorante_id e letta da _resolve_ristorante_id().

@router.get("/api/account/sedi", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_sedi(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Elenca le sedi (ristoranti attivi) dell'account e indica quella attiva.

    La UI mostra il selettore di sede SOLO se len(sedi) > 1.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    resp = (
        sb.table("ristoranti")
        .select("id, nome_ristorante, indirizzo, comune")
        .eq("user_id", user_id)
        .eq("attivo", True)
        .order("created_at")
        .execute()
    )
    sedi = resp.data or []
    attiva = _resolve_ristorante_id(user, sb)

    # nome_gruppo (etichetta account, vive su users): la sidebar lo usa come
    # identità del footer quando il cliente è nel contesto catena.
    nome_gruppo = ""
    try:
        ug = (
            sb.table("users").select("nome_gruppo").eq("id", user_id).single().execute()
        )
        nome_gruppo = str((ug.data or {}).get("nome_gruppo") or "").strip()
    except Exception:
        nome_gruppo = ""

    return {
        "nome_gruppo": nome_gruppo or None,
        "sedi": [
            {
                "id": str(s["id"]),
                "nome": s.get("nome_ristorante") or "Sede",
                "indirizzo": s.get("indirizzo"),
                "comune": s.get("comune"),
                "attiva": str(s["id"]) == str(attiva),
            }
            for s in sedi
        ],
        "ristorante_attivo_id": str(attiva) if attiva else None,
    }


class CambiaSedeBody(BaseModel):
    ristorante_id: str


@router.post("/api/account/cambia-sede", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_cambia_sede(
    body: CambiaSedeBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Imposta la sede attiva dell'account (users.ultimo_ristorante_id).

    Guard: il ristorante deve appartenere al chiamante ed essere attivo, così non
    si può puntare la propria sessione al ristorante di un altro cliente.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    rid = (body.ristorante_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="ristorante_id mancante")

    chk = (
        sb.table("ristoranti")
        .select("id")
        .eq("id", rid)
        .eq("user_id", user_id)
        .eq("attivo", True)
        .execute()
    )
    if not chk.data:
        raise HTTPException(status_code=404, detail="Sede non trovata per questo account")

    sb.table("users").update({"ultimo_ristorante_id": rid}).eq("id", user_id).execute()

    # Invalida la cache di sessione (TTL 30s, keyed sul token): senza questo
    # /api/auth/me e tutti gli endpoint che risolvono la sede attiva
    # continuerebbero a vedere la sede VECCHIA per ~30s dopo lo switch. Era la
    # causa del "devo ricaricare piu' volte e aspettare" segnalato sul selettore
    # sede. Best-effort: se l'invalidazione fallisce, al massimo resta il vecchio
    # comportamento (ritardo fino a 30s), non un errore.
    try:
        token = (authorization or "").split(" ", 1)[1].strip() if authorization else ""
        if token:
            from services.auth_service import _clear_sessione_cache
            _clear_sessione_cache(token)
            # Anche la micro-cache della sede attiva (TTL 5s): senza, lo switch
            # resterebbe stantio fino a 5s sugli endpoint successivi.
            _fw()._invalidate_sede_attiva_cache(token)
    except Exception as exc:
        logger.warning("cambia-sede: invalidazione cache sessione fallita: %s", exc)

    return {"ok": True, "ristorante_attivo_id": rid}
