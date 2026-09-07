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

import importlib
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "supabase" / "schema_snapshot.sql"

MIGRAZIONI = REPO_ROOT / "supabase" / "migrations"

# Lo snapshot e' una fotografia: il repo puo' contenere migration non ancora
# applicate al live, o applicate dopo la rigenerazione. Vanno caricate SOPRA lo
# snapshot, altrimenti i test misurano un database piu' vecchio del repo — e una
# migration nuova (per esempio una che revoca permessi) risulterebbe verde senza
# essere mai stata eseguita.
#
# Il taglio e' il timestamp nel nome file confrontato con la data di
# rigenerazione dichiarata dallo snapshot: `-- Rigenerato il AAAA-MM-GG`.


def _migrazioni_dopo_lo_snapshot(testo_snapshot: str) -> list[Path]:
    import re

    match = re.search(r"^-- Rigenerato il (\d{4})-(\d{2})-(\d{2})\.", testo_snapshot, re.M)
    if not match:
        return []
    # Il timestamp Supabase e' AAAAMMGGHHMMSS: si confronta il prefisso AAAAMMGG.
    # `>=` e non `>`: una migration dello STESSO giorno puo' essere posteriore
    # alla rigenerazione, e riapplicarla e' innocuo (i REVOKE/GRANT e i
    # CREATE OR REPLACE sono idempotenti), mentre saltarla non lo e'.
    giorno_snapshot = "".join(match.groups())
    recenti = []
    for percorso in sorted(MIGRAZIONI.glob("*.sql")):
        prefisso = percorso.name[:8]
        if prefisso.isdigit() and prefisso >= giorno_snapshot:
            recenti.append(percorso)
    return recenti


def _dipendenza(nome: str, motivo: str):
    """Importa una dipendenza dei test SQL, o si ferma nel modo giusto.

    In LOCALE si puo' saltare: chi lavora sul frontend non deve installare un
    Postgres per far girare la suite. In CI no — `pgserver` e `psycopg` sono in
    `requirements-lock.txt`, quindi mancarli significa che l'ambiente e' rotto, e
    un salto silenzioso spegnerebbe questi test proprio dove servono. Misurato il
    07/09/2026 mascherando il modulo: senza questa guardia la CI riportava
    "38 skipped" ed exit 0.
    """
    try:
        return importlib.import_module(nome)
    except ImportError:
        if os.environ.get("CI"):
            pytest.fail(
                f"{nome} non importabile in CI: e' in requirements-lock.txt, "
                f"quindi l'ambiente non e' quello atteso. {motivo}",
                pytrace=False,
            )
        pytest.skip(f"{nome} non installato: {motivo}", allow_module_level=True)


def _pgserver():
    return _dipendenza(
        "pgserver",
        "i test sulla logica SQL richiedono un Postgres locale (`pip install pgserver`)",
    )


def _psycopg():
    return _dipendenza("psycopg", "serve per parlare col Postgres di test")


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

    testo_snapshot = SNAPSHOT.read_text(encoding="utf-8")
    with psycopg.connect(uri, autocommit=True) as conn:
        conn.execute(testo_snapshot)
        # Il search_path della sessione che carica non sopravvive: va messo
        # sul database, cosi' ogni connessione successiva trova uuid_generate_v4.
        conn.execute("ALTER DATABASE postgres SET search_path TO public, extensions")

        for percorso in _migrazioni_dopo_lo_snapshot(testo_snapshot):
            try:
                conn.execute(percorso.read_text(encoding="utf-8"))
            except Exception as errore:  # pragma: no cover - dipende dal repo
                # Una migration che non si applica sopra lo snapshot e' un
                # problema vero (o la migration e' rotta, o lo snapshot e'
                # vecchio): va detto, non ingoiato. Il fallimento e' rumoroso
                # perche' i test successivi girerebbero su uno schema sbagliato.
                pytest.fail(
                    f"migration {percorso.name} non applicabile sopra "
                    f"schema_snapshot.sql: {errore}"
                )

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
