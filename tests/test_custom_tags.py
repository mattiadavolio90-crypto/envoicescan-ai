"""Test per custom tag e KPI di Analisi Personalizzata.

Storia: questi test estraevano le funzioni via AST da
`pages/4_analisi_personalizzata.py`, perche' la pagina Streamlit eseguiva
runtime a top-level e non era importabile. Rimosso il frontend Streamlit il
17/7/2026, puntano direttamente al codice vivo:
`_normalize_custom_tag_key` (db_service) e `_compute_kpi` (tag_analytics_service)
sono gli stessi che servono i clienti su Next.js.

`_compute_orfani` e `_build_usage_notice` esistevano SOLO nella pagina Streamlit
(logica di presentazione): i loro test sono stati rimossi insieme al codice.
"""
import pandas as pd
import pytest

from services.db_service import _normalize_custom_tag_key
from services.tag_analytics_service import _compute_kpi


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
        # La versione viva arrotonda a 4 decimali (tag_analytics_service:146);
        # quella Streamlit restituiva il float grezzo.
        assert result["prezzo_medio_ponderato"] == pytest.approx(32.0 / 3.0, abs=1e-4)
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
