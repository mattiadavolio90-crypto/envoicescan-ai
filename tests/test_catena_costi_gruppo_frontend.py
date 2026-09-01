"""Quello che le due finestre di catena mandano al backend.

`lib/catena-costi-gruppo.ts` raccoglie la logica di `finestra-costi-gruppo.tsx` e
`config-assistente-catena.tsx`: le due schermate dell'area che SCRIVONO. Un
errore nelle formule di `catena-tag.ts` sbaglia dei pixel; un errore qui persiste
— un importo storto, o dei punti vendita riattivati che l'utente aveva escluso.

Tre comportamenti che sembrano sviste e non lo sono, tenuti fermi da questi test:

1. `!(imp > 0)` invece di `imp <= 0` — la prima forma respinge anche NaN, la
   seconda lo lascerebbe passare fino al POST.
2. `ricalcolo_quote_ok === false` invece di `!ricalcolo_quote_ok` — il campo
   assente e' una risposta di un backend precedente, non un ricalcolo fallito.
3. `parseImportoManuale` con un `replace` non globale — bug vero, fotografato e
   non corretto: lo stesso pattern e' in ~25 punti dell'app e va sistemato tutto
   insieme, con la sua finestra di deploy.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-costi-gruppo"
RICHIEDE = [
    "parseImportoManuale", "importoValido", "datiCostoValidi",
    "mostraAvvisoDaClassificare", "frammentoConteggioCosti", "frammentoNonCorreggibili",
    "esitoCorrezioneCategoria", "segnaliDisattivati", "pvEsclusi", "applicaToggle",
]


def _ts(espr, arg=None):
    return esegui_ts(MODULO, espr, argomento=arg, richiede=RICHIEDE)


# ─── parseImportoManuale: il bug fotografato ────────────────────────────────

@pytest.mark.parametrize("testo,atteso", [
    ("2000", 2000),
    ("2000,50", 2000.5),
    ("0,99", 0.99),
    ("-500", -500),
])
def test_parse_importo_casi_che_funzionano(testo, atteso):
    assert _ts("emit(m.parseImportoManuale(input))", testo) == atteso


@pytest.mark.parametrize("testo", ["1.234,56", "1.234.567,89", "1,2,3"])
def test_fotografa_separatore_migliaia_produce_nan(testo):
    """ANOMALIA: i punti delle migliaia non vengono tolti -> Number(...) e' NaN.

    L'utente si vede rifiutare un importo valido con un messaggio che parla di
    campi mancanti. Non corretto qui: stesso pattern in ~25 punti dell'app.
    """
    assert _ts("emit(Number.isNaN(m.parseImportoManuale(input)))", testo) is True


def test_replaceall_non_sarebbe_il_fix():
    """Il `replace` non globale NON e' la causa del bug, ed e' una trappola.

    Sembra il colpevole ovvio ("manca la /g"), ma `replaceAll` lascia il difetto
    identico: a rompere la conversione e' il PUNTO delle migliaia, non la seconda
    virgola. Il mutante replace->replaceAll infatti sopravvive, ed e' equivalenza
    vera, non una lacuna dei test.

    Questo test tiene il chiodo dove serve: il fix e' togliere i separatori di
    migliaia prima di convertire la virgola.
    """
    r = _ts("""const t = input;
        emit({
          oggi: Number(t.replace(",", ".")),
          replaceAll: Number(t.replaceAll(",", ".")),
          fixVero: Number(t.replace(/\\./g, "").replace(",", ".")),
        });""", "1.234,56")
    assert r["oggi"] is None and r["replaceAll"] is None  # entrambi NaN -> null in JSON
    assert r["fixVero"] == 1234.56


def test_parse_importo_stringa_vuota_e_zero():
    """`Number("")` e' 0, non NaN: e' `importoValido` a respingerlo."""
    assert _ts("emit(m.parseImportoManuale(''))") == 0


# ─── importoValido: la guardia che cattura NaN ──────────────────────────────

@pytest.mark.parametrize("imp,atteso", [(1, True), (0.01, True), (0, False), (-5, False)])
def test_importo_valido(imp, atteso):
    assert _ts(f"emit(m.importoValido({imp}))") is atteso


def test_importo_valido_respinge_nan():
    """Il motivo per cui la forma e' `imp > 0` usata negata, e non `imp <= 0`:
    ogni confronto con NaN e' false, quindi `!(NaN > 0)` e' true (respinto) ma
    `NaN <= 0` e' false (accettato). E' la differenza fra bloccare e scrivere
    spazzatura nel database."""
    assert _ts("emit(m.importoValido(NaN))") is False
    assert _ts("emit(NaN <= 0)") is False  # la riscrittura "equivalente" fallirebbe


def test_dati_costo_validi():
    assert _ts("emit(m.datiCostoValidi('Stipendi', 100, 'PERSONALE'))") is True


@pytest.mark.parametrize("args", [
    "'', 100, 'X'",
    "'   ', 100, 'X'",
    "'Stipendi', 0, 'X'",
    "'Stipendi', NaN, 'X'",
    "'Stipendi', 100, ''",
])
def test_dati_costo_invalidi(args):
    assert _ts(f"emit(m.datiCostoValidi({args}))") is False


# ─── l'avviso "da classificare" ─────────────────────────────────────────────

@pytest.mark.parametrize("imp,atteso", [
    (100, True), (0.01, True), (0, False), (None, False), (-5, False),
])
def test_mostra_avviso(imp, atteso):
    val = "null" if imp is None else imp
    assert _ts(f"emit(m.mostraAvvisoDaClassificare({val}))") is atteso


def test_mostra_avviso_campo_assente():
    assert _ts("emit(m.mostraAvvisoDaClassificare(undefined))") is False


@pytest.mark.parametrize("n,atteso", [
    (1, " (1 costo)"),
    (3, " (3 costi)"),
    (0, ""),
    (None, ""),
])
def test_frammento_conteggio(n, atteso):
    val = "null" if n is None else n
    assert _ts(f"emit(m.frammentoConteggioCosti({val}))") == atteso


def test_frammento_conteggio_undefined():
    assert _ts("emit(m.frammentoConteggioCosti(undefined))") == ""


@pytest.mark.parametrize("nc,costi,atteso", [
    (2, 5, "2 di questi costi non hanno righe"),
    (1, 5, "1 di questi costi non ha righe"),
    (5, 5, "Nessuno di questi costi ha righe"),
    (0, 5, None),
])
def test_frammento_non_correggibili(nc, costi, atteso):
    assert _ts(f"emit(m.frammentoNonCorreggibili({nc}, {costi}))") == atteso


def test_frammento_non_correggibili_due_undefined():
    """Se entrambi mancassero, `undefined === undefined` direbbe "Nessuno di
    questi costi ha righe" — ma la guardia `> 0` non ci fa mai arrivare."""
    assert _ts("emit(m.frammentoNonCorreggibili(undefined, undefined))") is None


# ─── l'esito della correzione ───────────────────────────────────────────────

def test_esito_ricalcolo_fallito_e_warning():
    assert _ts("emit(m.esitoCorrezioneCategoria({ricalcolo_quote_ok: false}))") == {
        "tipo": "warning",
        "messaggio": "Categoria aggiornata, ma il ricalcolo delle quote non è riuscito. Riprova più tardi.",
    }


def test_esito_campo_assente_non_allarma():
    """`=== false` e non `!ricalcolo_quote_ok`: una risposta di un backend
    precedente non ha il campo, e non deve far comparire un allarme."""
    assert _ts("emit(m.esitoCorrezioneCategoria({}).tipo)") == "success"
    assert _ts("emit(m.esitoCorrezioneCategoria({ricalcolo_quote_ok: null}).tipo)") == "success"


def test_esito_ricalcolo_riuscito_con_una_sede():
    assert _ts("emit(m.esitoCorrezioneCategoria({ricalcolo_quote_ok: true, sedi_impattate: ['Centro']}))") == {
        "tipo": "success",
        "messaggio": "Categoria aggiornata · vale per Centro",
    }


def test_esito_senza_sedi():
    assert _ts("emit(m.esitoCorrezioneCategoria({sedi_impattate: []}).messaggio)") == "Categoria aggiornata"


def test_fotografa_join_sgrammaticato_su_tre_sedi():
    """ANOMALIA: `join(" e ")` produce "A e B e C". E' cio' che il cliente legge."""
    assert _ts(
        "emit(m.esitoCorrezioneCategoria({sedi_impattate: input}).messaggio)",
        ["Centro", "Nord", "Sud"],
    ) == "Categoria aggiornata · vale per Centro e Nord e Sud"


def test_esito_sedi_assenti():
    assert _ts("emit(m.esitoCorrezioneCategoria({}).messaggio)") == "Categoria aggiornata"


# ─── config assistente: cosa si esclude ─────────────────────────────────────

_SEGNALI = [
    {"key": "mol_basso", "enabled": True},
    {"key": "spreco", "enabled": False},
    {"key": "prezzi", "enabled": False},
]
_PV = [
    {"ristorante_id": "r1", "incluso": True},
    {"ristorante_id": "r2", "incluso": False},
]


def test_segnali_disattivati_e_l_inverso_degli_spuntati():
    assert _ts("emit(m.segnaliDisattivati(input))", _SEGNALI) == ["spreco", "prezzi"]


def test_pv_esclusi():
    assert _ts("emit(m.pvEsclusi(input))", _PV) == ["r2"]


def test_fotografa_liste_vuote_producono_liste_vuote():
    """ANOMALIA, la piu' seria dell'area.

    Lista vuota in ingresso -> lista vuota nel POST, che il backend legge come
    "l'utente non ha escluso niente". Ma la lista vuota e' anche lo stato
    INIZIALE del componente, quello in cui si resta se il load fallisce: salvare
    in quel momento riattiva in silenzio tutto cio' che era stato escluso.

    Oggi l'unica difesa e' il `disabled` del pulsante Salva — una guardia di
    interfaccia su una regola di dati. Non spostata qui in questa passata perche'
    chiuderla cambia il comportamento (con un backend che risponde `200 {}` il
    Salva oggi e' abilitato). Questo test tiene il buco visibile ed e' il punto
    d'aggancio del fix.

    Nota metodologica: su lista vuota nessuna mutazione di queste due funzioni e'
    osservabile — qualunque filtro su `[]` da' `[]`. E' un mutante IMPOSSIBILE,
    non un mutante sopravvissuto: la differenza va detta nel bilancio.
    """
    assert _ts("emit([m.segnaliDisattivati([]), m.pvEsclusi([])])") == [[], []]


def test_segnali_tutti_attivi_non_esclude_niente():
    """Indistinguibile dal caso "load fallito" guardando solo il payload."""
    assert _ts("emit(m.segnaliDisattivati(input))", [{"key": "a", "enabled": True}]) == []


# ─── applicaToggle ──────────────────────────────────────────────────────────

def test_applica_toggle_cambia_solo_il_corrispondente():
    assert _ts(
        "emit(m.applicaToggle(input, (s) => s.key === 'b', {enabled: true}))",
        [{"key": "a", "enabled": False}, {"key": "b", "enabled": False}],
    ) == [{"key": "a", "enabled": False}, {"key": "b", "enabled": True}]


def test_applica_toggle_non_muta_la_lista_originale():
    """E' uno stato React: mutarlo in place non farebbe ri-renderizzare."""
    assert _ts(
        """const orig = [{key:'a', enabled:false}];
        const nuovo = m.applicaToggle(orig, (s) => s.key === 'a', {enabled: true});
        emit({originale: orig[0].enabled, nuovo: nuovo[0].enabled, stessoRif: orig === nuovo});"""
    ) == {"originale": False, "nuovo": True, "stessoRif": False}


def test_applica_toggle_nessun_corrispondente():
    assert _ts(
        "emit(m.applicaToggle(input, (s) => s.key === 'zzz', {enabled: true}))",
        [{"key": "a", "enabled": False}],
    ) == [{"key": "a", "enabled": False}]


def test_applica_toggle_conserva_gli_altri_campi():
    assert _ts(
        "emit(m.applicaToggle(input, (p) => p.ristorante_id === 'r1', {incluso: false}))",
        [{"ristorante_id": "r1", "nome": "Centro", "incluso": True}],
    ) == [{"ristorante_id": "r1", "nome": "Centro", "incluso": False}]
