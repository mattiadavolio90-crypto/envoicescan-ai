"""Prima di unificare 12 formattatori duplicati: quali danno davvero lo stesso output?

`catena/` ridefinisce `euro`, `euro2`, `num`, `pct` in **5 file** e `MESI` in
**4** (misurato il 03/09/2026: il residuo diceva 4 file, sono 5). Unificarli
sembra una pulizia a costo zero. **Non lo è**: due di queste funzioni producono
stringhe diverse, e la stringa è ciò che il cliente legge.

Questo file misura la differenza **prima** della sostituzione, byte per byte, e
divide le copie in due gruppi:

- **sostituibili** — output identico su tutti i casi limite: si unificano;
- **divergenti** — output diverso: NON si toccano senza una decisione dell'owner,
  perché unificarle cambia cosa appare a schermo.

Metodo: le implementazioni sono ricostruite qui **verbatim** dai .tsx e
confrontate fra loro con `===` su stringa. Non si confrontano numeri: `1.234,56`
e `1234,56` sono lo stesso numero e due schermate diverse.
"""
import json
import pathlib
import re

import pytest

from tests.helpers_ts import esegui_ts

# Serve un modulo-contenitore per far girare le espressioni. `lib/format` va
# bene: e' senza side-effect e `richiede` accetta solo **funzioni** (il prologo
# di helpers_ts controlla `typeof === "function"`), quindi un modulo di soli
# array come `lib/mesi` non e' usabile come host. `MESI_LUNGHI` si legge con un
# import esplicito dentro l'espressione.
MODULO = "lib/format"
RICHIEDE = ["formatEuro"]

# ─── Le implementazioni, copiate verbatim dai sorgenti ──────────────────────

_EURO_INTL = """(n) => new Intl.NumberFormat("it-IT", {
  style: "currency", currency: "EUR", maximumFractionDigits: 0,
}).format(n)"""

_EURO_INTL_NULL = """(n) => {
  if (n == null) return "\\u2014";
  return new Intl.NumberFormat("it-IT", {
    style: "currency", currency: "EUR", maximumFractionDigits: 0,
  }).format(n);
}"""

# gruppo-tag-section.tsx:49
_EURO2_INTL = """(n) => {
  if (n == null) return "\\u2014";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 }).format(n);
}"""

# finestra-margini-coperti.tsx:320
_EURO2_TOFIXED = """(n) => {
  if (n == null) return "\\u2014";
  return `${n.toFixed(2).replace(".", ",")} \\u20ac`;
}"""

# gruppo-tag-section.tsx:53
_NUM_1DEC = """(n) => n.toLocaleString("it-IT", { maximumFractionDigits: 1 })"""
# finestra-margini-coperti.tsx:52
_NUM_DEFAULT = """(n) => {
  if (n == null) return "\\u2014";
  return n.toLocaleString("it-IT");
}"""

_PCT_SEMPLICE = """(n) => `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`"""
_PCT_NULL = """(n) => {
  if (n == null) return "\\u2014";
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}"""

# I casi limite che un formattatore di valuta incontra davvero.
_CASI = [0, 1, -1, 0.5, -0.5, 1234.56, -1234.56, 1234567.89,
         0.004, 0.005, 999.999, 1000, 1e6, 0.01, -0.01]


def _confronta(impl_a: str, impl_b: str, casi=None, con_null=True):
    """Ritorna la lista dei casi in cui le due implementazioni divergono.

    Il confronto e' su **stringa** (`!==`), non su numero: `1.234,56` e
    `1234,56` sono lo stesso numero e due schermate diverse.
    """
    lista = json.dumps(_CASI if casi is None else casi)
    if con_null:
        lista += ".concat([null])"
    return esegui_ts(
        MODULO,
        f"""
        const a = {impl_a};
        const b = {impl_b};
        const casi = {lista};
        const diff = [];
        for (const c of casi) {{
          let ra, rb;
          try {{ ra = a(c); }} catch (e) {{ ra = "THROW:" + e.constructor.name; }}
          try {{ rb = b(c); }} catch (e) {{ rb = "THROW:" + e.constructor.name; }}
          if (ra !== rb) diff.push({{ caso: c, a: ra, b: rb }});
        }}
        emit(diff);
        """,
        richiede=RICHIEDE,
    )


# ─── Gruppo 1: sostituibili ─────────────────────────────────────────────────

def test_le_quattro_copie_di_mesi_sono_identiche_a_mesi_lunghi():
    """La sostituzione a rischio zero: 4 array, stesse 12 stringhe."""
    copia = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    got = esegui_ts(
        MODULO,
        'const { MESI_LUNGHI } = await import("@/lib/mesi"); emit(MESI_LUNGHI);',
        richiede=RICHIEDE,
    )
    assert list(got) == copia, (
        "MESI_LUNGHI non coincide piu' con le copie locali di catena/: "
        "sostituirle cambierebbe le etichette a schermo"
    )


def test_euro_di_catena_e_formatEuro_della_lib_sono_identici():
    """La sostituzione che chiude 4 copie su una fonte che esiste gia'.

    `euro()` di catena usa `new Intl.NumberFormat(...).format(n)`, `formatEuro()`
    di `lib/format.ts` usa `n.toLocaleString(...)` con gli stessi option: due
    strade diverse per la stessa stringa. Verificato byte per byte prima di
    sostituire — non dedotto dalla somiglianza del codice.
    """
    diff = _confronta(_EURO_INTL, "(n) => m.formatEuro(n)", con_null=False)
    assert diff == [], (
        f"`euro()` di catena e `formatEuro()` di lib/format divergono: {diff}. "
        "La sostituzione cambierebbe cosa vede il cliente."
    )


def test_euro_con_e_senza_guardia_null_coincidono_sui_numeri():
    """Le due `euro` differiscono solo sul `null`: su ogni numero sono uguali.

    Unificare sulla versione con la guardia e' un **superset**: nessun output
    cambia, e in piu' un null smette di diventare "0 €".
    """
    diff = _confronta(_EURO_INTL, _EURO_INTL_NULL, con_null=False)
    assert diff == [], f"le due implementazioni di `euro` divergono: {diff}"


def test_fotografa_formatPct_NON_e_sostituibile_alle_pct_di_catena():
    """La sostituzione che il test ha **impedito**.

    Sembravano la stessa cosa e non lo sono: `formatPct` di `lib/format.ts` usa
    `toFixed(1)`, le `pct` di catena usano `toLocaleString("it-IT")`. Divergono
    su **tutti** i casi provati, in tre modi diversi:

        0      -> "0%"     (catena)  vs  "0.0%"   (lib)   decimale forzato
        12.34  -> "12,3%"            vs  "12.3%"          virgola vs punto
        12.35  -> "12,4%"            vs  "12.3%"          arrotondamento diverso

    Il punto decimale al posto della virgola su una percentuale italiana e' un
    difetto visibile. `pct` resta duplicata in catena finche' qualcuno non
    decide **quale** delle due forme e' quella giusta: non e' una pulizia, e'
    un cambio di output.

    Se questo test diventa verde le due implementazioni sono state allineate:
    allora `pct` diventa sostituibile e la roadmap va aggiornata.
    """
    diff = _confronta(
        '(n) => `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`',
        "(n) => m.formatPct(n)",
        casi=[0, 1, 12.34, 12.35, -5.55, 100],
        con_null=False,
    )
    assert len(diff) == 6, (
        f"formatPct e le pct di catena non divergono piu' su tutti i casi: {diff}"
    )


def test_pct_con_e_senza_guardia_null_coincidono_sui_numeri():
    diff = _confronta(_PCT_SEMPLICE, _PCT_NULL, con_null=False)
    assert diff == [], f"le due implementazioni di `pct` divergono: {diff}"


def test_su_null_la_versione_senza_guardia_non_e_sostituibile_ma_migliora():
    """La sola differenza, ed e' un miglioramento: `null` -> "—" invece di
    "0 €" o di un crash. Dichiarata, non nascosta."""
    diff = _confronta(_EURO_INTL, _EURO_INTL_NULL, casi=[], con_null=True)
    assert len(diff) == 1, f"atteso un solo caso divergente (null), trovati: {diff}"
    assert diff[0]["b"] == "—", diff


# ─── Gruppo 2: divergenti — NON si unificano ────────────────────────────────

def test_fotografa_le_due_euro2_divergono_davvero():
    """LA ragione per cui R4 non è un refactor meccanico.

    `gruppo-tag-section` usa `Intl` (separatore delle migliaia + spazio stretto
    U+202F prima di €); `finestra-margini-coperti` usa
    `toFixed(2).replace(".", ",")` (nessun separatore, spazio normale).
    Unificarle **cambia cosa il cliente vede**: e' una decisione dell'owner, non
    una pulizia. Le due `euro2` omonime sono gia' fra le «8 anomalie fotografate
    di proposito» dell'1/9.

    Se questo test diventa verde le due implementazioni sono state allineate:
    aggiorna la roadmap, non il test.
    """
    diff = _confronta(_EURO2_INTL, _EURO2_TOFIXED, con_null=True)
    assert diff != [], "le due `euro2` ora coincidono: la divergenza e' stata risolta"
    casi_diversi = {d["caso"] for d in diff}
    assert 1234.56 in casi_diversi, (
        f"1234.56 non diverge piu' fra le due euro2: {diff}"
    )


@pytest.mark.parametrize("valore", [0, 1, 1234.56, 12345.6, 1234567.89, -1234.56])
def test_le_due_euro2_differiscono_sempre_sullo_spazio(valore):
    """**Su OGNI valore**, non solo sui grandi: `Intl` mette uno spazio unificatore
    (U+00A0) prima di €, `toFixed` uno spazio normale.

    Misurato il 03/09: e' la differenza che rende `euro2` non sostituibile in
    modo meccanico. Invisibile a occhio, diversa byte per byte — e byte per byte
    e' come si confrontano due schermate.
    """
    r = esegui_ts(
        MODULO,
        f"emit({{ intl: ({_EURO2_INTL})({valore}), tofixed: ({_EURO2_TOFIXED})({valore}) }});",
        richiede=RICHIEDE,
    )
    assert r["intl"] != r["tofixed"], f"le due euro2 coincidono su {valore}: {r}"
    assert "\xa0\u20ac" in r["intl"], f"la versione Intl non usa lo spazio unificatore: {r!r}"
    assert " \u20ac" in r["tofixed"], f"la versione toFixed non usa lo spazio normale: {r!r}"


@pytest.mark.parametrize("valore,con_separatore", [
    (1234.56, False),      # 4 cifre: l'italiano NON separa
    (12345.6, True),       # 5 cifre: separa
    (1234567.89, True),
])
def test_il_separatore_delle_migliaia_compare_solo_da_cinque_cifre(valore, con_separatore):
    """La seconda meta' della divergenza, e la meno ovvia.

    Correggo una mia affermazione precedente: `Intl` **non** separa le migliaia a
    1.234,56 — la locale italiana omette il separatore sui numeri di 4 cifre.
    Compare da 10.000 in su. Chi decide se unificare deve sapere che la
    differenza cambia forma a seconda dell'importo.
    """
    r = esegui_ts(
        MODULO,
        f"emit({{ intl: ({_EURO2_INTL})({valore}), tofixed: ({_EURO2_TOFIXED})({valore}) }});",
        richiede=RICHIEDE,
    )
    assert ("." in r["intl"]) is con_separatore, (
        f"il separatore delle migliaia su {valore} non e' come misurato: {r!r}"
    )
    assert "." not in r["tofixed"], f"la versione toFixed separa le migliaia: {r!r}"


def test_fotografa_le_due_num_divergono_sui_decimali():
    """`num` con `maximumFractionDigits: 1` tronca, l'altra no: 1234.567
    diventa "1.234,6" oppure "1.234,567"."""
    diff = _confronta(_NUM_1DEC, _NUM_DEFAULT, casi=[1234.567, 0.25, 99.999], con_null=False)
    assert diff != [], "le due `num` ora coincidono: aggiorna la roadmap"


# ─── Che la sostituzione sia davvero avvenuta ───────────────────────────────

_CATENA = pathlib.Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)/catena"

# I 5 file che avevano una copia locale. Se una copia torna, il test di
# equivalenza qui sopra resterebbe verde: prova che le due implementazioni
# coincidono, non che il codice usi quella condivisa. (Trovato dal
# code-reviewer il 3/9; il gemello `test_iva_divisori_fonte_unica.py` questa
# verifica ce l'aveva.)
_MIGRATI = [
    "finestra-spesa-pv.tsx", "gruppo-tag-section.tsx",
    "finestra-costi-gruppo.tsx", "sintesi-catena.tsx",
]


@pytest.mark.parametrize("nome", _MIGRATI)
def test_i_file_migrati_non_ridefiniscono_euro(nome):
    testo = (_CATENA / nome).read_text(encoding="utf-8")
    assert not re.search(r"^function euro\(n: number\)", testo, re.M), (
        f"{nome} ha di nuovo una copia locale di `euro()`: usa "
        '`import {{ formatEuro as euro }} from "@/lib/format"`'
    )
    assert 'from "@/lib/format"' in testo, (
        f"{nome} non importa piu' da @/lib/format: la fonte unica e' stata persa"
    )


@pytest.mark.parametrize("nome", _MIGRATI + ["finestra-margini-coperti.tsx"])
def test_i_file_migrati_non_ridefiniscono_mesi(nome):
    testo = (_CATENA / nome).read_text(encoding="utf-8")
    assert not re.search(r"^const MESI(_LABEL)? = \[", testo, re.M), (
        f"{nome} ha di nuovo una copia locale dei nomi dei mesi: usa "
        '`import {{ MESI_LUNGHI }} from "@/lib/mesi"`'
    )
