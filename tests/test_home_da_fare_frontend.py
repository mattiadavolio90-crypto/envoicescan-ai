"""«Da fare oggi» comune alle due Home (`lib/home-da-fare.ts`, 28/9/2026).

La Home della catena prende lo stesso «Da fare» del punto vendita, composto dai
segnali di gruppo, dalle osservazioni e dalle fatture da collocare. Prima questo
stava in `card-segnali.tsx` («Da vedere nella catena»), dove la regola che
conta — un errore non e' mai «tutto in ordine» — si poteva provare solo leggendo
il sorgente. Ora e' logica pura, e qui si esegue con node.

Fase G (9/10/2026, screen 12): in catena il «Da fare» assorbe anche gli avvisi
delle sedi (prima in «Vedi tutti gli avvisi») e si raggruppa per punto vendita.
Il segnale «Mancano …» della catena sparisce solo dove l'avviso della sede dice
gia' ogni voce.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/home-da-fare"


_NESSUN_AVVISO = {"notifiche": [], "sedi_non_lette": []}


def _catena(segnali=None, errore=False, n=0, avvisi=_NESSUN_AVVISO, errore_avvisi=False, archiviati=None):
    return esegui_ts(
        MODULO,
        "emit(m.daFareCatena(input));",
        argomento={
            "segnali": segnali, "errore": errore, "nDaCollocare": n,
            "avvisi": avvisi, "erroreAvvisi": errore_avvisi, "archiviati": archiviati or [],
        },
        richiede=["daFareCatena"],
    )


def _seg(tipo="dati_mancanti", rid="r1", nome="PV Uno", testo="Mancano le fatture", severity="warning", manca=None):
    s = {
        "tipo": tipo, "severity": severity, "ristorante_id": rid,
        "pv_nome": nome, "testo": testo, "cta_page": "/margini",
    }
    if manca is not None:
        s["manca"] = manca
    return s


def _oss(tipo="andamento_incasso", rid="r1", nome="PV Uno", testo="Incasso in calo", severity="warning"):
    return {
        "tipo": tipo, "severity": severity, "ristorante_id": rid,
        "pv_nome": nome, "testo": testo, "cta_page": "/margini",
    }


def _avv(id="n1", rid="r1", nome="PV Uno", topic="scadenza_superata", title="Scadenze superate (3)",
         severity="warning", body=None, dismissible=True, action_page="/scadenziario", dismissed_at=None):
    return {
        "id": id, "topic_key": topic, "source_type": "live", "severity": severity,
        "title": title, "body": body, "action_page": action_page, "dismissible": dismissible,
        "dismissed_at": dismissed_at, "expires_at": None, "created_at": "2026-10-09T08:00:00Z",
        "ristorante_id": rid, "sede_nome": nome,
    }


def _avvisi(*notifiche, non_lette=()):
    return {"notifiche": list(notifiche), "sedi_non_lette": list(non_lette)}


def _testi(sede):
    return [v["testo"] for v in sede["voci"]]


# ─── Un errore non e' mai «tutto in ordine» ─────────────────────────────────


def test_segnali_non_ancora_letti_non_danno_il_verde():
    out = _catena(segnali=None, errore=False)
    assert out["verde"] is False
    assert out["avviso"] == "caricamento"


def test_segnali_falliti_non_danno_il_verde():
    """LA regressione che conta: l'elenco esiste per avvisare, e un fetch fallito
    non deve diventare «Tutto in ordine per oggi»."""
    out = _catena(segnali=None, errore=True)
    assert out["verde"] is False
    assert out["avviso"] == "errore"
    assert out["generali"] == [] and out["sedi"] == []


def test_verde_solo_con_segnali_e_avvisi_letti_e_niente_da_fare():
    out = _catena(segnali={"segnali": [], "osservazioni": []}, n=0)
    assert out == {"generali": [], "sedi": [], "totale": 0, "avviso": None, "notaAvvisi": None, "verde": True}


def test_avvisi_non_ancora_letti_non_danno_il_verde():
    out = _catena(segnali={"segnali": []}, avvisi=None)
    assert out["avviso"] == "caricamento"
    assert out["verde"] is False


def test_avvisi_falliti_si_dicono_e_spengono_il_verde():
    out = _catena(segnali={"segnali": []}, avvisi=None, errore_avvisi=True)
    assert out["avviso"] is None
    assert out["notaAvvisi"] == "Non è stato possibile leggere gli avvisi dei punti vendita."
    assert out["verde"] is False


def test_sedi_non_lette_si_dicono_e_spengono_il_verde():
    """Dato assente non e' «niente da fare»: una sede non letta poteva avere avvisi."""
    out = _catena(segnali={"segnali": []}, avvisi=_avvisi(non_lette=["Centro", "Mare"]))
    assert out["notaAvvisi"] == "Avvisi non letti per: Centro, Mare."
    assert out["verde"] is False


def test_la_coda_si_vede_anche_se_i_segnali_falliscono():
    """Il conteggio della coda arriva dal briefing di gruppo, che la Home ha
    gia': non deve sparire insieme ai segnali."""
    out = _catena(segnali=None, errore=True, n=3)
    assert [v["id"] for v in out["generali"]] == ["coda-gruppo"]
    assert out["verde"] is False


# ─── Le fatture da collocare ────────────────────────────────────────────────


@pytest.mark.parametrize("n", [0, None, -2])
def test_niente_coda_niente_voce(n):
    out = _catena(segnali={"segnali": []}, n=n)
    assert out["generali"] == []


def test_la_coda_porta_alla_scheda_da_collocare():
    v = _catena(segnali={"segnali": []}, n=4)["generali"][0]
    assert v["testo"] == "4 fatture di gruppo da collocare"
    assert v["dettaglio"] == "Assegnale a una sede o dividile fra i locali."
    assert v["azione"] == {"tipo": "pagina", "href": "/catena/fatture?tab=collocare", "etichetta": "Colloca"}
    assert v["ignorabile"] is False


def test_la_coda_al_singolare():
    v = _catena(segnali={"segnali": []}, n=1)["generali"][0]
    assert v["testo"] == "1 fattura di gruppo da collocare"
    assert v["dettaglio"] == "Assegnala a una sede o dividila fra i locali."


def test_con_la_sola_coda_niente_verde():
    out = _catena(segnali={"segnali": []}, n=2)
    assert out["verde"] is False
    assert out["totale"] == 1


# ─── Una riga per punto vendita ─────────────────────────────────────────────


def test_un_segnale_sta_nella_sua_sede_e_porta_a_quella_sede():
    out = _catena(segnali={"segnali": [_seg(rid="r7", nome="Centro")]})
    assert [(s["ristoranteId"], s["nome"]) for s in out["sedi"]] == [("r7", "Centro")]
    v = out["sedi"][0]["voci"][0]
    assert v["sede"] is None, "dentro la riga della sede il nome non si ripete"
    assert v["azione"] == {"tipo": "sede", "ristoranteId": "r7", "pagina": "/margini", "etichetta": "Vedi PV"}


def test_lo_stesso_segnale_su_due_sedi_e_in_ognuna_con_la_sua_destinazione():
    out = _catena(segnali={"segnali": [_seg(rid="a", nome="A"), _seg(rid="b", nome="B")]})
    assert [s["nome"] for s in out["sedi"]] == ["A", "B"]
    assert [s["voci"][0]["azione"]["ristoranteId"] for s in out["sedi"]] == ["a", "b"]


def test_segnale_senza_sede_sta_sopra_e_non_e_una_destinazione():
    out = _catena(segnali={"segnali": [_seg(rid="", nome="Catena", testo="Non è stato possibile controllare")]})
    assert out["sedi"] == []
    assert out["generali"][0]["azione"] is None


def test_gli_avvisi_della_sede_stanno_nella_sua_riga():
    out = _catena(
        segnali={"segnali": [_seg(tipo="margine_calo", rid="r1", nome="PV Uno", testo="Margine al 31%")]},
        avvisi=_avvisi(_avv(id="n9", rid="r1", title="**Scadenze** superate (3)", body="Da `pagare`")),
    )
    assert len(out["sedi"]) == 1
    sede = out["sedi"][0]
    assert _testi(sede) == ["Margine al 31%", "Scadenze superate (3)"]
    v = sede["voci"][1]
    assert v["dettaglio"] == "Da pagare"
    assert v["azione"] == {"tipo": "sede", "ristoranteId": "r1", "pagina": "/scadenziario", "etichetta": "Vai"}
    assert v["ignorabile"] is True
    assert v["rif"] == "n9", "senza l'id della notifica «Ignora» non saprebbe cosa archiviare"


def test_un_avviso_live_non_si_archivia():
    v = _catena(segnali={"segnali": []}, avvisi=_avvisi(_avv(dismissible=False)))["sedi"][0]["voci"][0]
    assert v["ignorabile"] is False


def test_un_avviso_senza_pagina_non_ha_pulsante():
    v = _catena(segnali={"segnali": []}, avvisi=_avvisi(_avv(action_page=None)))["sedi"][0]["voci"][0]
    assert v["azione"] is None


def test_la_sede_di_soli_avvisi_prende_il_nome_dall_avviso():
    out = _catena(segnali={"segnali": []}, avvisi=_avvisi(_avv(rid="r5", nome="Mare")))
    assert out["sedi"][0]["nome"] == "Mare"


def test_un_avviso_senza_sede_sta_sopra():
    out = _catena(segnali={"segnali": []}, avvisi=_avvisi(_avv(rid=None, nome=None)))
    assert out["sedi"] == []
    assert out["generali"][0]["azione"] is None


@pytest.mark.parametrize("come", ["dal_worker", "in_questa_visita"])
def test_un_avviso_archiviato_sparisce(come):
    a = _avv(id="n1", rid="r1", dismissed_at="2026-10-09T09:00:00Z" if come == "dal_worker" else None)
    out = _catena(
        segnali={"segnali": []}, avvisi=_avvisi(a),
        archiviati=["avviso-r1:n1"] if come == "in_questa_visita" else [],
    )
    assert out["sedi"] == []
    assert out["verde"] is True


def test_archiviare_in_una_sede_non_tocca_lo_stesso_avviso_nell_altra():
    """In catena lo stesso avviso live ha lo stesso id in ogni sede."""
    out = _catena(
        segnali={"segnali": []},
        avvisi=_avvisi(_avv(id="live-x", rid="a", nome="A"), _avv(id="live-x", rid="b", nome="B")),
        archiviati=["avviso-a:live-x"],
    )
    assert [s["nome"] for s in out["sedi"]] == ["B"]


# ─── Lo stesso fatto due volte: si tiene l'avviso della sede ────────────────


def _fatture_mancanti(rid="r1", nome="PV Uno"):
    return _avv(id="live-fatture", rid=rid, nome=nome, topic="fatture_mancanti",
                title="Mancano le fatture costo di settembre", dismissible=False, action_page="/analisi-fatture")


def test_il_segnale_detto_dall_avviso_della_sede_sparisce():
    out = _catena(
        segnali={"segnali": [_seg(testo="Mancano le fatture costo", manca=["fatture"])]},
        avvisi=_avvisi(_fatture_mancanti()),
    )
    assert _testi(out["sedi"][0]) == ["Mancano le fatture costo di settembre"]


def test_tutte_le_voci_dette_il_segnale_sparisce():
    out = _catena(
        segnali={"segnali": [_seg(testo="Mancano tutto", manca=["fatturato", "fatture", "personale"])]},
        avvisi=_avvisi(
            _fatture_mancanti(),
            _avv(id="l1", topic="fatturato_mancante", title="Fatturato mancante", dismissible=False),
            _avv(id="l2", topic="costo_personale_mancante", title="Personale mancante", dismissible=False),
        ),
    )
    assert "Mancano tutto" not in _testi(out["sedi"][0])


def test_una_voce_non_detta_tiene_il_segnale():
    """«Mancano il fatturato e le fatture costo» con il solo avviso delle
    fatture: togliendolo si perderebbe il fatturato."""
    out = _catena(
        segnali={"segnali": [_seg(testo="Mancano il fatturato e le fatture costo", manca=["fatturato", "fatture"])]},
        avvisi=_avvisi(_fatture_mancanti()),
    )
    assert "Mancano il fatturato e le fatture costo" in _testi(out["sedi"][0])


def test_l_avviso_di_un_altra_sede_non_conta():
    out = _catena(
        segnali={"segnali": [_seg(rid="a", nome="A", testo="Mancano le fatture costo", manca=["fatture"])]},
        avvisi=_avvisi(_fatture_mancanti(rid="b", nome="B")),
    )
    assert [(s["nome"], _testi(s)) for s in out["sedi"]] == [
        ("A", ["Mancano le fatture costo"]),
        ("B", ["Mancano le fatture costo di settembre"]),
    ]


@pytest.mark.parametrize("manca", [None, [], ["toString"], ["fatture", "constructor"]])
def test_senza_voci_note_il_segnale_resta(manca):
    """Snapshot di prima del 9/10 (niente `manca`) o voce sconosciuta: non si sa
    se l'avviso dice lo stesso, quindi il segnale resta."""
    out = _catena(
        segnali={"segnali": [_seg(testo="Mancano le fatture costo", manca=manca)]},
        avvisi=_avvisi(_fatture_mancanti()),
    )
    assert "Mancano le fatture costo" in _testi(out["sedi"][0])


def test_solo_dati_mancanti_si_toglie():
    out = _catena(
        segnali={"segnali": [_seg(tipo="ricavi_mancanti", testo="Nessun ricavo", manca=["fatture"])]},
        avvisi=_avvisi(_fatture_mancanti()),
    )
    assert "Nessun ricavo" in _testi(out["sedi"][0])


def test_un_avviso_archiviato_non_copre_il_segnale():
    a = _fatture_mancanti()
    a["dismissed_at"] = "2026-10-09T09:00:00Z"
    out = _catena(
        segnali={"segnali": [_seg(testo="Mancano le fatture costo", manca=["fatture"])]},
        avvisi=_avvisi(a),
    )
    assert _testi(out["sedi"][0]) == ["Mancano le fatture costo"]


def test_avvisi_non_letti_il_segnale_resta():
    """Gli avvisi della sede non sono arrivati: il segnale e' l'unico che lo dice."""
    out = _catena(
        segnali={"segnali": [_seg(testo="Mancano le fatture costo", manca=["fatture"])]},
        avvisi=None, errore_avvisi=True,
    )
    assert _testi(out["sedi"][0]) == ["Mancano le fatture costo"]


# ─── Osservazioni ───────────────────────────────────────────────────────────


def test_un_osservazione_positiva_e_una_voce_e_spegne_il_verde():
    """Stessa regola della Home del punto vendita (fase 4, decisione 2): nessun
    «tutto in ordine» sopra un fatto che il cliente deve leggere."""
    out = _catena(segnali={"segnali": [], "osservazioni": [_oss(severity="success", testo="Incasso in crescita")]})
    assert _testi(out["sedi"][0]) == ["Incasso in crescita"]
    assert out["verde"] is False


def test_osservazione_senza_testo_non_si_mostra():
    out = _catena(segnali={"segnali": [], "osservazioni": [_oss(testo="  ")]})
    assert out["sedi"] == []
    assert out["verde"] is True


def test_osservazione_senza_sede_sta_sopra_senza_bottone():
    out = _catena(segnali={"segnali": [], "osservazioni": [_oss(rid="", nome="Catena")]})
    assert out["sedi"] == []
    v = out["generali"][0]
    assert v["azione"] is None
    assert v["sede"] == "Catena"


def test_campo_osservazioni_assente_non_e_un_errore():
    """Worker vecchio durante un deploy: niente osservazioni, non un guasto."""
    out = _catena(segnali={"segnali": []})
    assert out["verde"] is True


# ─── Ordine e conteggi ──────────────────────────────────────────────────────


def test_nella_sede_prima_gli_errori_poi_l_ordine_di_arrivo():
    out = _catena(
        segnali={
            "segnali": [_seg(tipo="margine_calo", testo="Margine in calo")],
            "osservazioni": [
                _oss(testo="Incasso in crescita", severity="success"),
                _oss(testo="Food cost alto", tipo="food_cost_alto"),
            ],
        },
        avvisi=_avvisi(
            _avv(id="a1", title="Scadenze superate", severity="error"),
            _avv(id="a2", title="Suggeriti 20 tag", severity="info"),
            _avv(id="a3", title="Mancano le fatture", severity="warning"),
        ),
    )
    assert _testi(out["sedi"][0]) == [
        "Scadenze superate",
        "Margine in calo",
        "Mancano le fatture",
        "Food cost alto",
        "Suggeriti 20 tag",
        "Incasso in crescita",
    ]


def test_le_sedi_piu_gravi_prima_poi_le_piu_piene_poi_per_nome():
    out = _catena(
        segnali={"segnali": [
            _seg(tipo="margine_calo", rid="z", nome="Zeta", testo="m1"),
            _seg(tipo="margine_calo", rid="b", nome="Beta", testo="m2"),
            _seg(tipo="margine_calo", rid="a", nome="Alfa", testo="m3"),
            _seg(tipo="prezzi_sopra", rid="b", nome="Beta", testo="p2"),
        ]},
        avvisi=_avvisi(_avv(id="e", rid="z", nome="Zeta", severity="error"), _avv(id="i", rid="c", nome="Ciro", severity="info")),
    )
    assert [s["nome"] for s in out["sedi"]] == ["Zeta", "Beta", "Alfa", "Ciro"]
    assert [s["severity"] for s in out["sedi"]] == ["error", "warning", "warning", "info"]


def test_il_conteggio_della_riga_chiusa():
    out = _catena(
        segnali={"segnali": [_seg(rid="a", nome="A", testo="x"), _seg(rid="b", nome="B", testo="y"),
                             _seg(tipo="margine_calo", rid="b", nome="B", testo="z")]},
    )
    assert {s["nome"]: s["conteggio"] for s in out["sedi"]} == {"A": "1 avviso", "B": "2 avvisi"}


def test_il_totale_conta_ogni_voce():
    out = _catena(
        segnali={"segnali": [_seg(rid="a", nome="A"), _seg(rid="", nome="Catena")]},
        avvisi=_avvisi(_avv(id="1", rid="a", nome="A"), _avv(id="2", rid="b", nome="B")),
        n=2,
    )
    assert out["totale"] == 5


def test_gli_id_sono_unici():
    out = _catena(
        segnali={
            "segnali": [_seg(testo="x", rid="a"), _seg(testo="y", rid="b")],
            "osservazioni": [_oss(rid="a"), _oss(rid="a")],
        },
        avvisi=_avvisi(_avv(id="live-x", rid="a"), _avv(id="live-x", rid="b")),
        n=1,
    )
    ids = [v["id"] for v in out["generali"]] + [v["id"] for s in out["sedi"] for v in s["voci"]]
    assert len(ids) == len(set(ids)) == 7


def test_il_tetto_e_quello_delle_card_del_punto_vendita():
    from services.daily_briefing_service import _MAX_CARD
    assert esegui_ts(MODULO, "emit(m.MAX_SEDI_VISIBILI);") == _MAX_CARD == 4


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
