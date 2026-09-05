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

Nota sul modello (rivisto il 05/09/2026): le ore extra sono un SOTTOINSIEME del
turno. Il totale viene dagli orari di entrata/uscita, e `ore_extra` dice quante
di quelle ore sono straordinario: l'ordinario resta (ore_totali - ore_extra).
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


def test_le_ore_extra_sono_un_sottoinsieme_del_turno():
    """9-17 = 8h totali, di cui 2 extra => 6 ordinarie (modello 05/09/2026).

    Prima del 05/09 lo stesso turno valeva 10h con 8 ordinarie: il totale non
    dipendeva piu' dagli orari inseriti.
    """
    res = _calcola([_turno(costo_orario=10.0, ore_extra=2)])
    assert res["ore_totali"] == 8.0
    assert res["ore_extra"] == 2.0
    assert res["costo_dipendenti"] == 60.0
    assert res["costo_personale_extra"] == 20.0


def test_costo_orario_extra_maggiorato_si_applica_solo_alle_extra():
    res = _calcola([_turno(costo_orario=10.0, ore_extra=2, costo_orario_extra=15.0)])
    assert res["costo_dipendenti"] == 60.0
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


def test_il_clamp_impedisce_piu_extra_delle_ore_lavorate():
    """RILIEVO CHIUSO (05/09/2026) — il clamp di margini.py e' ora una guardia viva.

    Col modello vecchio (extra additive) `min(extra, ore)` era codice morto:
    l'extra era gia' dentro il totale e non poteva eccederlo, quindi un turno
    di 8h con ore_extra=99 produceva 107h totali e **990 EUR** di straordinari
    senza alcun tetto.

    Col modello nuovo il totale viene solo dagli orari (8h), quindi dichiarare
    99 ore extra su un turno di 8 e' incoerente e viene tagliato a 8: tutte le
    ore diventano straordinario, l'ordinario va a 0 e il costo resta ancorato
    alle ore realmente lavorate. Nessun importo puo' piu' crescere senza limite.
    """
    res = _calcola([_turno(costo_orario=10.0, ore_extra=99)])
    assert res["ore_totali"] == 8.0
    assert res["ore_extra"] == 8.0
    assert res["costo_dipendenti"] == 0.0
    assert res["costo_personale_extra"] == 80.0


def test_extra_pari_alle_ore_azzera_l_ordinario_senza_andare_negativo():
    res = _calcola([_turno(costo_orario=10.0, ore_extra=8)])
    assert res["costo_dipendenti"] == 0.0
    assert res["costo_personale_extra"] == 80.0


def test_doppio_turno_nello_stesso_giorno_somma_i_due_slot():
    res = _calcola([_turno(
        ora_inizio="09:00", ora_fine="12:00",
        ora_inizio2="18:00", ora_fine2="23:00", costo_orario=10.0,
    )])
    assert res["ore_totali"] == 8.0
    assert res["costo_dipendenti"] == 80.0
