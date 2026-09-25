"""La pagina Gestione Fatture inizia come le altre: ricerca, filtri, numeri.

Confrontando la pagina con Margini e Analisi Fatture, lo scostamento estetico
piu' visibile non era un colore — la pagina non ha una sola classe di palette
grezza e passa `test_colori_solo_token_frontend.py` — ma **dove stanno i
filtri**: una card grigia a meta' schermo, dopo la toolbar e il cestino, mentre
le altre pagine hanno `filtri-periodo.tsx` subito sotto il titolo. L'occhio non
trovava l'ancora che trova altrove.

**Cosa prova questo presidio, e cosa no.** E' un assert sull'ORDINE dei
marcatori nel sorgente: CLAUDE.md avverte giustamente che un test sul testo del
sorgente e' debole, e questo non fa eccezione — non prova che il layout sia
bello, ne' che i filtri siano leggibili, ne' che la pagina renda. Prova una cosa
sola, ed e' la regressione concreta: che qualcuno rimetta i filtri in fondo
senza accorgersene. La prova vera e' aprire la pagina.

Lo tengo perche' il blocco filtri e' 215 righe in un file da 2.700: uno
spostamento accidentale durante un altro lavoro non si nota rileggendo il diff.
"""
from pathlib import Path

import pytest

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)

# I marcatori sono i commenti di sezione del render, nell'ordine atteso.
ORDINE = [
    "{/* Ricerca — il primo gesto",
    "{/* Filtri — in cima",
    "{/* KPI bar",
    "{/* Toolbar */}",
    "{/* Content */}",
]


@pytest.fixture(scope="module")
def sorgente() -> str:
    assert CLIENT.exists(), f"{CLIENT} non esiste: se e' stato rinominato aggiorna il test"
    return CLIENT.read_text(encoding="utf-8")


def test_i_blocchi_sono_nell_ordine_delle_altre_pagine(sorgente: str):
    posizioni = []
    for marcatore in ORDINE:
        idx = sorgente.find(marcatore)
        assert idx != -1, (
            f"marcatore sparito dal sorgente: {marcatore!r}. Se il blocco e' stato "
            "rinominato aggiorna la lista, se e' stato rimosso valuta se il test "
            "ha ancora senso."
        )
        posizioni.append((marcatore, idx))

    for (nome_a, pos_a), (nome_b, pos_b) in zip(posizioni, posizioni[1:]):
        assert pos_a < pos_b, (
            f"{nome_a!r} deve venire prima di {nome_b!r}: la pagina inizia con "
            "ricerca e filtri, come Margini e Analisi Fatture"
        )


def test_i_filtri_non_sono_piu_una_card_isolata(sorgente: str):
    """Erano `rounded-lg border bg-card p-3`: un riquadro a se' in mezzo alla
    pagina. Nelle altre pagine i filtri sono una riga di controlli, non una card."""
    inizio = sorgente.find("{/* Filtri — in cima")
    assert inizio != -1
    apertura = sorgente[inizio:inizio + 400]
    assert 'className="rounded-lg border bg-card p-3' not in apertura, (
        "il blocco filtri e' tornato a essere una card isolata"
    )
