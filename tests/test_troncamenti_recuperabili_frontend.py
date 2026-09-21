"""Un testo troncato deve restare leggibile: `truncate` vuole un `title`.

Perche' qui e non in `apps/web/`: aggiungere un runner di test a `apps/web/`
farebbe scattare `deploy-vercel.yml` (`paths: apps/web/**`) a ogni merge di un
test. Questo presidio legge i sorgenti, non li esegue.

Cosa protegge: `truncate`, `text-ellipsis` e `line-clamp-N` tagliano il testo
con i tre puntini. Senza un `title` (o `aria-label`) il pezzo tagliato **non e'
piu' raggiungibile dall'interfaccia**: due fornitori che iniziano uguali
diventano indistinguibili, e per leggere il nome intero bisogna aprire la
fattura o l'export. Il 21/09/2026 erano 63 elementi su 77 (82%) a non averlo,
visibili negli screenshot come `AVICOVO S.N.C. DI SEVESO…`, `BRICOMAN ITALIA
S.R.L. S…`, `SUSHILAND MARIAN…` nella barra laterale.

Il presidio conta gli elementi, non le righe: la prima misura con `grep` diceva
93 su 125 perche' contava le RIGHE che contengono la classe
(`grep-c-conta-righe-non-occorrenze`). I commenti si neutralizzano invece di
cancellarli, cosi' il numero di riga riportato e' quello del file vero.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

APERTURA = re.compile(r"<(\w+)\s+([^>]*?)/?>", re.S)
# `(?![\w-])` invece di `\b`: il trattino E' un confine di parola per la
# regex, quindi `\btruncate\b` matcha anche `truncate-none` (che il
# troncamento lo TOGLIE). Stessa famiglia di `regex-su-classi-ordine-e-percorsi`.
TRONCA = re.compile(r"(?<![\w-])(truncate|text-ellipsis|line-clamp-\d+)(?![\w-])")
HA_TITOLO = re.compile(r"\b(title|aria-label)\s*=")

# Il perimetro e' quello del presidio colori, IMPORTATO invece che ricopiato:
# due liste scritte a mano divergono, e una cartella nuova finirebbe dentro una
# e fuori dall'altra. Il primo giro qui aveva "app/(admin)" mentre la cartella
# vera e' "app/(app)/admin/": 8 file rossi che non erano nel perimetro.
from tests.test_colori_solo_token_frontend import ESCLUSI

# Le uniche eccezioni ammesse, con la ragione. Un troncamento senza title si
# giustifica SOLO se il testo tagliato non porta un dato: una costante si
# riconosce anche a meta'. Ogni voce nuova qui va motivata.
ECCEZIONI = {
    ("app/(app)/catena/sintesi-catena.tsx", "ETICHETTA_INCOMPLETO"):
        "costante fissa (\"Incompleto\"): troncata resta riconoscibile, e il "
        "dettaglio di cosa manca vive in \"Da vedere nella catena\"",
}


def _perimetro() -> list[Path]:
    file = []
    for p in sorted(SRC.rglob("*.tsx")):
        rel = p.relative_to(SRC).as_posix()
        if any(rel.startswith(e) or ("/" + e) in ("/" + rel) for e in ESCLUSI):
            continue
        file.append(p)
    return file


def _neutralizza(src: str) -> str:
    """Commenti sostituiti con spazi: gli offset restano quelli del file vero."""
    def bianco(m: re.Match[str]) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    src = re.sub(r"/\*.*?\*/", bianco, src, flags=re.S)
    return re.sub(r"^\s*//.*$", bianco, src, flags=re.M)


def _troncamenti(p: Path) -> list[dict]:
    vero = p.read_text(encoding="utf-8")
    src = _neutralizza(vero)
    rel = p.relative_to(SRC).as_posix()
    fuori = []
    for m in APERTURA.finditer(src):
        if not TRONCA.search(m.group(2)):
            continue
        contenuto = " ".join(vero[m.end():m.end() + 90].split("<")[0].split())
        fuori.append({
            "file": rel,
            "riga": src[: m.start()].count("\n") + 1,
            "titolo": bool(HA_TITOLO.search(m.group(2))),
            "contenuto": contenuto[:60],
        })
    return fuori


PERIMETRO = _perimetro()


def test_il_perimetro_non_e_vuoto():
    """Se il perimetro si svuota (una cartella rinominata), i test sotto
    passerebbero per vuoto: questo no."""
    assert len(PERIMETRO) >= 80, len(PERIMETRO)
    assert any(p.name == "scadenziario-client.tsx" for p in PERIMETRO)


def test_il_rilevatore_riconosce_le_forme_che_il_codice_usa(tmp_path):
    """Un rilevatore che non matcha non misura niente: le forme si dichiarano.

    `mutante-che-non-matcha-non-e-una-prova` applicata al presidio stesso.
    """
    casi = [
        ('<span className="truncate">{x}</span>', 1, 0),
        ('<span className="truncate" title={x}>{x}</span>', 1, 1),
        ("<p className='text-ellipsis'>{x}</p>", 1, 0),
        ('<div className="line-clamp-2" aria-label={x}>{x}</div>', 1, 1),
        ('<td\n  className="truncate"\n  title={x}\n>{x}</td>', 1, 1),
        ('<span className={cn("a", "truncate")}>{x}</span>', 1, 0),
        ('<span className="text-sm">{x}</span>', 0, 0),
        # `truncate-none` non e' un troncamento: il confine di parola lo esclude
        ('<span className="truncate-none">{x}</span>', 0, 0),
    ]
    for sorgente, attesi, con_titolo in casi:
        f = tmp_path / "prova.tsx"
        f.write_text(sorgente, encoding="utf-8")
        trovati = [
            {"titolo": bool(HA_TITOLO.search(m.group(2)))}
            for m in APERTURA.finditer(_neutralizza(sorgente))
            if TRONCA.search(m.group(2))
        ]
        assert len(trovati) == attesi, sorgente
        assert sum(t["titolo"] for t in trovati) == con_titolo, sorgente


def test_un_troncamento_in_un_commento_non_si_conta():
    """I commenti si neutralizzano: un esempio dentro un commento non e' codice.

    `grep-conta-le-occorrenze-nei-commenti`.
    """
    src = '// <span className="truncate">{x}</span>\n<span className="text-sm">{y}</span>'
    trovati = [m for m in APERTURA.finditer(_neutralizza(src)) if TRONCA.search(m.group(2))]
    assert trovati == []


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_ogni_troncamento_ha_un_titolo(file: Path):
    nudi = []
    for t in _troncamenti(file):
        if t["titolo"]:
            continue
        chiave = (t["file"], t["contenuto"].strip("{}"))
        if chiave in ECCEZIONI:
            continue
        nudi.append(f"{t['file']}:{t['riga']}  {t['contenuto']}")
    assert not nudi, (
        "testo troncato senza title/aria-label: il dato tagliato non e' piu' "
        "recuperabile dall'interfaccia.\n" + "\n".join(nudi)
    )


def test_le_eccezioni_dichiarate_esistono_ancora():
    """Un'eccezione che non corrisponde piu' a niente e' una riga morta che
    autorizzerebbe in silenzio un troncamento futuro con lo stesso contenuto."""
    vivi = {
        (t["file"], t["contenuto"].strip("{}"))
        for p in PERIMETRO
        for t in _troncamenti(p)
        if not t["titolo"]
    }
    orfane = sorted(k for k in ECCEZIONI if k not in vivi)
    assert not orfane, f"eccezioni che non corrispondono a nulla: {orfane}"
