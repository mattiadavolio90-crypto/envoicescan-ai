"""L'avatar della Home (`lib/avatar-flusso.ts`, fase L del 15/10/2026).

Il flusso disegnato non si prova qui (canvas, niente runner): si prova la logica che
decide cosa fa. Ognuna di queste regole, se si rompe, cambia cosa vede il cliente:

- il modo: la voce vince su tutto, poi l'attesa della risposta, poi la chat a fuoco;
- la voce sale svelta e scende piano, se no il flusso trema;
- la frase evidenziata durante «Ascolta» e' quella letta, non quella del saluto;
- il benvenuto parte una volta al giorno di Roma, mai con meno animazioni;
- i nodi di luce stanno dove il nastro si mostra di taglio.
"""

import math

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/avatar-flusso"


def _chiama(fn, *args):
    return esegui_ts(MODULO, f"emit(m.{fn}(...input));", argomento=list(args), richiede=[fn])


# ─── il modo ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "parla,pensa,ascolta,atteso",
    [
        (True, True, True, "parla"),
        (True, False, False, "parla"),
        (False, True, True, "pensa"),
        (False, False, True, "ascolta"),
        (False, False, False, "riposo"),
    ],
)
def test_il_modo_segue_la_priorita(parla, pensa, ascolta, atteso):
    assert _chiama("modoAvatar", {"parla": parla, "pensa": pensa, "ascolta": ascolta}) == atteso


def test_ogni_modo_ha_la_sua_scritta():
    testi = esegui_ts(MODULO, "emit(m.TESTO_MODO);")
    assert testi == {
        "riposo": "Pronto",
        "ascolta": "Ti ascolto",
        "pensa": "Sto pensando…",
        "parla": "Sto leggendo il briefing",
    }


# ─── la voce ──────────────────────────────────────────────────────────────

def test_la_voce_sale_svelta_e_scende_piano():
    sale = _chiama("livelloVoce", 0, 1, 0.1)
    scende = 1 - _chiama("livelloVoce", 1, 0, 0.1)
    assert sale > 0.8, sale
    assert scende < 0.5, scende


def test_senza_tempo_la_voce_non_si_muove():
    assert _chiama("livelloVoce", 0.3, 1, 0) == pytest.approx(0.3)
    assert _chiama("avvicina", 0.3, 1, 5, 0) == pytest.approx(0.3)


def test_la_voce_simulata_resta_fra_0_e_1_e_si_muove():
    valori = esegui_ts(
        MODULO,
        "emit(Array.from({length: 400}, (_, i) => m.voceSimulata(i * 0.037)));",
        richiede=["voceSimulata"],
    )
    assert min(valori) >= 0 and max(valori) <= 1
    assert max(valori) - min(valori) > 0.3


# ─── la geometria ─────────────────────────────────────────────────────────

SPINTA = {"fase": 1.3, "amp": 1, "voce": 0, "pensa": 0, "uc": 0.5, "vicino": 0, "verso": 0}
NASTRO = {"fase": 0, "larg": 1, "dy": 0.02}


def test_la_voce_increspa_il_nastro():
    quieto = _chiama("centroNastro", 0.37, 2.0, SPINTA, NASTRO)
    parla = _chiama("centroNastro", 0.37, 2.0, {**SPINTA, "voce": 1}, NASTRO)
    assert parla != pytest.approx(quieto)


def test_il_nastro_si_piega_verso_il_cursore():
    sopra = _chiama("centroNastro", 0.5, 2.0, {**SPINTA, "vicino": 1, "verso": 1}, NASTRO)
    lontano = _chiama("centroNastro", 0.5, 2.0, SPINTA, NASTRO)
    sotto = _chiama("centroNastro", 0.5, 2.0, {**SPINTA, "vicino": 1, "verso": -1}, NASTRO)
    assert sopra > lontano > sotto


def test_ascoltare_apre_l_onda_e_pensare_la_fa_girare():
    fermo = {"ascolta": 0, "pensa": 0, "parla": 0}
    assert _chiama("ampiezza", {**fermo, "ascolta": 1}, 0) > _chiama("ampiezza", fermo, 0)
    v_fermo = _chiama("velocita", fermo)
    v_pensa = _chiama("velocita", {**fermo, "pensa": 1})
    v_ascolta = _chiama("velocita", {**fermo, "ascolta": 1})
    assert v_pensa["giro"] > v_ascolta["giro"] > v_fermo["giro"]


@pytest.mark.parametrize("giro,fase", [(0.0, 0.0), (1.7, 2.1), (13.4, 4.2), (-2.0, 0.0)])
def test_i_nodi_stanno_dove_il_nastro_e_di_taglio(giro, fase):
    giri = esegui_ts(MODULO, "emit(m.GIRI);")
    assert isinstance(giri, (int, float)), "GIRI sparito da lib/avatar-flusso"
    nodi = _chiama("nodiDiTaglio", giro, fase)
    assert nodi == sorted(nodi)
    assert nodi, "con 1,15 giri un nastro si mostra di taglio almeno una volta"
    for u in nodi:
        assert 0.06 <= u <= 0.94
        phi = u * 2 * math.pi * giri + giro + fase
        assert abs(math.cos(phi)) < 1e-9, (u, phi)


# ─── la frase letta ───────────────────────────────────────────────────────

NARRATIVA = "Ieri hai incassato 2.340 €, il 12% in più. Il food cost è al 31,8%! Manca il personale"


def test_le_frasi_non_si_spezzano_sulle_migliaia_e_tengono_la_coda():
    elenco = _chiama("frasi", NARRATIVA)
    assert [f["testo"] for f in elenco] == [
        "Ieri hai incassato 2.340 €, il 12% in più. ",
        "Il food cost è al 31,8%! ",
        "Manca il personale",
    ]
    assert "".join(f["testo"] for f in elenco) == NARRATIVA


def test_fraseal_trova_la_frase_del_carattere():
    elenco = _chiama("frasi", NARRATIVA)
    seconda = NARRATIVA.index("Il food")
    assert esegui_ts(MODULO, "emit(m.fraseAl(m.frasi(input[0]), input[1]));", argomento=[NARRATIVA, seconda], richiede=["fraseAl"]) == 1
    assert esegui_ts(MODULO, "emit(m.fraseAl(m.frasi(input[0]), -1));", argomento=[NARRATIVA], richiede=["fraseAl"]) == -1
    assert len(elenco) == 3


def test_sul_saluto_non_si_evidenzia_niente():
    testo = "Buongiorno Mattia. " + NARRATIVA
    assert _chiama("carattereNarrativa", testo, NARRATIVA, 0.0) == -1
    assert _chiama("carattereNarrativa", testo, NARRATIVA, 0.05) == -1


def test_a_meta_lettura_si_e_dentro_la_narrativa():
    testo = "Buongiorno Mattia. " + NARRATIVA
    c = _chiama("carattereNarrativa", testo, NARRATIVA, 0.5)
    assert c == math.floor(0.5 * len(testo)) - len("Buongiorno Mattia. ")


def test_un_avviso_dopo_la_narrativa_non_si_evidenzia():
    testo = NARRATIVA + " Hai 3 fatture da collocare."
    assert _chiama("carattereNarrativa", testo, NARRATIVA, 0.99) == -1


def test_senza_narrativa_nel_testo_niente_evidenza():
    assert _chiama("carattereNarrativa", "Altro testo.", NARRATIVA, 0.5) == -1


# ─── il benvenuto ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "istante,giorno",
    [
        # Alle 23:30 UTC a Roma e' gia' il giorno dopo: il benvenuto riparte.
        ("2026-10-14T23:30:00Z", "2026-10-15"),
        ("2026-12-31T23:30:00Z", "2027-01-01"),
        ("2026-10-15T08:00:00Z", "2026-10-15"),
    ],
)
def test_il_giorno_del_benvenuto_e_quello_di_roma(istante, giorno):
    assert esegui_ts(MODULO, "emit(m.giornoDiRoma(new Date(input)));", argomento=istante, tz="UTC", richiede=["giornoDiRoma"]) == giorno


def test_la_chiave_del_benvenuto_cambia_col_giorno():
    assert _chiama("chiaveBenvenuto", "2026-10-15") == "oneflux:benvenuto:2026-10-15"


@pytest.mark.parametrize(
    "gia_visto,meno,atteso",
    [(False, False, True), (True, False, False), (False, True, False), (True, True, False)],
)
def test_il_benvenuto_parte_una_volta_e_mai_con_meno_animazioni(gia_visto, meno, atteso):
    assert _chiama("mostraBenvenuto", {"gia_visto": gia_visto, "meno_animazioni": meno}) is atteso


def test_l_opacita_resta_fra_0_e_1():
    assert _chiama("conOpacita", "rgba(1,2,3,", 2) == "rgba(1,2,3,1.000)"
    assert _chiama("conOpacita", "rgba(1,2,3,", -1) == "rgba(1,2,3,0.000)"


# ─── quanto e' stato letto ────────────────────────────────────────────────

def test_con_l_audio_conta_la_sua_durata():
    assert _chiama("frazioneLetta", {"currentTime": 15, "duration": 60}, 999, 300) == pytest.approx(0.25)


@pytest.mark.parametrize("durata", [0, None])
def test_senza_durata_si_stima_dal_tempo(durata):
    audio = None if durata is None else {"currentTime": 3, "duration": durata}
    # 15 caratteri al secondo: 4 secondi su 300 caratteri = 0,2
    assert _chiama("frazioneLetta", audio, 4, 300) == pytest.approx(0.2)


def test_la_frazione_resta_fra_0_e_1():
    assert _chiama("frazioneLetta", None, 999, 10) == 1
    assert _chiama("frazioneLetta", None, -5, 10) == 0
