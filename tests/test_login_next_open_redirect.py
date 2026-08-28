"""`?next=` non deve poter portare fuori dal dominio dopo il login.

`/login?next=` viene letto dalla query string e finisce in
`window.location.href`: un valore ostile e' un redirect fuori dominio DOPO che
l'utente ha inserito le credenziali sul sito vero — la forma piu' credibile di
phishing.

Questo test **esegue** `nextSicuro()` estratta dal .tsx di produzione (via node,
stesso parser WHATWG dei browser) su tutte le classi di bypass note. Esiste
perche' il fix e' stato riscritto tre volte e i primi due giri sembravano
completi:

  1. filtro sul prefisso        -> aggirato da "/<TAB>/evil.com" (%09): la
     WHATWG rimuove TAB/LF/CR PRIMA di parsare, quindi il controllo guardava
     una stringa diversa da quella eseguita;
  2. origin + pathname+search+hash -> aggirato da "/..//evil.com": il check
     sull'origine passava, ma la ri-serializzazione reintroduceva un secondo
     parsing e restituiva "//evil.com", protocol-relative. In chiaro, senza
     encoding.

Entrambi erano stati verificati "su decine di forme": le forme erano tante ma
della stessa classe. Qui le classi sono nominate una per una.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

LOGIN_TSX = Path(__file__).resolve().parents[1] / "apps/web/src/app/(auth)/login/page.tsx"
ORIGIN = "https://app.oneflux.it"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="serve node per eseguire nextSicuro()"
)


def _estrai_next_sicuro() -> str:
    """Prende la funzione dal file di PRODUZIONE, non una copia nel test.

    Una copia diverge in silenzio, ed e' esattamente il difetto che l'audit F2
    ha corretto altrove (le 4 liste di categorie, la policy password).
    """
    sorgente = LOGIN_TSX.read_text(encoding="utf-8")
    m = re.search(
        r"function nextSicuro\(raw: string \| null\): string \| null \{.*?\n\}",
        sorgente,
        re.S,
    )
    assert m, (
        "nextSicuro() non trovata in login/page.tsx: se e' stata rinominata o "
        "spostata aggiorna questo test, non cancellarlo"
    )
    return m.group(0).replace("(raw: string | null): string | null", "(raw)")


def _risolvi(valori):
    """Per ogni valore: cosa ritorna nextSicuro, e dove atterra il browser."""
    script = f"""
global.window = {{ location: {{ origin: {json.dumps(ORIGIN)} }} }};
{_estrai_next_sicuro()}
const input = JSON.parse(process.argv[1]);
console.log(JSON.stringify(input.map((raw) => {{
  const out = nextSicuro(raw);
  // Il componente usa `next || default`: null e stringa vuota cadono sul default.
  return new URL(out || "/dashboard", {json.dumps(ORIGIN)}).href;
}})));
"""
    res = subprocess.run(
        ["node", "-e", script, json.dumps(valori)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, f"nextSicuro() non gira: {res.stderr}"
    return json.loads(res.stdout)


# Ogni voce e' una CLASSE di bypass, non una variante della stessa.
ATTACCHI = [
    # protocol-relative e schemi assoluti
    "//evil.com", "https://evil.com", "http://evil.com", "///evil.com",
    # schemi non-http
    "javascript:alert(1)", "data:text/html,<script>alert(1)</script>",
    # backslash (i browser lo normalizzano a slash)
    "/\\evil.com", "\\/evil.com", "//\\evil.com",
    # caratteri rimossi dal parser PRIMA della risoluzione (bypass n.1)
    "/\t/evil.com", "/\n/evil.com", "/\r/evil.com", "\t//evil.com", "/\t\\evil.com",
    # dot-segment: origin interno ma pathname protocol-relative (bypass n.2)
    "/..//evil.com", "/./..//evil.com", "/a/../..//evil.com", "/../..//evil.com",
    "/..///evil.com", "/..\\evil.com", "/%2e%2e//evil.com", "/..\t//evil.com",
    "/..//evil.com/login", "/..//evil.com?x=1", "/..//evil.com#z",
    # userinfo: il dominio vero finisce prima della @
    "//user:pass@evil.com", "//APP.ONEFLUX.IT@evil.com", "/..//user:pass@evil.com",
    # suffisso di dominio: contiene il nostro host ma non lo e'
    "//app.oneflux.it.evil.com", "https://app.oneflux.it.evil.com",
    "/..//app.oneflux.it.evil.com",
    # fragment che imita l'host
    "//evil.com#@app.oneflux.it",
    # downgrade di schema: stesso host, ma http. Un controllo su url.host invece
    # che su url.origin lo lascerebbe passare, e la sessione appena creata
    # viaggerebbe in chiaro.
    "http://app.oneflux.it/dashboard",
    "http://app.oneflux.it",
]

LECITI = [
    "/dashboard", "/catena", "/m", "/analisi-fatture?x=1&y=2", "/margini#kpi",
    "/impostazioni/", "/", "/?q=a+b", "/prezzi?f=%2Fx",
]


@pytest.mark.parametrize("attacco", ATTACCHI)
def test_nessun_attacco_esce_dallorigine(attacco):
    """Origine, non solo host: uno stesso host su http invece di https e' un
    downgrade che manda in chiaro la sessione appena creata."""
    (destinazione,) = _risolvi([attacco])
    assert destinazione.startswith(ORIGIN + "/"), (
        f"{attacco!r} porta l'utente su {destinazione} dopo il login"
    )


@pytest.mark.parametrize("path", LECITI)
def test_i_path_interni_restano_intatti(path):
    """Un filtro troppo severo romperebbe il `next` scritto da proxy.ts:93,
    cioe' il ritorno alla pagina richiesta dopo il login."""
    (destinazione,) = _risolvi([path])
    from urllib.parse import urljoin
    assert destinazione == urljoin(ORIGIN, path), (
        f"{path!r} doveva restare se stesso, invece porta a {destinazione}"
    )


def test_valori_vuoti_cadono_sul_default():
    for destinazione in _risolvi(["", None]):
        assert destinazione == f"{ORIGIN}/dashboard"
