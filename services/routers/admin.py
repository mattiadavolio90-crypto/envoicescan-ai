"""Router dominio ADMIN — endpoints /api/admin/* (pannello amministratore).

Estratto da fastapi_worker.py. DOMINIO PIU' SENSIBILE: ogni endpoint e' protetto
dal gate `_verify_admin` (doppio guard: X-Worker-Key server-to-server + Bearer
token admin verificato via sessione). Il gate compare in due forme equivalenti,
preservate identiche all'originale:
  - dependencies=[Depends(_verify_admin)] nel decoratore
  - admin_user: dict = Depends(_verify_admin) come parametro funzione

`_verify_admin` e' stato SPOSTATO qui perche' usato esclusivamente dalle route
admin. Tutto il resto resta nel worker ed e' importato:
  - `_admin_emails_set`: usato anche da _run_agent_notturno (worker) → resta.
  - `_log_review_action`: usato anche da _run_agent_notturno (worker) → resta.
  - `_is_admin_email`, `_get_ristorante_id_for_user`, `get_supabase_client`,
    `logger`, `WORKER_DEV_MODE`, `WORKER_SECRET_KEY`, lo stato/funzioni
    dell'agent notturno: condivisi/definiti nel worker → importati.
  - I model Marketplace (Item/List/StatoBody) vivono nella sezione Notifiche del
    worker accanto al lead non-admin → importati.

Path/gate/response/forma dei body invariati rispetto all'originale.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import asyncio

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint admin. Costanti (WORKER_*) e stato mutabile
# (_agent_notturno_state, dict mutato in-place) si leggono via accessor: lo stato
# DEVE essere lo stesso oggetto del worker, che _run_agent_notturno modifica.
import logging
logger = logging.getLogger("fastapi_worker")


def _fw():
    import services.fastapi_worker as fw
    return fw


def get_supabase_client(*args, **kwargs):
    return _fw().get_supabase_client(*args, **kwargs)


def _is_admin_email(*args, **kwargs):
    return _fw()._is_admin_email(*args, **kwargs)


def _admin_emails_set(*args, **kwargs):
    return _fw()._admin_emails_set(*args, **kwargs)


def _get_ristorante_id_for_user(*args, **kwargs):
    return _fw()._get_ristorante_id_for_user(*args, **kwargs)


def _log_review_action(*args, **kwargs):
    return _fw()._log_review_action(*args, **kwargs)


def _agent_notturno_persist(*args, **kwargs):
    return _fw()._agent_notturno_persist(*args, **kwargs)


def _run_agent_notturno(*args, **kwargs):
    return _fw()._run_agent_notturno(*args, **kwargs)


def _agent_state():
    """Stato (dict) dell'agent notturno dal worker: stesso oggetto, mutato in-place."""
    return _fw()._agent_notturno_state


def _worker_dev_mode():
    return _fw().WORKER_DEV_MODE


def _worker_secret_key():
    return _fw().WORKER_SECRET_KEY


# I modelli Marketplace sono del dominio admin e usati a IMPORT-TIME nei decorator
# (response_model / annotazioni body): non possono essere lazy. Erano rimasti in
# fastapi_worker dopo lo split god-file; spostati qui (non usati altrove).
class MarketplaceLeadItem(BaseModel):
    id: str
    servizio_key: str
    servizio_label: str
    messaggio: str
    contatto_email: Optional[str] = None
    contatto_nome: Optional[str] = None
    ristorante_nome: Optional[str] = None
    stato: str
    created_at: Optional[str] = None


class MarketplaceLeadList(BaseModel):
    leads: List[MarketplaceLeadItem]
    nuovi: int


class MarketplaceLeadStatoBody(BaseModel):
    stato: str = Field(..., pattern="^(nuovo|gestito|archiviato)$")


router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN — guard + endpoints /api/admin/*
# Doppio guard: X-Worker-Key (server-to-server) + Bearer token admin
# ═══════════════════════════════════════════════════════════════════════════

def _verify_admin(
    authorization: Optional[str] = Header(None),
    x_worker_key: Optional[str] = Header(None),
) -> dict:
    """Worker key + bearer token → utente admin verificato. Ritorna il dict utente."""
    _dev_mode = _worker_dev_mode()
    _secret = _worker_secret_key()
    if not (_dev_mode and not _secret) and not secrets.compare_digest(x_worker_key or "", _secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token admin mancante")
    token = authorization.split(" ", 1)[1].strip()
    from services.auth_service import verifica_sessione_da_cookie
    user = verifica_sessione_da_cookie(token)
    if not user or not _is_admin_email(user.get("email")):
        raise HTTPException(status_code=403, detail="Accesso riservato agli amministratori")
    return user


# ── Marketplace / Assistenza: coda lead (admin) ──────────────────────────────
# Definiti qui (e non nella sezione Notifiche dove sta crea_marketplace_lead)
# perche' dipendono da _verify_admin, risolto a import-time del decorator.

@router.get(
    "/api/admin/marketplace/leads",
    response_model=MarketplaceLeadList,
    summary="Coda richieste servizi (admin)",
    tags=["Admin"],
)
def admin_marketplace_leads(
    stato: Optional[str] = None,
    admin_user: dict = Depends(_verify_admin),
) -> MarketplaceLeadList:
    sb = get_supabase_client()

    query = (
        sb.table("marketplace_leads")
        .select("id,servizio_key,servizio_label,messaggio,contatto_email,contatto_nome,stato,created_at,ristorante_id")
        .order("created_at", desc=True)
        .limit(200)
    )
    if stato in ("nuovo", "gestito", "archiviato"):
        query = query.eq("stato", stato)

    rows = query.execute().data or []

    # Risolve il nome ristorante per le righe che hanno un ristorante_id.
    rist_ids = list({r["ristorante_id"] for r in rows if r.get("ristorante_id")})
    nomi: Dict[str, str] = {}
    if rist_ids:
        rr = sb.table("ristoranti").select("id,nome").in_("id", rist_ids).execute()
        nomi = {str(x["id"]): x.get("nome") or "" for x in (rr.data or [])}

    leads = [
        MarketplaceLeadItem(
            id=str(r["id"]),
            servizio_key=r.get("servizio_key") or "",
            servizio_label=r.get("servizio_label") or "",
            messaggio=r.get("messaggio") or "",
            contatto_email=r.get("contatto_email"),
            contatto_nome=r.get("contatto_nome"),
            ristorante_nome=nomi.get(str(r.get("ristorante_id"))) if r.get("ristorante_id") else None,
            stato=r.get("stato") or "nuovo",
            created_at=str(r["created_at"]) if r.get("created_at") else None,
        )
        for r in rows
    ]
    nuovi = sum(1 for l in leads if l.stato == "nuovo")
    return MarketplaceLeadList(leads=leads, nuovi=nuovi)


@router.patch(
    "/api/admin/marketplace/leads/{lead_id}",
    summary="Aggiorna stato di una richiesta servizio (admin)",
    tags=["Admin"],
)
def admin_marketplace_lead_stato(
    lead_id: str,
    body: MarketplaceLeadStatoBody,
    admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    sb = get_supabase_client()
    sb.table("marketplace_leads").update({"stato": body.stato}).eq("id", lead_id).execute()
    return {"ok": True}


# ── Overview ────────────────────────────────────────────────────────────────

@router.get("/api/admin/overview", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_overview():
    """KPI flotta: clienti, attivi, fatture mese corrente, costi AI mese.

    Difensivo: ogni sezione è isolata. Non solleva mai 500 — ritorna i dati
    calcolabili e accumula gli errori in `_errors` per diagnosi.
    """
    sb = get_supabase_client()
    errors: list = []

    n_clienti = 0
    n_attivi = 0
    try:
        admin_emails = _admin_emails_set()
        all_users = sb.table("users").select("id,email,attivo").execute().data or []
        clienti = [u for u in all_users if u.get("email", "").lower() not in admin_emails]
        n_clienti = len(clienti)
        n_attivi = sum(1 for u in clienti if u.get("attivo"))
    except Exception as e:
        logger.exception("admin_overview: users query failed")
        errors.append(f"users: {type(e).__name__}: {e}")

    mese_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Conteggio esatto fatture del mese (count, non len cappato a 1000)
    fatture_mese = 0
    try:
        resp = sb.table("fatture_documenti").select("id", count="exact").gte("created_at", mese_start).limit(1).execute()
        fatture_mese = resp.count or 0
    except Exception as e1:
        try:
            resp = sb.table("fatture").select("id", count="exact").gte("created_at", mese_start).is_("deleted_at", "null").limit(1).execute()
            fatture_mese = resp.count or 0
        except Exception as e2:
            logger.exception("admin_overview: fatture count failed")
            errors.append(f"fatture_mese: {type(e2).__name__}: {e2}")

    # Breakdown mensile ultimi 12 mesi
    fatture_per_mese: list = []
    try:
        twelve_ago = (datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=365)).isoformat()
        per_mese: dict = {}
        try:
            rows = sb.table("fatture_documenti").select("data_documento").gte("data_documento", twelve_ago).limit(50000).execute().data or []
        except Exception:
            rows = sb.table("fatture").select("data_documento").gte("data_documento", twelve_ago).is_("deleted_at", "null").limit(50000).execute().data or []
        for r in rows:
            d = r.get("data_documento") or ""
            if len(d) >= 7:
                per_mese[d[:7]] = per_mese.get(d[:7], 0) + 1
        fatture_per_mese = [{"mese": k, "count": v} for k, v in sorted(per_mese.items())]
    except Exception as e:
        logger.exception("admin_overview: breakdown mensile failed")
        errors.append(f"fatture_per_mese: {type(e).__name__}: {e}")

    costi_mese = 0.0
    try:
        costs_resp = sb.rpc("get_ai_costs_summary", {"p_days": 30}).execute()
        costi_mese = sum(float(r.get("ai_cost_total", 0)) for r in (costs_resp.data or []))
    except Exception as e:
        logger.exception("admin_overview: costi AI failed")
        errors.append(f"costi_ai: {type(e).__name__}: {e}")

    return {
        "n_clienti": n_clienti,
        "n_attivi": n_attivi,
        "fatture_mese": fatture_mese,
        "costi_ai_mese": round(costi_mese, 4),
        "fatture_per_mese": fatture_per_mese,
        "_errors": errors,
    }


# ── Lista clienti ────────────────────────────────────────────────────────────

@router.get("/api/admin/clienti", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_lista_clienti():
    """Lista tutti i clienti non-admin con stats aggregate (fatture, ultimo accesso, piano, trial)."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()

    users_resp = sb.table("users").select(
        "id,email,nome_ristorante,ragione_sociale,partita_iva,attivo,piano,piano_inizio_at,created_at,"
        "last_seen_at,trial_active,trial_activated_at,pagine_abilitate"
    ).order("email").execute()
    clienti_raw = [u for u in (users_resp.data or []) if u.get("email", "").lower() not in admin_emails]
    if not clienti_raw:
        return []

    user_ids = [u["id"] for u in clienti_raw]

    # Totale fatture per utente (storico completo, non solo mese corrente)
    n_fatture_map: dict = {}
    try:
        chunk_size = 100
        for i in range(0, len(user_ids), chunk_size):
            chunk = user_ids[i : i + chunk_size]
            resp = sb.table("fatture_documenti").select("user_id").in_("user_id", chunk).limit(500000).execute()
            for r in (resp.data or []):
                uid = r["user_id"]
                n_fatture_map[uid] = n_fatture_map.get(uid, 0) + 1
    except Exception:
        try:
            for i in range(0, len(user_ids), chunk_size):
                chunk = user_ids[i : i + chunk_size]
                resp = sb.table("fatture").select("user_id").in_("user_id", chunk).is_("deleted_at", "null").limit(500000).execute()
                for r in (resp.data or []):
                    uid = r["user_id"]
                    n_fatture_map[uid] = n_fatture_map.get(uid, 0) + 1
        except Exception:
            pass

    # Sedi per utente
    sedi_map: dict = {}
    try:
        for i in range(0, len(user_ids), 100):
            chunk = user_ids[i : i + 100]
            resp = sb.table("ristoranti").select("user_id,id,nome_ristorante,partita_iva,ragione_sociale,attivo").in_("user_id", chunk).execute()
            for r in (resp.data or []):
                sedi_map.setdefault(r["user_id"], []).append(r)
    except Exception:
        pass

    _PIANO_LIMITI_LOCAL = {"free": 50, "base": 50, "plus": 100, "pro": 200}

    result = []
    for u in clienti_raw:
        uid = u["id"]
        piano = (u.get("piano") or "base").lower()
        limite = _PIANO_LIMITI_LOCAL.get(piano, 50)
        sedi = sedi_map.get(uid, [])
        n_fatture = n_fatture_map.get(uid, 0)

        trial_info = None
        if u.get("trial_active") and u.get("trial_activated_at"):
            try:
                activated = datetime.fromisoformat(str(u["trial_activated_at"]).replace("Z", "+00:00"))
                expires_at = activated + timedelta(days=7)
                days_rem = max(0, (expires_at - datetime.now(timezone.utc)).days)
                trial_info = {"active": True, "expires_at": expires_at.isoformat(), "days_remaining": days_rem}
            except Exception:
                trial_info = {"active": True}

        result.append({
            "id": uid,
            "email": u["email"],
            "nome_ristorante": u.get("nome_ristorante") or "",
            "ragione_sociale": u.get("ragione_sociale"),
            "partita_iva": u.get("partita_iva"),
            "attivo": bool(u.get("attivo")),
            "piano": piano,
            "piano_inizio_at": u.get("piano_inizio_at"),
            "limite_fatture_mese": limite,
            "n_fatture": n_fatture,
            "created_at": u.get("created_at"),
            "last_seen_at": u.get("last_seen_at"),
            "trial": trial_info,
            "pagine_abilitate": u.get("pagine_abilitate") or {},
            "n_sedi": len(sedi),
            "sedi": sedi,
        })

    return result


# ── Dettaglio cliente ────────────────────────────────────────────────────────

@router.get("/api/admin/clienti/{cliente_id}", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_dettaglio_cliente(cliente_id: str):
    """Dettaglio completo di un cliente."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()

    resp = sb.table("users").select(
        "id,email,nome_ristorante,ragione_sociale,partita_iva,attivo,piano,created_at,"
        "last_seen_at,trial_active,trial_activated_at,pagine_abilitate,price_alert_threshold"
    ).eq("id", cliente_id).limit(1).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    u = resp.data[0]
    if u.get("email", "").lower() in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi gestire account admin")

    sedi_resp = sb.table("ristoranti").select(
        "id,nome_ristorante,partita_iva,ragione_sociale,attivo"
    ).eq("user_id", cliente_id).execute()
    sedi = sedi_resp.data or []

    piano = (u.get("piano") or "base").lower()
    _PIANO_LIMITI_LOCAL = {"free": 50, "base": 50, "plus": 100, "pro": 200}
    limite = _PIANO_LIMITI_LOCAL.get(piano, 50)

    trial_info = None
    if u.get("trial_active") and u.get("trial_activated_at"):
        try:
            activated = datetime.fromisoformat(str(u["trial_activated_at"]).replace("Z", "+00:00"))
            expires_at = activated + timedelta(days=7)
            days_rem = max(0, (expires_at - datetime.now(timezone.utc)).days)
            trial_info = {"active": True, "expires_at": expires_at.isoformat(), "days_remaining": days_rem}
        except Exception:
            trial_info = {"active": True}

    ristorante_id = _get_ristorante_id_for_user(cliente_id, sb)
    chat_ai_enabled = True
    if ristorante_id:
        try:
            pref_resp = sb.table("assistant_preferences").select("chat_ai_enabled").eq("ristorante_id", ristorante_id).limit(1).execute()
            if pref_resp.data and pref_resp.data[0].get("chat_ai_enabled") is not None:
                chat_ai_enabled = bool(pref_resp.data[0]["chat_ai_enabled"])
        except Exception:
            pass

    return {
        "id": u["id"],
        "email": u["email"],
        "nome_ristorante": u.get("nome_ristorante") or "",
        "ragione_sociale": u.get("ragione_sociale"),
        "partita_iva": u.get("partita_iva"),
        "attivo": bool(u.get("attivo")),
        "piano": piano,
        "limite_fatture_mese": limite,
        "created_at": u.get("created_at"),
        "last_seen_at": u.get("last_seen_at"),
        "price_alert_threshold": u.get("price_alert_threshold"),
        "trial": trial_info,
        "pagine_abilitate": u.get("pagine_abilitate") or {},
        "chat_ai_enabled": chat_ai_enabled,
        "sedi": sedi,
    }


# ── Aggiorna dati cliente ────────────────────────────────────────────────────

class AggiornaClienteBody(BaseModel):
    nome_ristorante: Optional[str] = Field(None, max_length=100)
    partita_iva: Optional[str] = Field(None, max_length=11)
    ragione_sociale: Optional[str] = None
    piano: Optional[str] = Field(None, pattern="^(free|base|plus|pro)$")
    piano_inizio_at: Optional[str] = None


@router.patch("/api/admin/clienti/{cliente_id}", tags=["Admin"])
def admin_aggiorna_cliente(cliente_id: str, body: AggiornaClienteBody, admin_user: dict = Depends(_verify_admin)):
    """Aggiorna nome ristorante, P.IVA, ragione sociale, piano."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    check = sb.table("users").select("email").eq("id", cliente_id).limit(1).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    if check.data[0].get("email", "").lower() in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi modificare account admin")
    upd: dict = {}
    if body.nome_ristorante is not None:
        upd["nome_ristorante"] = body.nome_ristorante.strip()
    if body.partita_iva is not None:
        upd["partita_iva"] = body.partita_iva.strip()
    if body.ragione_sociale is not None:
        upd["ragione_sociale"] = body.ragione_sociale.strip() or None
    if body.piano is not None:
        upd["piano"] = body.piano
    if body.piano_inizio_at is not None:
        upd["piano_inizio_at"] = body.piano_inizio_at if body.piano_inizio_at else None
    if not upd:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    sb.table("users").update(upd).eq("id", cliente_id).execute()
    return {"ok": True, "updated": list(upd.keys())}


# ── Crea cliente ─────────────────────────────────────────────────────────────

class NuovoClienteBody(BaseModel):
    email: str = Field(..., max_length=254)
    nome_ristorante: str = Field(..., max_length=100)
    partita_iva: str = Field(..., max_length=11)
    ragione_sociale: Optional[str] = Field(None, max_length=150)
    piano: str = Field("free", pattern="^(free|base|plus|pro)$")


@router.post("/api/admin/clienti", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_crea_cliente(body: NuovoClienteBody, admin_user: dict = Depends(_verify_admin)):
    """Crea nuovo cliente + ristorante + invia email onboarding via Brevo."""
    from services.auth_service import crea_cliente_con_token
    import html as _html_mod
    import requests as _requests

    successo, messaggio, token = crea_cliente_con_token(
        email=body.email,
        nome_ristorante=body.nome_ristorante,
        partita_iva=body.partita_iva,
        ragione_sociale=body.ragione_sociale,
    )
    if not successo:
        raise HTTPException(status_code=400, detail=messaggio)

    # Aggiorna piano se diverso da default
    if body.piano != "base":
        try:
            sb = get_supabase_client()
            sb.table("users").update({"piano": body.piano}).eq("email", body.email.lower()).execute()
        except Exception:
            pass

    link = f"https://app.oneflux.it/reset-password?token={token}&onboarding=1"
    email_inviata = False
    brevo_key = os.getenv("BREVO_API_KEY", "")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "noreply@oneflux.it")
    sender_name = os.getenv("BREVO_SENDER_NAME", "ONEFLUX")

    if brevo_key:
        try:
            nome_safe = _html_mod.escape(body.nome_ristorante)
            email_safe = _html_mod.escape(body.email)
            piva_safe = _html_mod.escape(body.partita_iva)
            html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#0ea5e9;">Benvenuto in ONEFLUX</h2>
  <p>Ciao <strong>{nome_safe}</strong>,</p>
  <p>Il tuo account è stato creato. Imposta la tua password per iniziare:</p>
  <div style="text-align:center;margin:30px 0;">
    <a href="{link}" style="background:#0ea5e9;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">
      Attiva il mio account
    </a>
  </div>
  <p style="color:#dc2626;"><strong>⚠️ Il link scade tra 24 ore.</strong></p>
  <p><strong>Email di accesso:</strong> {email_safe}<br><strong>P.IVA:</strong> {piva_safe}</p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
  <p style="color:#666;font-size:13px;"><strong>ONEFLUX Team</strong> — md@oneflux.it</p>
</div>"""
            payload = {
                "sender": {"email": sender_email, "name": sender_name},
                "to": [{"email": body.email, "name": nome_safe}],
                "replyTo": {"email": "md@oneflux.it", "name": "Mattia - ONEFLUX"},
                "subject": f"Benvenuto {nome_safe} — Attiva il tuo account ONEFLUX",
                "htmlContent": html_body,
            }
            r = _requests.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                timeout=10,
            )
            email_inviata = r.status_code == 201
        except Exception as exc:
            logger.warning("Errore invio email onboarding: %s", exc)

    logger.info("Admin crea_cliente: %s | admin=%s | email_inviata=%s", body.email, admin_user.get("email"), email_inviata)
    return {"ok": True, "email": body.email, "link_attivazione": link, "email_inviata": email_inviata, "warning": messaggio if "⚠️" in messaggio else None}


# ── Qualità AI — Coda review ──────────────────────────────────────────────────

def _descrizioni_impronta_umana(sb, allowed_ids: list) -> set:
    """Set di descrizioni (normalizzate + raw) classificate da un UMANO.

    Una scelta manuale del cliente/admin e' sacra: NON deve entrare nella coda
    "Da controllare". Si considera umana se:
      - prodotti_utente.classificato_da inizia con 'Manuale' (override locale cliente);
      - prodotti_master.verified=true E classificato_da inizia con
        'Utente'/'Admin'/'Manuale' (correzione manuale promossa a globale).
    Le voci 'auto-review'/'agent-notturno'/'keyword-auto' NON sono umane.
    """
    from utils.text_utils import pulisci_caratteri_corrotti

    def _norm(s: str) -> str:
        return pulisci_caratteri_corrotti(s).strip().upper() if isinstance(s, str) else ""

    umane: set = set()
    _HUMAN_PREFIX = ("MANUALE", "UTENTE", "ADMIN ", "ADMIN:")

    try:
        # Override locali manuali del cliente
        if allowed_ids:
            off = 0
            while True:
                resp = (sb.table("prodotti_utente")
                        .select("descrizione,classificato_da")
                        .in_("user_id", allowed_ids)
                        .range(off, off + 999).execute())
                chunk = resp.data or []
                for r in chunk:
                    cd = str(r.get("classificato_da") or "").upper()
                    if cd.startswith("MANUALE"):
                        umane.add(_norm(r.get("descrizione")))
                if len(chunk) < 1000:
                    break
                off += 1000
    except Exception as e:  # pragma: no cover - difensivo
        logger.warning("coda: load prodotti_utente umani fallito: %s", e)

    try:
        off = 0
        while True:
            resp = (sb.table("prodotti_master")
                    .select("descrizione,classificato_da,verified")
                    .eq("verified", True)
                    .range(off, off + 999).execute())
            chunk = resp.data or []
            for r in chunk:
                cd = str(r.get("classificato_da") or "").upper()
                if cd.startswith(_HUMAN_PREFIX):
                    umane.add(_norm(r.get("descrizione")))
            if len(chunk) < 1000:
                break
            off += 1000
    except Exception as e:  # pragma: no cover - difensivo
        logger.warning("coda: load prodotti_master umani fallito: %s", e)

    umane.discard("")
    return umane


@router.get("/api/admin/qualita-ai/coda", tags=["Admin"])
def admin_qualita_coda(
    cliente_id: Optional[str] = None,
    bucket: Optional[str] = None,
    scope: str = "da_controllare",
    admin_user: dict = Depends(_verify_admin),
):
    """Righe speciali raggruppate per descrizione.

    scope='da_controllare' (default): coda di lavoro, ESCLUDE le righe la cui
        descrizione e' stata classificata a mano da un umano (intoccabili).
    scope='scelte_clienti': SOLO quelle a impronta umana, sola lettura.
    """
    import pandas as pd
    from utils.validation import classify_special_row_vectorized, SPECIAL_ROW_NORMALE
    from utils.text_utils import pulisci_caratteri_corrotti

    sb = get_supabase_client()
    admin_emails = _admin_emails_set()

    allowed_ids: list = []
    nomi_per_user: dict = {}
    if cliente_id:
        allowed_ids = [cliente_id]
    else:
        users_resp = sb.table("users").select("id,email,nome_ristorante").execute()
        for u in (users_resp.data or []):
            if u.get("email", "").lower() in admin_emails:
                continue
            allowed_ids.append(u["id"])
            nomi_per_user[u["id"]] = u.get("nome_ristorante") or u.get("email") or u["id"]
    if not allowed_ids:
        return {"gruppi": [], "stats": {}}

    all_rows: list = []
    page_size = 1000
    offset = 0
    while True:
        q = (sb.table("fatture")
             .select("id,descrizione,categoria,fornitore,prezzo_unitario,totale_riga,quantita,tipo_documento,needs_review,user_id")
             .is_("deleted_at", "null")
             .in_("user_id", allowed_ids)
             .order("id")
             .range(offset, offset + page_size - 1))
        resp = q.execute()
        chunk = resp.data or []
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size

    _empty_stats = {"totale": 0, "diciture": 0, "sconti": 0, "storni": 0, "ambigue": 0, "scelte_clienti": 0}
    if not all_rows:
        return {"gruppi": [], "stats": _empty_stats}

    df = pd.DataFrame(all_rows)
    if "descrizione" in df.columns:
        df["descrizione"] = df["descrizione"].apply(lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x)

    meta = classify_special_row_vectorized(df)
    df["bucket_raw"] = meta["bucket"]
    df["bucket"] = df["bucket_raw"].where(~df["needs_review"].fillna(False).astype(bool), other="da_verificare")
    df = df[df["bucket"] != SPECIAL_ROW_NORMALE].copy()

    # A1: segrega le righe a impronta umana
    umane = _descrizioni_impronta_umana(sb, allowed_ids)
    df["_desc_norm"] = df["descrizione"].apply(lambda s: s.strip().upper() if isinstance(s, str) else "")
    df["_umana"] = df["_desc_norm"].isin(umane)
    n_scelte_clienti = int(df["_umana"].sum())

    if scope == "scelte_clienti":
        df = df[df["_umana"]].copy()
    else:
        df = df[~df["_umana"]].copy()

    if bucket:
        df = df[df["bucket"] == bucket]

    if df.empty:
        return {"gruppi": [], "stats": {**_empty_stats, "scelte_clienti": n_scelte_clienti}}

    stats = {
        "totale": len(df),
        "diciture": int((df["bucket"] == "dicitura").sum()),
        "sconti": int((df["bucket"] == "sconto_omaggio").sum()),
        "storni": int((df["bucket"] == "storno").sum()),
        "ambigue": int((df["bucket"] == "da_verificare").sum()),
        "scelte_clienti": n_scelte_clienti,
    }

    # Raggruppa per descrizione
    grp = df.groupby("descrizione", as_index=False).agg(
        bucket=("bucket", "first"),
        count=("id", "count"),
        ids=("id", list),
        categoria=("categoria", "first"),
        fornitore=("fornitore", "first"),
        prezzo_max=("prezzo_unitario", "max"),
        user_ids=("user_id", list),
    )
    grp["prezzo_max"] = grp["prezzo_max"].fillna(0).round(4)
    grp = grp.sort_values(["bucket", "count"], ascending=[True, False])

    from services.ai_service import applica_regole_categoria_forti, applica_correzioni_dizionario

    # A2: pre-carica i suggerimenti AI gia' preparati (categoria_suggerita su prodotti_master)
    descrizioni_coda = grp["descrizione"].dropna().astype(str).tolist()
    suggerimenti_ai: dict = {}
    try:
        for i in range(0, len(descrizioni_coda), 200):
            chunk = descrizioni_coda[i:i + 200]
            resp = (sb.table("prodotti_master")
                    .select("descrizione,categoria_suggerita,suggerimento_fonte")
                    .in_("descrizione", chunk)
                    .not_.is_("categoria_suggerita", "null")
                    .execute())
            for r in (resp.data or []):
                cs = r.get("categoria_suggerita")
                if cs:
                    suggerimenti_ai[str(r.get("descrizione") or "").strip().upper()] = (
                        cs, r.get("suggerimento_fonte") or "ai")
    except Exception as e:  # pragma: no cover - difensivo
        logger.warning("coda: load suggerimenti AI fallito: %s", e)

    gruppi = grp.to_dict("records")
    for g in gruppi:
        g["ids"] = [int(i) for i in g["ids"]]
        g["count"] = int(g["count"])
        g["prezzo_max"] = float(g["prezzo_max"])

        # Cliente: nome se 1 solo user, altrimenti "N clienti"
        uids = list({str(u) for u in (g.pop("user_ids", None) or [])})
        if len(uids) == 1:
            g["cliente"] = nomi_per_user.get(uids[0]) or (cliente_id and "—") or uids[0]
        else:
            g["cliente"] = f"{len(uids)} clienti"

        # A2: suggerimento a 3 livelli con FONTE esplicita
        desc = str(g.get("descrizione") or "")
        cat_attuale = str(g.get("categoria") or "")
        suggerita = None
        fonte = None
        if desc:
            cat_forte, _ = applica_regole_categoria_forti(desc, "Da Classificare")
            if cat_forte and cat_forte not in ("Da Classificare", cat_attuale):
                suggerita, fonte = cat_forte, "regola"
            if not suggerita:
                cat_dict = applica_correzioni_dizionario(desc, "Da Classificare")
                if cat_dict and cat_dict not in ("Da Classificare", cat_attuale):
                    suggerita, fonte = cat_dict, "memoria"
            if not suggerita:
                ai = suggerimenti_ai.get(desc.strip().upper())
                if ai and ai[0] and ai[0] != cat_attuale:
                    suggerita, fonte = ai[0], (ai[1] or "ai")
        g["categoria_suggerita"] = suggerita
        g["fonte"] = fonte

    return {"gruppi": gruppi, "stats": stats}


class ClassificaBody(BaseModel):
    ids: List[int] = Field(..., min_length=1)
    categoria: str = Field(..., max_length=100)
    salva_memoria: bool = True


@router.post("/api/admin/qualita-ai/coda/classifica", tags=["Admin"])
def admin_qualita_classifica(body: ClassificaBody, admin_user: dict = Depends(_verify_admin)):
    """Classifica un gruppo di righe e opzionalmente salva in memoria globale."""
    from datetime import datetime, timezone
    from config.constants import TUTTE_LE_CATEGORIE

    # Validazione categoria: deve essere reale (o NOTE E DICITURE). Prima si scriveva
    # qualsiasi stringa <=100 char direttamente su fatture.
    _categorie_valide = set(TUTTE_LE_CATEGORIE) | {"📝 NOTE E DICITURE"}
    if body.categoria not in _categorie_valide:
        raise HTTPException(status_code=422, detail=f"Categoria non valida: {body.categoria}")

    sb = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()

    target_ids = list(body.ids)
    # Guardrail dominio #2: NOTE E DICITURE solo su righe a importo 0. Se l'admin
    # assegna NOTE, scriviamola solo sulle righe a importo zero (le altre restano).
    if body.categoria == "📝 NOTE E DICITURE":
        _rows = sb.table("fatture").select("id,totale_riga,prezzo_unitario").in_("id", body.ids).execute()
        def _imp(r):
            t = float(r.get("totale_riga") or 0)
            return t if t != 0 else float(r.get("prezzo_unitario") or 0)
        target_ids = [r["id"] for r in (_rows.data or []) if _imp(r) == 0]
        if not target_ids:
            raise HTTPException(status_code=422, detail="NOTE E DICITURE non applicabile: tutte le righe hanno importo diverso da zero.")

    update_payload = {
        "categoria": body.categoria,
        "needs_review": False,
        "reviewed_at": now,
        "reviewed_by": f"admin:{admin_user.get('email', 'admin')}",
    }
    sb.table("fatture").update(update_payload).in_("id", target_ids).is_("deleted_at", "null").execute()

    # Recupera info per audit log e memoria
    row_resp = sb.table("fatture").select("descrizione,prezzo_unitario,categoria").in_("id", body.ids).limit(1).execute()
    prima_desc = ""
    prima_cat_da = ""
    if row_resp.data:
        prima_desc = row_resp.data[0].get("descrizione", "")
        prima_cat_da = row_resp.data[0].get("categoria") or ""
        if body.salva_memoria:
            prezzo = float(row_resp.data[0].get("prezzo_unitario") or 0)
            if prima_desc and not (body.categoria == "📝 NOTE E DICITURE" and prezzo > 0):
                sb.table("prodotti_master").upsert({
                    "descrizione": prima_desc,
                    "categoria": body.categoria,
                    "confidence": "altissima",
                    "verified": True,
                    "classificato_da": f"admin:{admin_user.get('email', 'admin')}",
                    "ultima_modifica": now,
                }, on_conflict="descrizione").execute()

    _log_review_action(
        sb,
        attore=f"admin:{admin_user.get('email', 'admin')}",
        azione="classifica",
        categoria_a=body.categoria,
        ids_fatture=body.ids,
        descrizione=prima_desc,
        categoria_da=prima_cat_da,
        nota=f"salva_memoria={body.salva_memoria}",
    )

    logger.info("admin_qualita_classifica: %d righe → %s | admin=%s", len(target_ids), body.categoria, admin_user.get("email"))
    return {"ok": True, "righe_aggiornate": len(target_ids)}


class SuggerisciAiBody(BaseModel):
    cliente_id: Optional[str] = None
    ids: Optional[List[int]] = None


def prepara_suggerimenti_ai(sb, allowed_ids: list, only_ids: Optional[list] = None,
                            attore: str = "admin") -> dict:
    """Prepara suggerimenti AI per le righe dubbie SENZA scriverne la categoria.

    Per ogni descrizione 'da_verificare' che NON ha gia' un suggerimento
    deterministico (regola/dizionario), chiama GPT e salva il risultato in
    prodotti_master.categoria_suggerita (+ fonte 'ai', + suggerito_at). NON tocca
    fatture.categoria ne' needs_review: e' solo una proposta da approvare a mano.

    Idempotente: salta descrizioni con un suggerimento gia' fresco (<24h).
    Condivisa fra l'endpoint on-demand (A3) e l'agent notturno (B2).
    """
    import pandas as pd
    from datetime import datetime, timezone, timedelta
    from utils.validation import classify_special_row_vectorized, SPECIAL_ROW_NORMALE
    from utils.text_utils import pulisci_caratteri_corrotti
    from services.ai_service import applica_regole_categoria_forti, applica_correzioni_dizionario, classifica_con_ai

    if not allowed_ids:
        return {"suggerite": 0, "saltate": 0, "errori": 0}

    all_rows: list = []
    page_size = 1000
    offset = 0
    while True:
        q = (sb.table("fatture")
             .select("id,descrizione,categoria,fornitore,prezzo_unitario,totale_riga,quantita,tipo_documento,needs_review,user_id")
             .is_("deleted_at", "null")
             .in_("user_id", allowed_ids)
             .order("id")
             .range(offset, offset + page_size - 1))
        if only_ids:
            q = q.in_("id", only_ids)
        resp = q.execute()
        chunk = resp.data or []
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size

    if not all_rows:
        return {"suggerite": 0, "saltate": 0, "errori": 0}

    df = pd.DataFrame(all_rows)
    df["descrizione"] = df["descrizione"].apply(lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x)
    meta = classify_special_row_vectorized(df)
    df["bucket_raw"] = meta["bucket"]
    df["bucket"] = df["bucket_raw"].where(~df["needs_review"].fillna(False).astype(bool), other="da_verificare")
    # Solo righe ambigue reali (da_verificare). Diciture/sconti/storni hanno gia'
    # il loro percorso (auto-review) e non vanno mandati a GPT.
    df = df[df["bucket"] == "da_verificare"].copy()
    if df.empty:
        return {"suggerite": 0, "saltate": 0, "errori": 0}

    # Una riga rappresentativa per descrizione (fornitore + categoria attuale)
    grp = df.groupby("descrizione", as_index=False).agg(
        categoria=("categoria", "first"),
        fornitore=("fornitore", "first"),
    )

    # Escludi cio' che ha gia' una soluzione deterministica (regola/dizionario):
    # quelle non hanno bisogno dell'AI, la coda le suggerisce gia'.
    da_chiedere: list = []
    fornitori: list = []
    saltate = 0
    for _, r in grp.iterrows():
        desc = str(r.get("descrizione") or "").strip()
        if not desc:
            continue
        cat_att = str(r.get("categoria") or "")
        cat_forte, _m = applica_regole_categoria_forti(desc, "Da Classificare")
        if cat_forte and cat_forte not in ("Da Classificare", cat_att):
            saltate += 1
            continue
        cat_dict = applica_correzioni_dizionario(desc, "Da Classificare")
        if cat_dict and cat_dict not in ("Da Classificare", cat_att):
            saltate += 1
            continue
        da_chiedere.append(desc)
        fornitori.append(str(r.get("fornitore") or ""))

    if not da_chiedere:
        return {"suggerite": 0, "saltate": saltate, "errori": 0}

    # Idempotenza: salta descrizioni gia' suggerite di fresco (<24h)
    fresca_soglia = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    gia_fresche: set = set()
    try:
        for i in range(0, len(da_chiedere), 200):
            chunk = da_chiedere[i:i + 200]
            resp = (sb.table("prodotti_master")
                    .select("descrizione,suggerito_at")
                    .in_("descrizione", chunk)
                    .not_.is_("categoria_suggerita", "null")
                    .gte("suggerito_at", fresca_soglia)
                    .execute())
            for r in (resp.data or []):
                gia_fresche.add(str(r.get("descrizione") or ""))
    except Exception as e:  # pragma: no cover - difensivo
        logger.warning("suggerisci-ai: check idempotenza fallito: %s", e)

    pendenti = [(d, f) for d, f in zip(da_chiedere, fornitori) if d not in gia_fresche]
    saltate += len(da_chiedere) - len(pendenti)
    if not pendenti:
        return {"suggerite": 0, "saltate": saltate, "errori": 0}

    descs = [d for d, _ in pendenti]
    forns = [f for _, f in pendenti]

    suggerite = 0
    errori = 0
    now = datetime.now(timezone.utc).isoformat()
    BATCH = 40
    from config.constants import TUTTE_LE_CATEGORIE
    _categorie_valide = set(TUTTE_LE_CATEGORIE) | {"📝 NOTE E DICITURE"}

    for i in range(0, len(descs), BATCH):
        chunk_d = descs[i:i + BATCH]
        chunk_f = forns[i:i + BATCH]
        try:
            categorie, _conf = classifica_con_ai(
                lista_descrizioni=chunk_d,
                lista_fornitori=chunk_f,
                return_confidenze=True,
            )
        except Exception as exc:
            errori += len(chunk_d)
            logger.warning("suggerisci-ai batch %d-%d errore GPT: %s", i, i + BATCH, exc)
            continue

        for desc, cat in zip(chunk_d, categorie):
            cat = (cat or "").strip()
            # Non salvare suggerimenti inutili: fallback, vuoti o categorie non valide.
            if not cat or cat in ("Da Classificare", "Da Clasificare") or cat not in _categorie_valide:
                continue
            try:
                sb.table("prodotti_master").upsert({
                    "descrizione": desc,
                    "categoria_suggerita": cat,
                    "suggerimento_fonte": "ai",
                    "suggerito_at": now,
                }, on_conflict="descrizione").execute()
                suggerite += 1
            except Exception as exc:
                errori += 1
                logger.warning("suggerisci-ai upsert '%s' errore: %s", desc[:40], exc)

    logger.info("prepara_suggerimenti_ai: suggerite=%d saltate=%d errori=%d | attore=%s",
                suggerite, saltate, errori, attore)
    return {"suggerite": suggerite, "saltate": saltate, "errori": errori}


@router.post("/api/admin/qualita-ai/coda/suggerisci-ai", tags=["Admin"])
def admin_qualita_suggerisci_ai(body: SuggerisciAiBody, admin_user: dict = Depends(_verify_admin)):
    """Prepara suggerimenti AI per le righe dubbie (NON scrive la categoria)."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()

    if body.cliente_id:
        allowed_ids = [body.cliente_id]
    else:
        users_resp = sb.table("users").select("id,email").execute()
        allowed_ids = [u["id"] for u in (users_resp.data or []) if u.get("email", "").lower() not in admin_emails]

    res = prepara_suggerimenti_ai(
        sb, allowed_ids, only_ids=body.ids,
        attore=f"admin:{admin_user.get('email', 'admin')}",
    )
    return {"ok": True, **res}


class AutoReviewBody(BaseModel):
    cliente_id: Optional[str] = None


@router.post("/api/admin/qualita-ai/coda/auto-review", tags=["Admin"])
def admin_qualita_auto_review(body: AutoReviewBody, admin_user: dict = Depends(_verify_admin)):
    """Auto-classifica diciture sicure e sconti/omaggi in batch."""
    import pandas as pd
    from utils.validation import classify_special_row_vectorized, SPECIAL_ROW_NORMALE, SPECIAL_ROW_DICITURA, SPECIAL_ROW_SCONTO_OMAGGIO
    from utils.text_utils import pulisci_caratteri_corrotti
    from utils.validation import is_dicitura_sicura, is_sconto_omaggio_sicuro
    from datetime import datetime, timezone

    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    now = datetime.now(timezone.utc).isoformat()

    if body.cliente_id:
        allowed_ids = [body.cliente_id]
    else:
        users_resp = sb.table("users").select("id,email").execute()
        allowed_ids = [u["id"] for u in (users_resp.data or []) if u.get("email", "").lower() not in admin_emails]

    all_rows: list = []
    page_size = 1000
    offset = 0
    while True:
        q = (sb.table("fatture")
             .select("id,descrizione,categoria,prezzo_unitario,totale_riga,quantita,tipo_documento,needs_review")
             .is_("deleted_at", "null")
             .in_("user_id", allowed_ids)
             .order("id")
             .range(offset, offset + page_size - 1))
        resp = q.execute()
        chunk = resp.data or []
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size

    if not all_rows:
        return {"ok": True, "classificate": 0, "salvate_memoria": 0, "errori": 0}

    df = pd.DataFrame(all_rows)
    df["descrizione"] = df["descrizione"].apply(lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x)
    meta = classify_special_row_vectorized(df)
    df["bucket"] = meta["bucket"]
    df = df[df["bucket"] != SPECIAL_ROW_NORMALE].copy()

    auto_diciture = df[df["bucket"] == SPECIAL_ROW_DICITURA]["descrizione"].dropna().unique().tolist()
    auto_sconti = df[df["bucket"] == SPECIAL_ROW_SCONTO_OMAGGIO]["descrizione"].dropna().unique().tolist()

    classificate = 0
    salvate = 0
    errori = 0

    for desc in auto_diciture:
        try:
            prezzo_max = float(df[df["descrizione"] == desc]["prezzo_unitario"].max() or 0)
            if prezzo_max > 0:
                errori += 1
                continue
            ids = df[df["descrizione"] == desc]["id"].tolist()
            cat_da = str(df[df["descrizione"] == desc]["categoria"].iloc[0] or "")
            sb.table("fatture").update({
                "categoria": "📝 NOTE E DICITURE",
                "needs_review": False,
                "reviewed_at": now,
                "reviewed_by": "auto-review",
            }).in_("id", ids).is_("deleted_at", "null").execute()
            sb.table("prodotti_master").upsert({
                "descrizione": desc,
                "categoria": "📝 NOTE E DICITURE",
                "confidence": "altissima",
                "verified": True,
                "classificato_da": "auto-review",
                "ultima_modifica": now,
            }, on_conflict="descrizione").execute()
            _log_review_action(sb, "auto-review", "auto_review", "📝 NOTE E DICITURE", ids, desc, cat_da, "bucket=dicitura")
            classificate += len(ids)
            salvate += 1
        except Exception as exc:
            errori += 1
            logger.warning("auto-review dicitura error '%s': %s", desc[:40], exc)

    for desc in auto_sconti:
        try:
            row = df[df["descrizione"] == desc].iloc[0]
            cat = row.get("categoria") or ""
            if not cat or cat == "Da Clasificare":
                continue
            ids = df[df["descrizione"] == desc]["id"].tolist()
            sb.table("fatture").update({
                "needs_review": False,
                "reviewed_at": now,
                "reviewed_by": "auto-review",
            }).in_("id", ids).is_("deleted_at", "null").execute()
            sb.table("prodotti_master").upsert({
                "descrizione": desc,
                "categoria": cat,
                "confidence": "alta",
                "verified": True,
                "classificato_da": "auto-review",
                "ultima_modifica": now,
            }, on_conflict="descrizione").execute()
            _log_review_action(sb, "auto-review", "auto_review", cat, ids, desc, cat, "bucket=sconto_omaggio")
            classificate += len(ids)
            salvate += 1
        except Exception as exc:
            errori += 1
            logger.warning("auto-review sconto error '%s': %s", desc[:40], exc)

    logger.info("admin_auto_review: classificate=%d, salvate=%d, errori=%d | admin=%s", classificate, salvate, errori, admin_user.get("email"))
    return {"ok": True, "classificate": classificate, "salvate_memoria": salvate, "errori": errori}


# ── Qualità AI — Memoria globale ─────────────────────────────────────────────

@router.get("/api/admin/qualita-ai/memoria", tags=["Admin"])
def admin_qualita_memoria(
    search: Optional[str] = None,
    stato: str = "tutti",
    page: int = 1,
    per_page: int = 100,
    admin_user: dict = Depends(_verify_admin),
):
    """Prodotti master con filtri. stato: tutti|verified|non_verified|sospette."""
    from utils.text_utils import pulisci_caratteri_corrotti, escape_ilike

    sb = get_supabase_client()
    per_page = min(per_page, 500)
    offset = (page - 1) * per_page
    # Escape % e _ nel testo di ricerca: l'utente si aspetta match letterale, non wildcard.
    search_pattern = f"%{escape_ilike(search)}%" if search else None

    if stato == "sospette":
        # Carica tutto e filtra lato Python (servono i suggerimenti AI)
        from services.ai_service import applica_correzioni_dizionario, applica_regole_categoria_forti
        all_rows: list = []
        pg_offset = 0
        while True:
            resp = sb.table("prodotti_master").select("id,descrizione,categoria,volte_visto,verified,classificato_da").order("id").range(pg_offset, pg_offset + 999).execute()
            chunk = resp.data or []
            if not chunk:
                break
            all_rows.extend(chunk)
            if len(chunk) < 1000:
                break
            pg_offset += 1000

        sospette = []
        for row in all_rows:
            if row.get("verified"):
                continue
            desc = row.get("descrizione") or ""
            cat_attuale = (row.get("categoria") or "Da Classificare").strip()
            cat_keyword = applica_correzioni_dizionario(desc, "Da Classificare")
            cat_suggerita, motivo = applica_regole_categoria_forti(desc, cat_keyword)
            if not cat_suggerita or cat_suggerita == "Da Classificare" or cat_suggerita == cat_attuale:
                continue
            sospette.append({**row, "categoria_suggerita": cat_suggerita, "motivo": motivo or ""})

        total = len(sospette)
        rows = sospette[offset: offset + per_page]
    else:
        q = sb.table("prodotti_master").select("id,descrizione,categoria,volte_visto,verified,classificato_da,ultima_modifica")
        if stato == "verified":
            q = q.eq("verified", True)
        elif stato == "non_verified":
            q = q.eq("verified", False)
        if search_pattern:
            q = q.ilike("descrizione", search_pattern)
        count_resp = sb.table("prodotti_master").select("id", count="exact")
        if stato == "verified":
            count_resp = count_resp.eq("verified", True)
        elif stato == "non_verified":
            count_resp = count_resp.eq("verified", False)
        if search_pattern:
            count_resp = count_resp.ilike("descrizione", search_pattern)
        try:
            count_r = count_resp.execute()
            total = count_r.count or 0
        except Exception:
            total = 0

        resp = q.order("volte_visto", desc=True).range(offset, offset + per_page - 1).execute()
        rows = resp.data or []
        for r in rows:
            if "descrizione" in r and isinstance(r["descrizione"], str):
                r["descrizione"] = pulisci_caratteri_corrotti(r["descrizione"])

    return {"rows": rows, "total": total, "page": page, "per_page": per_page}


class MemoriaUpdateBody(BaseModel):
    categoria: Optional[str] = None
    verified: Optional[bool] = None


@router.patch("/api/admin/qualita-ai/memoria/{prod_id}", tags=["Admin"])
def admin_qualita_memoria_update(
    prod_id: str,
    body: MemoriaUpdateBody,
    admin_user: dict = Depends(_verify_admin),
):
    from datetime import datetime, timezone
    sb = get_supabase_client()
    update: dict = {"ultima_modifica": datetime.now(timezone.utc).isoformat()}
    if body.categoria is not None:
        update["categoria"] = body.categoria
        update["verified"] = True
    if body.verified is not None:
        update["verified"] = body.verified
    sb.table("prodotti_master").update(update).eq("id", prod_id).execute()
    logger.info("admin_memoria_update: id=%s | admin=%s", prod_id, admin_user.get("email"))
    return {"ok": True}


@router.delete("/api/admin/qualita-ai/memoria/{prod_id}", tags=["Admin"])
def admin_qualita_memoria_delete(prod_id: str, admin_user: dict = Depends(_verify_admin)):
    sb = get_supabase_client()
    sb.table("prodotti_master").delete().eq("id", prod_id).execute()
    logger.info("admin_memoria_delete: id=%s | admin=%s", prod_id, admin_user.get("email"))
    return {"ok": True}


# ── Qualità AI — Conflitti memoria ───────────────────────────────────────────

@router.get("/api/admin/qualita-ai/conflitti", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_qualita_conflitti():
    """Descrizioni dove prodotti_utente ha categoria diversa da prodotti_master."""
    from utils.text_utils import pulisci_caratteri_corrotti

    sb = get_supabase_client()
    global_rows: list = []
    local_rows: list = []
    pg = 0
    while True:
        resp = sb.table("prodotti_master").select("id,descrizione,categoria,volte_visto").order("id").range(pg, pg + 999).execute()
        chunk = resp.data or []
        if not chunk:
            break
        global_rows.extend(chunk)
        if len(chunk) < 1000:
            break
        pg += 1000

    pg = 0
    while True:
        resp = sb.table("prodotti_utente").select("id,descrizione,categoria,volte_visto,user_id,classificato_da").order("id").range(pg, pg + 999).execute()
        chunk = resp.data or []
        if not chunk:
            break
        local_rows.extend(chunk)
        if len(chunk) < 1000:
            break
        pg += 1000

    if not global_rows or not local_rows:
        return []

    users_resp = sb.table("users").select("id,email,nome_ristorante").execute()
    users_map = {r["id"]: {"email": r.get("email") or "", "nome": r.get("nome_ristorante") or ""} for r in (users_resp.data or [])}

    global_map = {r["descrizione"]: r for r in global_rows if r.get("descrizione")}
    conflitti = []
    for local in local_rows:
        desc = local.get("descrizione")
        if not desc:
            continue
        if "eccezione locale accettata" in (local.get("classificato_da") or ""):
            continue
        glb = global_map.get(desc)
        if not glb:
            continue
        if local.get("categoria") == glb.get("categoria"):
            continue
        uid = local.get("user_id") or ""
        conflitti.append({
            "local_id": local["id"],
            "global_id": glb["id"],
            "descrizione": pulisci_caratteri_corrotti(desc),
            "categoria_locale": local.get("categoria"),
            "categoria_globale": glb.get("categoria"),
            "email_cliente": users_map.get(uid, {}).get("email", "—"),
            "nome_cliente": users_map.get(uid, {}).get("nome", "—"),
            "volte_locale": int(local.get("volte_visto") or 0),
            "volte_globale": int(glb.get("volte_visto") or 0),
        })

    conflitti.sort(key=lambda x: x["volte_locale"], reverse=True)
    return conflitti[:500]


class RisolviConflittoBody(BaseModel):
    local_id: str
    azione: str = Field(..., pattern="^(promuovi|ignora)$")


@router.post("/api/admin/qualita-ai/conflitti/risolvi", tags=["Admin"])
def admin_qualita_risolvi_conflitto(body: RisolviConflittoBody, admin_user: dict = Depends(_verify_admin)):
    from datetime import datetime, timezone
    sb = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()

    local_resp = sb.table("prodotti_utente").select("descrizione,categoria").eq("id", body.local_id).limit(1).execute()
    if not local_resp.data:
        raise HTTPException(status_code=404, detail="Record locale non trovato")
    local = local_resp.data[0]

    if body.azione == "promuovi":
        sb.table("prodotti_master").upsert({
            "descrizione": local["descrizione"],
            "categoria": local["categoria"],
            "verified": True,
            "classificato_da": f"admin:{admin_user.get('email', 'admin')}",
            "ultima_modifica": now,
        }, on_conflict="descrizione").execute()
    else:
        sb.table("prodotti_utente").update({
            "classificato_da": "eccezione locale accettata",
        }).eq("id", body.local_id).execute()

    _log_review_action(
        sb,
        attore=f"admin:{admin_user.get('email', 'admin')}",
        azione="risolvi_conflitto",
        categoria_a=local["categoria"],
        ids_fatture=[],
        descrizione=local.get("descrizione", ""),
        nota=f"azione={body.azione} local_id={body.local_id}",
    )

    logger.info("admin_risolvi_conflitto: local_id=%s azione=%s | admin=%s", body.local_id, body.azione, admin_user.get("email"))
    return {"ok": True}


# ── Qualità AI — Audit log ────────────────────────────────────────────────────

@router.get("/api/admin/qualita-ai/audit", tags=["Admin"])
def admin_qualita_audit(
    page: int = 1,
    per_page: int = 50,
    attore: Optional[str] = None,
    solo_annullabili: bool = False,
    admin_user: dict = Depends(_verify_admin),
):
    """Feed audit log azioni AI/admin su classificazioni."""
    per_page = min(per_page, 200)
    offset = (page - 1) * per_page
    sb = get_supabase_client()

    q = sb.table("ai_review_log").select("*")
    if attore:
        q = q.eq("attore", attore)
    if solo_annullabili:
        q = q.is_("annullato_at", "null")

    count_q = sb.table("ai_review_log").select("id", count="exact")
    if attore:
        count_q = count_q.eq("attore", attore)
    if solo_annullabili:
        count_q = count_q.is_("annullato_at", "null")
    try:
        total = count_q.execute().count or 0
    except Exception:
        total = 0

    rows = q.order("created_at", desc=True).range(offset, offset + per_page - 1).execute().data or []
    return {"rows": rows, "total": total, "page": page, "per_page": per_page}


class AnnullaBody(BaseModel):
    log_id: int


@router.post("/api/admin/qualita-ai/audit/annulla", tags=["Admin"])
def admin_qualita_audit_annulla(body: AnnullaBody, admin_user: dict = Depends(_verify_admin)):
    """Annulla un'azione loggata: ripristina categoria_da sulle righe fattura."""
    from datetime import datetime, timezone
    sb = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()

    log_resp = sb.table("ai_review_log").select("*").eq("id", body.log_id).limit(1).execute()
    if not log_resp.data:
        raise HTTPException(status_code=404, detail="Azione non trovata")
    entry = log_resp.data[0]

    if entry.get("annullato_at"):
        raise HTTPException(status_code=409, detail="Azione già annullata")

    categoria_da = entry.get("categoria_da") or ""
    if not categoria_da:
        raise HTTPException(status_code=400, detail="Nessuna categoria precedente salvata, impossibile annullare")

    ids = [int(i) for i in (entry.get("ids_fatture") or [])]
    if ids:
        sb.table("fatture").update({
            "categoria": categoria_da,
            "needs_review": True,
            "reviewed_at": None,
            "reviewed_by": None,
        }).in_("id", ids).is_("deleted_at", "null").execute()

    sb.table("ai_review_log").update({
        "annullato_at": now,
        "annullato_da": f"admin:{admin_user.get('email', 'admin')}",
    }).eq("id", body.log_id).execute()

    _log_review_action(
        sb,
        attore=f"admin:{admin_user.get('email', 'admin')}",
        azione="annulla",
        categoria_a=categoria_da,
        ids_fatture=ids,
        descrizione=entry.get("descrizione", ""),
        categoria_da=entry.get("categoria_a", ""),
        nota=f"annulla log_id={body.log_id}",
    )

    logger.info("admin_audit_annulla: log_id=%d righe=%d | admin=%s", body.log_id, len(ids), admin_user.get("email"))
    return {"ok": True, "righe_ripristinate": len(ids)}


# ── Sistema/Salute — Costi AI ─────────────────────────────────────────────────

@router.get("/api/admin/sistema/costi-ai", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_sistema_costi_ai(days: int = 30):
    from datetime import datetime, timezone
    sb = get_supabase_client()

    summary_args = {"p_days": days} if days else {}
    timeseries_args = {"p_days": days or 30}
    recent_args = {"p_days": days or 30, "p_limit": 50}

    try:
        summary = sb.rpc("get_ai_costs_summary", summary_args).execute().data or []
    except Exception:
        summary = []
    try:
        timeseries = sb.rpc("get_ai_costs_timeseries", timeseries_args).execute().data or []
    except Exception:
        timeseries = []
    try:
        recent = sb.rpc("get_ai_recent_operations", recent_args).execute().data or []
    except Exception:
        recent = []

    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
    try:
        vision_resp = (sb.table("ai_usage_events")
                       .select("ristorante_id,operation_type")
                       .gte("created_at", today_start)
                       .in_("operation_type", ["pdf", "vision"])
                       .execute())
        vision_oggi_by_rist: dict = {}
        for r in (vision_resp.data or []):
            rid = r.get("ristorante_id") or ""
            vision_oggi_by_rist[rid] = vision_oggi_by_rist.get(rid, 0) + 1
    except Exception:
        vision_oggi_by_rist = {}

    return {
        "summary": summary,
        "timeseries": timeseries,
        "recent": recent,
        "vision_oggi_by_ristorante": vision_oggi_by_rist,
    }


# ── Sistema/Salute — Integrità DB ─────────────────────────────────────────────

# ── Sistema/Salute — Retention ───────────────────────────────────────────────

@router.get("/api/admin/sistema/retention", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_sistema_retention():
    from services.db_service import get_retention_last_status
    status = get_retention_last_status(get_supabase_client())
    return status


# ── Sistema/Salute — Import ricavi problematici ──────────────────────────────

@router.get("/api/admin/sistema/ricavi-import", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_sistema_ricavi_import():
    """Record di import ricavi (ricavi_email_queue) in stato problematico.

    Sola lettura: mostra all'admin gli import bloccati (mittente non mappato,
    in retry o morti dopo i tentativi) che altrimenti restano solo nei log del
    worker. Coda pulita → items vuoto, counts a zero (empty-state lato UI).
    """
    sb = get_supabase_client()
    problem_states = ["unknown_sender", "failed", "dead"]
    try:
        resp = (
            sb.table("ricavi_email_queue")
            .select(
                "id,status,email_sender,email_subject,attachment_name,"
                "created_at,attempt_count,max_attempts,last_error,processed_at"
            )
            .in_("status", problem_states)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        items = resp.data or []
    except Exception as exc:
        logger.error("admin ricavi-import: query fallita: %s", exc)
        items = []

    counts = {s: 0 for s in problem_states}
    for it in items:
        st = it.get("status")
        if st in counts:
            counts[st] += 1

    return {"items": items, "counts": counts}


# ── Sistema/Salute — Salute import ricavi PER RISTORANTE ─────────────────────

def _buchi_serie(date_set: set, first_iso: Optional[str], last_iso: Optional[str]) -> List[str]:
    """Giorni mancanti (ISO) tra first_iso e last_iso inclusi, assenti da date_set.

    Estremi inclusi: se manca anche un estremo (non dovrebbe, sono min/max del set)
    verrebbe comunque elencato. date_set contiene solo giorni con dati.
    """
    from datetime import date as _date
    if not first_iso or not last_iso:
        return []
    try:
        cur = _date.fromisoformat(first_iso)
        end = _date.fromisoformat(last_iso)
    except ValueError:
        return []
    out: List[str] = []
    while cur <= end:
        iso = cur.isoformat()
        if iso not in date_set:
            out.append(iso)
        cur += timedelta(days=1)
    return out


def _classifica_salute_ricavi(giorni_silenzio: Optional[int], n_buchi: int,
                              coda_problemi: int, silenzio_giorni: int) -> str:
    """Stato salute import di un ristorante a partire dai 3 segnali.

    - critico: nessun dato (silenzio None), silenzio oltre soglia, o coda bloccata.
    - warning: serie con buchi ma silenzio entro soglia e coda pulita.
    - ok: aggiornato, nessun buco, coda pulita.
    """
    silenzio_critico = giorni_silenzio is None or giorni_silenzio > silenzio_giorni
    if silenzio_critico or coda_problemi > 0:
        return "critico"
    if n_buchi > 0:
        return "warning"
    return "ok"


@router.get("/api/admin/sistema/ricavi-salute", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_sistema_ricavi_salute(silenzio_giorni: int = 2):
    """Salute dell'import ricavi aggregata PER RISTORANTE.

    A differenza di /ricavi-import (che elenca i singoli record bloccati in coda),
    qui ogni ristorante che usa l'import via email ha UNA riga di stato che combina
    tre segnali:
      - silenzio: nessun ricavo da > silenzio_giorni giorni (mail mai arrivata o
        non processata) — è il caso che lascia la coda pulita e passa inosservato;
      - buchi: giorni mancanti nella serie recente fino all'ultimo dato (il file è
        arrivato ma non conteneva tutti i giorni);
      - coda: record failed/dead/unknown_sender di quel ristorante.

    "Usa l'import email" = ha almeno un mittente attivo in ricavi_email_sender_map.
    Gli altri ristoranti non vengono valutati per silenzio/buchi (inserimento
    manuale → falsi allarmi). Sola lettura.
    """
    from datetime import date as _date

    sb = get_supabase_client()
    silenzio_giorni = max(1, min(30, int(silenzio_giorni or 2)))
    oggi = datetime.now(timezone.utc).date()
    # Finestra di analisi buchi: ultime 2 settimane fino all'ultimo dato noto.
    finestra_da = (oggi - timedelta(days=14)).isoformat()
    problem_states = ["unknown_sender", "failed", "dead"]

    # ── Ristoranti che usano l'import email (mittente attivo) ─────────────────
    try:
        sender_rows = (
            sb.table("ricavi_email_sender_map")
            .select("ristorante_id")
            .eq("attivo", True)
            .execute()
        ).data or []
    except Exception as exc:
        logger.error("admin ricavi-salute: sender_map fallita: %s", exc)
        sender_rows = []

    email_rist_ids = {str(r["ristorante_id"]) for r in sender_rows if r.get("ristorante_id")}
    if not email_rist_ids:
        return {"items": [], "counts": {"ok": 0, "warning": 0, "critico": 0}, "silenzio_giorni": silenzio_giorni}

    # Nomi ristoranti
    nomi: Dict[str, str] = {}
    try:
        rist_rows = (
            sb.table("ristoranti")
            .select("id,nome_ristorante")
            .in_("id", list(email_rist_ids))
            .execute()
        ).data or []
        nomi = {str(r["id"]): (r.get("nome_ristorante") or "—") for r in rist_rows}
    except Exception as exc:
        logger.error("admin ricavi-salute: nomi ristoranti falliti: %s", exc)

    # ── Ricavi recenti per ristorante (date) ─────────────────────────────────
    date_per_rist: Dict[str, set] = {rid: set() for rid in email_rist_ids}
    try:
        ricavi_rows = (
            sb.table("ricavi_giornalieri")
            .select("ristorante_id,data")
            .in_("ristorante_id", list(email_rist_ids))
            .gte("data", finestra_da)
            .execute()
        ).data or []
        for r in ricavi_rows:
            rid = str(r.get("ristorante_id"))
            d = str(r.get("data") or "")[:10]
            if rid in date_per_rist and d:
                date_per_rist[rid].add(d)
    except Exception as exc:
        logger.error("admin ricavi-salute: ricavi_giornalieri falliti: %s", exc)

    # ── Coda problematica per ristorante ─────────────────────────────────────
    coda_per_rist: Dict[str, int] = {rid: 0 for rid in email_rist_ids}
    try:
        coda_rows = (
            sb.table("ricavi_email_queue")
            .select("ristorante_id,status")
            .in_("ristorante_id", list(email_rist_ids))
            .in_("status", problem_states)
            .execute()
        ).data or []
        for r in coda_rows:
            rid = str(r.get("ristorante_id"))
            if rid in coda_per_rist:
                coda_per_rist[rid] += 1
    except Exception as exc:
        logger.error("admin ricavi-salute: coda per ristorante fallita: %s", exc)

    def _parse_iso(s: str):
        try:
            return _date.fromisoformat(s)
        except ValueError:
            return None

    items = []
    counts = {"ok": 0, "warning": 0, "critico": 0}

    for rid in sorted(email_rist_ids, key=lambda x: nomi.get(x, "")):
        date_set = date_per_rist.get(rid, set())
        last_data = max(date_set) if date_set else None
        last_dt = _parse_iso(last_data) if last_data else None
        giorni_silenzio = (oggi - last_dt).days if last_dt else None

        # Buchi: giorni mancanti tra il primo dato della finestra e l'ultimo.
        buchi = _buchi_serie(date_set, min(date_set) if date_set else None, last_data)
        coda_problemi = coda_per_rist.get(rid, 0)
        stato = _classifica_salute_ricavi(giorni_silenzio, len(buchi), coda_problemi, silenzio_giorni)
        counts[stato] += 1

        items.append({
            "ristorante_id": rid,
            "nome_ristorante": nomi.get(rid, "—"),
            "stato": stato,
            "ultima_data": last_data,
            "giorni_silenzio": giorni_silenzio,
            "buchi": buchi,
            "n_buchi": len(buchi),
            "coda_problemi": coda_problemi,
        })

    # Ristoranti problematici in cima
    ordine = {"critico": 0, "warning": 1, "ok": 2}
    items.sort(key=lambda it: (ordine.get(it["stato"], 9), it["nome_ristorante"]))

    return {"items": items, "counts": counts, "silenzio_giorni": silenzio_giorni}


# ── Flusso dati — salute ricezione fatture Invoicetronic ──────────────────────
# Specchio di ricavi-salute, ma per la coda fatture (fatture_queue): dà a ogni
# cliente UNA riga di stato sulla ricezione automatica delle fatture SDI.
# Sola lettura. Mai espone l'XML (solo payload_meta, già non-PII).

# Stati problematici della coda (gli altri = sano: pending in attesa, done fatto).
_QUEUE_STATI_PROBLEMA = ["unknown_tenant", "da_assegnare", "failed", "dead"]


def _classifica_salute_invoicetronic(n_unknown: int, n_dead: int, n_failed: int,
                                     n_da_assegnare: int) -> str:
    """Stato salute ricezione fatture di un cliente.

    - critico: fatture arrivate ma non abbinate (unknown_tenant) o perse (dead),
      o errori di elaborazione (failed) — fatture reali che non entrano nell'app.
    - warning: solo multi-sede da smistare (da_assegnare): la fattura c'è, manca
      solo la scelta della sede.
    - ok: nessun problema in coda.
    """
    if n_unknown > 0 or n_dead > 0 or n_failed > 0:
        return "critico"
    if n_da_assegnare > 0:
        return "warning"
    return "ok"


@router.get("/api/admin/sistema/invoicetronic-salute", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_sistema_invoicetronic_salute(giorni: int = 30):
    """Salute della ricezione fatture Invoicetronic aggregata PER CLIENTE.

    Per ogni cliente (via P.IVA delle sue sedi) combina lo stato dei record in
    fatture_queue:
      - unknown_tenant: la fattura è arrivata ma la P.IVA non ha trovato il cliente
        (refuso P.IVA, sede non registrata) → fattura non entra nell'app;
      - da_assegnare: cliente multi-sede, indirizzo ambiguo → manca la scelta sede;
      - failed/dead: errore di elaborazione (download XML, parsing) → retry/persa;
      - done/pending: sane.

    Le P.IVA in unknown_tenant che non corrispondono a NESSUN cliente finiscono in
    `orfane` (fatture di qualcuno che non è ancora a sistema). Sola lettura.
    """
    sb = get_supabase_client()
    giorni = max(1, min(365, int(giorni or 30)))
    da_iso = (datetime.now(timezone.utc) - timedelta(days=giorni)).isoformat()

    # ── Mappa P.IVA → cliente (tutte le sedi attive) ─────────────────────────
    rist_per_piva: Dict[str, dict] = {}
    sedi_per_user: Dict[str, list] = {}
    try:
        rist_rows = (
            sb.table("ristoranti")
            .select("id,user_id,nome_ristorante,partita_iva,attivo")
            .eq("attivo", True)
            .execute()
        ).data or []
    except Exception as exc:
        logger.error("admin invoicetronic-salute: ristoranti falliti: %s", exc)
        rist_rows = []
    for r in rist_rows:
        piva = (r.get("partita_iva") or "").strip()
        uid = str(r.get("user_id") or "")
        if piva:
            rist_per_piva.setdefault(piva, {"user_id": uid, "ristorante_id": str(r["id"]),
                                            "nome_ristorante": r.get("nome_ristorante") or "—"})
        if uid:
            sedi_per_user.setdefault(uid, []).append({
                "id": str(r["id"]),
                "nome_ristorante": r.get("nome_ristorante") or "—",
                "partita_iva": piva,
            })

    # Nome cliente per user_id (preferisce nome ristorante della prima sede)
    nome_cliente: Dict[str, str] = {}
    for uid, sedi in sedi_per_user.items():
        nome_cliente[uid] = sedi[0]["nome_ristorante"] if sedi else "—"

    # ── Record problematici della coda (no XML) ──────────────────────────────
    try:
        coda_rows = (
            sb.table("fatture_queue")
            .select("id,user_id,piva_raw,status,attempt_count,created_at,last_error,payload_meta")
            .in_("status", _QUEUE_STATI_PROBLEMA)
            .gte("created_at", da_iso)
            .order("created_at", desc=True)
            .execute()
        ).data or []
    except Exception as exc:
        logger.error("admin invoicetronic-salute: coda fallita: %s", exc)
        coda_rows = []

    # Conteggio sani per cliente (done/pending nel periodo)
    sani_per_user: Dict[str, int] = {}
    try:
        sani_rows = (
            sb.table("fatture_queue")
            .select("user_id,status")
            .in_("status", ["done", "pending", "processing"])
            .gte("created_at", da_iso)
            .execute()
        ).data or []
        for r in sani_rows:
            uid = str(r.get("user_id") or "")
            if uid:
                sani_per_user[uid] = sani_per_user.get(uid, 0) + 1
    except Exception as exc:
        logger.error("admin invoicetronic-salute: sani falliti: %s", exc)

    def _meta(row, *keys):
        m = row.get("payload_meta") or {}
        for k in keys:
            v = m.get(k)
            if v not in (None, ""):
                return v
        return None

    # ── Smista i record problematici per cliente / orfane ────────────────────
    problemi_per_user: Dict[str, list] = {}
    orfane: list = []
    for row in coda_rows:
        item = {
            "queue_id": row.get("id"),
            "status": row.get("status"),
            "piva_raw": row.get("piva_raw"),
            "fornitore": _meta(row, "piva_cedente"),
            "numero": _meta(row, "numero_fattura"),
            "importo": _meta(row, "importo_totale"),
            "indirizzo": _meta(row, "indirizzo_destinatario"),
            "created_at": row.get("created_at"),
            "attempt_count": row.get("attempt_count"),
            "last_error": (row.get("last_error") or "")[:200] or None,
        }
        uid = str(row.get("user_id") or "")
        piva = (row.get("piva_raw") or "").strip()
        # Cliente noto: via user_id (failed/dead/da_assegnare hanno user_id) o via P.IVA.
        target_uid = uid if uid else (rist_per_piva.get(piva, {}).get("user_id", ""))
        if target_uid:
            problemi_per_user.setdefault(target_uid, []).append(item)
        else:
            orfane.append(item)

    # ── Una riga per cliente (tutti gli user con sede, anche se sani) ─────────
    items = []
    counts = {"ok": 0, "warning": 0, "critico": 0}
    for uid in sedi_per_user:
        probs = problemi_per_user.get(uid, [])
        n_unknown = sum(1 for p in probs if p["status"] == "unknown_tenant")
        n_dead = sum(1 for p in probs if p["status"] == "dead")
        n_failed = sum(1 for p in probs if p["status"] == "failed")
        n_da_assegnare = sum(1 for p in probs if p["status"] == "da_assegnare")
        stato = _classifica_salute_invoicetronic(n_unknown, n_dead, n_failed, n_da_assegnare)
        counts[stato] += 1
        items.append({
            "user_id": uid,
            "nome": nome_cliente.get(uid, "—"),
            "stato": stato,
            "n_sani": sani_per_user.get(uid, 0),
            "n_unknown": n_unknown,
            "n_dead": n_dead,
            "n_failed": n_failed,
            "n_da_assegnare": n_da_assegnare,
            "sedi": sedi_per_user.get(uid, []),
            "problemi": probs,
        })

    ordine = {"critico": 0, "warning": 1, "ok": 2}
    items.sort(key=lambda it: (ordine.get(it["stato"], 9), it["nome"]))
    return {"items": items, "counts": counts, "orfane": orfane, "giorni": giorni}


# ── Flusso dati — azioni correttive sulla coda fatture ────────────────────────
# Tutte richiedono conferma esplicita lato UI e loggano l'admin. Riusano le RPC
# DB già esistenti (resolve_unknown_tenant, assegna_fattura_a_sede) o un UPDATE
# guardato. NIENTE delete dall'UI.

class AssegnaPivaBody(BaseModel):
    piva: str = Field(..., max_length=32)
    ristorante_id: Optional[str] = None


@router.post("/api/admin/fatture-queue/assegna-piva", tags=["Admin"])
def admin_queue_assegna_piva(body: AssegnaPivaBody, admin_user: dict = Depends(_verify_admin)):
    """Sblocca le fatture unknown_tenant di una P.IVA, abbinandole a un cliente.

    Se passo ristorante_id → UPDATE mirato dei record unknown_tenant con quella
    piva_raw (utile quando la P.IVA in fattura differisce per refuso da quella a
    DB). Altrimenti delego a resolve_unknown_tenant(piva), che cerca il ristorante
    con quella P.IVA esatta. In entrambi i casi i record tornano 'pending'.
    """
    sb = get_supabase_client()
    piva = (body.piva or "").strip()
    if not piva:
        raise HTTPException(status_code=400, detail="P.IVA mancante")

    if body.ristorante_id:
        rid = body.ristorante_id
        rist = sb.table("ristoranti").select("id,user_id").eq("id", rid).eq("attivo", True).limit(1).execute()
        if not rist.data:
            raise HTTPException(status_code=404, detail="Ristorante non trovato o non attivo")
        user_id = rist.data[0]["user_id"]
        upd = (
            sb.table("fatture_queue")
            .update({"user_id": user_id, "ristorante_id": rid, "status": "pending",
                     "next_retry_at": datetime.now(timezone.utc).isoformat(),
                     "attempt_count": 0, "last_error": None})
            .eq("piva_raw", piva)
            .eq("status", "unknown_tenant")
            .execute()
        )
        n = len(upd.data or [])
    else:
        res = sb.rpc("resolve_unknown_tenant", {"p_piva": piva}).execute()
        n = int(res.data or 0)

    logger.warning("admin_queue_assegna_piva: piva=%s ristorante=%s record=%s | admin=%s",
                   piva, body.ristorante_id, n, admin_user.get("email"))
    return {"ok": True, "sbloccate": n}


class RiprovaQueueBody(BaseModel):
    queue_id: int


@router.post("/api/admin/fatture-queue/riprova", tags=["Admin"])
def admin_queue_riprova(body: RiprovaQueueBody, admin_user: dict = Depends(_verify_admin)):
    """Rimette in 'pending' una fattura failed/dead, azzerando i tentativi."""
    sb = get_supabase_client()
    cur = sb.table("fatture_queue").select("id,status").eq("id", body.queue_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="Fattura non trovata in coda")
    stato = cur.data[0].get("status")
    if stato not in ("failed", "dead"):
        raise HTTPException(status_code=409, detail=f"Stato '{stato}' non riprovabile (solo failed/dead)")
    sb.table("fatture_queue").update({
        "status": "pending",
        "next_retry_at": datetime.now(timezone.utc).isoformat(),
        "attempt_count": 0,
        "last_error": None,
    }).eq("id", body.queue_id).execute()
    logger.warning("admin_queue_riprova: queue_id=%s (era %s) | admin=%s",
                   body.queue_id, stato, admin_user.get("email"))
    return {"ok": True}


class AssegnaSedeQueueBody(BaseModel):
    queue_id: int
    ristorante_id: str


@router.post("/api/admin/fatture-queue/assegna-sede", tags=["Admin"])
def admin_queue_assegna_sede(body: AssegnaSedeQueueBody, admin_user: dict = Depends(_verify_admin)):
    """Smista una fattura multi-sede 'da_assegnare' alla sede scelta dall'admin.

    Riusa la RPC assegna_fattura_a_sede già usata lato cliente; qui l'admin opera
    per conto del cliente (nessun vincolo di proprietà sul chiamante).
    """
    sb = get_supabase_client()
    cur = sb.table("fatture_queue").select("id,status").eq("id", body.queue_id).eq("status", "da_assegnare").limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="Fattura non trovata o già assegnata")
    res = sb.rpc("assegna_fattura_a_sede", {"p_queue_id": body.queue_id, "p_ristorante_id": body.ristorante_id}).execute()
    if not bool(res.data):
        return {"ok": False, "motivo": "gia_assegnata"}
    logger.warning("admin_queue_assegna_sede: queue_id=%s sede=%s | admin=%s",
                   body.queue_id, body.ristorante_id, admin_user.get("email"))
    return {"ok": True}


# ── Sistema — Agent notturno ──────────────────────────────────────────────────

@router.get("/api/admin/sistema/agent-notturno", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_agent_notturno_status():
    """Ritorna lo stato corrente dell'agent notturno."""
    _agent_notturno_state = _agent_state()
    return {
        "enabled": _agent_notturno_state["enabled"],
        "ora_utc": _agent_notturno_state["ora_utc"],
        "last_run_at": _agent_notturno_state["last_run_at"],
        "last_digest": _agent_notturno_state["last_digest"],
        "running": _agent_notturno_state["running"],
    }


class AgentNotturnoToggleBody(BaseModel):
    enabled: bool
    ora_utc: Optional[int] = None


@router.post("/api/admin/sistema/agent-notturno/toggle", tags=["Admin"])
def admin_agent_notturno_toggle(body: AgentNotturnoToggleBody, admin_user: dict = Depends(_verify_admin)):
    """Abilita o disabilita l'agent notturno. Opzionalmente cambia l'ora di esecuzione (0-23 UTC)."""
    _agent_notturno_state = _agent_state()
    _agent_notturno_state["enabled"] = body.enabled
    if body.ora_utc is not None:
        _agent_notturno_state["ora_utc"] = max(0, min(23, body.ora_utc))
    _agent_notturno_persist()
    logger.info("agent_notturno toggle: enabled=%s ora_utc=%s | admin=%s",
                body.enabled, _agent_notturno_state["ora_utc"], admin_user.get("email"))
    return {
        "ok": True,
        "enabled": _agent_notturno_state["enabled"],
        "ora_utc": _agent_notturno_state["ora_utc"],
    }


@router.post("/api/admin/sistema/agent-notturno/esegui-ora", tags=["Admin"])
def admin_agent_notturno_esegui_ora(admin_user: dict = Depends(_verify_admin)):
    """Lancia subito l'agent notturno (indipendentemente dall'orario programmato)."""
    _agent_notturno_state = _agent_state()
    if _agent_notturno_state["running"]:
        raise HTTPException(status_code=409, detail="Agent già in esecuzione")
    asyncio.create_task(_run_agent_notturno(), name="agent-notturno-manual")
    logger.info("agent_notturno esecuzione manuale avviata | admin=%s", admin_user.get("email"))
    return {"ok": True, "message": "Agent avviato in background — aggiorna lo stato tra qualche secondi"}


# ── Azioni cliente (attiva/disattiva, reset password, cambia email, elimina) ──

class AzioneAccountBody(BaseModel):
    attivo: Optional[bool] = None


@router.patch("/api/admin/clienti/{cliente_id}/account", tags=["Admin"])
def admin_aggiorna_account(
    cliente_id: str,
    body: AzioneAccountBody,
    admin_user: dict = Depends(_verify_admin),
):
    """Attiva o disattiva account cliente."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    resp = sb.table("users").select("email").eq("id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    if resp.data[0]["email"].lower() in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi modificare account admin")

    update = {}
    if body.attivo is not None:
        update["attivo"] = body.attivo
    if not update:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")

    sb.table("users").update(update).eq("id", cliente_id).execute()
    logger.info("admin_aggiorna_account: cliente=%s attivo=%s | admin=%s", cliente_id, body.attivo, admin_user.get("email"))
    return {"ok": True}


@router.post("/api/admin/clienti/{cliente_id}/reset-password", tags=["Admin"])
def admin_reset_password(cliente_id: str, admin_user: dict = Depends(_verify_admin)):
    """Genera token reset password e invia email al cliente."""
    import html as _html_mod
    import requests as _requests
    import secrets as _secrets

    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    resp = sb.table("users").select("email,nome_ristorante").eq("id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    u = resp.data[0]
    if u["email"].lower() in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi modificare account admin")

    token = _secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    sb.table("users").update({"reset_code": token, "reset_expires": expires}).eq("id", cliente_id).execute()

    link = f"https://app.oneflux.it/reset-password?token={token}"
    email_inviata = False
    brevo_key = os.getenv("BREVO_API_KEY", "")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "noreply@oneflux.it")
    sender_name = os.getenv("BREVO_SENDER_NAME", "ONEFLUX")

    if brevo_key:
        try:
            nome_safe = _html_mod.escape(u.get("nome_ristorante") or u["email"])
            html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#0ea5e9;">Reset Password ONEFLUX</h2>
  <p>Ciao <strong>{nome_safe}</strong>,</p>
  <p>L'amministratore ha richiesto un reset della tua password.</p>
  <div style="text-align:center;margin:30px 0;">
    <a href="{link}" style="background:#0ea5e9;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">
      Imposta nuova password
    </a>
  </div>
  <p style="color:#dc2626;"><strong>⚠️ Il link scade tra 1 ora.</strong></p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
  <p style="color:#666;font-size:13px;"><strong>ONEFLUX Team</strong> — md@oneflux.it</p>
</div>"""
            r = _requests.post(
                "https://api.brevo.com/v3/smtp/email",
                json={
                    "sender": {"email": sender_email, "name": sender_name},
                    "to": [{"email": u["email"], "name": nome_safe}],
                    "replyTo": {"email": "md@oneflux.it", "name": "Mattia - ONEFLUX"},
                    "subject": "Reset Password — ONEFLUX",
                    "htmlContent": html_body,
                },
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                timeout=10,
            )
            email_inviata = r.status_code == 201
        except Exception as exc:
            logger.warning("Errore invio email reset: %s", exc)

    logger.info("admin_reset_password: cliente=%s | admin=%s | email_inviata=%s", cliente_id, admin_user.get("email"), email_inviata)
    return {"ok": True, "email_inviata": email_inviata, "link": link}


class CambioEmailBody(BaseModel):
    nuova_email: str = Field(..., max_length=254)


@router.patch("/api/admin/clienti/{cliente_id}/email", tags=["Admin"])
def admin_cambia_email(
    cliente_id: str,
    body: CambioEmailBody,
    admin_user: dict = Depends(_verify_admin),
):
    """Cambia email di login di un cliente e invalida la sua sessione."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    resp = sb.table("users").select("email").eq("id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    old_email = resp.data[0]["email"].lower()
    if old_email in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi modificare account admin")

    new_email = body.nuova_email.strip().lower()
    if new_email == old_email:
        raise HTTPException(status_code=400, detail="La nuova email deve essere diversa da quella attuale")

    dup = sb.table("users").select("id").eq("email", new_email).execute()
    if dup.data:
        raise HTTPException(status_code=409, detail="Email già registrata nel sistema")

    sb.table("users").update({
        "email": new_email,
        "session_token": None,
        "session_token_created_at": None,
    }).eq("id", cliente_id).execute()
    logger.info("admin_cambia_email: %s → %s | admin=%s", old_email, new_email, admin_user.get("email"))
    return {"ok": True}


@router.delete("/api/admin/clienti/{cliente_id}", tags=["Admin"])
def admin_elimina_cliente(
    cliente_id: str,
    elimina_memoria: bool = False,
    admin_user: dict = Depends(_verify_admin),
):
    """Elimina account cliente e tutti i suoi dati (cascade)."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    resp = sb.table("users").select("email").eq("id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    email_target = resp.data[0]["email"].lower()
    if email_target in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi eliminare account admin")

    deleted: dict = {}
    for table, col in [
        ("fatture", "user_id"),
        ("prodotti_utente", "user_id"),
        ("upload_events", "user_id"),
        ("classificazioni_manuali", "user_id"),
        # daily_briefing_state ha user_id TEXT (no FK CASCADE possibile): va ripulita
        # esplicitamente qui, altrimenti restano dati del cliente cancellato (GDPR).
        ("daily_briefing_state", "user_id"),
        ("ristoranti", "user_id"),
        ("ricette", "userid"),
        ("ingredienti_workspace", "userid"),
    ]:
        try:
            r = sb.table(table).delete().eq(col, cliente_id).execute()
            deleted[table] = len(r.data or [])
        except Exception as exc:
            logger.warning("Errore eliminazione %s: %s", table, exc)

    if elimina_memoria:
        try:
            r = sb.table("prodotti_master").delete().eq("user_id", cliente_id).execute()
            deleted["prodotti_master"] = len(r.data or [])
        except Exception as exc:
            logger.warning("Errore eliminazione prodotti_master: %s", exc)

    sb.table("users").delete().eq("id", cliente_id).execute()
    logger.warning("ELIMINAZIONE_ACCOUNT: cliente=%s | admin=%s | deleted=%s | memoria=%s", email_target, admin_user.get("email"), deleted, elimina_memoria)
    return {"ok": True, "deleted": deleted}


# ── Impersonazione ────────────────────────────────────────────────────────────

@router.post("/api/admin/impersona/{cliente_id}", tags=["Admin"])
def admin_impersona(cliente_id: str, admin_user: dict = Depends(_verify_admin)):
    """Genera un session token per il cliente target, ritorna target_token + info."""
    from services.session_service import crea_sessione
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()

    resp = sb.table("users").select("id,email,nome_ristorante,attivo").eq("id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    u = resp.data[0]
    if u["email"].lower() in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi impersonare un altro admin")

    # Sessione dedicata all'impersonazione: NON tocca le sessioni reali del cliente
    # (che oggi venivano sovrascritte). L'exit revoca solo questa.
    target_token = crea_sessione(cliente_id, source="impersonation")

    logger.warning("IMPERSONATION_START: admin=%s → target=%s (id=%s)", admin_user.get("email"), u["email"], cliente_id)
    return {
        "target_token": target_token,
        "target_email": u["email"],
        "target_nome": u.get("nome_ristorante") or u["email"],
    }


class ImpersonaExitBody(BaseModel):
    target_token: Optional[str] = Field(None, max_length=200)


@router.post("/api/admin/impersona/exit", tags=["Admin"])
def admin_impersona_exit(body: ImpersonaExitBody, admin_user: dict = Depends(_verify_admin)):
    """Chiude l'impersonazione invalidando nel DB il session_token del target.

    Senza questo, il token di impersonazione restava valido fino alla scadenza
    per inattivita' (8h) e l'admin ne conservava una copia funzionante. Qui lo
    azzeriamo: il cliente dovra' riloggarsi (e una eventuale copia del token non
    e' piu' utilizzabile).
    """
    target_token = (body.target_token or "").strip()
    if not target_token:
        return {"ok": True, "invalidated": False}
    from services.session_service import revoca_sessione
    invalidated = revoca_sessione(target_token)
    if not invalidated:
        # Fallback: token di impersonazione legacy su users.session_token (pre multi-token).
        sb = get_supabase_client()
        res = sb.table("users").update({"session_token": None}).eq("session_token", target_token).execute()
        invalidated = bool(res.data)
    logger.warning(
        "IMPERSONATION_END: admin=%s invalidato_token_target=%s",
        admin_user.get("email"), invalidated,
    )
    return {"ok": True, "invalidated": invalidated}


# ── Sedi (multi-ristorante) ───────────────────────────────────────────────────

class NuovaSedeBody(BaseModel):
    nome_ristorante: str = Field(..., max_length=150)
    partita_iva: str = Field(..., max_length=11)
    ragione_sociale: Optional[str] = Field(None, max_length=150)


@router.get("/api/admin/clienti/{cliente_id}/sedi", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_lista_sedi(cliente_id: str):
    sb = get_supabase_client()
    resp = sb.table("ristoranti").select("id,nome_ristorante,partita_iva,ragione_sociale,attivo").eq("user_id", cliente_id).execute()
    return resp.data or []


@router.post("/api/admin/clienti/{cliente_id}/sedi", tags=["Admin"])
def admin_crea_sede(
    cliente_id: str,
    body: NuovaSedeBody,
    admin_user: dict = Depends(_verify_admin),
):
    from utils.piva_validator import normalizza_piva, valida_formato_piva
    sb = get_supabase_client()
    piva = normalizza_piva(body.partita_iva)
    ok, msg = valida_formato_piva(piva)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    dup = sb.table("ristoranti").select("id").eq("user_id", cliente_id).eq("partita_iva", piva).execute()
    if dup.data:
        raise HTTPException(status_code=409, detail=f"P.IVA {piva} già registrata per questo cliente")
    r = sb.table("ristoranti").insert({
        "user_id": cliente_id,
        "nome_ristorante": body.nome_ristorante.strip(),
        "partita_iva": piva,
        "ragione_sociale": body.ragione_sociale.strip() if body.ragione_sociale else None,
        "attivo": True,
    }).execute()
    logger.info("admin_crea_sede: cliente=%s sede=%s | admin=%s", cliente_id, body.nome_ristorante, admin_user.get("email"))
    return r.data[0] if r.data else {"ok": True}


@router.delete("/api/admin/clienti/{cliente_id}/sedi/{sede_id}", tags=["Admin"])
def admin_elimina_sede(
    cliente_id: str,
    sede_id: str,
    admin_user: dict = Depends(_verify_admin),
):
    sb = get_supabase_client()
    resp = sb.table("ristoranti").select("id,nome_ristorante").eq("id", sede_id).eq("user_id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Sede non trovata")
    sb.table("ristoranti").delete().eq("id", sede_id).execute()
    logger.warning("admin_elimina_sede: sede=%s (%s) | admin=%s", sede_id, resp.data[0].get("nome_ristorante"), admin_user.get("email"))
    return {"ok": True}


# ── Mapping ragione sociale ───────────────────────────────────────────────────

class MappingBody(BaseModel):
    ragione_sociale: str = Field(..., max_length=200)
    ristorante_id: str


@router.get("/api/admin/ragione-sociale-map", tags=["Admin"], dependencies=[Depends(_verify_admin)])
def admin_lista_mapping():
    # La tabella ha `ragione_sociale_norm` (la chiave normalizzata che il parser
    # confronta), NON `ragione_sociale`. La esponiamo come `ragione_sociale` per
    # la UI, che mostra m.ragione_sociale. Prima qui si chiedeva una colonna
    # inesistente -> la lista risultava vuota anche con mapping presenti nel DB.
    sb = get_supabase_client()
    resp = (
        sb.table("ricavi_ragione_sociale_map")
        .select("id,ragione_sociale_norm,ristorante_id,gestionale,created_at")
        .order("ragione_sociale_norm")
        .execute()
    )
    return [
        {
            "id": r.get("id"),
            "ragione_sociale": r.get("ragione_sociale_norm"),
            "ristorante_id": r.get("ristorante_id"),
            "gestionale": r.get("gestionale"),
            "created_at": r.get("created_at"),
        }
        for r in (resp.data or [])
    ]


@router.post("/api/admin/ragione-sociale-map", tags=["Admin"])
def admin_crea_mapping(body: MappingBody, admin_user: dict = Depends(_verify_admin)):
    sb = get_supabase_client()
    # Normalizzazione IDENTICA a quella del parser (worker/email_queue_processor:
    # ragione_map.get(raw_ragione.lower().strip())). Se salvassimo la forma grezza,
    # il match in import fallirebbe e la riga ricadrebbe sul mittente.
    norm = body.ragione_sociale.strip().lower()
    if not norm:
        raise HTTPException(status_code=400, detail="Ragione sociale vuota")
    # `gestionale` e' NOT NULL e fa parte della chiave univoca
    # (ragione_sociale_norm, gestionale). Il worker scrive "passbi_v1": stesso
    # valore qui, altrimenti il dup-check non vedrebbe i mapping del worker.
    GESTIONALE = "passbi_v1"
    dup = (
        sb.table("ricavi_ragione_sociale_map")
        .select("id")
        .eq("ragione_sociale_norm", norm)
        .eq("gestionale", GESTIONALE)
        .execute()
    )
    if dup.data:
        raise HTTPException(status_code=409, detail="Ragione sociale già mappata")
    r = sb.table("ricavi_ragione_sociale_map").insert({
        "ragione_sociale_norm": norm,
        "ristorante_id": body.ristorante_id,
        "gestionale": GESTIONALE,
    }).execute()
    logger.info("admin_crea_mapping: %s → %s | admin=%s", norm, body.ristorante_id, admin_user.get("email"))
    row = r.data[0] if r.data else None
    if not row:
        return {"ok": True}
    return {
        "id": row.get("id"),
        "ragione_sociale": row.get("ragione_sociale_norm"),
        "ristorante_id": row.get("ristorante_id"),
        "gestionale": row.get("gestionale"),
        "created_at": row.get("created_at"),
    }


@router.delete("/api/admin/ragione-sociale-map/{mapping_id}", tags=["Admin"])
def admin_elimina_mapping(mapping_id: str, admin_user: dict = Depends(_verify_admin)):
    sb = get_supabase_client()
    sb.table("ricavi_ragione_sociale_map").delete().eq("id", mapping_id).execute()
    logger.info("admin_elimina_mapping: %s | admin=%s", mapping_id, admin_user.get("email"))
    return {"ok": True}


# ── Feature flags + blocchi + trial ──────────────────────────────────────────

class FlagsBody(BaseModel):
    pagine_abilitate: Optional[dict] = None
    chat_ai_enabled: Optional[bool] = None
    attivo: Optional[bool] = None
    trial_reset: Optional[bool] = None


@router.patch("/api/admin/clienti/{cliente_id}/flags", tags=["Admin"])
def admin_aggiorna_flags(
    cliente_id: str,
    body: FlagsBody,
    admin_user: dict = Depends(_verify_admin),
):
    """Aggiorna feature flags, stato account, trial."""
    sb = get_supabase_client()
    admin_emails = _admin_emails_set()
    resp = sb.table("users").select("email,pagine_abilitate").eq("id", cliente_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    if resp.data[0]["email"].lower() in admin_emails:
        raise HTTPException(status_code=403, detail="Non puoi modificare account admin")

    update: dict = {}
    if body.pagine_abilitate is not None:
        existing = resp.data[0].get("pagine_abilitate") or {}
        if isinstance(existing, dict):
            merged = {**existing, **body.pagine_abilitate}
        else:
            merged = body.pagine_abilitate
        update["pagine_abilitate"] = merged
    if body.attivo is not None:
        update["attivo"] = body.attivo
    if body.trial_reset:
        update["trial_active"] = False
        update["trial_activated_at"] = None

    if not update and body.chat_ai_enabled is None:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")

    if update:
        sb.table("users").update(update).eq("id", cliente_id).execute()

    if body.chat_ai_enabled is not None:
        ristorante_id = _get_ristorante_id_for_user(cliente_id, sb)
        if ristorante_id:
            sb.table("assistant_preferences").upsert(
                {"ristorante_id": ristorante_id, "chat_ai_enabled": body.chat_ai_enabled},
                on_conflict="ristorante_id",
            ).execute()

    logger.info("admin_aggiorna_flags: cliente=%s update=%s | admin=%s", cliente_id, list(update.keys()), admin_user.get("email"))
    return {"ok": True}


@router.post("/api/admin/clienti/{cliente_id}/trial", tags=["Admin"])
def admin_attiva_trial(cliente_id: str, admin_user: dict = Depends(_verify_admin)):
    """Attiva trial 7 giorni per il cliente."""
    from services.auth_service import attiva_trial
    ok, msg = attiva_trial(cliente_id, admin_user.get("email", ""), get_supabase_client())
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    logger.info("admin_attiva_trial: cliente=%s | admin=%s", cliente_id, admin_user.get("email"))
    return {"ok": True, "message": msg}
