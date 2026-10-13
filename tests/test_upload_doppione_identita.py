"""Il doppione per identita' esce dall'upload come quello per nome.

Due guardie anti-doppione: per NOME (`fastapi_worker`, prima del parsing) e per
IDENTITA' (stesso fornitore+numero+data+tipo sotto un altro nome, dentro
`salva_fattura_processata`). La prima rispondeva `ALREADY_LOADED:<file>` e la
finestra la mostrava «scartata»; la seconda tornava `duplicate_document` e la
finestra la mostrava in rosso, «non caricata», con l'avviso di chiusura. Il caso
tipico e' il download doppio del browser: `X (1).xml` e `X.xml` (screen di
Mattia del 12/10/2026, CASATI 14).

Il test attraversa l'endpoint vero con le sole dipendenze esterne finte.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import services
from services import fastapi_worker as fw
from services import invoice_service

XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<FatturaElettronica><FatturaElettronicaHeader/></FatturaElettronica>"
)


class _CatenaSupabase:
    """Ogni metodo ritorna se stesso; `execute()` non trova mai niente: la
    guardia per NOME non scatta, si arriva a quella per identita'."""

    data = []
    count = 0

    def __getattr__(self, nome):
        def _metodo(*args, **kwargs):
            return self
        return _metodo

    def execute(self):
        return self


def _endpoint(monkeypatch, esito_salvataggio):
    utente = {"id": "utente-dup", "email": "cliente@dup.test", "pagine_abilitate": {}}
    sede = {
        "id": "sede-dup", "nome_ristorante": "CASATI 14", "partita_iva": "",
        "indirizzo_match": "", "bypass_guardia_piva": False,
    }
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda authorization: utente)
    monkeypatch.setattr(services, "get_supabase_client", lambda: _CatenaSupabase())
    monkeypatch.setattr(fw, "_carica_sedi_attive_per_user", lambda user_id, sb: [sede])
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda user, sb: sede["id"])
    monkeypatch.setattr(
        invoice_service, "estrai_dati_da_xml",
        lambda file_like, user_id=None, **k: [
            {"Data_Documento": "2026-09-30", "Descrizione": "ARANCE", "Totale_Riga": 25.0}
        ],
    )
    monkeypatch.setattr(invoice_service, "salva_fattura_processata", lambda *a, **k: esito_salvataggio)
    client = TestClient(fw.app)
    return client.post(
        "/api/upload/invoice",
        files={"file": ("IT01879020517A2026_g7KVL.xml", XML, "text/xml")},
        headers={"Authorization": "Bearer prova"},
    )


def test_il_doppione_per_identita_risponde_come_quello_per_nome(monkeypatch):
    risposta = _endpoint(monkeypatch, {
        "success": False, "error": "duplicate_document", "righe": 0,
        "location": None, "duplicate_of": "IT01879020517A2026_g7KVL (1).xml",
    })

    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["success"] is False
    assert corpo["error"] == "ALREADY_LOADED:IT01879020517A2026_g7KVL (1).xml", corpo["error"]
    assert corpo["righe_salvate"] == 0


def test_il_doppione_senza_duplicate_of_resta_uno_scarto(monkeypatch):
    """Un result senza `duplicate_of` non deve tornare a essere un errore."""
    corpo = _endpoint(monkeypatch, {"success": False, "error": "duplicate_document", "righe": 0}).json()

    assert corpo["error"].startswith("ALREADY_LOADED:"), corpo["error"]


@pytest.mark.parametrize("errore", ["no_data", "missing_ristorante_id", "boom"])
def test_un_errore_vero_resta_un_errore(monkeypatch, errore):
    """Controllo positivo: solo il doppione cambia veste."""
    corpo = _endpoint(monkeypatch, {"success": False, "error": errore, "righe": 0}).json()

    assert corpo["success"] is False
    assert corpo["error"] == errore
