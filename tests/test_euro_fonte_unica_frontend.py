"""Le copie locali del formattatore euro non devono tornare.

Il 22/09/2026 il frontend scriveva un importo in euro da 19 punti diversi, con
9 forme distinte a schermo: il simbolo a volte prima («€ 322,10») a volte dopo
(«322,10 €»), i decimali 0, 2 o 4, il «+» presente in due posti e assente
altrove. Il consenso esistente era gia' netto — 92 call site su ~117 usavano
`formatEuro` di `lib/format.ts`, col simbolo in coda — quindi la decisione
(Mattia, 22/09) e' stata: **simbolo in coda ovunque**, e le copie spariscono.

**Perche' un test che legge il sorgente, e non solo uno che esegue.** La stessa
lezione e' scritta in `test_catena_formattatori_equivalenza_frontend.py`: un
test che ricostruisce l'implementazione e la esegue prova che quella forma si
comporta bene, non che il file la usi. Qui si presidia il FATTO che il file non
ridefinisca il formattatore.

**Perche' NON si cerca `from "@/lib/format"`.** Esistono tre barrel di
re-export — `analisi-fatture/periodi.ts`, `margini/periodi.ts`,
`lib/scadenziario.ts` — e una decina di file importano `formatEuro`
attraverso di essi, senza contenere mai quella stringa. Un assert sull'import
letterale accenderebbe il rosso su file corretti. Si cerca invece la FORMULA
duplicata, che e' il difetto vero.
"""
import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

# I file da cui la copia locale e' stata rimossa il 22/09/2026. Se una di
# queste righe torna, il presidio deve accorgersene.
_MIGRATI = [
    "app/(app)/workspace/inventario-tab.tsx",
    "app/(app)/workspace/inventario-storico-dialog.tsx",
    "app/(app)/workspace/inventario-aggiungi-dialog.tsx",
    "app/(app)/workspace/personale-tab.tsx",
    "app/(app)/workspace/spese-view.tsx",
    "app/(mobile)/m/diario/mobile-spese.tsx",
    "app/(mobile)/m/diario/mobile-incassi.tsx",
    "app/(mobile)/m/turni/mobile-turni.tsx",
    "app/(app)/prezzi/sconti-tab.tsx",
    "app/(app)/prezzi/nc-tab.tsx",
    "app/(app)/prezzi/score-tab.tsx",
    "app/(app)/prezzi/anteprima-fattura-dialog.tsx",
    "app/(app)/prezzi/variazioni-tab.tsx",
    "app/(app)/analisi-e-tag/analisi-e-tag-client.tsx",
]

# L'ECCEZIONE, documentata e presidiata: `lib/foodcost.ts` tiene la sua copia
# perche' `tests/helpers_ts.py` lo esegue con node, che non risolve un import
# relativo senza estensione (provato il 22/09/2026: 11 test rossi con
# ERR_MODULE_NOT_FOUND). Non e' una deroga: l'ultimo test di questo file prova
# che il suo output resta identico a `formatEuro(v, 2)`, valore per valore.
_COPIA_AMMESSA = "lib/foodcost.ts"

# `Intl.NumberFormat(... currency ...)`: la formula che le copie ripetevano.
# Su piu' righe, quindi DOTALL e ricerca sul testo intero.
_FORMULA_VALUTA = re.compile(
    r'Intl\.NumberFormat\(\s*"it-IT"\s*,\s*\{[^}]*currency\s*:\s*"EUR"',
    re.S,
)


@pytest.mark.parametrize("percorso", _MIGRATI)
def test_nessuna_copia_locale_del_formattatore_euro(percorso):
    testo = (_SRC / percorso).read_text(encoding="utf-8")
    trovate = _FORMULA_VALUTA.findall(testo)
    assert not trovate, (
        f"{percorso} ridefinisce il formattatore euro invece di usare "
        "`formatEuro` da lib/format: le copie divergono in silenzio "
        "(il 22/09 erano 9 forme diverse a schermo)."
    )


@pytest.mark.parametrize("percorso", _MIGRATI)
def test_il_simbolo_non_torna_in_testa(percorso):
    """«€ 322,10» era la forma di Osservatorio e Analisi e Tag; lo standard
    del prodotto e' «322,10 €». Si cerca il simbolo concatenato PRIMA di un
    numero interpolato, che e' come le copie lo scrivevano."""
    testo = (_SRC / percorso).read_text(encoding="utf-8")
    # `€ ${...}` dentro un template literal: la firma della forma in testa.
    in_testa = re.findall(r"`€\s*\$\{", testo)
    assert not in_testa, (
        f"{percorso} scrive di nuovo il simbolo prima del numero: "
        "lo standard del prodotto e' in coda («322,10 €»), deciso il 22/09."
    )


def test_il_formattatore_unico_esiste_e_mette_il_simbolo_in_coda():
    """Se un domani `formatEuro` cambiasse posizione al simbolo, i 92 call
    site la seguirebbero in silenzio: e' la riga che tiene lo standard."""
    testo = (_SRC / "lib" / "format.ts").read_text(encoding="utf-8")
    assert 'style: "currency"' in testo, (
        "formatEuro non usa piu' Intl con style:currency: in it-IT e' cio' "
        "che mette il simbolo in coda"
    )


def test_la_copia_ammessa_di_foodcost_resta_identica_alla_libreria():
    """L'eccezione non deve diventare una divergenza.

    `lib/foodcost.ts` non puo' importare `formatEuro` (limite dell'harness,
    vedi `_COPIA_AMMESSA`), quindi la sua `fmtEuro` e' l'unica copia rimasta.
    Qui si prova che produce la STESSA stringa della libreria — inclusi i
    limiti di arrotondamento e lo spazio unificatore, che a occhio non si
    distingue ma in un confronto di stringhe si'.
    """
    from tests.helpers_ts import esegui_ts

    valori = [0, 0.5, 1, 1.005, 2.675, 999.99, 1000, 1234.56, -1234.56,
              1_000_000, 27.6, 730, 322.10, 0.001, 1.2345, 9999.99, 10000]
    for v in valori:
        dalla_copia = esegui_ts(
            "lib/foodcost",
            "emit(m.fmtEuro(input));",
            argomento=v,
            richiede=["fmtEuro"],
        )
        dalla_libreria = esegui_ts(
            "lib/format",
            "emit(m.formatEuro(input, 2));",
            argomento=v,
            richiede=["formatEuro"],
        )
        assert dalla_copia == dalla_libreria, (v, dalla_copia, dalla_libreria)


def test_la_copia_ammessa_tiene_la_guardia_sul_null():
    """`formatEuro` su null lancia TypeError: la guardia e' cio' che rende la
    copia usabile dove il dato puo' mancare."""
    from tests.helpers_ts import esegui_ts

    assert esegui_ts(
        "lib/foodcost",
        "emit(m.fmtEuro(null));",
        richiede=["fmtEuro"],
    ) == "—"
