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


def test_bastano_le_spese_generali_senza_food_cost():
    """La condizione e' AND, non OR: un costo qualsiasi rende il mese leggibile.

    E' la stessa soglia del worker (`_mesi_senza_costi`): un mese con 114 EUR di
    sole spese generali su 444.000 EUR di ricavi conta come "con costi". La
    coerenza fra le due definizioni e' voluta — divergendo, la tabella
    colorerebbe di verde proprio i mesi per cui «Analisi visiva» dichiara di non
    avere un giudizio.
    """
    assert _senza_costi(
        _pivot(fatturato_netto=444234.0, costi_spese_totali=114.0)
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

def test_tutti_e_tre_i_punti_passano_il_flag():
    """Tre superfici calcolano il colore: cella desktop, colonna Totale, card mobile.

    Provare la funzione senza i suoi chiamanti e' esattamente l'errore che in
    questa fase ha lasciato passare 6 mutanti su 8 (blocco C): il colore giusto
    calcolato da nessuno resta un colore sbagliato a schermo. Qui si conta che
    NESSUNA chiamata a due argomenti sia rimasta indietro.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    chiamate = re.findall(r"valueColorCls\((.+?)\);", src)
    assert len(chiamate) == 3, f"attese 3 chiamate, trovate {len(chiamate)}: {chiamate}"
    for c in chiamate:
        assert c.count(",") >= 2, f"chiamata senza il flag di completezza: valueColorCls({c})"


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


def test_il_componente_usa_l_helper_e_non_ricalcola():
    """Se il .tsx rifacesse il conto a mano, i test sopra non lo vedrebbero."""
    src = _TABELLA.read_text(encoding="utf-8")
    assert "scrollPerMeseCorrente({" in src, "calcolo-tab.tsx non usa piu' l'helper"


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
    righe = [
        r.strip() for r in _TABELLA.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith(("//", "*", "/*"))
    ]
    legge = [r for r in righe if "giaScrollato.current" in r and "return" in r]
    alza = [r for r in righe if re.match(r"giaScrollato\.current\s*=\s*true", r)]
    assert legge, "manca il return anticipato: l'effetto rigira a ogni ricalcolo"
    assert alza, "il flag non viene mai alzato: la guardia non scatta mai"


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

    Si verifica l'ORDINE delle righe nell'effetto, che e' il comportamento:
    il return sul ref mancante deve venire prima dell'assegnazione.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    inizio = src.index("const scrollerRef")
    fine = src.index("}, [mesiVisibili]);", inizio)
    corpo = src[inizio:fine]
    guardia = corpo.index("if (!scroller || !cella) return;")
    alza = corpo.index("giaScrollato.current = true;")
    assert guardia < alza, (
        "il flag viene alzato prima della guardia sul ref: senza il mese corrente "
        "a schermo lo scroll si disarma e non scatta piu'"
    )
