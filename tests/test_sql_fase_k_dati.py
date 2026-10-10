"""Fase K3: la migration dei dati, ESEGUITA su un Postgres vero.

SHOP diventa RIVENDITA ovunque una riga porti il nome; la tabella `categorie`
segue il nuovo elenco. Si semina, si riesegue il file della migration dentro la
transazione del test e si guarda cosa e' cambiato: un assert sul testo del file
resterebbe verde anche con un WHERE sbagliato.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.sql

_MIGRATION = next(
    Path(__file__).resolve().parent.parent.glob("supabase/migrations/*_categorie_fase_k_dati.sql")
)
_UTENTE = "11111111-1111-4111-8111-111111111111"
_SEDE = "22222222-2222-4222-8222-222222222222"
_LOTTO = "9404d963-5cb3-4410-a552-b12043046eca"


def _semina(cur):
    cur.execute(
        "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
        "VALUES (%s, 'k@oneflux.test', 'x', 'Prova')", (_UTENTE,))
    cur.execute(
        "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva) "
        "VALUES (%s, %s, 'Sede', '01234567890')", (_SEDE, _UTENTE))
    righe = [
        # (numero_riga, descrizione, categoria, cancellata, arbitrata)
        (1, "CARAMELLE GOLIA", "SHOP", False, False),
        (2, "SIGARETTE", "SHOP", False, True),
        (3, "PATATINE", "SHOP", True, False),
        (4, "SALMONE", "PESCE", False, False),
        (5, "YAKI NORI", "SUSHI VARIE", False, False),
    ]
    for numero, desc, cat, cancellata, arbitrata in righe:
        cur.execute(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, "
            "data_documento, fornitore, descrizione, categoria, quantita, prezzo_unitario, "
            "totale_riga, deleted_at, reviewed_at, categoria_fonte) "
            "VALUES (%s, %s, 'k.xml', %s, DATE '2026-03-10', 'Fornitore', %s, %s, 1, 10, 10, "
            "%s, %s, %s)",
            (_UTENTE, _SEDE, numero, desc, cat,
             "2026-04-01" if cancellata else None,
             "2026-04-02" if arbitrata else None,
             "correzione_cliente" if arbitrata else None))
    cur.execute("INSERT INTO public.prodotti_master (descrizione, categoria) VALUES ('GOLIA', 'SHOP')")
    cur.execute("INSERT INTO public.prodotti_master (descrizione, categoria, categoria_suggerita) "
                "VALUES ('MARS', 'CARNE', 'SHOP')")
    cur.execute("INSERT INTO public.prodotti_utente (user_id, descrizione, categoria) "
                "VALUES (%s, 'GOLIA', 'SHOP')", (_UTENTE,))
    cur.execute("INSERT INTO public.review_confirmed (descrizione, categoria_finale, confirmed_by) "
                "VALUES ('GOLIA', 'SHOP', 'admin@oneflux.test')")
    cur.execute("INSERT INTO public.categorie (nome, icona, ordinamento) VALUES "
                "('SHOP', '🛍️', 500), ('SUSHI VARIE', '🍣', 140), ('PESCE', '🐟', 20) "
                "ON CONFLICT (nome) DO NOTHING")


def _applica(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(_MIGRATION.read_text(encoding="utf-8"))


@pytest.fixture
def seminato(db_sql):
    with db_sql.cursor() as cur:
        _semina(cur)
    _applica(db_sql)
    return db_sql


def _categorie_fatture(sql):
    return dict(sql("SELECT numero_riga, categoria FROM public.fatture WHERE user_id = %s", _UTENTE))


def test_shop_diventa_rivendita_su_ogni_riga_anche_decisa_a_mano_e_nel_cestino(seminato, sql):
    cat = _categorie_fatture(sql)
    assert cat[1] == cat[2] == cat[3] == "RIVENDITA"


def test_la_rinomina_non_cancella_la_decisione_del_cliente(seminato, scalare):
    assert scalare("SELECT reviewed_at IS NOT NULL FROM public.fatture "
                   "WHERE user_id = %s AND numero_riga = 2", _UTENTE) is True
    assert scalare("SELECT categoria_fonte FROM public.fatture "
                   "WHERE user_id = %s AND numero_riga = 2", _UTENTE) == "correzione_cliente"


def test_le_altre_righe_non_si_muovono(seminato, sql):
    """SUSHI VARIE la sposta lo script, riga per riga: la migration non la tocca."""
    cat = _categorie_fatture(sql)
    assert cat[4] == "PESCE"
    assert cat[5] == "SUSHI VARIE"


def test_memoria_e_conferme_seguono_la_rinomina(seminato, scalare):
    assert scalare("SELECT categoria FROM public.prodotti_master WHERE descrizione = 'GOLIA'") == "RIVENDITA"
    assert scalare("SELECT categoria_suggerita FROM public.prodotti_master WHERE descrizione = 'MARS'") == "RIVENDITA"
    assert scalare("SELECT categoria FROM public.prodotti_master WHERE descrizione = 'MARS'") == "CARNE"
    assert scalare("SELECT categoria FROM public.prodotti_utente WHERE descrizione = 'GOLIA'") == "RIVENDITA"
    assert scalare("SELECT categoria_finale FROM public.review_confirmed WHERE descrizione = 'GOLIA'") == "RIVENDITA"


def test_la_tabella_categorie_segue_il_nuovo_elenco(seminato, sql):
    nomi = {r[0] for r in sql("SELECT nome FROM public.categorie")}
    assert {"RIVENDITA", "RAPPRESENTANZA", "PESCE"} <= nomi
    assert not ({"SHOP", "SUSHI VARIE"} & nomi)


def test_il_registro_attribuisce_la_rinomina_alla_migration(seminato, sql):
    """Senza attribuzione il registro direbbe "db_trigger": un cambio di categoria
    di cui nessuno risulta autore, su righe che un cliente aveva deciso."""
    righe = sql(
        "SELECT source, batch_id::text FROM public.category_change_log "
        "WHERE table_name = 'fatture' AND old_categoria = 'SHOP' AND new_categoria = 'RIVENDITA'")
    assert len(righe) == 3
    assert {r[0] for r in righe} == {"migrazione_fase_k"}
    assert {r[1] for r in righe} == {_LOTTO}


def test_rieseguita_non_cambia_niente(seminato, sql):
    prima = sorted(sql("SELECT numero_riga, categoria FROM public.fatture WHERE user_id = %s", _UTENTE))
    log_prima = sql("SELECT count(*) FROM public.category_change_log")[0][0]
    _applica(seminato)
    assert sorted(sql("SELECT numero_riga, categoria FROM public.fatture WHERE user_id = %s", _UTENTE)) == prima
    assert sql("SELECT count(*) FROM public.category_change_log")[0][0] == log_prima
