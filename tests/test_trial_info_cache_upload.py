"""Test §27 residuo (27/8/2026) — `get_trial_info` non va richiesta per file.

`is_trial` e' invariante nel batch, ma l'upload e' per-file (una richiesta HTTP
per fattura): senza cache un caricamento da 200 fatture produce 200 SELECT
identiche su `users`. Mitigazione gia' presente prima del fix: la query si fa
solo se `blocco_mesi_precedenti` e' spento — ma quello e' il caso NORMALE (un
solo cliente su tutto il DB ha quel flag acceso).

Il TTL e' corto di proposito: la finestra in cui un trial appena scaduto verrebbe
letto come ancora attivo si misura in secondi, e l'esito peggiore e' un upload
consentito che sarebbe stato bloccato — non un dato sbagliato.
"""
import services.fastapi_worker as fw


def test_cache_esiste_ed_e_una_ttlcache():
    from utils.ttl_cache import TTLCache

    assert isinstance(fw._TRIAL_INFO_CACHE, TTLCache)


def test_ttl_breve():
    """Un TTL lungo terrebbe vivo un trial scaduto oltre il ragionevole."""
    assert 0 < fw._TRIAL_INFO_CACHE._ttl <= 60.0


def test_una_sola_query_per_utente_nella_finestra():
    """Il punto del fix: N file dello stesso utente = 1 sola lettura."""
    fw._TRIAL_INFO_CACHE.invalidate()
    chiamate = []

    def _finto_get_trial_info():
        chiamate.append(1)
        return {"is_trial": True}

    for _ in range(200):
        fw._TRIAL_INFO_CACHE.get_or_set("user-A", _finto_get_trial_info)

    assert len(chiamate) == 1, f"attesa 1 query, fatte {len(chiamate)}"


def test_utenti_diversi_non_si_contaminano():
    """La chiave e' il user_id: due clienti non devono condividere l'esito."""
    fw._TRIAL_INFO_CACHE.invalidate()
    fw._TRIAL_INFO_CACHE.get_or_set("user-A", lambda: {"is_trial": True})
    b = fw._TRIAL_INFO_CACHE.get_or_set("user-B", lambda: {"is_trial": False})
    assert b["is_trial"] is False
    assert fw._TRIAL_INFO_CACHE.get_or_set("user-A", lambda: {"is_trial": False})["is_trial"] is True


def test_upload_usa_la_cache_non_la_funzione_nuda():
    """Senza questo, rimuovere la cache dal call site passerebbe inosservato."""
    import inspect

    src = inspect.getsource(fw.upload_invoice)
    assert "_TRIAL_INFO_CACHE" in src, (
        "upload_invoice deve passare dalla cache: e' il punto del fix"
    )


def test_cache_registrata_nel_reset_fra_test():
    """Porta dati per-utente: senza reset contaminerebbe i test successivi.

    (`tests/test_conftest_cache_guardia.py` lo scopre dal sorgente; qui lo
    asseriamo esplicitamente perche' e' un requisito di questa cache.)
    """
    from tests.conftest import CACHE_WORKER

    assert "_TRIAL_INFO_CACHE" in CACHE_WORKER
