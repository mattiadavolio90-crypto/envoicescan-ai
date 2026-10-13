"""Un proxy Next inoltra al worker con lo stesso metodo HTTP con cui e' esportato.

Il PATCH di `api/tag/[tag_id]/prodotti/route.ts` (13/10/2026) nasce copiando il
POST accanto: lasciare `workerFetch("POST", ...)` dentro `export async function
PATCH` passa `tsc`, passa il presidio dichiarativo dell'autenticazione e manda
al worker un POST senza `descrizioni` -> 422, e il Salva del riquadro «Modifica
tag» fallisce sempre. La prova per mutazione l'ha lasciato vivo: nessun test lo
vedeva.

Perimetro: ogni `workerFetch("<METODO>", ...)` dentro il corpo di un handler
esportato in `apps/web/src/app/api/**/route.ts`. Le `fetch` dirette con
`method:` non sono coperte: le GET la omettono, e le poche altre passano gia' da
`workerFetch`.
"""
import re
from pathlib import Path

API = Path(__file__).resolve().parent.parent / "apps" / "web" / "src" / "app" / "api"

HANDLER = re.compile(r"^export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b", re.M)
INOLTRO = re.compile(r"workerFetch\(\s*[\"']([A-Z]+)[\"']")


def _inoltri():
    for percorso in sorted(API.rglob("route.ts")):
        testo = percorso.read_text(encoding="utf-8")
        for m in HANDLER.finditer(testo):
            inizio = m.end()
            prossimo = re.search(r"^export\s", testo[inizio:], re.M)
            corpo = testo[inizio:inizio + prossimo.start()] if prossimo else testo[inizio:]
            for w in INOLTRO.finditer(corpo):
                yield percorso.relative_to(API), m.group(1), w.group(1)


def test_il_perimetro_non_e_vuoto():
    # Un glob o una regex rotti darebbero zero inoltri e un verde per omissione.
    trovati = list(_inoltri())
    assert len(trovati) >= 60, f"solo {len(trovati)} inoltri trovati: la scansione e' rotta"
    assert ("tag/[tag_id]/prodotti/route.ts", "PATCH", "PATCH") in {(str(p), h, w) for p, h, w in trovati}


def test_ogni_handler_inoltra_con_il_proprio_metodo():
    sbagliati = [f"{p}: export {h} -> workerFetch(\"{w}\")" for p, h, w in _inoltri() if h != w]
    assert not sbagliati, "Proxy che inoltrano con un metodo diverso dal proprio:\n  " + "\n  ".join(sbagliati)
