"""Test _load_fatture_fb_for_period / _load_fatture_fb_per_categoria_e_mese
(services.fastapi_worker): il costo per categoria del tab Analisi margini deve
includere le quote dei costi di gruppo, come il tab Calcolo.

Prima del fix, il 1° Margine del tab Analisi (services/routers/margini.py:687,
`primo_margine = fatturato_netto_periodo - totale_costi_fb`) non includeva le
quote di riparto perche' queste due funzioni leggevano solo le fatture della
sede, mai la sede tecnica. Due tab della stessa pagina Margini mostravano un
1° Margine diverso per lo stesso periodo.
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


def _mock_sb_vuoto():
    """sb.table(...).select(...)... .execute() -> nessuna riga reale."""
    sb = MagicMock()
    resp = MagicMock()
    resp.data = []
    sb.table.return_value.select.return_value.eq.return_value.is_.return_value \
        .neq.return_value.gte.return_value.lte.return_value.range.return_value \
        .execute.return_value = resp
    return sb


def test_costo_per_categoria_include_la_quota_di_gruppo():
    sb = _mock_sb_vuoto()
    quota = [{"categoria": "CARNE", "totale_riga": 500.0, "data_documento": "2026-07-15"}]
    with patch.object(fw, "_righe_quote_gruppo", return_value=quota):
        out = fw._load_fatture_fb_for_period(sb, "rid-catena", "2026-07-01", "2026-07-31")
    assert out == {"CARNE": 500.0}


def test_costo_per_categoria_e_mese_include_la_quota_di_gruppo():
    sb = _mock_sb_vuoto()
    quota = [{"categoria": "CARNE", "totale_riga": 500.0, "data_documento": "2026-07-15"}]
    with patch.object(fw, "_righe_quote_gruppo", return_value=quota):
        out = fw._load_fatture_fb_per_categoria_e_mese(sb, "rid-catena", "2026-07-01", "2026-07-31")
    assert out == {(2026, 7, "CARNE"): 500.0}


def test_sede_mono_senza_quote_comportamento_invariato():
    sb = _mock_sb_vuoto()
    with patch.object(fw, "_righe_quote_gruppo", return_value=[]):
        out = fw._load_fatture_fb_for_period(sb, "rid-mono", "2026-07-01", "2026-07-31")
    assert out == {}
