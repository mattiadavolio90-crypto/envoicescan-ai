"""Test guardia: fail-open di _build_chat_system_prompt su errore tecnico
(audit §3b chat, F2 — MEDIUM).

Difetto trovato (25/8/2026): se una sezione del prompt falliva per un guasto
infrastrutturale (Supabase lento, RPC assente, timeout), il fallback finale
diceva "Nessun dato di costo o margine ancora registrato" — un'affermazione
POSITIVA sul cliente che il codice non aveva alcun modo di verificare. Il
modello avrebbe detto con sicurezza a un cliente con storico reale che non ha
registrato nulla, solo perche' la query era fallita.

Caso peggiore misurato: se falliscono solo gli alert (KPI presenti), il
modello riporta food cost/MOL come definitivi senza sapere che un controllo
e' saltato.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw
from services.fastapi_worker import _build_chat_system_prompt

FRASE_NESSUN_DATO = "Nessun dato di costo o margine ancora registrato"
FRASE_ERRORE_TECNICO = "problema tecnico"

USER = {"id": "u-test", "nome_ristorante": "TEST", "email": "t@x.it"}


def _sb_nessun_alert():
    """Nessun errore, e ogni alert trova dati sufficienti per NON scattare:
    fatture presenti nel mese (alert 1/5), ricavi/personale/spese > 0
    (alert 2/3/5), 0 righe categoria='Da Classificare' (alert 7)."""
    sb = MagicMock()
    state = {"table": None, "filters": {}}

    def _table(name):
        state["table"] = name
        state["filters"] = {}
        return q

    def _eq(field, value):
        state["filters"][field] = value
        return q

    def _execute():
        t = state["table"]
        if t == "fatture":
            if "categoria" in state["filters"]:
                return MagicMock(data=[], count=0)
            # alert 1 (fatture mese) e alert 5 (spese auto): presenti
            return MagicMock(data=[{"id": 1}], count=3)
        if t == "margini_mensili":
            return MagicMock(data=[{
                "fatturato_iva10": 1000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
                "costo_dipendenti": 500, "costo_personale_extra": 0,
                "altri_costi_spese": 100,
            }], count=None)
        return MagicMock(data=[], count=0)

    q = MagicMock()
    sb.table.side_effect = _table
    for m in ("select", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.eq.side_effect = _eq
    q.execute.side_effect = _execute
    return sb


def _sb_query_fallita():
    sb = MagicMock()
    q = MagicMock()

    def _execute():
        raise RuntimeError("connessione persa")

    for m in ("select", "eq", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.side_effect = _execute
    sb.table.return_value = q
    return sb


def test_kpi_home_fallito_non_dice_nessun_dato_registrato(monkeypatch):
    """home_kpi solleva E tutte le altre sezioni falliscono: il fallback deve
    dichiarare l'errore tecnico, non affermare che il cliente non ha dati."""
    monkeypatch.setattr(fw, "home_kpi", MagicMock(side_effect=RuntimeError("timeout")))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    prompt = _build_chat_system_prompt(USER, _sb_query_fallita(), None, ristorante_id="rid-1")
    assert FRASE_NESSUN_DATO not in prompt
    assert FRASE_ERRORE_TECNICO in prompt


def test_dati_veramente_assenti_dice_nessun_dato_registrato(monkeypatch):
    """Nessun errore, nessuna sezione produce testo: qui il fallback ottimistico
    e' corretto e deve restare (altrimenti il fix avrebbe eliminato il messaggio
    buono, non solo quello sbagliato)."""
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: MagicMock(has_data=False))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    prompt = _build_chat_system_prompt(USER, _sb_nessun_alert(), None, ristorante_id="rid-1")
    assert FRASE_NESSUN_DATO in prompt
    assert FRASE_ERRORE_TECNICO not in prompt


def test_solo_kpi_home_fallito_altro_ok_dichiara_errore_tecnico(monkeypatch):
    """Isola il flag sul PRIMO except (home_kpi): se solo quello fallisce e
    tutto il resto ha dati regolari, il fallback deve comunque riconoscere
    che una sezione e' saltata — non basta che gli altri except marchino il
    flag, il primo deve farlo anche da solo."""
    monkeypatch.setattr(fw, "home_kpi", MagicMock(side_effect=RuntimeError("timeout")))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    prompt = _build_chat_system_prompt(USER, _sb_nessun_alert(), None, ristorante_id="rid-1")
    assert FRASE_NESSUN_DATO not in prompt
    assert FRASE_ERRORE_TECNICO in prompt


def test_solo_top_categorie_fallito_altro_ok_dichiara_errore_tecnico(monkeypatch):
    """B4 (code-reviewer): isola il flag sull'except della sezione 2
    (_chat_top_cat_forn). Se solo quella salta e tutto il resto ha dati
    regolari, il prompt deve comunque dire che un controllo non e' passato —
    senza il flag qui, il fallback tornava al messaggio ottimistico."""
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: MagicMock(has_data=False))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", MagicMock(side_effect=RuntimeError("rpc giu'")))
    prompt = _build_chat_system_prompt(USER, _sb_nessun_alert(), None, ristorante_id="rid-1")
    assert FRASE_NESSUN_DATO not in prompt
    assert FRASE_ERRORE_TECNICO in prompt


def test_kpi_presenti_ma_alert_falliti_avvisa_di_non_fidarsi(monkeypatch):
    """Il caso piu' subdolo: KPI Home OK, ma il blocco alert (query fatture)
    solleva. Senza avviso, l'assenza di alert sembra 'tutto a posto'."""
    kpi_mock = MagicMock(
        has_data=True, food_cost_pct=30.0, fatturato=10000.0,
        costo_personale=2000.0, spese_generali=1000.0, mol=3000.0,
        periodo_label="agosto 2026", confronto_label=None,
    )
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: kpi_mock)
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    prompt = _build_chat_system_prompt(USER, _sb_query_fallita(), None, ristorante_id="rid-1")
    assert "MOL" in prompt  # i KPI sono presenti
    assert "controlli sui dati mancanti non sono stati eseguibili" in prompt
