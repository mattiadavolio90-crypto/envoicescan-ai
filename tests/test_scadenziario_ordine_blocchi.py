"""Gestione Fatture: le card in cima, poi le viste, poi TUTTI i filtri insieme.

**Decisione del 29/9 (Mattia), che rovescia quella sotto.** Con ricerca e filtri
sopra le card e la barra delle viste sotto, la pagina aveva controlli sia sopra
sia sotto i quattro numeri: «molto confusionario». Ora l'ordine e': card, barra
delle viste e delle azioni, un solo blocco di filtri (ricerca, una riga di
scelte, il conteggio), l'elenco. In catena il filtro per punto vendita e' una
tendina a scelta multipla, non piu' una riga di pillole.

La motivazione precedente, tenuta per storia:

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
    "{/* KPI bar",
    "{/* Toolbar */}",
    "{/* Filtri — sotto le card",
    "{/* Ricerca — il primo gesto",
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
            f"{nome_a!r} deve venire prima di {nome_b!r}: card, viste, poi un "
            "solo blocco di filtri sopra l'elenco (Mattia, 29/9)"
        )


def test_i_filtri_non_sono_piu_una_card_isolata(sorgente: str):
    """Erano `rounded-lg border bg-card p-3`: un riquadro a se' in mezzo alla
    pagina. Nelle altre pagine i filtri sono una riga di controlli, non una card."""
    inizio = sorgente.find("{/* Filtri — sotto le card")
    assert inizio != -1
    apertura = sorgente[inizio:inizio + 400]
    assert 'className="rounded-lg border bg-card p-3' not in apertura, (
        "il blocco filtri e' tornato a essere una card isolata"
    )


def test_nessun_filtro_sopra_le_card(sorgente: str):
    """I controlli che restringono l'elenco stanno tutti nel blocco filtri: uno
    rimasto sopra le card rifa' le due barre che Mattia ha tolto il 29/9."""
    kpi = sorgente.find("{/* KPI bar")
    inizio_render = sorgente.find('<div className="space-y-5 pb-20">')
    assert -1 < inizio_render < kpi
    sopra = sorgente[inizio_render:kpi]
    for controllo in ("ricercaRef", "setFiltroPeriodo", "FornitoreMultiSelect",
                      "PuntoVenditaMultiSelect", "setFiltroSoloNuove"):
        assert controllo not in sopra, f"{controllo} e' di nuovo sopra le card"


def test_il_filtro_punti_vendita_e_la_tendina_multipla(sorgente: str):
    """La tendina scrive `filtroSede` e l'elenco lo legge con `inPuntiVendita`
    (logica provata in test_scadenziario_punti_vendita_frontend.py): senza uno
    dei due capi la tendina si spunta e l'elenco non cambia."""
    import re
    assert re.search(
        r"<PuntoVenditaMultiSelect\s+sedi=\{kpiPerSede\}\s+selected=\{filtroSede\}\s+onChange=\{setFiltroSede\}",
        sorgente,
    ), "la tendina dei punti vendita non e' piu' collegata a filtroSede"
    corpo = re.search(r"function matchFiltroSede\(d: Documento\): boolean \{(.*?)\n  \}", sorgente, re.S)
    assert corpo, "matchFiltroSede non c'e' piu'"
    assert "inPuntiVendita(d.ristorante_id, filtroSede)" in corpo.group(1)
    assert "setFiltroSede(f => f === value" not in sorgente, "sono tornate le pillole a scelta singola"
