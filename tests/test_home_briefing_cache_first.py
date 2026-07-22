"""Test fast-path cache-first dell'endpoint home_briefing (services.fastapi_worker).

Difetto: il briefing e' un dato giornaliero ma veniva RICALCOLATO ad ogni
apertura della Home — incluso l'alert prezzi LIVE (fino a 4s su clienti con
molte fatture) e la chiamata OpenAI — sul percorso senza cache. Su clienti
grossi l'endpoint sforava il timeout di 8s del frontend e il briefing "spariva"
dalla Home, ricomparendo solo al refresh.

Fix "mai bloccante" MA coerente:
  1. snapshot di OGGI presente   -> servito subito (nessun calcolo pesante);
  2. snapshot di oggi assente     -> si COSTRUISCE un briefing fresco con tutti i
     segnali live TRANNE l'alert prezzi (l'unica parte da 4s) e senza AI, e si
     rigenera la versione completa in BACKGROUND. Niente piu' "tutto in ordine"
     falso: prima si serviva lo snapshot stale / un template dalle sole notifiche
     persistite, che ignorava i segnali live (fatture/righe/dati mancanti).

Questi test verificano il comportamento osservabile: l'endpoint risponde sempre
senza pagare in linea alert prezzi/AI, riflette i segnali live, e la generazione
pesante e' schedulata in background.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw
from services.daily_briefing_service import _BRIEFING_CODE_VERSION


def _bg():
    """BackgroundTasks finto: registra i task senza eseguirli (come FastAPI)."""
    bt = MagicMock()
    bt.tasks = []
    bt.add_task.side_effect = lambda fn, *a, **k: bt.tasks.append((fn, a, k))
    return bt


_USER = {"id": "u-1", "nome_referente": "Marco"}
_RID = "rist-abc"
# Snapshot FRESCO e con la versione corrente: il fast-path 1 lo serve dalla cache
# solo se snapshot_is_stale() lo considera valido (versione giusta + entro TTL).
_GENERATED_AT = datetime.now(timezone.utc).isoformat()
_SNAP_OGGI = {
    "azioni": [],
    "narrative": "Tutto sotto controllo oggi.",
    "severity_max": "info",
    "tutto_ok": True,
    "generated_at": _GENERATED_AT,
    "_db_created_at": _GENERATED_AT,
    "code_version": _BRIEFING_CODE_VERSION,
}


def _make_sb():
    """Mock supabase: ogni query (incluse le preferenze) torna data=[] di default.

    Il nome referente viene letto da assistant_preferences: data=[] significa
    nessun override -> resta il nome_referente dell'utente.
    """
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.or_.return_value = q
    q.order.return_value = q
    q.limit.return_value = q
    q.gte.return_value = q
    q.execute.return_value = MagicMock(data=[])
    sb.table.return_value = q
    return sb


def test_cache_first_serve_snapshot_senza_calcolo_pesante():
    sb = _make_sb()
    bt = _bg()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=dict(_SNAP_OGGI)) as m_get, \
         patch("services.daily_briefing_service.generate_and_save_briefing") as m_gen, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto") as m_alert:
        resp = fw.home_briefing(bt, authorization="Bearer tok")

    # Snapshot di oggi servito dalla cache
    assert resp.narrativa == "Tutto sotto controllo oggi."
    assert resp.tutto_ok is True
    assert resp.generated_at == _GENERATED_AT
    # Saluto popolato (nome referente dell'utente)
    assert "Marco" in resp.saluto
    # La cache di oggi e' stata letta...
    m_get.assert_called_once()
    # ...e il calcolo pesante NON e' stato eseguito (questo evita il timeout 8s)
    m_alert.assert_not_called()
    m_gen.assert_not_called()
    # Cache di oggi presente -> NESSUNA rigenerazione background schedulata
    bt.add_task.assert_not_called()


def test_senza_snapshot_oggi_costruisce_briefing_live_e_rigenera():
    """Manca lo snapshot di oggi: costruiamo un briefing FRESCO con i segnali live
    (senza alert prezzi ne' AI) e rigeneriamo la versione completa in background.
    Il briefing riflette i dati mancanti -> mai un falso 'tutto in ordine'."""
    sb = _make_sb()
    bt = _bg()
    live = [{
        "id": "fatt-x", "topic_key": "fatture_mancanti", "source_type": "live",
        "severity": "warning", "title": "Mancano le fatture costo di maggio",
        "body": "", "action_page": "/analisi-fatture",
        "payload": {"tipo": "mese_senza_costi", "mese": "maggio"},
        "source_event_at": None, "dedupe_key": "fatt-x",
    }]
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=None), \
         patch.object(fw, "_briefing_raccogli_notifiche", return_value=live) as m_racc, \
         patch("services.daily_briefing_service.generate_and_save_briefing") as m_gen, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto") as m_alert:
        resp = fw.home_briefing(bt, authorization="Bearer tok")

    # Briefing fresco coerente: NON "tutto in ordine", riflette il dato mancante
    assert resp.tutto_ok is False
    assert "maggio" in resp.narrativa.lower()
    # Raccolta SENZA alert prezzi (il parametro che evita i 4s in linea)
    m_racc.assert_called_once()
    assert m_racc.call_args.kwargs.get("includi_alert_prezzi") is False
    # Niente alert prezzi / save in linea
    m_alert.assert_not_called()
    m_gen.assert_not_called()
    # Rigenerazione completa schedulata in background
    bt.add_task.assert_called_once()
    assert bt.add_task.call_args.args[0] is fw._briefing_rigenera_async


def test_senza_segnali_live_dice_tutto_ok():
    """Nessuno snapshot e NESSUN segnale live (dati davvero a posto): allora si',
    'tutto in ordine'. Verifica che il fix non gridi al lupo quando non serve."""
    sb = _make_sb()
    bt = _bg()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=None), \
         patch.object(fw, "_briefing_raccogli_notifiche", return_value=[]), \
         patch("services.daily_briefing_service.generate_and_save_briefing") as m_gen, \
         patch("services.daily_briefing_service._narrate_with_ai") as m_ai, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto") as m_alert:
        resp = fw.home_briefing(bt, authorization="Bearer tok")

    assert resp.tutto_ok is True
    m_ai.assert_not_called()
    m_alert.assert_not_called()
    m_gen.assert_not_called()
    bt.add_task.assert_called_once()
    assert bt.add_task.call_args.args[0] is fw._briefing_rigenera_async


def test_async_usa_budget_prezzi_generoso():
    """Fase 2b: il path async (_briefing_rigenera_async) raccoglie le notifiche
    con alert_prezzi_budget_generoso=True. Cosi' su clienti grossi l'alert prezzi
    NON viene saltato in silenzio: la Home resta veloce (fast-path senza prezzi) e
    il load successivo serve lo snapshot con i prezzi dalla cache."""
    sb = _make_sb()
    with patch("services.get_supabase_client", return_value=sb), \
         patch("services.ai_service.set_ai_context"), \
         patch.object(fw, "_briefing_raccogli_notifiche", return_value=[]) as m_racc, \
         patch.object(fw, "_briefing_nome_referente", return_value=("Marco", set())), \
         patch("services.daily_briefing_service.generate_and_save_briefing"):
        fw._briefing_rigenera_async("u-1", _RID)

    m_racc.assert_called_once()
    assert m_racc.call_args.kwargs.get("alert_prezzi_budget_generoso") is True
