"""Un mese senza costi caricati non e' un mese andato bene.

Misurato il 23/09/2026 su SUSHILAND MARIANO (anno in corso, tema chiaro e scuro):
gennaio e febbraio avevano «Costi F&B —» perche' le fatture non erano state
caricate, e il MOL usciva **384.120 EUR in verde all'86%** e **321.619 EUR in
verde all'84%** — i due mesi piu' verdi dell'anno erano i due senza costi. Nella
stessa pagina, 400px piu' sotto, «Analisi visiva» diceva gia' «Nessun giudizio:
4 mesi su 9 mesi del periodo non ha costi registrati»: il gate lato worker esiste
dal 16/09 (`_mesi_senza_costi`, services/routers/margini.py), ma spegneva solo il
commento, non il colore della tabella.

Il numero NON cambia (decisione di Mattia: il calcolo non si tocca). Cambia solo
il giudizio: il verde/rosso di `valueColor: "sign"` diventa neutro.

**Perche' i test chiamano anche `valueColorCls` e non solo `meseSenzaCosti`:**
provare il predicato in isolamento non prova che la tabella lo usi. E' l'errore
gia' fatto due volte in questa fase (blocchi B e C): i test erano verdi e il
mutante al punto di chiamata sopravviveva. Qui la classe CSS e' il
comportamento osservabile, quindi si asserisce quella — su tutti e tre i punti
in cui la tabella la calcola (cella desktop, colonna Totale, card mobile).
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

_MODULO = "lib/margini-aggregati"
_TABELLA = Path("apps/web/src/app/(app)/margini/calcolo-tab.tsx")


def _pivot(**extra):
    """Un `MesePivot` completo: solo i campi che la funzione legge davvero."""
    base = {
        "anno": 2026, "mese": 1, "label": "Gen 2026",
        "fatturato_iva10": 0.0, "fatturato_iva22": 0.0, "altri_ricavi_noiva": 0.0,
        "fatturato_netto": 0.0,
        "costi_fb_auto": 0.0, "altri_costi_fb": 0.0, "costi_fb_totali": 0.0,
        "primo_margine": 0.0,
        "costi_spese_auto": 0.0, "altri_costi_spese": 0.0, "costi_spese_totali": 0.0,
        "costo_dipendenti": 0.0, "costo_personale_extra": 0.0, "costi_personale": 0.0,
        "mol": 0.0, "quote_riparto_fb": 0.0, "quote_riparto_spese": 0.0,
    }
    base.update(extra)
    return base


def _senza_costi(mese):
    return esegui_ts(
        _MODULO,
        "emit(m.meseSenzaCosti(...input));",
        argomento=[mese],
        richiede=["meseSenzaCosti"],
    )


# ───────────────────────── il predicato ─────────────────────────────────────

def test_mese_con_ricavi_e_zero_costi_e_incompleto():
    """Il caso reale: gennaio 2026, 444.234 EUR di ricavi e nessuna fattura."""
    assert _senza_costi(_pivot(fatturato_netto=444234.0, mol=384120.0)) is True


def test_mese_con_costi_fb_e_completo():
    assert _senza_costi(
        _pivot(fatturato_netto=418854.0, costi_fb_totali=29953.0)
    ) is False


def test_le_sole_spese_generali_non_bastano_senza_food_cost():
    """La condizione guarda i soli costi F&B: le spese non completano il mese.

    Fino al 23/09/2026 era un AND («F&B E spese entrambi a zero»), e un costo
    qualsiasi rendeva il mese giudicabile: 114 EUR di sole spese generali su
    444.000 EUR di ricavi (SUSHILAND gennaio 2026, tutte e tre le sedi) davano
    un MOL verde all'86% con food cost 0%. Decisione di Mattia: senza fatture
    della merce il mese non si giudica.

    E' la stessa soglia del worker (`_mesi_senza_costi`): la coerenza fra le due
    definizioni e' voluta — divergendo, la tabella colorerebbe di verde proprio
    i mesi per cui «Analisi visiva» dichiara di non avere un giudizio.
    """
    assert _senza_costi(
        _pivot(fatturato_netto=444234.0, costi_spese_totali=114.0)
    ) is True


def test_il_caso_casati_settembre():
    """Il caso che ha aperto la verifica: 101 EUR di utenze, zero merce.

    Misurato a DB il 23/09/2026: CASATI 14, Set 2026, 5.696 EUR di ricavi, 12
    righe fattura tutte di spese, nessuna di merce. La tabella mostrava
    «Margine F&B 5.696 EUR 100%» e «Guadagno finale (MOL) 5.595 EUR 98%» in
    verde su un mese con «Costi F&B (Fatture) —».
    """
    assert _senza_costi(
        _pivot(fatturato_netto=5696.0, costi_spese_totali=101.0, mol=5595.0)
    ) is True


def test_una_quota_di_riparto_fb_completa_il_mese():
    """La merce comprata dal gruppo e ripartita sulla sede E' merce.

    `costi_fb_totali` include gia' le quote di riparto F&B: una sede di catena
    che non compra in proprio non deve finire fra i mesi senza giudizio.
    """
    assert _senza_costi(
        _pivot(fatturato_netto=444234.0, costi_fb_totali=114.0)
    ) is False


def test_mese_senza_ricavi_non_e_incompleto():
    """Un mese vuoto non ha nulla da giudicare: non e' "dati mancanti", e' zero.

    Senza questa guardia ogni mese futuro dell'anno in corso (ottobre-dicembre,
    che la tabella mostra vuoti) risulterebbe "incompleto" e spegnerebbe colori
    che non ci sono comunque — rumore, non informazione.
    """
    assert _senza_costi(_pivot()) is False


def test_costi_negativi_contano_come_assenti():
    """`<= 0`, non `== 0`: una nota di credito puo' portare il totale sotto zero."""
    assert _senza_costi(
        _pivot(fatturato_netto=100000.0, costi_fb_totali=-500.0)
    ) is True


# ────────────── il colore: e' questo che il cliente vede ────────────────────

def _colore(vc, raw, incompleto):
    """`valueColorCls` non e' esportata: si rende eseguibile una copia estratta.

    La copia e' presa DAL SORGENTE a ogni giro (vedi `_estrai_value_color_cls`),
    non ricopiata qui: una copia a mano si dimenticherebbe di seguire il file e
    resterebbe verde su un difetto reale — e' la trappola «il test ricalcola la
    formula» gia' pagata in questo progetto.
    """
    return esegui_ts(
        _MODULO,
        _estrai_value_color_cls() + "\nemit(valueColorCls(...input));",
        argomento=[vc, raw, incompleto],
        richiede=["meseSenzaCosti"],
    )


def _estrai_value_color_cls() -> str:
    """Ritaglia `valueColorCls` da calcolo-tab.tsx e la rende eseguibile da node."""
    src = _TABELLA.read_text(encoding="utf-8")
    inizio = src.index("function valueColorCls(")
    # La funzione finisce alla prima riga che chiude a colonna zero.
    fine = src.index("\n}\n", inizio) + len("\n}\n")
    corpo = src[inizio:fine]
    # Via le annotazioni di tipo: node esegue JS, non TypeScript.
    corpo = corpo.replace("vc: ValueColor", "vc").replace("raw: number", "raw")
    corpo = corpo.replace("incompleto = false", "incompleto = false").replace("): string {", ") {")
    return corpo


@pytest.mark.parametrize("raw", [384120.0, -26988.0])
def test_mese_incompleto_non_riceve_giudizio_di_segno(raw):
    """Ne' verde ne' rosso: un MOL senza costi non e' buono e non e' cattivo."""
    assert _colore("sign", raw, True) == "text-muted-foreground"


def test_mese_completo_positivo_resta_verde():
    assert _colore("sign", 122913.0, False) == "text-positivo"


def test_mese_completo_negativo_resta_rosso():
    assert _colore("sign", -26988.0, False) == "text-negativo"


def test_le_righe_totale_non_cambiano_colore():
    """`valueColor: "totale"` e' il blu del brand: dato calcolato, nessun giudizio.

    Spegnerlo sui mesi incompleti sarebbe un danno: «= Fatturato Netto» resta un
    fatturato vero anche quando le fatture dei costi mancano.
    """
    assert _colore("totale", 444234.0, True) == "text-primary-text"


def test_le_righe_bianche_non_cambiano_colore():
    assert _colore("white", 344430.0, True) == ""


# ─────────── i punti di chiamata: il presidio che manca di piu' ─────────────

def _terzo_argomento(chiamata: str) -> str:
    """Il 3o argomento di `valueColorCls(a, b, c)`, rispettando le parentesi annidate.

    `split(",")` non basta: `meseSenzaCosti(mese)` non contiene virgole ma un
    domani `f(a, b)` si', e la chiamata verrebbe troncata a meta'.
    """
    livello, pezzi, corrente = 0, [], ""
    for ch in chiamata:
        if ch in "([{":
            livello += 1
        elif ch in ")]}":
            livello -= 1
        if ch == "," and livello == 0:
            pezzi.append(corrente)
            corrente = ""
            continue
        corrente += ch
    pezzi.append(corrente)
    return pezzi[2].strip() if len(pezzi) >= 3 else ""


def _valuta_flag(espressione: str, senza_costi: bool) -> bool:
    """ESEGUE l'espressione del 3o argomento con node, non la legge.

    `meseSenzaCosti(mese)` viene valutata davvero contro il modulo vero; il mese
    passato e' incompleto o completo a seconda di `senza_costi`. Cosi' `false`,
    `!meseSenzaCosti(mese)` e `false && meseSenzaCosti(mese)` danno un risultato
    DIVERSO dall'espressione giusta, mentre contando le virgole erano identici.
    """
    # Serve fatturato > 0 in entrambi i casi: `meseSenzaCosti` lo pretende (un
    # mese senza ricavi non e' «incompleto», e' semplicemente vuoto).
    mese = (
        _pivot(fatturato_netto=384120.0, costi_fb_totali=0.0, costi_spese_totali=0.0)
        if senza_costi
        else _pivot(fatturato_netto=384120.0, costi_fb_totali=114000.0)
    )
    return esegui_ts(
        _MODULO,
        "const { meseSenzaCosti } = m;\n"
        f"const mese = input;\nemit(Boolean({espressione}));",
        argomento=mese,
        richiede=["meseSenzaCosti"],
    )


def _prop_incompleto(src: str, componente: str) -> str:
    """Il valore passato come prop `incompleto` a `<Componente ...>`.

    Serve a distinguere i consumatori l'uno dall'altro: due prop scritte identiche
    si mascherano a vicenda in una ricerca per sottostringa.
    """
    m = re.search(rf"<{componente}\b[^>]*?\bincompleto=\{{([^}}]*)\}}", src, re.S)
    return m.group(1).strip() if m else ""


def test_tutti_e_tre_i_punti_passano_il_flag():
    """Tre superfici calcolano il colore: cella desktop, colonna Totale, card mobile.

    Provare la funzione senza i suoi chiamanti e' esattamente l'errore che in
    questa fase ha lasciato passare 6 mutanti su 8 (blocco C): il colore giusto
    calcolato da nessuno resta un colore sbagliato a schermo.

    La PRIMA stesura di questo presidio contava le virgole del 3o argomento. Era
    finta: `false` ha le stesse virgole di `meseSenzaCosti(mese)`, e quattro
    mutanti che rimettevano il difetto (fra cui uno che colorava di verde
    ESATTAMENTE e SOLO i mesi senza costi) passavano con 53 test verdi. Trovata
    dalla terza review del 23/09 — quinto presidio della stessa famiglia in una
    giornata. Ora l'espressione si ESEGUE: deve dire true su un mese senza costi
    e false su uno completo, che e' il comportamento, non la sua grafia.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    chiamate = re.findall(r"= valueColorCls\((.+?)\);", src)
    assert len(chiamate) == 3, f"attese 3 chiamate, trovate {len(chiamate)}: {chiamate}"

    flag_calcolati, flag_da_prop = [], []
    for c in chiamate:
        flag = _terzo_argomento(c)
        assert flag, f"chiamata senza il flag di completezza: valueColorCls({c})"
        (flag_da_prop if flag == "incompleto" else flag_calcolati).append(flag)

    # Chi calcola il flag sul posto (la cella desktop, che ha il mese sotto mano):
    # l'espressione si ESEGUE contro il modulo vero.
    assert flag_calcolati, "nessuna chiamata calcola il flag dal mese"
    for flag in flag_calcolati:
        assert _valuta_flag(flag, senza_costi=True) is True, (
            f"su un mese SENZA costi il flag deve essere true, `{flag}` non lo e'"
        )
        assert _valuta_flag(flag, senza_costi=False) is False, (
            f"su un mese completo il flag deve essere false, `{flag}` non lo e'"
        )

    # Chi lo riceve dall'alto (colonna Totale, card mobile): il valore lo decide
    # il chiamante, quindi si verifica che la prop esista e sia alimentata dal
    # calcolo sui mesi visibili — un letterale `false` qui rimetterebbe il difetto.
    assert len(flag_da_prop) == 2, (
        f"attese 2 chiamate che ricevono il flag come prop, trovate {len(flag_da_prop)}"
    )

    # Ogni consumatore si verifica PER NOME, uno alla volta. Cercare la sola
    # stringa `incompleto={periodoIncompleto}` non bastava: le occorrenze sono
    # due e si coprivano a vicenda — spegnendone una il test restava verde
    # (mutanti M6 e B1c del 23/09, sopravvissuti al primo giro di questo fix).
    for componente in ("TotalCell", "AnalisiVisiva"):
        assert _prop_incompleto(src, componente) == "periodoIncompleto", (
            f"<{componente}> non riceve il flag calcolato sui mesi visibili: "
            f"riceve `{_prop_incompleto(src, componente)}`"
        )


def test_il_totale_di_periodo_guarda_i_mesi_non_l_aggregato():
    """Sull'aggregato i costi di un mese solo bastano a farlo sembrare completo.

    E' la stessa trappola che il worker documenta a margini.py:895 («basta che
    qualche mese i costi ce li abbia perche' la condizione sia falsa»). Il
    periodo e' incompleto se lo e' anche UN solo mese, quindi la colonna Totale
    deve ricevere il flag dall'elenco dei mesi — non ricavarlo da `totali`.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    assert "mesiVisibili.some(meseSenzaCosti)" in src, (
        "la colonna Totale non deriva piu' la completezza dai singoli mesi"
    )
    assert "meseSenzaCosti(totali)" not in src, (
        "la completezza del periodo e' calcolata sull'aggregato: sempre falsa"
    )


def test_un_solo_mese_scoperto_rende_incompleto_il_periodo():
    """La regola del periodo, eseguita: 8 mesi pieni + 1 vuoto = incompleto."""
    mesi = [
        _pivot(mese=i, fatturato_netto=400000.0, costi_fb_totali=100000.0)
        for i in range(1, 9)
    ] + [_pivot(mese=9, fatturato_netto=288641.0)]
    esito = esegui_ts(
        _MODULO,
        "emit(input[0].some(m.meseSenzaCosti));",
        argomento=[mesi],
        richiede=["meseSenzaCosti"],
    )
    assert esito is True


# ───────── apertura sul mese corrente (23/09, richiesta di Mattia) ──────────

def _scroll(offset, larghezza=140, totale=160, visibile=1000, margine=None):
    opts = {
        "offsetCella": offset, "larghezzaCella": larghezza,
        "larghezzaTotale": totale, "larghezzaVisibile": visibile,
    }
    if margine is not None:
        opts["margine"] = margine
    return esegui_ts(
        _MODULO,
        "emit(m.scrollPerMeseCorrente(...input));",
        argomento=[opts],
        richiede=["scrollPerMeseCorrente"],
    )


def test_scrolla_fino_a_scoprire_il_mese_corrente():
    """Nove mesi da 140px non ci stanno: entrando si vedeva Gen-Lug.

    Settembre e' la nona colonna (offset 8*140 = 1120): con 1000px visibili il
    conto deve portare lo scroller abbastanza a destra da mostrarla.
    """
    assert _scroll(offset=1120) == 1120 + 140 + 160 + 24 - 1000


def test_lascia_spazio_alla_colonna_totale():
    """La colonna Totale e' `sticky right`: senza sottrarla copre il mese corrente.

    E' il pezzo che si sbaglia in silenzio — lo scroll "funziona", ma la colonna
    che doveva emergere finisce sotto quella dei totali e sembra non essere
    successo niente. La differenza fra i due conti e' esattamente la sua
    larghezza.
    """
    con = _scroll(offset=1120, totale=160)
    senza = _scroll(offset=1120, totale=0)
    assert con - senza == 160


def test_tabella_che_ci_sta_tutta_non_scrolla():
    """Poche colonne su uno schermo largo: nessuno scroll, non uno negativo."""
    assert _scroll(offset=140, visibile=2400) == 0


def test_non_torna_mai_un_valore_negativo():
    """`scrollLeft` negativo non esiste: il browser lo azzererebbe in silenzio."""
    assert _scroll(offset=0, visibile=5000) == 0


def _estrai_effetto_scroll() -> str:
    """Ritaglia il corpo dell'useEffect dello scroll e lo rende eseguibile da node.

    I ref diventano oggetti semplici forniti dal test (`scrollerRef`,
    `meseCorrenteRef`, `giaScrollato`): il corpo dell'effetto non sa che non e'
    React, perche' usa solo `.current`.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    inizio = src.index("  useEffect(() => {\n    if (giaScrollato.current) return;")
    fine = src.index("  }, [mesiVisibili]);", inizio)
    corpo = src[inizio:fine]
    corpo = corpo[corpo.index("{") + 1:]
    return "function effetto() {" + corpo + "}"


def _gira_effetto(*, ha_cella=True, gia_scrollato=False, giri=1,
                  offset=1120, larghezza=140, visibile=1000):
    """Esegue DAVVERO l'effetto su un DOM finto e torna lo scroll finale.

    Torna anche quante volte lo scroll e' stato scritto: la guardia «una volta
    sola» si misura contando le scritture su piu' giri, non cercando il nome
    `giaScrollato` nel sorgente.
    """
    setup = f"""
const scritture = [];
const scroller = {{ clientWidth: {visibile}, _s: 0,
  get scrollLeft() {{ return this._s; }},
  set scrollLeft(v) {{ this._s = v; scritture.push(v); }} }};
const cella = {'{ offsetLeft: %d, offsetWidth: %d }' % (offset, larghezza)};
const scrollerRef = {{ current: scroller }};
const meseCorrenteRef = {{ current: {'cella' if ha_cella else 'null'} }};
const giaScrollato = {{ current: {str(gia_scrollato).lower()} }};
"""
    corsa = "\n".join(["effetto();"] * giri)
    return esegui_ts(
        _MODULO,
        "const { scrollDaNodi } = m;\n" + setup + _estrai_effetto_scroll() + "\n" + corsa
        + "\nemit({ scrollLeft: scroller._s, scritture: scritture.length, armato: !giaScrollato.current });",
        richiede=["scrollDaNodi"],
    )


def test_il_componente_usa_l_helper_e_non_ricalcola():
    """Se il .tsx rifacesse il conto a mano, i test sopra non lo vedrebbero.

    Non basta che la chiamata esista: deve produrre il VALORE giusto. Mettere
    `larghezzaTotale: 0` al call site rimetteva il mese corrente sotto la colonna
    Totale sticky con tutti i test verdi (mutante M14 della terza review) — per
    questo la larghezza vive ora in `LARGHEZZA_COLONNA_TOTALE`, dentro il modulo.
    """
    esito = _gira_effetto(offset=1120, larghezza=140, visibile=1000)
    # La larghezza si legge DAL MODULO, non si riscrive qui: un `totale=160`
    # a mano nel test resterebbe verde se la costante cambiasse nel codice.
    larghezza_totale = esegui_ts(
        _MODULO, "emit(m.LARGHEZZA_COLONNA_TOTALE);",
        richiede=["scrollDaNodi"],
    )
    # Il confronto qui sopra prova l'ACCORDO fra effetto e helper, ma leggendo
    # la costante da entrambi i lati non ne prova il VALORE: raddoppiarla li
    # muove insieme e il test resta verde (mutante M17). Il valore si ancora a
    # cio' che rappresenta — la <col> della colonna Totale nel .tsx.
    assert larghezza_totale > 0, "la colonna Totale sticky ha larghezza zero?"
    src_tab = _TABELLA.read_text(encoding="utf-8")
    larghezze_col = re.findall(r'<col\s+className="w-\[(\d+)px\]"', src_tab)
    assert larghezze_col, "nessuna <col> con larghezza fissa: il layout e' cambiato"
    assert str(int(larghezza_totale)) in larghezze_col, (
        f"LARGHEZZA_COLONNA_TOTALE vale {larghezza_totale}px ma nessuna <col> della "
        f"tabella e' larga cosi' ({larghezze_col}): lo scroll lascerebbe il mese "
        "corrente sotto la colonna sticky, o lo scavalcherebbe"
    )
    atteso = _scroll(1120, larghezza=140, visibile=1000, totale=larghezza_totale)
    assert esito["scrollLeft"] == atteso, (
        f"l'effetto scrolla a {esito['scrollLeft']}, l'helper dice {atteso}: "
        "il componente non sta usando lo stesso conto"
    )


def test_lo_scroll_e_una_volta_sola():
    """Riscrollare a ogni ricalcolo strappa la vista da sotto le mani.

    Cambiando Totale/Media o salvando una cella, `mesiVisibili` cambia identita'
    e l'effetto rigira: senza la guardia il cliente che sta guardando marzo si
    ritroverebbe su settembre.

    La guardia ha DUE meta' e servono entrambe: il return anticipato che legge il
    flag, e l'assegnazione che lo alza. Cercare solo il nome `giaScrollato` non
    bastava — commentando l'assegnazione il nome resta nel file e il test passava
    (mutante S4, sopravvissuto al primo giro). Le righe di commento sono escluse
    per la stessa ragione.
    """
    primo = _gira_effetto(giri=1)
    assert primo["scritture"] == 1, "il primo giro deve scrollare una volta"
    assert primo["scrollLeft"] > 0, "il primo giro non ha scrollato affatto"

    # Tre ricalcoli di fila: lo scroll resta quello del primo giro.
    ripetuto = _gira_effetto(giri=3)
    assert ripetuto["scritture"] == 1, (
        f"l'effetto ha scrollato {ripetuto['scritture']} volte su 3 giri: "
        "il cliente si vede strappare la vista a ogni ricalcolo"
    )

    # Se il flag e' gia' alzato (effetto rimontato), non si scrolla piu'.
    dopo = _gira_effetto(gia_scrollato=True)
    assert dopo["scritture"] == 0, "con il flag alzato non si deve piu' scrollare"


def test_lo_scroll_non_muove_la_pagina():
    """`scrollIntoView()` scrolla anche l'antenato: salterebbe le tessere KPI."""
    righe = [
        r for r in _TABELLA.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith(("//", "*", "/*"))
    ]
    assert not [r for r in righe if "scrollIntoView" in r], (
        "scrollIntoView muove anche la pagina, non solo la tabella"
    )


def test_senza_il_mese_corrente_lo_scroll_resta_armato():
    """Un periodo che non contiene il mese corrente (es. «Seleziona mese» su marzo).

    La `<th>` del mese corrente non esiste, quindi il ref e' null. L'effetto deve
    uscire PRIMA di alzare il flag: alzandolo, quando i dati arrivano davvero
    (o si torna all'anno in corso) lo scroll non scatterebbe piu' e la tabella
    resterebbe su gennaio per sempre — un difetto che a schermo sembra
    intermittente e non si lega alla causa.

    Si ESEGUE l'effetto senza la cella: non deve scrollare e deve restare armato.
    Leggere l'ordine delle righe nel sorgente non bastava — e' la famiglia di
    presidi che in questa fase ha lasciato passare otto mutanti.
    """
    senza = _gira_effetto(ha_cella=False)
    assert senza["scritture"] == 0, "senza la cella non c'e' niente su cui scrollare"
    assert senza["armato"], (
        "il flag viene alzato anche senza la cella: quando il mese corrente "
        "comparira' lo scroll non scattera' piu' e la tabella restera' su gennaio"
    )

    # E quando la cella arriva, lo scroll scatta davvero.
    poi = _gira_effetto(ha_cella=True)
    assert poi["scritture"] == 1, "con la cella presente lo scroll deve scattare"


# ─────────── la cascata P&L: il quarto punto, trovato dalla terza review ────────

def _colore_barra(valore, incompleto):
    return esegui_ts(
        _MODULO,
        "emit(m.coloreBarraRisultato(...input));",
        argomento=[valore, incompleto],
        richiede=["coloreBarraRisultato"],
    )


def test_la_barra_di_un_periodo_incompleto_non_e_verde():
    """Il MOL di un periodo senza costi caricati esce positivo perche' mancano i
    costi, non perche' vada bene: la cascata non deve dipingerlo di verde.

    E' il QUARTO punto della pagina che colora per segno. Il commit 6a5364d ne
    aveva gateati tre (cella desktop, colonna Totale, card mobile) e dichiarava
    il difetto chiuso: la barra della cascata restava verde piena a pochi
    centimetri dai gauge che dicono «Nessun giudizio: N mesi su M non ha costi
    registrati». Trovato dalla terza review del 23/09.
    """
    assert _colore_barra(384120.0, True) == "var(--muted-foreground)"
    assert _colore_barra(-26988.0, True) == "var(--muted-foreground)"


def test_la_barra_di_un_periodo_completo_conserva_il_giudizio():
    """Il gate spegne il colore SOLO quando i dati mancano, non sempre."""
    assert _colore_barra(384120.0, False) == "var(--positivo)"
    assert _colore_barra(-26988.0, False) == "var(--negativo)"


def test_le_due_barre_result_passano_il_flag():
    """Margine F&B e MOL: nessuna delle due deve essere rimasta col ternario.

    Come per i tre punti della tabella, l'espressione del flag si ESEGUE.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    chiamate = re.findall(r"coloreBarraRisultato\((.+?)\)", src)
    assert len(chiamate) == 2, f"attese 2 barre result, trovate {len(chiamate)}: {chiamate}"

    livello_cascata = src.index("function CascataPL(")
    for c in chiamate:
        flag = c.split(",")[1].strip()
        assert flag == "incompleto", (
            f"la barra usa `{flag}` invece del flag del periodo: "
            "un letterale qui rimetterebbe il verde sui mesi senza costi"
        )

    # E il flag deve arrivare davvero dall'alto, non essere inventato dentro.
    firma = src[livello_cascata:livello_cascata + 200]
    assert "incompleto" in firma, "CascataPL non riceve il flag come prop"
    assert "<CascataPL t={t} incompleto={incompleto} />" in src, (
        "il call site di CascataPL non passa il flag"
    )
    assert "incompleto={periodoIncompleto}" in src, (
        "AnalisiVisiva non riceve il flag calcolato sui mesi visibili"
    )
