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
