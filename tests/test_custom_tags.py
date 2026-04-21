"""
Test mirati per custom tag e helper puri di Analisi Personalizzata.

Nota: pages/4_analisi_personalizzata.py contiene molto runtime Streamlit
eseguito a top-level. Per testare le funzioni pure senza eseguire la UI,
estraiamo via AST solo le funzioni necessarie.
"""
import ast
from pathlib import Path

import pandas as pd
import pytest

from config.constants import ORPHAN_CHECK_DAYS
from services.db_service import _normalize_custom_tag_key


PAGE_FILE = Path(__file__).resolve().parents[1] / "pages" / "4_analisi_personalizzata.py"


def _load_page_functions(*function_names):
    """Estrae funzioni pure dal file pagina senza importare il modulo Streamlit."""
    source = PAGE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PAGE_FILE))

    wanted = set(function_names)
    selected_nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]

    found = {node.name for node in selected_nodes}
    missing = wanted - found
    if missing:
        raise AssertionError(f"Funzioni non trovate in {PAGE_FILE.name}: {sorted(missing)}")

    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {
        "pd": pd,
        "ORPHAN_CHECK_DAYS": ORPHAN_CHECK_DAYS,
        "_normalize_custom_tag_key": _normalize_custom_tag_key,
    }
    exec(compile(module, str(PAGE_FILE), "exec"), namespace)
    return [namespace[name] for name in function_names]


_compute_kpi, _compute_orfani, _build_usage_notice = _load_page_functions(
    "_compute_kpi",
    "_compute_orfani",
    "_build_usage_notice",
)


class TestNormalizeCustomTagKey:
    """Test edge-case per la normalizzazione chiave tag."""

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            ("  pane   carasau  ", "PANE CARASAU"),
            ("AcQuA   FrizzAnte", "ACQUA FRIZZANTE"),
            ("", ""),
        ],
    )
    def test_normalize_custom_tag_key(self, raw_value, expected):
        assert _normalize_custom_tag_key(raw_value) == expected


class TestComputeKpi:
    """Verifica KPI su dataset minimale, con e senza righe convertibili."""

    def test_compute_kpi_con_record_convertibili(self):
        df = pd.DataFrame(
            [
                {
                    "TotaleRigaNum": 20.0,
                    "QuantitaNorm": 2.0,
                    "UnitaNorm": "KG",
                    "Fornitore": "FORNITORE A",
                    "FileOrigine": "fattura_001.xml",
                },
                {
                    "TotaleRigaNum": 12.0,
                    "QuantitaNorm": 1.0,
                    "UnitaNorm": "KG",
                    "Fornitore": "FORNITORE B",
                    "FileOrigine": "fattura_002.xml",
                },
            ]
        )

        result = _compute_kpi(df)

        assert result["spesa_totale"] == pytest.approx(32.0)
        assert result["quantita_norm_totale"] == pytest.approx(3.0)
        assert result["prezzo_medio_ponderato"] == pytest.approx(32.0 / 3.0)
        assert result["num_fornitori"] == 2
        assert result["num_fatture"] == 2
        assert result["quantita_label"] == "⚖️ Quantità Totale KG"
        assert result["prezzo_label"] == "💶 Prezzo Medio €/KG"

    def test_compute_kpi_senza_record_convertibili(self):
        df = pd.DataFrame(
            [
                {
                    "TotaleRigaNum": 15.0,
                    "QuantitaNorm": None,
                    "UnitaNorm": None,
                    "Fornitore": "FORNITORE A",
                    "FileOrigine": "fattura_001.xml",
                }
            ]
        )

        result = _compute_kpi(df)

        assert result["spesa_totale"] == pytest.approx(15.0)
        assert result["quantita_norm_totale"] == pytest.approx(0.0)
        assert result["prezzo_medio_ponderato"] is None
        assert result["num_fornitori"] == 1
        assert result["num_fatture"] == 1
        assert result["quantita_label"] == "⚖️ Quantità Normalizzata"
        assert result["prezzo_label"] == "💶 Prezzo Medio €/unità norm."


class TestBuildUsageNotice:
    def test_notice_non_selezionata_e_solo_informativa(self):
        level, text = _build_usage_notice(["Salmone Fresco", "Salmone Fresco", "Pesce Premium"], False)

        assert level == "info"
        assert "Già presente in altri tag" in text
        assert "Salmone Fresco" in text
        assert "Pesce Premium" in text

    def test_notice_selezionata_diventa_warning(self):
        level, text = _build_usage_notice(["Salmone Fresco"], True)

        assert level == "warning"
        assert "Se salvi questo tag" in text
        assert "Salmone Fresco" in text


class TestComputeOrfani:
    """Verifica associazioni presenti e assenti nelle fatture recenti."""

    def test_compute_orfani_associazione_presente_nelle_fatture_recenti(self):
        data_recente = (pd.Timestamp.now().normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df_all = pd.DataFrame(
            [
                {
                    "DataDocumento": data_recente,
                    "Descrizione": "  Pane   Bianco  ",
                }
            ]
        )
        associazioni_tag = [
            {
                "id": 1,
                "descrizione": "Pane Bianco",
                "descrizione_key": _normalize_custom_tag_key("Pane Bianco"),
            }
        ]

        result = _compute_orfani(df_all, associazioni_tag)

        assert result == []

    def test_compute_orfani_associazione_assente_nelle_fatture_recenti(self):
        data_vecchia = (
            pd.Timestamp.now().normalize() - pd.Timedelta(days=ORPHAN_CHECK_DAYS + 5)
        ).strftime("%Y-%m-%d")
        data_recente = (pd.Timestamp.now().normalize() - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        df_all = pd.DataFrame(
            [
                {
                    "DataDocumento": data_vecchia,
                    "Descrizione": "Latte Intero",
                },
                {
                    "DataDocumento": data_recente,
                    "Descrizione": "Acqua Naturale",
                },
            ]
        )
        associazioni_tag = [
            {
                "id": 7,
                "descrizione": "Latte Intero",
                "descrizione_key": _normalize_custom_tag_key("Latte Intero"),
            }
        ]

        result = _compute_orfani(df_all, associazioni_tag)

        assert len(result) == 1
        assert result[0]["id"] == 7
        assert result[0]["descrizione_key"] == "LATTE INTERO"