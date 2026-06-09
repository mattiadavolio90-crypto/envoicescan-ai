"""Test invalidazione + eviction della cache KPI Home (services.fastapi_worker).

Bug risolti:
- #1 inserendo fatturato/personale/centri o caricando fatture la card "I tuoi
  conti" restava stantia fino al TTL (2 min): ora i call site invalidano la
  cache. Qui testiamo l'helper `_invalidate_home_kpi_cache` (selettivo per
  ristorante + clear globale).
- #2 la cache cresceva senza limite (chiave include anno:mese, mai evicted):
  ora l'eviction opportunistica rimuove le entry scadute. Qui testiamo che
  l'helper sia selettivo e non tocchi altri ristoranti.
"""
import services.fastapi_worker as fw


def _seed():
    fw._HOME_KPI_CACHE.clear()
    fw._HOME_KPI_CACHE["r1:2026:5"] = (0.0, "a")
    fw._HOME_KPI_CACHE["r1:2026:4"] = (0.0, "b")
    fw._HOME_KPI_CACHE["r2:2026:5"] = (0.0, "c")


def test_invalidate_per_ristorante_toglie_solo_quel_ristorante():
    _seed()
    fw._invalidate_home_kpi_cache("r1")
    # tutte le entry di r1 (tutti i mesi) rimosse, r2 intatto
    assert set(fw._HOME_KPI_CACHE.keys()) == {"r2:2026:5"}


def test_invalidate_senza_argomento_svuota_tutto():
    _seed()
    fw._invalidate_home_kpi_cache()
    assert fw._HOME_KPI_CACHE == {}


def test_invalidate_ristorante_inesistente_non_rompe():
    _seed()
    fw._invalidate_home_kpi_cache("r-non-esiste")
    assert len(fw._HOME_KPI_CACHE) == 3


def test_prefisso_non_matcha_per_sottostringa():
    # "r1" non deve rimuovere "r10:..." (match per prefisso completo "r1:").
    fw._HOME_KPI_CACHE.clear()
    fw._HOME_KPI_CACHE["r1:2026:5"] = (0.0, "a")
    fw._HOME_KPI_CACHE["r10:2026:5"] = (0.0, "b")
    fw._invalidate_home_kpi_cache("r1")
    assert set(fw._HOME_KPI_CACHE.keys()) == {"r10:2026:5"}
