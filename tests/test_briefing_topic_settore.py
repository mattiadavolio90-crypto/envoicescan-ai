"""I topic del configuratore di un negozio (RETAIL_FASI.md, Fase 4).

`_CONFIG_TOPICS` acquisisce la dimensione settore. Due cose diverse:

1. `coperti_anomalia` SPARISCE per un negozio. La cassa manda solo il fatturato,
   e la Fase 3 gli ha spento la tab Coperti: lasciare il topic offrirebbe di
   accendere un avviso su un dato che non arriva mai, con una CTA verso una tab
   che non puo' aprire;
2. `fatturato_mancante` RESTA, ma la sua descrizione non promette il food cost —
   per un negozio quel fatturato serve al costo merce.

La parte che conta di piu' e' il ramo ristorazione: stessa lista, stesso ordine,
stesse stringhe di ieri.
"""
import pytest

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE


def _chiavi(settore):
    return [k for (k, _l, _b, _d) in fw._topics_per_settore(settore)]


def _descrizione(settore, chiave):
    return next(d for (k, _l, _b, d) in fw._topics_per_settore(settore) if k == chiave)


# ── Il negozio ───────────────────────────────────────────────────────────

def test_un_negozio_non_vede_il_topic_dei_coperti():
    assert "coperti_anomalia" not in _chiavi(SETTORE_RETAIL)


def test_un_negozio_vede_tutti_gli_altri_topic():
    """Spegnere il topic sbagliato gli toglierebbe un avviso che gli serve."""
    attesi = [k for (k, _l, _b, _d) in fw._CONFIG_TOPICS if k != "coperti_anomalia"]
    assert _chiavi(SETTORE_RETAIL) == attesi


def test_al_negozio_il_fatturato_non_promette_il_food_cost():
    d = _descrizione(SETTORE_RETAIL, "fatturato_mancante")
    assert "food cost" not in d.lower()
    assert "costo merce" in d.lower()
    assert "MOL" in d


def test_i_topic_bloccati_restano_bloccati_per_un_negozio():
    bloccati = {k for (k, _l, b, _d) in fw._topics_per_settore(SETTORE_RETAIL) if b}
    assert bloccati == fw._CONFIG_TOPICS_BLOCCATI


# ── Il vincolo: per un ristorante NON cambia niente ──────────────────────

@pytest.mark.parametrize("settore", [SETTORE_RISTORAZIONE, None, "", "valore_ignoto"])
def test_ramo_ristorazione_identico_lista_ordine_e_stringhe(settore):
    """Confronto sulla lista INTERA, non sulle sole chiavi: una descrizione
    riscritta e' un'etichetta cambiata, ed e' il vincolo di Mattia."""
    assert fw._topics_per_settore(settore) == list(fw._CONFIG_TOPICS)


def test_al_ristorante_il_fatturato_nomina_ancora_il_food_cost():
    d = _descrizione(SETTORE_RISTORAZIONE, "fatturato_mancante")
    assert d == "Ti ricordo di inserire il fatturato del mese, serve per food cost e MOL."


def test_al_ristorante_i_coperti_ci_sono_ancora():
    assert "coperti_anomalia" in _chiavi(SETTORE_RISTORAZIONE)


# ── La validazione del POST resta sulla lista completa ───────────────────

def test_un_topic_spento_per_settore_resta_salvabile():
    """`validi`/`bloccati` non devono restringersi col settore: un negozio che
    avesse gia' `coperti_anomalia` in topics_disabled lo vedrebbe sparire dal
    record, e riaccendersi da solo se un giorno il settore cambia."""
    validi = {k for (k, _l, _b, _d) in fw._CONFIG_TOPICS}
    assert "coperti_anomalia" in validi


# ── La notifica non viene nemmeno generata ───────────────────────────────

def test_il_briefing_di_un_negozio_non_calcola_l_anomalia_coperti(monkeypatch):
    """Il gate sulla LISTA dei topic non basta: la notifica nasce altrove, e
    senza questo un negozio la riceverebbe in campanella con una CTA verso la
    tab che non puo' aprire."""
    chiamata = {"si": False}

    def _mai(*a, **k):
        chiamata["si"] = True
        return None

    monkeypatch.setattr(fw, "_briefing_anomalia_coperti", _mai)
    monkeypatch.setattr("services.settore_service.settore_sede", lambda *a, **k: SETTORE_RETAIL)
    monkeypatch.setattr(fw, "_load_mensile_overrides", lambda *a, **k: {})

    from unittest.mock import MagicMock
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[], count=0)

    fw._briefing_dati_mensili_mancanti("rid-1", sb, set())
    assert chiamata["si"] is False, "un negozio ha calcolato l'anomalia coperti"


def test_il_briefing_di_un_ristorante_la_calcola_ancora(monkeypatch):
    chiamata = {"si": False}

    def _si(*a, **k):
        chiamata["si"] = True
        return None

    monkeypatch.setattr(fw, "_briefing_anomalia_coperti", _si)
    monkeypatch.setattr("services.settore_service.settore_sede", lambda *a, **k: SETTORE_RISTORAZIONE)
    monkeypatch.setattr(fw, "_load_mensile_overrides", lambda *a, **k: {})

    from unittest.mock import MagicMock
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[], count=0)

    fw._briefing_dati_mensili_mancanti("rid-1", sb, set())
    assert chiamata["si"] is True
