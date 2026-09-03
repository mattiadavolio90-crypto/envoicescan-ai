"""Il filtro «le righe non classificate non entrano nei margini», da un posto solo (R6).

**La regola** (CLAUDE.md §1): una riga che né dizionario/regole né l'AI sanno
classificare resta `"Da Classificare"`, ed è **esclusa dai margini** finché
qualcuno non la classifica — altrimenti falserebbe il MOL.

**Il difetto strutturale.** La regola era scritta a mano in **7 punti** del
backend: 6 come `.neq('categoria', 'Da Classificare')` e 1 dentro una stringa
di filtro PostgREST. Funzionavano tutti, ma sono sette copie della stessa
frase: il giorno che la regola cambia, chi ne aggiorna sei su sette produce due
totali diversi nella stessa pagina — il difetto «fix parziale» che il progetto
ha già pagato.

La costante `CATEGORIA_NON_CLASSIFICATA` esisteva già in `config/constants.py`,
dichiarata «Fonte unica», ed era **già usata in quegli stessi file** poche
righe più su: le query erano rimaste indietro, non per una scelta.

**Perché non serviva nessuna migration.** La roadmap dava R6 per «richiede una
migration su 7 account veri». Misurato il 3/9/2026: la sostituzione è
`'Da Classificare'` → `CATEGORIA_NON_CLASSIFICATA`, cioè **la stessa stringa**.
Nessun dato cambia, nessuna query cambia comportamento.
"""
import pathlib
import re

import pytest

from config.constants import CATEGORIA_FALLBACK, CATEGORIA_NON_CLASSIFICATA

_ROOT = pathlib.Path(__file__).resolve().parents[1]

# I file che contengono il filtro di esclusione dai margini.
_CON_FILTRO = [
    "services/margine_service.py",
    "services/fastapi_worker.py",
    "worker/queue_processor.py",
]


def _codice_vivo(percorso: pathlib.Path) -> str:
    return "\n".join(
        r for r in percorso.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith("#")
    )


def test_il_valore_della_costante_non_cambia():
    """La grafia esatta. Attenzione: `'Da Clasificare'` (una sola "s") è la
    variante errata storica, e resta sbagliata."""
    assert CATEGORIA_NON_CLASSIFICATA == "Da Classificare"
    assert CATEGORIA_FALLBACK is CATEGORIA_NON_CLASSIFICATA


@pytest.mark.parametrize("relativo", _CON_FILTRO)
def test_il_filtro_non_riscrive_piu_il_letterale(relativo):
    """Il cuore di R6: nessuna query esclude la categoria con la stringa a mano.

    Cerca il letterale **dentro una chiamata di filtro** (`.neq(...)` o un
    `.or_(...)`), non ovunque nel file: nei commenti e nei messaggi di log la
    stringa è legittima e va lasciata leggibile.
    """
    vivo = _codice_vivo(_ROOT / relativo)
    colpevoli = [
        r.strip()[:100]
        for r in vivo.splitlines()
        if re.search(r"\.(neq|eq)\(\s*[\"']categoria[\"']\s*,\s*[\"']Da Classificare[\"']", r)
        or ("categoria.eq.Da Classificare" in r)
    ]
    assert colpevoli == [], (
        f"{relativo}: il filtro riscrive di nuovo la categoria a mano invece di "
        f"usare `CATEGORIA_NON_CLASSIFICATA`: {colpevoli}"
    )


@pytest.mark.parametrize("relativo", _CON_FILTRO)
def test_il_file_importa_la_fonte_unica(relativo):
    vivo = _codice_vivo(_ROOT / relativo)
    assert "CATEGORIA_NON_CLASSIFICATA" in vivo, (
        f"{relativo} non usa piu' la costante: la regola di dominio e' tornata "
        "a essere una stringa scritta a mano"
    )


def test_le_otto_occorrenze_sono_tutte_legate():
    """Il conto, così un'aggiunta silenziosa si vede.

    7 filtri `.neq(...)` + 1 dentro la stringa PostgREST del queue-worker.
    L'ottava è del 3/9 (Fase 4bis): `_card_da_classificare` conta le righe
    dubbie ESCLUDENDO le 'Da Classificare' già contate a parte — usa la
    costante come gli altri punti.
    """
    trovate = 0
    for relativo in _CON_FILTRO:
        vivo = _codice_vivo(_ROOT / relativo)
        trovate += len(re.findall(r"\.neq\(\s*[\"']categoria[\"']\s*,\s*CATEGORIA_NON_CLASSIFICATA", vivo))
        trovate += len(re.findall(r"categoria\.eq\.\{CATEGORIA_NON_CLASSIFICATA\}", vivo))
    assert trovate == 8, (
        f"i punti legati alla fonte unica sono {trovate}, non 8. Se ne hai "
        "aggiunto uno aggiorna il numero; se ne è sparito uno, quel punto è "
        "tornato a decidere da solo se una riga entra nel MOL"
    )


def test_il_filtro_postgrest_da_la_stessa_stringa_del_letterale():
    """La sola sostituzione non banale: dentro una stringa di filtro.

    PostgREST separa le condizioni con la virgola e i campi col punto: se il
    valore ne contenesse, interpolarlo cambierebbe la query. `Da Classificare`
    non ne ha — verificato qui, non dedotto.
    """
    costruita = f"categoria.is.null,categoria.eq.{CATEGORIA_NON_CLASSIFICATA},categoria.eq."
    assert costruita == "categoria.is.null,categoria.eq.Da Classificare,categoria.eq."
    assert "," not in CATEGORIA_NON_CLASSIFICATA
    assert "." not in CATEGORIA_NON_CLASSIFICATA
