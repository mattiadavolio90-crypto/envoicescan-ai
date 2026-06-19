"""Test guardia per il gate del verde "Tutto in ordine" (PRIORITÀ 0, 19/06).

Difetto osservato (Mattia): la Home mostrava "Tutto in ordine" verde anche con
Salute incompleta / dati mancanti. Causa: tutto_ok guardava solo se c'erano card
da fare, ignorando i dati mancanti — che rendono FALSI i numeri di margine/MOL.

Regola decisa: il verde si accende SOLO se non c'è nessuna card da fare E nessun
dato mancante. Un dato mancante in posizione 5+ (oltre il taglio a _MAX_CARD) NON
deve far comparire il verde. Lo snapshot espone dati_mancanti per la nota neutra.
"""
from services.daily_briefing_service import _build_snapshot, _MAX_CARD


def _notif(topic, severity="warning", payload=None, title=None):
    return {
        "topic_key": topic,
        "severity": severity,
        "title": title or topic,
        "payload": payload or {},
    }


class TestVerdeGate:
    def test_nessuna_notifica_e_verde(self):
        snap = _build_snapshot([])
        assert snap["tutto_ok"] is True
        assert snap["dati_mancanti"] == []

    def test_dato_mancante_spegne_il_verde(self):
        # Un solo dato mancante (fatturato) -> NON tutto_ok, e finisce in dati_mancanti.
        snap = _build_snapshot([_notif("fatturato_mancante")])
        assert snap["tutto_ok"] is False
        assert "il fatturato del mese" in snap["dati_mancanti"]

    def test_dato_mancante_oltre_il_taglio_spegne_comunque_il_verde(self):
        # _MAX_CARD card "alte" di topic DIVERSI (la dedup tiene 1 voce per topic) +
        # un dato mancante a priorità più bassa, che resta FUORI dal taglio: il verde
        # deve restare spento lo stesso e il dato va comunque in dati_mancanti.
        alte = [
            _notif("upload_failed", "error", {"count": 1}),
            _notif("price_alert", payload={"count": 2}),
            _notif("uncategorized_rows", payload={"count": 3}),
            _notif("scadenza_superata", payload={"count": 1, "totale": 10.0}),
        ][:_MAX_CARD]
        notifs = alte + [_notif("incasso_mancante")]
        snap = _build_snapshot(notifs)
        # Il taglio lascia _MAX_CARD card, ma il dato mancante è comunque rilevato.
        assert len(snap["azioni"]) == _MAX_CARD
        assert snap["tutto_ok"] is False
        assert "l'incasso di ieri" in snap["dati_mancanti"]

    def test_task_non_dato_non_finisce_in_dati_mancanti(self):
        # Una scadenza è un task, NON un dato mancante: spegne il verde (c'è una card)
        # ma non entra nella lista dati_mancanti.
        snap = _build_snapshot([_notif("scadenza_superata", payload={"count": 2, "totale": 5.0})])
        assert snap["tutto_ok"] is False
        assert snap["dati_mancanti"] == []

    def test_onboarding_e_apertura_e_sopprime_le_altre(self):
        # Cliente nuovo: l'onboarding e' l'unica apertura; rientro/buona notizia
        # vengono soppressi. Non e' una card da fare e non produce il verde.
        from services.daily_briefing_service import _compose_narrative
        ob = _notif("onboarding", "info")
        snap = _build_snapshot([ob, _notif("rientro_assenza", "info"), _notif("buona_notizia", "success")])
        # Nessuna card (le aperture non sono to-do) ma nemmeno il verde.
        assert snap["azioni"] == []
        assert snap["tutto_ok"] is False
        assert "Benvenuto" in snap["narrative"]

    def test_dati_mancanti_deduplicati_e_ordinati(self):
        notifs = [
            _notif("fatture_mancanti"),
            _notif("fatturato_mancante"),
            _notif("fatture_mancanti"),  # duplicato
        ]
        snap = _build_snapshot(notifs)
        # Dedup mantenendo l'ordine di priorità (fatture_mancanti=35 < fatturato=40).
        assert snap["dati_mancanti"].count("le fatture costo") == 1
        assert snap["dati_mancanti"].index("le fatture costo") < snap["dati_mancanti"].index(
            "il fatturato del mese"
        )
