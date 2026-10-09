"""Gestione Fatture si apre su Archivio (fase H, Mattia 09/10/2026), su un Postgres vero.

La migration fa due cose: cambia il default della colonna (account nuovi) e
sposta chi era sul vecchio default 'agenda'. La seconda e' un UPDATE che sul DB
di test gira quando la tabella e' vuota: qui la si riesegue su righe vere, per
provare che tocca SOLO 'agenda' — chi ha scelto il Calendario resta li'.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.sql

MIGRATION = next(
    (Path(__file__).resolve().parents[1] / "supabase" / "migrations").glob("*_vista_fatture_archivio.sql")
)
AGENDA = "55555555-5555-4555-8555-555555555551"
CALENDARIO = "55555555-5555-4555-8555-555555555552"


def _utente(db_sql, uid, email, vista=None):
    with db_sql.cursor() as cur:
        if vista is None:
            cur.execute(
                "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
                "VALUES (%s, %s, 'x', 'Trattoria')",
                (uid, email),
            )
        else:
            cur.execute(
                "INSERT INTO public.users (id, email, password_hash, nome_ristorante, vista_fatture) "
                "VALUES (%s, %s, 'x', 'Trattoria', %s)",
                (uid, email, vista),
            )


def _sotto_utente(db_sql, titolare, email, vista=None):
    with db_sql.cursor() as cur:
        if vista is None:
            cur.execute(
                "INSERT INTO public.sotto_utenti (titolare_id, email, password_hash) "
                "VALUES (%s, %s, 'x') RETURNING id",
                (titolare, email),
            )
        else:
            cur.execute(
                "INSERT INTO public.sotto_utenti (titolare_id, email, password_hash, vista_fatture) "
                "VALUES (%s, %s, 'x', %s) RETURNING id",
                (titolare, email, vista),
            )
        return str(cur.fetchone()[0])


def test_un_account_nuovo_nasce_su_archivio(db_sql, scalare):
    _utente(db_sql, AGENDA, "nuovo@cliente.it")
    sid = _sotto_utente(db_sql, AGENDA, "resp@cliente.it")
    assert scalare("SELECT vista_fatture FROM public.users WHERE id = %s", AGENDA) == "lista_mensile"
    assert scalare("SELECT vista_fatture FROM public.sotto_utenti WHERE id = %s", sid) == "lista_mensile"


def test_la_migration_sposta_solo_chi_era_su_agenda(db_sql, scalare):
    _utente(db_sql, AGENDA, "agenda@cliente.it", "agenda")
    _utente(db_sql, CALENDARIO, "calendario@cliente.it", "calendario")
    su_agenda = _sotto_utente(db_sql, AGENDA, "resp-a@cliente.it", "agenda")
    su_calendario = _sotto_utente(db_sql, CALENDARIO, "resp-c@cliente.it", "calendario")

    with db_sql.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))

    assert scalare("SELECT vista_fatture FROM public.users WHERE id = %s", AGENDA) == "lista_mensile"
    assert scalare("SELECT vista_fatture FROM public.users WHERE id = %s", CALENDARIO) == "calendario"
    assert scalare("SELECT vista_fatture FROM public.sotto_utenti WHERE id = %s", su_agenda) == "lista_mensile"
    assert scalare("SELECT vista_fatture FROM public.sotto_utenti WHERE id = %s", su_calendario) == "calendario"
