"""`ristoranti.tipo_attivita` e la sede tecnica che lo eredita (retail, Fase 1.1).

Eseguito su un Postgres vero con la migration `20260910163000_add_tipo_attivita`
applicata sopra lo snapshot (tests/conftest_sql.py). Tre cose che il codice
Python non puo' garantire da solo:

  - una sede scritta SENZA settore nasce 'ristorazione': e' cio' che rende
    inerte la colonna per il codice vecchio e per le 12 sedi esistenti;
  - il CHECK rifiuta un valore fuori da (ristorazione, retail);
  - `assegna_fattura_a_sede_tecnica` crea "Costi comuni di gruppo" col settore
    della sede reale da cui copia gia' la P.IVA. L'INSERT originale non lo
    passava: su un account retail la sede tecnica sarebbe nata ristorazione
    per default, in silenzio. Il caso 'ristorazione' e' parametrizzato accanto
    per documentare che per i ristoranti il risultato e' identico.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

UTENTE = "aaaaaaaa-1111-4111-8111-111111111111"
SEDE = "bbbbbbbb-2222-4222-8222-222222222222"
PIVA = "01234567891"


def _semina(db_sql, tipo: str | None = None):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'retail@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        if tipo is None:
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva) "
                "VALUES (%s, %s, 'Sede', %s)",
                (SEDE, UTENTE, PIVA),
            )
        else:
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, tipo_attivita) "
                "VALUES (%s, %s, 'Sede', %s, %s)",
                (SEDE, UTENTE, PIVA, tipo),
            )


def _coda_da_assegnare(db_sql, queue_id: int = 9001) -> int:
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id) "
            "VALUES (%s, %s, %s, 'da_assegnare', %s)",
            (queue_id, f"evt-retail-{queue_id}", PIVA, UTENTE),
        )
    return queue_id


def test_una_sede_scritta_senza_settore_nasce_ristorazione(db_sql, scalare):
    _semina(db_sql)
    assert scalare("SELECT tipo_attivita FROM public.ristoranti WHERE id = %s", SEDE) == "ristorazione"


def test_il_check_rifiuta_un_settore_sconosciuto(db_sql):
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        _semina(db_sql, tipo="bar")
    db_sql.rollback()


@pytest.mark.parametrize("tipo", ["retail", "ristorazione"])
def test_la_sede_tecnica_eredita_il_settore_della_sede_reale(db_sql, sql, scalare, tipo):
    _semina(db_sql, tipo=tipo)
    queue_id = _coda_da_assegnare(db_sql)

    tecnica_id = scalare("SELECT public.assegna_fattura_a_sede_tecnica(%s)", queue_id)
    assert tecnica_id is not None

    righe = sql(
        "SELECT sede_tecnica, tipo_attivita, partita_iva FROM public.ristoranti WHERE id = %s",
        tecnica_id,
    )
    assert righe == [(True, tipo, PIVA)]
    # La coda e' rimessa in lavorazione sulla sede tecnica: il resto della
    # funzione non e' cambiato.
    assert sql("SELECT status, ristorante_id FROM public.fatture_queue WHERE id = %s", queue_id) == [
        ("pending", tecnica_id)
    ]
