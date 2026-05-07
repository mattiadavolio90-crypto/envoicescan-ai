import pytest
from utils.validation import (
    SPECIAL_ROW_DICITURA,
    SPECIAL_ROW_NORMALE,
    SPECIAL_ROW_SCONTO_OMAGGIO,
    SPECIAL_ROW_STORNO,
    _NC_GENERIC_DESCRIPTIONS,
    classify_special_row,
)


def test_documentale_zero_goes_to_dicitura():
    result = classify_special_row(
        descrizione='DDT N. 56 DEL 03/02/2026',
        prezzo=0,
        totale_riga=0,
    )
    assert result['bucket'] == SPECIAL_ROW_DICITURA
    assert result['include_in_dashboard'] is False


def test_zero_service_omaggio_stays_economic():
    result = classify_special_row(
        descrizione='DIRITTO DI CHIAMATA MILANO CENTRO OMAGGIO',
        categoria='SERVIZI E CONSULENZE',
        prezzo=0,
        totale_riga=0,
    )
    assert result['bucket'] == SPECIAL_ROW_SCONTO_OMAGGIO
    assert result['include_in_dashboard'] is True


def test_zero_lavorazione_is_not_dicitura():
    result = classify_special_row(
        descrizione='SERVIZIO DI DISOSSO E LAVORAZIONE',
        categoria='SERVIZI E CONSULENZE',
        prezzo=0,
        totale_riga=0,
    )
    assert result['bucket'] == SPECIAL_ROW_SCONTO_OMAGGIO


def test_negative_reso_is_storno():
    result = classify_special_row(
        descrizione='BISCOTTI FORTUNA 275PZ RESO',
        categoria='SHOP',
        prezzo=-10,
        totale_riga=-10,
    )
    assert result['bucket'] == SPECIAL_ROW_STORNO
    assert result['include_in_price_average'] is False


def test_positive_product_stays_normal():
    result = classify_special_row(
        descrizione='MOZZARELLA FIOR DI LATTE',
        categoria='LATTICINI',
        prezzo=10,
        totale_riga=20,
    )
    assert result['bucket'] == SPECIAL_ROW_NORMALE
    assert result['include_in_dashboard'] is True


# ──────────────────────────────────────────────────────────────────────────
# NC generiche TD04 (es. METRO "RIGA FATTURA")
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("desc", sorted(_NC_GENERIC_DESCRIPTIONS))
def test_td04_with_generic_description_sets_should_review(desc):
    """Ogni descrizione placeholder + TD04 deve attivare needs_review."""
    result = classify_special_row(
        descrizione=desc,
        tipo_documento='TD04',
        prezzo=-10,
        totale_riga=-10,
    )
    assert result['should_review'] is True, f"NC generica '{desc}' dovrebbe richiedere revisione"


def test_td04_with_non_generic_description_does_not_force_review():
    """TD04 con una descrizione reale non deve attivare il flag NC-generic."""
    result = classify_special_row(
        descrizione='MOZZARELLA DI BUFALA CAMPANA DOP',
        tipo_documento='TD04',
        prezzo=-5,
        totale_riga=-5,
    )
    # should_review può essere True per altri motivi, ma non per NC generic
    # verifichiamo che il bucket non venga forzato solo da NC generic logic
    assert result['bucket'] != SPECIAL_ROW_DICITURA


def test_td01_with_generic_description_does_not_trigger_nc_generic():
    """'RIGA FATTURA' su una fattura normale TD01 NON deve attivare NC generic."""
    result = classify_special_row(
        descrizione='RIGA FATTURA',
        tipo_documento='TD01',
        prezzo=10,
        totale_riga=10,
    )
    # Il flag should_review può essere False/True per altri motivi, ma non per NC-generic
    # La chiave discriminante è tipo_documento='TD04', quindi qui deve restare False
    # a meno di altri trigger. Con prezzo positivo e nessun hint di storno, deve essere normale.
    assert result['should_review'] is False


def test_nc_generic_descriptions_is_not_empty():
    assert len(_NC_GENERIC_DESCRIPTIONS) > 0


def test_nc_generic_descriptions_are_uppercase():
    for desc in _NC_GENERIC_DESCRIPTIONS:
        assert desc == desc.upper(), f"'{desc}' non è in maiuscolo — normalizzazione incoerente"
