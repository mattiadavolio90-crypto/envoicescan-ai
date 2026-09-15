"""Il periodo di default lo decide il giorno di Roma, non quello del server (L6, 15/09/2026).

`calcolaPeriodo(preset)` senza secondo argomento usa `new Date()`. Nei Server Component
(`margini/page.tsx`, `analisi-fatture/page.tsx`) quel codice gira su Vercel, che e' in
**UTC**: fra mezzanotte e le 02:00 italiane il giorno del server e' ancora ieri. Misurato
eseguendo il modulo vero: alle 00:30 del 1° ottobre a Roma il preset «mese in corso»
rispondeva `2026-09-01 -> 2026-09-30` — il mese precedente per intero, con KPI, food cost
e MOL di settembre sotto l'etichetta «Mese in corso».

Il difetto e' stato trovato da un agente refutatore che contestava la mia conclusione
«nel frontend le date senza fuso servono solo al nome di un file».

`test_margini_periodi_frontend.py` prova gia' i fusi estremi, ma confronta con il giorno
locale **del processo di test**: passa identico a UTC e a Roma, quindi non poteva vedere
questo. Qui i due fusi si confrontano fra loro sullo **stesso istante**.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.helpers_ts import esegui_ts

WEB_SRC = pathlib.Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
MODULO = "lib/oggi-roma"

# 00:30 del 1° ottobre a Roma (CEST, +02:00) = 22:30 del 30 settembre UTC.
ISTANTE_NOTTURNO = "2026-09-30T22:30:00Z"
PAGINE_SERVER = [
    "app/(app)/margini/page.tsx",
    "app/(app)/analisi-fatture/page.tsx",
]


def _oggi_a_roma(tz: str, istante: str = ISTANTE_NOTTURNO):
    """[anno, mese1based, giorno] che l'helper calcola, eseguito nel fuso `tz`."""
    return esegui_ts(
        MODULO,
        "const d = m.oggiARoma(new Date(input));"
        "emit([d.getFullYear(), d.getMonth() + 1, d.getDate()]);",
        istante,
        tz=tz,
        richiede=["oggiARoma"],
    )


@pytest.mark.parametrize("tz", ["UTC", "Europe/Rome", "Pacific/Kiritimati", "Pacific/Midway"])
def test_lo_stesso_istante_da_lo_stesso_giorno_di_roma_in_ogni_fuso(tz):
    """L'helper non deve dipendere dal fuso del processo: e' il punto."""
    assert _oggi_a_roma(tz) == [2026, 10, 1], (
        f"in {tz} l'helper non ha dato il giorno di Roma: legge il fuso del processo"
    )


def test_a_mezzogiorno_utc_non_cambia_nulla():
    """Controllo positivo: fuori dalla finestra notturna i due giorni coincidono gia'."""
    assert _oggi_a_roma("UTC", "2026-09-30T12:00:00Z") == [2026, 9, 30]


def test_senza_l_helper_il_server_vedrebbe_il_mese_sbagliato():
    """Controllo negativo che misura il difetto: `calcolaPeriodo` col `new Date()` interno,
    eseguito in UTC sullo stesso istante, chiude su settembre."""
    codice = (
        "const _D = Date;"
        "class F extends _D { constructor(...a) { if (!a.length) super(input); else super(...a); } "
        "static now() { return new _D(input).getTime(); } }"
        "globalThis.Date = F;"
        "emit(m.calcolaPeriodo('mese_corrente'));"
    )
    utc = esegui_ts("app/(app)/margini/periodi", codice, ISTANTE_NOTTURNO,
                    tz="UTC", richiede=["calcolaPeriodo"])
    assert utc == {"data_da": "2026-09-01", "data_a": "2026-09-30", "label": "Mese in corso"}


def test_con_l_helper_il_periodo_e_quello_di_roma():
    """Lo stesso istante, ma col giorno di Roma: ottobre, come lo vede il cliente.

    `periodi.ts` re-esporta da `@/lib/format`, alias che node non risolve: il giorno
    calcolato dall'helper si passa quindi come data, non come import incrociato.
    """
    anno, mese, giorno = _oggi_a_roma("UTC")
    risultato = esegui_ts(
        "app/(app)/margini/periodi",
        f"emit(m.calcolaPeriodo('mese_corrente', new Date({anno},{mese - 1},{giorno},12)));",
        tz="UTC",
        richiede=["calcolaPeriodo"],
    )
    assert risultato["data_da"] == "2026-10-01" and risultato["data_a"] == "2026-10-01", (
        "col giorno di Roma il periodo deve essere ottobre, non settembre"
    )


@pytest.mark.parametrize("pagina", PAGINE_SERVER)
def test_le_pagine_server_passano_il_giorno_di_roma_a_calcolaperiodo(pagina):
    """Le due pagine sono Server Component (niente "use client"): ogni `calcolaPeriodo`
    che vi compare deve ricevere un secondo argomento, o torna a leggere l'ora del server.
    """
    testo = (WEB_SRC / pagina).read_text(encoding="utf-8")
    assert not testo.lstrip().startswith('"use client"'), (
        f"{pagina} e' diventata un client component: questo presidio va ripensato, "
        "nel browser il fuso e' gia' quello del cliente"
    )
    chiamate = re.findall(r"calcolaPeriodo\(([^)]*)\)", testo)
    assert chiamate, f"{pagina} non chiama piu' calcolaPeriodo: aggiorna il presidio"
    for argomenti in chiamate:
        assert "," in argomenti, (
            f"{pagina} chiama calcolaPeriodo({argomenti}) senza il giorno: "
            "in un Server Component su Vercel (UTC) il periodo chiude sul giorno sbagliato"
        )
        assert "oggiARoma" in argomenti, (
            f"{pagina} passa un giorno che non viene da oggiARoma(): {argomenti}"
        )
