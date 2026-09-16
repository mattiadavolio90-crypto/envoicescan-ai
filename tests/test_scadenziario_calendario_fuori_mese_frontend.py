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
