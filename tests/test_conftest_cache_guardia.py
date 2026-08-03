"""Guardia: nessuna cache in-process puo' sfuggire al reset fra test.

Le cache per-processo (TTL 15-45s) sono legittime in produzione, ma dentro la
suite sono stato globale condiviso: un test che scrive una chiave la fa leggere
stantia al test successivo che usa lo stesso ristorante_id/token. La fixture
autouse `_reset_worker_caches` le svuota — ma finora l'elenco era scritto a mano
dentro la fixture, quindi una cache aggiunta dopo restava fuori senza che nulla
protestasse. E' successo davvero: `_SESSIONE_CACHE` (auth_service) e
`_FATTURE_ROWS_CACHE` (worker) erano scoperte, trovate solo dall'audit Test del
3/8/2026.

Questo test non ricontrolla una lista scritta a mano contro un'altra lista
scritta a mano: legge i moduli e SCOPRE le cache dal sorgente. Se domani
qualcuno aggiunge `_PIPPO_CACHE` senza metterla nella fixture, questo test
diventa rosso e dice quale.
"""
import re
from pathlib import Path

import pytest

from tests.conftest import (
    CACHE_ADMIN,
    CACHE_AI_MINUSCOLE,
    CACHE_AUTH,
    CACHE_ESCLUSE,
    CACHE_WORKER,
)


_RADICE = Path(__file__).resolve().parents[1]

# Assegnazione a livello di modulo di una cache: `_NOME_CACHE: Dict[...] = {}`
# oppure `_NOME_CACHE = TTLCache(ttl=...)`. Ancorata a inizio riga per non
# raccogliere le assegnazioni dentro le funzioni (che sono variabili locali).
#
# Case-insensitive di proposito: `ai_service.py` usa `_memoria_cache` minuscolo,
# e una regex sul solo MAIUSCOLO l'avrebbe mancata — cioe' la guardia avrebbe
# promesso piu' copertura di quanta ne desse, proprio sulla cache che contiene
# la memoria di categorizzazione per utente.
_RE_CACHE = re.compile(r"^(_[A-Za-z0-9_]*(?:CACHE|cache|Cache))\s*[:=]", re.MULTILINE)


def _cache_dichiarate(percorso_relativo):
    sorgente = (_RADICE / percorso_relativo).read_text(encoding="utf-8")
    return set(_RE_CACHE.findall(sorgente))


@pytest.mark.parametrize(
    "percorso, coperte",
    [
        ("services/fastapi_worker.py", set(CACHE_WORKER)),
        ("services/auth_service.py", set(CACHE_AUTH)),
        ("services/routers/admin.py", set(CACHE_ADMIN)),
        ("services/ai_service.py", set(CACHE_AI_MINUSCOLE)),
    ],
)
def test_ogni_cache_in_process_e_resettata_o_esclusa(percorso, coperte):
    trovate = _cache_dichiarate(percorso)
    scoperte = trovate - coperte - CACHE_ESCLUSE

    assert not scoperte, (
        f"{percorso}: cache non resettate fra i test e non dichiarate come "
        f"escluse: {sorted(scoperte)}.\n"
        "Aggiungile a CACHE_WORKER/CACHE_AUTH in tests/conftest.py (se portano "
        "dati) oppure a CACHE_ESCLUSE con il motivo (se sono memoizzazioni "
        "innocue, tipo un client stateless)."
    )


def test_la_regex_trova_davvero_le_cache():
    """Se la regex smettesse di matchare, il test sopra passerebbe sempre a
    vuoto (insieme vuoto - qualunque cosa = vuoto): la guardia diventerebbe
    decorativa senza dirlo. Qui verifichiamo che stia leggendo qualcosa."""
    trovate = _cache_dichiarate("services/fastapi_worker.py")
    assert len(trovate) >= 6, f"regex cache degenerata, trovate solo: {sorted(trovate)}"
    assert "_SEDE_ATTIVA_CACHE" in trovate


def test_cache_escluse_esistono_davvero():
    """Una voce in CACHE_ESCLUSE che non corrisponde piu' a nulla nel codice
    nasconderebbe un buco: la si crede coperta mentre e' solo un nome morto."""
    tutte = set()
    for _p in (
        "services/fastapi_worker.py",
        "services/auth_service.py",
        "services/routers/admin.py",
        "services/ai_service.py",
    ):
        tutte |= _cache_dichiarate(_p)
    morte = CACHE_ESCLUSE - tutte
    assert not morte, f"CACHE_ESCLUSE cita cache che non esistono piu': {sorted(morte)}"
