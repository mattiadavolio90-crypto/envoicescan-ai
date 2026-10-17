"""Nessuna lettura del frontend passa dalla Data Cache di Next.

La chiave di quella cache e' URL + metodo + header, cioe' il token: la sede attiva
non c'e', perche' il worker la legge dalla sessione. Con `next: { revalidate: 60 }`
`lib/fatture.ts` mostrava per un minuto, dopo il cambio sede, i mesi e le
categorie della sede di prima (audit di ottobre #22). Tutte le altre letture erano
gia' `cache: "no-store"`: qui si tiene la regola per tutto `apps/web/src`.
"""
import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

_VIETATI = [
    (re.compile(r"\bnext\s*:\s*\{[^}]*\brevalidate\s*:"), "next.revalidate"),
    (re.compile(r"""["']force-cache["']"""), "force-cache"),
    (re.compile(r"\bunstable_cache\b"), "unstable_cache"),
    (re.compile(r"""^\s*["']use cache["']""", re.M), "use cache"),
]


def _senza_commenti(testo):
    testo = re.sub(r"/\*.*?\*/", "", testo, flags=re.S)
    return re.sub(r"(?<![:\"'])//[^\n]*", "", testo)


def test_nessuna_lettura_in_data_cache():
    file_letti = 0
    trovati = []
    for f in sorted(WEB_SRC.rglob("*")):
        if f.suffix not in (".ts", ".tsx"):
            continue
        file_letti += 1
        codice = _senza_commenti(f.read_text(encoding="utf-8"))
        for regex, nome in _VIETATI:
            if regex.search(codice):
                trovati.append(f"{f.relative_to(WEB_SRC)}: {nome}")
    assert file_letti > 300, f"letti solo {file_letti} file: il percorso e' sbagliato"
    assert not trovati, trovati


def test_le_letture_di_analisi_fatture_sono_no_store():
    codice = _senza_commenti((WEB_SRC / "lib" / "fatture.ts").read_text(encoding="utf-8"))
    assert 'await fetch(url, { headers: workerHeaders(token), cache: "no-store" })' in codice
    assert "revalidate" not in codice
