"""Fase F del piano consulente (08/10/2026): l'assistente sulle pagine che non
conosceva. Decisione di Mattia: tutte e quattro — turni e spese extra (Agenda),
Score Fornitori e avvisi prezzi (Osservatorio), tag (Analisi e Tag).

Ogni strumento legge gli stessi dati e lo stesso periodo della sua pagina, e
passa due gate: la pagina abilitata e la scheda accesa (`tab_off_*`), sia
nell'elenco offerto al modello sia nell'esecuzione (il dispatcher esegue per
nome: un nome allucinato passerebbe). Il personale va al modello SOLO in totale
(Mattia, 8/10: niente nomi ne' costi per persona a OpenAI).
"""
import json
from concurrent.futures import TimeoutError as _TO
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw
from tests.test_costi_auto_fatture_mol import _FakeQuery

RID, ALTRO = "r-f4", "r-altro"
OGGI = date(2026, 10, 8)
NUOVI = ["query_personale", "query_spese_extra", "score_fornitori", "avvisi_prezzi", "query_tag"]


class _SB:
    def __init__(self, **tabelle):
        self.t = tabelle

    def table(self, nome):
        return _FakeQuery(self.t.get(nome, []), table=nome)


def _offerti(pagine):
    return [t["function"]["name"] for t in
            fw._chat_tools_sede_offerti({"id": "u", "pagine_abilitate": pagine}, "ristorazione")]


def _esegui(nome, args=None, pagine=None, sb=None, rid=RID):
    with patch.object(fw, "_oggi_rome", return_value=OGGI):
        return fw._chat_esegui_tool_sede(
            nome, args or {}, user={"id": "u", "pagine_abilitate": pagine},
            supabase_client=sb or _SB(), authorization=None, ristorante_id=rid,
            settore="ristorazione")


# ── I gate: pagina e scheda ───────────────────────────────────────────────

def test_l_admin_li_vede_tutti():
    assert set(NUOVI) <= set(_offerti(None))


@pytest.mark.parametrize("pagine,assenti", [
    (["margini"], set(NUOVI)),
    (["agenda"], {"score_fornitori", "avvisi_prezzi", "query_tag"}),
    (["prezzi"], {"query_personale", "query_spese_extra", "query_tag"}),
    (["analisi_e_tag"], {"query_personale", "query_spese_extra", "score_fornitori", "avvisi_prezzi"}),
])
def test_solo_le_pagine_abilitate(pagine, assenti):
    offerti = set(_offerti(pagine))
    assert not (assenti & offerti)
    assert (set(NUOVI) - assenti) <= offerti


@pytest.mark.parametrize("scheda,tolto", [
    ("tab_off_agenda_personale", "query_personale"),
    ("tab_off_agenda_spese", "query_spese_extra"),
    ("tab_off_prezzi_score", "score_fornitori"),
    ("tab_off_prezzi_variazioni", "avvisi_prezzi"),
])
def test_la_scheda_spenta_toglie_lo_strumento(scheda, tolto):
    pagine = ["agenda", "prezzi", "analisi_e_tag", scheda]
    offerti = set(_offerti(pagine))
    assert tolto not in offerti
    assert (set(NUOVI) - {tolto}) <= offerti


@pytest.mark.parametrize("nome,pagine", [
    ("query_personale", ["prezzi"]),
    ("score_fornitori", ["prezzi", "tab_off_prezzi_score"]),
    ("query_tag", ["agenda"]),
])
def test_l_esecuzione_rispetta_gli_stessi_gate(nome, pagine):
    """Il dispatcher esegue per nome: il gate sull'elenco non basta."""
    with patch.object(fw, "_chat_query_personale") as p, \
         patch.object(fw, "_chat_score_fornitori") as s, \
         patch.object(fw, "_chat_query_tag") as t:
        out = _esegui(nome, pagine=pagine)
    assert "errore" in out
    for m in (p, s, t):
        m.assert_not_called()


def test_senza_locale_niente():
    assert "errore" in _esegui("query_spese_extra", rid=None)


def test_la_catena_non_li_ha():
    """Fuori perimetro: la vista catena offre solo gli strumenti di sede che
    sanno ricevere una sede verificata."""
    assert not (set(NUOVI) & set(fw._CHAT_TOOLS_SEDE_IN_CATENA))


# ── Personale: solo totali ────────────────────────────────────────────────

def _turno(dip, giorno, ini="09:00", fine="17:00", extra=0, costo=10.0, rid=RID, **kw):
    return {"ristorante_id": rid, "dipendente_id": dip, "data_turno": f"2026-09-{giorno:02d}",
            "ora_inizio": ini, "ora_fine": fine, "ore_extra": extra, "costo_orario": costo,
            "mensile": False, "tipo_giorno": "turno", **kw}


TURNI = [
    _turno("dip-marco", 1), _turno("dip-marco", 2, extra=2),
    _turno("dip-anna", 1, costo=None),
    {"ristorante_id": RID, "dipendente_id": "dip-luca", "data_turno": "2026-09-30",
     "mensile": True, "tipo_giorno": "turno", "ore_dichiarate": 160,
     "lordo_mensile": 2000, "importo_extra": 200, "importo_chiamata": 100},
    _turno("dip-altro", 3, rid=ALTRO, costo=99.0),
    _turno("dip-marco", 1, costo=10.0) | {"data_turno": "2026-08-31"},
]


def test_personale_del_mese_in_totale():
    out = _esegui("query_personale", {"mese": 9, "anno": 2026}, sb=_SB(turni_personale=TURNI))
    assert out["persone"] == 3
    assert out["ore_totali_locale"] == 8 + 8 + 8 + 160
    assert "non di una persona" in out["attenzione"]
    assert out["di_cui_ore_extra"] == 2
    assert "ore" not in out and "ore_extra" not in out
    assert out["costo_ordinario"] == 6 * 10 + 8 * 10 + 1700
    assert out["costo_extra"] == 2 * 10 + 200
    assert out["costo_chiamata"] == 100
    assert out["costo_totale"] == 140 + 1700 + 220 + 100
    assert out["persone_senza_costo_orario"] == 1
    assert (out["mese"], out["anno"]) == ("settembre", 2026)


def test_personale_niente_nomi_ne_chiavi_per_persona():
    out = _esegui("query_personale", {"mese": 9, "anno": 2026}, sb=_SB(turni_personale=TURNI))
    testo = json.dumps(out)
    assert "dip-" not in testo
    assert all(not isinstance(v, (dict, list)) for v in out.values())


def test_personale_default_mese_in_corso_e_mese_vuoto():
    out = _esegui("query_personale", {}, sb=_SB(turni_personale=TURNI))
    assert (out["mese"], out["anno"], out["persone"]) == ("ottobre", 2026, 0)
    assert "nota" in out


@pytest.mark.parametrize("mese,anno", [(13, 2026), (0, 2026), ("boh", 2026), (9, 1900)])
def test_mese_fuori_intervallo_e_il_mese_in_corso(mese, anno):
    with patch.object(fw, "_oggi_rome", return_value=OGGI):
        assert fw._mese_anno_chat(mese, anno) == (10, 2026)


# ── Spese extra ───────────────────────────────────────────────────────────

def _spesa(giorno, importo, tipo="fb", rid=RID, cat="LATTICINI"):
    return {"ristorante_id": rid, "data_spesa": f"2026-09-{giorno:02d}", "descrizione": f"voce {giorno}",
            "categoria": cat, "importo": importo, "tipo": tipo}


def test_spese_del_mese_del_locale():
    spese = [_spesa(1, 20), _spesa(2, 30.5, tipo="generale", cat="UTENZE"),
             _spesa(3, 999, rid=ALTRO), {**_spesa(1, 77), "data_spesa": "2026-10-01"}]
    out = _esegui("query_spese_extra", {"mese": 9}, sb=_SB(spese_extra=spese))
    assert out["totale_food_beverage"] == 20 and out["totale_spese_generali"] == 30.5
    assert out["totale"] == 50.5 and out["voci_totali"] == 2
    assert {v["importo"] for v in out["voci"]} == {20, 30.5}


def test_spese_al_massimo_trenta_voci_ma_il_totale_e_di_tutte():
    spese = [_spesa(1 + i % 28, 1) for i in range(40)]
    out = _esegui("query_spese_extra", {"mese": 9}, sb=_SB(spese_extra=spese))
    assert len(out["voci"]) == 30 and out["voci_totali"] == 40 and out["totale"] == 40


# ── Score fornitori ───────────────────────────────────────────────────────

def _f(nome, spesa, score=70.0):
    return SimpleNamespace(fornitore=nome, score=score, stato="affidabile", frase_sintesi="ok",
                           spesa_periodo=spesa, impatto_rincari=5.0, n_fatture=3, bozza="NON DEVE USCIRE")


def _score(args, fornitori):
    from services.routers import prezzi
    with patch.object(prezzi, "_load_fatture_for_prezzi", return_value=[{"x": 1}]) as load, \
         patch.object(prezzi, "_calcola_variazioni_prezzi_sync", return_value=[]), \
         patch.object(prezzi, "_nc_credito_per_fornitore", return_value={}), \
         patch.object(prezzi, "_calcola_score_fornitori", return_value=fornitori):
        out = _esegui("score_fornitori", args)
    return out, load


def test_score_anno_in_corso_fino_a_oggi_del_locale():
    out, load = _score({}, [_f("ROSSI", 100)])
    assert load.call_args.args[1:] == (RID, "2026-01-01", "2026-10-08")
    assert out["fornitori"][0]["fornitore"] == "ROSSI"


def test_score_i_dieci_con_piu_spesa_e_senza_bozze():
    out, _ = _score({}, [_f(f"F{i}", i) for i in range(15)])
    assert [f["fornitore"] for f in out["fornitori"]] == [f"F{i}" for i in range(14, 4, -1)]
    assert "NON DEVE USCIRE" not in json.dumps(out)
    assert out["fornitori_valutati"] == 15


def test_score_filtro_per_nome():
    out, _ = _score({"fornitore": "ross"}, [_f("ROSSI SRL", 10), _f("BIANCHI", 99)])
    assert [f["fornitore"] for f in out["fornitori"]] == ["ROSSI SRL"]


# ── Avvisi prezzi ─────────────────────────────────────────────────────────

AP = {"count": 1, "alerts": [{"tipo": "prodotto", "nome": "SALMONE", "fornitore": "ITTICA",
                               "aumento_pct": 12.0, "impatto_mese": 80.0}],
      "top": None, "ribassi": [{"nome": "TONNO", "fornitore": "MARE", "ribasso_pct": 9.0,
                                "risparmio_mese": 30.0}]}


def test_avvisi_rincari_e_ribassi():
    import services.price_impact_service as pis
    with patch.object(pis, "calcola_alert_prezzi_impatto", return_value=AP) as calc:
        out = _esegui("avvisi_prezzi")
    assert calc.call_args.args[:2] == ("u", RID)
    assert out["rincari"] == [{"nome": "SALMONE", "tipo": "prodotto", "fornitore": "ITTICA",
                               "aumento_pct": 12.0, "costo_in_piu_al_mese": 80.0}]
    assert out["ribassi_ultima_settimana"][0]["nome"] == "TONNO"


def test_avvisi_lenti_non_bloccano_la_chat():
    fut = MagicMock()
    fut.result.side_effect = _TO()
    ex = MagicMock()
    ex.submit.return_value = fut
    with patch.object(fw, "_ALERT_PREZZI_EXECUTOR", ex):
        out = _esegui("avvisi_prezzi")
    assert "errore" in out
    assert fut.result.call_args.kwargs["timeout"] == fw._CHAT_AVVISI_PREZZI_TIMEOUT_SEC


# ── Tag ───────────────────────────────────────────────────────────────────

def _tag(args, tags, analisi):
    import services.db_service as dbsv
    import services.tag_analytics_service as tas
    with patch.object(dbsv, "get_custom_tags", return_value=tags) as gt, \
         patch.object(dbsv, "carica_e_prepara_dataframe", return_value="DF") as carica, \
         patch.object(tas, "analizza_tag", side_effect=analisi) as an:
        out = _esegui("query_tag", args)
    return out, gt, carica, an


KPI = {"vuoto": False, "kpi": {"spesa_totale": 500.0, "prezzo_medio_ponderato": 2.5,
                               "unita_dominante": "KG", "num_fornitori": 2, "num_fatture": 7}}


def test_tag_con_i_kpi_dall_inizio_dell_anno_e_un_solo_caricamento():
    out, gt, carica, an = _tag({}, [{"id": 1, "nome": "PESCE"}, {"id": 2, "nome": "BAR"}],
                               lambda *a, **k: KPI)
    assert gt.call_args.args == ("u", RID)
    assert carica.call_count == 1
    assert an.call_args.args[:5] == ("u", RID, 2, date(2026, 1, 1), OGGI)
    assert an.call_args.kwargs["df_precaricato"] == "DF"
    assert out["tag"][0] == {"tag": "PESCE", "spesa": 500.0, "prezzo_medio": 2.5, "unita": "KG",
                             "fornitori": 2, "fatture": 7}


def test_tag_filtro_tetto_e_vuoti():
    tags = [{"id": i, "nome": f"T{i}"} for i in range(12)]
    out, *_ = _tag({}, tags, lambda *a, **k: {"vuoto": True})
    assert len(out["tag"]) == 8 and out["tag_totali"] == 12
    assert out["tag"][0] == {"tag": "T0", "nota": "nessun acquisto quest'anno"}
    out, *_ = _tag({"tag": "t1"}, tags, lambda *a, **k: KPI)
    assert [t["tag"] for t in out["tag"]] == ["T1", "T10", "T11"]


def test_senza_tag():
    out, *_ = _tag({}, [], lambda *a, **k: KPI)
    assert out["tag"] == [] and "nota" in out


def test_un_guasto_dello_strumento_non_fa_cadere_la_chat():
    """In vista PV non c'e' un try per strumento: un'eccezione dava 502 a tutta
    la risposta (revisore, 9/10). Il modello riceve un errore che non e' «niente»."""
    with patch.object(fw, "_chat_query_tag", side_effect=RuntimeError("pandas")):
        out = _esegui("query_tag")
    assert "errore" in out and "non dire che non c'e'" in out["errore"]


def test_gli_avvisi_dicono_che_sono_al_massimo_tre():
    import services.price_impact_service as pis
    with patch.object(pis, "calcola_alert_prezzi_impatto", return_value=AP):
        out = _esegui("avvisi_prezzi")
    assert "al massimo i 3 rincari" in out["nota"]
