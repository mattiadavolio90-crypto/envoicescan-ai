"""Il contatore dei crediti conta SOLO le righe di chi chiede, sulla sede giusta.

Residuo della fase 2 del piano consulente (§5, «il piu' serio»): invertire il
filtro di proprieta' nel conteggio Python sopravviveva a tutti i test, perche' i
mock accettavano qualunque `eq()`. Dalla fase J (10/10/2026) il conteggio non e'
piu' in Python: lo fa la RPC `chat_crediti_stato`, e il suo isolamento fra
clienti e' provato su un Postgres vero con un secondo cliente rumoroso
(`tests/test_sql_chat_crediti.py`).

Qui resta la meta' Python: chi chiama passa alla RPC l'utente giusto e la sede
giusta — `None` (conteggio per account) solo per il pool multi-sede. Con la sede
al posto di None un account multi-sede vedrebbe il contatore di una sola sede
mentre la chat applica il pool (o viceversa).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw

U, A = "utente-u", "sede-a"


def _sb_rpc(data):
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value = MagicMock(data=data)
    return sb


@pytest.mark.parametrize("pool, sede_attesa", [(True, None), (False, A)])
def test_lo_stato_chiede_alla_rpc_utente_e_sede_giusti(pool, sede_attesa):
    sb = _sb_rpc({"oggi": 6, "mese": 30, "ricarica": 9})
    assert fw._chat_crediti_stato(U, A, pool, sb) == {"oggi": 6, "mese": 30, "ricarica": 9}
    nome, payload = sb.rpc.call_args.args
    assert nome == "chat_crediti_stato"
    assert payload == {"p_user_id": U, "p_ristorante_id": sede_attesa, "p_pool": pool}


def test_lo_stato_non_mostra_una_ricarica_negativa():
    """L'ultima domanda iniziata con un credito porta il saldo a -2: a schermo 0."""
    assert fw._chat_crediti_stato(U, A, False, _sb_rpc({"oggi": 3, "mese": 0, "ricarica": -2}))["ricarica"] == 0


@pytest.mark.parametrize("data", [None, 7, [], "x"])
def test_lo_stato_illeggibile_da_zeri(data):
    assert fw._chat_crediti_stato(U, A, False, _sb_rpc(data)) == {"oggi": 0, "mese": 0, "ricarica": 0}


def test_lo_stato_con_la_rpc_che_fallisce_da_zeri():
    sb = MagicMock()
    sb.rpc.side_effect = RuntimeError("rete")
    assert fw._chat_crediti_stato(U, A, False, sb) == {"oggi": 0, "mese": 0, "ricarica": 0}


@pytest.mark.parametrize("pool", [True, False])
def test_la_vista_passa_sede_e_pool_allo_stato(pool):
    with patch.object(fw, "_chat_quota_pool", return_value=(100, pool)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=1000), \
         patch.object(fw, "_chat_crediti_stato", return_value={"oggi": 3, "mese": 9, "ricarica": 0}) as stato:
        vista = fw._chat_crediti_vista({"id": U}, MagicMock(), A)
    assert stato.call_args.args[:3] == (U, A, pool)
    assert vista == {
        "limite_giorno": 100, "limite_mese": 1000, "pool": pool,
        "oggi": 3, "mese": 9, "ricarica": 0,
    }


def test_la_vista_a_piano_free_non_legge_niente():
    with patch.object(fw, "_chat_quota_pool", return_value=(0, False)), \
         patch.object(fw, "_chat_budget_mensile_pool") as mese, \
         patch.object(fw, "_chat_crediti_stato") as stato:
        vista = fw._chat_crediti_vista({"id": U}, MagicMock(), A)
    assert vista["limite_giorno"] == 0 and vista["limite_mese"] == 0
    mese.assert_not_called()
    stato.assert_not_called()


def _sb_config():
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "limit", "single", "upsert", "update", "insert"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    sb.table.return_value = q
    return sb


@pytest.mark.parametrize("pool", [True, False])
def test_la_home_passa_sede_e_pool_allo_stato(pool):
    """/api/home/config: il contatore della Home."""
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": U, "piano": "pro"}), \
         patch.object(fw, "_get_supabase_client", return_value=_sb_config()), \
         patch.object(fw, "_resolve_ristorante_id", return_value=A), \
         patch.object(fw, "_chat_quota_pool", return_value=(200, pool)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=2000), \
         patch.object(fw, "_chat_crediti_stato", return_value={"oggi": 0, "mese": 0, "ricarica": 0}) as stato:
        fw.home_config_get(authorization="Bearer t")
    assert stato.call_args.args[:3] == (U, A, pool)


@pytest.mark.parametrize("pool", [True, False])
def test_il_salvataggio_delle_impostazioni_passa_sede_e_pool_allo_stato(pool):
    """/api/home/config in POST ricalcola lo stesso contatore dopo il
    salvataggio: stessa regola della GET."""
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": U, "piano": "pro"}), \
         patch.object(fw, "_get_supabase_client", return_value=_sb_config()), \
         patch.object(fw, "_resolve_ristorante_id", return_value=A), \
         patch.object(fw, "_get_assistant_preferences", return_value={"topics_disabled": []}), \
         patch("services.settore_service.settore_utente", return_value="ristorazione"), \
         patch.object(fw, "_chat_quota_pool", return_value=(200, pool)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=2000), \
         patch.object(fw, "_chat_crediti_stato", return_value={"oggi": 0, "mese": 0, "ricarica": 0}) as stato:
        fw.home_config_post(fw.ConfigUpdateRequest(), authorization="Bearer t")
    assert stato.call_args.args[:3] == (U, A, pool)


def test_l_account_usa_la_stessa_vista_della_chat():
    """Impostazioni › Account: i numeri vengono da `_chat_crediti_vista`, la
    stessa della chat, con la sede attiva."""
    from services.routers import account
    vista = {"limite_giorno": 150, "limite_mese": 1500, "oggi": 6, "mese": 33, "ricarica": 120, "pool": True}
    sb = MagicMock()
    q = sb.table.return_value
    for m in ("select", "eq", "single", "is_", "gte"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data={"email": "a@b.it"})
    with patch.object(account, "_resolve_user_from_token", return_value={"id": U, "email": "a@b.it"}), \
         patch.object(account, "_get_supabase_client", return_value=sb), \
         patch.object(account, "_resolve_ristorante_id", return_value=A), \
         patch.object(account, "_is_admin_email", return_value=False), \
         patch.object(account, "_chat_crediti_vista", return_value=vista) as v:
        r = account.account_me(authorization="Bearer x")
    assert v.call_args.args[2] == A
    assert (r["chat_limite_giorno"], r["chat_limite_mese"]) == (150, 1500)
    assert (r["chat_crediti_oggi"], r["chat_crediti_mese"], r["chat_crediti_ricarica"]) == (6, 33, 120)
    assert r["chat_pool"] is True


def test_la_catena_conta_per_account():
    """/api/gruppo/chat-config: la vista con sede None, cioe' l'account intero."""
    from services.routers import gruppo
    vista = {"limite_giorno": 150, "limite_mese": 1500, "oggi": 6, "mese": 33, "ricarica": 120, "pool": True}
    with patch.object(gruppo, "_resolve_gruppo", return_value=(MagicMock(), U, [], "", {}, [])), \
         patch.object(gruppo, "_resolve_user_from_token", return_value={"id": U}), \
         patch.object(gruppo, "_gruppo_chat_disabilitata", return_value=False), \
         patch.object(gruppo, "_chat_crediti_vista", return_value=vista) as v:
        r = gruppo.gruppo_chat_config(authorization="Bearer x")
    assert v.call_args.args[2] is None
    assert r.enabled is True
    assert (r.limite_giorno, r.limite_mese) == (150, 1500)
    assert (r.crediti_oggi, r.crediti_mese, r.crediti_ricarica) == (6, 33, 120)


def test_la_catena_free_non_e_abilitata():
    from services.routers import gruppo
    vista = {"limite_giorno": 0, "limite_mese": 0, "oggi": 0, "mese": 0, "ricarica": 0, "pool": True}
    with patch.object(gruppo, "_resolve_gruppo", return_value=(MagicMock(), U, [], "", {}, [])), \
         patch.object(gruppo, "_resolve_user_from_token", return_value={"id": U}), \
         patch.object(gruppo, "_gruppo_chat_disabilitata", return_value=False), \
         patch.object(gruppo, "_chat_crediti_vista", return_value=vista):
        assert gruppo.gruppo_chat_config(authorization="Bearer x").enabled is False
