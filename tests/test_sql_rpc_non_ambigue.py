"""Nessuna RPC chiamata dal codice si risolve in piu' di una funzione.

Il difetto che questo test previene
===================================
PostgREST sceglie l'overload di una funzione dai nomi degli argomenti che
riceve. Se due varianti accettano lo stesso insieme di nomi, non puo' decidere e
risponde PGRST203 — a runtime, sul cliente, senza che nulla sia rosso in CI.

E' successo. `get_distinct_files` esisteva in tre varianti, `(text)`, `(uuid)` e
`(uuid, uuid)`: le prime due accettano entrambe il solo `p_user_id`. I due
chiamanti in produzione — services/db_service.py e services/upload_handler.py —
passano esattamente quello quando manca la sede. In `elimina_tutte_fatture`
l'eccezione veniva ingoiata (`logger.warning`) e il codice proseguiva con un
conteggio parziale: all'utente veniva dichiarato un numero di fatture piu' basso
di quante ne venivano davvero cancellate.

La variante `(text)` era per giunta rotta di suo: `SET search_path TO ''` ma
`FROM fatture` non qualificata, quindi se fosse stata scelta avrebbe risposto
`relation "fatture" does not exist`. E' stata eliminata dalla migration
20260907194500.

Perche' e' un test e non solo la migration
==========================================
La migration toglie l'ambiguita' di oggi. Questo test chiude la classe: si
accorge della prossima variante aggiunta con gli stessi nomi di parametri.

Il modo di misurare conta: NON si confronta il numero di varianti con una cifra
scritta qui (una funzione in piu', legittima e con nomi diversi, farebbe rosso
per niente). Si controlla la cosa che rompe davvero — due varianti che accettano
lo stesso insieme di nomi — e per get_distinct_files si prova a chiamarla come la
chiama il codice, verificando che risolva.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

# Le RPC che il codice chiama con un sottoinsieme dei parametri. Per queste
# l'ambiguita' non e' teorica: c'e' un chiamante che passa proprio quei nomi.
RPC_CHIAMATE_CON_UN_ARGOMENTO = [
    # (funzione, nomi passati dal chiamante, file del chiamante)
    ("get_distinct_files", ["p_user_id"], "services/db_service.py, services/upload_handler.py"),
]


def _varianti(sql, nome):
    return sql(
        "SELECT pg_get_function_identity_arguments(p.oid) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = %s "
        "ORDER BY 1",
        nome,
    )


def _nomi_parametri_accettati(sql, nome):
    """Per ogni variante, l'insieme dei nomi di parametro che accetta.

    Un parametro con DEFAULT e' opzionale: la variante e' chiamabile anche
    omettendolo, ed e' proprio cosi' che nascono le collisioni.
    """
    righe = sql(
        "SELECT p.oid::regprocedure::text, "
        "       COALESCE(p.proargnames, ARRAY[]::text[]), "
        "       p.pronargs - p.pronargdefaults "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = %s",
        nome,
    )
    accettati = []
    for firma, nomi, obbligatori in righe:
        # I nomi in ordine: i primi `obbligatori` sono richiesti, il resto opzionale.
        accettati.append((firma, tuple(nomi[:obbligatori])))
    return accettati


def test_get_distinct_files_non_e_piu_ambigua(db_sql, sql):
    """Chiamata col solo p_user_id, come fa il codice, deve risolvere.

    Il codice gira come `service_role`, quindi il test assume quel ruolo: senza,
    la guardia interna alla funzione risponde `Accesso negato` e l'ambiguita'
    resterebbe non misurata dietro un errore diverso.
    """
    with db_sql.cursor() as cur:
        cur.execute("SET LOCAL request.jwt.claim.role = 'service_role'")
    righe = sql(
        "SELECT * FROM public.get_distinct_files("
        "  p_user_id => '11111111-1111-4111-8111-111111111111'::uuid)"
    )
    # Nessuna fattura seminata: l'insieme vuoto e' il risultato giusto. Cio' che
    # si sta provando e' che la chiamata RISOLVA, non cosa ritorni.
    assert righe == []


def test_get_distinct_files_nega_a_chi_non_e_service_role(db_sql, sql):
    """La variante rimasta e' quella CON la guardia, non il wrapper nudo.

    Serve a distinguere quale delle tre e' sopravvissuta: se restasse quella
    sbagliata la chiamata risolverebbe lo stesso, e il test qui sopra da solo
    non se ne accorgerebbe.
    """
    import psycopg

    with pytest.raises(psycopg.errors.RaiseException, match="Accesso negato"):
        sql(
            "SELECT * FROM public.get_distinct_files("
            "  p_user_id => '11111111-1111-4111-8111-111111111111'::uuid)"
        )
    db_sql.rollback()


@pytest.mark.parametrize("nome, passati, chiamanti", RPC_CHIAMATE_CON_UN_ARGOMENTO)
def test_una_sola_variante_accetta_gli_argomenti_del_chiamante(sql, nome, passati, chiamanti):
    passati = set(passati)
    compatibili = [
        firma
        for firma, obbligatori in _nomi_parametri_accettati(sql, nome)
        if set(obbligatori) <= passati
    ]
    assert len(compatibili) == 1, (
        f"{nome} chiamata con {sorted(passati)} da {chiamanti} si risolve in "
        f"{len(compatibili)} varianti: {compatibili}. Con piu' di una PostgREST "
        f"risponde PGRST203 a runtime."
    )


def test_la_variante_text_di_get_distinct_files_non_esiste_piu(sql):
    """Era senza guardia auth, non filtrava il cestino e non si eseguiva.

    Regola di dominio #5: le query su `fatture` filtrano `deleted_at IS NULL`.
    Quella variante non lo faceva, quindi avrebbe contato anche le fatture nel
    cestino.
    """
    firme = [r[0] for r in _varianti(sql, "get_distinct_files")]
    assert "p_user_id text" not in firme, (
        "la variante (text) e' tornata: reintroduce l'ambiguita' PGRST203 e "
        "conta le fatture cestinate"
    )
    assert firme, (
        "get_distinct_files e' sparita del tutto: i chiamanti in "
        "services/db_service.py e services/upload_handler.py si aspettano che esista"
    )


@pytest.mark.parametrize(
    "nome, firma",
    [
        ("gruppo_prezzi_categoria", "p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean"),
        ("swap_ricette_order", "ricetta_id_1 uuid, ricetta_id_2 uuid"),
        ("create_ristorante_for_user", "p_user_id uuid, p_nome text, p_piva character varying, p_ragione_sociale text"),
        ("conta_ristoranti_utente", "p_user_id uuid"),
    ],
)
def test_le_funzioni_senza_chiamanti_sono_state_eliminate(sql, nome, firma):
    """Superficie in meno: erano tutte raggiungibili, nessuna era usata.

    Se una torna, va con un chiamante vero — e questo test va aggiornato a mano,
    che e' il punto: la rimozione e' una decisione, non un incidente.
    """
    assert firma not in [r[0] for r in _varianti(sql, nome)], (
        f"{nome}({firma}) e' tornata nel database senza che questo test lo sappia"
    )
