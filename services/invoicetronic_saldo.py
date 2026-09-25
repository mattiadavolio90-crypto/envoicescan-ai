"""Saldo crediti Invoicetronic: lettura, soglia e avvisi Telegram.

Perche' esiste: a saldo zero Invoicetronic risponde 403 `usage_limit_exceeded` a
ogni GET su /receive, anche per documenti gia' scaricati. Il webhook segna la
fattura `failed`, il worker ritenta 8 volte con attese che raddoppiano fino a
un'ora e in circa 2 ore ogni fattura in arrivo diventa `dead` — per TUTTI i
clienti, senza che nessuno lo sappia. Le fatture non sono perse (restano su
Invoicetronic 2 anni): dopo la ricarica quelle ancora in coda ripartono da
sole, quelle gia' `dead` si rimettono in coda con «Riprova». Il worker le
riscarica e, se il webhook non ne aveva letto il cliente, lo decide dall'XML
(services/routing_coda.py, passo 0-bis).

Due strade, indipendenti:
  - controllo periodico di GET /status dal queue-worker (`controlla_saldo`,
    chiamato da worker/run.py ogni 6 ore): avvisa sotto soglia e quando non
    riesce piu' a leggere il saldo;
  - avviso immediato quando un download riceve il 403 del saldo
    (`avvisa_saldo_esaurito`, dal recupero XML del worker; la Edge Function ha
    il suo gemello in TypeScript).

Gli avvisi non portano dati di clienti: Telegram non e' fra i sub-responsabili
dichiarati.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CODICE_SALDO_ESAURITO = "usage_limit_exceeded"
ENV_SOGLIA = "INVOICETRONIC_SOGLIA_OPERAZIONI"
SOGLIA_DEFAULT = 100
API_BASE_DEFAULT = "https://api.invoicetronic.com/v1"

RIPETI_AVVISO_S = 24 * 3600
FALLIMENTI_PRIMO_AVVISO = 2
FALLIMENTI_FRA_AVVISI = 4
RIPETI_AVVISO_403_S = 6 * 3600

_OK, _BASSO, _ESAURITO = 0, 1, 2

_HOST_CONSENTITI = {"invoicetronic.com", "api.invoicetronic.com", "invoicetronic.it"}
_SUFFISSI_CONSENTITI = (".invoicetronic.com", ".invoicetronic.it")


class SaldoIllegibile(Exception):
    """GET /status non ha dato un saldo. Il messaggio e' un motivo breve,
    senza URL ne' chiavi: finisce in un avviso Telegram."""


class SaldoInvoicetronicEsaurito(Exception):
    """Un download e' stato rifiutato per saldo esaurito: non e' un errore
    della singola fattura, e chi chiama deve dirlo cosi'."""


def soglia_configurata() -> int:
    grezzo = os.getenv(ENV_SOGLIA, "").strip()
    if not grezzo:
        return SOGLIA_DEFAULT
    try:
        valore = int(grezzo)
    except ValueError:
        logger.warning("%s=%r non e' un intero: uso %d", ENV_SOGLIA, grezzo, SOGLIA_DEFAULT)
        return SOGLIA_DEFAULT
    if valore < 1:
        logger.warning("%s=%d non ha senso: uso %d", ENV_SOGLIA, valore, SOGLIA_DEFAULT)
        return SOGLIA_DEFAULT
    return valore


def codice_problema(corpo: Any) -> Optional[str]:
    """Il campo `code` di una risposta problem-details, o None. Non solleva:
    un corpo illeggibile vuol dire solo che il codice non c'e'."""
    try:
        if isinstance(corpo, (bytes, bytearray)):
            corpo = corpo.decode("utf-8", errors="replace")
        if isinstance(corpo, str):
            corpo = json.loads(corpo)
    except Exception:
        return None
    if not isinstance(corpo, dict):
        return None
    codice = corpo.get("code")
    return codice if isinstance(codice, str) else None


def e_saldo_esaurito(status_code: Any, corpo: Any) -> bool:
    """403 con `code` = usage_limit_exceeded. La specifica chiede di decidere sul
    codice, non sul testo (`detail` e' tradotto secondo Accept-Language) ne' sul
    solo 403, che Invoicetronic usa anche per le firme e le sotto-chiavi."""
    return status_code == 403 and codice_problema(corpo) == CODICE_SALDO_ESAURITO


def _url_status() -> str:
    base = os.environ.get("INVOICETRONIC_API_BASE", API_BASE_DEFAULT).rstrip("/")
    url = f"{base}/status"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().strip()
    if parsed.scheme != "https" or not (host in _HOST_CONSENTITI or host.endswith(_SUFFISSI_CONSENTITI)):
        raise SaldoIllegibile("host dell'API non consentito")
    return url


def leggi_saldo(*, timeout: float = 10.0) -> int:
    """Operazioni rimaste sull'account (GET /status → operation_left).
    Solleva SaldoIllegibile con un motivo breve in ogni altro caso."""
    import httpx

    api_key = os.environ.get("INVOICETRONIC_API_KEY", "")
    if not api_key:
        raise SaldoIllegibile("INVOICETRONIC_API_KEY assente")
    url = _url_status()
    try:
        resp = httpx.get(url, auth=(api_key, ""), headers={"Accept": "application/json"}, timeout=timeout)
    except Exception as exc:
        raise SaldoIllegibile(f"chiamata fallita ({type(exc).__name__})") from None
    if e_saldo_esaurito(resp.status_code, resp.content):
        return 0
    if resp.status_code != 200:
        codice = codice_problema(resp.content)
        raise SaldoIllegibile(f"HTTP {resp.status_code}" + (f" {codice}" if codice else ""))
    try:
        dati = resp.json()
    except Exception:
        raise SaldoIllegibile("risposta non JSON") from None
    rimaste = dati.get("operation_left") if isinstance(dati, dict) else None
    if isinstance(rimaste, bool) or not isinstance(rimaste, int):
        raise SaldoIllegibile("risposta senza operation_left")
    return rimaste


def consumo_ultimi_30_giorni(sb) -> Optional[int]:
    """Documenti arrivati dallo SDI negli ultimi 30 giorni: il ritmo con cui il
    saldo scende (si paga il primo download di ogni documento)."""
    from datetime import datetime, timedelta, timezone

    da = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    resp = (
        sb.table("fatture_queue")
        .select("id", count="exact", head=True)
        .eq("source", "invoicetronic")
        .gte("created_at", da)
        .execute()
    )
    conteggio = getattr(resp, "count", None)
    return conteggio if isinstance(conteggio, int) else None


def _invia_telegram(testo: str) -> bool:
    from services.telegram_service import invia_messaggio

    return invia_messaggio(testo)


def testo_saldo_basso(rimaste: int, soglia: int, consumo_30gg: Optional[int]) -> str:
    righe = [f"⚠️ Saldo Invoicetronic basso: {rimaste} operazioni rimaste (soglia {soglia})."]
    if consumo_30gg:
        giorni = rimaste * 30 // consumo_30gg
        righe.append(
            f"Negli ultimi 30 giorni sono arrivate {consumo_30gg} fatture: "
            f"al ritmo attuale bastano circa {giorni} giorni."
        )
    righe.append("Ricarica dal dashboard Invoicetronic.")
    return "\n".join(righe)


def testo_saldo_esaurito(rimaste: int) -> str:
    return (
        f"🚨 Saldo Invoicetronic ESAURITO ({rimaste} operazioni).\n"
        "Le fatture in arrivo non si scaricano piu' e in circa 2 ore finiscono in errore.\n"
        "Dopo la ricarica: quelle finite in errore si rimettono in coda con Riprova (Admin → Flusso dati), runbook incidenti §4bis."
    )


def testo_saldo_rientrato(rimaste: int) -> str:
    return f"✅ Saldo Invoicetronic di nuovo sopra soglia: {rimaste} operazioni rimaste."


def testo_saldo_illeggibile(fallimenti: int, motivo: str) -> str:
    return (
        f"⚠️ Non riesco a leggere il saldo Invoicetronic da {fallimenti} controlli di fila "
        f"(ultimo motivo: {motivo}).\n"
        "Senza questo controllo un saldo a zero fermerebbe l'arrivo delle fatture senza avviso.\n"
        "Verifica INVOICETRONIC_API_KEY sul servizio queue-worker."
    )


class SorveglianzaSaldo:
    """Decide quando avvisare, fra un controllo e l'altro.

    - sotto soglia: avvisa subito, poi al massimo una volta ogni 24 ore;
    - se il livello peggiora (da basso a esaurito) avvisa subito, senza aspettare;
    - tornato sopra soglia dopo un avviso: lo dice, una volta;
    - saldo illeggibile: avvisa al secondo controllo fallito di fila, poi ogni 4
      (con un controllo ogni 6 ore: dopo 12 ore, poi una volta al giorno).

    Un avviso che Telegram non consegna non conta come dato: si ritenta al
    controllo successivo. Lo stato vive nel processo: un riavvio del worker puo'
    ripetere un avviso ancora valido, mai perderne uno.
    """

    def __init__(
        self,
        soglia: int,
        *,
        invia: Callable[[str], bool] = _invia_telegram,
        orologio: Callable[[], float] = time.time,
    ) -> None:
        self.soglia = soglia
        self._invia = invia
        self._orologio = orologio
        self._livello_avvisato = _OK
        self._ultimo_avviso: Optional[float] = None
        self._fallimenti = 0

    def _livello(self, rimaste: int) -> int:
        if rimaste <= 0:
            return _ESAURITO
        if rimaste < self.soglia:
            return _BASSO
        return _OK

    def registra_lettura(self, rimaste: int, consumo_30gg: Optional[int] = None) -> Optional[str]:
        """Ritorna il testo dell'avviso inviato, o None se non ne serviva uno."""
        self._fallimenti = 0
        livello = self._livello(rimaste)
        adesso = self._orologio()

        if livello == _OK:
            if self._livello_avvisato == _OK:
                return None
            testo = testo_saldo_rientrato(rimaste)
            logger.info("saldo Invoicetronic rientrato sopra soglia: %d", rimaste)
            if self._invia(testo):
                self._livello_avvisato = _OK
                self._ultimo_avviso = None
                return testo
            return None

        testo = testo_saldo_esaurito(rimaste) if livello == _ESAURITO else testo_saldo_basso(rimaste, self.soglia, consumo_30gg)
        logger.warning("saldo Invoicetronic sotto soglia: %d operazioni (soglia %d)", rimaste, self.soglia)
        peggiorato = livello > self._livello_avvisato
        scaduto = self._ultimo_avviso is None or adesso - self._ultimo_avviso >= RIPETI_AVVISO_S
        if not (peggiorato or scaduto):
            return None
        if self._invia(testo):
            self._livello_avvisato = livello
            self._ultimo_avviso = adesso
            return testo
        return None

    def registra_fallimento(self, motivo: str) -> Optional[str]:
        self._fallimenti += 1
        logger.error("saldo Invoicetronic illeggibile (%d di fila): %s", self._fallimenti, motivo)
        oltre = self._fallimenti - FALLIMENTI_PRIMO_AVVISO
        if oltre < 0 or oltre % FALLIMENTI_FRA_AVVISI != 0:
            return None
        testo = testo_saldo_illeggibile(self._fallimenti, motivo)
        return testo if self._invia(testo) else None


def controlla_saldo(sorveglianza: SorveglianzaSaldo, sb) -> Optional[str]:
    """Un giro del controllo periodico. Non solleva."""
    try:
        rimaste = leggi_saldo()
    except SaldoIllegibile as exc:
        return sorveglianza.registra_fallimento(str(exc))
    logger.info("saldo Invoicetronic: %d operazioni rimaste", rimaste)
    consumo = None
    if rimaste < sorveglianza.soglia:
        try:
            consumo = consumo_ultimi_30_giorni(sb)
        except Exception as exc:
            logger.warning("consumo Invoicetronic degli ultimi 30 giorni non disponibile: %s", exc)
    return sorveglianza.registra_lettura(rimaste, consumo)


_lock_403 = threading.Lock()
_ultimo_avviso_403: Optional[float] = None


def avvisa_saldo_esaurito(origine: str, *, orologio: Callable[[], float] = time.time) -> bool:
    """Avviso immediato su un 403 del saldo, al massimo uno ogni 6 ore per
    processo: con il saldo a zero OGNI tentativo di ogni fattura riceve il 403."""
    global _ultimo_avviso_403
    adesso = orologio()
    with _lock_403:
        if _ultimo_avviso_403 is not None and adesso - _ultimo_avviso_403 < RIPETI_AVVISO_403_S:
            return False
        testo = (
            "🚨 Invoicetronic ha rifiutato un download per saldo esaurito "
            f"({CODICE_SALDO_ESAURITO}, origine: {origine}).\n"
            "Le fatture in arrivo non si scaricano piu'.\n"
            "Dopo la ricarica: quelle finite in errore si rimettono in coda con Riprova (Admin → Flusso dati), runbook incidenti §4bis."
        )
        logger.error("Invoicetronic: download rifiutato per saldo esaurito (origine %s)", origine)
        if _invia_telegram(testo):
            _ultimo_avviso_403 = adesso
            return True
        return False
