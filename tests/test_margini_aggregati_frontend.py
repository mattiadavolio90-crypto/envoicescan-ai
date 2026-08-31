"""Copertura di `apps/web/src/lib/margini-aggregati.ts` — logica pura di margini/.

Le funzioni qui dentro erano dentro i componenti `.tsx` di `app/(app)/margini/`,
accanto a JSX e hook: `helpers_ts.esegui_ts` non sa montare React, quindi erano
irraggiungibili da un test e infatti non ne avevano nessuno. Sono state estratte
**byte per byte, senza correzioni** (fasi C/D/E dell'audit del 31/8/2026).

Cosa decidono, in euro:
- `aggregaCoperti`/`aggregaRicavi` scrivono la colonna Totale/Media della tabella
  coperti (scontrino medio, ricavi per coperto);
- `pivotMedia` divide **tutti** i campi della pivot del MOL;
- le `DERIVE` sommano le quote di riparto ai costi: se una sparisce, il costo
  mostrato e' piu' basso del vero e il MOL piu' alto;
- `buildMesiList` decide quali mesi l'utente puo' compilare a mano.

**Non e' un test di regressione ordinario:** `test_asimmetria_*` fotografa un
comportamento che sappiamo sbagliato. Vedi il docstring di quei test.
"""
import pytest

from tests.helpers_ts import esegui_ts

_MODULO = "lib/margini-aggregati"


def _mese(anno=2026, mese=1, coperti=None, ricavi=0.0, **extra):
    """Un `CopertiMese`. Solo i campi che le funzioni leggono davvero."""
    return {
        "anno": anno, "mese": mese, "label": f"{mese}/{anno}",
        "coperti": coperti, "ricavi_netto": ricavi, "ricavi_lordo": ricavi,
        "scontrino_medio_netto": None, "scontrino_medio_lordo": None,
        "costo_fb": 0.0, "costo_fb_per_coperto": None,
        **extra,
    }


def _chiama(fn, args, richiede=None):
    return esegui_ts(
        _MODULO,
        f"emit(m.{fn}(...input));",
        argomento=args,
        richiede=richiede or [fn],
    )


# ─────────────────────────── aggregaCoperti ────────────────────────────────

def test_coperti_totale_somma_i_mesi():
    mesi = [_mese(coperti=8), _mese(mese=2, coperti=16), _mese(mese=3, coperti=32)]
    assert _chiama("aggregaCoperti", [mesi, False, 3]) == 56


def test_coperti_media_divide_per_nmesi():
    mesi = [_mese(coperti=8), _mese(mese=2, coperti=16), _mese(mese=3, coperti=32)]
    assert _chiama("aggregaCoperti", [mesi, True, 4]) == 14


def test_coperti_tutti_null_torna_null_non_zero():
    """`null` = "non lo so", `0` = "nessun coperto". La UI mostra "—" sul primo.

    Se questo collassasse a 0 il cliente leggerebbe "zero coperti" su un periodo
    di cui semplicemente non abbiamo il dato — e' la stessa distinzione che
    `fetchNettoMese` protegge sul netto (vedi test_margini_netto_mese_frontend).
    """
    mesi = [_mese(coperti=None, ricavi=1024.0), _mese(mese=2, coperti=None)]
    assert _chiama("aggregaCoperti", [mesi, False, 2]) is None


def test_coperti_zero_esplicito_non_e_null():
    """`coperti: 0` e' un dato: il mese e' stato chiuso senza clienti."""
    assert _chiama("aggregaCoperti", [[_mese(coperti=0)], False, 1]) == 0


def test_coperti_ignora_i_null_nella_somma():
    mesi = [_mese(coperti=64), _mese(mese=2, coperti=None), _mese(mese=3, coperti=None)]
    assert _chiama("aggregaCoperti", [mesi, False, 1]) == 64


def test_coperti_lista_vuota_torna_null():
    assert _chiama("aggregaCoperti", [[], False, 0]) is None


def test_coperti_nmesi_zero_non_divide_per_zero():
    """`Math.max(1, nMesi)`: senza la guardia sarebbe `Infinity`, non un numero."""
    got = _chiama("aggregaCoperti", [[_mese(coperti=100)], True, 0])
    assert got == 100


# ─────────────────────────── aggregaRicavi ─────────────────────────────────

def test_ricavi_totale_somma_i_mesi():
    mesi = [_mese(ricavi=8.0), _mese(mese=2, ricavi=16.0), _mese(mese=3, ricavi=32.0)]
    assert _chiama("aggregaRicavi", [mesi, False, 3]) == 56


def test_ricavi_media_divide_per_nmesi():
    mesi = [_mese(ricavi=8.0), _mese(mese=2, ricavi=16.0), _mese(mese=3, ricavi=32.0)]
    assert _chiama("aggregaRicavi", [mesi, True, 2]) == 28


def test_ricavi_lista_vuota_e_zero_non_null():
    """A differenza dei coperti, i ricavi non hanno lo stato "non lo so"."""
    assert _chiama("aggregaRicavi", [[], False, 0]) == 0


def test_ricavi_nmesi_zero_non_divide_per_zero():
    assert _chiama("aggregaRicavi", [[_mese(ricavi=100.0)], True, 0]) == 100


# ───────────── filtri del componente: mesiVisibili / numMesiAttivi ─────────

def test_mesi_visibili_tiene_chi_ha_coperti_o_ricavi():
    mesi = [
        _mese(mese=1, coperti=10, ricavi=0.0),
        _mese(mese=2, coperti=None, ricavi=500.0),
        _mese(mese=3, coperti=0, ricavi=0.0),
        _mese(mese=4, coperti=None, ricavi=0.0),
    ]
    visibili = _chiama("mesiVisibili", [mesi], richiede=["mesiVisibili"])
    assert [v["mese"] for v in visibili] == [1, 2]


def test_num_mesi_attivi_conta_solo_i_coperti():
    mesi = [
        _mese(mese=1, coperti=10, ricavi=0.0),
        _mese(mese=2, coperti=None, ricavi=500.0),
        _mese(mese=3, coperti=0, ricavi=99.0),
    ]
    assert _chiama("numMesiAttivi", [mesi], richiede=["numMesiAttivi"]) == 1


# ─────────────────── L'ASIMMETRIA — comportamento fotografato ──────────────

def test_asimmetria_media_ricavi_sovrastimata_su_mese_senza_coperti():
    """FOTOGRAFIA DI UN DIFETTO NOTO — se questo test diventa rosso, **non
    aggiustarlo**: qualcuno ha corretto l'asimmetria, e allora va aggiornato
    insieme al verbale.

    `mesiVisibili` tiene i mesi con `coperti>0 OR ricavi>0`; `numMesiAttivi`
    conta solo quelli con `coperti>0`. `aggregaRicavi` somma **tutti** i mesi
    visibili ma divide per il conteggio piu' stretto: un mese con ricavi ma
    senza coperti gonfia il numeratore senza toccare il denominatore.

    Qui: 1024 + 1024 = 2048 di ricavi su 2 mesi, ma un solo mese ha coperti.
    La media mostrata e' 2048 (come se fosse un mese solo), non 1024.
    La label dice "Media sui 1 mesi con coperti" anche sulla riga Ricavi.

    Misurato il 31/8/2026: 0 sedi su 8 oggi nel caso misto, ma le 66 righe
    `source='manuale'` hanno tutte `coperti` NULL — si arma da solo.
    Decisione di Mattia: fotografare, non correggere.
    """
    grezzi = [
        _mese(mese=1, coperti=100, ricavi=1024.0),
        _mese(mese=2, coperti=None, ricavi=1024.0),
    ]
    visibili = _chiama("mesiVisibili", [grezzi], richiede=["mesiVisibili"])
    n = _chiama("numMesiAttivi", [visibili], richiede=["numMesiAttivi"])

    assert len(visibili) == 2, "entrambi i mesi restano visibili"
    assert n == 1, "ma solo uno conta come attivo"

    media = _chiama("aggregaRicavi", [visibili, True, n])
    assert media == 2048, "media sovrastimata: e' il difetto fotografato"

    onesta = sum(v["ricavi_netto"] for v in visibili) / len(visibili)
    assert onesta == 1024
    assert media == onesta * 2, "il fattore di gonfiaggio e' mesi_visibili/mesi_attivi"


def test_asimmetria_assente_quando_ogni_mese_ha_coperti():
    """Controprova: senza mesi misti le due medie coincidono."""
    grezzi = [
        _mese(mese=1, coperti=100, ricavi=1024.0),
        _mese(mese=2, coperti=50, ricavi=1024.0),
    ]
    visibili = _chiama("mesiVisibili", [grezzi], richiede=["mesiVisibili"])
    n = _chiama("numMesiAttivi", [visibili], richiede=["numMesiAttivi"])
    assert _chiama("aggregaRicavi", [visibili, True, n]) == 1024


# ──────────────────────────── pivotMedia (fase D) ──────────────────────────

def _pivot(**over):
    """MesePivot con ogni campo a una potenza di 2 distinta: qualunque scambio
    di campo si legge dal risultato senza ambiguita'."""
    base = {
        "anno": 2026, "mese": 6, "label": "Giu 2026",
        "fatturato_iva10": 2.0, "fatturato_iva22": 4.0, "altri_ricavi_noiva": 8.0,
        "fatturato_netto": 16.0, "costi_fb_auto": 32.0, "altri_costi_fb": 64.0,
        "costi_fb_totali": 128.0, "primo_margine": 256.0, "costi_spese_auto": 512.0,
        "altri_costi_spese": 1024.0, "costi_spese_totali": 2048.0,
        "costo_dipendenti": 4096.0, "costo_personale_extra": 8192.0,
        "costi_personale": 16384.0, "mol": 32768.0,
        "quote_riparto_fb": 65536.0, "quote_riparto_spese": 131072.0,
    }
    base.update(over)
    return base


def test_pivot_media_divide_ogni_campo_numerico():
    out = _chiama("pivotMedia", [_pivot(), 4], richiede=["pivotMedia"])
    assert out["fatturato_netto"] == 4.0
    assert out["mol"] == 8192.0
    assert out["costi_personale"] == 4096.0


def test_pivot_media_divide_anche_anno_e_mese():
    """FOTOGRAFIA: `anno` e `mese` sono numeri, quindi vengono divisi anche loro.

    Non e' un bug visibile — il chiamante usa `pivotMedia` solo sulla riga
    `totali`, che non mostra anno/mese. Ma se qualcuno la riusasse su un mese
    singolo si troverebbe l'anno 506. Documentato, non corretto.
    """
    out = _chiama("pivotMedia", [_pivot(), 4], richiede=["pivotMedia"])
    assert out["anno"] == 506.5
    assert out["mese"] == 1.5


def test_pivot_media_non_tocca_la_label():
    out = _chiama("pivotMedia", [_pivot(), 4], richiede=["pivotMedia"])
    assert out["label"] == "Giu 2026"


def test_pivot_media_nmesi_zero_non_da_infinito():
    """Senza `Math.max(1, nMesi)` ogni campo diventerebbe `Infinity`, che in
    JSON non esiste: la pagina mostrerebbe "NaN €" ovunque."""
    out = _chiama("pivotMedia", [_pivot(), 0], richiede=["pivotMedia"])
    assert out["fatturato_netto"] == 16.0
    assert out["mol"] == 32768.0


def test_pivot_media_nmesi_negativo_non_inverte_i_segni():
    out = _chiama("pivotMedia", [_pivot(), -5], richiede=["pivotMedia"])
    assert out["mol"] == 32768.0


def test_pivot_media_non_muta_l_input():
    """`{...p}` e' una copia: senza lo spread, la pivot dei totali verrebbe
    divisa **in place** e passando da Totale a Media e ritorno i numeri
    scenderebbero a ogni giro."""
    res = esegui_ts(
        _MODULO,
        """
        const p = input;
        const out = m.pivotMedia(p, 4);
        emit({ originale: p.mol, copia: out.mol });
        """,
        argomento=_pivot(),
        richiede=["pivotMedia"],
    )
    assert res["originale"] == 32768.0, "l'input e' stato mutato"
    assert res["copia"] == 8192.0


def test_pivot_media_coerenza_mol():
    """La media resta un'identita' contabile: media(MOL) = media(margine) − media(costi).

    E' la ragione dichiarata nel commento del codice per dividere per un
    divisore unico invece che per i mesi attivi di ogni singola riga.
    """
    p = _pivot(primo_margine=1000.0, costi_personale=250.0, costi_spese_totali=150.0,
               mol=600.0)
    out = _chiama("pivotMedia", [p, 5], richiede=["pivotMedia"])
    assert out["primo_margine"] - (out["costi_spese_totali"] + out["costi_personale"]) == out["mol"]


# ──────────────────────────── pctIncidenza (fase D) ────────────────────────

@pytest.mark.parametrize("raw,netto,atteso", [
    (25.0, 100.0, "25%"),
    (100.0, 100.0, "100%"),
    (-25.0, 100.0, "-25%"),
    (1.0, 3.0, "33%"),
    (2.0, 3.0, "67%"),
])
def test_pct_incidenza_calcola(raw, netto, atteso):
    assert _chiama("pctIncidenza", [raw, netto], richiede=["pctIncidenza"]) == atteso


@pytest.mark.parametrize("raw,netto", [(50.0, 0.0), (0.0, 100.0), (0.0, 0.0)])
def test_pct_incidenza_null_sui_casi_degeneri(raw, netto):
    """Senza la guardia su `netto` uscirebbe "Infinity%" nella cella."""
    assert _chiama("pctIncidenza", [raw, netto], richiede=["pctIncidenza"]) is None


def test_pct_incidenza_netto_negativo_non_e_degenere():
    """Un fatturato netto negativo e' anomalo ma non e' "nessun dato": la
    guardia `!netto` intercetta 0/NaN, non i negativi."""
    assert _chiama("pctIncidenza", [50.0, -100.0], richiede=["pctIncidenza"]) == "-50%"


# ──────────────────────── rowVal + DERIVE (fase D) ─────────────────────────

def test_row_val_legge_il_campo_semplice():
    got = _chiama("rowVal", [{"key": "mol"}, _pivot()], richiede=["rowVal"])
    assert got == 32768.0


def test_row_val_campo_assente_torna_zero_non_undefined():
    got = _chiama("rowVal", [{"key": "campo_inesistente"}, _pivot()], richiede=["rowVal"])
    assert got == 0


def test_derive_fb_somma_la_quota_di_riparto():
    """LA QUOTA DI RIPARTO PERSA. Se la `derive` sparisce, `rowVal` cade sul
    campo grezzo `costi_fb_auto` (32) e la quota ripartita (65536) non compare:
    il costo mostrato crolla e il MOL sembra molto piu' alto del vero.
    E' lo stesso difetto gia' trovato lato worker nel ciclo 07.
    """
    res = esegui_ts(
        _MODULO,
        """
        const row = { key: "costi_fb_auto", derive: m.DERIVE.costi_fb_auto };
        emit({ con: m.rowVal(row, input), senza: m.rowVal({ key: "costi_fb_auto" }, input) });
        """,
        argomento=_pivot(),
        richiede=["rowVal"],
    )
    assert res["con"] == 32.0 + 65536.0
    assert res["senza"] == 32.0
    assert res["con"] != res["senza"], "senza derive la quota di riparto sparisce"


def test_derive_spese_somma_la_quota_di_riparto():
    res = esegui_ts(
        _MODULO,
        'emit(m.rowVal({ key: "costi_spese_auto", derive: m.DERIVE.costi_spese_auto }, input));',
        argomento=_pivot(),
        richiede=["rowVal"],
    )
    assert res == 512.0 + 131072.0


def test_derive_totale_costi_somma_spese_e_personale():
    res = esegui_ts(
        _MODULO,
        'emit(m.rowVal({ key: "totale_costi", derive: m.DERIVE.totale_costi }, input));',
        argomento=_pivot(),
        richiede=["rowVal"],
    )
    assert res == 2048.0 + 16384.0


@pytest.mark.parametrize("chiave,campo_quota", [
    ("costi_fb_auto", "quote_riparto_fb"),
    ("costi_spese_auto", "quote_riparto_spese"),
])
@pytest.mark.parametrize("assente", [False, True])
def test_derive_quota_mancante_non_produce_nan(chiave, campo_quota, assente):
    """`?? 0`: il worker puo' non mandare le quote su un mese senza riparti.
    Senza il coalesce la cella mostrerebbe "NaN €".

    **Due casi, e servono entrambi.** Con `quote_riparto_fb: null` togliere il
    `?? 0` non cambia niente — in JavaScript `32 + null === 32`, quindi il
    mutante e' equivalente e sopravvive (misurato: e' successo). Il caso che il
    coalesce protegge davvero e' il **campo assente**: `32 + undefined` fa
    `NaN`, e da li' in poi ogni totale della colonna diventa "NaN €".
    Un worker che omette la chiave invece di mandarla a `null` e' lo scenario
    realistico: `?? 0` esiste per quello.
    """
    valori = dict(_pivot())
    if assente:
        del valori[campo_quota]
    else:
        valori[campo_quota] = None

    res = esegui_ts(
        _MODULO,
        f'''
        const got = m.rowVal({{ key: {chiave!r}, derive: m.DERIVE.{chiave} }}, input);
        emit({{ val: got, isNaN: Number.isNaN(got) }});
        ''',
        argomento=valori,
        richiede=["rowVal"],
    )
    assert not res["isNaN"], (
        f"quota {campo_quota} "
        f"{'assente' if assente else 'null'} produce NaN: la colonna mostra 'NaN €'"
    )
    assert res["val"] == valori[chiave]


def test_le_tre_derive_esistono_tutte():
    """Se una `derive` viene rinominata nel .tsx senza aggiornare il modulo,
    `ROWS` prende `undefined` e la riga silenziosamente perde il calcolo."""
    res = esegui_ts(
        _MODULO,
        'emit(Object.keys(m.DERIVE).sort());',
        richiede=["rowVal"],
    )
    assert res == ["costi_fb_auto", "costi_spese_auto", "totale_costi"]


# ──────────────────────── buildMesiList (fase E) ───────────────────────────

def test_build_mesi_list_dentro_un_anno():
    got = _chiama("buildMesiList", ["2026-03-01", "2026-06-30"], richiede=["buildMesiList"])
    assert [(g["anno"], g["mese"]) for g in got] == [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]


def test_build_mesi_list_a_cavallo_di_capodanno():
    got = _chiama("buildMesiList", ["2025-11-01", "2026-02-28"], richiede=["buildMesiList"])
    assert [(g["anno"], g["mese"]) for g in got] == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2),
    ]


def test_build_mesi_list_anno_intero_di_mezzo():
    got = _chiama("buildMesiList", ["2024-12-01", "2026-01-31"], richiede=["buildMesiList"])
    assert len(got) == 14
    assert (got[0]["anno"], got[0]["mese"]) == (2024, 12)
    assert (got[-1]["anno"], got[-1]["mese"]) == (2026, 1)
    assert [g["mese"] for g in got[1:13]] == list(range(1, 13))


def test_build_mesi_list_un_solo_mese():
    got = _chiama("buildMesiList", ["2026-07-01", "2026-07-31"], richiede=["buildMesiList"])
    assert len(got) == 1
    assert got[0]["label"] == "Lug 2026"


def test_build_mesi_list_range_invertito_e_vuoto():
    """Un URL con le date scambiate non deve produrre una griglia infinita."""
    got = _chiama("buildMesiList", ["2026-06-30", "2026-03-01"], richiede=["buildMesiList"])
    assert got == []


def test_build_mesi_list_range_invertito_nello_stesso_anno():
    got = _chiama("buildMesiList", ["2026-08-01", "2026-02-01"], richiede=["buildMesiList"])
    assert got == []


def test_build_mesi_list_label_usa_i_nomi_corti():
    got = _chiama("buildMesiList", ["2026-01-01", "2026-12-31"], richiede=["buildMesiList"])
    assert [g["label"] for g in got] == [
        "Gen 2026", "Feb 2026", "Mar 2026", "Apr 2026", "Mag 2026", "Giu 2026",
        "Lug 2026", "Ago 2026", "Set 2026", "Ott 2026", "Nov 2026", "Dic 2026",
    ]


def test_build_mesi_list_ignora_il_giorno():
    """Il periodo e' mensile: 15/03 e 01/03 devono dare la stessa lista."""
    a = _chiama("buildMesiList", ["2026-03-15", "2026-05-02"], richiede=["buildMesiList"])
    b = _chiama("buildMesiList", ["2026-03-01", "2026-05-31"], richiede=["buildMesiList"])
    assert a == b


@pytest.mark.parametrize("tz", ["Europe/Rome", "Pacific/Midway", "Pacific/Kiritimati"])
def test_build_mesi_list_non_dipende_dal_fuso(tz):
    """Lavora su `parseInt` di stringhe, non su `Date`: nessun fuso la sposta.

    Il confronto e' fra due esecuzioni della stessa grandezza assoluta (un range
    di date esplicito), non fra "oggi" in due fusi diversi.
    """
    got = esegui_ts(
        _MODULO,
        'emit(m.buildMesiList("2025-12-01", "2026-01-31"));',
        tz=tz,
        richiede=["buildMesiList"],
    )
    assert [(g["anno"], g["mese"]) for g in got] == [(2025, 12), (2026, 1)]


def test_build_mesi_list_e_la_stessa_dei_due_componenti():
    """Era duplicata identica in analisi-tab.tsx e carica-ricavi-dialog.tsx.

    Ora la importano entrambi: se qualcuno ne reintroduce una copia locale,
    questo test non se ne accorge — ma il grep in
    `test_documentazione_onesta.py` si'. Qui verifichiamo almeno che l'import
    ci sia in entrambi.
    """
    import pathlib
    base = pathlib.Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)/margini"
    for nome in ["analisi-tab.tsx", "carica-ricavi-dialog.tsx"]:
        testo = (base / nome).read_text(encoding="utf-8")
        assert "buildMesiList } from \"@/lib/margini-aggregati\"" in testo, (
            f"{nome} non importa piu' buildMesiList dal modulo condiviso: "
            "se e' tornata una copia locale, le due divergeranno."
        )
        assert "function buildMesiList" not in testo, (
            f"{nome} ha di nuovo una copia locale di buildMesiList"
        )
