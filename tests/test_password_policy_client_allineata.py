"""Il client dice all'utente gli STESSI requisiti che il server applica.

`apps/web/src/lib/password-policy.ts` e' uno specchio dichiarato di
`valida_password_compliance`. Uno specchio che nessuno controlla diverge: e'
gia' successo con le 4 liste di categorie di spesa (fix di F1).

Questi test **eseguono davvero** la funzione TypeScript (via node, spogliata
delle annotazioni di tipo) e ne confrontano il verdetto con quello del
validatore Python su un campione ampio. Una prima versione si limitava a
leggere le costanti col regex: passava anche mutilando la regex dei simboli o
disattivando del tutto il controllo di lunghezza — misurava due numeri, non il
comportamento.

Blacklist, sequenze e carattere ripetuto restano SOLO al server per scelta
esplicita: sono liste lunghe, il client non le replica e il messaggio del
server arriva comunque a video. Qui si confrontano i due criteri che il client
dichiara di replicare: lunghezza minima e categorie.
"""
import json
import os
import random
import re
import shutil
import string
import subprocess
from pathlib import Path

import pytest

from services.auth_service import valida_password_compliance

POLICY_TS = Path(__file__).resolve().parents[1] / "apps/web/src/lib/password-policy.ts"

def _node_o_fallisci():
    """Skip in locale se manca node, ma **fallimento in CI**.

    Il rischio non è teorico: `tests.yml` non ha uno step `setup-node` e si
    appoggia a ciò che l'immagine `ubuntu-latest` porta con sé. Il giorno in cui
    quell'immagine cambia, uno `skipif` trasformerebbe questi test di sicurezza
    in **skip verdi** — nessuno li guarda, e la regressione passa. In CI un
    ambiente senza node è un guasto da riparare, non un test da saltare.
    """
    if shutil.which("node"):
        return None
    if os.getenv("CI"):
        return pytest.fail(
            "node non disponibile in CI: questi test non possono essere saltati "
            "in silenzio. Aggiungi actions/setup-node a .github/workflows/tests.yml",
            pytrace=False,
        )
    pytest.skip("serve node per eseguire il codice client")


@pytest.fixture(autouse=True)
def _serve_node():
    _node_o_fallisci()


def _valuta_col_client(passwords):
    """Esegue erroreLocalePassword() del vero .ts su una lista di password.

    Le annotazioni di tipo vengono rimosse (il modulo e' TS solo nella firma:
    nessun enum, nessun decoratore), il resto del file gira tale e quale —
    regex incluse, che sono la parte che conta.
    """
    sorgente = POLICY_TS.read_text(encoding="utf-8")
    js = sorgente.replace("export const ", "const ").replace("export function ", "function ")
    js = js.replace("(password: string): number", "(password)")
    js = js.replace("(password: string): string | null", "(password)")
    script = js + """
const input = JSON.parse(process.argv[1]);
console.log(JSON.stringify(input.map((p) => erroreLocalePassword(p))));
"""
    out = subprocess.run(
        ["node", "-e", script, json.dumps(passwords)],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, f"il modulo client non gira: {out.stderr}"
    return json.loads(out.stdout)


def _costante(nome: str) -> int:
    m = re.search(rf"const {nome} = (\d+);", POLICY_TS.read_text(encoding="utf-8"))
    assert m, f"{nome} non trovata in password-policy.ts"
    return int(m.group(1))


def test_il_file_della_policy_client_esiste():
    assert POLICY_TS.exists(), (
        "password-policy.ts e' la fonte unica lato client: se e' stato spostato, "
        "aggiorna questo test invece di cancellarlo"
    )


def test_lunghezza_minima_coincide_col_server():
    """Il server rifiuta sotto i 10 caratteri: il client deve dire 10, non 8."""
    minimo_client = _costante("PASSWORD_MIN_LEN")

    # Una password lunga esattamente `minimo_client - 1` deve far scattare la
    # regola di lunghezza lato server; una lunga `minimo_client` no.
    corta = "Ab1!" + "x" * (minimo_client - 1 - 4)
    giusta = "Ab1!" + "x" * (minimo_client - 4)

    errori_corta = valida_password_compliance(corta, "mario@x.it", "Da Mario")
    errori_giusta = valida_password_compliance(giusta, "mario@x.it", "Da Mario")

    assert any("caratteri" in e for e in errori_corta), (
        f"il client promette {minimo_client} caratteri ma il server accetta "
        f"{len(corta)}: i due numeri sono divergenti"
    )
    assert not any("caratteri" in e for e in errori_giusta), (
        f"il server chiede piu' di {minimo_client} caratteri: il client "
        "sta promettendo una soglia piu' bassa del vero"
    )


def test_categorie_richieste_coincidono_col_server():
    minimo_categorie = _costante("PASSWORD_MIN_CATEGORIE")
    assert minimo_categorie == 3, (
        "il server (auth_service: `if categorie_presenti < 3`) ne chiede 3"
    )

    # Con 2 categorie il server protesta, con 3 no (a parita' di lunghezza).
    due = "abcdefghij1"          # minuscole + numero
    tre = "Abcdefghij1"          # + maiuscola
    assert any("Aggiungi almeno" in e for e in valida_password_compliance(due, "", ""))
    assert not any("Aggiungi almeno" in e for e in valida_password_compliance(tre, "", ""))


@pytest.mark.parametrize("frase", ["10 caratteri", "maiuscole", "numeri"])
def test_il_messaggio_mostrato_nomina_i_requisiti_veri(frase):
    """PASSWORD_HINT e' il placeholder dei due form: deve dire cosa serve
    davvero, altrimenti l'utente scopre i requisiti a tentativi (il worker
    restituisce un solo errore per volta)."""
    testo = POLICY_TS.read_text(encoding="utf-8")
    m = re.search(r'export const PASSWORD_HINT = "([^"]+)"', testo)
    assert m, "PASSWORD_HINT non trovata"
    assert frase in m.group(1), f"il suggerimento non nomina {frase!r}: {m.group(1)!r}"


def test_nessun_form_promette_ancora_8_caratteri():
    """Il vecchio testo "Almeno 8 caratteri" era in due form. Se ricompare,
    il client sta di nuovo mentendo all'utente."""
    web = Path(__file__).resolve().parents[1] / "apps/web/src"
    colpevoli = [
        str(p.relative_to(web))
        for p in web.rglob("*.tsx")
        if "almeno 8 caratteri" in p.read_text(encoding="utf-8").lower()
    ]
    assert not colpevoli, f"promettono ancora 8 caratteri: {colpevoli}"


# ── Il comportamento, non le costanti ────────────────────────────────────────

def test_client_e_server_concordano_su_400_password_casuali():
    """Il confronto che conta: stessa password, stesso verdetto sui due criteri
    replicati. Un mutante nella regex dei simboli o nel controllo di lunghezza
    fa divergere questo test, non i controlli sulle costanti."""
    random.seed(7)
    alfabeti = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*-_=+.,;:?"]
    passwords = []
    for _ in range(400):
        pool = "".join(random.sample(alfabeti, random.randint(1, 4)))
        passwords.append("".join(random.choice(pool) for _ in range(random.randint(4, 16))))

    verdetti_client = _valuta_col_client(passwords)

    divergenze = []
    for password, dal_client in zip(passwords, verdetti_client):
        errori = valida_password_compliance(password, "mario@ristorante.it", "Da Mario")
        server_lunghezza = any("almeno 10 caratteri" in e for e in errori)
        server_categorie = any("Aggiungi almeno" in e for e in errori)
        # Il server segnala entrambi i criteri; il client si ferma al primo.
        atteso = bool(server_lunghezza or server_categorie)
        if bool(dal_client) != atteso:
            divergenze.append((password, dal_client, errori))

    assert not divergenze, (
        f"{len(divergenze)} password su {len(passwords)} hanno verdetti diversi fra "
        f"client e server. Prime 3: {divergenze[:3]}"
    )


def test_il_client_blocca_davvero_le_password_deboli():
    """Controprova diretta: se `erroreLocalePassword` smettesse di bloccare
    (per una regex mutilata o un controllo disattivato) questo cadrebbe."""
    deboli = ["pizza123", "ciao1234", "abcdefghij", "AAAAAAAAAA", "1234567890"]
    verdetti = _valuta_col_client(deboli)
    passate = [p for p, v in zip(deboli, verdetti) if v is None]
    assert not passate, f"il client le lascia passare senza avvisare: {passate}"


def test_il_client_non_blocca_una_password_conforme():
    """L'altra direzione: un filtro troppo severo bloccherebbe utenti con una
    password che il server accetta."""
    conformi = ["Ab1!defghij", "Ristorante2026!", "Xk9-mnopqrst"]
    for password, verdetto in zip(conformi, _valuta_col_client(conformi)):
        assert verdetto is None, f"{password!r} bloccata dal client ma conforme: {verdetto}"
        assert not valida_password_compliance(password, "mario@x.it", "Da Mario")


def test_lunghezza_contata_in_codepoint_come_python():
    """`password.length` in JS conta unita' UTF-16: un emoji vale 2, mentre
    `len()` in Python ne conta 1. Senza [...password] il client direbbe "ok" su
    una password che il server rifiuta — l'errore nella direzione peggiore,
    perche' l'utente scopre il problema solo dopo aver premuto invio."""
    casi = ["Ab1!" + "\U0001F600" * 3, "Ab1!" + "\U0001F600" * 6, "Ab1!" + "e" * 6]
    verdetti = _valuta_col_client(casi)
    for password, dal_client in zip(casi, verdetti):
        dal_server = any(
            "almeno 10 caratteri" in e
            for e in valida_password_compliance(password, "mario@x.it", "Da Mario")
        )
        assert bool(dal_client) == dal_server, (
            f"{password!r}: client={dal_client!r}, il server segnala la lunghezza="
            f"{dal_server} (codepoint={len(password)}, UTF-16={len(password.encode('utf-16-le'))//2})"
        )
