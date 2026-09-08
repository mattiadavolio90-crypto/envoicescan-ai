"""Il chokepoint che dichiara CHI scrive una categoria.

Perche' esiste
==============
`aggiorna_categoria_fatture` e' l'unico punto da cui passano le scritture di
`categoria` su `fatture`. I test dei guardrail non lo coprono: i loro fake non
hanno `.rpc()`, quindi cadono tutti nel fallback HTTP (52 volte in tutta la
suite) e il percorso RPC — quello per cui la fase esiste — non era provato da
nessun test Python.

Qui si prova cio' che il registro promette: che l'attore arrivi davvero alla
RPC, che chi non dichiara sia segnalato ma non bloccato, e che il fallback non
sia piu' largo della query che sostituisce.
"""
from __future__ import annotations

import logging

import pytest

from services.db_service import SOURCE_NON_DICHIARATA, aggiorna_categoria_fatture


class _Query:
    def __init__(self, registro):
        self._r = registro
        self._r["filtri"] = {}

    def update(self, payload):
        self._r["payload"] = payload
        return self

    def in_(self, colonna, valori):
        self._r["ids"] = list(valori)
        return self

    def is_(self, colonna, valore):
        self._r["filtri"][colonna] = valore
        return self

    def eq(self, colonna, valore):
        self._r["filtri"][colonna] = valore
        return self

    def or_(self, espressione):
        # PostgREST prende l'espressione come stringa: il test la conserva
        # testuale, perche' e' proprio la sua forma a decidere se i NULL
        # sopravvivono (`.neq()` secco li scarterebbe).
        self._r["filtri"]["or"] = espressione
        return self

    def execute(self):
        return type("R", (), {"data": [{"id": i} for i in self._r["ids"]]})()


class _ClientRPC:
    """Client con la RPC disponibile: il percorso normale a migration applicata."""

    _AUTO = object()

    def __init__(self, ritorno=_AUTO):
        self.chiamate = []
        self._ritorno = ritorno

    def rpc(self, nome, parametri):
        self.chiamate.append((nome, parametri))
        dato = (len(parametri.get("p_ids") or [])
                if self._ritorno is self._AUTO else self._ritorno)
        return type("R", (), {"execute": lambda _s=None: type("X", (), {"data": dato})()})()

    def table(self, _nome):  # pragma: no cover - non deve essere raggiunto
        raise AssertionError("con la RPC disponibile non si deve usare l'HTTP")


class _ClientSenzaRPC:
    """Client senza la RPC: e' lo stato del DB live finche' la migration non e' applicata."""

    def __init__(self):
        self.registro = {}

    def rpc(self, nome, parametri):
        raise Exception("function public.aggiorna_categoria_fatture_attribuita does not exist")

    def table(self, nome):
        self.registro["tabella"] = nome
        return _Query(self.registro)


def test_l_attore_arriva_alla_rpc():
    """Senza questo, il registro resta anonimo pur avendo l'identita' in mano."""
    client = _ClientRPC()
    scritte = aggiorna_categoria_fatture(
        client, ids=[1, 2], categoria="PESCE", source="correzione_cliente",
        extra={"needs_review": False}, attore_email="mattia@oneflux.test",
        attore_user_id="44444444-4444-4444-8444-444444444444", batch_id="lotto-1",
    )
    assert scritte == 2
    nome, parametri = client.chiamate[0]
    assert nome == "aggiorna_categoria_fatture_attribuita"
    # Le componenti una per una: un assert sul solo nome della RPC resterebbe
    # verde anche se l'attore si perdesse per strada.
    assert parametri["p_ids"] == [1, 2]
    assert parametri["p_categoria"] == "PESCE"
    assert parametri["p_source"] == "correzione_cliente"
    assert parametri["p_actor_email"] == "mattia@oneflux.test"
    assert parametri["p_actor_user_id"] == "44444444-4444-4444-8444-444444444444"
    assert parametri["p_batch_id"] == "lotto-1"
    assert parametri["p_extra"] == {"needs_review": False}


def test_chi_non_dichiara_viene_segnalato_ma_scrive(caplog):
    """Nel worker un blocco fermerebbe la coda fatture: si segnala, non si blocca."""
    client = _ClientRPC()
    with caplog.at_level(logging.WARNING):
        scritte = aggiorna_categoria_fatture(client, ids=[7], categoria="PESCE")
    assert scritte == 1
    assert client.chiamate[0][1]["p_source"] == SOURCE_NON_DICHIARATA
    assert any("senza `source` dichiarata" in r.getMessage() for r in caplog.records)


def test_una_lista_vuota_non_chiama_nemmeno_la_rpc():
    client = _ClientRPC()
    assert aggiorna_categoria_fatture(client, ids=[], categoria="PESCE", source="worker_coda") == 0
    assert client.chiamate == []


@pytest.mark.parametrize("ritorno, atteso", [
    (3, 3),          # scalare: il caso normale di PostgREST
    ([3], 3),        # incapsulato in lista
    (None, 0),       # nessun dato
    ("5", 5),        # stringa numerica
])
def test_il_conteggio_e_sempre_un_intero(ritorno, atteso):
    """La firma dice `-> int` e alimenta `righe_aggiornate`, che decide se salvare
    la memoria AI e cosa vede il cliente: una lista li' sarebbe un bug silenzioso."""
    client = _ClientRPC(ritorno=ritorno)
    risultato = aggiorna_categoria_fatture(
        client, ids=[1], categoria="PESCE", source="worker_coda",
    )
    assert risultato == atteso and isinstance(risultato, int)


def test_senza_la_rpc_la_scrittura_passa_lo_stesso(caplog):
    """E' lo stato del DB live finche' la migration non e' applicata: si perde
    l'attribuzione, non la scrittura."""
    client = _ClientSenzaRPC()
    with caplog.at_level(logging.WARNING):
        scritte = aggiorna_categoria_fatture(
            client, ids=[1, 2], categoria="PESCE", source="worker_coda",
            extra={"needs_review": False},
        )
    assert scritte == 2
    assert client.registro["payload"] == {"categoria": "PESCE", "needs_review": False}
    assert any("fallback" in r.getMessage() for r in caplog.records)


def test_il_fallback_non_e_piu_largo_della_query_che_sostituisce():
    """Un fallback che perdesse i filtri di tenant sarebbe una falla di
    isolamento, non un ripiego: i call site convertiti li passano apposta."""
    client = _ClientSenzaRPC()
    aggiorna_categoria_fatture(
        client, ids=[1], categoria="PESCE", source="post_upload",
        user_id="utente-1", ristorante_id="sede-1",
    )
    assert client.registro["filtri"]["user_id"] == "utente-1"
    assert client.registro["filtri"]["ristorante_id"] == "sede-1"
    # E il soft-delete resta rispettato: una riga nel cestino non torna in vita.
    assert client.registro["filtri"]["deleted_at"] == "null"


# ---------------------------------------------------------------------------
# La guardia sulle correzioni gia' arbitrate.
#
# Il parametro e' opt-in: chi scrive per se' (il cliente dal frontend) deve
# poter riscrivere le proprie righe, chi scrive per conto d'altri (uno script)
# no. Qui si prova che la scelta arriva alla RPC e che il fallback HTTP non e'
# piu' largo di lei.
# ---------------------------------------------------------------------------


def test_la_guardia_arriva_alla_rpc_quando_si_chiede():
    client = _ClientRPC()
    aggiorna_categoria_fatture(
        client, ids=[1, 2], categoria="CARNE", source="script_ricategorizza_sede",
        salta_correzioni_manuali=True,
    )
    _, parametri = client.chiamate[0]
    assert parametri["p_salta_arbitrate"] is True


def test_senza_chiederla_la_guardia_resta_spenta():
    """I 13 chiamanti esistenti non la passano: il default non deve cambiare
    il loro comportamento, o il cliente non potrebbe correggersi due volte."""
    client = _ClientRPC()
    aggiorna_categoria_fatture(
        client, ids=[1], categoria="PESCE", source="correzione_cliente",
    )
    _, parametri = client.chiamate[0]
    assert parametri["p_salta_arbitrate"] is False


def test_il_fallback_replica_la_guardia():
    """Se il fallback non la replicasse, scriverebbe le righe che la RPC salta —
    e proprio nel caso in cui il registro e' gia' cieco."""
    client = _ClientSenzaRPC()
    aggiorna_categoria_fatture(
        client, ids=[7], categoria="CARNE", source="script_ricategorizza_sede",
        salta_correzioni_manuali=True,
    )
    filtri = client.registro["filtri"]
    assert filtri.get("reviewed_at") == "null"
    assert filtri.get("or") == (
        "categoria_fonte.is.null,categoria_fonte.neq.correzione_cliente"
    )


def test_il_fallback_con_la_guardia_non_scarta_le_righe_senza_fonte():
    """Il difetto che questo test previene, misurato sul live: `categoria_fonte`
    e' NULL su 39.221 righe su 39.515. Un `.neq()` secco le scarterebbe tutte
    (PostgREST esclude i NULL come `<>` in SQL), e la guardia bloccherebbe il
    99% del lavoro legittimo invece di proteggere le 330 arbitrate. La forma
    `or_(is.null, neq.)` e' l'unica che distingue i due casi — la stessa gia'
    usata da `escludi_da_verificare_margini`."""
    client = _ClientSenzaRPC()
    aggiorna_categoria_fatture(
        client, ids=[7], categoria="CARNE", source="script_ricategorizza_sede",
        salta_correzioni_manuali=True,
    )
    espressione = client.registro["filtri"].get("or", "")
    assert "categoria_fonte.is.null" in espressione, (
        "senza il ramo is.null la guardia scarta le righe mai arbitrate"
    )


def test_il_fallback_senza_guardia_non_filtra_le_arbitrate():
    """L'altra direzione: chi non chiede la guardia non deve subirla."""
    client = _ClientSenzaRPC()
    aggiorna_categoria_fatture(
        client, ids=[7], categoria="PESCE", source="correzione_cliente",
    )
    filtri = client.registro["filtri"]
    assert "or" not in filtri
    assert "reviewed_at" not in filtri
