"""Osservazioni da consulente in catena — `lib/catena-osservazioni.ts`.

Il modulo TS vero viene eseguito da node via `tests/helpers_ts.py` (vedi
`test_catena_segnali_raggruppati_frontend.py` per il perche' non in apps/web).

Cosa protegge:
- durante un deploy il worker vecchio non manda `osservazioni`, e uno snapshot
  scritto prima del deploy nemmeno: il campo assente e' "nessuna osservazione",
  mai un errore della card segnali (che direbbe «non e' stato possibile
  controllare i punti vendita» su una risposta buona);
- una riga senza testo non si mostra (un nome di sede seguito dal nulla);
- il bottone «Vedi PV» solo con un id: senza, cambierebbe la sede attiva del
  cliente su un PV qualunque — stessa regola dei segnali.
"""

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-osservazioni"


def _oss(testo="📊 Nelle ultime 4 settimane…", rid="a"):
    return {"tipo": "andamento_incasso", "severity": "success", "ristorante_id": rid,
            "pv_nome": "PV Alfa", "testo": testo, "cta_page": "/margini"}


def _da_mostrare(risposta):
    return esegui_ts(MODULO, "emit(m.osservazioniDaMostrare(input));",
                     argomento=risposta, richiede=["osservazioniDaMostrare"])


def _destinazione(o):
    return esegui_ts(MODULO, "emit(m.haDestinazione(input));",
                     argomento=o, richiede=["haDestinazione"])


@pytest.mark.parametrize("risposta", [
    None,
    {},
    {"segnali": []},
    {"segnali": [], "osservazioni": None},
    {"segnali": [], "osservazioni": "rotto"},
    {"segnali": [], "osservazioni": {"0": _oss()}},
])
def test_campo_assente_o_malformato_e_nessuna_osservazione(risposta):
    assert _da_mostrare(risposta) == []


def test_le_osservazioni_valide_passano_nell_ordine_del_backend():
    lista = [_oss(testo="primo", rid="b"), _oss(testo="secondo", rid="a")]
    assert _da_mostrare({"osservazioni": lista}) == lista


@pytest.mark.parametrize("scarto", [
    None, 42, "stringa", _oss(testo=""), _oss(testo="   "), dict(_oss(), testo=None),
])
def test_una_riga_senza_testo_non_si_mostra(scarto):
    buona = _oss(testo="resta")
    assert _da_mostrare({"osservazioni": [scarto, buona]}) == [buona]


@pytest.mark.parametrize("rid, atteso", [("a", True), ("", False), ("  ", False), (None, False)])
def test_il_bottone_vedi_pv_solo_con_una_destinazione(rid, atteso):
    assert _destinazione(dict(_oss(), ristorante_id=rid)) is atteso
