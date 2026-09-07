"""Nessuna funzione del database e' raggiungibile con la chiave pubblica.

Il difetto che questo test previene
===================================
Il progetto Supabase ha DEFAULT PRIVILEGES che concedono `EXECUTE` ad `anon` e
`authenticated` su OGNI funzione creata nello schema public (`pg_default_acl`,
`defaclobjtype='f'`). `anon` e' il ruolo della chiave che sta nel browser.
Quindi ogni funzione nuova, e ogni `DROP`+`CREATE` in una migration, nasce
raggiungibile dall'esterno — senza errori e senza test rossi, perche' l'app usa
`service_role` e continua a funzionare.

Attenzione alla forma della revoca: quei permessi sono GRANT NOMINALI, non solo
il permesso implicito via `PUBLIC`. Un `REVOKE ... FROM PUBLIC` da solo NON li
toglie: vanno nominati i ruoli (`FROM PUBLIC, anon, authenticated`).

E' successo davvero. Le migration del 19-20/06/2026 revocarono tutto; misurato
il 07/09/2026, 6 funzioni su 56 erano di nuovo aperte ad `anon`, fra cui
`gruppo_tag_analisi` (SECURITY DEFINER, ricreata con DROP il 27/08): dato un id
di sede e una descrizione, restituiva spesa e fornitori di quella sede senza
verificare chi stesse chiedendo.

Perche' e' un test e non solo una migration
===========================================
La migration chiude i sei buchi di oggi. Questo test chiude la CLASSE: fallisce
al prossimo DROP+CREATE che dimentica la revoca, cioe' esattamente quando serve.

Il conteggio non e' scritto a mano da nessuna parte: si interroga il catalogo.
Un test che asserisse "le funzioni aperte sono 0" contando su una lista
aggiornata a mano mentirebbe alla prima funzione nuova.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

# I due ruoli raggiungibili da fuori: `anon` e' la chiave pubblica,
# `authenticated` il ruolo di un utente loggato via Supabase Auth. ONEFLUX non
# usa Supabase Auth (auth.uid() e' sempre NULL), ma il ruolo esiste comunque e
# una chiave che lo assume sarebbe altrettanto esterna.
RUOLI_ESTERNI = ("anon", "authenticated")

_QUERY_FUNZIONI_ESPOSTE = """
SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS firma,
       %s AS ruolo,
       p.prosecdef AS security_definer
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.prokind = 'f'
  AND p.prorettype <> 'trigger'::regtype
  AND has_function_privilege(%s, p.oid, 'EXECUTE')
ORDER BY p.prosecdef DESC, 1
"""


@pytest.mark.parametrize("ruolo", RUOLI_ESTERNI)
def test_nessuna_funzione_eseguibile_da_un_ruolo_esterno(sql, ruolo):
    esposte = sql(_QUERY_FUNZIONI_ESPOSTE, ruolo, ruolo)
    if esposte:
        elenco = "\n".join(
            f"  - {firma}" + ("  [SECURITY DEFINER: ignora RLS]" if secdef else "")
            for firma, _r, secdef in esposte
        )
        pytest.fail(
            f"{len(esposte)} funzioni eseguibili dal ruolo {ruolo!r}, cioe' da chi "
            f"ha la chiave pubblica:\n{elenco}\n"
            "Di norma e' una funzione creata (o ricreata con DROP+CREATE) senza "
            "revoca: le default privileges del progetto concedono EXECUTE ad "
            "anon e authenticated a ogni CREATE FUNCTION. Aggiungere alla "
            "migration:\n"
            "  REVOKE ALL ON FUNCTION public.<firma> FROM PUBLIC, anon, authenticated;\n"
            "  GRANT EXECUTE ON FUNCTION public.<firma> TO service_role;\n"
            "Il REVOKE dal solo PUBLIC NON basta: quei permessi sono grant nominali."
        )


def test_service_role_puo_eseguire_le_funzioni_che_il_codice_chiama(sql):
    """La revoca non deve chiudere fuori il worker.

    Contrappeso al test sopra: revocare da PUBLIC senza il GRANT esplicito a
    `service_role` renderebbe verde il primo test e rotta la produzione. Le
    funzioni qui elencate sono quelle chiamate con `.rpc()` dal codice
    (misurate il 07/09/2026 su services/, worker/, utils/, config/).
    """
    chiamate_dal_codice = [
        "assegna_fattura_a_sede",
        "assegna_fattura_a_sede_tecnica",
        "claim_batch_for_processing",
        "costi_automatici_mensili",
        "crea_riparto_con_quote",
        "dashboard_stats_aggregata",
        "gruppo_tag_analisi",
        "riparto_quote_mensili",
        "scadenziario_fatture_aggregate",
        "soft_delete_fatture_massivo",
        "sostituisci_quote_riparto",
        "sposta_fattura_a_sede",
        "upsert_notification_inbox",
    ]
    righe = sql(
        """
        SELECT p.proname, bool_or(has_function_privilege('service_role', p.oid, 'EXECUTE'))
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = ANY(%s)
        GROUP BY p.proname
        """,
        chiamate_dal_codice,
    )
    trovate = {nome: puo for nome, puo in righe}
    mancanti = [f for f in chiamate_dal_codice if f not in trovate]
    assert not mancanti, f"funzioni sparite dal database: {mancanti}"
    chiuse = sorted(nome for nome, puo in trovate.items() if not puo)
    assert not chiuse, (
        f"service_role non puo' piu' eseguire {chiuse}: il worker riceverebbe "
        "'permission denied for function' in produzione"
    )


def test_le_funzioni_security_definer_hanno_search_path_fissato(sql):
    """Una SECURITY DEFINER senza `SET search_path` e' dirottabile.

    Gira con i privilegi del proprietario: se risolve i nomi delle tabelle nel
    search_path del CHIAMANTE, chi puo' creare uno schema puo' farle leggere le
    proprie tabelle. E' il rilievo che le migration del 19-20/06 hanno chiuso su
    tutte; questo test impedisce che la prossima nasca senza.
    """
    scoperte = sql(
        """
        SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind = 'f' AND p.prosecdef
          AND NOT EXISTS (
              SELECT 1 FROM unnest(COALESCE(p.proconfig, ARRAY[]::text[])) AS cfg
              WHERE cfg LIKE 'search_path=%%'
          )
        ORDER BY 1
        """
    )
    assert not scoperte, (
        "funzioni SECURITY DEFINER senza search_path fissato:\n"
        + "\n".join(f"  - {r[0]}" for r in scoperte)
    )
