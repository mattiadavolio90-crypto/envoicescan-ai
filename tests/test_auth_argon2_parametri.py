"""I parametri Argon2 sono quelli dichiarati, e restano compatibili col DB.

CLAUDE.md §Sicurezza dice: "Password: Argon2 (m=65536, t=3) — non cambiare
parametri". Fino al 28/8/2026 quella riga era **descrittiva**: `auth_service.py`
faceva `argon2.PasswordHasher()` e ereditava i default della libreria. Coincidevano
— verificato — ma `requirements.txt` dichiara `argon2-cffi>=23.1.0` senza tetto,
quindi un aggiornamento che cambiasse i default avrebbe cambiato il costo di
hashing senza che nulla fallisse.

Questi test rendono quella riga **falsificabile**: se qualcuno tocca i parametri,
o se un upgrade li sposta, qui si rompe qualcosa con un messaggio che dice cosa.

Nota su cosa NON si sta testando: la forza crittografica di Argon2. Quella e'
della libreria. Qui si verifica che ONEFLUX la usi con i parametri che dichiara.
"""
import argon2
import pytest

from services import auth_service


# I valori di CLAUDE.md §Sicurezza. `parallelism` NON e' nel doc (ci era rimasto
# implicito): e' il default della libreria, fissato qui perche' concorre al costo
# esattamente come gli altri due.
PARAMETRI_ATTESI = {
    "memory_cost": 65536,
    "time_cost": 3,
    "parallelism": 4,
}


@pytest.mark.parametrize("nome, atteso", sorted(PARAMETRI_ATTESI.items()))
def test_hasher_usa_i_parametri_dichiarati(nome, atteso):
    """L'hasher globale espone esattamente i parametri di CLAUDE.md."""
    reale = getattr(auth_service.ph, nome)
    assert reale == atteso, (
        f"Argon2 {nome}={reale}, atteso {atteso}. Se il cambio e' voluto, "
        f"aggiorna CLAUDE.md §Sicurezza; se non lo e', e' una regressione "
        f"del costo di hashing."
    )


def test_parametri_espliciti_non_ereditati_dai_default():
    """I parametri devono essere passati, non ereditati.

    Se `PasswordHasher()` tornasse senza argomenti il test sopra continuerebbe a
    passare finche' i default coincidono — cioe' misurerebbe la libreria, non il
    codice. Qui si verifica che il sorgente li nomini davvero.
    """
    import inspect

    sorgente = inspect.getsource(auth_service)
    riga = next(
        (r for r in sorgente.splitlines() if "PasswordHasher(" in r), None
    )
    assert riga is not None, "PasswordHasher non trovato in auth_service"
    blocco = sorgente.split("PasswordHasher(", 1)[1].split(")", 1)[0]
    for nome in PARAMETRI_ATTESI:
        assert nome in blocco, (
            f"'{nome}' non e' passato esplicitamente a PasswordHasher: "
            f"tornerebbe a dipendere dal default di argon2-cffi."
        )


def test_hash_prodotti_sono_argon2id_con_i_parametri_attesi():
    """L'hash scritto in DB porta i parametri incorporati: e' cosi' che gli hash
    vecchi restano verificabili quando quelli nuovi cambiano."""
    h = auth_service.ph.hash("password-di-prova")
    assert h.startswith("$argon2id$"), f"variante inattesa: {h.split('$')[1]}"
    assert "m=65536,t=3,p=4" in h, f"parametri inattesi nell'hash: {h[:60]}"


def test_hash_esistenti_con_parametri_diversi_restano_validi():
    """Proprieta' che protegge i clienti gia' registrati.

    `verify()` legge i parametri dall'hash, non dall'hasher: un hash creato con
    parametri piu' bassi resta valido anche dopo un irrigidimento. Senza questa
    garanzia, alzare i costi sloggherebbe tutti.
    """
    vecchio = argon2.PasswordHasher(memory_cost=8192, time_cost=2).hash("segreto")
    assert auth_service.ph.verify(vecchio, "segreto") is True


def test_password_sbagliata_resta_rifiutata_anche_su_hash_vecchi():
    """Il contraltare del test sopra: accettare hash vecchi non vuol dire
    accettare password sbagliate."""
    vecchio = argon2.PasswordHasher(memory_cost=8192, time_cost=2).hash("segreto")
    with pytest.raises(argon2.exceptions.VerifyMismatchError):
        auth_service.ph.verify(vecchio, "sbagliata")


def test_claude_md_dichiara_i_parametri_realmente_in_uso():
    """CLAUDE.md e il codice non devono divergere.

    E' lo stesso principio di `test_documentazione_onesta.py`: un .md che mente
    per mesi in silenzio e' peggio di un .md assente.
    """
    from pathlib import Path

    testo = Path(__file__).resolve().parents[1].joinpath("CLAUDE.md").read_text(
        encoding="utf-8"
    )
    riga = next((r for r in testo.splitlines() if "Argon2" in r), None)
    assert riga is not None, "CLAUDE.md non parla piu' di Argon2"
    assert f"m={PARAMETRI_ATTESI['memory_cost']}" in riga, riga
    assert f"t={PARAMETRI_ATTESI['time_cost']}" in riga, riga
    assert f"p={PARAMETRI_ATTESI['parallelism']}" in riga, (
        f"CLAUDE.md non dichiara il parallelism, che concorre al costo: {riga}"
    )
