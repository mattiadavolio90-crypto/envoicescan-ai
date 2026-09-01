"""Fase 7 — recupero delle righe riconoscibili (audit categorizzazione 1/9/2026).

La misura cieca su 815 righe mai verificate da un umano ha dato 96,7% di categorie
corrette: il sistema NON ha un problema di errori. Ha un problema diverso — il 34%
delle righe lasciate in "Da Classificare" (10 su 29 nel campione) era riconoscibile
senza ambiguita' da una persona. Non e' misclassificazione, e' mancata
classificazione: costi che restano fuori dai numeri del cliente per un buco del
dizionario, non per una vera ambiguita'.

Qui si prova il recupero di quei casi e, soprattutto, che le keyword aggiunte NON
catturino altro. Ogni forma e' stata verificata contro il DB di produzione prima di
essere scelta: le note sotto riportano le collisioni reali che hanno scartato la
forma piu' ovvia.
"""
from __future__ import annotations

import pytest

from services.ai_service import (
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
)


def _pipeline(descrizione: str, categoria_iniziale: str = "Da Classificare") -> str:
    """Dizionario poi regole forti: l'ordine di `categorizza_con_memoria` (L7)."""
    cat = applica_correzioni_dizionario(descrizione, categoria_iniziale)
    cat, _motivo = applica_regole_categoria_forti(descrizione, cat)
    return cat


class TestRigheRecuperate:
    """Casi reali estratti dal DB, giudicati recuperabili dal categorization-reviewer."""

    @pytest.mark.parametrize("descrizione,attesa", [
        ("CORIANDORO", "SPEZIE E AROMI"),
        ("SPAZZOLAPULIZIA", "MATERIALE DI CONSUMO"),
        ("CROSTINI PER ZUPPE-GR 200", "PRODOTTI DA FORNO"),
        ("BEVANDA AL TE' DI GELSOMINO", "BEVANDE"),
        ("SL PULIORECCHIE-PZ 160", "MATERIALE DI CONSUMO"),
        ("BIBITE", "BEVANDE"),
        ("SG-EQ. GALLETTA MAIS-GR 120", "PASTA E CEREALI"),
        ("MAIS VAPORE VALFRUTT.SG.140GX3", "SCATOLAME E CONSERVE"),
    ])
    def test_riga_riconoscibile_non_resta_in_coda(self, descrizione, attesa):
        assert _pipeline(descrizione) == attesa

    @pytest.mark.parametrize("descrizione", [
        # Attrezzo durevole o consumabile? A DB sta in MANUTENZIONE (3 righe), il
        # reviewer proponeva MATERIALE. Due letture legittime -> resta in coda:
        # e' esattamente il caso in cui la regola di dominio dice di non indovinare.
        "PELAPATATE 3IN1-UN 1",
        # Un microonde. "MW" e' troppo ambiguo per una keyword e "MICROONDE" secco
        # colliderebbe con 10 righe di contenitori per microonde (MATERIALE).
        "WHIRLP.MW MWP 203 SB 700W 20L GRILL",
    ])
    def test_caso_ambiguo_resta_onestamente_in_coda(self, descrizione):
        """Meglio in coda che indovinato: e' la regola di dominio del progetto."""
        assert _pipeline(descrizione) == "Da Classificare"


class TestKeywordNonCatturanoAltro:
    """Il rischio vero di una keyword nuova non e' non funzionare: e' rubare righe
    gia' corrette. Ogni caso qui sotto e' una collisione REALE trovata a DB che ha
    fatto scartare la forma secca della keyword."""

    def test_spazzol_secco_non_ruba_le_cozze(self):
        """'SPAZZOL' avrebbe catturato COZZA SPAZZOLATA (10 righe a DB, PESCE)."""
        assert _pipeline("COZZA ITALIA SPAZZOLATA", "PESCE") == "PESCE"

    def test_spazzol_secco_non_ruba_lo_spazzolone(self):
        """Lo spazzolone lavapavimenti e' attrezzatura durevole, non consumabile."""
        assert _pipeline(
            "/ FLOOR-SPAZZOLONE LAVAPAVIMENTI", "MANUTENZIONE E ATTREZZATURE"
        ) == "MANUTENZIONE E ATTREZZATURE"

    def test_crostini_snack_restano_shop(self):
        """'CROSTINI' secco avrebbe spostato i crostini da aperitivo (SHOP)."""
        assert _pipeline("CROSTINI G.75 DORATI SAN CARLO", "SHOP") == "SHOP"

    @pytest.mark.parametrize("descrizione,categoria", [
        ("BOND.MAIS&FAG.ROSSI-GR 280", "SCATOLAME E CONSERVE"),
        ("AMIDO DI MAIS", "PASTA E CEREALI"),
        ("FRESH MAIS AL PZ", "VERDURE"),
    ])
    def test_mais_secco_avrebbe_rotto_tre_categorie(self, descrizione, categoria):
        """A DB 'MAIS' vive legittimamente in 4 categorie: solo 'MAIS VAPORE'."""
        assert _pipeline(descrizione, categoria) == categoria

    def test_contenitori_per_microonde_restano_materiale(self):
        """10 righe a DB: sono contenitori, non elettrodomestici."""
        assert _pipeline(
            "CONTENITORE C+C MICROONDE 500ML 173X108X40 300PZ", "MATERIALE DI CONSUMO"
        ) == "MATERIALE DI CONSUMO"


class TestBrandAcquaMaBevanda:
    """Unico pattern di errore SISTEMICO emerso dalla misura cieca: 2 righe su 13
    campionate in ACQUA erano bibite (15% della categoria). I brand di acqua
    minerale vendono anche te', gassose e succhi: conta il prodotto, non il brand."""

    @pytest.mark.parametrize("descrizione", [
        "THE S.BENEDETTO LIM 33 CLX24 LAT SLEEK",
        "BIB LURISIA GASSOSA 0, 275 X24 VP",
        "SUCCOSO ACE S.BENEDETTO 1,5L",
        "SUCCOSO ANANAS S.BENEDETTO 1,5",
    ])
    def test_bibita_di_brand_acqua_e_bevanda(self, descrizione):
        assert _pipeline(descrizione, "ACQUA") == "BEVANDE"

    def test_il_motivo_e_esplicito(self):
        """Il motivo alimenta la tracciabilita' (Fase 2) e i log: deve dire perche'."""
        _cat, motivo = applica_regole_categoria_forti(
            "THE S.BENEDETTO LIM 33 CLX24 LAT SLEEK", "ACQUA"
        )
        assert motivo == "brand_acqua_ma_bevanda"

    @pytest.mark.parametrize("descrizione", [
        "ACQ S.BENEDETTO MILL NAT 33 LAT SLEEKX24",
        "ACQUA PANNA 0,75",
        "ACQUA FRIZZANTE LT1.5",
        "ACQUA NATURALE LT1.5",
    ])
    def test_l_acqua_vera_resta_acqua(self, descrizione):
        """La controprova che conta: la regola non deve svuotare la categoria ACQUA."""
        assert _pipeline(descrizione, "ACQUA") == "ACQUA"

    def test_servizio_idrico_resta_utenza(self):
        """UTENZE ha priorita': una bolletta dell'acquedotto non e' una bibita."""
        assert _pipeline("UI2 QI ACQUA POTABILE", "UTENZE E LOCALI") == "UTENZE E LOCALI"
