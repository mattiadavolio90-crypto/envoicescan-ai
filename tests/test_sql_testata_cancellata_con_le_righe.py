"""La testata sparisce con l'ultima riga della fattura, su un Postgres vero.

Le cancellazioni definitive (svuota cestino, purge del cestino scaduto, retention,
elimina definitiva) toglievano le righe di `fatture` e lasciavano la testata: 331
sul live il 17/10/2026. Ricaricando lo stesso file, la testata tornava col vecchio
«pagata». Il trigger `trg_elimina_testate_senza_righe` (migration 20261017154456)
la toglie quando del file non resta nessuna riga, attiva o nel cestino.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

U1 = "0e2c0000-0000-4000-8000-000000000001"
SEDE = "0e2c0000-0000-4000-8000-00000000000a"
ALTRA_SEDE = "0e2c0000-0000-4000-8000-00000000000b"
FILE = "IT02355260981_dqyDo.xml.p7m"


def _semina(db_sql, righe=((SEDE, 1, False), (SEDE, 2, False)), riga_altra_sede=True):
    """Testata pagata di FILE in SEDE e in ALTRA_SEDE; `righe` = (sede, numero, nel
    cestino), piu' una riga attiva in ALTRA_SEDE se `riga_altra_sede`."""
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, 'c@canc.test', 'x', 'T')",
            (U1,),
        )
        for sid in (SEDE, ALTRA_SEDE):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                "VALUES (%s, %s, 'Sede', '07863990961', TRUE)",
                (sid, U1),
            )
            cur.execute(
                "INSERT INTO public.fatture_documenti (user_id, ristorante_id, file_origine, fornitore, "
                "data_documento, tipo_documento, totale_documento, pagata) "
                "VALUES (%s, %s, %s, 'FORNITORE', '2026-01-31', 'TD01', 4884.56, TRUE)",
                (U1, sid, FILE),
            )
        for sid, numero, cestino in righe + (((ALTRA_SEDE, 1, False),) if riga_altra_sede else ()):
            cur.execute(
                "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, data_documento, "
                "fornitore, descrizione, totale_riga, categoria, deleted_at) "
                "VALUES (%s, %s, %s, %s, '2026-01-31', 'FORNITORE', 'MOZZARELLA', 10, 'LATTICINI', "
                "CASE WHEN %s THEN now() END)",
                (U1, sid, FILE, numero, cestino),
            )


def _testate(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "SELECT ristorante_id::text, pagata FROM public.fatture_documenti WHERE user_id = %s ORDER BY 1",
            (U1,),
        )
        return cur.fetchall()


def _cancella(db_sql, where):
    with db_sql.cursor() as cur:
        cur.execute(f"DELETE FROM public.fatture WHERE user_id = %s AND ristorante_id = %s AND {where}", (U1, SEDE))


def test_cancellata_l_ultima_riga_la_testata_sparisce(db_sql):
    _semina(db_sql)
    _cancella(db_sql, "TRUE")
    assert _testate(db_sql) == [(ALTRA_SEDE, True)], "la stessa fattura nell'altra sede resta"


def test_con_una_riga_rimasta_la_testata_resta(db_sql):
    """Il ricaricamento con meno righe cancella solo quelle in piu'."""
    _semina(db_sql)
    _cancella(db_sql, "numero_riga = 2")
    assert _testate(db_sql) == sorted([(SEDE, True), (ALTRA_SEDE, True)])


def test_una_riga_nel_cestino_tiene_la_testata(db_sql):
    """Il cestino resta ripristinabile: la testata serve al ripristino."""
    _semina(db_sql, righe=((SEDE, 1, False), (SEDE, 2, True)))
    _cancella(db_sql, "numero_riga = 1")
    assert (SEDE, True) in _testate(db_sql)


def test_svuota_cestino_e_ricarica_la_fattura_non_torna_pagata(db_sql):
    """Il percorso del 20/5/2026: cestino, svuota, ricarica con lo stesso nome."""
    from services.db_service import svuota_cestino
    from services.documenti_service import upsert_fattura_documento
    from tests.helpers_supabase_sql import ClientSQL

    _semina(db_sql, righe=((SEDE, 1, True), (SEDE, 2, True)))
    sb = ClientSQL(db_sql)
    esito = svuota_cestino(U1, ristorante_id=SEDE, supabase_client=sb)
    assert esito["success"] is True and esito["righe_eliminate"] == 2, esito
    assert _testate(db_sql) == [(ALTRA_SEDE, True)]

    upsert_fattura_documento(
        user_id=U1, ristorante_id=SEDE, file_origine=FILE,
        payload={"fornitore": "FORNITORE", "data_documento": "2026-01-31",
                 "tipo_documento": "TD01", "totale_documento": 4884.56},
        supabase_client=sb,
    )
    assert _testate(db_sql) == sorted([(SEDE, False), (ALTRA_SEDE, True)])


def test_la_cancellazione_tocca_solo_la_sede_delle_righe(db_sql):
    """Il caso OVERTIME/OFFSIDE: una testata senza righe in un'altra sede, con lo
    stesso nome file, non e' affare di questa cancellazione (la sistema lo script
    del verbale n. 36, spostandola)."""
    _semina(db_sql, riga_altra_sede=False)
    _cancella(db_sql, "TRUE")
    assert [r[0] for r in _testate(db_sql)] == [ALTRA_SEDE]
