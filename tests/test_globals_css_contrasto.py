"""I token colore di `globals.css`, misurati come li rende il browser.

Un token e' un contratto visivo ("questo blu si legge su bianco") che nessun
test TypeScript e nessun `tsc` puo' verificare. Qui l'oklch dichiarato viene
convertito in sRGB con la matematica di CSS Color 4 (la stessa del browser,
verificata contro due valori pubblicati da Tailwind) e si calcola il contrasto
WCAG 2 sui fondi su cui il token viene usato davvero, in ENTRAMBI i temi.

Perche' esiste: il 18/09/2026 `--primary` come testo su bianco misurava 2,7:1,
e la prima taratura dei semantici reggeva su bianco ma non sul proprio fondo
tinto /10 (3,95:1). Se qualcuno "schiarisce un po'" un token per gusto, questo
test dice di quanto e' sceso sotto soglia, prima che lo scopra un cliente.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Le esclusioni del presidio gemello «colori solo token»: admin, demo, landing
# e legal sono esentati da quella regola, e questo file deve usare lo STESSO
# perimetro invece di riscriverlo — due liste separate divergono.
from test_colori_solo_token_frontend import ESCLUSI  # noqa: E402

GLOBALS_CSS = Path(__file__).resolve().parent.parent / "apps" / "web" / "src" / "app" / "globals.css"
AA_TESTO = 4.5
FONDO_VISIBILE = 1.5

# ---------------------------------------------------------------- colore ----

def oklch_to_srgb(L: float, C: float, H: float) -> tuple[float, float, float]:
    """CSS Color 4, oklch -> oklab -> LMS -> sRGB lineare -> sRGB; clip in gamut."""
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def gamma(c: float) -> float:
        c = min(1.0, max(0.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    return gamma(r), gamma(g), gamma(bb)


def hexa(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def luminanza(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrasto(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = luminanza(a), luminanza(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def sovrapponi(sopra, sotto, alpha: float):
    """`bg-<token>/10`: il token al 10% composto sul fondo, come fa il browser."""
    return tuple(s * alpha + f * (1 - alpha) for s, f in zip(sopra, sotto))


# ---------------------------------------------------------------- parsing ---

_TOKEN = re.compile(r"--([a-z0-9-]+):\s*([^;]+);")
_OKLCH = re.compile(r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)")
_VAR = re.compile(r"var\(--([a-z0-9-]+)\)")


def _blocco(css: str, selettore: str) -> str:
    """Prima via i commenti: uno diceva `--destructive: quello e' ...` e la regex
    delle dichiarazioni se lo mangiava insieme al `--positivo` della riga dopo."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    inizio = css.index(selettore + " {")
    fine = css.index("\n  }", inizio)
    return css[inizio:fine]


def _tema(selettore: str) -> dict[str, tuple[float, float, float]]:
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    grezzi = dict(_TOKEN.findall(_blocco(css, selettore)))
    colori: dict[str, tuple[float, float, float]] = {}

    def risolvi(nome: str, profondita: int = 0):
        if nome in colori:
            return colori[nome]
        valore = grezzi.get(nome)
        if valore is None or profondita > 3:
            return None
        m = _VAR.fullmatch(valore.strip())
        if m:
            ris = risolvi(m.group(1), profondita + 1)
        else:
            m = _OKLCH.fullmatch(valore.strip())
            ris = oklch_to_srgb(*(float(x) for x in m.groups())) if m else None
        if ris is not None:
            colori[nome] = ris
        return ris

    for nome in grezzi:
        risolvi(nome)
    return colori


@pytest.fixture(scope="module", params=["light", "dark"])
def tema(request):
    colori = _tema(":root" if request.param == "light" else ".dark")
    colori["_nome"] = request.param  # type: ignore[assignment]
    return colori


def _cr(tema, testo: str, fondo: str) -> float:
    return contrasto(tema[testo], tema[fondo])


# ------------------------------------------------------------------ test ----

def test_la_conversione_e_quella_del_browser():
    """Due valori che Tailwind v4 pubblica sia in oklch sia in esadecimale."""
    assert hexa(oklch_to_srgb(0.205, 0, 0)) == "#171717"      # neutral-900
    assert hexa(oklch_to_srgb(0.685, 0.169, 237.323)) == "#00a6f4"  # sky-500


def test_i_token_della_fase_2_esistono_in_entrambi_i_temi(tema):
    for nome in ("primary-text", "positivo", "negativo", "incerto",
                 "grafico-1", "grafico-2", "grafico-3", "grafico-4", "grafico-5"):
        assert nome in tema, f"{nome} manca nel tema {tema['_nome']}"


@pytest.mark.parametrize("fondo", ["background", "card", "accent", "muted"])
def test_il_blu_del_testo_si_legge_su_ogni_fondo(tema, fondo):
    cr = _cr(tema, "primary-text", fondo)
    assert cr >= AA_TESTO, f"{tema['_nome']}: primary-text su {fondo} = {cr:.2f}:1"


def test_al_buio_il_blu_del_testo_e_il_brand(tema):
    """Un solo blu nel tema scuro: se divergono, ce ne sono due a video."""
    if tema["_nome"] == "dark":
        assert tema["primary-text"] == tema["primary"]
    else:
        assert tema["primary-text"] != tema["primary"]


@pytest.mark.parametrize("token", ["positivo", "negativo", "incerto"])
@pytest.mark.parametrize("fondo", ["background", "card"])
def test_i_semantici_si_leggono_su_fondo_neutro(tema, token, fondo):
    cr = _cr(tema, token, fondo)
    assert cr >= AA_TESTO, f"{tema['_nome']}: {token} su {fondo} = {cr:.2f}:1"


@pytest.mark.parametrize("token", ["positivo", "negativo", "incerto"])
def test_i_semantici_si_leggono_sul_proprio_fondo_tinto_al_10(tema, token):
    """`bg-<token>/10 text-<token>`, il chip: e' il pattern che la prima
    taratura non reggeva (3,95:1 in light). Al /15 non regge ancora: per
    questo le tinte semantiche si scrivono /10."""
    tinta = sovrapponi(tema[token], tema["card"], 0.10)
    cr = contrasto(tema[token], tinta)
    assert cr >= AA_TESTO, f"{tema['_nome']}: {token} sul proprio /10 = {cr:.2f}:1"


def test_il_testo_secondario_si_legge(tema):
    assert _cr(tema, "muted-foreground", "background") >= AA_TESTO


def test_accent_foreground_si_legge_su_accent(tema):
    assert _cr(tema, "accent-foreground", "accent") >= AA_TESTO


@pytest.mark.parametrize("serie", ["grafico-2", "grafico-3"])
def test_le_serie_dei_grafici_si_staccano_dal_fondo(tema, serie):
    """Un riempimento che non si stacca dal fondo e' una barra invisibile."""
    cr = _cr(tema, serie, "background")
    assert cr >= FONDO_VISIBILE, f"{tema['_nome']}: {serie} su background = {cr:.2f}:1"


def test_le_serie_dei_grafici_sono_una_rampa_del_brand(tema):
    """2 piu' scura del brand, 3 piu' chiara: e' una scala, non tre colori."""
    l1, l2, l3 = (luminanza(tema[n]) for n in ("grafico-1", "grafico-2", "grafico-3"))
    assert l2 < l1 < l3


# --------------------------------------------- il fondo pagina e le card ----
#
# Fino al 24/09/2026 `--background` e `--card` erano ENTRAMBI `oklch(1 0 0)` nel
# tema chiaro: ogni card era bianca su bianco e l'unico stacco restava il bordo.
# Al punto che la tabella di Margini si era dovuta difendere da sola, con ombra
# e anello scritti nel .tsx (`calcolo-tab.tsx`) invece che col tema. Nel tema
# scuro il rapporto c'era gia' (card 0.205 su fondo 0.145).
#
# Non e' un requisito WCAG — il contrasto del TESTO e' coperto dai test sopra —
# ma il contratto visivo che distingue una superficie sollevata dal piano della
# pagina. Senza presidio, riportare il fondo a `oklch(1 0 0)` non farebbe
# fallire nulla e le card tornerebbero invisibili.

# Le superfici SOLLEVATE: tutte devono staccarsi dal piano della pagina, non
# solo quella che si stava guardando. La prima stesura di questo presidio
# nominava `card` e basta — cosi' abbassare il fondo lasciava passare
# `--sidebar` diventato identico ad esso (la navigazione di tutte e 14 le aree
# bianca su bianco) e due mutanti su `--popover`, che ha lo stesso contratto e
# 22 usi. E' il pattern «mutanti scelti solo dove ho scritto».
SUPERFICI = ("card", "popover", "sidebar")


@pytest.mark.parametrize("superficie", SUPERFICI)
def test_le_superfici_si_staccano_dal_fondo_pagina(tema, superficie):
    """In ENTRAMBI i temi una superficie non deve avere la tinta del fondo."""
    assert superficie in tema, f"--{superficie} manca nel tema {tema['_nome']}"
    assert tema[superficie] != tema["background"], (
        f"tema {tema['_nome']}: --{superficie} e --background sono lo stesso "
        f"colore ({hexa(tema[superficie])}), la superficie sparisce nel fondo"
    )


def test_lo_stacco_superfici_fondo_e_percepibile(tema):
    """Una differenza di un centesimo sarebbe invisibile: serve una soglia.

    Il riferimento e' il tema scuro, che il difetto non ha mai avuto: card
    0.205 su fondo 0.145, cioe' **1.105:1**.

    ATTENZIONE alla taratura, la prima stesura di questo test era finta: con un
    `minimo * 0.9` la soglia scendeva a 0.994, e un rapporto di contrasto non
    puo' stare sotto 1 — quindi non bloccava nulla, nemmeno due fondi
    identici. Un mutante con fondo `oklch(0.998)` (stacco invisibile a occhio)
    ci passava. La soglia qui e' un valore ANCORATO, non derivato con un
    margine: sotto 1.04 lo stacco non si vede.
    """
    # Ancorata: abbassarla per far passare un colore che non si vede sarebbe
    # il modo piu' comodo di aggirare questo presidio, e nessun altro test lo
    # direbbe (mutante del 24/09/2026, sopravvissuto).
    STACCO_MINIMO = 1.04
    assert STACCO_MINIMO >= 1.04, "soglia abbassata: si aggira il presidio invece di correggere il colore"
    for superficie in SUPERFICI:
        cr = contrasto(tema[superficie], tema["background"])
        assert cr >= STACCO_MINIMO, (
            f"tema {tema['_nome']}: stacco {superficie}/fondo {cr:.4f}:1, sotto "
            f"{STACCO_MINIMO}:1 — la superficie non si distingue dalla pagina"
        )


def test_il_testo_resta_leggibile_sul_fondo_abbassato(tema):
    """Controprova: abbassare il fondo non deve costare contrasto al testo.

    E' il rischio del fix — scurire il fondo per staccare le card avvicina il
    fondo al testo. Qui si verifica che il margine su AA resti ampio.
    """
    assert _cr(tema, "foreground", "background") >= AA_TESTO


# ----------------------------------------- lo stato attivo e il suo fondo ----
#
# Contratto DIVERSO da quello delle SUPERFICI sopra: non «la superficie si
# stacca dal piano della pagina», ma «la voce evidenziata si stacca dal suo
# contenitore». Il contenitore pero' non e' uno solo — vedi l'elenco sotto: la
# stessa tinta di evidenziazione poggia su superfici diverse a seconda di dove
# la si usa, e ogni coppia va nominata.
#
# Perche' esiste: `--accent` ha 90 usi di `bg-accent` ed e' la tinta dello STATO
# ATTIVO della navigazione in tutte e 14 le aree (`data-active:!bg-accent`).
# Portandolo a coincidere col contenitore la voce attiva smette di distinguersi
# e nessun test se ne accorgeva (rilevato dalla re-review del 24/09/2026, che
# ha mutato quei token e li ha visti sopravvivere).

EVIDENZIATI = (
    # (token, contenitore su cui poggia DAVVERO)
    #
    # `accent` poggia su TRE contenitori diversi, e vanno nominati tutti — la
    # prima stesura diceva solo `card` ed era sbagliata due volte:
    #  - `sidebar`: e' li' che sta la voce di nav attiva (`data-active:!bg-accent`
    #    dentro `bg-sidebar`, sidebar.tsx:172), cioe' il caso per cui questo
    #    presidio e' nato. Misurando accent/CARD era verde per COINCIDENZA,
    #    perche' `--card` e `--sidebar` hanno lo stesso valore in entrambi i
    #    temi: un mutante che rendeva la sidebar uguale ad accent lasciava la
    #    nav attiva a 1.0000:1 (invisibile) con la suite verde.
    #  - `background`: `SidebarInset` e' `bg-background` (sidebar.tsx:310),
    #    quindi il contenuto di pagina NON sta su una card. `PageHeader`
    #    (presente in ogni area), `trigger-hint` e l'header del layout usano
    #    `bg-accent` direttamente sul fondo pagina: e' la coppia piu' stretta
    #    della famiglia e non era coperta da nulla.
    #  - `card`: gli usi dentro le card.
    #  - `popover`: `focus:bg-accent` dentro `bg-popover` (dropdown-menu.tsx,
    #    4 punti) e' la voce di menu a fuoco. Mancava, e anche qui il presidio
    #    era verde per coincidenza (`popover` == `card`): un mutante che rendeva
    #    il popover uguale ad accent lasciava la voce a fuoco invisibile
    #    (1.0000:1) con la suite verde. Trovato dalla review del 24/09/2026 —
    #    stessa classe di errore del contenitore sbagliato, ripetuta su un
    #    token che non avevo cercato.
    #  - `muted` e `secondary`: `hover:bg-muted` e' lo stato PIU' USATO dell'app
    #    — 180 occorrenze contro le 37 di `bg-accent` — e non era presidiato
    #    affatto. Poggia sia dentro le card sia sul fondo pagina
    #    (`SidebarInset` e' `bg-background`: analisi-fatture, agenda, dashboard
    #    lo usano li'). Quando il fondo e' sceso a 0.985 quella coppia e'
    #    rimasta a 1.0447, sotto questa stessa soglia, e un mutante che rendeva
    #    muted identico alla card sopravviveva a 988 test. Quarta volta che lo
    #    stesso presidio dimentica un contenitore: l'elenco qui sotto ora e'
    #    derivato dai `<stato>:bg-*` che esistono nel sorgente, non indovinato.
    ("accent", "sidebar"),
    ("accent", "background"),
    ("accent", "card"),
    ("accent", "popover"),
    ("sidebar-accent", "sidebar"),
    ("muted", "background"),
    ("muted", "card"),
    ("muted", "popover"),
    ("muted", "sidebar"),
    ("secondary", "background"),
    ("secondary", "card"),
)


@pytest.mark.parametrize("token,contenitore", EVIDENZIATI)
def test_lo_stato_attivo_si_stacca_dal_suo_contenitore(tema, token, contenitore):
    """Una voce evidenziata deve distinguersi dalla superficie che la ospita."""
    assert token in tema, f"--{token} manca nel tema {tema['_nome']}"
    assert tema[token] != tema[contenitore], (
        f"tema {tema['_nome']}: --{token} ha la stessa tinta di --{contenitore} "
        f"({hexa(tema[token])}): l'elemento attivo non si distingue"
    )
    # Soglia piu' bassa delle superfici: qui lo stacco e' rinforzato da testo in
    # grassetto, colore del testo e (per la nav) un bordo sinistro. Ancorata
    # sotto il valore piu' stretto della famiglia, misurato il 24/09/2026:
    # `sidebar-accent` su `sidebar` in chiaro, **1.0907** (le altre coppie
    # stanno fra 1.1252 e 1.2432). La stesura precedente diceva 1.1382
    # (`accent`/`background`) ed era sbagliata: quello e' il quarto valore, non
    # il minimo, e tarare la soglia li' renderebbe rossa una coppia sana.
    SOGLIA_EVIDENZIAZIONE = 1.08
    assert SOGLIA_EVIDENZIAZIONE >= 1.08, "soglia abbassata: si aggira il presidio"
    cr = contrasto(tema[token], tema[contenitore])
    assert cr >= SOGLIA_EVIDENZIAZIONE, (
        f"tema {tema['_nome']}: stacco {token}/{contenitore} {cr:.4f}:1, "
        "l'evidenziazione non si vede"
    )


def _stati_bg_dal_sorgente(escludi: tuple[str, ...] = ()) -> dict[str, int]:
    """Le classi `<stato>:bg-X` che il codice usa davvero, contate per token.

    Legge dall'INDICE git (`ls-files`), non dal filesystem: uno script di
    lavoro non versionato non deve entrare nel perimetro, ed e' l'errore che
    ha gia' fatto divergere un rilevatore fra locale e CI. `ls-files` legge
    l'indice, quindi funziona anche su checkout shallow.
    """
    import re
    import subprocess

    radice = Path(__file__).resolve().parent.parent
    file_ts = subprocess.run(
        ["git", "ls-files", "apps/web/src/**/*.tsx", "apps/web/src/**/*.ts"],
        cwd=radice, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert len(file_ts) >= 300, (
        f"il perimetro si e' svuotato: {len(file_ts)} file invece di 300+. "
        "Il pathspec o la struttura di apps/web/src sono cambiati."
    )

    stato = re.compile(
        r"(?:hover|focus|active|aria-selected|group-hover|data-\[[^\]]+\]):bg-([a-z][a-z-]*)"
    )
    conteggi: dict[str, int] = {}
    for rel in file_ts:
        corto = rel[len("apps/web/src/"):] if rel.startswith("apps/web/src/") else rel
        if any(corto.startswith(e) or ("/" + e) in ("/" + corto) for e in escludi):
            continue
        for token in stato.findall((radice / rel).read_text(encoding="utf-8")):
            conteggi[token] = conteggi.get(token, 0) + 1
    return conteggi


def test_il_perimetro_dei_presidi_colore_non_si_restringe_in_silenzio():
    """Ancora i NUMERI, non solo il comportamento.

    Provato per mutazione il 24/09/2026: togliere `muted` da `EVIDENZIATI`
    faceva scendere la suite da 76 a 72 test **senza un solo rosso**, e
    allargare `SATURE` o alzare `SOGLIA_VOLUME` rendeva innocuo il controllo
    sui token mancanti. Un presidio che si restringe in silenzio e' peggio di
    nessun presidio: sembra che copra, e non copre piu'.

    Questi sono valori ancorati a cio' che rappresentano, non riletti dalle
    strutture che misurano: se cambiano davvero si aggiornano apposta, con una
    riga di motivazione nel commit.
    """
    assert len(SUPERFICI) == 3, f"SUPERFICI: {len(SUPERFICI)} (attese 3: card, popover, sidebar)"
    assert len(EVIDENZIATI) == 11, (
        f"EVIDENZIATI: {len(EVIDENZIATI)} coppie invece di 11. Se ne hai "
        "aggiunta una aggiorna questo numero; se ne e' SPARITA una, il "
        "perimetro si e' ristretto e nessun altro test lo direbbe."
    )
    # I token che devono comparire come primo elemento di una coppia: sono le
    # tinte di evidenziazione realmente usate nel codice.
    token_presidiati = {t for t, _ in EVIDENZIATI}
    assert token_presidiati == {"accent", "sidebar-accent", "muted", "secondary"}, (
        f"i token presidiati sono cambiati: {sorted(token_presidiati)}"
    )


def test_il_rilevatore_degli_stati_vede_ancora_qualcosa():
    """Il guardiano del guardiano: senza di lui il presidio sotto e' cieco.

    Provato per mutazione il 24/09/2026: con la regex che non matcha piu' nulla
    — Tailwind cambia sintassi, o qualcuno tocca il pattern — il presidio sui
    token sopravviveva a TUTTI i 74 test. Un rilevatore che non trova niente
    dichiara «nessuna violazione», che e' il modo piu' silenzioso di mentire.
    Le ancore sono valori NOTI, non riletti dal codice che misurano.
    """
    conteggi = _stati_bg_dal_sorgente()
    assert conteggi, "nessuno `<stato>:bg-*` trovato: il rilevatore e' rotto, non il codice pulito"
    # `muted` e `accent` sono i due piu' usati e non spariranno senza un
    # refactor deliberato: se scendono sotto questi minimi, o il codice e'
    # cambiato molto o la regex non legge piu'. In entrambi i casi si guarda.
    assert conteggi.get("muted", 0) >= 100, f"bg-muted come stato: {conteggi.get('muted', 0)} (atteso 100+)"
    assert conteggi.get("accent", 0) >= 20, f"bg-accent come stato: {conteggi.get('accent', 0)} (atteso 20+)"


def test_ogni_tinta_di_evidenziazione_usata_nel_codice_e_presidiata():
    """Impedisce la QUINTA dimenticanza, rendendola rumorosa.

    `EVIDENZIATI` e' una lista scritta a mano, e in tre giri consecutivi le e'
    sfuggito un contenitore: prima `sidebar`, poi `background`, poi `popover`,
    e infine `muted` — il token piu' usato di tutti — che non c'era affatto.
    Una lista di inclusioni non puo' fallire rumorosamente: se dimentichi una
    voce il test resta verde, e il buco lo trova una review.

    Qui il perimetro si DERIVA dal sorgente e i FONDI si derivano dai token di
    `globals.css`, non da un elenco: la prima stesura aveva sostituito una
    lista a mano con DUE (`EVIDENZIATI` + un set `FONDI` scritto a mano), e
    quel set non falliva mai — un token nuovo come `hover:bg-surface-2` con 40
    usi restava invisibile. Ora un token sconosciuto **non passa in silenzio**:
    o e' un fondo e va presidiato, o e' una tinta satura e va dichiarato qui.
    """
    conteggi = _stati_bg_dal_sorgente()

    # Le tinte SATURE: evidenziazioni che non sono superfici, lontane da
    # qualunque fondo per costruzione (croma alto). Elencate una per una
    # perche' ognuna e' una decisione, non un default.
    SATURE = {
        "primary", "destructive", "incerto", "positivo", "negativo",
        "sidebar-primary", "ring", "background", "foreground",
    }
    SOGLIA_VOLUME = 10

    tema_chiaro = _tema(":root")
    presidiati = {token for token, _ in EVIDENZIATI}
    sconosciuti, mancanti = {}, {}
    for token, n in conteggi.items():
        if n < SOGLIA_VOLUME or token in presidiati or token in SATURE:
            continue
        if token in tema_chiaro:
            mancanti[token] = n      # e' un token del tema: va presidiato
        else:
            sconosciuti[token] = n   # non esiste in globals.css: va capito

    assert not mancanti, (
        "tinte di evidenziazione usate nel codice ma assenti da EVIDENZIATI: "
        + ", ".join(f"bg-{t} ({n} usi)" for t, n in sorted(mancanti.items()))
        + ". Aggiungile con i contenitori su cui poggiano davvero, oppure "
        "dichiarale in SATURE se sono tinte piene."
    )
    # Ancore sui FILTRI stessi: senza queste, allargare `SATURE` o alzare
    # `SOGLIA_VOLUME` rende il controllo innocuo e nessun test lo dice (mutanti
    # M2/M3 del 24/09/2026, sopravvissuti perche' oggi non esiste un token
    # scoperto da far emergere — domani sì).
    assert SOGLIA_VOLUME <= 20, (
        f"SOGLIA_VOLUME={SOGLIA_VOLUME}: alzandola i token con pochi usi "
        "escono dal perimetro senza che nulla lo segnali."
    )
    assert not (SATURE & {t for t, _ in EVIDENZIATI}), (
        "un token non puo' essere insieme SATURO e presidiato come "
        "evidenziazione: dichiararlo saturo lo toglie dal controllo."
    )

    # I token SCONOSCIUTI si controllano SENZA soglia di volume — un colore
    # Tailwind nudo viola «colori solo token» anche con due usi, e il commit
    # precedente dichiarava «non passano piu' in silenzio» mentre sotto i 10
    # usi passavano eccome — ma sul PERIMETRO DELLE PAGINE CLIENTE: admin,
    # demo, landing e legal sono esentati da quella regola, e le esclusioni si
    # importano da li' invece di riscriverle, cosi' le due liste non divergono.
    conteggi_cliente = _stati_bg_dal_sorgente(escludi=ESCLUSI)
    sconosciuti = {
        t: n for t, n in conteggi_cliente.items()
        if t not in tema_chiaro and t not in SATURE and t not in presidiati
    }
    assert not sconosciuti, (
        "classi `<stato>:bg-*` che non corrispondono a nessun token di "
        "globals.css: " + ", ".join(f"bg-{t} ({n} usi)" for t, n in sorted(sconosciuti.items()))
        + ". Se sono colori Tailwind nudi violano il presidio «colori solo token»."
    )


def _etichetta(deb: str) -> str:
    """`file.tsx:630 bg-muted+hover/70 = 1.04` -> `file.tsx bg-muted+hover/70`."""
    testa = deb.rsplit(" = ", 1)[0]
    posizione, resto = testa.split(" ", 1)
    return f"{posizione.rsplit(':', 1)[0]} {resto}"


def test_lo_stesso_token_a_due_alpha_resta_distinguibile():
    """Il pattern `bg-X … hover:bg-X/<alpha>` sullo stesso elemento.

    Trovato dalla review del 24/09/2026: e' un caso che `EVIDENZIATI` non puo'
    vedere, perche' confronta un token col suo CONTENITORE, mai un token con se
    stesso a due opacita'. Due punti usavano `bg-muted` con
    `hover:bg-muted/70|80`, e l'hover valeva 1.04 — impercettibile. Peggiorava
    man mano che `--muted` si avvicinava al fondo, quindi il fix del token lo
    stringeva invece di allargarlo.
    """
    import re
    import subprocess

    radice = Path(__file__).resolve().parent.parent
    file_ts = subprocess.run(
        ["git", "ls-files", "apps/web/src/**/*.tsx"],
        cwd=radice, capture_output=True, text=True, check=True,
    ).stdout.split()
    # 185 misurati il 24/09/2026 (solo .tsx: i .ts non contengono JSX).
    assert len(file_ts) >= 150, f"perimetro svuotato: {len(file_ts)} file"

    # `bg-X` opaco e `hover:bg-X/N` nella stessa stringa di classi.
    # Il `bg-X` di base NON deve essere a sua volta dentro uno stato: in
    # `hover:bg-muted … dark:hover:bg-muted/50` non esiste un fondo opaco di
    # partenza, sono due varianti alternative dello stesso hover. La prima
    # stesura non lo distingueva e produceva 5 falsi positivi sui componenti
    # base (badge/button, variante `ghost`).
    coppia = re.compile(
        r"(?<![:\w-])bg-([a-z][a-z-]*)\b(?![-/])"
        r"(?=[^\"'`]*?(?:hover|focus|active):bg-\1/(\d+))"
    )
    trovati = []
    for rel in file_ts:
        for riga_n, riga in enumerate((radice / rel).read_text(encoding="utf-8").splitlines(), 1):
            for m in coppia.finditer(riga):
                trovati.append((rel, riga_n, m.group(1), int(m.group(2))))

    # NIENTE return anticipato su "non ho trovato nulla": il pattern esiste in
    # 4 punti noti, quindi zero occorrenze significa che il RILEVATORE e' rotto,
    # non che il codice e' pulito. Un mutante che spegneva questa regex
    # sopravviveva proprio grazie al return che stava qui.
    assert trovati, (
        "nessuna coppia `bg-X … hover:bg-X/N` trovata: il rilevatore e' rotto "
        "(ne esistono 4 note nel codice), non il codice diventato pulito."
    )

    tema = _tema(":root")
    deboli = []
    for rel, riga_n, token, alpha in trovati:
        if token not in tema:
            continue
        # L'hover si compone sul CONTENITORE: il caso peggiore e' la card.
        base = tema[token]
        hover = sovrapponi(base, tema["card"], alpha / 100)
        cr = contrasto(base, hover)
        if cr < 1.08:
            deboli.append(f"{Path(rel).name}:{riga_n} bg-{token}+hover/{alpha} = {cr:.4f}")

    # I quattro casi noti al 24/09/2026, DICHIARATI e non corretti: due sono
    # nei componenti base (`badge.tsx`, `button.tsx` variante `secondary`) e
    # cambiarli tocca ogni pagina dell'app — e' una decisione di design che
    # spetta a Mattia, non un fix meccanico. Gli altri due sono singoli
    # elementi. Nessun bersaglio migliore esiste oggi: abbassare l'alpha
    # renderebbe l'hover PIU' CHIARO dello stato base (verso sbagliato),
    # `accent` sta a 1.04 e `--border` nel tema scuro e' un colore con alpha,
    # quindi non e' un fondo confrontabile.
    #
    # La lista e' ANCORATA: un caso NUOVO fa fallire il test, e uno di questi
    # che venga corretto pure — cosi' la deroga non sopravvive al suo motivo.
    # Senza il NUMERO DI RIGA: ancorarlo produceva un falso rosso al primo
    # inserimento di righe sopra, col messaggio «questi hover non esistono
    # piu'» — fuorviante, perche' esistono e si sono solo spostati.
    NOTI = {
        "badge.tsx bg-secondary+hover/80",
        "button.tsx bg-secondary+hover/80",
    }
    etichette = {_etichetta(d) for d in deboli}
    nuovi = etichette - NOTI
    assert not nuovi, (
        "hover impercettibile NUOVO (stesso token a due alpha, sotto 1.08): "
        + "; ".join(sorted(d for d in deboli if _etichetta(d) in nuovi))
        + ". Usa un token diverso per l'hover, o un'opacita' piu' distante."
    )
    spariti = NOTI - etichette
    assert not spariti, (
        "questi hover deboli non esistono piu': " + ", ".join(sorted(spariti))
        + ". Toglili da NOTI, o la deroga copre codice che non c'e' piu'."
    )
