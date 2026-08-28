"""Il client dice all'utente gli STESSI requisiti che il server applica.

`apps/web/src/lib/password-policy.ts` e' uno specchio dichiarato di
`valida_password_compliance`. Uno specchio che nessuno controlla diverge: e'
gia' successo con le 4 liste di categorie di spesa (fix di F1). Qui difendiamo
i due numeri che il client replica — lunghezza minima e categorie richieste —
leggendoli dal .tsx invece di riscriverli.

Blacklist, sequenze e carattere ripetuto restano SOLO al server per scelta
esplicita: sono liste lunghe, il client non le replica e il messaggio del
server arriva comunque a video.
"""
import re
from pathlib import Path

import pytest

from services.auth_service import valida_password_compliance

POLICY_TS = Path(__file__).resolve().parents[1] / "apps/web/src/lib/password-policy.ts"


def _costante(nome: str) -> int:
    testo = POLICY_TS.read_text(encoding="utf-8")
    m = re.search(rf"export const {nome} = (\d+);", testo)
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
