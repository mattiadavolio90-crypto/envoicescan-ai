"""Ricaricare una fattura cestinata riattiva anche la sua testata, su un Postgres vero.

Il 20/5/2026 cinque fatture di una sede sono state cestinate (righe e testata,
via `trg_propagate_deleted_at_fatture`) e ricaricate un'ora dopo con lo stesso
nome: `salva_fattura_processata` riattiva le righe, ma `upsert_fattura_documento`
non toccava `deleted_at`, e la testata e' rimasta nel cestino. Righe attive con la
testata archiviata: lo scadenziario le mostrava senza scadenza ne' «pagata», e la
guardia anti-doppione non le vedeva.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

U1 = "0e1b0000-0000-4000-8000-000000000001"
SEDE = "0e1b0000-0000-4000-8000-00000000000a"
FILE = "IT01879020517A2026_biRTd.xml.p7m"


def _semina(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, 'r@riatt.test', 'x', 'T')",
            (U1,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
            "VALUES (%s, %s, 'Sede', '07863990961', TRUE)",
            (SEDE, U1),
        )
        cur.execute(
            "INSERT INTO public.fatture_documenti (user_id, ristorante_id, file_origine, fornitore, "
            "data_documento, tipo_documento, totale_documento, pagata, deleted_at) "
            "VALUES (%s, %s, %s, 'FORNITORE', '2026-02-18', 'TD01', 437.74, TRUE, now())",
            (U1, SEDE, FILE),
        )


def _testata(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "SELECT deleted_at IS NULL, pagata, totale_documento::float FROM public.fatture_documenti "
            "WHERE user_id = %s AND ristorante_id = %s AND file_origine = %s",
            (U1, SEDE, FILE),
        )
        return cur.fetchall()


def test_il_ricaricamento_riattiva_la_testata_cestinata(db_sql):
    from services.documenti_service import upsert_fattura_documento
    from tests.helpers_supabase_sql import ClientSQL

    _semina(db_sql)
    upsert_fattura_documento(
        user_id=U1, ristorante_id=SEDE, file_origine=FILE,
        payload={"fornitore": "FORNITORE", "data_documento": "2026-02-18",
                 "tipo_documento": "TD01", "totale_documento": 437.74},
        supabase_client=ClientSQL(db_sql),
    )
    # Una sola testata, attiva, e lo stato «pagata» deciso dal cliente resta.
    assert _testata(db_sql) == [(True, True, 437.74)]
