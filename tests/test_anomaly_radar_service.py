from unittest.mock import MagicMock

from services.anomaly_radar_service import (
    _check_consecutive_months,
    check_on_upload,
)


class _SeqSupabase:
    def __init__(self, responses):
        self._responses = list(responses)

    def table(self, _name):
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def lte(self, *_args, **_kwargs):
        return self

    def neq(self, *_args, **_kwargs):
        return self

    def is_(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def not_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        data = self._responses.pop(0) if self._responses else []
        return MagicMock(data=data)


def test_duplicato_trovato():
    nuovi_docs = [{
        'id': '1',
        'piva_fornitore': 'IT123',
        'fornitore': 'Acme',
        'totale_documento': 100.0,
        'data_documento': '2026-05-10',
        'file_origine': 'a.xml',
    }]
    # bulk prefetch: contiene il potenziale duplicato (file diverso, data in range, piva uguale)
    candidati_bulk = [{
        'id': '2',
        'piva_fornitore': 'IT123',
        'totale_documento': 101.0,
        'file_origine': 'b.xml',
        'data_documento': '2026-05-09',
    }]

    sb = _SeqSupabase([
        nuovi_docs,
        candidati_bulk,  # prefetch bulk (step 2 + step 4)
        [],              # tutti per piva_dup (step 3)
    ])

    records = check_on_upload('u1', 'r1', 'up1', supabase_client=sb)
    topics = {r['topic_key'] for r in records}
    assert 'fattura_duplicata' in topics


def test_no_duplicato():
    nuovi_docs = [{
        'id': '1',
        'piva_fornitore': 'IT123',
        'fornitore': 'Acme',
        'totale_documento': 100.0,
        'data_documento': '2026-05-10',
        'file_origine': 'a.xml',
    }]

    sb = _SeqSupabase([
        nuovi_docs,
        [],  # prefetch bulk vuoto
        [],  # tutti per piva_dup
    ])

    records = check_on_upload('u1', 'r1', 'up1', supabase_client=sb)
    assert records == []


def test_piva_dup():
    nuovi_docs = [{
        'id': '1',
        'piva_fornitore': 'IT123',
        'fornitore': 'Acme',
        'totale_documento': 100.0,
        'data_documento': '2026-05-10',
        'file_origine': 'a.xml',
    }]
    tutti = [
        {'piva_fornitore': 'IT123', 'fornitore': 'Acme Srl'},
        {'piva_fornitore': 'IT123', 'fornitore': 'Acme SRL Nuova'},
    ]

    sb = _SeqSupabase([
        nuovi_docs,
        [],    # prefetch bulk vuoto
        tutti, # piva_dup (step 3)
    ])

    records = check_on_upload('u1', 'r1', 'up1', supabase_client=sb)
    topics = {r['topic_key'] for r in records}
    assert 'piva_duplicata_fornitore' in topics


def test_anomalia_5x():
    nuovi_docs = [{
        'id': '1',
        'piva_fornitore': 'IT123',
        'fornitore': 'Acme',
        'totale_documento': 1000.0,
        'data_documento': '2026-05-10',
        'file_origine': 'a.xml',
    }]
    # bulk prefetch: storici con piva_fornitore e file_origine diverso dall'upload
    storico_bulk = [
        {'id': '10', 'piva_fornitore': 'IT123', 'totale_documento': 100.0, 'file_origine': 'old.xml', 'data_documento': '2025-01-01'},
        {'id': '11', 'piva_fornitore': 'IT123', 'totale_documento': 110.0, 'file_origine': 'old.xml', 'data_documento': '2024-12-01'},
        {'id': '12', 'piva_fornitore': 'IT123', 'totale_documento': 90.0, 'file_origine': 'old.xml', 'data_documento': '2024-11-01'},
    ]

    sb = _SeqSupabase([
        nuovi_docs,
        storico_bulk,  # prefetch bulk (step 2 + step 4)
        [],            # tutti per piva_dup (step 3)
    ])

    records = check_on_upload('u1', 'r1', 'up1', supabase_client=sb)
    topics = {r['topic_key'] for r in records}
    assert 'fattura_anomala_importo' in topics


def test_troppo_pochi_storici():
    nuovi_docs = [{
        'id': '1',
        'piva_fornitore': 'IT123',
        'fornitore': 'Acme',
        'totale_documento': 1000.0,
        'data_documento': '2026-05-10',
        'file_origine': 'a.xml',
    }]
    # solo 2 storici: sotto la soglia minima di 3 → nessuna anomalia
    storico_bulk = [
        {'id': '10', 'piva_fornitore': 'IT123', 'totale_documento': 100.0, 'file_origine': 'old.xml', 'data_documento': '2025-01-01'},
        {'id': '11', 'piva_fornitore': 'IT123', 'totale_documento': 110.0, 'file_origine': 'old.xml', 'data_documento': '2024-12-01'},
    ]

    sb = _SeqSupabase([
        nuovi_docs,
        storico_bulk,  # prefetch bulk
        [],            # tutti per piva_dup
    ])

    records = check_on_upload('u1', 'r1', 'up1', supabase_client=sb)
    topics = {r['topic_key'] for r in records}
    assert 'fattura_anomala_importo' not in topics


def test_consecutive_months():
    assert _check_consecutive_months(['2026-01', '2026-02', '2026-03']) == 3
    assert _check_consecutive_months(['2026-01', '2026-03', '2026-04']) == 2
