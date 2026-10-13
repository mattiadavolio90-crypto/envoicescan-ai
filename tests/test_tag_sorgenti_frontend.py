"""Sede e catena con lo stesso pannello e lo stesso riquadro «Modifica tag» (Fase C2).

`lib/tag-sorgenti.ts` dice dove leggono e scrivono e se la ricerca dei prodotti
va sul server (catena: la lista iniziale e' dei primi 500 per spesa, poi si
cerca fra tutti i punti vendita). In `lib/tag-selezione.ts` due aggiunte per la
catena: la ricerca gia' applicata dal server non si rifiltra, e le descrizioni
viste restano in memoria per il Salva.

Casi scelti dove la versione sbagliata da' un altro risultato:
- la riga che il server trova per una variante ma mostra con un'altra
  descrizione (il testo cercato non c'e'): rifiltrata nel browser sparirebbe;
- un prodotto del tag che NON e' fra i risultati: senza filtro resterebbe in
  lista anche se non c'entra col testo;
- una spunta uscita di lista con una ricerca successiva: al Salva serve ancora
  la sua descrizione, non la chiave usata come testo;
- `n` della catena letto come occorrenze, non 0.

Limite dichiarato: si prova la logica, non che i .tsx la colleghino.
"""
import pytest

from tests.helpers_ts import esegui_ts

SORGENTI = "lib/tag-sorgenti"
SELEZIONE = "lib/tag-selezione"


def _sorgenti(espressione, argomento=None):
    return esegui_ts(SORGENTI, f"emit({espressione});", argomento=argomento,
                     richiede=["urlRicerca", "urlDescrizioni", "ricercaSulServer", "descrizioniDaRisposta"])


def _selezione(codice, argomento=None):
    return esegui_ts(SELEZIONE, codice, argomento=argomento,
                     richiede=["righeSelettore", "ricordaDescrizioni", "corpoModifiche"])


# ─── Le due sorgenti ──────────────────────────────────────────────────────────
def test_le_basi_delle_rotte():
    assert _sorgenti("[m.sorgenteSede.base, m.sorgenteCatena.base]") == ["/api/tag", "/api/gruppo/tag"]
    assert _sorgenti("[m.urlDescrizioni(m.sorgenteSede), m.urlDescrizioni(m.sorgenteCatena)]") == [
        "/api/tag/descrizioni", "/api/gruppo/tag/descrizioni",
    ]


@pytest.mark.parametrize("testo, atteso", [
    ("", None), ("a", None), (" a ", None),
    ("ol", "/api/gruppo/tag/descrizioni?q=ol"),
    ("  olio  ", "/api/gruppo/tag/descrizioni?q=olio"),
    ("olio & aceto", "/api/gruppo/tag/descrizioni?q=olio%20%26%20aceto"),
], ids=["vuoto", "una-lettera", "una-lettera-con-spazi", "due-lettere", "spazi-tolti", "codificato"])
def test_la_catena_cerca_sul_server_da_due_lettere(testo, atteso):
    assert _sorgenti("m.urlRicerca(m.sorgenteCatena, input)", argomento=testo) == atteso


def test_la_sede_non_cerca_mai_sul_server():
    """La sede ha gia' tutta la lista: una richiesta per lettera sarebbe solo carico."""
    assert _sorgenti('["", "a", "olio"].map(t => m.urlRicerca(m.sorgenteSede, t))') == [None, None, None]
    assert _sorgenti('m.ricercaSulServer(m.sorgenteSede, "olio")') is False
    assert _sorgenti('m.ricercaSulServer(m.sorgenteCatena, "olio")') is True


def test_descrizioni_di_catena_con_n_come_occorrenze():
    risposta = {"descrizioni": [
        {"descrizione": "OLIO EVO 5L", "descrizione_key": "OLIO EVO 5L", "n": 42, "spesa": 1234.5},
        {"descrizione": "SALE", "descrizione_key": "SALE", "n": 0, "spesa": 3},
    ]}
    assert _sorgenti("m.descrizioniDaRisposta(input)", argomento=risposta) == [
        {"descrizione": "OLIO EVO 5L", "descrizione_key": "OLIO EVO 5L", "occorrenze": 42},
        {"descrizione": "SALE", "descrizione_key": "SALE", "occorrenze": 0},
    ]


def test_descrizioni_di_sede_tengono_le_occorrenze():
    risposta = {"descrizioni": [
        {"descrizione": "Burro", "descrizione_key": "BURRO", "occorrenze": 7, "num_fornitori": 2},
    ]}
    assert _sorgenti("m.descrizioniDaRisposta(input)", argomento=risposta) == [
        {"descrizione": "Burro", "descrizione_key": "BURRO", "occorrenze": 7},
    ]


@pytest.mark.parametrize("risposta", [
    None, {}, {"descrizioni": None}, {"descrizioni": "x"}, [],
], ids=["null", "vuota", "descrizioni-null", "descrizioni-stringa", "lista"])
def test_risposta_malformata_da_lista_vuota_non_eccezione(risposta):
    assert _sorgenti("m.descrizioniDaRisposta(input)", argomento=risposta) == []


def test_righe_senza_chiave_o_senza_testo_si_scartano():
    risposta = {"descrizioni": [
        {"descrizione": "   ", "descrizione_key": "X", "n": 1},
        {"descrizione": "Y", "descrizione_key": "", "n": 1},
        {"descrizione": "Z", "n": 1},
        None,
        {"descrizione": "OK", "descrizione_key": "OK", "n": 1},
    ]}
    assert [d["descrizione_key"] for d in _sorgenti("m.descrizioniDaRisposta(input)", argomento=risposta)] == ["OK"]


# ─── Ricerca gia' applicata dal server ───────────────────────────────────────
# Il server ha trovato «OLIO» in una variante, ma mostra l'ultima descrizione,
# «EXTRAVERGINE 5L», che il testo non lo contiene. Nel tag c'e' anche
# «ACETO BALSAMICO», che coi risultati non c'entra.
_RISULTATI = [
    {"descrizione": "OLIO DI SEMI", "descrizione_key": "OLIO DI SEMI", "occorrenze": 3},
    {"descrizione": "EXTRAVERGINE 5L", "descrizione_key": "EXTRAVERGINE 5L", "occorrenze": 9},
]
_NEL_TAG = [
    {"descrizione": "ACETO BALSAMICO", "descrizione_key": "ACETO BALSAMICO"},
    {"descrizione": "OLIO VECCHIO", "descrizione_key": "OLIO VECCHIO"},
]


def _chiavi(sul_server, filtro="tutti"):
    return _selezione(
        f'emit(m.righeSelettore(input.r, input.t, "olio", "{filtro}", new Set(), {str(sul_server).lower()})'
        '.corrispondenti.map(r => r.descrizione_key));',
        argomento={"r": _RISULTATI, "t": _NEL_TAG},
    )


def test_coi_risultati_del_server_non_si_rifiltra():
    assert _chiavi(True) == ["OLIO DI SEMI", "EXTRAVERGINE 5L", "OLIO VECCHIO"]


def test_senza_server_il_testo_filtra_anche_le_descrizioni():
    """Il caso gemello: la sede filtra nel browser e la riga senza il testo esce."""
    assert _chiavi(False) == ["OLIO DI SEMI", "OLIO VECCHIO"]


def test_nel_tag_coi_risultati_del_server_resta_il_filtro_sul_testo():
    assert _chiavi(True, "nel_tag") == ["OLIO VECCHIO"]


# ─── Memoria delle descrizioni viste ─────────────────────────────────────────
def test_la_spunta_uscita_di_lista_si_salva_con_la_sua_descrizione():
    """Spuntata «Olio Evo» in una ricerca, poi cercato «sale»: il Salva deve
    mandare «Olio Evo», non la chiave usata come testo."""
    out = _selezione(
        """
let mem = m.ricordaDescrizioni(new Map(), input.prima);
mem = m.ricordaDescrizioni(mem, input.dopo);
const righe = [...mem].map(([descrizione_key, descrizione]) => ({ descrizione, descrizione_key }));
emit(m.corpoModifiche({ aggiungi: ["OLIO EVO"], togli: [] }, righe));
""",
        argomento={
            "prima": [{"descrizione": "Olio  Evo", "descrizione_key": "OLIO EVO", "occorrenze": 4}],
            "dopo": [{"descrizione": "Sale fino", "descrizione_key": "SALE FINO", "occorrenze": 2}],
        },
    )
    assert out == {"aggiungi": [{"descrizione": "Olio  Evo", "descrizione_key": "OLIO EVO", "fattore_kg": None}],
                   "togli": []}


def test_la_memoria_tiene_la_prima_descrizione_vista_e_non_tocca_l_originale():
    out = _selezione(
        """
const base = new Map([["A", "prima"]]);
const nuova = m.ricordaDescrizioni(base, [{ descrizione: "dopo", descrizione_key: "A" }, { descrizione: "b", descrizione_key: "B" }]);
emit({ nuova: [...nuova], base: [...base] });
""",
    )
    assert out == {"nuova": [["A", "prima"], ["B", "b"]], "base": [["A", "prima"]]}
