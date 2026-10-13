"""admin_ultimo_caricamento su un Postgres vero: la colonna «Ultimo caricamento»
della lista clienti dell'admin."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

UTENTE = "55555555-5555-4555-8555-555555555555"
SEDE = "66666666-6666-4666-8666-666666666666"
SEDE_VUOTA = "77777777-7777-4777-8777-777777777777"


def _prepara(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'u@cliente.it', 'x', 'Trattoria')", (UTENTE,),
        )
        for sid, piva in ((SEDE, "01234567890"), (SEDE_VUOTA, "01234567891")):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva) "
                "VALUES (%s, %s, 'Sede', %s)", (sid, UTENTE, piva),
            )


def _documento(db_sql, file, quando, cancellato=False):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture_documenti (user_id, ristorante_id, file_origine, created_at, deleted_at) "
            "VALUES (%s, %s, %s, %s::timestamptz, CASE WHEN %s THEN now() END)",
            (UTENTE, SEDE, file, quando, cancellato),
        )


def _ultimi(sql, *sedi):
    righe = sql("SELECT * FROM public.admin_ultimo_caricamento(%s::uuid[])", list(sedi))
    return {str(r[0]): r[1] for r in righe}


def test_torna_il_documento_piu_recente_non_cancellato(db_sql, sql):
    _prepara(db_sql)
    _documento(db_sql, "a.xml", "2026-09-01T10:00:00Z")
    _documento(db_sql, "b.xml", "2026-10-05T10:00:00Z")
    _documento(db_sql, "c.xml", "2026-10-10T10:00:00Z", cancellato=True)
    ultimo = _ultimi(sql, SEDE)[SEDE]
    assert ultimo.isoformat().startswith("2026-10-05T10:00:00")


def test_una_sede_senza_documenti_torna_con_null(db_sql, sql):
    _prepara(db_sql)
    _documento(db_sql, "a.xml", "2026-09-01T10:00:00Z")
    risultato = _ultimi(sql, SEDE, SEDE_VUOTA)
    assert set(risultato) == {SEDE, SEDE_VUOTA}
    assert risultato[SEDE_VUOTA] is None


def test_non_e_eseguibile_dai_ruoli_del_client(db_sql, scalare):
    for ruolo in ("anon", "authenticated"):
        assert scalare(
            "SELECT has_function_privilege(%s, 'public.admin_ultimo_caricamento(uuid[])', 'EXECUTE')",
            ruolo,
        ) is False
