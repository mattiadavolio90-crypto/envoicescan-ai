"""Crediti della chat e ricariche (Boost AI) su un Postgres vero.

Migration `20261010135911_chat_crediti_ricariche.sql`, fase J del piano
«Assistente consulente» (decisioni di Mattia del 10/10/2026):

* una domanda costa crediti; si spendono PRIMA i crediti del mese, POI la
  ricarica;
* la ricarica non scade: il residuo passa ai mesi dopo;
* il tetto del giorno vale anche quando si spende la ricarica;
* a mese e ricarica finiti il cliente legge «mese», non «torna domani».

Un secondo cliente ha sempre righe e ricariche sue: senza, togliere un filtro
`user_id = ...` lascerebbe i test verdi mentre i crediti passano da un cliente
all'altro (il buco dello STORICO §5 del piano, sul conteggio Python).
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.sql

UTENTE = "44444444-4444-4444-8444-444444444444"
SEDE = "55555555-5555-4555-8555-555555555555"
SEDE_B = "66666666-6666-4666-8666-666666666666"
ESTRANEO = "77777777-7777-4777-8777-777777777777"
SEDE_ESTRANEA = "88888888-8888-4888-8888-888888888888"
ROMA = ZoneInfo("Europe/Rome")


def _semina(db_sql):
    with db_sql.cursor() as cur:
        for uid, email in ((UTENTE, "crediti@oneflux.test"), (ESTRANEO, "altro@oneflux.test")):
            cur.execute(
                "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
                "VALUES (%s, %s, 'x', 'Prova')",
                (uid, email),
            )
        for sede, uid, piva in (
            (SEDE, UTENTE, "98765432101"),
            (SEDE_B, UTENTE, "98765432102"),
            (SEDE_ESTRANEA, ESTRANEO, "00000000009"),
        ):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                "VALUES (%s, %s, 'Sede', %s, true)",
                (sede, uid, piva),
            )
        # Il rumore dell'estraneo: una ricarica grande e domande di oggi, alcune
        # pagate con la ricarica. Se un filtro sparisce entrano nei numeri sotto.
        cur.execute(
            "INSERT INTO public.chat_ricariche (user_id, crediti) VALUES (%s, 900)", (ESTRANEO,)
        )
        for da_ricarica in (False, False, True):
            cur.execute(
                "INSERT INTO public.chat_usage_log (user_id, ristorante_id, crediti, da_ricarica) "
                "VALUES (%s, %s, 3, %s)",
                (ESTRANEO, SEDE_ESTRANEA, da_ricarica),
            )


def _ricarica(db_sql, crediti, utente=UTENTE):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.chat_ricariche (user_id, crediti) VALUES (%s, %s)", (utente, crediti)
        )


def _riga(db_sql, istante=None, *, sede=SEDE, crediti=3, da_ricarica=False, utente=UTENTE):
    with db_sql.cursor() as cur:
        if istante is None:
            cur.execute(
                "INSERT INTO public.chat_usage_log (user_id, ristorante_id, crediti, da_ricarica) "
                "VALUES (%s, %s, %s, %s)",
                (utente, sede, crediti, da_ricarica),
            )
        else:
            cur.execute(
                "INSERT INTO public.chat_usage_log (user_id, ristorante_id, crediti, da_ricarica, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (utente, sede, crediti, da_ricarica, istante),
            )


def _consuma(sql, *, giorno=100, mese=1000, costo=3, sede=SEDE, pool=False, utente=UTENTE):
    return sql(
        "SELECT public.chat_crediti_check_and_log(%s, %s, %s, %s, %s, %s)",
        utente, sede, pool, giorno, mese, costo,
    )[0][0]


def _stato(sql, *, sede=SEDE, pool=False, utente=UTENTE):
    return sql("SELECT public.chat_crediti_stato(%s, %s, %s)", utente, sede, pool)[0][0]


def _righe(scalare, utente=UTENTE):
    return scalare("SELECT count(*) FROM public.chat_usage_log WHERE user_id = %s", utente)


def _primo_del_mese(sql):
    adesso = sql("SELECT now()")[0][0].astimezone(ROMA)
    return adesso.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def test_prima_il_mese_poi_la_ricarica_poi_fermo(db_sql, sql, scalare):
    _semina(db_sql)
    _ricarica(db_sql, 6)

    primo = _consuma(sql, mese=6)
    assert primo == {"esito": "ok", "oggi": 3, "mese": 3, "ricarica": 6, "da_ricarica": False}
    assert _consuma(sql, mese=6)["da_ricarica"] is False

    # mese finito (6 su 6): ora paga la ricarica, e il mese non sale piu'
    terza = _consuma(sql, mese=6)
    assert terza == {"esito": "ok", "oggi": 9, "mese": 6, "ricarica": 3, "da_ricarica": True}
    assert _consuma(sql, mese=6)["ricarica"] == 0
    # il mese conta solo i crediti del piano: quelli pagati con la ricarica no
    assert _stato(sql) == {"oggi": 12, "mese": 6, "ricarica": 0}

    fermata = _consuma(sql, mese=6)
    assert fermata["esito"] == "mese"
    assert _righe(scalare) == 4, "una domanda fermata ha comunque scritto una riga"
    assert scalare(
        "SELECT count(*) FROM public.chat_usage_log WHERE user_id = %s AND da_ricarica", UTENTE
    ) == 2


def test_senza_ricarica_il_mese_finito_ferma(db_sql, sql, scalare):
    _semina(db_sql)
    assert _consuma(sql, mese=3)["esito"] == "ok"
    assert _consuma(sql, mese=3)["esito"] == "mese"
    assert _righe(scalare) == 1


def test_la_ricarica_non_scade_e_il_mese_riparte(db_sql, sql):
    """Una ricarica di 9 crediti, 3 spesi il mese scorso: questo mese il piano
    riparte da zero e la ricarica ne ha ancora 6."""
    _semina(db_sql)
    _ricarica(db_sql, 9)
    mese_scorso = _primo_del_mese(sql) - timedelta(days=3)
    _riga(db_sql, mese_scorso, crediti=3, da_ricarica=True)
    _riga(db_sql, mese_scorso, crediti=3)

    assert _stato(sql) == {"oggi": 0, "mese": 0, "ricarica": 6}


def test_il_tetto_del_giorno_vale_anche_sulla_ricarica(db_sql, sql):
    _semina(db_sql)
    _ricarica(db_sql, 300)
    assert _consuma(sql, giorno=6, mese=3)["da_ricarica"] is False
    assert _consuma(sql, giorno=6, mese=3)["da_ricarica"] is True
    fermata = _consuma(sql, giorno=6, mese=3)
    assert fermata["esito"] == "giorno"
    assert fermata["ricarica"] == 297


def test_a_mese_e_giorno_finiti_vince_il_mese(db_sql, sql):
    _semina(db_sql)
    assert _consuma(sql, giorno=3, mese=3)["esito"] == "ok"
    assert _consuma(sql, giorno=3, mese=3)["esito"] == "mese"


def test_il_giorno_ferma_anche_col_mese_aperto(db_sql, sql, scalare):
    _semina(db_sql)
    assert _consuma(sql, giorno=3, mese=1000)["esito"] == "ok"
    assert _consuma(sql, giorno=3, mese=1000)["esito"] == "giorno"
    assert _righe(scalare) == 1


def test_mese_senza_budget_non_ferma(db_sql, sql):
    _semina(db_sql)
    for _ in range(3):
        assert _consuma(sql, giorno=100, mese=0)["esito"] == "ok"


@pytest.mark.parametrize("giorno,costo", [(0, 3), (100, 0), (None, 3), (100, None)])
def test_tetto_o_costo_nulli_non_scrivono(db_sql, sql, scalare, giorno, costo):
    _semina(db_sql)
    assert _consuma(sql, giorno=giorno, costo=costo)["esito"] == "giorno"
    assert _righe(scalare) == 0


def test_i_crediti_si_sommano_non_si_contano(db_sql, sql):
    """Una domanda da 5 crediti pesa 5: il mese non e' il numero di righe."""
    _semina(db_sql)
    _riga(db_sql, crediti=5)
    assert _consuma(sql, mese=6, costo=1)["mese"] == 6
    assert _consuma(sql, mese=6, costo=1)["esito"] == "mese"


def test_una_riga_scritta_senza_crediti_ne_vale_tre(db_sql, sql):
    """Le righe gia' sul DB e quelle del worker vecchio (vecchia RPC) non hanno
    `crediti`: prendono il default 3, il costo di una domanda."""
    _semina(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.chat_usage_log (user_id, ristorante_id) VALUES (%s, %s)",
            (UTENTE, SEDE),
        )
    assert _stato(sql) == {"oggi": 3, "mese": 3, "ricarica": 0}


def test_la_vecchia_rpc_resta_per_il_worker_vecchio(db_sql, sql):
    """Fra migration e push il worker vecchio chiama ancora la vecchia firma."""
    _semina(db_sql)
    assert sql(
        "SELECT public.chat_usage_check_and_log(%s, %s, %s, %s, %s)", UTENTE, SEDE, 30, False, 300
    )[0][0] == 1


def test_niente_crediti_di_un_altro_cliente(db_sql, sql):
    """L'estraneo ha 900 crediti di ricarica e domande di oggi: niente di suo
    entra nei numeri dell'utente, ne' a sede, ne' a pool, ne' senza sede."""
    _semina(db_sql)
    vuoto = {"oggi": 0, "mese": 0, "ricarica": 0}
    assert _stato(sql) == vuoto
    assert _stato(sql, pool=True) == vuoto
    assert _stato(sql, sede=None) == vuoto
    # e a mese finito, la ricarica dell'estraneo non paga per lui
    assert _consuma(sql, mese=3)["esito"] == "ok"
    assert _consuma(sql, mese=3)["esito"] == "mese"


def test_la_ricarica_dell_utente_non_va_all_estraneo(db_sql, sql):
    _semina(db_sql)
    _ricarica(db_sql, 30)
    # estraneo: 900 caricati, 3 spesi da ricarica
    assert _stato(sql, utente=ESTRANEO, sede=SEDE_ESTRANEA)["ricarica"] == 897


def test_a_sede_conta_la_sede_a_pool_l_account(db_sql, sql):
    _semina(db_sql)
    _riga(db_sql, sede=SEDE_B)
    assert _stato(sql, sede=SEDE)["oggi"] == 0
    assert _stato(sql, sede=SEDE_B)["oggi"] == 3
    assert _stato(sql, pool=True)["oggi"] == 3
    assert _stato(sql, sede=None)["oggi"] == 3


def test_la_ricarica_e_dell_account_anche_a_sede(db_sql, sql):
    """Sede singola (niente pool): il mese si conta sulla sede, ma la ricarica
    spesa da un'altra sede dello stesso account scala lo stesso salvadanaio."""
    _semina(db_sql)
    _ricarica(db_sql, 9)
    _riga(db_sql, sede=SEDE_B, da_ricarica=True)
    assert _stato(sql, sede=SEDE)["ricarica"] == 6


def test_mese_comincia_a_mezzanotte_di_roma(db_sql, sql):
    _semina(db_sql)
    primo = _primo_del_mese(sql)
    _riga(db_sql, primo - timedelta(minutes=30))
    _riga(db_sql, primo + timedelta(minutes=30))
    assert _stato(sql)["mese"] == 3


def test_ricariche_cancellate_con_l_utente(db_sql, sql, scalare):
    _semina(db_sql)
    _ricarica(db_sql, 300)
    sql("DELETE FROM public.ristoranti WHERE user_id = %s", UTENTE)
    sql("DELETE FROM public.users WHERE id = %s", UTENTE)
    assert scalare("SELECT count(*) FROM public.chat_ricariche WHERE user_id = %s", UTENTE) == 0


def test_ricarica_a_zero_o_negativa_rifiutata(db_sql):
    _semina(db_sql)
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.CheckViolation):
        _ricarica(db_sql, 0)


def test_giorno_comincia_a_mezzanotte_di_roma(db_sql, sql):
    """Le due righe stanno a cavallo della mezzanotte di Roma (22:00 o 23:00
    UTC): col taglio UTC il conteggio di oggi sarebbe 0 o 6, mai 3."""
    _semina(db_sql)
    adesso = sql("SELECT now()")[0][0].astimezone(ROMA)
    mezzanotte = adesso.replace(hour=0, minute=0, second=0, microsecond=0)
    _riga(db_sql, mezzanotte - timedelta(minutes=30))
    _riga(db_sql, mezzanotte + timedelta(minutes=30))
    assert _stato(sql)["oggi"] == 3
