"""Lo strumento query_margini della chat dice la verita' su cio' che passa al modello.

Perche' esiste
==============
Audit di ottobre 2026 sul filone chat:

- K19: un errore di lettura dei margini diventava `{"mesi": []}`, la stessa
  risposta di una sede senza margini. Il modello diceva «non hai dati» durante
  un guasto, e il guasto non lasciava nemmeno una riga di log.
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw

UID, RID = "u-qm", "r-qm"


def _sb_vuoto():
    q = MagicMock()
    q.table.return_value = q
    for m in ("select", "eq", "in_", "limit", "lt", "gte", "lte", "order", "is_", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


def _query(carica, costi, oggi=date(2026, 10, 8)):
    with patch.multiple("services.margine_service", carica_margini_anno=carica,
                        calcola_costi_automatici_per_anno_sql=costi), \
         patch.object(fw, "_oggi_rome", return_value=oggi):
        return fw._chat_query_margini({"id": UID}, _sb_vuoto(), None, ristorante_id=RID)


# ── K19: guasto ≠ nessun dato ──────────────────────────────────────────────


@pytest.mark.parametrize("chi_si_rompe", ["margini", "costi"])
def test_un_guasto_di_lettura_e_un_errore_non_una_lista_vuota(chi_si_rompe, caplog):
    rotto = MagicMock(side_effect=RuntimeError("timeout supabase"))
    carica = rotto if chi_si_rompe == "margini" else MagicMock(return_value={})
    costi = rotto if chi_si_rompe == "costi" else MagicMock(return_value=({}, {}))
    with caplog.at_level("WARNING"):
        out = _query(carica, costi)
    assert "mesi" not in out
    assert "non dire che non c'e'" in out["errore"]
    assert "timeout supabase" in caplog.text


def test_il_guasto_sull_anno_prima_non_si_maschera_coi_mesi_letti():
    """A febbraio i sei mesi attraversano l'anno: un 2025 illeggibile non deve
    lasciar passare il 2026 come se il 2025 fosse vuoto."""
    carica = MagicMock(side_effect=lambda _u, _r, a: {1: {"altri_ricavi_noiva": 1000.0}}
                       if a == 2026 else (_ for _ in ()).throw(RuntimeError("giu'")))
    out = _query(carica, MagicMock(return_value=({}, {})), oggi=date(2026, 2, 10))
    assert "errore" in out and "mesi" not in out


def test_una_sede_senza_margini_resta_una_lista_vuota():
    out = _query(MagicMock(return_value={}), MagicMock(return_value=({}, {})))
    assert out == {"mesi": []}
