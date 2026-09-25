"""Invio automatico degli XML al commercialista: pianificatore ed esecutore
(fase C del piano, 25/09/2026).

Gira in un thread del queue-worker, che e' un processo solo (nel worker FastAPI,
a 4 processi, partirebbe 4 volte). Ogni minuto:

  1. righe appese: `in_corso` da oltre 2 ore. Senza email tentata → `errore`; con
     email tentata → `esito_incerto`. Mai ritentate da sole, e ogni esito incerto
     si segnala una volta.
  2. pianificatore: solo fra le 02:00 e le 04:59 di Roma e con
     INVIO_COMMERCIALISTA_ATTIVO=1. Una riga `ordinario` per ogni configurazione
     attiva, non sospesa, gia' partita (il primo invio lo lancia l'admin), con una
     sede SDI attiva e oltre la sua scadenza. Periodo: dal giorno dopo l'ultimo
     inviato (mai oltre 2 anni) a ieri, sul giorno di ARRIVO su Invoicetronic. Un
     tentativo per notte: se fallisce si riprova la notte dopo, col periodo che si
     allarga da solo.
  3. esecutore: prende le righe `richiesto` con un UPDATE condizionato ed esegue
     guardia → saldo → download → ZIP → Storage → email. Senza l'interruttore
     esegue solo le prove a vuoto.

Il registro e' la fonte di verita'. `inviato` solo dopo il 201 di Brevo; un
timeout o un 5xx dopo il tentativo e' `esito_incerto`, che blocca la
configurazione finche' non lo chiarisce l'admin: meglio un giorno di ritardo che
un doppione a un terzo. Negli avvisi Telegram solo id e motivi, mai email,
nomi o fornitori.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from config.logger_setup import get_logger
from services.invio_commercialista_guardia import (
    FiltroDoppioni,
    GuardiaViolata,
    controlla_azienda,
    controlla_coda,
    controlla_elenco,
    controlla_proprieta_piva,
    verifica_documento,
)
from services.invoicetronic_client import ErroreInvoicetronic, data_roma
from services.invoicetronic_saldo import SaldoInvoicetronicEsaurito

logger = get_logger("invio_commercialista")

ROMA = ZoneInfo("Europe/Rome")
ENV_ATTIVO = "INVIO_COMMERCIALISTA_ATTIVO"
ORA_DA = 2
ORA_A = 4
BUCKET = "invii-commercialista"
VALIDITA_LINK = timedelta(days=30)
RIMOZIONE_DOPO_SCADENZA = timedelta(days=1)
ETA_MASSIMA_FILE = VALIDITA_LINK + timedelta(days=3)
SOGLIA_DIVISIONE = 20 * 1024 * 1024
LIMITE_FILE = 50 * 1024 * 1024
MAX_EMAIL_24H = 3
APPESA_DOPO = timedelta(hours=2)
INTERVALLO_S = 60
PULIZIA_OGNI_S = 6 * 3600
ATTESA_MASSIMA_S = 3600
RIGHE_PER_CICLO = 20
PAGINE_BUCKET = 100
CONFIG = "invio_commercialista_config"
INVII = "invio_commercialista_invii"
RIFIUTO_DEL_DB = "23514"
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre")


# ── Calendario ──────────────────────────────────────────────────────────────

def adesso_utc() -> datetime:
    return datetime.now(timezone.utc)


def a_roma(istante: datetime) -> datetime:
    return istante.astimezone(ROMA)


def e_finestra_notturna(roma: datetime) -> bool:
    """Fra le 02:00 e le 04:59 di Roma. `roma` deve essere gia' a Roma."""
    return ORA_DA <= roma.hour <= ORA_A


def invio_attivo() -> bool:
    return os.getenv(ENV_ATTIVO, "").strip() == "1"


def ultima_scadenza(frequenza: str, oggi: date) -> date:
    """L'ultimo giorno d'invio non successivo a oggi: il lunedi', l'1 e il 16,
    l'1 del mese."""
    if frequenza == "settimanale":
        return oggi - timedelta(days=oggi.weekday())
    if frequenza == "quindicinale":
        return oggi.replace(day=16 if oggi.day >= 16 else 1)
    if frequenza == "mensile":
        return oggi.replace(day=1)
    raise ValueError(f"frequenza sconosciuta: {frequenza!r}")


def limite_due_anni(oggi: date) -> date:
    """Come `oggi - interval '2 years'` di Postgres: il 29/02 diventa il 28/02."""
    try:
        return oggi.replace(year=oggi.year - 2)
    except ValueError:
        return oggi.replace(year=oggi.year - 2, day=28)


def periodo_dovuto(frequenza: str, ultimo: Optional[date], oggi: date) -> Optional[Tuple[date, date]]:
    """Il periodo da spedire oggi, o None. Senza un primo invio riuscito non si
    parte: il primo lo lancia l'admin. Lo stesso calcolo del trigger del
    registro (GREATEST(ultimo + 1, limite)), che rifiuta ogni altro inizio."""
    if ultimo is None:
        return None
    if ultimo + timedelta(days=1) >= ultima_scadenza(frequenza, oggi):
        return None
    dal = max(ultimo + timedelta(days=1), limite_due_anni(oggi))
    al = oggi - timedelta(days=1)
    if dal > al:
        return None
    return dal, al


def inizio_giorno_utc(giorno: date) -> datetime:
    return datetime(giorno.year, giorno.month, giorno.day, tzinfo=ROMA).astimezone(timezone.utc)


def _istante(valore: Any) -> datetime:
    if isinstance(valore, datetime):
        dt = valore
    else:
        dt = datetime.fromisoformat(str(valore).replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _data(valore: Any) -> Optional[date]:
    if valore is None:
        return None
    if isinstance(valore, list):
        return _data(valore[0]) if valore else None
    if isinstance(valore, dict):
        return _data(next(iter(valore.values()), None))
    if isinstance(valore, datetime):
        return valore.date()
    if isinstance(valore, date):
        return valore
    return date.fromisoformat(str(valore)[:10])


def _iso(istante: datetime) -> str:
    return istante.astimezone(timezone.utc).isoformat()


def _it(giorno: date) -> str:
    return giorno.strftime("%d/%m/%Y")


def _breve(identificativo: Any) -> str:
    return str(identificativo)[:8]


# ── Letture dal DB ──────────────────────────────────────────────────────────

def ultimo_giorno_inviato(sb, config_id: str) -> Optional[date]:
    """Il cursore: lo stesso calcolo che usa il trigger del registro."""
    return _data(sb.rpc("invio_commercialista_ultimo_giorno", {"p_config_id": config_id}).execute().data)


def sede_sdi_attiva(sb, user_id: str, piva: str) -> bool:
    righe = (
        sb.table("ristoranti").select("id")
        .eq("user_id", user_id).eq("partita_iva", piva)
        .eq("sdi_attivo", True).eq("attivo", True)
        .limit(1).execute().data
    )
    return bool(righe)


def _esiste(query) -> bool:
    return bool(query.limit(1).execute().data)


# ── Pianificatore ───────────────────────────────────────────────────────────

def pianifica(sb, adesso: datetime, avvisa: Callable[[str], bool]) -> int:
    """Crea le righe `ordinario` dovute oggi. Ritorna quante. Il DB rifiuta i
    doppioni: qui si evita solo di provarci."""
    from utils.supabase_paging import fetch_all

    oggi = a_roma(adesso).date()
    da_oggi = _iso(inizio_giorno_utc(oggi))
    configurazioni = fetch_all(
        sb.table(CONFIG)
        .select("id,user_id,piva,invoicetronic_company_id,email_destinatario,frequenza")
        .eq("attivo", True).is_("sospesa_at", "null").order("id")
    )
    creati = 0
    for config in configurazioni:
        try:
            if _crea_ordinario(sb, config, oggi, da_oggi, avvisa):
                creati += 1
        except Exception as exc:
            logger.warning("Invio commercialista: configurazione %s non pianificata (%s)",
                           _breve(config.get("id")), type(exc).__name__)
    return creati


def _crea_ordinario(sb, config: Dict[str, Any], oggi: date, da_oggi: str,
                    avvisa: Callable[[str], bool]) -> bool:
    cid = config["id"]
    ultimo = ultimo_giorno_inviato(sb, cid)
    periodo = periodo_dovuto(config["frequenza"], ultimo, oggi)
    if periodo is None:
        return False
    if _esiste(sb.table(INVII).select("id").eq("config_id", cid)
               .eq("richiesto_da", "notturno").gte("creata_at", da_oggi)):
        return False
    if not sede_sdi_attiva(sb, config["user_id"], config["piva"]):
        logger.info("Invio commercialista %s sospeso: nessuna sede con SDI attivo", _breve(cid))
        return False
    dal, al = periodo
    try:
        sb.table(INVII).insert({
            "config_id": cid,
            "user_id": config["user_id"],
            "piva": config["piva"],
            "invoicetronic_company_id": config["invoicetronic_company_id"],
            "destinatario": config["email_destinatario"],
            "tipo": "ordinario",
            "periodo_dal": dal.isoformat(),
            "periodo_al": al.isoformat(),
            "stato": "richiesto",
            "richiesto_da": "notturno",
        }).execute()
    except Exception as exc:
        # Il caso normale e' un invio ancora in volo o da chiarire (ici_uno_in_volo):
        # e' il DB a dire di no, qui non si ricontrolla.
        logger.info("Invio commercialista %s: riga non creata (%s)", _breve(cid), getattr(exc, "code", type(exc).__name__))
        return False
    if ultimo is not None and ultimo + timedelta(days=1) < dal:
        avvisa(
            f"⚠️ Invio al commercialista (configurazione {_breve(cid)}): l'ultimo invio riuscito "
            f"risale a oltre 2 anni fa. Si riparte dal {_it(dal)}: il periodo precedente non e' piu' "
            "su Invoicetronic, va recuperato dal Cassetto fiscale."
        )
    return True


# ── Dipendenze esterne (sostituibili nei test) ──────────────────────────────

class ArchivioSupabase:
    """Il bucket privato degli ZIP."""

    def __init__(self, sb) -> None:
        self._bucket = sb.storage.from_(BUCKET)

    def carica(self, percorso: str, dati: bytes) -> None:
        self._bucket.upload(percorso, dati, {"content-type": "application/zip", "upsert": "false"})

    def link(self, percorso: str, secondi: int) -> str:
        risposta = self._bucket.create_signed_url(percorso, secondi)
        url = (risposta or {}).get("signedURL") or (risposta or {}).get("signedUrl")
        if not url:
            raise RuntimeError("link firmato non ottenuto")
        return url

    def rimuovi(self, percorsi: List[str]) -> None:
        if percorsi:
            self._bucket.remove(list(percorsi))

    def elenca(self, prefisso: str) -> List[Dict[str, Any]]:
        voci: List[Dict[str, Any]] = []
        for _ in range(PAGINE_BUCKET):
            pagina = list(self._bucket.list(prefisso, {"limit": 1000, "offset": len(voci)}) or [])
            voci += pagina
            if len(pagina) < 1000:
                return voci
        raise RuntimeError("elenco del bucket oltre il numero massimo di pagine")


def _avvisa_telegram(testo: str) -> bool:
    try:
        from services.telegram_service import invia_messaggio
        return bool(invia_messaggio(testo))
    except Exception as exc:
        logger.warning("Avviso Telegram non inviato: %s", type(exc).__name__)
        return False


@dataclass
class Dipendenze:
    client: Callable[[], Any]
    archivio: Callable[[Any], Any]
    invia_email: Callable[..., Any]
    leggi_saldo: Callable[[], int]
    soglia_saldo: Callable[[], int]
    avvisa: Callable[[str], bool]
    avvisa_saldo_esaurito: Callable[[str], bool]
    orologio: Callable[[], datetime] = adesso_utc


def dipendenze_reali() -> Dipendenze:
    from services.email_service import brevo_invia_con_esito
    from services.invoicetronic_client import ClientInvoicetronic
    from services.invoicetronic_saldo import avvisa_saldo_esaurito, leggi_saldo, soglia_configurata

    return Dipendenze(
        client=ClientInvoicetronic,
        archivio=ArchivioSupabase,
        invia_email=brevo_invia_con_esito,
        leggi_saldo=leggi_saldo,
        soglia_saldo=soglia_configurata,
        avvisa=_avvisa_telegram,
        avvisa_saldo_esaurito=avvisa_saldo_esaurito,
    )


# ── ZIP ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Parte:
    nome: str
    etichetta: str
    percorso: Path
    n_file: int
    byte: int


class _Pacchi:
    """Gli ZIP, scritti su disco un documento alla volta: uno per mese di arrivo, e
    dentro il mese un altro appena il corrente supera i 20 MB. A fine lavoro, se
    il totale sta sotto i 20 MB, diventano uno ZIP solo."""

    def __init__(self, cartella: Path, dal: date, al: date) -> None:
        self._cartella = cartella
        self._dal = dal
        self._al = al
        self._file: Dict[str, List[Path]] = {}
        self._aperto: Dict[str, zipfile.ZipFile] = {}
        self._conteggi: Dict[Path, int] = {}

    def _nuovo(self, mese: str) -> zipfile.ZipFile:
        percorso = self._cartella / f"mese_{mese}_{len(self._file.setdefault(mese, [])) + 1}.zip"
        self._file[mese].append(percorso)
        self._conteggi[percorso] = 0
        archivio = zipfile.ZipFile(percorso, "w", compression=zipfile.ZIP_DEFLATED)
        self._aperto[mese] = archivio
        return archivio

    def aggiungi(self, arrivo_roma: datetime, doc) -> None:
        mese = f"{arrivo_roma:%Y-%m}"
        archivio = self._aperto.get(mese)
        if archivio is None:
            archivio = self._nuovo(mese)
        elif archivio.fp.tell() > SOGLIA_DIVISIONE:
            archivio.close()
            archivio = self._nuovo(mese)
        info = zipfile.ZipInfo(doc.nome, date_time=arrivo_roma.timetuple()[:6])
        info.compress_type = zipfile.ZIP_DEFLATED
        archivio.writestr(info, doc.contenuto)
        self._conteggi[self._file[mese][-1]] += 1

    def abbandona(self) -> None:
        for archivio in self._aperto.values():
            archivio.close()

    def chiudi(self) -> List[Parte]:
        self.abbandona()
        mesi = sorted(self._file)
        if not mesi:
            return []
        tutti = [f for m in mesi for f in self._file[m]]
        if sum(f.stat().st_size for f in tutti) <= SOGLIA_DIVISIONE:
            destinazione = self._cartella / f"fatture_{self._dal:%Y-%m-%d}_{self._al:%Y-%m-%d}.zip"
            if len(tutti) == 1:
                os.replace(tutti[0], destinazione)
            else:
                with zipfile.ZipFile(destinazione, "w", compression=zipfile.ZIP_DEFLATED) as uscita:
                    for file in tutti:
                        with zipfile.ZipFile(file) as entrata:
                            for info in entrata.infolist():
                                uscita.writestr(info, entrata.read(info.filename))
            parti = [Parte(destinazione.name, "Scarica le fatture", destinazione,
                           sum(self._conteggi.values()), destinazione.stat().st_size)]
        else:
            parti = []
            for mese in mesi:
                anno, numero = mese.split("-")
                file = self._file[mese]
                for k, sorgente in enumerate(file, start=1):
                    suffisso = f"_{k}" if len(file) > 1 else ""
                    destinazione = self._cartella / f"fatture_{mese}{suffisso}.zip"
                    os.replace(sorgente, destinazione)
                    etichetta = f"Fatture arrivate a {MESI[int(numero) - 1]} {anno}"
                    if len(file) > 1:
                        etichetta += f" ({k} di {len(file)})"
                    parti.append(Parte(destinazione.name, etichetta, destinazione,
                                       self._conteggi[sorgente], destinazione.stat().st_size))
        if any(p.byte > LIMITE_FILE for p in parti):
            raise _Rinuncia("zip_oltre_il_limite_del_bucket", avviso=True)
        return parti


# ── Email ───────────────────────────────────────────────────────────────────

_SPAZI = re.compile(r"\s+")


def _una_riga(testo: Any, massimo: int = 120) -> str:
    return _SPAZI.sub(" ", str(testo or "")).strip()[:massimo]


def componi_email(nome: Any, piva: str, dal: date, al: date, n_file: int,
                  link: List[Tuple[str, str]], scade: date) -> Tuple[str, str, str]:
    """(oggetto, html, testo). Nessun importo e nessun fornitore: il contenuto
    sta solo nei file."""
    chi = _una_riga(nome) or f"P.IVA {piva}"
    periodo = f"dal {_it(dal)} al {_it(al)}"
    oggetto = f"Fatture ricevute {periodo} — {chi}"
    canale = (
        "Sono incluse solo le fatture arrivate sul codice destinatario gestito da OneFlux, "
        "non quelle ricevute su altri canali. È una copia di comodo: non è un servizio di "
        "conservazione e non sostituisce il Cassetto fiscale dell'Agenzia delle Entrate."
    )
    if n_file:
        apertura = (
            f"ecco le fatture passive di {chi} (P.IVA {piva}) arrivate tramite OneFlux {periodo}: "
            f"{n_file} file, negli originali XML o P7M firmati."
        )
        scadenza = (
            f"Il link è personale e vale fino al {_it(scade)}: dopo quella data la copia viene "
            "cancellata dai sistemi OneFlux."
        )
    else:
        apertura = (
            f"{periodo[0].upper()}{periodo[1:]} non sono arrivate tramite OneFlux fatture passive "
            f"per {chi} (P.IVA {piva}): questa volta non c'è nulla da scaricare."
        )
        scadenza = ""
    chiusura = "Per qualunque domanda può rispondere a questa email."
    firma = f"OneFlux — invio automatico richiesto da {chi}"

    testo = ["Buongiorno,", "", apertura, ""]
    for etichetta, url in link:
        testo += [f"{etichetta}: {url}"]
    if link:
        testo += [""]
    if scadenza:
        testo += [scadenza, ""]
    testo += [canale, "", chiusura, "", firma]

    e = html.escape
    pulsanti = "".join(
        f'<p style="margin:16px 0"><a href="{e(url, quote=True)}" '
        'style="display:inline-block;padding:10px 18px;background:#1d4ed8;color:#ffffff;'
        f'text-decoration:none;border-radius:6px">{e(etichetta)}</a></p>'
        for etichetta, url in link
    )
    corpo = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111827;max-width:560px">'
        "<p>Buongiorno,</p>"
        f"<p>{e(apertura)}</p>"
        f"{pulsanti}"
        + (f"<p>{e(scadenza)}</p>" if scadenza else "")
        + f'<p style="color:#4b5563;font-size:13px">{e(canale)}</p>'
        f"<p>{e(chiusura)}</p>"
        f'<p style="color:#6b7280;font-size:12px">{e(firma)}</p>'
        "</div>"
    )
    return oggetto, corpo, "\n".join(testo)


def misure_prova(documenti: List[Dict[str, Any]], saldo_prima: Optional[int],
                 saldo_dopo: Optional[int], parti: List[Parte]) -> str:
    """Cio' che la prova a vuoto deve misurare (piano A8): quanto `created` dista
    da `date_sent` e se scaricare di nuovo costa operazioni."""
    scarti: List[float] = []
    senza_data = 0
    for doc in documenti:
        inviata = doc.get("date_sent")
        if not inviata:
            senza_data += 1
            continue
        scarti.append((_istante(doc["created"]) - _istante(inviata)).total_seconds() / 86400)
    pezzi = [f"documenti {len(documenti)}"]
    if saldo_prima is not None:
        dopo = "illeggibile" if saldo_dopo is None else str(saldo_dopo)
        pezzi.append(f"saldo prima {saldo_prima}, dopo {dopo}")
    if scarti:
        pezzi.append(f"arrivo meno date_sent da {min(scarti):.2f} a {max(scarti):.2f} giorni")
    if senza_data:
        pezzi.append(f"senza date_sent {senza_data}")
    pezzi.append(f"zip {len(parti)}, {sum(p.byte for p in parti)} byte")
    return "prova: " + "; ".join(pezzi)


# ── Esecutore ───────────────────────────────────────────────────────────────

class _Rinuncia(Exception):
    """Un invio che non si fa, per un motivo ordinario (non una violazione)."""

    def __init__(self, motivo: str, avviso: bool = False) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.avviso = avviso


class _Bloccato(Exception):
    """Un invio fermato senza sospendere la configurazione (anti-loop)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def _rifiutato_dal_db(exc: Exception) -> bool:
    """Il trigger del registro ha detto no (check_violation), non la rete."""
    return getattr(exc, "code", None) == RIFIUTO_DEL_DB


def prendi_richiesto(sb, adesso: datetime) -> Optional[Dict[str, Any]]:
    """La prossima riga `richiesto`, presa con un UPDATE condizionato: se un
    altro processo l'ha gia' presa, l'UPDATE non tocca niente. Se nel frattempo
    la configurazione e' stata spenta, sospesa, cancellata o ha cambiato email, il
    DB rifiuta la presa: la riga si chiude in `errore` invece di restare li'."""
    candidati = (
        sb.table(INVII).select("id").eq("stato", "richiesto")
        .order("creata_at").limit(RIGHE_PER_CICLO).execute().data or []
    )
    for candidato in candidati:
        try:
            prese = (
                sb.table(INVII).update({"stato": "in_corso", "iniziata_at": _iso(adesso)})
                .eq("id", candidato["id"]).eq("stato", "richiesto").execute().data
            )
        except Exception as exc:
            if not _rifiutato_dal_db(exc):
                raise
            sb.table(INVII).update({"stato": "errore", "motivo": "non_piu_autorizzato", "conclusa_at": _iso(adesso)}) \
                .eq("id", candidato["id"]).eq("stato", "richiesto").execute()
            logger.info("Invio %s non piu' autorizzato alla presa: chiuso in errore", _breve(candidato["id"]))
            continue
        if prese:
            return prese[0]
    return None


class _Invio:
    def __init__(self, sb, riga: Dict[str, Any], dip: Dipendenze) -> None:
        self.sb = sb
        self.riga = riga
        self.dip = dip
        self.id = riga["id"]
        self.email_tentata = False
        self.caricati: List[str] = []
        self.client: Any = None

    # stato

    def _aggiorna(self, campi: Dict[str, Any], stato_atteso: str = "in_corso") -> bool:
        return bool(
            self.sb.table(INVII).update(campi)
            .eq("id", self.id).eq("stato", stato_atteso).execute().data
        )

    def _adesso(self) -> str:
        return _iso(self.dip.orologio())

    def _rimuovi_caricati(self) -> None:
        if not self.caricati:
            return
        try:
            self.dip.archivio(self.sb).rimuovi(self.caricati)
            self.sb.table(INVII).update({"file_rimossi_at": self._adesso()}).eq("id", self.id).execute()
        except Exception as exc:
            logger.warning("Invio %s: file non rimossi subito (%s), li toglie la pulizia",
                           _breve(self.id), type(exc).__name__)

    def _avviso(self, testo: str) -> None:
        self.dip.avvisa(testo)

    def _intestazione(self) -> str:
        return f"invio {_breve(self.id)}, configurazione {_breve(self.riga['config_id'])}, {self.riga['tipo']}"

    def _seconda_notte_di_fila(self) -> bool:
        if self.riga.get("richiesto_da") != "notturno":
            return False
        ultime = (
            self.sb.table(INVII).select("stato")
            .eq("config_id", self.riga["config_id"]).eq("richiesto_da", "notturno")
            .order("creata_at", desc=True).limit(2).execute().data or []
        )
        return len(ultime) == 2 and all(r.get("stato") == "errore" for r in ultime)

    def _fallisci(self, motivo: str, avviso: bool = False) -> str:
        motivo = motivo[:500]
        if self.email_tentata:
            self._aggiorna({"stato": "esito_incerto", "motivo": motivo})
            return "esito_incerto"
        self._aggiorna({"stato": "errore", "motivo": motivo, "conclusa_at": self._adesso()})
        self._rimuovi_caricati()
        if avviso or self._seconda_notte_di_fila():
            self._avviso(f"⚠️ Invio al commercialista non riuscito ({self._intestazione()}): {motivo}")
        return "errore"

    def _blocca(self, motivo: str, sospendi: bool) -> str:
        if self.email_tentata:
            return self._fallisci(motivo)
        self._aggiorna({"stato": "bloccato", "motivo": motivo, "conclusa_at": self._adesso()})
        self._rimuovi_caricati()
        if sospendi:
            self.sb.table(CONFIG).update({"sospesa_at": self._adesso(), "sospesa_motivo": motivo}) \
                .eq("id", self.riga["config_id"]).execute()
        self._avviso(
            f"🚨 Invio al commercialista BLOCCATO ({self._intestazione()}): {motivo}. "
            + ("Configurazione sospesa: nessun altro invio finche' non la riattivi dall'area admin."
               if sospendi else "Nessun file e' partito.")
        )
        return "bloccato"

    # lavoro

    def esegui(self) -> str:
        cartella = Path(tempfile.mkdtemp(prefix="invio_commercialista_"))
        try:
            return self._esegui(cartella)
        except GuardiaViolata as exc:
            return self._blocca(exc.codice, sospendi=True)
        except _Bloccato as exc:
            return self._blocca(exc.motivo, sospendi=False)
        except SaldoInvoicetronicEsaurito:
            self.dip.avvisa_saldo_esaurito("invio_commercialista")
            return self._fallisci("saldo_invoicetronic_esaurito")
        except ErroreInvoicetronic as exc:
            return self._fallisci(f"invoicetronic: {exc}", avviso=exc.configurazione)
        except _Rinuncia as exc:
            return self._fallisci(exc.motivo, avviso=exc.avviso)
        except Exception as exc:
            # Senza il messaggio: quello di un vincolo del DB riporta la riga intera,
            # email del commercialista compresa, e finirebbe nei log di Railway.
            logger.error("Invio %s: errore inatteso %s\n%s", _breve(self.id), type(exc).__name__,
                         "".join(traceback.format_tb(exc.__traceback__)))
            return self._fallisci(f"errore_interno: {type(exc).__name__}", avviso=True)
        finally:
            shutil.rmtree(cartella, ignore_errors=True)
            chiudi = getattr(self.client, "chiudi", None)
            if callable(chiudi):
                try:
                    chiudi()
                except Exception:
                    pass

    def _config(self) -> Dict[str, Any]:
        righe = (
            self.sb.table(CONFIG)
            .select("id,user_id,piva,invoicetronic_company_id,invoicetronic_nome")
            .eq("id", self.riga["config_id"]).limit(1).execute().data
        )
        if not righe:
            raise _Rinuncia("configurazione_assente")
        config = righe[0]
        r = self.riga
        if (str(config["user_id"]), config["piva"], config["invoicetronic_company_id"]) != (
                str(r["user_id"]), r["piva"], r["invoicetronic_company_id"]):
            raise GuardiaViolata("registro_diverso_dalla_configurazione")
        return config

    def _controlla_sede_sdi(self, config: Dict[str, Any]) -> None:
        """Attiva, non sospesa e col consenso per quel destinatario lo verifica il
        trigger del registro, alla presa e alla partenza dell'email. La sede con
        SDI attivo il DB non la guarda: il cliente che esce si ferma qui."""
        if not sede_sdi_attiva(self.sb, str(config["user_id"]), config["piva"]):
            raise _Rinuncia("nessuna_sede_con_sdi_attivo")

    def _controlla_saldo(self, da_scaricare: int) -> int:
        """Un arretrato lungo non deve svuotare il saldo che serve alle fatture in
        arrivo di tutti i clienti: dopo l'invio deve restare almeno la soglia
        dell'avviso (la specifica dice che ogni download costa un'operazione)."""
        try:
            rimaste = self.dip.leggi_saldo()
        except Exception as exc:
            raise _Rinuncia(f"saldo_illeggibile ({type(exc).__name__})") from None
        if rimaste - da_scaricare < self.dip.soglia_saldo():
            raise _Rinuncia(f"saldo_insufficiente ({rimaste} operazioni, {da_scaricare} documenti)", avviso=True)
        return rimaste

    def _segnala_arrivi_in_periodi_spediti(self, elenco: List[Dict[str, Any]]) -> set:
        """Il periodo si decide su `created`. Se Invoicetronic rielabora una fattura
        con la data di prima (le trattenute prima che l'azienda esista), quella cade
        in un periodo gia' spedito e il commercialista non la riceve mai. Qui si
        contano: documenti dell'elenco dentro un periodo inviato che nessun invio
        aveva visto (i doppioni scartati sono in `documenti_visti`, non danno
        allarmi). Si recuperano con un reinvio, che li include e li segna visti."""
        spediti = (
            self.sb.table(INVII).select("tipo,periodo_dal,periodo_al,documenti_visti")
            .eq("config_id", self.riga["config_id"]).in_("stato", ["inviato", "esito_incerto"])
            .execute().data or []
        )
        coperti = [(_data(r["periodo_dal"]), _data(r["periodo_al"]))
                   for r in spediti if r.get("tipo") in ("primo", "ordinario")]
        gia_visti = {i for r in spediti for i in (r.get("documenti_visti") or [])}
        fuori = [
            d for d in elenco
            if d["id"] not in gia_visti
            and any(dal <= data_roma(d["created"]) <= al for dal, al in coperti)
        ]
        if fuori:
            self._avviso(
                f"⚠️ Invio al commercialista ({self._intestazione()}): {len(fuori)} documenti risultano "
                "arrivati su Invoicetronic in periodi gia' spediti, e al commercialista non sono andati. "
                "Si recuperano con un reinvio di quei periodi dall'area admin."
            )
        return gia_visti

    def _controlla_frequenza_email(self, destinatario: str, adesso: datetime) -> None:
        """Anti-loop: al massimo MAX_EMAIL_24H email in 24 ore per ogni
        configurazione attiva che scrive a quell'indirizzo. Un commercialista con
        quattro clienti riceve quattro email l'1 del mese, e non e' un loop."""
        risposta = (
            self.sb.table("email_rate_log").select("id", count="exact", head=True)
            .eq("destinatario", destinatario).gte("created_at", _iso(adesso - timedelta(hours=24)))
            .execute()
        )
        conteggio = getattr(risposta, "count", None)
        configurazioni = getattr(
            self.sb.table(CONFIG).select("id", count="exact", head=True)
            .eq("email_destinatario", destinatario).eq("attivo", True).execute(),
            "count", None,
        )
        if not isinstance(conteggio, int) or not isinstance(configurazioni, int):
            raise _Rinuncia("contatore_email_illeggibile")
        if conteggio >= MAX_EMAIL_24H * max(configurazioni, 1):
            raise _Bloccato("troppe_email_allo_stesso_destinatario_in_24_ore")

    def _esegui(self, cartella: Path) -> str:
        r = self.riga
        prova = r["tipo"] == "prova"
        if not prova and not invio_attivo():
            raise _Rinuncia("invio_spento")
        config = self._config()
        if not prova:
            self._controlla_sede_sdi(config)
        user_id, piva, azienda = str(r["user_id"]), r["piva"], int(r["invoicetronic_company_id"])
        dal, al = _data(r["periodo_dal"]), _data(r["periodo_al"])
        adesso = self.dip.orologio()

        controlla_proprieta_piva(self.sb, piva, user_id)
        client = self.client = self.dip.client()
        controlla_azienda(client.azienda(azienda), azienda, piva)
        elenco = client.elenco_ricevute(azienda)
        controlla_elenco(elenco, azienda, piva)
        controlla_coda(self.sb, user_id, piva, azienda, {d["id"] for d in elenco}, adesso=adesso)

        nel_periodo = sorted(
            (d for d in elenco if dal <= data_roma(d["created"]) <= al),
            key=lambda d: (_istante(d["created"]), d["id"]),
        )
        if r["tipo"] in ("primo", "ordinario"):
            # Un documento gia' visto da un invio precedente non riparte, anche se
            # Invoicetronic ne ha spostato la data d'arrivo nel periodo nuovo.
            gia_visti = self._segnala_arrivi_in_periodi_spediti(elenco)
            nel_periodo = [d for d in nel_periodo if d["id"] not in gia_visti]
        visti = [d["id"] for d in nel_periodo]
        saldo_prima = self._controlla_saldo(len(nel_periodo)) if nel_periodo else None

        pacchi = _Pacchi(cartella, dal, al)
        filtro = FiltroDoppioni()
        ids: List[int] = []
        try:
            for voce in nel_periodo:
                doc = verifica_documento(client.documento(voce["id"]), azienda, piva)
                if filtro.ammetti(doc):
                    pacchi.aggiungi(a_roma(_istante(voce["created"])), doc)
                    ids.append(doc.receive_id)
        except BaseException:
            pacchi.abbandona()
            raise
        parti = pacchi.chiudi()
        byte_totali = sum(p.byte for p in parti)

        if prova:
            saldo_dopo = None
            if nel_periodo:
                try:
                    saldo_dopo = self.dip.leggi_saldo()
                except Exception:
                    saldo_dopo = None
            self._aggiorna({
                "stato": "prova_ok", "n_file": len(ids), "byte_totali": byte_totali, "documenti_ids": ids,
                "documenti_visti": visti,
                "motivo": misure_prova(nel_periodo, saldo_prima, saldo_dopo, parti),
                "conclusa_at": self._adesso(),
            })
            return "prova_ok"

        destinatario = r["destinatario"]
        self._controlla_frequenza_email(destinatario, adesso)
        if not os.getenv("BREVO_API_KEY", "").strip():
            raise _Rinuncia("brevo_non_configurato", avviso=True)

        scade = adesso + VALIDITA_LINK
        link: List[Tuple[str, str]] = []
        registro = {"n_file": len(ids), "byte_totali": byte_totali, "documenti_ids": ids, "documenti_visti": visti}
        if parti:
            percorsi = [f"{r['config_id']}/{self.id}/{p.nome}" for p in parti]
            # Prima di caricare: se il worker muore a meta', la pulizia sa cosa togliere.
            registro.update({"storage_paths": percorsi, "link_scade_il": _iso(scade)})
            if not self._aggiorna(registro):
                raise _Rinuncia("riga_non_piu_in_corso")
            self.caricati = percorsi
            archivio = self.dip.archivio(self.sb)
            for parte, percorso in zip(parti, percorsi):
                archivio.carica(percorso, parte.percorso.read_bytes())
            secondi = int(VALIDITA_LINK.total_seconds())
            link = [(parte.etichetta, archivio.link(percorso, secondi)) for parte, percorso in zip(parti, percorsi)]
        elif not self._aggiorna(registro):
            raise _Rinuncia("riga_non_piu_in_corso")

        # Il link scade all'ora dell'invio di quel giorno: l'ultimo giorno pieno e' il precedente.
        oggetto, corpo_html, corpo_testo = componi_email(
            config.get("invoicetronic_nome"), piva, dal, al, len(ids), link,
            a_roma(scade).date() - timedelta(days=1),
        )
        self.sb.table("email_rate_log").insert({
            "destinatario": destinatario,
            "oggetto_hash": hashlib.sha256(oggetto.encode("utf-8")).hexdigest(),
            "user_id": user_id,
        }).execute()
        try:
            partita = self._aggiorna({"email_tentata_at": self._adesso()})
        except Exception as exc:
            if _rifiutato_dal_db(exc):
                raise _Rinuncia("configurazione_cambiata_durante_l_invio", avviso=True) from None
            raise
        if not partita:
            raise _Rinuncia("riga_non_piu_in_corso")
        self.email_tentata = True
        esito = self.dip.invia_email(destinatario, "", oggetto, corpo_html,
                                     text_body=corpo_testo, contesto="invio_commercialista")
        return self._registra_esito(esito)

    def _registra_esito(self, esito) -> str:
        status = getattr(esito, "http_status", None)
        if esito.stato == "inviata":
            if not self._aggiorna({"stato": "inviato", "brevo_http_status": status,
                                   "brevo_message_id": getattr(esito, "message_id", None),
                                   "conclusa_at": self._adesso()}):
                logger.error("Invio %s: email partita ma la riga non era piu' in corso", _breve(self.id))
            return "inviato"
        if esito.stato == "rifiutata" and isinstance(status, int) and 400 <= status < 500:
            self._aggiorna({"stato": "errore", "brevo_http_status": status,
                            "motivo": f"brevo_rifiutata_http_{status}", "conclusa_at": self._adesso()})
            self._rimuovi_caricati()
            self._avviso(f"⚠️ Invio al commercialista rifiutato da Brevo ({self._intestazione()}): HTTP {status}")
            return "errore"
        self._aggiorna({"stato": "esito_incerto", "brevo_http_status": status, "motivo": "brevo_esito_incerto"})
        return "esito_incerto"


def esegui_richiesti(sb, dip: Dipendenze) -> List[str]:
    esiti: List[str] = []
    for _ in range(RIGHE_PER_CICLO):
        riga = prendi_richiesto(sb, dip.orologio())
        if riga is None:
            break
        esiti.append(_Invio(sb, riga, dip).esegui())
    return esiti


# ── Righe appese, avvisi sugli esiti incerti ────────────────────────────────

def gestisci_appese(sb, dip: Dipendenze) -> int:
    adesso = dip.orologio()
    appese = (
        sb.table(INVII).select("id,email_tentata_at,storage_paths")
        .eq("stato", "in_corso").lt("iniziata_at", _iso(adesso - APPESA_DOPO))
        .order("iniziata_at").limit(50).execute().data or []
    )
    for riga in appese:
        if riga.get("email_tentata_at") is None:
            chiusa = (
                sb.table(INVII).update({"stato": "errore", "motivo": "interrotto", "conclusa_at": _iso(adesso)})
                .eq("id", riga["id"]).eq("stato", "in_corso").execute().data
            )
            if chiusa and riga.get("storage_paths"):
                try:
                    dip.archivio(sb).rimuovi(riga["storage_paths"])
                    sb.table(INVII).update({"file_rimossi_at": _iso(adesso)}).eq("id", riga["id"]).execute()
                except Exception as exc:
                    logger.warning("Invio %s: file non rimossi (%s)", _breve(riga["id"]), type(exc).__name__)
        else:
            sb.table(INVII).update({"stato": "esito_incerto", "motivo": "interrotto_dopo_l_email"}) \
                .eq("id", riga["id"]).eq("stato", "in_corso").execute()

    incerte = (
        sb.table(INVII).select("id,config_id,tipo")
        .eq("stato", "esito_incerto").is_("avviso_inviato_at", "null")
        .order("creata_at").limit(50).execute().data or []
    )
    for riga in incerte:
        testo = (
            f"🚨 Invio al commercialista dall'esito incerto (invio {_breve(riga['id'])}, configurazione "
            f"{_breve(riga['config_id'])}, {riga['tipo']}): l'email potrebbe essere partita. Nessun altro "
            "invio per questo cliente finche' non lo chiarisci dall'area admin (log di Brevo)."
        )
        if dip.avvisa(testo):
            sb.table(INVII).update({"avviso_inviato_at": _iso(adesso)}) \
                .eq("id", riga["id"]).eq("stato", "esito_incerto").execute()
    return len(appese)


# ── Pulizia degli ZIP ───────────────────────────────────────────────────────

def rimuovi_file_scaduti(sb, archivio, adesso: datetime) -> int:
    """Guidata dal registro: un giorno dopo la scadenza del link."""
    righe = (
        sb.table(INVII).select("id,storage_paths")
        .not_.is_("storage_paths", "null").is_("file_rimossi_at", "null")
        .lt("link_scade_il", _iso(adesso - RIMOZIONE_DOPO_SCADENZA))
        .order("link_scade_il").limit(100).execute().data or []
    )
    rimossi = 0
    for riga in righe:
        archivio.rimuovi(riga["storage_paths"])
        sb.table(INVII).update({"file_rimossi_at": _iso(adesso)}).eq("id", riga["id"]).execute()
        rimossi += len(riga["storage_paths"])
    return rimossi


def rimuovi_file_del_cliente(sb, user_id: str, archivio=None) -> int:
    """Alla cancellazione dell'account gli ZIP non aspettano la scadenza del link:
    la privacy promette che se ne va tutto. Va chiamata PRIMA di cancellare
    `users`: dopo, il registro non dice piu' quali file erano suoi."""
    righe = (
        sb.table(INVII).select("id,storage_paths")
        .eq("user_id", user_id).not_.is_("storage_paths", "null").is_("file_rimossi_at", "null")
        .execute().data or []
    )
    percorsi = [percorso for riga in righe for percorso in (riga.get("storage_paths") or [])]
    if percorsi:
        (archivio or ArchivioSupabase(sb)).rimuovi(percorsi)
        sb.table(INVII).update({"file_rimossi_at": _iso(adesso_utc())}) \
            .in_("id", [riga["id"] for riga in righe]).execute()
    return len(percorsi)


def _file_vecchi(archivio, prefisso: str, soglia: datetime, profondita: int) -> List[str]:
    vecchi: List[str] = []
    for voce in archivio.elenca(prefisso):
        nome = voce.get("name")
        if not nome:
            continue
        percorso = f"{prefisso}/{nome}" if prefisso else nome
        if voce.get("id") is None:
            if profondita > 0:
                vecchi += _file_vecchi(archivio, percorso, soglia, profondita - 1)
            continue
        creato = voce.get("created_at")
        if creato and _istante(creato) < soglia:
            vecchi.append(percorso)
    return vecchi


def spazza_bucket(archivio, adesso: datetime) -> int:
    """Rete sotto il registro: la cancellazione di una configurazione porta via
    le sue righe, non i suoi file. Nessun file resta oltre ETA_MASSIMA_FILE."""
    vecchi = _file_vecchi(archivio, "", adesso - ETA_MASSIMA_FILE, profondita=2)
    if vecchi:
        archivio.rimuovi(vecchi)
    return len(vecchi)


# ── Il thread ───────────────────────────────────────────────────────────────

def segnala_configurazione() -> None:
    if not invio_attivo():
        logger.info("Invio al commercialista spento (%s diverso da 1): solo prove a vuoto e pulizie", ENV_ATTIVO)
        return
    mancanti = []
    if not os.getenv("BREVO_API_KEY", "").strip():
        mancanti.append("BREVO_API_KEY")
    if not (os.getenv("INVOICETRONIC_EXPORT_KEY") or os.getenv("INVOICETRONIC_API_KEY") or "").strip():
        mancanti.append("INVOICETRONIC_EXPORT_KEY o INVOICETRONIC_API_KEY")
    if mancanti:
        logger.error("Invio al commercialista acceso ma mancano: %s. Gli invii finiranno in errore.",
                     ", ".join(mancanti))


def ciclo(sb, dip: Dipendenze) -> List[str]:
    adesso = dip.orologio()
    gestisci_appese(sb, dip)
    if invio_attivo() and e_finestra_notturna(a_roma(adesso)):
        pianifica(sb, adesso, dip.avvisa)
    return esegui_richiesti(sb, dip)


def pulizia(sb, dip: Dipendenze) -> None:
    """Le due pulizie sono indipendenti: la spazzata e' la rete sotto il registro,
    e deve girare anche quando la pulizia guidata dal registro fallisce."""
    archivio = dip.archivio(sb)
    adesso = dip.orologio()
    for nome, passo in (("registro", lambda: rimuovi_file_scaduti(sb, archivio, adesso)),
                        ("spazzata", lambda: spazza_bucket(archivio, adesso))):
        try:
            passo()
        except Exception as exc:
            logger.warning("Invio commercialista: pulizia ZIP (%s) fallita (%s)", nome, type(exc).__name__)


def avvia_thread(get_client: Callable[[], Any], dip: Optional[Dipendenze] = None,
                 dormi: Callable[[float], None] = time.sleep,
                 fermo: Optional[threading.Event] = None) -> threading.Thread:
    """Il thread del queue-worker. Non muore mai per un errore: aspetta di piu'
    (fino a un'ora) e riprova, cosi' una tabella che manca non riempie i log."""
    fermo = fermo or threading.Event()

    def corpo() -> None:
        d = dip or dipendenze_reali()
        segnala_configurazione()
        ultima_pulizia: Optional[float] = None
        errori = 0
        while not fermo.is_set():
            try:
                sb = get_client()
                ciclo(sb, d)
                errori = 0
                if ultima_pulizia is None or time.monotonic() - ultima_pulizia >= PULIZIA_OGNI_S:
                    ultima_pulizia = time.monotonic()
                    try:
                        pulizia(sb, d)
                    except Exception as exc:
                        logger.warning("Invio commercialista: pulizia ZIP fallita (%s)", type(exc).__name__)
                attesa = INTERVALLO_S
            except Exception as exc:
                errori += 1
                attesa = min(INTERVALLO_S * 2 ** min(errori, 6), ATTESA_MASSIMA_S)
                logger.warning("Invio commercialista: ciclo fallito (%s), riprovo fra %ss",
                               type(exc).__name__, attesa)
            dormi(attesa)

    thread = threading.Thread(target=corpo, name="invio-commercialista", daemon=True)
    thread.start()
    return thread

