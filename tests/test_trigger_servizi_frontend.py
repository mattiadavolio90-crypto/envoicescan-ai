"""`triggerAbilitati` decide se il cliente vede i suggerimenti commerciali.

Questa funzione era **corretta e senza alcun test**, mentre il difetto stava a
monte: `_normalize_pagine` scartava `trigger_servizi_off` perche' non e' una
chiave-pagina, quindi la lista non lo conteneva mai e qui si tornava sempre
`true`. L'admin spegneva l'interruttore, il DB lo registrava, il cliente
continuava a vedere i suggerimenti — e nessuno dei due lati era "sbagliato" da
solo. Il presidio della giunzione sta in `test_tab_flags_frontend.py`; qui si
fissa l'estremo TS, che restava scoperto.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/trigger-servizi"
_RICHIEDE = ["triggerAbilitati"]


def _abilitati(pagine):
    return esegui_ts(
        MODULO, "emit(m.triggerAbilitati(input))", pagine, richiede=_RICHIEDE
    )


def test_admin_vede_i_trigger():
    # pagine == null = nessuna restrizione.
    assert _abilitati(None) is True


def test_cliente_senza_flag_vede_i_trigger():
    # Convenzione inversa: assente = ACCESI, anche per i clienti esistenti.
    assert _abilitati(["margini", "prezzi"]) is True


def test_flag_presente_spegne_i_trigger():
    assert _abilitati(["margini", "trigger_servizi_off"]) is False


# ─── Boost AI (fase J, 10/10/2026): al 75% dei crediti del mese ──────────────
#
# Decisioni di Mattia: l'offerta compare al 75% dei crediti del mese, non se il
# cliente ha ancora una ricarica da spendere, e solo a chi compra (il titolare).

import pytest  # noqa: E402

_RICHIEDE_BOOST = ["valutaTrigger", "segnaliBoost"]


def _home(segnali):
    return esegui_ts(MODULO, 'emit(m.valutaTrigger("home", input))', segnali, richiede=_RICHIEDE_BOOST)


def _sig(mese, limite=1000, ricarica=0, titolare=True):
    return {"creditiMese": mese, "creditiMeseLimite": limite, "creditiRicarica": ricarica, "titolare": titolare}


@pytest.mark.parametrize("mese,atteso", [(749, None), (750, "boost"), (1000, "boost"), (1002, "boost")])
def test_il_boost_compare_al_75_per_cento(mese, atteso):
    out = _home(_sig(mese))
    assert (out["key"] if out else None) == atteso


def test_il_boost_porta_alla_card_del_servizio():
    out = _home(_sig(800))
    assert out["servizioKey"] == "boost_ai"
    assert "10€" in out["messaggio"] and "300 crediti" in out["messaggio"]


def test_con_una_ricarica_da_spendere_non_compare():
    assert _home(_sig(900, ricarica=3)) is None


def test_al_collaboratore_non_compare():
    assert _home(_sig(900, titolare=False)) is None
    assert _home({"creditiMese": 900, "creditiMeseLimite": 1000, "creditiRicarica": 0}) is None


def test_senza_crediti_del_mese_non_compare():
    """Piano free o worker senza il mese: niente offerta su un numero che non c'e'."""
    assert _home(_sig(0, limite=0)) is None
    assert _home({"titolare": True}) is None


def test_la_soglia_e_quella_decisa():
    assert esegui_ts(MODULO, "emit(m.SOGLIA_BOOST)", None, richiede=_RICHIEDE_BOOST) == 0.75


def test_i_segnali_vengono_dalla_quota_del_contatore():
    quota = {"limiteGiorno": 150, "limiteMese": 1500, "oggi": 6, "mese": 1200, "ricarica": 0}
    out = esegui_ts(MODULO, "emit(m.segnaliBoost(input, true))", quota, richiede=_RICHIEDE_BOOST)
    assert out == {"creditiMese": 1200, "creditiMeseLimite": 1500, "creditiRicarica": 0, "titolare": True}


def test_il_boost_non_esce_nelle_altre_pagine():
    for pagina in ("margini", "prezzi", "analisi-fatture"):
        out = esegui_ts(
            MODULO, f'emit(m.valutaTrigger("{pagina}", input))', _sig(1000), richiede=_RICHIEDE_BOOST
        )
        assert out is None or out["key"] != "boost"
