"""Guardia anti-regressione: costi_automatici_mensili[_gruppo] (RPC SQL) devono
classificare FOOD con la stessa regola catch-all del fallback pandas
(services.margine_service.calcola_costi_automatici_per_anno).

Contesto (audit Bug margini.py, 2026-08-05, MEDIUM #2): la RPC era nata
catch-all il 18/6 (20260618120000_rpc_costi_food_catchall.sql), ma la
migration del 14/7 (20260714150000_riparto_anti_doppio_conteggio.sql), che ha
aggiunto il filtro anti-doppio-conteggio via CREATE OR REPLACE, ha
silenziosamente riportato la whitelist chiusa `categoria = ANY(p_cat_food)`.
Nessun test se ne accorse: i test esistenti mockano sempre l'helper SQL,
nessuno chiama la RPC vera. Questo file non richiede una connessione DB live:
verifica (1) che l'ultima migration che tocca queste due funzioni non
contenga piu' la whitelist `categoria = ANY(p_cat_food)`, e (2) che la stessa
regola catch-all sia matematicamente equivalente al fallback pandas per ogni
categoria oggi esistente in config/constants.py.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from config.constants import CATEGORIE_FOOD_BEVERAGE, CATEGORIE_SPESE_GENERALI

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def _ultima_definizione_sql(function_name: str) -> str:
    """Concatena tutte le migration che contengono un CREATE OR REPLACE per
    function_name, in ordine di timestamp (nome file). L'ultima occorrenza nel
    testo concatenato e' quella effettivamente applicata al DB (CREATE OR
    REPLACE successivi sovrascrivono i precedenti)."""
    pattern = re.compile(
        rf"CREATE OR REPLACE FUNCTION {function_name}\(.*?\$\$;",
        re.DOTALL,
    )
    trovate = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        testo = f.read_text(encoding="utf-8")
        for m in pattern.finditer(testo):
            trovate.append((f.name, m.group(0)))
    assert trovate, f"Nessuna migration definisce {function_name}"
    return trovate[-1][1]


@pytest.mark.parametrize(
    "function_name", ["costi_automatici_mensili", "costi_automatici_mensili_gruppo"]
)
def test_rpc_non_usa_whitelist_chiusa_su_food(function_name):
    """La definizione applicata per ultima non deve filtrare FOOD con
    `categoria = ANY(p_cat_food)`: e' la whitelist chiusa che ha causato il
    MEDIUM #2 (una categoria fuori lista spariva dal MOL)."""
    sql = _ultima_definizione_sql(function_name)
    assert "categoria = ANY(p_cat_food)" not in sql, (
        f"{function_name}: la whitelist chiusa su p_cat_food e' tornata — "
        "stessa regressione gia' avvenuta il 14/7. FOOD deve restare catch-all "
        "(tutto tranne p_cat_spese e NOTE E DICITURE)."
    )
    assert "p_cat_spese" in sql


def _classifica_catchall_python(categoria: str) -> str:
    """Replica in Python la regola SQL catch-all: food = tutto tranne
    Spese Generali e NOTE E DICITURE."""
    if categoria in CATEGORIE_SPESE_GENERALI:
        return "spese"
    if categoria == "📝 NOTE E DICITURE":
        return "nessuno"
    return "food"


def test_ogni_categoria_food_beverage_classificata_come_food():
    for cat in CATEGORIE_FOOD_BEVERAGE:
        assert _classifica_catchall_python(cat) == "food", cat


def test_ogni_categoria_spese_generali_classificata_come_spese():
    for cat in CATEGORIE_SPESE_GENERALI:
        assert _classifica_catchall_python(cat) == "spese", cat


def test_categoria_legacy_fuori_whitelist_non_sparisce_dal_mol():
    """Il caso concreto del MEDIUM #2: una categoria come 'SUSHI VARIE' o una
    legacy non ancora normalizzata (es. 'VERDURE MISTE') deve comunque entrare
    nel food catch-all, non sparire silenziosamente come faceva la whitelist."""
    for cat in ["SUSHI VARIE", "CATEGORIA_LEGACY_MAI_VISTA_PRIMA"]:
        assert _classifica_catchall_python(cat) == "food", cat


def test_equivalenza_catchall_python_vs_fallback_pandas():
    """Il fallback pandas (calcola_costi_automatici_per_anno) usa la stessa
    regola: df_fb = tutto tranne CATEGORIE_SPESE_GENERALI e NOTE E DICITURE."""
    righe = [
        {"categoria": c, "totale_riga": 10.0} for c in CATEGORIE_FOOD_BEVERAGE
    ] + [
        {"categoria": c, "totale_riga": 5.0} for c in CATEGORIE_SPESE_GENERALI
    ] + [
        {"categoria": "📝 NOTE E DICITURE", "totale_riga": 0.0},
        {"categoria": "CATEGORIA_LEGACY_MAI_VISTA_PRIMA", "totale_riga": 7.0},
    ]
    df = pd.DataFrame(righe)
    df_spese = df[df["categoria"].isin(CATEGORIE_SPESE_GENERALI)]
    df_fb = df[
        ~df["categoria"].isin(CATEGORIE_SPESE_GENERALI)
        & (df["categoria"] != "📝 NOTE E DICITURE")
    ]

    totale_fb_pandas = df_fb["totale_riga"].sum()
    totale_spese_pandas = df_spese["totale_riga"].sum()

    totale_fb_regola = sum(
        r["totale_riga"] for r in righe
        if _classifica_catchall_python(r["categoria"]) == "food"
    )
    totale_spese_regola = sum(
        r["totale_riga"] for r in righe
        if _classifica_catchall_python(r["categoria"]) == "spese"
    )

    assert totale_fb_pandas == totale_fb_regola
    assert totale_spese_pandas == totale_spese_regola
    # CATEGORIA_LEGACY_MAI_VISTA_PRIMA (7.0) deve finire in food, non sparire
    assert totale_fb_regola == sum(10.0 for _ in CATEGORIE_FOOD_BEVERAGE) + 7.0
