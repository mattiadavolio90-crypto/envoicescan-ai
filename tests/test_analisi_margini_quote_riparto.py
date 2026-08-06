"""Test _load_fatture_fb_for_period / _load_fatture_fb_per_categoria_e_mese
(services.fastapi_worker): il costo per categoria del tab Analisi margini deve
includere le quote dei costi di gruppo, come il tab Calcolo.

Prima del fix, il 1° Margine del tab Analisi (services/routers/margini.py:687,
`primo_margine = fatturato_netto_periodo - totale_costi_fb`) non includeva le
quote di riparto perche' queste due funzioni leggevano solo le fatture della
sede, mai la sede tecnica. Due tab della stessa pagina Margini mostravano un
1° Margine diverso per lo stesso periodo.

Il secondo blocco di test (anti-doppio-conteggio) copre la regressione opposta:
le due funzioni leggevano le righe della sede TECNICA senza escludere
ripartita_su_gruppo=True, a differenza delle funzioni gemelle
_calcola_costi_auto_per_mese/_per_periodo. Il mock qui sotto applica
davvero i filtri .eq()/.neq() alle righe fornite (non e' un mock 'muto' che
ignora i filtri), cosi' se il filtro ripartita_su_gruppo sparisce dal codice
il test fallisce.
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


class _FakeQuery:
    """Applica davvero i filtri .eq()/.neq()/.is_() alle righe fornite, cosi'
    un test che rompe un filtro nel codice reale rompe anche il test."""

    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def neq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) != value]
        return self

    def is_(self, field, value):
        want_null = str(value).lower() == "null"
        self._rows = [r for r in self._rows if (r.get(field) is None) == want_null]
        return self

    def gte(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def range(self, *_a, **_k):
        return self

    def execute(self):
        resp = MagicMock()
        resp.data = self._rows
        return resp


def _mock_sb_con_righe(rows):
    sb = MagicMock()
    sb.table.return_value = _FakeQuery(list(rows))
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


def test_analisi_periodo_esclude_righe_ripartite_su_gruppo():
    """MEDIUM #1 (audit Bug 2026-08-05): una riga ripartita sul gruppo NON deve
    entrare nel tab Analisi Centri, altrimenti diverge dal tab Calcolo che gia'
    la esclude (_calcola_costi_auto_per_mese/_per_periodo)."""
    righe = [
        {"categoria": "CARNE", "totale_riga": 300.0, "data_documento": "2026-07-10",
         "ristorante_id": "rid-tecnica", "deleted_at": None, "ripartita_su_gruppo": True},
        {"categoria": "CARNE", "totale_riga": 100.0, "data_documento": "2026-07-11",
         "ristorante_id": "rid-tecnica", "deleted_at": None, "ripartita_su_gruppo": False},
    ]
    sb = _mock_sb_con_righe(righe)
    with patch.object(fw, "_righe_quote_gruppo", return_value=[]):
        out = fw._load_fatture_fb_for_period(sb, "rid-tecnica", "2026-07-01", "2026-07-31")
    assert out == {"CARNE": 100.0}


def test_analisi_categoria_mese_esclude_righe_ripartite_su_gruppo():
    righe = [
        {"categoria": "CARNE", "totale_riga": 300.0, "data_documento": "2026-07-10",
         "ristorante_id": "rid-tecnica", "deleted_at": None, "ripartita_su_gruppo": True},
        {"categoria": "CARNE", "totale_riga": 100.0, "data_documento": "2026-07-11",
         "ristorante_id": "rid-tecnica", "deleted_at": None, "ripartita_su_gruppo": False},
    ]
    sb = _mock_sb_con_righe(righe)
    with patch.object(fw, "_righe_quote_gruppo", return_value=[]):
        out = fw._load_fatture_fb_per_categoria_e_mese(sb, "rid-tecnica", "2026-07-01", "2026-07-31")
    assert out == {(2026, 7, "CARNE"): 100.0}
