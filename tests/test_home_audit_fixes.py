"""Test guardia per i fix dell'audit Home (bug confermati dai due audit agent).

Copre:
- BUG #1/#3: il modello NotificaItem serializza payload e marca i segnali live
  come non archiviabili (dismissible=False), cosi' la X sparisce dalla UI e i
  trigger contestuali (contaTopicAttivo) leggono il count dal payload.
- BUG #2: coperti_anomalia, che compare in campanella, ora e' gestito anche dal
  briefing (azionabile + frase + azione), niente piu' divergenza campanella<->briefing.
"""
import services.fastapi_worker as fw
from services.daily_briefing_service import (
    _is_actionable, _action_for, _bullet_for, _TOPIC_PRIORITY,
)


# ── BUG #1/#3: payload + dismissible nel modello ──

def test_notifica_item_ha_payload_e_dismissible():
    n = fw.NotificaItem(id="x", title="t", payload={"count": 3}, dismissible=False)
    assert n.payload == {"count": 3}
    assert n.dismissible is False


def test_notifica_item_dismissible_default_true():
    # I record persistiti reali restano archiviabili per default.
    n = fw.NotificaItem(id="x", title="t")
    assert n.dismissible is True


def test_topic_live_sono_marcati_non_dismissibili():
    # I topic gestiti live non devono essere archiviabili (si chiudono da soli).
    for t in ("fatturato_mancante", "costo_personale_mancante", "uncategorized_rows",
              "fatture_mancanti", "incasso_mancante", "coperti_anomalia"):
        assert t in fw._LIVE_TOPICS_DATI_MANCANTI


# ── BUG #2: coperti_anomalia gestito nel briefing ──

def _notif_coperti():
    return {
        "topic_key": "coperti_anomalia",
        "severity": "warning",
        "title": "Ieri solo 40 coperti, 35% in meno della media della settimana scorsa",
        "payload": {"coperti": 40, "baseline": 62.0, "delta_pct": 35, "su": False},
    }


def test_coperti_anomalia_in_priority():
    assert "coperti_anomalia" in _TOPIC_PRIORITY


def test_coperti_anomalia_azionabile():
    assert _is_actionable(_notif_coperti()) is True


def test_coperti_anomalia_ha_azione_coperti():
    a = _action_for(_notif_coperti())
    assert a["cta_page"] == "/margini?tab=coperti"


def test_coperti_anomalia_bullet_usa_title():
    b = _bullet_for(_notif_coperti())
    assert "coperti" in b.lower()


# ── Perf #1: cache assistant_preferences condivisa (1 query, non N) ──

def test_assistant_preferences_cache_una_sola_query():
    from unittest.mock import MagicMock
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.return_value = MagicMock(data=[{"nome_referente": "X", "topics_disabled": []}])
    sb.table.return_value = q

    fw._invalidate_assist_pref_cache("rid-perf")
    fw._get_assistant_preferences("rid-perf", sb)
    fw._get_assistant_preferences("rid-perf", sb)  # seconda: deve venire dalla cache
    # Una sola execute() nonostante 2 chiamate ravvicinate.
    assert q.execute.call_count == 1


def test_assistant_preferences_invalidazione():
    from unittest.mock import MagicMock
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.return_value = MagicMock(data=[{"nome_referente": "X", "topics_disabled": []}])
    sb.table.return_value = q

    fw._invalidate_assist_pref_cache("rid-perf2")
    fw._get_assistant_preferences("rid-perf2", sb)
    fw._invalidate_assist_pref_cache("rid-perf2")
    fw._get_assistant_preferences("rid-perf2", sb)  # cache svuotata: rilegge
    assert q.execute.call_count == 2
