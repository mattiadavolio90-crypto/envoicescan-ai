"""Il registro dell'email settimanale su un Postgres vero (fase 7a).

Il test Python simula il vincolo; qui si prova che la migration lo crei
davvero, perche' e' LUI la garanzia che nessuno riceva due email nella stessa
settimana (il cron gira due volte il lunedi' di proposito).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.sql

MIGRATION = next(
    (Path(__file__).resolve().parents[1] / "supabase" / "migrations").glob("*_email_settimanale.sql")
)
UTENTE = "33333333-3333-4333-8333-333333333333"
ALTRO = "44444444-4444-4444-8444-444444444444"


def _utente(db_sql, uid, email):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, %s, 'x', 'Trattoria')",
            (uid, email),
        )


def _invio(db_sql, uid, settimana, stato="in_corso"):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.email_settimanale_invii (user_id, settimana, stato) "
            "VALUES (%s, %s, %s)",
            (uid, settimana, stato),
        )


def test_la_preferenza_nasce_accesa(db_sql, scalare):
    _utente(db_sql, UTENTE, "a@cliente.it")
    assert scalare("SELECT email_settimanale FROM public.users WHERE id = %s", UTENTE) is True


def test_due_invii_nella_stessa_settimana_sono_rifiutati(db_sql):
    psycopg = pytest.importorskip("psycopg")
    _utente(db_sql, UTENTE, "a@cliente.it")
    _invio(db_sql, UTENTE, "2026-09-28")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _invio(db_sql, UTENTE, "2026-09-28", "inviata")


def test_altra_settimana_o_altro_utente_passano(db_sql, scalare):
    _utente(db_sql, UTENTE, "a@cliente.it")
    _utente(db_sql, ALTRO, "b@cliente.it")
    _invio(db_sql, UTENTE, "2026-09-28")
    _invio(db_sql, UTENTE, "2026-10-05")
    _invio(db_sql, ALTRO, "2026-09-28")
    assert scalare("SELECT count(*) FROM public.email_settimanale_invii") == 3


def test_la_settimana_e_sempre_un_lunedi(db_sql):
    psycopg = pytest.importorskip("psycopg")
    _utente(db_sql, UTENTE, "a@cliente.it")
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, UTENTE, "2026-09-29")


def test_lo_stato_e_uno_di_quattro(db_sql):
    psycopg = pytest.importorskip("psycopg")
    _utente(db_sql, UTENTE, "a@cliente.it")
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, UTENTE, "2026-09-28", "spedita")


def test_cancellare_l_utente_cancella_il_suo_registro(db_sql, scalare):
    _utente(db_sql, UTENTE, "a@cliente.it")
    _invio(db_sql, UTENTE, "2026-09-28")
    with db_sql.cursor() as cur:
        cur.execute("DELETE FROM public.users WHERE id = %s", (UTENTE,))
    assert scalare("SELECT count(*) FROM public.email_settimanale_invii") == 0


@pytest.mark.parametrize("ruolo", ["anon", "authenticated"])
def test_i_ruoli_pubblici_non_toccano_il_registro(db_sql, scalare, ruolo):
    """Su Supabase anon/authenticated ricevono grant NOMINALI sulle tabelle
    nuove dalle default privileges del progetto; lo snapshot dei test non le
    riproduce, quindi senza aiuto questo test sarebbe verde anche senza REVOKE
    (mutante sopravvissuto il 24/09). Si concede come fa Supabase, poi si
    riesegue la migration vera (e' idempotente): la sua REVOKE deve toglierli."""
    esiste = scalare("SELECT count(*) FROM pg_roles WHERE rolname = %s", ruolo)
    if not esiste:
        pytest.skip(f"ruolo {ruolo} assente nello snapshot")
    with db_sql.cursor() as cur:
        cur.execute(f"GRANT ALL ON public.email_settimanale_invii TO {ruolo}")
    assert scalare(
        "SELECT has_table_privilege(%s, 'public.email_settimanale_invii', 'SELECT')", ruolo
    ) is True, "la simulazione delle default privileges non ha preso"
    with db_sql.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    for permesso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert scalare(
            "SELECT has_table_privilege(%s, 'public.email_settimanale_invii', %s)", ruolo, permesso
        ) is False, permesso
