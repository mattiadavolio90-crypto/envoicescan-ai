"""Test per get_documenti_scadenziario e get_fatture_cestino (Fase 1 catena/fatture).

Copre:
- totale autorevole da fatture_documenti (fallback su somma-righe) + warning totale_incoerente
- piva_fornitore esposta per riga (raggruppamento fornitori lato frontend)
- get_fatture_cestino con ristorante_id come lista (modalità catena)
"""
import importlib
import sys

from services.documenti_service import get_documenti_scadenziario

def _get_fatture_cestino_unwrapped():
    """Estrae get_fatture_cestino bypassando il mock streamlit di conftest.py.

    get_fatture_cestino e' decorata con @_make_cache -> st.cache_data(**kwargs),
    applicato a IMPORT TIME. conftest.py mocka l'intero modulo streamlit con un
    MagicMock generico: st.cache_data(**kwargs) restituisce quindi un altro
    MagicMock (non un decorator identity), e la funzione decorata diventa essa
    stessa un MagicMock che non esegue mai il body reale.

    Nessun altro test in questa suite chiama get_fatture_cestino direttamente
    (verificato), quindi il reload qui e' innocuo per il resto della sessione
    finche' viene ripristinato subito con il blocco finally: si rende
    cache_data un passthrough, si ricarica il modulo per estrarre la funzione
    reale (indipendente una volta ottenuta), poi si ripristina lo stato
    originale cosi' services.db_service torna identico a prima per tutti gli
    altri test (che contano su .clear() da MagicMock, es. test_db_service.py).
    """
    def _passthrough(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def _wrap(fn):
            return fn
        return _wrap

    import services.db_service as db_service

    original_cache_data = sys.modules["streamlit"].cache_data
    try:
        sys.modules["streamlit"].cache_data = _passthrough
        importlib.reload(db_service)
        return db_service.get_fatture_cestino
    finally:
        sys.modules["streamlit"].cache_data = original_cache_data
        importlib.reload(db_service)


get_fatture_cestino = _get_fatture_cestino_unwrapped()


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, tables):
        self.table_name = table_name
        self.tables = tables
        self._filters = {}
        self._single = False
        self._offset = 0

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def in_(self, key, values):
        self._filters[key] = ("__in__", list(values))
        return self

    def is_(self, *args, **kwargs):
        return self

    @property
    def not_(self):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def single(self):
        self._single = True
        return self

    def range(self, start, end):
        self._offset = start
        return self

    def _rows(self):
        rows = self.tables.get(self.table_name, [])
        out = []
        for row in rows:
            ok = True
            for k, v in self._filters.items():
                if isinstance(v, tuple) and v[0] == "__in__":
                    if row.get(k) not in v[1]:
                        ok = False
                        break
                elif row.get(k) != v:
                    ok = False
                    break
            if ok:
                out.append(row)
        return out

    def execute(self):
        if self._offset > 0:
            return _Response([] if not self._single else None)
        rows = self._rows()
        if self._single:
            return _Response(rows[0] if rows else None)
        return _Response(rows)


class _FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(name, self.tables)


def _base_tables(fatture_rows, fatture_documenti_rows, ristoranti_rows=None):
    return {
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": ristoranti_rows or [{"id": "rist-1", "nuovi_da": None}],
    }


def test_totale_autorevole_da_fatture_documenti(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [
        {
            "user_id": "u1",
            "ristorante_id": "rist-1",
            "file_origine": "doc1.xml",
            "fornitore": "Fornitore SRL",
            "tipo_documento": "TD01",
            "totale_riga": 50.0,
            "data_documento": "2026-01-10",
            "created_at": "2026-01-10T10:00:00Z",
        },
        {
            "user_id": "u1",
            "ristorante_id": "rist-1",
            "file_origine": "doc1.xml",
            "fornitore": "Fornitore SRL",
            "tipo_documento": "TD01",
            "totale_riga": 30.0,
            "data_documento": "2026-01-10",
            "created_at": "2026-01-10T10:00:00Z",
        },
    ]
    # totale_riga somma 80.0, ma il documento reale (PDF/XML) vale 100.0: una riga
    # e' stata soft-deleted senza che il totale_documento venga ricalcolato.
    fatture_documenti_rows = [
        {
            "user_id": "u1",
            "ristorante_id": "rist-1",
            "file_origine": "doc1.xml",
            "piva_fornitore": "12345678901",
            "numero_documento": "1",
            "totale_documento": 100.0,
            "scadenza_xml": None,
            "giorni_termini_xml": None,
            "scadenza_effettiva": None,
            "scadenza_source": None,
            "scadenza_override": None,
            "pagata": False,
            "pagata_at": None,
        }
    ]
    sb = _FakeSupabase(_base_tables(fatture_rows, fatture_documenti_rows))

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert len(result) == 1
    doc = result[0]
    assert doc["totale_documento"] == 100.0
    assert doc["totale_incoerente"] is True
    assert doc["piva_fornitore"] == "12345678901"


def test_totale_coerente_nessun_warning(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [
        {
            "user_id": "u1",
            "ristorante_id": "rist-1",
            "file_origine": "doc2.xml",
            "fornitore": "Altro Fornitore",
            "tipo_documento": "TD01",
            "totale_riga": 42.5,
            "data_documento": "2026-02-01",
            "created_at": "2026-02-01T09:00:00Z",
        },
    ]
    fatture_documenti_rows = [
        {
            "user_id": "u1",
            "ristorante_id": "rist-1",
            "file_origine": "doc2.xml",
            "piva_fornitore": "99988877766",
            "numero_documento": "2",
            "totale_documento": 42.5,
            "scadenza_xml": None,
            "giorni_termini_xml": None,
            "scadenza_effettiva": None,
            "scadenza_source": None,
            "scadenza_override": None,
            "pagata": False,
            "pagata_at": None,
        }
    ]
    sb = _FakeSupabase(_base_tables(fatture_rows, fatture_documenti_rows))

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["totale_incoerente"] is False


def test_totale_fallback_su_somma_righe_senza_fatture_documenti(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [
        {
            "user_id": "u1",
            "ristorante_id": "rist-1",
            "file_origine": "doc3.xml",
            "fornitore": "Senza Header",
            "tipo_documento": "TD01",
            "totale_riga": 20.0,
            "data_documento": "2026-03-01",
            "created_at": "2026-03-01T09:00:00Z",
        },
    ]
    sb = _FakeSupabase(_base_tables(fatture_rows, []))

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["totale_documento"] == 20.0
    assert result[0]["totale_incoerente"] is False
    assert result[0]["piva_fornitore"] is None


def test_get_documenti_scadenziario_lista_sedi_aggrega_e_marca_sede(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [
        {
            "user_id": "u1", "ristorante_id": "rist-1", "file_origine": "doc1.xml",
            "fornitore": "Fornitore A", "tipo_documento": "TD01", "totale_riga": 50.0,
            "data_documento": "2026-01-10", "created_at": "2026-01-10T10:00:00Z",
        },
        {
            "user_id": "u1", "ristorante_id": "rist-tecnica", "file_origine": "doc2.xml",
            "fornitore": "Fornitore B", "tipo_documento": "TD01", "totale_riga": 30.0,
            "data_documento": "2026-01-11", "created_at": "2026-01-11T10:00:00Z",
        },
    ]
    ristoranti_rows = [
        {"id": "rist-1", "nuovi_da": None},
        {"id": "rist-tecnica", "nuovi_da": None},
    ]
    sb = _FakeSupabase(_base_tables(fatture_rows, [], ristoranti_rows))
    sedi_nomi = {"rist-1": "OFFSIDE San Giuliano", "rist-tecnica": "Costi comuni di gruppo"}

    result = get_documenti_scadenziario(
        user_id="u1",
        ristorante_id=["rist-1", "rist-tecnica"],
        supabase_client=sb,
        sedi_nomi=sedi_nomi,
    )

    assert len(result) == 2
    by_file = {r["file_origine"]: r for r in result}
    assert by_file["doc1.xml"]["ristorante_id"] == "rist-1"
    assert by_file["doc1.xml"]["sede_nome"] == "OFFSIDE San Giuliano"
    assert by_file["doc2.xml"]["ristorante_id"] == "rist-tecnica"
    assert by_file["doc2.xml"]["sede_nome"] == "Costi comuni di gruppo"
    assert by_file["doc1.xml"]["totale_documento"] == 50.0


def test_get_documenti_scadenziario_ristorante_singolo_non_espone_sede(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [
        {
            "user_id": "u1", "ristorante_id": "rist-1", "file_origine": "doc1.xml",
            "fornitore": "Fornitore A", "tipo_documento": "TD01", "totale_riga": 50.0,
            "data_documento": "2026-01-10", "created_at": "2026-01-10T10:00:00Z",
        },
    ]
    sb = _FakeSupabase(_base_tables(fatture_rows, []))

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert len(result) == 1
    assert "ristorante_id" not in result[0]
    assert "sede_nome" not in result[0]


def test_get_documenti_scadenziario_stesso_file_origine_su_piu_sedi_non_si_confonde(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [
        {
            "user_id": "u1", "ristorante_id": "rist-1", "file_origine": "dup.xml",
            "fornitore": "F1", "tipo_documento": "TD01", "totale_riga": 10.0,
            "data_documento": "2026-01-01", "created_at": "2026-01-01T00:00:00Z",
        },
        {
            "user_id": "u1", "ristorante_id": "rist-2", "file_origine": "dup.xml",
            "fornitore": "F1", "tipo_documento": "TD01", "totale_riga": 15.0,
            "data_documento": "2026-01-01", "created_at": "2026-01-01T00:00:00Z",
        },
    ]
    ristoranti_rows = [{"id": "rist-1", "nuovi_da": None}, {"id": "rist-2", "nuovi_da": None}]
    sb = _FakeSupabase(_base_tables(fatture_rows, [], ristoranti_rows))

    result = get_documenti_scadenziario(
        user_id="u1", ristorante_id=["rist-1", "rist-2"], supabase_client=sb, sedi_nomi={},
    )

    assert len(result) == 2
    totali = sorted(r["totale_documento"] for r in result)
    assert totali == [10.0, 15.0]


def test_get_fatture_cestino_ristorante_singolo_invariato():
    rows = [
        {"user_id": "u1", "file_origine": "a.xml", "fornitore": "F1", "totale_riga": 10.0, "deleted_at": "2026-01-01T00:00:00Z", "data_documento": "2026-01-01", "ristorante_id": "rist-1"},
        {"user_id": "u1", "file_origine": "b.xml", "fornitore": "F2", "totale_riga": 5.0, "deleted_at": "2026-01-02T00:00:00Z", "data_documento": "2026-01-02", "ristorante_id": "rist-2"},
    ]
    sb = _FakeSupabase({"fatture": rows})

    result = get_fatture_cestino("u1", ristorante_id="rist-1", supabase_client=sb)

    assert len(result) == 1
    assert result[0]["file_origine"] == "a.xml"
    assert "ristorante_id" not in result[0]


def test_get_fatture_cestino_lista_sedi_aggrega_e_marca_sede(monkeypatch):
    rows = [
        {"user_id": "u1", "file_origine": "a.xml", "fornitore": "F1", "totale_riga": 10.0, "deleted_at": "2026-01-01T00:00:00Z", "data_documento": "2026-01-01", "ristorante_id": "rist-1"},
        {"user_id": "u1", "file_origine": "b.xml", "fornitore": "F2", "totale_riga": 5.0, "deleted_at": "2026-01-02T00:00:00Z", "data_documento": "2026-01-02", "ristorante_id": "rist-2"},
        {"user_id": "u1", "file_origine": "c.xml", "fornitore": "F3", "totale_riga": 7.0, "deleted_at": "2026-01-03T00:00:00Z", "data_documento": "2026-01-03", "ristorante_id": "rist-tecnica"},
    ]
    sb = _FakeSupabase({"fatture": rows})
    sedi_nomi = {"rist-1": "OFFSIDE San Giuliano", "rist-2": "OFFSIDE Villaguardia", "rist-tecnica": "Costi comuni di gruppo"}

    result = get_fatture_cestino(
        "u1",
        ristorante_id=["rist-1", "rist-2", "rist-tecnica"],
        supabase_client=sb,
        sedi_nomi=sedi_nomi,
    )

    assert len(result) == 3
    by_file = {r["file_origine"]: r for r in result}
    assert by_file["a.xml"]["sede_nome"] == "OFFSIDE San Giuliano"
    assert by_file["c.xml"]["sede_nome"] == "Costi comuni di gruppo"
    assert all("ristorante_id" in r for r in result)


def test_get_fatture_cestino_stesso_file_origine_su_piu_sedi_non_si_confonde():
    # Stesso file_origine su 2 sedi diverse (P.IVA condivisa, routing multi-sede):
    # devono restare 2 righe distinte, non una sola aggregata.
    rows = [
        {"user_id": "u1", "file_origine": "dup.xml", "fornitore": "F1", "totale_riga": 10.0, "deleted_at": "2026-01-01T00:00:00Z", "data_documento": "2026-01-01", "ristorante_id": "rist-1"},
        {"user_id": "u1", "file_origine": "dup.xml", "fornitore": "F1", "totale_riga": 15.0, "deleted_at": "2026-01-01T00:00:00Z", "data_documento": "2026-01-01", "ristorante_id": "rist-2"},
    ]
    sb = _FakeSupabase({"fatture": rows})

    result = get_fatture_cestino("u1", ristorante_id=["rist-1", "rist-2"], supabase_client=sb, sedi_nomi={})

    assert len(result) == 2
    totali = sorted(r["totale"] for r in result)
    assert totali == [10.0, 15.0]
