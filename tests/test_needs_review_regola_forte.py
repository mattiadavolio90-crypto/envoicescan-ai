"""Regressione cert. SUSHILAND 26/06: una descrizione mono-parola NON deve essere
marcata needs_review se una REGOLA FORTE deterministica ha già assegnato quella
categoria.

Bug originale: descrizione_e_dubbia marcava needs_review ogni riga con < 2 token
alfabetici. I prodotti SUSHILAND hanno descrizioni mono-parola ("SALMONE", "RUCOLA",
"LIMONE") ma categoria certissima da regola forte → 34% delle righe finiva
needs_review, restava fuori dai margini e gonfiava il MOL senza valore di verifica.

Fix: se applica_regole_categoria_forti assegna ESATTAMENTE la categoria finale,
la brevità della descrizione non rende la riga dubbia. Gli altri trigger
(descrizione criptica, fornitore non-food generico su categoria food) restano attivi.
"""
from services.ai_service import (
    descrizione_e_dubbia,
    applica_regole_categoria_forti,
)


class TestRegolaForteSbloccaMonoParola:

    def test_pesce_mono_parola_non_dubbio(self):
        assert applica_regole_categoria_forti("SALMONE", "Da Classificare")[0] == "PESCE"
        assert descrizione_e_dubbia("SALMONE", "ADC S.R.L", "PESCE") is False
        assert descrizione_e_dubbia("TONNO", "X", "PESCE") is False

    def test_bevanda_mono_parola_non_dubbia(self):
        assert descrizione_e_dubbia("COCA COLA", "PARTESA S.R.L", "BEVANDE") is False

    def test_ortofrutta_nuda_nota_non_dubbia(self):
        for desc, cat in [
            ("RUCOLA", "VERDURE"), ("ICEBERG", "VERDURE"), ("ZUCCHINE", "VERDURE"),
            ("CAROTE", "VERDURE"), ("POMODORO", "VERDURE"), ("AGLIO", "VERDURE"),
            ("LIMONE", "FRUTTA"), ("FRAGOLA", "FRUTTA"), ("MANGO", "FRUTTA"),
            ("ARANCIA", "FRUTTA"), ("ANANAS", "FRUTTA"), ("MELAGRANA", "FRUTTA"),
        ]:
            cat_forte, motivo = applica_regole_categoria_forti(desc, "Da Classificare")
            assert cat_forte == cat, f"{desc} atteso {cat}, avuto {cat_forte}"
            assert motivo in ("verdura_nuda", "frutta_nuda")
            assert descrizione_e_dubbia(desc, "MEFON SRL", cat) is False, desc


class TestNonRegressioneTriggerRimanenti:
    """I segnali di prudenza legittimi NON devono essere disattivati dal fix."""

    def test_descrizione_criptica_resta_dubbia(self):
        # token senza vocali → resta da rivedere anche se categoria food
        assert descrizione_e_dubbia("KRFT GRND MDLE", "X", "PASTA E CEREALI") is True

    def test_gdo_generico_NON_e_piu_dubbio(self):
        # 26/06: regola capovolta. Un GDO (Esselunga/Amazon) vende di tutto, ma una
        # sua riga categorizzata BENE non va flaggata solo per il fornitore. La
        # verifica-per-fornitore ha senso solo al contrario (mono-merce -> certo).
        assert descrizione_e_dubbia("RUCOLA", "ESSELUNGA S.P.A", "VERDURE") is False
        assert descrizione_e_dubbia("BANANE-KG 1", "ESSELUNGA S.P.A", "FRUTTA") is False
        assert descrizione_e_dubbia("PHILADELPHIA 200G", "AMAZON EU", "LATTICINI") is False

    def test_esotici_ambigui_senza_regola_forte_restano_dubbi(self):
        # Verdure asiatiche ambigue: nessuna regola forte → restano da classificare/rivedere.
        for desc in ["CRAUDI", "BERGA", "CAISUN", "KANKONG", "PIATONE"]:
            _, motivo = applica_regole_categoria_forti(desc, "Da Classificare")
            assert motivo is None, f"{desc} non deve avere regola forte"
            assert descrizione_e_dubbia(desc, "MEFON SRL", "VERDURE") is True, desc

    def test_descrizione_vuota_resta_dubbia(self):
        assert descrizione_e_dubbia("", "X", "PESCE") is True
        assert descrizione_e_dubbia(None, "X", "PESCE") is True


class TestLacuneMerceologicheSushiland:
    """Cert. SUSHILAND 26/06: prodotti banali che restavano Da Classificare o
    male assegnati perché né dizionario né regole li coprivano."""

    def _cat(self, desc):
        cat, motivo = applica_regole_categoria_forti(desc, "Da Classificare")
        return cat, motivo

    def test_pesce_extra(self):
        for d in ["GAMBERO ROSSO MEDITERRANEO", "KG1 GAMB ROSSO MEDIT 56+",
                  "CAPESANTE CONGELATO 900G", "TRANCIO DI SPADA -WOFCO-", "PESCE SPADA"]:
            assert self._cat(d)[0] == "PESCE", d

    def test_latticini_extra(self):
        for d in ["MOZZ.X PIZZA ESS.-GR 350", "S.LUCIA MOZZ.4X100", "SOTTILETTE CLAS",
                  "TOMINI FRESCHI 140 G", "ACTIMEL FRAGOLA X12", "PHILADELPHIA 1650G"]:
            assert self._cat(d)[0] == "LATTICINI", d

    def test_carne_extra(self):
        for d in ["CHICKEN FRITTO STICK", "CHUCK-ROLL BOV.AD.(EXTRA)", "PETTO TACCH. 200G",
                  "G800 FIORENT.SCOTT.SV"]:
            assert self._cat(d)[0] == "CARNE", d

    def test_materiale_consumo_extra(self):
        for d in ["SCARPE ANTINFORTUNISTICHE BASSE", "DIXAN POLVERE 60 MIS.",
                  "VASCHETTA SUSHI CON FIORI", "CARTA PER RAVIOLI 20X500PZ", "SPAZZOLA GRIP BUCATO"]:
            assert self._cat(d)[0] == "MATERIALE DI CONSUMO", d

    def test_manutenzione_edile(self):
        for d in ["BATTISCOPA PVC WHITE OAK", "CEMENTO RAPIDO KG 5",
                  "PATTEX MILLECHIODI CRYSTAL", "COMPENSATO DI PIOPPO", "LAVATOIOPVC"]:
            assert self._cat(d)[0] == "MANUTENZIONE E ATTREZZATURE", d

    def test_bevande_brand(self):
        for d in ["MONSTER", "C.COLA ZERO LATT.33X8", "SANBITTER POMPELMO X4"]:
            assert self._cat(d)[0] == "BEVANDE", d

    def test_acqua_brand_non_bevande(self):
        # regressione diretta del bug citato dal cliente: ACQ PANNA era BEVANDE
        for d in ["ACQ PANNA 75 CLX16 VR", "ACQ S.PELLEGRINO GAS 75CLX16VR"]:
            assert self._cat(d)[0] == "ACQUA", d

    def test_mozzarella_pizza_e_latticino_non_forno(self):
        assert self._cat("MOZZ.X PIZZA ESS.-GR 350")[0] == "LATTICINI"
        # ma la pizza vera resta PRODOTTI DA FORNO
        assert self._cat("PIZZA MARGHERITA SURGELATA")[0] == "PRODOTTI DA FORNO"

    def test_no_falsi_positivi(self):
        # parole che NON devono attivare le nuove regole
        assert self._cat("SPADA DA CUCINA INOX")[1] != "pesce_extra"
        assert self._cat("VITELLO SCALOPPINE")[1] != "manutenzione_edile"
        assert self._cat("PILAF DI RISO")[1] != "consumo_extra"
        assert self._cat("SPADELLATA DI VERDURE")[1] != "pesce_extra"

    def test_piatto_composto_non_diventa_ingrediente(self):
        # l'ingrediente nominato NON è il prodotto: piatti pronti/dolci restano
        # Da Classificare (onesto) invece di finire nella categoria dell'ingrediente.
        for d in ["KG1 MINI CROCCHE MOZZ/PROSC.MC", "KG1 PANZEROTTINI POM/MOZZ MC",
                  "STRUDEL MELE CLASSICO", "PRINCIPESSA (FRAGOLA)"]:
            cat, motivo = self._cat(d)
            assert motivo not in ("latticini_extra", "frutta_nuda", "verdura_nuda", "carne_extra"), d

    def test_ortofrutta_topping_e_aromi_non_sono_ortofrutta(self):
        # FOCACCIA CON CIPOLLA -> non VERDURE; CARAMELLE/COCKTAIL AL GUSTO DI UVA -> non FRUTTA
        for d in ["FOCACCIA CON CIPOLLA-KG 1", "CARAMELLE GOMMOSE AL GUSTO DI UVA",
                  "COCKTAIL AL GUSTO DI UVA VERDE"]:
            cat, motivo = self._cat(d)
            assert motivo not in ("frutta_nuda", "verdura_nuda"), d
