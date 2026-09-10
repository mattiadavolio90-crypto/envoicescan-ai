"""La memoria globale resta dei ristoranti (RETAIL_FASI.md 1.5): 2 scritture, 3 letture.

Scritture: lo streak del worker (`aggiorna_streak_classificazione`) e la
promozione admin (`salva_correzione_in_memoria_globale`) non partono per un
account retail. Letture: `ottieni_categoria_prodotto` (percorso PDF/Vision, legge
la memoria in proprio) ha lo stesso gate di `categorizza_con_memoria`;
`ottieni_hint_per_ai` non inietta un hint dei ristoranti nel prompt di un
negozio; la lettura L3 dentro `categorizza_con_memoria` e' gia' coperta dal gate
di `_ret` (1.3). Piu' il cablaggio: upload post-AI e Vision passano il settore.
"""
from __future__ import annotations

import copy
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.ai_service as ai
import services.routers.admin as admin
import services.settore_service as ss
import services.upload_handler as uh
import worker.queue_processor as qp
from tests.test_invoice_vision import PAYLOAD_OK, _FakeOpenAI, _file
from tests.test_retail_sede_tipo_attivita import _FakeSB as _AdminSB
from tests.test_worker_guardrail_note import FakeSB as _WorkerSB

UTENTE = "u-retail"


@pytest.fixture
def memoria():
    ai.invalida_cache_memoria()
    with ai._cache_lock:
        ai._memoria_cache["prodotti_utente"][UTENTE] = {"BISTECCA DI MANZO": "CARNE", "SCAFFALE METALLICO": "MANUTENZIONE E ATTREZZATURE"}
        ai._memoria_cache["prodotti_utente_norm"][UTENTE] = {
            ai.get_descrizione_normalizzata_e_originale(d)[0]: c
            for d, c in ai._memoria_cache["prodotti_utente"][UTENTE].items()
        }
        ai._memoria_cache["prodotti_master_hint"] = {
            ai.get_descrizione_normalizzata_e_originale("NOCE DI MANZO")[0]: "CARNE"
        }
        ai._memoria_cache["loaded"] = True
        ai._memoria_cache["_loaded_at"] = time.time()
        ai._memoria_cache["_loaded_user_ids"] = {UTENTE}
    yield
    ai.invalida_cache_memoria()


# ── scrittura 1: lo streak del worker ────────────────────────────────────────

def _worker(settore):
    rows = [{"id": 1, "descrizione": "CACCIAVITE TORX", "fornitore": "X", "iva_percentuale": 22,
             "totale_riga": 15.0, "categoria": None}]
    sb = _WorkerSB(rows)
    with patch.object(qp, "classifica_via_worker_con_confidenza", return_value=(["MATERIALE DI CONSUMO"], ["alta"])), \
         patch.object(qp, "aggiorna_streak_classificazione") as streak, \
         patch.object(qp, "filter_active", side_effect=lambda q: q), \
         patch.object(ss, "settore_utente", return_value=settore):
        qp._auto_classify_saved_rows(supabase=sb, user_id="u1", ristorante_id="r1", nome_file="F.xml")
    return sb, streak


def test_retail_la_riga_si_scrive_ma_lo_streak_non_tocca_la_memoria_globale():
    sb, streak = _worker("retail")
    assert sb._rows[0]["categoria"] == "MATERIALE DI CONSUMO"
    assert streak.call_count == 0


def test_per_i_ristoranti_lo_streak_scrive_come_prima():
    sb, streak = _worker("ristorazione")
    # "CACCIAVITE" ha una regola forte: l'override del runtime scavalca l'AI (come oggi).
    assert sb._rows[0]["categoria"] == "MANUTENZIONE E ATTREZZATURE"
    assert streak.call_count == 1


# ── scrittura 2: la promozione admin ─────────────────────────────────────────

def _promuovi(monkeypatch, settore):
    fake = _AdminSB([])
    fake.tables["prodotti_utente"] = [{"id": "loc-1", "descrizione": "MARTELLO", "categoria": "ARTICOLO DI VENDITA", "user_id": UTENTE}]
    fake.tables["prodotti_master"] = []
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: fake)
    chiamate: list = []
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: chiamate.append(uid) or settore)
    salva = MagicMock(return_value=True)
    monkeypatch.setattr(ai, "salva_correzione_in_memoria_globale", salva)
    monkeypatch.setattr(admin, "_log_review_action", lambda *a, **k: None)
    body = admin.RisolviConflittoBody(local_id="loc-1", azione="promuovi")
    return lambda: admin.admin_qualita_risolvi_conflitto(body, admin_user={"email": "md@oneflux.it"}), salva, chiamate


def test_una_voce_retail_non_si_promuove_nella_memoria_globale(monkeypatch):
    esegui, salva, chiamate = _promuovi(monkeypatch, "retail")
    with pytest.raises(HTTPException) as exc:
        esegui()
    assert exc.value.status_code == 400
    assert chiamate == [UTENTE]
    assert salva.call_count == 0


def test_una_voce_di_un_ristorante_si_promuove_come_prima(monkeypatch):
    esegui, salva, _ = _promuovi(monkeypatch, "ristorazione")
    esegui()
    assert salva.call_count == 1
    assert salva.call_args.kwargs["descrizione"] == "MARTELLO"


# ── lettura: ottieni_categoria_prodotto (PDF/Vision) ─────────────────────────

def test_retail_ottieni_categoria_prodotto_non_esce_in_food(memoria):
    assert ai.ottieni_categoria_prodotto("BISTECCA DI MANZO", UTENTE, settore="retail") == "Da Classificare"
    assert ai.ultima_provenienza() == ("nessuna", None)
    assert ai.ottieni_categoria_prodotto("SCAFFALE METALLICO", UTENTE, settore="retail") == "MANUTENZIONE E ATTREZZATURE"


@pytest.mark.parametrize("settore", [None, "ristorazione"])
def test_ottieni_categoria_prodotto_per_i_ristoranti_e_quello_di_prima(memoria, settore):
    assert ai.ottieni_categoria_prodotto("BISTECCA DI MANZO", UTENTE, settore=settore) == "CARNE"
    assert ai.ultima_provenienza() == ("L2_locale", "certa")


# ── lettura: l'hint nel prompt GPT ───────────────────────────────────────────

def test_retail_nessun_hint_dalla_memoria_globale(memoria):
    assert ai.ottieni_hint_per_ai("NOCE DI MANZO", UTENTE, settore="retail") is None
    assert ai.ottieni_hint_per_ai("NOCE DI MANZO", UTENTE) == "CARNE"
    assert ai.ottieni_hint_per_ai("NOCE DI MANZO", UTENTE, settore="ristorazione") == "CARNE"


# ── cablaggio: upload post-AI e Vision ───────────────────────────────────────

def test_l_upload_post_ai_passa_il_settore_all_hint(monkeypatch):
    rows = [{"id": 1, "descrizione": "MARTELLO 500G", "categoria": "Da Classificare", "fornitore": "X",
             "iva_percentuale": 22, "totale_riga": 10.0, "prezzo_unitario": 10.0, "quantita": 1,
             "needs_review": True, "file_origine": "f.xml", "tipo_documento": "TD01"},
            {"id": 2, "descrizione": "VITI 4X40", "categoria": "Da Classificare", "fornitore": "X",
             "iva_percentuale": 22, "totale_riga": 5.0, "prezzo_unitario": 5.0, "quantita": 1,
             "needs_review": True, "file_origine": "f.xml", "tipo_documento": "TD01"}]
    monkeypatch.setattr(uh, "fetch_all", lambda _q: rows)
    monkeypatch.setattr(uh, "carica_memoria_completa", lambda *a, **k: None)
    hint_kw: list = []
    monkeypatch.setattr(uh, "ottieni_hint_per_ai", lambda d, uid, **kw: hint_kw.append(kw) or None)
    monkeypatch.setattr(uh, "classifica_via_worker_con_confidenza",
                        lambda descrizioni, *a, **k: (["ARTICOLO DI VENDITA"] * len(descrizioni), ["alta"] * len(descrizioni)))
    monkeypatch.setattr("services.db_service.aggiorna_categoria_fatture", lambda *a, **k: 0)
    chiamate: list = []
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: chiamate.append(uid) or "retail")

    uh._run_post_upload_ai_categorization(MagicMock(), UTENTE, ["f.xml"], ristorante_id="r1")

    assert chiamate == [UTENTE]
    assert hint_kw and all(kw == {"settore": "retail"} for kw in hint_kw)


def test_il_percorso_vision_passa_il_settore():
    from services.invoice_service import estrai_dati_da_scontrino_vision

    payload = copy.deepcopy(PAYLOAD_OK)
    seconda = copy.deepcopy(payload["righe"][0])
    seconda["descrizione"] = "SECONDA RIGA"
    payload["righe"].append(seconda)
    sess = {"user_data": {"id": UTENTE}, "ristorante_id": "rist-1"}
    st_finto = MagicMock()
    st_finto.session_state.get = lambda k, d=None: sess.get(k, d)
    ricevuti: list = []
    chiamate: list = []

    def _ocp(descrizione, user_id, supabase_client=None, settore=None):
        ricevuti.append(settore)
        return "Da Classificare"

    with patch("services.invoice_service.st", st_finto), \
         patch("services.invoice_service.converti_in_base64", return_value="ZmFrZQ=="), \
         patch("services.ai_service.carica_memoria_completa", return_value=None), \
         patch("services.ai_service.ottieni_categoria_prodotto", side_effect=_ocp), \
         patch("services.ai_cost_service.track_ai_usage", MagicMock()), \
         patch.object(ss, "settore_utente", side_effect=lambda uid, supabase_client=None: chiamate.append(uid) or "retail"):
        righe = estrai_dati_da_scontrino_vision(_file(), _FakeOpenAI(json.dumps(payload)))

    assert len(righe) == 2
    assert chiamate == [UTENTE]
    assert ricevuti == ["retail", "retail"]
