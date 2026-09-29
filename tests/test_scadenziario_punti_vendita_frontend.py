"""Filtro punti vendita di Gestione Fatture in catena (`lib/scadenziario.ts`).

Mattia, 29/9: le pillole per sede sceglievano un punto vendita alla volta; ora
una tendina ne sceglie quanti se ne vuole. Decide quali fatture restano in
elenco: un documento che cade fuori dal filtro non da' errore, la lista e' solo
piu' corta. Si prova qui la logica, eseguita con node.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

SEDI = [
    {"id": "a", "nome": "LAND DEI SAPORI"},
    {"id": "b", "nome": "VILLA GUARDIA"},
    {"id": "g", "nome": "Gruppo"},
]


def _in(rid, scelti):
    return esegui_ts(
        MODULO,
        "emit(m.inPuntiVendita(input.rid, new Set(input.scelti)));",
        argomento={"rid": rid, "scelti": scelti},
        richiede=["inPuntiVendita"],
    )


def _alterna(scelti, id_, tutti):
    return sorted(esegui_ts(
        MODULO,
        "emit([...m.alternaPuntoVendita(new Set(input.scelti), input.id, input.tutti)]);",
        argomento={"scelti": scelti, "id": id_, "tutti": tutti},
        richiede=["alternaPuntoVendita"],
    ))


def _etichetta(scelti, sedi=SEDI):
    return esegui_ts(
        MODULO,
        "emit(m.etichettaPuntiVendita(new Set(input.scelti), input.sedi));",
        argomento={"scelti": scelti, "sedi": sedi},
        richiede=["etichettaPuntiVendita"],
    )


# ─── inPuntiVendita ────────────────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["a", "b", "g", None])
def test_nessuno_scelto_passano_tutti(rid):
    assert _in(rid, []) is True


def test_uno_scelto_passa_solo_lui():
    assert _in("a", ["a"]) is True
    assert _in("b", ["a"]) is False


def test_piu_scelti_passano_tutti_i_scelti():
    """Il motivo della modifica: prima se ne sceglieva uno solo."""
    assert _in("a", ["a", "g"]) is True
    assert _in("g", ["a", "g"]) is True
    assert _in("b", ["a", "g"]) is False


def test_documento_senza_sede_escluso_se_si_filtra():
    assert _in(None, ["a"]) is False


# ─── alternaPuntoVendita ───────────────────────────────────────────────────

def test_spunta_e_toglie():
    assert _alterna([], "a", ["a", "b", "g"]) == ["a"]
    assert _alterna(["a"], "b", ["a", "b", "g"]) == ["a", "b"]
    assert _alterna(["a", "b"], "a", ["a", "b", "g"]) == ["b"]


def test_spuntarli_tutti_torna_a_nessun_filtro():
    assert _alterna(["a", "b"], "g", ["a", "b", "g"]) == []


# ─── etichettaPuntiVendita ─────────────────────────────────────────────────

def test_etichetta_nessuno_e_tutti():
    assert _etichetta([]) == "Tutti i punti vendita"
    assert _etichetta(["a", "b", "g"]) == "Tutti i punti vendita"


def test_etichetta_uno_dice_il_nome():
    assert _etichetta(["b"]) == "VILLA GUARDIA"


def test_etichetta_piu_dice_quanti():
    assert _etichetta(["a", "g"]) == "2 punti vendita"


def test_etichetta_ignora_id_che_non_sono_fra_le_sedi():
    """Una sede sparita dalla lista (disattivata a pagina aperta) non conta."""
    assert _etichetta(["a", "zz"]) == "LAND DEI SAPORI"
