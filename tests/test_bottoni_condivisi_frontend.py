"""Nel frontend del cliente un bottone e' `<Button>` / `FilterChip` / ..., non un `<button>` a mano.

Presidio della coerenza dei bottoni (8/10/2026). L'audit visivo aveva misurato
sei altezze diverse per il bottone secondario, quattro versioni del filtro
«Tutti», angoli a 4, 8 e 10 px: ogni pagina aveva ricreato il bottone con le
sue classi invece di riusare `components/ui/button.tsx`.

Le due regole sono un TRINQUETTO, non un divieto assoluto: i file che avevano
gia' bottoni a mano (BASE_BUTTON) restano come sono finche' non vengono
migrati, ma il numero puo' solo scendere. Il perimetro e' tutta `apps/web/src`
meno ESCLUSI (admin, demo, `/m`, landing...) e `components/ui/`, dove i
componenti condivisi sono scritti per definizione con il tag nativo.

1. `<button` nativo: un file non puo' superare la sua base (0 se non in lista);
   se la base e' piu' alta del reale va abbassata, cosi' il numero non risale
   in silenzio dopo una migrazione.
2. `<Button` con nel proprio tag una classe che ridisegna la taglia (`h-8`,
   `size-7`, `rounded-*`, `text-xs`): la taglia si sceglie con `size=`, non la
   si sovrascrive. Stesso trinquetto (BASE_TAGLIA).

Un test solo per regola, non uno per file: un `.tsx` nuovo non cambia il
totale dei test.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_colori_solo_token_frontend import ESCLUSI

SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

CONDIVISI = ("components/ui/",)

# Misurate il 8/10/2026 con misura_basi() qui sotto, non ricopiate da un doc.
BASE_BUTTON: dict[str, int] = {
    "app/(app)/agenda/agenda-overview.tsx": 4,
    "app/(app)/agenda/layer-switcher.tsx": 1,
    "app/(app)/analisi-e-tag/analisi-e-tag-client.tsx": 27,
    "app/(app)/analisi-fatture/articoli-tab.tsx": 3,
    "app/(app)/analisi-fatture/filtri-periodo.tsx": 3,
    "app/(app)/analisi-fatture/pivot-tab.tsx": 3,
    "app/(app)/analisi-fatture/tabs-switcher.tsx": 1,
    "app/(app)/analisi-fatture/upload-modal.tsx": 1,
    "app/(app)/catena/analisi/scheda-margini-coperti.tsx": 2,
    "app/(app)/catena/analisi/scheda-spesa-pv.tsx": 1,
    "app/(app)/catena/analisi/scheda-tag-catena.tsx": 5,
    "app/(app)/catena/fatture/scheda-costi-gruppo.tsx": 4,
    "app/(app)/catena/sintesi-catena.tsx": 4,
    "app/(app)/dashboard/block-retry.tsx": 1,
    "app/(app)/impostazioni/account-client.tsx": 2,
    "app/(app)/margini/analisi-tab.tsx": 14,
    "app/(app)/margini/calcolo-tab.tsx": 12,
    "app/(app)/margini/carica-ricavi-dialog.tsx": 7,
    "app/(app)/margini/coperti-tab.tsx": 11,
    "app/(app)/margini/filtri-periodo.tsx": 3,
    "app/(app)/margini/tabs-switcher.tsx": 1,
    "app/(app)/notifiche/notifiche-list.tsx": 1,
    "app/(app)/prezzi/nc-tab.tsx": 2,
    "app/(app)/prezzi/sconti-tab.tsx": 2,
    "app/(app)/prezzi/score-tab.tsx": 3,
    "app/(app)/prezzi/tabs-switcher.tsx": 1,
    "app/(app)/prezzi/variazioni-tab.tsx": 5,
    "app/(app)/scadenziario/scadenziario-client.tsx": 19,
    "app/(app)/workspace/diario-tab.tsx": 1,
    "app/(app)/workspace/foodcost-tab.tsx": 2,
    "app/(app)/workspace/inventario-aggiungi-dialog.tsx": 1,
    "app/(app)/workspace/inventario-date-picker.tsx": 4,
    "app/(app)/workspace/inventario-storico-dialog.tsx": 1,
    "app/(app)/workspace/inventario-tab.tsx": 1,
    "app/(app)/workspace/personale-tab.tsx": 11,
    "app/(app)/workspace/ricetta-editor.tsx": 1,
    "app/(app)/workspace/spese-view.tsx": 3,
    "app/(app)/workspace/tabs-switcher.tsx": 1,
    "components/ascolta-button.tsx": 1,
    "components/fatture/coda-da-assegnare.tsx": 9,
    "components/home/card-home.tsx": 1,
    "components/home/da-fare-oggi.tsx": 1,
    "components/home/pannello-conversazione.tsx": 2,
}
BASE_TAGLIA: dict[str, int] = {
    "app/(app)/catena/analisi/scheda-margini-coperti.tsx": 1,
    "app/(app)/dashboard/notifiche-widget.tsx": 1,
    "app/(app)/notifiche/notifiche-list.tsx": 1,
    "app/(app)/scadenziario/scadenziario-client.tsx": 19,
    "app/(app)/workspace/foodcost-tab.tsx": 3,
    "app/(app)/workspace/ingredienti-manuali-dialog.tsx": 4,
    "app/(app)/workspace/inventario-aggiungi-dialog.tsx": 1,
    "app/(app)/workspace/inventario-tab.tsx": 2,
    "app/(app)/workspace/personale-tab.tsx": 12,
    "app/(app)/workspace/ricetta-editor.tsx": 2,
    "app/(app)/workspace/spese-view.tsx": 2,
    "components/home/pannello-conversazione.tsx": 1,
}

BUTTON_NATIVO = re.compile(r"<button(?![\w-])")
BUTTON_CONDIVISO = re.compile(r"<Button(?![\w-])")
STRINGA = re.compile(r'"([^"\\\n]*)"|\'([^\'\\\n]*)\'|`([^`]*)`')
# Altezza, lato, raggio e corpo del testo: cio' che `size=` gia' decide.
TAGLIA = re.compile(
    r"(?<![\w\-/.])(?:[a-z0-9-]+:)*!?(?:h-(?:\d|\[)|size-(?:\d|\[)|rounded(?:-[\w\[\]\-.]+)?|text-(?:xs|sm|base|lg|\[))(?![\w])"
)


def _perimetro() -> list[Path]:
    file = []
    for p in sorted(SRC.rglob("*.tsx")):
        rel = p.relative_to(SRC).as_posix()
        if any(rel.startswith(e) or ("/" + e) in ("/" + rel) for e in ESCLUSI + CONDIVISI):
            continue
        file.append(p)
    return file


def _neutralizza(src: str) -> str:
    """Commenti sostituiti con spazi: gli offset restano quelli del file vero."""
    def bianco(m: re.Match[str]) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    src = re.sub(r"/\*.*?\*/", bianco, src, flags=re.S)
    return re.sub(r"^\s*//.*$", bianco, src, flags=re.M)


def _fine_tag(src: str, inizio: int) -> int:
    """Indice del `>` che chiude il tag aperto in `inizio`, saltando `=>` e i
    `>` dentro le espressioni `{...}` e le stringhe."""
    profondita = 0
    i = inizio
    while i < len(src):
        c = src[i]
        if c in "\"'`":
            j = i + 1
            while j < len(src) and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            i = j
        elif c == "{":
            profondita += 1
        elif c == "}":
            profondita -= 1
        elif c == ">" and profondita == 0:
            return i
        i += 1
    return len(src)


def conta_button_nativi(src: str) -> int:
    return len(BUTTON_NATIVO.findall(_neutralizza(src)))


def conta_taglie_sovrascritte(src: str) -> int:
    src = _neutralizza(src)
    n = 0
    for m in BUTTON_CONDIVISO.finditer(src):
        tag = src[m.start(): _fine_tag(src, m.end())]
        stringhe = " ".join(a or b or c for a, b, c in STRINGA.findall(tag))
        if TAGLIA.search(stringhe):
            n += 1
    return n


def misura_basi() -> tuple[dict[str, int], dict[str, int]]:
    nativi, taglie = {}, {}
    for p in _perimetro():
        rel = p.relative_to(SRC).as_posix()
        src = p.read_text(encoding="utf-8")
        if n := conta_button_nativi(src):
            nativi[rel] = n
        if n := conta_taglie_sovrascritte(src):
            taglie[rel] = n
    return nativi, taglie


def _confronta(misurato: dict[str, int], base: dict[str, int], cosa: str) -> list[str]:
    errori = []
    for rel in sorted(set(misurato) | set(base)):
        reale, ammesso = misurato.get(rel, 0), base.get(rel, 0)
        if reale > ammesso:
            errori.append(f"{rel}: {reale} {cosa} (ammessi {ammesso})")
        elif reale < ammesso:
            errori.append(f"{rel}: ne restano {reale}, la base dice {ammesso} — abbassala a {reale}")
    return errori


PERIMETRO = _perimetro()
MISURATO_BUTTON, MISURATO_TAGLIA = misura_basi()


def test_il_perimetro_del_presidio_non_e_vuoto():
    assert len(PERIMETRO) >= 80, len(PERIMETRO)
    assert any(p.name == "scadenziario-client.tsx" for p in PERIMETRO)
    assert not any("/components/ui/" in "/" + p.relative_to(SRC).as_posix() for p in PERIMETRO)
    assert not any("/admin/" in p.as_posix() for p in PERIMETRO)


def test_il_rilevatore_riconosce_le_forme_che_deve():
    assert conta_button_nativi("<button onClick={x}>a</button>") == 1
    assert conta_button_nativi("<button\n  className='a'\n>a</button>") == 1
    assert conta_button_nativi("<Button>a</Button><buttonish>") == 0
    assert conta_button_nativi("// <button> a mano\n/* <button> */") == 0
    assert conta_taglie_sovrascritte('<Button className="h-8 text-xs">a</Button>') == 1
    assert conta_taglie_sovrascritte('<Button className={cn("x", on && "rounded-full")}>a</Button>') == 1
    assert conta_taglie_sovrascritte('<Button onClick={() => f(1)} className="size-7">a</Button>') == 1
    assert conta_taglie_sovrascritte('<Button size="sm" className="ml-auto w-full gap-2">a</Button>') == 0
    assert conta_taglie_sovrascritte('<Button title="Esporta il testo" size="xs">a</Button>') == 0
    assert conta_taglie_sovrascritte('<Button onClick={() => a > b}>ok</Button><p className="h-8"/>') == 0


def test_nessun_bottone_nativo_in_piu():
    errori = _confronta(MISURATO_BUTTON, BASE_BUTTON, "<button a mano")
    assert not errori, "usa <Button> / FilterChip / SegmentedControl:\n" + "\n".join(errori)


def test_nessuna_taglia_sovrascritta_in_piu():
    errori = _confronta(MISURATO_TAGLIA, BASE_TAGLIA, "<Button con taglia sovrascritta")
    assert not errori, "scegli la taglia con size=, non con le classi:\n" + "\n".join(errori)
