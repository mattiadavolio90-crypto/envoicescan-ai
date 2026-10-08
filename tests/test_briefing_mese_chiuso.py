"""Fase F del piano consulente (08/10/2026): il mese appena chiuso in una riga.

Mattia, screen 8: «briefing un po' scarno». Misura dell'8/10: i briefing reali
erano quasi solo dati mancanti; il mese chiuso si diceva solo se il MOL cresceva
(buona notizia, giorni 1-7). Ora nei primi 15 giorni una riga con food cost e
MOL del mese appena chiuso, «con le fatture arrivate finora» (al giorno 7 le
sedi SDI hanno il 96-100% della merce, CASATI 14 il 63-81%).

Solo nella Home del punto vendita: catena ed email settimanale chiamano
`_briefing_osservazioni`, che resta com'era.
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import services.daily_briefing_service as dbs
import services.fastapi_worker as fw

UID, RID = "u-f", "r-f"
INIZIO_OTTOBRE = date(2026, 10, 3)

# Netti 2026 di OVERTIME (misura dell'8/10), agosto aperto: nessun mese di ferie.
NETTI = {1: 28075.0, 2: 65771.0, 3: 37682.0, 4: 27178.0, 5: 34022.0,
         6: 27335.0, 7: 29106.0, 8: 29000.0, 9: 31285.0}
FB = {m: 9000.0 for m in range(1, 11)}


def _margini(personale=8000.0, settembre_netto=None):
    m = {k: {"altri_ricavi_noiva": v, "costo_dipendenti": personale,
             "altri_costi_spese": 2000.0} for k, v in NETTI.items()}
    if settembre_netto is not None:
        m[9]["altri_ricavi_noiva"] = settembre_netto
    return m


def _sb():
    q = MagicMock()
    q.table.return_value = q
    for n in ("select", "eq", "in_", "limit", "lt", "gte", "lte", "order", "is_", "not_"):
        getattr(q, n).return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


def _fonti(margini, fb=None, anno=2026):
    fb = FB if fb is None else fb
    return patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: margini if a == anno else {}),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: (fb, {}) if a == anno else ({}, {})),
    )


def _mese_chiuso(margini, oggi=INIZIO_OTTOBRE, fb=None, anno=2026):
    with _fonti(margini, fb, anno):
        return fw._briefing_mese_chiuso(UID, RID, _sb(), oggi)


# ── Il worker: quando c'e' e cosa porta ───────────────────────────────────

def test_settembre_a_inizio_ottobre():
    """31.285 netti, merce 9.000 (28,8%), personale 8.000, spese 2.000:
    MOL 12.285. Food cost in norma e MOL positivo: verso positivo."""
    rec = _mese_chiuso(_margini())
    assert rec["topic_key"] == "mese_chiuso"
    assert rec["payload"] == {"mese": "settembre", "anno": 2026,
                              "food_cost_pct": 28.8, "mol": 12285.0}
    assert rec["severity"] == "success"


@pytest.mark.parametrize("giorno,atteso", [(1, True), (15, True), (16, False), (30, False)])
def test_solo_nei_primi_quindici_giorni(giorno, atteso):
    assert (_mese_chiuso(_margini(), date(2026, 10, giorno)) is not None) is atteso


def test_gennaio_parla_di_dicembre_dell_anno_prima():
    margini = {12: {"altri_ricavi_noiva": 30000.0, "costo_dipendenti": 8000.0}}
    for m in range(6, 12):
        margini[m] = {"altri_ricavi_noiva": 30000.0}
    rec = _mese_chiuso(margini, date(2027, 1, 5), fb={12: 9000.0}, anno=2026)
    assert rec["payload"]["mese"] == "dicembre" and rec["payload"]["anno"] == 2026


def test_senza_personale_niente_mol():
    """Il MOL senza stipendi e' gonfiato: si dice solo il food cost, il
    personale lo chiede la riga dei dati mancanti."""
    rec = _mese_chiuso(_margini(personale=0.0))
    assert rec["payload"] == {"mese": "settembre", "anno": 2026, "food_cost_pct": 28.8}


def test_senza_merce_tace():
    """Food cost 0% non e' un food cost: la merce non e' ancora arrivata."""
    fb = dict(FB)
    fb[9] = 0.0
    assert _mese_chiuso(_margini(), fb=fb) is None


def test_senza_incasso_tace():
    assert _mese_chiuso(_margini(settembre_netto=0.0)) is None


def test_mese_di_ferie_tace():
    """Fase E: un settembre a 6.000 contro i ~29.000 dei mesi vicini e' una
    chiusura, il suo food cost (150%) non dice niente della cucina."""
    assert _mese_chiuso(_margini(settembre_netto=6000.0)) is None


def test_mese_normale_con_poca_merce_e_food_cost_alto_resta():
    """Controparte del test sopra: stesso locale, settembre normale ma con merce
    al 51%. Si dice, col verso negativo. Senza, il test delle ferie resterebbe
    verde con la riga sempre spenta."""
    fb = dict(FB)
    fb[9] = 16000.0
    rec = _mese_chiuso(_margini(), fb=fb)
    assert rec["payload"]["food_cost_pct"] == 51.1
    assert rec["severity"] == "warning"


def test_food_cost_al_limite_della_norma_e_positivo():
    """33% compreso e' norma (KPI_SOGLIE, `<=`)."""
    fb = dict(FB)
    fb[9] = 31285.0 * 0.33
    assert _mese_chiuso(_margini(), fb=fb)["severity"] == "success"


def test_merce_negativa_tace():
    """Note di credito piu' grandi degli acquisti del mese: «food cost -x%»
    non e' un food cost (revisore, 8/10)."""
    fb = dict(FB)
    fb[9] = -500.0
    assert _mese_chiuso(_margini(), fb=fb) is None


def test_mese_non_consolidato_non_regge_il_verde():
    """Nessuna merce di ottobre ancora: il food cost di settembre puo' essere
    piu' basso del vero (chi carica a mano), quindi verso negativo anche se e'
    in norma. Revisore, 8/10: un dato incompleto non regge «tutto in ordine»."""
    fb = dict(FB)
    fb[10] = 0.0
    rec = _mese_chiuso(_margini(), fb=fb)
    assert rec["payload"]["food_cost_pct"] == 28.8
    assert rec["severity"] == "warning"


def _dicembre(fb_gennaio):
    margini = {12: {"altri_ricavi_noiva": 30000.0, "costo_dipendenti": 8000.0}}
    for m in range(6, 12):
        margini[m] = {"altri_ricavi_noiva": 30000.0}
    fonti = {2026: (margini, {12: 9000.0}), 2027: ({}, fb_gennaio)}
    with patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(side_effect=lambda _u, _r, a: fonti.get(a, ({}, {}))[0]),
        calcola_costi_automatici_per_anno_sql=MagicMock(
            side_effect=lambda _u, _r, a: (fonti.get(a, ({}, {}))[1], {})),
    ):
        return fw._briefing_mese_chiuso(UID, RID, _sb(), date(2027, 1, 5))


def test_dicembre_si_consolida_con_la_merce_di_gennaio_dell_anno_dopo():
    assert _dicembre({1: 4000.0})["severity"] == "success"
    assert _dicembre({})["severity"] == "warning"


def test_sopra_la_norma_ma_sotto_il_critico_e_negativo():
    """35%: oltre la norma (33), sotto il critico (38). Il verso guarda la norma,
    come l'osservazione del food cost alto."""
    fb = dict(FB)
    fb[9] = 31285.0 * 0.35
    rec = _mese_chiuso(_margini(), fb=fb)
    assert rec["payload"]["food_cost_pct"] == 35.0
    assert rec["severity"] == "warning"


def test_mol_negativo_e_un_verso_negativo():
    rec = _mese_chiuso(_margini(personale=25000.0))
    assert rec["payload"]["mol"] == -4715.0
    assert rec["severity"] == "warning"


# ── Chi la calcola: solo il PV ────────────────────────────────────────────

def _oss_pv(spenti=(), settore="ristorazione", oggi=INIZIO_OTTOBRE):
    with _fonti(_margini()), patch("services.settore_service.settore_sede", return_value=settore):
        return fw._briefing_osservazioni_pv(UID, RID, _sb(), set(spenti), oggi)


def test_il_pv_la_calcola():
    assert [r["topic_key"] for r in _oss_pv()] == ["mese_chiuso"]


def test_spenta_dal_configuratore_non_si_calcola():
    with patch.object(fw, "_briefing_mese_chiuso") as calc:
        assert _oss_pv(spenti={"mese_chiuso"}) == []
    calc.assert_not_called()


def test_dopo_il_quindici_non_legge_niente():
    with patch.object(fw, "_briefing_mese_chiuso") as calc:
        assert _oss_pv(oggi=date(2026, 10, 16)) == []
    calc.assert_not_called()


def test_i_negozi_non_la_ricevono():
    """Regola 7: per un negozio il food cost non esiste."""
    assert _oss_pv(settore="retail") == []
    assert "mese_chiuso" in fw._TOPIC_OFF_PER_SETTORE["retail"]


def test_un_errore_non_rompe_il_briefing():
    with patch.object(fw, "_briefing_mese_chiuso", side_effect=RuntimeError("giu'")):
        assert _oss_pv() == []


def test_catena_ed_email_non_la_ricevono():
    """`_briefing_osservazioni` (catena ed email settimanale) resta com'era."""
    with _fonti(_margini()), patch("services.settore_service.settore_sede",
                                   return_value="ristorazione"):
        recs = fw._briefing_osservazioni(UID, RID, _sb(), set(), INIZIO_OTTOBRE)
    assert "mese_chiuso" not in [r["topic_key"] for r in recs]


def test_il_percorso_completo_del_pv_la_raccoglie():
    oss = {"topic_key": "mese_chiuso", "severity": "success", "payload": {}}
    with patch.object(fw, "_briefing_osservazioni_pv", return_value=[oss]) as pv, \
         patch.object(fw, "_briefing_osservazioni", return_value=[]), \
         patch.object(fw, "_get_assistant_preferences", return_value={}):
        out = fw._briefing_raccogli_notifiche(UID, RID, _sb(), includi_alert_prezzi=False,
                                             includi_osservazioni=True)
        assert oss in out
        pv.reset_mock()
        fw._briefing_raccogli_notifiche(UID, RID, _sb(), includi_alert_prezzi=False,
                                        includi_osservazioni=False)
    pv.assert_not_called()


def test_e_nel_configuratore():
    voci = {k: (lbl, bloccato) for (k, lbl, bloccato, _d) in fw._CONFIG_TOPICS}
    assert voci["mese_chiuso"] == ("Il mese appena chiuso", False)


# ── Il testo ──────────────────────────────────────────────────────────────

OSS_MESE = {
    "topic_key": "mese_chiuso", "severity": "success",
    "payload": {"mese": "settembre", "anno": 2026, "food_cost_pct": 28.8, "mol": 12285.0},
}


@pytest.mark.parametrize("payload,attesa", [
    ({"mese": "settembre", "food_cost_pct": 28.8, "mol": 12285.0},
     "📅 Settembre, con le fatture arrivate finora: food cost 28,8%, MOL di € 12.285."),
    ({"mese": "settembre", "food_cost_pct": 28.8, "mol": -4715.0},
     "📅 Settembre, con le fatture arrivate finora: food cost 28,8%, MOL negativo di € 4.715."),
    ({"mese": "agosto", "food_cost_pct": 41.0},
     "📅 Agosto, con le fatture arrivate finora: food cost 41,0%."),
])
def test_frase(payload, attesa):
    assert dbs._osservazione_frase({"topic_key": "mese_chiuso", "payload": payload}) == attesa


def test_entra_nel_briefing_e_tiene_il_verde():
    snap = dbs._build_snapshot([OSS_MESE])
    assert "food cost 28,8%, MOL di € 12.285" in snap["narrative"]
    assert snap["tutto_ok"] is True


def test_verso_negativo_spegne_il_verde():
    snap = dbs._build_snapshot([dict(OSS_MESE, severity="warning")])
    assert snap["tutto_ok"] is False


def test_spenta_dal_configuratore_non_si_dice():
    snap = dbs._build_snapshot([OSS_MESE], topics_disabled=["mese_chiuso"])
    assert "Settembre" not in snap["narrative"]


def _buona(tipo, mese):
    return {"topic_key": "buona_notizia", "severity": "success",
            "payload": {"tipo": tipo, "mese": mese, "mol": 12285, "delta_pct": 8.0,
                        "mese_prec": "agosto", "perdita": 100, "perdita_prec": 200}}


@pytest.mark.parametrize("tipo", ["mol_mese", "perdita_in_calo"])
def test_il_mol_dello_stesso_mese_lo_dice_la_buona_notizia(tipo):
    """§5.1: chi possiede un'informazione la dice una volta sola."""
    snap = dbs._build_snapshot([_buona(tipo, "settembre"), OSS_MESE])
    assert "food cost 28,8%." in snap["narrative"]
    assert "MOL di € 12.285" not in snap["narrative"].split("con le fatture arrivate finora")[1]


def test_la_buona_notizia_di_un_altro_mese_non_toglie_il_mol():
    snap = dbs._build_snapshot([_buona("mol_mese", "agosto"), OSS_MESE])
    assert "food cost 28,8%, MOL di € 12.285" in snap["narrative"]


def test_l_incasso_di_ieri_non_toglie_il_mol():
    buona = {"topic_key": "buona_notizia", "severity": "success",
             "payload": {"tipo": "incasso_ieri", "incasso": 500, "giorno_settimana": "martedì"}}
    snap = dbs._build_snapshot([buona, OSS_MESE])
    assert "food cost 28,8%, MOL di € 12.285" in snap["narrative"]


def test_numeri_che_l_ai_non_puo_perdere():
    assert set(dbs._numeri_obbligatori([OSS_MESE])) >= dbs._numeri_di("28,8") | dbs._numeri_di("12.285")
    senza_mol = {**OSS_MESE, "payload": {"mese": "settembre", "food_cost_pct": 28.8}}
    assert set(dbs._numeri_obbligatori([senza_mol])) == dbs._numeri_di("28,8")


# ── La narrativa AI non puo' togliere «finora» ────────────────────────────
# Col solo prompt il modello vero la toglieva 6 volte su 6 (8/10/2026): il
# food cost di un mese ancora incompleto diventava un dato definitivo.

def test_validatore_scarta_il_testo_senza_finora():
    bullets = [dbs._osservazione_frase(OSS_MESE)]
    senza = "A settembre il food cost è stato del 28,8% e il MOL è di € 12.285."
    con = "A settembre, con le fatture arrivate finora, il food cost è al 28,8% e il MOL è di € 12.285."
    assert dbs._narrazione_e_valida(senza, bullets, parole=["finora"])[0] is False
    assert dbs._narrazione_e_valida(con, bullets, parole=["finora"]) == (True, "")


def test_finora_si_pretende_solo_con_la_riga_del_mese_chiuso():
    oss_fc = {"topic_key": "food_cost_alto", "payload": {"food_cost_pct": 45.8}}
    assert dbs._parole_obbligatorie([OSS_MESE]) == ["finora"]
    assert dbs._parole_obbligatorie([oss_fc]) == []
    assert dbs._parole_obbligatorie([]) == []


def test_il_briefing_passa_la_parola_al_narratore():
    with patch.object(dbs, "_narrate_with_ai", return_value="ok") as narra:
        dbs._build_snapshot([OSS_MESE], use_ai=True)
    assert narra.call_args.args[3] == ["finora"]


def _narra_col_modello_finto(testo):
    risposta = MagicMock()
    risposta.choices = [MagicMock(finish_reason="stop", message=MagicMock(content=testo))]
    risposta.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    client = MagicMock()
    client.chat.completions.create.return_value = risposta
    with patch("services.ai_service._get_openai_client", return_value=client), \
         patch("services.ai_cost_service.track_ai_usage"):
        snap = dbs._build_snapshot([OSS_MESE], use_ai=True)
    client.chat.completions.create.assert_called_once()
    return snap["narrative"]


def test_narratore_torna_al_template_se_il_modello_toglie_finora():
    """Il percorso intero, col modello finto che risponde senza «finora»."""
    out = _narra_col_modello_finto("A settembre il food cost è al 28,8% e il MOL è di € 12.285.")
    assert out.startswith(dbs._osservazione_frase(OSS_MESE))


def test_narratore_tiene_il_testo_del_modello_se_dice_finora():
    """Controparte: senza, il test sopra resterebbe verde anche col narratore
    che torna sempre al template."""
    testo = "A settembre, con le fatture arrivate finora, il food cost è al 28,8% e il MOL è di € 12.285."
    assert _narra_col_modello_finto(testo) == testo
