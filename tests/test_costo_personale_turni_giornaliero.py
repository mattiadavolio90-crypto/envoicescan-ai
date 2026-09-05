"""Il ramo GIORNALIERO di get_costo_personale_da_turni — quello che i dati usano.

`tests/test_turni_mensili.py` copre il ramo `mensile` (busta paga) e le assenze.
Il ramo giornaliero — turni con `costo_orario` e `ore_extra`, cioe' come si
inseriscono i turni dal tab Personale — non aveva presidi, ed e' l'unico che i
dati reali percorrono: il 5/9/2026 `turni_personale` ha **107 righe, tutte
giornaliere** (`mensile` false su 107 su 107, 1 sola sede, 3 dipendenti).

Il caso piu' importante e' proprio quello misurato: `costo_orario` NULL su 107
su 107. Quei turni **non contribuiscono** al totale e vanno contati a parte in
`n_senza_costo`, o il costo del mese esce silenziosamente parziale — e finisce
in `margini_mensili.costo_dipendenti`, quindi nel MOL.

Nota sul modello (docstring di `_ore_turno`): le ore extra sono AGGIUNTIVE, non
un sottoinsieme, e l'ordinario si ricava come (ore_totali - ore_extra).
"""
from unittest.mock import MagicMock, patch

import services.routers.margini as margini

from tests.test_turni_mensili import _query_mock


def _patch_margini(turni):
    client = MagicMock()
    client.table.return_value = _query_mock(turni)
    return patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    )


def _turno(**over):
    t = {
        "id": "t1", "dipendente_id": "dip-1", "data_turno": "2026-09-02",
        "mensile": False, "tipo_giorno": "turno",
        "ora_inizio": "09:00", "ora_fine": "17:00",
    }
    t.update(over)
    return t


def _calcola(turni):
    with _patch_margini(turni):
        return margini.get_costo_personale_da_turni(
            anno=2026, mese=9, authorization="Bearer x"
        )


def test_turni_senza_costo_orario_non_entrano_nel_totale():
    """Il caso reale: 107 turni, nessun costo orario impostato."""
    res = _calcola([_turno(id=f"t{i}", costo_orario=None) for i in range(107)])
    assert res["costo_dipendenti"] == 0.0
    assert res["n_senza_costo"] == 107
    assert res["n_turni"] == 107


def test_un_turno_valorizzato_paga_le_ore_ordinarie():
    res = _calcola([_turno(costo_orario=12.0)])
    assert res["costo_dipendenti"] == 96.0
    assert res["ore_totali"] == 8.0


def test_le_ore_extra_sono_aggiuntive_e_vanno_sul_loro_campo():
    """8h da orari + 2h extra = 10h totali; l'ordinario resta 8h."""
    res = _calcola([_turno(costo_orario=10.0, ore_extra=2)])
    assert res["ore_totali"] == 10.0
    assert res["ore_extra"] == 2.0
    assert res["costo_dipendenti"] == 80.0
    assert res["costo_personale_extra"] == 20.0


def test_costo_orario_extra_maggiorato_si_applica_solo_alle_extra():
    res = _calcola([_turno(costo_orario=10.0, ore_extra=2, costo_orario_extra=15.0)])
    assert res["costo_dipendenti"] == 80.0
    assert res["costo_personale_extra"] == 30.0


def test_senza_costo_orario_extra_le_extra_usano_la_tariffa_standard():
    res = _calcola([_turno(costo_orario=10.0, ore_extra=2, costo_orario_extra=None)])
    assert res["costo_personale_extra"] == 20.0


def test_turno_misto_valorizzato_e_no_somma_solo_il_valorizzato():
    """Il totale resta parziale, ma n_senza_costo lo dichiara."""
    res = _calcola([
        _turno(id="a", costo_orario=12.0),
        _turno(id="b", costo_orario=None),
    ])
    assert res["costo_dipendenti"] == 96.0
    assert res["n_senza_costo"] == 1
    assert res["n_turni"] == 2


def test_costo_orario_zero_non_e_costo_mancante():
    """0 e' un valore inserito (stagista non pagato), non un'assenza di dato."""
    res = _calcola([_turno(costo_orario=0)])
    assert res["n_senza_costo"] == 0
    assert res["costo_dipendenti"] == 0.0


def test_il_clamp_min_extra_ore_non_puo_mai_scattare():
    """RILIEVO (5/9/2026) — la guardia difensiva di margini.py:1011 e' codice morto.

    `min(extra, ore)` confronta le ore extra con `_ore_turno(t)`, che vale
    `ore_orari + extra`: l'extra e' gia' dentro il totale, quindi non puo' mai
    eccederlo e il clamp non scatta. Un turno di 8h con `ore_extra=99` produce
    107h totali: l'ordinario resta 8h (107-99), ma gli straordinari valgono
    **990 EUR** a 10 EUR/h. Il totale del mese cresce senza limite col dato
    inserito, e non c'e' nessun tetto a proteggerlo.

    Il test fissa il comportamento ATTUALE, non quello desiderato: correggerlo
    cambia un importo che finisce nel MOL, ed e' una decisione di Mattia. Oggi
    l'esposizione e' nulla (0 turni con ore_extra su 107 a DB, 5/9/2026), per
    questo e' un rilievo e non un fix.
    """
    res = _calcola([_turno(costo_orario=10.0, ore_extra=99)])
    assert res["ore_totali"] == 107.0
    assert res["ore_extra"] == 99.0
    assert res["costo_dipendenti"] == 80.0
    assert res["costo_personale_extra"] == 990.0


def test_doppio_turno_nello_stesso_giorno_somma_i_due_slot():
    res = _calcola([_turno(
        ora_inizio="09:00", ora_fine="12:00",
        ora_inizio2="18:00", ora_fine2="23:00", costo_orario=10.0,
    )])
    assert res["ore_totali"] == 8.0
    assert res["costo_dipendenti"] == 80.0
