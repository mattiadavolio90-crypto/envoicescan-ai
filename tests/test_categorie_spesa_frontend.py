"""Le categorie di spesa del client dicono le STESSE cose del server.

`apps/web/src/lib/categorie-spesa.ts` e' nato come fix di F1: le 4 categorie di
spesa generale erano ricopiate come literal in articoli-tab, pivot-tab e
dropdown-categoria — quattro liste che dovevano restare identiche per sempre, e
che quindi prima o poi divergevano. Una categoria finita nel secchio sbagliato
sposta soldi fra i secchi del MOL **senza dare errore**.

Il commento del modulo dichiara «deve restare identica a `_tipo_da_categoria()`
in services/routers/workspace.py». Finora nessuno lo verificava: la dichiarazione
era una promessa, non un vincolo. Qui diventa eseguibile.

Si confronta il **comportamento**, non le costanti: leggere due liste col regex
passerebbe anche se `tipoDaCategoria` invertisse il ramo. Ed e' la lezione del
test sulla policy password, dove la prima versione misurava due numeri e non
accorgeva di una regex mutilata.
"""
import re
from pathlib import Path

import pytest

from config.constants import (
    CATEGORIA_NON_CLASSIFICATA,
    CATEGORIE_SPESE_GENERALI,
    TUTTE_LE_CATEGORIE,
)
from services.routers.workspace import _tipo_da_categoria
from tests.helpers_ts import WEB_SRC, esegui_ts

MODULO = "lib/categorie-spesa"

# Stringhe che un utente o un refactor possono produrre e che non devono far
# cadere il client in un ramo diverso dal server.
OSTILI = [
    "",
    " ",
    "utenze e locali",
    "UTENZE E LOCALI ",
    " UTENZE E LOCALI",
    "Utenze E Locali",
    "CATEGORIA INESISTENTE",
    "Da Clasificare",  # il refuso con una sola "s": filtrerebbe zero righe per sempre
    "📝 NOTE E DICITURE",
]


def _client(espressione, argomento=None, richiede=("tipoDaCategoria",)):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=richiede)


def test_le_spese_generali_sono_le_stesse_del_server():
    ts = _client("emit([...m.SPESE_GENERALI_SET]);")
    assert set(ts) == set(CATEGORIE_SPESE_GENERALI), (
        "SPESE_GENERALI_SET del client e CATEGORIE_SPESE_GENERALI del server "
        "sono divergenti: una categoria cambierebbe secchio nel MOL"
    )


def test_lo_stato_non_classificata_e_identico():
    ts = _client("emit(m.CATEGORIA_NON_CLASSIFICATA);")
    assert ts == CATEGORIA_NON_CLASSIFICATA


@pytest.mark.parametrize("categoria", sorted(TUTTE_LE_CATEGORIE) + OSTILI)
def test_tipo_da_categoria_concorda_col_server(categoria):
    """Il confronto che conta: stesso verdetto, categoria per categoria."""
    ts = esegui_ts(
        MODULO,
        "emit(m.tipoDaCategoria(input));",
        argomento=categoria,
        richiede=["tipoDaCategoria"],
    )
    assert ts == _tipo_da_categoria(categoria), (
        f"categoria {categoria!r}: il client dice {ts}, il server "
        f"{_tipo_da_categoria(categoria)}"
    )


def test_fb_e_generali_partizionano_i_selezionabili():
    """Un filtro invertito lascerebbe una lista vuota e l'altra piena."""
    ts = _client(
        "emit({fb: m.CATEGORIE_SPESA_FB, gen: m.CATEGORIE_SPESA_GENERALI});"
    )
    fb, gen = set(ts["fb"]), set(ts["gen"])

    assert fb and gen, "una delle due liste e' vuota: filtro invertito?"
    assert fb & gen == set(), "una categoria compare in entrambi i secchi"
    assert gen == set(CATEGORIE_SPESE_GENERALI)
    # Selezionabili = le canoniche meno NOTE (riservata alle righe a importo 0)
    # e meno Da Classificare (qui e' l'utente a scrivere la spesa: sa cos'e').
    attese = set(TUTTE_LE_CATEGORIE) - {"📝 NOTE E DICITURE", CATEGORIA_NON_CLASSIFICATA}
    assert fb | gen == attese


def test_da_scegliere_copre_le_tre_condizioni():
    """needs_review, categoria mancante e stato esplicito: erano ricopiate a mano."""
    casi = [
        {"needsReview": True, "categoria": "CARNE", "atteso": True},
        {"needsReview": False, "categoria": None, "atteso": True},
        {"needsReview": False, "categoria": "", "atteso": True},
        {"needsReview": False, "categoria": CATEGORIA_NON_CLASSIFICATA, "atteso": True},
        {"needsReview": False, "categoria": "CARNE", "atteso": False},
        {"needsReview": None, "categoria": "CARNE", "atteso": False},
    ]
    ts = esegui_ts(
        MODULO,
        "emit(input.map((c) => m.daScegliereCategoria(c.needsReview, c.categoria)));",
        argomento=casi,
        richiede=["daScegliereCategoria"],
    )
    assert ts == [c["atteso"] for c in casi]


def test_nessun_file_riderivà_la_divisione_fb_generali():
    """La guardia che impedisce a F1 di riformarsi.

    Il fix ha unificato quattro copie in una fonte sola. Senza guardia nulla
    vieta a un quinto file di ricostruire la lista a mano, ed e' esattamente
    cosi' che il difetto era nato.

    Cerca la **divisione**, non le stringhe: un file che nomina qualche
    categoria non e' un difetto (`admin.ts` tiene le 29 canoniche,
    `analisi-fatture/periodi.ts` una mappa di icone, `demo-data.ts` righe
    finte). Il difetto e' un file che raggruppa proprio le 4 spese generali
    per decidere un secchio: quella e' la copia che diverge e sposta soldi
    nel MOL.
    """
    modulo = (WEB_SRC / f"{MODULO}.ts").resolve()
    colpevoli = {}
    for f in WEB_SRC.rglob("*.ts*"):
        if f.resolve() == modulo:
            continue
        testo = f.read_text(encoding="utf-8")
        # Un raggruppamento = le 4 stringhe dentro la stessa parentesi quadra
        # o graffa (array, Set, unione di tipi), non sparse per il file.
        fb = [c for c in TUTTE_LE_CATEGORIE if c not in set(CATEGORIE_SPESE_GENERALI)]
        # Finestra fra la prima e l'ultima delle 4 stringhe, invece di un blocco
        # fra parentesi: il code-reviewer ha mostrato che la versione con le
        # parentesi non vedeva ne' un array di oggetti (`[{k: "..."}, ...]`) ne'
        # una union di tipi (`"..." | "..."`), perche' non attraversa
        # l'annidamento. Qui conta solo che le 4 stiano vicine e sole.
        if not all(c in testo for c in CATEGORIE_SPESE_GENERALI):
            continue
        # Un file che nomina ANCHE le F&B tiene la lista completa delle canoniche
        # (admin.ts) o una mappa su tutte (periodi.ts): non ricostruisce nessuna
        # divisione. Il difetto e' avere solo le 4, cioe' il gruppo isolato.
        if any(c in testo for c in fb):
            continue
        posizioni = [testo.find(f'"{c}"') for c in CATEGORIE_SPESE_GENERALI]
        posizioni += [testo.find(f"'{c}'") for c in CATEGORIE_SPESE_GENERALI]
        trovate = [p for p in posizioni if p != -1]
        finestra = testo[min(trovate):max(trovate) + 60]
        colpevoli[str(f.relative_to(WEB_SRC))] = " ".join(finestra.split())[:90]

    assert not colpevoli, (
        "questi file ricostruiscono la divisione FB/generali e divergeranno "
        f"da {MODULO}.ts: importa SPESE_GENERALI_SET invece di ricopiarla.\n"
        + "\n".join(f"  {k}: {v}" for k, v in colpevoli.items())
    )
