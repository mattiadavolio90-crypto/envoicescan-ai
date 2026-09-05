"""Un "Recupera dal tab Personale" a vuoto non deve azzerare il costo nel MOL.

**Il difetto, misurato il 5/9/2026.** Il costo del personale nel MOL vive in
`margini_mensili.costo_dipendenti` e ci arriva solo da un inserimento: i turni
non lo alimentano da soli. Il bottone «Recupera dal tab Personale» e' quell'
inserimento assistito.

A DB, il 5/9: `turni_personale` ha **107 righe su 1 sede**, e `costo_orario` e'
**NULL su 107 su 107** (`lordo_mensile` idem, `dipendenti.costo_orario_default`
NULL su tutti e 4). Su quei turni l'endpoint restituisce `costo_dipendenti = 0`
— e il dialog faceva `setLordo(toStr(0))`, che con `toStr` vale `""`: i campi si
svuotavano. Un Salva dopo quel Recupero scriveva **0** su un mese che aveva un
costo vero (CASATI 14 a luglio: **5.074,48 €**), togliendolo dal MOL.

Non e' teorico: nel 2026 il costo personale e' gia' fermo a **luglio su 6 sedi
su 6**, con agosto e settembre a zero su sedi da 400-473 k€/mese di fatturato.

Le assenze restano **fuori** dal totale: il worker le tiene isolate da
`costo_dipendenti` di proposito (`TestMarginiCostoAssenze` in
tests/test_turni_mensili.py). Qui si prova solo che vengano *mostrate*, perche'
oggi il dialog le scartava senza dirlo.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/costo-personale-turni"
RICHIEDE = ["esitoRecuperoTurni", "mostraCostoAssenze"]


def _calcolo(**over):
    base = {
        "costo_dipendenti": 0.0,
        "costo_personale_extra": 0.0,
        "costo_assenze_a_carico": 0.0,
        "ore_totali": 0.0,
        "ore_extra": 0.0,
        "n_turni": 0,
        "n_senza_costo": 0,
        "n_giorni_assenza": 0,
    }
    base.update(over)
    return base


def _esito(**over):
    return esegui_ts(
        MODULO, "emit(m.esitoRecuperoTurni(input))", _calcolo(**over), richiede=RICHIEDE
    )


def _mostra(**over):
    return esegui_ts(
        MODULO, "emit(m.mostraCostoAssenze(input))", _calcolo(**over), richiede=RICHIEDE
    )


def test_i_107_turni_reali_senza_costo_orario_non_compilano():
    """Il caso misurato a DB: turni presenti, nessuno valorizzato."""
    esito = _esito(n_turni=107, n_senza_costo=107)
    assert esito["azione"] == "non_valorizzati"
    assert "lordo" not in esito


def test_nessun_turno_non_e_un_recupero_a_zero():
    assert _esito(n_turni=0)["azione"] == "nessun_turno"


def test_risposta_assente_non_compila():
    """Un guasto non deve diventare "zero costo"."""
    esito = esegui_ts(
        MODULO, "emit(m.esitoRecuperoTurni(null))", richiede=RICHIEDE
    )
    assert esito["azione"] == "nessun_turno"


def test_turni_valorizzati_compilano_i_campi():
    esito = _esito(n_turni=12, costo_dipendenti=5074.48, costo_personale_extra=120.5)
    assert esito["azione"] == "compila"
    assert esito["lordo"] == 5074.48
    assert esito["extra"] == 120.5


def test_solo_extra_valorizzato_compila_lo_stesso():
    """Un mese di soli straordinari non e' un recupero a vuoto."""
    esito = _esito(n_turni=3, costo_personale_extra=90.0)
    assert esito["azione"] == "compila"
    assert esito["extra"] == 90.0


def test_turni_parzialmente_valorizzati_riportano_gli_esclusi():
    esito = _esito(n_turni=10, n_senza_costo=4, costo_dipendenti=800.0)
    assert esito["azione"] == "compila"
    assert esito["nSenzaCosto"] == 4


def test_assenze_a_carico_si_mostrano_solo_se_costano():
    assert _mostra(n_giorni_assenza=1, costo_assenze_a_carico=50.0) is True


def test_un_riposo_non_costa_e_non_si_mostra():
    """n_giorni_assenza > 0 non basta: il riposo non ha importo a carico."""
    assert _mostra(n_giorni_assenza=1, costo_assenze_a_carico=0.0) is False


def test_assenze_restano_fuori_dai_campi_compilati():
    """Isolamento voluto dal worker: non si sommano di nascosto al lordo."""
    esito = _esito(n_turni=1, costo_dipendenti=96.0, costo_assenze_a_carico=30.0)
    assert esito["lordo"] == 96.0
