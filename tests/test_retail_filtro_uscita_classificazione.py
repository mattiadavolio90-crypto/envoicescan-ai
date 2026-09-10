"""Il filtro d'uscita retail in `categorizza_con_memoria` (RETAIL_FASI.md 1.3).

Per un negozio (`settore='retail'`) una categoria food non esiste: qualunque
livello l'abbia proposta (memoria locale, dizionario), la riga torna
"Da Classificare" con `is_fallback=True` e provenienza "nessuna", cosi' il
chiamante la manda all'AI e la marca `needs_review`. I livelli generici
(utenze, note a importo zero, manutenzione) passano invariati.

Due guardie, provate separatamente: il gate nella closure `_ret` (da cui
passano tutti i return) e la guardia sull'auto-save in memoria locale, che
legge `categoria_keyword` e non il ritorno di `_ret`.

Il vincolo dei ristoranti: con `settore=None` (ogni chiamante di oggi) o
'ristorazione' l'output e' letteralmente quello di prima.
"""
from __future__ import annotations

import time

import pytest

import services.ai_service as ai

UTENTE = "u-retail"
LOCALE = {
    "BISTECCA DI MANZO": "CARNE",
    "BIRRA ARTIGIANALE IPA": "BIRRE",
    "CACCIAVITE TORX": "MANUTENZIONE E ATTREZZATURE",
}


@pytest.fixture
def memoria():
    """Memoria locale gia' in cache per UTENTE: nessuna query, nessuna rete."""
    ai.invalida_cache_memoria()
    with ai._cache_lock:
        ai._memoria_cache["prodotti_utente"][UTENTE] = dict(LOCALE)
        ai._memoria_cache["prodotti_utente_norm"][UTENTE] = {
            ai.get_descrizione_normalizzata_e_originale(d)[0]: c for d, c in LOCALE.items()
        }
        ai._memoria_cache["loaded"] = True
        ai._memoria_cache["_loaded_at"] = time.time()
        ai._memoria_cache["_loaded_user_ids"] = {UTENTE}
    yield
    ai.invalida_cache_memoria()


def _classifica(desc, settore, *, prezzo=10.0, fornitore="FORNITORE SRL", pending=None):
    out = ai.categorizza_con_memoria(
        desc, prezzo, 1.0, user_id=UTENTE, supabase_client=object(), fornitore=fornitore,
        pending_local_saves=pending if pending is not None else [],
        return_fallback_flag=True, totale_riga=prezzo, settore=settore,
    )
    return out, ai.ultima_provenienza()


@pytest.mark.parametrize("desc", ["BISTECCA DI MANZO", "BIRRA ARTIGIANALE IPA"])
def test_retail_una_categoria_food_dalla_memoria_locale_torna_da_classificare(memoria, desc):
    assert _classifica(desc, "retail") == (("Da Classificare", True), ("nessuna", None))


@pytest.mark.parametrize("settore", [None, "ristorazione"])
def test_i_ristoranti_vedono_esattamente_quello_di_prima(memoria, settore):
    assert _classifica("BISTECCA DI MANZO", settore) == (("CARNE", False), ("L2_locale", "certa"))
    assert _classifica("BIRRA ARTIGIANALE IPA", settore)[0] == ("BIRRE", False)


def test_retail_una_categoria_generica_passa_da_qualunque_livello(memoria):
    # "CACCIAVITE" lo prende una regola forte (L1.5) prima della memoria locale:
    # cio' che conta e' che la categoria generica arrivi intatta, non da chi.
    out, prov = _classifica("CACCIAVITE TORX", "retail")
    assert out == ("MANUTENZIONE E ATTREZZATURE", False)
    assert prov[0] != "nessuna"


def test_retail_il_fornitore_utility_passa(memoria):
    out, prov = _classifica("CANONE FIBRA", "retail", fornitore="FASTWEB SPA")
    assert out == ("UTENZE E LOCALI", False)
    assert prov[0] == "L0_fornitore"


def test_retail_una_dicitura_a_importo_zero_passa(memoria):
    out, _ = _classifica("SPESE DI TRASPORTO", "retail", prezzo=0)
    assert out == ("📝 NOTE E DICITURE", False)


def test_retail_il_dizionario_food_torna_da_classificare_e_non_finisce_in_memoria(memoria):
    pending: list = []
    out, prov = _classifica("POLLO INTERO", "retail", pending=pending)
    assert out == ("Da Classificare", True)
    assert prov == ("nessuna", None)
    assert pending == [], "una categoria food e' finita nella memoria locale di un negozio"


def test_per_un_ristorante_lo_stesso_dizionario_classifica_e_salva(memoria):
    pending: list = []
    out, prov = _classifica("POLLO INTERO", None, pending=pending)
    assert out == ("CARNE", False)
    assert prov[0] == "L7_dizionario"
    assert [p["categoria"] for p in pending] == ["CARNE"]


def test_retail_il_dizionario_generico_classifica_e_salva(memoria):
    pending: list = []
    out, _ = _classifica("CANONE MANUTENZIONE ESTINTORI", "retail", pending=pending)
    assert out == ("MANUTENZIONE E ATTREZZATURE", False)
    assert [p["categoria"] for p in pending] == ["MANUTENZIONE E ATTREZZATURE"]


def test_senza_flag_di_fallback_torna_la_stringa(memoria):
    out = ai.categorizza_con_memoria(
        "BISTECCA DI MANZO", 10.0, 1.0, user_id=UTENTE, supabase_client=object(),
        pending_local_saves=[], settore="retail",
    )
    assert out == "Da Classificare"
