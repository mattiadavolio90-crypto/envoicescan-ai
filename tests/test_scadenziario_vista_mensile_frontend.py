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


def _doc(file_origine, data_documento, totale=100.0, nota_credito=False):
    return {
        "id": file_origine,
        "file_origine": file_origine,
        "fornitore": "F",
        "tipo_documento": "TD04" if nota_credito else "TD01",
        "is_nota_credito": nota_credito,
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


def test_la_guardia_vuoto_testa_i_gruppi_resi_non_i_documenti_filtrati():
    """Il messaggio "nessuna fattura" non puo' comparire sotto un elenco pieno.

    Il ramo `lista_mensile` costruisce l'elenco da `gruppiMensili`, che nasce da
    `documentiCalendario` e IGNORA il filtro periodo (i suoi chip sono nascosti in
    questa vista). Testare `documentiFiltrati` — che al periodo obbedisce — mette
    le due collezioni in disaccordo: con "Solo scadute" attivo e zero scadute, il
    riquadro "Nessuna fattura corrisponde ai filtri" compariva sotto tutti i mesi.
    Nessun dato perso, ma la pagina si contraddiceva.

    E' una guardia sul sorgente e non sul comportamento perche' il rendering
    condizionale di un .tsx non e' raggiungibile dai test che eseguono il TS:
    qui si misura l'ANCORA (quale collezione viene testata), non un letterale di
    testo — una rinomina del messaggio non la fa gridare.
    """
    import pathlib
    import re

    sorgente = (pathlib.Path(__file__).resolve().parent.parent
                / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
                ).read_text(encoding="utf-8")

    inizio = sorgente.find('view === "lista_mensile" ? (')
    assert inizio > 0, "il ramo lista_mensile non esiste piu'"
    # fino all'inizio del ramo successivo (il calendario)
    fine = sorgente.find("<CalendarView", inizio)
    ramo = sorgente[inizio:fine if fine > inizio else len(sorgente)]

    guardie = re.findall(r"\{(\w+)\.length === 0 &&", ramo)
    assert guardie, "il ramo lista_mensile non ha piu' una guardia di elenco vuoto"
    assert "documentiFiltrati" not in guardie, (
        "la guardia di elenco vuoto testa `documentiFiltrati`, ma il ramo rende "
        f"`gruppiMensili`: {guardie}. Le due collezioni divergono quando e' attivo "
        "un filtro periodo, e il messaggio 'nessuna fattura' compare sotto un "
        "elenco pieno."
    )
    assert "gruppiMensili" in guardie, guardie


# --- Le note di credito nel totale del mese (audit di correttezza, ottobre 2026) ---
#
# Il totale del mese sommava `totale_documento` di ogni documento. Una nota di
# credito arriva dal worker col totale dell'XML, POSITIVO: era sommata come una
# fattura. Misurato sul DB il 15/10/2026: 149 note di credito su 5 account, tutte
# positive, 89.796 EUR di scarto sulle intestazioni dei mesi. Le fixture di
# questo file avevano solo fatture TD01, quindi il test restava verde sul bug.


@pytest.mark.parametrize("tz", FUSI)
def test_la_nota_di_credito_toglie_dal_totale_del_mese(tz):
    """300 di fattura e 100 di nota di credito nello stesso mese fanno 200."""
    docs = [
        _doc("fattura.xml", "2026-05-10", totale=300.0),
        _doc("nota.xml", "2026-05-20", totale=100.0, nota_credito=True),
    ]
    gruppi = _gruppi(docs, tz)
    assert len(gruppi) == 1
    assert gruppi[0]["totale"] == pytest.approx(200.0), gruppi[0]
    # la nota resta nell'elenco del mese: si sottrae, non si nasconde
    assert gruppi[0]["count"] == 2


@pytest.mark.parametrize("tz", FUSI)
def test_la_nota_di_credito_col_totale_negativo_toglie_lo_stesso(tz):
    """Senza testata in fatture_documenti il worker somma le righe, che per una
    nota di credito sono negative: anche cosi' deve togliere, non aggiungere."""
    docs = [
        _doc("fattura.xml", "2026-05-10", totale=300.0),
        _doc("nota.xml", "2026-05-20", totale=-100.0, nota_credito=True),
    ]
    assert _gruppi(docs, tz)[0]["totale"] == pytest.approx(200.0)


def test_importo_con_segno_cambia_solo_le_note_di_credito():
    """Una fattura col totale negativo (uno storno scritto come TD01) resta com'e':
    il segno si decide sul tipo del documento, non sul valore."""
    casi = [
        _doc("f.xml", "2026-05-10", totale=300.0),
        _doc("n.xml", "2026-05-10", totale=100.0, nota_credito=True),
        _doc("n2.xml", "2026-05-10", totale=-100.0, nota_credito=True),
        _doc("neg.xml", "2026-05-10", totale=-50.0),
        dict(_doc("vuoto.xml", "2026-05-10"), totale_documento=None),
    ]
    out = esegui_ts(
        MODULO,
        "emit(input.map((d) => m.importoConSegno(d)));",
        argomento=casi,
        richiede=["importoConSegno"],
    )
    assert out == [300.0, -100.0, -100.0, -50.0, 0]


def test_intestazione_e_riga_usano_l_importo_con_segno():
    """Il .tsx non e' eseguibile dai test: qui si guarda che l'intestazione della
    sezione e l'importo della riga passino dalle funzioni di lib provate sopra, e
    che la vecchia somma senza segno non sia tornata. La sezione «Note di
    credito» dello Scadenzario resta fuori: mostra crediti in positivo per
    scelta, sotto un titolo che lo dice."""
    import pathlib
    import re

    sorgente = (pathlib.Path(__file__).resolve().parent.parent
                / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
                ).read_text(encoding="utf-8")

    def corpo(nome):
        inizio = sorgente.find(f"function {nome}(")
        assert inizio >= 0, f"{nome} non esiste piu'"
        fine = sorgente.find("\nfunction ", inizio + 1)
        return sorgente[inizio:fine if fine > inizio else len(sorgente)]

    sezione = corpo("AgendaSection")
    assert re.search(r"const totale = totaleConSegno\(docs\);", sezione), (
        "l'intestazione di AgendaSection non calcola piu' il totale con "
        "totaleConSegno: le note di credito tornano a sommarsi nell'Archivio"
    )
    assert not re.search(r"\.reduce\(\(s, d\) => s \+ \(?d\.totale_documento", sezione), (
        "AgendaSection somma di nuovo totale_documento senza segno"
    )
    # Il totale col segno deve arrivare a video cosi' com'e': un Math.abs nel
    # render (mutante sopravvissuto alla prima stesura) rimetterebbe in positivo
    # un mese fatto di sole note di credito.
    assert "{formatEuro(totale)}" in sezione, (
        "l'intestazione di AgendaSection non mostra piu' il totale calcolato "
        "con totaleConSegno"
    )

    riga = corpo("DocumentoRow")
    assert "formatEuro(importoConSegno(doc))" in riga, (
        "la riga del documento non mostra piu' l'importo col segno: in Archivio "
        "una nota di credito comparirebbe come una fattura"
    )
    assert "formatEuro(doc.totale_documento)" not in riga
    assert re.search(r"\{doc\.is_nota_credito && \(", riga), (
        "la riga del documento non ha piu' l'etichetta «nota di credito»"
    )


def test_la_riga_dice_quando_l_importo_e_senza_iva():
    """Audit di ottobre 2026 (K12): senza il totale della fattura il worker
    ripiega sulla somma delle righe, che e' senza IVA, e la mette nella stessa
    colonna dei totali IVA inclusa. Il worker lo marca con `totale_senza_iva`
    (provato in test_documenti_service_scadenziario.py); qui si guarda che la
    riga lo dica accanto all'importo."""
    import pathlib
    import re

    sorgente = (pathlib.Path(__file__).resolve().parent.parent
                / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
                ).read_text(encoding="utf-8")
    inizio = sorgente.index("function DocumentoRow(")
    riga = sorgente[inizio:sorgente.index("\nfunction ", inizio + 1)]
    assert re.search(
        r"\{formatEuro\(importoConSegno\(doc\)\)\}</p>\s*\{doc\.totale_senza_iva && \(\s*<p[^>]*>\s*IVA esclusa\s*</p>",
        riga,
    ), "la riga non segnala piu' l'importo senza IVA accanto al totale"
