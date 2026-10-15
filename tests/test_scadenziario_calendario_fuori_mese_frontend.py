"""Il calendario dichiara le scadute che non sta mostrando.

Perche' esiste
==============
Il calendario mostra UN mese alla volta e disegna una casella solo per le
scadenze che cadono dentro quel mese. E' corretto, ma su una sede reale le
scadute erano 414 sparse su SEI mesi diversi (Villa Guardia, misurato il
16/09/2026): nessun mese potra' mai mostrarle insieme, per costruzione.

Il cliente leggeva "641.555 € scaduti" nei riquadri in cima e sotto vedeva una
griglia quasi vuota — i due numeri non si contraddicono, ma la pagina non lo
spiegava. Da qui l'impressione, riportata dall'audit, che "non ci sia niente da
pagare" proprio mentre c'e' mezzo milione in ritardo.

`scaduteFuoriDalMese` conta cio' che resta fuori dalla finestra visualizzata,
cosi' la vista puo' dirlo invece di tacere.

Cosa NON deve fare
==================
Contare due volte cio' che e' gia' a schermo: una scaduta che cade nel mese
mostrato ha gia' la sua casella. Il test sul confine (ultimo giorno del mese
precedente vs primo del mese mostrato) e' li' per quello, e usa un fuso a ovest
di Greenwich perche' `parseLocalDate` su ISO puo' spostare il giorno.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

FUSI = ["Europe/Rome", "America/Los_Angeles"]

# "Oggi" fisso: il conteggio dipende da cosa e' gia' scaduto, non dal giorno in
# cui gira la suite.
OGGI = "2026-06-15T12:00:00"


def _doc(file_origine, scadenza, **kw):
    base = {
        "id": file_origine,
        "file_origine": file_origine,
        "fornitore": "F",
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": 100.0,
        "data_documento": "2026-01-10",
        "numero_documento": None,
        "scadenza_effettiva": scadenza,
        "scadenza_source": None,
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "oscurata": False,
    }
    base.update(kw)
    return base


def _fuori(documenti, anno, mese, tz):
    """mese e' 0-based come nel componente (Date.getMonth())."""
    return esegui_ts(
        MODULO,
        f"emit(m.scaduteFuoriDalMese(input, {anno}, {mese}, new Date('{OGGI}')));",
        argomento=documenti,
        tz=tz,
        richiede=["scaduteFuoriDalMese", "statoDocumento"],
    )


@pytest.mark.parametrize("tz", FUSI)
def test_le_scadute_dei_mesi_precedenti_sono_contate(tz):
    """Il caso reale: si guarda giugno, le scadute stanno in marzo e aprile."""
    docs = [_doc("a.xml", "2026-03-27"), _doc("b.xml", "2026-04-10")]
    r = _fuori(docs, 2026, 5, tz)  # 5 = giugno
    assert r["count"] == 2
    assert r["totale"] == 200.0


@pytest.mark.parametrize("tz", FUSI)
def test_una_scaduta_dentro_il_mese_mostrato_non_si_conta_due_volte(tz):
    """Ha gia' la sua casella nella griglia."""
    docs = [_doc("dentro.xml", "2026-06-02")]
    assert _fuori(docs, 2026, 5, tz)["count"] == 0


@pytest.mark.parametrize("tz", FUSI)
def test_il_confine_fra_due_mesi(tz):
    """31 maggio e 1 giugno: il primo e' fuori, il secondo dentro. E' il caso
    dove `new Date(iso)` a ovest di Greenwich sposterebbe il giorno."""
    docs = [_doc("maggio.xml", "2026-05-31"), _doc("giugno.xml", "2026-06-01")]
    assert _fuori(docs, 2026, 5, tz)["count"] == 1


@pytest.mark.parametrize("tz", FUSI)
def test_le_future_non_sono_scadute(tz):
    """Una scadenza di agosto, guardando giugno, non e' in ritardo: e' futura."""
    assert _fuori([_doc("ago.xml", "2026-08-01")], 2026, 5, tz)["count"] == 0


@pytest.mark.parametrize("tz", FUSI)
def test_pagate_note_di_credito_e_oscurate_restano_fuori(tz):
    """Gli stessi tre esclusi del calendario e dei KPI: se entrassero qui, la
    frase direbbe un numero che nessuna altra parte della pagina conferma."""
    docs = [
        _doc("pagata.xml", "2026-03-01", pagata=True),
        _doc("nc.xml", "2026-03-01", is_nota_credito=True),
        _doc("osc.xml", "2026-03-01", oscurata=True),
    ]
    assert _fuori(docs, 2026, 5, tz)["count"] == 0


@pytest.mark.parametrize("tz", FUSI)
def test_senza_scadenza_non_conta(tz):
    assert _fuori([_doc("x.xml", None)], 2026, 5, tz)["count"] == 0


@pytest.mark.parametrize("tz", FUSI)
def test_nessuna_scaduta_da_zero(tz):
    """Zero e' il segnale che la frase non va mostrata affatto."""
    r = _fuori([], 2026, 5, tz)
    assert r["count"] == 0 and r["totale"] == 0


@pytest.mark.parametrize("tz", FUSI)
def test_il_conteggio_concorda_con_statoDocumento(tz):
    """L'invariante: cio' che si conta e' esattamente cio' che `statoDocumento`
    chiama "Scaduta" e che cade fuori dal mese mostrato. Se un giorno cambiasse
    la precedenza degli stati, le due funzioni restano allineate senza toccare
    questo file."""
    docs = [
        _doc("m3.xml", "2026-03-27"),
        _doc("m4.xml", "2026-04-10"),
        _doc("dentro.xml", "2026-06-02"),
        _doc("futura.xml", "2026-08-01"),
        _doc("pagata.xml", "2026-03-01", pagata=True),
        _doc("nc.xml", "2026-03-01", is_nota_credito=True),
        _doc("osc.xml", "2026-03-01", oscurata=True),
        _doc("nulla.xml", None),
    ]
    atteso = esegui_ts(
        MODULO,
        f"""
        const oggi = new Date('{OGGI}');
        emit(input.filter((d) => {{
          if (m.statoDocumento(d, oggi) !== "Scaduta") return false;
          const s = m.parseLocalDate(d.scadenza_effettiva);
          return !!s && !(s.getFullYear() === 2026 && s.getMonth() === 5);
        }}).length);
        """,
        argomento=docs,
        tz=tz,
        richiede=["statoDocumento", "parseLocalDate"],
    )
    assert _fuori(docs, 2026, 5, tz)["count"] == atteso
    assert atteso == 2


@pytest.mark.parametrize("tz", FUSI)
def test_lo_stesso_mese_di_un_anno_diverso_e_fuori(tz):
    """Giugno 2025 non e' giugno 2026.

    Il mutante che confrontava solo `getMonth()` ignorando l'anno sopravviveva a
    tutti gli altri casi: le fixture stavano tutte nel 2026. Su un cliente con
    storico di piu' anni la frase avrebbe detto un numero piu' basso del vero,
    tacendo proprio le scadute piu' vecchie.
    """
    docs = [_doc("vecchia.xml", "2025-06-10")]
    assert _fuori(docs, 2026, 5, tz)["count"] == 1


# ── La griglia e la lista del giorno ────────────────────────────────────────
#
# Fino all'audit di ottobre 2026 la griglia saltava solo pagate e note di
# credito: una fattura esclusa dai conti con scadenza nel mese entrava nel totale
# del giorno, mentre le card sopra e l'endpoint del worker la escludevano.


def _mese_giugno():
    return [
        _doc("osc.xml", "2026-06-21", oscurata=True, totale_documento=500.0),
        _doc("osc-scaduta.xml", "2026-06-03", oscurata=True, totale_documento=40.0),
        _doc("ok.xml", "2026-06-23", totale_documento=1100.0),
        _doc("ok2.xml", "2026-06-23", totale_documento=300.0),
        _doc("scaduta.xml", "2026-06-05", totale_documento=200.0),
        _doc("pagata.xml", "2026-06-23", pagata=True, totale_documento=50.0),
        _doc("nc.xml", "2026-06-23", is_nota_credito=True, totale_documento=70.0),
        _doc("luglio.xml", "2026-07-02", totale_documento=900.0),
    ]


@pytest.mark.parametrize("tz", FUSI)
def test_la_griglia_conta_solo_le_scadenze_da_pagare_del_mese(tz):
    agg = esegui_ts(
        MODULO,
        f"emit(m.aggregaCalendario(input, 2026, 5, new Date('{OGGI}')));",
        argomento=_mese_giugno(),
        tz=tz,
        richiede=["aggregaCalendario"],
    )
    assert agg == {"5": {"totale": 200, "count": 1}, "23": {"totale": 1400, "count": 2}}


@pytest.mark.parametrize("tz", FUSI)
def test_la_lista_del_mese_esclude_le_fatture_escluse_dai_conti(tz):
    docs = esegui_ts(
        MODULO,
        f"emit(m.scadenzeDelMese(input, 2026, 5, new Date('{OGGI}')).map(d => d.file_origine));",
        argomento=_mese_giugno(),
        tz=tz,
        richiede=["scadenzeDelMese"],
    )
    assert sorted(docs) == ["ok.xml", "ok2.xml", "scaduta.xml"]


def test_griglia_e_lista_del_giorno_usano_le_funzioni_della_lib():
    from pathlib import Path

    sorgente = (
        Path(__file__).resolve().parent.parent
        / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
    ).read_text(encoding="utf-8")
    inizio = sorgente.index("function CalendarView(")
    corpo = sorgente[inizio:sorgente.index("\nfunction ", inizio + 1)]
    assert "useMemo(() => aggregaCalendario(documenti, anno, mese)" in corpo
    assert "return scadenzeDelMese(documenti, anno, mese)" in corpo
    assert "if (doc.pagata) continue;" not in corpo
    assert "if (d.pagata) return false;" not in corpo
