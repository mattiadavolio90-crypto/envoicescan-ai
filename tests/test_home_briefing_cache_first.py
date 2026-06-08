"""Test fast-path cache-first dell'endpoint home_briefing (services.fastapi_worker).

Difetto: il briefing e' un dato giornaliero ma veniva RICALCOLATO ad ogni
apertura della Home — incluso l'alert prezzi LIVE (fino a 4s su clienti con
molte fatture) — solo per costruire il fingerprint con cui poi decidere se la
cache era valida. Su clienti grossi l'endpoint sforava il timeout di 8s del
frontend e il briefing "spariva" dalla Home pur essendo generato lato worker.

Fix: se lo snapshot di oggi esiste gia' in daily_briefing_state, l'endpoint lo
serve subito senza ricalcolare nulla di pesante.

Questi test verificano il comportamento osservabile dal punto di vista delle
performance: con cache presente NON si tocca il motore alert prezzi ne' si
rigenera lo snapshot; con cache assente si genera (e si salva).
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


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
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=dict(_SNAP_OGGI)) as m_get, \
         patch("services.daily_briefing_service.generate_and_save_briefing") as m_gen, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto") as m_alert:
        resp = fw.home_briefing(authorization="Bearer tok")

    # Snapshot di oggi servito dalla cache
    assert resp.narrativa == "Tutto sotto controllo oggi."
    assert resp.tutto_ok is True
    assert resp.generated_at == "2026-06-08T07:00:00+00:00"
    # Saluto popolato (nome referente dell'utente)
    assert "Marco" in resp.saluto
    # La cache e' stata letta...
    m_get.assert_called_once()
    # ...e il calcolo pesante NON e' stato eseguito (questo evita il timeout 8s)
    m_alert.assert_not_called()
    m_gen.assert_not_called()


def test_senza_snapshot_oggi_genera_e_salva():
    sb = _make_sb()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch("services.daily_briefing_service.get_today_briefing", return_value=None) as m_get, \
         patch("services.daily_briefing_service.generate_and_save_briefing", return_value=dict(_SNAP_OGGI)) as m_gen, \
         patch("services.price_impact_service.calcola_alert_prezzi_impatto", return_value={"count": 0, "top": None}):
        resp = fw.home_briefing(authorization="Bearer tok")

    assert resp.narrativa == "Tutto sotto controllo oggi."
    # Cache assente -> si genera e si salva lo snapshot del giorno
    m_get.assert_called_once()
    m_gen.assert_called_once()
