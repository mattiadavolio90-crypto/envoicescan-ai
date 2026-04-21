from unittest.mock import MagicMock, patch

from services.ai_service import applica_regole_categoria_forti
from services.upload_handler import (
    _build_policy_block_messages,
    _find_existing_saved_ok_events,
    _should_skip_post_upload_ai_for_row,
)
from utils.validation import is_dicitura_sicura
from utils.formatters import log_upload_event


def test_repair_with_gas_parts_is_maintenance_not_utilities():
    categoria, motivo = applica_regole_categoria_forti(
        "RIPARAZIONE CUCINA WOK CON SOSTITUZIONE RUBINETTO GAS, TERMOCOPPIA SIT",
        "Da Classificare",
    )
    assert categoria == "MANUTENZIONE E ATTREZZATURE"


def test_final_discount_line_is_treated_as_dicitura():
    assert is_dicitura_sicura("SCONTI FINALI - 5.00%", 0, 1) is True


def test_duplicate_status_is_normalized_for_upload_events_logging():
    mock_execute = MagicMock()
    mock_insert = MagicMock(return_value=MagicMock(execute=mock_execute))
    mock_table = MagicMock(return_value=MagicMock(insert=mock_insert))
    supabase = MagicMock(table=mock_table)

    log_upload_event(
        user_id="u1",
        user_email="test@example.com",
        file_name="dup.xml",
        status="DUPLICATE_SKIPPED",
        supabase_client=supabase,
    )

    payload = mock_insert.call_args[0][0]
    assert payload["status"] == "SAVED_PARTIAL"
    assert payload["details"]["original_status"] == "DUPLICATE_SKIPPED"


def test_previous_year_block_message_does_not_mention_trial():
    messages = _build_policy_block_messages(
        {
            "year": ["old_a.xml", "old_b.xml"],
            "month": [],
            "trial": [],
        }
    )

    assert len(messages) == 1
    assert "anno precedente" in messages[0].lower()
    assert "prova gratuita" not in messages[0].lower()


def test_passion_fruit_is_categorized_as_fruit():
    categoria, _ = applica_regole_categoria_forti("FRUTTA PASIONE", "VERDURE")
    assert categoria == "FRUTTA"


def test_bean_sprouts_are_vegetables_not_beverages():
    categoria, _ = applica_regole_categoria_forti("GERMOGLI DI SOIA", "BEVANDE")
    assert categoria == "VERDURE"


def test_stamp_duty_charge_is_services_not_utilities():
    categoria, _ = applica_regole_categoria_forti(
        "RIVALSA IMPOSTA DI BOLLO - NUM. PRATICA 1110213",
        "UTENZE E LOCALI",
    )
    assert categoria == "SERVIZI E CONSULENZE"


def test_saved_ok_event_lookup_respects_ristorante_id():
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.in_.return_value = query
    query.execute.return_value = MagicMock(data=[
        {
            "file_name": "dup.xml",
            "created_at": "2026-04-13T10:27:51+00:00",
            "details": {"ristorante_id": "rist-1"},
        },
        {
            "file_name": "dup.xml",
            "created_at": "2026-04-13T10:49:50+00:00",
            "details": {"ristorante_id": "rist-2"},
        },
    ])
    supabase = MagicMock()
    supabase.table.return_value = query

    matches = _find_existing_saved_ok_events(supabase, "user-1", "rist-1", ["dup.xml"])

    assert "dup.xml" in matches
    assert matches["dup.xml"]["details"]["ristorante_id"] == "rist-1"


def test_salvataggio_fattura_e_idempotente_delete_before_insert():
    from services.invoice_service import salva_fattura_processata

    table = MagicMock()
    delete_query = MagicMock()
    delete_query.eq.return_value = delete_query
    delete_query.execute.return_value = MagicMock(data=[{"id": 1}])
    insert_query = MagicMock()
    insert_query.execute.return_value = MagicMock(data=[{"id": 99}])

    table.delete.return_value = delete_query
    table.insert.return_value = insert_query

    supabase = MagicMock()
    supabase.table.return_value = table

    fake_row = {
        "Numero_Riga": 1,
        "Descrizione": "SALMONE 5-6",
        "Quantita": 1,
        "Unita_Misura": "KG",
        "Prezzo_Unitario": 10.0,
        "IVA_Percentuale": 10.0,
        "Totale_Riga": 10.0,
        "Fornitore": "ADC S.R.L.",
        "Categoria": "PESCE",
        "Data_Documento": "2026-01-31",
        "needs_review": False,
    }

    fake_st = MagicMock()
    fake_st.session_state.user_data = {"email": "test@example.com"}

    with patch("services.invoice_service.st", fake_st), \
         patch("services.invoice_service.verifica_integrita_fattura", return_value={"integrita_ok": True, "righe_parsed": 1, "righe_db": 1}), \
         patch("services.invoice_service.log_upload_event"):
        result = salva_fattura_processata(
            "dup.xml",
            [fake_row],
            supabase_client=supabase,
            silent=True,
            ristoranteid="rist-1",
            user_id="user-1",
        )

    assert result["success"] is True
    table.delete.assert_called_once()
    delete_query.eq.assert_any_call("user_id", "user-1")
    delete_query.eq.assert_any_call("file_origine", "dup.xml")
    delete_query.eq.assert_any_call("ristorante_id", "rist-1")
    table.insert.assert_called_once()


def test_skip_post_upload_ai_for_generic_or_document_rows():
    skip_varie, reason_varie = _should_skip_post_upload_ai_for_row({
        'descrizione': 'varie',
        'prezzo_unitario': 9.0,
        'quantita': 1,
    })
    skip_ddt, reason_ddt = _should_skip_post_upload_ai_for_row({
        'descrizione': 'Riferimento: DDT Nr. 018007 del 01/02/2026',
        'prezzo_unitario': 0.0,
        'quantita': 0,
    })
    skip_riga, reason_riga = _should_skip_post_upload_ai_for_row({
        'descrizione': 'RIGA FATTURA',
        'prezzo_unitario': -2066.95,
        'quantita': 1,
    })

    assert skip_varie is True
    assert reason_varie == 'descrizione_generica'
    assert skip_ddt is True
    assert reason_ddt in {'riferimento_documento', 'prezzo_zero_senza_contesto'}
    assert skip_riga is True
    assert reason_riga == 'riferimento_documento'



def test_td24_upload_event_persists_alert_data_consegna():
    from services.invoice_service import salva_fattura_processata

    fatture_table = MagicMock()
    delete_query = MagicMock()
    delete_query.eq.return_value = delete_query
    delete_query.execute.return_value = MagicMock(data=[])
    fatture_insert_query = MagicMock()
    fatture_insert_query.execute.return_value = MagicMock(data=[{"id": 1}])

    fatture_table.delete.return_value = delete_query
    fatture_table.insert.return_value = fatture_insert_query

    upload_events_table = MagicMock()
    upload_event_insert_query = MagicMock()
    upload_event_insert_query.execute.return_value = MagicMock(data=[{"id": 99}])
    upload_events_table.insert.return_value = upload_event_insert_query

    supabase = MagicMock()
    supabase.table.side_effect = lambda name: {
        "fatture": fatture_table,
        "upload_events": upload_events_table,
    }[name]

    td24_rows = [
        {
            "Numero_Riga": 1,
            "Descrizione": "MOZZARELLA",
            "Quantita": 1,
            "Unita_Misura": "KG",
            "Prezzo_Unitario": 10.0,
            "IVA_Percentuale": 10.0,
            "Totale_Riga": 10.0,
            "Fornitore": "ADC S.R.L.",
            "Categoria": "LATTICINI",
            "Data_Documento": "2026-01-31",
            "tipo_documento": "TD24",
            "data_consegna": None,
            "needs_review": False,
        }
    ]

    fake_st = MagicMock()
    fake_st.session_state.user_data = {"email": "test@example.com"}

    with patch("services.invoice_service.st", fake_st), \
         patch("services.invoice_service.verifica_integrita_fattura", return_value={"integrita_ok": True, "righe_parsed": 1, "righe_db": 1}):
        result = salva_fattura_processata(
            "td24.xml",
            td24_rows,
            supabase_client=supabase,
            silent=True,
            ristoranteid="rist-1",
            user_id="user-1",
        )

    assert result["success"] is True
    payload = upload_events_table.insert.call_args[0][0]
    assert payload["status"] == "SAVED_OK"
    assert payload["alert_data_consegna"] == "missing"
    assert payload["details"]["alert_data_consegna"] == "missing"
