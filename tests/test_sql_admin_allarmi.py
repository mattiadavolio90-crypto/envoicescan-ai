"""admin_allarme_segnala su un Postgres vero: ogni allarme arriva una volta, un
critico si ripete al massimo ogni 6 ore, e quando rientra si dice «risolto»."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql


def _segnala(scalare, problema, gravita="critico", chiave="worker_giu"):
    return scalare(
        "SELECT public.admin_allarme_segnala(%s, %s, %s, 'testo', 'https://app.oneflux.it/admin')",
        chiave, gravita, problema,
    )


def _invecchia(sql, ore, chiave="worker_giu"):
    sql(
        "UPDATE public.admin_allarmi SET ultimo_invio_at = now() - make_interval(hours => %s) WHERE chiave = %s",
        ore, chiave,
    )


def test_un_problema_nuovo_si_manda_una_volta_sola(db_sql, scalare):
    assert _segnala(scalare, True) == "invia"
    assert _segnala(scalare, True) == "zitto"
    assert _segnala(scalare, True) == "zitto"
    assert scalare("SELECT occorrenze FROM public.admin_allarmi WHERE chiave = 'worker_giu'") == 3


def test_un_critico_aperto_si_ripete_dopo_sei_ore(db_sql, sql, scalare):
    assert _segnala(scalare, True) == "invia"
    _invecchia(sql, 5)
    assert _segnala(scalare, True) == "zitto"
    _invecchia(sql, 7)
    assert _segnala(scalare, True) == "ripeti"
    assert _segnala(scalare, True) == "zitto"


def test_un_allarme_da_oggi_non_si_ripete_mai(db_sql, sql, scalare):
    assert _segnala(scalare, True, "oggi", "riepilogo") == "invia"
    _invecchia(sql, 30, "riepilogo")
    assert _segnala(scalare, True, "oggi", "riepilogo") == "zitto"


def test_quando_rientra_si_dice_risolto_una_volta(db_sql, scalare):
    assert _segnala(scalare, False) == "niente"
    assert _segnala(scalare, True) == "invia"
    assert _segnala(scalare, False) == "risolto"
    assert _segnala(scalare, False) == "niente"
    assert scalare("SELECT aperto_at IS NULL AND risolto_at IS NOT NULL FROM public.admin_allarmi WHERE chiave = 'worker_giu'") is True


def test_un_problema_che_torna_dopo_il_risolto_si_rimanda(db_sql, scalare):
    _segnala(scalare, True)
    _segnala(scalare, False)
    assert _segnala(scalare, True) == "invia"
    assert scalare("SELECT occorrenze FROM public.admin_allarmi WHERE chiave = 'worker_giu'") == 1


def test_chiavi_diverse_non_si_disturbano(db_sql, scalare):
    assert _segnala(scalare, True, chiave="a") == "invia"
    assert _segnala(scalare, True, chiave="b") == "invia"


def test_una_gravita_sconosciuta_e_rifiutata(db_sql, scalare):
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.RaiseException):
        _segnala(scalare, True, "urgentissimo")


def test_ne_la_tabella_ne_la_funzione_sono_dei_ruoli_del_client(db_sql, scalare):
    for ruolo in ("anon", "authenticated"):
        assert scalare("SELECT has_table_privilege(%s, 'public.admin_allarmi', 'SELECT')", ruolo) is False
        assert scalare(
            "SELECT has_function_privilege(%s, "
            "'public.admin_allarme_segnala(text, text, boolean, text, text, interval)', 'EXECUTE')",
            ruolo,
        ) is False
