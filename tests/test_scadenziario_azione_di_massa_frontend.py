"""«Segna pagate» e «Segna non pagate» agiscono solo sulle fatture che cambiano stato.

L'endpoint `POST /api/scadenziario/pagata` scrive `pagata_manuale_at` su ogni
fattura che riceve (`documenti_service.segna_fattura_pagata`), ed e' la
dichiarazione che spegne l'automatismo RID su quella fattura
(`get_documenti_scadenziario`: «quest'ultima vince sempre»). Fino al 26/09/2026 la
barra di selezione mandava all'endpoint TUTTA la selezione, qualunque fosse il
verso:

- «Seleziona tutte» prende solo fatture da pagare, e «Segna non pagate» le
  riscriveva tutte senza cambiarne nessuna: una regola RID messa dopo non le
  avrebbe piu' segnate pagate, senza niente a video che lo dicesse;
- nel verso opposto una fattura gia' pagata finita nella selezione perdeva la
  sua data di pagamento, sostituita da oggi.

La decisione (`pianoAzioneDiMassa`), l'aggiornamento a video
(`applicaPagataAVideo`), i testi (`messaggioConfermaAzioneDiMassa`,
`messaggioEsitoAzioneDiMassa`, `motivoAzioneSpenta`)
vivono in lib/scadenziario.ts e qui si eseguono davvero. Il componente React non
si esegue (`tests/helpers_ts.py` copre solo `lib/`): la terza parte controlla che
il .tsx usi quelle funzioni e non la selezione grezza, che e' la regressione
possibile — un fix nella lib con la pagina che continua a mandare tutto.
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


def _doc(fo, pagata=False, **kw):
    base = {
        "id": fo,
        "file_origine": fo,
        "fornitore": "F",
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "oscurata": False,
        "totale_documento": 100,
        "data_documento": "2026-08-01",
        "numero_documento": "1",
        "scadenza_effettiva": "2026-09-01",
        "scadenza_source": "xml",
        "pagata": pagata,
        "data_pagamento": "2026-08-20" if pagata else None,
        "pagata_at": "2026-08-20" if pagata else None,
        "stato_scadenza": "pagata" if pagata else "scaduta",
    }
    base.update(kw)
    return base


def _sel(documenti, nomi):
    """La selezione come la tiene la pagina: chiavi sede|file (`chiaveDocumento`).
    I test scritti per nome selezionano quel file su ogni sede che lo ha; un nome
    che nessun documento porta resta una chiave estranea."""
    chiavi = [f"{d.get('ristorante_id') or ''}|{d['file_origine']}" for d in documenti if d["file_origine"] in nomi]
    presenti = {d["file_origine"] for d in documenti}
    return chiavi + [f"|{n}" for n in nomi if n not in presenti]


def _piano(documenti, selezionate, pagata):
    selezionate = _sel(documenti, selezionate)
    # `undefined` sparisce da JSON.stringify: la sede mono-sede torna come null.
    return esegui_ts(
        MODULO,
        "const p = m.pianoAzioneDiMassa(input.documenti, input.selezionate, input.pagata);"
        "emit({"
        "  gruppi: p.gruppi.map(g => ({ ristorante_id: g.ristorante_id ?? null, file_origini: g.file_origini })),"
        "  cambiano: p.cambiano.map(d => d.file_origine),"
        "  giaCosi: p.giaCosi,"
        "});",
        argomento={"documenti": documenti, "selezionate": selezionate, "pagata": pagata},
        richiede=["pianoAzioneDiMassa"],
    )


# ── 1. La decisione, eseguita ────────────────────────────────────────────────

def test_seleziona_tutte_poi_segna_non_pagate_non_manda_nulla():
    """Il caso reale: «Seleziona tutte» + «Segna non pagate».

    Le chiavi vengono da `chiaviSelezionaTutte`, la stessa funzione del
    pulsante: se un domani «Seleziona tutte» prendesse anche le pagate, questo
    test smetterebbe di descrivere il caso e lo direbbe.
    """
    documenti = [_doc("a.xml"), _doc("b.xml"), _doc("c.xml"), _doc("pagata.xml", pagata=True)]
    selezionate = esegui_ts(
        MODULO,
        "emit(m.chiaviSelezionaTutte(input));",
        argomento=documenti,
        richiede=["chiaviSelezionaTutte"],
    )
    assert sorted(selezionate) == ["|a.xml", "|b.xml", "|c.xml"], (
        "«Seleziona tutte» ha cambiato popolazione: questo test non descrive piu' "
        "il caso reale e va rivisto"
    )

    piano = _piano(documenti, [k.split("|", 1)[1] for k in selezionate], False)

    assert piano["gruppi"] == [], (
        "«Segna non pagate» su fatture gia' da pagare manda ancora qualcosa "
        "all'endpoint: ognuna riceverebbe pagata_manuale_at e l'automatismo RID "
        "si spegnerebbe in silenzio"
    )
    assert piano["cambiano"] == []
    assert piano["giaCosi"] == 3


def test_segna_pagate_salta_le_gia_pagate():
    """Una pagata nella selezione non perde la sua data di pagamento."""
    documenti = [_doc("da_pagare.xml"), _doc("pagata.xml", pagata=True), _doc("fuori.xml")]

    piano = _piano(documenti, ["da_pagare.xml", "pagata.xml"], True)

    assert piano["gruppi"] == [{"ristorante_id": None, "file_origini": ["da_pagare.xml"]}]
    assert piano["cambiano"] == ["da_pagare.xml"]
    assert piano["giaCosi"] == 1


def test_segna_non_pagate_prende_solo_le_pagate_rid_compreso():
    """Una pagata per RID (senza dichiarazione manuale) si riporta indietro cosi'.

    `pagata` e' lo stato che il cliente vede: il worker lo mette a True per le
    RID. E' proprio il caso in cui scrivere pagata_manuale_at serve.
    """
    documenti = [
        _doc("manuale.xml", pagata=True),
        _doc("rid.xml", pagata=True, scadenza_source="fornitore_rid"),
        _doc("da_pagare.xml"),
    ]

    piano = _piano(documenti, ["manuale.xml", "rid.xml", "da_pagare.xml"], False)

    assert piano["gruppi"] == [{"ristorante_id": None, "file_origini": ["manuale.xml", "rid.xml"]}]
    assert piano["giaCosi"] == 1


def test_le_non_selezionate_restano_fuori():
    documenti = [_doc("a.xml"), _doc("b.xml", pagata=True), _doc("c.xml")]

    piano = _piano(documenti, ["a.xml", "inesistente.xml"], True)

    assert piano["cambiano"] == ["a.xml"]
    assert piano["giaCosi"] == 0


def test_in_catena_raggruppa_per_sede_solo_le_fatture_che_cambiano():
    """L'endpoint risolve UN ristorante_id per richiesta: una chiamata per sede."""
    documenti = [
        _doc("a.xml", ristorante_id="r1"),
        _doc("c.xml", ristorante_id="r2"),
        _doc("b.xml", ristorante_id="r1"),
        _doc("d.xml", pagata=True, ristorante_id="r2"),
        _doc("e.xml", pagata=True, ristorante_id="r3"),
    ]

    piano = _piano(documenti, ["a.xml", "b.xml", "c.xml", "d.xml", "e.xml"], True)

    assert piano["gruppi"] == [
        {"ristorante_id": "r1", "file_origini": ["a.xml", "b.xml"]},
        {"ristorante_id": "r2", "file_origini": ["c.xml"]},
    ], "una sede con solo fatture gia' pagate non deve ricevere nessuna chiamata"
    assert piano["giaCosi"] == 2


# ── 2. L'aggiornamento a video e il testo della conferma, eseguiti ───────────

def _dopo_l_azione(documenti, selezionate, pagata, oggi="2026-09-26"):
    selezionate = _sel(documenti, selezionate)
    return esegui_ts(
        MODULO,
        "const p = m.pianoAzioneDiMassa(input.documenti, input.selezionate, input.pagata);"
        "emit(m.applicaPagataAVideo(input.documenti, p.cambiano, input.pagata, input.oggi)"
        "  .map(d => ({ fo: d.file_origine, sede: d.ristorante_id ?? null, pagata: d.pagata, pagata_at: d.pagata_at })));",
        argomento={"documenti": documenti, "selezionate": selezionate, "pagata": pagata, "oggi": oggi},
        richiede=["pianoAzioneDiMassa", "applicaPagataAVideo"],
    )


def test_a_video_la_gia_pagata_tiene_la_sua_data():
    documenti = [_doc("nuova.xml"), _doc("vecchia.xml", pagata=True), _doc("fuori.xml")]

    dopo = _dopo_l_azione(documenti, ["nuova.xml", "vecchia.xml"], True)

    assert dopo == [
        {"fo": "nuova.xml", "sede": None, "pagata": True, "pagata_at": "2026-09-26"},
        {"fo": "vecchia.xml", "sede": None, "pagata": True, "pagata_at": "2026-08-20"},
        {"fo": "fuori.xml", "sede": None, "pagata": False, "pagata_at": None},
    ], "a video una fattura gia' pagata ha perso la data di pagamento, o ne e' cambiata una non selezionata"


def test_a_video_lo_storno_toglie_la_data_solo_alle_stornate():
    documenti = [_doc("pagata.xml", pagata=True), _doc("da_pagare.xml")]

    dopo = _dopo_l_azione(documenti, ["pagata.xml", "da_pagare.xml"], False)

    assert dopo == [
        {"fo": "pagata.xml", "sede": None, "pagata": False, "pagata_at": None},
        {"fo": "da_pagare.xml", "sede": None, "pagata": False, "pagata_at": None},
    ]


def test_a_video_in_catena_la_chiave_include_la_sede():
    """Stesso file_origine su due sedi: cambia solo quella che cambiava stato."""
    documenti = [
        _doc("x.xml", ristorante_id="r1"),
        _doc("x.xml", pagata=True, ristorante_id="r2"),
    ]

    dopo = _dopo_l_azione(documenti, ["x.xml"], True)

    assert dopo == [
        {"fo": "x.xml", "sede": "r1", "pagata": True, "pagata_at": "2026-09-26"},
        {"fo": "x.xml", "sede": "r2", "pagata": True, "pagata_at": "2026-08-20"},
    ]


def _messaggio(documenti, selezionate, pagata):
    return esegui_ts(
        MODULO,
        "const p = m.pianoAzioneDiMassa(input.documenti, input.selezionate, input.pagata);"
        "emit({ testo: m.messaggioConfermaAzioneDiMassa(p, input.pagata), euro: m.formatEuro(input.atteso) });",
        argomento={"documenti": documenti, "selezionate": _sel(documenti, selezionate), "pagata": pagata,
                   "atteso": sum(d["totale_documento"] for d in documenti
                                 if d["file_origine"] in selezionate and d["pagata"] != pagata)},
        richiede=["pianoAzioneDiMassa", "messaggioConfermaAzioneDiMassa", "formatEuro"],
    )


def test_la_conferma_conta_e_somma_solo_le_fatture_che_cambiano():
    documenti = [
        _doc("a.xml", totale_documento=100),
        _doc("b.xml", totale_documento=200),
        _doc("c.xml", pagata=True, totale_documento=5000),
    ]

    esito = _messaggio(documenti, ["a.xml", "b.xml", "c.xml"], True)

    assert esito["testo"].startswith(f"2 fatture per {esito['euro']}."), esito["testo"]
    assert "riportarle indietro selezionandole" in esito["testo"]
    assert esito["testo"].endswith(" 1 selezionata è già pagata: resta com'è."), esito["testo"]


def test_la_conferma_al_singolare():
    """Con «Segna non pagate» dopo il fix una fattura sola e' il caso tipico."""
    documenti = [_doc("p.xml", pagata=True, totale_documento=100), _doc("a.xml"), _doc("b.xml")]

    esito = _messaggio(documenti, ["p.xml", "a.xml", "b.xml"], False)

    assert esito["testo"] == (
        f"1 fattura per {esito['euro']} tornerà fra quelle da pagare, e la data di "
        "pagamento verrà rimossa. 2 selezionate sono già da pagare: restano come sono."
    )

    singola = _messaggio([_doc("a.xml", totale_documento=100)], ["a.xml"], True)
    assert singola["testo"] == (
        f"1 fattura per {singola['euro']}. Puoi sempre riportarla indietro selezionandola di nuovo."
    )


def test_la_conferma_al_plurale_senza_selezionate_ferme():
    documenti = [_doc("p.xml", pagata=True), _doc("q.xml", pagata=True)]

    esito = _messaggio(documenti, ["p.xml", "q.xml"], False)

    assert esito["testo"] == (
        f"2 fatture per {esito['euro']} torneranno fra quelle da pagare, e la data di "
        "pagamento verrà rimossa."
    )

    ferme = _messaggio([_doc("a.xml"), _doc("p.xml", pagata=True), _doc("q.xml", pagata=True)],
                       ["a.xml", "p.xml", "q.xml"], True)
    assert ferme["testo"].endswith(" 2 selezionate sono già pagate: restano come sono."), ferme["testo"]


# ── 3. Il cablaggio della pagina ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def sorgente() -> str:
    assert CLIENT.exists(), f"{CLIENT} non esiste: se e' stato rinominato aggiorna il test"
    return CLIENT.read_text(encoding="utf-8")


def _normalizza(testo: str) -> str:
    return re.sub(r"\s+", " ", testo).strip()


def _corpo_funzione(src: str, firma: str) -> str:
    """Il corpo di una funzione, con le graffe bilanciate a partire dalla firma."""
    i = src.find(firma)
    assert i != -1, f"{firma!r} non trovata: se e' stata rinominata aggiorna il test"
    j = src.index("{", src.index(")", i))
    prof = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[j:k + 1]
    raise AssertionError(f"corpo di {firma!r} non chiuso")


def _tag_button_con(src: str, onclick: str) -> str:
    """L'apertura `<Button ...>` che contiene quell'onClick."""
    i = src.find(onclick)
    assert i != -1, f"{onclick!r} non trovato nella barra di selezione"
    inizio = src.rfind("<Button", 0, i)
    fine = src.find(">\n", i)
    assert inizio != -1 and fine != -1
    return _normalizza(src[inizio:fine + 1])


def test_handle_bulk_paga_manda_solo_il_piano(sorgente: str):
    corpo = _normalizza(_corpo_funzione(sorgente, "async function handleBulkPaga("))

    assert "const piano = pianoAzioneDiMassa(documenti, selectedFileOrigini, pagata);" in corpo, (
        "handleBulkPaga non calcola piu' il piano: tornerebbe a mandare tutta la selezione"
    )
    assert "if (piano.gruppi.length === 0) return;" in corpo
    assert "for (const { ristorante_id, file_origini } of piano.gruppi)" in corpo, (
        "le chiamate all'endpoint non partono piu' dai gruppi del piano"
    )
    assert "selectedFileOrigini.has" not in corpo, (
        "handleBulkPaga legge di nuovo la selezione grezza: le fatture che non "
        "cambiano verrebbero riscritte"
    )
    assert "setDocumenti(prev => applicaPagataAVideo(prev, piano.cambiano, pagata, todayLocalIso()));" in corpo, (
        "l'aggiornamento a video non passa piu' da applicaPagataAVideo: una fattura "
        "gia' pagata nella selezione mostrerebbe la data di oggi"
    )
    # Un fallimento parziale (HTTP 200 con ok:false) non passa per successo:
    # conta le fatture inviate contro quelle aggiornate, gruppo per gruppo.
    assert "if (res.ok) aggiornate = data.aggiornate ?? 0;" in corpo
    assert "esiti.push({ inviate: file_origini.length, aggiornate });" in corpo
    assert "const esito = esitoAzioneDiMassa(esiti, pagata);" in corpo
    assert 'if (esito.tipo !== "ok") {' in corpo


def test_i_piani_si_ricalcolano_quando_cambia_la_selezione(sorgente: str):
    """Senza `selectedFileOrigini` fra le dipendenze pulsanti e conferma parlano
    della selezione vecchia, mentre handleBulkPaga ricalcola su quella nuova.
    In apps/web non gira nessun lint: exhaustive-deps non lo vedrebbe."""
    testo = _normalizza(sorgente)
    for nome, verso in (("pianoPagate", "true"), ("pianoNonPagate", "false")):
        atteso = (
            f"const {nome} = useMemo( () => pianoAzioneDiMassa(documenti, selectedFileOrigini, {verso}), "
            "[documenti, selectedFileOrigini], );"
        )
        assert atteso in testo, f"{nome} non e' piu' il piano del suo verso, o ha perso una dipendenza"


def test_i_pulsanti_si_spengono_e_dicono_perche(sorgente: str):
    testo = _normalizza(sorgente)
    assert "const motivoPagateSpento = motivoAzioneSpenta(pianoPagate, true);" in testo
    assert "const motivoNonPagateSpento = motivoAzioneSpenta(pianoNonPagate, false);" in testo

    # Il title sul Button disabilitato non compare (pointer-events-none): sta
    # sullo span che lo avvolge. Il motivo arriva anche agli screen reader, con
    # aria-describedby verso uno span `hidden` (sr-only lo farebbe leggere due volte).
    for onclick, motivo, span, ident in (
        ("onClick={() => setConfermaBulk(true)}", "motivoPagateSpento",
         "<span title={motivoPagateSpento ?? undefined}>", "motivo-segna-pagate"),
        ("onClick={() => setConfermaBulk(false)}", "motivoNonPagateSpento",
         '<span title={motivoNonPagateSpento ?? "Riporta le fatture selezionate fra quelle da pagare"}>',
         "motivo-segna-non-pagate"),
    ):
        tag = _tag_button_con(sorgente, onclick)
        assert f"disabled={{bulkPaying || {motivo} !== null}}" in tag, (
            f"il pulsante non si spegne piu' quando non cambierebbe nulla: {tag}"
        )
        assert f'aria-describedby={{{motivo} ? "{ident}" : undefined}}' in tag, tag
        assert "title=" not in tag

        i = sorgente.find(onclick)
        inizio_button = sorgente.rfind("<Button", 0, i)
        inizio_span = sorgente.rfind("<span", 0, inizio_button)
        assert _normalizza(sorgente[inizio_span:inizio_button]) == span, (
            f"il motivo del pulsante spento non e' piu' sullo span che lo avvolge: "
            f"{_normalizza(sorgente[inizio_span:inizio_button])}"
        )
        fine_button = sorgente.find("</Button>", i)
        dopo = _normalizza(sorgente[fine_button:sorgente.find("</span>\n", fine_button)])
        assert f'{{{motivo} && <span id="{ident}" hidden>{{{motivo}}}' in dopo, (
            f"il motivo non arriva piu' agli screen reader: {dopo}"
        )


def test_il_motivo_del_pulsante_spento():
    esito = esegui_ts(
        MODULO,
        "const pag = m.pianoAzioneDiMassa(input.docs, ['|a.xml'], true);"
        "const non = m.pianoAzioneDiMassa(input.docs, ['|a.xml'], false);"
        "emit([m.motivoAzioneSpenta(pag, true), m.motivoAzioneSpenta(non, false),"
        "      m.motivoAzioneSpenta(m.pianoAzioneDiMassa(input.docs, ['|p.xml'], true), true)]);",
        argomento={"docs": [_doc("a.xml"), _doc("p.xml", pagata=True)]},
        richiede=["pianoAzioneDiMassa", "motivoAzioneSpenta"],
    )
    assert esito == [None, "Le fatture selezionate sono già tutte da pagare",
                     "Le fatture selezionate sono già tutte pagate"]


def test_il_toast_dopo_l_azione_di_massa():
    esito = esegui_ts(
        MODULO,
        "emit([m.messaggioEsitoAzioneDiMassa(1, true), m.messaggioEsitoAzioneDiMassa(3, true),"
        "      m.messaggioEsitoAzioneDiMassa(1, false), m.messaggioEsitoAzioneDiMassa(2, false)]);",
        richiede=["messaggioEsitoAzioneDiMassa"],
    )
    assert esito == [
        "1 fattura segnata come pagata",
        "3 fatture segnate come pagate",
        "1 fattura riportata fra quelle da pagare",
        "2 fatture riportate fra quelle da pagare",
    ]


def test_handle_bulk_paga_usa_il_toast_della_lib(sorgente: str):
    corpo = _normalizza(_corpo_funzione(sorgente, "async function handleBulkPaga("))
    assert 'if (esito.tipo === "parziale") toast.warning(esito.messaggio); else toast.error(esito.messaggio); await loadData(); return;' in corpo
    assert "toast.success(esito.messaggio);" in corpo
    assert "Errore di connessione" not in corpo


@pytest.mark.parametrize(
    "gruppi,pagata,atteso",
    [
        # Tutto riuscito, su due sedi.
        ([{"inviate": 2, "aggiornate": 2}, {"inviate": 1, "aggiornate": 1}], True,
         {"tipo": "ok", "messaggio": "3 fatture segnate come pagate"}),
        # Il caso dell'audit: una sede risponde ok:false con 1 riuscita su 2.
        ([{"inviate": 2, "aggiornate": 2}, {"inviate": 2, "aggiornate": 1}], True,
         {"tipo": "parziale", "messaggio": "3 fatture segnate come pagate; 1 non riuscita, riprova"}),
        # Una sede irraggiungibile: le altre restano contate.
        ([{"inviate": 1, "aggiornate": 1}, {"inviate": 3, "aggiornate": 0}], False,
         {"tipo": "parziale", "messaggio": "1 fattura riportata fra quelle da pagare; 3 non riuscite, riprova"}),
        ([{"inviate": 2, "aggiornate": 0}], True,
         {"tipo": "errore", "messaggio": "Errore nel salvataggio: nessuna fattura aggiornata"}),
    ],
)
def test_esito_dell_azione_di_massa(gruppi, pagata, atteso):
    esito = esegui_ts(
        MODULO,
        "emit(m.esitoAzioneDiMassa(input.gruppi, input.pagata));",
        {"gruppi": gruppi, "pagata": pagata},
        richiede=["esitoAzioneDiMassa"],
    )
    assert esito == atteso


def test_il_pulsante_della_singola_fattura(sorgente: str):
    """Stessi due difetti corretti sull'azione di massa: un 200 con ok:false
    passava per successo, e l'aggiornamento a video guardava il solo
    file_origine (in catena lo stesso file puo' stare su due sedi)."""
    corpo = _normalizza(_corpo_funzione(sorgente, "async function handlePaga("))
    assert (
        'if (!res.ok || data.ok === false) { toast.error("Errore nel salvataggio"); await loadData(); return; }'
        in corpo
    ), corpo
    assert "setDocumenti(prev => applicaPagataAVideo(prev, [doc], pagata, todayLocalIso()));" in corpo
    assert "d.file_origine === doc.file_origine" not in corpo


def test_confirm_dialog_non_cambia_contenuto_mentre_si_chiude():
    """Durante l'animazione di chiusura il genitore ha gia' azzerato il verso e
    svuotato la selezione: il dialog mostrava per un attimo «0 fatture per 0 €»
    col titolo del verso opposto. Vale per tutte le pagine che lo usano."""
    src = (
        Path(__file__).resolve().parents[1] / "apps/web/src/components/ui/confirm-dialog.tsx"
    ).read_text(encoding="utf-8")
    testo = _normalizza(src)
    assert "useEffect(() => { if (open) setUltimo({ titolo, messaggio, confermaLabel }); }, [open, titolo, messaggio, confermaLabel]);" in testo
    assert "const mostrato = open ? { titolo, messaggio, confermaLabel } : ultimo;" in testo
    assert "<DialogTitle>{mostrato.titolo}</DialogTitle>" in testo
    assert "{mostrato.messaggio && <p" in testo and "{mostrato.messaggio}</p>" in testo
    assert "{mostrato.confermaLabel}" in testo
    for grezzo in ("{titolo}</DialogTitle>", "{messaggio}</p>", "{confermaLabel}\n"):
        assert grezzo not in src, f"il dialog mostra di nuovo le prop grezze: {grezzo!r}"


def test_la_conferma_usa_il_messaggio_del_piano(sorgente: str):
    i = sorgente.find("<ConfirmDialog\n        open={confermaBulk !== null}")
    assert i != -1, "il dialog di conferma dell'azione di massa non si trova piu'"
    dialog = _normalizza(sorgente[i:sorgente.find("/>", i)])

    assert (
        "messaggio={confermaBulk ? messaggioConfermaAzioneDiMassa(pianoPagate, true) "
        ": messaggioConfermaAzioneDiMassa(pianoNonPagate, false)}"
    ) in dialog, f"la conferma non usa piu' il messaggio del piano del suo verso: {dialog}"


# ── Stesso file_origine su due sedi (audit di ottobre 2026, K04) ─────────────
#
# Il controllo dei doppioni al caricamento e' per sede: niente impedisce lo
# stesso nome file su due sedi dello stesso account. Con la selezione per sola
# file_origine una spunta selezionava due righe, «Seleziona tutte» annunciava N
# e ne scriveva di piu', e «Segna non pagate» toglieva il pagamento a una
# fattura dell'altra sede che nessuno aveva scelto. Oggi 0 casi nei dati.


def test_una_spunta_su_una_sede_scrive_solo_su_quella():
    documenti = [_doc("DUP2.xml", ristorante_id="rA"), _doc("DUP2.xml", ristorante_id="rB")]
    out = esegui_ts(
        MODULO,
        "const k = m.chiaveDocumento(input[0]);"
        "const p = m.pianoAzioneDiMassa(input, [k], true);"
        "emit({ gruppi: p.gruppi, sezione: m.statoSelezioneSezione(input, [k]) });",
        argomento=documenti,
        richiede=["chiaveDocumento", "pianoAzioneDiMassa", "statoSelezioneSezione"],
    )
    assert out["gruppi"] == [{"ristorante_id": "rA", "file_origini": ["DUP2.xml"]}]
    assert out["sezione"] == {"selezionabili": 2, "selezionati": 1, "tutte": False}


def test_seleziona_tutte_non_tocca_l_omonima_pagata_dell_altra_sede():
    documenti = [
        _doc("X1.xml", ristorante_id="rA"),
        _doc("DUP.xml", ristorante_id="rA"),
        _doc("DUP.xml", pagata=True, ristorante_id="rB"),
    ]
    out = esegui_ts(
        MODULO,
        "const k = m.chiaviSelezionaTutte(input);"
        "const p = m.pianoAzioneDiMassa(input, k, false);"
        "emit({ gruppi: p.gruppi, motivo: m.motivoAzioneSpenta(p, false) });",
        argomento=documenti,
        richiede=["chiaviSelezionaTutte", "pianoAzioneDiMassa", "motivoAzioneSpenta"],
    )
    assert out == {"gruppi": [], "motivo": "Le fatture selezionate sono già tutte da pagare"}


def test_seleziona_tutte_annuncia_quante_ne_scrive():
    documenti = [_doc("DUP2.xml", ristorante_id="rA"), _doc("DUP2.xml", ristorante_id="rB")]
    out = esegui_ts(
        MODULO,
        "const k = m.chiaviSelezionaTutte(input);"
        "const p = m.pianoAzioneDiMassa(input, k, true);"
        "emit({ chiavi: k.length, distinte: new Set(k).size, cambiano: p.cambiano.length, giaCosi: p.giaCosi });",
        argomento=documenti,
        richiede=["chiaviSelezionaTutte", "pianoAzioneDiMassa"],
    )
    assert out == {"chiavi": 2, "distinte": 2, "cambiano": 2, "giaCosi": 0}


def test_stesso_documento_confronta_anche_la_sede():
    out = esegui_ts(
        MODULO,
        "emit([m.stessoDocumento(input[0], input[1]), m.stessoDocumento(input[0], input[2])]);",
        argomento=[
            {"file_origine": "x.xml", "ristorante_id": "rA"},
            {"file_origine": "x.xml", "ristorante_id": "rB"},
            {"file_origine": "x.xml", "ristorante_id": "rA"},
        ],
        richiede=["stessoDocumento"],
    )
    assert out == [False, True]


def test_il_client_usa_la_chiave_con_la_sede(sorgente: str):
    sezione = _normalizza(_corpo_funzione(sorgente, "function AgendaSection("))
    assert "key={chiaveDocumento(doc)}" in sezione
    assert "onToggleSelect={() => onToggleSelect(chiaveDocumento(doc))}" in sezione
    toggle_all = _normalizza(_corpo_funzione(sorgente, "function toggleAll("))
    assert "if (selectAll) next.add(chiaveDocumento(d)); else next.delete(chiaveDocumento(d));" in toggle_all
    for firma in ("async function handleSetScadenza(doc: Documento", "async function handleElimina(doc: Documento",
                  "async function handleOscura(doc: Documento", "function handleSpostata(doc: Documento"):
        corpo = _normalizza(_corpo_funzione(sorgente, firma))
        assert "stessoDocumento(d, doc)" in corpo, firma
        assert "d.file_origine === doc.file_origine" not in corpo, firma
        assert "d.file_origine !== doc.file_origine" not in corpo, firma
