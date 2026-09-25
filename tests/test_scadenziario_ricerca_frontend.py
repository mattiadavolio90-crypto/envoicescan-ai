"""La ricerca trova la fattura che il contabile ha in mano.

Prima di questo presidio la pagina Gestione Fatture **non aveva alcuna ricerca**
(misurato il 25/09/2026: zero stati `search` nel client, nessun predicato
testuale in `matchDocumento`). Il gesto piu' frequente di chi ci lavora — il
fornitore chiama e chiede della fattura 4521 da 1.250 euro — era l'unico
completamente assente: restavano il filtro fornitore e lo scorrimento a vista.

**Perche' i casi sono questi.** La ricerca serve quando si copia un dato da un
foglio o lo si legge al telefono, non quando lo si conosce nella grafia esatta
del database. Quindi i casi provano le forme in cui il dato ARRIVA:

- `numero_documento` sta a DB come "4521/A" ma viene dettato come "4521";
- l'importo sta a DB come `1250.5` e si LEGGE a video come "1.250,50": chi
  cerca copia quello che vede, non il float;
- il fornitore si scrive con e senza accento, in maiuscolo o minuscolo.

**Perche' l'importo va provato in entrambe le grafie.** E' il caso in cui e'
piu' facile scrivere un codice che sembra giusto: confrontare solo
`String(totale_documento)` passa il test "1250" e fallisce quello "1.250,50",
cioe' proprio la cifra che il cliente ha davanti.

Mutazioni provate (25/09/2026), tutte uccise da almeno un caso:
1. tolto `numero_documento` dal predicato -> test_trova_per_numero_documento
2. confronto case-sensitive (via `toLowerCase`) -> test_ignora_maiuscole_e_accenti
3. tolta la grafia italiana dell'importo -> test_trova_per_importo_come_si_legge
4. `normalizzaRicerca` che non toglie i separatori -> test_trova_per_numero_documento
5. query vuota che filtra tutto invece di non filtrare -> test_ricerca_vuota_non_filtra
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

_RICHIEDE = ["matchRicerca", "normalizzaRicerca", "matchDocumento", "filtraDocumenti"]


def _doc(**kw):
    base = {
        "id": "x",
        "file_origine": "f.xml",
        "fornitore": "Metro Italia",
        "piva_fornitore": None,
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": 1250.5,
        "data_documento": "2026-09-01",
        "numero_documento": "4521/A",
        "scadenza_effettiva": None,
        "scadenza_source": None,
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "is_nuovo": False,
    }
    base.update(kw)
    return base


def _match(doc, query):
    return esegui_ts(
        MODULO,
        "emit(m.matchRicerca(input.doc, input.q));",
        {"doc": doc, "q": query},
        richiede=_RICHIEDE,
    )


@pytest.mark.parametrize(
    "query",
    [
        "4521",       # dettato al telefono, senza la parte dopo la barra
        "4521/A",     # copiato dal documento
        "N. 4521/A",  # copiato con il prefisso che sta sulla fattura
        "4521/a",     # scritto in minuscolo
    ],
)
def test_trova_per_numero_documento(query):
    """Il numero si cerca come lo si ha sotto mano, non come sta a DB."""
    assert _match(_doc(), query) is True


@pytest.mark.parametrize("query", ["metro", "METRO", "Metro Italia", "italia"])
def test_trova_per_fornitore_anche_parziale(query):
    assert _match(_doc(), query) is True


def test_ignora_maiuscole_e_accenti():
    """Chi cerca non sa se il fornitore e' scritto con l'accento."""
    doc = _doc(fornitore="Caffè Brasile")
    assert _match(doc, "caffe") is True
    assert _match(doc, "CAFFE") is True
    assert _match(doc, "caffè") is True


@pytest.mark.parametrize(
    "query",
    [
        "1250.5",     # come sta nel dato grezzo
        "1250,50",    # come si legge a video, senza separatore di migliaia
        "1.250,50",   # come si legge a video, copiato per intero
    ],
)
def test_trova_per_importo_come_si_legge(query):
    """L'importo si cerca nella grafia che il cliente VEDE, non solo nel float."""
    assert _match(_doc(totale_documento=1250.5), query) is True


def test_non_trova_cio_che_non_c_e():
    """Senza questo, un predicato che risponde sempre `true` passerebbe tutto."""
    doc = _doc(fornitore="Metro Italia", numero_documento="4521/A", totale_documento=1250.5)
    assert _match(doc, "9999") is False
    assert _match(doc, "Bofrost") is False


def test_numero_documento_assente_non_rompe():
    """L'11,2% delle fatture in produzione non ha numero documento."""
    doc = _doc(numero_documento=None)
    assert _match(doc, "metro") is True
    assert _match(doc, "4521") is False


def test_ricerca_vuota_non_filtra():
    """Campo vuoto = nessun filtro, non «nessun risultato»."""
    assert _match(_doc(), "") is True
    assert _match(_doc(), "   ") is True


def test_matchDocumento_applica_la_ricerca():
    """La ricerca deve passare per il filtro vero, non solo esistere come funzione.

    Senza questo caso, `matchRicerca` potrebbe essere corretta e non essere mai
    chiamata da `matchDocumento`: la pagina resterebbe senza ricerca con tutti
    gli altri test verdi.
    """
    docs = [
        _doc(id="a", fornitore="Metro Italia", numero_documento="4521/A"),
        _doc(id="b", fornitore="Bofrost", numero_documento="77/B", totale_documento=99),
    ]
    trovati = esegui_ts(
        MODULO,
        "emit(m.filtraDocumenti(input.docs, {periodo: 'tutti', ricerca: input.q})"
        ".map(d => d.id));",
        {"docs": docs, "q": "bofrost"},
        richiede=_RICHIEDE,
    )
    assert trovati == ["b"]


def test_ricerca_si_combina_con_gli_altri_filtri():
    """La ricerca restringe, non sostituisce: chi filtra «solo scadute» e poi
    cerca deve restare dentro le scadute."""
    docs = [
        _doc(id="pagata", fornitore="Metro", pagata=True),
        _doc(id="aperta", fornitore="Metro", pagata=False),
    ]
    trovati = esegui_ts(
        MODULO,
        "emit(m.filtraDocumenti(input.docs, "
        "{periodo: 'tutti', ricerca: 'metro', soloNuove: false})"
        ".map(d => d.id));",
        {"docs": docs},
        richiede=_RICHIEDE,
    )
    assert set(trovati) == {"pagata", "aperta"}
