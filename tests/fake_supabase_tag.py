"""Finto Supabase per i tag di catena: applica DAVVERO filtri e vincoli del DB.

I vincoli si dichiarano per tabella, come stanno sul DB vero:
- `unici`: indici unici, ognuno una tupla di colonne (il nome confrontato come
  `lower(btrim(nome))`); violazione -> errore 23505;
- `fk`: FK composte {tabella: (colonne_locali, tabella_riferita, colonne_riferite)};
  violazione -> 23503; il DELETE della riga riferita fa `SET NULL` della sola
  prima colonna locale, come `ON DELETE SET NULL (cartella_id)`;
- `upsert` con `on_conflict` aggiorna la riga con la stessa chiave invece di
  duplicarla.

Un fake che registra soltanto le chiamate lascerebbe verde anche un update
senza il filtro di account. La FK e il SET NULL veri si provano su Postgres
(tests/test_sql_gruppo_tag_cartelle.py).
"""
import copy
from types import SimpleNamespace


class ErroreDb(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _valore(riga, colonna):
    v = riga.get(colonna)
    return str(v).strip().lower() if colonna == "nome" else v


class _Q:
    def __init__(self, sb, nome):
        self.sb = sb
        self.nome = nome
        self.modo = "select"
        self.payload = None
        self.on_conflict = None
        self.filtri = []
        self.ordini = []
        self.limite = None
        self.intervallo = None
        self.colonne = None

    def select(self, colonne="*", **_k):
        self.colonne = None if colonne.strip() == "*" else [c.strip() for c in colonne.split(",")]
        return self

    def eq(self, col, val):
        self.filtri.append(lambda r, c=col, v=val: str(r.get(c)) == str(v))
        return self

    def in_(self, col, valori):
        valori = [str(v) for v in valori]
        self.filtri.append(lambda r, c=col: str(r.get(c)) in valori)
        return self

    def order(self, col, desc=False, **_k):
        self.ordini.append((col, desc))
        return self

    def limit(self, n):
        self.limite = n
        return self

    def range(self, inizio, fine):
        self.intervallo = (inizio, fine)
        return self

    def insert(self, payload):
        self.modo, self.payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None, **_k):
        self.modo, self.payload, self.on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload):
        self.modo, self.payload = "update", payload
        return self

    def delete(self):
        self.modo = "delete"
        return self

    def _match(self, r):
        return all(f(r) for f in self.filtri)

    def _inserisci(self, payload):
        riga = dict(payload)
        self.sb.prossimo_id += 1
        riga.setdefault("id", self.sb.prossimo_id)
        riga.setdefault("created_at", "2026-10-13T08:00:00+00:00")
        if self.nome == "gruppo_tags":
            riga.setdefault("cartella_id", None)
            riga.setdefault("preferito", False)
        self.sb.vincoli(self.nome, riga, escluso=None)
        self.sb.tabelle.setdefault(self.nome, []).append(riga)
        self.sb.scritture.append(("insert", self.nome, riga["id"], dict(payload)))
        return riga

    def execute(self):
        if self.sb.rompi.get((self.modo, self.nome)):
            self.sb.rompi[(self.modo, self.nome)] -= 1
            if self.sb.rompi[(self.modo, self.nome)] == 0:
                raise RuntimeError("connessione persa")
        righe = self.sb.tabelle.setdefault(self.nome, [])
        if self.modo == "insert":
            return SimpleNamespace(data=[dict(self._inserisci(self.payload))])
        if self.modo == "upsert":
            colonne = [c.strip() for c in (self.on_conflict or "").split(",") if c.strip()]
            out = []
            for p in (self.payload if isinstance(self.payload, list) else [self.payload]):
                esistente = next(
                    (r for r in righe if colonne and all(str(r.get(c)) == str(p.get(c)) for c in colonne)), None
                )
                if esistente is not None:
                    esistente.update(p)
                    self.sb.scritture.append(("upsert-update", self.nome, esistente["id"], dict(p)))
                    out.append(dict(esistente))
                else:
                    out.append(dict(self._inserisci(p)))
            return SimpleNamespace(data=out)
        if self.modo == "update":
            colpite = [r for r in righe if self._match(r)]
            for r in colpite:
                self.sb.vincoli(self.nome, {**r, **self.payload}, escluso=r)
            for r in colpite:
                r.update(self.payload)
                self.sb.scritture.append(("update", self.nome, r["id"], dict(self.payload)))
            return SimpleNamespace(data=[dict(r) for r in colpite])
        if self.modo == "delete":
            via = [r for r in righe if self._match(r)]
            self.sb.tabelle[self.nome] = [r for r in righe if not self._match(r)]
            for r in via:
                self.sb.scritture.append(("delete", self.nome, r["id"], None))
                self.sb.cascata(self.nome, r)
            return SimpleNamespace(data=[dict(r) for r in via])
        trovate = [dict(r) for r in righe if self._match(r)]
        for col, desc in reversed(self.ordini):
            trovate.sort(key=lambda r, c=col: (r.get(c) is None, r.get(c)), reverse=desc)
        if self.intervallo is not None:
            trovate = trovate[self.intervallo[0]: self.intervallo[1] + 1]
        if self.limite is not None:
            trovate = trovate[: self.limite]
        if self.colonne:
            trovate = [{c: r.get(c) for c in self.colonne} for r in trovate]
        return SimpleNamespace(data=trovate)


class FakeSupabase:
    def __init__(self, tabelle, unici=None, fk=None):
        self.tabelle = copy.deepcopy(tabelle)
        self.unici = unici or {}
        self.fk = fk or {}
        self.scritture = []
        self.prossimo_id = 5000
        # (modo, tabella) -> n: la n-esima esecuzione di quel tipo fallisce.
        self.rompi = {}

    def table(self, nome):
        return _Q(self, nome)

    def vincoli(self, tabella, riga, escluso):
        for colonne in self.unici.get(tabella, ()):
            chiave = tuple(_valore(riga, c) for c in colonne)
            for altra in self.tabelle.get(tabella, []):
                if altra is not escluso and tuple(_valore(altra, c) for c in colonne) == chiave:
                    raise ErroreDb("23505", "duplicate key value violates unique constraint")
        if tabella in self.fk:
            locali, riferita, remote = self.fk[tabella]
            valori = [riga.get(c) for c in locali]
            if valori[0] is not None and not any(
                all(str(r.get(rc)) == str(v) for rc, v in zip(remote, valori))
                for r in self.tabelle.get(riferita, [])
            ):
                raise ErroreDb("23503", "insert or update violates foreign key constraint")

    def cascata(self, tabella, cancellata):
        for figlia, (locali, riferita, remote) in self.fk.items():
            if riferita != tabella:
                continue
            for r in self.tabelle.get(figlia, []):
                if all(str(r.get(lc)) == str(cancellata.get(rc)) for lc, rc in zip(locali, remote)):
                    r[locali[0]] = None


def fake_catena(tabelle):
    """Lo schema di catena: indice unico sul nome della cartella per account,
    FK (cartella_id, user_id) -> gruppo_tag_cartelle(id, user_id), indice unico
    (tag_id, descrizione_key) sui prodotti. Nessun indice unico sul nome dei tag."""
    return FakeSupabase(
        tabelle,
        unici={
            "gruppo_tag_cartelle": [("user_id", "nome")],
            "gruppo_tag_prodotti": [("tag_id", "descrizione_key")],
        },
        fk={"gruppo_tags": (("cartella_id", "user_id"), "gruppo_tag_cartelle", ("id", "user_id"))},
    )
