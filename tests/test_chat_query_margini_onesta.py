"""Lo strumento query_margini della chat dice la verita' su cio' che passa al modello.

Perche' esiste
==============
Audit di ottobre 2026 sul filone chat:

- K19: un errore di lettura dei margini diventava `{"mesi": []}`, la stessa
  risposta di una sede senza margini. Il modello diceva «non hai dati» durante
  un guasto, e il guasto non lasciava nemmeno una riga di log.
- K05: il modello riceveva il solo fatturato IVA inclusa e soglie «÷ fatturato»,
  e divideva da solo sul lordo: le fasce di MOL e personale cambiavano rispetto
  alla pagina Margini, che divide per il netto.
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


# ── K05: le percentuali sono sul netto, come la pagina Margini ─────────────
#
# Settembre: 50.000 € al 10% e 5.000 € al 22% (netto 49.552,91), merce 14.000,
# personale 15.000, spese 9.000. La pagina Margini (routers/margini.py, `*_perc`
# su netto) dice personale 30,27% «elevato»; sul lordo sarebbe 27,27% «norma».
# Le cifre attese sono scritte a mano, non ricalcolate con la stessa formula.

SETTEMBRE = {9: {"fatturato_iva10": 50000.0, "fatturato_iva22": 5000.0,
                 "costo_dipendenti": 15000.0, "altri_costi_spese": 9000.0}}
FB = {9: 14000.0}
ATTESE = {"personale_pct": 30.3, "spese_pct": 18.2, "mol_pct": 23.3}


def _fonti():
    return (MagicMock(side_effect=lambda _u, _r, a: SETTEMBRE if a == 2026 else {}),
            MagicMock(side_effect=lambda _u, _r, a: (FB, {}) if a == 2026 else ({}, {})))


def test_query_margini_da_netto_e_percentuali_sul_netto():
    carica, costi = _fonti()
    mese = {r["mese"]: r for r in _query(carica, costi)["mesi"]}["settembre 2026"]
    assert mese["fatturato"] == 55000.0
    assert mese["fatturato_netto"] == 49552.91
    assert {k: mese[k] for k in ATTESE} == ATTESE


def test_senza_netto_nessuna_percentuale():
    assert fw._pct_su_netto({"netto": 0, "costo_personale": 10.0, "spese_generali": 1.0, "mol": -11.0}) == {
        "personale_pct": None, "spese_pct": None, "mol_pct": None}


def test_home_kpi_porta_netto_e_percentuali_al_prompt():
    carica, costi = _fonti()
    fw._HOME_KPI_CACHE.clear()
    try:
        with patch.multiple("services.margine_service", carica_margini_anno=carica,
                            calcola_costi_automatici_per_anno_sql=costi), \
             patch.object(fw, "_resolve_user_from_token", return_value={"id": UID}), \
             patch.object(fw, "_get_supabase_client", return_value=_sb_vuoto()), \
             patch.object(fw, "_resolve_ristorante_id", return_value=RID), \
             patch.object(fw, "_oggi_rome", return_value=date(2026, 10, 8)):
            kpi = fw.home_kpi(authorization="Bearer t")
    finally:
        fw._HOME_KPI_CACHE.clear()
    assert kpi.periodo_label == "Settembre"
    assert kpi.netto == 49552.91
    assert {k: getattr(kpi, k) for k in ATTESE} == ATTESE


@pytest.mark.parametrize("v,atteso", [(30.3, " (30,3% del netto)"), (None, ""), (True, ""), ("x", "")])
def test_percentuale_nel_prompt(v, atteso):
    assert fw._pct_testo(v) == atteso
