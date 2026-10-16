"""Tag ordinabili a mano dentro la cartella (lib/tag-cartelle.ts, 16/10/2026).

Il pannello dei tag, in «Analisi e Tag» e nei «Tag di catena», lascia mettere
i tag nell'ordine che si vuole trascinandoli. La logica che il .tsx usa:
- `raggruppa` ordina i tag di una cartella per (ordine, nome): con tutti a 0
  (gruppo mai riordinato) resta alfabetico, come prima della migration;
- `gruppoDopoIlRilascio` calcola il gruppo d'arrivo intero, dall'alto, cioe' il
  corpo di PUT .../ordine;
- `applicaOrdineTag` e `ordineTagApplicato` fanno l'aggiornamento ottimista e
  dicono se si puo' tornare indietro.

Casi scelti dove la versione sbagliata da' un altro risultato: ordine che vince
sul nome (e il nome che decide a pari ordine), lasciato su un tag piu' in alto
e piu' in basso nello stesso gruppo, lasciato su un tag di un altro gruppo (prende
il suo posto, non va in fondo), lasciato sulla cartella (in fondo), «Senza
cartella» vuota. Limite dichiarato: si prova la logica, non il trascinamento
nel .tsx.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/tag-cartelle"
RICHIEDE = ["raggruppa", "soloPreferiti", "gruppoDopoIlRilascio", "applicaOrdineTag", "ordineTagApplicato"]

PROLOGO = """
const cart = (id, nome, ordine) => ({ id, nome, ordine, created_at: "" });
const tag = (id, nome, extra = {}) => ({ id, nome, emoji: null, ...extra });
const nomi = (righe) => righe.map((r) => r.tags.map((t) => t.nome));
// Cartella 1: tre tag mai riordinati (alfabetici). Cartella 2: MANZO. Senza: AGLIO.
const C = [cart(1, "Pesce", 0), cart(2, "Carne", 1)];
const T = [
  tag(9, "SALMONE", { cartella_id: 1 }), tag(10, "ORATA", { cartella_id: 1 }), tag(13, "BRANZINO", { cartella_id: 1 }),
  tag(11, "MANZO", { cartella_id: 2 }), tag(12, "AGLIO"),
];
const R = m.raggruppa(T, C, { mostraSenzaCartella: true });
"""


def _js(corpo):
    return esegui_ts(MODULO, PROLOGO + corpo, richiede=RICHIEDE)


# ── L'ordine nella lista ───────────────────────────────────────────────────
def test_gruppo_mai_riordinato_resta_alfabetico():
    assert _js("emit(nomi(R));") == [["BRANZINO", "ORATA", "SALMONE"], ["MANZO"], ["AGLIO"]]


def test_la_posizione_vince_sul_nome_e_a_pari_posizione_decide_il_nome():
    out = _js("""
const t = [tag(9, "SALMONE", { cartella_id: 1, ordine: 0 }), tag(10, "ORATA", { cartella_id: 1, ordine: 1 }),
           tag(13, "BRANZINO", { cartella_id: 1, ordine: 1 }), tag(14, "ALICI", { cartella_id: 1, ordine: 2 })];
emit(nomi(m.raggruppa(t, C))[0]);
""")
    assert out == ["SALMONE", "BRANZINO", "ORATA", "ALICI"]


def test_senza_cartella_segue_la_posizione():
    out = _js("""
const t = [tag(12, "AGLIO", { ordine: 1 }), tag(15, "ZUCCHERO", { ordine: 0 })];
emit(nomi(m.raggruppa(t, []))[0]);
""")
    assert out == ["ZUCCHERO", "AGLIO"]


def test_i_preferiti_restano_alfabetici():
    out = _js("""
const t = [tag(9, "SALMONE", { preferito: true, ordine: 0 }), tag(13, "BRANZINO", { preferito: true, ordine: 5 })];
emit(m.soloPreferiti(t).map((x) => x.nome));
""")
    assert out == ["BRANZINO", "SALMONE"]


# ── Il gruppo dopo il rilascio ─────────────────────────────────────────────
# Cartella 1 a video: BRANZINO (13), ORATA (10), SALMONE (9).
def test_nello_stesso_gruppo_su_un_tag_piu_in_alto_ne_prende_il_posto():
    assert _js("emit(m.gruppoDopoIlRilascio(R, 9, 1, 13));") == [9, 13, 10]


def test_nello_stesso_gruppo_su_un_tag_piu_in_basso_ne_prende_il_posto():
    assert _js("emit(m.gruppoDopoIlRilascio(R, 13, 1, 9));") == [10, 9, 13]


def test_nello_stesso_gruppo_sulla_cartella_o_su_se_stesso_non_cambia_niente():
    assert _js("emit([m.gruppoDopoIlRilascio(R, 10, 1, null), m.gruppoDopoIlRilascio(R, 10, 1, 10)]);") == [None, None]


def test_da_un_altro_gruppo_su_un_tag_ne_prende_il_posto():
    assert _js("emit(m.gruppoDopoIlRilascio(R, 11, 1, 10));") == [13, 11, 10, 9]


def test_da_un_altro_gruppo_sulla_cartella_va_in_fondo():
    assert _js("emit(m.gruppoDopoIlRilascio(R, 11, 1, null));") == [13, 10, 9, 11]


def test_in_senza_cartella_vuota_resta_solo_lui():
    out = _js("""
const r = m.raggruppa(T.filter((t) => t.id !== 12), C, { mostraSenzaCartella: true });
emit(m.gruppoDopoIlRilascio(r, 9, null, null));
""")
    assert out == [9]


def test_una_cartella_che_non_e_in_lista_non_produce_niente():
    assert _js("emit(m.gruppoDopoIlRilascio(R, 9, 424242, null));") is None


# ── Aggiornamento ottimista e ritorno indietro ─────────────────────────────
def test_applica_ordine_mette_cartella_e_posizione_solo_ai_tag_del_gruppo():
    out = _js("""
const t = m.applicaOrdineTag(T, 1, [13, 11, 10, 9]);
emit(t.map((x) => [x.id, x.cartella_id ?? null, x.ordine ?? null]));
""")
    assert out == [[9, 1, 3], [10, 1, 2], [13, 1, 0], [11, 1, 1], [12, None, None]]


def test_ordine_applicato_vero_finche_nessuno_lo_cambia():
    out = _js("""
const dopo = m.applicaOrdineTag(T, 1, [13, 11, 10, 9]);
// 13 resta in testa (ordine 0) ma in un'altra cartella: cambia SOLO la cartella.
const cambiato = m.applicaOrdineTag(dopo, 2, [13]);
emit([m.ordineTagApplicato(dopo, 1, [13, 11, 10, 9]), m.ordineTagApplicato(cambiato, 1, [13, 11, 10, 9]),
      m.ordineTagApplicato(T, 1, [13, 10, 9])]);
""")
    assert out == [True, False, False]
