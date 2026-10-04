"""«Lo stipendio del mese vince» nel frontend del Personale (fase C, 04/10/2026).

**Il caso vivo.** CASATI 14 segna i turni (le ore) durante il mese, senza
costo orario; a fine mese mette lo stipendio dalla busta paga. Fino a C2 turni
e riga mensile si escludevano (409 dal worker, banner nel modulo): il cliente
non poteva mettere lo stipendio e il tab restava a «Paghe non inserite».

Ora convivono, con una regola sola (identica al worker): per chi ha la riga
mensile il costo viene SOLO da li' (ordinario = lordo − extra − chiamata,
extra e chiamata «di cui»); i suoi turni contano come ore, non come costo; le
ore vengono dai turni se ci sono, altrimenti dalla riga mensile, mai insieme.

Si asseriscono le COMPONENTI una per una, non i totali: due errori opposti si
compensano nella somma (lezione di `test_ore_turno_frontend.py`).
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/ore-turno"


def _aggrega(turni):
    return esegui_ts(
        MODULO,
        "emit(m.aggregaPerPersona(input.turni, (t) => t.dipendente_id, (t) => t.ore))",
        {"turni": turni},
        richiede=["aggregaPerPersona"],
    )


def _turno(ore, **over):
    t = {"dipendente_id": "mario", "tipo_giorno": "turno", "mensile": False,
         "ore_extra": None, "costo_orario": None, "costo_orario_extra": None,
         "data_turno": "2026-09-10", "ore": ore}
    t.update(over)
    return t


def _mensile(ore=0, **over):
    t = _turno(ore, mensile=True, data_turno="2026-09-01", lordo_mensile=None,
               importo_extra=None, importo_chiamata=None)
    t.update(over)
    return t


# ── aggregaPerPersona ────────────────────────────────────────────────────────

def _casati(ordine):
    """Due turni con tariffa (che da soli varrebbero 140 EUR) e lo stipendio."""
    turni = [
        _turno(8.0, ore_extra=2, costo_orario=10),
        _turno(6.0, costo_orario=10, data_turno="2026-09-11"),
        _mensile(0, lordo_mensile=1800, importo_extra=200, importo_chiamata=100),
    ]
    return turni if ordine == "mensile_in_coda" else list(reversed(turni))


def test_stipendio_vince_sul_costo_dei_turni_nei_due_ordini():
    """Il costo e' SOLO lo stipendio, qualunque sia l'ordine delle righe.

    Il desktop fonde due fetch (giornalieri poi mensili): la riga mensile
    arriva IN CODA. In una passata sola i turni sarebbero gia' stati sommati.
    """
    for ordine in ("mensile_in_coda", "mensile_in_testa"):
        r = _aggrega(_casati(ordine))
        assert r["costoStd"]["mario"] == 1500.0, ordine   # 1800 - 200 - 100
        assert r["costoExt"]["mario"] == 200.0, ordine
        assert r["costoChi"]["mario"] == 100.0, ordine
        assert r["costoTot"]["mario"] == 1800.0, ordine


def test_con_lo_stipendio_le_ore_vengono_dai_turni_e_non_si_raddoppiano():
    """La riga mensile salvata con ore 148 dichiarate: le ore restano i turni."""
    for ordine in ("in_coda", "in_testa"):
        turni = [_turno(8.0, ore_extra=2), _turno(6.0, data_turno="2026-09-11"),
                 _mensile(148.0, ore_extra=20, lordo_mensile=1800)]
        if ordine == "in_testa":
            turni.reverse()
        r = _aggrega(turni)
        assert r["oreStd"]["mario"] == 12.0, ordine      # (8-2) + 6
        assert r["oreExt"]["mario"] == 2.0, ordine


def test_stipendio_senza_turni_prende_le_ore_dalla_riga_mensile():
    r = _aggrega([_mensile(160.0, ore_extra=20, lordo_mensile=2000, importo_extra=300)])
    assert r["oreStd"]["mario"] == 140.0
    assert r["oreExt"]["mario"] == 20.0
    assert r["costoStd"]["mario"] == 1700.0
    assert r["costoExt"]["mario"] == 300.0
    assert r["costoChi"]["mario"] == 0
    assert r["costoTot"]["mario"] == 2000.0


def test_la_chiamata_e_parte_del_lordo_non_un_addendo():
    """lordo 1000 di cui chiamata 250: ordinario 750, totale 1000 (non 1250)."""
    r = _aggrega([_mensile(0, lordo_mensile=1000, importo_chiamata=250)])
    assert r["costoStd"]["mario"] == 750.0
    assert r["costoExt"]["mario"] == 0
    assert r["costoChi"]["mario"] == 250.0
    assert r["costoTot"]["mario"] == 1000.0


def test_ordinario_mai_negativo_se_extra_e_chiamata_superano_il_lordo():
    r = _aggrega([_mensile(0, lordo_mensile=100, importo_extra=80, importo_chiamata=50)])
    assert r["costoStd"]["mario"] == 0
    assert r["costoExt"]["mario"] == 80.0
    assert r["costoChi"]["mario"] == 50.0
    assert r["costoTot"]["mario"] == 130.0


def test_le_assenze_non_contano_ne_ore_ne_costo_e_non_danno_lo_stipendio():
    """Una ferie con importo a carico non e' un turno lavorato: le ore restano
    quelle dichiarate in busta, e il costo e' lo stipendio."""
    r = _aggrega([
        _turno(8.0, tipo_giorno="ferie", importo_a_carico=70, costo_orario=10),
        _mensile(150.0, lordo_mensile=1600),
    ])
    assert r["oreStd"]["mario"] == 150.0
    assert r["costoTot"]["mario"] == 1600.0


def test_lo_stipendio_di_uno_non_spegne_i_turni_di_un_altro():
    r = _aggrega([
        _turno(8.0, costo_orario=10, dipendente_id="lucia"),
        _turno(8.0, costo_orario=10),
        _mensile(0, lordo_mensile=1500),
    ])
    assert r["costoTot"]["lucia"] == 80.0
    assert r["costoStd"]["lucia"] == 80.0
    assert r["costoTot"]["mario"] == 1500.0
    assert r["oreStd"]["lucia"] == 8.0
    assert r["oreStd"]["mario"] == 8.0


def test_senza_stipendio_tutto_come_prima():
    r = _aggrega([_turno(8.0, ore_extra=2, costo_orario=10, costo_orario_extra=15)])
    assert r["costoStd"]["mario"] == 60.0
    assert r["costoExt"]["mario"] == 30.0
    assert r["costoChi"] == {}
    assert r["costoTot"]["mario"] == 90.0


# ── oreTurniPerDipendente ────────────────────────────────────────────────────

def _ore_segnate(turni):
    return esegui_ts(
        MODULO,
        "emit(m.oreTurniPerDipendente(input.turni, (t) => t.ore))",
        {"turni": turni},
        richiede=["oreTurniPerDipendente"],
    )


def test_ore_segnate_sommano_solo_i_turni_lavorati():
    r = _ore_segnate([
        _turno(8.0, ore_extra=2),
        _turno(7.5, data_turno="2026-09-11"),
        _turno(8.0, tipo_giorno="riposo"),
        _turno(8.0, tipo_giorno="ferie"),
        _turno(8.0, tipo_giorno="malattia"),
        _mensile(148.0, ore_extra=20, lordo_mensile=1800),
        _turno(4.0, dipendente_id="lucia"),
    ])
    assert r["mario"] == {"ordinarie": 13.5, "extra": 2.0, "nTurni": 2}
    assert r["lucia"] == {"ordinarie": 4.0, "extra": 0, "nTurni": 1}


def test_ore_segnate_vuote_per_chi_ha_solo_la_riga_mensile():
    r = _ore_segnate([_mensile(148.0, lordo_mensile=1800), _turno(8.0, tipo_giorno="riposo")])
    assert r == {}


def test_ore_segnate_con_extra_oltre_le_ore_restano_le_ore_del_turno():
    r = _ore_segnate([_turno(8.0, ore_extra=10)])
    assert r["mario"] == {"ordinarie": 0, "extra": 8.0, "nTurni": 1}


# ── riepilogo per dipendente di /m ───────────────────────────────────────────

def _riepilogo(turni):
    return esegui_ts(
        MODULO,
        "emit(m.riepilogoPerDipendente(input.turni, (t) => t.ore))",
        {"turni": turni},
        richiede=["riepilogoPerDipendente"],
    )


def _per_id(righe):
    return {r["dipendenteId"]: r for r in righe}


def test_riepilogo_mobile_senza_stipendio_somma_turni_e_assenze_a_carico():
    """Il comportamento di /m che resta: per chi non ha lo stipendio la ferie
    pagata e' un costo che altrimenti non comparirebbe."""
    r = _per_id(_riepilogo([
        _turno(8.0, ore_extra=2, costo_orario=10, costo_orario_extra=15),
        _turno(8.0, tipo_giorno="ferie", importo_a_carico=70),
        _turno(8.0, tipo_giorno="malattia", importo_a_carico=30),
        _turno(8.0, tipo_giorno="riposo"),
    ]))["mario"]
    assert r["costoTot"] == 190.0            # 6x10 + 2x15 + 70 + 30
    assert r["oreLavorate"] == 8.0
    assert r["giorniLavorati"] == 1
    assert r["giorniFerie"] == 1
    assert r["giorniMalattia"] == 1
    assert r["giorniRiposo"] == 1
    assert r["haStipendio"] is False


def test_riepilogo_mobile_con_stipendio_costo_solo_dalla_busta():
    """Turni con tariffa (80) + ferie a carico (70) + stipendio 1500: 1500."""
    for inverti in (False, True):
        turni = [
            _turno(8.0, costo_orario=10),
            _turno(8.0, tipo_giorno="ferie", importo_a_carico=70, data_turno="2026-09-12"),
            _mensile(148.0, lordo_mensile=1500, importo_chiamata=100),
        ]
        if inverti:
            turni.reverse()
        r = _per_id(_riepilogo(turni))["mario"]
        assert r["costoTot"] == 1500.0, inverti
        assert r["oreLavorate"] == 8.0, inverti     # dai turni, non 148 + 8
        assert r["haStipendio"] is True, inverti
        assert [t["data_turno"] for t in r["turniGiornalieri"]] == ["2026-09-10", "2026-09-12"], inverti


def test_riepilogo_mobile_stipendio_senza_turni_usa_le_ore_dichiarate():
    r = _per_id(_riepilogo([_mensile(148.0, lordo_mensile=1500)]))["mario"]
    assert r["oreLavorate"] == 148.0
    assert r["costoTot"] == 1500.0
    assert r["giorniLavorati"] == 0
    assert r["turniGiornalieri"] == []


# ── payloadMensile: il corpo che desktop e /m mandano al worker ─────────────

def _payload(**over):
    v = {"oreOrd": 0, "oreExtra": 0, "importoOrd": 0, "importoExtra": 0,
         "importoChiamata": 0, "oreDaiTurni": False, "note": ""}
    v.update(over)
    return esegui_ts(MODULO, "emit(m.payloadMensile(input.v))", {"v": v},
                     richiede=["payloadMensile"])


def test_payload_con_ore_dai_turni_manda_zero_ore_e_nessuna_extra():
    """Con i turni le ore le conta il worker: ore_totali 0 e niente ore_extra,
    anche se nei campi (nascosti) resta un valore — il worker rifiuterebbe
    ore_extra > ore_totali."""
    r = _payload(oreDaiTurni=True, oreOrd=150, oreExtra=12,
                 importoOrd=1500, importoExtra=200, importoChiamata=100)
    p = r["payload"]
    assert p["ore_totali"] == 0
    assert p["ore_extra"] is None
    assert p["lordo"] == 1800
    assert p["importo_extra"] == 200
    assert p["importo_chiamata"] == 100


def test_payload_senza_turni_manda_le_ore_scritte():
    p = _payload(oreOrd=140, oreExtra=8, importoOrd=1700, importoExtra=150)["payload"]
    assert p["ore_totali"] == 148
    assert p["ore_extra"] == 8
    assert p["lordo"] == 1850
    assert p["importo_extra"] == 150
    assert p["importo_chiamata"] is None


def test_payload_la_chiamata_entra_nel_lordo():
    p = _payload(importoOrd=1000, importoChiamata=37, oreOrd=10)["payload"]
    assert p["lordo"] == 1037
    assert p["importo_chiamata"] == 37


def test_payload_con_ore_dai_turni_senza_stipendio_e_un_errore():
    assert _payload(oreDaiTurni=True, oreOrd=150) == {"errore": "Inserisci lo stipendio del mese"}


def test_payload_senza_ore_ne_lordo_e_un_errore():
    assert "errore" in _payload()


def test_payload_ogni_importo_negativo_e_un_errore():
    for campo in ("importoOrd", "importoExtra", "importoChiamata"):
        v = {"oreOrd": 10, "importoOrd": 100, "importoExtra": 0, "importoChiamata": 0}
        v[campo] = -1
        r = _payload(**v)
        assert r == {"errore": "Gli importi non possono essere negativi"}, campo
