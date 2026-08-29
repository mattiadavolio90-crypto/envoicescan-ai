"""Test del radar anomalie.

Il fake qui sotto valida i nomi di colonna contro lo schema reale di
`fatture_documenti` (misurato su information_schema il 29/8/2026, 27 colonne).
La versione precedente restituiva `self` da ogni builder ignorando gli
argomenti: i 6 test passavano da sempre su una query che filtrava
`.eq('upload_id', ...)`, colonna che non e' mai esistita. Un mock che non
guarda cosa gli viene chiesto non e' una rete, e' un tappeto.
"""

import pytest
from unittest.mock import MagicMock

from services.anomaly_radar_service import (
    _check_consecutive_months,
    check_on_upload,
)

# Schema reale di fatture_documenti (information_schema, 29/8/2026).
_COLONNE_FATTURE_DOCUMENTI = {
    'id', 'user_id', 'ristorante_id', 'file_origine', 'fornitore',
    'piva_fornitore', 'numero_documento', 'data_documento', 'data_competenza',
    'tipo_documento', 'totale_documento', 'totale_imponibile', 'totale_iva',
    'segno_compensazione', 'scadenza_xml', 'giorni_termini_xml',
    'scadenza_override', 'scadenza_effettiva', 'scadenza_source', 'pagata',
    'pagata_at', 'note_pagamento', 'source_origin', 'created_at', 'updated_at',
    'deleted_at', 'pagata_manuale_at',
}

_SCHEMI = {'fatture_documenti': _COLONNE_FATTURE_DOCUMENTI}


class _SeqSupabase:
    """Fake fluent che risponde in sequenza MA verifica le colonne richieste.

    Registra in `self.filtri` ogni (metodo, colonna) applicato, così i test
    possono asserire su cosa e' stato davvero interrogato.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.filtri = []
        self.colonne_selezionate = []
        self._tabella = None

    def _valida(self, colonna):
        schema = _SCHEMI.get(self._tabella)
        if schema is not None and colonna not in schema:
            raise AssertionError(
                f"Colonna '{colonna}' inesistente su '{self._tabella}'. "
                f"Colonne reali: {sorted(schema)}"
            )

    def table(self, name):
        self._tabella = name
        return self

    def select(self, *args, **_kwargs):
        for arg in args:
            for col in str(arg).split(','):
                col = col.strip()
                if col and col != '*':
                    self._valida(col)
                    self.colonne_selezionate.append(col)
        return self

    def eq(self, colonna, _valore=None):
        self._valida(colonna)
        self.filtri.append(('eq', colonna))
        return self

    def in_(self, colonna, _valori=None):
        self._valida(colonna)
        self.filtri.append(('in_', colonna))
        return self

    def gte(self, colonna, _valore=None):
        self._valida(colonna)
        self.filtri.append(('gte', colonna))
        return self

    def lte(self, colonna, _valore=None):
        self._valida(colonna)
        self.filtri.append(('lte', colonna))
        return self

    def neq(self, colonna, _valore=None):
        self._valida(colonna)
        self.filtri.append(('neq', colonna))
        return self

    def is_(self, colonna, _valore=None):
        self._valida(colonna)
        self.filtri.append(('is_', colonna))
        return self

    def not_(self, *_args, **_kwargs):
        return self

    def order(self, colonna, **_kwargs):
        self._valida(colonna)
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        data = self._responses.pop(0) if self._responses else []
        return MagicMock(data=data)

        return MagicMock(data=data)


def test_duplicato_trovato():
    nuovi_docs = [{
        'id': '1',
        'piva_fornitore': 'IT123',
        'fornitore': 'Acme',
        'totale_documento': 100.0,
        'data_documento': '2026-05-10',
        'file_origine': 'a.xml',
        'numero_documento': 'FT-500',
    }]
    # bulk prefetch: stesso numero documento => duplicato vero
    candidati_bulk = [{
        'id': '2',
        'piva_fornitore': 'IT123',
        'totale_documento': 101.0,
        'file_origine': 'b.xml',
        'data_documento': '2026-05-09',
        'numero_documento': 'FT-500',
    }]

    sb = _SeqSupabase([
        nuovi_docs,
        candidati_bulk,  # prefetch bulk (step 2 + step 4)
        [],              # tutti per piva_dup (step 3)
    ])

    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
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

    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
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

    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
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

    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
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

    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
    topics = {r['topic_key'] for r in records}
    assert 'fattura_anomala_importo' not in topics


def test_consecutive_months():
    assert _check_consecutive_months(['2026-01', '2026-02', '2026-03']) == 3
    assert _check_consecutive_months(['2026-01', '2026-03', '2026-04']) == 2


# ── Ritaratura della regola duplicati (29/8/2026) ────────────────────────
# Misurato sui 3.839 documenti reali: senza il confronto sul numero documento
# la regola produceva 1.446 coppie su 897 documenti in 9 sedi, nessuna con lo
# stesso numero. Erano 897 allarmi 'error' tutti falsi.

def _doc(**kw):
    base = {
        'id': '1', 'piva_fornitore': 'IT123', 'fornitore': 'Acme',
        'totale_documento': 100.0, 'data_documento': '2026-05-10',
        'file_origine': 'a.xml', 'numero_documento': 'FT-500',
    }
    base.update(kw)
    return base


def test_fornitura_ricorrente_non_e_un_duplicato():
    """Stessa P.IVA, data vicina, importo quasi uguale, ma numero diverso.

    E' il profilo di TUTTE le 1.446 coppie misurate in produzione: consegne
    ricorrenti dello stesso fornitore. Non deve allarmare.
    """
    sb = _SeqSupabase([
        [_doc(numero_documento='FT-500')],
        [_doc(id='2', file_origine='b.xml', totale_documento=101.0,
              data_documento='2026-05-09', numero_documento='FT-777')],
        [],
    ])
    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
    assert 'fattura_duplicata' not in {r['topic_key'] for r in records}


def test_duplicato_vero_resta_intercettato():
    """Stesso fornitore, stesso numero, stesso importo: e' il caso che costa soldi."""
    sb = _SeqSupabase([
        [_doc(numero_documento='FT-500')],
        [_doc(id='2', file_origine='b.xml', numero_documento='FT-500')],
        [],
    ])
    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
    assert 'fattura_duplicata' in {r['topic_key'] for r in records}


def test_documento_senza_numero_non_allarma():
    sb = _SeqSupabase([
        [_doc(numero_documento='')],
        [_doc(id='2', file_origine='b.xml', numero_documento='')],
        [],
    ])
    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
    assert 'fattura_duplicata' not in {r['topic_key'] for r in records}


# ── Correlatore ──────────────────────────────────────────────────────────

def test_filtra_su_file_origine_non_su_upload_id():
    """La query deve interrogare `file_origine`, l'unica identita' persistita.

    Il fake solleva da solo su una colonna inesistente; qui si asserisce anche
    che il filtro giusto sia stato davvero applicato.
    """
    sb = _SeqSupabase([[], [], []])
    check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
    assert ('in_', 'file_origine') in sb.filtri
    assert not any(col == 'upload_id' for _, col in sb.filtri)


def test_file_ids_usano_il_file_origine_reale():
    """Il bucket di dedupe deve essere stabile per documento.

    Con il vecchio `upload_id` (un timestamp generato a ogni esecuzione) l'hash
    dei file_ids cambiava sempre e la dedupe era di fatto disattivata.
    """
    sb = _SeqSupabase([
        [_doc(numero_documento='FT-500')],
        [_doc(id='2', file_origine='b.xml', numero_documento='FT-500')],
        [],
    ])
    records = check_on_upload('u1', 'r1', ['a.xml'], supabase_client=sb)
    dup = [r for r in records if r['topic_key'] == 'fattura_duplicata']
    assert dup, 'atteso un duplicato da cui leggere il bucket'
    assert dup[0]['payload']['file_origine'] == 'a.xml'


@pytest.mark.parametrize('correlatore', [[], None, '', ['   ']])
def test_correlatore_vuoto_non_interroga_il_db(correlatore):
    sb = _SeqSupabase([[], [], []])
    assert check_on_upload('u1', 'r1', correlatore, supabase_client=sb) == []
    assert sb.filtri == []


def test_accetta_anche_una_stringa_singola():
    """L'aggancio per-fattura passa un solo file: non deve essere iterato a caratteri."""
    sb = _SeqSupabase([[], [], []])
    check_on_upload('u1', 'r1', 'a.xml', supabase_client=sb)
    assert ('in_', 'file_origine') in sb.filtri
