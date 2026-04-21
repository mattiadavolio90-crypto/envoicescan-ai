"""Test per services/ai_service.py — Dizionario correzioni e priorità cache memoria."""
import pytest
from unittest.mock import MagicMock, patch
import services.ai_service as ai_mod
from services.ai_service import applica_correzioni_dizionario, applica_regole_categoria_forti, invalida_cache_memoria
import json


class TestApplicaCorrezioniDizionario:
    """Verifica priorità: ALIMENTO > CONTENITORE, e match keyword."""

    def test_carne(self):
        assert applica_correzioni_dizionario("SALSICCIA FRESCA", "Da Classificare") == "CARNE"

    def test_verdura(self):
        result = applica_correzioni_dizionario("CAROTE FRESCHE", "Da Classificare")
        assert result in ("FRUTTA E VERDURA", "ORTOFRUTTA", "VERDURE")

    def test_alimento_priorita_su_contenitore(self):
        """Se nella descrizione c'è sia cibo che contenitore, vince il cibo."""
        result = applica_correzioni_dizionario("SALSICCIA VASCHETTA", "Da Classificare")
        assert result == "CARNE"  # Non MATERIALE DI CONSUMO

    def test_solo_contenitore(self):
        """Se c'è solo un contenitore, deve essere MATERIALE DI CONSUMO."""
        result = applica_correzioni_dizionario("VASCHETTE ALLUMINIO", "Da Classificare")
        assert result == "MATERIALE DI CONSUMO"

    def test_nessun_match(self):
        """Nessun keyword trovato → restituisce categoria AI originale."""
        result = applica_correzioni_dizionario("ARTICOLO GENERICO XYZ", "BEVANDE")
        assert result == "BEVANDE"

    def test_stringa_vuota(self):
        assert applica_correzioni_dizionario("", "CARNE") == "CARNE"

    def test_none(self):
        assert applica_correzioni_dizionario(None, "PESCE") == "PESCE"

    def test_case_insensitive(self):
        """Il match è case-insensitive (la funzione fa .upper())."""
        result = applica_correzioni_dizionario("salsiccia fresca", "Da Classificare")
        assert result == "CARNE"

    @pytest.mark.parametrize(
        "descrizione",
        [
            "MAIS DOLCE TRIS SIGMA GR",
            "PROVOL.DOLCE VALPADANA DO",
        ],
    )
    def test_dolce_generico_non_forza_pasticceria(self, descrizione):
        result = applica_correzioni_dizionario(descrizione, "Da Classificare")
        assert result != "PASTICCERIA"


class TestRegoleFortiCategorizzazione:
    def _finale(self, descrizione: str):
        categoria = applica_correzioni_dizionario(descrizione, "Da Classificare")
        return applica_regole_categoria_forti(descrizione, categoria)

    @pytest.mark.parametrize(
        ("descrizione", "attesa"),
        [
            ("ARANCE DA SPREMUTA (15KG)", "FRUTTA"),
            ("CIF C CANDEG SPRAY ML650 LIMONE", "MATERIALE DI CONSUMO"),
            ("GOMA WAKAME SALAD (AT) (AT)", "SUSHI VARIE"),
            ("SATONO YUKI TOFU FIRM", "LATTICINI"),
            ("CIP. TRECCIA 600 G-GR 600", "VERDURE"),
            ("CASTAGNE D' ACQUA CINESI AT *", "SCATOLAME E CONSERVE"),
            ("COPPA CIP CIOK X", "GELATI"),
            ("LMA VASC LIMONE", "GELATI"),
            ("MARTINI BIANCO L1", "AMARI/LIQUORI"),
            ("FEVER TREE PINK GRAPEFRUIT CL20 VP", "BEVANDE"),
            ("SANTHE' PESCA 33CL-CL 33", "BEVANDE"),
            ("KG1 ALBUME MC", "UOVA"),
            ("INS. ROMANA PAD. (IT II)", "VERDURE"),
            ("TABASCO BT ML60 (12) MC.ILHENNY", "SALSE E CREME"),
            ("PRODUCTS (::P887101::2026-01-16:2026-01-31)", "SERVIZI E CONSULENZE"),
            ("LAMPONI GR125 IL MERCATO", "FRUTTA"),
            ("SHOCK SENSOR", "MATERIALE DI CONSUMO"),
            ("VAL D'OCA NERO DOCG ML 750 (5X6)", "VINI"),
            ("PANETTONE KG 1", "PASTICCERIA"),
            ("PANDORO 1 KG", "PASTICCERIA"),
            ("MACARONS ARTISANALE PZ 432 (12X36) ASSORTITI", "PASTICCERIA"),
            ("MARITOZZO MIDI FARCITO SURG GR 50 PZ 15", "PASTICCERIA"),
            ("MOCCHI CIOCCOLATO 1X10X6PZ", "PASTICCERIA"),
            ("PLN010817 ELFBAR ELFA PREFILLED POD BLUEBERRY ( ) MG", "SHOP"),
            ("PLN012184 LOST MARY TOCA AIR POD 20MG SPEARMINT", "SHOP"),
            ("OCB CARTINA NERA CORTA DOPPIA 25LIBRETTIX100FOGLI", "SHOP"),
            ("SMOKING FILTRI SLIM SIZE LUNGHI 22MMX6MM 30X120UNT", "SHOP"),
            ("VIVIDENT XYLIT SPEARMINT STICK PZ.40", "SHOP"),
            ("VIGORSOL AIR ACTION ASTUCCIO PZ.20", "SHOP"),
            ("RICOLA MELISSA LIMONCELLA PZ.20", "SHOP"),
            ("PEDAGGI AUTOSTRADALI", "SERVIZI E CONSULENZE"),
            ("TRATTENIMENTI DAL VIVO SENZA BALLO", "SERVIZI E CONSULENZE"),
            ("TOT. TRX 'UNICAPOS' DIC '25-GEN '26", "SERVIZI E CONSULENZE"),
            ("INVIO TELEMATICO MODELLO F24 N.2 MESE DI SETTEMBRE'25", "SERVIZI E CONSULENZE"),
            ("SERVIZIO INVIO TELEMATICO F24", "SERVIZI E CONSULENZE"),
            ("INFOCERT CODICE FIRMA CON SPID M11-25", "SERVIZI E CONSULENZE"),
            ("NOLEGGIO ESERCENTE - COD. ESER.: 624283 - COD. TERMINALE: 02310589", "SERVIZI E CONSULENZE"),
            ("SPESE INCASSO", "SERVIZI E CONSULENZE"),
            ("UNA TANTUM ATTIVAZIONE CASHBACK CIRCUITO SCONTIPOSTE 10,00", "SERVIZI E CONSULENZE"),
            ("SALDO CONTRIBUTO ANNUALE ECOMAP 2025", "SERVIZI E CONSULENZE"),
            ("CIALDE CELLINI DECAFFEINATO BOX", "CAFFE E THE"),
            ("CAPSULE FAP CELLINI GINSENG 1X50", "CAFFE E THE"),
            ("TAZZE+PIAT CAFFE'CELLINI", "MANUTENZIONE E ATTREZZATURE"),
            ("PORTAZUCCHERO CELLINI", "VARIE BAR"),
            ("PREPARATO X GINSENG CON ZUCCH LATT", "CAFFE E THE"),
            ("GEKKEIKAN SAKE 1,8LT 14,5% 6*1,8LT", "DISTILLATI"),
            ("TANQUERAY ALCOHOL FREE 0.0% 700ML -", "DISTILLATI"),
            ("FONTANAVECCHIA FALANG. DEL TAB. DOP ML750 (5X6)", "VINI"),
            ("ROASTBEEF B.A. Q MAIUSCOLA", "CARNE"),
            ("NOCE SCOTTONA BRE KG6 S/V F EJENDU", "CARNE"),
            ("MACINATO BOV.SV KG1", "CARNE"),
            ("MAGATELLO BOV ADULTO KG2+ S/V F TERNERA", "CARNE"),
            ("PREP CARNE TRITA BOV ADULTO KG1 S/V F", "CARNE"),
            ("MORT.MODENA CIL. C/P KG6 MZ CRTX2 NGR", "SALUMI"),
            ("SAL.VENTRICINA PICCANTE KG2,8 CTX1PZ MNT", "SALUMI"),
            ("G800 CALAM PATA PUL12/14 IQFMC", "PESCE"),
            ("POLPETTI 20/40 IND GR800 (12) IQF C", "PESCE"),
            ("GAMB.ROSSO SICIL.20/25 G.800 Q MAIUSCOLA", "PESCE"),
            ("SEPPIOLINE PUL 8/12 IN GR800 (10) IQF", "PESCE"),
            ("TAKOYAKI(MISURAKI) 500GX20PCX25PZ", "PESCE"),
            ("MUFFINS CON GLASSA", "PASTICCERIA"),
            ("CREAMI - RICARICA PISTACCHIO", "PASTICCERIA"),
            ("CREAMI - DISPENSER SINGOLO", "MANUTENZIONE E ATTREZZATURE"),
            ("BLEND T GUNPOWDER 15 FILTRI", "CAFFE E THE"),
            ("LATTIERA EUROPA 50 CL LOGO", "LATTICINI"),
            ("TOPPING CIOCCOLATO CACAO 1KG", "VARIE BAR"),
            ("TOPPING FRUTTI BOSCO KG.1 TOSCHI", "VARIE BAR"),
            ("VASSOIO DA ESPOSIZIONE 60*20", "MANUTENZIONE E ATTREZZATURE"),
            ("ORZO 200GR", "CAFFE E THE"),
            ("PACK PROTEZIONE (6 SHOCK SENSOR) 1 UN", "MANUTENZIONE E ATTREZZATURE"),
            ("SENSORE DI MOVIMENTO CERTIFICATO CON FOTOCAMERA 1 UN", "MANUTENZIONE E ATTREZZATURE"),
            ("GROSTOLI X 2 KG", "PASTICCERIA"),
            ("ZEPPOLE X 9 PZ", "PASTICCERIA"),
            ("CAMICIA DONNA TENERIFE BIANCO", "MANUTENZIONE E ATTREZZATURE"),
            ("CRAVATTINO BISCOTTO", "MANUTENZIONE E ATTREZZATURE"),
            ("50 CONTEN.MONOP.IN PET ML96", "MATERIALE DI CONSUMO"),
            ("100PZ FINGERF. COMP. FOGLIA MP", "MATERIALE DI CONSUMO"),
            ("VISITA MEDICA MANSIONE BARISTA - CAMERIERE IN DATA 31/03/2026", "SERVIZI E CONSULENZE"),
            ("SPUNTINELLE MORATO GR 700", "PRODOTTI DA FORNO"),
            ("DOLCIFICANTE RISTORA LIGHT 150 BUSTINE", "VARIE BAR"),
            ("MOROSITAS ASS.SC.24PZ", "SHOP"),
            ("POCKET COFFEE T5X32PZ - POCKET COFFE", "SHOP"),
            ("PIX-HCG-886461/1 PUNTO METALLICO - MENU MARZO FSC MIX 70% TSUD-COC-001228 058179015468315", "SERVIZI E CONSULENZE"),
            ("FISHERMAN'S BIANCA X 24 PZ", "SHOP"),
            ("COMPENSO PER PRESTAZIONE PROFESSIONALE RELATIVA A: RESTYLING GRAFICO E AGGIORNAMENTO CONTENUTI DEI M", "SERVIZI E CONSULENZE"),
            ("APERTURA PRATICA", "SERVIZI E CONSULENZE"),
            ("NPSACCHETTO COMPOST.LE", "MATERIALE DI CONSUMO"),
            ("ODK POLPA FRUTTI DI BOSCO KG1***", "VARIE BAR"),
            ("ODK SCIROPPO VANIGLIA ML750***", "VARIE BAR"),
            ("G180CARPACCIO TARTUFO NERO EST", "SCATOLAME E CONSERVE"),
            ("MIZKAN SHIRAGIKU ACETO DI RISO 20LT", "OLIO E CONDIMENTI"),
            ("UNAGI KABAYAKI 240-275G #4968 (10KG)2*5KG", "PESCE"),
            ("RAVIOLI DI GAMBERI HAUKAU - AT ( )5*2KG", "SECCO"),
            ("SHAOMAI DI GAMBERI 20PZ", "SECCO"),
            ("GYOZA DI CARNE 600G", "SECCO"),
            # --- Regole apr20 batch 2: prodotti Da Classificare ---
            ("LIQ.ANIMA NERA CL.70 21GR MARZADRO", "AMARI/LIQUORI"),
            ("DENTICI O PAGARO MAGGIORE 1000+ FRESCO PAGRUS MAJOR ALLEVATE GRECIA (FIO", "PESCE"),
            ("UNICUM CL.70", "AMARI/LIQUORI"),
            ("MALIBU' CL.100", "AMARI/LIQUORI"),
            ("PISELLI FINI KG.2,5", "VERDURE"),
            ("LIEVITO FRESCO G.25X2 LIEVITAL", "SECCO"),
            ("PAGRO MAGGIORE 600+ FRESCO ALLEVATO PAGRUS MAJOR ALLEVATE GRECIA (COP0", "PESCE"),
            # --- Errori di categorizzazione ---
            ("SALV.LIMONE X100 TNT 70X100", "MATERIALE DI CONSUMO"),
            ("TORTELLI AL RADICCH.ROSSO KG.3 SURGITAL", "SECCO"),
            ("RICE FLAKES 30X227G", "SECCO"),
            # --- Fix M1 (audit 2026-04-20): keyword nuove ---
            ("REVISORE LEGALE ANNO 2025", "SERVIZI E CONSULENZE"),
            ("COUPON LIDL PLUS 5", "📝 NOTE E DICITURE"),
            ("BUONO SCONTO 10%", "📝 NOTE E DICITURE"),
        ],
    )
    def test_regole_forti_residui_audit(self, descrizione, attesa):
        categoria, _ = self._finale(descrizione)
        assert categoria == attesa


class TestClassificaConAiFallback:
    def test_json_non_valido_non_collassa_su_materiale(self):
        fake_client = MagicMock()
        with patch('services.ai_service._chiama_gpt_classificazione', side_effect=json.JSONDecodeError('msg', 'doc', 0)):
            result = ai_mod.classifica_con_ai([
                'BLEND T GUNPOWDER 15 FILTRI',
                'CREAMI - RICARICA PISTACCHIO',
            ], openai_client=fake_client)
        assert result == ['Da Classificare', 'Da Classificare']

    def test_eccezione_ai_usa_fallback_neutro(self):
        fake_client = MagicMock()
        with patch('services.ai_service._chiama_gpt_classificazione', side_effect=RuntimeError('boom')):
            result = ai_mod.classifica_con_ai([
                'ARTICOLO GENERICO XYZ',
                'ALTRO ARTICOLO SENZA MATCH',
            ], openai_client=fake_client)
        assert result == ['Da Classificare', 'Da Classificare']


# ============================================================
# GROUP B: priorità cache in-memory (ottieni_categoria_prodotto)
# ============================================================

class TestPrioritaMemoria:
    """
    Inietta dati direttamente in ai_mod._memoria_cache per testare la
    logica di priorità senza chiamare Supabase né l'AI.
    """

    def setup_method(self):
        """Reset cache ad ogni test."""
        invalida_cache_memoria()

    def _inject_cache(self, classificazioni_manuali=None, prodotti_utente=None,
                      prodotti_master=None, user_id='user_test'):
        """Inietta dati nel cache globale e lo segna come loaded."""
        ai_mod._memoria_cache['classificazioni_manuali'] = classificazioni_manuali or {}
        ai_mod._memoria_cache['prodotti_utente'] = {user_id: (prodotti_utente or {})}
        ai_mod._memoria_cache['prodotti_master'] = prodotti_master or {}
        ai_mod._memoria_cache['loaded'] = True
        ai_mod._memoria_cache['_loaded_user_ids'] = {user_id}

    def test_classificazioni_manuali_priorita_assoluta(self):
        """admin override batte sia prodotti_utente che prodotti_master."""
        self._inject_cache(
            classificazioni_manuali={'SALMONE FRESCO': {'categoria': '🐟 PESCE', 'is_dicitura': False}},
            prodotti_utente={'SALMONE FRESCO': '🥦 VERDURE'},
            prodotti_master={'SALMONE FRESCO': '🥩 CARNE'},
        )
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('SALMONE FRESCO', 'user_test')
        assert result == '🐟 PESCE', "classificazioni_manuali deve avere priorità assoluta"

    def test_prodotti_utente_priorita_su_master(self):
        """prodotti_utente batte prodotti_master quando non c'è classificazione_manuale."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'TONNO IN OLIO': '🐟 PESCE'},
            prodotti_master={'TONNO IN OLIO': '🥩 CARNE'},
        )
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('TONNO IN OLIO', 'user_test')
        assert result == '🐟 PESCE', "prodotti_utente deve battere prodotti_master"

    def test_override_varie_bar_batte_cache_locale_errata(self):
        """I brand bar non negoziabili devono battere cache locale automatica errata."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'ODK SCIROPPO VANIGLIA ML750***': 'SPEZIE E AROMI'},
            prodotti_master={'ODK SCIROPPO VANIGLIA ML750***': 'FRUTTA'},
        )
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('ODK SCIROPPO VANIGLIA ML750***', 'user_test')
        assert result == 'VARIE BAR'

    def test_categorizza_con_memoria_override_varie_bar_batte_cache_locale_errata(self):
        """Anche il path di import deve ignorare cache locale errata per brand bar forti."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'ODK POLPA FRUTTI DI BOSCO KG1***': 'FRUTTA'},
            prodotti_master={'ODK POLPA FRUTTI DI BOSCO KG1***': 'FRUTTA'},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='ODK POLPA FRUTTI DI BOSCO KG1***',
            prezzo=9.52,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
            fornitore='ENTERPRISE S.R.L',
            unita_misura='BT',
        )
        assert result == 'VARIE BAR'

    def test_categorizza_con_memoria_capricciosa_secchio_batte_cache_locale_errata(self):
        """Le regole forti food devono battere una cache locale automatica errata."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'INS.CAPRICCIOSA KG.1 SECCHIO IL TUO CHEF': 'MANUTENZIONE E ATTREZZATURE'},
            prodotti_master={'INS.CAPRICCIOSA KG.1 SECCHIO IL TUO CHEF': 'MANUTENZIONE E ATTREZZATURE'},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='INS.CAPRICCIOSA KG.1 SECCHIO IL TUO CHEF',
            prezzo=5.99,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
            fornitore='SOGEGROSS S.P.A',
            unita_misura='PZ',
        )
        assert result == 'SCATOLAME E CONSERVE'

    def test_prodotti_master_fallback(self):
        """prodotti_master usato quando né classificazioni_manuali né prodotti_utente matchano."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={},
            prodotti_master={'FARINA 00': '🌾 FARINE E CEREALI'},
        )
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('FARINA 00', 'user_test')
        assert result == '🌾 FARINE E CEREALI', "prodotti_master deve essere il secondo fallback"

    def test_nessuna_memoria_ritorna_da_classificare(self):
        """Nessuna voce in cache → 'Da Classificare'."""
        self._inject_cache()
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('PRODOTTO SCONOSCIUTO XYZ', 'user_test')
        assert result == 'Da Classificare'

    def test_is_dicitura_restituisce_nota(self):
        """is_dicitura=True in classificazioni_manuali → '📝 NOTE E DICITURE'."""
        self._inject_cache(
            classificazioni_manuali={
                'DDT 12345': {'categoria': 'QUALSIASI', 'is_dicitura': True}
            }
        )
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('DDT 12345', 'user_test')
        assert result == '📝 NOTE E DICITURE'

    def test_invalida_cache_reset_stato(self):
        """invalida_cache_memoria() azzera tutto il cache."""
        self._inject_cache(
            prodotti_master={'FRUTTA': '🍎 FRUTTA E VERDURA'}
        )
        invalida_cache_memoria()
        assert ai_mod._memoria_cache['loaded'] is False
        assert ai_mod._memoria_cache['prodotti_master'] == {}
        assert ai_mod._memoria_cache['_loaded_user_ids'] == set()

    def test_utente_diverso_non_vede_cache_altrui(self):
        """Un user_id non caricato non deve vedere i prodotti_utente di un altro."""
        self._inject_cache(
            prodotti_utente={'SALMONE FRESCO': '🐟 PESCE'},
            prodotti_master={},
            user_id='user_A',
        )
        # user_B non è in _loaded_user_ids, ma il cache globale è già loaded=True.
        # Per user_B prodotti_utente non ha chiave 'user_B' → deve tornare Da Classificare.
        # Aggiungiamo user_B alla lista caricati ma senza dati utente.
        ai_mod._memoria_cache['_loaded_user_ids'].add('user_B')
        with patch('services.ai_service.st'):
            result = ai_mod.ottieni_categoria_prodotto('SALMONE FRESCO', 'user_B')
        # prodotti_master è vuoto, prodotti_utente non ha 'user_B' → Da Classificare
        assert result == 'Da Classificare', \
            "user_B non deve vedere i prodotti_utente di user_A"
