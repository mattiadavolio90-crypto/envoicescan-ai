"""Il pool dei suggerimenti Tag non puo' fermarsi alla millesima riga.

Il difetto: `_fetch_recent_rows` chiudeva la query con `.limit(MAX_POOL_ROWS)`
(12000) e `.execute()`. PostgREST **clampa** quel limit a `max_rows` (1000 su
questo progetto) e tronca in silenzio: nessun errore, nessun log, solo un pool
piu' piccolo. Misurato in produzione il 5/9: sulle 5 sedi sopra il cap la
detection vedeva ~450 prodotti distinti su ~1.100 reali.

Perche' conta: `occorrenze` e `fornitori` di ogni prodotto sono conteggi su
questo pool, e le soglie (MIN_ROWS_DEFAULT, MIN_PRODUCTS_DEFAULT,
MIN_FORNITORI_NEW_TAG) si applicano a quei conteggi. Un prodotto comprato da 2
fornitori oltre la millesima riga risulta comprato da 1 e il suggerimento non
nasce mai — un tag che manca non si nota, a differenza di uno sbagliato.

I test chiamano `_fetch_recent_rows` vero contro un fake che tronca come
PostgREST: non ricalcolano la formula.
"""
import pytest

from tests.test_paginazione_e_cache_audit_performance import FakePostgrest


class _SBPool:
    """Client che serve due query diverse sulla stessa tabella `fatture`:
    l'ancora (una riga, .limit(1)) e il pool (tutte le righe della finestra)."""

    def __init__(self, pool_rows, max_rows=1000):
        self._pool_rows = pool_rows
        self._max_rows = max_rows
        self.pool_query = None

    def table(self, _nome):
        if self.pool_query is None:
            # prima chiamata: l'ancora di _latest_invoice_date
            self.pool_query = False
            return FakePostgrest([{"data_documento": "2026-09-01"}], self._max_rows)
        q = FakePostgrest(self._pool_rows, self._max_rows)
        self.pool_query = q
        return q


def _righe(n):
    return [
        {
            "descrizione": f"PRODOTTO {i}",
            "fornitore": f"FORN {i % 7}",
            "data_documento": "2026-08-15",
            "categoria": "ALIMENTARI",
        }
        for i in range(n)
    ]


class TestPoolTagOltreIlCap:
    def test_il_pool_non_si_ferma_alla_millesima_riga(self):
        import services.tag_suggestion_service as ts

        sb = _SBPool(_righe(4343))
        rows = ts._fetch_recent_rows("u1", "r1", window_days=90, supabase_client=sb)

        assert len(rows) == 4343, (
            f"pool troncato a {len(rows)}: le righe oltre la millesima non "
            "producono suggerimenti e falsano occorrenze/fornitori"
        )

    @pytest.mark.parametrize("n", [0, 999, 1000, 1001, 2500])
    def test_conteggio_esatto_ai_bordi_della_pagina(self, n):
        """1000 e 1001 distinguono un fix vero da uno apparente."""
        import services.tag_suggestion_service as ts

        sb = _SBPool(_righe(n))
        rows = ts._fetch_recent_rows("u1", "r1", window_days=90, supabase_client=sb)
        assert len(rows) == n

    def test_nessuna_riga_persa_ne_duplicata(self):
        import services.tag_suggestion_service as ts

        sb = _SBPool(_righe(2345))
        rows = ts._fetch_recent_rows("u1", "r1", window_days=90, supabase_client=sb)
        assert [r["descrizione"] for r in rows] == [f"PRODOTTO {i}" for i in range(2345)]

    def test_il_fornitore_oltre_il_cap_conta_per_la_soglia(self):
        """Il caso di dominio: MIN_FORNITORI_NEW_TAG=2 chiede due fornitori
        distinti. Se il secondo sta oltre la millesima riga, il prodotto
        sembra di marca e il suggerimento non nasce."""
        import services.tag_suggestion_service as ts

        righe = _righe(1200)
        righe[5] = {
            "descrizione": "SALMONE AFFUMICATO",
            "fornitore": "FORNITORE ALFA",
            "data_documento": "2026-08-15",
            "categoria": "ALIMENTARI",
        }
        righe[1100] = {
            "descrizione": "SALMONE AFFUMICATO",
            "fornitore": "FORNITORE BETA",
            "data_documento": "2026-08-16",
            "categoria": "ALIMENTARI",
        }

        sb = _SBPool(righe)
        rows = ts._fetch_recent_rows("u1", "r1", window_days=90, supabase_client=sb)
        pool = ts._aggregate_pool(rows)
        key = ts._normalize_custom_tag_key("SALMONE AFFUMICATO")

        assert len(pool[key]["fornitori"]) == 2, (
            "il secondo fornitore sta oltre il cap: con il troncamento il "
            "prodotto resta sotto MIN_FORNITORI_NEW_TAG e non viene mai proposto"
        )
