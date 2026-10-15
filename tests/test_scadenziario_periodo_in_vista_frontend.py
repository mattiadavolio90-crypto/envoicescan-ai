"""Il filtro periodo vale solo nello Scadenzario; «Pagate (mese)» non lo subisce.

Perche' esiste
==============
Audit di ottobre 2026, tre difetti dello stesso pezzo di pagina:

- in Calendario le card e i chip di periodo restavano accesi e filtravano le
  card, ma il calendario li ignorava (due numeri diversi sullo stesso schermo);
- in Archivio il chip «Solo scadute» restava attivabile e non cambiava l'elenco,
  le checkbox di riga non facevano niente e la barra delle azioni di massa
  restava a video con una selezione fatta nello Scadenzario;
- con «Scadute» attivo la card «Pagate (mese)» diceva 0 €: il filtro periodo
  scarta ogni pagata, e l'etichetta non diceva «(filtro)».

Le guardie sul sorgente coprono il cablaggio del .tsx (il rendering non ha un
runner); la logica sta in `lib/scadenziario.ts` ed e' eseguita con node.
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
FUSI = ["Europe/Rome", "America/Los_Angeles"]
CLIENT = (
    Path(__file__).resolve().parent.parent
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


def _doc(file_origine, **kw):
    base = {
        "id": file_origine,
        "file_origine": file_origine,
        "fornitore": kw.pop("fornitore", "F"),
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": 100.0,
        "data_documento": "2026-01-10",
        "numero_documento": None,
        "scadenza_effettiva": "2026-01-10",
        "scadenza_source": None,
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "oscurata": False,
    }
    base.update(kw)
    return base


@pytest.mark.parametrize(
    "view,periodo,atteso",
    [
        ("agenda", "scadute", "scadute"),
        ("agenda", "personalizzato", "personalizzato"),
        ("calendario", "scadute", "tutti"),
        ("calendario", "settimana", "tutti"),
        ("lista_mensile", "scadute", "tutti"),
        ("lista_mensile", "personalizzato", "tutti"),
    ],
)
def test_il_periodo_vale_solo_nello_scadenzario(view, periodo, atteso):
    out = esegui_ts(
        MODULO,
        "emit(m.periodoInVista(input.view, input.periodo));",
        {"view": view, "periodo": periodo},
        richiede=["periodoInVista"],
    )
    assert out == atteso


def _pagate(docs, filtri, tz):
    # La pagata e' di oggi, letto nel fuso del test: e' "questo mese" ovunque.
    return esegui_ts(
        MODULO,
        "for (const d of input.docs) if (d.pagata) d.pagata_at = m.todayLocalIso();"
        "emit(m.pagateDelMese(input.docs, input.filtri));",
        {"docs": docs, "filtri": filtri},
        tz=tz,
        richiede=["pagateDelMese", "todayLocalIso"],
    )


@pytest.mark.parametrize("tz", FUSI)
@pytest.mark.parametrize("periodo", ["scadute", "settimana", "mese", "personalizzato"])
def test_pagate_del_mese_non_subisce_il_periodo(tz, periodo):
    docs = [
        _doc("pagata.xml", pagata=True, totale_documento=250.0),
        _doc("pagata2.xml", pagata=True, totale_documento=50.0),
        _doc("scaduta.xml"),
    ]
    filtri = {"periodo": periodo, "fornitori": [], "dataDa": "2020-01-01", "dataA": "2020-01-02"}
    assert _pagate(docs, filtri, tz) == {"count": 2, "totale": 300}


@pytest.mark.parametrize("tz", FUSI)
def test_pagate_del_mese_segue_gli_altri_filtri(tz):
    docs = [
        _doc("a.xml", fornitore="Alfa", pagata=True, totale_documento=250.0),
        _doc("b.xml", fornitore="Beta", pagata=True, totale_documento=50.0),
    ]
    filtri = {"periodo": "scadute", "fornitori": [], "ricerca": ""}
    chiave = esegui_ts(
        MODULO, "emit(m.fornitoreKey(input));", docs[1], richiede=["fornitoreKey"],
    )
    filtri["fornitori"] = [chiave]
    assert _pagate(docs, filtri, tz) == {"count": 1, "totale": 50}


# ── Cablaggio nel client ────────────────────────────────────────────────────


def _sorgente():
    return CLIENT.read_text(encoding="utf-8")


def _corpo(sorgente, firma):
    inizio = sorgente.index(firma)
    return sorgente[inizio:sorgente.index("\nfunction ", inizio + 1)]


def test_i_filtri_comuni_usano_il_periodo_della_vista():
    s = _sorgente()
    assert "const periodo = periodoInVista(view, filtroPeriodo);" in s
    assert re.search(r"const filtriComuni = useMemo\(\(\) => \(\{\s*periodo,", s)
    assert re.search(r"const filtriAttivi = periodo !== \"tutti\" \|\| filtriNonPeriodo;", s)
    assert "{periodo === \"personalizzato\" && (" in s


def test_la_card_pagate_usa_pagate_del_mese_e_dichiara_il_filtro():
    s = _sorgente()
    assert "pagateDelMese(documenti, filtriComuni, matchFiltroSede)" in s
    card = re.search(r"<KpiCard label=\{([^}]*)\} count=\{pagate\.count\} totale=\{pagate\.totale\}", s)
    assert card, "la card Pagate deve leggere pagateDelMese"
    assert card.group(1) == 'filtriNonPeriodo ? "Pagate (mese, filtro)" : "Pagate (mese)"'
    assert "kpi.pagate_mese_count" not in s


def test_card_e_chip_di_periodo_solo_nello_scadenzario():
    s = _sorgente()
    assert s.count('onClick={view === "agenda" ? ') == 3
    assert s.count('items-center gap-1.5 ${view === "agenda" ? "flex" : "hidden"}') == 2


def test_in_archivio_niente_selezione():
    s = _sorgente()
    riga = _corpo(s, "function DocumentoRow(")
    assert re.search(r"\{mostraScadenze && \(\s*<input\s+type=\"checkbox\"", riga)
    sezione = _corpo(s, "function AgendaSection(")
    assert "selected={mostraScadenze && selectedFileOrigini.has(chiaveDocumento(doc))}" in sezione
    assert "{mostraScadenze && selectedCount > 0 && (" in sezione
    assert "{view === \"agenda\" && selectedFileOrigini.size > 0 && (" in s
