"""Test per services/auth_service.py — Validazione password GDPR."""
import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.auth_service import valida_password_compliance
from services.auth_service import riepilogo_fatture_auto_da_ultimo_login


class TestValidaPasswordCompliance:
    """Verifica regole GDPR Art.32 + Garante Privacy Italia."""

    def test_password_valida(self):
        errori = valida_password_compliance("Ab1!defghi", "test@email.com")
        assert errori == []

    def test_password_troppo_corta(self):
        errori = valida_password_compliance("Ab1!defg", "test@email.com")
        assert any("10 caratteri" in e for e in errori)

    def test_password_vuota(self):
        errori = valida_password_compliance("", "test@email.com")
        assert any("obbligatoria" in e for e in errori)

    def test_password_comune(self):
        errori = valida_password_compliance("password", "test@email.com")
        assert any("comune" in e.lower() for e in errori)

    def test_password_con_email(self):
        """Email nella password → errore dati personali."""
        errori = valida_password_compliance("testuser1234!", "testuser@email.com")
        assert any("email" in e.lower() for e in errori)

    def test_password_con_nome_ristorante(self):
        errori = valida_password_compliance("ilpizzaiolo12!", "a@b.com", "Il Pizzaiolo")
        assert any("ristorante" in e.lower() for e in errori)

    def test_no_complessita(self):
        """Solo minuscole → manca complessità 3/4."""
        errori = valida_password_compliance("abcdefghijklmnop", "test@email.com")
        assert any("Aggiungi" in e for e in errori)

    def test_carattere_ripetuto(self):
        errori = valida_password_compliance("aaaaaaaaaa", "test@email.com")
        assert any("ripetuto" in e for e in errori)

    def test_sequenza_numerica(self):
        errori = valida_password_compliance("012345678901234", "test@email.com")
        assert any("sequenza" in e.lower() for e in errori)

    def test_password_forte(self):
        """Password complessa con tutti i requisiti → nessun errore."""
        errori = valida_password_compliance("Str0ng!P@ss2026", "user@domain.com")
        assert errori == []

    def test_nome_ristorante_corto_ignorato(self):
        """Nome ristorante < 4 char non dovrebbe generare falso positivo."""
        errori = valida_password_compliance("Abc123!@#xyz", "a@b.com", "Bar")
        assert not any("ristorante" in e.lower() for e in errori)


def _make_query_mock(data):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.in_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    # filter_active() aggiunge .is_("deleted_at", "null"): il mock deve
    # conoscerlo come il client vero, altrimenti i test passano solo finché
    # nessuno rispetta la regola soft-delete di CLAUDE.md §5.
    query.is_.return_value = query
    query.execute.return_value = MagicMock(data=data)
    return query


class TestRiepilogoFattureAuto:

    def test_include_needs_review_counts(self):
        upload_events_query = _make_query_mock([
            {
                'file_name': 'fattura-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-08T08:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_OK',
            }
        ])
        fatture_query = _make_query_mock([
            {
                'file_origine': 'fattura-a.xml',
                'fornitore': 'Test Fornitore',
                'data_documento': '2026-04-07',
                'totale_riga': 10.0,
                'created_at': '2026-04-08T08:00:00Z',
                'needs_review': True,
            },
            {
                'file_origine': 'fattura-a.xml',
                'fornitore': 'Test Fornitore',
                'data_documento': '2026-04-07',
                'totale_riga': 12.0,
                'created_at': '2026-04-08T08:00:01Z',
                'needs_review': False,
            },
        ])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [upload_events_query, fatture_query]

        summary = riepilogo_fatture_auto_da_ultimo_login(
            user_id='user-1',
            last_login_precedente='2026-04-07T08:00:00Z',
            login_at='2026-04-08T08:00:00Z',
            supabase_client=supabase_client,
        )

        assert summary['has_new'] is True
        assert summary['needs_review_count'] == 1
        assert summary['files_detail'][0]['needs_review_count'] == 1

    def test_ignore_manual_upload_events(self):
        upload_events_query = _make_query_mock([
            {
                'file_name': 'manuale-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-08T08:00:00Z',
                'details': {'source': 'manual_upload'},
                'status': 'SAVED_OK',
            }
        ])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [upload_events_query]

        summary = riepilogo_fatture_auto_da_ultimo_login(
            user_id='user-1',
            last_login_precedente='2026-04-07T08:00:00Z',
            login_at='2026-04-08T08:00:00Z',
            supabase_client=supabase_client,
        )

        assert summary['has_new'] is False
        assert summary['file_count'] == 0

    def test_counts_and_event_ids_grouped_by_file(self):
        upload_events_query = _make_query_mock([
            {
                'id': 101,
                'file_name': 'fattura-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-08T09:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_OK',
            },
            {
                'id': 99,
                'file_name': 'fattura-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-07T08:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_OK',
            },
            {
                'id': 102,
                'file_name': 'fattura-b.xml',
                'rows_saved': 1,
                'created_at': '2026-04-07T07:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_PARTIAL',
            },
        ])
        fatture_query = _make_query_mock([
            {
                'file_origine': 'fattura-a.xml',
                'fornitore': 'Fornitore A',
                'data_documento': '2026-04-08',
                'totale_riga': 10.0,
                'created_at': '2026-04-08T09:00:00Z',
                'needs_review': False,
            },
            {
                'file_origine': 'fattura-b.xml',
                'fornitore': 'Fornitore B',
                'data_documento': '2026-04-07',
                'totale_riga': 5.0,
                'created_at': '2026-04-07T07:00:00Z',
                'needs_review': False,
            },
        ])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [upload_events_query, fatture_query]

        summary = riepilogo_fatture_auto_da_ultimo_login(
            user_id='user-1',
            last_login_precedente='2026-04-07T08:00:00Z',
            login_at='2026-04-08T08:30:00Z',
            supabase_client=supabase_client,
        )

        assert summary['has_new'] is True
        assert summary['file_count'] == 2
        assert summary['total_pending_count'] == 2
        assert summary['new_count'] == 1
        assert summary['pending_count'] == 1

        file_a = next(f for f in summary['files_detail'] if f['file_name'] == 'fattura-a.xml')
        assert sorted(file_a['event_ids']) == [99, 101]


def _make_reset_supabase_mock(captured_updates):
    """Mock supabase per imposta_password_da_token: ritorna un utente valido con
    token non scaduto e cattura il payload passato a .update()."""
    from datetime import datetime, timezone, timedelta

    user = {
        'id': 'user-42',
        'email': 'mario@trattoria.it',
        'nome_ristorante': 'Trattoria',
        'attivo': False,
        'reset_code': 'tok-valid',
        'reset_expires': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        'password_hash': None,
    }

    table = MagicMock()
    table.select.return_value = table
    table.eq.return_value = table
    table.execute.return_value = MagicMock(data=[user])

    def _capture_update(payload):
        captured_updates.append(payload)
        upd = MagicMock()
        upd.eq.return_value = upd
        upd.execute.return_value = MagicMock(data=[user])
        return upd

    table.update.side_effect = _capture_update

    client = MagicMock()
    client.table.return_value = table
    return client


class TestImpostaPasswordConsentGDPR:
    """GDPR Art. 7(1): privacy_accepted_at va scritto SOLO con consenso reale."""

    def test_consenso_registrato_quando_accettato(self):
        from services.auth_service import imposta_password_da_token

        captured = []
        client = _make_reset_supabase_mock(captured)
        ok, _msg, _user = imposta_password_da_token(
            'tok-valid', 'Str0ng!P@ss2026', client, privacy_accepted=True
        )

        assert ok is True
        assert len(captured) == 1
        assert captured[0].get('privacy_accepted_at') is not None

    def test_consenso_non_registrato_quando_non_accettato(self):
        from services.auth_service import imposta_password_da_token

        captured = []
        client = _make_reset_supabase_mock(captured)
        ok, _msg, _user = imposta_password_da_token(
            'tok-valid', 'Str0ng!P@ss2026', client, privacy_accepted=False
        )

        assert ok is True
        assert len(captured) == 1
        # Nessuna prova di consenso falsa quando non è stato prestato.
        assert 'privacy_accepted_at' not in captured[0]

    def test_default_retrocompat_streamlit_registra_consenso(self):
        """Il flusso Streamlit chiama posizionalmente senza privacy_accepted:
        il default True preserva il comportamento storico (checkbox già validato)."""
        from services.auth_service import imposta_password_da_token

        captured = []
        client = _make_reset_supabase_mock(captured)
        ok, _msg, _user = imposta_password_da_token('tok-valid', 'Str0ng!P@ss2026', client)

        assert ok is True
        assert captured[0].get('privacy_accepted_at') is not None


def _make_rate_limit_client(fail_count, oldest_attempted_at=None):
    """Client Supabase mock per controlla_rate_limit.

    La prima execute() serve il count dei tentativi falliti nella finestra,
    la seconda (solo in lockout) il tentativo piu' vecchio.
    """
    client = MagicMock()
    query = MagicMock()
    for passthrough in ('select', 'eq', 'gte', 'order', 'limit', 'delete', 'lt'):
        getattr(query, passthrough).return_value = query
    risposte = [SimpleNamespace(count=fail_count, data=[])]
    if oldest_attempted_at is not None:
        risposte.append(
            SimpleNamespace(count=None, data=[{'attempted_at': oldest_attempted_at}])
        )
    risposte.append(SimpleNamespace(count=None, data=[]))
    query.execute.side_effect = risposte
    client.table.return_value = query
    return client


class TestControllaRateLimit:
    """Regola CLAUDE.md: 5 tentativi falliti -> blocco 15 minuti.

    Prima di questi test la regola non era coperta da nessun test della suite:
    era verificabile solo leggendo il sorgente.
    """

    def test_sotto_soglia_non_blocca(self):
        from services.auth_service import controlla_rate_limit

        bloccato, minuti = controlla_rate_limit(
            'utente@test.it', _make_rate_limit_client(fail_count=4)
        )

        assert bloccato is False
        assert minuti == 0

    def test_alla_soglia_blocca(self):
        """Il 5o tentativo fallito fa scattare il lockout (>=, non >)."""
        from services.auth_service import controlla_rate_limit

        appena_fallito = datetime.now(timezone.utc).isoformat()
        bloccato, minuti = controlla_rate_limit(
            'utente@test.it',
            _make_rate_limit_client(fail_count=5, oldest_attempted_at=appena_fallito),
        )

        assert bloccato is True
        # Tentativo piu' vecchio appena registrato -> lockout quasi pieno.
        # 16 e non 15: il calcolo arrotonda per eccesso (int(sec/60) + 1) per
        # non annunciare all'utente meno attesa di quella reale.
        assert 15 <= minuti <= 16

    def test_lockout_quasi_scaduto_riporta_pochi_minuti(self):
        """I minuti rimanenti si calcolano dal tentativo piu' vecchio, non fissi a 15."""
        from services.auth_service import controlla_rate_limit

        quasi_scaduto = (
            datetime.now(timezone.utc) - timedelta(minutes=13)
        ).isoformat()
        bloccato, minuti = controlla_rate_limit(
            'utente@test.it',
            _make_rate_limit_client(fail_count=5, oldest_attempted_at=quasi_scaduto),
        )

        assert bloccato is True
        assert minuti <= 3

    def test_email_normalizzata_lowercase(self):
        """CLAUDE.md: i confronti email sono sempre .strip().lower()."""
        from services.auth_service import controlla_rate_limit

        client = _make_rate_limit_client(fail_count=0)
        controlla_rate_limit('  Utente@TEST.it  ', client)

        chiamate_email = [
            c.args[1] for c in client.table.return_value.eq.call_args_list
            if c.args and c.args[0] == 'email'
        ]
        assert chiamate_email, 'nessun filtro per email applicato'
        assert all(e == 'utente@test.it' for e in chiamate_email)

    def test_errore_db_non_apre_il_login(self):
        """Fail-closed: se il DB non risponde si solleva, non si restituisce
        'non bloccato' (che lascerebbe passare tentativi illimitati).

        `_is_connectivity_error` fa isinstance() sulle eccezioni di requests:
        dal 28/8/2026 il conftest non mocka piu' requests, quindi sono classi
        vere e il percorso e' quello di produzione.
        """
        from services.auth_service import (
            controlla_rate_limit,
            AuthServiceUnavailableError,
        )

        client = MagicMock()
        client.table.side_effect = RuntimeError('db giu')

        with pytest.raises(AuthServiceUnavailableError):
            controlla_rate_limit('utente@test.it', client)


class TestVerifyAndMigratePassword:
    """Verifica Argon2 al login, con hash REALI.

    Non si patcha `ph.verify`: si genera l'hash con `ph.hash()` e si verifica
    l'esito booleano. Cosi' il test misura la verifica vera (m=65536, t=3,
    parametri intoccabili — CLAUDE.md §Sicurezza) invece di limitarsi a
    constatare che un mock e' stato chiamato. Costo ~60ms per hash.
    `patch.object(ph, 'verify')` non sarebbe comunque possibile: PasswordHasher
    ha __slots__ e i suoi attributi sono read-only.
    """

    def test_password_corretta_accettata(self):
        from services import auth_service

        hash_reale = auth_service.ph.hash('giusta')
        ok = auth_service.verify_and_migrate_password(
            {'id': 'u1', 'password_hash': hash_reale}, 'giusta'
        )

        assert ok is True

    def test_password_sbagliata_rifiutata(self):
        """Argon2 segnala il mismatch sollevando: deve tradursi in False."""
        from services import auth_service

        hash_reale = auth_service.ph.hash('giusta')
        ok = auth_service.verify_and_migrate_password(
            {'id': 'u1', 'password_hash': hash_reale}, 'sbagliata'
        )

        assert ok is False

    def test_hash_vuoto_rifiutato(self):
        """Nessun hash memorizzato non deve mai valere come login riuscito."""
        from services import auth_service

        assert auth_service.verify_and_migrate_password({'id': 'u1'}, 'qualsiasi') is False
        assert auth_service.verify_and_migrate_password(
            {'id': 'u1', 'password_hash': '   '}, 'qualsiasi'
        ) is False


class TestBridgeSupabaseAuthNonAvvelenaIlSingleton:
    """Il bridge Supabase Auth non deve mai chiamare sign_in_with_password sul
    client service_role condiviso.

    sign_in_with_password sostituisce il token del client con il JWT dell'utente.
    Siccome get_supabase_client() e' un singleton cachato per processo, da quel
    momento ogni query del worker gira come 'authenticated' invece che
    'service_role': sintomo osservato "permission denied for table sessioni"
    subito dopo un login riuscito (login rotto in locale, 5/8/2026).
    """

    def test_senza_anon_key_il_bridge_si_salta(self):
        """Niente anon client -> None, senza toccare il client service_role."""
        from services import auth_service

        service_role_client = MagicMock()

        with patch.object(auth_service, '_get_supabase_anon_client', return_value=None), \
             patch.object(auth_service, '_supabase_auth_bridge_disabilitato', return_value=False):
            esito = auth_service._tenta_login_supabase_auth(
                'a@b.com', 'pw', service_role_client
            )

        assert esito is None
        service_role_client.auth.sign_in_with_password.assert_not_called()

    def test_con_anon_key_usa_solo_il_client_anon(self):
        """Il sign_in avviene sull'anon client, mai su quello service_role."""
        from services import auth_service

        service_role_client = MagicMock()
        anon_client = MagicMock()
        anon_client.auth.sign_in_with_password.return_value = SimpleNamespace(
            session=SimpleNamespace(access_token='at', refresh_token='rt')
        )

        with patch.object(auth_service, '_get_supabase_anon_client', return_value=anon_client), \
             patch.object(auth_service, '_supabase_auth_bridge_disabilitato', return_value=False):
            esito = auth_service._tenta_login_supabase_auth(
                'a@b.com', 'pw', service_role_client
            )

        assert esito is not None
        anon_client.auth.sign_in_with_password.assert_called_once()
        service_role_client.auth.sign_in_with_password.assert_not_called()


class TestGuardiaAuthHeaderServiceRole:
    """get_supabase_client() risana l'Authorization header se qualcuno lo sostituisce."""

    def test_header_avvelenato_viene_ripristinato(self):
        import services

        atteso = 'Bearer SERVICE_ROLE_KEY'
        client = MagicMock()
        client.options.headers = {'Authorization': 'Bearer JWT_UTENTE'}
        client.postgrest.session.headers = {'Authorization': 'Bearer JWT_UTENTE'}

        services._riallinea_auth_header(client, 'SERVICE_ROLE_KEY')

        assert client.options.headers['Authorization'] == atteso
        assert client.postgrest.session.headers['Authorization'] == atteso

    def test_header_gia_corretto_resta_invariato(self):
        import services

        atteso = 'Bearer SERVICE_ROLE_KEY'
        client = MagicMock()
        client.options.headers = {'Authorization': atteso}
        client.postgrest.session.headers = {'Authorization': atteso}

        services._riallinea_auth_header(client, 'SERVICE_ROLE_KEY')

        assert client.options.headers['Authorization'] == atteso
        assert client.postgrest.session.headers['Authorization'] == atteso
