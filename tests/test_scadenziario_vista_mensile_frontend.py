"""La vista "Per mese" non perde fatture e non le mette nel mese sbagliato.

Perche' esiste
==============
`raggruppaPerMeseFattura` decide cosa il cliente vede nella terza vista di
Gestione Fatture. Due difetti possibili, entrambi invisibili:

1. **Righe che spariscono.** `data_documento` e' nullable sul DB. Scartare le
   fatture senza data farebbe un elenco piu' corto della vista Lista, senza un
   errore: il cliente non ha modo di sapere che ne mancano. L'invariante
   "somma dei count == documenti in ingresso" e' cio' che lo impedisce.

2. **Il mese sbagliato.** `new Date("2026-03-01")` e' mezzanotte UTC: a ovest di
   Greenwich cade il 28 febbraio, e la fattura del primo del mese finisce nel
   mese precedente. E' il difetto gia' corretto due volte in questo modulo
   (righe 78 e 112), e si vede SOLO in un fuso a ovest — per questo i test
   girano anche su America/Los_Angeles, che non e' un fuso a caso.

Le fixture sono ai CONFINI (primo e ultimo giorno del mese) perche' una fattura a
meta' mese non distingue nessuno dei due difetti: il raggruppamento sbagliato la
lascerebbe comunque nel mese giusto.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

FUSI = ["Europe/Rome", "America/Los_Angeles"]


def _doc(file_origine, data_documento, totale=100.0):
    return {
        "id": file_origine,
        "file_origine": file_origine,
        "fornitore": "F",
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": totale,
        "data_documento": data_documento,
        "numero_documento": None,
        "scadenza_effettiva": None,
        "scadenza_source": None,
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "oscurata": False,
    }


def _gruppi(documenti, tz):
    return esegui_ts(
        MODULO,
        "emit(m.raggruppaPerMeseFattura(input).map((g) => "
        "({chiave: g.chiave, label: g.label, count: g.count, totale: g.totale, "
        "files: g.docs.map((d) => d.file_origine)})));",
        argomento=documenti,
        tz=tz,
        richiede=["raggruppaPerMeseFattura", "parseLocalDate"],
    )


@pytest.mark.parametrize("tz", FUSI)
def test_il_primo_del_mese_resta_nel_suo_mese(tz):
    """Il confine che smaschera `new Date(iso)`: mezzanotte UTC del 1° marzo e'
    il 28 febbraio in California."""
    docs = [
        _doc("primo.xml", "2026-03-01"),
        _doc("ultimo.xml", "2026-03-31"),
    ]
    gruppi = _gruppi(docs, tz)
    assert len(gruppi) == 1, f"attesi in un solo mese, ottenuti {[g['chiave'] for g in gruppi]}"
    assert gruppi[0]["chiave"] == "2026-03"
    assert gruppi[0]["count"] == 2


@pytest.mark.parametrize("tz", FUSI)
def test_i_mesi_vanno_dal_piu_recente_al_piu_vecchio(tz):
    """E i mesi senza fatture non compaiono: l'elenco salta i buchi, non li inventa."""
    docs = [
        _doc("gen.xml", "2026-01-15"),
        _doc("mag.xml", "2026-05-20"),   # marzo e aprile non esistono
        _doc("dic.xml", "2025-12-31"),
    ]
    gruppi = _gruppi(docs, tz)
    assert [g["chiave"] for g in gruppi] == ["2026-05", "2026-01", "2025-12"]


@pytest.mark.parametrize("tz", FUSI)
def test_nessuna_fattura_si_perde_per_strada(tz):
    """L'invariante che impedisce alla vista di mentire sul proprio totale."""
    docs = [
        _doc("a.xml", "2026-03-10", 100.0),
        _doc("b.xml", "2026-03-11", 50.0),
        _doc("c.xml", "2026-02-01", 25.0),
        _doc("senza.xml", None, 10.0),
    ]
    gruppi = _gruppi(docs, tz)
    assert sum(g["count"] for g in gruppi) == len(docs)
    assert sum(g["totale"] for g in gruppi) == pytest.approx(185.0)


@pytest.mark.parametrize("tz", FUSI)
def test_le_fatture_senza_data_finiscono_in_coda_non_in_testa(tz):
    """La chiave del gruppo senza data e' "": ordinata come le altre finirebbe in
    TESTA, davanti al mese piu' recente. E' un residuo, va in fondo."""
    docs = [_doc("senza.xml", None), _doc("mar.xml", "2026-03-10")]
    gruppi = _gruppi(docs, tz)
    assert [g["chiave"] for g in gruppi] == ["2026-03", ""]
    assert gruppi[-1]["label"] == "Senza data"


@pytest.mark.parametrize("tz", FUSI)
def test_dentro_il_mese_la_piu_recente_sta_in_alto(tz):
    """Stesso verso dei mesi: l'occhio scende sempre indietro nel tempo."""
    docs = [
        _doc("vecchia.xml", "2026-03-02"),
        _doc("nuova.xml", "2026-03-28"),
        _doc("mezzo.xml", "2026-03-15"),
    ]
    gruppi = _gruppi(docs, tz)
    assert gruppi[0]["files"] == ["nuova.xml", "mezzo.xml", "vecchia.xml"]


@pytest.mark.parametrize("tz", FUSI)
def test_l_etichetta_del_mese_e_in_italiano(tz):
    """Il cliente legge "marzo 2026", non "2026-03" ne' "March 2026"."""
    gruppi = _gruppi([_doc("a.xml", "2026-03-10")], tz)
    assert gruppi[0]["label"] == "marzo 2026"


@pytest.mark.parametrize("tz", FUSI)
def test_elenco_vuoto_non_produce_gruppi_fantasma(tz):
    assert _gruppi([], tz) == []
