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
from pathlib import Path

import pytest

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
