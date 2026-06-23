"""Test dello strumento unico "Categorie" (admin):

- `_descrizioni_impronta_umana`: segrega le righe scelte a mano (Manuale/Utente/
  Admin) che NON devono entrare nella coda "Da controllare".
- `prepara_suggerimenti_ai`: prepara suggerimenti GPT per le righe dubbie SENZA
  scriverne la categoria; salta quelle gia' risolte da regola/dizionario; non
  tocca mai fatture.categoria / needs_review.

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


# ─── prepara_suggerimenti_ai ──────────────────────────────────────────────────

def _fatture_dubbie(*descrizioni):
    return [
        {
            "id": i + 1, "user_id": "u1", "descrizione": d, "categoria": "SERVIZI E CONSULENZE",
            "fornitore": "FORNITORE X", "prezzo_unitario": 5.0, "totale_riga": 5.0,
            "quantita": 1, "tipo_documento": "TD01", "needs_review": True,
        }
        for i, d in enumerate(descrizioni)
    ]


def test_suggerisci_ai_salta_regola_forte_e_non_chiama_gpt(monkeypatch):
    # MAGNUM CLASSICO ha gia' una regola forte (-> SHOP): non deve andare a GPT.
    sb = FakeClient({"fatture": _fatture_dubbie("MAGNUM CLASSICO")})

    chiamato = {"gpt": False}

    def _fake_gpt(*a, **k):
        chiamato["gpt"] = True
        return ([], [])
    monkeypatch.setattr("services.ai_service.classifica_con_ai", _fake_gpt)

    res = admin.prepara_suggerimenti_ai(sb, ["u1"])
    assert chiamato["gpt"] is False
    assert res["suggerite"] == 0
    assert res["saltate"] >= 1
    # Nessuna scrittura su fatture (categoria/needs_review intatti)
    for r in sb.dump("fatture"):
        assert r["categoria"] == "SERVIZI E CONSULENZE"
        assert r["needs_review"] is True


def test_suggerisci_ai_prepara_suggerimento_senza_scrivere_categoria(monkeypatch):
    # Descrizione ignota al dizionario: deve chiamare GPT e salvare il
    # suggerimento in prodotti_master SENZA toccare fatture.
    sb = FakeClient({"fatture": _fatture_dubbie("TRSSE TLTTE GM SHNE"), "prodotti_master": []})

    def _fake_gpt(lista_descrizioni, **k):
        cats = ["MATERIALE DI CONSUMO" for _ in lista_descrizioni]
        return (cats, ["media" for _ in lista_descrizioni])
    monkeypatch.setattr("services.ai_service.classifica_con_ai", _fake_gpt)

    res = admin.prepara_suggerimenti_ai(sb, ["u1"])
    assert res["suggerite"] == 1
    master = sb.dump("prodotti_master")
    assert len(master) == 1
    assert master[0]["categoria_suggerita"] == "MATERIALE DI CONSUMO"
    assert master[0]["suggerimento_fonte"] == "ai"
    assert master[0].get("suggerito_at")
    # NON ha scritto la categoria definitiva
    assert "categoria" not in master[0] or master[0].get("categoria") != "MATERIALE DI CONSUMO"
    # fatture intatte
    for r in sb.dump("fatture"):
        assert r["categoria"] == "SERVIZI E CONSULENZE"
        assert r["needs_review"] is True


def test_suggerisci_ai_scarta_categoria_non_valida(monkeypatch):
    sb = FakeClient({"fatture": _fatture_dubbie("XYZ IGNOTO QWE"), "prodotti_master": []})

    def _fake_gpt(lista_descrizioni, **k):
        # GPT ritorna fallback / categoria inesistente: NON va salvato.
        return (["Da Classificare"], ["bassa"])
    monkeypatch.setattr("services.ai_service.classifica_con_ai", _fake_gpt)

    res = admin.prepara_suggerimenti_ai(sb, ["u1"])
    assert res["suggerite"] == 0
    assert sb.dump("prodotti_master") == []


def test_suggerisci_ai_idempotente_salta_suggerimento_fresco(monkeypatch):
    from datetime import datetime, timezone
    fresco = datetime.now(timezone.utc).isoformat()
    sb = FakeClient({
        "fatture": _fatture_dubbie("QWE IGNOTO ZXC"),
        "prodotti_master": [{
            "descrizione": "QWE IGNOTO ZXC", "categoria_suggerita": "MATERIALE DI CONSUMO",
            "suggerimento_fonte": "ai", "suggerito_at": fresco,
        }],
    })

    chiamato = {"gpt": False}

    def _fake_gpt(*a, **k):
        chiamato["gpt"] = True
        return ([], [])
    monkeypatch.setattr("services.ai_service.classifica_con_ai", _fake_gpt)

    res = admin.prepara_suggerimenti_ai(sb, ["u1"])
    assert chiamato["gpt"] is False        # gia' suggerito di fresco -> skip
    assert res["suggerite"] == 0
    assert res["saltate"] >= 1


def test_modulo_admin_importa_helper_categorie():
    # Guardia: i nuovi simboli devono esistere a livello modulo.
    m = importlib.reload(admin) if False else admin
    assert hasattr(m, "_descrizioni_impronta_umana")
    assert hasattr(m, "prepara_suggerimenti_ai")
    assert hasattr(m, "admin_qualita_suggerisci_ai")
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
