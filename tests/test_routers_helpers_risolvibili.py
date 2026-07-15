"""Guardia: gli helper condivisi DEVONO essere risolvibili come nomi globali
dentro le funzioni dei router (no NameError a runtime).

Contesto (incidente 08/06/2026, secondo round): per rompere il ciclo
router<->fastapi_worker, i router erano passati da un import esplicito
`from services.fastapi_worker import (_resolve_user_from_token, ...)` a un
module-level `__getattr__` (PEP 562). Ma PEP 562 risolve SOLO gli accessi-
attributo ESTERNI (`modulo.simbolo`), MAI i lookup di nome globale "nudi" dentro
le funzioni del modulo stesso. Risultato: ogni endpoint che usava
`_resolve_user_from_token(...)` o `_get_supabase_client()` esplodeva con
NameError -> HTTP 500. L'intera app cliente (fatture, margini, prezzi,
scadenziario, cestino, tag, workspace, account, admin) serviva 500.

Il test anti-ciclo (test_routers_no_circular_import.py) restava VERDE col bug,
perche' verifica solo l'importabilita', non l'esecuzione. Questo test colma il
buco: verifica che ogni nome globale libero usato nelle funzioni dei router sia
effettivamente risolvibile (definito nel modulo o nei builtins) una volta che
fastapi_worker e' caricato. Se qualcuno reintroduce il pattern __getattr__ per
gli helper, questo test fallisce.
"""
import ast
import builtins
import importlib
from pathlib import Path

import pytest

# Caricare il worker rende disponibili i moduli; i wrapper nei router restano
# comunque definiti localmente (e' quello che il test verifica).
import services.fastapi_worker  # noqa: F401

_ROUTERS = [
    "account",
    "admin",
    "cestino",
    "fatture",
    "margini",
    "prezzi",
    "ricavi",
    "riparto",
    "scadenziario",
    "tag",
    "workspace",
]

_ROUTERS_DIR = Path(__file__).resolve().parents[1] / "services" / "routers"
_BUILTINS = set(dir(builtins))


def _module_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
                elif isinstance(tgt, ast.Tuple):
                    for el in tgt.elts:
                        if isinstance(el, ast.Name):
                            names.add(el.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _locally_bound(fn: ast.AST) -> set[str]:
    """Nomi legati localmente in una funzione: parametri, assegnazioni (anche
    tuple-unpacking), import, for/with/comprehension targets, def annidate."""
    bound: set[str] = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = fn.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            bound.add(arg.arg)
        if a.vararg:
            bound.add(a.vararg.arg)
        if a.kwarg:
            bound.add(a.kwarg.arg)

    def add_target(t: ast.AST) -> None:
        if isinstance(t, ast.Name):
            bound.add(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for el in t.elts:
                add_target(el)
        elif isinstance(t, ast.Starred):
            add_target(t.value)

    for node in ast.walk(fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                add_target(tgt)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
            if isinstance(getattr(node, "target", None), ast.Name):
                bound.add(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add_target(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    add_target(item.optional_vars)
        elif isinstance(node, (ast.comprehension,)):
            add_target(node.target)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound


@pytest.mark.parametrize("router_name", _ROUTERS)
def test_router_nessun_nome_globale_irrisolto(router_name: str) -> None:
    """Ogni nome globale libero usato nelle funzioni del router deve essere
    risolvibile a livello modulo (o builtin). Un helper preso dal worker via
    __getattr__ NON e' un nome globale del modulo -> NameError a runtime."""
    path = _ROUTERS_DIR / f"{router_name}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mod_names = _module_level_names(tree)

    irrisolti: set[tuple[str, str, int]] = set()

    def visita(fn: ast.AST, ereditati: set[str]) -> None:
        # Binding visibili in questa funzione = quelli legati qui + quelli degli
        # scope contenitori (closure): _parse_date usa un _dt importato dal genitore.
        local = ereditati | _locally_bound(fn)
        for node in ast.iter_child_nodes(fn):
            _scandisci(fn, node, local)

    def _scandisci(fn: ast.AST, node: ast.AST, local: set[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visita(node, local)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
            if name not in local and name not in mod_names and name not in _BUILTINS:
                if name.startswith("_") or name.isupper() or name in (
                    "logger",
                    "get_supabase_client",
                    "get_articoli_da_fatture",
                ):
                    irrisolti.add((getattr(fn, "name", "<mod>"), name, node.lineno))
        for child in ast.iter_child_nodes(node):
            _scandisci(fn, child, local)

    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visita(top, set())

    assert not irrisolti, (
        f"{router_name}.py usa nomi globali NON risolvibili (NameError a runtime): "
        + ", ".join(f"{n} in {f}() L{ln}" for f, n, ln in sorted(irrisolti))
        + ". Definisci un wrapper esplicito nel modulo (pattern ricavi.py), "
        "NON affidarti a __getattr__ (PEP 562 non risolve i global lookup interni)."
    )


def test_nessun_router_usa_getattr_per_gli_helper() -> None:
    """Nessun router deve risolvere gli helper via module-level __getattr__:
    e' il pattern che ha causato i 500. I wrapper espliciti sono l'unico modo."""
    colpevoli = []
    for router_name in _ROUTERS:
        src = (_ROUTERS_DIR / f"{router_name}.py").read_text(encoding="utf-8")
        if "def __getattr__" in src:
            colpevoli.append(router_name)
    assert not colpevoli, (
        "Questi router usano ancora `def __getattr__` per risolvere gli helper "
        f"(causa dei 500): {colpevoli}. Sostituire con wrapper espliciti."
    )
