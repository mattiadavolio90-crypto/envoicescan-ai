"""Client Invoicetronic per l'invio degli XML al commercialista (fase B del piano).

Solo letture, e ognuna controllata: una lista vuota o incompleta scambiata per
«periodo senza fatture» consumerebbe il periodo per sempre, quindi qui un dubbio
e' un errore, mai un risultato vuoto.

- La chiave deve essere di produzione (`ik_live_`): con `ik_test_` si leggerebbe la
  Sandbox, dove i documenti restano 24 ore — liste vuote e plausibili.
  INVOICETRONIC_EXPORT_KEY (sotto-chiave in sola lettura, facoltativa) ha la
  precedenza su INVOICETRONIC_API_KEY.
- La lista e' tutta l'azienda, senza filtri di data (`date_sent` puo' essere
  nulla, e le fatture trattenute prima che l'azienda esista vengono rielaborate
  molto dopo): ordinata dalla piu' recente, senza doppioni, e il numero di id
  deve tornare con l'intestazione Invoicetronic-Total-Count. Il periodo si
  sceglie dopo, su `created`, in giorni di Roma.
- Il documento si scarica in JSON (include_payload): la variante text/plain
  sarebbe decodificata come ISO-8859-1 e gli accenti cambierebbero il file.
- 429 → si aspetta Retry-After (massimo 60 s, 5 volte); 403 del saldo →
  SaldoInvoicetronicEsaurito; 5xx e rete → 3 tentativi; 400/401/403/422 sono
  errori di configurazione, da dire subito e senza ritentare.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from services.invoicetronic_saldo import SaldoInvoicetronicEsaurito, codice_problema, e_saldo_esaurito

API_BASE_DEFAULT = "https://api.invoicetronic.com/v1"
PREFISSO_LIVE = "ik_live_"
PAGINA = 200
PAGINE_MASSIME = 500
RITMO_S = 0.5
ATTESA_429_MAX_S = 60
TENTATIVI_429 = 5
ATTESE_RETE_S = (2, 8, 30)
LETTURE_ELENCO = 3
INTESTAZIONE_TOTALE = "Invoicetronic-Total-Count"

_HOST_CONSENTITI = {"invoicetronic.com", "api.invoicetronic.com"}
_SUFFISSO_CONSENTITO = ".invoicetronic.com"


class ErroreInvoicetronic(Exception):
    """Una risposta che non si puo' usare. `configurazione` = colpa nostra (chiave,
    permessi, parametri): ritentare la notte dopo non serve, va detto subito."""

    def __init__(self, motivo: str, status: Optional[int] = None, codice: Optional[str] = None,
                 configurazione: bool = False) -> None:
        super().__init__(motivo)
        self.status = status
        self.codice = codice
        self.configurazione = configurazione


def _chiave_dall_ambiente() -> str:
    return (os.environ.get("INVOICETRONIC_EXPORT_KEY") or os.environ.get("INVOICETRONIC_API_KEY") or "").strip()


def _base_dall_ambiente() -> str:
    base = os.environ.get("INVOICETRONIC_API_BASE", API_BASE_DEFAULT).rstrip("/")
    parsed = urlparse(base)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host in _HOST_CONSENTITI or host.endswith(_SUFFISSO_CONSENTITO)):
        raise ErroreInvoicetronic("host dell'API non consentito", configurazione=True)
    return base


def data_roma(istante: Any) -> date:
    """Il giorno di Roma di un istante Invoicetronic (UTC ISO, fino a 7 decimali)."""
    from zoneinfo import ZoneInfo

    if isinstance(istante, datetime):
        dt = istante
    else:
        dt = datetime.fromisoformat(str(istante).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Europe/Rome")).date()


def _attesa_retry_after(valore: Optional[str]) -> float:
    try:
        secondi = float(valore) if valore is not None else 0.0
    except ValueError:
        secondi = 0.0
    return min(max(secondi, 1.0), ATTESA_429_MAX_S)


class ClientInvoicetronic:
    def __init__(self, chiave: Optional[str] = None, *, http: Any = None,
                 dormi: Callable[[float], None] = time.sleep,
                 orologio: Callable[[], float] = time.monotonic) -> None:
        chiave = (chiave if chiave is not None else _chiave_dall_ambiente()).strip()
        if not chiave:
            raise ErroreInvoicetronic("chiave Invoicetronic assente", configurazione=True)
        if not chiave.startswith(PREFISSO_LIVE):
            raise ErroreInvoicetronic("la chiave Invoicetronic non e' di produzione (ik_live_)", configurazione=True)
        self._base = _base_dall_ambiente()
        if http is None:
            import httpx

            http = httpx.Client(
                auth=(chiave, ""),
                headers={"Accept": "application/json"},
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=False,
            )
        self._http = http
        self._dormi = dormi
        self._orologio = orologio
        self._ultima: Optional[float] = None

    def chiudi(self) -> None:
        chiudi = getattr(self._http, "close", None)
        if callable(chiudi):
            chiudi()

    def _rispetta_ritmo(self) -> None:
        if self._ultima is not None:
            mancante = RITMO_S - (self._orologio() - self._ultima)
            if mancante > 0:
                self._dormi(mancante)
        self._ultima = self._orologio()

    def _get(self, percorso: str, params: Optional[Dict[str, Any]] = None):
        tentativi_429 = 0
        tentativi_rete = 0
        while True:
            self._rispetta_ritmo()
            try:
                resp = self._http.get(f"{self._base}{percorso}", params=params)
            except Exception as exc:
                if tentativi_rete < len(ATTESE_RETE_S):
                    self._dormi(ATTESE_RETE_S[tentativi_rete])
                    tentativi_rete += 1
                    continue
                raise ErroreInvoicetronic(f"Invoicetronic non raggiungibile ({type(exc).__name__})") from None
            status = resp.status_code
            if status == 200:
                return resp
            if status == 429:
                if tentativi_429 >= TENTATIVI_429:
                    raise ErroreInvoicetronic("troppe richieste (429) anche dopo le attese", status=429)
                self._dormi(_attesa_retry_after(resp.headers.get("Retry-After")))
                tentativi_429 += 1
                continue
            if e_saldo_esaurito(status, resp.content):
                raise SaldoInvoicetronicEsaurito("saldo Invoicetronic esaurito (usage_limit_exceeded)")
            if status >= 500:
                if tentativi_rete < len(ATTESE_RETE_S):
                    self._dormi(ATTESE_RETE_S[tentativi_rete])
                    tentativi_rete += 1
                    continue
                raise ErroreInvoicetronic(f"Invoicetronic in errore (HTTP {status})", status=status)
            codice = codice_problema(resp.content)
            raise ErroreInvoicetronic(
                f"HTTP {status}" + (f" {codice}" if codice else ""), status=status, codice=codice,
                configurazione=status in (400, 401, 403, 422),
            )

    def _json(self, resp, tipo: type) -> Any:
        try:
            dati = resp.json()
        except Exception:
            raise ErroreInvoicetronic("risposta non JSON") from None
        if not isinstance(dati, tipo):
            raise ErroreInvoicetronic("risposta di forma inattesa")
        return dati

    def _azienda(self, percorso: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._get(percorso)
        except ErroreInvoicetronic as exc:
            if exc.status == 404:
                return None
            raise
        dati = self._json(resp, dict)
        if not isinstance(dati.get("id"), int) or isinstance(dati.get("id"), bool):
            raise ErroreInvoicetronic("azienda senza id")
        return dati

    def azienda_per_piva(self, piva: str) -> Optional[Dict[str, Any]]:
        """GET /company/IT<piva>: sempre col prefisso, perche' /company/{vat} e
        /company/{id} sono lo stesso percorso. None se non esiste."""
        if not (len(piva) == 11 and piva.isdigit()):
            raise ErroreInvoicetronic("P.IVA non di 11 cifre", configurazione=True)
        azienda = self._azienda(f"/company/IT{piva}")
        if azienda is not None and str(azienda.get("vat") or "").upper() != f"IT{piva}":
            raise ErroreInvoicetronic("Invoicetronic ha restituito un'azienda con un'altra P.IVA")
        return azienda

    def azienda(self, company_id: int) -> Optional[Dict[str, Any]]:
        return self._azienda(f"/company/{int(company_id)}")

    def elenco_ricevute(self, company_id: int) -> List[Dict[str, Any]]:
        """Tutti i documenti ricevuti dall'azienda, dal piu' recente. Vale solo una
        lettura in cui il totale dichiarato resta lo stesso su tutte le pagine e
        torna coi documenti letti: una fattura arrivata (o cancellata) a meta'
        sposta le pagine, e allora si rilegge da capo. Solleva se la lista non e'
        completa, non e' ordinata come chiesto, o non si ferma mai."""
        for _ in range(LETTURE_ELENCO):
            documenti, totali = self._leggi_elenco(company_id)
            if len(set(totali)) == 1 and len(documenti) == totali[0]:
                return documenti
        raise ErroreInvoicetronic(
            f"elenco instabile o incompleto dopo {LETTURE_ELENCO} letture: "
            f"{len(documenti)} documenti contro {totali[0]}..{totali[-1]} dichiarati"
        )

    def _leggi_elenco(self, company_id: int) -> tuple[List[Dict[str, Any]], List[int]]:
        visti: Dict[int, Dict[str, Any]] = {}
        totali: List[int] = []
        precedente: Optional[datetime] = None
        for pagina in range(1, PAGINE_MASSIME + 1):
            resp = self._get("/receive", {
                "company_id": int(company_id), "page": pagina, "page_size": PAGINA, "sort": "-created",
            })
            try:
                totali.append(int(resp.headers[INTESTAZIONE_TOTALE]))
            except (KeyError, ValueError):
                raise ErroreInvoicetronic(f"intestazione {INTESTAZIONE_TOTALE} assente") from None
            documenti = self._json(resp, list)
            if not documenti:
                break
            for doc in documenti:
                if not isinstance(doc, dict) or not isinstance(doc.get("id"), int) or isinstance(doc.get("id"), bool):
                    raise ErroreInvoicetronic("documento senza id")
                try:
                    creato = datetime.fromisoformat(str(doc["created"]).replace("Z", "+00:00"))
                except Exception:
                    raise ErroreInvoicetronic("documento senza data di arrivo") from None
                if creato.tzinfo is None:
                    creato = creato.replace(tzinfo=timezone.utc)
                if precedente is not None and creato > precedente:
                    raise ErroreInvoicetronic("elenco non ordinato come richiesto")
                precedente = creato
                visti.setdefault(doc["id"], doc)
        else:
            raise ErroreInvoicetronic("elenco oltre il numero massimo di pagine")
        return list(visti.values()), totali

    def documento(self, receive_id: int) -> Dict[str, Any]:
        resp = self._get(f"/receive/{int(receive_id)}", {"include_payload": "true"})
        dati = self._json(resp, dict)
        if dati.get("id") != receive_id or not isinstance(dati.get("payload"), str) or not dati["payload"]:
            raise ErroreInvoicetronic("documento senza contenuto")
        return dati
