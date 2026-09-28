"""«Da fare oggi» comune alle due Home (`lib/home-da-fare.ts`, 28/9/2026).

La Home della catena prende lo stesso «Da fare» del punto vendita, composto dai
segnali di gruppo, dalle osservazioni e dalle fatture da collocare. Prima questo
stava in `card-segnali.tsx` («Da vedere nella catena»), dove la regola che
conta — un errore non e' mai «tutto in ordine» — si poteva provare solo leggendo
il sorgente. Ora e' logica pura, e qui si esegue con node.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/home-da-fare"


def _catena(segnali=None, errore=False, n=0):
    return esegui_ts(
        MODULO,
        "emit(m.daFareCatena(input));",
        argomento={"segnali": segnali, "errore": errore, "nDaCollocare": n},
        richiede=["daFareCatena"],
    )


def _seg(tipo="dati_mancanti", rid="r1", nome="PV Uno", testo="Mancano le fatture", severity="warning"):
    return {
        "tipo": tipo, "severity": severity, "ristorante_id": rid,
        "pv_nome": nome, "testo": testo, "cta_page": "/margini",
    }


def _oss(tipo="andamento_incasso", rid="r1", nome="PV Uno", testo="Incasso in calo", severity="warning"):
    return {
        "tipo": tipo, "severity": severity, "ristorante_id": rid,
        "pv_nome": nome, "testo": testo, "cta_page": "/margini",
    }


# ─── Un errore non e' mai «tutto in ordine» ─────────────────────────────────


def test_segnali_non_ancora_letti_non_danno_il_verde():
    out = _catena(segnali=None, errore=False)
    assert out["verde"] is False
    assert out["avviso"] == "caricamento"


def test_segnali_falliti_non_danno_il_verde():
    """LA regressione che conta: la card esiste per avvisare, e un fetch fallito
    non deve diventare «Tutto in ordine per oggi»."""
    out = _catena(segnali=None, errore=True)
    assert out["verde"] is False
    assert out["avviso"] == "errore"
    assert out["voci"] == []


def test_verde_solo_con_segnali_letti_e_niente_da_fare():
    out = _catena(segnali={"segnali": [], "osservazioni": []}, n=0)
    assert out == {"voci": [], "avviso": None, "verde": True}


def test_la_coda_si_vede_anche_se_i_segnali_falliscono():
    """Il conteggio della coda arriva dal briefing di gruppo, che la Home ha
    gia': non deve sparire insieme ai segnali."""
    out = _catena(segnali=None, errore=True, n=3)
    assert [v["id"] for v in out["voci"]] == ["coda-gruppo"]
    assert out["verde"] is False


# ─── Le fatture da collocare ────────────────────────────────────────────────


@pytest.mark.parametrize("n", [0, None, -2])
def test_niente_coda_niente_voce(n):
    out = _catena(segnali={"segnali": []}, n=n)
    assert out["voci"] == []


def test_la_coda_porta_alla_scheda_da_collocare():
    v = _catena(segnali={"segnali": []}, n=4)["voci"][0]
    assert v["testo"] == "4 fatture di gruppo da collocare"
    assert v["dettaglio"] == "Assegnale a una sede o dividile fra i locali."
    assert v["azione"] == {"tipo": "pagina", "href": "/catena/fatture?tab=collocare", "etichetta": "Colloca"}
    assert v["ignorabile"] is False


def test_la_coda_al_singolare():
    v = _catena(segnali={"segnali": []}, n=1)["voci"][0]
    assert v["testo"] == "1 fattura di gruppo da collocare"
    assert v["dettaglio"] == "Assegnala a una sede o dividila fra i locali."


def test_con_la_sola_coda_niente_verde():
    out = _catena(segnali={"segnali": []}, n=2)
    assert out["verde"] is False


# ─── Segnali e osservazioni ─────────────────────────────────────────────────


def test_un_segnale_di_una_sede_porta_a_quella_sede():
    v = _catena(segnali={"segnali": [_seg(rid="r7", nome="Centro")]})["voci"][0]
    assert v["sede"] == "Centro"
    assert v["azione"] == {"tipo": "sede", "ristoranteId": "r7", "pagina": "/margini", "etichetta": "Vedi PV"}


def test_lo_stesso_segnale_su_piu_sedi_e_una_riga_senza_destinazione():
    """Raggruppato: il bottone manderebbe su una sede arbitraria."""
    out = _catena(segnali={"segnali": [_seg(rid="a", nome="A"), _seg(rid="b", nome="B")]})
    assert len(out["voci"]) == 1
    v = out["voci"][0]
    assert v["sede"] == "2 punti vendita · A · B"
    assert v["sedeCompleta"] == "A · B"
    assert v["azione"] is None


def test_segnale_senza_sede_non_e_una_destinazione():
    v = _catena(segnali={"segnali": [_seg(rid="", nome="")]})["voci"][0]
    assert v["azione"] is None


def test_un_osservazione_positiva_e_una_voce_e_spegne_il_verde():
    """Stessa regola della Home del punto vendita (fase 4, decisione 2): nessun
    «tutto in ordine» sopra un fatto che il cliente deve leggere."""
    out = _catena(segnali={"segnali": [], "osservazioni": [_oss(severity="success", testo="Incasso in crescita")]})
    assert [v["testo"] for v in out["voci"]] == ["Incasso in crescita"]
    assert out["verde"] is False


def test_osservazione_senza_testo_non_si_mostra():
    out = _catena(segnali={"segnali": [], "osservazioni": [_oss(testo="  ")]})
    assert out["voci"] == []
    assert out["verde"] is True


def test_osservazione_senza_sede_non_ha_bottone():
    v = _catena(segnali={"segnali": [], "osservazioni": [_oss(rid="")]})["voci"][0]
    assert v["azione"] is None


def test_campo_osservazioni_assente_non_e_un_errore():
    """Worker vecchio durante un deploy: niente osservazioni, non un guasto."""
    out = _catena(segnali={"segnali": []})
    assert out == {"voci": [], "avviso": None, "verde": True}


# ─── Ordine ─────────────────────────────────────────────────────────────────


def test_prima_gli_errori_poi_coda_e_avvisi_poi_le_osservazioni():
    out = _catena(
        segnali={
            "segnali": [
                _seg(tipo="margine_calo", rid="a", nome="A", testo="Margine in calo", severity="warning"),
                _seg(tipo="dati_mancanti", rid="b", nome="B", testo="Dati mancanti", severity="error"),
            ],
            "osservazioni": [
                _oss(rid="c", nome="C", testo="Incasso in crescita", severity="success"),
                _oss(rid="d", nome="D", testo="Food cost alto", severity="warning", tipo="food_cost_alto"),
            ],
        },
        n=2,
    )
    assert [v["testo"] for v in out["voci"]] == [
        "Dati mancanti",
        "2 fatture di gruppo da collocare",
        "Margine in calo",
        "Food cost alto",
        "Incasso in crescita",
    ]


def test_gli_id_sono_unici():
    out = _catena(
        segnali={
            "segnali": [_seg(testo="x", rid="a"), _seg(testo="y", rid="b")],
            "osservazioni": [_oss(rid="a"), _oss(rid="a")],
        },
        n=1,
    )
    ids = [v["id"] for v in out["voci"]]
    assert len(ids) == len(set(ids)) == 5


# ─── Le azioni del punto vendita nella forma comune ─────────────────────────


def test_azioni_pv_nella_forma_comune():
    azioni = [
        {"id": "a1", "topic_key": "fatture", "severity": "warning", "testo": "T",
         "cta_label": "Vai", "cta_page": "/analisi-fatture", "dettaglio": "D", "dismissible": True},
        {"id": "a2", "topic_key": "personale", "severity": "error", "testo": "U",
         "cta_label": "Inserisci", "cta_page": "/workspace", "dismissible": False},
    ]
    out = esegui_ts(
        MODULO,
        "emit(m.vociDaAzioniPV(input, (a) => a.dismissible === true));",
        argomento=azioni,
        richiede=["vociDaAzioniPV"],
    )
    assert out == [
        {"id": "a1", "severity": "warning", "testo": "T", "dettaglio": "D", "sede": None,
         "azione": {"tipo": "pagina", "href": "/analisi-fatture", "etichetta": "Vai"}, "ignorabile": True},
        {"id": "a2", "severity": "error", "testo": "U", "dettaglio": None, "sede": None,
         "azione": {"tipo": "pagina", "href": "/workspace", "etichetta": "Inserisci"}, "ignorabile": False},
    ]
