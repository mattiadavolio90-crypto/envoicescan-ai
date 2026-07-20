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

    def test_vino_con_sigle_e_formato_non_dubbio(self):
        # 26/06: "BERNARDI PROSECCO VALDOB.DOCG ML 750 (5X6)" è pieno di sigle
        # (VALDOB/DOCG/ML/5X6) ma è VINO certo da regola forte → NON deve essere review.
        for d in ["BERNARDI PROSECCO VALDOB.DOCG ML 750 (5X6)",
                  "VAL D'OCA NERO DOCG ML 750 (1X6)"]:
            assert descrizione_e_dubbia(d, "VAV SRL", "VINI") is False, d

    def test_gdo_generico_NON_e_piu_dubbio(self):
        # 26/06: regola capovolta. Un GDO (Esselunga/Amazon) vende di tutto, ma una
        # sua riga categorizzata BENE non va flaggata solo per il fornitore. La
        # verifica-per-fornitore ha senso solo al contrario (mono-merce -> certo).
        assert descrizione_e_dubbia("RUCOLA", "ESSELUNGA S.P.A", "VERDURE") is False
        assert descrizione_e_dubbia("BANANE-KG 1", "ESSELUNGA S.P.A", "FRUTTA") is False
        assert descrizione_e_dubbia("PHILADELPHIA 200G", "AMAZON EU", "LATTICINI") is False

    def test_criptico_vero_senza_conferma_resta_dubbio(self):
        # Token illeggibili (senza vocali) e categoria NON confermata da dizionario/regola:
        # resta dubbio. NB: BERGA/CAISUN/CRAUDI NON sono più qui — il dizionario li censisce
        # come VERDURE (verdure asiatiche note), quindi non sono dubbi (vedi sotto).
        from services.ai_service import applica_correzioni_dizionario
        for desc in ["TRSSE TLTTE GM", "KRFT GRND MDLE", "SC XPLT NQR"]:
            assert applica_correzioni_dizionario(desc, "Da Classificare") == "Da Classificare", desc
            assert descrizione_e_dubbia(desc, "MEFON SRL", "VERDURE") is True, desc

    def test_voce_censita_in_dizionario_non_e_dubbia(self):
        # Cert. San Giuliano 26/06: una categoria CONFERMATA dal dizionario non è dubbia
        # anche con sigle/codici commerciali. Le verdure asiatiche note (BERGA, CAISUN)
        # sono nel dizionario → VERDURE certo → niente needs_review inutile.
        from services.ai_service import applica_correzioni_dizionario
        for desc in ["BERGA", "CAISUN", "CRAUDI"]:
            assert applica_correzioni_dizionario(desc, "Da Classificare") == "VERDURE", desc
            assert descrizione_e_dubbia(desc, "MEFON SRL", "VERDURE") is False, desc

    def test_descrizione_vuota_resta_dubbia(self):
        assert descrizione_e_dubbia("", "X", "PESCE") is True
        assert descrizione_e_dubbia(None, "X", "PESCE") is True

    def test_sigle_commerciali_con_categoria_certa_non_dubbie(self):
        # Cert. San Giuliano 26/06: il fastidio #1. Prodotti ovvi ma con codici/quantità
        # in testa (KG1, ML10X198, G500, GR 120) finivano needs_review in massa.
        # Se dizionario/regola conferma la categoria, le sigle NON la rendono dubbia.
        casi = [
            ("KG1 BURRO MC", "LATTICINI"),
            ("PATATE GRANDI 10KG", "VERDURE"),
            ("ZUCCHERO IN BUSTA DA 1KGX10", "SCATOLAME E CONSERVE"),
            ("KG5 PASTA SEM BARIL PEN.RIG.73", "PASTA E CEREALI"),
            ("ML10X198 BS.KETCHUP CALVE", "SALSE E CREME"),
            ("OLIO DI GIRASOLE PET 2X10LT", "OLIO E CONDIMENTI"),
            ("QUARTO POLLO HAL.ATM 2,5KG", "CARNE"),
        ]
        for desc, cat in casi:
            assert descrizione_e_dubbia(desc, "METRO ITALIA S.P.A", cat) is False, desc


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

    def test_mazzancolle_abbreviato_e_pesce(self):
        # cert. SUSHILAND 28/06: "MAZZANC." troncato (1 riga su ~200) finiva in FRUTTA;
        # la grafia abbreviata col punto è inequivocabilmente mazzancolla = PESCE.
        assert self._cat("MAZZANC. TROPICALE (EQCUADOR) 10X2,27KG 31/35")[0] == "PESCE"
        assert self._cat("MAZZANCOLLE TROPICALE(EQUADOR) 10X2,27KG 36/40")[0] == "PESCE"

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


class TestTreFamiglieSushiland2606:
    """Cert. SUSHILAND 26/06: dopo la simulazione sui 607, gli errori più costosi e
    ricorrenti su TUTTI i modelli erano 3 famiglie + il pet-food. Regole forti che
    le chiudono una volta sola, valide per ogni catena sushi futura."""

    def _cat(self, desc):
        return applica_regole_categoria_forti(desc, "Da Classificare")

    def test_stoviglie_monouso_in_materiale_non_manutenzione(self):
        # I 2 item più costosi del dataset (PLA da asporto) finivano in MANUTENZIONE
        # su mini/4.1-mini/4o. Sono monouso → MATERIALE.
        for d in ["ALCHEMY ABSTRACT PIATTO COUPE BOWL 20,3 CM APRDAF8 1",
                  "INKED BLACK NATURAL ORGANIC OBLONG CM 26X20 TDBKPLA31",
                  "PIATTO BIO COMPOSTABILE 23CM 50PZ", "BACCHETTE BAMBU MONOUSO 100PZ"]:
            assert self._cat(d)[0] == "MATERIALE DI CONSUMO", d

    def test_stoviglie_durevoli_restano_manutenzione(self):
        # regola di dominio consolidata: vasellame durevole professionale ≠ monouso
        for d in ["PIATTO CERAMICA 26CM", "POSATE ACCIAIO INOX SET 24PZ",
                  "VASSOIO DA ESPOSIZIONE 60*20"]:
            assert self._cat(d)[0] == "MANUTENZIONE E ATTREZZATURE", d

    def test_voci_bolletta_in_utenze(self):
        for d in ["TARIFFA ECCEDENZA III", "TRASMISSIONE", "SPREAD",
                  "ONERI DI SISTEMA", "DISPACCIAMENTO ENERGIA", "QUOTA POTENZA"]:
            assert self._cat(d)[0] == "UTENZE E LOCALI", d

    def test_sottovoci_bolletta_gergali_in_utenze(self):
        # cert. SUSHILAND 28/06: sottovoci di bolletta gas/acqua che NON contengono
        # parole-chiave evidenti (es. TARIFFA) ma terminologia tecnica inconfondibile.
        for d in ["COMP. RE FINO A 200.000 SMC", "COMP. UG1 FINO A 200.000 SMC",
                  "COMP. UC3 FINO A", "COMM.AL DETTAGLIO - PARTE FISSA",
                  "BONIFICA VILLORESI", "CONSUMO FATTURATO GAS"]:
            cat, motivo = self._cat(d)
            assert cat == "UTENZE E LOCALI", d
            assert motivo == "voce_bolletta_utenza", d

    def test_sottovoci_bolletta_non_toccano_alimenti(self):
        # guardia anti-falso-positivo: token come RE/UG/AL/SMC NON devono dirottare
        # prodotti alimentari che li contengono per caso.
        for d, cat_attesa in [("RE PESCE FRESCO", "PESCE"),
                              ("PROSCIUTTO COTTO AL DETTAGLIO", "SALUMI"),
                              ("UGO ROSSO VINO", "VINI"),
                              ("COMPOSTO PER TEMPURA", "PASTA E CEREALI")]:
            assert applica_regole_categoria_forti(d, cat_attesa)[0] == cat_attesa, d

    def test_fritti_giapponesi_non_sono_sushi_varie(self):
        assert self._cat("TEMPURA")[0] == "PASTA E CEREALI"
        assert self._cat("PASTELLA TEMPURA NISSHIN 1KG")[0] == "PASTA E CEREALI"
        assert self._cat("TAKOYAKI(MISURAKI) 500GX20PCX25PZ")[0] == "PESCE"
        assert self._cat("EBI FRY GAMBERO IMPANATO")[0] == "PESCE"

    def test_pet_food_resta_da_classificare(self):
        # non è alimento del ristorante: onesto -> Da Classificare, MAI PESCE
        for d in ["CATISFACTION SALMONE 400G", "FRISKIES CROCCHETTE GATTO",
                  "FELIX BUSTE MANZO 100G"]:
            cat, motivo = self._cat(d)
            assert cat == "Da Classificare", d
            assert motivo == "pet_food_non_alimento", d


class TestMenuPubAnglofono2007:
    """Cert. OFFSIDE 20/07: un pub ha il menù in inglese (BLACK BURGER, PULLED PORK,
    NUGGETS). Due bug indipendenti tenevano queste righe food ovvie in "Da Classificare":

      1. descrizione_e_dubbia marcava CRIPTICA ogni parola povera di vocali. L'inglese
         ne ha meno dell'italiano ("PORK" 1/4, "BLACK" 1/5, "PULLED" 2/6): parole vere
         venivano scambiate per sigle troncate → riga dubbia anche con AI 'alta' corretta.
      2. il DIZIONARIO non conosceva il vocabolario pub → nessuna conferma runtime, la
         riga dipendeva al 100% dall'umore dell'AI (spesso 'media' → coda).

    Fix: (1) una parola PRONUNCIABILE (nessuna corsa di >=4 consonanti) non è criptica
    anche se povera di vocali; (2) BURGER/NUGGETS/PULLED PORK->CARNE, CIABAT->FORNO,
    MOZZARELLIN->LATTICINI nel dizionario. Ora si categorizzano da sole, senza AI.
    """

    def _cat(self, desc):
        from services.ai_service import applica_correzioni_dizionario, applica_regole_categoria_forti
        dz = applica_correzioni_dizionario(desc, "Da Classificare")
        rf, _ = applica_regole_categoria_forti(desc, dz)
        return rf or dz

    def test_food_pub_confermato_dal_dizionario(self):
        # descrizioni REALI dal DB OFFSIDE: ora il dizionario le conferma da solo.
        casi = [
            ("BLACK BURGER G.100X20PZ EDNA", "CARNE"),
            ("BLACK NUGGETS CEDDAR C/JALAPENO KG1 AVIK", "CARNE"),
            ("PULLED PORK BITES KG.1 SALOMON", "CARNE"),
            ("PULLED PORK GELO 2PZ P.V.KG.1CA BALDI", "CARNE"),
            ("STINCO PROSCIUT PREC COLLEMILIA 550GRX12", "CARNE"),
            ("CIABAT.RUST.PRET. G.100X36PZ MASTERFOOD", "PRODOTTI DA FORNO"),
            ("MOZZARELLINE FRITTE 1KG", "LATTICINI"),
        ]
        for desc, cat in casi:
            assert self._cat(desc) == cat, f"{desc} atteso {cat}, avuto {self._cat(desc)}"

    def test_food_pub_non_e_piu_dubbio(self):
        # confermato dal dizionario => descrizione_e_dubbia deve dire False anche con
        # sigle/codici commerciali in coda (G.100X20PZ, KG1, ...).
        for desc, cat in [("BLACK BURGER G.100X20PZ EDNA", "CARNE"),
                          ("PULLED PORK BITES KG.1 SALOMON", "CARNE"),
                          ("CIABAT.RUST.PRET. G.100X36PZ MASTERFOOD", "PRODOTTI DA FORNO")]:
            assert descrizione_e_dubbia(desc, "RISTOPIU LOMBARDIA", cat) is False, desc

    def test_parola_inglese_non_e_criptica(self):
        # il cuore del fix #1: parole EN vere, povere di vocali, NON sono dubbie da sole.
        # Nessuna conferma dizionario passata (categoria None) → isola il trigger criptico.
        for desc in ["PULLED PORK BITES", "FILLET SOUTHERN FRIED", "BLACK BURGER"]:
            assert descrizione_e_dubbia(desc, "X", None) is False, desc

    def test_sigla_troncata_vera_resta_dubbia(self):
        # non-regressione: le vere sigle senza vocali (corsa di >=4 consonanti) restano
        # criptiche → riga dubbia se non confermata.
        assert descrizione_e_dubbia("KRFT GRND MDLE", "X", None) is True
        assert descrizione_e_dubbia("TRSSE TLTTE", "X", None) is True

    def test_portapanini_non_diventa_carne(self):
        # guardia falso-positivo: "50PORTA HAMBURG.COMP" è packaging monouso, NON carne.
        # "BURGER" non deve dirottare un contenitore. "HAMBURG" è troncato (non matcha
        # HAMBURGER né BURGER col boundary), quindi la riga NON finisce in CARNE.
        assert self._cat("50PORTA HAMBURG.COMP.15X15MP") != "CARNE"

    def test_panburger_resta_prodotti_da_forno(self):
        # "PANBURGER" (il pane del panino) contiene "BURGER" ma è preceduto da lettera:
        # il boundary del dizionario impedisce il match interno → resta PRODOTTI DA FORNO.
        assert self._cat("G100 PANBURGER SESAMO 50PZ") == "PRODOTTI DA FORNO"

    def test_burger_composto_e_carne(self):
        # Cert. OFFSIDE 20/07 (2° giro, febbraio): parole composte col burger attaccato
        # (ANGUSBURGER ×6 a 107€!) sfuggivano al confine di parola di HAMBURGER.
        # Ora "burger" come sotto-stringa → CARNE, per ogni cliente futuro.
        for d in ["ANGUSBURGER IRLANDA G.200X14PZ BALDI", "CHEESEBURGER 150G",
                  "CHICKENBURGER SURGELATO", "DOUBLE BACONBURGER"]:
            assert self._cat(d) == "CARNE", d

    def test_panburger_non_travolto_dal_burger_composto(self):
        # guardia critica dell'eccezione: la regola burger-sotto-stringa NON deve
        # dirottare il PANE del panino. PANBURGER resta PRODOTTI DA FORNO.
        for d in ["PANBURGER CLASSICO", "G100 PANBURGER SESAMO 50PZ",
                  "PANBURGER SENZA GLUTINE X6"]:
            assert self._cat(d) == "PRODOTTI DA FORNO", d

    def test_alette_pollo_sono_carne(self):
        # "DOR ALETTE DURANGO KG.5 AIA" ×4 a 139€ restava Da Classificare.
        for d in ["DOR ALETTE DURANGO KG.5 AIA", "ALETTE DI POLLO PICCANTI",
                  "CHICKEN WINGS HOT"]:
            assert self._cat(d) == "CARNE", d


class TestRuleTrapRimosse2606:
    """Le rule-trap che scavalcavano risposte AI corrette: ora NON devono più scattare."""

    def _cat(self, desc):
        return applica_regole_categoria_forti(desc, "Da Classificare")

    def test_spumilia_non_e_pesce(self):
        # SPUMILIA = cavolfiore siciliano (VERDURE), era hardcoded in _PESCE_RE
        assert self._cat("SPUMILIA FRESCA KG")[0] != "PESCE"

    def test_vit_troncato_non_e_manutenzione(self):
        # "VIT." abbreviazione di vitello: non deve cadere in MANUTENZIONE per "VITI"
        assert self._cat("VIT. SCALOPPINE 1KG")[1] != "manutenzione_edile"
        assert self._cat("FETTINE DI VIT.")[1] != "manutenzione_edile"

    def test_viti_ferramenta_vere_restano_manutenzione(self):
        # le viti vere (ferramenta) sì
        assert self._cat("VITI AUTOFILETTANTI 4X40 100PZ")[0] == "MANUTENZIONE E ATTREZZATURE"
