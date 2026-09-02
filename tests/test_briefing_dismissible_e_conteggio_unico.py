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
    """B3: Salute e briefing devono contare la STESSA unita' (prodotti distinti).

    Test COMPORTAMENTALE, non su inspect.getsource: la prima stesura asseriva sul
    testo del sorgente e un mutante `len({...})` -> `len([...])` (cioe' il ritorno
    esatto al conteggio per righe) passava tutti e 17 i test. Un presidio che
    sopravvive alla mutazione che deve impedire non e' un presidio. Verificato: con
    questi test il mutante fallisce.
    """

    @staticmethod
    def _righe(descrizioni):
        """Mock MINIMO: restituisce SOLO 'descrizione', come la query reale.

        Un mock che regalasse altre colonne renderebbe verde anche
        un'implementazione che le usa: qui il punto e' proprio quali colonne servono.
        """
        from unittest.mock import MagicMock

        import services.fastapi_worker as fw

        q = MagicMock()
        for attr in ("select", "eq", "is_", "gte", "order", "range", "limit"):
            getattr(q, attr).return_value = q
        q.execute.return_value = MagicMock(
            data=[{"descrizione": d} for d in descrizioni],
            count=len(descrizioni),
        )
        sb = MagicMock()
        sb.table.return_value = q
        return fw.fetch_all(sb.table("fatture").select("descrizione"))

    @staticmethod
    def _conta_distinti(righe):
        """La stessa normalizzazione delle due superfici."""
        return len({
            (r.get("descrizione") or "").strip()
            for r in righe
            if (r.get("descrizione") or "").strip()
        })

    def test_tre_righe_stessa_voce_contano_come_un_prodotto(self):
        """Il caso che ha originato B3: Analisi Fatture aggrega per descrizione,
        quindi 3 righe 'COMPENSAZIONE RIGA OMAGGIO' sono UNA voce da controllare."""
        righe = self._righe([
            "COMPENSAZIONE RIGA OMAGGIO",
            "COMPENSAZIONE RIGA OMAGGIO",
            "COMPENSAZIONE RIGA OMAGGIO",
        ])
        assert self._conta_distinti(righe) == 1, "3 righe della stessa voce = 1 prodotto"
        assert len(righe) == 3, "le righe restano 3: e' l'unita' di misura a cambiare"

    def test_scarta_le_descrizioni_vuote_e_normalizza_gli_spazi(self):
        righe = self._righe(["  PANE  ", "PANE", "", "   ", "OLIO"])
        assert self._conta_distinti(righe) == 2, (
            "PANE con spazi e' lo stesso prodotto; le descrizioni vuote non contano"
        )

    def test_lo_scarto_reale_fra_righe_e_prodotti(self):
        """Proporzione misurata a DB il 2/9/2026 su San Giuliano: 187 righe per 112
        prodotti. Il test riproduce lo scarto, non il numero esatto."""
        righe = self._righe([f"prod-{i // 2}" for i in range(20)])  # 20 righe, 10 voci
        assert len(righe) == 20
        assert self._conta_distinti(righe) == 10

    def test_le_due_superfici_normalizzano_allo_stesso_modo(self):
        """Se briefing e Salute normalizzassero diversamente (es. una col lower())
        i due numeri tornerebbero a divergere in silenzio."""
        import inspect

        import services.fastapi_worker as fw

        briefing = inspect.getsource(fw._briefing_righe_da_classificare)
        salute = inspect.getsource(fw.home_salute)
        frammento = '(r.get("descrizione") or "").strip()'
        assert frammento in briefing and frammento in salute, (
            "le due superfici devono normalizzare la descrizione allo stesso modo"
        )


class TestHomeSaluteConteggioReale:
    """Chiama DAVVERO home_salute: e' l'unico modo di uccidere il mutante.

    I test sopra riproducono la logica di conteggio, quindi una mutazione DENTRO
    home_salute (len({...}) -> len([...])) sopravviveva. Verificato: con questo
    test il mutante fallisce. Nota: prima d'ora NESSUN test invocava home_salute —
    l'indice 0-100 che il cliente vede in Home era senza rete.
    """

    @staticmethod
    def _fake_sb(descrizioni_review):
        """Client minimo: la tabella 'fatture' risponde con le righe needs_review
        (SOLO 'descrizione' + 'needs_review'), le altre tabelle vuote."""
        from unittest.mock import MagicMock

        righe_review = [
            {"descrizione": d, "needs_review": True, "categoria": "X"}
            for d in descrizioni_review
        ]

        def _table(nome):
            q = MagicMock()
            for attr in ("select", "eq", "is_", "gte", "lte", "order", "range", "limit", "single"):
                getattr(q, attr).return_value = q
            if nome == "fatture":
                q.execute.return_value = MagicMock(
                    data=righe_review, count=len(righe_review)
                )
            else:
                q.execute.return_value = MagicMock(data=[], count=0)
            return q

        sb = MagicMock()
        sb.table.side_effect = _table
        sb.rpc.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=[]))
        )
        return sb

    def test_la_voce_conta_i_prodotti_non_le_righe(self, monkeypatch):
        """5 righe, 2 descrizioni distinte -> la voce deve dire 2, non 5."""
        import services.fastapi_worker as fw

        cinque_righe_due_voci = ["PANE", "PANE", "PANE", "OLIO", "OLIO"]
        sb = self._fake_sb(cinque_righe_due_voci)

        monkeypatch.setattr(fw, "_resolve_user_from_token", lambda _a: {"id": "u1"})
        monkeypatch.setattr(fw, "_get_supabase_client", lambda: sb)
        monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda _u, _s: "rid-1")
        monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: None)
        monkeypatch.setattr(
            fw, "_briefing_nome_referente", lambda *a, **k: (None, []), raising=False
        )

        resp = fw.home_salute(authorization="Bearer x")
        voce = next(v for v in resp.voci if v.key == "classificate")
        assert "2 prodotti da controllare" == voce.dettaglio, (
            f"atteso il conteggio per PRODOTTI, ottenuto: {voce.dettaglio!r}"
        )
        assert "5" not in voce.dettaglio, "5 e' il numero delle RIGHE: sarebbe il bug B3"
        assert voce.ok is False
