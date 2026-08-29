"""La saturazione del pool si misura su cio' che il server ha mandato.

Difetto F7 (29/8/2026): `poolSaturo: pool.length >= 500` misurava la soglia
**dopo** i filtri client invece che prima. La RPC di catena tronca a 500
(`routers/gruppo.py`, `p_limit`), ma `pool` era gia' passato per `giaAssociate`
e per il testo digitato: sull'account reale (4 PV, 4.518 descrizioni esistenti,
500 ricevute) con 67 associazioni scendeva a 433, la guardia non scattava piu' e
la dialog tornava a mostrare una cifra falsa — «Altri 373 prodotti non
mostrati», quando quelli veri erano migliaia. Bastava digitare una lettera.

Il fix e' passato da `tsc`, sembrava giusto a leggerlo e **non scattava su
nessuno dei 3 casi reali**: l'ha trovato il `code-reviewer`, non i tipi. Questi
test lo rendono una regressione visibile.

**Limite dichiarato.** Qui si prova che `calcolaCandidati` calcoli `poolSaturo`
su `risposta`, non che il componente le passi `risposta` e non il pool filtrato.
Quel refuso resta possibile: il componente non e' testato (nessun rendering).
Mitigazione a costo zero gia' applicata: il parametro si chiama `risposta`, e'
il primo, e nel componente non esiste una variabile filtrata prima della
chiamata. Un buco dichiarato e' gestibile, uno taciuto no.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/tag-candidati"
RICHIEDE = ["calcolaCandidati"]

# Le costanti vivono nel modulo: leggerle di qui invece di riscrivere 500/60
# significa che se il backend cambia `p_limit` il test non mente.
LIMITE, VISIBILI = esegui_ts(
    MODULO,
    "emit([m.RPC_LIMITE_DESCRIZIONI, m.MAX_CANDIDATI_VISIBILI]);",
    richiede=RICHIEDE,
)


def _calcola(n_risposta, n_associate=0, filtro="", in_ricerca=False, prefisso="PRODOTTO"):
    return esegui_ts(
        MODULO,
        """
const { n, nAss, filtro, inRicerca, prefisso } = input;
const risposta = Array.from({ length: n }, (_, i) => ({
  descrizione: prefisso + " " + i, descrizione_key: "k" + i,
}));
const gia = new Set(risposta.slice(0, nAss).map((d) => d.descrizione_key));
const r = m.calcolaCandidati(risposta, gia, filtro, inRicerca);
emit({ candidati: r.candidati.length, nascosti: r.nascosti, poolSaturo: r.poolSaturo });
""",
        argomento={"n": n_risposta, "nAss": n_associate, "filtro": filtro,
                   "inRicerca": in_ricerca, "prefisso": prefisso},
        richiede=RICHIEDE,
    )


def test_lo_scenario_reale_che_sfuggiva():
    """4 PV, 500 ricevute dalla RPC, 67 gia' associate: pool filtrato = 433.

    E' il caso misurato in produzione. Prima del fix `poolSaturo` era False
    perche' 433 < 500, e la dialog dichiarava un numero di nascosti che non
    era quello vero.
    """
    r = _calcola(LIMITE, n_associate=67)
    assert r["poolSaturo"] is True, (
        "poolSaturo misurato dopo i filtri client: e' il difetto F7"
    )


def test_resta_saturo_anche_digitando():
    """La seconda meta' del bug: bastava una lettera per far ricomparire la
    cifra falsa, perche' il filtro sul testo riduceva ancora il pool."""
    r = _calcola(LIMITE, n_associate=67, filtro="P")
    assert r["poolSaturo"] is True

    # Anche con un filtro che non lascia passare NIENTE: la saturazione e' una
    # proprieta' della risposta, non di cio' che resta.
    vuoto = _calcola(LIMITE, n_associate=67, filtro="ZZZNESSUNO")
    assert vuoto["candidati"] == 0 and vuoto["nascosti"] == 0
    assert vuoto["poolSaturo"] is True


@pytest.mark.parametrize(
    "n, atteso",
    [(LIMITE - 1, False), (LIMITE, True), (LIMITE + 1, True)],
)
def test_confine_della_soglia(n, atteso):
    """`>=`, non `>`: a 500 esatte la risposta e' gia' troncata."""
    assert _calcola(n)["poolSaturo"] is atteso


@pytest.mark.parametrize(
    "n, candidati, nascosti",
    [(0, 0, 0), (VISIBILI - 1, VISIBILI - 1, 0), (VISIBILI, VISIBILI, 0),
     (VISIBILI + 1, VISIBILI, 1)],
)
def test_confine_del_taglio_a_60(n, candidati, nascosti):
    """`nascosti` mente se non conta il pool filtrato: e' quello che il
    cliente legge come «Altri N prodotti non mostrati»."""
    r = _calcola(n)
    assert (r["candidati"], r["nascosti"]) == (candidati, nascosti)


def test_le_gia_associate_escono_dai_candidati():
    r = _calcola(100, n_associate=40)
    assert r["candidati"] == VISIBILI
    assert r["nascosti"] == 0  # 100 - 40 = 60 -> nessuno nascosto


def test_in_ricerca_non_rifiltra_il_testo_del_server():
    """In ricerca il filtro l'ha gia' applicato il server: riapplicarlo qui
    scarterebbe risultati che il server considera pertinenti (es. match sul
    codice o sul fornitore, non sulla descrizione)."""
    r = _calcola(10, filtro="NESSUNMATCH", in_ricerca=True)
    assert r["candidati"] == 10, (
        "in ricerca i risultati del server vengono rifiltrati sul testo: "
        "spariscono match legittimi"
    )
    # Fuori ricerca invece il filtro locale deve agire.
    locale = _calcola(10, filtro="NESSUNMATCH", in_ricerca=False)
    assert locale["candidati"] == 0


def test_il_filtro_locale_ignora_maiuscole_e_spazi():
    assert _calcola(5, filtro="  prodotto  ")["candidati"] == 5
    assert _calcola(5, filtro="pRoDoTtO")["candidati"] == 5
