"""Nel frontend del cliente il colore passa dai token, mai dalla palette Tailwind.

E' il presidio della fase 2 della coerenza visiva (18/09/2026). Prima: 1.561
classi di palette scritte a mano in 93 file, 376 `sky-*` al posto del token
`--primary`, 77 esadecimali nei grafici. Il sintomo per il cliente era
"l'azzurro a volte c'e' e a volte no" e un tema scuro mai verificato.

Il perimetro e' tutta `apps/web/src` MENO le esclusioni decise (admin, demo,
`/m`, landing, auth, legal, api): una lista di ESCLUSIONI, non di inclusioni,
cosi' una cartella nuova e' dentro per default e non "sfugge" al presidio.

Cosa controlla, riga per riga e con i commenti tolti (un commento dice com'era):
1. nessuna classe `prop-famiglia-tonalita` (`text-sky-500`, `bg-emerald-50`...)
2. nessun `var(--color-famiglia-tonalita)` dentro un valore arbitrario
3. nessun colore esadecimale fra virgolette: i grafici usano `var(--grafico-N)`
4. ogni token colore usato in una classe e' dichiarato in `@theme inline`:
   Tailwind NON avvisa su `text-primary-txt`, rende solo... niente
5. nessun testo di un token semantico sul proprio fondo tinto sopra /10:
   e' misurato in test_globals_css_contrasto.py che al /15 il light scende
   sotto 4,5:1
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
GLOBALS_CSS = SRC / "app" / "globals.css"

ESCLUSI = (
    "app/(app)/admin/", "app/(demo)/", "app/(mobile)/", "app/(auth)/", "app/(legal)/",
    "app/api/", "components/admin/", "components/demo/", "components/landing/",
    "components/legal/", "lib/admin.ts", "lib/landing-content.ts",
    # themeColor del manifest: e' metadata, non CSS, e vuole un esadecimale
    "app/layout.tsx",
)

FAMIGLIE = ("sky|blue|cyan|teal|indigo|violet|purple|fuchsia|pink|rose|red|orange|"
            "amber|yellow|lime|green|emerald|slate|gray|zinc|neutral|stone")
# Le proprieta' composte PRIMA delle semplici: con `border` davanti a `border-l`
# la regex leggeva `border-l-primary` come prop `border` e token `l-primary`.
PROPS = (r"inset-ring|ring-offset|ring|border-[trblxyse]|border|text|bg|from|to|via|fill|"
         r"stroke|shadow|outline|divide|decoration|placeholder|caret|accent")
CLASSE_PALETTE = re.compile(r"(?<![\w-])(?:[a-z0-9-]+:)*!?(?:%s)-(?:%s)-(?:50|[1-9]00|950)(?:/\S*)?(?![\w-])" % (PROPS, FAMIGLIE))
VAR_PALETTE = re.compile(r"var\(--color-(?:%s)-(?:50|[1-9]00|950)\)" % FAMIGLIE)
HEX_QUOTATO = re.compile(r"""["'`]#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])""")
CLASSE_TOKEN = re.compile(r"(?<![\w\-/.])(?:[a-z0-9-]+:)*!?(%s)-([a-z][a-z-]*[a-z](?:-[0-9]+)?)(?:/(?:\d{1,3}|\[[^\]]+\]))?(?![\w\-.])" % PROPS)
STRINGA = re.compile(r'"([^"\\\n]*)"|\'([^\'\\\n]*)\'|`([^`\n]*)`')
SEMANTICI = ("positivo", "negativo", "incerto")

# Suffissi che NON sono un colore per quella proprieta' (dimensioni, stili...).
NON_COLORE = {
    "text": {"xs", "sm", "base", "lg", "xl", "left", "right", "center", "justify", "start", "end",
             "wrap", "nowrap", "balance", "pretty", "ellipsis", "clip"},
    "bg": {"none", "cover", "contain", "auto", "fixed", "local", "scroll", "center", "top", "bottom",
           "left", "right", "repeat", "no-repeat", "repeat-x", "repeat-y", "repeat-round",
           "repeat-space", "clip-text", "clip-border", "clip-padding", "clip-content",
           "origin-border", "origin-padding", "origin-content", "linear", "radial", "conic", "blend"},
    "border": {"none", "solid", "dashed", "dotted", "double", "hidden", "collapse", "separate", "spacing"},
    "ring": {"inset", "offset"}, "shadow": {"xs", "sm", "md", "lg", "xl", "none", "inner", "inset"},
    "outline": {"none", "hidden", "solid", "dashed", "dotted", "double"},
    "divide": {"solid", "dashed", "dotted", "double", "none", "x-reverse", "y-reverse"},
    "decoration": {"solid", "double", "dotted", "dashed", "wavy", "auto", "from-font"},
    "fill": {"none"}, "stroke": {"none"}, "accent": {"auto"},
}
# Le parole chiave di colore che Tailwind ha senza token.
COLORI_BASE = {"white", "black", "transparent", "current", "inherit"}


def _perimetro() -> list[Path]:
    file = []
    for p in sorted(SRC.rglob("*")):
        if p.suffix not in (".ts", ".tsx") or p.name.endswith(".d.ts") or p.name.endswith("_test.ts"):
            continue
        rel = p.relative_to(SRC).as_posix()
        if any(rel.startswith(e) or ("/" + e) in ("/" + rel) for e in ESCLUSI):
            continue
        file.append(p)
    return file


def _senza_commenti(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    righe = []
    for r in src.splitlines():
        t = r.lstrip()
        if t.startswith("//") or t.startswith("*"):
            continue
        righe.append(r)
    return "\n".join(righe)


def _token_dichiarati() -> set[str]:
    css = re.sub(r"/\*.*?\*/", "", GLOBALS_CSS.read_text(encoding="utf-8"), flags=re.S)
    theme = css[css.index("@theme inline {"):]
    theme = theme[: theme.index("\n}")]
    return set(re.findall(r"--color-([a-z0-9-]+):", theme)) | COLORI_BASE


PERIMETRO = _perimetro()
DICHIARATI = _token_dichiarati()


def test_il_perimetro_del_presidio_non_e_vuoto():
    """Fuori dalla parametrizzazione: se il perimetro si svuota (una cartella
    rinominata) i test sotto passerebbero per vuoto, questo no."""
    assert len(PERIMETRO) >= 80, len(PERIMETRO)
    assert any(p.name == "app-sidebar.tsx" for p in PERIMETRO)
    assert not any("/admin/" in p.as_posix() for p in PERIMETRO)


def test_i_token_della_fase_2_sono_dichiarati():
    """Se questo fallisce, i test sotto non possono distinguere un token vero da un refuso."""
    assert {"primary", "primary-text", "accent", "positivo", "negativo", "incerto",
            "grafico-1", "grafico-5", "muted-foreground", "destructive"} <= DICHIARATI


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_nessuna_classe_di_palette(file: Path):
    src = _senza_commenti(file.read_text(encoding="utf-8"))
    trovate = CLASSE_PALETTE.findall(src) + VAR_PALETTE.findall(src)
    assert not trovate, f"palette scritta a mano: {sorted(set(trovate))[:8]}"


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_nessun_esadecimale_fra_virgolette(file: Path):
    src = _senza_commenti(file.read_text(encoding="utf-8"))
    trovati = HEX_QUOTATO.findall(src)
    assert not trovati, f"colore esadecimale: {trovati[:5]} -- i grafici usano var(--grafico-N)"


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_ogni_token_usato_esiste(file: Path):
    src = _senza_commenti(file.read_text(encoding="utf-8"))
    ignoti = set()
    for prop, nome in CLASSE_TOKEN.findall(src):
        base = "border" if prop.startswith("border") else ("ring" if prop.startswith("ring") else prop)
        radice = re.sub(r"-\d+$", "", nome)      # spacing-0 -> spacing
        if nome in DICHIARATI or nome in NON_COLORE.get(base, set()) or radice in NON_COLORE.get(base, set()):
            continue
        if base in ("text", "shadow") and re.fullmatch(r"\d?xl", nome):
            continue
        if base == "bg" and re.match(r"(gradient|linear|radial|conic|blend)-", nome):
            continue
        ignoti.add(f"{prop}-{nome}")
    assert not ignoti, f"token non dichiarato in @theme (refuso? Tailwind non avvisa): {sorted(ignoti)}"


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_nessun_testo_semantico_sul_proprio_fondo_sopra_il_10(file: Path):
    src = _senza_commenti(file.read_text(encoding="utf-8"))
    violazioni = []
    for m in STRINGA.finditer(src):
        s = next(g for g in m.groups() if g is not None)
        for t in SEMANTICI:
            if re.search(rf"\btext-{t}\b", s) and re.search(rf"\bbg-{t}/(1[1-9]|[2-9]\d|100)\b", s):
                violazioni.append(s.strip()[:80])
    assert not violazioni, f"testo e fondo dello stesso token sopra /10: {violazioni[:3]}"


# Lo stesso testo a video con due colori semantici diversi nello stesso file.
# Il 18/09 `06bd099` (fase 2, "le card non sono piu' tinte") ha lasciato
# "Paghe non inserite" `text-positivo` sulla prima card del Personale e
# `text-incerto` sulle altre due: lo stesso dato mancante letto come un esito
# positivo su una tessera e come un avviso sulle altre, in tre tessere
# affiancate che il commento del codice dichiarava gia' allineate.
ETICHETTA_SEMANTICA = re.compile(
    r"text-(positivo|negativo|incerto)[^\"'>]*\"\s*>\s*([^<{][^<]*?)\s*</span>"
)


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_una_etichetta_non_cambia_colore_semantico_nello_stesso_file(file: Path):
    per_testo: dict[str, set[str]] = {}
    for m in ETICHETTA_SEMANTICA.finditer(_senza_commenti(file.read_text(encoding="utf-8"))):
        token, testo = m.group(1), " ".join(m.group(2).split())
        if testo:
            per_testo.setdefault(testo, set()).add(token)
    discordi = {t: sorted(k) for t, k in per_testo.items() if len(k) > 1}
    assert not discordi, f"stessa etichetta con colori semantici diversi: {discordi}"
