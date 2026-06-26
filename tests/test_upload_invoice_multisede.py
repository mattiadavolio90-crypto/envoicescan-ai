"""Gating dello smistamento multi-sede nell'upload manuale.

L'endpoint /api/upload/invoice e' async con molte dipendenze (parser, salvataggio,
streamlit): qui si testa la logica DECISIONALE nuova in isolamento —
  - _upload_e_multisede_stessa_piva: quando si attiva lo smistamento
  - _carica_sedi_attive_per_user: query sedi
La decisione di routing vera e propria e' coperta da test_multisede_routing.py;
lo smistamento end-to-end su XML reali si verifica caricando le fatture del cliente.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from services.fastapi_worker import (
    _carica_sedi_attive_per_user,
    _upload_e_multisede_stessa_piva,
)


# ─── _upload_e_multisede_stessa_piva: gating ──────────────────────────────────

def test_gating_due_sedi_stessa_piva_attiva():
    sedi = [
        {"id": "a", "partita_iva": "07863990961", "indirizzo_match": "via losanna 46 20154 milano"},
        {"id": "b", "partita_iva": "07863990961", "indirizzo_match": "via settembrini 36 20124 milano"},
    ]
    assert _upload_e_multisede_stessa_piva(sedi) is True


def test_gating_una_sola_sede_non_attiva():
    sedi = [{"id": "a", "partita_iva": "07863990961", "indirizzo_match": "x"}]
    assert _upload_e_multisede_stessa_piva(sedi) is False


def test_gating_due_sedi_piva_diverse_non_attiva():
    # Stesso account, sedi con P.IVA diverse: NON e' lo scenario indirizzo-discriminante.
    sedi = [
        {"id": "a", "partita_iva": "11111111111", "indirizzo_match": "x"},
        {"id": "b", "partita_iva": "22222222222", "indirizzo_match": "y"},
    ]
    assert _upload_e_multisede_stessa_piva(sedi) is False


def test_gating_piva_mancante_non_attiva():
    sedi = [
        {"id": "a", "partita_iva": None, "indirizzo_match": "x"},
        {"id": "b", "partita_iva": "", "indirizzo_match": "y"},
    ]
    assert _upload_e_multisede_stessa_piva(sedi) is False


def test_gating_tre_sedi_due_condividono_attiva():
    sedi = [
        {"id": "a", "partita_iva": "07863990961", "indirizzo_match": "x"},
        {"id": "b", "partita_iva": "07863990961", "indirizzo_match": "y"},
        {"id": "c", "partita_iva": "99999999999", "indirizzo_match": "z"},
    ]
    assert _upload_e_multisede_stessa_piva(sedi) is True


# ─── _carica_sedi_attive_per_user: query ──────────────────────────────────────

def _sb_sedi(data):
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=data)
    return sb


def test_carica_sedi_ritorna_lista():
    data = [{"id": "a", "nome_ristorante": "PUB", "partita_iva": "0786", "indirizzo_match": "via x"}]
    out = _carica_sedi_attive_per_user("u1", _sb_sedi(data))
    assert out == data


def test_carica_sedi_errore_ritorna_vuoto():
    sb = MagicMock()
    sb.table.side_effect = RuntimeError("DB giu'")
    assert _carica_sedi_attive_per_user("u1", sb) == []
