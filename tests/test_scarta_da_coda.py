"""Test dell'endpoint POST /api/fatture/scarta-da-coda (services/routers/fatture.py).

Contesto (16/07/2026): dalla coda 'da_assegnare' si usciva SOLO assegnando la
fattura a un locale o ripartendola sul gruppo — entrambe la fanno ENTRARE nei
costi. Un documento non pertinente (o un doppione arrivato dallo SDI con un altro
nome file) restava in coda per sempre e gonfiava il contatore del briefing di
gruppo. Nessuna via d'uscita: non in UI, non via API, non in DB.

Qui si verifica il contratto dell'endpoint:
  - passa alla RPC il queue_id E l'user_id del CHIAMANTE (il guard cross-tenant sta
    nel WHERE della RPC: se l'endpoint passasse un user_id arbitrario dal body,
    chiunque potrebbe svuotare la coda altrui indovinando un queue_id);
  - RPC che torna FALSE (item non del chiamante, o assegnato da un altro click nel
    frattempo) NON è un errore: la riga va via dalla lista in ogni caso.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.routers.fatture as fatture


class _FakeSupabase:
    """Registra le chiamate RPC e restituisce l'esito che il test decide."""

    def __init__(self, rpc_result):
        self.rpc_result = rpc_result
        self.rpc_calls = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_result))


def _chiama(rpc_result, queue_id=42, user_id="user-aaa"):
    sb = _FakeSupabase(rpc_result)
    with patch.object(fatture, "_resolve_user_from_token", return_value={"id": user_id}), \
         patch.object(fatture, "_get_supabase_client", return_value=sb):
        out = fatture.fatture_scarta_da_coda(
            fatture.ScartaCodaBody(queue_id=queue_id),
            authorization="Bearer token-finto",
        )
    return out, sb


class TestScartoRiuscito:
    def test_ok_true_quando_la_rpc_scarta(self):
        out, _ = _chiama(rpc_result=True)
        assert out["ok"] is True
        assert out["queue_id"] == 42

    def test_chiama_la_rpc_giusta(self):
        _, sb = _chiama(rpc_result=True)
        assert len(sb.rpc_calls) == 1
        assert sb.rpc_calls[0][0] == "scarta_fattura_da_coda"


class TestGuardCrossTenant:
    """Il tenant lo decide il TOKEN, mai il body: è ciò che impedisce di svuotare
    la coda di un altro cliente indovinandone il queue_id."""

    def test_passa_user_id_del_token_non_del_body(self):
        _, sb = _chiama(rpc_result=True, user_id="user-vero")
        params = sb.rpc_calls[0][1]
        assert params["p_user_id"] == "user-vero"
        assert params["p_queue_id"] == 42

    def test_user_id_e_una_stringa(self):
        # _resolve_user_from_token può restituire un UUID non-str: la RPC vuole
        # comunque un valore serializzabile.
        sb = _FakeSupabase(True)
        with patch.object(fatture, "_resolve_user_from_token", return_value={"id": 123}), \
             patch.object(fatture, "_get_supabase_client", return_value=sb):
            fatture.fatture_scarta_da_coda(
                fatture.ScartaCodaBody(queue_id=1), authorization="Bearer x"
            )
        assert sb.rpc_calls[0][1]["p_user_id"] == "123"


class TestRaceNonEUnErrore:
    """Se fra il click e la RPC qualcuno ha assegnato la fattura, la RPC torna
    FALSE. Per la UI non è un fallimento: la riga sparisce comunque, ed è giusto —
    la fattura non è più in coda."""

    def test_ok_false_con_motivo_quando_rpc_torna_false(self):
        out, _ = _chiama(rpc_result=False)
        assert out["ok"] is False
        assert out["motivo"] == "gia_gestita"

    def test_rpc_senza_dati_non_solleva(self):
        out, _ = _chiama(rpc_result=None)
        assert out["ok"] is False


class TestMigrationRispettaIVincoliDellaTabella:
    """Due vincoli veri di fatture_queue hanno fatto fallire lo scarto in prova, su
    fattura reale. Sono invisibili leggendo solo il codice Python: la guardia sta qui.

    1. next_retry_at è NOT NULL (default now()). La prima versione lo metteva a NULL
       → 23502 a ogni scarto. mark_queue_item_done, che chiude gli item 'done', non
       lo tocca: per uno stato terminale è irrilevante.
    2. chk_fatture_queue_tenant_consistency pretende user_id e ristorante_id
       entrambi valorizzati o entrambi NULL, con eccezione per 'da_assegnare'. Una
       scartata ha il cliente ma nessuna sede → serve la stessa eccezione, o 23514.
    """

    def _sql(self) -> str:
        from pathlib import Path
        p = (
            Path(__file__).parent.parent
            / "supabase" / "migrations" / "20260716180000_scarta_fattura_da_coda.sql"
        )
        return p.read_text(encoding="utf-8")

    def test_non_scrive_next_retry_at(self):
        # Cerca solo nel corpo dell'UPDATE: i commenti la nominano di proposito.
        sql = self._sql()
        corpo = sql.split("UPDATE public.fatture_queue", 1)[1].split("WHERE", 1)[0]
        assert "next_retry_at" not in corpo, (
            "next_retry_at è NOT NULL: scriverlo nell'UPDATE fa fallire ogni scarto (23502)"
        )

    def test_eccezione_tenant_consistency_include_scartata(self):
        sql = self._sql()
        assert "chk_fatture_queue_tenant_consistency" in sql
        assert "'da_assegnare', 'scartata'" in sql, (
            "senza l'eccezione per 'scartata' il CHECK di coerenza tenant blocca "
            "l'UPDATE (23514): la scartata ha user_id ma nessun ristorante_id"
        )

    def test_usa_row_count_non_found(self):
        # `GET DIAGNOSTICS ... = FOUND` non esiste (42601): FOUND si legge diretto.
        # Le RPC gemelle della tabella usano tutte ROW_COUNT.
        sql = self._sql()
        corpo = sql.split("CREATE OR REPLACE FUNCTION", 1)[1]
        assert "GET DIAGNOSTICS" in corpo and "ROW_COUNT" in corpo
        assert "GET DIAGNOSTICS v_ok = FOUND" not in corpo

    def test_stato_scartata_ammesso_dal_check_status(self):
        assert "'da_assegnare', 'scartata'" in self._sql()
