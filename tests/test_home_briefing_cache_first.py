"""Test fast-path cache-first dell'endpoint home_briefing (services.fastapi_worker).

Difetto: il briefing e' un dato giornaliero ma veniva RICALCOLATO ad ogni
apertura della Home — incluso l'alert prezzi LIVE (fino a 4s su clienti con
molte fatture) e la chiamata OpenAI — sul percorso senza cache. Su clienti
grossi l'endpoint sforava il timeout di 8s del frontend e il briefing "spariva"
dalla Home, ricomparendo solo al refresh.

Fix "mai bloccante":
  1. snapshot di OGGI presente   -> servito subito (nessun calcolo pesante);
  2. snapshot di oggi assente     -> si serve l'ultimo disponibile (anche di
     ieri) e si rigenera quello di oggi in BACKGROUND (BackgroundTasks);
  3. nessuno snapshot mai generato -> template deterministico istantaneo (no AI,
     no alert prezzi) + rigenerazione in background.

Questi test verificano il comportamento osservabile: l'endpoint risponde sempre
senza pagare in linea alert prezzi/AI, e la generazione pesante e' schedulata in
background.
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


def _bg():
    """BackgroundTasks finto: registra i task senza eseguirli (come FastAPI)."""
    bt = MagicMock()
    bt.tasks = []
    bt.add_task.side_effect = lambda fn, *a, **k: bt.tasks.append((fn, a, k))
    return bt


_USER = {"id": "u-1", "nome_referente": "Marco"}
_RID = "rist-abc"
_SNAP_OGGI = {
    "azioni": [],
    "narrative": "Tutto sotto controllo oggi.",
    "severity_max": "info",
    "tutto_ok": True,
    "generated_at": "2026-06-08T07:00:00+00:00",
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
    assert resp.generated_at == "2026-06-08T07:00:00+00:00"
    # Saluto popolato (nome referente dell'utente)
    assert "Marco" in resp.saluto
    # La cache di oggi e' stata letta...
    m_get.assert_called_once()
    # ...e il calcolo pesante NON e' stato eseguito (questo evita il timeout 8s)
    m_alert.assert_not_called()
    m_gen.assert_not_called()
    # Cache di oggi presente -> NESSUNA rigenerazione background schedulata
    bt.add_task.assert_not_called()


def test_senza_snapshot_oggi_serve_stale_e_rigenera_in_background():
    """Manca oggi ma esiste un briefing recente: lo serviamo subito e rigeneriamo
    in background (mai in linea, per non sforare gli 8s)."""
    sb = _make_sb()
    bt = _bg()
    stale = dict(_SNAP_OGGI, narrative="Briefing di ieri", _stale=True)
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=None), \
         patch("services.daily_briefing_service.get_latest_briefing", return_value=stale) as m_latest, \
         patch("services.daily_briefing_service.generate_and_save_briefing") as m_gen, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto") as m_alert:
        resp = fw.home_briefing(bt, authorization="Bearer tok")

    # Serviamo subito l'ultimo snapshot disponibile (stale)
    assert resp.narrativa == "Briefing di ieri"
    m_latest.assert_called_once()
    # La generazione pesante NON gira in linea: ne' alert prezzi ne' save
    m_alert.assert_not_called()
    m_gen.assert_not_called()
    # ...ma e' schedulata in background sull'helper di rigenerazione
    bt.add_task.assert_called_once()
    assert bt.add_task.call_args.args[0] is fw._briefing_rigenera_async


def test_cliente_nuovo_template_istantaneo_senza_ai_ne_alert():
    """Nessuno snapshot mai generato: template deterministico istantaneo (no AI,
    no alert prezzi live) + rigenerazione in background."""
    sb = _make_sb()
    bt = _bg()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=None), \
         patch("services.daily_briefing_service.get_latest_briefing", return_value=None), \
         patch("services.daily_briefing_service.generate_and_save_briefing") as m_gen, \
         patch("services.daily_briefing_service._narrate_with_ai") as m_ai, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto") as m_alert:
        resp = fw.home_briefing(bt, authorization="Bearer tok")

    # Risponde comunque (template), senza toccare AI ne' alert prezzi in linea
    assert resp.tutto_ok is True
    m_ai.assert_not_called()
    m_alert.assert_not_called()
    m_gen.assert_not_called()
    # Rigenerazione completa schedulata in background
    bt.add_task.assert_called_once()
    assert bt.add_task.call_args.args[0] is fw._briefing_rigenera_async
