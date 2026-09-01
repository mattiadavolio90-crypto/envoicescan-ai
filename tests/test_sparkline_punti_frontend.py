"""Mini-linee `<polyline>` (`lib/sparkline-punti.ts`) — 4 grafici, 1 formula.

Perche' esiste: la stessa curva era scritta a mano in quattro pagine (margini,
prezzi, analisi-fatture, demo), nessuna coperta da test. Non erano copie
identiche, ed e' il punto: geometrie diverse (100x24, 96x32, 64x18) e DUE
normalizzazioni diverse dell'asse y. Una funzione unica avrebbe cambiato
grafici oggi corretti, quindi i parametri restano espliciti e questi test
fissano la configurazione di ciascuna pagina.

L'unico comportamento reso uniforme e' il filtro dei valori non finiti, che
aveva una sola delle quattro: senza, un NaN o un Infinity propaga in min/max e
produce `points="NaN,NaN"` — la polyline sparisce senza nessun errore. Le altre
tre filtravano `isNaN` a monte (che non ferma Infinity) o niente affatto.
"""

from tests.helpers_ts import esegui_ts

MODULO = "lib/sparkline-punti"

# Le quattro configurazioni reali, come le passano i componenti.
KPI_BAR = {"w": 100, "h": 24, "ancoraZero": True, "padY": 1}          # margini/kpi-bar
VARIAZIONI = {"w": 96, "h": 32}                                       # prezzi + demo
PIVOT = {"w": 64, "h": 18, "ancoraZero": True, "decimali": None}      # analisi-fatture


def _punti(valori, opts):
    return esegui_ts(
        MODULO,
        "emit(m.puntiSparkline(...input));",
        argomento=[valori, opts],
        richiede=["puntiSparkline"],
    )


def _punti_js(espr_valori, opts):
    """Come `_punti`, ma la serie e' costruita in JavaScript.

    Serve per NaN/Infinity: `json.dumps` li scrive come `NaN`/`Infinity`, che
    NON sono JSON validi — `JSON.parse` dentro l'harness muore con SyntaxError.
    Un valore non finito non puo' attraversare il confine Python->node come
    dato, quindi si genera dall'altra parte.
    """
    return esegui_ts(
        MODULO,
        f"emit(m.puntiSparkline({espr_valori}, input[0]));",
        argomento=[opts],
        richiede=["puntiSparkline"],
    )


def _coppie(s):
    return [tuple(float(x) for x in p.split(",")) for p in s.split(" ")]


# ─── meno di due punti non e' una linea ───────────────────────────────────

def test_serie_troppo_corta_torna_null():
    """null e non stringa vuota: una polyline con points="" e' un elemento
    degenere, il chiamante deve poter mostrare altro."""
    assert _punti([5], KPI_BAR) is None
    assert _punti([], KPI_BAR) is None


def test_serie_che_diventa_corta_DOPO_il_filtro_torna_null():
    """Due valori di cui uno NaN: dopo il filtro ne resta uno solo."""
    assert _punti_js("[5, NaN]", KPI_BAR) is None


# ─── il filtro dei non finiti: il fix vero di questa fase ────────────────

def test_un_NaN_non_contamina_piu_tutta_la_linea():
    """Prima: un solo NaN entrava in Math.min/max, range diventava NaN e OGNI
    coordinata usciva "NaN,NaN" — grafico vuoto, nessun errore, nessun indizio.
    """
    out = _punti_js("[10, NaN, 30]", VARIAZIONI)
    assert "NaN" not in out
    assert len(_coppie(out)) == 2      # il valore rotto e' scartato, non zero


def test_Infinity_e_scartato_come_NaN():
    """`isNaN` (il filtro che avevano tre delle quattro pagine) lascia passare
    Infinity: `Math.max` diventa Infinity e range esplode."""
    out = _punti_js("[10, Infinity, 30]", VARIAZIONI)
    assert "NaN" not in out and "Infinity" not in out
    assert len(_coppie(out)) == 2


def test_meno_infinito_idem():
    out = _punti_js("[10, -Infinity, 30]", VARIAZIONI)
    assert "NaN" not in out and "Infinity" not in out


# ─── geometria: le coordinate esatte, non solo "coerenti" ────────────────

def test_kpi_bar_geometria_assoluta():
    """Valori assoluti: un errore coerente (padY ignorato, asse capovolto)
    passerebbe un test che controlla solo la forma."""
    out = _punti([0, 10], KPI_BAR)
    assert out == "0.0,23.0 100.0,1.0"


def test_variazioni_geometria_assoluta():
    out = _punti([0, 10], VARIAZIONI)
    assert out == "0.0,32.0 96.0,0.0"


def test_pivot_NON_arrotonda_le_coordinate():
    """pivot-tab non aveva toFixed: le coordinate escono intere/grezze.
    Se un giorno le si vuole arrotondare e' una decisione, non un dettaglio."""
    out = _punti([0, 1], PIVOT)
    assert out == "0,18 64,0"


def test_x_va_da_zero_alla_larghezza_piena():
    out = _coppie(_punti([1, 2, 3], VARIAZIONI))
    assert out[0][0] == 0.0 and out[-1][0] == 96.0


def test_y_e_invertita_valore_alto_sta_in_alto():
    """In SVG y cresce verso il basso: il valore massimo deve avere y minima."""
    c = _coppie(_punti([1, 100], VARIAZIONI))
    assert c[1][1] < c[0][1]


# ─── ancoraZero: la differenza che vietava di unificare le 4 copie ───────

def test_ancoraZero_include_lo_zero_nella_scala():
    """Serie tutta positiva: con l'ancora l'asse parte da 0, quindi il minimo
    NON tocca il fondo del grafico."""
    ancorata = _coppie(_punti([10, 20], {"w": 100, "h": 24, "ancoraZero": True}))
    assert ancorata[0][1] < 24.0        # 10 non e' sul fondo: lo zero e' sotto


def test_senza_ancora_la_scala_si_adatta_ai_valori():
    """Stessi dati, nessuna ancora: il minimo tocca il fondo."""
    libera = _coppie(_punti([10, 20], {"w": 100, "h": 24}))
    assert libera[0][1] == 24.0


def test_ancoraZero_include_anche_UNO_non_solo_lo_zero():
    """`Math.max(...vals, 1)`: il tetto della scala non scende mai sotto 1.

    Serve su serie di conteggi piccoli (pivot-tab conta righe fattura): senza,
    una serie [0, 0.4] verrebbe scalata come se 0,4 fosse il massimo possibile
    e il grafico mostrerebbe una salita a fondo scala per quattro decimi.

    Trovato da un mutante SOPRAVVISSUTO: tutti i miei casi avevano valori >= 1,
    dove `max(...vals, 1)` e `max(...vals)` coincidono.
    """
    out = _coppie(_punti([0, 0.4], PIVOT))
    assert out[1][1] > 0.0          # 0,4 NON tocca il tetto del grafico
    # con la scala ancorata a 1, 0,4 sta al 40% dell'altezza
    assert abs(out[1][1] - 18 * 0.6) < 0.01


def test_le_due_normalizzazioni_danno_linee_DIVERSE():
    """La prova che non si potevano collassare in un comportamento unico."""
    assert _punti([10, 20], {"w": 100, "h": 24, "ancoraZero": True}) != _punti(
        [10, 20], {"w": 100, "h": 24}
    )


# ─── casi degeneri ────────────────────────────────────────────────────────

def test_serie_piatta_non_divide_per_zero():
    """max - min = 0: `|| 1` evita la divisione e la linea resta dritta."""
    out = _coppie(_punti([7, 7, 7], VARIAZIONI))
    ys = {y for _, y in out}
    assert len(ys) == 1 and "nan" not in str(ys).lower()


def test_tutti_zero_con_ancora():
    out = _punti([0, 0], PIVOT)
    assert "NaN" not in out


def test_valori_negativi():
    out = _punti([-100, -50], VARIAZIONI)
    assert "NaN" not in out
    c = _coppie(out)
    assert c[1][1] < c[0][1]      # -50 e' maggiore: sta piu' in alto


def test_valori_enormi_non_perdono_la_forma():
    c = _coppie(_punti([1e9, -1e9], VARIAZIONI))
    assert c[0][1] == 0.0 and c[1][1] == 32.0


def test_serie_lunga_ha_un_punto_per_valore():
    out = _coppie(_punti(list(range(24)), KPI_BAR))
    assert len(out) == 24
