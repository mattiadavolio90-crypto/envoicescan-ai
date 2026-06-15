"""Test della logica di salute import ricavi per ristorante (admin panel).

Copre le funzioni pure estratte dall'endpoint /api/admin/sistema/ricavi-salute:
  - _buchi_serie: rileva i giorni mancanti nella serie
  - _classifica_salute_ricavi: silenzio/buchi/coda -> ok/warning/critico
"""
from services.routers.admin import _buchi_serie, _classifica_salute_ricavi


class TestBuchiSerie:
    def test_serie_completa_nessun_buco(self):
        date_set = {"2026-06-12", "2026-06-13", "2026-06-14"}
        assert _buchi_serie(date_set, "2026-06-12", "2026-06-14") == []

    def test_buchi_intermedi(self):
        # Caso LAND DEI SAPORI: c'e' 11 e 15 ma mancano 12,13,14
        date_set = {"2026-06-11", "2026-06-15"}
        assert _buchi_serie(date_set, "2026-06-11", "2026-06-15") == [
            "2026-06-12", "2026-06-13", "2026-06-14",
        ]

    def test_singolo_giorno_nessun_buco(self):
        assert _buchi_serie({"2026-06-14"}, "2026-06-14", "2026-06-14") == []

    def test_set_vuoto(self):
        assert _buchi_serie(set(), None, None) == []

    def test_estremi_none(self):
        assert _buchi_serie({"2026-06-14"}, None, "2026-06-14") == []


class TestClassificaSalute:
    def test_ok_aggiornato_senza_problemi(self):
        assert _classifica_salute_ricavi(1, 0, 0, silenzio_giorni=2) == "ok"

    def test_ok_silenzio_pari_soglia(self):
        # silenzio == soglia non e' critico (solo > soglia lo e')
        assert _classifica_salute_ricavi(2, 0, 0, silenzio_giorni=2) == "ok"

    def test_critico_silenzio_oltre_soglia(self):
        # Caso del bug: ultimo dato 4 giorni fa, soglia 2
        assert _classifica_salute_ricavi(4, 0, 0, silenzio_giorni=2) == "critico"

    def test_critico_nessun_dato(self):
        assert _classifica_salute_ricavi(None, 0, 0, silenzio_giorni=2) == "critico"

    def test_critico_coda_bloccata_anche_se_aggiornato(self):
        # Coda problematica prevale anche con dati freschi
        assert _classifica_salute_ricavi(1, 0, 1, silenzio_giorni=2) == "critico"

    def test_warning_buchi_ma_aggiornato(self):
        assert _classifica_salute_ricavi(1, 3, 0, silenzio_giorni=2) == "warning"

    def test_critico_prevale_su_warning(self):
        # Silenzio critico + buchi -> resta critico
        assert _classifica_salute_ricavi(5, 3, 0, silenzio_giorni=2) == "critico"
