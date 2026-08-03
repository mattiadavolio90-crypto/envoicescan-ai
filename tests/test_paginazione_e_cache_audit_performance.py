"""Difese dell'audit Performance (3/8/2026).

Tre difetti chiusi in quella passata, tutti dello stesso tipo: il codice
sembrava funzionare e restituiva silenziosamente un risultato sbagliato o
sprecato.

1. PostgREST tronca a `max_rows` (1000) ogni `.select()` senza `.range()`. Nessun
   errore, nessun log: il risultato sembra solo piu' piccolo. Sul DB reale
   costava la sparizione di "Da Classificare" dal filtro categorie su 4 sedi.
2. `utils.streamlit_compat.make_cache` dichiarava un TTL e non cachava niente
   (Streamlit non e' installato): 14 funzioni "cachate" rileggevano ogni volta.
3. La cache righe di PREZZI e quella di FATTURE leggono gli stessi dati: se
   l'invalidazione non le tocca entrambe, le due pagine divergono dopo un upload.

I test NON verificano che il codice "chiami .range()" (sarebbe un test sulla
forma): verificano che, davanti a una fonte che tronca come fa PostgREST, il
risultato sia comunque completo.
"""
import time

import pytest

from utils.streamlit_compat import make_cache
from utils.supabase_paging import fetch_all


class FakePostgrest:
    """Query-builder che si comporta come PostgREST: senza `.range()` non
    restituisce mai piu' di `max_rows` righe, e non segnala il troncamento."""

    def __init__(self, rows, max_rows=1000):
        self._rows = rows
        self._max_rows = max_rows
        self._range = None
        self.execute_calls = 0

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        self.execute_calls += 1
        if self._range is None:
            rows = self._rows[: self._max_rows]
        else:
            start, end = self._range
            # PostgREST: estremi inclusivi, e comunque mai piu' di max_rows.
            rows = self._rows[start : min(end + 1, start + self._max_rows)]
        return type("R", (), {"data": rows})()


def _rows(n, prefix="riga"):
    return [{"id": i, "descrizione": f"{prefix}-{i}"} for i in range(n)]


class TestFetchAllContro1000:
    def test_senza_paginazione_postgrest_tronca_in_silenzio(self):
        """Il fake e' fedele: e' proprio questo il comportamento che ci ha morso."""
        q = FakePostgrest(_rows(2500))
        assert len(q.select().execute().data) == 1000

    def test_fetch_all_restituisce_tutte_le_righe(self):
        q = FakePostgrest(_rows(2500))
        assert len(fetch_all(q.select())) == 2500

    @pytest.mark.parametrize("n", [0, 1, 999, 1000, 1001, 3000])
    def test_conteggio_esatto_ai_bordi_della_pagina(self, n):
        """1000 e 1001 sono i casi che distinguono un fix vero da uno apparente."""
        q = FakePostgrest(_rows(n))
        assert len(fetch_all(q.select())) == n

    def test_nessuna_riga_persa_ne_duplicata(self):
        q = FakePostgrest(_rows(2345))
        got = [r["id"] for r in fetch_all(q.select())]
        assert got == list(range(2345))

    def test_ultima_pagina_piena_non_causa_giro_a_vuoto_infinito(self):
        """n multiplo esatto di page_size: serve un giro in piu' che torna vuoto."""
        q = FakePostgrest(_rows(2000))
        assert len(fetch_all(q.select())) == 2000
        assert q.execute_calls == 3

    def test_max_rows_ferma_la_paginazione(self):
        """Rete di sicurezza: non si pagina all'infinito su un filtro sbagliato."""
        q = FakePostgrest(_rows(10000))
        assert len(fetch_all(q.select(), max_rows=3000)) == 3000

    def test_categoria_oltre_la_millesima_riga_resta_visibile(self):
        """Il caso reale: 'Da Classificare' compariva solo dopo la riga 1000.

        E' la regola di dominio #1 (CLAUDE.md): una riga non classificata deve
        restare visibile al cliente nel filtro, non sparire.
        """
        righe = [{"categoria": "ALIMENTARI"} for _ in range(1500)]
        righe.append({"categoria": "Da Classificare"})
        q = FakePostgrest(righe)

        troncato = {r["categoria"] for r in q.select().execute().data}
        assert "Da Classificare" not in troncato, "premessa del test non valida"

        completo = {r["categoria"] for r in fetch_all(FakePostgrest(righe).select())}
        assert "Da Classificare" in completo


class TestMakeCacheCachaDavvero:
    def test_risultato_riusato_entro_il_ttl(self):
        chiamate = {"n": 0}

        @make_cache(ttl=60, show_spinner=False)
        def f(x):
            chiamate["n"] += 1
            return x * 2

        assert [f(2), f(2), f(2)] == [4, 4, 4]
        assert chiamate["n"] == 1, "la cache non sta cachando (era il bug)"

    def test_argomenti_diversi_non_si_sovrascrivono(self):
        @make_cache(ttl=60)
        def f(x):
            return x * 2

        assert (f(2), f(3)) == (4, 6)

    def test_clear_forza_il_ricalcolo(self):
        chiamate = {"n": 0}

        @make_cache(ttl=60)
        def f():
            chiamate["n"] += 1
            return chiamate["n"]

        f()
        f.clear()
        f()
        assert chiamate["n"] == 2

    def test_scadenza_ttl(self):
        chiamate = {"n": 0}

        @make_cache(ttl=0.05)
        def f():
            chiamate["n"] += 1
            return chiamate["n"]

        f()
        time.sleep(0.08)
        f()
        assert chiamate["n"] == 2

    def test_argomenti_non_hashabili_non_esplodono(self):
        """get_fatture_cestino riceve liste (catena) e dict (sedi_nomi)."""

        @make_cache(ttl=60)
        def f(ids, mappa=None):
            return len(ids) + len(mappa or {})

        assert f(["a", "b"], mappa={"x": 1}) == 3

    def test_dict_riordinato_e_la_stessa_domanda(self):
        chiamate = {"n": 0}

        @make_cache(ttl=60)
        def f(mappa):
            chiamate["n"] += 1
            return sorted(mappa)

        f({"a": 1, "b": 2})
        f({"b": 2, "a": 1})
        assert chiamate["n"] == 1

    def test_il_client_non_entra_nella_chiave(self):
        """Il repr di un client contiene l'indirizzo di memoria: se finisse nella
        chiave, ogni istanza sarebbe un miss e la cache non servirebbe a nulla."""
        chiamate = {"n": 0}

        class FintoClient:
            pass

        @make_cache(ttl=60)
        def f(user_id, client):
            chiamate["n"] += 1
            return user_id

        f("u1", FintoClient())
        f("u1", FintoClient())
        assert chiamate["n"] == 1

    def test_sedi_diverse_restano_separate(self):
        """Il rovescio del test precedente: la cache non deve confondere sedi."""

        @make_cache(ttl=60)
        def f(rid, client=None):
            return rid

        assert (f("r1"), f("r2")) == ("r1", "r2")


class TestLaVersioneCacheNonVaCachata:
    """`_get_cache_version_internal` e' il MECCANISMO di invalidazione, non un
    dato: e' la chiave con cui lo Scadenziario decide se la sua cache e' scaduta,
    e i bump sono read-modify-write (`version = leggi() + 1`).

    Cacharla produce due danni: la fattura appena segnata pagata continua a
    comparire non pagata (la chiave non cambia), e due bump ravvicinati leggono
    lo stesso valore e scrivono lo stesso `version+1` — un'invalidazione persa
    per sempre, non ritardata. Durante la remediation 3/8 il decoratore c'era
    davvero, per un giro: questo test impedisce che ci ritorni.
    """

    def test_la_lettura_vede_subito_il_valore_nuovo(self):
        import services.documenti_service as ds

        db = {"v": 5}

        class _Q:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def limit(self, *_a, **_k):
                return self

            def execute(self):
                return type("R", (), {"data": [{"version": db["v"]}]})()

        class _SB:
            def table(self, *_a, **_k):
                return _Q()

        import services

        originale = services.get_supabase_client
        services.get_supabase_client = lambda: _SB()
        try:
            assert ds.get_cache_version("fatture_documenti") == 5
            db["v"] = 6
            assert ds.get_cache_version("fatture_documenti") == 6, (
                "lettura stale: un bump non invaliderebbe la cache a valle"
            )
        finally:
            services.get_supabase_client = originale

    def test_non_e_decorata_con_una_cache(self):
        import services.documenti_service as ds

        assert not hasattr(ds._get_cache_version_internal, "clear"), (
            "_get_cache_version_internal e' stata ri-decorata con @_make_cache: "
            "rompe l'invalidazione dello Scadenziario e fa perdere i bump"
        )


class TestCachePrezziEInvalidazione:
    """La cache righe di PREZZI deve sparire insieme a quella di FATTURE: leggono
    gli stessi dati, e due pagine che divergono dopo un upload sono peggio di due
    pagine lente."""

    @staticmethod
    def _sb(rows):
        class _SB:
            def __init__(self):
                self.q = FakePostgrest(rows)

            def table(self, _name):
                return self.q

        return _SB()

    def test_seconda_chiamata_non_rilegge(self):
        from services.routers import prezzi

        prezzi._invalidate_prezzi_rows_cache()
        sb = self._sb(_rows(10))
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-12-31")
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-12-31")
        assert sb.q.execute_calls == 1

    def test_periodo_diverso_e_una_chiave_diversa(self):
        from services.routers import prezzi

        prezzi._invalidate_prezzi_rows_cache()
        sb = self._sb(_rows(10))
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-06-30")
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-07-01", "2026-12-31")
        assert sb.q.execute_calls == 2

    def test_sedi_diverse_non_si_mescolano(self):
        from services.routers import prezzi

        prezzi._invalidate_prezzi_rows_cache()
        sb = self._sb(_rows(10))
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-12-31")
        prezzi._load_fatture_for_prezzi(sb, "r2", "2026-01-01", "2026-12-31")
        assert sb.q.execute_calls == 2

    def test_invalidare_fatture_invalida_anche_prezzi(self):
        import services.fastapi_worker as fw
        from services.routers import prezzi

        prezzi._invalidate_prezzi_rows_cache()
        sb = self._sb(_rows(10))
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-12-31")
        fw._invalidate_fatture_rows_cache("r1")
        prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-12-31")
        assert sb.q.execute_calls == 2, "dopo un upload PREZZI serviva dati stale"

    def test_le_righe_oltre_1000_arrivano_anche_a_prezzi(self):
        from services.routers import prezzi

        prezzi._invalidate_prezzi_rows_cache()
        sb = self._sb(_rows(2500))
        out = prezzi._load_fatture_for_prezzi(sb, "r1", "2026-01-01", "2026-12-31")
        assert len(out) == 2500
