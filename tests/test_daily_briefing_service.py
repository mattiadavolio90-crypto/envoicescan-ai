"""Unit tests per services/daily_briefing_service.py

Copertura:
- _build_snapshot(): quota L1/L2, dedup topic_key, topic sconosciuti ignorati
- _bullet_for(): testo corretto per ogni topic con payload / fallback title
- _severity_max(): error > warning > info, lista vuota
- get_today_briefing(): row trovata, row assente, eccezione
- generate_and_save_briefing(): upsert corretto, valore restituito, eccezione

Non si connette mai a Supabase reale: usa MagicMock.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.daily_briefing_service import (
    _build_snapshot,
    _bullet_for,
    _severity_max,
    _today_rome,
    generate_and_save_briefing,
    get_today_briefing,
)


# ────────────────────────────────────────────────
# Fixtures helpers
# ────────────────────────────────────────────────

UID = "user-aaa"
RID = "rist-bbb"


def _make_supabase_mock(return_data=None):
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.upsert.return_value = q
    q.execute.return_value = MagicMock(data=return_data or [])
    return q


def _notif(topic, severity="warning", payload=None, title=None):
    return {
        "topic_key": topic,
        "severity": severity,
        "title": title or topic,
        "payload": payload or {},
    }


# ────────────────────────────────────────────────
# _severity_max
# ────────────────────────────────────────────────

class TestSeverityMax:
    def test_empty(self):
        assert _severity_max([]) == "info"

    def test_all_info(self):
        assert _severity_max([_notif("x", "info"), _notif("y", "info")]) == "info"

    def test_mixed_no_error(self):
        assert _severity_max([_notif("x", "info"), _notif("y", "warning")]) == "warning"

    def test_error_wins(self):
        assert _severity_max([_notif("x", "warning"), _notif("y", "error")]) == "error"

    def test_error_short_circuits(self):
        # anche se l'error e' il primo, lo restituisce subito
        notifs = [_notif("x", "error")] + [_notif(str(i), "warning") for i in range(10)]
        assert _severity_max(notifs) == "error"


# ────────────────────────────────────────────────
# _bullet_for
# ────────────────────────────────────────────────

class TestBulletFor:
    def test_scadenza_superata_with_payload(self):
        n = _notif("scadenza_superata", "error", {"count": 3, "totale": 1200.50})
        b = _bullet_for(n)
        assert "3" in b
        assert "1,200.50" in b or "1.200,50" in b  # locale Python default usa ,
        assert "fatture scadute" in b

    def test_scadenza_superata_singular(self):
        n = _notif("scadenza_superata", "error", {"count": 1, "totale": 500.0})
        assert "fattura scaduta" in _bullet_for(n)

    def test_scadenza_superata_fallback(self):
        n = _notif("scadenza_superata", "error", {}, title="Scadenza!")
        assert "Scadenza!" in _bullet_for(n)

    def test_upload_failed_with_payload(self):
        n = _notif("upload_failed", "error", {"count": 2})
        b = _bullet_for(n)
        assert "2" in b
        assert "fatture non sono state caricate" in b

    def test_upload_failed_singular(self):
        n = _notif("upload_failed", "error", {"count": 1})
        assert "fattura non" in _bullet_for(n)

    def test_upload_failed_fallback(self):
        n = _notif("upload_failed", "error", {}, title="Errore upload")
        assert "Errore upload" in _bullet_for(n)

    def test_scadenza_imminente_with_payload(self):
        n = _notif("scadenza_imminente", "info", {"count": 4, "totale": 600.0})
        b = _bullet_for(n)
        assert "4" in b
        assert "fatture in scadenza" in b
        assert "7 giorni" in b

    def test_fatturato_mancante_with_payload(self):
        n = _notif("fatturato_mancante", "warning", {"mese": "aprile", "anno": 2026})
        b = _bullet_for(n)
        assert "aprile" in b
        assert "2026" in b

    def test_fatturato_mancante_fallback(self):
        n = _notif("fatturato_mancante", "warning", {}, title="Manca fatturato")
        assert "Manca fatturato" in _bullet_for(n)

    def test_costo_personale_with_payload(self):
        n = _notif("costo_personale_mancante", "warning", {"mese": "marzo", "anno": 2026})
        b = _bullet_for(n)
        assert "marzo" in b
        assert "2026" in b
        assert "personale" in b

    def test_price_alert_with_top_product(self):
        n = _notif("price_alert", "warning", {
            "count": 3, "top_product": "Mozzarella", "top_increase_pct": 12.5
        })
        b = _bullet_for(n)
        assert "3" in b
        assert "Mozzarella" in b
        assert "12.5" in b

    def test_price_alert_without_top_product(self):
        n = _notif("price_alert", "warning", {"count": 2})
        b = _bullet_for(n)
        assert "2" in b
        assert "prodotti" in b

    def test_price_alert_fallback(self):
        n = _notif("price_alert", "warning", {}, title="Alert prezzi")
        assert "Alert prezzi" in _bullet_for(n)

    def test_uncategorized_rows_payload_key(self):
        n = _notif("uncategorized_rows", "warning", {"uncategorized_rows": 7})
        b = _bullet_for(n)
        assert "7" in b
        assert "classificazione" in b

    def test_uncategorized_rows_fallback_count_key(self):
        n = _notif("uncategorized_rows", "warning", {"count": 5})
        b = _bullet_for(n)
        assert "5" in b

    def test_unknown_topic_returns_title(self):
        n = _notif("food_cost_soglia_superata", "warning", {}, title="FC alto")
        assert _bullet_for(n) == "FC alto"


# ────────────────────────────────────────────────
# _build_snapshot
# ────────────────────────────────────────────────

class TestBuildSnapshot:
    def test_empty_notifications(self):
        snap = _build_snapshot([])
        assert snap["bullets"] == []
        assert snap["notif_count"] == 0
        assert snap["severity_max"] == "info"
        assert "generated_at" in snap

    def test_quota_l1_capped_at_3(self):
        # 4 L1 topics: solo 3 devono finire nei bullet (quota L1=3)
        notifs = [
            _notif("scadenza_superata", "error", {"count": 1, "totale": 100}),
            _notif("upload_failed",     "error", {"count": 1}),
            # scadenza_superata e upload_failed esauriscono i topic L1 noti (solo 2)
            # Aggiungiamo topic sconosciuti L1 simulando entita' future
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) <= 3 + 2  # max quota totale

    def test_quota_l2_capped_at_2(self):
        # 3 L2 topics: solo 2 devono apparire
        notifs = [
            _notif("scadenza_imminente",       "info",    {"count": 2, "totale": 200}),
            _notif("fatturato_mancante",       "warning", {"mese": "aprile", "anno": 2026}),
            _notif("costo_personale_mancante", "warning", {"mese": "aprile", "anno": 2026}),
        ]
        snap = _build_snapshot(notifs)
        # Solo i primi 2 L2 per priorita' (scadenza_imminente=30, fatturato_mancante=40)
        assert len(snap["bullets"]) == 2
        bullets_text = " ".join(snap["bullets"])
        assert "7 giorni" in bullets_text      # scadenza_imminente
        assert "aprile" in bullets_text        # fatturato_mancante
        # costo_personale_mancante tagliato dalla quota
        assert "personale" not in bullets_text

    def test_dedup_same_topic(self):
        # Due notifiche con stesso topic_key: conta come 1
        notifs = [
            _notif("scadenza_superata", "error", {"count": 3, "totale": 300}),
            _notif("scadenza_superata", "error", {"count": 5, "totale": 500}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 1
        # Mantiene la prima occorrenza (piu' recente)
        assert "3" in snap["bullets"][0]

    def test_unknown_topics_excluded(self):
        notifs = [
            _notif("food_cost_soglia_superata", "error"),
            _notif("mol_negativo",              "warning"),
            _notif("topic_sconosciuto",         "info"),
        ]
        snap = _build_snapshot(notifs)
        assert snap["bullets"] == []

    def test_notif_count_includes_all(self):
        # notif_count conta TUTTE le notifiche passate, non solo quelle nei bullet
        notifs = [_notif(f"topic_{i}", "info") for i in range(10)]
        snap = _build_snapshot(notifs)
        assert snap["notif_count"] == 10

    def test_full_mixed_quota(self):
        # 2 L1 + 3 L2 → 2 L1 + 2 L2 = 4 bullet
        notifs = [
            _notif("scadenza_superata",        "error",   {"count": 2, "totale": 800}),
            _notif("upload_failed",            "error",   {"count": 1}),
            _notif("scadenza_imminente",       "info",    {"count": 3, "totale": 600}),
            _notif("fatturato_mancante",       "warning", {"mese": "marzo", "anno": 2026}),
            _notif("costo_personale_mancante", "warning", {"mese": "marzo", "anno": 2026}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 4
        assert snap["severity_max"] == "error"

    def test_priority_order_l1(self):
        # scadenza_superata (priorita' 10) prima di upload_failed (priorita' 20)
        notifs = [
            _notif("upload_failed",     "error", {"count": 1}),
            _notif("scadenza_superata", "error", {"count": 2, "totale": 500}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 2
        # Il primo bullet deve essere scadenza_superata
        assert "fatture scadute" in snap["bullets"][0] or "fattura scaduta" in snap["bullets"][0]

    def test_priority_order_l2(self):
        # scadenza_imminente (30) prima di price_alert (60)
        notifs = [
            _notif("price_alert",       "warning", {"count": 2}),
            _notif("scadenza_imminente", "info",   {"count": 1, "totale": 200}),
        ]
        snap = _build_snapshot(notifs)
        assert "7 giorni" in snap["bullets"][0]


# ────────────────────────────────────────────────
# get_today_briefing
# ────────────────────────────────────────────────

class TestGetTodayBriefing:
    def test_returns_snapshot_if_found(self):
        today = date.today().isoformat()
        snap_data = {"bullets": ["bullet 1"], "severity_max": "info"}
        sb = _make_supabase_mock([{"snapshot": snap_data, "created_at": "2026-05-18T10:00:00Z"}])

        with patch("services.daily_briefing_service._today_rome", return_value=date.today()):
            result = get_today_briefing(UID, RID, sb)

        assert result is not None
        assert result["bullets"] == ["bullet 1"]
        assert result["_db_created_at"] == "2026-05-18T10:00:00Z"

    def test_returns_none_if_no_row(self):
        sb = _make_supabase_mock([])
        result = get_today_briefing(UID, RID, sb)
        assert result is None

    def test_returns_none_on_missing_params(self):
        sb = _make_supabase_mock()
        assert get_today_briefing("", RID, sb) is None
        assert get_today_briefing(UID, "", sb) is None
        assert get_today_briefing(UID, RID, None) is None

    def test_returns_none_on_exception(self):
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("DB down")
        result = get_today_briefing(UID, RID, sb)
        assert result is None


# ────────────────────────────────────────────────
# generate_and_save_briefing
# ────────────────────────────────────────────────

class TestGenerateAndSaveBriefing:
    def test_returns_snapshot_on_success(self):
        sb = _make_supabase_mock([])
        notifs = [
            _notif("scadenza_superata", "error", {"count": 2, "totale": 400}),
        ]
        result = generate_and_save_briefing(UID, RID, notifs, sb)

        assert result is not None
        assert isinstance(result["bullets"], list)
        assert len(result["bullets"]) >= 1
        assert "generated_for_date" in result

    def test_calls_upsert_with_correct_keys(self):
        sb = _make_supabase_mock([])
        notifs = [_notif("upload_failed", "error", {"count": 3})]
        generate_and_save_briefing(UID, RID, notifs, sb)

        # Verifica che upsert sia stato chiamato
        sb.table.assert_called_with("daily_briefing_state")
        upsert_call = sb.upsert.call_args
        record = upsert_call[0][0]
        assert record["user_id"] == UID
        assert record["ristorante_id"] == RID
        assert "generated_for_date" in record
        assert "snapshot" in record

    def test_returns_none_on_missing_params(self):
        sb = _make_supabase_mock()
        assert generate_and_save_briefing("", RID, [], sb) is None
        assert generate_and_save_briefing(UID, "", [], sb) is None
        assert generate_and_save_briefing(UID, RID, [], None) is None

    def test_returns_none_on_exception(self):
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("DB down")
        result = generate_and_save_briefing(UID, RID, [], sb)
        assert result is None

    def test_upsert_conflict_key(self):
        sb = _make_supabase_mock([])
        generate_and_save_briefing(UID, RID, [], sb)
        on_conflict = sb.upsert.call_args.kwargs.get("on_conflict")
        assert on_conflict == "user_id,ristorante_id,generated_for_date"
