"""Difesa dei 2 punti di services/upload_handler.py toccati dalla remediation
Performance HIGH (0bed331, 3/8): `response = query.execute(); rows = response.data or []`
sostituito da `rows = fetch_all(query)` per non troncare a 1000 righe (limite PostgREST).

I test NON verificano che il codice "chiami fetch_all" (forma): verificano che, davanti
a una fonte che tronca come fa PostgREST, il risultato visto da _collect_post_upload_quality_checks
e _run_post_upload_ai_categorization resti completo oltre la millesima riga.
"""
from unittest.mock import patch

from services.upload_handler import (
    _collect_post_upload_quality_checks,
    _run_post_upload_ai_categorization,
)


class FakePostgrest:
    """Query-builder che si comporta come PostgREST: senza `.range()` non
    restituisce mai piu' di `max_rows` righe, e non segnala il troncamento."""

    def __init__(self, rows, max_rows=1000):
        self._rows = rows
        self._max_rows = max_rows
        self._range = None
        self.eq_filters = {}

    def table(self, *_a, **_k):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, campo=None, valore=None, *_a, **_k):
        if campo is not None:
            self.eq_filters[campo] = valore
        return self

    def is_(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._range is None:
            rows = self._rows[: self._max_rows]
        else:
            start, end = self._range
            rows = self._rows[start: min(end + 1, start + self._max_rows)]
        return type("R", (), {"data": rows})()


def _quality_row(prezzo=1.0, needs_review=False, categoria="ALIMENTARI"):
    return {
        "file_origine": "f.xml",
        "prezzo_unitario": prezzo,
        "categoria": categoria,
        "needs_review": needs_review,
        "descrizione": "PASTA",
    }


class TestCollectPostUploadQualityChecksPaginazione:
    def test_rows_saved_conta_tutte_le_righe_oltre_1000(self):
        righe = [_quality_row() for _ in range(1500)]
        client = FakePostgrest(righe)

        checks = _collect_post_upload_quality_checks(client, "u1", ["f.xml"])

        assert checks["verification_ok"] is True
        assert checks["rows_saved"] == 1500

    def test_contatori_qualita_visti_su_tutte_le_pagine(self):
        righe = [_quality_row() for _ in range(1500)]
        # una riga "sospetta" nella prima pagina, una nella seconda
        righe[500] = _quality_row(prezzo=0.0, needs_review=True, categoria="Da Classificare")
        righe[1200] = _quality_row(prezzo=0.0, needs_review=True, categoria="Da Classificare")
        client = FakePostgrest(righe)

        checks = _collect_post_upload_quality_checks(client, "u1", ["f.xml"])

        assert checks["zero_price_rows"] == 2
        assert checks["needs_review_rows"] == 2
        assert checks["uncategorized_rows"] == 2

    def test_paginazione_completa_anche_con_ristorante_id(self):
        """Il ramo multi-sede: add_ristorante_filter aggiunge .eq('ristorante_id')
        PRIMA di fetch_all. E' il ramo che gira in produzione per i clienti con
        piu' sedi, e va paginato come l'altro."""
        righe = [_quality_row() for _ in range(1500)]
        client = FakePostgrest(righe)

        checks = _collect_post_upload_quality_checks(
            client, "u1", ["f.xml"], ristorante_id="r1"
        )

        # senza questa asserzione il test passerebbe anche se il filtro sede
        # non fosse mai stato applicato
        assert client.eq_filters.get("ristorante_id") == "r1"
        assert checks["rows_saved"] == 1500

    def test_supabase_client_none_ritorna_default_senza_verificare(self):
        checks = _collect_post_upload_quality_checks(None, "u1", ["f.xml"])
        assert checks["verification_ok"] is False
        assert checks["rows_saved"] == 0

    def test_file_names_vuoto_ritorna_default_senza_verificare(self):
        client = FakePostgrest([_quality_row()])
        checks = _collect_post_upload_quality_checks(client, "u1", [])
        assert checks["verification_ok"] is False
        assert checks["rows_saved"] == 0


class TestRunPostUploadAiCategorizationPaginazione:
    def _row_non_eligible(self):
        # descrizione vuota -> _should_skip_post_upload_ai_for_row ritorna
        # True/'dati_insufficienti': la riga resta "unresolved" ma non chiama l'AI.
        return {
            "id": 1,
            "descrizione": "",
            "fornitore": "",
            "iva_percentuale": 0,
            "prezzo_unitario": 0,
            "totale_riga": 0,
            "quantita": 0,
            "categoria": "Da Classificare",
            "needs_review": True,
            "tipo_documento": "TD01",
            "file_origine": "f.xml",
        }

    @patch("services.upload_handler.carica_memoria_completa", return_value=None)
    @patch("services.upload_handler.invalida_cache_memoria", return_value=None)
    def test_rows_scanned_conta_le_righe_non_classificate_oltre_1000(self, _mock_inv, _mock_mem):
        righe = [self._row_non_eligible() for _ in range(1500)]
        client = FakePostgrest(righe)

        summary = _run_post_upload_ai_categorization(client, "u1", ["f.xml"])

        assert summary["rows_scanned"] == 1500
        assert summary["completed"] is True

    @patch("services.upload_handler.carica_memoria_completa", return_value=None)
    @patch("services.upload_handler.invalida_cache_memoria", return_value=None)
    def test_paginazione_completa_anche_con_ristorante_id(self, _mock_inv, _mock_mem):
        righe = [self._row_non_eligible() for _ in range(1500)]
        client = FakePostgrest(righe)

        summary = _run_post_upload_ai_categorization(
            client, "u1", ["f.xml"], ristorante_id="r1"
        )

        assert client.eq_filters.get("ristorante_id") == "r1"
        assert summary["rows_scanned"] == 1500

    def test_supabase_client_none_ritorna_summary_default(self):
        summary = _run_post_upload_ai_categorization(None, "u1", ["f.xml"])
        assert summary["rows_scanned"] == 0
        assert summary["completed"] is False

    def test_user_id_vuoto_ritorna_summary_default(self):
        client = FakePostgrest([self._row_non_eligible()])
        summary = _run_post_upload_ai_categorization(client, "", ["f.xml"])
        assert summary["rows_scanned"] == 0
        assert summary["completed"] is False
