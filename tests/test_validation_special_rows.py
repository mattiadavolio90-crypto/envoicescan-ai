from utils.validation import (
    SPECIAL_ROW_DICITURA,
    SPECIAL_ROW_NORMALE,
    SPECIAL_ROW_SCONTO_OMAGGIO,
    SPECIAL_ROW_STORNO,
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