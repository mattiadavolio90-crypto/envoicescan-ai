"""Cartelle e preferiti della barra dei tag (lib/tag-cartelle.ts).

Fase 2 di «Analisi e Tag» (13/10/2026): i tag si raccolgono in cartelle per
sede, ordinabili trascinandole, e si segnano con la stella. Servono solo a
organizzare la barra, non entrano in nessuna analisi.

Le regole che un'implementazione plausibile sbaglierebbe, provate con casi in
cui la versione sbagliata da' un risultato diverso:
- le cartelle vanno per (ordine, id): ordinare per id, o solo per ordine con
  un ordinamento stabile, da' un'altra sequenza sullo stesso input;
- una cartella vuota resta in barra (ci si deve poter trascinare dentro);
- un tag che punta a una cartella sconosciuta finisce in «Senza cartella»
  invece di sparire; «Senza cartella» c'e' solo se non e' vuota, salvo durante
  il trascinamento;
- i tag sono alfabetici con le regole dell'italiano: maiuscole e accenti non
  li spostano in fondo, come farebbe il confronto per codice carattere;
- lo stato di comodo letto da localStorage non lancia mai: un input malformato
  da' il predefinito, un input in parte valido conserva la parte valida.

Limite dichiarato: si prova la logica, non che il .tsx la colleghi ai bottoni
e al trascinamento (nessun rendering nei test del frontend).
"""
import json

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/tag-cartelle"
RICHIEDE = [
    "raggruppa", "soloPreferiti", "riordina", "primoTagMostrato", "leggiStatoComodo",
    "scriviStatoComodo", "ordinaCartelle", "applicaOrdine", "spostaTag", "alternaChiusa",
    "nomeCartellaGiaUsato", "messaggioErroreCartella", "campiCambiati", "idRiga",
    "cartellaDaIdRiga", "tagDaIdTrascinabile", "idTagTrascinabile", "stessoOrdine",
]

PREDEFINITO = {"vista": "tutte", "chiuse": []}

PROLOGO = """
const cart = (id, nome, ordine) => ({ id, nome, ordine, created_at: "" });
const tag = (id, nome, extra = {}) => ({ id, nome, emoji: null, colore: null, created_at: "", ...extra });
const forma = (righe) => righe.map((r) => ({
  cartella: r.cartella ? r.cartella.id : null,
  tags: r.tags.map((t) => t.nome),
}));
"""


def _js(corpo, argomento=None):
    return esegui_ts(MODULO, PROLOGO + corpo, argomento=argomento, richiede=RICHIEDE)


# ── raggruppa ──────────────────────────────────────────────────────────────

def test_le_cartelle_vanno_per_ordine_poi_per_id():
    # Per id sarebbe [1, 2, 3]; per solo ordine con sort stabile [3, 2, 1].
    r = _js("""
const c = [cart(3, "C", 1), cart(1, "A", 2), cart(2, "B", 1)];
emit(forma(m.raggruppa([], c)).map((x) => x.cartella));
""")
    assert r == [2, 3, 1]


def test_una_cartella_vuota_resta_in_barra():
    r = _js("""
const c = [cart(1, "Pesce", 0), cart(2, "Carne", 1)];
const t = [tag(10, "Pollo", { cartella_id: 2 })];
emit(forma(m.raggruppa(t, c)));
""")
    assert r == [{"cartella": 1, "tags": []}, {"cartella": 2, "tags": ["Pollo"]}]


def test_un_tag_con_cartella_sconosciuta_o_assente_finisce_in_senza_cartella():
    r = _js("""
const c = [cart(1, "Pesce", 0)];
const t = [
  tag(10, "Salmone", { cartella_id: 1 }),
  tag(11, "Orfano", { cartella_id: 99 }),
  tag(12, "Vecchio"),
  tag(13, "Nullo", { cartella_id: null }),
];
emit(forma(m.raggruppa(t, c)));
""")
    assert r == [
        {"cartella": 1, "tags": ["Salmone"]},
        {"cartella": None, "tags": ["Nullo", "Orfano", "Vecchio"]},
    ]


def test_i_tag_sono_alfabetici_all_italiana():
    # Per codice carattere: maiuscole prima delle minuscole, «È» dopo la «z».
    r = _js("""
const t = [tag(1, "zucca"), tag(2, "Banane"), tag(3, "Èrba"), tag(4, "agnello"), tag(5, "Arance")];
emit(forma(m.raggruppa(t, []))[0].tags);
""")
    assert r == ["agnello", "Arance", "Banane", "Èrba", "zucca"]


def test_senza_cartella_manca_se_vuota_e_compare_durante_il_trascinamento():
    r = _js("""
const c = [cart(1, "Pesce", 0)];
const t = [tag(10, "Salmone", { cartella_id: 1 })];
emit({
  normale: forma(m.raggruppa(t, c)),
  trascinando: forma(m.raggruppa(t, c, { mostraSenzaCartella: true })),
});
""")
    assert r["normale"] == [{"cartella": 1, "tags": ["Salmone"]}]
    assert r["trascinando"] == [{"cartella": 1, "tags": ["Salmone"]}, {"cartella": None, "tags": []}]


def test_senza_cartella_sta_in_fondo_anche_con_cartelle_dopo_nell_input():
    r = _js("""
const c = [cart(5, "Ultima", 9), cart(4, "Prima", 0)];
const t = [tag(1, "Libero")];
emit(forma(m.raggruppa(t, c)).map((x) => x.cartella));
""")
    assert r == [4, 5, None]


def test_raggruppa_non_riordina_gli_array_ricevuti():
    r = _js("""
const c = [cart(2, "B", 1), cart(1, "A", 0)];
const t = [tag(2, "Zeta"), tag(1, "Alfa")];
m.raggruppa(t, c);
emit({ c: c.map((x) => x.id), t: t.map((x) => x.id) });
""")
    assert r == {"c": [2, 1], "t": [2, 1]}


# ── preferiti ──────────────────────────────────────────────────────────────

def test_solo_preferiti_tiene_le_sole_stelle_in_ordine_alfabetico():
    r = _js("""
const t = [
  tag(1, "Zucchine", { preferito: true }),
  tag(2, "Manzo", { preferito: false }),
  tag(3, "agnello", { preferito: true }),
  tag(4, "Senza campo"),
];
emit(m.soloPreferiti(t).map((x) => x.nome));
""")
    assert r == ["agnello", "Zucchine"]


# ── riordino ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "da,a,atteso",
    [
        (1, 3, [2, 3, 1, 4]),
        (4, 1, [4, 1, 2, 3]),
        (2, 2, [1, 2, 3, 4]),
        (9, 1, [1, 2, 3, 4]),
        (1, 9, [1, 2, 3, 4]),
    ],
)
def test_riordina_sposta_al_posto_del_bersaglio(da, a, atteso):
    r = _js("""
const ids = [1, 2, 3, 4];
const out = m.riordina(ids, input.da, input.a);
emit({ out, intatto: ids });
""", argomento={"da": da, "a": a})
    assert r["out"] == atteso
    assert r["intatto"] == [1, 2, 3, 4]


def test_applica_ordine_mette_l_indice_come_ordine():
    r = _js("""
const c = [cart(1, "A", 0), cart(2, "B", 1), cart(3, "C", 2)];
emit(m.ordinaCartelle(m.applicaOrdine(c, [3, 1, 2])).map((x) => x.id));
""")
    assert r == [3, 1, 2]


def test_applica_ordine_mette_in_coda_le_cartelle_fuori_elenco():
    r = _js("""
const c = [cart(1, "A", 0), cart(2, "B", 1), cart(3, "C", 2), cart(9, "Nuova", 0)];
const out = m.applicaOrdine(c, [3, 1, 2]);
emit([m.ordinaCartelle(out).map((x) => x.id), out.find((x) => x.id === 9).ordine >= 3]);
""")
    assert r == [[3, 1, 2, 9], True]


@pytest.mark.parametrize("ids, atteso", [
    ([2, 1, 3], True),
    ([1, 2, 3], False),
    ([2, 1], False),
    ([2, 1, 3, 4], False),
], ids=["uguale", "ordine-diverso", "manca-una", "una-in-piu"])
def test_stesso_ordine_confronta_l_ordine_mostrato(ids, atteso):
    r = _js(f"""
const c = [cart(1, "A", 1), cart(3, "C", 2), cart(2, "B", 0)];
emit(m.stessoOrdine(c, {json.dumps(ids)}));
""")
    assert r is atteso


def test_sposta_tag_cambia_solo_quel_tag():
    r = _js("""
const t = [tag(1, "A", { cartella_id: 5 }), tag(2, "B", { cartella_id: 5 })];
emit(m.spostaTag(t, 2, null).map((x) => x.cartella_id));
""")
    assert r == [5, None]


# ── selezione iniziale ─────────────────────────────────────────────────────

PRIMO = """
const c = [cart(1, "Pesce", 0), cart(2, "Carne", 1)];
const t = [
  tag(10, "Salmone", { cartella_id: 1 }),
  tag(11, "Astici", { cartella_id: 1 }),
  tag(20, "Pollo", { cartella_id: 2, preferito: true }),
  tag(30, "Formaggi"),
];
const righe = m.raggruppa(t, c);
const pref = m.soloPreferiti(t);
"""


def test_il_primo_tag_mostrato_e_il_primo_della_prima_cartella_non_dell_input():
    # Il primo dell'input sarebbe 10 (Salmone); il mostrato e' Astici.
    assert _js(PRIMO + 'emit(m.primoTagMostrato("tutte", righe, pref));') == 11


def test_nella_vista_preferiti_e_il_primo_preferito():
    assert _js(PRIMO + 'emit(m.primoTagMostrato("preferiti", righe, pref));') == 20


def test_preferiti_senza_stelle_ripiega_sull_ordine_delle_cartelle():
    assert _js(PRIMO + 'emit(m.primoTagMostrato("preferiti", righe, []));') == 11


def test_una_cartella_chiusa_si_salta():
    assert _js(PRIMO + 'emit(m.primoTagMostrato("tutte", righe, pref, [1]));') == 20


def test_tutte_chiuse_ripiega_sulla_prima_con_tag():
    assert _js(PRIMO + """
const soloCartelle = m.raggruppa(t.filter((x) => x.cartella_id != null), c);
emit(m.primoTagMostrato("tutte", soloCartelle, pref, [1, 2]));
""") == 11


def test_senza_tag_non_c_e_selezione():
    assert _js('emit(m.primoTagMostrato("tutte", m.raggruppa([], [cart(1, "A", 0)]), []));') is None


# ── stato di comodo (localStorage) ─────────────────────────────────────────

@pytest.mark.parametrize(
    "grezzo",
    [None, "", "{", "null", "[]", "42", '"tutte"', '{"vista":"boh"}', '{"chiuse":"1,2"}', "[1,2]"],
)
def test_stato_di_comodo_malformato_da_il_predefinito(grezzo):
    r = _js("emit(m.leggiStatoComodo(input === null ? null : input));", argomento=grezzo)
    assert r == PREDEFINITO


def test_stato_di_comodo_in_parte_valido_conserva_la_parte_valida():
    grezzo = json.dumps({"vista": "preferiti", "chiuse": [3, "4", -1, 3, 2.5, 0, 7, None]})
    assert _js("emit(m.leggiStatoComodo(input));", argomento=grezzo) == {"vista": "preferiti", "chiuse": [3, 7]}


def test_vista_invalida_non_butta_le_cartelle_chiuse():
    grezzo = json.dumps({"vista": "PREFERITI", "chiuse": [5]})
    assert _js("emit(m.leggiStatoComodo(input));", argomento=grezzo) == {"vista": "tutte", "chiuse": [5]}


def test_stato_di_comodo_fa_andata_e_ritorno():
    r = _js("""
emit(m.leggiStatoComodo(m.scriviStatoComodo({ vista: "preferiti", chiuse: [4, 2, 4] })));
""")
    assert r == {"vista": "preferiti", "chiuse": [4, 2]}


def test_alterna_chiusa_apre_e_chiude():
    assert _js("emit([m.alternaChiusa([1, 2], 2), m.alternaChiusa([1], 3)]);") == [[1], [1, 3]]


# ── nomi e messaggi ────────────────────────────────────────────────────────

def test_nome_gia_usato_ignora_maiuscole_e_spazi_e_la_cartella_stessa():
    r = _js("""
const c = [cart(1, "Pesce", 0), cart(2, "Carne", 1)];
emit([
  m.nomeCartellaGiaUsato(c, "  pesce "),
  m.nomeCartellaGiaUsato(c, "PESCE", 1),
  m.nomeCartellaGiaUsato(c, "Pesce fresco"),
]);
""")
    assert r == [True, False, False]


@pytest.mark.parametrize(
    "status,dettaglio,atteso",
    [
        (409, "duplicate key", "Esiste già una cartella con questo nome"),
        (404, "", "La cartella non esiste più: ricarica la pagina"),
        (400, "Nome troppo lungo", "Nome troppo lungo"),
        (400, "", "Il nome della cartella non può essere vuoto"),
        (502, "", "Il servizio non risponde, riprova fra poco"),
        (502, "Errore del worker", "Errore del worker"),
    ],
)
def test_messaggio_errore_cartella(status, dettaglio, atteso):
    r = _js("emit(m.messaggioErroreCartella(input.s, input.d));", argomento={"s": status, "d": dettaglio})
    assert r == atteso


# ── campi della PATCH del riquadro «Modifica tag» ──────────────────────────

CAMPI = """
const c = [cart(1, "Pesce", 0)];
"""


def test_campi_cambiati_manda_solo_quello_che_cambia():
    r = _js(CAMPI + """
const base = tag(7, "Salmone", { emoji: "🐟", cartella_id: 1 });
emit([
  m.campiCambiati(base, { nome: "Salmone", emoji: "🐟", cartella_id: 1 }, c),
  m.campiCambiati(base, { nome: "Salmone", emoji: "🐟", cartella_id: null }, c),
  m.campiCambiati(base, { nome: "Salmone norvegese", emoji: null, cartella_id: 1 }, c),
]);
""")
    assert r == [{}, {"cartella_id": None}, {"nome": "Salmone norvegese", "emoji": None}]


def test_una_cartella_sparita_lasciata_com_e_non_e_una_modifica():
    # Nella barra il tag sta in «Senza cartella»: il riquadro mostra quello, e
    # salvarlo senza toccarlo non deve mandare cartella_id.
    r = _js(CAMPI + """
const base = tag(7, "Salmone", { emoji: null, cartella_id: 99 });
emit(m.campiCambiati(base, { nome: "Salmone", emoji: null, cartella_id: null }, c));
""")
    assert r == {}


def test_emoji_assente_vale_nessuna_emoji():
    r = _js(CAMPI + """
const base = { id: 7, nome: "Salmone", colore: null, created_at: "" };
emit(m.campiCambiati(base, { nome: "Salmone", emoji: null, cartella_id: null }, c));
""")
    assert r == {}


# ── identificativi del trascinamento ───────────────────────────────────────

def test_gli_id_delle_righe_e_dei_tag_non_si_confondono():
    r = _js("""
emit({
  riga: [m.cartellaDaIdRiga(m.idRiga(12)), m.cartellaDaIdRiga(m.idRiga(null))],
  nonRighe: [m.cartellaDaIdRiga("tag:12"), m.cartellaDaIdRiga(12), m.cartellaDaIdRiga("cartella:abc"),
             m.cartellaDaIdRiga("cartella:0"), m.cartellaDaIdRiga(null)],
  tag: [m.tagDaIdTrascinabile(m.idTagTrascinabile(5)), m.tagDaIdTrascinabile("cartella:5")],
});
""")
    # undefined non passa da JSON: in un array diventa null.
    assert r["riga"] == [12, None]
    assert r["nonRighe"] == [None, None, None, None, None]
    assert r["tag"] == [5, None]


def test_senza_cartella_e_null_non_undefined():
    # null = bersaglio «Senza cartella», undefined = non e' una riga: il .tsx
    # sposta il tag solo nel primo caso.
    r = _js("""
emit([m.cartellaDaIdRiga(m.idRiga(null)) === null, m.cartellaDaIdRiga("tag:1") === undefined]);
""")
    assert r == [True, True]
