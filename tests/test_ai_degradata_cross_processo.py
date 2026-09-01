"""Fase 0 — le tre falle che ingannano (audit categorizzazione 1/9/2026).

Coprono difetti REALI misurati in produzione, non ipotesi:

D11 il flag "AI degradata" non attraversava il confine HTTP: `ai_degradata()` e' un
    ContextVar del processo chiamante, ma la classificazione avviene nel worker via
    POST. Il retry di `_auto_classify_saved_rows` usciva SEMPRE al primo giro
    credendo che l'AI avesse risposto, mentre poteva aver risposto il fallback
    deterministico. Il commento nel worker dichiarava il bug risolto: lo era solo
    nel ramo in-process (WORKER_BASE_URL vuoto).

D17 i fallback d'import del worker degradavano dizionario+regole forti a no-op con
    `except` muti: nessun log, nessun segnale. Unico sintomo un aumento di
    'Da Classificare', indistinguibile da un catalogo difficile.

D18 quando l'AI non rispondeva, al cliente veniva detto "dati insufficienti" —
    cioe' "la tua descrizione e' povera" — mentre la causa era tecnica.

NB: qui si prova la propagazione del flag, non la libreria HTTP: `requests.post` e'
sostituito, ma la logica sotto esame (lettura del campo, ri-segnalazione nel
processo locale, attribuzione della causa) e' quella vera.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from services.ai_service import ai_degradata, reset_ai_degradata


def _risposta(payload: dict, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    r.headers = {}
    return r


# ─────────────────────────── D11 ───────────────────────────

class TestDegradoAttraversaHTTP:
    """Il degrado avvenuto nel worker deve diventare visibile al chiamante."""

    def test_degradata_true_risegnalata_nel_processo_chiamante(self):
        import services.worker_client as wc

        payload = {
            "categorie": ["PESCE", "CARNE"], "confidenze": ["bassa", "bassa"],
            "count": 2, "elapsed_ms": 10, "degradata": True,
        }
        with patch.object(wc, "_worker_base_url", lambda: "http://worker-finto"), \
             patch.object(wc.requests, "post", lambda *a, **k: _risposta(payload)):
            reset_ai_degradata()
            assert ai_degradata() is False
            cats, confs = wc.classifica_via_worker_con_confidenza(["A", "B"])

        assert cats == ["PESCE", "CARNE"]
        # Il punto del test: senza il fix restava False e i retry non ripartivano.
        assert ai_degradata() is True

    def test_worker_sano_non_segnala_degrado(self):
        import services.worker_client as wc

        payload = {"categorie": ["PESCE"], "confidenze": ["alta"],
                   "count": 1, "elapsed_ms": 5, "degradata": False}
        with patch.object(wc, "_worker_base_url", lambda: "http://worker-finto"), \
             patch.object(wc.requests, "post", lambda *a, **k: _risposta(payload)):
            reset_ai_degradata()
            wc.classifica_via_worker_con_confidenza(["A"])

        assert ai_degradata() is False

    def test_worker_vecchio_senza_campo_resta_non_degradato(self):
        """Retrocompatibilita': durante un rollout worker e frontend non cambiano
        nello stesso istante. Un worker che non invia `degradata` non deve far
        credere che l'AI sia giu'."""
        import services.worker_client as wc

        payload = {"categorie": ["PESCE"], "confidenze": ["alta"],
                   "count": 1, "elapsed_ms": 5}  # nessun campo 'degradata'
        with patch.object(wc, "_worker_base_url", lambda: "http://worker-finto"), \
             patch.object(wc.requests, "post", lambda *a, **k: _risposta(payload)):
            reset_ai_degradata()
            wc.classifica_via_worker_con_confidenza(["A"])

        assert ai_degradata() is False

    def test_response_model_espone_il_campo(self):
        """Il contratto HTTP deve trasportare il flag, con default prudente."""
        from services.fastapi_worker import ClassifyResponse

        assert "degradata" in ClassifyResponse.model_fields
        vuota = ClassifyResponse(categorie=[], count=0, elapsed_ms=1)
        assert vuota.degradata is False


# ─────────────────────────── D17 ───────────────────────────

class TestImportDegradatiNonSilenziosi:
    def test_esiste_il_segnalatore_e_logga_a_error(self, caplog):
        """Un import fallito deve dichiararsi: prima erano `except` muti."""
        from worker import queue_processor as qp

        # La lista e' globale di modulo: la ripristiniamo, altrimenti questo test
        # sporca `test_in_condizioni_normali_nessun_import_degradato`.
        _prima = list(qp._IMPORT_DEGRADATI)
        try:
            with caplog.at_level(logging.ERROR):
                qp._segnala_import_degradato("funzione_x", RuntimeError("boom"))

            assert any(r.levelno >= logging.ERROR for r in caplog.records)
            testo = caplog.text
            assert "funzione_x" in testo
            # Deve dire la CONSEGUENZA, non solo la causa.
            assert "categorizzazione" in testo.lower()
            assert "funzione_x" in qp._IMPORT_DEGRADATI
        finally:
            qp._IMPORT_DEGRADATI[:] = _prima

    def test_in_condizioni_normali_nessun_import_degradato(self):
        """Su un ambiente sano la lista e' vuota: se questo test fallisce, il
        worker sta girando azzoppato e va indagato prima di guardare altro."""
        from worker.queue_processor import _IMPORT_DEGRADATI

        assert _IMPORT_DEGRADATI == []

    def test_il_runtime_deterministico_e_quello_vero(self):
        """Controprova del fallback: le funzioni importate devono classificare
        davvero, non essere gli stub che ritornano None/False."""
        from worker.queue_processor import (
            _categoria_deterministica_runtime,
            _runtime_conferma_categoria,
        )

        assert _categoria_deterministica_runtime("SALMONE AFFUMICATO 200G") == "PESCE"
        assert _runtime_conferma_categoria("SALMONE AFFUMICATO 200G", "PESCE") is True


# ─────────────────────────── D18 ───────────────────────────

class TestCausaVeraMostrataAlCliente:
    def test_guasto_ai_non_viene_riportato_come_dati_insufficienti(self):
        """La distinzione fra le due cause deve esistere nel sorgente: sono
        messaggi diversi per il cliente ('riprova' vs 'sistema la descrizione')."""
        from pathlib import Path

        src = Path("services/upload_handler.py").read_text(encoding="utf-8")
        assert "ai_non_raggiungibile" in src
        assert "_desc_errore_ai" in src

    def test_le_due_cause_sono_contate_separatamente(self):
        """Il ramo di errore AI incrementa la propria causa, non quella generica."""
        from pathlib import Path

        src = Path("services/upload_handler.py").read_text(encoding="utf-8")
        assert "remaining_reasons['ai_non_raggiungibile'] += 1" in src
        # e la causa generica resta per il caso vero (descrizione davvero povera)
        assert "remaining_reasons['dati_insufficienti'] += 1" in src
