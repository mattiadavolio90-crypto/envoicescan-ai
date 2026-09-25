"""Email settimanale dell'assistente (fase 7 del piano consulente) — la struttura.

Una volta a settimana, il lunedi' alle 7 di Roma, l'assistente raggiunge il
cliente anche se non apre l'app. Decisioni di Mattia: il link porta alla Home
(24/09); la riceve SOLO chi l'admin ha abilitato, cliente per cliente (25/09,
`users.email_settimanale_abilitata`), e il cliente la puo' sempre spegnere
(`users.email_settimanale`, la sua scelta, che nessuno sovrascrive).

IL CONTENUTO (fase 7b, deciso da Mattia il 25/09): «mi spaventa inviare
informazioni inutili o incomplete». Ogni argomento parla SOLO se per quel
cliente il dato e' affidabile, e le sezioni sono una lista di funzioni
(`SEZIONI`) che restituiscono una frase o None:
- l'incasso della settimana contro la precedente, se ENTRAMBE hanno i giorni
  registrati (almeno 6 su 7, meno i giorni di chiusura dichiarati);
- le fatture arrivate dallo SDI, solo dove arrivano davvero in automatico
  (misurato: l'SDI «attivo» non basta, una catena lo ha e carica a mano);
- le osservazioni della fase 4, quando scattano;
- a chi non manda dati da 4 settimane, un invito a riprendere.
Niente compiti (righe da classificare, dati mancanti): non sono notizie. Se
tutte le sezioni tacciono l'email non parte.

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
    # La sede tecnica di una catena («Costi comuni di gruppo») riceve le fatture
    # intestate alla societa'. Non e' un locale: entra SOLO nelle fatture dallo
    # SDI (Mattia, 25/09), mai in incasso, invito o osservazioni.
    sedi_tecniche: List[Dict[str, Any]] = field(default_factory=list)


def scegli_destinatari(utenti: List[Dict[str, Any]], sedi: List[Dict[str, Any]]) -> List[Destinatario]:
    """Funzione pura: chi riceve l'email, a partire dalle righe gia' lette.

    Riceve: utente attivo, ABILITATO dall'admin, con la sua preferenza accesa,
    non admin (per ruolo o per email), con almeno una sede attiva e non tecnica.
    Abilitazione assente = non abilitato: si spedisce solo a chi e' stato
    scelto. Una email per utente: la catena ha tutte le sue sedi nella stessa
    email.
    """
    admin = {e.strip().lower() for e in ADMIN_EMAILS}
    per_utente: Dict[str, List[Dict[str, Any]]] = {}
    tecniche: Dict[str, List[Dict[str, Any]]] = {}
    for s in sedi:
        if s.get("attivo") is False:
            continue
        voce = {"id": str(s.get("id")), "nome": str(s.get("nome_ristorante") or "").strip()}
        dove = tecniche if s.get("sede_tecnica") is True else per_utente
        dove.setdefault(str(s.get("user_id")), []).append(voce)
    out: List[Destinatario] = []
    for u in utenti:
        email = str(u.get("email") or "").strip()
        if not email or u.get("attivo") is False or u.get("email_settimanale") is False:
            continue
        if u.get("email_settimanale_abilitata") is not True:
            continue
        if str(u.get("ruolo") or "").strip().lower() == "admin" or email.lower() in admin:
            continue
        uid = str(u.get("id"))
        sedi_utente = sorted(per_utente.get(uid, []), key=lambda x: x["nome"])
        if not sedi_utente:
            continue
        nome = str(u.get("nome_referente") or u.get("nome_gruppo") or u.get("nome_ristorante") or "").strip()
        out.append(Destinatario(
            user_id=uid, email=email, nome=nome, sedi=sedi_utente,
            sedi_tecniche=sorted(tecniche.get(uid, []), key=lambda x: x["nome"]),
        ))
    return out


def leggi_destinatari(sb, solo_user_id: Optional[str] = None,
                      senza_abilitazione: bool = False) -> List[Destinatario]:
    """`senza_abilitazione`: solo per anteprima e prova all'admin, che servono
    a decidere SE abilitare un cliente. La scelta del cliente resta rispettata."""
    from utils.supabase_paging import fetch_all

    q = sb.table("users").select(
        "id,email,attivo,ruolo,email_settimanale,email_settimanale_abilitata,"
        "nome_referente,nome_gruppo,nome_ristorante"
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
    if senza_abilitazione:
        utenti = [{**u, "email_settimanale_abilitata": True} for u in utenti]
    return scegli_destinatari(utenti, sedi)


# ── Contenuto: le sezioni ───────────────────────────────────────────────────

Sezione = Callable[[Any, Destinatario, date], Optional[str]]

GIORNI_MINIMI_INCASSO = 6      # su 7, in entrambe le settimane
GIORNI_FERMO = 28              # senza dati da tanto = invito a riprendere
GIORNI_FLUSSO_SDI = 30         # fatture dallo SDI in questa finestra = flusso automatico
_NOTE_DI_CREDITO = ("TD04", "TD08")
_MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
         "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _roma():
    from zoneinfo import ZoneInfo
    return ZoneInfo("Europe/Rome")


def settimana_chiusa(oggi: date) -> tuple:
    """(lunedi', domenica) della settimana appena finita."""
    lun = lunedi_della_settimana(oggi)
    return lun - timedelta(days=7), lun - timedelta(days=1)


def _inizio_giorno(g: date) -> str:
    return datetime(g.year, g.month, g.day, tzinfo=_roma()).isoformat()


def _euro(valore: float) -> str:
    from services.daily_briefing_service import _euro_it
    return _euro_it(valore)


def _per_sedi(dest: Destinatario, righe: List[tuple], singola: str, elenco: str,
              n_sedi: Optional[int] = None) -> Optional[str]:
    """Una sede: la frase `singola` con il testo al posto di {}. Piu' sedi
    (catena): l'intestazione `elenco` e una riga per sede col nome davanti.
    `n_sedi` conta anche la sede tecnica, dove la sezione la include."""
    if not righe:
        return None
    if (len(dest.sedi) if n_sedi is None else n_sedi) == 1:
        return singola.format(righe[0][1])
    return f"{elenco}:\n" + "\n".join(f"• {nome}: {testo}" for nome, testo in righe)


def dal_giorno(g: date, anno_di_oggi: int) -> str:
    """«dal 15 luglio», ma «dall'8 agosto», «dall'11 agosto», «dal 1° agosto».
    Con l'anno se diverso da quello corrente."""
    if g.day == 1:
        testo = f"dal 1° {_MESI[g.month]}"
    elif g.day in (8, 11):
        testo = f"dall{chr(39)}{g.day} {_MESI[g.month]}"
    else:
        testo = f"dal {g.day} {_MESI[g.month]}"
    if g.year != anno_di_oggi:
        testo += f" {g.year}"
    return testo


def percentuale_con_articolo(n: int) -> str:
    """«il 5%», ma «l'8%», «l'11%», «l'80%»: l'articolo segue il suono del
    numero (uno, otto, undici, ottanta...)."""
    cifre = str(n)
    vocale = cifre in ("1", "11") or cifre.startswith("8")
    return f"{'l' + chr(39) if vocale else 'il '}{cifre}%"


def _giorni_chiusura(sb, ristorante_id: str) -> int:
    try:
        from services import fastapi_worker as fw
        v = int(fw._get_assistant_preferences(ristorante_id, sb).get("giorni_chiusura_settimanali") or 0)
        return max(0, min(v, 3))
    except Exception:
        return 0


def _incassi_per_giorno(sb, ristorante_id: str, da: date, a: date) -> Dict[str, float]:
    from utils.supabase_paging import fetch_all
    righe = fetch_all(
        sb.table("ricavi_giornalieri")
        .select("id,data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
        .eq("ristorante_id", ristorante_id)
        .gte("data", da.isoformat())
        .lte("data", a.isoformat())
        .order("id")
    )
    per_giorno: Dict[str, float] = {}
    for r in righe:
        giorno = str(r.get("data") or "")[:10]
        valore = (float(r.get("fatturato_iva10") or 0) + float(r.get("fatturato_iva22") or 0)
                  + float(r.get("altri_ricavi_noiva") or 0))
        per_giorno[giorno] = per_giorno.get(giorno, 0.0) + valore
    return {g: v for g, v in per_giorno.items() if v > 0}


def _sezione_incasso(sb, dest: Destinatario, oggi: date) -> Optional[str]:
    """L'incasso della settimana chiusa contro quella prima, sede per sede.
    Solo se ENTRAMBE le settimane hanno i giorni registrati: un confronto con
    una settimana a buchi direbbe «-40%» per un dato che manca."""
    from services import fastapi_worker as fw

    da, a = settimana_chiusa(oggi)
    da_prima, a_prima = da - timedelta(days=7), da - timedelta(days=1)
    righe: List[tuple] = []
    for s in dest.sedi:
        minimo = GIORNI_MINIMI_INCASSO - _giorni_chiusura(sb, s["id"])
        giorni = _incassi_per_giorno(sb, s["id"], da_prima, a)
        # Il limite superiore (domenica) lo mette gia' la query.
        ora = [v for g, v in giorni.items() if g >= da.isoformat()]
        prima = [v for g, v in giorni.items() if da_prima.isoformat() <= g <= a_prima.isoformat()]
        if len(ora) < minimo or len(prima) < minimo:
            continue
        tot, tot_prima = sum(ora), sum(prima)
        delta = (tot - tot_prima) / tot_prima * 100
        if abs(delta) < fw._ANDAMENTO_STABILE_PCT:
            confronto = "in linea con la settimana prima"
        else:
            confronto = (f"{percentuale_con_articolo(round(abs(delta)))} in "
                         f"{'più' if delta > 0 else 'meno'} della settimana prima")
        righe.append((s["nome"], f"€ {_euro(tot)}, {confronto}"))
    return _per_sedi(dest, righe, "La settimana scorsa hai incassato {}.",
                     "Incasso della settimana scorsa")


def _sezione_fatture_sdi(sb, dest: Destinatario, oggi: date) -> Optional[str]:
    """Le fatture arrivate dallo SDI nella settimana chiusa, solo dove il flusso
    e' automatico. Chi carica a mano lo fa a blocchi (214 fatture in un giorno,
    misurato): «questa settimana ne sono arrivate 0» sarebbe falso. Le note di
    credito sono salvate con importo positivo: non si sommano alle fatture."""
    from utils.supabase_paging import fetch_all

    da, a = settimana_chiusa(oggi)
    fine = a + timedelta(days=1)
    dal_flusso = fine - timedelta(days=GIORNI_FLUSSO_SDI)
    righe: List[tuple] = []
    tutte = [*dest.sedi, *dest.sedi_tecniche]
    for s in tutte:
        docs = fetch_all(
            sb.table("fatture_documenti")
            .select("id,totale_documento,tipo_documento,source_origin,created_at,deleted_at")
            .eq("ristorante_id", s["id"])
            .eq("source_origin", "invoicetronic")
            .gte("created_at", _inizio_giorno(dal_flusso))
            .lt("created_at", _inizio_giorno(fine))
            .order("id")
        )
        docs = [d for d in docs if not d.get("deleted_at")]
        if not docs:
            continue
        # Il limite superiore (mezzanotte di lunedi' a Roma) lo mette gia' la query.
        fatture = [
            d for d in docs
            if _giorno_a_roma(d.get("created_at")) >= da
            and str(d.get("tipo_documento") or "") not in _NOTE_DI_CREDITO
        ]
        if not fatture:
            continue
        n = len(fatture)
        tot = sum(float(d.get("totale_documento") or 0) for d in fatture)
        righe.append((s["nome"], f"{n} {'fattura' if n == 1 else 'fatture'} per € {_euro(tot)}"))
    return _per_sedi(dest, righe, "La settimana scorsa sono arrivate dallo SDI {}.",
                     "Fatture arrivate dallo SDI la settimana scorsa", n_sedi=len(tutte))


def _giorno_a_roma(created_at: Any) -> date:
    try:
        istante = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return date.min
    return istante.astimezone(_roma()).date()


def _sezione_osservazioni(sb, dest: Destinatario, oggi: date) -> Optional[str]:
    """Le osservazioni della fase 4 (andamento dell'incasso, food cost alto),
    con le loro regole e rispettando le voci spente nel configuratore della
    sede. Oggi parlano poco: si accendono quando i dati ci sono."""
    from services import fastapi_worker as fw
    from services.daily_briefing_service import _osservazione_frase, espandi_topic_spenti

    righe: List[tuple] = []
    for s in dest.sedi:
        try:
            td = fw._get_assistant_preferences(s["id"], sb).get("topics_disabled")
            spenti = set(espandi_topic_spenti(td or []))
        except Exception as exc:
            # Fail-CLOSED, al contrario della Home: un'email spedita non si
            # ritira, e senza preferenze non sappiamo se il cliente ha spento
            # questa osservazione. Quella sede tace.
            logger.warning("email settimanale: preferenze di %s illeggibili: %s", s["id"], exc)
            continue
        for rec in fw._briefing_osservazioni(dest.user_id, s["id"], sb, spenti, oggi=oggi):
            righe.append((s["nome"], _osservazione_frase(rec)))
    if not righe:
        return None
    if len(dest.sedi) == 1:
        return "\n".join(testo for _nome, testo in righe)
    return "\n".join(f"• {nome}: {testo}" for nome, testo in righe)


def _ultimo_dato(sb, dest: Destinatario, oggi: date) -> Optional[date]:
    """Il giorno piu' recente in cui e' arrivato un dato da una delle sedi:
    una fattura (qualunque canale) o un incasso."""
    ultimo: Optional[date] = None
    for s in dest.sedi:
        f = (sb.table("fatture_documenti").select("created_at")
             .eq("ristorante_id", s["id"]).is_("deleted_at", "null")
             .order("created_at", desc=True).limit(1).execute().data or [])
        if f:
            g = datetime.fromisoformat(str(f[0]["created_at"]).replace("Z", "+00:00")).astimezone(_roma()).date()
            ultimo = g if ultimo is None or g > ultimo else ultimo
        r = (sb.table("ricavi_giornalieri").select("data")
             .eq("ristorante_id", s["id"]).lte("data", oggi.isoformat())
             .order("data", desc=True).limit(1).execute().data or [])
        if r:
            g = date.fromisoformat(str(r[0]["data"])[:10])
            ultimo = g if ultimo is None or g > ultimo else ultimo
    return ultimo


def _sezione_invito(sb, dest: Destinatario, oggi: date) -> Optional[str]:
    """A chi non manda dati da 4 settimane: una riga, senza numeri (Mattia,
    25/09). Chi manda dati non la riceve mai."""
    ultimo = _ultimo_dato(sb, dest, oggi)
    if ultimo is not None and (oggi - ultimo).days < GIORNI_FERMO:
        return None
    if ultimo is None:
        dove = "dai tuoi locali" if len(dest.sedi) > 1 else "dal tuo locale"
        return f"Non abbiamo ancora ricevuto dati {dove}: bastano le fatture per cominciare."
    return f"Non riceviamo dati {dal_giorno(ultimo, oggi.year)}: bastano le fatture per ricominciare."


SEZIONI: List[Sezione] = [_sezione_invito, _sezione_incasso, _sezione_fatture_sdi, _sezione_osservazioni]


def calcola_frasi(
    sb, dest: Destinatario, oggi: date, sezioni: Optional[List[Sezione]] = None,
    fallite: Optional[List[str]] = None,
) -> List[str]:
    """Una frase per sezione che ha qualcosa da dire. Una sezione che fallisce
    tace e non fa saltare le altre, ma finisce in `fallite`: chi chiama la
    conta come errore, o un guasto (una colonna rinominata) spegnerebbe
    l'email di tutti in silenzio, registrata come «niente da dire»."""
    frasi: List[str] = []
    for sezione in (SEZIONI if sezioni is None else sezioni):
        try:
            frase = sezione(sb, dest, oggi)
        except Exception as exc:
            logger.warning("email settimanale: sezione %s fallita per %s: %s",
                           getattr(sezione, "__name__", "?"), dest.user_id, exc)
            if fallite is not None:
                fallite.append(getattr(sezione, "__name__", "?"))
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
    corpo_html = html.escape(saluto) + "<br><br>" + "<br><br>".join(
        html.escape(f).replace("\n", "<br>") for f in frasi
    )
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
        "gia_gestite": 0, "errori": 0, "composte": 0, "sezioni_fallite": 0,
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
        fallite: List[str] = []
        frasi = calcola_frasi(sb, dest, oggi, sezioni, fallite)
        if fallite:
            # Un guasto e' un errore: fa scattare l'avviso del workflow.
            resoconto["sezioni_fallite"] += len(fallite)
            resoconto["errori"] += 1
            if not frasi:
                # Non si registra «niente da dire»: non lo sappiamo. Senza la
                # riga, un nuovo giro della stessa settimana puo' riprovare.
                continue
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
    """L'email che quel cliente riceverebbe adesso SE fosse abilitato, senza
    spedirla: serve all'admin per decidere se abilitarlo."""
    destinatari = leggi_destinatari(sb, solo_user_id=user_id, senza_abilitazione=True)
    if not destinatari:
        return {"riceverebbe": False, "motivo": "non e' fra i destinatari (disattivata dal cliente, "
                                                "account spento, admin o senza sedi)"}
    dest = destinatari[0]
    fallite: List[str] = []
    frasi = calcola_frasi(sb, dest, adesso.date(), fallite=fallite)
    if not frasi:
        motivo = f"sezioni fallite: {', '.join(fallite)}" if fallite else "niente da dire"
        return {"riceverebbe": False, "motivo": motivo, "sedi": dest.sedi, "sezioni_fallite": fallite}
    try:
        email = componi_email(dest, frasi)
    except RuntimeError as exc:
        # Senza EMAIL_DISISCRIZIONE_SECRET l'email non si compone (e non
        # partirebbe): l'anteprima lo dice invece di rispondere 500.
        return {"riceverebbe": False, "motivo": str(exc), "sedi": dest.sedi, "frasi": frasi}
    return {"riceverebbe": True, "sedi": dest.sedi, "frasi": frasi, "sezioni_fallite": fallite,
            "oggetto": email["oggetto"], "html": email["html"], "testo": email["testo"]}


def invia_prova(sb, user_id: str, a_email: str, *, adesso: datetime) -> Dict[str, Any]:
    """Compone l'email di quel cliente e la spedisce SOLO a `a_email` (l'admin),
    con «[PROVA]» nell'oggetto. Non tocca il registro e non richiede
    l'interruttore dell'invio: serve a vedere l'email vera nella propria casella
    prima di accenderla. Il link di disiscrizione resta quello del cliente:
    non va cliccato."""
    from services.email_service import brevo_send

    a = anteprima(sb, user_id, adesso=adesso)
    if not a.get("riceverebbe"):
        return {"inviata": False, "motivo": a.get("motivo")}
    dest = leggi_destinatari(sb, solo_user_id=user_id, senza_abilitazione=True)[0]
    email = componi_email(dest, a["frasi"])
    ok = brevo_send(
        a_email, "Prova ONEFLUX", f"[PROVA] {email['oggetto']}", email["html"],
        contesto="settimanale-prova", text_body=email["testo"], headers=email["headers"],
    )
    return {"inviata": ok, "a": a_email, "frasi": a["frasi"]}


def disiscrivi(sb, user_id: str, token: str) -> bool:
    """Spegne la preferenza se il token e' valido. False altrimenti, senza dire
    perche': chi prova id a caso non deve sapere quali esistono."""
    if not verifica_token(user_id, token):
        return False
    sb.table("users").update({"email_settimanale": False}).eq("id", user_id).execute()
    return True
