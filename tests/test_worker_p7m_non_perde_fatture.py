"""Regressione: una fattura il cui XML non è leggibile non deve sparire.

CAUSA RADICE (agosto 2026, OFFSIDE): la Edge Function, fallito lo sbustamento
P7M, salvava in `xml_content` la busta binaria grezza. Il parser esplodeva,
`estrai_dati_da_xml` ingoiava l'eccezione e ritornava `[]`, il worker leggeva
`[]` come "fattura valida senza righe" e chiudeva l'item `done` PURGANDO l'XML.
Due fatture TOYOTA sono sparite senza traccia lasciando un riparto orfano
(+531,76 € di costo fantasma).

La catena che qui si verifica, anello per anello:
  1. `estrai_dati_da_xml` ritorna None (non []) quando il documento non è letto;
  2. `_xml_pare_fattura` distingue una FatturaPA vera da una busta grezza;
  3. `_process_item` va in retry (XML conservato) invece che done+purge;
  4. una fattura valida SENZA righe resta `done` — la guardia non deve
     trasformare un caso legittimo in retry infiniti.
"""
import io
from unittest import mock

import pytest

from worker import queue_processor as qp


XML_VALIDO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<ns0:FatturaElettronica xmlns:ns0="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
    "<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA>"
    "<IdPaese>IT</IdPaese><IdCodice>07863990961</IdCodice></IdFiscaleIVA></DatiAnagrafici>"
    "</CessionarioCommittente></FatturaElettronicaHeader>"
    "<FatturaElettronicaBody></FatturaElettronicaBody>"
    "</ns0:FatturaElettronica>"
)

# Busta P7M non sbustata, come finiva in xml_content: binario con i NUL già
# rimossi dalla Edge Function (payload_sanitized='null_bytes_removed').
BUSTA_GREZZA = "0\x82%\x06\t*\x86H\xde\xad\xbe\xef1\x0f"


# ─── _xml_pare_fattura ───────────────────────────────────────────────────────

def test_xml_valido_riconosciuto():
    assert qp._xml_pare_fattura(XML_VALIDO) is True


def test_busta_grezza_non_e_fattura():
    assert qp._xml_pare_fattura(BUSTA_GREZZA) is False


def test_xml_troncato_non_e_fattura():
    # Contiene il tag ma non è well-formed: è il caso peggiore, perché una
    # ricerca per sottostringa lo promuoverebbe a documento valido.
    assert qp._xml_pare_fattura('<?xml version="1.0"?><FatturaElettronica><rotto>') is False


def test_vuoto_e_none_non_sono_fatture():
    assert qp._xml_pare_fattura(None) is False
    assert qp._xml_pare_fattura("") is False


def test_accetta_bytes():
    assert qp._xml_pare_fattura(XML_VALIDO.encode("utf-8")) is True


# ─── _process_item: 0 righe ──────────────────────────────────────────────────

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


def test_busta_grezza_zero_righe_va_in_retry_non_done():
    """Il caso TOYOTA: se chiudesse `done` l'XML verrebbe purgato e la fattura persa."""
    with mock.patch.object(qp, "estrai_dati_da_xml", return_value=[]), \
         mock.patch.object(qp, "_fetch_xml_via_api", return_value=None):
        res = qp._process_item(mock.MagicMock(), _item(BUSTA_GREZZA, resource_id=96551))

    assert res.status == "retry", "un documento non letto non va archiviato come done"
    assert "non è una FatturaPA valida" in (res.error or "")


def test_fattura_valida_senza_righe_resta_done():
    """Guardia anti-regressione: il caso legittimo non deve diventare retry."""
    with mock.patch.object(qp, "estrai_dati_da_xml", return_value=[]):
        res = qp._process_item(mock.MagicMock(), _item(XML_VALIDO))

    assert res.status == "done"
    assert res.righe == 0


def test_parser_ritorna_none_va_in_retry():
    with mock.patch.object(qp, "estrai_dati_da_xml", return_value=None):
        res = qp._process_item(mock.MagicMock(), _item(XML_VALIDO))

    assert res.status == "retry"


# ─── _process_item: recupero dell'XML sano prima del parsing ─────────────────

def test_busta_grezza_recuperata_via_api_viene_parsata():
    """Con l'XML recuperato dall'API la fattura si salva: nessuna perdita."""
    visti = {}

    def _parser(file_like, user_id=None):
        visti["xml"] = file_like.read().decode("utf-8")
        return [{"Fornitore": "TOYOTA", "totale_riga": 431.01}]

    sb = mock.MagicMock()
    with mock.patch.object(qp, "estrai_dati_da_xml", side_effect=_parser), \
         mock.patch.object(qp, "_fetch_xml_via_api", return_value=XML_VALIDO), \
         mock.patch.object(qp, "_claim_ancora_valido", return_value=True), \
         mock.patch.object(qp, "salva_fattura_processata", return_value={"success": True, "righe": 1}), \
         mock.patch.object(qp, "_auto_classify_saved_rows", return_value=(1, 0)), \
         mock.patch.object(qp, "_mark_ripartita_se_sede_tecnica", return_value=None), \
         mock.patch.object(qp, "_advance_nuovi_da_daily", return_value=None):
        res = qp._process_item(sb, _item(BUSTA_GREZZA, resource_id=96551))

    assert "<IdCodice>07863990961</IdCodice>" in visti["xml"], \
        "il parser deve ricevere l'XML recuperato, non la busta grezza"
    assert res.status == "done"


def test_flag_p7m_extract_failed_forza_il_recupero():
    """Anche se xml_content sembrasse leggibile, il flag della Edge Function vince."""
    with mock.patch.object(qp, "estrai_dati_da_xml", return_value=[]), \
         mock.patch.object(qp, "_fetch_xml_via_api", return_value=None) as fetch:
        qp._process_item(mock.MagicMock(), _item(XML_VALIDO, resource_id=96551, p7m_extract_failed=True))

    assert fetch.called, "p7m_extract_failed deve innescare il riscarico via API"


def test_xml_valido_non_innesca_recupero_inutile():
    with mock.patch.object(qp, "estrai_dati_da_xml", return_value=[]), \
         mock.patch.object(qp, "_fetch_xml_via_api", return_value=None) as fetch:
        qp._process_item(mock.MagicMock(), _item(XML_VALIDO, resource_id=96551))

    assert not fetch.called, "un XML già valido non deve costare una chiamata API"
