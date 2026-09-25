"""Il conteggio delle domande alla chat conta SOLO le righe di chi chiede.

Residuo della fase 2 del piano consulente (§5, «il piu' serio»): invertire il
filtro di proprieta' in `_chat_domande_oggi` / `_chat_domande_mese`
(`eq("ristorante_id")` <-> `eq("user_id")`) sopravviveva a tutti i test, perche'
i mock accettavano qualunque `eq()` e restituivano se stessi. In produzione
sarebbe un contatore che mescola i clienti: «ti restano N domande» calcolato
sulle domande di qualcun altro.

Qui il finto database applica DAVVERO i filtri, conosce una sola tabella
(`chat_usage_log`) e contiene righe di due clienti e di due sedi dello stesso
cliente, dentro e fuori dalle finestre di Roma. E si prova che chi chiama passa
la sede giusta: `None` (conteggio per utente) solo per il pool multi-sede.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

import services.fastapi_worker as fw

ROMA = ZoneInfo("Europe/Rome")
U, X = "utente-u", "utente-x"          # due clienti
A, B, C = "sede-a", "sede-b", "sede-c"  # A e B di U, C di X


class _Q:
    def __init__(self, righe):
        self.righe, self.filtri = righe, []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append(lambda r: r.get(col) == val)
        return self

    def gte(self, col, val):
        soglia = datetime.fromisoformat(val)
        self.filtri.append(lambda r: r[col] >= soglia)
        return self

    def execute(self):
        n = sum(1 for r in self.righe if all(f(r) for f in self.filtri))
        return type("R", (), {"count": n, "data": []})()


class _DB:
    """Conosce solo `chat_usage_log`: leggere un'altra tabella e' un errore."""

    def __init__(self, righe):
        self.righe = righe

    def table(self, nome):
        if nome != "chat_usage_log":
            raise AssertionError(f"tabella inattesa: {nome}")
        return _Q(self.righe)


def _finestre():
    adesso = datetime.now(ROMA)
    inizio_giorno = datetime.combine(adesso.date(), time.min, tzinfo=ROMA)
    inizio_mese = inizio_giorno.replace(day=1)
    return inizio_giorno, inizio_mese


def _righe():
    inizio_giorno, inizio_mese = _finestre()
    oggi = inizio_giorno + timedelta(seconds=1)
    ieri = inizio_giorno - timedelta(seconds=1)
    mese_prima = inizio_mese - timedelta(seconds=1)
    righe = []

    def metti(n, user, sede, quando):
        righe.extend({"user_id": user, "ristorante_id": sede, "created_at": quando} for _ in range(n))

    metti(2, U, A, oggi)
    metti(1, U, B, oggi)
    metti(4, X, C, oggi)            # l'altro cliente, lo stesso giorno
    metti(5, U, A, ieri)
    metti(7, U, A, mese_prima)
    return righe


def _ieri_nel_mese():
    inizio_giorno, inizio_mese = _finestre()
    return (inizio_giorno - timedelta(seconds=1)) >= inizio_mese


# ── Oggi ────────────────────────────────────────────────────────────────────

def test_oggi_per_sede_conta_solo_quella_sede():
    assert fw._chat_domande_oggi(A, U, _DB(_righe())) == 2
    assert fw._chat_domande_oggi(B, U, _DB(_righe())) == 1


def test_oggi_in_pool_conta_tutte_le_sedi_dell_utente_e_nessun_altro():
    assert fw._chat_domande_oggi(None, U, _DB(_righe())) == 3


def test_oggi_l_altro_cliente_vede_solo_le_sue():
    assert fw._chat_domande_oggi(C, X, _DB(_righe())) == 4
    assert fw._chat_domande_oggi(None, X, _DB(_righe())) == 4


# ── Mese ────────────────────────────────────────────────────────────────────

def test_mese_per_sede_e_per_utente():
    ieri = 5 if _ieri_nel_mese() else 0
    assert fw._chat_domande_mese(A, U, _DB(_righe())) == 2 + ieri
    assert fw._chat_domande_mese(None, U, _DB(_righe())) == 3 + ieri
    assert fw._chat_domande_mese(None, X, _DB(_righe())) == 4


# ── Chi chiama passa la sede giusta ─────────────────────────────────────────

@pytest.mark.parametrize("pool, sede_attesa", [(True, None), (False, A)])
def test_la_vista_della_quota_conta_per_utente_solo_in_pool(pool, sede_attesa):
    with patch.object(fw, "_chat_quota_pool", return_value=(20, pool)), \
         patch.object(fw, "_chat_domande_oggi", return_value=0) as conta:
        fw._chat_quota_view({"id": U}, MagicMock(), A)
    assert conta.call_args.args[:2] == (sede_attesa, U)


def _sb_config():
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "limit", "single", "upsert", "update", "insert"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    sb.table.return_value = q
    return sb


@pytest.mark.parametrize("pool, sede_attesa", [(True, None), (False, A)])
def test_la_home_conta_per_utente_solo_in_pool(pool, sede_attesa):
    """/api/home/config: il «ti restano N» della Home. Con la sede al posto di
    None, un account multi-sede vedrebbe il contatore di una sola sede mentre
    la chat applica il pool (o viceversa)."""
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": U, "piano": "pro"}), \
         patch.object(fw, "_get_supabase_client", return_value=_sb_config()), \
         patch.object(fw, "_resolve_ristorante_id", return_value=A), \
         patch.object(fw, "_chat_quota_pool", return_value=(20, pool)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=600), \
         patch.object(fw, "_chat_domande_oggi", return_value=0) as oggi, \
         patch.object(fw, "_chat_domande_mese", return_value=0) as mese:
        fw.home_config_get(authorization="Bearer t")
    assert oggi.call_args.args[:2] == (sede_attesa, U)
    assert mese.call_args.args[:2] == (sede_attesa, U)


@pytest.mark.parametrize("pool, sede_attesa", [(True, None), (False, A)])
def test_il_salvataggio_delle_impostazioni_conta_per_utente_solo_in_pool(pool, sede_attesa):
    """/api/home/config in POST ricalcola lo stesso contatore dopo il
    salvataggio: stessa regola della GET (mutanti sopravvissuti prima di
    questo test)."""
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": U, "piano": "pro"}), \
         patch.object(fw, "_get_supabase_client", return_value=_sb_config()), \
         patch.object(fw, "_resolve_ristorante_id", return_value=A), \
         patch.object(fw, "_get_assistant_preferences", return_value={"topics_disabled": []}), \
         patch("services.settore_service.settore_utente", return_value="ristorazione"), \
         patch.object(fw, "_chat_quota_pool", return_value=(20, pool)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=600), \
         patch.object(fw, "_chat_domande_oggi", return_value=0) as oggi, \
         patch.object(fw, "_chat_domande_mese", return_value=0) as mese:
        fw.home_config_post(fw.ConfigUpdateRequest(), authorization="Bearer t")
    assert oggi.call_args.args[:2] == (sede_attesa, U)
    assert mese.call_args.args[:2] == (sede_attesa, U)
