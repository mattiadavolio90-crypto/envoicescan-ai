"""Le due card della Home (conti e completezza), PV e catena — step 3, 28/9/2026.

Mattia: «completezza dati e conti sia in catena che in punto vendita
esteticamente non sono coerenti con il resto dell'app e sono enormi». Le quattro
card avevano gradiente, aloni sfocati, un MOL a 48-60 px e un anello da 128 px.
Ora usano i pezzi comuni di `components/home/card-home.tsx`, sul modello delle
tessere di Margini.

Il rendering non si esegue (nessun runner npm): questi test guardano che le
quattro card passino dai pezzi comuni e che il vecchio disegno non torni. La
logica che decide (colore del MOL, voci da aprire) sta in lib/ ed e' eseguita
altrove (`test_home_kpi_frontend.py`, `test_catena_confronti_frontend.py`).
"""
import re
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parent.parent / "apps/web/src"
_PEZZI = _WEB / "components/home/card-home.tsx"
_PV_CONTI = _WEB / "app/(app)/dashboard/kpi-block.tsx"
_PV_SALUTE = _WEB / "app/(app)/dashboard/salute-card.tsx"
_CATENA = _WEB / "app/(app)/catena/sintesi-catena.tsx"
_PV_HOME = _WEB / "app/(app)/dashboard/page.tsx"


def _testo(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _senza_commenti(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", t)


@pytest.mark.parametrize("file", [_PEZZI, _PV_CONTI, _PV_SALUTE, _CATENA], ids=lambda p: p.name)
@pytest.mark.parametrize("vecchio", ["bg-gradient", "blur-3xl", "tint.card", "tint.orb", "text-5xl", "text-6xl", "size-28", "size-32"])
def test_il_vecchio_disegno_non_torna(file, vecchio):
    assert vecchio not in _senza_commenti(_testo(file)), (
        f"{file.name} ha di nuovo «{vecchio}»: le card della Home hanno il fondo "
        "neutro e le cifre piccole delle altre pagine (Mattia, 28/9)"
    )


@pytest.mark.parametrize(
    "file,titolo",
    [
        (_PV_CONTI, 'titolo="I tuoi conti"'),
        (_PV_SALUTE, 'titolo="Completezza dati"'),
        (_CATENA, 'titolo="I conti del gruppo"'),
        (_CATENA, 'titolo="Completezza dati e margini per sede"'),
    ],
)
def test_ogni_card_passa_dal_contenitore_comune(file, titolo):
    assert f"<CardHome {titolo}" in _testo(file), (
        f"{file.name}: la card {titolo} non usa piu' CardHome — il PV e la catena "
        "tornerebbero a due disegni diversi"
    )


def test_il_contenitore_comune_e_quello_delle_altre_pagine():
    t = _senza_commenti(_testo(_PEZZI))
    corpo = re.search(r"export function CardHome\(.*?\n\}\n", t, re.S).group(0)
    assert "rounded-xl border border-border bg-card p-4" in corpo


def test_le_due_card_della_completezza_usano_lo_stesso_riepilogo():
    assert "<RiepilogoCompletezza" in _testo(_PV_SALUTE)
    assert "<RiepilogoCompletezza" in _testo(_CATENA)


def test_la_card_del_pv_apre_solo_le_voci_da_sistemare():
    """La decisione sta in `vociCompletezza`; qui si guarda che la card la usi e
    che la lista con dettaglio giri sulle voci da sistemare, non su tutte."""
    t = _senza_commenti(_testo(_PV_SALUTE))
    assert "vociCompletezza(salute.voci)" in t
    assert "daSistemare.map(" in t
    assert "salute.voci.map(" not in t
    assert "aPosto.map(" in t


def test_andamento_scritto_una_volta_sola():
    """Prima c'erano MolAndamento (PV) e MolSparkline (catena), la stessa curva."""
    for f in (_PV_CONTI, _CATENA):
        t = _testo(f)
        assert "<AndamentoMargine" in t
        assert "function MolAndamento" not in t and "function MolSparkline" not in t


def test_nella_home_pv_i_conti_vengono_prima_della_completezza():
    """Stesso ordine della Home di catena: conti a sinistra, completezza a destra."""
    t = _senza_commenti(_testo(_PV_HOME))
    assert t.index("<KpiBlock ") < t.index("<SaluteCard ")
    c = _senza_commenti(_testo(_CATENA))
    assert c.index("<ContiGruppoCard") < c.index("<SaluteGruppoCard")


# ─── I collegamenti che decidono, riscritti in questo step ───────────────────
#
# Le regole stanno in lib/ e sono eseguite altrove; qui il punto e' che i .tsx
# riscritti le passino ancora nel verso giusto. Segnalato dal revisore il 28/9:
# invertire uno di questi collegamenti lasciava verde tutta la suite.


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", _senza_commenti(t))


def test_il_trend_del_mol_non_e_mai_verde_se_in_perdita_o_con_costi_mancanti():
    assert "neutro={!molPos||!molAttendibile}" in _norm(_testo(_PV_CONTI))
    assert "constmolAttendibile=!kpi.costi_mancanti;" in _norm(_testo(_PV_CONTI))


def test_l_andamento_del_pv_segue_l_attendibilita_del_mol():
    assert "<AndamentoMarginepunti={kpi.mol_mensile}anno={kpi.mol_mensile_anno}affidabile={molAttendibile}/>" in _norm(_testo(_PV_CONTI))


def test_in_catena_personale_e_spese_solo_con_dati_affidabili():
    n = _norm(_testo(_CATENA))
    assert 'constaffidabile=metrica.stato==="mol"&&metrica.affidabile;' in n
    i = n.index("{affidabile&&(<><TesseraVocelabel=\"Costopersonale\"")
    assert 'label="Spesegenerali"' in n[i:i + 400]
    assert "<AndamentoMarginepunti={overview.mol_mensile}anno={overview.mol_mensile_anno}affidabile={affidabile}/>" in n


def test_in_catena_il_margine_percentuale_solo_con_dati_affidabili():
    assert '{affidabile&&<spanclassName="tabular-nums">margine{pct(kpi.margine_medio_perc)}</span>}' in _norm(_testo(_CATENA))
