"""Una fattura esclusa dai conti sparisce dai numeri e resta nell'elenco.

Perche' esiste
==============
"Escludi dai conti" e' inutile se il cliente la esclude e continua a vederla nei
KPI in cima alla pagina: significherebbe due verita' diverse sullo stesso
documento nella stessa schermata. Il filtro va applicato in QUATTRO punti di
`lib/scadenziario.ts` (`computeKpi`, `bucketizeDocumenti`, `buildCashFlow`,
`aggregaPerSede`) piu' `statoDocumento`, che decide anche cosa scrive il CSV
scaricato. Dimenticarne uno non rompe niente: cambia solo un numero.

Perche' le fixture hanno importo != 0 e scadenza SCADUTA
========================================================
Provato per mutazione: con un documento a importo zero, o senza scadenza,
`scadute_totale` resta 0 sia prima che dopo l'esclusione e il test e' verde
anche se il filtro non c'e'. La riga esclusa deve valere qualcosa in OGNI
aggregato che si misura, o non misura niente.

Perche' due fusi
================
Stessa ragione del file KPI fratello: le fixture sono costruite su date relative
a "oggi", e "oggi" a ovest di Greenwich non e' lo stesso giorno. Un test scritto
solo su Europe/Rome nasconde la classe di difetto di fuso gia' corretta due
volte in questo modulo.
"""
import datetime

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

FUSI = ["Europe/Rome", "America/Los_Angeles"]


def _doc(**kw):
    base = {
        "id": kw.get("id", "x"),
        "file_origine": kw.get("file_origine", "a.xml"),
        "fornitore": "F",
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": 100.0,
        "data_documento": None,
        "numero_documento": None,
        "scadenza_effettiva": None,
        "scadenza_source": None,
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "oscurata": False,
    }
    base.update(kw)
    return base


def _oggi_in(tz):
    iso = esegui_ts(
        MODULO,
        "const d = new Date();"
        "emit([d.getFullYear(), d.getMonth() + 1, d.getDate()]);",
        tz=tz,
    )
    return datetime.date(*iso)


def _coppia(tz):
    """Due documenti IDENTICI e scaduti, uno escluso dai conti.

    Scaduti e con importo: cosi' ogni aggregato misurato (scadute, da pagare,
    cash-flow, per-sede) e' diverso da zero prima dell'esclusione — e il
    dimezzamento e' visibile.
    """
    scaduta = (_oggi_in(tz) - datetime.timedelta(days=10)).isoformat()
    return [
        _doc(id="1", file_origine="a.xml", scadenza_effettiva=scaduta,
             ristorante_id="sede-1"),
        _doc(id="2", file_origine="b.xml", scadenza_effettiva=scaduta,
             ristorante_id="sede-1", oscurata=True),
    ]


@pytest.mark.parametrize("tz", FUSI)
def test_i_kpi_ignorano_le_fatture_fuori_dai_conti(tz):
    """L'esclusa non e' ne' un debito ne' una scadenza: esce da tutti i KPI."""
    kpi = esegui_ts(
        MODULO, "emit(m.computeKpi(input));", argomento=_coppia(tz), tz=tz,
        richiede=["computeKpi"],
    )
    assert kpi["scadute_count"] == 1
    assert kpi["scadute_totale"] == pytest.approx(100.0)
    assert kpi["da_pagare_count"] == 1
    assert kpi["da_pagare_totale"] == pytest.approx(100.0)


@pytest.mark.parametrize("tz", FUSI)
def test_il_cash_flow_ignora_le_fatture_fuori_dai_conti(tz):
    """La barra dell'esposizione futura conta solo debiti veri."""
    fasce = esegui_ts(
        MODULO, "emit(m.buildCashFlow(input));", argomento=_coppia(tz), tz=tz,
        richiede=["buildCashFlow"],
    )
    scadute = next(f for f in fasce if f["label"] == "Scadute")
    assert scadute["count"] == 1
    assert scadute["totale"] == pytest.approx(100.0)


@pytest.mark.parametrize("tz", FUSI)
def test_il_totale_per_sede_ignora_le_fatture_fuori_dai_conti(tz):
    """Il KPI per-sede della catena non somma cio' che e' escluso."""
    per_sede = esegui_ts(
        MODULO,
        "emit(Object.fromEntries(m.aggregaPerSede(input, "
        "{periodo: 'tutti', fornitori: [], soloNuove: false})));",
        argomento=_coppia(tz), tz=tz, richiede=["aggregaPerSede"],
    )
    assert per_sede["sede-1"]["count"] == 1
    assert per_sede["sede-1"]["totale"] == pytest.approx(100.0)


@pytest.mark.parametrize("tz", FUSI)
def test_l_esclusa_resta_in_elenco_in_una_sezione_sua(tz):
    """Non sparisce come il cestino: finisce nel bucket `oscurate`, e in UNO solo.

    Il conteggio totale dei bucket deve restare pari ai documenti in ingresso: un
    documento che comparisse in due sezioni (o in nessuna) sarebbe un elenco che
    mente sul proprio totale.
    """
    conteggi = esegui_ts(
        MODULO,
        "emit(Object.fromEntries(Object.entries(m.bucketizeDocumenti(input))"
        ".map(([k, v]) => [k, v.length])));",
        argomento=_coppia(tz), tz=tz, richiede=["bucketizeDocumenti"],
    )
    assert conteggi["oscurate"] == 1
    assert conteggi["scadute"] == 1
    assert sum(conteggi.values()) == 2


@pytest.mark.parametrize("tz", FUSI)
def test_l_esclusione_vince_su_nota_di_credito_e_pagata(tz):
    """Precedenza: `oscurata` PRIMA di NC e pagata, in bucket e in stato.

    Se `is_nota_credito` fosse valutato per primo, una NC esclusa finirebbe nella
    sezione note di credito E fuori dai conti: due posti per un documento solo.
    `statoDocumento` deve seguire la stessa precedenza, perche' e' cio' che
    scrive il CSV scaricato (lo impone il commento nel modulo).
    """
    docs = [
        _doc(id="1", file_origine="nc.xml", is_nota_credito=True, oscurata=True),
        _doc(id="2", file_origine="pg.xml", pagata=True, oscurata=True),
    ]
    conteggi = esegui_ts(
        MODULO,
        "emit(Object.fromEntries(Object.entries(m.bucketizeDocumenti(input))"
        ".map(([k, v]) => [k, v.length])));",
        argomento=docs, tz=tz, richiede=["bucketizeDocumenti"],
    )
    assert conteggi["oscurate"] == 2
    assert conteggi["noteCredito"] == 0
    assert conteggi["pagate"] == 0

    stati = esegui_ts(
        MODULO, "emit(input.map((d) => m.statoDocumento(d)));",
        argomento=docs, tz=tz, richiede=["statoDocumento"],
    )
    assert stati == ["Fuori dai conti", "Fuori dai conti"]


@pytest.mark.parametrize("tz", FUSI)
def test_senza_il_campo_il_documento_conta_come_prima(tz):
    """Compatibilita': un worker che non manda ancora `oscurata` non deve
    cambiare nulla. Il campo e' opzionale, non un booleano obbligatorio."""
    scaduta = (_oggi_in(tz) - datetime.timedelta(days=10)).isoformat()
    doc = _doc(id="1", scadenza_effettiva=scaduta)
    del doc["oscurata"]
    kpi = esegui_ts(
        MODULO, "emit(m.computeKpi(input));", argomento=[doc], tz=tz,
        richiede=["computeKpi"],
    )
    assert kpi["scadute_count"] == 1
