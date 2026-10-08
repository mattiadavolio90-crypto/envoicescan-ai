"""Fase E del piano consulente (08/10/2026): numeri coerenti in catena.

Il caso: ad agosto 2026 OVERTIME ha incassato 5.936 EUR netti contro i ~29.000
dei mesi vicini (chiusura per ferie) e la catena ha detto «food cost del 94,6%,
oltre la soglia critica». Mattia: «si erano chiusi per ferie quindi nessun
allarme». Un mese con l'incasso sotto i 3/4 della mediana dei mesi vicini non
da' l'allarme del food cost; la chat lo sa e lo dice; la catena chiede un mese
preciso con gli stessi numeri della pagina.

Le serie sono quelle misurate sul live l'8/10 (netti mensili di OVERTIME 2026).
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw
from services.routers import gruppo

UID, RID = "u-e", "r-e"
OGGI = date(2026, 10, 8)

# Netti mensili di OVERTIME 2026 (misura dell'8/10) e la sua merce.
NETTI_OVERTIME = {
    1: 28075.0, 2: 65771.0, 3: 37682.0, 4: 27178.0, 5: 34022.0,
    6: 27335.0, 7: 29106.0, 8: 5936.0, 9: 31285.0,
}
FB_OVERTIME = {
    1: 5826.0, 2: 17980.0, 3: 13338.0, 4: 9834.0, 5: 9008.0,
    6: 11002.0, 7: 8166.0, 8: 5541.0, 9: 9379.0, 10: 1786.0,
}


def _netti(anno, per_mese):
    return {(anno, m): v for m, v in per_mese.items()}


# ── La regola pura ────────────────────────────────────────────────────────

def test_agosto_di_ferie_e_fuori_norma_e_nessun_altro_mese():
    netti = _netti(2026, NETTI_OVERTIME)
    esiti = {m: fw._incasso_fuori_norma(netti, 2026, m, OGGI) for m in NETTI_OVERTIME}
    assert esiti[8] is True
    assert {m for m, v in esiti.items() if v is True} == {8}


def test_aprile_di_overtime_non_e_fuori_norma_col_riferimento_centrato():
    """Coi soli mesi precedenti (gen 28k, feb 66k, mar 38k) aprile valeva 0,72:
    il riferimento e' centrato sul mese, e con i mesi dopo e' 0,90."""
    netti = _netti(2026, NETTI_OVERTIME)
    assert fw._incasso_fuori_norma(netti, 2026, 4, OGGI) is False


@pytest.mark.parametrize("netto, atteso", [(75.0, False), (74.99, True)])
def test_soglia_tre_quarti_della_mediana(netto, atteso):
    netti = {(2026, 5): 100.0, (2026, 6): 100.0, (2026, 7): 100.0, (2026, 8): netto}
    assert fw._incasso_fuori_norma(netti, 2026, 8, OGGI) is atteso


def test_la_mediana_non_la_media():
    """Un mese eccezionale (66k) non alza il riferimento: con la media 30 su
    (40, 40, 400) sarebbe sotto i 3/4, con la mediana (40) no."""
    netti = {(2026, 5): 40.0, (2026, 6): 40.0, (2026, 7): 400.0, (2026, 8): 31.0}
    assert fw._incasso_fuori_norma(netti, 2026, 8, OGGI) is False


def test_mediana_di_un_numero_pari_di_mesi():
    # (20 + 40) / 2 = 30 -> soglia 22,5
    base = {(2026, 4): 20.0, (2026, 5): 20.0, (2026, 6): 40.0, (2026, 7): 40.0}
    assert fw._incasso_fuori_norma({**base, (2026, 8): 22.6}, 2026, 8, OGGI) is False
    assert fw._incasso_fuori_norma({**base, (2026, 8): 22.4}, 2026, 8, OGGI) is True


def test_servono_tre_mesi_di_riferimento():
    due = {(2026, 6): 100.0, (2026, 7): 100.0, (2026, 8): 10.0}
    assert fw._incasso_fuori_norma(due, 2026, 8, OGGI) is None
    tre = {**due, (2026, 5): 100.0}
    assert fw._incasso_fuori_norma(tre, 2026, 8, OGGI) is True


def test_il_mese_in_corso_non_fa_da_riferimento():
    """Ottobre e' in corso (parziale): contarlo darebbe il terzo mese."""
    netti = {(2026, 6): 100.0, (2026, 7): 100.0, (2026, 8): 10.0, (2026, 10): 100.0}
    assert fw._incasso_fuori_norma(netti, 2026, 8, OGGI) is None


def test_raggio_di_sei_mesi():
    lontani = {(2026, 1): 100.0, (2025, 12): 100.0, (2025, 11): 100.0, (2026, 8): 10.0}
    assert fw._incasso_fuori_norma(lontani, 2026, 8, OGGI) is None, "7+ mesi prima contano"
    vicini = {(2026, 2): 100.0, (2026, 3): 100.0, (2026, 4): 100.0, (2026, 8): 10.0}
    assert fw._incasso_fuori_norma(vicini, 2026, 8, OGGI) is True


def test_raggio_vale_anche_dopo():
    netti = {(2026, 2): 100.0, (2026, 3): 100.0, (2026, 9): 100.0, (2026, 8): 10.0}
    assert fw._incasso_fuori_norma(netti, 2026, 8, date(2027, 6, 1)) is True
    netti_oltre = {(2026, 2): 100.0, (2026, 3): 100.0, (2027, 3): 100.0, (2026, 8): 10.0}
    assert fw._incasso_fuori_norma(netti_oltre, 2026, 8, date(2027, 6, 1)) is None


def test_riferimento_che_attraversa_l_anno():
    netti = {(2025, 11): 100.0, (2025, 12): 100.0, (2026, 2): 100.0, (2026, 1): 10.0}
    assert fw._incasso_fuori_norma(netti, 2026, 1, OGGI) is True


def test_mese_senza_incasso_non_e_giudicabile():
    netti = {(2026, 5): 100.0, (2026, 6): 100.0, (2026, 7): 100.0}
    assert fw._incasso_fuori_norma(netti, 2026, 8, OGGI) is None


@pytest.mark.parametrize("anno, mese, oggi, attesi", [
    (2026, 8, OGGI, [2026]),
    (2026, 1, OGGI, [2025, 2026]),
    (2026, 6, OGGI, [2025, 2026]),
    (2026, 7, OGGI, [2026]),
    (2025, 12, OGGI, [2025, 2026]),
    (2026, 9, date(2027, 2, 1), [2026, 2027]),
])
def test_anni_da_leggere(anno, mese, oggi, attesi):
    assert fw._anni_riferimento_incasso(anno, mese, oggi) == attesi


def test_netti_mensili_scorpora_l_iva_come_kpi_periodo():
    netti = fw._netti_mensili(
        lambda a: {8: {"fatturato_iva10": 1100.0, "altri_ricavi_noiva": 50.0}} if a == 2026 else {},
        [2025, 2026],
    )
    assert netti == {(2026, 8): pytest.approx(1050.0)}


# ── Il finto Supabase e le fonti dei margini ──────────────────────────────

def _sb_vuoto():
    q = MagicMock()
    q.table.return_value = q
    for m in ("select", "eq", "in_", "limit", "lt", "gte", "lte", "order", "is_", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


def _margini_overtime(agosto_netto=None):
    netti = dict(NETTI_OVERTIME)
    if agosto_netto is not None:
        netti[8] = agosto_netto
    return {m: {"altri_ricavi_noiva": v} for m, v in netti.items()}


def _patch_fonti(margini_2026, fb_2026=None):
    fb_2026 = FB_OVERTIME if fb_2026 is None else fb_2026
    return patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: margini_2026 if a == 2026 else {}),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: (fb_2026, {}) if a == 2026 else ({}, {})),
    )


# ── L'osservazione «food cost alto» (Home del PV e catena) ────────────────

INIZIO_OTTOBRE = date(2026, 10, 2)


def test_osservazione_tace_su_agosto_di_ferie():
    with _patch_fonti(_margini_overtime()):
        rec = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)
    assert rec is None, "OVERTIME agosto 2026 (95,3%, chiuso per ferie) non e' un allarme"


def test_osservazione_resta_su_un_agosto_normale_con_food_cost_alto():
    """Stesso locale, agosto con l'incasso dei mesi vicini e la merce al 51,7%:
    l'allarme c'e'. Senza questo caso il test sopra resterebbe verde anche se
    l'osservazione tacesse sempre."""
    fb = dict(FB_OVERTIME)
    fb[8] = 15000.0
    with _patch_fonti(_margini_overtime(agosto_netto=29000.0), fb):
        rec = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)
    assert rec is not None
    assert rec["payload"]["food_cost_pct"] == 51.7


def test_osservazione_senza_storia_resta_come_prima():
    """Meno di tre mesi di riferimento: non giudicabile, si dice come prima."""
    margini = {8: {"altri_ricavi_noiva": 5936.0}, 9: {"altri_ricavi_noiva": 31285.0}}
    with _patch_fonti(margini):
        rec = fw._briefing_food_cost_alto(UID, RID, _sb_vuoto(), INIZIO_OTTOBRE)
    assert rec is not None and rec["payload"]["food_cost_pct"] == 93.3


def test_un_errore_di_lettura_non_e_nella_norma_ne_fuori():
    with patch("services.margine_service.carica_margini_anno", side_effect=RuntimeError("giu'")):
        assert fw._incasso_fuori_norma_sede(UID, RID, _sb_vuoto(), 2026, 8, OGGI) is None


def test_fuori_norma_sede_riusa_i_margini_che_il_chiamante_ha_gia():
    carica = MagicMock(return_value={})
    with patch("services.margine_service.carica_margini_anno", carica):
        v = fw._incasso_fuori_norma_sede(UID, RID, _sb_vuoto(), 2026, 8, OGGI,
                                         {2026: _margini_overtime()})
    assert v is True
    carica.assert_not_called()


# ── La chat del punto vendita ─────────────────────────────────────────────

def _query_margini():
    with _patch_fonti(_margini_overtime()), \
         patch.object(fw, "_oggi_rome", return_value=OGGI):
        return fw._chat_query_margini({"id": UID}, _sb_vuoto(), None, ristorante_id=RID)


def test_query_margini_segna_agosto_e_solo_agosto():
    mesi = {r["mese"]: r for r in _query_margini()["mesi"]}
    agosto = mesi["agosto 2026"]
    assert agosto["incasso_fuori_norma"] is True
    assert "ferie" in agosto["nota"]
    assert agosto["food_cost_pct"] == 93.3, "il numero resta quello della pagina"
    segnati = {k for k, r in mesi.items() if "incasso_fuori_norma" in r}
    assert segnati == {"agosto 2026"}


def test_query_margini_non_segna_il_mese_in_corso():
    """Ottobre ha solo la merce (nessun incasso): ma anche un ottobre con un
    incasso piccolo e' parziale, non un mese di ferie."""
    margini = _margini_overtime()
    margini[10] = {"altri_ricavi_noiva": 3000.0}
    with _patch_fonti(margini), patch.object(fw, "_oggi_rome", return_value=OGGI):
        mesi = {r["mese"]: r for r in fw._chat_query_margini(
            {"id": UID}, _sb_vuoto(), None, ristorante_id=RID)["mesi"]}
    assert mesi["ottobre 2026"]["parziale"] is True
    assert "incasso_fuori_norma" not in mesi["ottobre 2026"]


def _home_kpi(oggi):
    fw._HOME_KPI_CACHE.clear()
    try:
        with _patch_fonti(_margini_overtime()), \
             patch.object(fw, "_resolve_user_from_token", return_value={"id": UID}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb_vuoto()), \
             patch.object(fw, "_resolve_ristorante_id", return_value=RID), \
             patch.object(fw, "_oggi_rome", return_value=oggi):
            return fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()


def test_home_kpi_segna_agosto_mostrato_a_settembre():
    kpi = _home_kpi(date(2026, 9, 10))
    assert kpi.periodo_label == "Agosto"
    assert kpi.incasso_fuori_norma is True


def test_home_kpi_non_segna_settembre_mostrato_a_ottobre():
    kpi = _home_kpi(OGGI)
    assert kpi.periodo_label == "Settembre"
    assert kpi.incasso_fuori_norma is False


def _kpi(fuori_norma):
    return MagicMock(
        has_data=True, food_cost_pct=93.3, fatturato=6488.0,
        costo_personale=7430.0, spese_generali=500.0, mol=-7000.0,
        periodo_label="Agosto", confronto_label=None,
        incasso_fuori_norma=fuori_norma,
    )


def _prompt_pv(kpi, monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: kpi)
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    user = {"id": UID, "nome_ristorante": "OVERTIME", "email": "t@x.it",
            "pagine_abilitate": {"margini": True}}
    return fw._build_chat_system_prompt(user, _sb_vuoto(), None, RID, None)


def test_prompt_pv_dice_che_agosto_non_e_un_allarme(monkeypatch):
    p = _prompt_pv(_kpi(True), monkeypatch)
    assert "nel mese di agosto l'incasso e' stato molto piu' basso del solito" in p
    assert "non e' un allarme" in p


@pytest.mark.parametrize("valore", [False, None])
def test_prompt_pv_tace_sul_mese_normale(valore, monkeypatch):
    p = _prompt_pv(_kpi(valore), monkeypatch)
    assert "molto piu' basso del solito" not in p


# ── La catena: il mese, il food cost, la stessa fonte ─────────────────────

@pytest.mark.parametrize("args, atteso", [
    ({"mese": 8}, 8),
    ({"mese": 12}, 12),
    ({"mese": 1}, 1),
    ({}, None),
    ({"mese": 13}, None),
    ({"mese": 0}, None),
    ({"mese": True}, None),
    ({"mese": "8"}, None),
])
def test_tool_catena_passa_il_mese(args, atteso):
    g = MagicMock()
    with patch.object(fw, "_gruppo_router_mod", return_value=g):
        fw._chat_esegui_tool_gruppo("gruppo_margini_coperti", args, "Bearer t")
    g.gruppo_margini_coperti.assert_called_once_with(mese=atteso, authorization="Bearer t")


def test_tool_catena_dichiara_il_mese():
    tool = next(t for t in fw._CHAT_TOOLS_GRUPPO
                if t["function"]["name"] == "gruppo_margini_coperti")
    mese = tool["function"]["parameters"]["properties"]["mese"]
    assert (mese["type"], mese["minimum"], mese["maximum"]) == ("integer", 1, 12)
    retail = next(t for t in fw._chat_tools_gruppo("retail")
                  if t["function"]["name"] == "gruppo_margini_coperti")
    assert "mese" in retail["function"]["parameters"]["properties"]


def _prompt_catena(settore, monkeypatch):
    monkeypatch.setattr(
        fw, "_gruppo_router_mod",
        lambda: MagicMock(gruppo_overview=MagicMock(side_effect=RuntimeError("no"))),
    )
    return fw._build_chat_system_prompt_catena({"id": UID}, _sb_vuoto(), None, settore)


def test_prompt_catena_chiede_il_periodo_e_spiega_il_mese_fuori_norma(monkeypatch):
    p = _prompt_catena(None, monkeypatch)
    assert "Di' sempre a quale periodo si riferisce ogni numero" in p
    assert "passa `mese` a gruppo_margini_coperti" in p
    assert "incasso_fuori_norma" in p and "il suo food cost e il suo margine" in p
    assert "Il food cost del gruppo e dei punti vendita sta in gruppo_margini_coperti" in p
    r = _prompt_catena("retail", monkeypatch)
    assert "la sua incidenza della merce e il suo margine" in r
    assert "il suo food cost" not in r
    assert "L'incidenza della merce del gruppo e dei punti vendita sta in" in r


# Agosto 2026 di una sede di catena: IVA al 10% da scorporare, ricavi senza IVA,
# altri costi F&B a mano e quota di un costo di gruppo. Ogni addendo della
# formula ha un valore diverso: una copia che ne dimentica uno da' un altro numero.
RIGA_AGOSTO = {
    "ristorante_id": "a", "anno": 2026, "mese": 8,
    "fatturato_netto": 0, "fatturato_iva10": 11_000.0, "fatturato_iva22": 1_220.0,
    "altri_ricavi_noiva": 500.0, "altri_costi_fb": 300.0, "altri_costi_spese": 0,
    "quote_riparto_fb": 200.0, "quote_riparto_spese": 0,
    "costo_dipendenti": 2_000.0, "costo_personale_extra": 0,
    "costo_personale_chiamata": 0, "coperti": 400,
}
FB_AUTO_AGOSTO = 4_000.0


class _Q:
    def __init__(self, righe):
        self._righe = righe

    def __getattr__(self, _n):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=self._righe, count=len(self._righe))


class _SBCatena:
    def table(self, nome):
        return _Q([dict(RIGA_AGOSTO)] if nome == "margini_mensili" else [])


def _margini_coperti(mese, fuori_norma, fb_auto=FB_AUTO_AGOSTO):
    sb = _SBCatena()
    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, UID, [{"id": "a"}], "Gruppo", {"a": "PV a"}, ["a"])), \
         patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 10)), \
         patch.object(gruppo, "_completezza_dati_pv", return_value={}), \
         patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": FB_AUTO_AGOSTO}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               return_value={"a": ({8: fb_auto} if fb_auto else {}, {})}), \
         patch.object(fw, "_incasso_fuori_norma_sede", fuori_norma):
        return gruppo.gruppo_margini_coperti(mese=mese, authorization="Bearer t")


def test_presidio_catena_e_pagina_stesso_mese_stesso_food_cost():
    """Il food cost che la chat di catena legge per agosto e' quello della
    pagina Margini del PV (`_kpi_periodo`) e della chat del PV
    (`_chat_query_margini`), sugli stessi dati."""
    resp = _margini_coperti(8, MagicMock(return_value=None))
    catena = resp.righe[0].food_cost_perc

    margini_pv = {8: {k: v for k, v in RIGA_AGOSTO.items()
                      if k not in ("ristorante_id", "anno", "mese")}}
    pagina = fw._kpi_periodo(margini_pv, {8: FB_AUTO_AGOSTO}, {}, 8)["food_cost_pct"]
    with _patch_fonti(margini_pv, {8: FB_AUTO_AGOSTO}), \
         patch.object(fw, "_oggi_rome", return_value=OGGI):
        chat_pv = {r["mese"]: r for r in fw._chat_query_margini(
            {"id": UID}, _sb_vuoto(), None, ristorante_id="a")["mesi"]}["agosto 2026"]["food_cost_pct"]

    # (4.000 + 300 + 200) / (10.000 + 1.000 + 500) = 39,1%
    assert catena == pagina == chat_pv == 39.1
    assert resp.gruppo.food_cost_perc == 39.1
    assert resp.periodo_label == "Agosto 2026"


def test_catena_food_cost_none_senza_merce(monkeypatch):
    monkeypatch.setitem(RIGA_AGOSTO, "altri_costi_fb", 0)
    monkeypatch.setitem(RIGA_AGOSTO, "quote_riparto_fb", 0)
    resp = _margini_coperti(8, MagicMock(return_value=None), fb_auto=0)
    assert resp.righe[0].food_cost_perc is None, "uno 0% senza merce non e' un valore"


@pytest.mark.parametrize("esito", [True, False, None])
def test_catena_riporta_l_incasso_fuori_norma_del_mese(esito):
    calcolo = MagicMock(return_value=esito)
    resp = _margini_coperti(8, calcolo)
    assert resp.righe[0].incasso_fuori_norma is esito
    assert resp.gruppo.incasso_fuori_norma is None
    _u, rid, _sb, anno, mese, _oggi = calcolo.call_args.args
    assert (_u, rid, anno, mese) == (UID, "a", 2026, 8)


def test_catena_senza_mese_non_giudica_l_incasso():
    calcolo = MagicMock(return_value=True)
    resp = _margini_coperti(None, calcolo)
    calcolo.assert_not_called()
    assert resp.righe[0].incasso_fuori_norma is None


def test_tool_catena_mette_la_nota_accanto_al_mese_fuori_norma():
    """Col modello vero la sola riga del prompt dava «problema grave» 2 volte su 3."""
    g = MagicMock()
    g.gruppo_margini_coperti.return_value.model_dump.return_value = {
        "righe": [
            {"nome": "OVERTIME", "food_cost_perc": 93.3, "incasso_fuori_norma": True},
            {"nome": "OFFSIDE", "food_cost_perc": 42.7, "incasso_fuori_norma": False},
            {"nome": "LAND", "food_cost_perc": 30.0, "incasso_fuori_norma": None},
        ],
        "gruppo": {"food_cost_perc": 60.0, "incasso_fuori_norma": None},
    }
    with patch.object(fw, "_gruppo_router_mod", return_value=g):
        out = fw._chat_esegui_tool_gruppo("gruppo_margini_coperti", {"mese": 8}, "Bearer t")
    note = {r["nome"]: r.get("nota") for r in out["righe"]}
    assert "non sono un allarme" in note["OVERTIME"]
    assert note["OFFSIDE"] is None and note["LAND"] is None
    assert out["righe"][0]["food_cost_perc"] == 93.3, "il numero resta quello della pagina"
