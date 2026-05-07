import ast
from pathlib import Path


PAGE_FILE = Path(__file__).resolve().parents[1] / 'components' / 'category_editor.py'


def _extract_update_dicts(tree: ast.AST):
    """Ritorna i dict passati a .update(...) nel category editor."""
    dict_nodes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == 'update' and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Dict):
                dict_nodes.append(first_arg)
    return dict_nodes


def _dict_to_constant_map(dict_node: ast.Dict) -> dict[str, object]:
    mapped = {}
    for key_node, value_node in zip(dict_node.keys, dict_node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        key = key_node.value
        if isinstance(value_node, ast.Constant):
            mapped[key] = value_node.value
        else:
            mapped[key] = None
    return mapped


def test_manual_category_save_always_clears_needs_review():
    """Ogni update categoria nel dettaglio articoli deve azzerare needs_review."""
    source = PAGE_FILE.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(PAGE_FILE))

    update_dicts = _extract_update_dicts(tree)
    categoria_updates = []
    for dict_node in update_dicts:
        mapped = _dict_to_constant_map(dict_node)
        if 'categoria' in mapped:
            categoria_updates.append(mapped)

    assert categoria_updates, 'Nessun update con chiave categoria trovato in category_editor.py'

    missing_flag = [d for d in categoria_updates if d.get('needs_review') is not False]
    assert not missing_flag, (
        'Tutti gli update categoria devono includere needs_review=False '
        'per rimuovere ALERT dopo revisione manuale cliente'
    )
