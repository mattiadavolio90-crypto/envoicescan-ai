import ast
from pathlib import Path

import pandas as pd


PAGE_FILE = Path(__file__).resolve().parents[1] / 'components' / 'category_editor.py'


def _load_functions(*function_names):
    source = PAGE_FILE.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(PAGE_FILE))

    wanted = set(function_names)
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]

    for node in selected:
        node.decorator_list = []

    found = {node.name for node in selected}
    missing = wanted - found
    if missing:
        raise AssertionError(f"Funzioni non trovate in {PAGE_FILE.name}: {sorted(missing)}")

    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    def _fake_get_nome_base_file(name):
        value = str(name or '').strip()
        if value.lower().endswith('.p7m'):
            value = value[:-4]
        return value

    namespace = {'pd': pd, 'get_nome_base_file': _fake_get_nome_base_file}
    exec(compile(module, str(PAGE_FILE), 'exec'), namespace)
    return [namespace[name] for name in function_names]


_compute_novita_badge, _resolve_novita_badge, _sort_detail_rows = _load_functions(
    '_compute_novita_badge',
    '_resolve_novita_badge',
    '_sort_detail_rows',
)


def test_compute_novita_badge_uses_last_login_reference():
    assert _compute_novita_badge('2026-04-19T10:00:00+00:00', '2026-04-18T20:00:00+00:00') == '🆕 Nuova'
    assert _compute_novita_badge('2026-04-18T10:00:00+00:00', '2026-04-18T20:00:00+00:00') == ''
    assert _compute_novita_badge('', '2026-04-18T20:00:00+00:00') == ''


def test_resolve_novita_badge_prefers_latest_uploaded_files_only():
    recent_files = {'fattura_nuova.xml'}
    assert _resolve_novita_badge('fattura_nuova.xml', '2026-04-10T10:00:00+00:00', '2026-04-18T20:00:00+00:00', recent_files) == '🆕 Nuova'
    assert _resolve_novita_badge('fattura_vecchia.xml', '2026-04-19T10:00:00+00:00', '2026-04-18T20:00:00+00:00', recent_files) == ''


def test_resolve_novita_badge_falls_back_to_login_when_no_recent_files():
    assert _resolve_novita_badge('fattura.xml', '2026-04-19T10:00:00+00:00', '2026-04-18T20:00:00+00:00', set()) == '🆕 Nuova'


def test_resolve_novita_badge_matches_invoicetronic_files_even_with_p7m_suffix():
    recent_files = {'fattura_123.xml.p7m'}
    assert _resolve_novita_badge('fattura_123.xml', '2026-04-10T10:00:00+00:00', '2026-04-18T20:00:00+00:00', recent_files) == '🆕 Nuova'


def test_sort_detail_rows_prefers_created_at_desc_and_fallbacks_to_data_documento():
    df = pd.DataFrame([
        {'Descrizione': 'B', 'CreatedAt': '2026-04-19T09:00:00+00:00', 'DataDocumento': '2026-04-10'},
        {'Descrizione': 'A', 'CreatedAt': '2026-04-19T12:00:00+00:00', 'DataDocumento': '2026-04-01'},
        {'Descrizione': 'C', 'CreatedAt': None, 'DataDocumento': '2026-04-18'},
    ])

    sorted_df = _sort_detail_rows(df)
    assert sorted_df['Descrizione'].tolist() == ['A', 'B', 'C']

    df_no_created = pd.DataFrame([
        {'Descrizione': 'Vecchia', 'DataDocumento': '2026-04-01'},
        {'Descrizione': 'Nuova', 'DataDocumento': '2026-04-18'},
    ])
    sorted_fallback = _sort_detail_rows(df_no_created)
    assert sorted_fallback['Descrizione'].tolist() == ['Nuova', 'Vecchia']
