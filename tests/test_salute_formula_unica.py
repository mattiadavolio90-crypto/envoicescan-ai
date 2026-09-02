"""B4: la formula della Salute deve esistere UNA volta sola.

Difetto misurato il 2/9/2026. La formula viveva in due posti:
  - home_salute        -> escludeva le voci spente dal denominatore
  - _salute_indice_rosso -> divideva SEMPRE per 4
Chi spegneva un avviso poteva quindi vedere la card VERDE e contemporaneamente far
scattare i gate che usano _salute_indice_rosso (buona notizia soppressa, amo
"Assistenza" del rientro offerto a torto). Il commento della funzione duplicata
diceva "se la formula cambia, allineare anche qui": non era mai stato fatto.

B2: il fingerprint dello snapshot non e' un meccanismo di invalidazione — la
docstring che lo affermava e' stata corretta.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.daily_briefing_service import (  # noqa: E402
    SALUTE_SOGLIA_GIALLO,
    SALUTE_SOGLIA_VERDE,
    calcola_indice_salute,
    colore_salute,
    salute_e_rossa,
)

# Il caso che divergeva: fatture ok, fatturato e personale mancanti, 90% classificate.
PUNTEGGI = {"fatture": 100, "fatturato": 0, "personale": 0, "classificate": 90}


class TestFormulaUnica:
    def test_le_voci_spente_escono_dal_denominatore(self):
        """Il cuore di B4: una voce spenta non vale zero, semplicemente non conta."""
        con_tutte = calcola_indice_salute(PUNTEGGI)
        senza_fatturato = calcola_indice_salute(PUNTEGGI, {"fatturato"})
        assert con_tutte == 48, "media su 4 voci"
        assert senza_fatturato == 63, "media su 3 voci: la spenta esce, non vale 0"
        assert colore_salute(con_tutte) == "rosso"
        assert colore_salute(senza_fatturato) == "giallo"

    def test_e_proprio_il_caso_che_dava_verde_e_rosso_insieme(self):
        """Con la vecchia duplicazione: card gialla/verde e gate rosso sugli
        STESSI dati. Ora la risposta e' una sola."""
        indice = calcola_indice_salute(PUNTEGGI, {"fatturato"})
        assert salute_e_rossa(indice) is False
        assert colore_salute(indice) != "rosso"

    def test_tutte_spente_non_e_misurabile(self):
        tutte = {"fatture", "fatturato", "personale", "classificate"}
        assert calcola_indice_salute(PUNTEGGI, tutte) == 100
        assert colore_salute(100) == "verde"

    @pytest.mark.parametrize("indice,atteso", [
        (100, "verde"), (80, "verde"), (79, "giallo"),
        (50, "giallo"), (49, "rosso"), (0, "rosso"),
    ])
    def test_soglie_colore(self, indice, atteso):
        assert colore_salute(indice) == atteso

    def test_le_soglie_sono_costanti_non_numeri_sparsi(self):
        assert SALUTE_SOGLIA_VERDE == 80 and SALUTE_SOGLIA_GIALLO == 50

    def test_salute_e_rossa_usa_la_stessa_soglia_del_colore(self):
        for i in range(0, 101):
            assert salute_e_rossa(i) == (colore_salute(i) == "rosso")

    def test_punteggi_mancanti_valgono_zero(self):
        """Robustezza: una voce assente dal dict non deve far esplodere il calcolo."""
        assert calcola_indice_salute({}) == 0
        assert calcola_indice_salute({"fatture": 100}) == 25


class TestNessunaDuplicazioneResidua:
    def test_home_salute_usa_la_formula_condivisa(self):
        import inspect

        import services.fastapi_worker as fw

        src = inspect.getsource(fw.home_salute)
        assert "calcola_indice_salute" in src, "deve usare la formula unica"
        assert "/ len(_attive)" not in src, "niente formula reimplementata"
        assert 'indice >= 80' not in src, "le soglie stanno in colore_salute()"

    def test_il_gate_del_briefing_usa_la_formula_condivisa(self):
        import inspect

        import services.fastapi_worker as fw

        src = inspect.getsource(fw._salute_indice_rosso)
        assert "calcola_indice_salute" in src
        assert "salute_e_rossa" in src
        assert ") / 4" not in src, "era la divisione fissa che ignorava i toggle"
        assert "indice < 50" not in src, "la soglia sta in colore_salute()"

    def test_il_gate_legge_i_toggle(self):
        """Se non leggesse i topic spenti tornerebbe a divergere dalla card."""
        import inspect

        import services.fastapi_worker as fw

        src = inspect.getsource(fw._salute_indice_rosso)
        assert "espandi_topic_spenti" in src
        assert "_VOCE_TOPIC_SALUTE" in src

    def test_la_mappa_voce_topic_e_condivisa(self):
        import services.fastapi_worker as fw

        assert set(fw._VOCE_TOPIC_SALUTE) == {
            "fatture", "fatturato", "personale", "classificate"
        }


class TestFingerprintNonEUnGate:
    def test_la_docstring_non_promette_un_invalidazione_inesistente(self):
        """B2: la docstring diceva 'usata per capire se il briefing e' allineato',
        ma nessuno rilegge il fingerprint. snapshot_is_stale guarda solo
        code_version e TTL."""
        import inspect

        from services.daily_briefing_service import (
            notifications_fingerprint,
            snapshot_is_stale,
        )

        gate = inspect.getsource(snapshot_is_stale)
        assert "fingerprint" not in gate, (
            "se un domani il gate lo usa, aggiorna anche la docstring"
        )
        doc = inspect.getdoc(notifications_fingerprint) or ""
        assert "NESSUNO lo rilegge" in doc or "traccia diagnostica" in doc
