"""Rigenera `supabase/schema_snapshot.sql` dai cataloghi del DB live.

Perche' esiste
==============
Le migration del repo NON ricostruiscono il database. Misurato il 7/9/2026
applicandole tutte (91 legacy + 139 canoniche) a un Postgres vuoto: 18 tabelle
su 59, 28 funzioni su 79, 171 file falliti. `fatture`, `users`, `app_settings` e
`memoria_ai_categorie` non hanno un `CREATE TABLE` in nessun file — sono nate
dal dashboard Supabase. Quindi i test che devono ESEGUIRE la logica SQL (77
funzioni, 26 trigger, mai coperte da un test in tre cicli di audit) non possono
partire dalle migration: partono da questo snapshot.

Cosa NON e'
===========
Non e' `pg_dump` (non disponibile: il DB e' gestito, non c'e' accesso shell) e
non e' una migration. E' una fotografia leggibile dei cataloghi, rigenerabile,
che serve solo a montare un DB di test. Lo stato autorevole resta il DB live.

Uso
===
    python scripts/genera_schema_snapshot.py            # scrive il file
    python scripts/genera_schema_snapshot.py --check    # esce 1 se e' cambiato

Serve `SUPABASE_DB_URL` (connessione diretta al Postgres, non l'URL REST) in
ambiente o in `.env`. Senza quella variabile lo script esce con un messaggio,
NON con uno snapshot vuoto: uno snapshot vuoto farebbe passare i test su un DB
senza tabelle.

Al 7/9/2026 quella variabile NON e' configurata (il progetto usa solo l'URL REST
+ service_role_key): lo snapshot in repo e' stato prodotto eseguendo queste
stesse query via MCP Supabase. Lo script resta la definizione autorevole di
*cosa* ci va dentro e diventa eseguibile appena la stringa di connessione
esiste; `--check` serve a non far invecchiare lo snapshot in silenzio.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESTINAZIONE = REPO_ROOT / "supabase" / "schema_snapshot.sql"

# Ruoli e funzioni che Supabase fornisce e che il Postgres di test non ha.
# Stanno qui e non nello snapshot perche' NON sono schema dell'applicazione:
# sono l'ambiente in cui lo schema vive. auth.uid() torna sempre NULL come in
# produzione (auth custom), auth.role() legge la GUC che PostgREST imposta.
PREAMBOLO = """\
-- Ambiente Supabase ricreato per il DB di test: ruoli, schema auth, GUC.
-- NON fa parte dello schema dell'applicazione — vedi scripts/genera_schema_snapshot.py.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS extensions;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END
$$;

-- Il Postgres embedded dei test non ha uuid-ossp (il live si). Invece di
-- riscrivere i DEFAULT delle tabelle, si fornisce la funzione con lo stesso
-- nome: dalla 13 gen_random_uuid() e' nel core e basta a se stessa.
--
-- La sostitutiva va in `extensions`, NON in `public`: nel live uuid_generate_v4
-- appartiene all'estensione e non compare fra le funzioni di public. Metterla
-- li' falserebbe ogni conteggio sulle funzioni del progetto e la farebbe
-- risultare "eseguibile da anon" in un test sui permessi. `extensions` e' nel
-- search_path di default di Supabase, quindi i DEFAULT la trovano comunque.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        BEGIN
            CREATE EXTENSION "uuid-ossp";
        EXCEPTION WHEN OTHERS THEN
            CREATE OR REPLACE FUNCTION extensions.uuid_generate_v4() RETURNS uuid
                LANGUAGE sql VOLATILE AS $f$ SELECT gen_random_uuid() $f$;
        END;
    END IF;
END
$$;
-- Sul live il search_path di default include `extensions`; qui lo si imposta
-- per la sessione che carica lo snapshot, cosi' i DEFAULT delle tabelle
-- risolvono uuid_generate_v4() sia in CREATE TABLE sia negli INSERT dei test.
SET search_path TO public, extensions;

-- auth.uid() e' sempre NULL in produzione (auth custom, non Supabase Auth):
-- qui legge la stessa claim, cosi' un test puo' simulare entrambi i casi.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION auth.role() RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('request.jwt.claim.role', true), '') $$;

CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb
    LANGUAGE sql STABLE
    AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;

CREATE TABLE IF NOT EXISTS auth.users (
    id uuid PRIMARY KEY,
    email text
);
"""

Q_SEQUENZE = """
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S' AND n.nspname = 'public'
ORDER BY c.relname;
"""

# `attgenerated = 's'` marca una colonna GENERATED ALWAYS AS ... STORED:
# la sua espressione sta in pg_attrdef come le DEFAULT, ma emetterla come
# DEFAULT non e' valido (referenzia altre colonne). Oggi ce n'e' una,
# inventario_voci.valore_totale.
Q_TABELLE = """
SELECT c.relname AS tbl,
       string_agg(
           '    ' || quote_ident(a.attname) || ' ' || format_type(a.atttypid, a.atttypmod)
           || CASE
                WHEN a.attgenerated = 's'
                    THEN ' GENERATED ALWAYS AS (' || pg_get_expr(d.adbin, d.adrelid) || ') STORED'
                ELSE COALESCE(' DEFAULT ' || pg_get_expr(d.adbin, d.adrelid), '')
              END
           || CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END,
           E',\\n' ORDER BY a.attnum) AS cols
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
WHERE n.nspname = 'public' AND c.relkind = 'r'
GROUP BY c.relname
ORDER BY c.relname;
"""

Q_SEQ_OWNED = """
SELECT s.relname AS seq, t.relname AS tbl, a.attname AS col
FROM pg_class s
JOIN pg_depend dep ON dep.objid = s.oid AND dep.classid = 'pg_class'::regclass AND dep.deptype = 'a'
JOIN pg_class t ON t.oid = dep.refobjid
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = dep.refobjsubid
JOIN pg_namespace n ON n.oid = s.relnamespace
WHERE s.relkind = 'S' AND n.nspname = 'public'
ORDER BY s.relname;
"""

# I vincoli si applicano in due ondate: prima PK/UNIQUE/CHECK (indipendenti),
# poi le FOREIGN KEY, che richiedono l'esistenza della tabella referenziata.
Q_VINCOLI = """
SELECT c.contype::text AS tipo, r.relname AS tbl, c.conname AS nome,
       pg_get_constraintdef(c.oid) AS def
FROM pg_constraint c
JOIN pg_class r ON r.oid = c.conrelid
JOIN pg_namespace n ON n.oid = r.relnamespace
WHERE n.nspname = 'public' AND c.contype IN ('p', 'u', 'c', 'f')
ORDER BY CASE c.contype WHEN 'p' THEN 0 WHEN 'u' THEN 1 WHEN 'c' THEN 2 ELSE 3 END,
         r.relname, c.conname;
"""

# Solo gli indici che NON nascono da un vincolo: quelli li crea il vincolo.
Q_INDICI = """
SELECT indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname NOT IN (SELECT conname FROM pg_constraint WHERE contype IN ('p', 'u'))
ORDER BY tablename, indexname;
"""

# Ordine di creazione. `plpgsql` non valida i riferimenti a compile-time, ma
# `LANGUAGE sql` SI': se il corpo di una `sql` chiama un'altra funzione, quella
# deve gia' esistere. Quindi le `sql` vanno PER ULTIME fra le non-trigger, dopo
# tutte le plpgsql. Il caso che lo impone: get_distinct_files(uuid), che e'
# `sql`, delega a get_distinct_files(uuid, uuid), che e' `plpgsql`. Fra le
# `sql` restano prima le IMMUTABLE (foglie pure come _riparto_categoria_is_fb).
# I trigger chiudono, quando tutte le funzioni esistono.
Q_FUNZIONI = """
SELECT p.proname, pg_get_functiondef(p.oid) AS def
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname = 'public' AND p.prokind = 'f'
ORDER BY CASE WHEN p.prorettype = 'trigger'::regtype THEN 3
              WHEN p.provolatile = 'i' THEN 0
              WHEN l.lanname = 'sql' THEN 2
              ELSE 1 END,
         p.proname, pg_get_function_identity_arguments(p.oid);
"""

Q_TRIGGER = """
SELECT pg_get_triggerdef(t.oid) AS def
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname;
"""

# I GRANT sulle funzioni sono schema quanto il corpo: e' da un GRANT mancante
# che una funzione SECURITY DEFINER diventa leggibile con la chiave pubblica.
#
# Prima dei GRANT serve la REVOKE: Postgres concede EXECUTE a PUBLIC su ogni
# funzione appena creata, e PUBLIC include anon e authenticated. Il DB live ha
# quella revoca su 50 funzioni su 56 (misurato il 7/9/2026); senza riprodurla
# il DB di test direbbe "57 funzioni aperte ad anon" invece di 6, e un test sui
# permessi misurerebbe il default di Postgres, non il progetto.
#
# Le 6 che anon PUO' eseguire hanno invece GRANT NOMINALI ad anon e
# authenticated, non solo il permesso via PUBLIC: vengono dalle DEFAULT
# PRIVILEGES del progetto Supabase (`pg_default_acl`, defaclobjtype='f'), che
# concedono EXECUTE a quei ruoli su ogni funzione creata. Per questo lo snapshot
# emette anche i GRANT nominali: senza, il DB di test non riprodurrebbe il
# difetto e un test sui permessi passerebbe a torto.
Q_REVOKE_PUBLIC = """
SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS sig
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.prokind = 'f'
  AND p.prorettype <> 'trigger'::regtype
  AND NOT has_function_privilege('public', p.oid, 'EXECUTE')
ORDER BY 1;
"""

Q_GRANT_FUNZIONI = """
SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS sig,
       r.rolname
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
CROSS JOIN (SELECT unnest(ARRAY['anon', 'authenticated', 'service_role']) AS rolname) r
WHERE n.nspname = 'public' AND p.prokind = 'f'
  AND p.prorettype <> 'trigger'::regtype
  AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')
ORDER BY 1, 2;
"""

Q_RLS = """
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity
ORDER BY c.relname;
"""


def _connessione():
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO_ROOT / ".env")
            url = os.environ.get("SUPABASE_DB_URL")
        except ImportError:
            pass
    if not url:
        print(
            "SUPABASE_DB_URL non impostata: serve la stringa di connessione diretta\n"
            "al Postgres di Supabase (Project settings -> Database -> Connection string).\n"
            "Senza, questo script non puo' leggere i cataloghi.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    import psycopg

    return psycopg.connect(url)


def genera() -> str:
    with _connessione() as conn, conn.cursor() as cur:
        cur.execute(Q_SEQUENZE)
        sequenze = [r[0] for r in cur.fetchall()]
        cur.execute(Q_TABELLE)
        tabelle = cur.fetchall()
        cur.execute(Q_SEQ_OWNED)
        seq_owned = cur.fetchall()
        cur.execute(Q_VINCOLI)
        vincoli = cur.fetchall()
        cur.execute(Q_INDICI)
        indici = [r[0] for r in cur.fetchall()]
        cur.execute(Q_FUNZIONI)
        funzioni = cur.fetchall()
        cur.execute(Q_TRIGGER)
        trigger = [r[0] for r in cur.fetchall()]
        cur.execute(Q_REVOKE_PUBLIC)
        revoche = [r[0] for r in cur.fetchall()]
        cur.execute(Q_GRANT_FUNZIONI)
        grant = cur.fetchall()
        cur.execute(Q_RLS)
        rls = [r[0] for r in cur.fetchall()]

    p: list[str] = []
    p.append(
        "-- Snapshot dello schema `public` del DB live, generato da\n"
        "-- scripts/genera_schema_snapshot.py. NON modificare a mano: rigenerare.\n"
        "-- Serve a montare il Postgres dei test (le migration del repo non\n"
        "-- ricostruiscono il database: vedi il docstring dello script).\n"
        f"-- Rigenerato il {date.today().isoformat()}.\n"
    )
    p.append(PREAMBOLO)

    p.append("\n-- ── Sequenze ────────────────────────────────────────────────────")
    for s in sequenze:
        p.append(f"CREATE SEQUENCE IF NOT EXISTS public.{s};")

    p.append("\n-- ── Tabelle ─────────────────────────────────────────────────────")
    for tbl, cols in tabelle:
        p.append(f"CREATE TABLE IF NOT EXISTS public.{tbl} (\n{cols}\n);")

    p.append("\n-- ── Sequenze possedute da una colonna ───────────────────────────")
    for seq, tbl, col in seq_owned:
        p.append(f"ALTER SEQUENCE public.{seq} OWNED BY public.{tbl}.{col};")

    etichette = {"p": "Chiavi primarie", "u": "Vincoli UNIQUE", "c": "Vincoli CHECK",
                 "f": "Chiavi esterne"}
    tipo_corrente = None
    for tipo, tbl, nome, definizione in vincoli:
        if tipo != tipo_corrente:
            p.append(f"\n-- ── {etichette[tipo]} ──────────────────────────────────")
            tipo_corrente = tipo
        p.append(
            f"ALTER TABLE public.{tbl} ADD CONSTRAINT {nome} {definizione};"
        )

    p.append("\n-- ── Indici (esclusi quelli creati dai vincoli) ──────────────────")
    for definizione in indici:
        p.append(f"{definizione};")

    p.append("\n-- ── Funzioni ────────────────────────────────────────────────────")
    for _nome, definizione in funzioni:
        p.append(f"{definizione.rstrip()};")

    p.append("\n-- ── Trigger ─────────────────────────────────────────────────────")
    for definizione in trigger:
        p.append(f"{definizione};")

    p.append(
        "\n-- ── Permessi EXECUTE sulle funzioni ─────────────────────────────\n"
        "-- Fotografia dei permessi VERI, difetti compresi: e' cosi' che un test\n"
        "-- puo' vedere una funzione SECURITY DEFINER aperta ad anon.\n"
        "-- Prima le REVOKE da PUBLIC (che Postgres concede in automatico alla\n"
        "-- creazione), poi i GRANT espliciti."
    )
    for sig in revoche:
        p.append(f"REVOKE ALL ON FUNCTION public.{sig} FROM PUBLIC;")
    for sig, ruolo in grant:
        p.append(f"GRANT EXECUTE ON FUNCTION public.{sig} TO {ruolo};")

    p.append(
        "\n-- ── RLS ─────────────────────────────────────────────────────────\n"
        "-- Solo l'abilitazione, non le 96 policy: ogni client dell'app usa\n"
        "-- service_role (BYPASSRLS), quindi le policy non filtrano nulla e\n"
        "-- ricopiarle darebbe una protezione solo apparente ai test."
    )
    for tbl in rls:
        p.append(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY;")

    return "\n".join(p) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="non scrive: esce 1 se lo snapshot su disco e' diverso dal DB live",
    )
    args = parser.parse_args()

    nuovo = genera()
    if args.check:
        vecchio = DESTINAZIONE.read_text(encoding="utf-8") if DESTINAZIONE.exists() else ""
        # La riga della data cambia ogni giorno: non e' drift.
        def _senza_data(testo: str) -> str:
            return "\n".join(
                r for r in testo.splitlines() if not r.startswith("-- Rigenerato il ")
            )

        if _senza_data(vecchio) != _senza_data(nuovo):
            print("schema_snapshot.sql NON allineato al DB live: rigeneralo.")
            return 1
        print("schema_snapshot.sql allineato al DB live.")
        return 0

    DESTINAZIONE.parent.mkdir(parents=True, exist_ok=True)
    DESTINAZIONE.write_text(nuovo, encoding="utf-8")
    print(f"scritto {DESTINAZIONE.relative_to(REPO_ROOT)} ({len(nuovo.splitlines())} righe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
