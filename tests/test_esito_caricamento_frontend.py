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
RICHIEDE = ["esitoLista", "davveroVuota"]


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


@pytest.mark.parametrize(
    "risposta,atteso",
    [
        ("null", False),               # non lo so -> NON e' "davvero vuota"
        ("{ righe: [] }", True),       # il worker ha detto zero
        ("{ righe: [1] }", False),
    ],
)
def test_davvero_vuota_solo_quando_lo_sappiamo(risposta, atteso):
    """La guardia che le pagine useranno per scrivere «Nessun documento».

    Se questo test cade, torna possibile rassicurare il cliente su un errore.
    """
    got = esegui_ts(
        MODULO,
        f"emit(m.davveroVuota(m.esitoLista({risposta}, 'righe')))",
        richiede=RICHIEDE,
    )
    assert got is atteso


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
