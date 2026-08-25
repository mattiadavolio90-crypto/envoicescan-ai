"""Test guardia: gate permessi-pagina applicato ai DATI del prompt, non solo
ai tool (audit §3b chat, F4 — MEDIUM).

Difetto trovato (25/8/2026): il gate tool (_TOOL_FLAG in chat_ai) impedisce a
un utente senza 'margini' di chiamare query_margini, dichiarando esplicitamente
"chi non vede una pagina non puo' nemmeno interrogarne i dati via chat". Ma
_build_chat_system_prompt iniettava MOL/food cost/spese/alert SEMPRE, con
l'unica eccezione dell'agenda — l'invariante dichiarata dal codice era violata
dal codice stesso. Un utente senza 'margini' trovava gia' il MOL scritto nel
prompt anche se non poteva chiamare il tool per richiederlo.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from services.fastapi_worker import _build_chat_system_prompt

USER_SENZA_MARGINI = {
    "id": "u-test", "nome_ristorante": "TEST", "email": "t@x.it",
    "pagine_abilitate": {"margini": False, "analisi_fatture": True, "agenda": True},
}
USER_SENZA_FATTURE = {
    "id": "u-test", "nome_ristorante": "TEST", "email": "t@x.it",
    "pagine_abilitate": {"margini": True, "analisi_fatture": False, "agenda": True},
}
USER_TUTTO = {
    "id": "u-test", "nome_ristorante": "TEST", "email": "t@x.it",
    "pagine_abilitate": {"margini": True, "analisi_fatture": True, "agenda": True},
}
USER_ADMIN_NESSUN_FLAG = {"id": "u-admin", "nome_ristorante": "ADMIN", "email": "a@x.it"}


def _kpi_mock():
    return MagicMock(
        has_data=True, food_cost_pct=30.0, fatturato=10000.0,
        costo_personale=2000.0, spese_generali=1000.0, mol=3000.0,
        periodo_label="agosto 2026", confronto_label=None,
    )


def _sb_dati_puliti():
    """Nessun alert deve scattare, cosi' l'unica differenza osservabile tra i
    casi e' il gate sulla sezione KPI/top-list."""
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


def test_utente_senza_margini_non_vede_mol_ne_alert(monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    prompt = _build_chat_system_prompt(USER_SENZA_MARGINI, _sb_dati_puliti(), None, ristorante_id="rid-1")
    assert "MOL (margine operativo lordo)" not in prompt
    assert "€10,000.00" not in prompt
    assert "Avvisi fondamentali" not in prompt


def test_utente_con_margini_vede_mol(monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    prompt = _build_chat_system_prompt(USER_TUTTO, _sb_dati_puliti(), None, ristorante_id="rid-1")
    assert "MOL (margine operativo lordo)" in prompt


def test_utente_senza_analisi_fatture_non_vede_top_categorie(monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: MagicMock(has_data=False))
    top_cat_mock = MagicMock(return_value=([("CARNE", 500.0)], [("Fornitore X", 800.0)]))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", top_cat_mock)
    prompt = _build_chat_system_prompt(USER_SENZA_FATTURE, _sb_dati_puliti(), None, ristorante_id="rid-1")
    assert "Costi per categoria" not in prompt
    top_cat_mock.assert_not_called()


def test_utente_con_analisi_fatture_vede_top_categorie(monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: MagicMock(has_data=False))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([("CARNE", 500.0)], [("Fornitore X", 800.0)]))
    prompt = _build_chat_system_prompt(USER_TUTTO, _sb_dati_puliti(), None, ristorante_id="rid-1")
    assert "Costi per categoria" in prompt


def test_admin_senza_pagine_abilitate_vede_tutto(monkeypatch):
    """pagine_abilitate assente (admin/nessun flag impostato) => nessun gate,
    coerente col comportamento gia' esistente per l'agenda e per i tool."""
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([("CARNE", 500.0)], []))
    prompt = _build_chat_system_prompt(USER_ADMIN_NESSUN_FLAG, _sb_dati_puliti(), None, ristorante_id="rid-1")
    assert "MOL (margine operativo lordo)" in prompt
    assert "Costi per categoria" in prompt
