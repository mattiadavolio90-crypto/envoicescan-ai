"""Due worker sulla stessa coda, su un Postgres vero (lente L6, 15/09/2026).

I dieci presidi di `test_sql_funzioni_soldi` provano `claim_batch_for_processing`
con un worker alla volta. Qui la seconda connessione arriva MENTRE la prima ha la
transazione ancora aperta: e' la finestra di ogni deploy Railway (il container
vecchio e quello nuovo convivono) e di ogni riavvio dopo un crash.

Le righe si committano davvero — una transazione aperta sulla connessione A deve
essere visibile a B — quindi usano id e uuid lontani da quelli dei test in
rollback e si puliscono a mano nel `finally`.
"""
from __future__ import annotations

import threading
import time

import pytest

pytestmark = pytest.mark.sql

ID_BASE = 910_000
UTENTE_L6 = "99999999-9999-4999-8999-999999999901"
SEDE_L6 = "99999999-9999-4999-8999-999999999902"
SEDE_L6_B = "99999999-9999-4999-8999-999999999903"


@pytest.fixture
def due_connessioni(_server_sql):
    psycopg = pytest.importorskip("psycopg")
    a = psycopg.connect(_server_sql, autocommit=False)
    b = psycopg.connect(_server_sql, autocommit=False)
    try:
        yield a, b
    finally:
        for conn in (a, b):
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
        pulizia = psycopg.connect(_server_sql, autocommit=True)
        try:
            pulizia.execute(
                "DELETE FROM public.fatture_queue WHERE id >= %s AND id < %s",
                (ID_BASE, ID_BASE + 1000),
            )
            pulizia.execute("DELETE FROM public.ristoranti WHERE id IN (%s, %s)", (SEDE_L6, SEDE_L6_B))
            pulizia.execute("DELETE FROM public.users WHERE id = %s", (UTENTE_L6,))
        finally:
            pulizia.close()


def _semina_pending(conn, quante):
    with conn.cursor() as cur:
        for i in range(quante):
            cur.execute(
                "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, "
                "attempt_count, max_attempts, next_retry_at) "
                "VALUES (%s, %s, '12345678901', 'pending', 0, 8, now())",
                (ID_BASE + i, f"l6-evento-{ID_BASE + i}"),
            )
    conn.commit()
    return [ID_BASE + i for i in range(quante)]


def _claim(conn, worker, lotto=10):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.claim_batch_for_processing(%s, %s) ORDER BY id",
            (worker, lotto),
        )
        return [r[0] for r in cur.fetchall()]


def test_due_worker_concorrenti_si_dividono_la_coda_senza_sovrapporsi(due_connessioni):
    """A ha preso il suo lotto e non ha ancora committato: B deve vedere solo il resto."""
    a, b = due_connessioni
    tutti = _semina_pending(a, 12)
    b.execute("SET lock_timeout = '5s'")

    presi_da_a = _claim(a, "worker-a", 10)
    presi_da_b = _claim(b, "worker-b", 10)

    assert len(presi_da_a) == 10
    assert set(presi_da_a).isdisjoint(presi_da_b), "la stessa fattura a due worker"
    assert sorted(presi_da_a + presi_da_b) == tutti, "una fattura non e' andata a nessuno"

    a.commit()
    b.commit()
    with a.cursor() as cur:
        cur.execute(
            "SELECT locked_by, count(*) FROM public.fatture_queue "
            "WHERE id = ANY(%s) GROUP BY locked_by ORDER BY locked_by",
            (tutti,),
        )
        assert cur.fetchall() == [("worker-a", 10), ("worker-b", 2)]


def test_il_secondo_worker_non_aspetta_il_primo(due_connessioni):
    """Con la coda tutta in mano ad A, B torna subito a mani vuote.

    Senza SKIP LOCKED la seconda SELECT ... FOR UPDATE resterebbe appesa fino al
    commit di A: qui il lock_timeout di 5 s lo trasformerebbe in un errore, e il
    cronometro lo denuncerebbe comunque.
    """
    a, b = due_connessioni
    _semina_pending(a, 5)
    b.execute("SET lock_timeout = '5s'")

    assert len(_claim(a, "worker-a", 10)) == 5
    partenza = time.monotonic()
    presi_da_b = _claim(b, "worker-b", 10)
    durata = time.monotonic() - partenza

    assert presi_da_b == []
    assert durata < 2, f"B ha aspettato {durata:.1f}s: il lock di A lo bloccava"


def test_assegnazione_a_sede_il_secondo_aspetta_il_commit_del_primo_e_non_sovrascrive(due_connessioni):
    """`assegna_fattura_a_sede` prende un FOR UPDATE senza SKIP LOCKED, di proposito:
    due assegnazioni della stessa fattura devono serializzarsi. B parte mentre A non
    ha ancora committato, aspetta, e quando legge lo stato lo trova gia' assegnato:
    FALSE, e la sede resta quella di A.

    Senza il FOR UPDATE sulla SELECT, B leggerebbe 'da_assegnare' (A non e' visibile),
    si bloccherebbe solo sull'UPDATE e, dopo il commit di A, lo sovrascriverebbe con
    la propria sede: due assegnazioni, vince l'ultima.
    """
    a, b = due_connessioni
    with a.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'l6@oneflux.test', 'x', 'L6')",
            (UTENTE_L6,),
        )
        for sede, nome, piva in ((SEDE_L6, "Sede L6", "01234567899"), (SEDE_L6_B, "Sede L6 B", "01234567898")):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                "VALUES (%s, %s, %s, %s, TRUE)",
                (sede, UTENTE_L6, nome, piva),
            )
        cur.execute(
            "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, "
            "attempt_count, max_attempts, next_retry_at) "
            "VALUES (%s, 'l6-da-assegnare', '12345678901', 'da_assegnare', %s, 0, 8, now())",
            (ID_BASE, UTENTE_L6),
        )
    a.commit()

    with a.cursor() as cur:
        cur.execute("SELECT public.assegna_fattura_a_sede(%s, %s)", (ID_BASE, SEDE_L6))
        assert cur.fetchone()[0] is True

    esito_b = {}

    def _b_assegna_all_altra_sede():
        partenza = time.monotonic()
        with b.cursor() as cur:
            cur.execute("SELECT public.assegna_fattura_a_sede(%s, %s)", (ID_BASE, SEDE_L6_B))
            esito_b["valore"] = cur.fetchone()[0]
        esito_b["attesa"] = time.monotonic() - partenza
        b.commit()

    thread_b = threading.Thread(target=_b_assegna_all_altra_sede, daemon=True)
    thread_b.start()
    time.sleep(0.5)
    a.commit()
    thread_b.join(timeout=10)

    assert not thread_b.is_alive(), "B e' rimasto appeso anche dopo il commit di A"
    assert esito_b["attesa"] >= 0.4, "B non ha aspettato A: ha letto uno stato non committato"
    assert esito_b["valore"] is False, "la seconda assegnazione e' passata"
    with a.cursor() as cur:
        cur.execute(
            "SELECT status, ristorante_id::text FROM public.fatture_queue WHERE id = %s",
            (ID_BASE,),
        )
        assert cur.fetchone() == ("pending", SEDE_L6), "B ha sovrascritto la sede di A"


def test_il_lock_e_del_lotto_ma_il_lavoro_e_dell_item_rinnovarlo_lo_tiene_nostro(due_connessioni):
    """Il claim scrive `locked_at` una volta per tutto il lotto. Dopo dieci minuti spesi
    sui primi item, il terzo partirebbe con un lock gia' stantio e un altro processo
    (`release_stale_locks` + `claim`) se lo prenderebbe mentre A lo elabora. A rinnova
    il lock all'inizio di ogni item con `_rinnova_lock`: qui gira quella funzione vera,
    col builder tradotto in SQL, e B non riesce a portarglielo via. E un item che B ha
    gia' preso non si lascia rinnovare da A.
    """
    from tests.helpers_supabase_sql import ClientSQL
    from worker.queue_processor import _rinnova_lock

    a, b = due_connessioni
    ids = _semina_pending(a, 3)
    assert _claim(a, "worker-a", 10) == ids
    a.commit()
    # dieci minuti passati sui primi due item: il lock del lotto e' stantio per tutti
    a.execute(
        "UPDATE public.fatture_queue SET locked_at = now() - INTERVAL '11 minutes' "
        "WHERE locked_by = 'worker-a'"
    )
    a.commit()

    assert _rinnova_lock(ClientSQL(a), ids[2], "worker-a") is True
    a.commit()

    with b.cursor() as cur:
        cur.execute("SELECT public.release_stale_locks(10)")
        assert cur.fetchone()[0] == 2, "rilasciati anche item col lock rinnovato"
        cur.execute("UPDATE public.fatture_queue SET next_retry_at = now() WHERE id = ANY(%s)", (ids[:2],))
    assert _claim(b, "worker-b", 10) == ids[:2]
    b.commit()

    with a.cursor() as cur:
        cur.execute(
            "SELECT id, status, locked_by FROM public.fatture_queue WHERE id = ANY(%s) ORDER BY id",
            (ids,),
        )
        assert cur.fetchall() == [
            (ids[0], "processing", "worker-b"),
            (ids[1], "processing", "worker-b"),
            (ids[2], "processing", "worker-a"),
        ]
    assert _rinnova_lock(ClientSQL(a), ids[0], "worker-a") is False, "A ha rinnovato un item di B"
    a.rollback()
