"""La policy sulle date dell'upload decide col giorno di Roma, non con quello del server (L6).

Railway e Vercel vivono in UTC. Fra mezzanotte e le 02:00 ora italiana `date.today()`
sul server e' ancora ieri: il primo del mese, per un'ora o due, la policy «mese
corrente + precedente» ammetteva un mese che a Roma era gia' scaduto, e il messaggio
di blocco nominava i mesi sbagliati. `valuta_policy_data` e `messaggio_blocco`
accettano `oggi`: l'endpoint deve passare `_oggi_rome()`, che nel file c'era gia'.

Il test attraversa l'endpoint vero (`/api/upload/invoice`) con le sole dipendenze
esterne finte: e' il call site che si prova, non la libreria.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import services
from services import fastapi_worker as fw
from services import invoice_service, upload_policy

XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<FatturaElettronica><FatturaElettronicaHeader/></FatturaElettronica>"
)
ROMA_OGGI = date(2026, 3, 1)      # 00:30 del primo marzo a Roma...
UTC_OGGI = date(2026, 2, 28)      # ...mentre il server e' ancora al 28 febbraio


class _DataDelServer(date):
    @classmethod
    def today(cls):
        return UTC_OGGI


class _CatenaSupabase:
    """Ogni metodo ritorna se stesso; `execute()` non trova mai niente."""

    data = []
    count = 0

    def __getattr__(self, nome):
        def _metodo(*args, **kwargs):
            return self
        return _metodo

    def execute(self):
        return self


@pytest.fixture
def endpoint(monkeypatch):
    salvataggi = []
    utente = {
        "id": "utente-l6",
        "email": "cliente@l6.test",
        "pagine_abilitate": {"blocco_mesi_precedenti": True},
    }
    sede = {
        "id": "sede-l6", "nome_ristorante": "Sede L6", "partita_iva": "",
        "indirizzo_match": "", "bypass_guardia_piva": False,
    }
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda authorization: utente)
    monkeypatch.setattr(services, "get_supabase_client", lambda: _CatenaSupabase())
    monkeypatch.setattr(fw, "_carica_sedi_attive_per_user", lambda user_id, sb: [sede])
    monkeypatch.setattr(fw, "_get_ristorante_id_for_user", lambda user_id, sb: sede["id"])
    monkeypatch.setattr(
        invoice_service, "estrai_dati_da_xml",
        lambda file_like, user_id=None, **k: [
            {"Data_Documento": "2026-01-15", "Descrizione": "ARTICOLO", "Totale_Riga": 10.0}
        ],
    )
    monkeypatch.setattr(
        invoice_service, "salva_fattura_processata",
        lambda *a, **k: salvataggi.append((a, k)) or {"success": True, "righe_salvate": 1},
    )
    monkeypatch.setattr(upload_policy, "date", _DataDelServer)
    monkeypatch.setattr(fw, "_oggi_rome", lambda: ROMA_OGGI)
    return TestClient(fw.app), salvataggi


def _carica(client):
    return client.post(
        "/api/upload/invoice",
        files={"file": ("fattura-gennaio.xml", XML, "text/xml")},
        headers={"Authorization": "Bearer prova"},
    )


def test_il_primo_del_mese_alle_00_30_la_policy_e_gia_nel_mese_nuovo(endpoint):
    """Una fattura di gennaio caricata il primo marzo (ora italiana) non passa,
    anche se per il server e' ancora febbraio e gennaio sarebbe «il mese precedente»."""
    client, salvataggi = endpoint

    risposta = _carica(client)

    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["success"] is False
    assert corpo["error"].startswith("MESE NON CONSENTITO"), corpo["error"]
    assert salvataggi == [], "la fattura di gennaio e' stata salvata"


def test_il_messaggio_di_blocco_nomina_i_mesi_di_roma(endpoint):
    """Il cliente legge i mesi ammessi cosi' come sono per lui: Febbraio o Marzo,
    non Gennaio o Febbraio come li vede il server."""
    client, _ = endpoint

    errore = _carica(client).json()["error"]

    assert "Febbraio 2026" in errore and "Marzo 2026" in errore, errore
    assert "Gennaio" not in errore, errore


def test_la_libreria_da_sola_userebbe_il_giorno_del_server(monkeypatch):
    """Controllo positivo: senza `oggi` la policy legge `date.today()` (UTC) e
    ammette gennaio. E' il comportamento che il call site deve evitare."""
    monkeypatch.setattr(upload_policy, "date", _DataDelServer)

    assert upload_policy.valuta_policy_data(
        "2026-01-15", {"blocco_mesi_precedenti": True},
    ) is None
    assert upload_policy.valuta_policy_data(
        "2026-01-15", {"blocco_mesi_precedenti": True}, oggi=ROMA_OGGI,
    ) == upload_policy.BLOCCO_MESE
