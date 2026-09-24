"""Fase 4 — il briefing da consulente: le due osservazioni calcolate.

Misura sul DB live del 24/09/2026, prima del codice: dei cinque candidati del
piano solo due tacevano abbastanza da essere notizie.

- `andamento_incasso`: il martedi', incasso delle ultime 4 settimane complete
  contro le 4 prima, oltre il 10%. Misurato: 7 volte su 73 da giugno.
- `food_cost_alto`: nella finestra del MOL, il food cost del mese di due mesi fa,
  solo se consolidato (sono arrivate fatture del mese dopo), sopra il 33%.

Ogni topic ha il caso che lo fa SCATTARE su dati reali (serie di incasso vere,
anonimizzate: solo date e importi) e i casi che lo tengono ZITTO. Le soglie sono
scritte qui come letterali (33, 38, 10%, 20 giorni) e NON lette dalle costanti:
un test che legge la stessa costante del codice si muove con lei e non prova
niente.
"""
import os
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import services.fastapi_worker as fw  # noqa: E402
import services.daily_briefing_service as dbs  # noqa: E402
from services.settore_service import SETTORE_RETAIL, SETTORE_RISTORAZIONE  # noqa: E402
from tests.test_costi_auto_fatture_mol import _FakeQuery  # noqa: E402

UID = "user-cons"
RID = "rid-cons"

# Serie VERA di una piccola sede (senza coperti): 4 settimane al 19/07/2026
# contro le 4 prima. +15,7%, con la finestra precedente esattamente a 20 giorni
# d'incasso — il minimo richiesto.
SERIE_SCATTA = [
    ("2026-06-02", 557.3),
    ("2026-06-03", 346.2),
    ("2026-06-04", 377.5),
    ("2026-06-05", 355.1),
    ("2026-06-06", 428.3),
    ("2026-06-07", 185.6),
    ("2026-06-08", 93.0),
    ("2026-06-09", 357.2),
    ("2026-06-10", 280.6),
    ("2026-06-11", 242.6),
    ("2026-06-12", 347.5),
    ("2026-06-13", 493.65),
    ("2026-06-14", 111.5),
    ("2026-06-15", 58.4),
    ("2026-06-16", 295.7),
    ("2026-06-17", 330.6),
    ("2026-06-18", 300.5),
    ("2026-06-19", 332.4),
    ("2026-06-20", 332.4),
    ("2026-06-21", 309.9),
    ("2026-06-22", 10.0),
    ("2026-06-23", 242.4),
    ("2026-06-24", 230.9),
    ("2026-06-26", 364.5),
    ("2026-06-27", 443.5),
    ("2026-06-28", 198.0),
    ("2026-07-01", 291.1),
    ("2026-07-02", 300.4),
    ("2026-07-03", 366.4),
    ("2026-07-04", 382.1),
    ("2026-07-05", 200.8),
    ("2026-07-07", 280.4),
    ("2026-07-08", 404.2),
    ("2026-07-09", 274.4),
    ("2026-07-10", 267.7),
    ("2026-07-11", 457.0),
    ("2026-07-12", 370.1),
    ("2026-07-13", 100.0),
    ("2026-07-14", 291.0),
    ("2026-07-15", 361.1),
    ("2026-07-16", 329.6),
    ("2026-07-17", 316.6),
    ("2026-07-18", 421.1),
    ("2026-07-19", 198.5),
]

# Serie VERA di una sede grande (con coperti): 4 settimane al 20/09/2026
# contro le 4 prima. +5,9%: sotto soglia, deve tacere.
SERIE_TACE = [
    ("2026-07-27", 11959.09, 396),
    ("2026-07-28", 10368.25, 473),
    ("2026-07-29", 13722.18, 445),
    ("2026-07-30", 14253.89, 457),
    ("2026-07-31", 13799.61, 436),
    ("2026-08-01", 21739.24, 629),
    ("2026-08-02", 14716.97, 430),
    ("2026-08-03", 12756.34, 422),
    ("2026-08-04", 8755.01, 286),
    ("2026-08-05", 11027.84, 345),
    ("2026-08-06", 9993.8, 321),
    ("2026-08-07", 15956.54, 509),
    ("2026-08-08", 15317.16, 430),
    ("2026-08-09", 10605.66, 324),
    ("2026-08-10", 11583.9, 409),
    ("2026-08-11", 13333.25, 459),
    ("2026-08-12", 12197.56, 409),
    ("2026-08-13", 11037.65, 379),
    ("2026-08-14", 12886.02, 420),
    ("2026-08-15", 22683.29, 539),
    ("2026-08-16", 15587.17, 466),
    ("2026-08-17", 13050.92, 429),
    ("2026-08-18", 12436.03, 408),
    ("2026-08-19", 11659.99, 413),
    ("2026-08-20", 13223.5, 450),
    ("2026-08-21", 15902.8, 522),
    ("2026-08-22", 18245.13, 518),
    ("2026-08-23", 17439.2, 532),
    ("2026-08-24", 10292.62, 374),
    ("2026-08-25", 12231.2, 420),
    ("2026-08-26", 13143.43, 431),
    ("2026-08-27", 13434.01, 468),
    ("2026-08-28", 16091.57, 551),
    ("2026-08-29", 21321.67, 594),
    ("2026-08-30", 16064.12, 477),
    ("2026-08-31", 12364.73, 446),
    ("2026-09-01", 13045.07, 438),
    ("2026-09-02", 11413.66, 369),
    ("2026-09-03", 14236.09, 469),
    ("2026-09-04", 17555.06, 575),
    ("2026-09-05", 21249.36, 624),
    ("2026-09-06", 16658.69, 509),
    ("2026-09-07", 10878.87, 376),
    ("2026-09-08", 11348.27, 381),
    ("2026-09-09", 12224.82, 411),
    ("2026-09-10", 14099.8, 485),
    ("2026-09-11", 15098.51, 492),
    ("2026-09-12", 23470.63, 702),
    ("2026-09-13", 17073.16, 524),
    ("2026-09-14", 13235.81, 502),
    ("2026-09-15", 8910.35, 312),
    ("2026-09-16", 8464.94, 290),
    ("2026-09-17", 12413.03, 424),
    ("2026-09-18", 15607.7, 494),
    ("2026-09-19", 20864.1, 611),
    ("2026-09-20", 16136.42, 492),
]


class _SB:
    def __init__(self, righe):
        self._righe = righe
        self.tabelle = []

    def table(self, name):
        self.tabelle.append(name)
        return _FakeQuery(self._righe if name == "ricavi_giornalieri" else [], table=name)


def _righe(serie, rid=RID):
    out = []
    for x in serie:
        r = {"ristorante_id": rid, "data": x[0], "fatturato_iva10": x[1],
             "fatturato_iva22": 0, "altri_ricavi_noiva": 0, "coperti": None}
        if len(x) > 2:
            r["coperti"] = x[2]
        out.append(r)
    return out


# Martedi' 21/07/2026: le finestre finiscono domenica 19/07.
MARTEDI_SCATTA = date(2026, 7, 21)
MARTEDI_TACE = date(2026, 9, 22)


# ── andamento_incasso ────────────────────────────────────────────────────────

def test_andamento_scatta_sulla_serie_reale():
    rec = fw._briefing_andamento_incasso(RID, _SB(_righe(SERIE_SCATTA)), MARTEDI_SCATTA)
    assert rec is not None, "la serie reale a +15,7% non e' stata detta"
    p = rec["payload"]
    assert rec["topic_key"] == "andamento_incasso"
    assert p["incasso"] == 7102 and p["incasso_prec"] == 6136
    assert p["delta_pct"] == 16 and p["su"] is True
    assert p["settimane"] == 4
    # Senza coperti inseriti, coperti e scontrino non si inventano.
    assert "coperti_verso" not in p and "scontrino_verso" not in p


def test_andamento_tace_sulla_serie_reale_sotto_soglia():
    assert fw._briefing_andamento_incasso(RID, _SB(_righe(SERIE_TACE)), MARTEDI_TACE) is None


def test_andamento_tace_se_non_e_martedi():
    """Il mercoledi' le finestre sono IDENTICHE (finiscono sempre domenica):
    lo ferma solo il giorno. Ripeterlo ogni giorno sarebbe il rumore da togliere."""
    for giorno in (date(2026, 7, 20), date(2026, 7, 22), date(2026, 7, 26)):
        assert fw._briefing_andamento_incasso(RID, _SB(_righe(SERIE_SCATTA)), giorno) is None, giorno


def test_andamento_tace_sotto_i_venti_giorni():
    """Togliendo UN giorno alla finestra precedente (20 -> 19) il confronto non
    regge piu': chiusure e buchi di inserimento pesano piu' dell'andamento."""
    serie = [x for x in SERIE_SCATTA if x[0] != "2026-06-10"]
    assert fw._briefing_andamento_incasso(RID, _SB(_righe(serie)), MARTEDI_SCATTA) is None


def test_andamento_tace_se_l_ultima_finestra_ha_diciannove_giorni():
    """La guardia contro il guasto piu' probabile: la sede smette di inserire.
    Con 14 giorni su 28 il confronto direbbe un falso "-50%"."""
    serie = _serie_sintetica(1000.0, 1000.0)
    buchi = {date.fromordinal(date(2026, 6, 22).toordinal() + i).isoformat() for i in range(9)}
    serie = [x for x in serie if x[0] not in buchi]
    assert sum(1 for x in serie if x[0] >= "2026-06-22") == 19
    assert fw._briefing_andamento_incasso(RID, _SB(_righe(serie)), MARTEDI_SCATTA) is None


def test_coperti_taciuti_se_inseriti_meno_di_venti_giorni():
    """Chi comincia a inserire i coperti non deve leggere "coperti +400%"."""
    serie = _serie_sintetica(1000.0, 1200.0, 40, 40)
    serie = [(d, v, c if d >= "2026-06-10" else None) for (d, v, c) in serie]
    assert sum(1 for x in serie if x[0] < "2026-06-22" and x[2]) == 12
    p = fw._briefing_andamento_incasso(RID, _SB(_righe(serie)), MARTEDI_SCATTA)["payload"]
    assert p["delta_pct"] == 20
    assert "coperti_verso" not in p and "scontrino_verso" not in p


def test_scontrino_solo_sui_giorni_con_coperti():
    """21 giorni su 28 con coperti: lo scontrino si calcola sull'incasso di quei
    giorni. Sul totale uscirebbe un falso +33%."""
    serie = []
    for i in range(56):
        d = date.fromordinal(date(2026, 5, 25).toordinal() + i).isoformat()
        if i < 28:
            serie.append((d, 1000.0, 40))
        else:
            serie.append((d, 1200.0, 48 if i < 49 else None))
    p = fw._briefing_andamento_incasso(RID, _SB(_righe(serie)), MARTEDI_SCATTA)["payload"]
    assert p["scontrino_verso"] == "stabile"
    assert p["coperti_verso"] == "giu" and p["coperti_delta_pct"] == 10


def test_confine_di_stabile_al_tre_per_cento():
    """Sotto il 3% stabile, dal 3% in su si dice il verso."""
    p = fw._briefing_andamento_incasso(
        RID, _SB(_righe(_serie_sintetica(1000.0, 1200.0, 100, 103))), MARTEDI_SCATTA)["payload"]
    assert p["coperti_verso"] == "su" and p["coperti_delta_pct"] == 3
    p = fw._briefing_andamento_incasso(
        RID, _SB(_righe(_serie_sintetica(1000.0, 1200.0, 100, 102.9))), MARTEDI_SCATTA)["payload"]
    assert p["coperti_verso"] == "stabile"


def test_andamento_legge_solo_la_sua_sede():
    """Le righe di un'altra sede nelle stesse date non devono contare."""
    altra = _righe([(d, v * 5) for (d, v) in SERIE_SCATTA if d >= "2026-06-22"], rid="rid-altra")
    rec = fw._briefing_andamento_incasso(RID, _SB(_righe(SERIE_SCATTA) + altra), MARTEDI_SCATTA)
    assert rec is not None and rec["payload"]["incasso"] == 7102


def test_andamento_esclude_i_giorni_fuori_finestra():
    """Una riga dopo la domenica (lunedi' 20/07) non entra nell'ultima finestra,
    una prima del 25/05 non entra nella precedente."""
    extra = _righe([("2026-07-20", 99999.0), ("2026-05-24", 99999.0)])
    rec = fw._briefing_andamento_incasso(RID, _SB(_righe(SERIE_SCATTA) + extra), MARTEDI_SCATTA)
    assert rec["payload"]["incasso"] == 7102 and rec["payload"]["incasso_prec"] == 6136


def _serie_sintetica(prec, ultime, cop_prec=None, cop_ultime=None):
    """28 giorni al livello `prec` fino al 21/06 e 28 al livello `ultime` dopo."""
    out = []
    for i in range(56):
        d = date.fromordinal(date(2026, 5, 25).toordinal() + i).isoformat()
        prima = i < 28
        riga = [d, prec if prima else ultime]
        if cop_prec is not None:
            riga.append(cop_prec if prima else cop_ultime)
        out.append(tuple(riga))
    return out


def test_andamento_in_calo_con_coperti_e_scontrino():
    """-15% di incasso, coperti -15%, scontrino fermo: il calo e' di clienti."""
    serie = _serie_sintetica(1000.0, 850.0, 40, 34)
    rec = fw._briefing_andamento_incasso(RID, _SB(_righe(serie)), MARTEDI_SCATTA)
    p = rec["payload"]
    assert p["su"] is False and p["delta_pct"] == 15
    assert rec["severity"] == "warning"
    assert p["coperti_verso"] == "giu" and p["coperti_delta_pct"] == 15
    assert p["scontrino_verso"] == "stabile"


def test_andamento_scontrino_sale_oltre_il_tre_per_cento():
    serie = _serie_sintetica(1000.0, 1200.0, 40, 44)  # coperti +10%, scontrino +9%
    p = fw._briefing_andamento_incasso(RID, _SB(_righe(serie)), MARTEDI_SCATTA)["payload"]
    assert p["coperti_verso"] == "su" and p["coperti_delta_pct"] == 10
    assert p["scontrino_verso"] == "su" and p["scontrino_delta_pct"] == 9


def test_andamento_confine_del_dieci_per_cento():
    """9,9% tace, 10% parla."""
    assert fw._briefing_andamento_incasso(
        RID, _SB(_righe(_serie_sintetica(1000.0, 1099.0))), MARTEDI_SCATTA) is None
    assert fw._briefing_andamento_incasso(
        RID, _SB(_righe(_serie_sintetica(1000.0, 1100.0))), MARTEDI_SCATTA) is not None
    assert fw._briefing_andamento_incasso(
        RID, _SB(_righe(_serie_sintetica(1000.0, 901.0))), MARTEDI_SCATTA) is None


# ── food_cost_alto ───────────────────────────────────────────────────────────

def _sb_vuoto():
    q = MagicMock()
    q.table.return_value = q
    for m in ("select", "eq", "in_", "limit", "lt", "gte", "lte", "order"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


def _patch_costi(netto_agosto, fb_agosto, fb_settembre, anno=2026, extra=None):
    """Agosto con `netto_agosto` di ricavi (senza IVA) e `fb_agosto` di merce."""
    margini = {m: {} for m in range(1, 13)}
    margini[8] = {"altri_ricavi_noiva": netto_agosto}
    cfb = {8: fb_agosto, 9: fb_settembre}
    per_anno = {anno: (cfb, {})}
    per_anno.update(extra or {})
    calc = MagicMock(side_effect=lambda _u, _r, a: per_anno.get(a, ({}, {})))
    return patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(return_value=margini),
        calcola_costi_automatici_per_anno_sql=calc,
    ), calc


INIZIO_OTTOBRE = date(2026, 10, 2)


def test_food_cost_scatta_sul_caso_reale():
    """Il caso misurato: una piccola sede ad agosto 2026 al 45,8% (merce
    consolidata: a settembre sono gia' arrivate fatture)."""
    p_costi, _ = _patch_costi(4540.0, 2079.32, 150.0)
    with p_costi:
        rec = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)
    assert rec is not None, "food cost al 45,8% su mese consolidato non detto"
    p = rec["payload"]
    assert rec["topic_key"] == "food_cost_alto"
    assert p["mese"] == "agosto" and p["anno"] == 2026
    assert p["food_cost_pct"] == 45.8
    assert p["critico"] is True
    assert (p["soglia_min"], p["soglia_norma"], p["soglia_critica"]) == (28, 33, 38)
    # (45,8 - 33) / 100 * 4.540 = 581
    assert p["eccedenza"] == 581


def test_food_cost_legge_il_fatturato_inserito_come_totale_mensile():
    """Le sedi che inseriscono il fatturato del mese (ricavi_modalita_mensile)
    hanno margini_mensili a zero: senza la fusione tacerebbero sempre."""
    margini = {m: {} for m in range(1, 13)}
    calc = MagicMock(return_value=({8: 2079.32, 9: 150.0}, {}))
    ov = {(2026, 8): {"iva10": 0.0, "iva22": 0.0, "altri": 4540.0}}
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(return_value=margini),
        calcola_costi_automatici_per_anno_sql=calc,
    ), patch.object(fw, "_load_mensile_overrides", return_value=ov):
        rec = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)
    assert rec is not None and rec["payload"]["food_cost_pct"] == 45.8


def test_food_cost_tace_fino_al_trentatre():
    """Fino a 33 compreso e' la norma di KPI_SOGLIE (`<=`)."""
    for fb in (1498.2, 1400.0):  # 33,0% e 30,8%
        p_costi, _ = _patch_costi(4540.0, fb, 150.0)
        with p_costi:
            assert fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE) is None, fb


def test_food_cost_sopra_norma_ma_non_critico():
    p_costi, _ = _patch_costi(10000.0, 3550.0, 150.0)  # 35,5%
    with p_costi:
        p = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)["payload"]
    assert p["food_cost_pct"] == 35.5 and p["critico"] is False
    p_costi, _ = _patch_costi(10000.0, 3800.0, 150.0)  # 38,0: ancora "sopra la media"
    with p_costi:
        assert fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)["payload"]["critico"] is False


def test_food_cost_tace_se_il_mese_non_e_consolidato():
    """Nessuna fattura di merce del mese dopo: le fatture di fine agosto possono
    ancora arrivare, e l'ultimo mese caricato e' sistematicamente parziale."""
    p_costi, _ = _patch_costi(4540.0, 2079.32, 0.0)
    with p_costi:
        assert fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE) is None


def test_food_cost_tace_senza_incassi_o_senza_merce():
    for netto, fb in ((0.0, 2079.32), (4540.0, 0.0)):
        p_costi, _ = _patch_costi(netto, fb, 150.0)
        with p_costi:
            assert fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE) is None


def test_food_cost_tace_fuori_finestra():
    """Una volta al mese: fuori dalla finestra del MOL non si ripete."""
    p_costi, _ = _patch_costi(4540.0, 2079.32, 150.0)
    with p_costi:
        for giorno in (date(2026, 10, 8), date(2026, 10, 15), date(2026, 9, 24)):
            assert fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), giorno) is None, giorno


def test_food_cost_mese_giusto_nei_bordi_della_finestra():
    """Il 30/09 vale per ottobre (agosto); il 7/10 e' l'ultimo giorno utile."""
    assert fw._mese_food_cost_da_dire(date(2026, 9, 30)) == (8, 2026)
    assert fw._mese_food_cost_da_dire(date(2026, 10, 1)) == (8, 2026)
    assert fw._mese_food_cost_da_dire(date(2026, 10, 7)) == (8, 2026)
    assert fw._mese_food_cost_da_dire(date(2026, 10, 8)) is None
    assert fw._mese_food_cost_da_dire(date(2026, 1, 3)) == (11, 2025)
    assert fw._mese_food_cost_da_dire(date(2026, 2, 3)) == (12, 2025)


def test_food_cost_di_dicembre_si_consolida_con_gennaio_dell_anno_dopo():
    margini = {m: {} for m in range(1, 13)}
    margini[12] = {"altri_ricavi_noiva": 10000.0}
    per_anno = {2025: ({12: 4000.0}, {}), 2026: ({1: 200.0}, {})}
    calc = MagicMock(side_effect=lambda _u, _r, a: per_anno.get(a, ({}, {})))
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(return_value=margini),
        calcola_costi_automatici_per_anno_sql=calc,
    ):
        rec = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), date(2026, 2, 3))
    assert rec is not None and rec["payload"]["mese"] == "dicembre"
    assert {c.args[2] for c in calc.call_args_list} == {2025, 2026}
    per_anno[2026] = ({}, {})
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(return_value=margini),
        calcola_costi_automatici_per_anno_sql=calc,
    ):
        assert fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), date(2026, 2, 3)) is None


# ── Raccolta: settore, configuratore, solo path asincrono ────────────────────

def _spia_osservazioni(settore, spenti=frozenset(), oggi=INIZIO_OTTOBRE):
    rec_inc = {"topic_key": "andamento_incasso", "payload": {}}
    rec_fc = {"topic_key": "food_cost_alto", "payload": {}}
    with patch.object(fw, "_briefing_andamento_incasso", return_value=rec_inc) as a, \
         patch.object(fw, "_briefing_food_cost_alto", return_value=rec_fc) as f, \
         patch.object(fw, "_oggi_rome", return_value=oggi), \
         patch("services.settore_service.settore_sede", return_value=settore) as s:
        out = fw._briefing_osservazioni(UID, RID, MagicMock(), set(spenti))
    f.settore = s
    return [r["topic_key"] for r in out], a, f


def test_fuori_finestra_il_settore_non_si_legge():
    """22-23 giorni al mese il food cost non puo' uscire: niente query sul settore."""
    chiavi, _a, f = _spia_osservazioni(SETTORE_RISTORAZIONE, oggi=date(2026, 9, 24))
    assert chiavi == ["andamento_incasso"]
    f.assert_not_called()
    f.settore.assert_not_called()


def test_ristorante_riceve_entrambe_le_osservazioni():
    chiavi, _a, _f = _spia_osservazioni(SETTORE_RISTORAZIONE)
    assert chiavi == ["andamento_incasso", "food_cost_alto"]


def test_negozio_non_riceve_il_food_cost():
    chiavi, _a, f = _spia_osservazioni(SETTORE_RETAIL)
    assert chiavi == ["andamento_incasso"]
    f.assert_not_called()


def test_osservazione_spenta_non_si_calcola():
    chiavi, a, f = _spia_osservazioni(SETTORE_RISTORAZIONE, {"andamento_incasso", "food_cost_alto"})
    assert chiavi == []
    a.assert_not_called()
    f.assert_not_called()


def test_un_osservazione_che_fallisce_non_spegne_l_altra():
    with patch.object(fw, "_briefing_andamento_incasso", side_effect=RuntimeError("x")), \
         patch.object(fw, "_briefing_food_cost_alto", return_value={"topic_key": "food_cost_alto"}), \
         patch.object(fw, "_oggi_rome", return_value=INIZIO_OTTOBRE), \
         patch("services.settore_service.settore_sede", return_value=SETTORE_RISTORAZIONE):
        out = fw._briefing_osservazioni(UID, RID, MagicMock(), set())
    assert [r["topic_key"] for r in out] == ["food_cost_alto"]


_NEUTRI = {
    "_briefing_dati_mensili_mancanti": [],
    "_briefing_righe_da_classificare": None,
    "_briefing_fatture_mancanti": None,
    "_briefing_appuntamenti_oggi": [],
    "_briefing_buona_notizia": None,
    "_briefing_rientro_assenza": None,
    "_briefing_onboarding": None,
    "_briefing_aggiorna_last_seen": None,
}


def _raccogli(**kw):
    sentinella = {"topic_key": "andamento_incasso", "payload": {"x": 1}}
    patches = [patch.object(fw, k, return_value=v) for k, v in _NEUTRI.items()]
    patches.append(patch.object(fw, "_briefing_osservazioni", return_value=[sentinella]))
    patches.append(patch.object(fw, "_get_assistant_preferences", return_value={}))
    for p in patches:
        p.start()
    try:
        out = fw._briefing_raccogli_notifiche(
            UID, RID, _SB([]), includi_alert_prezzi=False, **kw)
    finally:
        for p in patches:
            p.stop()
    return [n.get("topic_key") for n in out]


def test_il_path_sincrono_non_calcola_le_osservazioni():
    """E7: la Home che aspetta ha 4 s. Il default e' il fast-path."""
    assert "andamento_incasso" not in _raccogli()


def test_il_path_asincrono_le_calcola():
    assert "andamento_incasso" in _raccogli(includi_osservazioni=True)


def test_la_rigenerazione_asincrona_chiede_le_osservazioni():
    with patch.object(fw, "_briefing_raccogli_notifiche", return_value=[]) as racc, \
         patch.object(fw, "_briefing_nome_referente", return_value=(None, [])), \
         patch("services.daily_briefing_service.generate_and_save_briefing"), \
         patch("services.get_supabase_client", return_value=MagicMock()):
        fw._briefing_rigenera_async(UID, RID)
    assert racc.call_args.kwargs.get("includi_osservazioni") is True


def test_configuratore_offre_le_due_osservazioni_spegnibili():
    voci = {k: b for (k, _l, b, _d) in fw._CONFIG_TOPICS}
    assert voci.get("andamento_incasso") is False
    assert voci.get("food_cost_alto") is False
    assert "andamento_incasso" not in dbs.TOPIC_LIVE_NON_IGNORABILI
    assert "food_cost_alto" not in dbs.TOPIC_LIVE_NON_IGNORABILI


# ── Snapshot: dove e come lo dice il briefing ────────────────────────────────

OSS_INCASSO = {
    "topic_key": "andamento_incasso", "severity": "success",
    "payload": {"settimane": 4, "incasso": 7102, "incasso_prec": 6136,
                "delta_pct": 16, "su": True},
}
OSS_FC = {
    "topic_key": "food_cost_alto", "severity": "warning",
    "payload": {"mese": "agosto", "anno": 2026, "food_cost_pct": 45.8, "critico": True,
                "soglia_min": 28, "soglia_norma": 33, "soglia_critica": 38,
                "eccedenza": 581},
}
FATTURATO_MANCA = {
    "topic_key": "fatturato_mancante", "severity": "warning",
    "payload": {"mese": "agosto", "anno": 2026}, "title": "Fatturato mancante",
}


def test_frasi_esatte():
    assert dbs._andamento_incasso_frase(OSS_INCASSO["payload"]) == (
        "\U0001F4CA Nelle ultime 4 settimane sono entrati € 7.102 di incasso, "
        "il 16% in più delle 4 settimane prima (€ 6.136)."
    )
    assert dbs._food_cost_alto_frase(OSS_FC["payload"]) == (
        "\U0001F37D️ Ad agosto il food cost è stato del 45,8%, oltre la soglia critica "
        "del 38%: rispetto al 33% sono circa € 581 di acquisti in più."
    )
    lug = dict(OSS_FC["payload"], mese="luglio", food_cost_pct=35.5, critico=False, eccedenza=250)
    assert dbs._food_cost_alto_frase(lug) == (
        "\U0001F37D️ A luglio il food cost è stato del 35,5%, sopra la norma del settore "
        "(28-33%): rispetto al 33% sono circa € 250 di acquisti in più."
    )


def test_frase_incasso_in_calo_con_coperti():
    p = dict(OSS_INCASSO["payload"], su=False, delta_pct=15, coperti_verso="giu",
             coperti_delta_pct=15, scontrino_verso="stabile", scontrino_delta_pct=1)
    assert dbs._andamento_incasso_frase(p).endswith(
        "il 15% in meno delle 4 settimane prima (€ 6.136). I coperti sono scesi del 15% "
        "e lo scontrino medio è rimasto stabile."
    )
    p.update(coperti_verso="stabile", scontrino_verso="su", scontrino_delta_pct=9)
    assert dbs._andamento_incasso_frase(p).endswith(
        "I coperti sono rimasti stabili e lo scontrino medio è salito del 9%."
    )


def test_le_osservazioni_aprono_il_briefing_prima_delle_cose_da_fare():
    snap = dbs._build_snapshot([FATTURATO_MANCA, OSS_FC, OSS_INCASSO])
    righe = snap["narrative"].split("\n")
    assert righe[0].startswith("\U0001F4CA Nelle ultime 4 settimane")
    assert righe[1].startswith("\U0001F37D️ Ad agosto il food cost")
    assert righe[2] == "Da sistemare oggi:"
    # Non sono card: le card sono solo cose da fare.
    assert [a["topic_key"] for a in snap["azioni"]] == ["fatturato_mancante"]


def test_le_osservazioni_non_toccano_il_verde():
    snap = dbs._build_snapshot([OSS_INCASSO])
    assert snap["azioni"] == [] and snap["tutto_ok"] is True
    assert snap["narrative"].startswith("\U0001F4CA")


def test_osservazione_spenta_dal_configuratore_non_si_dice():
    snap = dbs._build_snapshot([OSS_INCASSO, OSS_FC], topics_disabled=["food_cost_alto"])
    assert "food cost" not in snap["narrative"]
    assert "Nelle ultime 4 settimane" in snap["narrative"]


def test_al_cliente_nuovo_non_si_fanno_osservazioni():
    onb = {"topic_key": "onboarding", "payload": {}}
    snap = dbs._build_snapshot([onb, OSS_INCASSO, OSS_FC])
    assert "Nelle ultime" not in snap["narrative"] and "food cost" not in snap["narrative"]


# ── La narrativa AI non puo' perderle ────────────────────────────────────────

def test_validatore_scarta_un_testo_che_perde_la_cifra_obbligatoria():
    bullets = [dbs._andamento_incasso_frase(OSS_INCASSO["payload"])]
    ok, motivo = dbs._narrazione_e_valida("Da sistemare oggi il fatturato.", bullets, ["16"])
    assert ok is False and "obbligatorio" in motivo
    assert dbs._narrazione_e_valida("L'incasso e' salito del 16%.", bullets, ["16"])[0] is True


def test_validatore_accetta_il_food_cost_arrotondato():
    bullets = [dbs._food_cost_alto_frase(OSS_FC["payload"])]
    for testo in ("food cost al 45,8%", "food cost al 46%", "food cost al 45%"):
        assert dbs._narrazione_e_valida(testo, bullets, ["45.8"])[0] is True, testo
    assert dbs._narrazione_e_valida("food cost alto", bullets, ["45.8"])[0] is False


def test_numeri_obbligatori_delle_osservazioni():
    assert dbs._numeri_obbligatori([OSS_INCASSO, OSS_FC, FATTURATO_MANCA]) == ["16", "45.8"]


def _client_che_risponde(testo):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=testo))]
    resp.usage = None
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def test_snapshot_ricade_sul_template_se_l_ai_tace_l_osservazione():
    """Cablaggio vero: _build_snapshot -> _narrate_with_ai -> validatore."""
    tace = _client_che_risponde("Il fatturato di agosto va ancora inserito.")
    with patch("services.ai_service._get_openai_client", return_value=tace):
        snap = dbs._build_snapshot([FATTURATO_MANCA, OSS_INCASSO], use_ai=True)
    assert snap["narrative"].startswith("\U0001F4CA Nelle ultime 4 settimane")

    dice = _client_che_risponde(
        "Nelle ultime 4 settimane l'incasso e' salito del 16%, € 7.102 contro € 6.136. "
        "Il fatturato di agosto 2026 va ancora inserito.")
    with patch("services.ai_service._get_openai_client", return_value=dice):
        snap = dbs._build_snapshot([FATTURATO_MANCA, OSS_INCASSO], use_ai=True)
    assert snap["narrative"].startswith("Nelle ultime 4 settimane l'incasso e' salito")


def test_la_sola_osservazione_basta_a_chiamare_l_ai():
    """Senza card da fare, l'osservazione e' comunque una ragione per narrare."""
    dice = _client_che_risponde(
        "Nelle ultime 4 settimane l'incasso e' salito del 16%, € 7.102 contro € 6.136.")
    with patch("services.ai_service._get_openai_client", return_value=dice):
        snap = dbs._build_snapshot([OSS_INCASSO], use_ai=True)
    assert snap["narrative"].startswith("Nelle ultime 4 settimane l'incasso e' salito")


def test_al_cliente_nuovo_la_narrativa_ai_non_pretende_i_numeri_delle_osservazioni():
    """Nel ramo onboarding i bullet delle osservazioni non entrano: pretenderne
    la cifra scarterebbe ogni narrativa."""
    onb = {"topic_key": "onboarding", "payload": {}}
    ai = _client_che_risponde("Benvenuto in ONEFLUX, per iniziare bastano i primi dati.")
    with patch("services.ai_service._get_openai_client", return_value=ai):
        snap = dbs._build_snapshot([onb, OSS_INCASSO], use_ai=True)
    assert snap["narrative"] == "Benvenuto in ONEFLUX, per iniziare bastano i primi dati."


def test_narrativa_troncata_ricade_sul_template():
    """Col limite di token il testo puo' finire a meta' frase: i numeri obbligatori
    stanno all'inizio e il validatore lo lascerebbe passare."""
    ai = _client_che_risponde(
        "Nelle ultime 4 settimane l'incasso e' salito del 16%, € 7.102 contro")
    ai.chat.completions.create.return_value.choices[0].finish_reason = "length"
    with patch("services.ai_service._get_openai_client", return_value=ai):
        snap = dbs._build_snapshot([OSS_INCASSO], use_ai=True)
    assert snap["narrative"].startswith("\U0001F4CA Nelle ultime 4 settimane sono entrati")


def test_bump_della_versione_del_briefing():
    """Senza bump chi ha lo snapshot di oggi non vede le osservazioni fino al TTL."""
    assert dbs._BRIEFING_CODE_VERSION >= 27
