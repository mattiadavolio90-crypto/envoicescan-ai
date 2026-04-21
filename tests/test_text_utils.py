"""Test per utils/text_utils.py — Normalizzazione testi, estrazione categorie, escape."""
import pytest
from utils.text_utils import (
    escape_ilike,
    pulisci_caratteri_corrotti,
    normalizza_descrizione,
    normalizza_stringa,
    get_descrizione_normalizzata_e_originale,
    estrai_nome_categoria,
)


# ============================================================
# escape_ilike
# ============================================================

class TestEscapeIlike:

    def test_percentuale(self):
        assert escape_ilike("20% off") == r"20\% off"

    def test_underscore(self):
        assert escape_ilike("nome_file") == r"nome\_file"

    def test_entrambi(self):
        assert escape_ilike("100%_ok") == r"100\%\_ok"

    def test_nessun_speciale(self):
        assert escape_ilike("PASTA PENNE") == "PASTA PENNE"

    def test_stringa_vuota(self):
        assert escape_ilike("") == ""


# ============================================================
# pulisci_caratteri_corrotti
# ============================================================

class TestPulisciCaratteriCorrotti:

    def test_testo_pulito(self):
        result = pulisci_caratteri_corrotti("PASTA PENNE 500G")
        assert result == "PASTA PENNE 500G"

    def test_caratteri_cinesi(self):
        result = pulisci_caratteri_corrotti("SAKE PER CUCINA °×º×³øÓÃÇå¾Æ1*18LT")
        assert "SAKE" in result
        assert "18LT" in result or "18" in result

    def test_replacement_char(self):
        result = pulisci_caratteri_corrotti("RISO�THAI")
        assert "RISO" in result
        assert "THAI" in result

    def test_stringa_vuota(self):
        assert pulisci_caratteri_corrotti("") == ""

    def test_none(self):
        assert pulisci_caratteri_corrotti(None) == ""


# ============================================================
# normalizza_descrizione
# ============================================================

class TestNormalizzaDescrizione:

    def test_rimuove_unita_misura(self):
        result = normalizza_descrizione("POLLO INTERO KG 2.5")
        assert "KG" not in result
        assert "2.5" not in result
        assert "POLLO" in result

    def test_maiuscolo(self):
        result = normalizza_descrizione("pasta penne")
        assert result == result.upper()

    def test_stringa_vuota(self):
        assert normalizza_descrizione("") == ""

    def test_none(self):
        assert normalizza_descrizione(None) == ""


# ============================================================
# normalizza_stringa
# ============================================================

class TestNormalizzaStringa:

    def test_maiuscolo(self):
        assert normalizza_stringa("pollo intero") == "POLLO INTERO"

    def test_spazi_multipli(self):
        assert normalizza_stringa("  pasta   penne  ") == "PASTA PENNE"

    def test_punteggiatura_finale(self):
        result = normalizza_stringa("Pollo Intero...")
        assert not result.endswith("...")

    def test_troncamento_100_char(self):
        testo_lungo = "A" * 200
        result = normalizza_stringa(testo_lungo)
        assert len(result) <= 100

    def test_stringa_vuota(self):
        assert normalizza_stringa("") == ""

    def test_none(self):
        assert normalizza_stringa(None) == ""

    def test_non_stringa(self):
        assert normalizza_stringa(123) == ""


# ============================================================
# get_descrizione_normalizzata_e_originale
# ============================================================

class TestGetDescrizioneNormalizzataEOriginale:

    def test_base(self):
        norm, orig = get_descrizione_normalizzata_e_originale("Pasta Penne 500g")
        assert orig == "PASTA PENNE 500G"
        assert "PASTA" in norm
        assert "PENNE" in norm

    def test_originale_maiuscolo(self):
        _, orig = get_descrizione_normalizzata_e_originale("olio evo")
        assert orig == "OLIO EVO"


# ============================================================
# estrai_nome_categoria
# ============================================================

class TestEstraiNomeCategoria:

    def test_con_emoji(self):
        assert estrai_nome_categoria("🍖 CARNE") == "CARNE"

    def test_senza_emoji(self):
        assert estrai_nome_categoria("CARNE") == "CARNE"

    def test_multi_parola_con_emoji(self):
        assert estrai_nome_categoria("📦 MATERIALE DI CONSUMO") == "MATERIALE DI CONSUMO"

    def test_multi_parola_senza_emoji(self):
        assert estrai_nome_categoria("MATERIALE DI CONSUMO") == "MATERIALE DI CONSUMO"

    def test_vuota(self):
        assert estrai_nome_categoria("") == "Da Classificare"

    def test_none(self):
        assert estrai_nome_categoria(None) == "Da Classificare"

    def test_solo_spazi(self):
        result = estrai_nome_categoria("   ")
        assert result.strip() == "" or result == "Da Classificare"
