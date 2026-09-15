"""Ciclo di vita delle colonne del DB: chi le scrive, chi le legge, chi non le nomina mai.

Perche' esiste
==============
Il DB ha 667 colonne su 59 tabelle (misurato il 15/09/2026), cresciute in sei
mesi di sviluppo veloce. Una colonna scritta e mai letta e' lavoro sprecato a
ogni riga inserita; una **letta e mai scritta** e' peggio: qualcuno legge un
valore che non arriva mai. E' la famiglia del KPI a 0,00 EUR (un tab leggeva lo
snapshot, l'altro l'override) e del radar verde su `fatture_documenti.upload_id`,
colonna mai esistita. La lente L5 dell'audit trasversale nasce per questa classe.

Cosa fa
=======
Legge i file UNA volta sola (un `grep` per colonna costa ~7 s a colonna: oltre
un'ora per 336 nomi) e per ogni colonna distingue:

- **letture**: `.select("...")`, `.eq("col", ...)` e gli altri filtri del builder
  Supabase, `row["col"]`, `row.get("col")` in Python; `.select`/filtri e
  `obj.col` in TypeScript; ogni uso non di definizione nell'SQL;
- **scritture**: le chiavi dei dizionari passati a `.insert/.update/.upsert`
  (Python e TypeScript), `INSERT INTO t (cols)`, `UPDATE t SET col =`,
  `NEW.col :=` nei trigger. Un default non NULL e' una scrittura (del DB).

Le scritture sono attribuite alla tabella quando la catena la nomina
(`.table("x")`, `.from("x")`, `INSERT INTO x`, il trigger `ON x`); altrimenti
restano "senza tabella" e valgono come segnale debole. Se un `.insert(payload)`
riceve una variabile e non un dizionario letterale, la scrittura e' **opaca**:
per quella tabella non si puo' dire "mai scritta" con certezza, e lo script lo
dichiara invece di tacere.

Trappole gia' pagate (15/09/2026), incorporate qui
=================================================
1. Il grep su Python/TS non vede l'SQL: `idempotency_key` ha 0 riscontri nel
   codice applicativo ed e' viva (un `unique (...)` in migration). Si scandisce
   anche `supabase/`.
2. Creazione != uso: la riga `ADD COLUMN`, la definizione dentro `CREATE TABLE`,
   `COMMENT ON COLUMN` e i commenti `--` NON contano come uso.
3. Nomi corti senza word boundary: `ack` matcha dentro "fallback". `\b` sempre.
4. Trigger e default scrivono senza comparire nel codice: i corpi dei trigger
   stanno nello snapshot dello schema (che e' in `supabase/`) e i default nel
   `CREATE TABLE`.
5. Il frontend puo' leggere per nome dinamico (`row[campo]`): 0 occorrenze nel
   frontend NON prova che il campo non sia consumato.
6. "0 righe a DB" non e' "colonna morta" (puo' essere nuova) e una colonna piena
   di dati puo' non essere letta da nessuno. Il CSV `--stat` (vedi sotto) serve
   a incrociare, non a decidere da solo.

Limiti dichiarati
=================
- `tools/` non e' nel perimetro (script manutentivi, non runtime): un grep a
  mano l'ha trovato innocuo il 15/09 (un solo hit, in tools/check_migrations.py).
- Nell'SQL, lettura e scrittura si distinguono per statement: le colonne di un
  `INSERT`/`UPDATE SET`/`NEW.col :=` sono scritture, ogni altro uso e' lettura.
  In `UPDATE t SET a = b` l'intera clausola SET e' scrittura: `b` perde la sua
  lettura (verificato il 15/09 che non sposta nessun verdetto: le colonne
  «morte» hanno tutte 0 usi SQL).
  Una funzione che la nomina in un `WHERE` conta come lettore anche se e' un
  job di purge: il verdetto «scritta mai letta» va comunque riletto al call site.
- Le tabelle si attribuiscono solo dalle catene che le nominano con una
  stringa letterale (`.table("x")`, `.from("x")`, `INSERT INTO x`). Un nome
  di tabella in una variabile lascia la scrittura «opaca senza tabella».

Uso
===
    python scripts/audit_ciclo_vita_colonne.py                 # inventario
    python scripts/audit_ciclo_vita_colonne.py --taratura      # esce 1 se i casi noti non tornano
    python scripts/audit_ciclo_vita_colonne.py --stat docs/storico/audit-2026-09/L5_stat_colonne_2026-09-15.csv
    python scripts/audit_ciclo_vita_colonne.py --json /tmp/inventario.json

Lo schema viene da `supabase/schema_snapshot.sql` (riproducibile senza DB). Il
CSV di `--stat` e' la fotografia dei dati e si produce sul DB live con:

    SELECT c.table_name AS tabella, c.column_name AS colonna, c.data_type AS tipo,
           c.is_nullable AS nullable, c.column_default AS "default",
           (xpath('/row/n/text()',  x.doc))[1]::text::bigint AS n,
           (xpath('/row/nn/text()', x.doc))[1]::text::bigint AS nn,
           (xpath('/row/nd/text()', x.doc))[1]::text::bigint AS nd
    FROM information_schema.columns c
    JOIN information_schema.tables tb ON tb.table_schema = c.table_schema
         AND tb.table_name = c.table_name AND tb.table_type = 'BASE TABLE',
    LATERAL (SELECT query_to_xml(format(
        'select count(*) as n, count(%I) as nn, count(distinct (%I)::text) as nd from public.%I',
        c.column_name, c.column_name, c.table_name), false, true, '') AS doc) x
    WHERE c.table_schema = 'public' ORDER BY 1, 2;

(`n` righe della tabella, `nn` valori non NULL, `nd` valori distinti.) Se il CSV
elenca colonne che lo snapshot non ha, lo script le aggiunge e le segnala: e' il
drift dello snapshot, non un errore.

Sola lettura: non tocca ne' il DB ne' i file. Non propone migration: far cadere
una colonna e' irreversibile e la decisione e' di Mattia.
"""
from __future__ import annotations

import argparse
import ast
import collections
import csv
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "supabase" / "schema_snapshot.sql"
DIR_CODICE = ("services", "utils", "config", "worker", "scripts", "apps/web/src")
DIR_EDGE = ("supabase/functions",)
DIR_SQL = ("supabase",)
ESCLUDI = ("node_modules", "__pycache__", ".next")
QUESTO_FILE = pathlib.Path(__file__).resolve()  # nomina le colonne nel docstring: fuori dal perimetro

FILTRI_BUILDER = {
    "eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is_", "in_", "is", "in",
    "contains", "contained_by", "order", "filter", "match", "not_", "text_search",
    "on_conflict", "range_gt", "range_lt", "range_gte", "range_lte", "overlaps",
}
SCRITTORI_BUILDER = {"insert", "upsert", "update"}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Taratura del 15/09/2026 (file di codice che nominano il nome, perimetro DIR_CODICE).
# Le cifre contano i file VERSIONATI: `deleted_at` fu inciso a 37 misurando un
# filesystem con 4 script di lavoro non committati in `scripts/`, e in CI (checkout
# pulito) ne risultavano 33 — rosso sul solo ambiente, col repo identico. Ora il
# perimetro e' `git ls-files`, quindi la cifra giusta e' 33 ovunque.
TARATURA_FILE_CODICE = {
    "correzioni_count": 0, "ultimo_correttore": 0,           # morte, confermate da L4
    "consecutive_correct_classifications": 4, "categoria_fonte": 12,
    "tipo_attivita": 16, "deleted_at": 33,                   # vive
}


# ---------------------------------------------------------------- schema


def leggi_snapshot(percorso: pathlib.Path) -> dict[tuple[str, str], str | None]:
    """(tabella, colonna) -> default, dai `CREATE TABLE` dello snapshot."""
    testo = percorso.read_text(encoding="utf-8", errors="ignore")
    colonne: dict[tuple[str, str], str | None] = {}
    for blocco in re.finditer(
        r"CREATE TABLE IF NOT EXISTS public\.(\w+) \((.*?)\n\);", testo, re.S
    ):
        tabella = blocco.group(1)
        for riga in blocco.group(2).splitlines():
            riga = riga.strip().rstrip(",")
            if riga.upper().startswith(("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN")):
                continue
            m = re.match(r'^"?([a-z_][a-z0-9_]*)"?\s+[a-z"]', riga)
            if not m:
                continue
            d = re.search(r"\bDEFAULT\s+(.+?)(?:\s+NOT NULL)?$", riga)
            default = d.group(1).strip() if d else None
            if default and default.upper().startswith("NULL"):
                default = None
            colonne[(tabella, m.group(1))] = default
    return colonne


def leggi_stat(percorso: pathlib.Path) -> dict[tuple[str, str], dict]:
    stat: dict[tuple[str, str], dict] = {}
    with percorso.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            stat[(r["tabella"], r["colonna"])] = {
                "n": int(r["n"]), "nn": int(r["nn"]), "nd": int(r["nd"]),
                "default": (r.get("default") or None),
            }
    return stat


# ---------------------------------------------------------------- file


def _file_versionati() -> set[pathlib.Path] | None:
    """I path tracciati da git, o None se git non risponde.

    Il perimetro deve essere il REPO, non il filesystem: uno script di lavoro non
    versionato in `scripts/` conta come file di codice e sposta la cifra. E' gia'
    successo — la taratura di `deleted_at` fu incisa a 37 su una macchina con 4
    script locali non committati, e in CI (checkout pulito) ne risultavano 33: il
    test di taratura falliva sul solo ambiente, senza che il repo fosse cambiato.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {
        (ROOT / nome).resolve()
        for nome in res.stdout.decode("utf-8", "replace").split("\0")
        if nome
    }


def elenca_file(radici: tuple[str, ...], estensioni: tuple[str, ...]) -> list[pathlib.Path]:
    versionati = _file_versionati()
    out: list[pathlib.Path] = []
    for radice in radici:
        base = ROOT / radice
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix not in estensioni or not p.is_file():
                continue
            if any(parte in ESCLUDI for parte in p.parts) or p.resolve() == QUESTO_FILE:
                continue
            if versionati is not None and p.resolve() not in versionati:
                continue
            out.append(p)
    return out


# ---------------------------------------------------------------- Python (AST)


class Occorrenze:
    """Letture e scritture raccolte da tutti i file, per nome e per (tabella, nome)."""

    def __init__(self) -> None:
        self.letture_nome: collections.Counter = collections.Counter()
        self.letture_tab: collections.Counter = collections.Counter()
        self.scritture_nome: collections.Counter = collections.Counter()
        self.scritture_tab: collections.Counter = collections.Counter()
        self.scritture_opache: collections.Counter = collections.Counter()  # per tabella
        self.dove: dict[tuple[str, str, str], list[str]] = collections.defaultdict(list)

    def leggi(self, nome: str, tabella: str | None, dove: str) -> None:
        self.letture_nome[nome] += 1
        if tabella:
            self.letture_tab[(tabella, nome)] += 1
        self.dove[("L", tabella or "", nome)].append(dove)

    def scrivi(self, nome: str, tabella: str | None, dove: str) -> None:
        self.scritture_nome[nome] += 1
        if tabella:
            self.scritture_tab[(tabella, nome)] += 1
        self.dove[("S", tabella or "", nome)].append(dove)


def _tabella_della_catena(nodo: ast.AST) -> str | None:
    """Risale `x.table("t").select(...).eq(...)` fino a `.table("t")` / `.from_("t")`."""
    while isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
        if nodo.func.attr in ("table", "from_") and nodo.args:
            a = nodo.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                return a.value
            return None
        nodo = nodo.func.value
    return None


def _chiavi_dict(nodo: ast.AST) -> tuple[set[str], bool]:
    """Chiavi stringa dei dizionari letterali (anche in liste). (chiavi, opaco)."""
    chiavi: set[str] = set()
    opaco = False
    if isinstance(nodo, ast.Dict):
        for k in nodo.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                chiavi.add(k.value)
            else:
                opaco = True  # `**altro` o chiave calcolata
    elif isinstance(nodo, (ast.List, ast.Tuple)):
        for el in nodo.elts:
            c, o = _chiavi_dict(el)
            chiavi |= c
            opaco = opaco or o
    else:
        opaco = True
    return chiavi, opaco


def _costanti_modulo(albero: ast.Module) -> dict[str, str]:
    """`_SEDE_SELECT = "id,nome,..."` a livello di modulo: `.select(_SEDE_SELECT)` la usa."""
    out: dict[str, str] = {}
    for nodo in albero.body:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            if isinstance(nodo.value, ast.Constant) and isinstance(nodo.value.value, str):
                out[nodo.targets[0].id] = nodo.value.value
    return out


def _stringa(nodo: ast.AST, costanti: dict[str, str]) -> str | None:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.Name):
        return costanti.get(nodo.id)
    return None


def scandisci_python(percorso: pathlib.Path, occ: Occorrenze, nomi: set[str]) -> bool:
    """False se il file non si lascia parsare: un file saltato in silenzio e' un buco."""
    # utf-8-sig: 10 file del repo hanno il BOM, e con "utf-8" ast.parse fallisce
    # su U+FEFF — fra loro fastapi_worker.py e invoice_service.py (15/09/2026).
    try:
        albero = ast.parse(percorso.read_text(encoding="utf-8-sig", errors="ignore"))
    except SyntaxError:
        return False
    costanti = _costanti_modulo(albero)
    rel = str(percorso.relative_to(ROOT))
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            metodo = nodo.func.attr
            dove = f"{rel}:{nodo.lineno}"
            if metodo in SCRITTORI_BUILDER and nodo.args:
                tabella = _tabella_della_catena(nodo)
                chiavi, opaco = _chiavi_dict(nodo.args[0])
                for c in chiavi & nomi:
                    occ.scrivi(c, tabella, dove)
                if opaco:
                    occ.scritture_opache[tabella or "?"] += 1
            elif metodo == "select" and nodo.args:
                testo = _stringa(nodo.args[0], costanti)
                if testo is not None:
                    tabella = _tabella_della_catena(nodo)
                    for c in set(IDENT.findall(testo)) & nomi:
                        occ.leggi(c, tabella, dove)
            elif metodo in FILTRI_BUILDER and nodo.args:
                testo = _stringa(nodo.args[0], costanti)
                if testo is not None:
                    tabella = _tabella_della_catena(nodo)
                    for c in set(IDENT.findall(testo)) & nomi:
                        occ.leggi(c, tabella, dove)
            elif metodo == "get" and nodo.args:
                a = nodo.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value in nomi:
                    occ.leggi(a.value, None, dove)
        elif isinstance(nodo, ast.Subscript) and isinstance(nodo.ctx, ast.Load):
            s = nodo.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, str) and s.value in nomi:
                occ.leggi(s.value, None, f"{rel}:{nodo.lineno}")
    return True


# ---------------------------------------------------------------- TypeScript (regex)

RE_TS_SELECT = re.compile(r"\.select\(\s*[`\"']([^`\"']*)[`\"']")
RE_TS_FILTRO = re.compile(
    r"\.(?:eq|neq|gt|gte|lt|lte|like|ilike|is|in|contains|order|match|not|filter)\(\s*[\"']([A-Za-z_][A-Za-z0-9_.]*)[\"']"
)
RE_TS_SCRITTURA = re.compile(r"\.(insert|update|upsert)\(\s*")
RE_TS_FROM = re.compile(r"\.from\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\)")
RE_TS_CHIAVE = re.compile(r"(?:^|[{,\s])([A-Za-z_][A-Za-z0-9_]*)\s*(?=[:,}])")
RE_TS_PROPRIETA = re.compile(r"(?:\?\.|\.)([A-Za-z_][A-Za-z0-9_]*)\b|\[[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\]")


def _blocco_bilanciato(testo: str, inizio: int) -> str | None:
    """Il testo fra la parentesi/graffa in `inizio` e la sua chiusura."""
    apri = testo[inizio]
    chiudi = {"{": "}", "[": "]", "(": ")"}.get(apri)
    if not chiudi:
        return None
    livello = 0
    for i in range(inizio, min(len(testo), inizio + 20000)):
        ch = testo[i]
        if ch in "{[(":
            livello += 1
        elif ch in "}])":
            livello -= 1
            if livello == 0:
                return testo[inizio:i + 1]
    return None


def _tabella_ts(testo: str, pos: int) -> str | None:
    finestra = testo[max(0, pos - 400):pos]
    trovate = RE_TS_FROM.findall(finestra)
    return trovate[-1] if trovate else None


def scandisci_typescript(percorso: pathlib.Path, occ: Occorrenze, nomi: set[str]) -> None:
    testo = percorso.read_text(encoding="utf-8-sig", errors="ignore")
    rel = str(percorso.relative_to(ROOT))

    def riga(pos: int) -> str:
        return f"{rel}:{testo.count(chr(10), 0, pos) + 1}"

    for m in RE_TS_SELECT.finditer(testo):
        tab = _tabella_ts(testo, m.start())
        for c in set(IDENT.findall(m.group(1))) & nomi:
            occ.leggi(c, tab, riga(m.start()))
    for m in RE_TS_FILTRO.finditer(testo):
        tab = _tabella_ts(testo, m.start())
        for c in set(IDENT.findall(m.group(1))) & nomi:
            occ.leggi(c, tab, riga(m.start()))
    for m in RE_TS_SCRITTURA.finditer(testo):
        tab = _tabella_ts(testo, m.start())
        pos = m.end()
        if pos < len(testo) and testo[pos] in "{[":
            blocco = _blocco_bilanciato(testo, pos) or ""
            for c in set(RE_TS_CHIAVE.findall(blocco)) & nomi:
                occ.scrivi(c, tab, riga(m.start()))
        else:
            occ.scritture_opache[tab or "?"] += 1
    for m in RE_TS_PROPRIETA.finditer(testo):
        c = m.group(1) or m.group(2)
        if c in nomi:
            occ.leggi(c, None, riga(m.start()))


# ---------------------------------------------------------------- SQL (regex)

# `ALTER TABLE x ADD COLUMN y` sta spesso su UNA riga: il match e' sulla riga
# intera, non sul suo inizio (il presidio l'ha trovato alla prima stesura).
RE_SQL_DEF = re.compile(
    r"^\s*(?:--|COMMENT ON\b|.*\b(?:ADD|ALTER|DROP|RENAME) COLUMN\b)", re.I
)
RE_SQL_INSERT = re.compile(r"INSERT INTO\s+(?:public\.)?(\w+)\s*\(([^)]*)\)", re.I)
RE_SQL_UPDATE = re.compile(
    r"\bUPDATE\s+(?:public\.)?(\w+)\s+SET\s+(.*?)(?=\bWHERE\b|\bRETURNING\b|;|\bFROM\b)", re.I | re.S
)
RE_SQL_UPSERT = re.compile(r"ON CONFLICT[^;]*?DO UPDATE\s+SET\s+(.*?)(?=\bWHERE\b|;)", re.I | re.S)
RE_SQL_NEW = re.compile(r"\bNEW\.(\w+)\s*:?=", re.I)
RE_SQL_ASSEGNA = re.compile(r"(?:^|,)\s*(\w+)\s*=", re.S)
RE_SQL_TRIGGER = re.compile(
    r"CREATE TRIGGER\s+\w+.*?\bON\s+(?:public\.)?(\w+)\b.*?EXECUTE (?:FUNCTION|PROCEDURE)\s+(?:public\.)?(\w+)\s*\(",
    re.I | re.S,
)
RE_SQL_FUNZIONE = re.compile(
    r"CREATE (?:OR REPLACE )?FUNCTION\s+(?:public\.)?(\w+)\s*\(.*?\$(\w*)\$(.*?)\$\2\$", re.I | re.S
)


def _senza_definizioni(testo: str) -> str:
    """Toglie le righe di definizione (trappola 2): restano solo gli usi."""
    righe = []
    dentro_create = False
    for riga in testo.splitlines():
        if re.match(r"^\s*CREATE TABLE\b", riga, re.I):
            dentro_create = True
            continue
        if dentro_create:
            if riga.strip().startswith(")"):
                dentro_create = False
            elif not re.match(r"^\s*(CONSTRAINT|UNIQUE|PRIMARY|CHECK|FOREIGN)\b", riga.strip(), re.I):
                continue  # riga di definizione di colonna
            else:
                righe.append(riga)
            continue
        if RE_SQL_DEF.match(riga):
            continue
        righe.append(riga.split("--")[0])
    return "\n".join(righe)


def scandisci_sql(percorso: pathlib.Path, occ: Occorrenze, nomi: set[str],
                  trigger_tabella: dict[str, str]) -> set[str]:
    """Ritorna i nomi USATI (non solo definiti) nel file, e registra le scritture."""
    testo = percorso.read_text(encoding="utf-8-sig", errors="ignore")
    rel = str(percorso.relative_to(ROOT))
    usi = _senza_definizioni(testo)
    nominati = set(IDENT.findall(usi)) & nomi

    # Le letture si contano sul testo RESIDUO, tolti gli statement di scrittura:
    # un nome scritto da un INSERT e letto da un SELECT nello stesso file ha
    # entrambe. (Prima stesura: chi era scritto nel file perdeva ogni lettura —
    # e' la direzione che spinge verso «morta», l'ha visto il code-reviewer.)
    residuo = list(usi)

    def _cancella(inizio: int, fine: int) -> None:
        for i in range(inizio, fine):
            residuo[i] = " "

    for m in RE_SQL_INSERT.finditer(usi):
        for c in set(IDENT.findall(m.group(2))) & nomi:
            occ.scrivi(c, m.group(1), f"{rel}:insert")
        _cancella(m.start(2), m.end(2))
    for m in RE_SQL_UPDATE.finditer(usi):
        for c in set(RE_SQL_ASSEGNA.findall(m.group(2))) & nomi:
            occ.scrivi(c, m.group(1), f"{rel}:update")
        _cancella(m.start(2), m.end(2))
    for m in RE_SQL_UPSERT.finditer(usi):
        ins = RE_SQL_INSERT.search(usi, max(0, m.start() - 3000), m.start())
        tab = ins.group(1) if ins else None
        for c in set(RE_SQL_ASSEGNA.findall(m.group(1))) & nomi:
            occ.scrivi(c, tab, f"{rel}:upsert")
        _cancella(m.start(1), m.end(1))
    for f in RE_SQL_FUNZIONE.finditer(usi):
        tab = trigger_tabella.get(f.group(1))
        for m in RE_SQL_NEW.finditer(f.group(3)):
            if m.group(1) in nomi:
                occ.scrivi(m.group(1), tab, f"{rel}:trigger {f.group(1)}")
            _cancella(f.start(3) + m.start(), f.start(3) + m.end())
    for c in set(IDENT.findall("".join(residuo))) & nomi:
        occ.leggi(c, None, f"{rel}:sql")
    return nominati


def mappa_trigger(file_sql: list[pathlib.Path]) -> dict[str, str]:
    """funzione trigger -> tabella, dai CREATE TRIGGER di tutto il corpus SQL."""
    mappa: dict[str, str] = {}
    for p in file_sql:
        for m in RE_SQL_TRIGGER.finditer(p.read_text(encoding="utf-8", errors="ignore")):
            mappa[m.group(2)] = m.group(1)
    return mappa


# ---------------------------------------------------------------- inventario


def classifica(tab: str, col: str, r: dict) -> str:
    """L'esito. Se c'e' il CSV dei dati, un valore non NULL vale come scrittura:
    il rilevatore non attribuisce le scritture opache (`insert(payload)`), i
    dati si'. "letta_mai_scritta" resta quindi solo dove i dati NON smentiscono
    (colonna NULL al 100%, o tabella vuota che non puo' dire niente)."""
    if r["file_codice"] == 0 and r["file_edge"] == 0 and r["file_sql_uso"] == 0:
        return "mai_nominata"
    scritta_nei_dati = r.get("nn", 0) > 0
    scritta = r["scritture_tab"] > 0 or r["default"] is not None or scritta_nei_dati
    letta = r["letture_tab"] > 0 or r["letture_nome"] > 0
    if letta and not scritta:
        if r["scritture_nome"] == 0 and r["scritture_opache"] == 0:
            return "letta_mai_scritta"
        return "letta_scrittura_incerta"
    if scritta and not letta:
        return "scritta_mai_letta"
    if scritta and letta:
        return "viva"
    return "nominata_senza_uso"


def inventario(snapshot: pathlib.Path, stat: dict | None) -> tuple[dict, dict]:
    inizio = time.time()
    schema = leggi_snapshot(snapshot)
    drift: list[tuple[str, str]] = []
    if stat:
        for chiave, s in stat.items():
            if chiave not in schema:
                schema[chiave] = s["default"]
                drift.append(chiave)
    nomi = {c for (_, c) in schema}

    file_codice = elenca_file(DIR_CODICE, (".py", ".ts", ".tsx"))
    file_edge = elenca_file(DIR_EDGE, (".ts",))
    file_sql = elenca_file(DIR_SQL, (".sql",))
    trigger_tabella = mappa_trigger(file_sql)

    occ = Occorrenze()
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, nomi), key=len, reverse=True)) + r")\b")
    conta_codice: collections.Counter = collections.Counter()
    conta_edge: collections.Counter = collections.Counter()
    conta_sql_uso: collections.Counter = collections.Counter()
    conta_frontend: collections.Counter = collections.Counter()

    non_parsati: list[str] = []
    for p in file_codice:
        testo = p.read_text(encoding="utf-8-sig", errors="ignore")
        trovati = set(pattern.findall(testo))
        for c in trovati:
            conta_codice[c] += 1
            if "apps/web/src" in str(p):
                conta_frontend[c] += 1
        if p.suffix == ".py":
            if not scandisci_python(p, occ, nomi):
                non_parsati.append(str(p.relative_to(ROOT)))
        else:
            scandisci_typescript(p, occ, nomi)
    for p in file_edge:
        testo = p.read_text(encoding="utf-8-sig", errors="ignore")
        for c in set(pattern.findall(testo)):
            conta_edge[c] += 1
        scandisci_typescript(p, occ, nomi)
    for p in file_sql:
        for c in scandisci_sql(p, occ, nomi, trigger_tabella):
            conta_sql_uso[c] += 1

    righe: dict[str, dict] = {}
    for (tab, col), default in sorted(schema.items()):
        r = {
            "tabella": tab, "colonna": col, "default": default,
            "file_codice": conta_codice[col], "file_edge": conta_edge[col],
            "file_sql_uso": conta_sql_uso[col], "file_frontend": conta_frontend[col],
            "letture_tab": occ.letture_tab[(tab, col)], "letture_nome": occ.letture_nome[col],
            "scritture_tab": occ.scritture_tab[(tab, col)], "scritture_nome": occ.scritture_nome[col],
            "scritture_opache": occ.scritture_opache[tab],
        }
        if stat and (tab, col) in stat:
            s = stat[(tab, col)]
            r.update(n=s["n"], nn=s["nn"], nd=s["nd"])
            r["dati"] = ("tabella_vuota" if s["n"] == 0 else
                         "NULL_100" if s["nn"] == 0 else
                         "costante" if s["nd"] == 1 and s["n"] > 1 else "variabile")
        r["esito"] = classifica(tab, col, r)
        righe[f"{tab}.{col}"] = r

    meta = {
        "tabelle": len({t for (t, _) in schema}), "colonne": len(schema), "nomi": len(nomi),
        "file_codice": len(file_codice), "file_edge": len(file_edge), "file_sql": len(file_sql),
        "drift_snapshot": [f"{t}.{c}" for (t, c) in drift],
        "non_parsati": non_parsati,
        "scritture_opache_senza_tabella": occ.scritture_opache["?"],
        "secondi": round(time.time() - inizio, 1),
        "dove": {f"{k}:{t}:{n}": v for (k, t, n), v in occ.dove.items()},
    }
    return righe, meta


def taratura(righe: dict, meta: dict) -> list[str]:
    """I casi di esito noto: se non tornano, e' rotto il rilevatore, non il codice."""
    errori = []
    for f in meta["non_parsati"]:
        errori.append(f"{f}: non parsato dall'AST, le sue letture/scritture non sono contate")
    per_nome = {}
    for r in righe.values():
        per_nome[r["colonna"]] = r
    for nome, atteso in TARATURA_FILE_CODICE.items():
        if nome not in per_nome:
            errori.append(f"{nome}: non e' nello snapshot (drift): passa --stat con il CSV del DB live")
            continue
        got = per_nome[nome]["file_codice"]
        if got != atteso:
            errori.append(f"{nome}: file_codice atteso {atteso}, trovato {got}")
    for chiave in ("prodotti_master.correzioni_count", "prodotti_master.ultimo_correttore"):
        if chiave in righe and righe[chiave]["esito"] == "viva":
            errori.append(f"{chiave}: L4 la dichiara morta, qui risulta viva")
    idem = righe.get("ricavi_email_queue.idempotency_key")
    if not idem or idem["file_sql_uso"] == 0:
        errori.append("ricavi_email_queue.idempotency_key: e' viva solo in SQL, e l'SQL non la vede")
    if "upload_events.ack" in righe and righe["upload_events.ack"]["file_codice"] > 3:
        errori.append("upload_events.ack: conteggio gonfiato — `ack` matcha dentro 'fallback'?")
    bypass = righe.get("ristoranti.bypass_guardia_piva")
    if bypass and bypass["letture_tab"] == 0:
        errori.append("ristoranti.bypass_guardia_piva: letta in fastapi_worker.py (select + get) e non contata — BOM?")
    return errori


def stampa(righe: dict, meta: dict) -> None:
    print("CICLO DI VITA DELLE COLONNE")
    print(f"  {meta['tabelle']} tabelle, {meta['colonne']} colonne, {meta['nomi']} nomi distinti")
    print(f"  {meta['file_codice']} file di codice + {meta['file_edge']} edge + {meta['file_sql']} sql in {meta['secondi']}s")
    if meta["drift_snapshot"]:
        print(f"  snapshot indietro rispetto ai dati: {', '.join(meta['drift_snapshot'])}")
    if meta["non_parsati"]:
        print(f"  FILE PYTHON NON PARSATI ({len(meta['non_parsati'])}): {', '.join(meta['non_parsati'])}")
    print(f"  scritture opache senza tabella attribuibile: {meta['scritture_opache_senza_tabella']}")
    conta = collections.Counter(r["esito"] for r in righe.values())
    print()
    for esito in ("mai_nominata", "letta_mai_scritta", "letta_scrittura_incerta",
                  "scritta_mai_letta", "nominata_senza_uso", "viva"):
        print(f"  {esito:<26} {conta[esito]:>4}")
    if any("dati" in r for r in righe.values()):
        dati = collections.Counter(r.get("dati") for r in righe.values())
        print()
        print("  dati (dal CSV --stat):")
        for k in ("tabella_vuota", "NULL_100", "costante", "variabile"):
            print(f"    {k:<16} {dati[k]:>4}")
    for esito in ("mai_nominata", "letta_mai_scritta", "letta_scrittura_incerta", "scritta_mai_letta", "nominata_senza_uso"):
        print()
        print(f"== {esito} ==")
        for chiave, r in righe.items():
            if r["esito"] != esito:
                continue
            extra = f"  dati={r['dati']} ({r['nn']}/{r['n']} non-null, {r['nd']} distinti)" if "dati" in r else ""
            print(f"  {chiave:<58} cod={r['file_codice']:<3} edge={r['file_edge']:<2} sql={r['file_sql_uso']:<3} "
                  f"L={r['letture_tab']}/{r['letture_nome']:<4} S={r['scritture_tab']}/{r['scritture_nome']:<4} "
                  f"opache={r['scritture_opache']:<2} default={'si' if r['default'] else 'no'}{extra}")
    print()
    print("== lette dal worker, mai nominate nel frontend (trappola 5: puo' leggere per nome dinamico) ==")
    for chiave, r in righe.items():
        if r["esito"] == "viva" and r["file_frontend"] == 0 and r["letture_tab"] > 0:
            print(f"  {chiave}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", type=pathlib.Path, default=SNAPSHOT)
    ap.add_argument("--stat", type=pathlib.Path, help="CSV tabella,colonna,...,n,nn,nd dal DB live")
    ap.add_argument("--json", type=pathlib.Path, help="scrive l'inventario completo qui")
    ap.add_argument("--taratura", action="store_true", help="esce 1 se i casi noti non tornano")
    ap.add_argument("--dove", metavar="TABELLA.COLONNA", nargs="+", help="stampa i punti di lettura/scrittura di una colonna")
    args = ap.parse_args(argv)

    stat = leggi_stat(args.stat) if args.stat else None
    righe, meta = inventario(args.snapshot, stat)

    if args.dove:
        for voce in args.dove:
            tab, _, col = voce.partition(".")
            print(f"--- {voce}")
            for k, v in sorted(meta["dove"].items()):
                kk, t, n = k.split(":")
                if n == col and (t == tab or t == ""):
                    print(f"  {'LETTURA ' if kk == 'L' else 'SCRITTURA'} [{t or '?'}] " + ", ".join(sorted(set(v))))
        return 0

    if args.json:
        args.json.write_text(json.dumps({"meta": {k: v for k, v in meta.items() if k != "dove"},
                                          "colonne": righe}, indent=1, ensure_ascii=False), encoding="utf-8")
    errori = taratura(righe, meta)
    if args.taratura:
        for e in errori:
            print("TARATURA FALLITA:", e)
        print("taratura: " + ("OK" if not errori else f"{len(errori)} errori"))
        return 1 if errori else 0
    stampa(righe, meta)
    if errori:
        print()
        print("ATTENZIONE, taratura non superata (non fidarti dell'esito):")
        for e in errori:
            print("  ", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
