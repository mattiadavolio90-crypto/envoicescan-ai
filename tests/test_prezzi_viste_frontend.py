"""Le viste delle variazioni di prezzo (`lib/prezzi-viste.ts`), comuni a
Osservatorio del PV e catena: Tutti, Preferiti, Da controllare.

«Da controllare» tiene fuori da Tutti — e quindi dai totali — i prezzi saltati
di 10 volte o piu' (cambio di confezione). La stella si salva con le chiavi
intere: col nome troncato a video 10 preferiti su 19 non si riaccendevano.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/prezzi-viste"
FUNZIONI = ("inVista", "contaDaControllare", "coppiaPreferito", "chiavePreferito")


def _ts(codice, argomento=None):
    return esegui_ts(MODULO, codice, argomento=argomento, richiede=FUNZIONI)


@pytest.mark.parametrize("da_controllare, vista, preferito, atteso", [
    (False, "tutti", False, True),
    (True, "tutti", False, False),       # fuori da Tutti: e' cio' che lo toglie dai totali
    (True, "tutti", True, False),
    (False, "preferiti", True, True),
    (False, "preferiti", False, False),
    (True, "preferiti", True, False),    # neanche fra i preferiti: resta nella sua vista
    (True, "da_controllare", False, True),
    (False, "da_controllare", True, False),
])
def test_in_vista(da_controllare, vista, preferito, atteso):
    arg = {"r": {"da_controllare": da_controllare}, "vista": vista, "p": preferito}
    assert _ts("emit(m.inVista(input.r, input.vista, input.p))", arg) is atteso


def test_una_riga_senza_il_campo_e_una_variazione_vera():
    """Le response in cache da prima del campo non hanno `da_controllare`."""
    assert _ts('emit([m.inVista({}, "tutti", false), m.inVista({}, "da_controllare", false)])') == [True, False]


def test_conta_da_controllare():
    assert _ts("emit(m.contaDaControllare(input))", [{"da_controllare": True}, {}, {"da_controllare": False}]) == 1


def test_la_stella_usa_le_chiavi_intere_quando_ci_sono():
    r = {"prodotto": "PRODOTTO TRONCATO", "fornitore": "DINGFENG IMPORTEXPORT S.R.L. U",
         "desc_key": "PRODOTTO TRONCATO ANCHE PIU LUNGO", "forn_key": "DINGFENG IMPORTEXPORT S.R.L. UNIPERSONALE"}
    assert _ts("emit(m.coppiaPreferito(input))", r) == {
        "prodotto": "PRODOTTO TRONCATO ANCHE PIU LUNGO", "fornitore": "DINGFENG IMPORTEXPORT S.R.L. UNIPERSONALE",
    }


def test_senza_chiavi_ripiega_sul_nome_ripulito():
    r = {"prodotto": " limone ⚠️ >6m", "fornitore": " Mefon "}
    assert _ts("emit(m.chiavePreferito(input))", r) == "LIMONE|MEFON"
