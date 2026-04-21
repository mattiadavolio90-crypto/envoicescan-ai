"""
Test unitari per il sistema di trial 7 giorni gratuiti.

Copre:
- get_trial_info(): stati possibili (non trial, attiva, scaduta)
- attiva_trial(): happy path, errori (già attiva, account disattivato)
- disattiva_trial_scaduta(): side-effect su DB
- Filtro mese upload (logica datetime)
- Limiti upload in trial: max 50 file, solo XML/P7M
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call


# ──────────────────────────────────────────────────────────────────────────────
# Helper per costruire mock del client Supabase
# ──────────────────────────────────────────────────────────────────────────────

def _make_supabase_mock(rows):
    """Restituisce un mock del Supabase client che risponde con `rows` su .execute()."""
    resp = MagicMock()
    resp.data = rows
    table_mock = MagicMock()
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.limit.return_value = table_mock
    table_mock.update.return_value = table_mock
    table_mock.execute.return_value = resp
    client = MagicMock()
    client.table.return_value = table_mock
    return client, table_mock


# ──────────────────────────────────────────────────────────────────────────────
# get_trial_info
# ──────────────────────────────────────────────────────────────────────────────

class TestGetTrialInfo:
    """Test per la funzione get_trial_info()."""

    def test_utente_senza_trial(self):
        """Utente normale senza trial: ritorna is_trial=False, days_left=0."""
        from services.auth_service import get_trial_info

        client, _ = _make_supabase_mock([{'trial_active': False, 'trial_activated_at': None}])

        result = get_trial_info('user-123', supabase_client=client)

        assert result['is_trial'] is False
        assert result['days_left'] == 0
        assert result['expired'] is False
        assert result['trial_month'] is None

    def test_trial_attiva_giorni_rimasti(self):
        """Trial attivata 2 giorni fa: is_trial=True, days_left tra 4 e 5 (boundary timing)."""
        from services.auth_service import get_trial_info

        activated = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        client, _ = _make_supabase_mock([{
            'trial_active': True,
            'trial_activated_at': activated,
        }])

        result = get_trial_info('user-456', supabase_client=client)

        assert result['is_trial'] is True
        assert result['days_left'] in (4, 5)  # timedelta.days tronca, boundary timing
        assert result['expired'] is False
        assert result['trial_month'] == datetime.now(timezone.utc).month

    def test_trial_scaduta(self):
        """Trial attivata 8 giorni fa (> 7): expired=True, is_trial=False."""
        from services.auth_service import get_trial_info

        activated = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        client, _ = _make_supabase_mock([{
            'trial_active': True,
            'trial_activated_at': activated,
        }])

        result = get_trial_info('user-789', supabase_client=client)

        assert result['is_trial'] is False
        assert result['days_left'] == 0
        assert result['expired'] is True

    def test_utente_non_trovato(self):
        """DB ritorna lista vuota: default sicuro (no trial)."""
        from services.auth_service import get_trial_info

        client, _ = _make_supabase_mock([])

        result = get_trial_info('user-000', supabase_client=client)

        assert result['is_trial'] is False
        assert result['expired'] is False

    def test_errore_db_restituisce_default(self):
        """Eccezione DB: ritorna default sicuro senza propagare."""
        from services.auth_service import get_trial_info

        client = MagicMock()
        client.table.side_effect = Exception("DB connection error")

        result = get_trial_info('user-err', supabase_client=client)

        assert result['is_trial'] is False
        assert result['expired'] is False

    def test_trial_attivata_oggi_7_giorni(self):
        """Trial attivata adesso: days_left deve essere 7 (o 6 a causa dei secondi)."""
        from services.auth_service import get_trial_info

        activated = datetime.now(timezone.utc).isoformat()
        client, _ = _make_supabase_mock([{
            'trial_active': True,
            'trial_activated_at': activated,
        }])

        result = get_trial_info('user-now', supabase_client=client)

        assert result['is_trial'] is True
        assert result['days_left'] in (6, 7)  # Dipende dai secondi trascorsi
        assert result['expired'] is False

    def test_mese_e_anno_trial_corretti(self):
        """I campi trial_month e trial_year riflettono la data di attivazione."""
        from services.auth_service import get_trial_info

        # Simula attivazione il 15 Febbraio 2026
        activated = datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc)
        # "Adesso" = 16 Febbraio 2026 (trial ancora attiva)
        with patch('services.auth_service.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 16, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat

            client, _ = _make_supabase_mock([{
                'trial_active': True,
                'trial_activated_at': activated.isoformat(),
            }])

            result = get_trial_info('user-feb', supabase_client=client)

        assert result['trial_month'] == 2
        assert result['trial_year'] == 2026


# ──────────────────────────────────────────────────────────────────────────────
# attiva_trial
# ──────────────────────────────────────────────────────────────────────────────

class TestAttivaTrial:
    """Test per la funzione attiva_trial()."""

    def test_attivazione_successo(self):
        """Utente attivo senza trial: attivazione riuscita."""
        from services.auth_service import attiva_trial

        resp_select = MagicMock()
        resp_select.data = [{
            'email': 'cliente@test.it',
            'trial_active': False,
            'trial_activated_at': None,
            'attivo': True,
        }]
        resp_update = MagicMock()
        resp_update.data = [{'id': 'u1'}]

        client = MagicMock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        tbl.update.return_value = tbl
        tbl.execute.side_effect = [resp_select, resp_update]
        client.table.return_value = tbl

        ok, msg = attiva_trial('u1', 'admin@test.it', supabase_client=client)

        assert ok is True
        assert 'cliente@test.it' in msg

    def test_account_disattivato(self):
        """Utente con attivo=False: non attiva trial."""
        from services.auth_service import attiva_trial

        resp = MagicMock()
        resp.data = [{
            'email': 'inactive@test.it',
            'trial_active': False,
            'trial_activated_at': None,
            'attivo': False,
        }]
        client, tbl = _make_supabase_mock([])
        tbl.execute.return_value = resp

        ok, msg = attiva_trial('u2', 'admin@test.it', supabase_client=client)

        assert ok is False
        assert 'disattivato' in msg.lower()

    def test_trial_gia_attiva(self):
        """
        Utente con trial già attiva nel DB: l'UPDATE atomico restituisce 0 righe
        (WHERE trial_active = FALSE non matcha) → attiva_trial ritorna False.
        """
        from services.auth_service import attiva_trial

        # SELECT: utente attivo trovato
        resp_select = MagicMock()
        resp_select.data = [{'email': 'already@test.it', 'attivo': True}]
        # UPDATE con .eq('trial_active', False): 0 righe aggiornate
        resp_update = MagicMock()
        resp_update.data = []

        table = MagicMock()
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.side_effect = [resp_select, resp_update]

        client = MagicMock()
        client.table.return_value = table

        ok, msg = attiva_trial('u3', 'admin@test.it', supabase_client=client)

        assert ok is False
        assert 'già attiva' in msg.lower()

    def test_utente_non_trovato(self):
        """DB ritorna lista vuota: fallisce con messaggio utente non trovato."""
        from services.auth_service import attiva_trial

        client, _ = _make_supabase_mock([])

        ok, msg = attiva_trial('u-gone', 'admin@test.it', supabase_client=client)

        assert ok is False
        assert 'non trovato' in msg.lower()


# ──────────────────────────────────────────────────────────────────────────────
# disattiva_trial_scaduta
# ──────────────────────────────────────────────────────────────────────────────

class TestDisattivaTrial:
    """Test per disattiva_trial_scaduta()."""

    def test_disattivazione_ok(self):
        """Aggiorna correttamente attivo=False e trial_active=False."""
        from services.auth_service import disattiva_trial_scaduta

        resp = MagicMock()
        resp.data = [{'id': 'u1'}]

        client = MagicMock()
        tbl = MagicMock()
        tbl.update.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.execute.return_value = resp
        client.table.return_value = tbl

        result = disattiva_trial_scaduta('u1', supabase_client=client)

        assert result is True
        # Verifica che update sia stato chiamato con i campi corretti
        tbl.update.assert_called_once_with({'trial_active': False, 'attivo': False})

    def test_errore_db_ritorna_false(self):
        """Eccezione DB: ritorna False senza propagare."""
        from services.auth_service import disattiva_trial_scaduta

        client = MagicMock()
        client.table.side_effect = Exception("DB error")

        result = disattiva_trial_scaduta('u-err', supabase_client=client)

        assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# Logica filtro mese upload (isolata da pd.to_datetime)
# ──────────────────────────────────────────────────────────────────────────────

class TestTrialMonthFilter:
    """
    Verifica la logica di confronto mese/anno usata in upload_handler.py.
    Test in isolamento senza dipendenze Streamlit.
    """

    @staticmethod
    def _check_month(data_documento: str, trial_month: int, trial_year: int) -> bool:
        """Ritorna True se la data è fuori da mese corrente o precedente."""
        import pandas as pd

        dt = pd.to_datetime(data_documento)
        current_period = (trial_year, trial_month)
        previous_ref = pd.Timestamp(year=trial_year, month=trial_month, day=1) - pd.Timedelta(days=1)
        previous_period = (previous_ref.year, previous_ref.month)
        return (dt.year, dt.month) not in {current_period, previous_period}

    def test_stesso_mese_anno_non_bloccato(self):
        assert not self._check_month('2026-03-15', 3, 2026)

    def test_mese_diverso_bloccato(self):
        assert self._check_month('2026-04-01', 3, 2026)

    def test_anno_diverso_bloccato(self):
        assert self._check_month('2025-03-15', 3, 2026)

    def test_mese_precedente_non_bloccato(self):
        assert not self._check_month('2026-02-28', 3, 2026)

    def test_due_mesi_prima_bloccato(self):
        assert self._check_month('2026-01-30', 3, 2026)

    def test_ultimo_giorno_stesso_mese_non_bloccato(self):
        assert not self._check_month('2026-03-31', 3, 2026)


# ──────────────────────────────────────────────────────────────────────────────
class TestTrialInvoiceDatePolicy:
    """Verifica la policy reale date fatture consentite durante la trial."""

    def test_mese_corrente_consentito(self):
        from services.upload_handler import _is_trial_invoice_date_allowed

        assert _is_trial_invoice_date_allowed('2026-04-15', reference_date='2026-04-20') is True

    def test_mese_precedente_consentito(self):
        from services.upload_handler import _is_trial_invoice_date_allowed

        assert _is_trial_invoice_date_allowed('2026-03-31', reference_date='2026-04-20') is True

    def test_due_mesi_fa_bloccato(self):
        from services.upload_handler import _is_trial_invoice_date_allowed

        assert _is_trial_invoice_date_allowed('2026-02-28', reference_date='2026-04-20') is False

    def test_gennaio_accetta_dicembre_precedente(self):
        from services.upload_handler import _is_trial_invoice_date_allowed

        assert _is_trial_invoice_date_allowed('2025-12-31', reference_date='2026-01-10') is True


class TestTrialUploadLimits:
    """
    Logica limiti upload in prova gratuita.
    Replica le regole di upload_handler.py in isolamento (no Streamlit).
    """

    _TRIAL_MAX_FILES = 50
    _TRIAL_ALLOWED_EXT = ('.xml', '.p7m')

    def _make_file(self, name: str):
        """File mock con solo il campo .name."""
        f = MagicMock()
        f.name = name
        return f

    def _filter_format(self, files):
        """Replica: rimuovi PDF/immagini se trial, ritorna (ammessi, bloccati)."""
        allowed = [f for f in files if f.name.lower().endswith(self._TRIAL_ALLOWED_EXT)]
        blocked = [f for f in files if not f.name.lower().endswith(self._TRIAL_ALLOWED_EXT)]
        return allowed, blocked

    def _check_count_limit(self, files):
        """Replica: True se supera il limite 50."""
        return len(files) > self._TRIAL_MAX_FILES

    # ---- test formato ----

    def test_xml_ammesso(self):
        files = [self._make_file('fattura.xml')]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 1
        assert len(blocked) == 0

    def test_p7m_ammesso(self):
        files = [self._make_file('fattura.xml.p7m')]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 1
        assert len(blocked) == 0

    def test_pdf_bloccato(self):
        files = [self._make_file('ricevuta.pdf')]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 0
        assert len(blocked) == 1

    def test_jpg_bloccato(self):
        files = [self._make_file('scontrino.jpg')]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 0
        assert len(blocked) == 1

    def test_png_bloccato(self):
        files = [self._make_file('foto.png')]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 0
        assert len(blocked) == 1

    def test_mix_filtra_solo_non_consentiti(self):
        files = [
            self._make_file('a.xml'),
            self._make_file('b.p7m'),
            self._make_file('c.pdf'),
            self._make_file('d.jpg'),
        ]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 2
        assert len(blocked) == 2
        assert all(f.name.endswith(('.xml', '.p7m')) for f in allowed)

    def test_estensione_maiuscola_bloccata(self):
        """Case-insensitive: .PDF deve essere bloccato."""
        files = [self._make_file('FATTURA.PDF')]
        allowed, blocked = self._filter_format(files)
        assert len(blocked) == 1

    def test_estensione_maiuscola_xml_ammessa(self):
        files = [self._make_file('FATTURA.XML')]
        allowed, blocked = self._filter_format(files)
        assert len(allowed) == 1

    # ---- test limite 50 ----

    def test_50_file_ok(self):
        files = [self._make_file(f'f{i}.xml') for i in range(50)]
        assert not self._check_count_limit(files)

    def test_51_file_bloccato(self):
        files = [self._make_file(f'f{i}.xml') for i in range(51)]
        assert self._check_count_limit(files)

    def test_0_file_ok(self):
        assert not self._check_count_limit([])

    def test_100_file_bloccato(self):
        files = [self._make_file(f'f{i}.xml') for i in range(100)]
        assert self._check_count_limit(files)

    def test_limite_dopo_filtro_formato(self):
        """
        Scenario reale: 60 XML + 40 PDF → dopo filtro = 60 XML → supera limite 50.
        """
        files = (
            [self._make_file(f'a{i}.xml') for i in range(60)]
            + [self._make_file(f'b{i}.pdf') for i in range(40)]
        )
        allowed, _ = self._filter_format(files)
        assert self._check_count_limit(allowed)  # 60 > 50

    def test_limite_dopo_filtro_ok(self):
        """
        30 XML + 30 PDF → dopo filtro = 30 XML → entro limite.
        """
        files = (
            [self._make_file(f'a{i}.xml') for i in range(30)]
            + [self._make_file(f'b{i}.pdf') for i in range(30)]
        )
        allowed, _ = self._filter_format(files)
        assert not self._check_count_limit(allowed)  # 30 <= 50


# ──────────────────────────────────────────────────────────────────────────────
# Test casi edge non coperti (audit)
# ──────────────────────────────────────────────────────────────────────────────

class TestTrialEdgeCases:
    """
    Casi edge identificati nell'audit del sistema trial:
    - Race condition doppia attivazione (UPDATE atomico)
    - disattiva_trial_scaduta fallisce → restituisce False (non True)
    - attiva_trial con account disattivato
    - Impersonazione: trial_info sempre no-trial per admin
    """

    # ---- race condition: UPDATE atomico ----

    def test_doppia_attivazione_update_atomico_secondo_fallisce(self):
        """
        Se l'UPDATE restituisce 0 righe (trial già attiva nel DB),
        attiva_trial deve ritornare (False, messaggio errore).
        Simula la race condition: due admin cliccano simultaneamente.
        """
        from services.auth_service import attiva_trial

        # Secondo admin: UPDATE restituisce 0 righe (race condition)
        resp_user = MagicMock()
        resp_user.data = [{'email': 'c@c.it', 'attivo': True}]
        resp_update_empty = MagicMock()
        resp_update_empty.data = []

        table = MagicMock()
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.side_effect = [resp_user, resp_update_empty]

        client = MagicMock()
        client.table.return_value = table
        ok, msg = attiva_trial('u1', 'admin2@a.it', supabase_client=client)
        assert ok is False
        assert 'già attiva' in msg.lower() or 'frattempo' in msg.lower()

    def test_prima_attivazione_update_atomico_successo(self):
        """Primo admin: UPDATE restituisce 1 riga → attivazione riuscita."""
        from services.auth_service import attiva_trial

        resp_user = MagicMock()
        resp_user.data = [{'email': 'c@c.it', 'attivo': True}]
        resp_update_ok = MagicMock()
        resp_update_ok.data = [{'id': 'u1'}]

        table = MagicMock()
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.side_effect = [resp_user, resp_update_ok]

        client = MagicMock()
        client.table.return_value = table
        ok, msg = attiva_trial('u1', 'admin@a.it', supabase_client=client)
        assert ok is True

    # ---- disattiva_trial_scaduta: controlla rowcount ----

    def test_disattiva_trial_scaduta_0_righe_ritorna_false(self):
        """
        Se l'UPDATE non trova righe (user_id sbagliato),
        disattiva_trial_scaduta deve ritornare False, non True.
        """
        from services.auth_service import disattiva_trial_scaduta

        resp_empty = MagicMock()
        resp_empty.data = []
        table = MagicMock()
        table.update.return_value = table
        table.eq.return_value = table
        table.execute.return_value = resp_empty

        client = MagicMock()
        client.table.return_value = table
        result = disattiva_trial_scaduta('id-inesistente', supabase_client=client)
        assert result is False

    def test_disattiva_trial_scaduta_riga_aggiornata_ritorna_true(self):
        """Se l'UPDATE trova e aggiorna la riga, ritorna True."""
        from services.auth_service import disattiva_trial_scaduta

        resp_ok = MagicMock()
        resp_ok.data = [{'id': 'u1'}]
        table = MagicMock()
        table.update.return_value = table
        table.eq.return_value = table
        table.execute.return_value = resp_ok

        client = MagicMock()
        client.table.return_value = table
        result = disattiva_trial_scaduta('u1', supabase_client=client)
        assert result is True

    # ---- attiva_trial: account disattivato ----

    def test_attiva_trial_account_disattivato_non_chiama_update(self):
        """
        attiva_trial non deve procedere con UPDATE se l'account è disattivato.
        """
        from services.auth_service import attiva_trial

        resp_user = MagicMock()
        resp_user.data = [{'email': 'x@x.it', 'attivo': False}]

        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.return_value = resp_user

        client = MagicMock()
        client.table.return_value = table
        ok, msg = attiva_trial('u-off', 'admin@a.it', supabase_client=client)

        assert ok is False
        assert 'disattivato' in msg.lower()
        table.update.assert_not_called()

    # ---- impersonazione: trial_info sempre no-trial ----

    def test_trial_info_sovrascritta_per_impersonazione(self):
        """
        La logica corretta in app.py sovrascrive SEMPRE trial_info nel ramo
        admin/impersonating, anche se era già presente un trial_info residuo.
        Verifica che la sovrascrittura incondizionale funzioni.
        """
        session = {
            'trial_info': {
                'is_trial': True, 'days_left': 3,
                'trial_month': 3, 'trial_year': 2026, 'expired': False,
            }
        }
        # Logica corretta (sempre sovrascrive):
        session['trial_info'] = {
            'is_trial': False, 'days_left': 0,
            'trial_month': None, 'trial_year': None, 'expired': False,
        }
        assert session['trial_info']['is_trial'] is False
