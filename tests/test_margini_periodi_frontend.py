"""`periodi.ts` decide QUALI fatture entrano nel MOL, e scorpora l'IVA sui ricavi.

Due classi di difetto, entrambe invisibili: il numero esce solo sbagliato.

1. **I confini di periodo** (`calcolaPeriodo`, 13 preset) diventano `data_da`/
   `data_a` nelle query. Un trimestre che sfora di un mese non solleva niente:
   somma fatture di un periodo diverso da quello che l'utente ha chiesto.
2. **Lo scorporo IVA** (`scorporoNetto`) e' una **divisione**: i ricavi sono
   salvati lordi. Un `/` diventato `*` gonfia il fatturato del 21% e il MOL con
   lui.

**Perche' non e' codice di una pagina sola.** `margini/periodi.ts` e' importata
anche da `(mobile)/m/diario/mobile-incassi.tsx:10` (`scorporoNetto`, `NettoMese`):
un difetto qui esce su due frontend, e `/m` non e' responsive ma separato.

**Perche' i fusi.** I confini si costruiscono con `new Date(y, m, d)`, che e'
**locale**. Un mutante che passa a UTC muore solo a ovest di Greenwich. I preset
che chiudono su `fmt(oggi)` si provano anche a UTC+14/UTC-11: li' il "giorno
corrente" differisce di due giorni civili da quello UTC.

**Perche' 12 mesi parametrizzati su `meseLabel`.** Con un solo mese di campione,
il mutante `arr[month1Based]` (che slitta l'etichetta di uno) muore solo su
dicembre, dove finisce fuori array. Su tutti gli altri restituisce il nome del
mese successivo — sbagliato ma plausibile, e sopravvive.

**Fatto verificato il 31/8, non ri-indagarlo:** esistono due `periodi.ts`,
`margini/` (156 righe) e `analisi-fatture/` (103). Non sono un clone divergente:
quello di margini e' un superset (trimestri, semestri, anno precedente, scorporo
IVA) e le parti comuni sono equivalenti — `calcolaMese` differisce solo nel come
costruisce l'etichetta, non nelle date.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "app/(app)/margini/periodi"

FUSI = ["Europe/Rome", "America/Los_Angeles"]
# Offset -11 e +14: 25 ore di distanza. Qualunque sia l'ora in cui gira la suite,
# in almeno uno dei due la data locale differisce da quella UTC.
FUSI_ESTREMI = ["Pacific/Midway", "Pacific/Kiritimati"]

_RICHIEDE = ["calcolaPeriodo", "calcolaMese", "mesiSelezionabili",
             "scorporoNetto", "meseLabel"]


def _periodo(preset, oggi=None, tz="Europe/Rome"):
    """`oggi` = (anno, mese1based, giorno); None = usa il new Date() interno."""
    arg = f"new Date({oggi[0]},{oggi[1] - 1},{oggi[2]})" if oggi else "undefined"
    return esegui_ts(MODULO, f"emit(m.calcolaPeriodo(input, {arg}));",
                     argomento=preset, tz=tz, richiede=_RICHIEDE)


def _oggi_in(tz):
    """La data che node vede in quel fuso.

    Non si usa `date.today()` di Python: a cavallo di mezzanotte, o col processo
    in un fuso diverso, le due divergono e il test fallirebbe per un motivo che
    non c'entra col codice sotto esame.
    """
    return esegui_ts(
        MODULO,
        "const d = new Date();"
        "emit([d.getFullYear(), d.getMonth() + 1, d.getDate()]);",
        tz=tz, richiede=_RICHIEDE,
    )


# Oggi fisso al 31/8/2026: dentro Q3 e H2, cosi' i preset "corrente" hanno un
# valore atteso stabile e non a cavallo di nessun confine.
_OGGI = (2026, 8, 31)

# Misurati eseguendo il modulo vero, non dedotti a mente.
_ATTESI = {
    "mese_corrente":      ("2026-08-01", "2026-08-31", "Mese in corso"),
    "trimestre_corrente": ("2026-07-01", "2026-08-31", "Trimestre"),
    "semestre_corrente":  ("2026-07-01", "2026-08-31", "Semestre"),
    "anno_corrente":      ("2026-01-01", "2026-08-31", "Anno in corso"),
    "anno_precedente":    ("2025-01-01", "2025-12-31", "Anno 2025"),
    "q1": ("2026-01-01", "2026-03-31", "Q1 2026"),
    "q2": ("2026-04-01", "2026-06-30", "Q2 2026"),
    "q3": ("2026-07-01", "2026-09-30", "Q3 2026"),
    "q4": ("2026-10-01", "2026-12-31", "Q4 2026"),
    "h1": ("2026-01-01", "2026-06-30", "H1 2026"),
    "h2": ("2026-07-01", "2026-12-31", "H2 2026"),
}


@pytest.mark.parametrize("preset", sorted(_ATTESI))
@pytest.mark.parametrize("tz", FUSI)
def test_ogni_preset_ha_i_suoi_confini(preset, tz):
    """Ogni preset e' un confine di data: sforare somma fatture di un altro periodo."""
    da, a, label = _ATTESI[preset]
    r = _periodo(preset, _OGGI, tz)
    assert (r["data_da"], r["data_a"]) == (da, a), (
        f"preset {preset!r}: confini {r['data_da']}..{r['data_a']} invece di "
        f"{da}..{a}. Le fatture sommate non sono quelle del periodo chiesto"
    )
    assert r["label"] == label


@pytest.mark.parametrize("preset", ["personalizzato", "mese_specifico"])
def test_i_preset_a_date_libere_cadono_sul_default(preset):
    """Non hanno confini propri: le date le passa `filtri-periodo.tsx`.

    Il default e' "anno corrente". E' un comportamento che nessuno puo' leggere
    senza aprire il file: scritto qui.
    """
    r = _periodo(preset, _OGGI)
    assert (r["data_da"], r["data_a"], r["label"]) == (
        "2026-01-01", "2026-08-31", "Anno in corso")


def test_un_preset_ignoto_non_esplode():
    """Il cast `as PeriodoPreset` in page.tsx non valida: un preset dall'URL
    puo' essere qualunque stringa e deve cadere sul default, non su undefined."""
    r = _periodo("pippo", _OGGI)
    assert r["data_da"] == "2026-01-01" and r["label"] == "Anno in corso"


@pytest.mark.parametrize("tz", FUSI + FUSI_ESTREMI)
@pytest.mark.parametrize("preset", ["mese_corrente", "anno_corrente"])
def test_i_preset_correnti_chiudono_sul_giorno_locale(preset, tz):
    """`data_a` = `fmt(oggi)`: deve essere il giorno LOCALE, non quello UTC.

    Nei fusi estremi la data locale e quella UTC differiscono: se `fmt` leggesse
    l'istante UTC, il periodo si chiuderebbe un giorno prima o dopo. A cavallo
    di fine mese questo sposta il periodo di un mese intero.
    """
    anno, mese, giorno = _oggi_in(tz)
    r = _periodo(preset, None, tz)
    assert r["data_a"] == f"{anno:04d}-{mese:02d}-{giorno:02d}", (
        f"il periodo non chiude sul giorno locale di {tz}: fmt() sta leggendo "
        "l'istante UTC invece dell'ora locale"
    )


@pytest.mark.parametrize("mese1,ultimo", [
    (1, 31), (2, 28), (3, 31), (4, 30), (5, 31), (6, 30),
    (7, 31), (8, 31), (9, 30), (10, 31), (11, 30), (12, 31),
])
@pytest.mark.parametrize("tz", FUSI)
def test_calcola_mese_copre_il_mese_intero(mese1, ultimo, tz):
    """`calcolaMese` prende il mese **1-based**, mentre `oggi.getMonth()` e'
    0-based: e' la classe di off-by-one piu' facile da introdurre qui."""
    r = esegui_ts(MODULO, f"emit(m.calcolaMese(2026, {mese1}));",
                  tz=tz, richiede=_RICHIEDE)
    assert r["data_da"] == f"2026-{mese1:02d}-01", (
        f"il mese {mese1} non parte dal primo: off-by-one 1-based/0-based"
    )
    assert r["data_a"] == f"2026-{mese1:02d}-{ultimo:02d}", (
        f"il mese {mese1} non finisce il {ultimo}: lastDay sbagliato di un mese"
    )


@pytest.mark.parametrize("anno,ultimo", [(2024, 29), (2026, 28), (2000, 29), (1900, 28)])
def test_febbraio_bisestile(anno, ultimo):
    """Il 2000 e' bisestile (divisibile per 400), il 1900 no (per 100 ma non 400).
    `new Date(y, 2, 0)` deve saperlo: e' la regola del calendario, non aritmetica."""
    r = esegui_ts(MODULO, f"emit(m.calcolaMese({anno}, 2));", richiede=_RICHIEDE)
    assert r["data_a"] == f"{anno}-02-{ultimo}"


@pytest.mark.parametrize("tz", FUSI)
def test_i_quattro_trimestri_coprono_l_anno_senza_buchi_ne_sovrapposizioni(tz):
    """La proprieta' che i singoli assert non catturano: Q1..Q4 devono
    tassellare l'anno esattamente. Un confine spostato crea un buco (fatture
    che non entrano in nessun trimestre) o una sovrapposizione (contate due)."""
    q = [_periodo(f"q{i}", _OGGI, tz) for i in range(1, 5)]
    assert q[0]["data_da"] == "2026-01-01"
    assert q[3]["data_a"] == "2026-12-31"
    for i in range(3):
        fine, inizio_dopo = q[i]["data_a"], q[i + 1]["data_da"]
        assert fine < inizio_dopo, f"Q{i+1} e Q{i+2} si sovrappongono"
        import datetime
        d_fine = datetime.date.fromisoformat(fine)
        d_dopo = datetime.date.fromisoformat(inizio_dopo)
        assert (d_dopo - d_fine).days == 1, (
            f"buco fra Q{i+1} ({fine}) e Q{i+2} ({inizio_dopo}): le fatture "
            "in mezzo non entrano in nessun trimestre"
        )


@pytest.mark.parametrize("tz", FUSI)
def test_i_due_semestri_coprono_l_anno(tz):
    h1, h2 = _periodo("h1", _OGGI, tz), _periodo("h2", _OGGI, tz)
    assert (h1["data_da"], h1["data_a"]) == ("2026-01-01", "2026-06-30")
    assert (h2["data_da"], h2["data_a"]) == ("2026-07-01", "2026-12-31")


@pytest.mark.parametrize("mese1,trim_da", [
    (1, "01"), (3, "01"), (4, "04"), (6, "04"),
    (7, "07"), (9, "07"), (10, "10"), (12, "10"),
])
def test_il_trimestre_corrente_parte_dal_mese_giusto(mese1, trim_da):
    """Confini di trimestre: primo e ultimo mese di ciascuno.
    `Math.floor(m/3)*3` — un `ceil` sposterebbe l'inizio in avanti."""
    r = _periodo("trimestre_corrente", (2026, mese1, 15))
    assert r["data_da"] == f"2026-{trim_da}-01", (
        f"a {mese1}/2026 il trimestre parte da {r['data_da']}"
    )


@pytest.mark.parametrize("mese1,sem_da", [(1, "01"), (6, "01"), (7, "07"), (12, "07")])
def test_il_semestre_corrente_parte_dal_mese_giusto(mese1, sem_da):
    """Giugno e' l'ultimo del primo semestre, luglio il primo del secondo:
    `m < 6` con m 0-based. Un `<=` sposterebbe luglio nel primo semestre."""
    r = _periodo("semestre_corrente", (2026, mese1, 15))
    assert r["data_da"] == f"2026-{sem_da}-01"


@pytest.mark.parametrize("n", [1, 2, 13, 24, 25])
def test_mesi_selezionabili_decrementa_con_il_wrap_di_anno(n):
    """n=13 e n=25 attraversano il capodanno una e due volte: e' li' che il
    decremento a mano (`m -= 1; if (m < 1) { m = 12; y -= 1 }`) sbaglia."""
    got = esegui_ts(
        MODULO,
        f"emit(m.mesiSelezionabili({n}, new Date(2026,0,15)).map(x => [x.year, x.month]));",
        richiede=_RICHIEDE,
    )
    atteso, y, mm = [], 2026, 1
    for _ in range(n):
        atteso.append([y, mm])
        mm -= 1
        if mm < 1:
            mm, y = 12, y - 1
    assert got == atteso, f"lista mesi sbagliata a n={n}"
    assert len(got) == n
    assert all(1 <= mese <= 12 for _, mese in got), (
        f"mese fuori range 1-12 (wrap sbagliato): {got}"
    )


def test_il_primo_mese_selezionabile_e_quello_corrente():
    got = esegui_ts(
        MODULO,
        "emit(m.mesiSelezionabili(24, new Date(2026,7,31))[0]);",
        richiede=_RICHIEDE,
    )
    assert (got["year"], got["month"]) == (2026, 8), (
        "la lista non parte dal mese corrente: sta andando nel futuro o "
        "saltando un mese"
    )


@pytest.mark.parametrize("mese1,nome", [
    (1, "Gennaio"), (2, "Febbraio"), (3, "Marzo"), (4, "Aprile"),
    (5, "Maggio"), (6, "Giugno"), (7, "Luglio"), (8, "Agosto"),
    (9, "Settembre"), (10, "Ottobre"), (11, "Novembre"), (12, "Dicembre"),
])
def test_mese_label_su_tutti_i_dodici_mesi(mese1, nome):
    """Tutti e 12: con un mese solo, `arr[month1Based]` (slitta di uno)
    sopravvive ovunque tranne dicembre."""
    got = esegui_ts(MODULO, f"emit(m.meseLabel(2026, {mese1}));", richiede=_RICHIEDE)
    assert got == f"{nome} 2026"


@pytest.mark.parametrize("mese1,short", [(1, "Gen"), (5, "Mag"), (9, "Set"), (12, "Dic")])
def test_mese_label_short(mese1, short):
    got = esegui_ts(MODULO, f"emit(m.meseLabel(2026, {mese1}, true));", richiede=_RICHIEDE)
    assert got == f"{short} 2026"


# ============================================================
# scorporoNetto — i ricavi sono salvati LORDI
# ============================================================

def test_scorporo_e_una_divisione_non_una_moltiplicazione():
    """Il mutante `/` -> `*` deve morire: gonfierebbe il fatturato del 21%.

    Importi scelti perche' il netto sia intero: 1.10*8 scorporato da' 8,
    1.22*16 da' 16, `altri` non si scorpora. Netto = 56.
    """
    got = esegui_ts(MODULO, f"emit(m.scorporoNetto({1.10 * 8}, {1.22 * 16}, 32));",
                    richiede=_RICHIEDE)
    assert got == pytest.approx(56), (
        "lo scorporo non divide: i ricavi sono salvati lordi e il netto "
        "risulterebbe piu' alto del lordo"
    )
    assert got < (1.10 * 8) + (1.22 * 16) + 32, "il netto non puo' superare il lordo"


def test_le_due_aliquote_sono_distinte():
    """Se i due divisori collassassero sullo stesso valore, un ricavo al 22%
    verrebbe scorporato al 10% (e viceversa)."""
    a = esegui_ts(MODULO, "emit(m.scorporoNetto(100, 0, 0));", richiede=_RICHIEDE)
    b = esegui_ts(MODULO, "emit(m.scorporoNetto(0, 100, 0));", richiede=_RICHIEDE)
    assert a != b, "IVA 10% e 22% scorporano allo stesso modo"
    assert a == pytest.approx(100 / 1.10)
    assert b == pytest.approx(100 / 1.22)


def test_i_divisori_iva_valgono_le_aliquote_di_legge():
    """Le costanti sono duplicate a mano in `carica-ricavi-dialog.tsx:464,490`
    (`/1.10`, `/1.22` scritti in chiaro). Il commento a `periodi.ts:93` dichiara
    che lo scorporo sta "in un solo punto": questo test e' la rete che se ne
    accorge se un'aliquota cambia in un posto solo."""
    d10, d22 = esegui_ts(MODULO, "emit([m.IVA_DIVISORE_10, m.IVA_DIVISORE_22]);",
                         richiede=_RICHIEDE)
    assert (d10, d22) == (1.10, 1.22)


def test_gli_altri_ricavi_non_si_scorporano():
    """Sono senza IVA: dividerli sarebbe uno sconto silenzioso."""
    got = esegui_ts(MODULO, "emit(m.scorporoNetto(0, 0, 500));", richiede=_RICHIEDE)
    assert got == 500


def test_scorporo_additivo_sui_tre_addendi():
    """Nessun addendo sparisce o viene contato due volte."""
    parti = [
        esegui_ts(MODULO, f"emit(m.scorporoNetto({a}, {b}, {c}));", richiede=_RICHIEDE)
        for a, b, c in [(110, 0, 0), (0, 122, 0), (0, 0, 7)]
    ]
    insieme = esegui_ts(MODULO, "emit(m.scorporoNetto(110, 122, 7));", richiede=_RICHIEDE)
    assert insieme == pytest.approx(sum(parti))


@pytest.mark.parametrize("tz", FUSI + FUSI_ESTREMI)
def test_lo_scorporo_non_dipende_dal_fuso(tz):
    """Aritmetica pura: qualunque dipendenza dal fuso qui sarebbe un difetto.
    E' il test che vale anche per `(mobile)/m/diario`, che importa questa funzione."""
    got = esegui_ts(MODULO, "emit(m.scorporoNetto(110, 122, 5));",
                    tz=tz, richiede=_RICHIEDE)
    assert got == pytest.approx(205)


def test_formato_data_iso_stretto():
    """`fmt` produce le stringhe che finiscono nelle query: giorno e mese a due
    cifre. Un `2026-8-1` non e' confrontabile lessicograficamente con `2026-08-15`,
    ed e' cosi' che i filtri di `filtri-periodo.tsx:126,140` confrontano i range."""
    import re
    r = _periodo("mese_corrente", (2026, 8, 5))
    for campo in ("data_da", "data_a"):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[campo]), (
            f"{campo}={r[campo]!r} non e' ISO a cifre fisse"
        )
    assert r["data_da"] == "2026-08-01" and r["data_a"] == "2026-08-05"
