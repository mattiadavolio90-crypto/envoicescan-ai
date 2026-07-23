"""Test dell'endpoint GET /api/riparto/anteprima-coda (services/routers/riparto.py).

Anteprima riga-per-riga di una fattura ancora in coda 'da_assegnare' (non ancora
collocata su un locale). Riusa estrai_dati_da_xml() in SOLA LETTURA (user_id=None):
qui verifichiamo solo il WIRING dell'endpoint — parsing/categorizzazione reali sono
testati altrove (test di invoice_service.py). Verifichiamo:
  - riga trovata + xml_content presente → chiama estrai_dati_da_xml con user_id=None
    (niente memoria personalizzata, niente scritture) e ritorna le righe mappate;
  - queue_id non trovato o non del chiamante o non 'da_assegnare' → 404;
  - xml_content assente → {disponibile: False, righe: []} (nessun errore);
  - parsing fallito (eccezione) → {disponibile: False, righe: []}, non propaga.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        if self._t == "fatture_queue":
            return SimpleNamespace(data=self._c.queue_rows)
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, queue_rows):
        self.queue_rows = queue_rows

    def table(self, name):
        return _Query(self, name)


_RIGA_OK = {
    "id": 42, "user_id": "user-1", "status": "da_assegnare",
    "xml_content": "<xml>finto</xml>",
    "payload_meta": {"nome_file": "IT123_abc.xml"},
}

_RIGHE_PARSATE = [
    {
        "Numero_Riga": 1, "Descrizione": "Coca Cola 1L", "Quantita": 12.0,
        "Unita_Misura": "PZ", "Prezzo_Unitario": 1.5, "IVA_Percentuale": 22.0,
        "Totale_Riga": 18.0, "Categoria": "BEVANDE",
    },
]


def _patch(queue_rows):
    sb = _FakeSB(queue_rows)
    return sb, patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
    )


def test_anteprima_ok_chiama_parser_sola_lettura():
    sb, p = _patch([_RIGA_OK])
    with p, patch("services.invoice_service.estrai_dati_da_xml") as mock_parse:
        mock_parse.return_value = _RIGHE_PARSATE
        out = riparto.riparto_anteprima_coda(queue_id=42, authorization="Bearer x")

    assert out["disponibile"] is True
    assert len(out["righe"]) == 1
    assert out["righe"][0]["descrizione"] == "Coca Cola 1L"
    assert out["righe"][0]["totale_riga"] == 18.0
    # user_id=None: niente memoria personalizzata, niente scritture (vedi docstring
    # estrai_dati_da_xml — carica_memoria_completa/flush sono no-op senza user_id).
    _, kwargs = mock_parse.call_args
    assert kwargs.get("user_id") is None


def test_queue_id_non_trovato_404():
    sb, p = _patch([])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_anteprima_coda(queue_id=999, authorization="Bearer x")
    assert exc.value.status_code == 404


def test_xml_assente_ritorna_non_disponibile():
    riga = dict(_RIGA_OK)
    riga["xml_content"] = None
    sb, p = _patch([riga])
    with p:
        out = riparto.riparto_anteprima_coda(queue_id=42, authorization="Bearer x")
    assert out == {"righe": [], "disponibile": False, "motivo": "assente"}


def test_parsing_fallito_non_propaga():
    sb, p = _patch([_RIGA_OK])
    with p, patch("services.invoice_service.estrai_dati_da_xml") as mock_parse:
        mock_parse.side_effect = RuntimeError("XML malformato")
        out = riparto.riparto_anteprima_coda(queue_id=42, authorization="Bearer x")
    assert out == {"righe": [], "disponibile": False, "motivo": "illeggibile"}
