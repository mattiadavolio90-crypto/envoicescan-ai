"""Una fattura esclusa dai conti esce da OGNI aggregato, e resta nella lista.

Perche' esiste
==============
"Escludi dai conti" e' una colonna (`fatture.oscurata`) che 13 funzioni SQL
devono rispettare e una (`scadenziario_fatture_aggregate`) deve ignorare. Non
c'e' un punto unico da cui passano: il filtro e' scritto 13 volte a mano, e il
modo tipico di sbagliarlo e' metterlo nella CTE sbagliata di una funzione che ne
ha due — dove non fallisce niente, cambia solo un numero.

Un test che legge il TESTO della migration sopravvive a qualunque mutazione del
corpo e non e' un presidio: queste funzioni vanno ESEGUITE su un Postgres vero.

Come misura
===========
Due righe identiche, stessa sede, stesso mese, stessa categoria. Una viene
esclusa. L'aggregato deve DIMEZZARSI. Non "essere diverso": dimezzarsi, perche'
un filtro messo nel posto sbagliato spesso azzera tutto o non cambia nulla, e
solo il valore esatto distingue i due casi.

Le fixture usano CARNE e totale_riga > 0 perche' devono passare TUTTI i filtri
gia' presenti nelle 13 funzioni insieme: `Da Classificare` esclusa (regola #1),
NOTE E DICITURE esclusa, `gruppo_peso_categoria` scarta le spese generali,
`gruppo_spreco_fb_categorie` accetta solo una lista chiusa di categorie F&B e
solo importi positivi. Una fixture "qualunque" sarebbe verde a vuoto su meta'
delle funzioni: zero prima e zero dopo non prova niente.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.sql

UTENTE = "11111111-1111-4111-8111-111111111111"
SEDE = "22222222-2222-4222-8222-222222222222"

# Deve passare i filtri di categoria di TUTTE le 13 funzioni insieme (vedi docstring).
CATEGORIA = "CARNE"
CAT_FOOD = ["CARNE", "PESCE"]
CAT_SPESE = ["UTENZE", "AFFITTO"]
DATA = "2026-03-10"
ANNO, MESE = 2026, 3
IMPORTO = Decimal("100.00")


def _semina(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'prova@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
            "partita_iva, attivo) VALUES (%s, %s, 'Sede 1', '01234567891', true)",
            (SEDE, UTENTE),
        )


def _come_service_role(db_sql):
    """Due funzioni sono SECURITY DEFINER e negano a chi non e' `service_role`.
    In ONEFLUX ogni client usa quella chiave (`auth.uid()` e' sempre NULL), e il
    ruolo si assume impostando il GUC che `auth.role()` legge — stesso helper di
    tests/test_sql_funzioni_soldi.py.
    """
    with db_sql.cursor() as cur:
        cur.execute("SET LOCAL request.jwt.claim.role = 'service_role'")


def _riga(db_sql, *, file, oscurata=False, descrizione="RIGA TAG"):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
            "numero_riga, data_documento, fornitore, descrizione, categoria, "
            "quantita, prezzo_unitario, totale_riga, oscurata) "
            "VALUES (%s, %s, %s, 1, %s, 'Fornitore', %s, %s, 1, %s, %s, %s)",
            (UTENTE, SEDE, file, DATA, descrizione, CATEGORIA, IMPORTO, IMPORTO,
             oscurata),
        )


# Come si chiama ogni funzione e quale numero si misura. La chiave e' il nome
# della funzione; il valore e' (SQL che torna UN numero, parametri).
# Il numero e' una SOMMA di importi tranne dove la funzione conta righe
# (salute_componenti: n_fatture) — li' l'unita' e' il conteggio, non gli euro.
AGGREGATI = {
    "costi_automatici_mensili": (
        "SELECT COALESCE(SUM(food), 0) FROM public.costi_automatici_mensili("
        "%(u)s, %(s)s, %(anno)s, %(food)s, %(spese)s)",
    ),
    "costi_automatici_mensili_gruppo": (
        "SELECT COALESCE(SUM(food), 0) FROM public.costi_automatici_mensili_gruppo("
        "%(u)s, %(sedi)s, %(anno)s, %(food)s, %(spese)s)",
    ),
    "articoli_da_fatture": (
        "SELECT COUNT(*) FROM public.articoli_da_fatture(%(u)s, %(s)s, %(escluse)s)",
    ),
    "dashboard_stats_aggregata": (
        "SELECT (public.dashboard_stats_aggregata(%(u)s, %(s)s) -> 'kpi' "
        "->> 'spesa_totale')::numeric",
    ),
    "chat_top_categoria_fornitore": (
        "SELECT COALESCE(SUM(spesa), 0) FROM public.chat_top_categoria_fornitore("
        "%(u)s, %(s)s, 3650, 5) WHERE tipo = 'categoria'",
    ),
    "gruppo_peso_categoria": (
        "SELECT COALESCE(SUM(spesa), 0) FROM public.gruppo_peso_categoria("
        "%(sedi)s, %(da)s, %(a)s)",
    ),
    "gruppo_spesa_pivot": (
        "SELECT COALESCE(SUM(totale), 0) FROM public.gruppo_spesa_pivot("
        "%(sedi)s, 'categoria', %(da)s, %(a)s)",
    ),
    "gruppo_spreco_fb_categorie": (
        "SELECT COALESCE(SUM(totale), 0) FROM public.gruppo_spreco_fb_categorie("
        "%(sedi)s, %(da)s, %(a)s)",
    ),
    "gruppo_salute_componenti": (
        "SELECT COALESCE(SUM(n_fatture), 0) FROM public.gruppo_salute_componenti("
        "%(sedi)s, %(inizio)s, %(anno)s, %(mese)s)",
    ),
    "gruppo_tag_analisi": (
        "SELECT COALESCE(SUM(spesa), 0) FROM public.gruppo_tag_analisi("
        "%(sedi)s, %(chiavi)s, %(da)s, %(a)s)",
    ),
    "gruppo_tag_descrizioni": (
        "SELECT COALESCE(SUM(spesa), 0) FROM public.gruppo_tag_descrizioni("
        "%(sedi)s, NULL, 500)",
    ),
    "gruppo_tag_fornitori": (
        "SELECT COALESCE(SUM(spesa), 0) FROM public.gruppo_tag_fornitori("
        "%(sedi)s, %(chiavi)s, %(da)s, %(a)s)",
    ),
    "gruppo_tag_trend": (
        "SELECT COALESCE(SUM(spesa), 0) FROM public.gruppo_tag_trend("
        "%(sedi)s, %(chiavi)s, %(da)s, %(a)s)",
    ),
}

PARAMETRI = {
    "u": UTENTE,
    "s": SEDE,
    "sedi": [SEDE],
    "anno": ANNO,
    "mese": MESE,
    "food": CAT_FOOD,
    "spese": CAT_SPESE,
    "escluse": ["UTENZE"],
    "da": "2026-01-01",
    "a": "2026-12-31",
    "inizio": "2020-01-01T00:00:00+00:00",
    "chiavi": ["RIGA TAG", "RIGA TAG DUE"],
}


def _misura(db_sql, funzione):
    with db_sql.cursor() as cur:
        cur.execute(AGGREGATI[funzione][0], PARAMETRI)
        return cur.fetchone()[0]


@pytest.mark.parametrize("funzione", sorted(AGGREGATI))
def test_rpc_esclude_le_fatture_oscurate(db_sql, funzione):
    """Con due righe identiche e una esclusa, l'aggregato si DIMEZZA.

    Il valore esatto, non "e' diverso": un AND finito nella CTE sbagliata
    tipicamente azzera il risultato o non lo cambia affatto, e solo il confronto
    con la meta' esatta distingue il filtro giusto da quei due casi.
    """
    _semina(db_sql)
    _come_service_role(db_sql)
    # Descrizioni DIVERSE: `articoli_da_fatture` fa DISTINCT ON (descrizione) e
    # con la stessa descrizione due righe darebbero un solo articolo — il
    # dimezzamento non si applicherebbe e il test sarebbe verde a vuoto.
    # `gruppo_tag_*` raggruppa per chiave descrizione: entrambe le chiavi sono
    # in PARAMETRI["chiavi"], quindi la somma resta su due righe.
    _riga(db_sql, file="a.xml", descrizione="RIGA TAG")
    _riga(db_sql, file="b.xml", descrizione="RIGA TAG DUE")

    intero = _misura(db_sql, funzione)
    assert intero, f"{funzione}: fixture muta (0 prima dell'esclusione)"

    with db_sql.cursor() as cur:
        cur.execute(
            "UPDATE public.fatture SET oscurata = true, oscurata_at = now() "
            "WHERE file_origine = 'b.xml'"
        )

    meta = _misura(db_sql, funzione)
    assert meta * 2 == intero, (
        f"{funzione}: escludendo una riga su due l'aggregato e' passato da "
        f"{intero} a {meta}, atteso {intero / 2}"
    )


def test_la_lista_di_gestione_fatture_mostra_ancora_le_oscurate(db_sql):
    """`scadenziario_fatture_aggregate` NON filtra: la fattura resta consultabile.

    E' il presidio contro un futuro "uniformiamo tutte le RPC", che farebbe
    sparire dalla lista proprio le fatture che il cliente ha scelto di tenere.
    """
    _semina(db_sql)
    _come_service_role(db_sql)
    _riga(db_sql, file="a.xml")
    _riga(db_sql, file="b.xml")
    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.fatture SET oscurata = true WHERE file_origine = 'b.xml'")
        cur.execute(
            "SELECT file_origine FROM public.scadenziario_fatture_aggregate(%s, %s) "
            "ORDER BY file_origine",
            (UTENTE, [SEDE]),
        )
        assert [r[0] for r in cur.fetchall()] == ["a.xml", "b.xml"]


def test_il_cestino_e_l_esclusione_sono_stati_indipendenti(db_sql):
    """Escludere non cestina e cestinare non esclude: due assi separati.

    Se si confondessero, "rimetti nei conti" farebbe riemergere dal cestino una
    fattura che il cliente aveva cancellato.
    """
    _semina(db_sql)
    _riga(db_sql, file="a.xml", oscurata=True)
    with db_sql.cursor() as cur:
        cur.execute("SELECT deleted_at FROM public.fatture WHERE file_origine = 'a.xml'")
        assert cur.fetchone()[0] is None

        cur.execute("UPDATE public.fatture SET deleted_at = now() WHERE file_origine = 'a.xml'")
        cur.execute("SELECT oscurata FROM public.fatture WHERE file_origine = 'a.xml'")
        assert cur.fetchone()[0] is True


def test_la_colonna_e_not_null_con_default_falso(db_sql):
    """Le righe esistenti e le nuove entrano nei conti senza dover dire nulla.

    NOT NULL per costruzione: con un NULL ammesso ogni filtro dovrebbe scrivere
    COALESCE, e il primo che lo dimentica riporta la fattura nei conteggi in
    silenzio (e' la ragione per cui `ripartita_su_gruppo`, nullable, obbliga le
    sue RPC a COALESCE).
    """
    _semina(db_sql)
    _riga(db_sql, file="a.xml")
    with db_sql.cursor() as cur:
        cur.execute("SELECT oscurata, oscurata_at FROM public.fatture WHERE file_origine = 'a.xml'")
        assert cur.fetchone() == (False, None)

        cur.execute("SELECT is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_name = 'fatture' AND column_name = 'oscurata'")
        nullable, default = cur.fetchone()
        assert nullable == "NO"
        assert "false" in (default or "").lower()
