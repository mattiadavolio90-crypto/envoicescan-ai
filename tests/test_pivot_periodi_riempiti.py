"""Le colonne della pivot coprono l'arco, non i soli periodi con righe.

Il difetto: `periodi` nasceva dai soli periodi CON fatture, quindi un mese
senza acquisti spariva dalla tabella. A schermo si leggeva «Gen, Mar, Apr»
come una serie continua — colonne e sparkline le trattano come equidistanti
nel tempo — e il cliente non aveva modo di accorgersi del buco.
"""
import pytest

from services.routers.fatture import _espandi_periodi, _scegli_granularita


class TestEspandiPeriodiMese:
    def test_febbraio_compare(self):
        # Il caso visto a schermo: febbraio manca perche' non ci sono fatture.
        assert _espandi_periodi(["2026-01", "2026-03"], "mese") == [
            "2026-01", "2026-02", "2026-03",
        ]

    def test_buco_lungo_piu_mesi(self):
        assert _espandi_periodi(["2026-01", "2026-06"], "mese") == [
            "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
        ]

    def test_attraversa_il_capodanno(self):
        assert _espandi_periodi(["2025-11", "2026-02"], "mese") == [
            "2025-11", "2025-12", "2026-01", "2026-02",
        ]

    def test_non_estende_oltre_i_dati(self):
        # Riempie l'INTERNO: non allunga il range fino a oggi o a fine anno.
        out = _espandi_periodi(["2026-03", "2026-05"], "mese")
        assert out[0] == "2026-03" and out[-1] == "2026-05"

    def test_un_solo_periodo_resta_solo(self):
        assert _espandi_periodi(["2026-04"], "mese") == ["2026-04"]

    def test_nessun_periodo(self):
        assert _espandi_periodi([], "mese") == []

    def test_input_non_ordinato(self):
        assert _espandi_periodi(["2026-03", "2026-01"], "mese") == [
            "2026-01", "2026-02", "2026-03",
        ]

    def test_senza_buchi_non_cambia_nulla(self):
        dentro = ["2026-01", "2026-02", "2026-03"]
        assert _espandi_periodi(dentro, "mese") == dentro


class TestEspandiPeriodiTrimestre:
    def test_riempie_i_trimestri(self):
        assert _espandi_periodi(["2026-Q1", "2026-Q4"], "trimestre") == [
            "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4",
        ]

    def test_trimestri_attraverso_l_anno(self):
        assert _espandi_periodi(["2025-Q3", "2026-Q2"], "trimestre") == [
            "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2",
        ]


class TestEspandiPeriodiAnno:
    def test_riempie_gli_anni(self):
        assert _espandi_periodi(["2024", "2026"], "anno") == ["2024", "2025", "2026"]


class TestGranularitaSullArco:
    """La granularita' si sceglie sull'arco coperto, non sui mesi con righe.

    Con due sole fatture lontane nel tempo i mesi presenti sono 2: scegliere
    "mese" e poi riempire produrrebbe decine di colonne mensili.
    """

    def test_due_fatture_a_tre_anni_di_distanza_non_danno_36_colonne(self):
        mesi_presenti = {"2024-01", "2026-12"}
        arco = set(_espandi_periodi(sorted(mesi_presenti), "mese"))
        assert len(arco) == 36
        assert _scegli_granularita(arco) == "trimestre"

    def test_arco_breve_resta_mensile(self):
        mesi_presenti = {"2026-01", "2026-06"}
        arco = set(_espandi_periodi(sorted(mesi_presenti), "mese"))
        assert _scegli_granularita(arco) == "mese"

    def test_arco_oltre_i_tre_anni_passa_ad_anno(self):
        mesi_presenti = {"2020-01", "2026-12"}
        arco = set(_espandi_periodi(sorted(mesi_presenti), "mese"))
        assert len(arco) > 36
        assert _scegli_granularita(arco) == "anno"


# ─────────────────────────────────────────────────────────────────────────────
# L'endpoint vero. I test qui sopra provano `_espandi_periodi`, non il suo USO:
# rimettendo `periodi = sorted(periodi_set)` al call site restavano tutti verdi.
# Il mutante deve somigliare al difetto, e il difetto era proprio al call site.
# ─────────────────────────────────────────────────────────────────────────────
from unittest.mock import MagicMock, patch  # noqa: E402

from services.routers import fatture as fatture_router  # noqa: E402


def _riga(data: str, categoria: str, totale: float) -> dict:
    return {"data_documento": data, "categoria": categoria,
            "fornitore": "FORNITORE X", "totale_riga": totale}


def _pivot_con(rows):
    with patch.multiple(
        fatture_router,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=MagicMock()),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
        _fetch_fatture_rows=MagicMock(return_value=list(rows)),
    ):
        return fatture_router.get_fatture_pivot(
            dimensione="categoria", authorization="Bearer t",
        )


class TestEndpointPivotColonne:
    def test_il_mese_senza_fatture_resta_una_colonna(self):
        """Gen e Mar con acquisti, Feb senza: a schermo erano due colonne
        accostate e la serie si leggeva continua."""
        res = _pivot_con([
            _riga("2026-01-15", "CARNE", 1000.0),
            _riga("2026-03-10", "CARNE", 1200.0),
        ])
        assert res.periodi == ["2026-01", "2026-02", "2026-03"]
        assert "Feb 26" in res.periodi_labels

    def test_il_mese_vuoto_non_inventa_spesa(self):
        res = _pivot_con([
            _riga("2026-01-15", "CARNE", 1000.0),
            _riga("2026-03-10", "CARNE", 1200.0),
        ])
        assert res.totali_periodo["2026-02"] == 0.0
        assert res.grand_total == 2200.0

    def test_la_riga_non_porta_la_chiave_del_mese_vuoto(self):
        # `periodi` dichiara la colonna; la riga resta sparsa e il frontend
        # legge `?? 0`. Inventare una chiave a 0 direbbe "acquisto da 0 EUR".
        res = _pivot_con([
            _riga("2026-01-15", "CARNE", 1000.0),
            _riga("2026-03-10", "CARNE", 1200.0),
        ])
        riga = next(r for r in res.rows if r.dimensione == "CARNE")
        assert "2026-02" not in riga.periodi

    def test_la_sparkline_ha_un_punto_per_colonna(self):
        # Senza riempimento la spezzata saltava il buco e disegnava una
        # pendenza che nei dati non c'e'.
        res = _pivot_con([
            _riga("2026-01-15", "CARNE", 1000.0),
            _riga("2026-04-10", "CARNE", 1200.0),
        ])
        riga = next(r for r in res.rows if r.dimensione == "CARNE")
        assert len(res.periodi) == 4
        assert len(riga.sparkline) == 4
        assert riga.sparkline == [1000.0, 0, 0, 1200.0]

    def test_senza_buchi_le_colonne_non_cambiano(self):
        res = _pivot_con([
            _riga("2026-01-15", "CARNE", 100.0),
            _riga("2026-02-15", "CARNE", 100.0),
        ])
        assert res.periodi == ["2026-01", "2026-02"]

    def test_una_sola_fattura_una_sola_colonna(self):
        res = _pivot_con([_riga("2026-05-15", "CARNE", 100.0)])
        assert res.periodi == ["2026-05"]

    def test_arco_lungo_non_esplode_in_colonne_mensili(self):
        """Due fatture a tre anni di distanza: i mesi CON righe sono 2, ma
        l'arco e' 36 — la granularita' si sceglie sull'arco."""
        res = _pivot_con([
            _riga("2024-01-15", "CARNE", 100.0),
            _riga("2026-12-10", "CARNE", 100.0),
        ])
        assert res.granularita == "trimestre"
        assert len(res.periodi) == 12


def _trend_con(rows, valori=None):
    with patch.multiple(
        fatture_router,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=MagicMock()),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
        _fetch_fatture_rows=MagicMock(return_value=list(rows)),
    ):
        return fatture_router.get_fatture_trend(
            dimensione="categoria", valori=valori, authorization="Bearer t",
        )


class TestEndpointTrendColonne:
    """Il grafico a linee soffre il buco piu' della tabella: un mese assente
    non lascia uno spazio, sposta la PENDENZA fra i due punti che restano."""

    def test_il_mese_vuoto_e_un_punto_a_zero(self):
        res = _trend_con([
            _riga("2026-01-15", "CARNE", 1000.0),
            _riga("2026-03-10", "CARNE", 1200.0),
        ])
        assert res.periodi == ["2026-01", "2026-02", "2026-03"]
        serie = next(s for s in res.serie if s.valore == "CARNE")
        assert [p.valore for p in serie.punti] == [1000.0, 0, 1200.0]

    def test_il_totale_non_cambia(self):
        res = _trend_con([
            _riga("2026-01-15", "CARNE", 1000.0),
            _riga("2026-03-10", "CARNE", 1200.0),
        ])
        serie = next(s for s in res.serie if s.valore == "CARNE")
        assert serie.totale == 2200.0

    def test_arco_lungo_non_esplode(self):
        res = _trend_con([
            _riga("2024-01-15", "CARNE", 100.0),
            _riga("2026-12-10", "CARNE", 100.0),
        ])
        assert len(res.periodi) == 12
