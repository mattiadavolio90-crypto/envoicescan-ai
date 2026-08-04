"""Test guardia: la propagazione admin di una correzione di memoria globale
(prodotti_master → tutte le fatture storiche di TUTTI i clienti) applica il
guardrail NOTE E DICITURE su righe con importo != 0.

Contesto (audit AI 2ª passata, 04/08): _propaga_global_override_a_fatture_storiche
selezionava e aggiornava le righe fatture SENZA controllare totale_riga, a
differenza di ogni altro punto di scrittura categoria (12+ call site in
ai_service.py, più routers/admin.py:967-976). Un admin che promuove una
descrizione a "📝 NOTE E DICITURE" da Admin → Categorie → Memoria globale
avrebbe silenziosamente tolto dai margini righe con importo != 0 di clienti
diversi da quello su cui stava correggendo — violazione regola di dominio #2,
nessun needs_review, nessuna traccia in coda.
"""
import importlib

ai_service = importlib.import_module("services.ai_service")


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, updates, op="select"):
        self._store = store
        self._updates = updates
        self._op = op
        self._vals = None
        self._in_filter = None
        self._eq_filters = []
        self._neq_filters = []

    def select(self, *_a, **_k):
        return self

    def update(self, vals):
        self._op = "update"
        self._vals = dict(vals)
        return self

    def is_(self, _f, _v):
        return self

    def neq(self, f, v):
        self._neq_filters.append((f, v))
        return self

    def eq(self, f, v):
        self._eq_filters.append((f, v))
        return self

    def ilike(self, _f, _pattern):
        return self  # il fake non filtra per token: la logica reale confronta la desc normalizzata

    def in_(self, f, vals):
        self._in_filter = (f, list(vals))
        return self

    def range(self, _start, _end):
        return self

    def execute(self):
        if self._op == "update":
            f, ids = self._in_filter
            touched = [r for r in self._store if r.get(f) in ids]
            for r in touched:
                r.update(self._vals)
            self._updates.append((dict(self._vals), [r.get("id") for r in touched]))
            return _Resp([dict(r) for r in touched])
        rows = list(self._store)
        for col, val in self._neq_filters:
            rows = [r for r in rows if r.get(col) != val]
        return _Resp([dict(r) for r in rows])


class FakeSB:
    def __init__(self, rows, override_rows=None):
        self._rows = rows
        self._override_rows = override_rows or []
        self.updates = []

    def table(self, name):
        if name == "prodotti_utente":
            return _Query(self._override_rows, self.updates)
        return _Query(self._rows, self.updates)


def test_propagazione_note_esclude_righe_con_importo_diverso_da_zero():
    """Due clienti hanno fatture con la stessa descrizione: uno a importo 0 (vera
    dicitura), l'altro a importo > 0. La propagazione a NOTE E DICITURE deve
    scrivere solo sulla riga a importo zero."""
    rows = [
        {"id": "f1", "user_id": "u_a", "descrizione": "SCONTO FINALE OMAGGIO",
         "categoria": "Da Classificare", "totale_riga": 0.0, "prezzo_unitario": 0.0},
        {"id": "f2", "user_id": "u_b", "descrizione": "SCONTO FINALE OMAGGIO",
         "categoria": "Da Classificare", "totale_riga": 12.50, "prezzo_unitario": 12.50},
    ]
    sb = FakeSB(rows)
    desc_normalized, _ = ai_service.get_descrizione_normalizzata_e_originale("SCONTO FINALE OMAGGIO")

    aggiornate = ai_service._propaga_global_override_a_fatture_storiche(
        desc_normalized, "📝 NOTE E DICITURE", sb,
    )

    assert aggiornate == 1
    assert sb._rows[0]["categoria"] == "📝 NOTE E DICITURE"  # importo 0: propagata
    assert sb._rows[1]["categoria"] == "Da Classificare"      # importo != 0: NON toccata


def test_propagazione_note_con_importo_negativo_esclusa():
    """Un reso/abbuono con segno negativo è comunque != 0: esclude dalla propagazione
    NOTE E DICITURE, stesso criterio degli importi positivi."""
    rows = [
        {"id": "f1", "user_id": "u_a", "descrizione": "ABBUONO CLIENTE",
         "categoria": "Da Classificare", "totale_riga": -5.0, "prezzo_unitario": -5.0},
    ]
    sb = FakeSB(rows)
    desc_normalized, _ = ai_service.get_descrizione_normalizzata_e_originale("ABBUONO CLIENTE")

    aggiornate = ai_service._propaga_global_override_a_fatture_storiche(
        desc_normalized, "📝 NOTE E DICITURE", sb,
    )

    assert aggiornate == 0
    assert sb._rows[0]["categoria"] == "Da Classificare"


def test_propagazione_categoria_normale_non_richiede_filtro_importo():
    """Per categorie reali (non NOTE E DICITURE) il guardrail importo non si applica:
    la propagazione tocca tutte le righe candidate a prescindere dall'importo."""
    rows = [
        {"id": "f1", "user_id": "u_a", "descrizione": "POMODORI PELATI",
         "categoria": "VERDURE", "totale_riga": 30.0, "prezzo_unitario": 30.0},
        {"id": "f2", "user_id": "u_b", "descrizione": "POMODORI PELATI",
         "categoria": "VERDURE", "totale_riga": 18.0, "prezzo_unitario": 18.0},
    ]
    sb = FakeSB(rows)
    desc_normalized, _ = ai_service.get_descrizione_normalizzata_e_originale("POMODORI PELATI")

    aggiornate = ai_service._propaga_global_override_a_fatture_storiche(
        desc_normalized, "SCATOLAME E CONSERVE", sb,
    )

    assert aggiornate == 2
    assert sb._rows[0]["categoria"] == "SCATOLAME E CONSERVE"
    assert sb._rows[1]["categoria"] == "SCATOLAME E CONSERVE"


def test_propagazione_note_via_alias_senza_emoji_applica_comunque_guardrail():
    """_normalize_category_name converte l'alias storico 'NOTE E DICITURE' (senza
    emoji) nella categoria canonica PRIMA del calcolo del flag guardrail: passare
    l'alias non deve bucare il filtro importo."""
    rows = [
        {"id": "f1", "user_id": "u_a", "descrizione": "SCONTO FINALE OMAGGIO",
         "categoria": "Da Classificare", "totale_riga": 0.0, "prezzo_unitario": 0.0},
        {"id": "f2", "user_id": "u_b", "descrizione": "SCONTO FINALE OMAGGIO",
         "categoria": "Da Classificare", "totale_riga": 12.50, "prezzo_unitario": 12.50},
    ]
    sb = FakeSB(rows)
    desc_normalized, _ = ai_service.get_descrizione_normalizzata_e_originale("SCONTO FINALE OMAGGIO")

    aggiornate = ai_service._propaga_global_override_a_fatture_storiche(
        desc_normalized, "NOTE E DICITURE", sb,  # alias, senza emoji
    )

    assert aggiornate == 1
    assert sb._rows[0]["categoria"] == "📝 NOTE E DICITURE"
    assert sb._rows[1]["categoria"] == "Da Classificare"


def test_propagazione_note_rispetta_override_locale_manuale():
    """Un utente con correzione manuale locale (prodotti_utente) resta escluso dalla
    propagazione globale, indipendentemente dal guardrail importo (comportamento
    preesistente, verificato per non aver regredito col fix)."""
    rows = [
        {"id": "f1", "user_id": "u_a", "descrizione": "SCONTO FINALE OMAGGIO",
         "categoria": "Da Classificare", "totale_riga": 0.0, "prezzo_unitario": 0.0},
    ]
    override_rows = [
        {"user_id": "u_a", "descrizione": "SCONTO FINALE OMAGGIO", "classificato_da": "Manuale:cliente"},
    ]
    sb = FakeSB(rows, override_rows=override_rows)
    desc_normalized, _ = ai_service.get_descrizione_normalizzata_e_originale("SCONTO FINALE OMAGGIO")

    aggiornate = ai_service._propaga_global_override_a_fatture_storiche(
        desc_normalized, "📝 NOTE E DICITURE", sb,
    )

    assert aggiornate == 0
    assert sb._rows[0]["categoria"] == "Da Classificare"
