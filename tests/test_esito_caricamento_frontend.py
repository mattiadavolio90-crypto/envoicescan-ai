"""La differenza fra "non c'e' niente" e "non sono riuscito a chiedere".

**Il difetto, misurato il 3/9/2026 (R10).** I caricamenti server tornano `null`
su *ogni* fallimento — token assente, non-2xx, timeout, rete giu'. Le pagine
scrivevano `data?.documenti ?? []`, e quel `null` diventava una lista vuota: il
cliente leggeva **«Nessun documento trovato»** mentre il worker era giu'.

Non e' teorico. Railway spegne il worker quando non e' usato e il risveglio
sfora il timeout di 8s: `BlockRetry` esiste per quello. Su `/scadenziario` il
costo e' misurabile a DB: **3.219 fatture non pagate, 4,4 M€, 1.891 gia'
scadute, su 11 sedi su 11**.

`esitoLista` obbliga a distinguere i due casi. Questi test provano che la
distinzione regge, **inclusa** la differenza che conta: una risposta *arrivata*
ma senza il campo e' un vuoto legittimo, un `null` no.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/esito-caricamento"
RICHIEDE = ["esitoLista"]


def _esito(risposta: str, campo: str = "righe"):
    return esegui_ts(
        MODULO,
        f"emit(m.esitoLista({risposta}, {campo!r}))",
        richiede=RICHIEDE,
    )


def test_null_non_e_una_lista_vuota():
    """Il cuore del difetto: `null` = "non lo so", non "zero righe"."""
    assert _esito("null")["stato"] == "non_disponibile"


def test_undefined_e_trattato_come_null():
    assert _esito("undefined")["stato"] == "non_disponibile"


def test_lista_piena_passa_intatta():
    esito = _esito('{ righe: [1, 2, 3] }')
    assert esito["stato"] == "ok"
    assert esito["righe"] == [1, 2, 3]


def test_lista_vuota_arrivata_e_un_vuoto_legittimo():
    """Il worker ha risposto «zero righe»: quello e' un vuoto vero, e si mostra."""
    esito = _esito('{ righe: [] }')
    assert esito["stato"] == "ok"
    assert esito["righe"] == []


def test_risposta_senza_il_campo_atteso_e_vuoto_non_errore():
    """Distinzione che conta: la risposta e' ARRIVATA, manca solo il campo.

    Trattarla come "non disponibile" farebbe apparire un errore dove il worker
    ha risposto correttamente con un payload senza righe.
    """
    esito = _esito('{ altro: 1 }')
    assert esito["stato"] == "ok"
    assert esito["righe"] == []


def test_campo_non_array_non_esplode():
    """Un payload malformato non deve far crashare la pagina."""
    for valore in ('"stringa"', "42", "null", "{}"):
        esito = _esito(f'{{ righe: {valore} }}')
        assert esito["stato"] == "ok"
        assert esito["righe"] == []



# ─── Che le pagine lo USINO davvero ────────────────────────────────────────
#
# I test sopra provano che `esitoLista` distingue i due casi. Questi provano che
# le pagine la chiamano: rimettere `?? []` le lascerebbe altrimenti verdi.

import pathlib

_APP = pathlib.Path(__file__).resolve().parents[1] / "apps/web/src/app"

# Le pagine dove un falso "vuoto" MENTE AL CLIENTE. Le pagine admin non sono in
# lista: le vede solo l'owner, e un elenco vuoto li' non rassicura nessuno.
_PAGINE_CLIENTE = [
    "(app)/scadenziario/page.tsx",
    "(app)/catena/fatture/page.tsx",
    "(app)/notifiche/page.tsx",
    "(mobile)/m/notifiche/page.tsx",
    "(app)/analisi-e-tag/page.tsx",
    "(app)/analisi-fatture/page.tsx",
]


def _codice_vivo(percorso: pathlib.Path) -> str:
    """Il sorgente senza le righe commentate.

    Serve perche' una `?? []` neutralizzata dentro un commento non e' un
    difetto, e una chiamata commentata via non e' un presidio: cercare il
    testo grezzo sbaglierebbe in entrambe le direzioni.
    """
    return "\n".join(
        r for r in percorso.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith("//")
    )


@pytest.mark.parametrize("pagina", _PAGINE_CLIENTE)
def test_le_pagine_cliente_distinguono_il_guasto_dal_vuoto(pagina):
    vivo = _codice_vivo(_APP / pagina)
    assert "esitoLista" in vivo, (
        f"{pagina} non usa piu' `esitoLista`: un worker giu' torna a diventare "
        "una lista vuota, e la pagina rassicura il cliente su un guasto (R10)"
    )
    assert "non_disponibile" in vivo, (
        f"{pagina} non guarda piu' lo stato dell'esito: senza, `esitoLista` "
        "viene chiamata ma il guasto resta indistinguibile dal vuoto"
    )


@pytest.mark.parametrize("pagina", _PAGINE_CLIENTE)
def test_le_pagine_cliente_non_schiacciano_piu_il_null(pagina):
    """Il difetto originale, nella sua forma esatta.

    `?? []` su una risposta che puo' essere `null` e' il modo in cui "non sono
    riuscito a chiedere" diventava "non c'e' niente".
    """
    vivo = _codice_vivo(_APP / pagina)
    assert "?? []" not in vivo, (
        f"{pagina} e' tornata a `?? []` su una risposta che puo' essere null: "
        "e' esattamente il difetto R10"
    )


def test_lo_stato_vuoto_dello_scadenziario_dipende_dal_flag():
    """Il messaggio al cliente, non solo il dato che ci arriva.

    Passare `caricamentoFallito` senza usarlo nel testo lascerebbe la pagina
    dire ancora «Nessun documento trovato» su un guasto.
    """
    vivo = _codice_vivo(_APP / "(app)/scadenziario/scadenziario-client.tsx")
    assert "caricamentoFallito" in vivo, "il client non riceve piu' il flag"
    assert "Non è stato possibile caricare le scadenze" in vivo, (
        "il messaggio onesto e' sparito: su un guasto il cliente rilegge "
        "«Nessun documento trovato»"
    )


# ─── La SCELTA del messaggio, eseguita ─────────────────────────────────────
#
# Perche' questi test esistono, e i grep sul sorgente non bastano (3/9/2026).
# Il `code-reviewer` ha ucciso i presidi precedenti con due mutanti che il
# testo del sorgente non vede:
#
#   const fallito = esito.stato === "non_disponibile" ? false : false;
#   {false && caricamentoFallito && documenti.length === 0 ? ... }
#
# In entrambi i casi la stringa onesta resta scritta nel file — e non compare
# mai a schermo. L'unico modo di provarlo e' ESEGUIRE la scelta, e l'harness
# esegue `lib/`, non i `.tsx`: per questo la decisione e' stata estratta in
# `messaggioListaVuota` / `mostraGuasto` invece di restare un ternario nel JSX.


def _messaggio(fallito: str, righe: int, filtri: str = "false") -> str:
    return esegui_ts(
        MODULO,
        f"""emit(m.messaggioListaVuota({{
          caricamentoFallito: {fallito}, righeCaricate: {righe},
          filtriAttivi: {filtri},
          guasto: "GUASTO", vuoto: "VUOTO", conFiltri: "FILTRI",
        }}))""",
        richiede=["messaggioListaVuota"],
    )


def test_worker_giu_e_lista_vuota_mostra_il_guasto():
    """Il caso che R10 corregge: niente dati E caricamento fallito."""
    assert _messaggio("true", 0) == "GUASTO"


def test_lista_vuota_davvero_non_mostra_il_guasto():
    """Il worker ha risposto «zero righe»: non e' un errore."""
    assert _messaggio("false", 0) == "VUOTO"


def test_dopo_un_retry_riuscito_il_guasto_sparisce():
    """La guardia `righeCaricate === 0`.

    Il client rifa' il fetch: se arrivano dati, il messaggio d'errore non deve
    restare appiccicato a una lista che ora e' piena.
    """
    assert _messaggio("true", 5) != "GUASTO"


def test_il_guasto_vince_sui_filtri():
    """Con un guasto, «nessuna riga corrisponde ai filtri» sarebbe fuorviante:
    non sappiamo neanche cosa ci fosse da filtrare."""
    assert _messaggio("true", 0, filtri="true") == "GUASTO"


def test_i_filtri_valgono_solo_quando_il_caricamento_e_riuscito():
    assert _messaggio("false", 0, filtri="true") == "FILTRI"


@pytest.mark.parametrize(
    "fallito,righe,atteso",
    [("true", 0, True), ("false", 0, False), ("true", 3, False), ("false", 3, False)],
)
def test_mostra_guasto_e_la_gemella_booleana(fallito, righe, atteso):
    """Per i casi in cui i due rami sono JSX diversi, non due stringhe."""
    got = esegui_ts(
        MODULO,
        f"emit(m.mostraGuasto({fallito}, {righe}))",
        richiede=["mostraGuasto"],
    )
    assert got is atteso


@pytest.mark.parametrize(
    "pagina,funzione",
    [
        ("(app)/scadenziario/scadenziario-client.tsx", "messaggioListaVuota"),
        ("(app)/notifiche/page.tsx", "messaggioListaVuota"),
        ("(mobile)/m/notifiche/page.tsx", "messaggioListaVuota"),
        ("(app)/analisi-fatture/articoli-tab.tsx", "messaggioListaVuota"),
        ("(app)/analisi-e-tag/analisi-e-tag-client.tsx", "mostraGuasto"),
        # L9, 17/09/2026: il fix di R10 era arrivato al desktop e non a `/m`.
        # Su 6 file mobile con uno stato vuoto, uno solo (notifiche) delegava.
        # Gli altri quattro dicevano «Nessun incasso inserito in questo mese.»
        # anche quando il worker non aveva risposto — con lo stato iniziale a
        # `null`, cioe' proprio all'apertura della pagina. Il toast d'errore
        # sparisce dopo pochi secondi e lascia in pagina la frase falsa.
        # Delegano a `statoLista`, che i test ESEGUONO: vedi sopra.
        ("(mobile)/m/diario/mobile-incassi.tsx", "statoLista"),
        ("(mobile)/m/diario/mobile-spese.tsx", "statoLista"),
        ("(mobile)/m/diario/mobile-diario.tsx", "statoLista"),
        ("(mobile)/m/turni/mobile-turni.tsx", "statoLista"),
    ],
)
def test_le_pagine_delegano_la_scelta_invece_di_riscriverla(pagina, funzione):
    """Il ponte fra i test di comportamento e le pagine.

    I test sopra provano che la funzione sceglie bene; questo prova che le
    pagine la chiamano invece di rifare il ternario a mano — dove tornerebbe
    neutralizzabile senza che nessun test se ne accorga.
    """
    vivo = _codice_vivo(_APP / pagina)
    assert funzione in vivo, (
        f"{pagina} non delega piu' a `{funzione}`: la scelta del messaggio e' "
        "tornata nel JSX, dove un `false &&` la spegne senza rompere un test"
    )


# ─── L'ultimo miglio: la riga della pagina che non si puo' eseguire ─────────
#
# `esegui_ts` importa moduli `.ts`, non `.tsx` (helpers_ts.py): la riga in cui
# una PAGINA calcola il proprio flag non e' eseguibile dai test. Resta leggibile,
# e va letta nella sua FORMA ESATTA — non cercando una sottostringa.
#
# Misurato il 3/9: il `code-reviewer` ha ucciso la versione a sottostringa con
#     const fallito = esito.stato === "non_disponibile" ? false : false;
# che contiene il testo cercato e vale sempre `false`. Un `assert "x" in testo`
# non distingue "l'espressione e' questa" da "l'espressione contiene questa".

_FLAG_ATTESO = {
    "(app)/notifiche/page.tsx": 'const fallito = esito.stato === "non_disponibile";',
    "(mobile)/m/notifiche/page.tsx": 'const fallito = esito.stato === "non_disponibile";',
    "(app)/scadenziario/page.tsx":
        'caricamentoFallito={esito.stato === "non_disponibile"}',
    "(app)/catena/fatture/page.tsx":
        'caricamentoFallito={esito.stato === "non_disponibile"}',
}


# ─── I client mobile: la decisione ESEGUITA, non letta ─────────────────────
#
# Primo giro di L9: i presidi leggevano la FORMA delle righe dei `.tsx`, perche'
# l'harness esegue `lib/` e non i componenti. Il code-reviewer ha costruito due
# mutanti EVASIVI — scritti sapendo cosa il test cerca — e sono sopravvissuti
# entrambi, ripristinando il difetto intero con la suite verde:
#
#     ) : (false && mostraGuasto(fallito, voci.length)) ? (   // ramo spento
#     } finally { setFallito(false); setLoading(false); }     // flag riazzerato
#
# Il secondo e' il piu' insidioso: soddisfa alla lettera un test che chiede
# «esiste setFallito(true) ed esiste setFallito(false)», mentre il reset a ogni
# giro cancella il primo. La lezione e' quella di [assert-in-non-e-assert-uguale]
# portata un passo piu' in la': nessuna lettura del sorgente chiude la famiglia,
# perche' i modi di spegnere un ramo sono infiniti e i modi di cercarlo no.
#
# La decisione e' stata quindi ESTRATTA in `statoLista` (lib/), dove i test la
# eseguono davvero. Nei `.tsx` resta una riga che la chiama e tre rami che
# confrontano il risultato: la logica che puo' sbagliare sta tutta qui sotto.


def _stato(caricamento: str, fallito: str, righe: int) -> str:
    return esegui_ts(
        MODULO,
        f"""emit(m.statoLista({{
          caricamento: {caricamento}, caricamentoFallito: {fallito},
          righeCaricate: {righe},
        }}))""",
        richiede=["statoLista"],
    )


@pytest.mark.parametrize(
    "caricamento,fallito,righe,atteso",
    [
        # Lo skeleton vince su tutto: mentre carica non si afferma niente.
        ("true", "false", 0, "caricamento"),
        ("true", "true", 0, "caricamento"),
        ("true", "true", 5, "caricamento"),
        # Finito il caricamento, con righe si mostrano le righe.
        ("false", "false", 3, "dati"),
        # Il caso del difetto: niente righe E caricamento fallito.
        ("false", "true", 0, "guasto"),
        # Il vuoto vero: il worker ha risposto «zero».
        ("false", "false", 0, "vuoto"),
        # Dopo un retry riuscito il guasto non resta appiccicato ai dati.
        ("false", "true", 7, "dati"),
    ],
)
def test_stato_lista_distingue_i_quattro_casi(caricamento, fallito, righe, atteso):
    """Il cuore di L9, eseguito: nessun mutante evasivo sopravvive a questo."""
    assert _stato(caricamento, fallito, righe) == atteso


def test_stato_lista_non_dice_mai_vuoto_su_un_guasto():
    """La proprieta' in forma generale, su tutta la griglia.

    Scritta separata dai casi sopra perche' e' l'invariante che il difetto
    violava: con `caricamentoFallito` e zero righe, la risposta non puo' essere
    "vuoto" — cioe' l'affermazione «non hai niente» su dati mai arrivati.
    """
    for righe in (0, 1, 50):
        for caricamento in ("true", "false"):
            got = _stato(caricamento, "true", righe)
            if caricamento == "false" and righe == 0:
                assert got == "guasto"
            else:
                assert got != "vuoto"


# ─── Il ponte: i client chiamano la funzione, e nessun ramo resta scoperto ───

_CLIENT_MOBILE = [
    "(mobile)/m/diario/mobile-incassi.tsx",
    "(mobile)/m/diario/mobile-spese.tsx",
    "(mobile)/m/diario/mobile-diario.tsx",
    "(mobile)/m/turni/mobile-turni.tsx",
]


@pytest.mark.parametrize("pagina", _CLIENT_MOBILE)
def test_ogni_stato_vuoto_mobile_passa_da_stato_lista(pagina):
    """Nessuna lista puo' dire «non c'e' niente» decidendolo da sola.

    Il difetto del primo giro non fu la logica ma il CENSIMENTO: in
    `mobile-turni.tsx` il flag fu collegato alla sola vista mese, e le altre due
    (mensile, e la giornaliera che e' il DEFAULT) restarono col difetto intero.
    Un test per file non lo avrebbe mai visto; questo conta i rami.

    La regola: ogni `length === 0` vivo deve avere accanto un ramo deciso da
    `statoLista`, cioe' tanti `stato* === "vuoto"` quanti sono gli stati vuoti.
    """
    vivo = _codice_vivo(_APP / pagina)
    assert "statoLista(" in vivo, f"{pagina} non usa piu' statoLista"

    vuoti = vivo.count('=== "vuoto"')
    guasti = vivo.count('=== "guasto"')
    length0 = vivo.count("length === 0")
    assert length0 == 0, (
        f"{pagina}: restano {length0} `length === 0` che decidono da soli se "
        "mostrare uno stato vuoto. Ogni lista deve passare da `statoLista`, o "
        "quel ramo torna a dire «non c'e' niente» su dati mai arrivati (L9)."
    )
    assert vuoti == guasti, (
        f"{pagina}: {vuoti} rami «vuoto» ma {guasti} rami «guasto». Ogni vista "
        "ha la sua lista e il suo stato vuoto: se ne manca uno, quella vista "
        "conserva il difetto (in mobile-turni.tsx ne mancavano 2 su 3)."
    )
    assert vuoti >= 1, f"{pagina}: nessun ramo «vuoto» trovato"


@pytest.mark.parametrize("pagina", _CLIENT_MOBILE)
def test_il_ramo_del_guasto_mobile_non_e_spento_e_il_flag_non_e_riazzerato(pagina):
    """L'ultimo miglio, e il suo limite dichiarato.

    `statoLista` e' eseguita dai test, ma il suo USO nel JSX no: l'harness non
    importa i `.tsx` (`tests/helpers_ts.py`). Due mutanti evasivi del
    code-reviewer sopravvivono a ogni test di comportamento, perche' agiscono
    fuori dalla funzione:

        ) : (false && stato === "guasto") ? (      # il ramo non si accende mai
        } finally { setFallito(false); ... }       # il flag muore a ogni giro

    Questa e' una lettura del SORGENTE, con tutti i limiti che il resto del file
    documenta: uccide i due mutanti noti e le loro varianti dirette, non chiude
    la famiglia. La chiusura vera sarebbe un runner frontend (punto 9, ciclo
    2026-08: decisione esplicita di Mattia in senso contrario).
    """
    vivo = _codice_vivo(_APP / pagina)
    righe = [" ".join(r.split()) for r in vivo.splitlines()]

    # (a) nessun ramo «guasto» spento da una costante
    for r in righe:
        if '=== "guasto"' in r:
            assert "false &&" not in r and "&& false" not in r, (
                f"{pagina}: il ramo del guasto e' spento da una costante "
                f"({r!r}). Il difetto di L9 e' ripristinato: il cliente rilegge "
                "«non c'e' niente» su dati mai arrivati."
            )

    # (c) ogni chiamata passa il FLAG, non una costante. Mutante sopravvissuto
    # al primo giro di questa guardia:
    #     statoLista({ ..., caricamentoFallito: false, ... })
    # spegne il guasto di UNA vista sola — e in `mobile-turni.tsx` le viste sono
    # tre, quindi il difetto torna dove nessuno guarda.
    for r in righe:
        if "statoLista({" in r:
            assert "caricamentoFallito: fallito" in r, (
                f"{pagina}: una chiamata a statoLista non passa il flag ({r!r}). "
                "Con una costante quella vista non mostra mai il guasto."
            )

    # (b) il flag non viene riazzerato nel `finally`, che gira SEMPRE
    dentro_finally = False
    for r in righe:
        if r.startswith("} finally {"):
            dentro_finally = True
            continue
        if dentro_finally:
            if r in ("}", "});"):
                dentro_finally = False
                continue
            assert "setFallito(" not in r, (
                f"{pagina}: `setFallito` dentro il `finally` ({r!r}): gira a "
                "ogni caricamento, riuscito o no, e cancella il `true` del "
                "catch. Il flag va alzato nel catch e abbassato nel try."
            )


@pytest.mark.parametrize("pagina,atteso", sorted(_FLAG_ATTESO.items()))
def test_il_flag_della_pagina_ha_la_forma_esatta(pagina, atteso):
    """Nessun `? false : false`, nessun `&& false`, nessuna costante.

    Confronto sulla riga NORMALIZZATA (spazi collassati) e non con `in`: la
    riga deve *essere* quell'espressione, non contenerla.
    """
    vivo = _codice_vivo(_APP / pagina)
    righe = [" ".join(r.split()) for r in vivo.splitlines()]
    assert atteso in righe, (
        f"{pagina}: il flag non ha piu' la forma attesa `{atteso}`.\n"
        "Se l'hai rinominato aggiorna il test; se ci hai aggiunto un `? false` "
        "o un `&& false`, il messaggio onesto non compare piu' e il worker giu' "
        "torna a essere «non hai niente da fare» (R10)."
    )


@pytest.mark.parametrize(
    "file,chiamata",
    [
        ("(app)/scadenziario/scadenziario-client.tsx", "caricamentoFallito,"),
        ("(app)/notifiche/page.tsx", "caricamentoFallito: fallito,"),
        ("(mobile)/m/notifiche/page.tsx", "caricamentoFallito: fallito,"),
        ("(app)/analisi-fatture/articoli-tab.tsx", "caricamentoFallito,"),
    ],
)
def test_il_flag_arriva_alla_funzione_non_una_costante(file, chiamata):
    """Che alla scelta arrivi il flag VERO.

    `messaggioListaVuota({caricamentoFallito: false, ...})` chiamerebbe la
    funzione giusta con l'argomento sbagliato: i test di comportamento
    resterebbero verdi e la pagina mentirebbe lo stesso.
    """
    vivo = _codice_vivo(_APP / file)
    righe = [" ".join(r.split()) for r in vivo.splitlines()]
    assert chiamata in righe, (
        f"{file}: alla scelta del messaggio non arriva piu' il flag ma "
        "probabilmente una costante — il messaggio onesto non compare mai"
    )
