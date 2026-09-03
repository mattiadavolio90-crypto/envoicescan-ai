"""I formattatori duplicati di `catena/`: quali erano davvero uguali, e come sono finiti.

`catena/` ridefiniva `euro`, `euro2`, `num`, `pct` in **5 file** e `MESI` in
**4** (misurato il 03/09/2026: il residuo diceva 4 file, sono 5). Unificarli
sembrava una pulizia a costo zero. **Non lo era**: alcune producevano stringhe
diverse, e la stringa è ciò che il cliente legge.

Il test di equivalenza è arrivato **prima** della sostituzione e ha diviso le
copie in due gruppi. Ha impedito un difetto vero: `formatPct` di `lib/format.ts`
sembrava intercambiabile con le `pct` di catena e avrebbe messo **il punto
decimale in ogni percentuale italiana** (`12.3%` invece di `12,3%`).

**Cosa è stato unificato, e quando:**

| Copie | Esito |
|---|---|
| 4 × `MESI`/`MESI_LABEL` | → `MESI_LUNGHI` (byte-identiche) |
| 4 × `euro` | → `formatEuro` (output identico, verificato) |
| 2 × `euro2` | → `formatEuro(n, 2)` — **decisione owner 3/9**: vince la forma col separatore delle migliaia (`12.345,60 €`) |
| 2 × `num` | → 1 decimale — **decisione owner 3/9**: i coperti sono conteggi |
| 3 × `pct` | **restano duplicate**: `formatPct` non è sostituibile (vedi sopra) |

**Due modi di provare, e servono entrambi.** I test che *ricostruiscono*
un'implementazione e la eseguono provano che quella forma si comporta bene, non
che il file la usi: rimettere `n.toLocaleString("it-IT")` senza opzioni li
lasciava verdi (mutante sopravvissuto, 3/9). Per questo ogni decisione ha anche
un test che legge il **sorgente vero**.

Metodo del confronto: `===` su stringa, mai su numero — `1.234,56` e `1234,56`
sono lo stesso numero e due schermate diverse.
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


def test_formatPct_ora_coincide_con_le_pct_di_catena():
    """La divergenza che ha tenuto `pct` duplicata per tre mesi, ora chiusa.

    Fino al 3/9 `formatPct` usava `toFixed(1)` e divergeva su **tutti** i casi:

        0      -> "0%"     (catena)  vs  "0.0%"   (lib)   decimale forzato
        12.34  -> "12,3%"            vs  "12.3%"          virgola vs punto
        12.35  -> "12,4%"            vs  "12.3%"          troncava invece di arrotondare

    Il punto decimale inglese su una percentuale italiana e' un difetto
    visibile: la forma giusta era quella di catena. Misurato il 3/9 che
    `formatPct` **non aveva piu' nessun chiamante** (solo la definizione e un
    re-export in `margini/periodi.ts`), allinearla non ha cambiato nessuna
    schermata — ha solo reso sostituibili le 3 copie.

    Se questo test torna rosso qualcuno ha rimesso `toFixed` o cambiato le
    opzioni di `toLocaleString`: le percentuali di catena cambiano forma.
    """
    diff = _confronta(
        '(n) => `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`',
        "(n) => m.formatPct(n)",
        casi=[0, 1, 12.34, 12.35, -5.55, 100, 1234.5, 33.333],
        con_null=False,
    )
    assert diff == [], f"formatPct e le pct di catena divergono di nuovo: {diff}"


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

def test_le_due_euro2_sono_state_unificate_col_separatore():
    """La divergenza è stata **risolta** il 3/9, non più fotografata.

    Decisione dell'owner: vince la forma con il separatore delle migliaia
    (`12.345,60 €`). Entrambe le copie ora chiamano `formatEuro(n, 2)`.

    Prima: `gruppo-tag-section` usava `Intl` (separatore da 5 cifre),
    `finestra-margini-coperti` usava `toFixed(2).replace(".", ",")` — mai il
    separatore, e uno spazio normale invece di U+00A0.
    """
    diff = _confronta(_EURO2_INTL, "(n) => m.formatEuro(n, 2)", con_null=False)
    assert diff == [], f"`formatEuro(n, 2)` non produce più la forma scelta: {diff}"


@pytest.mark.parametrize("valore,atteso", [
    (12345.6, "12.345,60"),        # il separatore che l'owner ha scelto
    (1234567.89, "1.234.567,89"),
    (1234.56, "1234,56"),          # sotto le 5 cifre l'italiano non separa
    (2.5, "2,50"),
])
def test_euro2_mostra_il_separatore_delle_migliaia(valore, atteso):
    """La forma esatta, per non doverla ri-dedurre fra sei mesi."""
    r = esegui_ts(MODULO, f"emit(m.formatEuro({valore}, 2));", richiede=RICHIEDE)
    assert r.startswith(atteso), f"atteso «{atteso} €», ottenuto {r!r}"


def test_num_arrotonda_a_un_decimale():
    """Seconda metà della decisione del 3/9.

    I coperti sono conteggi: `finestra-margini-coperti` ne mostrava fino a 3
    decimali (`1234,567`), ora 1 (`1234,6`). Allineata a `gruppo-tag-section`,
    che già arrotondava.
    """
    espr = (
        'const num = (n) => n == null ? "\\u2014"'
        '  : n.toLocaleString("it-IT", { maximumFractionDigits: 1 });'
        "emit([1234.567, 0.005, 99.999, 12345.6].map(num));"
    )
    assert esegui_ts(MODULO, espr, richiede=RICHIEDE) == [
        "1234,6", "0", "100", "12.345,6",
    ]


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


@pytest.mark.parametrize("nome", ["gruppo-tag-section.tsx", "finestra-margini-coperti.tsx"])
def test_le_due_euro2_chiamano_la_fonte_unica(nome):
    """Che la decisione del 3/9 non venga disfatta in silenzio.

    Il test sopra prova che `formatEuro(n, 2)` dà la forma giusta; questo prova
    che i due file la **usano**. Senza, reintrodurre `toFixed(2).replace(...)`
    lascerebbe la suite verde.
    """
    testo = (_CATENA / nome).read_text(encoding="utf-8")
    assert "formatEuro(n, 2)" in testo, (
        f"{nome} non chiama piu' `formatEuro(n, 2)`: la forma con il separatore "
        "delle migliaia decisa il 3/9 e' stata persa"
    )
    assert 'toFixed(2).replace(".", ",")' not in testo, (
        f"{nome} e' tornato a `toFixed(2).replace(...)`: e' la forma SENZA "
        "separatore delle migliaia, scartata il 3/9"
    )


def test_num_nel_sorgente_arrotonda_a_un_decimale():
    """Il gemello del test sopra per `num`, e serve davvero.

    `test_num_arrotonda_a_un_decimale` **ricostruisce** l'implementazione e la
    esegue: prova che quella forma arrotonda, non che il file la usi. Con solo
    quello, rimettere `n.toLocaleString("it-IT")` senza opzioni lasciava la
    suite verde — mutante sopravvissuto, misurato il 3/9.
    """
    for nome in ("finestra-margini-coperti.tsx", "gruppo-tag-section.tsx"):
        testo = (_CATENA / nome).read_text(encoding="utf-8")
        corpo = re.search(r"function num\([^)]*\): string \{(.*?)\n\}", testo, re.S)
        assert corpo, f"{nome}: `num` non c'e' piu'"
        assert "maximumFractionDigits: 1" in corpo.group(1), (
            f"{nome}: `num` non arrotonda piu' a 1 decimale. I coperti sono "
            "conteggi: senza l'opzione tornano fino a 3 cifre decimali "
            "(decisione owner 3/9)"
        )


_CON_PCT = ["sintesi-catena.tsx", "finestra-margini-coperti.tsx", "gruppo-tag-section.tsx"]


@pytest.mark.parametrize("nome", _CON_PCT)
def test_le_tre_pct_chiamano_la_fonte_unica(nome):
    """L'ultima duplicazione di catena, chiusa il 3/9.

    Le 3 `pct` restano come **wrapper** — una e' passata per riferimento nella
    tabella `COLS` (`fmt: pct`), le altre due tengono la guardia sul null — ma
    la forma della stringa ora viene da un posto solo. Il test legge il corpo
    della funzione: una copia rimessa dentro il wrapper lo fa fallire, mentre
    un assert sul solo `import` non la vedrebbe.
    """
    testo = (_CATENA / nome).read_text(encoding="utf-8")
    corpo = re.search(r"function pct\([^)]*\): string \{(.*?)\n\}", testo, re.S)
    assert corpo, f"{nome}: `pct` non c'e' piu'"
    assert "formatPct(" in corpo.group(1), (
        f"{nome}: `pct` non chiama piu' `formatPct`. La forma italiana della "
        "percentuale e' tornata a essere riscritta a mano"
    )
    assert "toLocaleString" not in corpo.group(1), (
        f"{nome}: `pct` ha di nuovo una formattazione locale invece di "
        "delegare a `formatPct`"
    )


def test_formatPct_nel_sorgente_usa_la_virgola_italiana():
    """La correzione a monte, letta dal sorgente vero.

    `toFixed` scrive il punto decimale inglese (`12.3%`) e tronca invece di
    arrotondare. Le 3 copie di catena erano nate per evitarlo: se qualcuno lo
    rimette, le percentuali di tutta la plancia cambiano forma in silenzio.
    """
    testo = (_CATENA.parents[2] / "lib" / "format.ts").read_text(encoding="utf-8")
    vive = "\n".join(
        r for r in testo.splitlines() if not r.lstrip().startswith("//")
    )
    corpo = re.search(r"function formatPct\([^)]*\): string \{(.*?)\n\}", vive, re.S)
    assert corpo, "formatPct non c'e' piu' in lib/format.ts"
    assert "toLocaleString" in corpo.group(1) and 'it-IT' in corpo.group(1), (
        "formatPct non formatta piu' in it-IT: la virgola decimale e' persa"
    )
    assert "toFixed" not in corpo.group(1), (
        "formatPct e' tornata a `toFixed`: punto inglese e troncamento, "
        "la divergenza chiusa il 3/9"
    )
