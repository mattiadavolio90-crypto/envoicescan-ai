"""Le retention GDPR su sessioni e log — eseguite davvero su Postgres.

Il difetto che questi test prevengono
=====================================
Una purge sbagliata fallisce in due modi opposti, ed entrambi sono silenziosi:

  - cancella troppo — `purge_sessioni_scadute` che tocca una sessione ancora
    viva slogga i clienti senza che nessun errore lo segnali;
  - non cancella niente — la prima stesura di `purge_marketplace_leads`
    filtrava su `stato IN ('chiuso','annullato','rifiutato')`, valori che il
    CHECK della tabella non ammette nemmeno. Sarebbe stata un no-op perenne,
    verde in ogni test che si limitasse a chiamarla senza seminare dati.

Per questo ogni funzione è provata sui DUE versanti: una riga vecchia che DEVE
sparire e una recente (o viva, o aperta) che DEVE restare. Asserire solo che
"la chiamata non esplode" o solo che il conteggio scende non distingue una
purge corretta da una che cancella tutto.

Si esegue la RPC su un Postgres vero e si rilegge la tabella: mai assertire sul
testo del corpo con `pg_get_functiondef`, che sopravvive a qualunque mutazione
del comportamento.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

UTENTE = "aaaaaaaa-1111-4111-8111-111111111111"
SEDE = "bbbbbbbb-2222-4222-8222-222222222222"


def _semina_utente_e_sede(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'retention@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
            "partita_iva, attivo) VALUES (%s, %s, 'Sede', '01234567890', true)",
            (SEDE, UTENTE),
        )


def _chiama(db_sql, funzione: str, giorni: int) -> int:
    with db_sql.cursor() as cur:
        cur.execute(f"SELECT public.{funzione}(%s)", (giorni,))
        return cur.fetchone()[0]


def _conta(db_sql, tabella: str) -> int:
    with db_sql.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM public.{tabella}")
        return cur.fetchone()[0]


# --------------------------------------------------------------------------
# sessioni — il caso in cui "cancellare troppo" slogga un cliente vero
# --------------------------------------------------------------------------

def test_purge_sessioni_elimina_le_inattive_e_lascia_le_vive(db_sql) -> None:
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.sessioni (user_id, token, last_seen_at, ip, user_agent) "
            "VALUES (%s, 'vecchia', now() - interval '200 days', '1.2.3.4', 'UA')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.sessioni (user_id, token, last_seen_at, ip, user_agent) "
            "VALUES (%s, 'viva', now() - interval '2 hours', '5.6.7.8', 'UA')",
            (UTENTE,),
        )

    eliminate = _chiama(db_sql, "purge_sessioni_scadute", 90)

    assert eliminate == 1
    with db_sql.cursor() as cur:
        cur.execute("SELECT token FROM public.sessioni")
        rimaste = [r[0] for r in cur.fetchall()]
    assert rimaste == ["viva"], (
        "La purge deve eliminare solo le sessioni inattive: una sessione viva "
        "cancellata slogga il cliente."
    )


def test_purge_sessioni_rifiuta_retention_zero(db_sql) -> None:
    """A 0 giorni cancellerebbe ogni sessione attiva. La guardia non è un
    dettaglio: è ciò che separa una manutenzione da un logout di massa."""
    with pytest.raises(Exception) as exc:
        _chiama(db_sql, "purge_sessioni_scadute", 0)
    assert "p_retention_days" in str(exc.value)


def test_purge_sessioni_conserva_la_finestra_dichiarata(db_sql) -> None:
    """90 giorni dichiarati alla privacy: una sessione di 89 giorni resta."""
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.sessioni (user_id, token, last_seen_at) "
            "VALUES (%s, 'quasi', now() - interval '89 days')",
            (UTENTE,),
        )

    assert _chiama(db_sql, "purge_sessioni_scadute", 90) == 0
    assert _conta(db_sql, "sessioni") == 1


# --------------------------------------------------------------------------
# email_rate_log / category_change_log / ai_usage_events
# --------------------------------------------------------------------------

def test_purge_email_rate_log_taglia_solo_le_righe_vecchie(db_sql) -> None:
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.email_rate_log (destinatario, user_id, created_at) "
            "VALUES ('vecchio@test.it', %s, now() - interval '120 days')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.email_rate_log (destinatario, user_id, created_at) "
            "VALUES ('recente@test.it', %s, now() - interval '3 days')",
            (UTENTE,),
        )

    assert _chiama(db_sql, "purge_email_rate_log", 90) == 1
    with db_sql.cursor() as cur:
        cur.execute("SELECT destinatario FROM public.email_rate_log")
        assert [r[0] for r in cur.fetchall()] == ["recente@test.it"]


def test_purge_category_change_log_taglia_solo_le_righe_vecchie(db_sql) -> None:
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.category_change_log "
            "(table_name, actor_email, changed_at) "
            "VALUES ('fatture', 'vecchio@test.it', now() - interval '400 days')"
        )
        cur.execute(
            "INSERT INTO public.category_change_log "
            "(table_name, actor_email, changed_at) "
            "VALUES ('fatture', 'recente@test.it', now() - interval '30 days')"
        )

    assert _chiama(db_sql, "purge_category_change_log", 365) == 1
    with db_sql.cursor() as cur:
        cur.execute("SELECT actor_email FROM public.category_change_log")
        assert [r[0] for r in cur.fetchall()] == ["recente@test.it"]


def test_purge_ai_usage_events_taglia_solo_le_righe_vecchie(db_sql) -> None:
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.ai_usage_events "
            "(ristorante_id, user_id, operation_type, source_file, created_at) "
            "VALUES (%s, %s, 'categorization', 'vecchio.xml', now() - interval '400 days')",
            (SEDE, UTENTE),
        )
        cur.execute(
            "INSERT INTO public.ai_usage_events "
            "(ristorante_id, user_id, operation_type, source_file, created_at) "
            "VALUES (%s, %s, 'categorization', 'recente.xml', now() - interval '10 days')",
            (SEDE, UTENTE),
        )

    assert _chiama(db_sql, "purge_ai_usage_events", 365) == 1
    with db_sql.cursor() as cur:
        cur.execute("SELECT source_file FROM public.ai_usage_events")
        assert [r[0] for r in cur.fetchall()] == ["recente.xml"]


# --------------------------------------------------------------------------
# marketplace_leads — qui il rischio è il no-op silenzioso
# --------------------------------------------------------------------------

def test_purge_marketplace_leads_elimina_solo_gli_archiviati_vecchi(db_sql) -> None:
    """Tre righe, un solo bersaglio: vecchio+archiviato. Un lead 'nuovo' della
    stessa età è una trattativa aperta e non si cancella; un archiviato recente
    è dentro la finestra. Se il filtro sullo stato usasse valori inesistenti
    (com'era nella prima stesura), qui il conteggio sarebbe 0."""
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        for etichetta, stato, eta in [
            ("archiviato-vecchio", "archiviato", "800 days"),
            ("nuovo-vecchio", "nuovo", "800 days"),
            ("archiviato-recente", "archiviato", "100 days"),
        ]:
            cur.execute(
                "INSERT INTO public.marketplace_leads "
                "(user_id, ristorante_id, servizio_key, servizio_label, "
                " contatto_email, stato, created_at, updated_at) "
                f"VALUES (%s, %s, %s, %s, 'lead@test.it', %s, "
                f"now() - interval '{eta}', now() - interval '{eta}')",
                (UTENTE, SEDE, etichetta, etichetta, stato),
            )

    assert _chiama(db_sql, "purge_marketplace_leads", 730) == 1
    with db_sql.cursor() as cur:
        cur.execute("SELECT servizio_key FROM public.marketplace_leads ORDER BY servizio_key")
        assert [r[0] for r in cur.fetchall()] == ["archiviato-recente", "nuovo-vecchio"]


# --------------------------------------------------------------------------
# I permessi: una purge eseguibile da anon è una cancellazione a comando
# --------------------------------------------------------------------------

FUNZIONI_PURGE = [
    "purge_sessioni_scadute",
    "purge_email_rate_log",
    "purge_category_change_log",
    "purge_ai_usage_events",
    "purge_marketplace_leads",
]


@pytest.mark.parametrize("funzione", FUNZIONI_PURGE)
def test_purge_non_eseguibile_da_anon_e_authenticated(db_sql, funzione: str) -> None:
    """Su Supabase anon/authenticated ricevono grant nominali dalle default
    privileges: il solo REVOKE FROM PUBLIC non basta, vanno nominati."""
    with db_sql.cursor() as cur:
        cur.execute(
            "SELECT has_function_privilege('anon', p.oid, 'EXECUTE'), "
            "       has_function_privilege('authenticated', p.oid, 'EXECUTE'), "
            "       has_function_privilege('service_role', p.oid, 'EXECUTE') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = %s",
            (funzione,),
        )
        riga = cur.fetchone()
    assert riga is not None, f"{funzione} non esiste nel database"
    anon, authenticated, service_role = riga
    assert not anon, f"{funzione} eseguibile da anon"
    assert not authenticated, f"{funzione} eseguibile da authenticated"
    assert service_role, f"{funzione} non eseguibile da service_role: il worker non può chiamarla"
