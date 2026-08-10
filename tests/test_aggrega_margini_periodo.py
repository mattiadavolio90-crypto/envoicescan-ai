"""Test audit §3 — `_aggrega_mensili_margini` / `_aggrega_totali_margini`
(`services/fastapi_worker.py`, 10/8/2026).

Qui si CHIUDE il conto economico: ricavi (o override mensile) meno costi
automatici, meno costi manuali, meno personale = MOL. E' il numero su cui il
cliente decide, e prima di questa passata nessun test lo eseguiva.

`tests/test_kpi_periodo_quote_riparto.py:50-60` sembra coprirlo ma non lo fa:
RISCRIVE la formula a mano nel test ("stessa identica somma di
_aggrega_mensili_margini", dice il commento) invece di chiamare l'helper. Se la
formula vera cambia, quel test resta verde. Qui la formula attesa e' calcolata a
mano su numeri scelti, mai ri-derivata dal codice sotto test.

Le due funzioni sono CLONI a meno delle sparkline (righe 7867-7898 vs 7925-7950):
un fix applicato a una sola produrrebbe due MOL diversi nella stessa pagina —
KPI e grafico che si contraddicono. Da qui il test di coerenza, il piu' prezioso
del file.

I costi automatici NON sono stubbati: le righe di `fatture` passano dal fake e
attraversano `_calcola_costi_auto_per_mese` vero. Stubbarlo ridurrebbe questi
test all'aritmetica dei soli campi di `margini_mensili`, cioe' a meta' del loro
valore — l'integrazione fra fatture e conto economico e' proprio il punto.

Nota (D6, osservata non corretta): entrambi chiamano `_calcola_costi_auto_per_mese`
UNA VOLTA PER MESE, 12 scansioni di `fatture` per un anno, mentre
`_calcola_costi_auto_per_periodo` esiste apposta per farne una ed e' gia' usato
da `margini.py:1107` e `ricavi.py:1008`. E' un refactor fuori perimetro, ma il
test di coerenza qui sotto lo renderebbe sicuro: chi lo fara' avra' una rete che
verifica che il totale non cambi.
"""
import os
from datetime import date

import pytest

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import services.fastapi_worker as fw  # noqa: E402

# Fake condiviso col file fratello: e' lo stesso dominio (righe di `fatture` che
# alimentano il MOL) e duplicarlo significherebbe farlo divergere.
from tests.test_costi_auto_fatture_mol import (  # noqa: E402
    CAT_FB, CAT_SPESE, RID, _FakeSB, _fattura,
)

CHIAVI_TOTALI = ("lordo", "netto", "fb", "pm", "spese", "pers", "mol", "mesi_attivi")


def _margini(anno=2026, mese=3, i10=0.0, i22=0.0, altri=0.0, altri_fb=0.0,
             altri_spese=0.0, quote_fb=0.0, quote_spese=0.0, dip=0.0, extra=0.0):
    """Riga di `margini_mensili` con i campi che gli helper leggono."""
    return {
        "ristorante_id": RID, "anno": anno, "mese": mese,
        "fatturato_iva10": i10, "fatturato_iva22": i22, "altri_ricavi_noiva": altri,
        "altri_costi_fb": altri_fb, "altri_costi_spese": altri_spese,
        "quote_riparto_fb": quote_fb, "quote_riparto_spese": quote_spese,
        "costo_dipendenti": dip, "costo_personale_extra": extra,
    }


def _override(anno=2026, mese=3, i10=0.0, i22=0.0, altri=0.0, modalita="mensile", coperti=None):
    return {
        "ristorante_id": RID, "anno": anno, "mese": mese, "modalita": modalita,
        "fatturato_iva10": i10, "fatturato_iva22": i22,
        "altri_ricavi_noiva": altri, "coperti": coperti,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coerenza fra i due cloni — il test piu' importante del file
# ─────────────────────────────────────────────────────────────────────────────

def _scenario_completo():
    """Uno scenario che accende TUTTI i termini della formula, su 3 mesi."""
    fatture = [
        _fattura(CAT_FB, 1000.0, "2026-01-10", competenza=None),
        _fattura(CAT_SPESE, 200.0, "2026-01-11", competenza=None),
        _fattura(CAT_FB, 1500.0, "2026-02-10", competenza=None),
        # competenza a febbraio ma documento a marzo: pesa su FEBBRAIO
        _fattura(CAT_FB, 300.0, "2026-03-02", competenza="2026-02-27"),
        _fattura(CAT_SPESE, 250.0, "2026-03-10", competenza=None),
        # righe che il MOL deve ignorare
        _fattura("Da Classificare", 900.0, "2026-03-11", competenza=None),
        _fattura(CAT_FB, 800.0, "2026-03-12", competenza=None, ripartita=True),
    ]
    margini = [
        _margini(2026, 1, i10=11000.0, i22=2440.0, altri=100.0, dip=3000.0),
        _margini(2026, 2, i10=22000.0, i22=1220.0, altri_fb=500.0, quote_fb=250.0, dip=3500.0),
        _margini(2026, 3, i10=33000.0, i22=3660.0, altri_spese=400.0,
                 quote_spese=150.0, dip=4000.0, extra=600.0),
    ]
    modalita = [_override(2026, 2, i10=25000.0, i22=1220.0, altri=50.0)]
    return fatture, margini, modalita


def test_mensili_e_totali_coincidono_sui_totali():
    """I due helper sono cloni: se divergono, KPI e sparkline della stessa pagina
    raccontano due MOL diversi."""
    fatture, margini, modalita = _scenario_completo()
    d_da, d_a = date(2026, 1, 1), date(2026, 3, 31)

    mens = fw._aggrega_mensili_margini(
        _FakeSB(fatture=fatture, margini=margini, modalita=modalita), RID, d_da, d_a)
    tot = fw._aggrega_totali_margini(
        _FakeSB(fatture=fatture, margini=margini, modalita=modalita), RID, d_da, d_a)

    for k in CHIAVI_TOTALI:
        assert mens[k] == pytest.approx(tot[k]), f"divergenza su '{k}'"


def test_somma_sparkline_uguale_al_totale():
    """Il grafico non puo' raccontare una storia diversa dal KPI accanto."""
    fatture, margini, modalita = _scenario_completo()
    mens = fw._aggrega_mensili_margini(
        _FakeSB(fatture=fatture, margini=margini, modalita=modalita),
        RID, date(2026, 1, 1), date(2026, 3, 31))
    for spark, totale in (("spark_lordo", "lordo"), ("spark_fb", "fb"),
                          ("spark_margine", "pm"), ("spark_spese", "spese"),
                          ("spark_personale", "pers"), ("spark_mol", "mol")):
        assert sum(mens[spark]) == pytest.approx(mens[totale], abs=0.05), spark


# ─────────────────────────────────────────────────────────────────────────────
# La formula, su numeri scelti a mano
# ─────────────────────────────────────────────────────────────────────────────

def test_formula_mol_su_un_mese_noto():
    """Valori attesi calcolati a mano, NON ri-derivati dalla formula sotto test.

    i10 e i22 sono diversi di proposito: con valori uguali uno scambio dei
    divisori 1.10/1.22 non produrrebbe alcuna differenza e il test resterebbe
    verde su un errore reale.
    """
    fatture = [
        _fattura(CAT_FB, 1000.0, "2026-03-10", competenza=None),
        _fattura(CAT_SPESE, 200.0, "2026-03-11", competenza=None),
    ]
    margini = [_margini(2026, 3, i10=11000.0, i22=2440.0, altri=100.0,
                        altri_fb=500.0, altri_spese=300.0,
                        quote_fb=250.0, quote_spese=150.0,
                        dip=3000.0, extra=600.0)]
    tot = fw._aggrega_totali_margini(
        _FakeSB(fatture=fatture, margini=margini), RID, date(2026, 3, 1), date(2026, 3, 31))

    # lordo  = 11000 + 2440 + 100                     = 13540
    # netto  = 11000/1.10 + 2440/1.22 + 100 = 10000 + 2000 + 100 = 12100
    # fb     = 1000 (auto) + 500 (manuale) + 250 (quota)         = 1750
    # spese  = 200 (auto) + 300 (manuale) + 150 (quota)          = 650
    # pers   = 3000 + 600                                        = 3600
    # pm     = 12100 - 1750                                      = 10350
    # mol    = 10350 - 650 - 3600                                = 6100
    assert tot["lordo"] == pytest.approx(13540.0)
    assert tot["netto"] == pytest.approx(12100.0)
    assert tot["fb"] == pytest.approx(1750.0)
    assert tot["spese"] == pytest.approx(650.0)
    assert tot["pers"] == pytest.approx(3600.0)
    assert tot["pm"] == pytest.approx(10350.0)
    assert tot["mol"] == pytest.approx(6100.0)
    assert tot["mesi_attivi"] == 1


def test_costi_auto_reali_entrano_nel_mol():
    """Le fatture attraversano `_calcola_costi_auto_per_mese` VERO (non stubbato):
    e' l'integrazione fra ingresso dati e conto economico."""
    fatture = [
        _fattura(CAT_FB, 700.0, "2026-03-10", competenza=None),
        _fattura(CAT_SPESE, 300.0, "2026-03-11", competenza=None),
        _fattura("Da Classificare", 999.0, "2026-03-12", competenza=None),
    ]
    tot = fw._aggrega_totali_margini(
        _FakeSB(fatture=fatture, margini=[_margini(2026, 3, i10=1100.0)]),
        RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["fb"] == pytest.approx(700.0)
    assert tot["spese"] == pytest.approx(300.0)


def test_quote_riparto_sommate_ai_costi():
    """Catena: le quote di gruppo a carico del PV entrano nei costi, o il tab
    Analisi divergerebbe dal tab Calcolo."""
    margini = [_margini(2026, 3, i10=1100.0, quote_fb=250.0, quote_spese=150.0)]
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=margini), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["fb"] == pytest.approx(250.0)
    assert tot["spese"] == pytest.approx(150.0)


# ─────────────────────────────────────────────────────────────────────────────
# Override mensile
# ─────────────────────────────────────────────────────────────────────────────

def test_override_mensile_vince_su_margini_mensili():
    margini = [_margini(2026, 3, i10=1100.0, i22=1220.0, altri=10.0)]
    modalita = [_override(2026, 3, i10=5500.0, i22=2440.0, altri=60.0)]
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=margini, modalita=modalita), RID, date(2026, 3, 1), date(2026, 3, 31))
    # 5500 + 2440 + 60 = 8000, non 1100 + 1220 + 10
    assert tot["lordo"] == pytest.approx(8000.0)
    assert tot["netto"] == pytest.approx(5500 / 1.10 + 2440 / 1.22 + 60)


def test_override_non_mensile_non_si_applica():
    """`_load_mensile_overrides` filtra `modalita = 'mensile'`: una riga
    'giornaliera' non deve scavalcare `margini_mensili`."""
    margini = [_margini(2026, 3, i10=1100.0)]
    modalita = [_override(2026, 3, i10=9900.0, modalita="giornaliera")]
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=margini, modalita=modalita), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["lordo"] == pytest.approx(1100.0)


def test_override_a_zero_azzera_i_ricavi_del_mese():
    """Un override valorizzato a ZERO vince comunque: il mese e' dichiarato
    'mensile' e vuoto, non 'senza override'. Con un `or` al posto di `if ov` il
    codice ricadrebbe su margini_mensili e mostrerebbe ricavi che il cliente ha
    esplicitamente azzerato."""
    margini = [_margini(2026, 3, i10=5000.0)]
    modalita = [_override(2026, 3, i10=0.0, i22=0.0, altri=0.0)]
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=margini, modalita=modalita), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["lordo"] == pytest.approx(0.0)
    assert tot["mesi_attivi"] == 0


def test_override_su_un_mese_non_tocca_gli_altri():
    margini = [_margini(2026, 2, i10=1100.0), _margini(2026, 3, i10=2200.0)]
    modalita = [_override(2026, 3, i10=9900.0)]
    mens = fw._aggrega_mensili_margini(
        _FakeSB(margini=margini, modalita=modalita), RID, date(2026, 2, 1), date(2026, 3, 31))
    assert mens["spark_lordo"] == [1100.0, 9900.0]


# ─────────────────────────────────────────────────────────────────────────────
# Sparkline e finestra dei mesi
# ─────────────────────────────────────────────────────────────────────────────

def test_sparkline_allineate_ai_mesi_del_periodo():
    """Un mese senza dati vale 0.0 ed E' PRESENTE: se sparisse, il grafico
    slitterebbe e ogni punto verrebbe attribuito al mese sbagliato."""
    margini = [_margini(2026, 1, i10=1100.0), _margini(2026, 3, i10=3300.0)]
    mens = fw._aggrega_mensili_margini(
        _FakeSB(margini=margini), RID, date(2026, 1, 1), date(2026, 4, 30))
    for k in ("spark_lordo", "spark_fb", "spark_margine", "spark_spese",
              "spark_personale", "spark_mol"):
        assert len(mens[k]) == 4, k
    assert mens["spark_lordo"] == [1100.0, 0.0, 3300.0, 0.0]


def test_periodo_a_cavallo_di_anno():
    """Wrap `m > 12`: 2025-11 -> 2026-02 sono 4 mesi su 2 anni.

    Esercitato su ENTRAMBI gli helper: il wrap e' duplicato in tutti e due, e
    testarne uno solo lascerebbe l'altro scoperto proprio sul calcolo dei mesi.
    """
    margini = [
        {**_margini(2025, 11, i10=1100.0), "anno": 2025},
        {**_margini(2025, 12, i10=2200.0), "anno": 2025},
        _margini(2026, 1, i10=3300.0),
        _margini(2026, 2, i10=4400.0),
    ]
    d_da, d_a = date(2025, 11, 1), date(2026, 2, 28)
    mens = fw._aggrega_mensili_margini(_FakeSB(margini=margini), RID, d_da, d_a)
    assert mens["spark_lordo"] == [1100.0, 2200.0, 3300.0, 4400.0]

    tot = fw._aggrega_totali_margini(_FakeSB(margini=margini), RID, d_da, d_a)
    assert tot["lordo"] == pytest.approx(11000.0)
    assert tot["mesi_attivi"] == 4


def test_periodo_di_un_solo_mese():
    margini = [_margini(2026, 3, i10=1100.0)]
    mens = fw._aggrega_mensili_margini(
        _FakeSB(margini=margini), RID, date(2026, 3, 5), date(2026, 3, 20))
    assert len(mens["spark_lordo"]) == 1
    assert mens["lordo"] == pytest.approx(1100.0)


@pytest.mark.parametrize("i10,attesi", [(0.0, 0), (1100.0, 1)])
def test_mesi_attivi_conta_solo_i_mesi_con_netto_positivo(i10, attesi):
    margini = [_margini(2026, 3, i10=i10)]
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=margini), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["mesi_attivi"] == attesi


def test_mese_senza_riga_margini_mensili_non_rompe():
    """Nessuna riga a DB per quel mese: tutti i termini a zero, nessun KeyError."""
    tot = fw._aggrega_totali_margini(
        _FakeSB(), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["lordo"] == 0.0 and tot["mol"] == 0.0 and tot["mesi_attivi"] == 0


def test_solo_i_costi_senza_ricavi_danno_mol_negativo():
    """Caso reale di inizio mese: fatture caricate, incassi non ancora inseriti."""
    fatture = [_fattura(CAT_FB, 500.0, "2026-03-10", competenza=None)]
    tot = fw._aggrega_totali_margini(
        _FakeSB(fatture=fatture), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["fb"] == pytest.approx(500.0)
    assert tot["mol"] == pytest.approx(-500.0)
    assert tot["mesi_attivi"] == 0


def test_filtro_per_ristorante_su_margini_mensili():
    margini = [_margini(2026, 3, i10=1100.0),
               {**_margini(2026, 3, i10=9900.0), "ristorante_id": "rid-altro"}]
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=margini), RID, date(2026, 3, 1), date(2026, 3, 31))
    assert tot["lordo"] == pytest.approx(1100.0)
