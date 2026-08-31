"""I filtri dello scadenziario mostrano le fatture giuste, in ogni fuso.

`matchDocumento` e i suoi compagni decidono **quali fatture il cliente vede**.
E' una classe di difetto peggiore di un numero sbagliato: se un documento cade
fuori dal filtro non compare nessun errore, la lista e' solo piu' corta. Il
29/8 e' costata una guardia che misurava una soglia *dopo* i filtri client
invece che prima — passava `tsc`, sembrava giusta a leggerla, e non scattava su
nessuno dei 3 casi reali.

**Perche' le fixture sono ai confini.** Le date lontane dai bordi non
distinguono i rami: `s < today` e `s <= today` danno lo stesso esito su una
fattura del 2020. Serve un documento che scade **esattamente oggi**, uno al
**settimo** giorno e uno all'**ottavo**, altrimenti i mutanti sopravvivono in
silenzio.

**Perche' le date sono relative a oggi.** Con date fisse il test invecchia: una
fixture scritta oggi come "scade fra 7 giorni" fra due settimane e' scaduta, e
il confine che doveva presidiare non e' piu' sotto il test.

**Perche' anche America/Los_Angeles.** Il mutante `new Date()` al posto di
`parseLocalDate` — il difetto di fuso che questo codice ha gia' corretto una
volta su `pagata_at` — muore SOLO a ovest di Greenwich. A Roma sopravvive.

**Cosa NON si confronta fra fusi**: l'esito *assoluto* di un confine di data.
Fra le 22:00 e le 00:00 UTC Roma e Los Angeles sono in due giorni diversi, e
"scade oggi" e' gia' scaduto per l'uno e non per l'altro **per costruzione**
(vedi `test_i_kpi_non_dipendono_dal_fuso` nell'altro file: quel test e' stato
rosso ~2 ore su 24 prima di essere ristretto). Qui ogni fuso costruisce le
proprie fixture sul proprio "oggi" e si confrontano gli **id inclusi**, che
sono indipendenti dal fuso.
"""
import datetime

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

# Rome = il fuso reale degli utenti. Los Angeles = l'unico che smaschera
# l'errore di mezzanotte UTC (vedi docstring). Non toglierlo.
FUSI = ["Europe/Rome", "America/Los_Angeles"]

_RICHIEDE = [
    "matchDocumento", "filtraDocumenti", "elencaFornitori", "ordinaDocumenti",
    "statoDocumento", "aggregaPerSede", "fornitoreKey", "confiniPeriodo",
]


def _doc(**kw):
    base = {
        "id": kw.get("id", "x"),
        "fornitore": "F",
        "piva_fornitore": None,
        "is_nota_credito": False,
        "totale_documento": 0,
        "scadenza_effettiva": None,
        "pagata": False,
        "pagata_at": None,
        "is_nuovo": False,
        "ristorante_id": None,
    }
    base.update(kw)
    return base


def _oggi_in(tz):
    """La data che node vede in quel fuso: le fixture si costruiscono su questa.

    Non si usa `date.today()` di Python: a cavallo di mezzanotte, o col processo
    Python in un fuso diverso, le due date divergono e il test fallirebbe per un
    motivo che non c'entra col codice sotto esame.
    """
    iso = esegui_ts(
        MODULO,
        "const d = new Date();"
        "emit([d.getFullYear(), d.getMonth() + 1, d.getDate()]);",
        tz=tz,
    )
    return datetime.date(*iso)


def _filtra(docs, filtri, tz):
    """Gli id dei documenti che sopravvivono ai filtri."""
    return esegui_ts(
        MODULO,
        "emit(m.filtraDocumenti(input.docs, input.filtri).map(d => d.id));",
        argomento={"docs": docs, "filtri": filtri},
        tz=tz,
        richiede=_RICHIEDE,
    )


def _buckets(docs, tz):
    return esegui_ts(
        MODULO,
        "emit(Object.fromEntries(Object.entries(m.bucketizeDocumenti(input))"
        ".map(([k, v]) => [k, v.map(d => d.id)])));",
        argomento=docs,
        tz=tz,
        richiede=["bucketizeDocumenti"],
    )


def _stati(docs, tz):
    return esegui_ts(
        MODULO,
        "emit(Object.fromEntries(input.map(d => [d.id, m.statoDocumento(d)])));",
        argomento=docs,
        tz=tz,
        richiede=_RICHIEDE,
    )


def _fornitori(docs, tz="Europe/Rome"):
    return esegui_ts(
        MODULO,
        "emit(m.elencaFornitori(input));",
        argomento=docs,
        tz=tz,
        richiede=_RICHIEDE,
    )


def _ordina(docs, ordine, tz="Europe/Rome"):
    return esegui_ts(
        MODULO,
        "emit(m.ordinaDocumenti(input.docs, input.ordine).map(d => d.id));",
        argomento={"docs": docs, "ordine": ordine},
        tz=tz,
        richiede=_RICHIEDE,
    )


def _per_sede(docs, filtri, tz):
    return esegui_ts(
        MODULO,
        "emit(Object.fromEntries(m.aggregaPerSede(input.docs, input.filtri)));",
        argomento={"docs": docs, "filtri": filtri},
        tz=tz,
        richiede=_RICHIEDE,
    )


def _campione(tz):
    """Un documento per ogni confine che i mutanti sanno attraversare."""
    oggi = _oggi_in(tz)
    g = lambda n: (oggi + datetime.timedelta(days=n)).isoformat()
    return oggi, [
        _doc(id="ieri", scadenza_effettiva=g(-1), totale_documento=1),
        # il confine caldo: scaduta-stretto vs settimana-inclusivo
        _doc(id="oggi", scadenza_effettiva=g(0), totale_documento=2, is_nuovo=True),
        _doc(id="g7", scadenza_effettiva=g(7), totale_documento=4),
        _doc(id="g8", scadenza_effettiva=g(8), totale_documento=8),
        _doc(id="g30", scadenza_effettiva=g(30), totale_documento=16),
        _doc(id="g31", scadenza_effettiva=g(31), totale_documento=32),
        _doc(id="senza", scadenza_effettiva=None, totale_documento=64),
        _doc(id="pagata", scadenza_effettiva=g(3), pagata=True, totale_documento=128),
        _doc(id="nc", scadenza_effettiva=g(3), is_nota_credito=True, totale_documento=256),
        # NC *e* pagata: senza questo doc lo scambio dei due rami in
        # statoDocumento non e' osservabile e il mutante sopravvive.
        _doc(id="nc_pagata", scadenza_effettiva=g(3), is_nota_credito=True,
             pagata=True, totale_documento=512),
    ]


@pytest.mark.parametrize("tz", FUSI)
def test_scadute_esclude_chi_scade_oggi(tz):
    """`s < today` e' STRETTO: una fattura che scade oggi non e' ancora scaduta."""
    _, docs = _campione(tz)
    assert _filtra(docs, {"periodo": "scadute"}, tz) == ["ieri"], (
        "se compare 'oggi' il confronto e' `<=` invece di `<`: al cliente "
        "risulterebbe scaduto un pagamento che ha ancora tutta la giornata"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_settimana_include_oggi_e_il_settimo_giorno(tz):
    """`s >= today && s <= in7`: inclusivo a **entrambi** gli estremi."""
    _, docs = _campione(tz)
    # 'nc' (nota di credito a +3gg, non pagata) passa: i filtri escludono le
    # PAGATE, non le note di credito — quelle le separa `bucketizeDocumenti` a
    # valle. Verificato sul client originale prima del refactor.
    assert _filtra(docs, {"periodo": "settimana"}, tz) == ["oggi", "g7", "nc"], (
        "manca 'oggi' -> il confine basso e' `>` invece di `>=`; manca 'g7' -> "
        "il confine alto e' `<` invece di `<=`, o in7 e' calcolato a +6 giorni; "
        "c'e' 'g8' -> la finestra e' piu' larga di 7 giorni"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_chip_mese_e_cumulativo_non_e_il_bucket_mese(tz):
    """Il chip "Questo mese" e la sezione "Questo mese" sono insiemi DIVERSI.

    Si chiamano con le stesse parole nella UI — il chip filtro
    (`scadenziario-client.tsx`, la pillola "Questo mese") e l'intestazione della
    sezione in agenda — ma:

    - il **chip** e' una finestra CUMULATIVA `oggi..+30gg`: include anche cio'
      che scade questa settimana;
    - la **sezione** e' la terza fascia di una scaletta (`bucketizeDocumenti`),
      `+8gg..+30gg`: la settimana ha gia' la sua sezione sopra.

    **Non e' un bug.** Filtrando "questo mese" l'utente si aspetta di vedere
    anche cio' che scade domani; scorrendo l'agenda si aspetta che una fattura
    compaia in una sezione sola. Il test esiste perche' la coincidenza di nome
    e' una trappola: chi allinea l'uno all'altro "per coerenza" cambia cio' che
    il cliente vede senza accorgersene. Deciso da Mattia il 31/8/2026: si
    lascia com'e' e si scrive qui il perche'.
    """
    _, docs = _campione(tz)

    chip = _filtra(docs, {"periodo": "mese"}, tz)
    assert chip == ["oggi", "g7", "g8", "g30", "nc"], (
        "il chip 'Questo mese' e' CUMULATIVO da oggi: se 'oggi' e 'g7' "
        "spariscono, qualcuno lo ha allineato al bucket e il cliente non vede "
        "piu' le scadenze imminenti quando filtra per mese"
    )

    sezione = _buckets(docs, tz)["mese"]
    assert sezione == ["g8", "g30"], (
        "la sezione 'Questo mese' ESCLUDE la settimana (che ha la sua sezione): "
        "se compaiono 'oggi'/'g7' la stessa fattura e' in due sezioni"
    )

    # Al netto delle NC (che il bucket separa e il chip no) il chip resta un
    # sovrainsieme STRETTO: e' questa la relazione fra i due.
    assert set(chip) - {"nc"} > set(sezione), (
        "il chip deve essere un sovrainsieme STRETTO della sezione: e' questa "
        "la relazione fra i due, ed e' quella che si rompe se si toccano"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_ogni_periodo_esclude_le_pagate_tranne_tutti(tz):
    """`if (d.pagata) return false` sta DENTRO il blocco periodo.

    La controprova con "tutti" e' la meta' che discrimina: un test che guardasse
    solo i periodi filtrati passerebbe anche se le pagate fossero escluse
    sempre, e la sezione "Pagate" dell'agenda sparirebbe senza che nulla lo dica.
    """
    _, docs = _campione(tz)

    for periodo in ("scadute", "settimana", "mese", "personalizzato"):
        assert "pagata" not in _filtra(docs, {"periodo": periodo}, tz), (
            f"periodo '{periodo}': una fattura gia' pagata non e' una scadenza"
        )

    assert "pagata" in _filtra(docs, {"periodo": "tutti"}, tz), (
        "con 'tutti' le pagate DEVONO passare: e' cio' che alimenta la sezione "
        "'Pagate' e il calendario"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_filtro_fornitori_vuoto_non_filtra_nulla(tz):
    """Lista vuota = nessun filtro, non "nessun fornitore ammesso"."""
    _, docs = _campione(tz)
    tutti = [d["id"] for d in docs]

    assert _filtra(docs, {"periodo": "tutti", "fornitori": []}, tz) == tutti, (
        "con lista vuota il filtro non deve scattare: se scatta, il cliente "
        "apre lo scadenziario e trova la lista vuota"
    )
    assert _filtra(docs, {"periodo": "tutti", "fornitori": None}, tz) == tutti


def test_elenca_fornitori_deduplica_per_piva():
    """Stessa P.IVA scritta in due modi = UNA voce, col nome piu' frequente.

    Il tie-break a parita' di conteggio e' deterministico per spec: `Map` itera
    in ordine di inserimento e `sort` e' stabile da ES2019, quindi vince il nome
    incontrato per primo. Asserito sotto, cosi' se un domani si passasse a una
    struttura non ordinata il test lo direbbe invece di diventare intermittente.
    """
    docs = [
        _doc(id="1", piva_fornitore="P1", fornitore="Rossi SRL"),
        _doc(id="2", piva_fornitore="P1", fornitore="ROSSI S.R.L."),
        _doc(id="3", piva_fornitore="P1", fornitore="Rossi SRL"),
        _doc(id="4", piva_fornitore=None, fornitore="Bianchi"),
    ]
    voci = _fornitori(docs)

    assert [v["key"] for v in voci] == ["Bianchi", "P1"], (
        "due voci, ordinate per etichetta: la stessa P.IVA con ragione sociale "
        "diversa non deve comparire due volte nel menu"
    )
    assert voci[1]["label"] == "Rossi SRL", (
        "vince il nome piu' frequente (2 contro 1): col comparatore invertito "
        "il menu mostrerebbe la grafia rara"
    )

    pari = [
        _doc(id="1", piva_fornitore="P1", fornitore="Primo"),
        _doc(id="2", piva_fornitore="P1", fornitore="Secondo"),
    ]
    assert _fornitori(pari)[0]["label"] == "Primo", (
        "a parita' di conteggio vince l'inserito per primo (Map + sort stabile)"
    )

    # Chiave vuota (ne' P.IVA ne' nome): niente voce fantasma nel menu.
    senza_chiave = [
        _doc(id="1", piva_fornitore=None, fornitore=""),
        _doc(id="2", piva_fornitore="P1", fornitore="Vero"),
    ]
    assert [v["key"] for v in _fornitori(senza_chiave)] == ["P1"], (
        "un documento senza fornitore ne' P.IVA non deve produrre una voce "
        "vuota nel filtro"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_filtro_solo_nuove(tz):
    _, docs = _campione(tz)
    assert _filtra(docs, {"periodo": "tutti", "soloNuove": True}, tz) == ["oggi"], (
        "solo il documento marcato is_nuovo: con la negazione invertita il "
        "filtro mostrerebbe esattamente le fatture gia' viste"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_stato_documento_concorda_con_i_bucket(tz):
    """Il CSV scaricato dice la stessa cosa che si vede a video.

    `statoDocumento` e' nata come quarta derivazione dello stato dentro
    `exportCsv`, reimplementata a mano. Questo test la lega a
    `bucketizeDocumenti`: se qualcuno reintroduce un `stato()` locale con un
    ordine di precedenza diverso, non basta piu' che "sembri equivalente".

    Il documento `nc_pagata` (nota di credito **e** pagata) e' quello che rende
    osservabile l'ordine dei due rami: senza di lui sono indistinguibili.
    """
    _, docs = _campione(tz)
    stati = _stati(docs, tz)
    b = _buckets(docs, tz)

    atteso = {
        "Scaduta": set(b["scadute"]),
        "Pagata": set(b["pagate"]),
        "Nota di credito": set(b["noteCredito"]),
        "Senza scadenza": set(b["senzaScadenza"]),
        "Da pagare": set(b["settimana"]) | set(b["mese"]) | set(b["oltre"]),
    }
    for stato, ids in atteso.items():
        ottenuti = {k for k, v in stati.items() if v == stato}
        assert ottenuti == ids, (
            f"stato '{stato}': il CSV e l'agenda non concordano. "
            f"CSV={sorted(ottenuti)} agenda={sorted(ids)}"
        )

    assert stati["nc_pagata"] == "Nota di credito", (
        "una NC pagata resta una nota di credito: il ramo NC viene PRIMA di "
        "quello pagata, come in bucketizeDocumenti"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_personalizzato_e_le_senza_scadenza(tz):
    """Il ramo controintuitivo: le senza-scadenza appaiono solo senza estremi.

    E' una scelta di prodotto (un intervallo di date non puo' contenere una
    fattura che una data non ce l'ha), ma non e' ovvia leggendo il codice: senza
    test, il primo che ci mette mano la "semplifica" in `return true` e il
    cliente si ritrova le senza-scadenza dentro ogni intervallo.
    """
    oggi, docs = _campione(tz)
    g = lambda n: (oggi + datetime.timedelta(days=n)).isoformat()

    assert "senza" in _filtra(docs, {"periodo": "personalizzato"}, tz)
    assert "senza" not in _filtra(
        docs, {"periodo": "personalizzato", "dataDa": g(0)}, tz)
    assert "senza" not in _filtra(
        docs, {"periodo": "personalizzato", "dataA": g(10)}, tz)

    assert _filtra(
        docs, {"periodo": "personalizzato", "dataDa": g(0), "dataA": g(7)}, tz
    ) == ["oggi", "g7", "nc"], (
        "estremi INCLUSIVI: se 'g7' sparisce il confronto e' `s >= a` invece "
        "di `s > a` e l'ultimo giorno dell'intervallo scelto viene tagliato"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_periodo_tutti_applica_solo_gli_altri_filtri(tz):
    """Pinna la vista calendario, che chiama i filtri con periodo "tutti".

    Il calendario ha la propria navigazione mensile: applica fornitore e nuove,
    **non** il periodo. L'atteso e' calcolato in Python dalla fixture, non da
    un'altra chiamata al TS: un test che confronta il codice con se stesso non
    misura niente.
    """
    _, docs = _campione(tz)
    docs = [dict(d, piva_fornitore="P1" if d["id"] in ("oggi", "g7") else "P2")
            for d in docs]

    atteso = [d["id"] for d in docs if d["piva_fornitore"] == "P1"]
    ottenuto = _filtra(docs, {"periodo": "tutti", "fornitori": ["P1"]}, tz)

    assert ottenuto == atteso == ["oggi", "g7"], (
        "con periodo 'tutti' passano tutti i documenti del fornitore scelto, "
        "scaduti o no, pagati o no: e' cio' che il calendario mostra"
    )


def test_ordina_mette_le_senza_scadenza_in_fondo():
    """`?? Infinity`: una fattura senza scadenza non e' una scadenza vicina.

    Col fallback a 0 finirebbe in cima, davanti alle scadute — cioe' la lista si
    aprirebbe su cio' che non ha una data.
    """
    docs = [
        _doc(id="senza", scadenza_effettiva=None, totale_documento=5),
        _doc(id="tardi", scadenza_effettiva="2030-01-01", totale_documento=30),
        _doc(id="presto", scadenza_effettiva="2020-01-01", totale_documento=10),
    ]
    assert _ordina(docs, "scadenza") == ["presto", "tardi", "senza"]
    assert _ordina(docs, "importo") == ["tardi", "presto", "senza"], (
        "importo decrescente: 30, 10, 5"
    )


def test_ordina_per_fornitore_mette_le_accentate_al_posto_giusto():
    """Le accentate non finiscono in coda all'alfabeto.

    **Cosa NON prova questo test, misurato.** Non discrimina la rimozione
    dell'argomento `"it"`: l'ordinamento accent-insensitive di "Àlfa" e' il
    default UCA di Unicode, non una specificita' italiana — `undefined`, `it`,
    `en-US`, `sv-SE` e `de-DE` danno tutti `[Àlfa, Mario, Zeta]`. Il mutante che
    toglie il locale **sopravvive**, ed e' dichiarato nel verbale del 31/8.

    Quello che prova e' che l'ordinamento non sia per code-unit (`<`/`>` nudi o
    un `sort()` di default), dove "Àlfa" (U+00C0) finirebbe dopo "Zeta".
    """
    docs = [
        _doc(id="z", fornitore="Zeta"),
        _doc(id="a", fornitore="Àlfa"),
        _doc(id="m", fornitore="Mario"),
    ]
    assert _ordina(docs, "fornitore") == ["a", "m", "z"], (
        "'Àlfa' va ordinata come 'Alfa': con un confronto per code-unit "
        "finirebbe dopo 'Zeta'"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_il_predicato_extra_filtra_la_sede(tz):
    """`extra` e' il filtro di sede, e in catena decide cosa il cliente vede.

    Senza questo test il parametro non era esercitato da nessuna chiamata: il
    mutante che ignora `extra` (`d => matchDocumento(...)`) sopravviveva, e con
    lui un filtro sede che non filtra — in modalita' catena il cliente vedrebbe
    le fatture di tutte le sedi.
    """
    _, base = _campione(tz)
    docs = [dict(d, ristorante_id="S1" if d["id"] in ("ieri", "oggi") else "S2")
            for d in base]

    solo_s1 = esegui_ts(
        MODULO,
        "emit(m.filtraDocumenti(input.docs, input.filtri,"
        " d => d.ristorante_id === 'S1').map(d => d.id));",
        argomento={"docs": docs, "filtri": {"periodo": "tutti"}},
        tz=tz,
        richiede=_RICHIEDE,
    )
    assert solo_s1 == ["ieri", "oggi"], (
        "il predicato extra deve restringere alla sede scelta: se torna tutto, "
        "il filtro sede e' ignorato"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_aggrega_per_sede_conta_solo_i_debiti(tz):
    """Pagate e note di credito non sono debiti, e restano fuori dai totali.

    La striscia per-sede e' cliccabile e mostra un totale in euro: se una NC ci
    entra, il cliente legge un'esposizione che non ha.
    """
    _, base = _campione(tz)
    docs = [dict(d, ristorante_id="S1") for d in base]
    docs.append(_doc(id="orfano", ristorante_id=None, scadenza_effettiva=None,
                     totale_documento=1024))
    docs.append(_doc(id="altra", ristorante_id="S2", totale_documento=2048,
                     scadenza_effettiva=None))

    per_sede = _per_sede(docs, {"periodo": "tutti"}, tz)

    assert set(per_sede) == {"S1", "S2"}, (
        "un documento senza ristorante_id non ha una sede a cui sommarsi"
    )
    # 1+2+4+8+16+32+64 = 127: tutti tranne pagata (128), nc (256), nc_pagata (512)
    assert per_sede["S1"] == {"count": 7, "totale": 127}, (
        "se il totale sale, una pagata o una nota di credito e' entrata nei debiti"
    )
    assert per_sede["S2"] == {"count": 1, "totale": 2048}

    ristretto = _per_sede(docs, {"periodo": "settimana"}, tz)
    assert ristretto["S1"] == {"count": 2, "totale": 6}, (
        "la striscia per-sede riflette gli ALTRI filtri attivi (qui il periodo): "
        "e' il requisito 'stessi filtri comuni, tranne quello di sede'"
    )


def test_i_filtri_non_dipendono_dal_fuso():
    """Gli stessi documenti, relativi al proprio oggi, danno lo stesso esito.

    Ogni fuso costruisce le fixture sul **proprio** "oggi" e si confrontano gli
    id inclusi: e' una grandezza indipendente dal fuso, mentre l'esito assoluto
    di un confine non lo e' (fra le 22:00 e le 00:00 UTC Roma e Los Angeles sono
    in due giorni diversi — vedi la docstring del modulo).

    E' il test che sarebbe rosso col mutante `new Date()` al posto di
    `parseLocalDate`: a Roma sopravvive, a Los Angeles muore.
    """
    esiti = {}
    for tz in FUSI:
        _, docs = _campione(tz)
        esiti[tz] = {
            periodo: _filtra(docs, {"periodo": periodo}, tz)
            for periodo in ("scadute", "settimana", "mese", "tutti")
        }

    assert esiti["Europe/Rome"] == esiti["America/Los_Angeles"], (
        "una scadenza 'YYYY-MM-DD' vale lo stesso giorno ovunque: se i due fusi "
        "divergono, da qualche parte si legge una data nuda come istante UTC"
    )
