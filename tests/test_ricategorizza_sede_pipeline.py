"""La pipeline deterministica di scripts/ricategorizza_sede.py non deve divergere
dall'ingest di produzione.

Contesto: lo script aveva iniziato a concatenare il nome fornitore alla
descrizione prima di applicare dizionario e regole forti, per far vedere il
carrier alle regole telecom. Effetto collaterale misurato su 3.376 coppie reali:
19 divergenze dal percorso di produzione — "LINEA MARE SRL" fa scattare
_SERVIZI_CANONI_RE su "LINEA" (gamberi in SERVIZI), "COMO ACQUA S.R.L" fa
scattare _ACQUA_CONFEZIONATA_RE (bolletta idrica fra le bevande), e all'opposto
la ragione sociale davanti alla descrizione rompe i match del dizionario.

Lo script vive in scripts/ e non e' importabile (esegue I/O a import time), quindi
qui si fissa il CONTRATTO che la sua pipeline deve rispettare: stesso risultato
del LIVELLO 0 di produzione (ai_service.py:4564), descrizione mai contaminata.
"""

import pytest

from services.ai_service import (
    _is_fornitore_utenze_sempre,
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
)


def _pipeline(desc, fornitore=None):
    """Replica di pipeline_deterministica (scripts/ricategorizza_sede.py)."""
    if fornitore:
        is_utility, _ = _is_fornitore_utenze_sempre(fornitore)
        if is_utility:
            return "UTENZE E LOCALI"
    cat = applica_correzioni_dizionario(desc, "Da Classificare")
    cat, _ = applica_regole_categoria_forti(desc, cat)
    return cat


class TestFornitoreNonContaminaLaDescrizione:
    @pytest.mark.parametrize("desc", [
        "GAMBERO ROSSO MEDITERRANEO",
        "SCAMPO 20/30 BORDO CONG",
        "RICCIOLA OCEANICA IKEJIME",
    ])
    def test_linea_nel_fornitore_non_manda_il_pesce_in_servizi(self, desc):
        """'LINEA MARE SRL' contiene LINEA, che _SERVIZI_CANONI_RE riconosce come
        canone telefonico: concatenandolo, 24 righe di pesce finivano in SERVIZI."""
        assert _pipeline(desc, "LINEA MARE SRL") == "PESCE"

    @pytest.mark.parametrize("desc", [
        "ARROTONDAMENTO ATTUALE",
        "ONERI PEREQUAZIONE",
        "ACCONTI BOLLETTE PRECEDENTI",
    ])
    def test_bolletta_idrica_resta_utenze_e_non_diventa_bevanda(self, desc):
        """'COMO ACQUA S.R.L' e' un fornitore utility: le sue righe vanno in
        UTENZE per hard override, non in ACQUA (che e' food cost)."""
        assert _pipeline(desc, "COMO ACQUA S.R.L") == "UTENZE E LOCALI"

    @pytest.mark.parametrize("desc,atteso", [
        ("QUATTRO FORMAGGI", "LATTICINI"),
        ("TARTARE DI MANZO", "CARNE"),
        ("FUNGHI", "VERDURE"),
    ])
    def test_ragione_sociale_non_degrada_i_match_del_dizionario(self, desc, atteso):
        """Regressione di segno opposto: la ragione sociale anteposta rompeva il
        match e degradava a Da Classificare una riga gia' classificabile."""
        assert _pipeline(desc, "RISTORANTE MONOPOLI SRL") == atteso

    def test_stesso_esito_con_e_senza_fornitore_non_utility(self):
        """Per un fornitore non-utility il fornitore non deve cambiare nulla."""
        for desc in ("QUATTRO FORMAGGI", "GAMBERO ROSSO MEDITERRANEO", "FUNGHI"):
            assert _pipeline(desc, "RISTORANTE MONOPOLI SRL") == _pipeline(desc)


class TestOverrideUtilityRestaAttivo:
    def test_fornitore_telecom_forza_utenze(self):
        """Lo scopo originale della modifica — far vedere il carrier alle regole —
        resta soddisfatto, ma via LIVELLO 0 invece che per concatenazione."""
        assert _pipeline("TRAFFICO DATI NAZIONALE", "WINDTRE SPA") == "UTENZE E LOCALI"

    def test_descrizione_windtre_classificata_anche_senza_fornitore(self):
        """Il fix in _FORNITORI_TELECOM_UTENZE_RE copre il caso in cui il carrier
        e' nella descrizione (WIND non matchava WINDTRE per via del \\b)."""
        cat, motivo = applica_regole_categoria_forti(
            "COSTO WINDTRE PIU' SICURI MOBILE", "Da Classificare")
        assert cat == "UTENZE E LOCALI"
        assert motivo == "fornitore_telecom_utenze"
