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
    "lib/foodcost.ts",
    "app/(app)/prezzi/sconti-tab.tsx",
    "app/(app)/prezzi/nc-tab.tsx",
    "app/(app)/prezzi/score-tab.tsx",
    "app/(app)/prezzi/anteprima-fattura-dialog.tsx",
    "app/(app)/prezzi/variazioni-tab.tsx",
    "app/(app)/analisi-e-tag/analisi-e-tag-client.tsx",
]

# Due grafie, non una. La prima e' `currency: "EUR"`; la seconda e' un
# `Intl.NumberFormat` NEUTRO con accanto il simbolo dell'euro, che e' come si
# scrive una copia col simbolo in testa e sfuggiva al regex precedente
# (provato per mutazione il 22/09: il presidio la lasciava passare).
# Non basta cercare `Intl.NumberFormat("it-IT")` e basta: formatta anche
# quantita' e pesi, che euro non sono — cercare la famiglia sbagliata accende
# il rosso su codice corretto, che e' l'altro modo di rendere inutile un test.
_FORMULA_VALUTA = re.compile(
    r'Intl\.NumberFormat\(\s*"it-IT"\s*,\s*\{[^}]*currency\s*:\s*"EUR"',
    re.S,
)
_SIMBOLO_ACCANTO = re.compile(
    r'(?:€|\\u20ac)[^\n]{0,20}Intl\.NumberFormat|Intl\.NumberFormat[^\n]{0,80}\}\)[^\n]{0,10}(?:€|\\u20ac)'
)


@pytest.mark.parametrize("percorso", _MIGRATI)
def test_nessuna_copia_locale_del_formattatore_euro(percorso):
    testo = (_SRC / percorso).read_text(encoding="utf-8")
    trovate = _FORMULA_VALUTA.findall(testo) + _SIMBOLO_ACCANTO.findall(testo)
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
    # Tre grafie, non una: il template literal, la concatenazione con `+`, e
    # l'escape unicode. Col solo pattern del template una copia scritta
    # `"\u20ac " + ...` passava indisturbata (provato per mutazione).
    simbolo = r"(?:€|\\u20ac)"
    in_testa = (
        re.findall(rf"`{simbolo}\s*\$\{{", testo)
        + re.findall(rf'"{simbolo}\s*"\s*\+', testo)
        + re.findall(rf"'{simbolo}\s*'\s*\+", testo)
    )
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
