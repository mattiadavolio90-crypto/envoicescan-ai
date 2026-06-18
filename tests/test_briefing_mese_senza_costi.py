"""Test guardia: il mese CHIUSO con ricavi ma ZERO costi non e' una buona notizia.

Difetto osservato (LAND DEI SAPORI, 18/06): maggio aveva fatturato + personale
inseriti a mano ma NESSUNA fattura costo (food cost 0%, spese 0). La card Salute
era verde al 94% ("Fatture caricate" green, basata sul caricamento recente di
fatture datate marzo), il KPI mostrava un MOL gonfiato e il briefing festeggiava
"+172%" — un dato falso.

Fix coperto qui:
  - _kpi_periodo espone `costi_mancanti` (ricavi > 0 ma food + spese = 0).
  - _briefing_fatture_mancanti segnala 'mese_senza_costi' (caso B) PRIMA del caso
    pipeline-ferma, cosi' la voce rossa della Salute ha la sua notifica coerente.
  - La narrativa del briefing usa il testo dedicato al mese senza costi.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from services.fastapi_worker import _briefing_fatture_mancanti, _kpi_periodo
from services.daily_briefing_service import _bullet_for, _narrative_phrase_for

RID = "rist-land"


def _sb_multi(fatturato, fatture_count, user_id="u1", partita_iva=None):
    """Mock multi-tabella: ristoranti(.single), margini_mensili, fatture(count)."""
    sb = MagicMock()
    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        t = state["table"]
        if t == "ristoranti":
            return MagicMock(data={"partita_iva": partita_iva, "user_id": user_id})
        if t == "margini_mensili":
            rows = [{"fatturato_iva10": fatturato}] if fatturato else []
            return MagicMock(data=rows, count=None)
        return MagicMock(count=fatture_count,
                         data=[{"id": i} for i in range(fatture_count or 0)])

    q = MagicMock()
    sb.table.side_effect = _table
    for m in ("select", "eq", "is_", "gte", "limit", "single"):
        getattr(q, m).return_value = q
    q.execute.side_effect = _execute
    return sb


# ── _kpi_periodo: flag costi_mancanti ──

def test_kpi_costi_mancanti_true_con_ricavi_e_zero_costi():
    margini = {5: {"fatturato_iva10": 516152, "mol": 280924}}
    assert _kpi_periodo(margini, {}, {}, 5)["costi_mancanti"] is True


def test_kpi_costi_mancanti_false_con_food_presente():
    margini = {5: {"fatturato_iva10": 516152, "mol": 280924}}
    assert _kpi_periodo(margini, {5: 1000.0}, {}, 5)["costi_mancanti"] is False


def test_kpi_costi_mancanti_false_con_spese_presenti():
    margini = {5: {"fatturato_iva10": 516152, "mol": 280924}}
    assert _kpi_periodo(margini, {}, {5: 50.0}, 5)["costi_mancanti"] is False


def test_kpi_costi_mancanti_false_mese_vuoto():
    # Nessun ricavo: e' un mese non iniziato, non "costi mancanti".
    assert _kpi_periodo({}, {}, {}, 5)["costi_mancanti"] is False


# ── _briefing_fatture_mancanti: caso B (mese chiuso senza costi) ──

def test_mese_con_ricavi_senza_costi_genera_avviso(monkeypatch):
    monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: 0.0)
    # Ci sono fatture recenti (count=5): il caso A (pipeline ferma) NON scatterebbe.
    # L'avviso arriva quindi solo dal caso B.
    out = _briefing_fatture_mancanti(RID, _sb_multi(fatturato=516152, fatture_count=5))
    assert out is not None
    assert out["topic_key"] == "fatture_mancanti"
    assert out["payload"]["tipo"] == "mese_senza_costi"
    assert out["payload"]["mese"]
    assert "fatture costo" in out["title"].lower()


def test_mese_con_ricavi_e_costi_nessun_avviso(monkeypatch):
    monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: 1234.0)
    # Costi presenti + fatture recenti -> nessun buco.
    assert _briefing_fatture_mancanti(RID, _sb_multi(fatturato=516152, fatture_count=5)) is None


def test_mese_vuoto_non_chiama_rpc_costi(monkeypatch):
    chiamate = {"n": 0}

    def _spy(*a, **k):
        chiamate["n"] += 1
        return 0.0

    monkeypatch.setattr(fw, "_costi_automatici_mese", _spy)
    # Nessun fatturato nel mese: caso B saltato (niente RPC), caso A con fatture
    # recenti -> None.
    assert _briefing_fatture_mancanti(RID, _sb_multi(fatturato=0, fatture_count=5)) is None
    assert chiamate["n"] == 0


def test_rpc_indisponibile_ricade_su_caso_a(monkeypatch):
    # Se la fonte costi non e' determinabile (None), il caso B non scatta e si
    # valuta solo la pipeline: con fatture recenti -> None.
    monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: None)
    assert _briefing_fatture_mancanti(RID, _sb_multi(fatturato=516152, fatture_count=5)) is None


# ── Narrativa del briefing ──

def test_narrativa_mese_senza_costi():
    notif = {
        "topic_key": "fatture_mancanti",
        "title": "Mancano le fatture costo di maggio",
        "payload": {"tipo": "mese_senza_costi", "mese": "maggio"},
    }
    bullet = _bullet_for(notif)
    frase = _narrative_phrase_for(notif)
    assert "maggio" in bullet
    assert "food cost" in frase.lower()
    assert "maggio" in frase
