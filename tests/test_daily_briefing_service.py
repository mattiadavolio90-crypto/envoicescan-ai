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
    _action_for,
    _anonymize_bullets,
    _build_snapshot,
    _bullet_for,
    _deanonymize,
    _narrate_with_ai,
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

    def test_card_non_supera_il_massimo(self):
        # Mai piu' di _MAX_CARD card, anche con tanti topic azionabili.
        notifs = [
            _notif("scadenza_superata", "error", {"count": 1, "totale": 100}),
            _notif("upload_failed",     "error", {"count": 1}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) <= 5

    def test_ordine_tematico_fatturato_prima_di_personale(self):
        # fatturato_mancante (40) prima di costo_personale_mancante (50),
        # e scadenza_imminente (61) in coda. Tutti azionabili, tutti mostrati.
        notifs = [
            _notif("scadenza_imminente",       "info",    {"count": 2, "totale": 200}),
            _notif("costo_personale_mancante", "warning", {"mese": "aprile", "anno": 2026}),
            _notif("fatturato_mancante",       "warning", {"mese": "aprile", "anno": 2026}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 3
        # ordine: fatturato, personale, scadenza
        assert "fatturato" in snap["bullets"][0].lower()
        assert "personale" in snap["bullets"][1].lower()
        assert "7 giorni" in snap["bullets"][2]

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

    def test_max_5_card(self):
        # Tutti azionabili: la gerarchia tiene al massimo 5 card.
        notifs = [
            _notif("upload_failed",            "error",   {"count": 1}),
            _notif("price_alert",              "warning", {"count": 2}),
            _notif("uncategorized_rows",       "warning", {"count": 4}),
            _notif("fatturato_mancante",       "warning", {"mese": "marzo", "anno": 2026}),
            _notif("costo_personale_mancante", "warning", {"mese": "marzo", "anno": 2026}),
            _notif("scadenza_superata",        "error",   {"count": 2, "totale": 800}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 5

    def test_gerarchia_tematica_upload_prima_di_scadenza(self):
        # Gerarchia tematica pura: upload_failed (10) prima di scadenza_superata
        # (60), anche se la scadenza e' "piu' grave". Decisione Mattia.
        notifs = [
            _notif("scadenza_superata", "error", {"count": 2, "totale": 500}),
            _notif("upload_failed",     "error", {"count": 1}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 2
        # Il primo bullet deve essere upload_failed
        assert "non" in snap["bullets"][0] and "caricat" in snap["bullets"][0]

    def test_gerarchia_tematica_prezzi_prima_di_scadenze(self):
        # price_alert (20) prima di scadenza_imminente (61)
        notifs = [
            _notif("scadenza_imminente", "info",    {"count": 1, "totale": 200}),
            _notif("price_alert",        "warning", {"count": 2}),
        ]
        snap = _build_snapshot(notifs)
        assert "Alert prezzi" in snap["bullets"][0]

    def test_filtro_count_zero_escluso(self):
        # Notifica con count 0 = rumore: non diventa card.
        notifs = [
            _notif("uncategorized_rows", "warning", {"count": 0}),
            _notif("price_alert",        "warning", {"count": 3}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 1
        assert "Alert prezzi" in snap["bullets"][0]

    def test_filtro_upload_manuale_escluso(self):
        # Upload manuale: il cliente lo vede mentre carica -> mai card.
        notifs = [
            _notif("upload_failed", "error", {"count": 1, "source": "manuale"}),
        ]
        snap = _build_snapshot(notifs)
        assert snap["bullets"] == []

    def test_topic_spento_dal_configuratore_escluso(self):
        # price_alert spento dal cliente: non diventa card.
        notifs = [
            _notif("price_alert",        "warning", {"count": 2}),
            _notif("uncategorized_rows", "warning", {"count": 3}),
        ]
        snap = _build_snapshot(notifs, topics_disabled=["price_alert"])
        assert len(snap["bullets"]) == 1
        assert "classificazione" in snap["bullets"][0]

    def test_upload_failed_non_disattivabile(self):
        # upload_failed e' bloccato: resta attivo anche se messo tra gli spenti.
        notifs = [
            _notif("upload_failed", "error", {"count": 1}),
        ]
        snap = _build_snapshot(notifs, topics_disabled=["upload_failed"])
        assert len(snap["bullets"]) == 1

    def test_upload_ricavi_failed_dopo_fatture_prima_di_prezzi(self):
        # Gerarchia: upload fatture (10) > upload ricavi (15) > prezzi (20).
        notifs = [
            _notif("price_alert",          "warning", {"count": 2}),
            _notif("upload_ricavi_failed", "warning", {"giorni_senza": 4}),
            _notif("upload_failed",        "error",   {"count": 1}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == 3
        assert "caricat" in snap["bullets"][0]              # upload fatture
        assert "ricavi automatici" in snap["bullets"][1].lower()  # upload ricavi
        assert "Alert prezzi" in snap["bullets"][2]         # prezzi
        # il testo ricavi riporta i giorni di assenza
        assert "4 giorni" in snap["bullets"][1]


# ────────────────────────────────────────────────
# _action_for
# ────────────────────────────────────────────────

class TestActionFor:
    def test_known_topic_uses_topic_fallback_page(self):
        n = _notif("scadenza_superata", "error", {"count": 1, "totale": 100})
        a = _action_for(n)
        assert a["topic_key"] == "scadenza_superata"
        assert a["severity"] == "error"
        assert a["cta_label"] == "Controlla scadenze"
        assert a["cta_page"] == "/scadenziario"
        # testo riusa _bullet_for
        assert a["testo"] == _bullet_for(n)

    def test_notif_action_page_overrides_when_next_path(self):
        n = _notif("fatturato_mancante", "warning", {"mese": "aprile", "anno": 2026})
        n["action_page"] = "/margini/2026/04"
        a = _action_for(n)
        assert a["cta_page"] == "/margini/2026/04"

    def test_legacy_streamlit_action_page_ignored(self):
        # path Streamlit legacy -> ignorato, si usa il fallback per topic
        n = _notif("price_alert", "warning", {"count": 2})
        n["action_page"] = "pages/3_controllo_prezzi.py"
        a = _action_for(n)
        assert a["cta_page"] == "/prezzi"

    def test_empty_action_page_uses_fallback(self):
        n = _notif("upload_failed", "error", {"count": 1})
        n["action_page"] = ""
        a = _action_for(n)
        assert a["cta_page"] == "/analisi-fatture"

    def test_unknown_topic_generic_action(self):
        n = _notif("food_cost_alto", "warning", {}, title="FC alto")
        a = _action_for(n)
        assert a["cta_label"] == "Apri"
        assert a["cta_page"] == "/dashboard"

    def test_id_propagated_for_dismiss(self):
        n = _notif("price_alert", "warning", {"count": 2})
        n["id"] = "notif-xyz"
        a = _action_for(n)
        assert a["id"] == "notif-xyz"


# ────────────────────────────────────────────────
# _build_snapshot — azioni e tutto_ok
# ────────────────────────────────────────────────

class TestSnapshotAzioni:
    def test_azioni_align_with_bullets(self):
        notifs = [
            _notif("scadenza_superata",  "error", {"count": 2, "totale": 800}),
            _notif("scadenza_imminente", "info",  {"count": 3, "totale": 600}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["azioni"]) == len(snap["bullets"]) == 2
        assert snap["azioni"][0]["topic_key"] == "scadenza_superata"
        assert snap["tutto_ok"] is False

    def test_tutto_ok_true_when_no_known_topics(self):
        snap = _build_snapshot([_notif("topic_sconosciuto", "info")])
        assert snap["azioni"] == []
        assert snap["tutto_ok"] is True

    def test_tutto_ok_true_on_empty(self):
        snap = _build_snapshot([])
        assert snap["tutto_ok"] is True
        assert snap["azioni"] == []


# ────────────────────────────────────────────────
# Narrazione AI: anonimizzazione + fallback
# ────────────────────────────────────────────────

class TestNarrazioneAI:
    def test_anonymize_replaces_product_name(self):
        bullets = ["\U0001F4C8 Alert prezzi su 2 prodotti — es. Mozzarella +12.5%."]
        anon, mapping = _anonymize_bullets(bullets)
        assert "Mozzarella" not in anon[0]
        assert "<<P1>>" in anon[0]
        assert mapping["<<P1>>"] == "Mozzarella"

    def test_anonymize_leaves_other_bullets_untouched(self):
        bullets = ["⚠️ 3 fatture scadute per € 1.200,00 — controlla."]
        anon, mapping = _anonymize_bullets(bullets)
        assert anon == bullets
        assert mapping == {}

    def test_deanonymize_roundtrip(self):
        text = "Occhio a <<P1>>, e' rincarato."
        assert _deanonymize(text, {"<<P1>>": "Mozzarella"}) == "Occhio a Mozzarella, e' rincarato."

    def test_narrate_empty_returns_fallback(self):
        assert _narrate_with_ai([], "FALLBACK") == "FALLBACK"

    def test_narrate_returns_fallback_on_ai_error(self):
        # Nessuna API key in test -> _get_openai_client solleva -> fallback
        with patch(
            "services.ai_service._get_openai_client",
            side_effect=RuntimeError("no key"),
        ):
            out = _narrate_with_ai(["⚠️ qualcosa"], "FALLBACK")
        assert out == "FALLBACK"

    def test_narrate_deanonymizes_ai_response(self):
        fake_client = MagicMock()
        fake_msg = MagicMock()
        fake_msg.content = "Occhio: <<P1>> e' rincarato, controlla i margini!"
        fake_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=fake_msg)],
            usage=None,
        )
        bullets = ["\U0001F4C8 Alert prezzi su 1 prodotto — es. Pomodoro +9.0%."]
        with patch("services.ai_service._get_openai_client", return_value=fake_client), \
             patch("services.ai_service._resolve_ristorante_id", return_value=None):
            out = _narrate_with_ai(bullets, "FALLBACK")
        assert "Pomodoro" in out
        assert "<<P1>>" not in out

    def test_build_snapshot_use_ai_false_uses_template(self):
        notifs = [_notif("scadenza_superata", "error", {"count": 1, "totale": 100})]
        snap = _build_snapshot(notifs, use_ai=False)
        assert snap["narrative"].startswith("Ciao!")


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
