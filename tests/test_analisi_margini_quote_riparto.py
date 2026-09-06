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


# ───────────────────────────────────────────────────────────────────────────
# get_analisi_centri e l'override "modalita' mensile" (audit 06/09)
#
# Chi inserisce il fatturato come totale del mese ha margini_mensili.
# fatturato_netto a ZERO: i ricavi veri vivono in ricavi_modalita_mensile.
# `get_analisi_centri` leggeva solo lo snapshot, mentre `get_analisi_avanzata`
# — stesso file, stessa pagina — fondeva gia' l'override: due tab della stessa
# schermata Margini davano fatturati diversi sugli stessi mesi. Misurato il
# 06/09 a DB: una sede con snapshot 0,00 su 9 mesi su 9 e ~292.000 EUR di
# ricavi reali nell'override.
#
# I test chiamano l'ENDPOINT, non la formula: un test che ricalcola il conto
# sopravvive al mutante.
# ───────────────────────────────────────────────────────────────────────────
import services.routers.margini as margini


def _patch_centri(saved_rows, overrides, costi_per_cat):
    """Isola l'endpoint da auth/DB lasciando vivo il calcolo che si vuole provare."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.gte.return_value = q
    q.lte.return_value = q
    q.in_.return_value = q
    q.execute.return_value = MagicMock(data=saved_rows or [])
    client = MagicMock()
    client.table.return_value = q
    return patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
        _load_fatture_fb_for_period=MagicMock(return_value=dict(costi_per_cat)),
        _load_mensile_overrides=MagicMock(return_value=dict(overrides)),
    )


def test_analisi_centri_vede_il_fatturato_in_modalita_mensile():
    """Snapshot a zero + override valorizzato: il fatturato NON puo' uscire 0.

    Numeri scritti a mano, non ricalcolati: 11.000/1.10 + 12.200/1.22 + 500
    = 10.000 + 10.000 + 500 = 20.500.
    """
    with _patch_centri(
        saved_rows=[{"anno": 2026, "mese": 3, "fatturato_netto": 0.0}],
        overrides={(2026, 3): {"iva10": 11000.0, "iva22": 12200.0, "altri": 500.0}},
        costi_per_cat={"CARNE": 4500.0},
    ):
        resp = margini.get_analisi_centri("2026-03-01", "2026-03-31", authorization="Bearer x")

    # Le COMPONENTI, non solo il totale: due errori opposti quadrano la somma.
    assert resp.fatturato_netto_periodo == 20500.0
    assert resp.totale_costi_fb == 4500.0
    assert resp.primo_margine == 16000.0
    assert resp.mesi_con_dati == [3], "il mese ha ricavi: non puo' risultare senza dati"


def test_analisi_centri_senza_override_usa_lo_snapshot():
    """Il fallback resta quello di prima: chi non e' in modalita' mensile non cambia."""
    with _patch_centri(
        saved_rows=[{"anno": 2026, "mese": 3, "fatturato_netto": 8000.0}],
        overrides={},
        costi_per_cat={"CARNE": 3000.0},
    ):
        resp = margini.get_analisi_centri("2026-03-01", "2026-03-31", authorization="Bearer x")

    assert resp.fatturato_netto_periodo == 8000.0
    assert resp.primo_margine == 5000.0
    assert resp.mesi_con_dati == [3]


def test_analisi_centri_override_ha_la_precedenza_sullo_snapshot():
    """Snapshot valorizzato E override presente: vince l'override.

    Se vincesse lo snapshot il totale sarebbe 999,0: il test lo esclude.
    """
    with _patch_centri(
        saved_rows=[{"anno": 2026, "mese": 5, "fatturato_netto": 999.0}],
        overrides={(2026, 5): {"iva10": 2200.0, "iva22": 0.0, "altri": 0.0}},
        costi_per_cat={},
    ):
        resp = margini.get_analisi_centri("2026-05-01", "2026-05-31", authorization="Bearer x")

    assert resp.fatturato_netto_periodo == 2000.0


def test_analisi_centri_e_avanzata_danno_lo_stesso_fatturato():
    """La rete vera: i due tab della stessa pagina, sugli stessi dati.

    E' il presidio che impedisce al prossimo fix di essere di nuovo parziale —
    la divergenza fra questi due endpoint e' gia' costata un fatturato a zero.
    """
    saved = [{"anno": 2026, "mese": 3, "fatturato_netto": 0.0}]
    overrides = {(2026, 3): {"iva10": 11000.0, "iva22": 12200.0, "altri": 500.0}}

    with _patch_centri(saved, overrides, {"CARNE": 4500.0}):
        centri = margini.get_analisi_centri("2026-03-01", "2026-03-31", authorization="Bearer x")

    with _patch_centri(saved, overrides, {"CARNE": 4500.0}), \
            patch.object(margini, "_load_fatture_fb_per_categoria_e_mese",
                         MagicMock(return_value={(2026, 3, "CARNE"): 4500.0})):
        avanzata = margini.get_analisi_avanzata("2026-03-01", "2026-03-31", authorization="Bearer x")

    assert centri.fatturato_netto_periodo == avanzata.fatturato_netto_periodo
    assert centri.primo_margine == avanzata.primo_margine
