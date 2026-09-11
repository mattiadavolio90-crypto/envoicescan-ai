"""Soglie e nomi KPI di un negozio (RETAIL_FASI.md, Fase 4).

Il nome KPI "Food Cost" e i testi delle soglie sono un blocco solo: rinominare
il KPI da solo lascerebbe un negozio a leggere «Costo Merce · Food cost
eccellente», cioe' mezzo testo da ristorante.

Per il retail NIENTE colori in v1 (decisione di Mattia): i benchmark reali vanno
da ~35% a ~78% secondo cosa si vende, e una soglia unica colorerebbe di rosso
clienti sani. Ma «nessun giudizio» non e' «nessun commento»: la riga resta con
l'emoji neutra, perche' il frontend (`coloreDaCommento`, calcolo-tab.tsx) mappa
l'assenza di commento su un gauge NEUTRO — toglierla spegnerebbe il gauge, che
e' una cosa diversa da non colorarlo.
"""
import pytest

from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from services.routers.margini import (
    _KPI_SOGLIE_MARGINI,
    _nome_kpi_per_settore,
    _valuta_soglia_margine,
)


# ── Il KPI merce: nome e giudizio cambiano INSIEME ───────────────────────

def test_negozio_legge_costo_merce_non_food_cost():
    assert _nome_kpi_per_settore("food_cost", "Food Cost", SETTORE_RETAIL) == "Costo Merce"


def test_negozio_non_riceve_un_giudizio_di_soglia_sulla_merce():
    emoji, testo = _valuta_soglia_margine(62.0, "food_cost", True, SETTORE_RETAIL)
    assert emoji == "ℹ️", "un colore su una soglia che per il retail non esiste"
    assert "soglia" in testo and "mesi precedenti" in testo
    assert "eccellente" not in testo and "critico" not in testo


def test_il_giudizio_non_cambia_col_valore_per_un_negozio():
    """Se restasse una soglia nascosta, due valori lontani darebbero esiti diversi."""
    basso = _valuta_soglia_margine(5.0, "food_cost", True, SETTORE_RETAIL)
    alto = _valuta_soglia_margine(95.0, "food_cost", True, SETTORE_RETAIL)
    assert basso == alto


def test_nome_e_giudizio_sono_coerenti_fra_loro():
    """Il difetto che questa casella doveva evitare: mezzo testo da ristorante."""
    nome = _nome_kpi_per_settore("food_cost", "Food Cost", SETTORE_RETAIL)
    _, testo = _valuta_soglia_margine(62.0, "food_cost", True, SETTORE_RETAIL)
    assert "Food cost" not in testo, f"«{nome}» accompagnato da un testo che dice food cost"
    assert "ristorazione" not in testo


# ── Le altre voci restano giudicate anche per un negozio ─────────────────

@pytest.mark.parametrize("key", ["personale", "spese_generali", "mol", "primo_margine"])
def test_le_altre_voci_restano_giudicate(key):
    """Sono incidenze sul fatturato che non dipendono dal tipo di merce: spegnerle
    avrebbe tolto al negozio l'unica valutazione che per lui resta valida."""
    emoji, testo = _valuta_soglia_margine(10.0, key, True, SETTORE_RETAIL)
    assert emoji != "ℹ️"
    assert testo == _valuta_soglia_margine(10.0, key, True, SETTORE_RISTORAZIONE)[1]


@pytest.mark.parametrize("key", ["personale", "spese_generali", "mol", "primo_margine"])
def test_le_altre_voci_non_sono_rinominate(key):
    assert _nome_kpi_per_settore(key, "X", SETTORE_RETAIL) == "X"


# ── Il vincolo: per un ristorante non cambia NIENTE ──────────────────────

@pytest.mark.parametrize("settore", [SETTORE_RISTORAZIONE, None, "", "valore_ignoto"])
@pytest.mark.parametrize("key", list(_KPI_SOGLIE_MARGINI))
@pytest.mark.parametrize("valore", [0.0, 15.0, 27.9, 28.0, 33.0, 50.0, 250.0])
def test_ramo_ristorazione_identico_al_comportamento_di_ieri(settore, key, valore):
    """Il testo di ieri, non una parafrasi — ricalcolato dalla tabella originale
    come la faceva la funzione prima del settore, su tutta la banda dei valori.

    Include None/ignoto: il fail-safe del settore va verso la ristorazione, ed
    e' li' che cade ogni chiamante che non lo passa.
    """
    soglie = _KPI_SOGLIE_MARGINI[key]
    atteso = next(
        ((e, t) for s, e, t in soglie if valore <= s),
        (soglie[-1][1], soglie[-1][2]),
    )
    assert _valuta_soglia_margine(valore, key, True, settore) == atteso


def test_food_cost_resta_food_cost_per_un_ristorante():
    for settore in (SETTORE_RISTORAZIONE, None, "", "valore_ignoto"):
        assert _nome_kpi_per_settore("food_cost", "Food Cost", settore) == "Food Cost"
        emoji, testo = _valuta_soglia_margine(26.5, "food_cost", True, settore)
        assert emoji == "🟢"
        assert testo == "Food cost eccellente — ottimo controllo acquisti e sprechi"


def test_la_firma_senza_settore_e_ancora_ristorazione():
    """I chiamanti che non passano il settore (analisi-avanzata, tab spenta per
    il retail) devono continuare a comportarsi come ieri."""
    assert _valuta_soglia_margine(26.5, "food_cost", crescente=True) == (
        "🟢", "Food cost eccellente — ottimo controllo acquisti e sprechi",
    )


# ── L'ENDPOINT vero, non solo le due funzioni ────────────────────────────
#
# Asserire su `_valuta_soglia_margine` prova la funzione, non che l'endpoint le
# passi il settore. Qui si chiama `get_margini_analisi` e si leggono i commenti
# che arrivano davvero nella response.
from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import services.routers.margini as margini  # noqa: E402


def _commenti_endpoint(settore):
    saved = [{
        "anno": 2026, "mese": 3,
        "fatturato_iva10": 11000.0, "fatturato_iva22": 0.0, "altri_ricavi_noiva": 0.0,
        "altri_costi_fb": 0.0, "altri_costi_spese": 0.0,
        "quote_riparto_fb": 0.0, "quote_riparto_spese": 0.0,
        "costo_dipendenti": 2000.0, "costo_personale_extra": 0.0,
    }]
    q = MagicMock()
    for m in ("select", "eq", "in_", "gte", "lte"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=saved)
    client = MagicMock()
    client.table.return_value = q

    with patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ), patch.object(
        margini, "_calcola_costi_auto_per_periodo",
        MagicMock(return_value={(2026, 3): (6000.0, 0.0)}),
    ), patch.object(
        margini, "_load_mensile_overrides", MagicMock(return_value={})
    ), patch(
        "services.settore_service.settore_utente", MagicMock(return_value=settore)
    ):
        resp = margini.get_margini_analisi("2026-03-01", "2026-03-31", authorization="Bearer x")
    return {c.kpi_nome: c for c in resp.commenti}


def test_endpoint_da_a_un_negozio_costo_merce_senza_colore():
    c = _commenti_endpoint(SETTORE_RETAIL)
    assert "Costo Merce" in c, f"il KPI merce non e' stato rinominato: {list(c)}"
    assert "Food Cost" not in c
    assert c["Costo Merce"].emoji == "ℹ️"
    assert "mesi precedenti" in c["Costo Merce"].commento


def test_endpoint_da_a_un_ristorante_esattamente_quello_di_ieri():
    c = _commenti_endpoint(SETTORE_RISTORAZIONE)
    assert "Food Cost" in c
    assert "Costo Merce" not in c
    assert c["Food Cost"].emoji in ("🟢", "🟡", "🟠", "🔴")
    assert "Food cost" in c["Food Cost"].commento


def test_endpoint_lascia_al_negozio_le_voci_ancora_valide():
    """MOL e Costo del Lavoro restano giudicati: spegnerli avrebbe tolto al
    negozio l'unica valutazione che per lui e' ancora vera."""
    c = _commenti_endpoint(SETTORE_RETAIL)
    assert c["MOL"].emoji != "ℹ️"
    assert c["Costo del Lavoro"].emoji != "ℹ️"
