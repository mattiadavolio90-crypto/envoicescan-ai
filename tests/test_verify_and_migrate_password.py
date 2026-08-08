"""Test di services.auth_service.verify_and_migrate_password.

Verifica password con supporto Argon2 (formato moderno) e fallback SHA256
legacy con migrazione automatica: se un utente ha ancora un hash SHA256 (da
prima dell'introduzione di Argon2) e la password è corretta, la funzione
riscrive silenziosamente password_hash sul DB in formato Argon2.

Il ramo Argon2 (righe 657-663) era già coperto da altri test del progetto.
Il ramo SHA256 legacy + migrazione (665-685) era a 0% (audit ONEFLUX §2,
8/8/2026): nessun test verificava né il matching SHA256, né che la
migrazione scriva l'hash giusto sulla riga giusta, né che un fallimento
della migrazione non faccia perdere l'accesso all'utente (la password era
comunque corretta).
"""
import hashlib
from unittest.mock import MagicMock, patch

from services.auth_service import verify_and_migrate_password


# `argon2` è mockato globalmente in conftest.py (installato davvero, ma
# oscurato per l'ambiente test): niente hashing reale disponibile qui. I test
# Argon2 verificano quindi il WIRING (ph.verify chiamato/non chiamato,
# risultato propagato), non un vero round-trip di hashing — quello vive nei
# test dedicati ad argon2 stesso, non nel dominio di questo file.


def _sha256_user(password: str, user_id: str = "user-1") -> dict:
    return {
        "id": user_id,
        "password_hash": hashlib.sha256(password.encode()).hexdigest(),
    }


# ─── stored vuoto / assente ──────────────────────────────────────────────────

def test_password_hash_assente_ritorna_false():
    assert verify_and_migrate_password({"id": "user-1"}, "qualsiasi") is False


def test_password_hash_vuoto_ritorna_false():
    assert verify_and_migrate_password({"id": "user-1", "password_hash": "  "}, "x") is False


# ─── Ramo Argon2 (già coperto altrove, verificato qui per completezza) ──────────

def test_argon2_password_corretta():
    user = {"id": "user-1", "password_hash": "$argon2id$fake-hash"}
    with patch("services.auth_service.ph") as mock_ph:
        mock_ph.verify.return_value = None  # ph.verify non solleva → password corretta
        assert verify_and_migrate_password(user, "Segreta123!") is True
    mock_ph.verify.assert_called_once_with("$argon2id$fake-hash", "Segreta123!")


def test_argon2_password_sbagliata():
    user = {"id": "user-1", "password_hash": "$argon2id$fake-hash"}
    with patch("services.auth_service.ph") as mock_ph:
        mock_ph.verify.side_effect = Exception("mismatch")
        assert verify_and_migrate_password(user, "Sbagliata999!") is False


# ─── Ramo SHA256 legacy: match + migrazione ─────────────────────────────────

def test_sha256_password_corretta_migra_e_ritorna_true():
    user = _sha256_user("VecchiaPass1!", user_id="user-42")
    sb = MagicMock()
    with patch("services.get_supabase_client", return_value=sb), \
         patch("services.auth_service.ph") as mock_ph:
        mock_ph.hash.return_value = "$argon2id$nuovo-hash"
        ok = verify_and_migrate_password(user, "VecchiaPass1!")

    assert ok is True
    # l'hash nuovo è generato dalla stessa password appena verificata, non da stored
    mock_ph.hash.assert_called_once_with("VecchiaPass1!")
    sb.table.assert_called_with("users")
    update_call = sb.table.return_value.update
    update_call.assert_called_once_with({"password_hash": "$argon2id$nuovo-hash"})
    # aggiornata la riga dell'utente giusto, non un altro
    sb.table.return_value.update.return_value.eq.assert_called_once_with("id", "user-42")


def test_sha256_password_sbagliata_non_migra_ritorna_false():
    user = _sha256_user("VecchiaPass1!")
    sb = MagicMock()
    with patch("services.get_supabase_client", return_value=sb):
        ok = verify_and_migrate_password(user, "PasswordErrata!")

    assert ok is False
    sb.table.return_value.update.assert_not_called()


def test_sha256_migrazione_fallisce_ma_password_corretta_ritorna_true():
    """Se la UPDATE fallisce (es. rete, RLS), l'utente non deve perdere
    l'accesso: la password era comunque corretta. Resta con l'hash SHA256
    finché non riprova (comportamento by-design, righe 679-680)."""
    user = _sha256_user("VecchiaPass1!")
    sb = MagicMock()
    sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError("DB down")
    with patch("services.get_supabase_client", return_value=sb):
        ok = verify_and_migrate_password(user, "VecchiaPass1!")

    assert ok is True


def test_sha256_get_supabase_client_fallisce_password_corretta_ritorna_true():
    """get_supabase_client fallisce DENTRO il try di migrazione (righe
    674-680, non quello esterno 666-685): stesso comportamento della
    migrazione che fallisce per altri motivi. La password era corretta,
    l'utente non deve perdere l'accesso — resta con l'hash SHA256 finché
    la migrazione non riesce in un login successivo."""
    user = _sha256_user("VecchiaPass1!")
    with patch("services.get_supabase_client", side_effect=RuntimeError("no client")):
        ok = verify_and_migrate_password(user, "VecchiaPass1!")

    assert ok is True


def test_sha256_password_non_stringa_fallisce_chiuso():
    """password.encode() (riga 671) solleva se password non è una stringa
    (es. None passato per errore da un chiamante): il try esterno lo
    cattura e la funzione fallisce chiuso, non propaga l'eccezione fino al
    login."""
    user = _sha256_user("VecchiaPass1!")
    sb = MagicMock()
    with patch("services.get_supabase_client", return_value=sb):
        ok = verify_and_migrate_password(user, None)

    assert ok is False
