"""Unit test per il fallback API del worker (_fetch_xml_via_api).

Copre il recupero XML di secondo livello quando la Edge Function non ha salvato
l'XML e xml_url e' assente (es. 404 transitorio Invoicetronic). Non richiede rete:
urllib e' mockato.
"""
import base64
import io
import json
from unittest import mock

import pytest

from worker import queue_processor as qp


def _fake_response(body: str):
    """Context-manager fittizio che imita urllib.request.urlopen()."""
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = body.encode("utf-8")
    cm.__exit__.return_value = False
    return cm


def test_no_api_key_returns_none(monkeypatch):
    monkeypatch.delenv("INVOICETRONIC_API_KEY", raising=False)
    assert qp._fetch_xml_via_api(12345) is None


def test_blank_resource_id_returns_none(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    assert qp._fetch_xml_via_api(None) is None
    assert qp._fetch_xml_via_api("") is None
    assert qp._fetch_xml_via_api("   ") is None


def test_ssrf_block_on_malicious_base(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setenv("INVOICETRONIC_API_BASE", "https://evil.example.com/v1")
    # Ricarica la costante derivata dall'env
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://evil.example.com/v1")
    with mock.patch("urllib.request.urlopen") as m:
        assert qp._fetch_xml_via_api(123) is None
        m.assert_not_called()  # bloccato PRIMA di qualsiasi I/O


def test_payload_plain_xml(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")
    body = json.dumps({"payload": "<FatturaElettronica>OK</FatturaElettronica>", "encoding": "Xml"})
    with mock.patch("urllib.request.urlopen", return_value=_fake_response(body)):
        out = qp._fetch_xml_via_api(123)
    assert out == "<FatturaElettronica>OK</FatturaElettronica>"


def test_payload_base64(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")
    xml = "<FatturaElettronica>àèì</FatturaElettronica>"
    b64 = base64.b64encode(xml.encode("utf-8")).decode()
    body = json.dumps({"payload": b64, "encoding": "Base64"})
    with mock.patch("urllib.request.urlopen", return_value=_fake_response(body)):
        out = qp._fetch_xml_via_api(123)
    assert out == xml


def test_xml_file_base64(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")
    xml = "<FatturaElettronica>X</FatturaElettronica>"
    b64 = base64.b64encode(xml.encode("utf-8")).decode()
    body = json.dumps({"xml_file": b64})
    with mock.patch("urllib.request.urlopen", return_value=_fake_response(body)):
        out = qp._fetch_xml_via_api(123)
    assert out == xml


def _make_chunked_der_p7m(xml: str, chunk_len: int = 40) -> bytes:
    """Busta P7M "a chunk DER": XML in un Constructed OCTET STRING (0x24 0x80)
    spezzato in chunk primitivi 0x04 <len> <dati>, chiuso da end-of-contents 0x00 0x00.
    È la variante CAdES che il decode UTF-8 diretto corromperebbe."""
    xml_bytes = xml.encode("utf-8")
    head = bytes([0x30, 0x82, 0x25, 0x00, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x24, 0x80])
    parts = bytearray(head)
    for i in range(0, len(xml_bytes), chunk_len):
        chunk = xml_bytes[i:i + chunk_len]
        parts += bytes([0x04, len(chunk)]) + chunk
    parts += bytes([0x00, 0x00])  # end-of-contents
    parts += bytes([0x31, 0x0f, 0x00, 0xde, 0xad, 0xbe, 0xef])  # coda binaria firma
    return bytes(parts)


def test_payload_base64_p7m_chunked_der(monkeypatch):
    # Rigenerazione del bug OFFSIDE: p7m "a chunk DER" scaricato via fallback API.
    # Prima il decode UTF-8 diretto lasciava gli header DER dentro i tag (XML
    # corrotto); ora _bytes_to_xml_str delega a estrai_xml_da_p7m e riassembla.
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
        '<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA>'
        '<IdPaese>IT</IdPaese><IdCodice>00484960588</IdCodice></IdFiscaleIVA></DatiAnagrafici>'
        '</CessionarioCommittente></FatturaElettronicaHeader>'
        '<FatturaElettronicaBody></FatturaElettronicaBody></p:FatturaElettronica>'
    )
    p7m = _make_chunked_der_p7m(xml, chunk_len=40)
    b64 = base64.b64encode(p7m).decode()
    body = json.dumps({"payload": b64, "encoding": "Base64"})
    with mock.patch("urllib.request.urlopen", return_value=_fake_response(body)):
        out = qp._fetch_xml_via_api(123)
    assert out is not None
    # XML ricomposto: nessun byte di controllo residuo, P.IVA intatta.
    assert "<IdCodice>00484960588</IdCodice>" in out
    assert "FatturaElettronica" in out
    for ch in out:
        assert ord(ch) >= 32 or ch in "\t\n\r", "nessun control char residuo nell'XML"


def test_response_without_xml_returns_none(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")
    body = json.dumps({"id": 123, "file_name": "x.xml"})  # nessun payload/xml_file/xml_url
    with mock.patch("urllib.request.urlopen", return_value=_fake_response(body)):
        out = qp._fetch_xml_via_api(123)
    assert out is None


def test_http_error_returns_none(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "k")
    monkeypatch.setattr(qp, "_INVOICETRONIC_API_BASE", "https://api.invoicetronic.com/v1")
    with mock.patch("urllib.request.urlopen", side_effect=Exception("HTTP 404")):
        out = qp._fetch_xml_via_api(123)
    assert out is None
