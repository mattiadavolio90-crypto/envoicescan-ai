"""Isolamento fra test della cache di sessione (auth_service._SESSIONE_CACHE).

`verifica_sessione_da_cookie` memoizza l'utente per token con TTL 30s. E' la
cache dietro l'HIGH Security del 29/7 e dietro il bug dello switch sede (si
continuava a leggere il vecchio `ultimo_ristorante_id`). Nella suite e' stato
globale: senza reset, un test che scalda il token si porta dietro l'utente nel
test successivo che usa lo stesso token — e il secondo test passerebbe senza mai
toccare il DB, cioe' verificando nulla.

I due test qui sotto sono deliberatamente ACCOPPIATI e vanno letti in coppia:
il primo popola la cache, il secondo pretende di NON vedere quel valore. Se la
fixture `_reset_worker_caches` smette di svuotare `_SESSIONE_CACHE`, il secondo
diventa rosso.
"""
import time

import services.ai_service as ai_service
import services.auth_service as auth_service


_TOKEN = "token-condiviso-fra-i-due-test"
_UTENTE_DEL_PRIMO_TEST = {"id": "utente-A", "email": "a@oneflux.it"}


def test_a_popola_la_cache_di_sessione():
    auth_service._SESSIONE_CACHE[_TOKEN] = (
        time.time() + auth_service._SESSIONE_CACHE_TTL,
        dict(_UTENTE_DEL_PRIMO_TEST),
    )
    assert auth_service._SESSIONE_CACHE.get(_TOKEN) is not None


def test_b_non_eredita_la_sessione_del_test_precedente():
    # Il TTL e' 30s e i due test girano a millisecondi di distanza: se questa
    # entry e' ancora qui, NON e' scaduta da sola — e' la fixture di reset che
    # non l'ha svuotata.
    residuo = auth_service._SESSIONE_CACHE.get(_TOKEN)
    assert residuo is None, (
        "_SESSIONE_CACHE non e' stata svuotata fra i test: l'utente "
        f"{residuo[1] if residuo else None} e' sopravvissuto al test precedente. "
        "Un test successivo leggerebbe questa sessione senza mai interrogare il DB."
    )


# --- stessa coppia, per la memoria di categorizzazione di ai_service --------
# `_memoria_cache` e' la piu' sensibile: contiene le categorie apprese PER UTENTE
# (`prodotti_utente[user_id]`) e un set `_loaded_user_ids` che, se sopravvive,
# convince il codice che l'utente e' gia' stato caricato — quindi il test
# successivo NON rilegge dal DB e valida categorie ereditate da un altro test.

_UTENTE_MEMORIA = "utente-memoria-A"


def test_c_popola_la_memoria_di_categorizzazione():
    ai_service._memoria_cache["prodotti_utente"][_UTENTE_MEMORIA] = {
        "farina 00": "PASTICCERIA"
    }
    ai_service._memoria_cache["_loaded_user_ids"].add(_UTENTE_MEMORIA)
    assert _UTENTE_MEMORIA in ai_service._memoria_cache["_loaded_user_ids"]


def test_d_non_eredita_la_memoria_del_test_precedente():
    caricati = ai_service._memoria_cache.get("_loaded_user_ids", set())
    assert _UTENTE_MEMORIA not in caricati, (
        "_memoria_cache non e' stata invalidata fra i test: l'utente "
        f"{_UTENTE_MEMORIA} risulta gia' caricato, quindi il codice salterebbe "
        "la rilettura dal DB e classificherebbe con categorie ereditate."
    )
    assert _UTENTE_MEMORIA not in ai_service._memoria_cache.get("prodotti_utente", {})
