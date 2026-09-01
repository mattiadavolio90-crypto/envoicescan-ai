"""Fase 1 — "VASCHETTA": contenitore venduto o modo in cui il cibo e' confezionato?

`_CONSUMO_EXTRA_RE` esiste per una ragione giusta (cert. SUSHILAND 26/06): il non-food
va deciso PRIMA del food, o "VASCHETTA SUSHI" finisce fra i pesci. Ma "VASCHETTA" e'
l'unico termine di quella regex che nomina tanto il contenitore quanto il modo in cui
un alimento e' venduto, e la regola presa alla lettera perdeva piu' di quanto salvasse.

Misurato a DB il 1/9/2026 — righe non cancellate contenenti "VASCHETT[AE]":

    LATTICINI             38    358,80 EUR   <- cibo
    MATERIALE DI CONSUMO  37  1.988,09 EUR   <- imballo
    GELATI E DESSERT      28    864,35 EUR   <- cibo
    SPEZIE E AROMI         5      5,76 EUR   <- cibo
    SALSE E CREME          2     51,85 EUR   <- cibo

73 righe di cibo contro 37 di imballo. E lo STESSO prodotto — "MOZZARELLA FIOR DI LATTE
GR 250 VASCHETTA KG 1" — vive a DB in LATTICINI (35 righe) e in MATERIALE DI CONSUMO (5):
due percorsi di categorizzazione, due esiti, stessa descrizione. E' il sintomo D14 in
forma pura, ed e' cio' che la Fase 1 esiste per eliminare.

Discriminante scelta, letta sui dati veri e non inventata: l'imballo NOMINA il materiale
o il formato di confezionamento (PLAST, ALLUMINIO, SUSHI, MICROONDE, LIDS, 400PZ, CC600);
l'alimento parla solo di se stesso e della sua pezzatura (GR 250, KG 1).

I 24 casi qui sotto sono TUTTE le descrizioni distinte con "VASCHETTA" presenti a DB:
non un campione. Sull'intero catalogo reale (6.959 descrizioni distinte) questa modifica
cambia esattamente 4 righe — le mozzarelle — e nient'altro.
"""
from __future__ import annotations

import pytest

from services.ai_service import (
    _e_consumo_extra,
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
)

MATERIALE = "MATERIALE DI CONSUMO"


def _pipeline(descrizione: str) -> str:
    cat = applica_correzioni_dizionario(descrizione, "Da Classificare")
    cat, _motivo = applica_regole_categoria_forti(descrizione, cat)
    return cat


class TestVaschettaEUnAlimento:
    """Il cibo venduto in vaschetta e' cibo. Sono righe vere, tutte a DB."""

    @pytest.mark.parametrize("descrizione,attesa", [
        ("MOZZARELLA FIOR DI LATTE GR 250 VASCHETTA KG 1", "LATTICINI"),
        ("MOZZARELLA FIOR DI LATTE GR 250 VASCHETTA KG 1 G/C", "LATTICINI"),
        ("MOZZARELLA CILIEGINA GR 10 VASCHETTA KG 1", "LATTICINI"),
        ("MOZZARELLA CILIEGINA GR 10 VASCHETTA KG 1 SCAD 10/07/26", "LATTICINI"),
        ("BASILICO VASCHETTA G 30***", "SPEZIE E AROMI"),
        ("BASILICO IN VASCHETTA", "SPEZIE E AROMI"),
        ('VASCHETTA "GRAN GALA" CREMA 2800 ML--', "GELATI E DESSERT"),
        ('VASCHETTA "GRAN GALA" RISO 2800 ML--', "GELATI E DESSERT"),
        ('VASCHETTA "GRAN GALA" THE VERDE 2800 ML--', "GELATI E DESSERT"),
        ("VASCHETTA DA 500 GR DI GELATO SFUSO", "GELATI E DESSERT"),
        ("VASCHETTA DA 1.000 GR DI GELATO SFUSO", "GELATI E DESSERT"),
        ("PASTA DI ROBIOLA VASCHETTA ANTICHI SAPORI", "SALSE E CREME"),
    ])
    def test_alimento_in_vaschetta_resta_alimento(self, descrizione, attesa):
        assert _pipeline(descrizione) == attesa


class TestVaschettaEImballo:
    """La controprova che conta: la regola non deve svuotarsi. Se questi passassero a
    food, la modifica avrebbe solo spostato l'errore dall'altra parte."""

    @pytest.mark.parametrize("descrizione", [
        "VASCHETTA SUSHI FIORI C+C 225X100 H50 400PZ",
        "VASCHETTA SUSHI CON FIORI C+C 175X125 H50 400PZ",
        "VASCHETTA SUSHI FIORI C+C 140X85 H50 800PZ",
        "BLACK VASCHETTA SUSHI NERO C+C 170X90 H54 600PZ",
        "HP01 VASCHETTA DI PLAST TO0.4",
        "HP00 VASCHETTA DI PLAST TO0.0",
        "HP03 VASCHETTA DI PLAST TO0.8",
        "HP61 VASCHETTA DI PLAST WH53",
        "PP500G VASCHETTA DI PLAST",
        "FH750 HQ LIDS VASCHETTA DI PLAST",
        "FH500 HQ LIDS 500PZ/CT VASCHETTA DI PLAST",
        "VASCHETTA DI ALUMINIO",
        "VASCHETTA ALLUMINIO14X100PZ 2",
        "VASCHETTE INC MICROONDE ONDI CC600 PZ50",
        "VASCHETTE INC MICROONDE ONDI CC1000 PZ50",
        "VASCHETTE INC MICROONDE ONDI CC250 PZ50",
    ])
    def test_contenitore_venduto_resta_materiale(self, descrizione):
        assert _pipeline(descrizione) == MATERIALE

    def test_materiale_attaccato_al_formato(self):
        """'ALLUMINIO14X100PZ' e' una parola sola nelle descrizioni vere: un
        word-boundary a destra di ALLUMINIO non matcherebbe, e la riga sarebbe
        finita fra gli alimenti. E' il motivo per cui la regex non usa \\b."""
        assert _pipeline("VASCHETTA ALLUMINIO14X100PZ 2") == MATERIALE


class TestGliAltriTerminiNonSonoToccati:
    """La disambiguazione vale SOLO per "VASCHETTA". Gli altri termini di
    _CONSUMO_EXTRA_RE non nominano mai un alimento, e restano assoluti."""

    @pytest.mark.parametrize("descrizione", [
        "CARTA PER RAVIOLI",
        "GUANTI LATTICE LOGEX MONO",
        "SACCHETTI SPAZZATURA 70X110",
        "DETERSIVO PIATTI CONCENTRATO",
        "TOVAGLIOLI 33X33 BIANCHI",
    ])
    def test_termine_non_ambiguo_decide_da_solo(self, descrizione):
        assert _e_consumo_extra(descrizione.upper()) is True

    def test_vaschetta_senza_contesto_non_e_imballo(self):
        assert _e_consumo_extra("MOZZARELLA FIOR DI LATTE GR 250 VASCHETTA KG 1") is False

    def test_vaschetta_con_altro_termine_resta_imballo(self):
        """Se nella riga c'e' anche un termine non ambiguo, decide quello: la
        guardia si applica solo quando VASCHETTA e' l'unica ragione del match."""
        assert _e_consumo_extra("VASCHETTA E TOVAGLIOLI 33X33") is True


class TestUnSoloPuntoDiVerita:
    """_CONSUMO_EXTRA_RE ha tre siti d'uso, due dei quali in NEGAZIONE (dimsum,
    pesce). Se la disambiguazione vivesse solo nel sito affermativo, "MOZZARELLA
    ... VASCHETTA" smetterebbe di essere imballo li' e resterebbe imballo negli
    altri due: si sarebbe creata una settima pipeline divergente invece di
    eliminarne una. Questo test e' la ragione per cui esiste `_e_consumo_extra`."""

    def test_i_tre_siti_passano_dallo_stesso_helper(self):
        import inspect

        from services import ai_service

        src = inspect.getsource(ai_service.applica_regole_categoria_forti)
        assert "_CONSUMO_EXTRA_RE.search" not in src, (
            "un sito consulta ancora la regex grezza: la disambiguazione VASCHETTA "
            "non lo raggiunge"
        )
        assert src.count("_e_consumo_extra(desc_u)") >= 2

    def test_carta_pesce_resta_imballo_nel_ramo_pesce(self):
        """Il sito in negazione: 'CARTA PESCE' e' carta da banco, non pesce."""
        assert _pipeline("CARTA PESCE 500 FOGLI") == MATERIALE
