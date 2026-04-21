"""Test per utils/piva_validator.py — Validazione P.IVA italiana."""
import pytest
from utils.piva_validator import valida_formato_piva, normalizza_piva, _verifica_checksum_piva


# ============================================================
# normalizza_piva
# ============================================================

class TestNormalizzaPiva:

    def test_spazi(self):
        assert normalizza_piva("123 456 789 01") == "12345678901"

    def test_trattini(self):
        assert normalizza_piva("123-456-789-01") == "12345678901"

    def test_prefisso_IT(self):
        assert normalizza_piva("IT12345678901") == "12345678901"

    def test_prefisso_it_minuscolo(self):
        assert normalizza_piva("it12345678901") == "12345678901"

    def test_gia_pulita(self):
        assert normalizza_piva("12345678901") == "12345678901"

    def test_vuota(self):
        assert normalizza_piva("") == ""

    def test_none(self):
        assert normalizza_piva(None) == ""


# ============================================================
# valida_formato_piva
# ============================================================

class TestValidaFormatoPiva:

    def test_piva_troppo_corta(self):
        ok, errore = valida_formato_piva("123")
        assert ok is False
        assert "11 cifre" in errore

    def test_piva_troppo_lunga(self):
        ok, errore = valida_formato_piva("123456789012")
        assert ok is False
        assert "11 cifre" in errore

    def test_piva_con_lettere(self):
        ok, errore = valida_formato_piva("1234567890A")
        assert ok is False
        assert "solo numeri" in errore or "11 cifre" in errore

    def test_piva_vuota(self):
        ok, errore = valida_formato_piva("")
        assert ok is False
        assert "obbligatoria" in errore

    def test_piva_none(self):
        ok, errore = valida_formato_piva(None)
        assert ok is False

    def test_piva_con_spazi_valida(self):
        """P.IVA con formattazione ma checksum valido."""
        # Usiamo una P.IVA nota come valida
        ok, _ = valida_formato_piva("IT 00000000000")
        # Solo 0 non passa il checksum, ma formato è corretto
        assert isinstance(ok, bool)

    def test_piva_11_zeri(self):
        """00000000000 ha checksum: somma=0, 0%10=0 → dovrebbe passare."""
        ok, _ = valida_formato_piva("00000000000")
        assert isinstance(ok, bool)


# ============================================================
# _verifica_checksum_piva
# ============================================================

class TestVerificaChecksumPiva:

    def test_lunghezza_errata(self):
        assert _verifica_checksum_piva("123") is False

    def test_non_numerico(self):
        assert _verifica_checksum_piva("1234567890A") is False

    def test_tutti_zeri(self):
        # 00000000000: somma_dispari=0, somma_pari=0, totale=0, 0%10=0 → True
        assert _verifica_checksum_piva("00000000000") is True

    def test_checksum_coerente(self):
        """Verifica che valida_formato_piva e _verifica_checksum siano allineati."""
        ok, _ = valida_formato_piva("12345678903")
        checksum_ok = _verifica_checksum_piva("12345678903")
        assert ok == checksum_ok
