"""Test _righe_quote_gruppo (services.fastapi_worker).

Helper condiviso da tab Analisi margini (1° Margine per centro) e finestra
catena "Spesa per PV": entrambi leggevano i costi da `fatture` filtrando su
ristorante_id, ma le fatture di struttura di una catena vivono sulla SEDE
TECNICA (ripartita_su_gruppo=True) — una query per singolo PV non le vede mai.
Il costo di gruppo compariva nel tab Calcolo (che legge margini_mensili.
quote_riparto_*) ma spariva da queste due superfici: due tab della stessa
pagina mostravano un 1° Margine diverso per lo stesso periodo.

Regole verificate:
- PV senza quote (mono-sede, es. CASATI) -> lista vuota, nessuna chiamata extra;
- PV di catena -> le righe proiettate della sua quota vengono restituite;
- righe proiettate con categoria 'Da Classificare' sono escluse, come le query
  sulle righe reali (regola di dominio 1, CLAUDE.md): altrimenti una quota non
  classificata entrerebbe nei totali da una porta di servizio che i tab normali
  non hanno.
"""
from unittest.mock import patch

import services.fastapi_worker as fw


def test_pv_senza_quote_ritorna_vuoto():
    with patch.object(fw, "_ristorante_quote_meta", return_value=(None, False)):
        assert fw._righe_quote_gruppo(sb=None, ristorante_id="rid-mono", data_da="2026-01-01", data_a="2026-01-31") == []


def test_pv_di_catena_ritorna_le_righe_proiettate():
    righe = [
        {"categoria": "CARNE", "totale_riga": 100.0, "fornitore": "METRO"},
        {"categoria": "VERDURE", "totale_riga": 50.0, "fornitore": "METRO"},
    ]
    with patch.object(fw, "_ristorante_quote_meta", return_value=("uid-1", True)), \
         patch("services.riparto_service.righe_ripartite_proiettate", return_value=righe):
        out = fw._righe_quote_gruppo(sb=None, ristorante_id="rid-catena", data_da="2026-07-01", data_a="2026-07-31")
    assert out == righe


def test_esclude_le_righe_da_classificare():
    righe = [
        {"categoria": "CARNE", "totale_riga": 100.0},
        {"categoria": "Da Classificare", "totale_riga": 9999.0},
    ]
    with patch.object(fw, "_ristorante_quote_meta", return_value=("uid-1", True)), \
         patch("services.riparto_service.righe_ripartite_proiettate", return_value=righe):
        out = fw._righe_quote_gruppo(sb=None, ristorante_id="rid-catena", data_da="2026-07-01", data_a="2026-07-31")
    assert out == [{"categoria": "CARNE", "totale_riga": 100.0}]
    assert sum(r["totale_riga"] for r in out) == 100.0


def test_proiezione_fallita_non_rompe_il_chiamante():
    with patch.object(fw, "_ristorante_quote_meta", return_value=("uid-1", True)), \
         patch("services.riparto_service.righe_ripartite_proiettate", side_effect=RuntimeError("boom")):
        assert fw._righe_quote_gruppo(sb=None, ristorante_id="rid-catena", data_da="2026-07-01", data_a="2026-07-31") == []
