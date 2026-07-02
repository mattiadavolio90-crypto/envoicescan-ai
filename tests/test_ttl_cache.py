"""Test per utils.ttl_cache.TTLCache (cache TTL thread-safe con single-flight).

Il single-flight e' la difesa contro il load parallelo della Home (6-7 endpoint
concorrenti che a cache fredda colpivano tutti il DB): va protetto da regressioni.
"""
import threading
import time

from utils.ttl_cache import TTLCache


def test_get_or_set_cacha_e_riusa():
    c = TTLCache(ttl=10.0)
    calls = []
    val = c.get_or_set("k", lambda: (calls.append(1), "v")[1])
    assert val == "v"
    # seconda chiamata: dalla cache, producer NON rieseguito
    val2 = c.get_or_set("k", lambda: (calls.append(1), "altro")[1])
    assert val2 == "v"
    assert len(calls) == 1


def test_ttl_scade():
    c = TTLCache(ttl=0.05)
    c.get_or_set("k", lambda: "primo")
    time.sleep(0.1)
    assert c.get("k") is None
    assert c.get_or_set("k", lambda: "secondo") == "secondo"


def test_invalidate_singola_chiave_e_tutto():
    c = TTLCache(ttl=10.0)
    c.set("a", 1)
    c.set("b", 2)
    c.invalidate("a")
    assert c.get("a") is None
    assert c.get("b") == 2
    c.invalidate()
    assert c.get("b") is None


def test_single_flight_una_sola_esecuzione_sotto_concorrenza():
    """N thread sulla STESSA chiave fredda -> producer chiamato 1 volta sola."""
    c = TTLCache(ttl=5.0)
    n_calls = {"n": 0}
    guard = threading.Lock()

    def slow():
        with guard:
            n_calls["n"] += 1
        time.sleep(0.15)  # simula query DB
        return "risultato"

    results = []
    threads = [threading.Thread(target=lambda: results.append(c.get_or_set("key", slow)))
               for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert n_calls["n"] == 1
    assert results == ["risultato"] * 10


def test_chiavi_diverse_non_si_bloccano():
    c = TTLCache(ttl=5.0)
    assert c.get_or_set("a", lambda: 1) == 1
    assert c.get_or_set("b", lambda: 2) == 2
