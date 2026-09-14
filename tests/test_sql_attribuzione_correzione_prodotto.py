"""La correzione del cliente dice CHI e' stato anche nella memoria dei prodotti.

Il difetto che questi test prevengono
=====================================
Una sola azione del cliente — "questa riga non e' BEVANDE, e' ACQUA" — scrive in
DUE posti: la riga in `fatture` e la voce in `prodotti_utente` (la memoria che
eviter di richiedere la stessa classificazione domani). Il 08/09/2026 le
scritture di categoria hanno imparato a dichiarare l'attore, ma solo il primo dei
due percorsi e' stato collegato.

Misurato sul DB live il 14/09/2026: tutte e **113** le righe di
`category_change_log` su `prodotti_utente` sono senza attore, comprese 3 del
10/09 — cioe' DOPO che l'attribuzione era gia' in produzione (`origin/main`). La
RPC gemella `aggiorna_categoria_prodotto_attribuita` esisteva sul DB live ed era
coperta da test, ma aveva **zero chiamanti in produzione**: era uno strumento
costruito e mai collegato.

Conseguenza concreta: fra sei mesi, sulla stessa correzione, il registro sa chi
ha cambiato la riga di fattura e non sa chi ha cambiato la memoria — che e'
proprio la meta' che decide le classificazioni future.

Perche' sono SQL e non con un mock
==================================
L'attribuzione vive nei GUC di sessione letti da un trigger: un mock direbbe solo
"la RPC e' stata chiamata", non che il registro ha davvero registrato l'attore.
Qui gira il vero `salva_correzione_in_memoria_locale` su un Postgres vero, con il
client Supabase tradotto in SQL (`tests/helpers_supabase_sql.py`, scritto per L2).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

UTENTE = "11111111-1111-4111-8111-111111111111"
EMAIL = "cliente@oneflux.test"


def _client(db_sql):
    from tests.helpers_supabase_sql import ClientSQL

    return ClientSQL(db_sql)


def _semina_utente(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, %s, 'x', 'Prova')",
            (UTENTE, EMAIL),
        )


def _chiave(descrizione: str) -> str:
    """La chiave con cui la memoria e' scritta e riletta.

    Si chiede alla funzione vera invece di scriverla a mano: `salva_correzione_
    in_memoria_locale` normalizza la descrizione ('acqua panna 1l' -> 'ACQUA
    PANNA'), e un test che seminasse la forma grezza sarebbe verde su una riga
    che il codice non guarda mai.
    """
    from services.ai_service import get_descrizione_normalizzata_e_originale

    return get_descrizione_normalizzata_e_originale(descrizione)[0]


def _voce(db_sql, descrizione: str, categoria: str):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.prodotti_utente (user_id, descrizione, categoria) "
            "VALUES (%s, %s, %s)",
            (UTENTE, _chiave(descrizione), categoria),
        )


def _log(sql):
    return sql(
        "SELECT old_categoria, new_categoria, actor_email, actor_user_id, source "
        "FROM public.category_change_log WHERE table_name = 'prodotti_utente' "
        "ORDER BY id"
    )


def _correggi(db_sql, descrizione: str, nuova: str):
    """Il percorso vero del cliente, non la RPC chiamata a mano."""
    from services.ai_service import salva_correzione_in_memoria_locale

    return salva_correzione_in_memoria_locale(
        descrizione=descrizione,
        nuova_categoria=nuova,
        user_id=UTENTE,
        user_email=EMAIL,
        supabase_client=_client(db_sql),
    )


def test_la_correzione_di_una_voce_esistente_dice_chi_e_stato(db_sql, sql):
    """Il caso del difetto: la voce c'e' gia', il cliente la cambia."""
    _semina_utente(db_sql)
    _voce(db_sql, "acqua panna 1l", "BEVANDE")

    assert _correggi(db_sql, "acqua panna 1l", "ACQUA") is True

    righe = _log(sql)
    assert len(righe) == 1, f"attesa una riga di registro, trovate {len(righe)}"
    vecchia, nuova, attore_email, attore_id, source = righe[0]
    assert (vecchia, nuova) == ("BEVANDE", "ACQUA")
    assert attore_email == EMAIL, "la correzione e' rimasta anonima nel registro"
    assert str(attore_id) == UTENTE
    assert source == "correzione_cliente"


def test_la_categoria_resta_quella_scelta_dal_cliente(db_sql, sql):
    """L'attribuzione non deve cambiare il risultato: prima di tutto si corregge."""
    _semina_utente(db_sql)
    _voce(db_sql, "acqua panna 1l", "BEVANDE")

    _correggi(db_sql, "acqua panna 1l", "ACQUA")

    categoria = sql(
        "SELECT categoria FROM public.prodotti_utente WHERE user_id = %s "
        "AND descrizione = %s",
        UTENTE, _chiave("acqua panna 1l"),
    )
    assert categoria == [("ACQUA",)]


def test_una_descrizione_mai_vista_si_salva_lo_stesso(db_sql, sql):
    """La RPC fa solo UPDATE: se attribuisse e basta, la voce nuova si perderebbe.

    Il registro qui non ha niente da dire (il trigger logga i soli UPDATE), ma la
    memoria DEVE imparare: e' il caso piu' frequente, e romperlo significherebbe
    che il cliente corregge e il giorno dopo ritrova lo stesso errore.
    """
    _semina_utente(db_sql)

    assert _correggi(db_sql, "prodotto mai visto", "CARNE") is True

    categoria = sql(
        "SELECT categoria FROM public.prodotti_utente WHERE user_id = %s "
        "AND descrizione = %s",
        UTENTE, _chiave("prodotto mai visto"),
    )
    assert categoria == [("CARNE",)]
    assert _log(sql) == [], "un inserimento non deve produrre righe di registro"


def test_il_registro_non_conta_due_volte_la_stessa_correzione(db_sql, sql):
    """Attribuzione + upsert sono due scritture: il log deve vederne UNA.

    L'upsert a valle riscrive lo stesso valore, e il trigger ignora gli UPDATE che
    non cambiano la categoria (`IS NOT DISTINCT FROM`). Se un giorno l'ordine
    cambiasse, questo test lo direbbe: due righe uguali nel registro sono una
    correzione che sembra fatta due volte.
    """
    _semina_utente(db_sql)
    _voce(db_sql, "acqua panna 1l", "BEVANDE")

    _correggi(db_sql, "acqua panna 1l", "ACQUA")

    assert len(_log(sql)) == 1


def test_la_dichiarazione_non_cola_sulla_scrittura_dopo(db_sql, sql):
    """I GUC muoiono con la transazione della RPC: la voce di un altro resta sua.

    Un registro che attribuisce male e' peggio di uno vuoto, perche' sembra
    affidabile: qui si prova che dopo la correzione attribuita una scrittura
    anonima resta anonima.
    """
    _semina_utente(db_sql)
    _voce(db_sql, "acqua panna 1l", "BEVANDE")
    _voce(db_sql, "altra voce", "CARNE")

    _correggi(db_sql, "acqua panna 1l", "ACQUA")

    with db_sql.cursor() as cur:
        cur.execute(
            "UPDATE public.prodotti_utente SET categoria = 'PESCE' "
            "WHERE user_id = %s AND descrizione = %s",
            (UTENTE, _chiave("altra voce")),
        )

    righe = _log(sql)
    assert len(righe) == 2
    assert righe[0][2] == EMAIL
    assert righe[1][2] is None, "la dichiarazione e' colata sulla scrittura dopo"
