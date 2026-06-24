"""Test guardia: auto-invalidazione dello snapshot briefing (no cache stantia).

Problema risolto: il briefing e' cache-first sul giorno -> una volta scritto la
mattina veniva servito fino a mezzanotte, anche dopo un deploy (codice nuovo) o
dopo che i dati cambiavano in giornata. Il cliente vedeva info vecchie (caso LAND:
"543 righe" da uno snapshot del codice vecchio).

snapshot_is_stale() scarta lo snapshot quando:
  - la versione della logica e' cambiata (deploy) -> code_version diverso;
  - lo snapshot e' piu' vecchio del TTL.
"""
from datetime import datetime, timezone, timedelta

from services.daily_briefing_service import (
    snapshot_is_stale,
    _BRIEFING_CODE_VERSION,
    _BRIEFING_TTL_MINUTI,
)


def _snap(code_version=_BRIEFING_CODE_VERSION, eta_minuti=0):
    """Snapshot di prova con versione e 'eta' (minuti fa) controllabili."""
    scritto = datetime.now(timezone.utc) - timedelta(minutes=eta_minuti)
    return {
        "bullets": [],
        "code_version": code_version,
        "_db_created_at": scritto.isoformat(),
    }


def test_snapshot_fresco_e_versione_giusta_non_stantio():
    assert snapshot_is_stale(_snap(eta_minuti=1)) is False


def test_snapshot_versione_vecchia_e_stantio():
    # Deploy: snapshot prodotto da una versione precedente -> va rigenerato.
    assert snapshot_is_stale(_snap(code_version=_BRIEFING_CODE_VERSION - 1)) is True


def test_snapshot_oltre_ttl_e_stantio():
    assert snapshot_is_stale(_snap(eta_minuti=_BRIEFING_TTL_MINUTI + 1)) is True


def test_snapshot_appena_dentro_ttl_non_stantio():
    assert snapshot_is_stale(_snap(eta_minuti=_BRIEFING_TTL_MINUTI - 1)) is False


def test_snapshot_none_e_stantio():
    assert snapshot_is_stale(None) is True
    assert snapshot_is_stale({}) is True


def test_snapshot_senza_versione_e_stantio():
    # Snapshot vecchio scritto prima dell'introduzione di code_version.
    vecchio = {"bullets": [], "_db_created_at": datetime.now(timezone.utc).isoformat()}
    assert snapshot_is_stale(vecchio) is True


def test_snapshot_data_illeggibile_e_stantio():
    assert snapshot_is_stale({"code_version": _BRIEFING_CODE_VERSION, "_db_created_at": "non-una-data"}) is True


def test_fallback_generated_at_se_manca_db_created_at():
    # Se manca _db_created_at usa generated_at: fresco -> non stantio.
    fresco = {
        "code_version": _BRIEFING_CODE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    assert snapshot_is_stale(fresco) is False
