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
    _MAX_CARD,
    _action_for,
    _anonymize_bullets,
    _build_snapshot,
    _bullet_for,
    _is_actionable,
    _deanonymize,
    _narrate_with_ai,
    _narrative_phrase_for,
    _rientro_bullet,
    _severity_max,
    _today_rome,
    generate_and_save_briefing,
    get_latest_briefing,
    get_today_briefing,
    invalidate_today_briefing,
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
    q.order.return_value = q
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

    def test_appuntamento_singolo(self):
        n = _notif("appuntamento_imminente", "info",
                   {"count": 1, "primo": "Fornitore vini", "ora": "10:30"})
        b = _bullet_for(n)
        assert "Fornitore vini" in b
        assert "10:30" in b

    def test_appuntamento_plurale(self):
        n = _notif("appuntamento_imminente", "info",
                   {"count": 3, "primo": "Commercialista", "ora": "09:00"})
        b = _bullet_for(n)
        assert "3 appuntamenti" in b
        assert "Commercialista" in b

    def test_appuntamento_fallback(self):
        n = _notif("appuntamento_imminente", "info", {}, title="Appuntamenti")
        assert "Appuntamenti" in _bullet_for(n)


# ────────────────────────────────────────────────
# _is_actionable — appuntamenti
# ────────────────────────────────────────────────

class TestAppuntamentoActionable:
    def test_con_appuntamenti_e_card(self):
        n = _notif("appuntamento_imminente", "info", {"count": 2})
        assert _is_actionable(n) is True

    def test_senza_appuntamenti_no_card(self):
        n = _notif("appuntamento_imminente", "info", {"count": 0})
        assert _is_actionable(n) is False

    def test_price_alert_bullet_singolo_prodotto(self):
        n = _notif("price_alert", "warning", {
            "count": 1, "top_product": "Mozzarella",
            "top_increase_pct": 23.8, "top_tipo": "prodotto",
        })
        b = _bullet_for(n)
        assert "Prezzo in aumento" in b
        assert "— Mozzarella +23.8%" in b
        assert "prodotti" not in b  # singolare: niente plurale

    def test_price_alert_bullet_singolo_tag(self):
        n = _notif("price_alert", "warning", {
            "count": 1, "top_product": "BAR, CAFFE'",
            "top_increase_pct": 119.6, "impatto_mese": 80, "top_tipo": "tag",
        })
        b = _bullet_for(n)
        assert "Categoria in aumento" in b
        assert "— BAR, CAFFE' +119.6%" in b
        assert "prodotto" not in b.lower()

    def test_price_alert_bullet_piu_tag(self):
        n = _notif("price_alert", "warning", {
            "count": 4, "top_product": "BIRRE",
            "top_increase_pct": 15.0, "top_tipo": "tag",
        })
        b = _bullet_for(n)
        assert "su 4 categorie" in b
        assert "— BIRRE +15.0%" in b

    def test_uncategorized_rows_payload_key(self):
        n = _notif("uncategorized_rows", "warning", {"uncategorized_rows": 7})
        b = _bullet_for(n)
        assert "7" in b
        assert "controllare" in b

    def test_uncategorized_rows_fallback_count_key(self):
        n = _notif("uncategorized_rows", "warning", {"count": 5})
        b = _bullet_for(n)
        assert "5" in b

    def test_unknown_topic_returns_title(self):
        n = _notif("food_cost_soglia_superata", "warning", {}, title="FC alto")
        assert _bullet_for(n) == "FC alto"


# ────────────────────────────────────────────────
# _narrative_phrase_for — price_alert (Difetto 1: prodotto vs categoria)
# ────────────────────────────────────────────────

class TestNarrativePriceAlert:
    def test_singolo_prodotto_nominato_senza_soprattutto(self):
        # count==1 deve nominare il prodotto direttamente, mai "soprattutto"
        # (che implicherebbe un elenco di piu' voci).
        n = _notif("price_alert", "warning", {
            "count": 1, "top_product": "Mozzarella",
            "top_increase_pct": 23.8, "top_tipo": "prodotto",
        })
        frase = _narrative_phrase_for(n)
        assert "Mozzarella" in frase
        assert "soprattutto" not in frase
        assert "23.8" in frase
        assert "prezzo di Mozzarella" in frase

    def test_singolo_tag_chiamato_categoria(self):
        # Un alert su un TAG non e' un "prodotto": va detto "categoria".
        n = _notif("price_alert", "warning", {
            "count": 1, "top_product": "BAR, CAFFE', PASTICCERIE",
            "top_increase_pct": 119.6, "impatto_mese": 80, "top_tipo": "tag",
        })
        frase = _narrative_phrase_for(n)
        assert "categoria BAR, CAFFE', PASTICCERIE" in frase
        assert "prodotto" not in frase.lower()
        assert "soprattutto" not in frase
        assert "119.6" in frase
        assert "80" in frase

    def test_piu_voci_usa_piu_pesante(self):
        # count>1: niente piu' "soprattutto", ma "il prodotto piu' pesante e' …".
        n = _notif("price_alert", "warning", {
            "count": 3, "top_product": "Mozzarella",
            "top_increase_pct": 12.5, "top_tipo": "prodotto",
        })
        frase = _narrative_phrase_for(n)
        assert "3 voci" in frase
        assert "più pesante" in frase
        assert "Mozzarella" in frase
        assert "soprattutto" not in frase

    def test_piu_voci_tag_qualifica_categoria(self):
        n = _notif("price_alert", "warning", {
            "count": 2, "top_product": "BIRRE",
            "top_increase_pct": 30.0, "top_tipo": "tag",
        })
        frase = _narrative_phrase_for(n)
        assert "categoria più pesante è BIRRE" in frase

    def test_tipo_assente_resta_prodotto(self):
        # Retrocompat: senza top_tipo si assume prodotto (vecchi snapshot).
        n = _notif("price_alert", "warning", {
            "count": 1, "top_product": "Pomodori", "top_increase_pct": 10.0,
        })
        frase = _narrative_phrase_for(n)
        assert "prezzo di Pomodori" in frase


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

    def test_max_card(self):
        # Tutti azionabili: la gerarchia tiene al massimo _MAX_CARD card (4 da 19/06).
        notifs = [
            _notif("upload_failed",            "error",   {"count": 1}),
            _notif("price_alert",              "warning", {"count": 2}),
            _notif("uncategorized_rows",       "warning", {"count": 4}),
            _notif("fatturato_mancante",       "warning", {"mese": "marzo", "anno": 2026}),
            _notif("costo_personale_mancante", "warning", {"mese": "marzo", "anno": 2026}),
            _notif("scadenza_superata",        "error",   {"count": 2, "totale": 800}),
        ]
        snap = _build_snapshot(notifs)
        assert len(snap["bullets"]) == _MAX_CARD

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
        assert "controllare" in snap["bullets"][0]

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

    def test_uncategorized_rows_deep_link_analisi_fatture(self):
        # La classificazione si fa in Analisi Fatture (tab Articoli, filtro
        # verifica), NON in Analisi e Tag. Deep-link diretto sul filtro.
        n = _notif("uncategorized_rows", "warning", {"count": 7})
        a = _action_for(n)
        assert a["cta_label"] == "Controlla righe"
        assert a["cta_page"] == "/analisi-fatture?tab=articoli&verifica=1"
        assert "analisi-e-tag" not in a["cta_page"]

    def test_fatture_mancanti_azionabile_e_in_snapshot(self):
        # La voce 1 della Salute ("Fatture caricate" rossa) deve diventare
        # un'azione nel briefing, non restare un pallino muto.
        n = _notif("fatture_mancanti", "warning", {})
        assert _is_actionable(n) is True
        a = _action_for(n)
        assert a["cta_page"] == "/analisi-fatture"
        snap = _build_snapshot([n], use_ai=False)
        assert snap["tutto_ok"] is False
        assert any(az["topic_key"] == "fatture_mancanti" for az in snap["azioni"])


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
        # Formato reale prodotto da _bullet_for (price_alert): "… — <prodotto> +NN%".
        # Il vecchio test usava "es. <prodotto>" (formato obsoleto): la regex storica
        # matchava il test ma NON il bullet reale -> nomi inviati a OpenAI in chiaro.
        bullets = ["\U0001F4C8 Alert prezzi su 2 prodotti — Mozzarella +12.5% (≈€80/mese)."]
        anon, mapping = _anonymize_bullets(bullets)
        assert "Mozzarella" not in anon[0]
        assert "<<P1>>" in anon[0]
        assert mapping["<<P1>>"] == "Mozzarella"

    def test_anonymize_leaves_other_bullets_untouched(self):
        bullets = ["⚠️ 3 fatture scadute per € 1.200,00 — controlla."]
        anon, mapping = _anonymize_bullets(bullets)
        assert anon == bullets
        assert mapping == {}

    def test_anonymize_singolo_prodotto_nuovo_formato(self):
        # Bullet count==1: "📈 Prezzo in aumento — <Nome> +NN%". Anche qui il
        # nome non deve mai finire a OpenAI in chiaro.
        b = _bullet_for(_notif("price_alert", "warning", {
            "count": 1, "top_product": "Mozzarella di bufala",
            "top_increase_pct": 23.8, "top_tipo": "prodotto",
        }))
        anon, mapping = _anonymize_bullets([b])
        assert "Mozzarella di bufala" not in anon[0]
        assert mapping.get("<<P1>>") == "Mozzarella di bufala"

    def test_anonymize_singolo_tag_nuovo_formato(self):
        b = _bullet_for(_notif("price_alert", "warning", {
            "count": 1, "top_product": "BAR, CAFFE', PASTICCERIE",
            "top_increase_pct": 119.6, "impatto_mese": 80, "top_tipo": "tag",
        }))
        anon, mapping = _anonymize_bullets([b])
        assert "BAR, CAFFE', PASTICCERIE" not in anon[0]
        assert mapping.get("<<P1>>") == "BAR, CAFFE', PASTICCERIE"

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
        # Tono sobrio: il template apre con "Da sistemare oggi:" e contiene il
        # dettaglio della voce, senza saluti/incoraggiamenti enfatici.
        assert snap["narrative"].startswith("Da sistemare oggi:")
        assert "scadenza superata" in snap["narrative"]


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
# get_latest_briefing (fallback "mai bloccante")
# ────────────────────────────────────────────────

class TestGetLatestBriefing:
    def test_returns_latest_marked_stale(self):
        snap_data = {"bullets": ["b"], "severity_max": "info"}
        sb = _make_supabase_mock([
            {"snapshot": snap_data, "created_at": "2026-06-08T07:00:00Z",
             "generated_for_date": "2026-06-08"},
        ])
        result = get_latest_briefing(UID, RID, sb)
        assert result is not None
        assert result["bullets"] == ["b"]
        # marcato come ripiego, cosi' il chiamante sa che e' un briefing passato
        assert result["_stale"] is True
        assert result["_db_created_at"] == "2026-06-08T07:00:00Z"

    def test_returns_none_if_no_row(self):
        sb = _make_supabase_mock([])
        assert get_latest_briefing(UID, RID, sb) is None

    def test_returns_none_on_missing_params(self):
        sb = _make_supabase_mock()
        assert get_latest_briefing("", RID, sb) is None
        assert get_latest_briefing(UID, "", sb) is None
        assert get_latest_briefing(UID, RID, None) is None

    def test_returns_none_on_exception(self):
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("DB down")
        assert get_latest_briefing(UID, RID, sb) is None


# ────────────────────────────────────────────────
# espandi_topic_spenti + filtro "Scadenze" (fix 9/6: il toggle Scadenze
# spegne sia scadenza_superata che scadenza_imminente, stesso tema)
# ────────────────────────────────────────────────

from services.daily_briefing_service import espandi_topic_spenti


class TestEspandiTopicSpenti:
    def test_scadenza_espande_a_imminente(self):
        spenti = espandi_topic_spenti(["scadenza_superata"])
        assert spenti == {"scadenza_superata", "scadenza_imminente"}

    def test_topic_senza_figli_invariato(self):
        assert espandi_topic_spenti(["price_alert"]) == {"price_alert"}

    def test_lista_vuota(self):
        assert espandi_topic_spenti([]) == set()

    def test_input_malformato_set_vuoto(self):
        assert espandi_topic_spenti(None) == set()
        assert espandi_topic_spenti("scadenza_superata") == set()

    def test_mix(self):
        spenti = espandi_topic_spenti(["scadenza_superata", "price_alert"])
        assert spenti == {"scadenza_superata", "scadenza_imminente", "price_alert"}


class TestFiltroScadenzeNelloSnapshot:
    def test_spegnere_scadenze_nasconde_anche_imminente(self):
        notifs = [
            _notif("scadenza_superata", "error", {"count": 2, "totale": 900.0}),
            _notif("scadenza_imminente", "warning", {"count": 1, "totale": 100.0}),
            _notif("price_alert", "warning", {"count": 1}),
        ]
        snap = _build_snapshot(notifs, use_ai=False, topics_disabled=["scadenza_superata"])
        topic_keys = {a.get("topic_key") for a in snap["azioni"]}
        assert "scadenza_superata" not in topic_keys
        assert "scadenza_imminente" not in topic_keys  # il fix: spento anche questo
        assert "price_alert" in topic_keys


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


# ────────────────────────────────────────────────
# invalidate_today_briefing
# ────────────────────────────────────────────────

def _make_supabase_delete_mock():
    q = MagicMock()
    q.table.return_value = q
    q.delete.return_value = q
    q.eq.return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


class TestInvalidateTodayBriefing:
    def test_deletes_today_snapshot(self):
        sb = _make_supabase_delete_mock()
        with patch("services.daily_briefing_service._today_rome", return_value=date(2026, 6, 8)):
            invalidate_today_briefing(UID, RID, sb)

        sb.table.assert_called_with("daily_briefing_state")
        sb.delete.assert_called_once()
        # Filtra per user, ristorante e data di oggi
        eq_args = [c.args for c in sb.eq.call_args_list]
        assert ("user_id", UID) in eq_args
        assert ("ristorante_id", RID) in eq_args
        assert ("generated_for_date", "2026-06-08") in eq_args
        sb.execute.assert_called_once()

    def test_noop_on_missing_params(self):
        sb = _make_supabase_delete_mock()
        invalidate_today_briefing("", RID, sb)
        invalidate_today_briefing(UID, "", sb)
        invalidate_today_briefing(UID, RID, None)
        sb.delete.assert_not_called()

    def test_swallows_exception(self):
        # Best-effort: un errore qui non deve propagare (non bloccare upload/save).
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("DB down")
        invalidate_today_briefing(UID, RID, sb)  # non solleva


# ────────────────────────────────────────────────
# Trigger rientro_assenza (bentornato + amo soft Assistenza)
# ────────────────────────────────────────────────

class TestRientroAssenza:
    def test_bullet_solo_bentornato_senza_offerta(self):
        # Salute non rossa: solo bentornato, niente amo commerciale.
        testo = _rientro_bullet({"giorni": 10, "offri_assistenza": False})
        assert "Bentornato" in testo
        assert "gestire noi" not in testo

    def test_bullet_con_offerta_assistenza(self):
        # Salute rossa: in coda l'amo soft (un'offerta, mai un rimprovero).
        testo = _rientro_bullet({"giorni": 10, "offri_assistenza": True})
        assert "Bentornato" in testo
        assert "gestire noi" in testo
        # Mai un tono di rimprovero per l'assenza.
        assert "arres" not in testo.lower()

    def test_rientro_apre_la_narrativa_e_non_e_una_card(self):
        # Il rientro e' apertura: entra nella narrativa ma NON conta come card
        # to-do (non incrementa azioni, non azzera 'tutto_ok' da solo).
        rientro = _notif("rientro_assenza", severity="info",
                         payload={"giorni": 9, "offri_assistenza": True})
        snap = _build_snapshot([rientro], use_ai=False)
        assert "Bentornato" in snap["narrative"]
        assert snap["azioni"] == []
        assert snap["bullets"] == []
        # Nessuna to-do reale: tutto_ok resta True (il rientro non e' un problema).
        assert snap["tutto_ok"] is True

    def test_rientro_precede_le_todo(self):
        # Con rientro + una to-do reale: il bentornato apre, la to-do segue.
        rientro = _notif("rientro_assenza", severity="info",
                         payload={"giorni": 8, "offri_assistenza": False})
        todo = _notif("scadenza_superata", severity="error",
                      payload={"count": 2, "totale": 500.0})
        snap = _build_snapshot([rientro, todo], use_ai=False)
        narr = snap["narrative"]
        assert "Bentornato" in narr
        # Il bentornato compare prima della to-do nel testo.
        assert narr.index("Bentornato") < narr.index("scadenz")
        # La to-do resta una card vera.
        assert len(snap["azioni"]) == 1
        assert snap["tutto_ok"] is False
