"""Fase 6 (D4): il bypass della memoria globale richiede una CONFERMA.

Prima bastava `confidence: 'alta'` — che per 357 voci era la sola parola
dell'AI, mai vista da nessuno (misurate a DB il 3/9; campionando quel
dizionario ~29% di errori: «NOCE di manzo» → FRUTTA). Ora una voce salta l'AI
solo se un umano l'ha verificata (`verified`) o se lo streak l'ha confermata
(>=3 fatture di fila senza correzione). Tutto il resto passa come hint: l'AI
ha l'ultima parola e il gate a valle decide.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.ai_service as ai_mod


def _query(data):
    q = MagicMock()
    for m in ["select", "eq", "neq", "gte", "lte", "is_", "range", "or_", "in_", "limit"]:
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=data)
    return q


def _cache_con_master(rows_master):
    ai_mod.invalida_cache_memoria()
    supabase = MagicMock()

    def _table(name):
        if name == "prodotti_master":
            return _query(rows_master)
        return _query([])

    supabase.table.side_effect = _table
    try:
        return ai_mod.carica_memoria_completa("user-1", supabase_client=supabase)
    finally:
        ai_mod.invalida_cache_memoria()


def _voce(desc, conf, verified=False, streak=0, cat="CARNE"):
    return {
        "descrizione": desc, "categoria": cat, "confidence": conf,
        "consecutive_correct_classifications": streak, "verified": verified,
    }


def test_alta_verificata_resta_in_bypass():
    cache = _cache_con_master([_voce("POLLO INTERO", "alta", verified=True)])
    assert cache["prodotti_master"]["POLLO INTERO"] == "CARNE"


def test_alta_non_verificata_diventa_hint():
    """Il cuore della Fase 6: le 357 voci solo-AI escono dal bypass."""
    cache = _cache_con_master([_voce("NOCE DI MANZO", "alta", verified=False)])
    assert "NOCE DI MANZO" not in cache["prodotti_master"]
    assert cache["prodotti_master_hint"]["NOCE DI MANZO"] == "CARNE"


def test_altissima_non_verificata_diventa_hint():
    cache = _cache_con_master([_voce("X", "altissima", verified=False)])
    assert "X" not in cache["prodotti_master"]
    assert "X" in cache["prodotti_master_hint"]


def test_lo_streak_conferma_anche_senza_umano():
    """3 fatture di fila senza correzione = conferma: la promozione via streak
    (aggiorna_streak_classificazione) deve continuare a funzionare."""
    cache = _cache_con_master([_voce("BURRATA 125G", "alta", verified=False, streak=3)])
    assert cache["prodotti_master"]["BURRATA 125G"] == "CARNE"


def test_media_con_streak_resta_in_bypass():
    cache = _cache_con_master([_voce("Y", "media", verified=False, streak=5)])
    assert "Y" in cache["prodotti_master"]


def test_media_non_confermata_resta_hint():
    cache = _cache_con_master([_voce("Z", "media", verified=False, streak=2)])
    assert "Z" not in cache["prodotti_master"]
    assert "Z" in cache["prodotti_master_hint"]
