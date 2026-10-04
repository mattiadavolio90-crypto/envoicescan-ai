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
RICHIEDE = [
    "esitoRecuperoTurni", "mostraCostoAssenze", "sintesiRecuperoTurni",
    "vociPersonaleValide", "totalePersonale",
]


def _calcolo(**over):
    base = {
        "costo_dipendenti": 0.0,
        "costo_personale_extra": 0.0,
        "costo_personale_chiamata": 0.0,
        "costo_assenze_a_carico": 0.0,
        "ore_totali": 0.0,
        "ore_extra": 0.0,
        "n_turni": 0,
        "n_senza_costo": 0,
        "n_con_stipendio": 0,
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


# --- Terza voce «Chiamata» (fase C, step C3) -------------------------------


def test_solo_chiamata_compila():
    """Un mese di sole chiamate non e' un recupero a vuoto."""
    esito = _esito(n_turni=2, costo_personale_chiamata=150.0)
    assert esito["azione"] == "compila"
    assert esito["chiamata"] == 150.0
    assert esito["lordo"] == 0
    assert esito["extra"] == 0


def test_compila_porta_le_tre_voci_ognuna_al_suo_posto():
    esito = _esito(
        n_turni=12,
        costo_dipendenti=5074.48,
        costo_personale_extra=120.5,
        costo_personale_chiamata=300.25,
    )
    assert esito["azione"] == "compila"
    assert esito["lordo"] == 5074.48
    assert esito["extra"] == 120.5
    assert esito["chiamata"] == 300.25


def test_tre_voci_a_zero_non_compilano():
    esito = _esito(n_turni=5, n_senza_costo=5)
    assert esito["azione"] == "non_valorizzati"
    assert "chiamata" not in esito


def test_risposta_senza_i_campi_nuovi_vale_zero():
    """Worker non ancora aggiornato: mancano chiamata e n_con_stipendio."""
    vecchia = _calcolo(n_turni=4, costo_dipendenti=400.0)
    del vecchia["costo_personale_chiamata"]
    del vecchia["n_con_stipendio"]
    esito = esegui_ts(
        MODULO, "emit(m.esitoRecuperoTurni(input))", vecchia, richiede=RICHIEDE
    )
    assert esito["azione"] == "compila"
    assert esito["chiamata"] == 0
    assert esito["lordo"] == 400.0
    riga = esegui_ts(
        MODULO, "emit(m.sintesiRecuperoTurni(input))", vecchia, richiede=RICHIEDE
    )
    assert "stipendio" not in riga


def _sintesi(**over):
    return esegui_ts(
        MODULO, "emit(m.sintesiRecuperoTurni(input))", _calcolo(**over), richiede=RICHIEDE
    )


def test_sintesi_dice_quanti_hanno_lo_stipendio_del_mese():
    riga = _sintesi(n_turni=30, ore_totali=240.4, ore_extra=10.6, n_con_stipendio=3)
    assert riga == "30 turni · 240h di cui 11h extra · 3 dipendenti con lo stipendio del mese"


def test_sintesi_al_singolare_con_un_solo_stipendio():
    riga = _sintesi(n_turni=8, ore_totali=64, n_con_stipendio=1, n_senza_costo=2)
    assert riga == (
        "8 turni · 64h di cui 0h extra · 1 dipendente con lo stipendio del mese"
        " · 2 senza costo orario"
    )


def test_sintesi_tace_lo_stipendio_se_nessuno_lo_ha():
    riga = _sintesi(n_turni=8, ore_totali=64, n_senza_costo=2)
    assert riga == "8 turni · 64h di cui 0h extra · 2 senza costo orario"


def test_sintesi_assente_senza_turni():
    assert _sintesi(n_turni=0, n_con_stipendio=2) is None


def _valide(lordo, extra, chiamata):
    return esegui_ts(
        MODULO,
        "emit(m.vociPersonaleValide(input[0], input[1], input[2]))",
        [lordo, extra, chiamata],
        richiede=RICHIEDE,
    )


def test_ogni_voce_negativa_blocca_il_salvataggio():
    assert _valide(0, 0, 0) is True
    assert _valide(-1, 0, 0) is False
    assert _valide(0, -1, 0) is False
    assert _valide(0, 0, -1) is False


def test_totale_personale_somma_le_tre_voci():
    totale = esegui_ts(
        MODULO,
        "emit(m.totalePersonale(input[0], input[1], input[2]))",
        [1000.0, 200.0, 30.0],
        richiede=RICHIEDE,
    )
    assert totale == 1230.0


def test_il_modulo_scrive_le_tre_celle_ognuna_col_suo_valore():
    """Le tre voci del modulo Margini finiscono ciascuna nella sua colonna: se la
    Chiamata mancasse dalla lista, il modulo la mostrerebbe senza salvarla."""
    celle = esegui_ts(
        "lib/costo-personale-turni",
        "emit(m.celleDaSalvare(1000, 200, 37))",
        {},
        richiede=["celleDaSalvare"],
    )
    assert celle == [
        ["costo_dipendenti", 1000],
        ["costo_personale_extra", 200],
        ["costo_personale_chiamata", 37],
    ]
