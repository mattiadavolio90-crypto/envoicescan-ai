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


class _MasterFinto:
    """Una riga di prodotti_master che RICORDA gli update, così si può far
    girare il ciclo vero (AI conferma → streak → bypass) su più chiamate,
    invece di costruire a mano lo stato finale."""

    def __init__(self, desc, categoria, confidence, verified=False, streak=0):
        self.row = {
            "id": 1, "descrizione": desc, "categoria": categoria,
            "confidence": confidence, "verified": verified,
            "consecutive_correct_classifications": streak,
        }
        self.upsert_chiamato = False

    def table(self, _n):
        return self

    def select(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def execute(self):
        col, val = getattr(self, "_eq", (None, None))
        trovato = col == "descrizione" and val == self.row["descrizione"]
        return SimpleNamespace(data=[dict(self.row)] if trovato else [])

    def update(self, payload):
        self.row.update(payload)
        return self

    def upsert(self, *_a, **_k):
        self.upsert_chiamato = True
        return self


def test_voce_declassata_puo_rientrare_nel_bypass():
    """Il ciclo di rientro della Fase 6, percorso completo.

    Una voce 'alta' MAI verificata da un umano è esattamente ciò che la Fase 6
    declassa. La fase le promette una via di rientro: 3 conferme di fila dell'AI
    e torna a saltare il modello. Questo test la percorre davvero — tre chiamate
    vere — invece di costruire a mano lo stato finale, che è ciò che rendeva il
    presidio precedente verde su un bug che il codice non sapeva produrre.

    Mutante: rimettere `if current_conf in ('alta','altissima'): return` nella
    guardia → lo streak resta 0 e il test diventa rosso.
    """
    sb = _MasterFinto("NOCE DI MANZO", "CARNE", "alta", verified=False, streak=0)

    for atteso in (1, 2, 3):
        ai_mod.aggiorna_streak_classificazione("NOCE DI MANZO", "CARNE", sb)
        assert sb.row["consecutive_correct_classifications"] == atteso, (
            f"lo streak non sale: la voce declassata non ha via di rientro "
            f"(atteso {atteso}, trovato {sb.row['consecutive_correct_classifications']})"
        )

    assert sb.upsert_chiamato is False, "ha creato un doppione invece di aggiornare"

    # Lo stato raggiunto deve davvero riaprire il bypass in cache.
    cache = _cache_con_master([_voce(
        "NOCE DI MANZO", sb.row["confidence"],
        verified=False, streak=sb.row["consecutive_correct_classifications"],
    )])
    assert cache["prodotti_master"]["NOCE DI MANZO"] == "CARNE", (
        "streak a soglia ma la voce non rientra nel bypass"
    )


def test_voce_declassata_rientra_anche_in_grafia_normalizzata():
    """Stessa via di rientro sul ramo gemello: la coda passa descrizioni grezze
    mentre altri percorsi scrivono la variante normalizzata. Se la guardia
    sbagliata resta solo qui, si corregge metà del percorso e le voci che
    esistono in sola grafia normalizzata restano bloccate."""
    from utils.text_utils import normalizza_descrizione

    grezza = "(I)100 COP EST. X DW 280CC"
    norm = normalizza_descrizione(grezza)
    assert norm != grezza, "prerequisito: la grafia deve normalizzare diversa"

    sb = _MasterFinto(norm, "MATERIALE DI CONSUMO", "alta", verified=False, streak=0)

    for atteso in (1, 2, 3):
        ai_mod.aggiorna_streak_classificazione(grezza, "MATERIALE DI CONSUMO", sb)
        assert sb.row["consecutive_correct_classifications"] == atteso, (
            f"ramo gemello: streak fermo (atteso {atteso})"
        )

    assert sb.upsert_chiamato is False, "ha creato un doppione invece di aggiornare"


def test_chi_e_gia_in_bypass_non_viene_toccato():
    """La guardia deve continuare a proteggere chi è GIÀ in bypass: un
    verificato non si tocca mai, e chi è a soglia non ha nulla da guadagnare."""
    verificato = _MasterFinto("POLLO INTERO", "CARNE", "altissima", verified=True, streak=0)
    ai_mod.aggiorna_streak_classificazione("POLLO INTERO", "PESCE", verificato)
    assert verificato.row["categoria"] == "CARNE", "ha sovrascritto un verificato umano"
    assert verificato.row["consecutive_correct_classifications"] == 0

    a_soglia = _MasterFinto("BURRATA 125G", "LATTICINI", "alta", verified=False, streak=3)
    ai_mod.aggiorna_streak_classificazione("BURRATA 125G", "LATTICINI", a_soglia)
    assert a_soglia.row["consecutive_correct_classifications"] == 3, (
        "chi è già a soglia non deve essere ri-scritto a ogni fattura"
    )


def test_ai_puo_correggere_la_categoria_di_una_voce_declassata():
    """Effetto voluto della Fase 6, ma che nessun test dichiarava: la categoria
    di una voce 'alta' MAI verificata non è più immutabile.

    Prima del fix quelle voci uscivano subito e la categoria a DB restava com'era
    — anche quando era il caso «NOCE DI MANZO → FRUTTA» che ha motivato la fase.
    Ora l'AI può correggerla, e lo streak riparte da 1 sulla nuova categoria.
    Vale in entrambe le direzioni: è il prezzo dichiarato di considerare quelle
    voci non attendibili finché una conferma non le rialza.
    """
    sb = _MasterFinto("NOCE DI MANZO", "FRUTTA", "alta", verified=False, streak=0)
    ai_mod.aggiorna_streak_classificazione("NOCE DI MANZO", "CARNE", sb)

    assert sb.row["categoria"] == "CARNE", "l'errore della memoria non si corregge"
    assert sb.row["consecutive_correct_classifications"] == 1, (
        "categoria cambiata: lo streak deve ripartire, non proseguire"
    )

    # Un verificato, invece, resta intoccabile: è la riga di confine.
    umano = _MasterFinto("POLLO", "CARNE", "altissima", verified=True, streak=0)
    ai_mod.aggiorna_streak_classificazione("POLLO", "FRUTTA", umano)
    assert umano.row["categoria"] == "CARNE"
