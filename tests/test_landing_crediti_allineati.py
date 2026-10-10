"""I crediti della landing sono quelli che l'app applica (fase J, 10/10/2026).

Fino al 10/10 la landing prometteva 1.000/2.000/3.000 «crediti AI» e l'app
contava 300/600/900 DOMANDE: due unita' diverse, e Plus e Pro dicevano un
numero che il prodotto non conosceva. Ora l'app conta crediti: il test tiene
insieme la promessa e il motore.
"""
from __future__ import annotations

import re

import services.fastapi_worker as fw
from services.routers import admin
from tests.helpers_ts import esegui_ts


def _piani():
    return esegui_ts("lib/landing-content", "emit(m.LANDING.piani);", None)


def _numero(testo: str) -> int:
    return int(re.match(r"([\d.]+) crediti AI / mese", testo).group(1).replace(".", ""))


def test_i_crediti_dei_piani_sono_quelli_del_worker():
    for p in _piani()["lista"]:
        assert _numero(p["crediti"]) == fw.CHAT_BUDGET_MENSILE_PIANO[p["nome"].lower()], p


def test_le_richieste_al_giorno_non_promettono_piu_di_quanto_c_e():
    """«~N richieste al giorno» con N <= crediti / 3 / 30 arrotondato: la nota e'
    un ordine di grandezza, ma non puo' superare cio' che il mese consente."""
    for p in _piani()["lista"]:
        n = int(re.match(r"~(\d+) richieste al giorno", p["creditiNota"]).group(1))
        al_giorno = _numero(p["crediti"]) / fw.CHAT_CREDITI_PER_DOMANDA / 30
        assert n <= al_giorno, (p["nome"], n, al_giorno)
        assert n >= al_giorno * 0.6, (p["nome"], n, al_giorno)


def test_la_catena_dice_la_regola_del_worker():
    testo = _piani()["creditiCatena"]
    assert "per intero" in testo and "per metà" in testo
    assert fw.CHAT_PESO_SEDE_AGGIUNTIVA == 0.5


def test_il_boost_della_landing_e_quello_dell_app():
    testo = _piani()["boost"]
    assert f"{admin.RICARICA_AI_CREDITI} crediti a 10€" in testo
    assert "senza scadenza" in testo
