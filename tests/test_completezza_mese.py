"""Una sola regola per «il mese ha la merce che serve per giudicarne i conti».

Perche' esiste
==============
Audit di ottobre 2026 (K03): 100 EUR inseriti a mano su 386.300 EUR di incasso
netto bastavano a dichiarare completo un mese senza una fattura (MOL verde,
food cost 0%), e la regola «merce > 0» era ricopiata in sette punti, uno dei
quali (la catena) gia' divergeva. Decisione di Mattia del 16/10/2026, misurata
sui 73 mesi chiusi del live e rivista la sera: meno del 20% del netto = senza
merce (giallo); fatture di merce ma nessuna negli ultimi 5 giorni del mese = in
attesa (grigio); il mese in corso resta sulla merce assente. Qui la regola e
ogni punto che deve usarla.
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
    (100000.0, 19999.0, True),       # sotto il 20%
    (100000.0, 20000.0, False),      # al 20%
    (100000.0, 15000.0, True),       # il 15% della prima stesura: ora giallo
    (73323.0, 13059.0, True),        # il bar reale al 17,8%: il costo noto del 20%
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
    from services.completezza_mese import GIORNI_FINE_MESE
    assert SOGLIA_MERCE_SU_NETTO == 0.20 and GIORNI_FINE_MESE == 5


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
    for m in ("select", "eq", "neq", "or_", "in_", "limit", "lt", "gt", "gte", "lte", "order", "is_", "not_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=margini_rows or [])
    return q


@pytest.mark.parametrize("auto,riga,atteso", [
    (0.0, {"fatturato_iva10": 424930.0, "altri_costi_fb": 100.0}, True),     # K03: 100 a mano
    (19000.0, {"fatturato_iva10": 110000.0}, True),                          # 19% del netto
    (21000.0, {"fatturato_iva10": 110000.0}, False),                         # 21%
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
    with patch.object(fw, "_costi_automatici_mese", return_value=16000.0), \
         patch.object(fw, "_load_mensile_overrides", return_value=ov):
        out = fw._merce_del_mese("r", 2026, 6, _sb([{"fatturato_iva10": 3549.7}]), "u")
    # 16.000 su 73.323 (21,8%) e' completo; sul netto dello snapshot (3.227) lo sarebbe comunque,
    # ma il netto letto dev'essere quello dell'override
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
#
# Decisione di Mattia (16/10/2026, sera): in attesa = mese chiuso sopra soglia,
# con fatture di merce ma nessuna datata negli ultimi 5 giorni del mese.

from services.completezza_mese import in_attesa_fine_mese, inizio_fine_mese


@pytest.mark.parametrize("anno,mese,atteso", [
    (2026, 9, date(2026, 9, 25)), (2026, 10, date(2026, 10, 26)), (2026, 2, date(2026, 2, 23)),
    (2028, 2, date(2028, 2, 24)),
])
def test_inizio_della_fine_mese(anno, mese, atteso):
    assert inizio_fine_mese(anno, mese) == atteso


@pytest.mark.parametrize("netto,merce,fatture,coperta,in_corso,atteso", [
    (100000.0, 25000.0, 25000.0, False, False, True),    # niente fatture di fine mese
    (100000.0, 25000.0, 25000.0, True, False, False),    # fine mese coperta
    (100000.0, 25000.0, 25000.0, None, False, False),    # non so: niente stato inventato
    (100000.0, 25000.0, 25000.0, False, True, False),    # mese in corso: e' un altro caso
    (100000.0, 15000.0, 15000.0, False, False, False),   # sotto il 20%: e' giallo, non attesa
    (100000.0, 25000.0, 0.0, False, False, False),       # merce a mano o quote: nessuna data
    (0.0, 25000.0, 25000.0, False, False, False),        # senza incasso
])
def test_in_attesa(netto, merce, fatture, coperta, in_corso, atteso):
    assert in_attesa_fine_mese(netto, merce, merce_fatture=fatture,
                               fine_mese_coperta=coperta, in_corso=in_corso) is atteso


@pytest.mark.parametrize("righe,atteso", [
    ([{"categoria": "CARNE", "totale_riga": 120.0}], True),
    ([{"categoria": "UTENZE E LOCALI", "totale_riga": 300.0}], False),        # spese, non merce
    ([{"categoria": "📝 NOTE E DICITURE", "totale_riga": 0.0}], False),
    ([{"categoria": "CARNE", "totale_riga": -50.0}], False),                  # nota di credito
    ([], False),
])
def test_fine_mese_coperta_legge_solo_la_merce(righe, atteso):
    sb = _sb(righe)
    assert fw._fine_mese_coperta(sb, "r", 2026, 9) is atteso
    sb.gte.assert_any_call("data_documento", "2026-09-25")


def test_fine_mese_coperta_non_sa_se_la_lettura_fallisce():
    sb = _sb()
    sb.execute.side_effect = RuntimeError("timeout")
    assert fw._fine_mese_coperta(sb, "r", 2026, 9) is None


def _home_kpi_con(margini, fb, coperta, oggi=date(2026, 10, 15)):
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
             patch.object(fw, "_fine_mese_coperta", return_value=coperta), \
             patch.object(fw, "_oggi_rome", return_value=oggi):
            return fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()


SETTEMBRE_PIENO = {9: {"fatturato_iva10": 110000.0, "costo_dipendenti": 20000.0}}


def test_home_kpi_mese_senza_fatture_di_fine_mese_e_in_attesa():
    kpi = _home_kpi_con(SETTEMBRE_PIENO, {9: 25000.0}, coperta=False)
    assert kpi.periodo_label == "Settembre"
    assert kpi.in_attesa is True and kpi.costi_mancanti is False


def test_home_kpi_mese_con_la_fine_coperta_non_e_in_attesa():
    assert _home_kpi_con(SETTEMBRE_PIENO, {9: 25000.0}, coperta=True).in_attesa is False


def test_home_kpi_merce_tutta_a_mano_non_e_in_attesa():
    """Nessuna fattura, merce inserita a mano: non c'e' una data da aspettare."""
    a_mano = {9: {"fatturato_iva10": 110000.0, "altri_costi_fb": 25000.0, "costo_dipendenti": 20000.0}}
    assert _home_kpi_con(a_mano, {}, coperta=False).in_attesa is False


def _buona_notizia(margini, cfb, csp, coperta):
    import tests.test_briefing_onesta_fatturato_zero as bo
    with bo._DENTRO_FINESTRA_MOL, bo._patch_loaders(margini, cfb, csp), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ), patch.object(fw, "_fine_mese_coperta", return_value=coperta):
        return fw._briefing_buona_notizia(bo.UID, bo.RID, bo._sb_senza_incasso())


def test_buona_notizia_tace_sul_mese_in_attesa():
    margini = {m: {"altri_ricavi_noiva": 40000.0 + m * 1000, "costo_dipendenti": 8000.0} for m in range(1, 13)}
    csp = {m: 1000.0 for m in range(1, 13)}
    cfb = {m: 12000.0 for m in range(1, 13)}
    assert _buona_notizia(margini, cfb, csp, coperta=True) is not None
    assert _buona_notizia(margini, cfb, csp, coperta=False) is None


def test_chat_query_margini_dichiara_il_mese_in_attesa():
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: SETTEMBRE_PIENO if a == 2026 else {}),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: ({9: 25000.0}, {}) if a == 2026 else ({}, {})),
    ), patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)), \
         patch.object(fw, "_fine_mese_coperta", side_effect=lambda _sb, _r, a, m: (a, m) != (2026, 9)):
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


def test_la_perdita_in_calo_tace_sul_mese_in_attesa():
    margini = {m: {"altri_ricavi_noiva": 40000.0, "costo_dipendenti": 30000.0 - m * 500} for m in range(1, 13)}
    csp = {m: 1000.0 for m in range(1, 13)}
    cfb = {m: 14000.0 for m in range(1, 13)}
    coperto = _buona_notizia(margini, cfb, csp, coperta=True)
    assert coperto is not None and coperto["payload"]["tipo"] == "perdita_in_calo"
    assert _buona_notizia(margini, cfb, csp, coperta=False) is None


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


def test_il_caricamento_dei_costi_riconosce_la_fine_mese():
    """Le righe sono gia' quelle dei costi di Margini: la data dell'ultima fattura
    si ricava li', senza query in piu'. Conta la data del documento, cosi' una
    fattura differita del 3 ottobre con competenza a settembre copre settembre."""
    righe = [
        {"categoria": "CARNE", "totale_riga": 100.0, "data_documento": "2026-08-20", "data_competenza": None},
        {"categoria": "UTENZE E LOCALI", "totale_riga": 300.0, "data_documento": "2026-08-30", "data_competenza": None},
        {"categoria": "CARNE", "totale_riga": 80.0, "data_documento": "2026-10-03", "data_competenza": "2026-09-01"},
        {"categoria": "PESCE", "totale_riga": 90.0, "data_documento": "2026-07-27", "data_competenza": None},
    ]
    q = MagicMock()
    for m in ("table", "select", "eq", "neq", "or_", "is_", "range", "order", "not_", "in_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=righe)
    fine = {}
    costi = fw._calcola_costi_auto_per_periodo(q, "r", [(2026, 7), (2026, 8), (2026, 9)], fine_mese=fine)
    assert fine == {(2026, 9): True, (2026, 7): True}
    assert costi[(2026, 8)] == (100.0, 300.0)


# ── I rilievi del revisore sulla regola rivista ─────────────────────────────

def test_home_kpi_non_dice_in_attesa_su_un_mese_vecchio():
    """La card ripiega su giugno a ottobre (luglio-settembre vuoti): l'attesa
    vale solo sul mese appena chiuso, giugno non resta grigio per sempre."""
    giugno = {6: {"fatturato_iva10": 110000.0, "costo_dipendenti": 20000.0}}
    kpi = _home_kpi_con(giugno, {6: 25000.0}, coperta=False)
    assert kpi.periodo_label == "Giugno" and kpi.in_attesa is False


def test_home_e_briefing_chiedono_la_data_del_mese_giusto():
    chiesti = []
    fw._HOME_KPI_CACHE.clear()
    try:
        with patch.multiple(
            "services.margine_service",
            carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: SETTEMBRE_PIENO if a == 2026 else {}),
            calcola_costi_automatici_per_anno_sql=MagicMock(
                side_effect=lambda _u, _r, a: ({9: 25000.0}, {}) if a == 2026 else ({}, {})),
        ), patch.object(fw, "_resolve_user_from_token", return_value={"id": "u"}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb()), \
             patch.object(fw, "_resolve_ristorante_id", return_value="r"), \
             patch.object(fw, "_fine_mese_coperta", side_effect=lambda _sb, _r, a, m: chiesti.append((a, m)) or True), \
             patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)):
            fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()
    assert chiesti == [(2026, 9)]


def test_la_data_si_chiede_solo_quando_serve():
    """Sotto soglia, senza incasso o senza fatture di merce la risposta e' gia'
    no: niente query (la chat ne farebbe fino a sei per domanda)."""
    with patch.object(fw, "_fine_mese_coperta", side_effect=AssertionError("query inutile")):
        assert fw._mese_in_attesa({"netto": 100000.0, "merce": 10000.0, "costi_mancanti": True},
                                  10000.0, None, "r", 2026, 9) is False
        assert fw._mese_in_attesa({"netto": 0.0, "merce": 0.0}, 0.0, None, "r", 2026, 9) is False
        assert fw._mese_in_attesa({"netto": 100000.0, "merce": 25000.0}, 0.0, None, "r", 2026, 9) is False
    with patch.object(fw, "_fine_mese_coperta", return_value=False):
        assert fw._mese_in_attesa({"netto": 100000.0, "merce": 25000.0}, 25000.0, None, "r", 2026, 9) is True


def test_fine_mese_coperta_applica_i_filtri_dei_costi():
    sb = _sb([{"categoria": "CARNE", "totale_riga": 120.0}])
    fw._fine_mese_coperta(sb, "r", 2026, 9)
    sb.eq.assert_any_call("ristorante_id", "r")
    sb.eq.assert_any_call("oscurata", False)
    sb.is_.assert_any_call("deleted_at", "null")
    sb.neq.assert_any_call("categoria", "Da Classificare")
    sb.neq.assert_any_call("ripartita_su_gruppo", True)
    sb.gt.assert_any_call("totale_riga", 0)
    filtro = sb.or_.call_args.args[0]
    assert "data_competenza.gte.2026-09-01" in filtro and "data_competenza.lte.2026-09-30" in filtro
    assert "data_competenza.is.null,data_documento.lte.2026-09-30" in filtro


def test_il_caricamento_dei_costi_pagina_con_un_ordine_fisso():
    q = MagicMock()
    for m in ("table", "select", "eq", "neq", "or_", "is_", "range", "order", "not_", "in_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    fw._calcola_costi_auto_per_periodo(q, "r", [(2026, 9)])
    q.order.assert_any_call("id")


def test_la_chat_dice_l_attesa_solo_sul_mese_appena_chiuso():
    margini = {m: {"fatturato_iva10": 110000.0, "costo_dipendenti": 20000.0} for m in (7, 8, 9)}
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: margini if a == 2026 else {}),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: ({7: 25000.0, 8: 25000.0, 9: 25000.0}, {}) if a == 2026 else ({}, {})),
    ), patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)), \
         patch.object(fw, "_fine_mese_coperta", return_value=False):
        mesi = {r["mese"]: r for r in fw._chat_query_margini({"id": "u"}, _sb(), None, ristorante_id="r")["mesi"]}
    assert mesi["settembre 2026"].get("in_attesa") is True
    assert "in_attesa" not in mesi["agosto 2026"] and "in_attesa" not in mesi["luglio 2026"]


@pytest.mark.parametrize("oggi,anno,mese,atteso", [
    (date(2027, 1, 5), 2026, 12, True),     # a gennaio il mese chiuso e' dicembre dell'anno prima
    (date(2027, 1, 5), 2027, 12, False),
    (date(2026, 10, 15), 2026, 9, True),
    (date(2026, 10, 15), 2026, 8, False),
])
def test_ultimo_mese_chiuso(oggi, anno, mese, atteso):
    assert fw._e_l_ultimo_mese_chiuso(anno, mese, oggi) is atteso


def test_il_briefing_non_festeggia_un_dato_non_letto():
    """Lettura delle date fallita (None): la Home non mostra un grigio inventato,
    il briefing non da' il verde."""
    kpi = {"netto": 100000.0, "merce": 25000.0}
    with patch.object(fw, "_fine_mese_coperta", return_value=None):
        assert fw._mese_in_attesa(kpi, 25000.0, None, "r", 2026, 9) is False
        assert fw._mese_consolidato(kpi, 25000.0, None, "r", 2026, 9) is False
    with patch.object(fw, "_fine_mese_coperta", return_value=True):
        assert fw._mese_consolidato(kpi, 25000.0, None, "r", 2026, 9) is True
    with patch.object(fw, "_fine_mese_coperta", side_effect=AssertionError("query inutile")):
        assert fw._mese_consolidato(kpi, 0.0, None, "r", 2026, 9) is True      # merce a mano
        assert fw._mese_consolidato({"netto": 100000.0, "merce": 10000.0}, 10000.0, None, "r", 2026, 9) is True


def test_la_buona_notizia_tace_se_la_data_non_si_legge():
    margini = {m: {"altri_ricavi_noiva": 40000.0 + m * 1000, "costo_dipendenti": 8000.0} for m in range(1, 13)}
    csp = {m: 1000.0 for m in range(1, 13)}
    cfb = {m: 12000.0 for m in range(1, 13)}
    assert _buona_notizia(margini, cfb, csp, coperta=None) is None


# ── K10: la card MOL di Margini ─────────────────────────────────────────────

def test_l_aggregato_dei_kpi_conta_i_mesi_senza_merce():
    """Gennaio al 24,8% di merce, febbraio al 4%: un mese senza merce nel periodo.
    Il mese in corso con poca merce non conta (resta su «nessuna merce»)."""
    import tests.test_aggrega_margini_periodo as am
    fatture = [
        am._fattura(am.CAT_FB, 3000.0, "2026-01-10", competenza=None),
        am._fattura(am.CAT_FB, 500.0, "2026-02-10", competenza=None),
        am._fattura(am.CAT_FB, 200.0, "2026-10-03", competenza=None),
    ]
    margini = [am._margini(2026, 1, i10=13310.0), am._margini(2026, 2, i10=13310.0),
               am._margini(2026, 10, i10=13310.0)]
    with patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 15)):
        tot = fw._aggrega_mensili_margini(
            am._FakeSB(fatture=fatture, margini=margini, modalita=[]), am.RID,
            date(2026, 1, 1), date(2026, 2, 28))
        tot_con_ottobre = fw._aggrega_mensili_margini(
            am._FakeSB(fatture=fatture, margini=margini, modalita=[]), am.RID,
            date(2026, 10, 1), date(2026, 10, 31))
    assert tot["mesi_senza_merce"] == 1
    assert tot_con_ottobre["mesi_senza_merce"] == 0


@pytest.mark.parametrize("kpi,atteso", [
    ({"mol": 5000, "mesi_senza_merce": 0}, "positivo"),
    ({"mol": 5000, "mesi_senza_merce": 2}, "neutro"),
    ({"mol": -5000, "mesi_senza_merce": 2}, "negativo"),
    ({"mol": 5000}, "positivo"),          # worker vecchio: come prima
])
def test_tono_della_card_mol(kpi, atteso):
    out = esegui_ts("lib/kpi-margini-tab", "emit(m.toneMol(input));", kpi, richiede=["toneMol"])
    assert out == atteso


def test_la_card_mol_usa_il_tono_della_regola():
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "apps/web/src/app/(app)/margini/kpi-bar.tsx").read_text(encoding="utf-8")
    assert "const molTone: Tone = toneMol(kpi);" in s
    assert "kpi.mol >= 0 ? \"positivo\"" not in s


def test_l_endpoint_dei_kpi_manda_i_mesi_senza_merce():
    from services.routers import margini
    cur = {"lordo": 100.0, "netto": 100.0, "fb": 1.0, "pm": 99.0, "spese": 0.0, "pers": 0.0,
           "mol": 99.0, "mesi_attivi": 1, "mesi_senza_merce": 1,
           **{k: [] for k in ("spark_lordo", "spark_fb", "spark_margine", "spark_spese",
                              "spark_personale", "spark_mol")}}
    with patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "u"}),
        _get_supabase_client=MagicMock(return_value=_sb()),
        _resolve_ristorante_id=MagicMock(return_value="r"),
        _aggrega_mensili_margini=MagicMock(return_value=cur),
    ):
        resp = margini.get_margini_kpi("2026-09-01", "2026-09-30", authorization="Bearer t")
    assert resp.mesi_senza_merce == 1


# ── K13: la Home di una sede ferma ──────────────────────────────────────────

def _home_kpi_spese(margini, fb, spese, oggi=date(2026, 10, 15)):
    fw._HOME_KPI_CACHE.clear()
    try:
        with patch.multiple(
            "services.margine_service",
            carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: margini if a == 2026 else {}),
            calcola_costi_automatici_per_anno_sql=MagicMock(
                side_effect=lambda _u, _r, a: (fb, spese) if a == 2026 else ({}, {})),
        ), patch.object(fw, "_resolve_user_from_token", return_value={"id": "u"}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb()), \
             patch.object(fw, "_resolve_ristorante_id", return_value="r"), \
             patch.object(fw, "_fine_mese_coperta", return_value=True), \
             patch.object(fw, "_oggi_rome", return_value=oggi):
            return fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()


def test_un_mese_di_sole_spese_non_fa_da_ultima_fotografia():
    """Il caso misurato: giugno pieno, luglio solo 89 EUR di spese, agosto e
    settembre vuoti. La card mostra giugno, non «Luglio, MOL -89»."""
    margini = {6: {"fatturato_iva10": 80655.0, "costo_dipendenti": 20080.0}}
    kpi = _home_kpi_spese(margini, {6: 13058.88}, {6: 4180.61, 7: 89.08})
    assert kpi.periodo_label == "Giugno" and kpi.incasso_mancante is False
    assert kpi.mol > 0


def test_senza_incasso_in_sei_mesi_lo_dichiara():
    """La sede che non ha mai inserito incassi: si mostra agosto, ma dichiarato,
    senza variazioni (con luglio di sole spese la freccia direbbe -97,9% verde)."""
    kpi = _home_kpi_spese({}, {8: 234.33}, {7: 4000.0, 8: 460.43})
    assert kpi.periodo_label == "Agosto" and kpi.incasso_mancante is True
    assert all(getattr(kpi, k) is None for k in (
        "fatturato_delta_pct", "food_cost_delta_pp", "personale_delta_pct",
        "spese_delta_pct", "mol_delta_pct"))


def test_la_linea_del_mol_salta_i_mesi_senza_incasso():
    margini = {m: {"fatturato_iva10": 55000.0, "costo_dipendenti": 15000.0} for m in (1, 2, 4)}
    fb = {1: 14000.0, 2: 14000.0, 4: 14000.0}
    kpi = _home_kpi_spese(margini, fb, {3: 89.0}, oggi=date(2026, 5, 10))
    assert [p.mese for p in kpi.mol_mensile] == [1, 2, 4]


def test_tinta_della_home_senza_incasso_e_gialla():
    out = esegui_ts("lib/catena-confronti", "emit(m.tintContiPV(input));",
                    {"mol": -694.76, "incasso_mancante": True}, richiede=["tintContiPV"])
    assert out == "giallo"


def test_la_card_della_home_dice_che_manca_l_incasso():
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "apps/web/src/app/(app)/dashboard/kpi-block.tsx").read_text(encoding="utf-8")
    assert "{kpi.incasso_mancante && (" in s
    assert "il MOL qui sopra è solo la" in s


# ── F1a-02: la fattura ripartita nella sede che la ospita ───────────────────

def test_analisi_fatture_toglie_la_fattura_intera_quando_c_e_la_sua_quota():
    """La sede che ospita una fattura ripartita la riceve come quota: le righe
    intere non restano accanto (456,30 + 114,08 a gennaio 2026, audit F1a-02)."""
    righe = [
        {"id": 1, "file_origine": "a.xml", "categoria": "CARNE", "totale_riga": 100.0, "ripartita_su_gruppo": False},
        {"id": 2, "file_origine": "rip.xml", "categoria": "UTENZE E LOCALI", "totale_riga": 451.3, "ripartita_su_gruppo": True},
    ]
    quota = [{"id": "q1", "file_origine": "rip.xml", "categoria": "UTENZE E LOCALI", "totale_riga": 112.83}]
    q = MagicMock()
    for m in ("table", "select", "eq", "is_", "gte", "lte", "or_", "order", "range"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=righe)
    fw._FATTURE_ROWS_CACHE.clear()
    try:
        with patch.object(fw, "_ristorante_quote_meta", return_value=("u", True)), \
             patch("services.riparto_service.righe_ripartite_proiettate", return_value=quota):
            out = fw._fetch_fatture_rows(q, "pv-1", "2026-01-01", "2026-01-31")
    finally:
        fw._FATTURE_ROWS_CACHE.clear()
    assert sorted(str(r["id"]) for r in out) == ["1", "q1"]


def test_senza_quote_la_fattura_ripartita_resta():
    righe = [{"id": 2, "file_origine": "rip.xml", "categoria": "UTENZE E LOCALI", "totale_riga": 451.3, "ripartita_su_gruppo": True}]
    q = MagicMock()
    for m in ("table", "select", "eq", "is_", "gte", "lte", "or_", "order", "range"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=righe)
    fw._FATTURE_ROWS_CACHE.clear()
    try:
        with patch.object(fw, "_ristorante_quote_meta", return_value=("u", False)):
            out = fw._fetch_fatture_rows(q, "pv-1", "2026-01-01", "2026-01-31")
    finally:
        fw._FATTURE_ROWS_CACHE.clear()
    assert [r["id"] for r in out] == [2]


# ── Etichette che dicevano due cose con una parola (audit #16, #34, #35, #39) ─

def test_salute_dice_quanti_prodotti_sono_fuori_dai_margini():
    assert fw._dettaglio_righe_classificate(89, 6743, 37) == (
        "89 prodotti da controllare, di cui 37 senza categoria (fuori dai margini)")
    assert fw._dettaglio_righe_classificate(89, 6743) == "89 prodotti da controllare"


def test_home_salute_conta_i_prodotti_senza_categoria(monkeypatch):
    import tests.test_salute_percentuale_non_troncata as sp
    monkeypatch.setattr(fw, "_merce_del_mese", lambda *a, **k: None)
    resp = sp._chiama_home_salute(monkeypatch, sp._fake_sb_con_cap(sp._righe(40, 12)))
    voce = next(v for v in resp.voci if v.key == "classificate")
    # Il finto client non filtra `needs_review`: tutte e 40 le voci contano come da
    # controllare, le 12 «Da Classificare» sono quelle senza categoria.
    assert voce.dettaglio == "40 prodotti da controllare, di cui 12 senza categoria (fuori dai margini)"


@pytest.mark.parametrize("percorso,deve,non_deve", [
    ("apps/web/src/app/(app)/dashboard/kpi-block.tsx", 'label="Fatturato (IVA incl.)"', 'label="Fatturato"'),
    ("apps/web/src/app/(app)/analisi-e-tag/analisi-e-tag-client.tsx", "Media dei prezzi giornalieri:", "Media periodo:"),
    ("apps/web/src/app/(app)/analisi-fatture/kpi-bar.tsx",
     "Per data della fattura. Non comprende i costi inseriti a mano in Margini.", None),
])
def test_le_etichette_dicono_la_base(percorso, deve, non_deve):
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / percorso).read_text(encoding="utf-8")
    assert deve in s
    if non_deve:
        assert non_deve not in s
