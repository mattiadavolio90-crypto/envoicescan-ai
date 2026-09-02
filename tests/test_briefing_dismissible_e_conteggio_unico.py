"""B1 + B3: chi decide se una card si puo' ignorare, e con che unita' si conta.

B1 — Il briefing offriva "Ignora" su segnali LIVE che tornano al refresh. La lista
dei non-ignorabili viveva DUPLICATA nel frontend (briefing-shared.ts) ed era gia'
divergente dal backend: le mancava `coperti_anomalia`, che infatti mostrava un
bottone che non ignorava nulla. Ora la decisione viaggia nel campo `dismissible`
dell'azione, da una lista canonica unica.

B3 — La card Salute contava le RIGHE needs_review, il briefing i PRODOTTI DISTINTI:
sulla stessa schermata comparivano due numeri per la stessa cosa. Misurato il
2/9/2026: 187 vs 112 (San Giuliano), 156 vs 100 (Villa Guardia), 80 vs 37 (costi di
gruppo), 45 vs 29 (LAND).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.daily_briefing_service import (  # noqa: E402
    TOPIC_LIVE_NON_IGNORABILI,
    _action_for,
    _build_snapshot,
)


class TestDismissibileDecisoDalBackend:
    @pytest.mark.parametrize("topic", sorted(TOPIC_LIVE_NON_IGNORABILI))
    def test_i_segnali_live_non_si_possono_ignorare(self, topic):
        azione = _action_for(
            {"id": "x", "topic_key": topic, "severity": "warning", "title": "t", "payload": {}}
        )
        assert azione["dismissible"] is False, (
            f"{topic} e' ricalcolato live: 'Ignora' tornerebbe al refresh"
        )

    @pytest.mark.parametrize("topic", [
        "scadenza_superata", "scadenza_imminente",
        "appuntamento_imminente", "upload_failed", "price_alert",
    ])
    def test_gli_altri_topic_restano_ignorabili(self, topic):
        azione = _action_for(
            {"id": "x", "topic_key": topic, "severity": "warning", "title": "t", "payload": {}}
        )
        assert azione["dismissible"] is True

    def test_coperti_anomalia_e_il_caso_che_era_rotto(self):
        """Era l'unico topic live assente dalla lista frontend: la card mostrava
        'Ignora', l'utente lo premeva e la card tornava al refresh."""
        assert "coperti_anomalia" in TOPIC_LIVE_NON_IGNORABILI
        azione = _action_for(
            {"id": "x", "topic_key": "coperti_anomalia", "severity": "info",
             "title": "Ieri 120 coperti", "payload": {}}
        )
        assert azione["dismissible"] is False

    def test_il_campo_arriva_in_ogni_azione_dello_snapshot(self):
        """Il frontend legge azione.dismissible: deve esserci sempre, o ricade
        sulla lista legacy."""
        notifs = [
            {"id": "1", "topic_key": "uncategorized_rows", "severity": "warning",
             "title": "t", "payload": {"count": 5, "uncategorized_rows": 5, "totale": 5}},
            {"id": "2", "topic_key": "scadenza_superata", "severity": "error",
             "title": "t", "payload": {"count": 2, "totale": 100.0}},
        ]
        snap = _build_snapshot(notifs, use_ai=False)
        assert snap["azioni"], "servono azioni per il test"
        for a in snap["azioni"]:
            assert "dismissible" in a, f"campo mancante su {a['topic_key']}"
            assert isinstance(a["dismissible"], bool)


class TestUnaSolaFonteDeiTopicLive:
    def test_il_worker_riusa_la_lista_del_servizio(self):
        """Se qualcuno ridefinisce la lista nel worker invece di importarla, le due
        superfici tornano a divergere in silenzio come prima."""
        import services.fastapi_worker as fw

        assert fw._LIVE_TOPICS_DATI_MANCANTI is TOPIC_LIVE_NON_IGNORABILI, (
            "il worker deve IMPORTARE la lista canonica, non ridefinirla"
        )

    def test_la_lista_copre_tutti_i_topic_ricalcolati_live(self):
        attesi = {
            "fatturato_mancante", "costo_personale_mancante", "incasso_mancante",
            "uncategorized_rows", "fatture_mancanti", "coperti_anomalia",
        }
        assert set(TOPIC_LIVE_NON_IGNORABILI) == attesi


class TestConteggioUnicoSaluteBriefing:
    """B3: Salute e briefing devono contare la STESSA unita' (prodotti distinti)."""

    def test_la_salute_conta_prodotti_distinti_non_righe(self):
        """Il caso reale: 3 righe della stessa voce = 1 prodotto in Analisi Fatture.
        Se la Salute contasse le righe direbbe 3 dove il briefing dice 1."""
        import inspect

        import services.fastapi_worker as fw

        src = inspect.getsource(fw.home_salute)
        blocco = src[src.index("Conteggio MOSTRATO al cliente"):]
        blocco = blocco[: blocco.index("classificate_ok")]
        assert 'select("descrizione")' in blocco, (
            "la voce deve leggere le descrizioni per contare i prodotti distinti"
        )
        assert 'select("id", count="exact")' not in blocco, (
            "contare le righe fa divergere Salute e briefing (187 vs 112 su San Giuliano)"
        )

    def test_il_fallback_non_produce_un_falso_verde(self):
        """Se la query autorevole fallisce, il ripiego NON deve dare 0: righe_mese
        non porta 'descrizione', quindi contare i distinti li' darebbe sempre zero
        = 'tutto classificato' proprio mentre il dato non e' disponibile."""
        import inspect

        import services.fastapi_worker as fw

        src = inspect.getsource(fw.home_salute)
        blocco = src[src.index("conteggio prodotti da controllare fallito"):]
        blocco = blocco[: blocco.index("classificate_ok")]
        assert 'sum(1 for r in righe_mese if r.get("needs_review"))' in blocco, (
            "il fallback deve contare le righe recenti, non i distinti di righe_mese"
        )
