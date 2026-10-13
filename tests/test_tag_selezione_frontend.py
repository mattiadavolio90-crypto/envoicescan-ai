"""La lista unica a spunte del riquadro «Modifica tag» (lib/tag-selezione.ts).

Il riquadro (12/10/2026) sostituisce il wizard «Nuovo tag» a due passi, il
dialog «Aggiungi prodotti» e la sezione «Prodotti associati»: un prodotto
spuntato e' dentro il tag, e Salva applica aggiunte e rimozioni insieme.

Le regole che un'implementazione plausibile sbaglierebbe, e che qui si provano
con casi in cui la versione sbagliata da' un risultato diverso:
- un prodotto del tag che non compare piu' fra le descrizioni (fatture
  eliminate, descrizione cambiata) resta in lista, altrimenti non si toglie;
- «Nel tag» guarda il tag ALL'APERTURA, non le spunte correnti: togliere una
  spunta non fa sparire la riga sotto il dito;
- «Seleziona tutti» vale su tutte le righe che passano filtro e ricerca, anche
  oltre le 80 mostrate; «Deseleziona tutti» non tocca le spunte fuori filtro.

Limite dichiarato: si prova la logica, non che il .tsx la colleghi ai bottoni
giusti (nessun rendering nei test del frontend).
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/tag-selezione"
RICHIEDE = [
    "righeSelettore", "selezionaTutti", "deselezionaTutti", "inverti",
    "differenze", "corpoModifiche", "partiContatore", "etichettaProdotti",
    "testoEsito", "chiaviDelTag", "blocchiModifiche",
]

# Il worker rifiuta oltre 2000 elementi per lista (MAX_ELEMENTI_PER_LISTA in
# services/tag_organizza_service.py): ogni blocco deve restare sotto.
LIMITE_WORKER = 2000

# Ancorato qui, non riletto dal modulo: un atteso che legge la stessa costante
# dell'ottenuto si muove con lei e non prova nulla.
TETTO = 80

PROLOGO = """
const desc = (d, k, o) => ({ descrizione: d, descrizione_key: k, occorrenze: o,
  num_fornitori: 1, fornitori: [], ultima_data: null, unita_misura: [] });
const prod = (d, k) => ({ id: 1, tag_id: 1, descrizione: d, descrizione_key: k,
  fattore_kg: null, created_at: "" });
const chiavi = (righe) => righe.map((r) => r.descrizione_key);
"""


def _js(corpo, argomento=None):
    return esegui_ts(MODULO, PROLOGO + corpo, argomento=argomento, richiede=RICHIEDE)


def test_il_tetto_e_80():
    assert _js("emit(m.MAX_DESC_VISIBILI);") == TETTO


def test_un_prodotto_del_tag_sparito_dalle_fatture_resta_in_lista_in_coda():
    r = _js("""
const d = [desc("SALMONE FRESCO", "salmone fresco", 11), desc("TONNO", "tonno", 4)];
const p = [prod("SALMONE FRESCO", "salmone fresco"), prod("SALMONE VECCHIO", "salmone vecchio")];
const tutti = m.righeSelettore(d, p, "", "tutti");
const nel = m.righeSelettore(d, p, "", "nel_tag");
emit({ tutti: tutti.corrispondenti, nel: chiavi(nel.corrispondenti) });
""")
    assert [x["descrizione_key"] for x in r["tutti"]] == ["salmone fresco", "tonno", "salmone vecchio"]
    orfano = r["tutti"][-1]
    assert orfano["occorrenze"] is None, "l'orfano non ha occorrenze: non e' fra le descrizioni"
    assert orfano["descrizione"] == "SALMONE VECCHIO"
    # Il prodotto presente in entrambe le liste compare una volta sola.
    assert r["nel"] == ["salmone fresco", "salmone vecchio"]


def test_nel_tag_guarda_il_tag_all_apertura_non_le_spunte():
    """Spunte tolte ad A, aggiunta B: «Nel tag» mostra ancora A e non B."""
    r = _js("""
const d = [desc("A", "a", 9), desc("B", "b", 8), desc("C", "c", 7)];
const p = [prod("A", "a"), prod("C", "c")];
const sel = new Set(["b", "c"]);
const e = m.righeSelettore(d, p, "", "nel_tag", sel);
emit({ righe: chiavi(e.corrispondenti), spuntate: e.spuntateCorrispondenti });
""")
    assert r["righe"] == ["a", "c"]
    assert r["spuntate"] == 1, "fra le righe mostrate solo C e' spuntata"


def test_la_ricerca_ignora_maiuscole_e_spazi_e_vale_anche_per_gli_orfani():
    r = _js("""
const d = [desc("SALMONE 5-6 KG", "s1", 11), desc("TONNO PINNA GIALLA", "t1", 3)];
const p = [prod("Salmone affumicato", "s9")];
emit(chiavi(m.righeSelettore(d, p, "  salmo ", "tutti").corrispondenti));
""")
    assert r == ["s1", "s9"]


def test_oltre_il_tetto_seleziona_tutti_prende_TUTTE_le_corrispondenti():
    """200 salmoni e 50 tonni, ricerca «salmo»: se ne vedono 80, se ne
    spuntano 200 — e nessun tonno."""
    r = _js("""
const d = [];
for (let i = 0; i < 200; i++) d.push(desc("SALMONE " + i, "s" + i, 300 - i));
for (let i = 0; i < 50; i++) d.push(desc("TONNO " + i, "t" + i, 1));
const e = m.righeSelettore(d, [], "SALMO", "tutti");
const sel = m.selezionaTutti(new Set(["t0"]), chiavi(e.corrispondenti));
const dopo = m.righeSelettore(d, [], "SALMO", "tutti", sel);
emit({
  visibili: e.visibili.length, totale: e.totale, nascoste: e.nascoste,
  spuntate: sel.size, tonni: [...sel].filter((k) => k.startsWith("t")),
  spuntateDopo: dopo.spuntateCorrispondenti, totaleDopo: dopo.totale,
});
""")
    assert r["visibili"] == TETTO
    assert r["totale"] == 200
    assert r["nascoste"] == 120
    assert r["spuntate"] == 201, "200 salmoni + il tonno gia' spuntato prima"
    assert r["tonni"] == ["t0"], "i tonni fuori ricerca non si spuntano"
    # E' la condizione che spegne «Seleziona tutti»: deve contare solo le
    # corrispondenti, non tutto il Set (201).
    assert r["spuntateDopo"] == r["totaleDopo"] == 200


def test_deseleziona_tutti_lascia_le_spunte_fuori_filtro():
    r = _js("""
const d = [desc("SALMONE A", "s1", 5), desc("SALMONE B", "s2", 4), desc("TONNO", "t1", 3)];
const e = m.righeSelettore(d, [], "salmone", "tutti");
emit([...m.deselezionaTutti(new Set(["s1", "s2", "t1"]), chiavi(e.corrispondenti))]);
""")
    assert r == ["t1"]


def test_le_funzioni_di_selezione_non_mutano_il_set_ricevuto():
    """React confronta per riferimento: un Set mutato in place non ridisegna."""
    r = _js("""
const orig = new Set(["a"]);
const s1 = m.selezionaTutti(orig, ["b"]);
const s2 = m.deselezionaTutti(orig, ["a"]);
const s3 = m.inverti(orig, "a");
emit({ orig: [...orig], s1: [...s1].sort(), s2: [...s2], s3: [...s3], nuovi: s1 !== orig && s2 !== orig && s3 !== orig });
""")
    assert r == {"orig": ["a"], "s1": ["a", "b"], "s2": [], "s3": [], "nuovi": True}


def test_differenze_nei_due_sensi():
    r = _js("""
const d = m.differenze(new Set(["a", "b", "c"]), new Set(["b", "c", "d", "e"]));
emit({ aggiungi: d.aggiungi.sort(), togli: d.togli.sort() });
""")
    assert r == {"aggiungi": ["d", "e"], "togli": ["a"]}


def test_togliere_e_rimettere_la_spunta_non_e_una_modifica():
    r = _js("""
const ini = new Set(["a", "b"]);
const s = m.inverti(m.inverti(ini, "a"), "a");
emit(m.differenze(ini, s));
""")
    assert r == {"aggiungi": [], "togli": []}


def test_il_corpo_della_patch_porta_la_descrizione_leggibile():
    r = _js("""
const righe = m.righeSelettore([desc("SALMONE FRESCO", "salmone fresco", 3)], [prod("X", "x")], "", "tutti").corrispondenti;
emit(m.corpoModifiche({ aggiungi: ["salmone fresco"], togli: ["x"] }, righe));
""")
    assert r == {
        "aggiungi": [{"descrizione": "SALMONE FRESCO", "descrizione_key": "salmone fresco", "fattore_kg": None}],
        "togli": ["x"],
    }


def test_contatore_del_piede():
    r = _js("emit([m.partiContatore(2, 1), m.partiContatore(0, 0), m.partiContatore(1, 0), m.partiContatore(0, 3)]);")
    assert r[0] == {"aggiungi": "+2 da aggiungere", "togli": "−1 da togliere"}
    assert r[1] == {"aggiungi": None, "togli": None}
    assert r[2] == {"aggiungi": "+1 da aggiungere", "togli": None}
    assert r[3] == {"aggiungi": None, "togli": "−3 da togliere"}


def test_singolari_e_plurali():
    r = _js("""
emit({
  e: [m.testoEsito(1, 0), m.testoEsito(2, 0), m.testoEsito(0, 1), m.testoEsito(0, 4),
      m.testoEsito(3, 1), m.testoEsito(1, 2), m.testoEsito(0, 0)],
  l: [m.etichettaProdotti(0), m.etichettaProdotti(1), m.etichettaProdotti(43)],
});
""")
    assert r["e"] == [
        "1 prodotto aggiunto", "2 prodotti aggiunti", "1 prodotto tolto",
        "4 prodotti tolti", "3 prodotti aggiunti, 1 tolto", "1 prodotto aggiunto, 2 tolti", "",
    ]
    assert r["l"] == ["Nessun prodotto", "1 prodotto", "43 prodotti"]


def test_seleziona_tutti_oltre_il_limite_del_worker_parte_a_blocchi():
    """Una sede reale ha 2.277 descrizioni: «Seleziona tutti» su un tag nuovo
    produce una PATCH che il worker rifiuterebbe in un colpo solo."""
    r = _js("""
const corpo = {
  aggiungi: Array.from({ length: 2277 }, (_, i) => ({ descrizione: "P" + i, descrizione_key: "P" + i, fattore_kg: null })),
  togli: Array.from({ length: 5 }, (_, i) => "T" + i),
};
const b = m.blocchiModifiche(corpo);
emit({
  n: b.length,
  maxAgg: Math.max(...b.map((x) => x.aggiungi.length)),
  maxTog: Math.max(...b.map((x) => x.togli.length)),
  agg: b.flatMap((x) => x.aggiungi.map((v) => v.descrizione_key)),
  tog: b.flatMap((x) => x.togli),
});
""")
    assert r["n"] >= 2
    assert r["maxAgg"] <= LIMITE_WORKER and r["maxTog"] <= LIMITE_WORKER
    assert r["agg"] == [f"P{i}" for i in range(2277)], "nessun elemento perso o ripetuto, ordine conservato"
    assert r["tog"] == [f"T{i}" for i in range(5)]


def test_un_corpo_vuoto_non_produce_nessuna_patch():
    assert _js('emit(m.blocchiModifiche({ aggiungi: [], togli: [] }).length);') == 0


def test_un_corpo_piccolo_e_una_patch_sola():
    r = _js('emit(m.blocchiModifiche({ aggiungi: [], togli: ["A", "B"] }));')
    assert r == [{"aggiungi": [], "togli": ["A", "B"]}]


def test_anche_le_rimozioni_si_distribuiscono_su_tutti_i_blocchi():
    r = _js("""
const corpo = {
  aggiungi: ["A1", "A2", "A3"].map((k) => ({ descrizione: k, descrizione_key: k, fattore_kg: null })),
  togli: ["T1", "T2", "T3", "T4", "T5"],
};
emit(m.blocchiModifiche(corpo, 2).map((b) => ({ a: b.aggiungi.map((x) => x.descrizione_key), t: b.togli })));
""")
    assert r == [
        {"a": ["A1", "A2"], "t": ["T1", "T2"]},
        {"a": ["A3"], "t": ["T3", "T4"]},
        {"a": [], "t": ["T5"]},
    ]
