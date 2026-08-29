"""Il login deve riportare gli hash Argon2 deboli ai parametri correnti.

Misurato sul DB live il 29/8/2026: 6 hash a `m=65536,t=3,p=4` e **1 a `p=1`**,
di un utente che accede regolarmente (ultimo accesso il 28/8). I parametri
stanno dentro l'hash, quindi `verify()` continuava ad accettarlo e nulla lo
aggiornava: `check_needs_rehash` esisteva solo dentro un commento.

Il ramo SHA256 migrava gia' correttamente; questi test coprono il ramo Argon2,
che era l'unico scoperto.
"""

from unittest.mock import MagicMock, patch

import argon2
import pytest

import services.auth_service as auth_service


PASSWORD = "una-password-qualsiasi"


def _hash_debole(password=PASSWORD):
    """Hash valido ma con parametri sotto lo standard corrente (come il p=1 reale)."""
    return argon2.PasswordHasher(
        memory_cost=8192, time_cost=2, parallelism=1
    ).hash(password)


def _hash_corrente(password=PASSWORD):
    return auth_service.ph.hash(password)


def _supabase_finto():
    sb = MagicMock()
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    return sb


def test_hash_debole_viene_riscritto_al_login():
    sb = _supabase_finto()
    record = {'id': 'u1', 'password_hash': _hash_debole()}

    with patch('services.get_supabase_client', return_value=sb):
        assert auth_service.verify_and_migrate_password(record, PASSWORD) is True

    sb.table.assert_called_with('users')
    update = sb.table.return_value.update
    assert update.called, "l'hash debole doveva essere riscritto"
    nuovo = update.call_args[0][0]['password_hash']
    assert 'm=65536,t=3,p=4' in nuovo


def test_hash_gia_corrente_non_viene_riscritto():
    """Nessuna scrittura inutile a ogni login."""
    sb = _supabase_finto()
    record = {'id': 'u1', 'password_hash': _hash_corrente()}

    with patch('services.get_supabase_client', return_value=sb):
        assert auth_service.verify_and_migrate_password(record, PASSWORD) is True

    assert not sb.table.return_value.update.called


def test_password_sbagliata_non_riscrive_nulla():
    """Il re-hash deve avvenire solo DOPO una verifica riuscita."""
    sb = _supabase_finto()
    record = {'id': 'u1', 'password_hash': _hash_debole()}

    with patch('services.get_supabase_client', return_value=sb):
        assert auth_service.verify_and_migrate_password(record, "sbagliata") is False

    assert not sb.table.return_value.update.called


def test_errore_di_scrittura_non_impedisce_il_login():
    """Best-effort: se il DB non risponde, l'utente entra lo stesso."""
    sb = MagicMock()
    sb.table.side_effect = RuntimeError("DB irraggiungibile")
    record = {'id': 'u1', 'password_hash': _hash_debole()}

    with patch('services.get_supabase_client', return_value=sb):
        assert auth_service.verify_and_migrate_password(record, PASSWORD) is True


def test_il_re_hash_verifica_ancora_la_password_originale():
    """L'hash riscritto deve restare valido per la stessa password."""
    sb = _supabase_finto()
    record = {'id': 'u1', 'password_hash': _hash_debole()}

    with patch('services.get_supabase_client', return_value=sb):
        auth_service.verify_and_migrate_password(record, PASSWORD)

    nuovo = sb.table.return_value.update.call_args[0][0]['password_hash']
    auth_service.ph.verify(nuovo, PASSWORD)  # non solleva
    with pytest.raises(Exception):
        auth_service.ph.verify(nuovo, "altra-password")
