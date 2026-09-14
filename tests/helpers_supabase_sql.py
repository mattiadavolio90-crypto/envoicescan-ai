"""Client Supabase finto che ESEGUE le catene del builder su un Postgres vero.

Perche' esiste
==============
Il worker parla col database attraverso `supabase-py`, cioe' PostgREST via HTTP:
nei test quella strada e' chiusa (guardia di rete del conftest) e finora ogni
endpoint e' stato provato con un MagicMock, che risponde a QUALUNQUE catena con
quello che il test gli ha messo dentro. Un mock cosi' non puo' misurare
l'isolamento fra clienti: se un endpoint dimentica `.eq("user_id", ...)`, il
mock non se ne accorge — e' il «mock generoso» che ha gia' lasciato scoperta
meta' di un fix (i test del radar passavano su una colonna mai esistita).

Questo client prende la STESSA catena che il codice di produzione costruisce
(`sb.table("fatture").select("id").eq("user_id", uid).is_("deleted_at",
"null").execute()`) e la traduce in SQL sul Postgres locale dei test SQL
(`tests/conftest_sql.py`, schema dallo snapshot del DB live). Se il filtro
manca, le righe dell'altro cliente tornano davvero. E' l'unico modo per
eseguire un filtro tenant invece di leggerlo.

Cosa traduce
============
Il sottoinsieme del builder che il codice usa, misurato il 14/09/2026 su
`services/` (occorrenze): eq 944, select 428, limit 145, update 107, order 94,
is_ 93, in_ 90, delete 67, gte 60, rpc 47, upsert 41, range 38, lte 35,
insert 34, neq 23, single 20, or_ 19, ilike 13, lt 11, maybe_single 4, gt 3,
not_ (is_/in_) 15, `count="exact"` 40, `head=True` 2. Zero embed nelle select,
zero path JSON nei filtri, zero alias.

Tutto il resto solleva `NonSupportato`: un endpoint che usa una forma nuova
finisce in 500 e va guardato, non assolto in silenzio.

Fedelta' a PostgREST — le scelte che contano
============================================
- I valori dei filtri vengono castati al tipo della colonna letto da
  `information_schema` (`%s::uuid`, `%s::int8`): PostgREST fa lo stesso lato
  server, e cosi' `.eq("id", "79")` su un bigint funziona come in produzione.
- `.single()` con 0 o >1 righe solleva `postgrest.exceptions.APIError` come il
  vero client (PGRST116); un errore SQL viene incapsulato nello stesso tipo, e
  la transazione torna al savepoint precedente, cosi' il test puo' continuare
  a interrogare il DB dopo un endpoint fallito.
- `numeric` esce come float, `uuid`/date/timestamp come stringhe ISO, jsonb
  come dict: e' quello che `httpx.json()` restituisce sul client vero.
- `.rpc()` chiama la funzione con argomenti NOMINATI castati ai tipi di
  `pg_proc`; una funzione scalare torna lo scalare, `RETURNS TABLE` una lista.
- Ogni `execute()` gira dentro un SAVEPOINT: come PostgREST, dove ogni
  richiesta e' una transazione a se'. Il rollback finale resta quello della
  fixture `db_sql`.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from postgrest.base_request_builder import APIResponse, SingleAPIResponse
from postgrest.exceptions import APIError
from psycopg.types.json import Jsonb


class NonSupportato(RuntimeError):
    """Forma del builder che questo client non traduce (di proposito rumoroso)."""


def _json_safe(valore: Any) -> Any:
    """Rende il valore identico a cio' che `httpx.json()` darebbe da PostgREST."""
    if isinstance(valore, Decimal):
        return float(valore)
    if isinstance(valore, (datetime, date, time)):
        return valore.isoformat()
    if isinstance(valore, UUID):
        return str(valore)
    if isinstance(valore, dict):
        return {k: _json_safe(v) for k, v in valore.items()}
    if isinstance(valore, (list, tuple)):
        return [_json_safe(v) for v in valore]
    if isinstance(valore, bytes):
        return valore.decode("utf-8", errors="replace")
    return valore


_ARRAY = re.compile(r"^_")


def _tipo_sql(udt: str) -> str:
    """`information_schema.columns.udt_name` -> tipo castabile (`_uuid` -> `uuid[]`)."""
    if _ARRAY.match(udt):
        return f"{udt[1:]}[]"
    return udt


def _adatta(valore: Any, udt: str) -> Any:
    """Adatta un valore Python al tipo della colonna prima di passarlo a psycopg."""
    if valore is None:
        return None
    if udt in ("jsonb", "json") and isinstance(valore, (dict, list)):
        return Jsonb(valore)
    if udt in ("bool",) and isinstance(valore, str):
        return valore.strip().lower() in ("true", "t", "1", "yes")
    if isinstance(valore, bool):
        return valore
    if isinstance(valore, (int, float, Decimal, str, date, datetime, time, UUID, list, dict)):
        return valore
    return str(valore)


class _Savepoint:
    """Ogni richiesta PostgREST e' atomica: si imita con un savepoint per execute."""

    _n = 0

    def __init__(self, conn):
        self._conn = conn
        _Savepoint._n += 1
        self._nome = f"sp_supabase_{_Savepoint._n}"

    def __enter__(self):
        self._conn.execute(f"SAVEPOINT {self._nome}")
        return self

    def __exit__(self, tipo, exc, tb):
        if exc is None:
            self._conn.execute(f"RELEASE SAVEPOINT {self._nome}")
        else:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {self._nome}")
        return False


class ClientSQL:
    """Sostituto del client supabase-py, agganciato a una connessione psycopg."""

    def __init__(self, conn):
        self._conn = conn
        self._colonne: Dict[str, Dict[str, str]] = {}
        self._pk: Dict[str, List[str]] = {}
        self.query_eseguite: List[Tuple[str, tuple]] = []
        # services.get_supabase_client() riallinea header e trasporto del client
        # vero ad ogni chiamata: qui non c'e' HTTP, ma senza questi attributi
        # ogni chiamata loggherebbe un warning "struttura httpx inattesa".
        self.options = SimpleNamespace(headers={})
        self.postgrest = SimpleNamespace(
            session=SimpleNamespace(headers={}, _transport=SimpleNamespace(
                _pool=SimpleNamespace(_http2=False, _keepalive_expiry=5.0))),
        )

    # -- API supabase-py --------------------------------------------------
    def table(self, nome: str) -> "_Builder":
        return _Builder(self, nome)

    from_ = table

    def rpc(self, nome: str, params: Optional[Dict[str, Any]] = None) -> "_Rpc":
        return _Rpc(self, nome, dict(params or {}))

    # -- catalogo ----------------------------------------------------------
    def colonne(self, tabella: str) -> Dict[str, str]:
        if tabella not in self._colonne:
            righe = self._conn.execute(
                "SELECT column_name, udt_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (tabella,),
            ).fetchall()
            if not righe:
                raise NonSupportato(f"tabella sconosciuta allo schema di test: {tabella}")
            self._colonne[tabella] = {r[0]: r[1] for r in righe}
        return self._colonne[tabella]

    def chiave_primaria(self, tabella: str) -> List[str]:
        if tabella not in self._pk:
            righe = self._conn.execute(
                "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema "
                "WHERE tc.table_schema = 'public' AND tc.table_name = %s "
                "  AND tc.constraint_type = 'PRIMARY KEY' ORDER BY kcu.ordinal_position",
                (tabella,),
            ).fetchall()
            self._pk[tabella] = [r[0] for r in righe]
        return self._pk[tabella]

    def nome_tipo(self, oid: int) -> str:
        """`pg_type.typname` di un OID: serve ai cast sui risultati delle RPC."""
        cache = self.__dict__.setdefault("_tipi_oid", {})
        if oid not in cache:
            riga = self._conn.execute("SELECT typname FROM pg_type WHERE oid = %s", (oid,)).fetchone()
            cache[oid] = riga[0] if riga else "text"
        return cache[oid]

    def udt(self, tabella: str, colonna: str) -> str:
        cols = self.colonne(tabella)
        if colonna not in cols:
            raise NonSupportato(f"colonna {tabella}.{colonna} inesistente nello schema di test")
        return cols[colonna]

    # -- esecuzione --------------------------------------------------------
    def esegui(self, sql: str, params: Sequence[Any] = ()) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Esegue in un savepoint; ritorna (righe come dict, nome della prima colonna)."""
        self.query_eseguite.append((sql, tuple(params)))
        try:
            with _Savepoint(self._conn):
                cur = self._conn.execute(sql, tuple(params))
                if cur.description is None:
                    return [], None
                nomi = [d.name for d in cur.description]
                righe = [dict(zip(nomi, r)) for r in cur.fetchall()]
                return righe, nomi[0]
        except NonSupportato:
            raise
        except Exception as errore:  # errore SQL -> come PostgREST, un APIError
            raise APIError({
                "message": str(errore).strip(),
                "code": getattr(errore, "sqlstate", None) or "PGRST000",
                "details": f"sql={sql!r} params={tuple(params)!r}",
                "hint": "",
            }) from errore


# ─── filtri PostgREST (`or_`) ──────────────────────────────────────────────
_OPERATORI = {
    "eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "LIKE", "ilike": "ILIKE",
}


def _spezza_virgole(testo: str) -> List[str]:
    """Divide sulle virgole di primo livello (rispetta le parentesi)."""
    pezzi, livello, corrente = [], 0, []
    for ch in testo:
        if ch == "(":
            livello += 1
        elif ch == ")":
            livello -= 1
        if ch == "," and livello == 0:
            pezzi.append("".join(corrente))
            corrente = []
        else:
            corrente.append(ch)
    if corrente:
        pezzi.append("".join(corrente))
    return [p for p in pezzi if p != ""]


class _Builder:
    def __init__(self, client: ClientSQL, tabella: str):
        self._c = client
        self._t = tabella
        self._op = "select"
        self._cols = "*"
        self._count: Optional[str] = None
        self._head = False
        self._where: List[Tuple[str, list]] = []
        self._order: List[str] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._single: Optional[str] = None
        self._payload: Any = None
        self._on_conflict: Optional[str] = None
        self._ignore_duplicates = False

    # -- operazioni --------------------------------------------------------
    def select(self, columns: str = "*", count: Optional[str] = None, head: bool = False, **_k):
        if _k:
            raise NonSupportato(f"select kwargs non tradotti: {_k}")
        self._op = "select" if self._op == "select" else self._op
        self._cols = columns
        self._count = count
        self._head = head
        return self

    def insert(self, json_: Any, count: Optional[str] = None, returning: str = "representation",
               upsert: bool = False, **_k):
        self._op = "upsert" if upsert else "insert"
        self._payload = json_
        self._count = count
        return self

    def upsert(self, json_: Any, count: Optional[str] = None, on_conflict: Optional[str] = None,
               ignore_duplicates: bool = False, returning: str = "representation", **_k):
        self._op = "upsert"
        self._payload = json_
        self._count = count
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        return self

    def update(self, json_: Dict[str, Any], count: Optional[str] = None, **_k):
        self._op = "update"
        self._payload = json_
        self._count = count
        return self

    def delete(self, count: Optional[str] = None, **_k):
        self._op = "delete"
        self._count = count
        return self

    # -- sorgente e tipi: una tabella, oppure (nelle RPC) il risultato di una funzione
    def _udt(self, col: str) -> str:
        return self._c.udt(self._t, col)

    def _fonte(self) -> Tuple[str, list]:
        return f'public."{self._t}"', []

    # -- filtri ------------------------------------------------------------
    def _cast(self, col: str) -> str:
        return _tipo_sql(self._udt(col))

    def _confronto(self, col: str, op: str, val: Any, negato: bool = False):
        tipo = self._cast(col)
        udt = self._udt(col)
        frammento = f'"{col}" {_OPERATORI[op]} %s::{tipo}'
        if negato:
            frammento = f"NOT ({frammento})"
        self._where.append((frammento, [_adatta(val, udt)]))
        return self

    def eq(self, col, val):
        return self._confronto(col, "eq", val)

    def neq(self, col, val):
        return self._confronto(col, "neq", val)

    def gt(self, col, val):
        return self._confronto(col, "gt", val)

    def gte(self, col, val):
        return self._confronto(col, "gte", val)

    def lt(self, col, val):
        return self._confronto(col, "lt", val)

    def lte(self, col, val):
        return self._confronto(col, "lte", val)

    def like(self, col, pattern):
        return self._confronto(col, "like", str(pattern).replace("*", "%"))

    def ilike(self, col, pattern):
        return self._confronto(col, "ilike", str(pattern).replace("*", "%"))

    def is_(self, col, val, negato: bool = False):
        self._udt(col)
        if val is None or (isinstance(val, str) and val.strip().lower() == "null"):
            fr = f'"{col}" IS NULL'
        elif isinstance(val, str) and val.strip().lower().replace(".", " ") == "not null":
            fr = f'"{col}" IS NOT NULL'
        elif val is True or (isinstance(val, str) and val.lower() == "true"):
            fr = f'"{col}" IS TRUE'
        elif val is False or (isinstance(val, str) and val.lower() == "false"):
            fr = f'"{col}" IS FALSE'
        else:
            raise NonSupportato(f"is_({col!r}, {val!r})")
        if negato:
            fr = f"NOT ({fr})"
        self._where.append((fr, []))
        return self

    def in_(self, col, valori, negato: bool = False):
        tipo = self._cast(col)
        valori = list(valori)
        if not valori:
            self._where.append(("TRUE" if negato else "FALSE", []))
            return self
        fr = f'"{col}" = ANY(%s::{tipo}[])'
        if negato:
            fr = f"NOT ({fr})"
        self._where.append((fr, [[_adatta(v, self._udt(col)) for v in valori]]))
        return self

    def match(self, criteri: Dict[str, Any]):
        for k, v in criteri.items():
            self.eq(k, v)
        return self

    def contains(self, col, val):
        udt = self._udt(col)
        tipo = _tipo_sql(udt)
        self._where.append((f'"{col}" @> %s::{tipo}', [_adatta(val, udt)]))
        return self

    def or_(self, filtri: str, **_k):
        if _k:
            raise NonSupportato(f"or_ kwargs non tradotti: {_k}")
        fr, params = self._traduci_gruppo(filtri, "OR")
        self._where.append((fr, params))
        return self

    def _traduci_gruppo(self, testo: str, congiunzione: str) -> Tuple[str, list]:
        frammenti, params = [], []
        for pezzo in _spezza_virgole(testo.strip()):
            m = re.match(r"^(and|or)\((.*)\)$", pezzo, re.S)
            if m:
                fr, p = self._traduci_gruppo(m.group(2), m.group(1).upper())
            else:
                fr, p = self._traduci_condizione(pezzo)
            frammenti.append(f"({fr})")
            params.extend(p)
        return f" {congiunzione} ".join(frammenti), params

    def _traduci_condizione(self, pezzo: str) -> Tuple[str, list]:
        negato = pezzo.startswith("not.")
        if negato:
            pezzo = pezzo[4:]
        parti = pezzo.split(".", 2)
        if len(parti) != 3:
            raise NonSupportato(f"condizione PostgREST non tradotta: {pezzo!r}")
        col, op, val = parti
        udt = self._udt(col)
        tipo = _tipo_sql(udt)
        if op == "is":
            v = val.lower()
            fr = {"null": f'"{col}" IS NULL', "true": f'"{col}" IS TRUE', "false": f'"{col}" IS FALSE'}.get(v)
            if fr is None:
                raise NonSupportato(f"is.{val}")
            p: list = []
        elif op == "in":
            valori = [x.strip().strip('"') for x in val.strip("()").split(",") if x.strip()]
            fr = f'"{col}" = ANY(%s::{tipo}[])'
            p = [valori]
        elif op in _OPERATORI:
            fr = f'"{col}" {_OPERATORI[op]} %s::{tipo}'
            p = [_adatta(val.replace("*", "%") if op in ("like", "ilike") else val, udt)]
        else:
            raise NonSupportato(f"operatore PostgREST non tradotto: {op}")
        if negato:
            fr = f"NOT ({fr})"
        return fr, p

    @property
    def not_(self):
        return _Negato(self)

    # -- ordinamento e paginazione ------------------------------------------
    def order(self, col: str, desc: bool = False, nullsfirst: Optional[bool] = None, **_k):
        if _k:
            raise NonSupportato(f"order kwargs non tradotti: {_k}")
        self._udt(col)
        fr = f'"{col}" {"DESC" if desc else "ASC"}'
        if nullsfirst is True:
            fr += " NULLS FIRST"
        elif nullsfirst is False:
            fr += " NULLS LAST"
        self._order.append(fr)
        return self

    def limit(self, n: int, **_k):
        self._limit = int(n)
        return self

    def range(self, start: int, end: int, **_k):
        self._offset = int(start)
        self._limit = int(end) - int(start) + 1
        return self

    def single(self):
        self._single = "single"
        return self

    def maybe_single(self):
        self._single = "maybe"
        return self

    # -- esecuzione --------------------------------------------------------
    def _where_sql(self) -> Tuple[str, list]:
        if not self._where:
            return "", []
        return " WHERE " + " AND ".join(f"({fr})" for fr, _ in self._where), [
            p for _, ps in self._where for p in ps
        ]

    def _colonne_select(self) -> str:
        cols = re.sub(r"\s+", "", self._cols)
        if cols == "*":
            return "*"
        out = []
        for c in cols.split(","):
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", c):
                raise NonSupportato(f"select con forma non tradotta: {c!r}")
            self._udt(c)
            out.append(f'"{c}"')
        return ", ".join(out)

    def _righe_payload(self) -> List[Dict[str, Any]]:
        righe = self._payload if isinstance(self._payload, list) else [self._payload]
        if not righe or any(not isinstance(r, dict) for r in righe):
            raise NonSupportato(f"payload non tradotto: {self._payload!r}")
        return righe

    def execute(self):
        where, wparams = self._where_sql()
        tab, tparams = self._fonte()
        conteggio: Optional[int] = None

        if self._op == "select":
            if self._count == "exact":
                conteggio = self._c.esegui(f"SELECT count(*) AS n FROM {tab}{where}", tparams + wparams)[0][0]["n"]
            if self._head:
                return APIResponse(data=[], count=conteggio)
            sql = f"SELECT {self._colonne_select()} FROM {tab}{where}"
            if self._order:
                sql += " ORDER BY " + ", ".join(self._order)
            params = tparams + list(wparams)
            if self._limit is not None:
                sql += " LIMIT %s"
                params.append(self._limit)
            if self._offset:
                sql += " OFFSET %s"
                params.append(self._offset)
            righe, _ = self._c.esegui(sql, params)

        elif self._op in ("insert", "upsert"):
            righe_in = self._righe_payload()
            cols = list(dict.fromkeys(k for r in righe_in for k in r))
            for c in cols:
                self._c.udt(self._t, c)
            valori_sql, params = [], []
            for r in righe_in:
                celle = []
                for c in cols:
                    if c in r:
                        celle.append(f"%s::{_tipo_sql(self._c.udt(self._t, c))}")
                        params.append(_adatta(r[c], self._c.udt(self._t, c)))
                    else:
                        celle.append("DEFAULT")
                valori_sql.append("(" + ", ".join(celle) + ")")
            sql = (f"INSERT INTO {tab} (" + ", ".join(f'"{c}"' for c in cols) + ") VALUES "
                   + ", ".join(valori_sql))
            if self._op == "upsert":
                conflitto = [c.strip() for c in (self._on_conflict or ",".join(self._c.chiave_primaria(self._t))).split(",") if c.strip()]
                if not conflitto:
                    raise NonSupportato(f"upsert su {self._t} senza chiave di conflitto")
                sql += " ON CONFLICT (" + ", ".join(f'"{c}"' for c in conflitto) + ")"
                da_aggiornare = [c for c in cols if c not in conflitto]
                if self._ignore_duplicates or not da_aggiornare:
                    sql += " DO NOTHING"
                else:
                    sql += " DO UPDATE SET " + ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in da_aggiornare)
            sql += " RETURNING *"
            righe, _ = self._c.esegui(sql, params)

        elif self._op == "update":
            if not isinstance(self._payload, dict) or not self._payload:
                raise NonSupportato(f"update con payload {self._payload!r}")
            set_sql, params = [], []
            for c, v in self._payload.items():
                udt = self._c.udt(self._t, c)
                set_sql.append(f'"{c}" = %s::{_tipo_sql(udt)}')
                params.append(_adatta(v, udt))
            sql = f"UPDATE {tab} SET " + ", ".join(set_sql) + where + " RETURNING *"
            righe, _ = self._c.esegui(sql, params + wparams)

        elif self._op == "delete":
            sql = f"DELETE FROM {tab}{where} RETURNING *"
            righe, _ = self._c.esegui(sql, wparams)
        else:  # pragma: no cover
            raise NonSupportato(self._op)

        righe = [_json_safe(r) for r in righe]
        if self._count == "exact" and conteggio is None:
            conteggio = len(righe)

        if self._single == "single":
            if len(righe) != 1:
                raise APIError({
                    "message": "JSON object requested, multiple (or no) rows returned",
                    "code": "PGRST116", "details": f"{len(righe)} rows", "hint": "",
                })
            return SingleAPIResponse(data=righe[0], count=conteggio)
        if self._single == "maybe":
            if len(righe) > 1:
                raise APIError({
                    "message": "JSON object requested, multiple rows returned",
                    "code": "PGRST116", "details": f"{len(righe)} rows", "hint": "",
                })
            return SingleAPIResponse(data=righe[0] if righe else None, count=conteggio)
        return APIResponse(data=righe, count=conteggio)


class _Negato:
    """Proxy di `.not_`: nega il filtro successivo."""

    def __init__(self, b: _Builder):
        self._b = b

    def is_(self, col, val):
        return self._b.is_(col, val, negato=True)

    def in_(self, col, valori):
        return self._b.in_(col, valori, negato=True)

    def eq(self, col, val):
        return self._b._confronto(col, "eq", val, negato=True)

    def neq(self, col, val):
        return self._b._confronto(col, "neq", val, negato=True)

    def ilike(self, col, pattern):
        return self._b._confronto(col, "ilike", str(pattern).replace("*", "%"), negato=True)

    def like(self, col, pattern):
        return self._b._confronto(col, "like", str(pattern).replace("*", "%"), negato=True)

    def __getattr__(self, nome):
        raise NonSupportato(f"not_.{nome} non tradotto")


class _Rpc(_Builder):
    """`sb.rpc(nome, params)`: la funzione e' la sorgente, poi valgono i filtri
    e la paginazione del builder (`.range()` dopo `.rpc()` e' usato dallo
    scadenziario, che pagina una RPC SETOF)."""

    def __init__(self, client: ClientSQL, nome: str, params: Dict[str, Any]):
        super().__init__(client, nome)
        self._nome = nome
        self._params = params
        self._tipi_risultato: Optional[Dict[str, str]] = None
        self._firma_cache: Optional[Tuple[List[str], List[str], str]] = None

    def _firma(self) -> Tuple[List[str], List[str], str]:
        """(nomi argomenti in ingresso, tipi, tipo di ritorno) dell'overload che combacia."""
        if self._firma_cache:
            return self._firma_cache
        righe = self._c._conn.execute(
            "SELECT p.proargnames, p.proargmodes, p.proargtypes::regtype[]::text[], "
            "       pg_get_function_result(p.oid), p.pronargdefaults "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = %s",
            (self._nome,),
        ).fetchall()
        if not righe:
            raise NonSupportato(f"RPC {self._nome} inesistente nello schema di test")
        candidati = []
        for nomi, modi, tipi, ritorno, n_default in righe:
            nomi = list(nomi or [])
            modi = list(modi or ["i"] * len(nomi))
            in_nomi = [n for n, m in zip(nomi, modi) if m in ("i", "b", "v")]
            passati = set(self._params)
            if not passati.issubset(set(in_nomi)):
                continue
            obbligatori = in_nomi[: max(0, len(in_nomi) - int(n_default or 0))]
            if not set(obbligatori).issubset(passati):
                continue
            candidati.append((len(in_nomi) - len(passati), in_nomi, list(tipi), ritorno))
        if not candidati:
            raise NonSupportato(f"RPC {self._nome}: nessun overload accetta {sorted(self._params)}")
        candidati.sort(key=lambda c: c[0])
        _, in_nomi, tipi, ritorno = candidati[0]
        self._firma_cache = (in_nomi, tipi, ritorno)
        return self._firma_cache

    def _chiamata(self) -> Tuple[str, list]:
        in_nomi, tipi, _ = self._firma()
        tipo_per_nome = dict(zip(in_nomi, tipi))
        args, params = [], []
        for nome, valore in self._params.items():
            tipo = tipo_per_nome[nome]
            args.append(f"{nome} := %s::{tipo}")
            params.append(_adatta(valore, "jsonb" if tipo in ("jsonb", "json") else ""))
        return f"public.{self._nome}(" + ", ".join(args) + ")", params

    def _fonte(self) -> Tuple[str, list]:
        chiamata, params = self._chiamata()
        return f"(SELECT * FROM {chiamata}) AS t", params

    def _udt(self, col: str) -> str:
        if self._tipi_risultato is None:
            chiamata, params = self._chiamata()
            self._c.query_eseguite.append((f"-- tipi di {self._nome}", ()))
            with _Savepoint(self._c._conn):
                cur = self._c._conn.execute(f"SELECT * FROM {chiamata} LIMIT 0", tuple(params))
                self._tipi_risultato = {d.name: self._c.nome_tipo(d.type_code) for d in cur.description}
        if col not in self._tipi_risultato:
            raise NonSupportato(f"colonna {col!r} assente dal risultato di {self._nome}")
        return self._tipi_risultato[col]

    def execute(self):
        _, _, ritorno = self._firma()
        if ritorno.upper().startswith(("TABLE", "SETOF", "RECORD")):
            return super().execute()
        # Funzione scalare: APIResponse pretende una lista; il client vero espone
        # il valore nudo in `.data`. Si imita la forma letta dal codice, non la classe.
        chiamata, params = self._chiamata()
        righe, prima = self._c.esegui(f"SELECT * FROM {chiamata}", params)
        valore = righe[0][prima] if righe else None
        return SimpleNamespace(data=_json_safe(valore), count=None)
