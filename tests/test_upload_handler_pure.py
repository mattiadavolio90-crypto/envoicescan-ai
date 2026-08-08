"""Test per utils/upload_handler.py — funzioni pure senza Streamlit/Supabase."""
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

import services.upload_handler as uh
# Importa solo funzioni pure (senza side effects Streamlit/Supabase)
from services.upload_handler import (
    _acquire_upload_lock,
    _build_policy_block_messages,
    _duplicate_reason_for_ui,
    _format_saved_ok_date,
    _get_just_uploaded_for_current_ristorante,
    _get_policy_block_kind,
    _is_fallback_servizi_da_riclassificare,
    _is_trial_invoice_date_allowed,
    _make_problematic_upload_entry,
    _release_upload_lock,
    _should_skip_post_upload_ai_for_row,
)


class TestIsTrialInvoiceDateAllowed:
    def test_current_month_is_allowed(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-05-01', reference_date=ref) is True

    def test_last_day_current_month_is_allowed(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-05-31', reference_date=ref) is True

    def test_previous_month_is_allowed(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-04-15', reference_date=ref) is True

    def test_two_months_ago_is_blocked(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-03-01', reference_date=ref) is False

    def test_next_year_is_blocked(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2027-01-01', reference_date=ref) is False

    def test_previous_year_is_blocked(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2025-12-31', reference_date=ref) is False

    def test_none_data_is_allowed(self):
        """Data mancante → lascia passare per default (sicurezza verso l'alto)."""
        assert _is_trial_invoice_date_allowed(None) is True

    def test_na_string_is_allowed(self):
        assert _is_trial_invoice_date_allowed('N/A') is True

    def test_invalid_date_is_allowed(self):
        assert _is_trial_invoice_date_allowed('not-a-date') is True

    def test_january_ref_previous_month_is_december(self):
        """A gennaio, il mese precedente è dicembre dell'anno scorso."""
        ref = pd.Timestamp('2026-01-15')
        assert _is_trial_invoice_date_allowed('2025-12-01', reference_date=ref) is True
        assert _is_trial_invoice_date_allowed('2025-11-30', reference_date=ref) is False


class TestMakeProblematicUploadEntry:
    def test_returns_dict_with_expected_keys(self):
        result = _make_problematic_upload_entry('fattura.xml', 'file corrotto', 'parse_error')
        assert result == {
            'file_name': 'fattura.xml',
            'reason': 'file corrotto',
            'category': 'parse_error',
        }

    def test_preserves_values_as_is(self):
        result = _make_problematic_upload_entry('x', '', '')
        assert result['file_name'] == 'x'
        assert result['reason'] == ''
        assert result['category'] == ''


class TestGetPolicyBlockKind:
    def test_anno_precedente_prefix_returns_year(self):
        assert _get_policy_block_kind('ANNO PRECEDENTE: fattura.xml') == 'year'

    def test_mese_precedente_prefix_returns_month(self):
        assert _get_policy_block_kind('MESE PRECEDENTE: fattura.xml') == 'month'

    def test_blocco_trial_prefix_returns_trial(self):
        assert _get_policy_block_kind('BLOCCO TRIAL: periodo non consentito') == 'trial'

    def test_unknown_prefix_returns_none(self):
        assert _get_policy_block_kind('ERRORE GENERICO') is None

    def test_empty_string_returns_none(self):
        assert _get_policy_block_kind('') is None

    def test_none_returns_none(self):
        assert _get_policy_block_kind(None) is None

    def test_prefix_case_sensitive(self):
        """Il match deve essere case-sensitive come nel codice sorgente."""
        assert _get_policy_block_kind('anno precedente: fattura.xml') is None

    def test_partial_prefix_not_matched(self):
        assert _get_policy_block_kind('ANNO') is None


class TestBuildPolicyBlockMessages:
    """I banner dei blocchi data. Non verifico l'HTML carattere per carattere
    (cambierebbe a ogni ritocco estetico): verifico che ogni tipo di blocco
    produca un banner e che conteggio/singolare-plurale siano quelli giusti,
    perche' e' cio' che il cliente legge per capire perche' un file non e'
    entrato."""

    def test_dict_vuoto_nessun_messaggio(self):
        assert _build_policy_block_messages({}) == []

    def test_chiavi_presenti_ma_liste_vuote_nessun_messaggio(self):
        assert _build_policy_block_messages({'year': [], 'month': [], 'trial': []}) == []

    def test_year_singolare(self):
        msgs = _build_policy_block_messages({'year': ['a.xml']})
        assert len(msgs) == 1
        assert '1 file ignorato' in msgs[0]
        assert 'file ignorati' not in msgs[0]

    def test_year_plurale(self):
        msgs = _build_policy_block_messages({'year': ['a.xml', 'b.xml', 'c.xml']})
        assert len(msgs) == 1
        assert '3 file ignorati' in msgs[0]

    def test_month_cita_il_mese_corrente_in_lettere(self):
        from config.constants import MESI_ITA
        atteso = MESI_ITA[pd.Timestamp.now().month - 1]
        msgs = _build_policy_block_messages({'month': ['a.xml']})
        assert len(msgs) == 1
        assert atteso in msgs[0]

    def test_trial_cita_mese_corrente_e_precedente(self):
        from config.constants import MESI_ITA
        now = pd.Timestamp.now()
        prev = now.replace(day=1) - pd.Timedelta(days=1)
        msgs = _build_policy_block_messages({'trial': ['a.xml']})
        assert len(msgs) == 1
        assert MESI_ITA[now.month - 1] in msgs[0]
        # il mese precedente puo' essere dell'anno prima (gennaio -> dicembre):
        # il messaggio deve portarsi dietro l'anno giusto, non l'anno corrente
        assert f"{MESI_ITA[prev.month - 1]} {prev.year}" in msgs[0]

    def test_tutti_e_tre_i_blocchi_danno_tre_banner_distinti(self):
        msgs = _build_policy_block_messages({
            'year': ['a.xml'],
            'month': ['b.xml'],
            'trial': ['c.xml'],
        })
        assert len(msgs) == 3
        assert len(set(msgs)) == 3


class TestFormatSavedOkDate:
    def test_stringa_iso(self):
        assert _format_saved_ok_date('2026-05-07T10:30:00Z') == '07/05/2026'

    def test_timestamp_pandas(self):
        assert _format_saved_ok_date(pd.Timestamp('2026-01-02')) == '02/01/2026'

    def test_non_parsabile_fallback(self):
        assert _format_saved_ok_date('non-una-data') == 'data sconosciuta'

    def test_none_fallback(self):
        assert _format_saved_ok_date(None) == 'data sconosciuta'


class TestDuplicateReasonForUi:
    def test_chiave_assente_usa_default(self):
        assert _duplicate_reason_for_ui('f.xml', {}) == 'Già presente nel database'

    def test_lista_di_motivi_joinata(self):
        out = _duplicate_reason_for_ui('f.xml', {'f.xml': ['stesso nome', 'stesso importo']})
        assert out == 'stesso nome — stesso importo'

    def test_lista_vuota_usa_default(self):
        assert _duplicate_reason_for_ui('f.xml', {'f.xml': []}) == 'Già presente nel database'

    def test_lista_di_soli_falsy_usa_default(self):
        """Una lista di stringhe vuote produrrebbe un join vuoto: deve
        ricadere sul default invece di mostrare al cliente una riga muta."""
        assert _duplicate_reason_for_ui('f.xml', {'f.xml': ['', None]}) == 'Già presente nel database'

    def test_valore_non_lista_convertito_a_stringa(self):
        assert _duplicate_reason_for_ui('f.xml', {'f.xml': 'motivo singolo'}) == 'motivo singolo'


class TestGetJustUploadedForCurrentRistorante:
    """Blocco cross-tenant sui file appena caricati: se il contesto sede e'
    cambiato, i file dell'altra sede NON devono trapelare. E' un controllo di
    sicurezza multi-sede, non una comodita' di UI."""

    def _session(self, **kwargs):
        return patch.object(uh.st, 'session_state', _FakeSessionState(kwargs))

    def test_payload_set_stessa_sede(self):
        with self._session(
            just_uploaded_files={'a.xml', 'b.xml'},
            ristorante_id='r1',
            just_uploaded_ristorante_id='r1',
        ):
            assert _get_just_uploaded_for_current_ristorante() == {'a.xml', 'b.xml'}

    def test_payload_set_sede_diversa_blocca(self):
        with self._session(
            just_uploaded_files={'a.xml'},
            ristorante_id='r2',
            just_uploaded_ristorante_id='r1',
        ):
            assert _get_just_uploaded_for_current_ristorante() == set()

    def test_payload_dict_strutturato(self):
        with self._session(
            just_uploaded_files={'files': ['a.xml', ' b.xml '], 'ristorante_id': 'r1'},
            ristorante_id='r1',
        ):
            assert _get_just_uploaded_for_current_ristorante() == {'a.xml', 'b.xml'}

    def test_payload_dict_sede_diversa_blocca(self):
        with self._session(
            just_uploaded_files={'files': ['a.xml'], 'ristorante_id': 'r1'},
            ristorante_id='r2',
        ):
            assert _get_just_uploaded_for_current_ristorante() == set()

    def test_migrazione_soft_fissa_il_contesto_corrente(self):
        """Sessione legacy senza sede memorizzata: i file passano e la sede
        corrente viene scritta in session_state (side-effect voluto)."""
        state = _FakeSessionState({
            'just_uploaded_files': {'a.xml'},
            'ristorante_id': 'r1',
        })
        with patch.object(uh.st, 'session_state', state):
            assert _get_just_uploaded_for_current_ristorante() == {'a.xml'}
            assert state.just_uploaded_ristorante_id == 'r1'

    def test_nessuna_sede_corrente_non_blocca(self):
        with self._session(
            just_uploaded_files={'a.xml'},
            just_uploaded_ristorante_id='r1',
        ):
            assert _get_just_uploaded_for_current_ristorante() == {'a.xml'}

    def test_nomi_vuoti_scartati(self):
        with self._session(just_uploaded_files={'a.xml', '', '   '}):
            assert _get_just_uploaded_for_current_ristorante() == {'a.xml'}


class _FakeSessionState(dict):
    """st.session_state sotto lo shim e' un dict, ma il codice ci accede
    anche per attributo (`st.session_state.just_uploaded_ristorante_id = ...`)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class TestIsFallbackServiziDaRiclassificare:
    """Ripesca SOLO le righe finite in SERVIZI per il vecchio fallback forzato,
    lasciando intatti i servizi veri (regola di dominio #1: niente fallback
    travestito, ma nemmeno riclassificazioni a caso di servizi legittimi)."""

    def _row(self, **kwargs):
        base = {
            'categoria': 'SERVIZI E CONSULENZE',
            'needs_review': True,
            'descrizione': 'PRODOTTO IGNOTO XY',
        }
        base.update(kwargs)
        return base

    def test_categoria_diversa_da_servizi_esclusa(self):
        assert _is_fallback_servizi_da_riclassificare(self._row(categoria='ALIMENTARI')) is False

    def test_needs_review_falso_escluso(self):
        assert _is_fallback_servizi_da_riclassificare(self._row(needs_review=False)) is False

    def test_descrizione_vuota_esclusa(self):
        assert _is_fallback_servizi_da_riclassificare(self._row(descrizione='   ')) is False

    def test_servizio_vero_riconosciuto_dal_dizionario_non_toccato(self):
        with patch.object(uh, 'applica_correzioni_dizionario', return_value='SERVIZI E CONSULENZE'):
            assert _is_fallback_servizi_da_riclassificare(self._row(descrizione='CANONE HACCP')) is False

    def test_dizionario_non_riconosce_va_riclassificata(self):
        with patch.object(uh, 'applica_correzioni_dizionario', return_value='Da Classificare'):
            assert _is_fallback_servizi_da_riclassificare(self._row()) is True


class TestShouldSkipPostUploadAiForRow:
    """Le righe che non devono nemmeno arrivare all'AI. Ogni caso qui e' una
    chiamata AI risparmiata E una categoria inventata in meno."""

    def _row(self, descrizione, prezzo=5.0, quantita=1.0):
        return {
            'descrizione': descrizione,
            'prezzo_unitario': prezzo,
            'quantita': quantita,
        }

    def test_descrizione_vuota(self):
        assert _should_skip_post_upload_ai_for_row(self._row('')) == (True, 'dati_insufficienti')

    def test_descrizione_mancante(self):
        assert _should_skip_post_upload_ai_for_row({}) == (True, 'dati_insufficienti')

    def test_dicitura_sicura(self):
        skip, reason = _should_skip_post_upload_ai_for_row(self._row('DDT N. 12345', prezzo=0))
        assert (skip, reason) == (True, 'riferimento_documento')

    def test_solo_simboli_e_numeri(self):
        """Serve una stringa LUNGA: sotto i 15 caratteri is_dicitura_sicura la
        cattura prima come dicitura, e il ramo 'dati_insufficienti' non si
        raggiunge mai."""
        skip, reason = _should_skip_post_upload_ai_for_row(self._row('1234567890 / 0987654321 // 1122'))
        assert (skip, reason) == (True, 'dati_insufficienti')

    @pytest.mark.parametrize('desc', ['VARIE', 'MERCE', 'ARTICOLI', 'misto'])
    def test_descrizione_generica_esatta(self, desc):
        skip, reason = _should_skip_post_upload_ai_for_row(self._row(desc))
        assert (skip, reason) == (True, 'descrizione_generica')

    def test_pochi_token_con_parola_generica(self):
        skip, reason = _should_skip_post_upload_ai_for_row(self._row('MERCE ASSORTITA'))
        assert (skip, reason) == (True, 'descrizione_generica')

    def test_riferimento_documento_da_regex(self):
        skip, reason = _should_skip_post_upload_ai_for_row(self._row('CONSEGNA ORDINE 8899 CLIENTE'))
        assert (skip, reason) == (True, 'riferimento_documento')

    def test_prezzo_zero_senza_contesto(self):
        skip, reason = _should_skip_post_upload_ai_for_row(self._row('OMAGGIO PROMO', prezzo=0))
        assert (skip, reason) == (True, 'prezzo_zero_senza_contesto')

    def test_prezzo_non_convertibile_trattato_come_zero(self):
        skip, reason = _should_skip_post_upload_ai_for_row(
            self._row('OMAGGIO PROMO', prezzo='non-un-numero')
        )
        assert (skip, reason) == (True, 'prezzo_zero_senza_contesto')

    def test_quantita_non_convertibile_non_solleva(self):
        skip, _ = _should_skip_post_upload_ai_for_row(
            {'descrizione': 'PASTA PENNE 500G', 'prezzo_unitario': 2.5, 'quantita': 'x'}
        )
        assert skip is False

    def test_prodotto_vero_va_allai(self):
        assert _should_skip_post_upload_ai_for_row(self._row('PASTA PENNE RIGATE 500G')) == (False, '')

    def test_prezzo_zero_ma_descrizione_ricca_va_allai(self):
        """Il taglio su prezzo zero vale solo con <=3 token: un prodotto
        descritto bene resta lavorabile anche a importo zero (omaggi)."""
        skip, _ = _should_skip_post_upload_ai_for_row(
            self._row('PASTA PENNE RIGATE BARILLA 500G', prezzo=0)
        )
        assert skip is False


class TestUploadLock:
    """Lock upload per sede. Il caso che conta davvero e' il fail-closed:
    se il lock non e' verificabile si BLOCCA, perche' un doppio upload
    concorrente duplicherebbe fatture reali."""

    def test_senza_ristorante_id_acquisisce(self):
        assert _acquire_upload_lock(MagicMock(), '', 'u1') is True

    def test_insert_riuscito_acquisisce(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'ristorante_id': 'r1'}]
        )
        assert _acquire_upload_lock(client, 'r1', 'u1') is True

    def test_conflitto_stesso_utente_fa_refresh_e_acquisisce(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = Exception('duplicate key')
        (client.table.return_value.select.return_value.eq.return_value
         .limit.return_value.execute.return_value) = MagicMock(
            data=[{'user_id': 'u1', 'locked_at': '2026-01-01T00:00:00Z'}]
        )
        assert _acquire_upload_lock(client, 'r1', 'u1') is True

    def test_conflitto_altro_utente_blocca(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = Exception('duplicate key')
        (client.table.return_value.select.return_value.eq.return_value
         .limit.return_value.execute.return_value) = MagicMock(
            data=[{'user_id': 'ALTRO', 'locked_at': '2026-01-01T00:00:00Z'}]
        )
        assert _acquire_upload_lock(client, 'r1', 'u1') is False

    def test_conflitto_e_lettura_fallita_blocca(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = Exception('duplicate key')
        (client.table.return_value.select.return_value.eq.return_value
         .limit.return_value.execute.side_effect) = Exception('rete giu')
        assert _acquire_upload_lock(client, 'r1', 'u1') is False

    def test_errore_generico_e_fail_closed(self):
        """Se il client esplode PRIMA di poter dire se il lock e' libero, la
        risposta e' False (bloccare), mai True (rischiare duplicati)."""
        client = MagicMock()
        client.table.side_effect = Exception('client rotto')
        assert _acquire_upload_lock(client, 'r1', 'u1') is False

    def test_cleanup_stale_fallito_non_blocca_acquisizione(self):
        client = MagicMock()
        client.table.return_value.delete.return_value.lt.return_value.execute.side_effect = (
            Exception('cleanup ko')
        )
        client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{'x': 1}])
        assert _acquire_upload_lock(client, 'r1', 'u1') is True

    def test_release_senza_ristorante_id_non_tocca_il_db(self):
        client = MagicMock()
        _release_upload_lock(client, '')
        client.table.assert_not_called()

    def test_release_cancella_il_lock_della_sede(self):
        client = MagicMock()
        _release_upload_lock(client, 'r1')
        client.table.assert_called_with('upload_locks')
        client.table.return_value.delete.return_value.eq.assert_called_with('ristorante_id', 'r1')

    def test_release_non_solleva_su_errore(self):
        client = MagicMock()
        client.table.side_effect = Exception('giu')
        _release_upload_lock(client, 'r1')  # non deve sollevare
