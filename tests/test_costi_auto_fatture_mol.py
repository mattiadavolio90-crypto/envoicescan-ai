"""Test audit §3 — `_calcola_costi_auto_per_mese` / `_calcola_costi_auto_per_periodo`
(`services/fastapi_worker.py`, 10/8/2026).

Questi due helper sono il NUMERATORE del MOL: leggono le righe di `fatture` e le
dividono fra F&B e Spese Generali. Prima di questa passata nessun test ne eseguiva
la logica — gli unici esistenti (`tests/test_audit_bug_passata2.py:105-126`) usano
`inspect.getsource()` e verificano che una stringa compaia nel sorgente, non che il
filtro funzioni. Un test così resta verde anche se la query smette di filtrare.

Sono DUE implementazioni indipendenti della stessa regola:
  - `_per_mese` chiede al DB un mese solo e somma tutto quello che torna
    (il bucketing e' delegato alla `.or_()`);
  - `_per_periodo` chiede un range ampio in UNA passata e fa il bucketing in
    Python su `data_competenza or data_documento`.
Da qui il test piu' importante del file: a parita' di input devono dare lo stesso
totale. E' anche la rete che renderebbe sicuro il refactor D6 (gli `_aggrega_*`
chiamano ancora `_per_mese` mese-per-mese: 12 scansioni di `fatture` per un anno,
mentre `_per_periodo` esiste apposta per farne una).

IL FAKE FILTRA DAVVERO, `.or_()` COMPRESA. Misurato sul DB live il 10/8/2026:
`data_competenza` e' NULL su 33.771 righe su 34.000 (99,3%), e su 229 righe cade in
un mese DIVERSO da `data_documento`. Il fallback `data_competenza -> data_documento`
non e' quindi un caso di bordo: e' il percorso normale di quasi tutto il MOL, e un
bug li' sposta una fattura di mese senza sollevare nulla. Con una `.or_()` no-op il
fake restituirebbe tutte le righe e il filtro di periodo non verrebbe MAI
esercitato: un test "marzo da' 100 euro" passerebbe anche se il codice chiedesse
aprile, perche' verificherebbe l'aggregazione senza la selezione.
"""
import os
import re

import pytest

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import services.fastapi_worker as fw  # noqa: E402
from config.constants import CATEGORIE_SPESE_GENERALI  # noqa: E402

RID = "rid-test"
ALTRO_RID = "rid-altro"

# Una categoria di spese generali e una F&B, prese dalla costante vera: se domani
# la classificazione cambia, il test segue la produzione invece di fossilizzarla.
CAT_SPESE = sorted(CATEGORIE_SPESE_GENERALI)[0]
CAT_FB = "CARNE"


# ─────────────────────────────────────────────────────────────────────────────
# Fake Supabase — deriva da tests/test_ricavi_coerenza_e_cache.py:51, esteso con
# neq / is_ / or_ / la tabella `fatture`.
# ─────────────────────────────────────────────────────────────────────────────

_AND_RE = re.compile(r"and\(([^()]*)\)")


def _match_cond(row, cond: str) -> bool:
    """Valuta una singola condizione PostgREST nella forma 'col.op.val'."""
    col, op, val = cond.split(".", 2)
    got = row.get(col)
    if op == "is":
        if val == "null":
            return got is None
        raise AssertionError(f"is.{val} non gestito dal fake")
    if got is None:
        # gte/lte/gt/eq su NULL sono NULL in SQL: la riga non passa.
        return False
    if op == "gte":
        return str(got) >= val
    if op == "lte":
        return str(got) <= val
    if op == "gt":
        return str(got) > val
    if op == "eq":
        return str(got) == val
    raise AssertionError(f"operatore '{op}' non gestito dal fake")


def applica_or(rows, expr: str):
    """Applica DAVVERO la `.or_()` nella forma prodotta dal worker.

    Forme gestite:
      'and(a.gte.X,a.lte.Y),and(a.is.null,b.gte.X,b.lte.Y)'   (costi auto)
      'expires_at.is.null,expires_at.gt.<iso>'                 (notifiche)

    Se la forma cambia il fake ALZA invece di ignorare: un `or_` che lascia
    passare tutto renderebbe vacuo il test sul fallback competenza->documento,
    che e' la ragione per cui questo parser esiste.
    """
    gruppi = _AND_RE.findall(expr)
    resto = _AND_RE.sub("", expr).strip(", ")
    if resto:
        gruppi = gruppi + [c for c in resto.split(",") if c]
    if not gruppi:
        raise AssertionError(f"or_ non riconosciuta dal fake: {expr!r}")

    def _ok(row):
        for g in gruppi:
            conds = [c for c in g.split(",") if c]
            if conds and all(_match_cond(row, c) for c in conds):
                return True
        return False

    return [r for r in rows if _ok(r)]


class _FakeQuery:
    """Builder che applica per davvero i filtri usati dagli helper sotto test.

    `range()` affetta come PostgREST (estremi INCLUSIVI), cosi' la paginazione
    viene esercitata invece che solo dichiarata.
    """

    def __init__(self, rows, recorder=None, table=""):
        self._rows = list(rows)
        self._rec = recorder
        self._table = table
        self._range = None
        self._limit = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def neq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) != val]
        return self

    def is_(self, col, val):
        if str(val).lower() == "null":
            self._rows = [r for r in self._rows if r.get(col) is None]
        else:
            raise AssertionError(f"is_({col}, {val!r}) non gestito dal fake")
        return self

    def in_(self, col, vals):
        vs = set(vals)
        self._rows = [r for r in self._rows if r.get(col) in vs]
        return self

    def gte(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) is not None and str(r.get(col)) >= str(val)]
        return self

    def lte(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) is not None and str(r.get(col)) <= str(val)]
        return self

    def or_(self, expr):
        self._rows = applica_or(self._rows, expr)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = self._rows
        if self._range is not None:
            s, e = self._range
            rows = rows[s:e + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return type("R", (), {"data": rows, "count": len(rows)})()


class _FakeSB:
    """Client fake con routing per tabella. Ogni `table()` crea una query NUOVA:
    un builder condiviso accumulerebbe i filtri fra chiamate successive, e questi
    helper interrogano `fatture` una volta per mese.
    """

    def __init__(self, fatture=None, margini=None, modalita=None, recorder=None):
        self._fatture = fatture or []
        self._margini = margini or []
        self._modalita = modalita or []
        self._rec = recorder if recorder is not None else {}

    def table(self, name):
        self._rec.setdefault("tables", []).append(name)
        src = {
            "fatture": self._fatture,
            "margini_mensili": self._margini,
            "ricavi_modalita_mensile": self._modalita,
        }.get(name, [])
        return _FakeQuery(src, recorder=self._rec, table=name)


def _fattura(categoria=CAT_FB, totale=100.0, documento="2026-03-15",
             competenza=None, ristorante_id=RID, ripartita=False, deleted_at=None):
    """Riga di `fatture` con i soli campi che gli helper leggono.

    `ripartita_su_gruppo` e' sempre valorizzato (mai None): sul DB live la colonna
    e' NOT NULL DEFAULT false (verificato 10/8/2026, 0 righe NULL su 34.000),
    quindi la semantica SQL del NULL non entra in questi test.
    """
    return {
        "categoria": categoria,
        "totale_riga": totale,
        "data_documento": documento,
        "data_competenza": competenza,
        "ristorante_id": ristorante_id,
        "ripartita_su_gruppo": ripartita,
        "deleted_at": deleted_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coerenza fra i due helper — il test piu' importante del file
# ─────────────────────────────────────────────────────────────────────────────

def _dataset_misto():
    """Righe su 3 mesi con tutte le classi che il MOL deve trattare a modo suo."""
    return [
        # marzo, competenza esplicita
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza="2026-03-05"),
        _fattura(CAT_SPESE, 50.0, "2026-03-10", competenza="2026-03-10"),
        # marzo per COMPETENZA ma documento di aprile (le 229 righe reali)
        _fattura(CAT_FB, 70.0, "2026-04-02", competenza="2026-03-28"),
        # marzo senza competenza -> vale il documento (il 99,3% del DB)
        _fattura(CAT_FB, 30.0, "2026-03-20", competenza=None),
        # febbraio e aprile, per verificare che non sconfinino
        _fattura(CAT_FB, 999.0, "2026-02-11", competenza=None),
        _fattura(CAT_SPESE, 888.0, "2026-04-11", competenza=None),
        # righe che il MOL deve ignorare
        _fattura("Da Classificare", 500.0, "2026-03-12", competenza=None),
        _fattura("📝 NOTE E DICITURE", 400.0, "2026-03-13", competenza=None),
        _fattura(CAT_FB, 300.0, "2026-03-14", competenza=None, ripartita=True),
        _fattura(CAT_FB, 200.0, "2026-03-15", competenza=None, deleted_at="2026-03-16T10:00:00Z"),
        _fattura(CAT_FB, 150.0, "2026-03-17", competenza=None, ristorante_id=ALTRO_RID),
    ]


@pytest.mark.parametrize("anno,mese", [(2026, 2), (2026, 3), (2026, 4)])
def test_costi_per_mese_e_per_periodo_danno_lo_stesso_totale(anno, mese):
    """Due implementazioni della stessa regola non devono divergere.

    `_per_mese` delega il bucketing al DB via `.or_()`, `_per_periodo` lo rifa in
    Python: e' esattamente il tipo di coppia che va a deriva quando si corregge
    uno solo dei due.
    """
    rows = _dataset_misto()
    per_mese = fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, anno, mese)
    per_periodo = fw._calcola_costi_auto_per_periodo(
        _FakeSB(fatture=rows), RID, [(anno, mese)]
    )[(anno, mese)]
    assert per_mese == per_periodo


def test_costi_per_periodo_su_piu_mesi_uguale_alla_somma_dei_singoli():
    rows = _dataset_misto()
    mesi = [(2026, 2), (2026, 3), (2026, 4)]
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, mesi)
    for (yy, mm) in mesi:
        atteso = fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, yy, mm)
        assert per_periodo[(yy, mm)] == atteso


# ─────────────────────────────────────────────────────────────────────────────
# Il fallback competenza -> documento (99,3% delle righe reali)
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_competenza_su_documento_assegna_il_mese_giusto():
    """La competenza VINCE sul documento; se manca, vale il documento.

    Riga A: documento aprile, competenza marzo -> pesa su MARZO.
    Riga B: documento aprile, competenza assente -> pesa su APRILE.
    Se il codice invertisse la precedenza, entrambe finirebbero ad aprile e il
    MOL di marzo risulterebbe piu' leggero del vero senza alcun errore visibile.
    """
    rows = [
        _fattura(CAT_FB, 70.0, "2026-04-02", competenza="2026-03-28"),   # A
        _fattura(CAT_FB, 25.0, "2026-04-03", competenza=None),           # B
    ]
    marzo_mese = fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3)
    aprile_mese = fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 4)
    assert marzo_mese == (70.0, 0.0)
    assert aprile_mese == (25.0, 0.0)

    per_periodo = fw._calcola_costi_auto_per_periodo(
        _FakeSB(fatture=rows), RID, [(2026, 3), (2026, 4)]
    )
    assert per_periodo[(2026, 3)] == (70.0, 0.0)
    assert per_periodo[(2026, 4)] == (25.0, 0.0)


def test_riga_con_competenza_fuori_periodo_non_entra():
    """Documento dentro il mese ma competenza FUORI: non deve essere contata.

    E' il ramo che una `.or_()` no-op non potrebbe mai esercitare: senza il
    filtro, la riga passerebbe per via del documento.
    """
    rows = [_fattura(CAT_FB, 99.0, "2026-03-10", competenza="2026-01-05")]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (0.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (0.0, 0.0)


def test_ultimo_giorno_del_mese_incluso():
    """Il bordo destro del range e' inclusivo, e febbraio usa monthrange."""
    rows = [
        _fattura(CAT_FB, 10.0, "2026-02-28", competenza=None),
        _fattura(CAT_FB, 20.0, "2026-03-31", competenza=None),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 2) == (10.0, 0.0)
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (20.0, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Regole di dominio CLAUDE.md
# ─────────────────────────────────────────────────────────────────────────────

def test_da_classificare_escluse_dal_mol():
    """Regola #1: una riga non classificata non entra nei margini finche' non
    viene classificata, per non falsare il MOL con una categoria inventata."""
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura("Da Classificare", 999.0, "2026-03-06", competenza=None),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (100.0, 0.0)


@pytest.mark.parametrize("cat_note", ["📝 NOTE E DICITURE", "NOTE E DICITURE"])
def test_note_e_diciture_escluse_dal_fb(cat_note):
    """Regola #2: le diciture non sono un costo.

    L'importo e' volutamente != 0: con `totale_riga = 0` il test non
    discriminerebbe (sommare zero non cambia il totale) e resterebbe verde anche
    senza il filtro `CATEGORIE_NOTE_WORKER`.
    """
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(cat_note, 400.0, "2026-03-06", competenza=None),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (100.0, 0.0)


def test_fatture_ripartite_sul_gruppo_non_contate():
    """Le fatture di struttura arrivano gia' come quote_riparto_* sui singoli PV:
    contarle anche qui le sottrarrebbe DUE volte dal MOL."""
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(CAT_FB, 300.0, "2026-03-06", competenza=None, ripartita=True),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (100.0, 0.0)


def test_soft_delete_escluso():
    """Regola #5: le righe nel cestino non entrano nei margini."""
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(CAT_FB, 200.0, "2026-03-06", competenza=None, deleted_at="2026-03-07T00:00:00Z"),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (100.0, 0.0)


def test_filtro_per_ristorante():
    """Guardia multi-tenant: i costi di un'altra sede non entrano in questo MOL."""
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(CAT_FB, 700.0, "2026-03-06", competenza=None, ristorante_id=ALTRO_RID),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (100.0, 0.0)


def test_spese_generali_separate_dal_fb():
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(CAT_SPESE, 40.0, "2026-03-06", competenza=None),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 40.0)


# ─────────────────────────────────────────────────────────────────────────────
# Paginazione — il cap PostgREST a 1000 righe tronca in SILENZIO
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [999, 1000, 1001, 2000, 2500])
def test_paginazione_oltre_mille_righe(n):
    """I bordi esatti 1000 e 2000 sono dove `len(rows) < page_size` sbaglia."""
    rows = [_fattura(CAT_FB, 1.0, "2026-03-05", competenza=None) for _ in range(n)]
    sb = _FakeSB(fatture=rows)
    assert fw._calcola_costi_auto_per_mese(sb, RID, 2026, 3) == (float(n), 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (float(n), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Bordi e robustezza
# ─────────────────────────────────────────────────────────────────────────────

def test_mese_senza_fatture_ritorna_zero_zero():
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=[]), RID, 2026, 3) == (0.0, 0.0)


def test_per_periodo_include_tutti_i_mesi_target_anche_vuoti():
    """Invariante che gli `_aggrega_*` assumono implicitamente: la chiave c'e'
    sempre, anche per i mesi senza una sola fattura."""
    rows = [_fattura(CAT_FB, 100.0, "2026-03-05", competenza=None)]
    mesi = [(2026, 1), (2026, 2), (2026, 3)]
    out = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, mesi)
    assert set(out.keys()) == set(mesi)
    assert out[(2026, 1)] == (0.0, 0.0)
    assert out[(2026, 2)] == (0.0, 0.0)
    assert out[(2026, 3)] == (100.0, 0.0)


def test_per_periodo_ignora_righe_fuori_dai_mesi_target():
    """Con un buco nei mesi target, le righe di febbraio rientrano nel range della
    query (gen-mar) ma non hanno un bucket: vanno scartate, non sommate altrove."""
    rows = [
        _fattura(CAT_FB, 10.0, "2026-01-05", competenza=None),
        _fattura(CAT_FB, 999.0, "2026-02-05", competenza=None),
        _fattura(CAT_FB, 30.0, "2026-03-05", competenza=None),
    ]
    out = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 1), (2026, 3)])
    assert out == {(2026, 1): (10.0, 0.0), (2026, 3): (30.0, 0.0)}


def test_per_periodo_vuoto_ritorna_dict_vuoto_senza_interrogare_il_db():
    rec = {}
    sb = _FakeSB(fatture=_dataset_misto(), recorder=rec)
    assert fw._calcola_costi_auto_per_periodo(sb, RID, []) == {}
    assert rec.get("tables", []) == []


@pytest.mark.parametrize("valore", ["abc", None, "", "12,50"])
def test_totale_riga_non_numerico_vale_zero(valore):
    """Un importo illeggibile non deve far esplodere il calcolo del MOL."""
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(CAT_FB, valore, "2026-03-06", competenza=None),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)
    per_periodo = fw._calcola_costi_auto_per_periodo(_FakeSB(fatture=rows), RID, [(2026, 3)])
    assert per_periodo[(2026, 3)] == (100.0, 0.0)


@pytest.mark.parametrize("cat_vuota", ["", None])
def test_categoria_vuota_non_entra_nel_fb(cat_vuota):
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(cat_vuota, 700.0, "2026-03-06", competenza=None),
    ]
    assert fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3) == (100.0, 0.0)


def test_importi_sommati_prima_di_arrotondare():
    """L'arrotondamento e' FINALE, non per riga.

    Quattro righe da 0.004: sommate danno 0.016 -> 0.02. Arrotondando prima ogni
    riga si otterrebbe 0.0. Evito di proposito importi che finiscono in .xx5
    esatto (round() in Python pareggia al pari: 0.015 -> 0.01), perche' lì il
    test misurerebbe la regola di pareggio invece dell'ordine delle operazioni.
    """
    rows = [_fattura(CAT_FB, 0.004, "2026-03-05", competenza=None) for _ in range(4)]
    fb, _ = fw._calcola_costi_auto_per_mese(_FakeSB(fatture=rows), RID, 2026, 3)
    assert fb == 0.02


@pytest.mark.parametrize("data_rotta", ["2026-0x-06", "2026-**-06"])
def test_data_illeggibile_non_rompe_il_periodo(data_rotta):
    """`_per_periodo` ricava (anno, mese) affettando la stringa: una data in un
    formato inatteso va saltata, non deve far esplodere il calcolo del MOL.

    Le date scelte passano il confronto lessicale del range ('2026-03-01' <=
    '2026-0x-06' <= '2026-03-31' non regge, quindi si usa un range piu' ampio)
    ma non si lasciano convertire in interi: e' il ramo
    `except (ValueError, IndexError)`. Una data tipo 'xxxx-yy-zz' non
    servirebbe: verrebbe scartata prima, dal filtro di periodo.
    """
    rows = [
        _fattura(CAT_FB, 100.0, "2026-03-05", competenza=None),
        _fattura(CAT_FB, 50.0, "2026-03-06", competenza=data_rotta),
    ]
    out = fw._calcola_costi_auto_per_periodo(
        _FakeSB(fatture=rows), RID, [(2026, 3), (2026, 12)])
    assert out[(2026, 3)] == (100.0, 0.0)
