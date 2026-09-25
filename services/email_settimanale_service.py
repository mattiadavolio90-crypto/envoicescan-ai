"""Email settimanale dell'assistente (fase 7 del piano consulente) — la struttura.

Una volta a settimana, il lunedi' alle 7 di Roma, l'assistente raggiunge il
cliente anche se non apre l'app. Decisioni di Mattia (24/09/2026): parte a tutti
i clienti attivi con la disiscrizione in ogni email; il link porta alla Home.

IL CONTENUTO NON E' QUI. Mattia vuole studiarlo a parte (fase 7b): le sezioni
sono una lista di funzioni (`SEZIONI`), ognuna riceve i dati del cliente e
restituisce una frase o None. Oggi c'e' un solo segnaposto. Se tutte tacciono
l'email non parte: meglio nessuna email che un'email vuota.

TRE SICURE PRIMA DI UN INVIO VERO, tutte e tre necessarie:
- `dry_run` (default True nell'endpoint);
- la variabile `EMAIL_SETTIMANALE_ATTIVA=1` sul worker (fase 7c, dopo la privacy);
- la riga del registro `email_settimanale_invii`, UNIQUE su (utente, lunedi'):
  chi la inserisce spedisce, chi la trova gia' li' salta. Il cron gira due
  volte di proposito (cambio d'ora) e una ripartenza non deve mai diventare una
  seconda email.
Senza le prime due non si scrive NIENTE, nemmeno il registro: una prova non deve
occupare la settimana di un invio vero.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

from config.constants import ADMIN_EMAILS, APP_URL
from config.logger_setup import get_logger

logger = get_logger("email_settimanale")

GIORNO_INVIO = 0          # lunedi' (date.weekday)
# Finestra d'invio, ore di Roma incluse: dalle 7 alle 9:59. Il cron gira alle
# 05:35 e alle 06:35 UTC: d'estate cadono entrambe dentro (7:35 e 8:35, la
# seconda trova tutto gia' gestito), d'inverno una sola (7:35). Tre ore e non
# una: con la finestra di un'ora bastava un cron in ritardo di mezz'ora per
# perdere la settimana in silenzio (review del 24/09). Dai doppi protegge il
# registro, non la finestra.
ORA_INVIO_DA = 7
ORA_INVIO_A = 9
ENV_INVIO_ATTIVO = "EMAIL_SETTIMANALE_ATTIVA"
ENV_SEGRETO = "EMAIL_DISISCRIZIONE_SECRET"
OGGETTO = "La settimana del tuo locale — ONEFLUX"


# ── Calendario ──────────────────────────────────────────────────────────────

def adesso_roma() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(tz=ZoneInfo("Europe/Rome"))


def lunedi_della_settimana(giorno: date) -> date:
    return giorno - timedelta(days=giorno.weekday())


def e_ora_di_invio(adesso: datetime) -> bool:
    """Lunedi' fra le 7:00 e le 9:59 di Roma. `adesso` deve essere gia' a Roma:
    e' qui che il cambio d'ora smette di contare."""
    return adesso.weekday() == GIORNO_INVIO and ORA_INVIO_DA <= adesso.hour <= ORA_INVIO_A


def invio_attivo() -> bool:
    return os.getenv(ENV_INVIO_ATTIVO, "").strip() == "1"


# ── Disiscrizione ───────────────────────────────────────────────────────────

def _segreto() -> Optional[bytes]:
    s = os.getenv(ENV_SEGRETO, "").strip()
    return s.encode("utf-8") if s else None


def token_disiscrizione(user_id: str) -> str:
    """HMAC-SHA256 dell'id utente. Senza segreto SOLLEVA: un link di
    disiscrizione che non si puo' verificare non deve partire in nessuna email."""
    segreto = _segreto()
    if segreto is None:
        raise RuntimeError(f"{ENV_SEGRETO} mancante: impossibile firmare la disiscrizione")
    return hmac.new(segreto, f"disiscrizione:{user_id}".encode("utf-8"), hashlib.sha256).hexdigest()


def verifica_token(user_id: str, token: str) -> bool:
    """Fail-closed: senza segreto, id o token nessuna disiscrizione passa."""
    if not user_id or not token or _segreto() is None:
        return False
    # Confronto su byte: compare_digest su stringhe non ASCII solleva TypeError
    # (un 500 invece di un «link non valido»).
    return hmac.compare_digest(
        token_disiscrizione(user_id).encode("utf-8"), str(token).encode("utf-8"),
    )


def link_disiscrizione(user_id: str, *, api: bool = False) -> str:
    """`api=False`: la pagina con il bottone (per le persone). `api=True`:
    l'indirizzo del List-Unsubscribe, che i client di posta chiamano in POST
    (RFC 8058) senza passare dalla pagina."""
    percorso = "/api/email/disiscrizione" if api else "/disiscrizione"
    return f"{APP_URL}{percorso}?" + urlencode({"u": user_id, "t": token_disiscrizione(user_id)})


# ── Destinatari ─────────────────────────────────────────────────────────────

@dataclass
class Destinatario:
    user_id: str
    email: str
    nome: str
    sedi: List[Dict[str, Any]] = field(default_factory=list)


def scegli_destinatari(utenti: List[Dict[str, Any]], sedi: List[Dict[str, Any]]) -> List[Destinatario]:
    """Funzione pura: chi riceve l'email, a partire dalle righe gia' lette.

    Riceve: utente attivo, con la preferenza accesa, non admin (per ruolo o per
    email), con almeno una sede attiva e non tecnica. Una email per utente: la
    catena ha tutte le sue sedi nella stessa email.
    """
    admin = {e.strip().lower() for e in ADMIN_EMAILS}
    per_utente: Dict[str, List[Dict[str, Any]]] = {}
    for s in sedi:
        if s.get("attivo") is False or s.get("sede_tecnica") is True:
            continue
        per_utente.setdefault(str(s.get("user_id")), []).append(
            {"id": str(s.get("id")), "nome": str(s.get("nome_ristorante") or "").strip()}
        )
    out: List[Destinatario] = []
    for u in utenti:
        email = str(u.get("email") or "").strip()
        if not email or u.get("attivo") is False or u.get("email_settimanale") is False:
            continue
        if str(u.get("ruolo") or "").strip().lower() == "admin" or email.lower() in admin:
            continue
        uid = str(u.get("id"))
        sedi_utente = sorted(per_utente.get(uid, []), key=lambda x: x["nome"])
        if not sedi_utente:
            continue
        nome = str(u.get("nome_referente") or u.get("nome_gruppo") or u.get("nome_ristorante") or "").strip()
        out.append(Destinatario(user_id=uid, email=email, nome=nome, sedi=sedi_utente))
    return out


def leggi_destinatari(sb, solo_user_id: Optional[str] = None) -> List[Destinatario]:
    from utils.supabase_paging import fetch_all

    q = sb.table("users").select(
        "id,email,attivo,ruolo,email_settimanale,nome_referente,nome_gruppo,nome_ristorante"
    )
    if solo_user_id:
        q = q.eq("id", solo_user_id)
    utenti = fetch_all(q.order("id"))
    ids = [str(u["id"]) for u in utenti]
    if not ids:
        return []
    sedi = fetch_all(
        sb.table("ristoranti")
        .select("id,user_id,nome_ristorante,attivo,sede_tecnica")
        .in_("user_id", ids)
        .order("id")
    )
    return scegli_destinatari(utenti, sedi)


# ── Contenuto: le sezioni ───────────────────────────────────────────────────

Sezione = Callable[[Destinatario, date], Optional[str]]


def _sezione_segnaposto(dest: Destinatario, oggi: date) -> Optional[str]:
    """SEGNAPOSTO della fase 7a: prova la catena di montaggio, non e' il
    contenuto. La fase 7b lo sostituisce con le sezioni scelte da Mattia."""
    nomi = ", ".join(s["nome"] for s in dest.sedi if s["nome"])
    if not nomi:
        return None
    return f"Il riepilogo della settimana di {nomi} è pronto nella Home di ONEFLUX."


SEZIONI: List[Sezione] = [_sezione_segnaposto]


def calcola_frasi(dest: Destinatario, oggi: date, sezioni: Optional[List[Sezione]] = None) -> List[str]:
    """Una frase per sezione che ha qualcosa da dire. Una sezione che fallisce
    tace, e basta: non puo' far saltare l'email delle altre."""
    frasi: List[str] = []
    for sezione in (SEZIONI if sezioni is None else sezioni):
        try:
            frase = sezione(dest, oggi)
        except Exception as exc:
            logger.warning("email settimanale: sezione %s fallita per %s: %s",
                           getattr(sezione, "__name__", "?"), dest.user_id, exc)
            continue
        if frase and frase.strip():
            frasi.append(frase.strip())
    return frasi


def componi_email(dest: Destinatario, frasi: List[str]) -> Dict[str, Any]:
    """Oggetto, HTML, testo e intestazioni. Tutto il testo che arriva dai dati
    passa da `html.escape`: nomi di sedi e frasi non sono HTML fidato."""
    from services.email_service import email_template

    link_home = f"{APP_URL}/dashboard"
    link_via = link_disiscrizione(dest.user_id)
    saluto = f"Ciao {dest.nome}," if dest.nome else "Ciao,"
    corpo_html = html.escape(saluto) + "<br><br>" + "<br><br>".join(html.escape(f) for f in frasi)
    piede = (
        "Ricevi questa email una volta a settimana perché usi ONEFLUX. "
        f'<a href="{html.escape(link_via)}" style="color:#64748b;">Non voglio più riceverla</a>.'
    )
    corpo_testo = "\n\n".join([saluto, *frasi, f"Apri ONEFLUX: {link_home}",
                               f"Non voglio più riceverla: {link_via}"])
    return {
        "oggetto": OGGETTO,
        "html": email_template(
            titolo="La tua settimana",
            corpo_html=corpo_html,
            cta_label="Apri ONEFLUX",
            cta_link=link_home,
            piede_html=piede,
        ),
        "testo": corpo_testo,
        "headers": {
            "List-Unsubscribe": f"<{link_disiscrizione(dest.user_id, api=True)}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }


# ── Il lavoro del lunedi' ───────────────────────────────────────────────────

def _prendi_la_settimana(sb, user_id: str, settimana: date, stato: str, motivo: Optional[str]) -> bool:
    """Inserisce la riga del registro. False se c'e' gia' (UNIQUE): quella
    settimana per quell'utente e' gia' stata gestita da un altro giro."""
    try:
        sb.table("email_settimanale_invii").insert({
            "user_id": user_id,
            "settimana": settimana.isoformat(),
            "stato": stato,
            "motivo": motivo,
        }).execute()
        return True
    except Exception as exc:
        testo = str(exc)
        if "23505" in testo or "duplicate key" in testo:
            return False
        raise


def _chiudi(sb, user_id: str, settimana: date, stato: str, motivo: Optional[str]) -> None:
    try:
        sb.table("email_settimanale_invii").update({
            "stato": stato,
            "motivo": motivo,
            "aggiornata_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).eq("settimana", settimana.isoformat()).execute()
    except Exception as exc:
        logger.warning("email settimanale: registro di %s non aggiornato (%s): %s", user_id, stato, exc)


def esegui(
    sb,
    *,
    adesso: datetime,
    dry_run: bool = True,
    solo_user_id: Optional[str] = None,
    sezioni: Optional[List[Sezione]] = None,
) -> Dict[str, Any]:
    """Compone (e se consentito spedisce) l'email della settimana a ogni
    destinatario. Ritorna un resoconto con i conteggi, mai il contenuto."""
    from services.email_service import brevo_send

    oggi = adesso.date()
    settimana = lunedi_della_settimana(oggi)
    spedisce = (not dry_run) and invio_attivo()
    resoconto: Dict[str, Any] = {
        "settimana": settimana.isoformat(),
        "dry_run": dry_run,
        "invio_attivo": invio_attivo(),
        "destinatari": 0, "inviate": 0, "niente_da_dire": 0,
        "gia_gestite": 0, "errori": 0, "composte": 0,
    }
    if not dry_run and not invio_attivo():
        # Il cron chiama con dry_run=false: finche' l'invio e' spento non c'e'
        # niente da fare, nemmeno comporre. Comporre senza il segreto della
        # disiscrizione (che arriva con la fase 7c) conterebbe un errore per
        # destinatario, e il workflow avviserebbe su Telegram ogni lunedi' per un
        # guasto che non c'e'. La composizione resta per le prove (dry_run=true).
        resoconto["motivo"] = "invio spento"
        return resoconto
    destinatari = leggi_destinatari(sb, solo_user_id=solo_user_id)
    resoconto["destinatari"] = len(destinatari)
    for dest in destinatari:
        frasi = calcola_frasi(dest, oggi, sezioni)
        if not spedisce:
            if not frasi:
                resoconto["niente_da_dire"] += 1
                continue
            try:
                componi_email(dest, frasi)
                resoconto["composte"] += 1
            except Exception as exc:
                logger.warning("email settimanale: composizione fallita per %s: %s", dest.user_id, exc)
                resoconto["errori"] += 1
            continue
        if not frasi:
            try:
                presa = _prendi_la_settimana(sb, dest.user_id, settimana, "saltata", "niente da dire")
            except Exception as exc:
                logger.warning("email settimanale: registro non scritto per %s: %s", dest.user_id, exc)
                resoconto["errori"] += 1
                continue
            resoconto["niente_da_dire" if presa else "gia_gestite"] += 1
            continue
        try:
            email = componi_email(dest, frasi)
        except Exception as exc:
            logger.warning("email settimanale: composizione fallita per %s: %s", dest.user_id, exc)
            resoconto["errori"] += 1
            continue
        try:
            presa = _prendi_la_settimana(sb, dest.user_id, settimana, "in_corso", None)
        except Exception as exc:
            # Un errore del registro diverso dal duplicato non ferma gli altri:
            # questo cliente salta la settimana (nessun invio senza la riga),
            # gli altri no.
            logger.warning("email settimanale: registro non scritto per %s: %s", dest.user_id, exc)
            resoconto["errori"] += 1
            continue
        if not presa:
            resoconto["gia_gestite"] += 1
            continue
        ok = brevo_send(
            dest.email, dest.nome, email["oggetto"], email["html"],
            contesto="settimanale", text_body=email["testo"], headers=email["headers"],
        )
        if ok:
            _chiudi(sb, dest.user_id, settimana, "inviata", None)
            resoconto["inviate"] += 1
        else:
            _chiudi(sb, dest.user_id, settimana, "errore", "Brevo non ha accettato l'invio")
            resoconto["errori"] += 1
    return resoconto


def anteprima(sb, user_id: str, *, adesso: datetime) -> Dict[str, Any]:
    """L'email che quel cliente riceverebbe adesso, senza spedirla: lo
    strumento della fase 7b per studiare il contenuto sui dati veri."""
    destinatari = leggi_destinatari(sb, solo_user_id=user_id)
    if not destinatari:
        return {"riceverebbe": False, "motivo": "non e' fra i destinatari"}
    dest = destinatari[0]
    frasi = calcola_frasi(dest, adesso.date())
    if not frasi:
        return {"riceverebbe": False, "motivo": "niente da dire", "sedi": dest.sedi}
    try:
        email = componi_email(dest, frasi)
    except RuntimeError as exc:
        # Senza EMAIL_DISISCRIZIONE_SECRET l'email non si compone (e non
        # partirebbe): l'anteprima lo dice invece di rispondere 500.
        return {"riceverebbe": False, "motivo": str(exc), "sedi": dest.sedi, "frasi": frasi}
    return {"riceverebbe": True, "sedi": dest.sedi, "frasi": frasi,
            "oggetto": email["oggetto"], "html": email["html"], "testo": email["testo"]}


def disiscrivi(sb, user_id: str, token: str) -> bool:
    """Spegne la preferenza se il token e' valido. False altrimenti, senza dire
    perche': chi prova id a caso non deve sapere quali esistono."""
    if not verifica_token(user_id, token):
        return False
    sb.table("users").update({"email_settimanale": False}).eq("id", user_id).execute()
    return True
