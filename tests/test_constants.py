"""Test per config/constants.py — Verifica che le costanti centralizzate esistano e abbiano valori sensati."""
import pytest
from config.constants import (
    TRUNCATE_DESC_LOG,
    TRUNCATE_DESC_QUERY,
    TRUNCATE_ERROR_DISPLAY,
    MAX_FILE_SIZE_P7M,
    MAX_DESC_LENGTH_DB,
    MEMORIA_SESSION_CAP,
    UI_DELAY_QUICK,
    UI_DELAY_SHORT,
    UI_DELAY_MEDIUM,
    UI_DELAY_LONG,
    BATCH_RATE_LIMIT_DELAY,
    CATEGORIE_FOOD_BEVERAGE,
    CATEGORIE_SPESE_OPERATIVE,
    DIZIONARIO_CORREZIONI,
    TUTTE_LE_CATEGORIE,
    CATEGORIA_PER_FORNITORE,
    CUSTOM_TAG_SUGGESTION_LIMIT,
    CUSTOM_TAG_SEARCH_RESULT_LIMIT,
    CUSTOM_TAG_ALERT_SOGLIA_DEFAULT,
    CUSTOM_TAG_COLOR_DEFAULT,
    CUSTOM_TAG_UNITA_KG,
    CUSTOM_TAG_UNITA_LT,
)


class TestCostantiLimiti:
    """Verifica che i limiti siano definiti e ragionevoli."""

    def test_truncate_desc_log(self):
        assert isinstance(TRUNCATE_DESC_LOG, int)
        assert 20 <= TRUNCATE_DESC_LOG <= 100

    def test_truncate_desc_query(self):
        assert isinstance(TRUNCATE_DESC_QUERY, int)
        assert 10 <= TRUNCATE_DESC_QUERY <= 50

    def test_truncate_error_display(self):
        assert isinstance(TRUNCATE_ERROR_DISPLAY, int)
        assert 50 <= TRUNCATE_ERROR_DISPLAY <= 500

    def test_max_file_size_p7m(self):
        assert MAX_FILE_SIZE_P7M > 1_000_000  # > 1MB
        assert MAX_FILE_SIZE_P7M <= 100_000_000  # <= 100MB

    def test_max_desc_length(self):
        assert 100 <= MAX_DESC_LENGTH_DB <= 1000

    def test_memoria_session_cap(self):
        assert MEMORIA_SESSION_CAP > 0


class TestCostantiDelay:
    """Verifica ordine delay: quick < short < medium < long."""

    def test_ordine_crescente(self):
        assert UI_DELAY_QUICK < UI_DELAY_SHORT
        assert UI_DELAY_SHORT < UI_DELAY_MEDIUM
        assert UI_DELAY_MEDIUM <= UI_DELAY_LONG

    def test_nessun_delay_eccessivo(self):
        assert UI_DELAY_LONG <= 2.0  # Max 2 secondi
        assert BATCH_RATE_LIMIT_DELAY <= 2.0


class TestCostantiCategorie:
    """Verifica struttura categorie."""

    def test_categorie_food_non_vuote(self):
        assert len(CATEGORIE_FOOD_BEVERAGE) >= 10

    def test_categorie_spese_non_vuote(self):
        assert len(CATEGORIE_SPESE_OPERATIVE) >= 1

    def test_tutte_le_categorie_include_food(self):
        for cat in CATEGORIE_FOOD_BEVERAGE:
            assert cat in TUTTE_LE_CATEGORIE

    def test_dizionario_non_vuoto(self):
        assert len(DIZIONARIO_CORREZIONI) >= 50

    def test_dizionario_valori_sono_stringhe(self):
        for keyword, categoria in DIZIONARIO_CORREZIONI.items():
            assert isinstance(keyword, str), f"Keyword non stringa: {keyword}"
            assert isinstance(categoria, str), f"Categoria non stringa per '{keyword}'"


class TestCategoriaPerFornitore:
    """Verifica le nuove regole fornitore aggiunte nel fix M1 (audit 2026-04-20)."""

    def test_shidu_international_rimosso(self):
        # Cert. SUSHILAND 25/06: SHIDU vende anche noodle/pasta (SOBA, VERMICELLI),
        # non solo verdure. La regola-fornitore secca VERDURE era essa stessa fonte
        # di errore. I prodotti SHIDU ora sono categorizzati per keyword/regole forti.
        assert 'SHIDU INTERNATIONAL' not in CATEGORIA_PER_FORNITORE

    def test_nova_horeca_presente(self):
        assert 'NOVA HORECA' in CATEGORIA_PER_FORNITORE
        assert CATEGORIA_PER_FORNITORE['NOVA HORECA'] == 'MANUTENZIONE E ATTREZZATURE'

    def test_fornitori_mono_categoria_cert_sushiland(self):
        # Fornitori mono-categoria verificati a DB (cert. MARIANO 25/06).
        assert CATEGORIA_PER_FORNITORE['BRICOMAN'] == 'MANUTENZIONE E ATTREZZATURE'
        assert CATEGORIA_PER_FORNITORE['CIESSECI'] == 'MANUTENZIONE E ATTREZZATURE'
        assert CATEGORIA_PER_FORNITORE['PARAMIDANI'] == 'MANUTENZIONE E ATTREZZATURE'
        assert CATEGORIA_PER_FORNITORE['HAL SERVICE'] == 'UTENZE E LOCALI'
        assert CATEGORIA_PER_FORNITORE['TAURUSLAB'] == 'SERVIZI E CONSULENZE'


class TestDizionarioKeywordNuovi:
    """Verifica le nuove keyword aggiunte nel fix M1/C2 (audit 2026-04-20)."""

    def test_revisore_legale_in_servizi(self):
        assert 'REVISORE LEGALE' in DIZIONARIO_CORREZIONI
        assert DIZIONARIO_CORREZIONI['REVISORE LEGALE'] == 'SERVIZI E CONSULENZE'

    def test_revisore_in_servizi(self):
        assert 'REVISORE' in DIZIONARIO_CORREZIONI
        assert DIZIONARIO_CORREZIONI['REVISORE'] == 'SERVIZI E CONSULENZE'

    def test_coupon_in_note(self):
        assert 'COUPON' in DIZIONARIO_CORREZIONI
        assert DIZIONARIO_CORREZIONI['COUPON'] == '📝 NOTE E DICITURE'

    def test_buono_sconto_in_note(self):
        assert 'BUONO SCONTO' in DIZIONARIO_CORREZIONI
        assert DIZIONARIO_CORREZIONI['BUONO SCONTO'] == '📝 NOTE E DICITURE'


class TestCostantiCustomTag:
    """Verifica che tutte le costanti CUSTOM_TAG_* siano importabili e tipizzate correttamente."""

    @pytest.mark.parametrize(
        ("value", "expected_type"),
        [
            (CUSTOM_TAG_SUGGESTION_LIMIT, int),
            (CUSTOM_TAG_SEARCH_RESULT_LIMIT, int),
            (CUSTOM_TAG_ALERT_SOGLIA_DEFAULT, float),
            (CUSTOM_TAG_COLOR_DEFAULT, str),
            (CUSTOM_TAG_UNITA_KG, set),
            (CUSTOM_TAG_UNITA_LT, set),
        ],
    )
    def test_costanti_custom_tag_tipo_atteso(self, value, expected_type):
        assert isinstance(value, expected_type)

    def test_costanti_custom_tag_unita_contengono_stringhe(self):
        assert all(isinstance(item, str) for item in CUSTOM_TAG_UNITA_KG)
        assert all(isinstance(item, str) for item in CUSTOM_TAG_UNITA_LT)


class TestDizionarioEncoding:
    """Audit prompt AI 3/9/2026: 12 chiavi del dizionario erano mojibake (doppia
    codifica UTF-8: 'BACCALÃ€' invece di 'BACCALÀ') e non potevano matchare NESSUNA
    descrizione reale. Le fatture elettroniche scrivono senza accenti, quindi
    l'impatto era latente — ma il percorso PDF/Vision gli accenti li conserva."""

    def test_nessuna_chiave_mojibake(self):
        # 'Ã' e 'â' non esistono in nessuna parola italiana o di prodotto: se
        # compaiono in una chiave, è di nuovo doppia codifica.
        corrotte = [k for k in DIZIONARIO_CORREZIONI if 'Ã' in k or 'â' in k]
        assert corrotte == [], f"chiavi con doppia codifica UTF-8: {corrotte}"

    @pytest.mark.parametrize(
        ("descrizione", "categoria_attesa"),
        [
            # forma reale in fattura elettronica (senza accento / con apostrofo)
            ("BACCALA MANTECATO KG1", "PESCE"),
            ("RAGU' DI CARNE VASCHETTA", "SALSE E CREME"),
            ("CONTABILITA MENSILE", "SERVIZI E CONSULENZE"),
            ("ELETTRICITA F1", "UTENZE E LOCALI"),
            ("MACCHINA CAFFE' 2 GRUPPI", "MANUTENZIONE E ATTREZZATURE"),
            # forma accentata (percorso PDF/Vision, che conserva gli accenti)
            ("BACCALÀ MANTECATO KG1", "PESCE"),
            ("RAGÙ DI CARNE VASCHETTA", "SALSE E CREME"),
            ("CAFFÈ MISCELA ORO", "CAFFE E THE"),
            ("TIRAMISÙ MONOPORZIONE", "GELATI E DESSERT"),
            ("WÜRSTEL SUINO", "SALUMI"),
        ],
    )
    def test_keyword_accentate_matchano(self, descrizione, categoria_attesa):
        from services.ai_service import applica_correzioni_dizionario

        assert applica_correzioni_dizionario(descrizione, "Da Classificare") == categoria_attesa
