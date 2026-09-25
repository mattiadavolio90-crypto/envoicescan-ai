"""Worker: un download rifiutato per saldo Invoicetronic esaurito (passo 0, 25/09/2026).

Prima il recupero via API ingoiava ogni errore e ritornava None: con il saldo a
zero la fattura andava in retry con «API fallita» fino a `dead`, senza avviso e
senza dire perche'. Ora il 403 `usage_limit_exceeded` solleva un errore dedicato,
parte l'avviso Telegram e il motivo arriva fino a last_error — negli unici due
punti che chiamano il recupero.
"""
from __future__ import annotations

import io
import urllib.error
from unittest import mock

import pytest

from services.invoicetronic_saldo import SaldoInvoicetronicEsaurito
from worker import queue_processor as qp


def _http_error(status: int, corpo: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.invoicetronic.com/v1/receive/96551?include_payload=true",
        status, "errore", {}, io.BytesIO(corpo),
    )


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")


def test_403_saldo_esaurito_solleva_e_avvisa(api):
    errore = _http_error(403, b'{"status": 403, "code": "usage_limit_exceeded"}')
    with mock.patch("urllib.request.urlopen", side_effect=errore), \
         mock.patch.object(qp, "avvisa_saldo_esaurito") as avvisa:
        with pytest.raises(SaldoInvoicetronicEsaurito, match="usage_limit_exceeded"):
            qp._fetch_xml_via_api(96551)
    avvisa.assert_called_once_with("worker")


@pytest.mark.parametrize("status,corpo", [
    (403, b'{"code": "signature_limit_exceeded"}'),
    (403, b"Forbidden"),
    (404, b'{"code": "usage_limit_exceeded"}'),
    (500, b""),
])
def test_altri_errori_http_restano_none_senza_avviso(api, status, corpo):
    with mock.patch("urllib.request.urlopen", side_effect=_http_error(status, corpo)), \
         mock.patch.object(qp, "avvisa_saldo_esaurito") as avvisa:
        assert qp._fetch_xml_via_api(96551) is None
    avvisa.assert_not_called()


def test_corpo_dell_errore_illeggibile_resta_none(api):
    errore = _http_error(403, b"")
    errore.read = mock.MagicMock(side_effect=OSError("stream chiuso"))
    with mock.patch("urllib.request.urlopen", side_effect=errore), \
         mock.patch.object(qp, "avvisa_saldo_esaurito") as avvisa:
        assert qp._fetch_xml_via_api(96551) is None
    avvisa.assert_not_called()


# ─── I due punti che chiamano il recupero ────────────────────────────────────

XML_VALIDO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<ns0:FatturaElettronica xmlns:ns0="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
    "<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA>"
    "<IdPaese>IT</IdPaese><IdCodice>07863990961</IdCodice></IdFiscaleIVA></DatiAnagrafici>"
    "</CessionarioCommittente></FatturaElettronicaHeader>"
    "<FatturaElettronicaBody></FatturaElettronicaBody>"
    "</ns0:FatturaElettronica>"
)


def _item(xml_content, **meta):
    return {
        "id": 673,
        "event_id": "evt-test",
        "user_id": "2f3f93a1-c1f4-4804-858e-a161e6f36f3f",
        "ristorante_id": "f7bba05f-90a8-4f12-94ed-4d8a08a0bbae",
        "xml_content": xml_content,
        "xml_url": None,
        "piva_raw": "07863990961",
        "attempt_count": 1,
        "payload_meta": {"nome_file": "IT02355260981_gsm0f.xml.p7m", **meta},
    }


_ESAURITO = SaldoInvoicetronicEsaurito("saldo Invoicetronic esaurito (usage_limit_exceeded): dopo la ricarica riparte da sola; se e' gia' dead, Riprova (runbook incidenti §4bis)")


def test_xml_assente_e_saldo_esaurito_va_in_retry_col_motivo():
    with mock.patch.object(qp, "_scarica_via_api", side_effect=_ESAURITO), \
         mock.patch.object(qp, "estrai_dati_da_xml") as parser:
        res = qp._process_item(mock.MagicMock(), _item(None, resource_id=96551))
    assert res.status == "retry"
    assert "usage_limit_exceeded" in (res.error or "")
    parser.assert_not_called()


def test_xml_da_recuperare_e_saldo_esaurito_va_in_retry_senza_parsare_la_busta():
    with mock.patch.object(qp, "_fetch_xml_via_api", side_effect=_ESAURITO), \
         mock.patch.object(qp, "estrai_dati_da_xml") as parser:
        res = qp._process_item(
            mock.MagicMock(), _item(XML_VALIDO, resource_id=96551, p7m_extract_failed=True),
        )
    assert res.status == "retry"
    assert "usage_limit_exceeded" in (res.error or "")
    parser.assert_not_called()
