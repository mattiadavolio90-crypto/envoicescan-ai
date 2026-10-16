"""Una sola regola per «il mese ha la merce che serve per giudicarne i conti».

Perche' esiste
==============
Audit di ottobre 2026 (K03): 100 EUR inseriti a mano su 386.300 EUR di incasso
netto bastavano a dichiarare completo un mese senza una fattura (MOL verde,
food cost 0%), e la regola «merce > 0» era ricopiata in sette punti, uno dei
quali (la catena) gia' divergeva. Decisione di Mattia del 16/10/2026, misurata
sui 73 mesi chiusi del live: meno del 15% del netto = senza merce; il mese in
corso resta sulla merce assente. Qui la regola e ogni punto che deve usarla.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw
from services.completezza_mese import SOGLIA_MERCE_SU_NETTO, merce_insufficiente
from services.routers import gruppo
from tests.helpers_ts import esegui_ts


# ── La regola ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("netto,merce,atteso", [
    (386299.74, 100.0, True),        # il caso K03
    (100000.0, 14999.0, True),       # sotto il 15%
    (100000.0, 15000.0, False),      # al 15%
    (73323.0, 13059.0, False),       # il bar reale al 17,8%
    (405016.0, 37777.0, True),       # marzo di una sede appena entrata, 9,3%
    (5936.0, 5658.0, False),         # agosto di ferie: poco incasso, merce alta
    (0.0, 0.0, False),               # senza incasso non si giudica
    (0.0, 500.0, False),
])
def test_mese_chiuso(netto, merce, atteso):
    assert merce_insufficiente(netto, merce) is atteso


@pytest.mark.parametrize("merce,atteso", [(0.0, True), (1.0, False), (100.0, False)])
def test_mese_in_corso_guarda_solo_la_merce_assente(merce, atteso):
    assert merce_insufficiente(386299.74, merce, in_corso=True) is atteso


def test_la_soglia_e_quella_decisa():
    assert SOGLIA_MERCE_SU_NETTO == 0.15


# ── Home: _kpi_periodo e home_kpi ───────────────────────────────────────────

SETTEMBRE_K03 = {9: {"fatturato_iva10": 309017.38, "altri_ricavi_noiva": 105374.85, "altri_costi_fb": 100.0}}


def test_kpi_del_caso_k03_e_senza_merce():
    assert fw._kpi_periodo(SETTEMBRE_K03, {}, {}, 9)["costi_mancanti"] is True


def test_home_kpi_mostra_il_caso_k03_come_incompleto():
    fw._HOME_KPI_CACHE.clear()
    try:
        with patch.multiple(
            "services.margine_service",
            carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: SETTEMBRE_K03 if a == 2026 else {}),
            calcola_costi_automatici_per_anno_sql=MagicMock(return_value=({}, {})),
        ), patch.object(fw, "_resolve_user_from_token", return_value={"id": "u"}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb()), \
             patch.object(fw, "_resolve_ristorante_id", return_value="r"), \
             patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)):
            kpi = fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()
    assert kpi.periodo_label == "Settembre" and kpi.costi_mancanti is True


def test_home_kpi_sul_mese_in_corso_non_applica_la_percentuale():
    """Cliente appena partito: solo il mese in corso, con poca merce. Non giallo."""
    ottobre = {10: {"fatturato_iva10": 50000.0}}
    fw._HOME_KPI_CACHE.clear()
    try:
        with patch.multiple(
            "services.margine_service",
            carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: ottobre if a == 2026 else {}),
            calcola_costi_automatici_per_anno_sql=MagicMock(
                side_effect=lambda _u, _r, a: ({10: 2000.0}, {}) if a == 2026 else ({}, {})),
        ), patch.object(fw, "_resolve_user_from_token", return_value={"id": "u"}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb()), \
             patch.object(fw, "_resolve_ristorante_id", return_value="r"), \
             patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)):
            kpi = fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()
    assert kpi.is_mese_in_corso is True and kpi.costi_mancanti is False


# ── Salute e avviso «mancano le fatture costo» ──────────────────────────────

def _sb(margini_rows=None):
    q = MagicMock()
    q.table.return_value = q
    for m in ("select", "eq", "in_", "limit", "lt", "gte", "lte", "order", "is_", "not_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=margini_rows or [])
    return q


@pytest.mark.parametrize("auto,riga,atteso", [
    (0.0, {"fatturato_iva10": 424930.0, "altri_costi_fb": 100.0}, True),     # K03: 100 a mano
    (14000.0, {"fatturato_iva10": 110000.0}, True),                          # 14% del netto
    (16000.0, {"fatturato_iva10": 110000.0}, False),                         # 16%
    (0.0, {"fatturato_iva10": 110000.0, "quote_riparto_fb": 20000.0}, False),  # sole quote di gruppo
])
def test_merce_del_mese_somma_fatture_manuale_e_quote(auto, riga, atteso):
    with patch.object(fw, "_costi_automatici_mese", return_value=auto), \
         patch.object(fw, "_load_mensile_overrides", return_value={}):
        out = fw._merce_del_mese("r", 2026, 9, _sb([riga]), "u")
    assert out["insufficiente"] is atteso


def test_merce_del_mese_usa_l_incasso_dell_override():
    """Sede in modalita' mensile: margini_mensili ha 0, l'incasso vero e' l'override."""
    ov = {(2026, 6): {"iva10": 80655.3, "iva22": 0.0, "altri": 0.0}}
    with patch.object(fw, "_costi_automatici_mese", return_value=13059.0), \
         patch.object(fw, "_load_mensile_overrides", return_value=ov):
        out = fw._merce_del_mese("r", 2026, 6, _sb([{"fatturato_iva10": 3549.7}]), "u")
    assert out["netto"] == pytest.approx(73323.0, abs=1) and out["insufficiente"] is False


def test_merce_del_mese_non_sa_se_le_fatture_non_si_leggono():
    with patch.object(fw, "_costi_automatici_mese", return_value=None):
        assert fw._merce_del_mese("r", 2026, 9, _sb(), "u") is None


@pytest.mark.parametrize("merce_mese,atteso", [
    ({"netto": 386299.74, "merce": 100.0, "insufficiente": True}, False),
    ({"netto": 100000.0, "merce": 30000.0, "insufficiente": False}, True),
    ({"netto": 0.0, "merce": 500.0, "insufficiente": False}, True),
    ({"netto": 0.0, "merce": 0.0, "insufficiente": False}, False),
])
def test_voce_fatture_della_salute(merce_mese, atteso):
    assert fw._fatture_del_mese_ok(merce_mese) is atteso


# ── Catena ──────────────────────────────────────────────────────────────────

def test_catena_applica_la_stessa_regola_per_sede():
    righe = [
        {"ristorante_id": "a", "mese": 9, "fatturato_iva10": 424930.0, "altri_costi_fb": 100.0},
        {"ristorante_id": "b", "mese": 9, "fatturato_iva10": 110000.0},
        {"ristorante_id": "c", "mese": 9, "fatturato_iva10": 110000.0, "quote_riparto_fb": 20000.0},
    ]
    with patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": 0.0, "b": 30000.0, "c": 0.0}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_oggi_rome", return_value=date(2026, 10, 15)):
        out = gruppo._merce_ok_per_sede(_sb(righe), "u", ["a", "b", "c"], 2026, 9)
    assert out == {"a": False, "b": True, "c": True}


def test_catena_mese_in_corso_resta_sulla_merce_assente():
    righe = [{"ristorante_id": "a", "mese": 10, "fatturato_iva10": 110000.0}]
    with patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": 2000.0}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_oggi_rome", return_value=date(2026, 10, 15)):
        assert gruppo._merce_ok_per_sede(_sb(righe), "u", ["a"], 2026, 10) == {"a": True}


def test_completezza_e_indice_leggono_il_verdetto():
    rows = [{"ristorante_id": "a", "netto": 400000.0, "personale": 1.0, "n_fatture": 50, "n_needs_review": 0}]
    with patch.object(gruppo, "_voci_spente_per_sede", return_value={}):
        comp = gruppo._completezza_dati_pv(None, ["a"], rows=rows, costi_mese={"a": False})
        assert comp == {"a": ["le fatture costo"]}
        assert gruppo._completezza_dati_pv(None, ["a"], rows=rows, costi_mese={"a": True}) == {}
        senza = gruppo._salute_indici_batch(None, ["a"], rows=rows, costi_mese={"a": False})
        con = gruppo._salute_indici_batch(None, ["a"], rows=rows, costi_mese={"a": True})
    assert senza["a"] < con["a"]


# ── Margini: il worker decide, il frontend legge ────────────────────────────

def _pivot(**kw):
    base = {"anno": 2026, "mese": 3, "label": "Mar 2026", "fatturato_iva10": 0, "fatturato_iva22": 0,
            "altri_ricavi_noiva": 0, "fatturato_netto": 400000.0, "costi_fb_auto": 0, "altri_costi_fb": 0,
            "costi_fb_totali": 37777.0, "primo_margine": 0, "costi_spese_auto": 0, "altri_costi_spese": 0,
            "costi_spese_totali": 0, "costo_dipendenti": 0, "costo_personale_extra": 0,
            "costo_personale_chiamata": 0, "costi_personale": 0, "mol": 0,
            "quote_riparto_fb": 0, "quote_riparto_spese": 0}
    base.update(kw)
    return base


@pytest.mark.parametrize("campo,atteso", [(True, True), (False, False)])
def test_il_frontend_legge_il_verdetto_del_worker(campo, atteso):
    out = esegui_ts("lib/margini-aggregati", "emit(m.meseSenzaCosti(input));",
                    _pivot(senza_merce=campo), richiede=["meseSenzaCosti"])
    assert out is atteso


def test_il_frontend_senza_campo_ripiega_sulla_merce_assente():
    """Worker vecchio, nella finestra fra i due deploy: la regola di prima."""
    assert esegui_ts("lib/margini-aggregati", "emit(m.meseSenzaCosti(input));",
                     _pivot(), richiede=["meseSenzaCosti"]) is False
    assert esegui_ts("lib/margini-aggregati", "emit(m.meseSenzaCosti(input));",
                     _pivot(costi_fb_totali=0), richiede=["meseSenzaCosti"]) is True


# ── I collegamenti che i primi mutanti hanno trovato scoperti ───────────────

def test_merce_inserita_a_mano_completa_il_mese():
    with patch.object(fw, "_costi_automatici_mese", return_value=0.0), \
         patch.object(fw, "_load_mensile_overrides", return_value={}):
        out = fw._merce_del_mese("r", 2026, 9, _sb([{"fatturato_iva10": 110000.0, "altri_costi_fb": 30000.0}]), "u")
    assert out["insufficiente"] is False and out["merce"] == 30000.0


def test_chat_query_margini_sul_mese_in_corso_non_applica_la_percentuale():
    ottobre = {10: {"fatturato_iva10": 50000.0}}
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: ottobre if a == 2026 else {}),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: ({10: 2000.0}, {}) if a == 2026 else ({}, {})),
    ), patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 8)):
        mesi = fw._chat_query_margini({"id": "u"}, _sb(), None, ristorante_id="r")["mesi"]
    ottobre_out = next(r for r in mesi if r["mese"] == "ottobre 2026")
    assert ottobre_out["parziale"] is True and "dati_incompleti" not in ottobre_out


@pytest.mark.parametrize("insufficiente,rosso", [(True, True), (False, False)])
def test_salute_indice_rosso_legge_la_regola(insufficiente, rosso, monkeypatch):
    """Fatturato mancante (una voce gia' rossa): la voce fatture decide il colore."""
    import tests.test_salute_modalita_mensile as sm
    monkeypatch.setattr(fw, "_merce_del_mese", lambda *a, **k: {
        "netto": 100000.0, "merce": 100.0 if insufficiente else 30000.0, "insufficiente": insufficiente})
    assert fw._salute_indice_rosso(sm.RID, sm._sb([])) is rosso


@pytest.mark.parametrize("insufficiente,ok", [(True, False), (False, True)])
def test_home_salute_legge_la_regola(insufficiente, ok, monkeypatch):
    import tests.test_salute_percentuale_non_troncata as sp
    monkeypatch.setattr(fw, "_merce_del_mese", lambda *a, **k: {
        "netto": 386299.74, "merce": 100.0, "insufficiente": insufficiente})
    resp = sp._chiama_home_salute(monkeypatch, sp._fake_sb_con_cap(sp._righe(100, 0)))
    voce = next(v for v in resp.voci if v.key == "fatture")
    assert voce.ok is ok


def test_overview_di_catena_passa_il_verdetto_della_regola():
    import tests.test_catena_errore_non_diventa_tutto_ok as ce
    visti = []
    with patch.object(gruppo, "_merce_ok_per_sede", return_value={"a": False}) as merce_ok:
        with patch.object(gruppo, "_completezza_dati_pv",
                          side_effect=lambda *a, **k: visti.append(k.get("costi_mese")) or {}):
            sb = MagicMock()
            q = MagicMock()
            for m in ("select", "in_", "eq", "lte", "order", "limit"):
                getattr(q, m).return_value = q
            q.execute.return_value = MagicMock(data=[ce.RIGA_COMPLETA])
            sb.table.return_value = q
            sb.rpc.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
            with patch.object(gruppo, "_resolve_gruppo",
                              return_value=(sb, "u1", [{"id": "a"}], "Gruppo", {"a": "PV a"}, ["a"])), \
                 patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)), \
                 patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
                 patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                       return_value={"a": ({5: 4_000.0, 6: 4_000.0}, {})}), \
                 patch.object(gruppo, "_calcola_segnali", return_value=[]):
                gruppo.gruppo_overview(authorization="Bearer t")
    assert merce_ok.called
    assert {"a": False} in visti


def test_margine_calo_esclude_il_mese_chiuso_con_poca_merce():
    """M1 con merce al 10% esce all'80% di margine: se entrasse nella media
    precedente (80, 30, 30 → 46,7) il 28,6% di M4 sarebbe un calo di 18 punti.
    Senza M1 la media e' 30: 1,4 punti, sotto la soglia dei 3."""
    import tests.test_gruppo_segnale_margine_calo as mc
    righe = {mc.ANNO: [mc._mm("a", m, pers=1000.0) for m in mc.MESI]}
    costi = {mc.ANNO: {"a": ({mc.M1: 1000.0, mc.M2: 6000.0, mc.M3: 6000.0, mc.M4: 6140.0}, {})}}
    ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in mc.MESI}}
    assert mc._segnali(righe, costi, overrides=ovr) == []


# ── Secondo passo: «in attesa delle fatture di fine mese» ───────────────────

from services.completezza_mese import in_attesa_fine_mese


@pytest.mark.parametrize("netto,merce,dopo,in_corso,atteso", [
    (100000.0, 25000.0, 0.0, False, True),       # chiuso, merce giusta, niente dopo
    (100000.0, 25000.0, 300.0, False, False),    # e' arrivata merce del mese dopo
    (100000.0, 25000.0, None, False, False),     # non so: niente stato inventato
    (100000.0, 25000.0, 0.0, True, False),       # mese in corso: e' un altro caso
    (100000.0, 10000.0, 0.0, False, False),      # senza merce: e' giallo, non attesa
    (0.0, 25000.0, 0.0, False, False),           # senza incasso
])
def test_in_attesa(netto, merce, dopo, in_corso, atteso):
    assert in_attesa_fine_mese(netto, merce, dopo, in_corso=in_corso) is atteso


def _home_kpi_con(margini, fb, oggi=date(2026, 10, 15)):
    fw._HOME_KPI_CACHE.clear()
    try:
        with patch.multiple(
            "services.margine_service",
            carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: margini if a == 2026 else {}),
            calcola_costi_automatici_per_anno_sql=MagicMock(
                side_effect=lambda _u, _r, a: (fb, {}) if a == 2026 else ({}, {})),
        ), patch.object(fw, "_resolve_user_from_token", return_value={"id": "u"}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb()), \
             patch.object(fw, "_resolve_ristorante_id", return_value="r"), \
             patch.object(fw, "_oggi_rome", return_value=oggi):
            return fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()


SETTEMBRE_PIENO = {9: {"fatturato_iva10": 110000.0, "costo_dipendenti": 20000.0}}


def test_home_kpi_mese_chiuso_senza_merce_dopo_e_in_attesa():
    kpi = _home_kpi_con(SETTEMBRE_PIENO, {9: 25000.0})
    assert kpi.periodo_label == "Settembre"
    assert kpi.in_attesa is True and kpi.costi_mancanti is False


def test_home_kpi_mese_consolidato_non_e_in_attesa():
    kpi = _home_kpi_con(SETTEMBRE_PIENO, {9: 25000.0, 10: 800.0})
    assert kpi.in_attesa is False


def test_buona_notizia_tace_sul_mese_in_attesa():
    import tests.test_briefing_onesta_fatturato_zero as bo
    margini = {m: {"altri_ricavi_noiva": 40000.0 + m * 1000, "costo_dipendenti": 8000.0} for m in range(1, 13)}
    csp = {m: 1000.0 for m in range(1, 13)}
    consolidato = {m: 12000.0 for m in range(1, 13)}
    in_attesa = {m: 12000.0 for m in range(1, 9)}   # settembre (il mese dopo agosto) senza merce
    for cfb, attesa in ((consolidato, False), (in_attesa, True)):
        with bo._DENTRO_FINESTRA_MOL, bo._patch_loaders(margini, cfb, csp), patch(
            "services.fastapi_worker._salute_indice_rosso", return_value=False
        ):
            out = fw._briefing_buona_notizia(bo.UID, bo.RID, bo._sb_senza_incasso())
        assert (out is None) is attesa, (attesa, out)


def test_chat_query_margini_dichiara_il_mese_in_attesa():
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: SETTEMBRE_PIENO if a == 2026 else {}),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: ({9: 25000.0}, {}) if a == 2026 else ({}, {})),
    ), patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)):
        mesi = {r["mese"]: r for r in fw._chat_query_margini({"id": "u"}, _sb(), None, ristorante_id="r")["mesi"]}
    assert mesi["settembre 2026"]["in_attesa"] is True
    assert "possono cambiare" in mesi["settembre 2026"]["nota_attesa"]


def test_tinta_della_home_in_attesa_e_neutra():
    casi = [
        {"mol": 5000, "in_attesa": True},
        {"mol": 5000, "in_attesa": False},
        {"mol": -5000, "in_attesa": True},
        {"mol": 5000, "in_attesa": True, "costi_mancanti": True},
    ]
    out = esegui_ts("lib/catena-confronti", "emit(input.map(k => m.tintContiPV(k)));", casi,
                    richiede=["tintContiPV"])
    assert out == ["grigio", "verde", "rosso", "giallo"]


def test_cella_del_mese_in_attesa_senza_colore_ma_il_periodo_resta_giudicato():
    out = esegui_ts(
        "lib/margini-aggregati",
        "emit([m.meseSenzaGiudizio(input, 5000), m.meseSenzaGiudizio(input, -5000), m.meseSenzaCosti(input)]);",
        _pivot(senza_merce=False, in_attesa=True), richiede=["meseSenzaGiudizio", "meseSenzaCosti"])
    # positivo: neutro; negativo: resta rosso come in Home; il periodo resta giudicato
    assert out == [True, False, False]


def test_home_kpi_non_dice_in_attesa_su_un_mese_vecchio():
    """La card ripiega su giugno a ottobre (luglio-settembre vuoti): «in attesa
    delle fatture di fine giugno» non dice niente di vero."""
    giugno = {6: {"fatturato_iva10": 110000.0, "costo_dipendenti": 20000.0}}
    kpi = _home_kpi_con(giugno, {6: 25000.0})
    assert kpi.periodo_label == "Giugno" and kpi.in_attesa is False


def test_la_perdita_in_calo_tace_sul_mese_in_attesa():
    import tests.test_briefing_onesta_fatturato_zero as bo
    margini = {m: {"altri_ricavi_noiva": 40000.0, "costo_dipendenti": 30000.0 - m * 500} for m in range(1, 13)}
    csp = {m: 1000.0 for m in range(1, 13)}
    consolidato = {m: 14000.0 for m in range(1, 13)}
    in_attesa = {m: 14000.0 for m in range(1, 9)}
    esiti = {}
    for nome, cfb in (("consolidato", consolidato), ("in_attesa", in_attesa)):
        with bo._DENTRO_FINESTRA_MOL, bo._patch_loaders(margini, cfb, csp), patch(
            "services.fastapi_worker._salute_indice_rosso", return_value=False
        ):
            esiti[nome] = fw._briefing_buona_notizia(bo.UID, bo.RID, bo._sb_senza_incasso())
    assert esiti["consolidato"] is not None and esiti["consolidato"]["payload"]["tipo"] == "perdita_in_calo"
    assert esiti["in_attesa"] is None


def test_la_card_della_home_mostra_l_attesa():
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "apps/web/src/app/(app)/dashboard/kpi-block.tsx").read_text(encoding="utf-8")
    assert "{!kpi.costi_mancanti && kpi.in_attesa && (" in s
    assert "In attesa delle fatture di fine mese" in s
    assert "neutro={!molPos || !molAttendibile || kpi.in_attesa === true}" in s


def test_la_tabella_di_margini_colora_con_il_mese_senza_giudizio():
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "apps/web/src/app/(app)/margini/calcolo-tab.tsx").read_text(encoding="utf-8")
    assert "const colorCls = valueColorCls(row.valueColor, raw, meseSenzaGiudizio(mese, raw));" in s
    assert "const incompleto = isTotal ? mesi.some(meseSenzaCosti) : meseSenzaCosti(current);" in s
    assert "valueColorCls(row.valueColor, raw, incompleto || (!isTotal && meseSenzaGiudizio(current, raw)))" in s
    assert "() => mesiVisibili.some(meseSenzaCosti)," in s
