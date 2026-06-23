"""Test guardia: il path di auto-classificazione del worker (webhook automatico)
applica il guardrail NOTE E DICITURE su righe con importo != 0.

Contesto (audit 19/06, finding AI/DB MEDIUM): il flusso webhook
(_auto_classify_saved_rows) scriveva la categoria passando solo da
enforce_no_unclassified_category(), che NON guarda l'importo. Le regole forti / il
dizionario possono restituire "📝 NOTE E DICITURE" (es. COUPON, "RIGA FATTURA")
anche su righe con totale_riga > 0 → violazione regola di dominio #2 (NOTE E
DICITURE solo a importo zero), riga esclusa dai margini/MOL. Il path upload manuale
applicava già il guardrail; questo path no. Rilevante col go-live (fatture in arrivo
automatico dal 1/7).

Questi test esercitano la funzione REALE con un fake client in-memory + AI mockata.
"""
import importlib
from unittest.mock import patch

import pytest

qp = importlib.import_module("worker.queue_processor")


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    """Riproduce il chaining supabase-py usato da _auto_classify_saved_rows."""
    def __init__(self, store, updates):
        self._store = store
        self._updates = updates
        self._op = "select"
        self._eq = []
        self._or = None
        self._in = None
        self._vals = None

    def select(self, *_a, **_k):
        return self

    def update(self, vals):
        self._op = "update"
        self._vals = dict(vals)
        return self

    def eq(self, f, v):
        self._eq.append((f, v))
        return self

    def or_(self, expr):
        self._or = expr
        return self

    def in_(self, f, vals):
        self._in = (f, list(vals))
        return self

    def limit(self, _n):
        return self

    def is_(self, _f, _v):
        return self

    def not_(self, *_a, **_k):
        return self

    def _select_rows(self):
        # filtro: solo righe con categoria vuota/NULL/Da Classificare (come or_)
        out = []
        for r in self._store:
            cat = r.get("categoria")
            if cat in (None, "", "Da Classificare"):
                out.append(r)
        return out

    def execute(self):
        if self._op == "update":
            f, ids = self._in
            touched = [r for r in self._store if r.get(f) in ids]
            for r in touched:
                r.update(self._vals)
            self._updates.append((dict(self._vals), [r.get("id") for r in touched]))
            return _Resp([dict(r) for r in touched])
        return _Resp([dict(r) for r in self._select_rows()])


class FakeSB:
    def __init__(self, rows):
        self._rows = rows
        self.updates = []

    def table(self, _name):
        return _Query(self._rows, self.updates)


def _run(rows, categorie, confidenze=None):
    sb = FakeSB(rows)
    conf = confidenze if confidenze is not None else ["alta"] * len(categorie)
    with patch.object(qp, "classifica_via_worker_con_confidenza",
                      return_value=(categorie, conf)), \
         patch.object(qp, "aggiorna_streak_classificazione", return_value=None), \
         patch.object(qp, "filter_active", side_effect=lambda q: q):
        qp._auto_classify_saved_rows(
            supabase=sb, user_id="u1", ristorante_id="r1", nome_file="F.xml"
        )
    return sb


def test_note_su_importo_positivo_viene_corretta():
    """AI/regole assegnano NOTE E DICITURE a una riga con importo > 0 → non può
    restare NOTE: va riportata a 'Da Classificare' (non più SERVIZI travestito)."""
    rows = [
        {"id": 1, "descrizione": "COUPON SCONTO", "fornitore": "X", "iva_percentuale": 22,
         "totale_riga": 15.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["📝 NOTE E DICITURE"])
    assert sb._rows[0]["categoria"] == "Da Classificare"
    assert sb._rows[0]["needs_review"] is True


def test_note_su_importo_zero_resta_note():
    """Una vera dicitura a importo zero deve poter restare NOTE E DICITURE."""
    rows = [
        {"id": 1, "descrizione": "SCONTO FINALE OMAGGIO", "fornitore": "X", "iva_percentuale": 0,
         "totale_riga": 0.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["📝 NOTE E DICITURE"])
    assert sb._rows[0]["categoria"] == "📝 NOTE E DICITURE"


def test_categoria_normale_non_viene_toccata():
    """Una categoria reale su riga con importo passa invariata."""
    rows = [
        {"id": 1, "descrizione": "POMODORI PELATI", "fornitore": "X", "iva_percentuale": 10,
         "totale_riga": 30.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["VERDURE"])
    assert sb._rows[0]["categoria"] == "VERDURE"


def test_note_su_importo_negativo_viene_corretta():
    """Anche un importo negativo (reso/abbuono con segno) è != 0 → fuori da NOTE,
    riportato a 'Da Classificare'."""
    rows = [
        {"id": 1, "descrizione": "ABBUONO", "fornitore": "X", "iva_percentuale": 22,
         "totale_riga": -5.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["📝 NOTE E DICITURE"])
    assert sb._rows[0]["categoria"] == "Da Classificare"


# ─── Confidence routing: 'media' confermata dal runtime NON va in coda ─────────
# Contesto (23/06): un import via worker (LAND DEI SAPORI) aveva riempito la coda
# "Da controllare" di 207 prodotti OVVI (ICEBERG, SALMONE, LATTE...) solo perché GPT
# li aveva classificati con confidence 'media'. Se dizionario + regole forti del
# runtime confermano la stessa categoria, due fonti indipendenti concordano: niente
# revisione. La confidence 'bassa' resta sempre in coda.

def test_media_confermata_dal_runtime_non_va_in_review():
    """GPT 'media' su SALMONE→PESCE: le regole forti confermano PESCE → NO review."""
    rows = [
        {"id": 1, "descrizione": "SALMONE 5-6", "fornitore": "ADC SRL", "iva_percentuale": 10,
         "totale_riga": 40.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["PESCE"], confidenze=["media"])
    assert sb._rows[0]["categoria"] == "PESCE"
    assert sb._rows[0]["needs_review"] is False


def test_media_non_confermata_dal_runtime_va_in_review():
    """GPT 'media' su una descrizione che il runtime NON sa classificare da solo
    (sigla gergale) → resta in coda."""
    rows = [
        {"id": 1, "descrizione": "CRAUDI", "fornitore": "MEFON SRL", "iva_percentuale": 4,
         "totale_riga": 12.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["VERDURE"], confidenze=["media"])
    assert sb._rows[0]["categoria"] == "VERDURE"
    assert sb._rows[0]["needs_review"] is True


def test_bassa_va_sempre_in_review_anche_se_confermata():
    """Confidence 'bassa': in coda comunque, anche se il runtime confermerebbe."""
    rows = [
        {"id": 1, "descrizione": "ICEBERG", "fornitore": "MEFON SRL", "iva_percentuale": 4,
         "totale_riga": 8.0, "categoria": None},
    ]
    sb = _run(rows, categorie=["VERDURE"], confidenze=["bassa"])
    assert sb._rows[0]["categoria"] == "VERDURE"
    assert sb._rows[0]["needs_review"] is True
