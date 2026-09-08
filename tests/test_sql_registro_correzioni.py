"""Il registro delle modifiche di categoria dice CHI ha scritto — eseguito davvero.

Il difetto che questi test prevengono
=====================================
`category_change_log` esiste dal 29/04/2026 per rispondere a una domanda sola:
quando fra sei mesi una categoria risulta cambiata, chi l'ha cambiata? Misurato
sul DB live l'08/09/2026: 4.132 righe, e ZERO valori su `actor_email`,
`actor_user_id` e `batch_id`; `source` con un solo valore distinto
('db_trigger'). Il trigger cercava i dati dove non potevano esserci (il JWT di
un'auth che qui e' custom) o in GUC che nessuno impostava.

Nel frattempo 34 fatture gia' riviste a mano sono state ricategorizzate dopo la
revisione, in 38 eventi fra il 30/04 e il 27/08: da chi, il registro non lo sa.

Come sono scritti
=================
Si semina una riga vera, si chiama la RPC, si legge `category_change_log`. Mai
asserire sul TESTO del corpo con `pg_get_functiondef`: un mutante che cambia il
comportamento lascia il testo intatto e sopravviverebbe.

Due trappole misurate sul trigger, che decidono la forma della semina:
  - logga SOLO gli UPDATE (`IF TG_OP <> 'UPDATE' THEN RETURN NEW`), quindi la
    riga va inserita PRIMA e aggiornata poi: un test che solo inserisce e' verde
    a vuoto;
  - e solo se la categoria CAMBIA davvero (`IS NOT DISTINCT FROM`): riscrivere
    lo stesso valore non produce nessuna riga di log.

Il trigger e' attivo su DUE tabelle (`fatture` e `prodotti_utente`): entrambe
sono coperte qui, perche' coprirne una sola lascerebbe meta' registro cieco.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.sql

UTENTE = "11111111-1111-4111-8111-111111111111"
SEDE = "22222222-2222-4222-8222-222222222222"
ATTORE = "44444444-4444-4444-8444-444444444444"
LOTTO = "55555555-5555-4555-8555-555555555555"


def _semina_utente_e_sede(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'prova@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
            "partita_iva, attivo) VALUES (%s, %s, 'Sede', '01234567890', true)",
            (SEDE, UTENTE),
        )


def _riga_fattura(db_sql, *, numero_riga=1, categoria="CARNE", descrizione="riga"):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
            "numero_riga, data_documento, fornitore, descrizione, categoria, "
            "quantita, prezzo_unitario, totale_riga) "
            "VALUES (%s, %s, 'prova.xml', %s, '2026-03-10', 'Fornitore', %s, %s, "
            "1, 100.00, 100.00) RETURNING id",
            (UTENTE, SEDE, numero_riga, descrizione, categoria),
        )
        return cur.fetchone()[0]


def _log(sql, tabella="fatture"):
    """Le righe di registro prodotte, dalla piu' vecchia."""
    return sql(
        "SELECT target_id, old_categoria, new_categoria, actor_user_id, "
        "actor_email, source, batch_id, user_id, ristorante_id "
        "FROM public.category_change_log WHERE table_name = %s ORDER BY id",
        tabella,
    )


def test_una_scrittura_senza_dichiarazione_resta_riconoscibile_come_anonima(db_sql, sql):
    """Chi non dichiara non viene bloccato, ma non viene nemmeno spacciato per noto.

    E' il comportamento storico delle 4.132 righe gia' in produzione: deve
    restare valido, o la migration avrebbe riscritto il passato.
    """
    _semina_utente_e_sede(db_sql)
    riga = _riga_fattura(db_sql, categoria="CARNE")

    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.fatture SET categoria = 'PESCE' WHERE id = %s", (riga,))

    righe = _log(sql)
    assert len(righe) == 1, "un UPDATE che cambia categoria deve lasciare una riga di registro"
    _, vecchia, nuova, actor_id, actor_email, source, batch, _, _ = righe[0]
    assert (vecchia, nuova) == ("CARNE", "PESCE")
    assert actor_id is None and actor_email is None
    assert source == "db_trigger"
    assert batch is None


def test_la_rpc_registra_chi_ha_corretto(db_sql, sql, scalare):
    """La correzione manuale del cliente: l'unico percorso con identita' vera."""
    _semina_utente_e_sede(db_sql)
    riga = _riga_fattura(db_sql, categoria="CARNE")

    aggiornate = scalare(
        "SELECT public.aggiorna_categoria_fatture_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        [riga], "PESCE", "correzione_cliente",
        '{"needs_review": false, "categoria_fonte": "correzione_cliente"}',
        "mattia@oneflux.test", ATTORE, None,
    )
    assert aggiornate == 1

    righe = _log(sql)
    assert len(righe) == 1
    _, vecchia, nuova, actor_id, actor_email, source, _, _, _ = righe[0]
    # Le componenti una per una: un assert sul solo `source` resterebbe verde
    # anche se l'attore andasse perduto per strada.
    assert (vecchia, nuova) == ("CARNE", "PESCE")
    assert str(actor_id) == ATTORE
    assert actor_email == "mattia@oneflux.test"
    assert source == "correzione_cliente"


def test_la_rpc_scrive_anche_i_campi_che_accompagnano_la_categoria(db_sql, sql, scalare):
    """needs_review e categoria_fonte viaggiano nello stesso UPDATE.

    Se finissero in un UPDATE separato, il registro conterebbe due eventi per una
    correzione sola.
    """
    _semina_utente_e_sede(db_sql)
    riga = _riga_fattura(db_sql, categoria="CARNE")

    scalare(
        "SELECT public.aggiorna_categoria_fatture_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        [riga], "PESCE", "correzione_cliente",
        '{"needs_review": false, "categoria_fonte": "correzione_cliente", '
        '"categoria_fiducia": "certa"}',
        None, None, None,
    )

    stato = sql(
        "SELECT categoria, needs_review, categoria_fonte, categoria_fiducia "
        "FROM public.fatture WHERE id = %s", riga,
    )[0]
    assert stato == ("PESCE", False, "correzione_cliente", "certa")
    assert len(_log(sql)) == 1, "un solo UPDATE, quindi un solo evento"


def test_un_lotto_si_riconosce_come_lotto(db_sql, sql, scalare):
    """Le righe di una scrittura massiva condividono il batch_id.

    Senza, 500 righe cambiate da uno script sembrerebbero 500 correzioni
    indipendenti — che e' esattamente come si presentano oggi i 38 eventi
    sospetti.
    """
    _semina_utente_e_sede(db_sql)
    prima = _riga_fattura(db_sql, numero_riga=1, categoria="CARNE")
    seconda = _riga_fattura(db_sql, numero_riga=2, categoria="CARNE")

    aggiornate = scalare(
        "SELECT public.aggiorna_categoria_fatture_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        [prima, seconda], "PESCE", "worker_coda", "{}", None, None, LOTTO,
    )
    assert aggiornate == 2

    righe = _log(sql)
    assert len(righe) == 2
    assert {r[6] and str(r[6]) for r in righe} == {LOTTO}
    assert {r[5] for r in righe} == {"worker_coda"}
    assert {r[0] for r in righe} == {str(prima), str(seconda)}


def test_il_registro_copre_anche_la_memoria_dei_prodotti(db_sql, sql, scalare):
    """Il trigger e' su due tabelle: prodotti_utente non va dimenticata."""
    _semina_utente_e_sede(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.prodotti_utente (user_id, descrizione, categoria) "
            "VALUES (%s, 'pomodoro', 'VERDURA')",
            (UTENTE,),
        )

    aggiornate = scalare(
        "SELECT public.aggiorna_categoria_prodotto_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        UTENTE, "pomodoro", "CONSERVE", "correzione_cliente",
        "mattia@oneflux.test", ATTORE, None,
    )
    assert aggiornate == 1

    righe = _log(sql, tabella="prodotti_utente")
    assert len(righe) == 1
    _, vecchia, nuova, actor_id, actor_email, source, _, _, _ = righe[0]
    assert (vecchia, nuova) == ("VERDURA", "CONSERVE")
    assert str(actor_id) == ATTORE
    assert actor_email == "mattia@oneflux.test"
    assert source == "correzione_cliente"


def test_la_dichiarazione_non_cola_sulla_scrittura_successiva(db_sql, sql, scalare):
    """I GUC sono `is_local`: muoiono con la transazione della RPC.

    E' il punto per cui l'attribuzione vive nel DB e non negli header del client
    Supabase, che e' un singleton di processo: la' un attore lasciato indietro
    verrebbe attribuito alla richiesta di un ALTRO utente. Un registro che
    attribuisce male e' peggio di uno vuoto, perche' sembra affidabile.
    """
    _semina_utente_e_sede(db_sql)
    prima = _riga_fattura(db_sql, numero_riga=1, categoria="CARNE")
    seconda = _riga_fattura(db_sql, numero_riga=2, categoria="CARNE")

    scalare(
        "SELECT public.aggiorna_categoria_fatture_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        [prima], "PESCE", "correzione_cliente", "{}",
        "mattia@oneflux.test", ATTORE, LOTTO,
    )
    # Scrittura non dichiarata subito dopo, nella stessa sessione.
    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.fatture SET categoria = 'PANE' WHERE id = %s", (seconda,))

    righe = _log(sql)
    assert len(righe) == 2
    dichiarata, non_dichiarata = righe[0], righe[1]
    assert dichiarata[5] == "correzione_cliente"
    assert non_dichiarata[5] == "db_trigger", "l'attore precedente e' colato sulla scrittura dopo"
    assert non_dichiarata[3] is None and non_dichiarata[4] is None
    assert non_dichiarata[6] is None


def test_la_rpc_non_tocca_le_righe_nel_cestino(db_sql, sql, scalare):
    """Soft delete: una riga cancellata non torna in vita cambiando categoria."""
    _semina_utente_e_sede(db_sql)
    riga = _riga_fattura(db_sql, categoria="CARNE")
    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.fatture SET deleted_at = now() WHERE id = %s", (riga,))

    aggiornate = scalare(
        "SELECT public.aggiorna_categoria_fatture_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        [riga], "PESCE", "worker_coda", "{}", None, None, None,
    )
    assert aggiornate == 0
    assert sql("SELECT categoria FROM public.fatture WHERE id = %s", riga)[0][0] == "CARNE"


def test_una_lista_vuota_non_riscrive_il_mondo(db_sql, sql, scalare):
    """`id = ANY('{}')` non tocca nulla; NULL nemmeno.

    Una guardia che mancasse qui trasformerebbe una lista vuota — il caso normale
    di "niente da classificare" — in un UPDATE senza WHERE utile.
    """
    _semina_utente_e_sede(db_sql)
    riga = _riga_fattura(db_sql, categoria="CARNE")

    for ids in ([], None):
        assert scalare(
            "SELECT public.aggiorna_categoria_fatture_attribuita(%s, %s, %s, %s, %s, %s, %s)",
            ids, "PESCE", "worker_coda", "{}", None, None, None,
        ) == 0

    assert sql("SELECT categoria FROM public.fatture WHERE id = %s", riga)[0][0] == "CARNE"
    assert _log(sql) == []


def test_la_dichiarazione_della_gemella_non_cola(db_sql, sql, scalare):
    """Stesso rischio di colata sulla RPC di prodotti_utente.

    Serve un test suo: la prova sulla gemella di `fatture` non copre questa —
    misurato, togliendo l'azzeramento qui la suite restava verde.
    """
    _semina_utente_e_sede(db_sql)
    riga = _riga_fattura(db_sql, categoria="CARNE")
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.prodotti_utente (user_id, descrizione, categoria) "
            "VALUES (%s, 'pomodoro', 'VERDURA')",
            (UTENTE,),
        )

    scalare(
        "SELECT public.aggiorna_categoria_prodotto_attribuita(%s, %s, %s, %s, %s, %s, %s)",
        UTENTE, "pomodoro", "CONSERVE", "correzione_cliente",
        "mattia@oneflux.test", ATTORE, LOTTO,
    )
    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.fatture SET categoria = 'PANE' WHERE id = %s", (riga,))

    dopo = _log(sql)[0]
    assert dopo[5] == "db_trigger", "l'attore della gemella e' colato sulla scrittura dopo"
    assert dopo[3] is None and dopo[4] is None
    assert dopo[6] is None
