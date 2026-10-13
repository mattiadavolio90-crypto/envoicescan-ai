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

Secondo presidio, il PERCORSO (mutante M11f della Fase 2, 13/10/2026): il PUT
di `api/tag/cartelle/[cartella_id]/route.ts` inoltrato a `/api/tag/${cartella_id}`
rinominerebbe il TAG con lo stesso numero della cartella (sequenze diverse, id
che possono coincidere), e il controllo del metodo resta verde. Il percorso
passato a `workerFetch`, con `${x}` letto come `[x]`, deve coincidere con la
cartella del `route.ts`. Le eccezioni volute stanno in `PERCORSI_DIVERSI`,
misurate il 13/10/2026: 2 su 76 inoltri con percorso letterale.
"""
import re
from pathlib import Path

API = Path(__file__).resolve().parent.parent / "apps" / "web" / "src" / "app" / "api"

HANDLER = re.compile(r"^export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b", re.M)
INOLTRO = re.compile(r"workerFetch\(\s*[\"']([A-Z]+)[\"']\s*,\s*(`[^`]*`|\"[^\"]*\"|'[^']*')?")
INTERPOLAZIONE = re.compile(r"\$\{\s*(?:encodeURIComponent\()?\s*([A-Za-z_][\w.]*)\s*\)?\s*\}")

# Proxy che inoltrano di proposito a un'altra rotta del worker.
PERCORSI_DIVERSI = {
    ("fatture/da-assegnare/route.ts", "POST"): "/api/fatture/assegna-sede",
    ("notifiche/dismiss/route.ts", "POST"): "/api/notifiche/[id]/dismiss",
}


def _percorso_normalizzato(letterale: str) -> str:
    senza_apici = letterale[1:-1]
    con_parametri = INTERPOLAZIONE.sub(lambda m: "[" + m.group(1).split(".")[-1] + "]", senza_apici)
    return con_parametri.split("?")[0]


def _inoltri():
    for percorso in sorted(API.rglob("route.ts")):
        testo = percorso.read_text(encoding="utf-8")
        for m in HANDLER.finditer(testo):
            inizio = m.end()
            prossimo = re.search(r"^export\s", testo[inizio:], re.M)
            corpo = testo[inizio:inizio + prossimo.start()] if prossimo else testo[inizio:]
            for w in INOLTRO.finditer(corpo):
                yield percorso.relative_to(API), m.group(1), w.group(1), w.group(2)


def _inoltri_metodo():
    for p, h, w, _letterale in _inoltri():
        yield p, h, w


def test_il_perimetro_non_e_vuoto():
    # Un glob o una regex rotti darebbero zero inoltri e un verde per omissione.
    trovati = list(_inoltri_metodo())
    assert len(trovati) >= 60, f"solo {len(trovati)} inoltri trovati: la scansione e' rotta"
    assert ("tag/[tag_id]/prodotti/route.ts", "PATCH", "PATCH") in {(str(p), h, w) for p, h, w in trovati}


def test_ogni_handler_inoltra_con_il_proprio_metodo():
    sbagliati = [f"{p}: export {h} -> workerFetch(\"{w}\")" for p, h, w in _inoltri_metodo() if h != w]
    assert not sbagliati, "Proxy che inoltrano con un metodo diverso dal proprio:\n  " + "\n  ".join(sbagliati)


def _percorsi():
    for p, h, _w, letterale in _inoltri():
        if letterale is None:
            continue
        atteso = PERCORSI_DIVERSI.get((str(p), h), "/api/" + p.parent.as_posix())
        yield str(p), h, _percorso_normalizzato(letterale), atteso


def test_il_perimetro_dei_percorsi_non_e_vuoto():
    trovati = list(_percorsi())
    assert len(trovati) >= 60, f"solo {len(trovati)} percorsi letterali trovati: la scansione e' rotta"
    assert ("tag/cartelle/[cartella_id]/route.ts", "PUT", "/api/tag/cartelle/[cartella_id]",
            "/api/tag/cartelle/[cartella_id]") in set(trovati)
    assert ("riparto/[id]/route.ts", "PATCH", "/api/riparto/[id]", "/api/riparto/[id]") in set(trovati), \
        "`${encodeURIComponent(id)}` deve leggersi come `[id]`"


def test_ogni_handler_inoltra_alla_rotta_della_propria_cartella():
    sbagliati = [f"{p}: export {h} -> {reale} (atteso {atteso})" for p, h, reale, atteso in _percorsi() if reale != atteso]
    assert not sbagliati, "Proxy che inoltrano a una rotta diversa dalla propria cartella:\n  " + "\n  ".join(sbagliati)


def test_le_eccezioni_dichiarate_esistono_ancora():
    presenti = {(p, h) for p, h, _r, _a in _percorsi()}
    sparite = [k for k in PERCORSI_DIVERSI if k not in presenti]
    assert not sparite, f"eccezioni in PERCORSI_DIVERSI senza piu' un proxy: {sparite}"
