"""Test per utils/validation.py — is_dicitura_sicura e is_prezzo_valido"""
import pytest
from utils.validation import is_dicitura_sicura, is_prezzo_valido


# ============================================================
# is_dicitura_sicura
# ============================================================

class TestIsDicituraSicura:
    """Verifica che diciture (non-prodotti) vengano riconosciute correttamente."""

    # ---- Diciture che DEVONO essere riconosciute (True) ----
    @pytest.mark.parametrize("desc", [
        "BOLLA N. 12345",
        "DDT N. 456",
        "TRASPORTO GRATUITO",
        "CONTRIBUTO CONAI",
        "SPESE SPEDIZIONE",
        "PORTO FRANCO",
        "IMBALLO",
        "DDT",
        "TRASPORTO",
        "ARROTONDAMENTO",
        "RIF.",
        "COME DA ACCORDI",
        "VS ORDINE 12345",
        "VEDI ALLEGATO",
        "NOTA: consegna lunedì",
    ])
    def test_diciture_riconosciute(self, desc):
        assert is_dicitura_sicura(desc, 0, 1) is True

    # ---- Prodotti che NON devono essere classificati come diciture (False) ----
    @pytest.mark.parametrize("desc", [
        "PASTA PENNE 500G",
        "OLIO EXTRAVERGINE 1L",
        "MOZZARELLA DI BUFALA KG",
        "COCA COLA 330ML",
        "POLLO INTERO KG 2.5",
        "SALSICCIA FRESCA",
        "BIRRA MORETTI 33CL",
    ])
    def test_prodotti_non_diciture(self, desc):
        assert is_dicitura_sicura(desc, 2.50, 1) is False

    def test_stringa_vuota(self):
        assert is_dicitura_sicura("", 0, 1) is False

    def test_none(self):
        assert is_dicitura_sicura(None, 0, 1) is False

    def test_solo_numeri_breve(self):
        """Stringa breve con solo numeri/simboli → dicitura."""
        assert is_dicitura_sicura("12345", 0, 1) is True

    def test_pattern_bolla_data(self):
        """Pattern tipo 'BOLL DEL 12-12-2025' → dicitura."""
        assert is_dicitura_sicura("BOLL DEL 12-12-2025", 0, 1) is True


# ============================================================
# is_prezzo_valido
# ============================================================

class TestIsPrezzoValido:
    """Verifica range prezzo."""

    def test_prezzo_normale(self):
        assert is_prezzo_valido(10.50) is True

    def test_prezzo_zero(self):
        assert is_prezzo_valido(0) is False

    def test_prezzo_negativo(self):
        assert is_prezzo_valido(-5) is False

    def test_prezzo_troppo_alto(self):
        assert is_prezzo_valido(150_000) is False

    def test_prezzo_limite_basso(self):
        assert is_prezzo_valido(0.001) is True

    def test_prezzo_limite_alto(self):
        assert is_prezzo_valido(100_000) is True

    def test_prezzo_custom_range(self):
        assert is_prezzo_valido(0.5, min_val=1.0) is False
        assert is_prezzo_valido(5.0, min_val=1.0, max_val=10.0) is True

    def test_prezzo_non_numerico(self):
        assert is_prezzo_valido("abc") is False
        assert is_prezzo_valido(None) is False
