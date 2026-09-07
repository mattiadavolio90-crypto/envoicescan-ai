"""Fixture per i test che ESEGUONO la logica SQL del database.

Perche' esiste
==============
77 funzioni e 26 trigger girano in produzione a ogni scrittura e calcolano
numeri che il cliente vede (riparto, scadenziario, dashboard, margini). In tre
cicli di audit nessun test ne ha mai eseguita una riga: pytest mocka il DB, e i
pochi test che citano una migration ne leggono il TESTO con `read_text` — cosa
che sopravvive a qualunque mutazione del corpo, quindi non e' un presidio.

Come funziona
=============
Un Postgres vero, locale, effimero (`pgserver`: wheel pip con Postgres 16
embedded, nessun servizio da installare in CI), caricato con
`supabase/schema_snapshot.sql`. Lo schema viene da uno SNAPSHOT del DB live e
non dalle migration perche' le migration non ricostruiscono il database:
misurato il 7/9/2026, applicandole tutte a un DB vuoto restano 18 tabelle su 59
(`fatture` e `users` non hanno un `CREATE TABLE` in nessun file).

Il server parte UNA volta per sessione di test; ogni test riceve una
connessione dentro una transazione che viene sempre annullata, quindi i test
non si vedono a vicenda e l'ordine non conta.

Cosa NON fa
===========
Non tocca il DB di produzione e non ha bisogno di credenziali: il conftest
principale vieta la rete a tutta la suite, e qui si parla con un Postgres su
socket unix locale. Se `pgserver` non e' installato i test si saltano con un
messaggio esplicito — mai passano in silenzio.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "supabase" / "schema_snapshot.sql"

# Le migration canoniche piu' recenti dello snapshot vanno applicate sopra:
# lo snapshot e' una fotografia, il repo puo' essere avanti. Il confronto e'
# sul nome file (timestamp) contro la data di rigenerazione dello snapshot.
MIGRAZIONI = REPO_ROOT / "supabase" / "migrations"


def _pgserver():
    try:
        import pgserver  # noqa: F401
    except ImportError:
        pytest.skip(
            "pgserver non installato: i test sulla logica SQL richiedono un "
            "Postgres locale (`pip install pgserver`)",
            allow_module_level=True,
        )
    return __import__("pgserver")


def _psycopg():
    try:
        import psycopg  # noqa: F401
    except ImportError:
        pytest.skip("psycopg non installato", allow_module_level=True)
    return __import__("psycopg")


@pytest.fixture(scope="session")
def _server_sql(tmp_path_factory):
    """Postgres locale con lo schema caricato. Uno per sessione di test."""
    pgserver = _pgserver()
    psycopg = _psycopg()

    if not SNAPSHOT.exists():
        pytest.skip(f"snapshot mancante: {SNAPSHOT.relative_to(REPO_ROOT)}")

    datadir = tmp_path_factory.mktemp("pgdata_oneflux")
    server = pgserver.get_server(str(datadir))
    uri = server.get_uri()

    with psycopg.connect(uri, autocommit=True) as conn:
        conn.execute(SNAPSHOT.read_text(encoding="utf-8"))
        # Il search_path della sessione che carica non sopravvive: va messo
        # sul database, cosi' ogni connessione successiva trova uuid_generate_v4.
        conn.execute('ALTER DATABASE postgres SET search_path TO public, extensions')

    yield uri

    try:
        server.cleanup()
    except Exception:
        # Un server di test che non si spegne non deve far fallire la suite:
        # la directory e' temporanea e sparisce con tmp_path_factory.
        pass


@pytest.fixture
def db_sql(_server_sql):
    """Connessione al DB di test, in una transazione sempre annullata.

    Ogni test parte da uno schema pulito e non lascia righe agli altri: il
    rollback finale e' incondizionato, anche se il test passa.
    """
    psycopg = _psycopg()
    conn = psycopg.connect(_server_sql, autocommit=False)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def sql(db_sql):
    """Esegue una query e ritorna le righe. Scorciatoia per i test brevi."""

    def _esegui(query: str, *parametri):
        with db_sql.cursor() as cur:
            cur.execute(query, parametri or None)
            if cur.description is None:
                return []
            return cur.fetchall()

    return _esegui


@pytest.fixture
def scalare(sql):
    """Esegue una query che ritorna un solo valore."""

    def _uno(query: str, *parametri):
        righe = sql(query, *parametri)
        assert righe, f"query senza risultato: {query}"
        return righe[0][0]

    return _uno
