"""Test dello strumento unico "Categorie" (admin):

- `_descrizioni_impronta_umana`: segrega le righe scelte a mano (Manuale/Utente/
  Admin) che NON devono entrare nella coda "Da controllare".
- `_suggerimento_deterministico`: il suggerimento della pagina «Da sistemare».
  («Rivedi con AI» e `prepara_suggerimenti_ai` tolti il 14/10/2026: in
  prodotti_master non c'era nessun suggerimento AI salvato.)

Fake client Supabase in-memory che riproduce il chaining usato dal router
(table/select/eq/in_/is_/not_.is_/gte/range/upsert/execute).
"""
import importlib

import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin


class _Result:
    def __init__(self, data):
        self.data = data


class _NotProxy:
    """Supporta `.not_.is_(campo, 'null')`."""
    def __init__(self, q):
        self._q = q

    def is_(self, field, _null):
        self._q._not_null.append(field)
        return self._q


class _Query:
    def __init__(self, store):
        self._store = store
        self._op = "select"
        self._filters = []        # eq
        self._in = None           # (campo, [valori])
        self._is_null = []
        self._not_null = []
        self._gte = []            # (campo, soglia)
        self._range = None
        self._upsert_row = None

    # mutazioni
    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def upsert(self, row, on_conflict=None):
        self._op = "upsert"
        self._upsert_row = dict(row)
        self._on_conflict = on_conflict
        return self

    # filtri
    def eq(self, f, v):
        self._filters.append((f, v))
        return self

    def in_(self, f, vals):
        self._in = (f, list(vals))
        return self

    def is_(self, f, _null):
        self._is_null.append(f)
        return self

    @property
    def not_(self):
        return _NotProxy(self)

    def gte(self, f, soglia):
        self._gte.append((f, soglia))
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, lo, hi):
        self._range = (lo, hi)
        return self

    def _matches(self, row):
        for f, v in self._filters:
            if row.get(f) != v:
                return False
        if self._in is not None:
            f, vals = self._in
            if row.get(f) not in vals:
                return False
        for f in self._is_null:
            if row.get(f) is not None:
                return False
        for f in self._not_null:
            if row.get(f) is None:
                return False
        for f, soglia in self._gte:
            if (row.get(f) or "") < soglia:
                return False
        return True

    def execute(self):
        if self._op == "upsert":
            key = self._upsert_row.get("descrizione")
            for r in self._store:
                if r.get("descrizione") == key:
                    r.update(self._upsert_row)
                    return _Result([dict(r)])
            self._store.append(dict(self._upsert_row))
            return _Result([dict(self._upsert_row)])

        rows = [dict(r) for r in self._store if self._matches(r)]
        if self._range is not None:
            lo, hi = self._range
            rows = rows[lo:hi + 1]
        return _Result(rows)


class FakeClient:
    def __init__(self, tables):
        self._tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        return _Query(self._tables.setdefault(name, []))

    def dump(self, name):
        return self._tables.get(name, [])


# ─── _descrizioni_impronta_umana ──────────────────────────────────────────────

def test_impronta_umana_include_manuale_utente_admin_esclude_auto():
    sb = FakeClient({
        "prodotti_utente": [
            {"user_id": "u1", "descrizione": "PANE CASERECCIO", "classificato_da": "Manuale (mario@x.it)"},
            {"user_id": "u1", "descrizione": "ACQUA NATURALE", "classificato_da": "keyword-auto"},
        ],
        "prodotti_master": [
            {"descrizione": "TONNO PINNA GIALLA", "verified": True, "classificato_da": "Utente (mario@x.it)"},
            {"descrizione": "CONSULENZA HACCP", "verified": True, "classificato_da": "Admin (md@oneflux.it)"},
            {"descrizione": "ZUCCHERO 1KG", "verified": True, "classificato_da": "auto-review"},
            {"descrizione": "SALE FINO", "verified": True, "classificato_da": "agent-notturno"},
        ],
    })
    umane = admin._descrizioni_impronta_umana(sb, ["u1"])
    assert "PANE CASERECCIO" in umane          # Manuale locale
    assert "TONNO PINNA GIALLA" in umane        # Utente globale
    assert "CONSULENZA HACCP" in umane          # Admin globale
    # NON umane: classificazioni della macchina
    assert "ACQUA NATURALE" not in umane        # keyword-auto locale
    assert "ZUCCHERO 1KG" not in umane          # auto-review
    assert "SALE FINO" not in umane             # agent-notturno


def test_impronta_umana_normalizza_uppercase_e_trim():
    # La normalizzazione (uppercase + trim + pulisci_caratteri_corrotti) deve
    # essere la STESSA applicata alla coda su fatture.descrizione, cosi' il match
    # avviene su entrambi i lati in modo coerente.
    from utils.text_utils import pulisci_caratteri_corrotti
    raw = "  pane casereccio  "
    atteso = pulisci_caratteri_corrotti(raw).strip().upper()
    sb = FakeClient({
        "prodotti_utente": [{"user_id": "u1", "descrizione": raw, "classificato_da": "Manuale (x)"}],
        "prodotti_master": [],
    })
    umane = admin._descrizioni_impronta_umana(sb, ["u1"])
    assert atteso in umane
    assert atteso == "PANE CASERECCIO"


def test_modulo_admin_importa_helper_categorie():
    # Guardia: i nuovi simboli devono esistere a livello modulo.
    m = importlib.reload(admin) if False else admin
    assert hasattr(m, "_descrizioni_impronta_umana")
    assert hasattr(m, "admin_categorie_da_sistemare")
    assert hasattr(m, "_righe_da_sistemare")
    assert hasattr(m, "_suggerimento_deterministico")


# ─── Suggerimento coda: affidabile, niente match ciechi su parola singola ──────
# Contesto (23/06): la colonna "Suggerita" proponeva di PEGGIORARE categorie già
# giuste perché dizionario e regole erano valutati separatamente (es. "VASC. LIMONE"
# = gelato al limone → suggeriva FRUTTA dal solo match su LIMONE). Ora il suggerimento
# deterministico compare solo se l'intera pipeline runtime concorda e il prodotto non
# è in un contenitore/formato ambiguo non confermato da una regola forte.

def test_suggerimento_non_propone_su_contenitore_ambiguo():
    # "VASC. LIMONE" è già GELATI E DESSERT (giusto): NESSUN suggerimento (era FRUTTA).
    sugg, fonte = admin._suggerimento_deterministico("VASC. LIMONE 4,8 LT", "GELATI E DESSERT")
    assert sugg is None and fonte is None
    # Salvietta al limone, già MATERIALE: niente suggerimento FRUTTA.
    sugg, fonte = admin._suggerimento_deterministico("SALV.LIMONE X100 TNT 70X100", "MATERIALE DI CONSUMO")
    assert sugg is None and fonte is None


def test_suggerimento_propone_correzione_vera():
    # SALMONE in coda SERVIZI (fallback): suggerisce PESCE.
    sugg, fonte = admin._suggerimento_deterministico("SALMONE 5-6", "SERVIZI E CONSULENZE")
    assert sugg == "PESCE"
    assert fonte in ("regola", "memoria")


def test_suggerimento_niente_se_gia_giusto():
    # Categoria già corretta → nessun suggerimento da mostrare.
    sugg, fonte = admin._suggerimento_deterministico("FINOCCHIO", "VERDURE")
    assert sugg is None and fonte is None
