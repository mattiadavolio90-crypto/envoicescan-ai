"""Test per services/ai_service.py — Dizionario correzioni e priorità cache memoria."""
import pytest
from unittest.mock import MagicMock, patch
import services.ai_service as ai_mod
from services.ai_service import applica_correzioni_dizionario, applica_regole_categoria_forti, invalida_cache_memoria, _applica_guardrail_iva_bassa_spese_generali
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

    def test_lecca_lecca_piatto_non_scambia_per_stoviglia(self):
        categoria, motivo = applica_regole_categoria_forti("LECCA LECCA PIATTO G.5 X200 M.LOLL", "SHOP")
        assert categoria == "SHOP"
        assert motivo is None

    @pytest.mark.parametrize(
        ("descrizione", "attesa"),
        [
            ("ARANCE DA SPREMUTA (15KG)", "FRUTTA"),
            ("CIF C CANDEG SPRAY ML650 LIMONE", "MATERIALE DI CONSUMO"),
            ("GOMA WAKAME SALAD (AT) (AT)", "SUSHI VARIE"),
            ("SATONO YUKI TOFU FIRM", "LATTICINI"),
            ("CIP. TRECCIA 600 G-GR 600", "VERDURE"),
            ("CASTAGNE D' ACQUA CINESI AT *", "SCATOLAME E CONSERVE"),
            ("COPPA CIP CIOK X", "GELATI E DESSERT"),
            ("LMA VASC LIMONE", "GELATI E DESSERT"),
            ("VASCHETTA GRAN GALA CREMA 2800 ML", "GELATI E DESSERT"),
            ("VASCHETTA GRAN GALA PISTACCHIO 2800 ML", "GELATI E DESSERT"),
            ("COCCO RIPIENO 1X15", "GELATI E DESSERT"),
            ("LIMONE RIPIENO 1X12", "GELATI E DESSERT"),
            ("MARTINI BIANCO L1", "AMARI/LIQUORI"),
            ("FEVER TREE PINK GRAPEFRUIT CL20 VP", "BEVANDE"),
            ("SANTHE' PESCA 33CL-CL 33", "BEVANDE"),
            ("ESTATHE LIM. LATT.", "BEVANDE"),
            ("THE ESTATHE LIMONE LATT", "BEVANDE"),
            ("E STA THE PESCA LATT", "BEVANDE"),
            # ESTATHE varianti con "33" (stale keyword-auto CAFFE E THE risolte)
            ("THE ESTATHE LIMONE 33 LATT", "BEVANDE"),
            ("THE ESTATHE PESCA 33 LATT", "BEVANDE"),
            # SANTHE (brand diverso, stesso comportamento)
            ("SANTHE' PESCA 33CL CL", "BEVANDE"),
            # BRODO granulare/dado -> SCATOLAME E CONSERVE (non SALSE E CREME)
            ("BRODO GRANULARE AL POLLO TTL", "SCATOLAME E CONSERVE"),
            ("DADO BRODO VEGETALE", "SCATOLAME E CONSERVE"),
            # Vino di riso / Shaoxing -> VINI
            ("VINO RISO SHAOXING (LAOJIU) *10LT", "VINI"),
            ("SHAOXING WINE 640ML", "VINI"),
            # Stoviglie durevoli -> MANUTENZIONE E ATTREZZATURE
            ("PIATTO CERAMICA 26CM", "MANUTENZIONE E ATTREZZATURE"),
            ("PIATTO PORCELLANA BIANCO", "MANUTENZIONE E ATTREZZATURE"),
            ("PIATTINO ARDESIA RETTANGOLARE", "MANUTENZIONE E ATTREZZATURE"),
            # Stoviglie monouso/formato quantità -> MATERIALE DI CONSUMO
            ("PIATTO CARTA 50X20", "MATERIALE DI CONSUMO"),
            ("PIATTO PLASTICA MONOUSO 50X100", "MATERIALE DI CONSUMO"),
            # Posate durevoli -> MANUTENZIONE E ATTREZZATURE
            ("POSATE ACCIAIO INOX SET 24PZ", "MANUTENZIONE E ATTREZZATURE"),
            # Altri utensili/stoviglie durevoli emersi dalle correzioni manuali
            ("CUCCHIAIO MELAMINA BIANCA CM 5X4 5X1 H", "MANUTENZIONE E ATTREZZATURE"),
            ("FRUSTA ANTISLIP 8FILI CM21 MP", "MANUTENZIONE E ATTREZZATURE"),
            ("COPERCHIO CM ALBLACK", "MANUTENZIONE E ATTREZZATURE"),
            ("PENNELLO PAST SILIC21X4CM MPRO", "MANUTENZIONE E ATTREZZATURE"),
            # Sac à poche -> MATERIALE DI CONSUMO
            ("SAC A POCHE MONOUSO 45CM PZ100", "MATERIALE DI CONSUMO"),
            ("SACCAPOCHE PASTICCERIA", "MATERIALE DI CONSUMO"),
            ("ROTOLIIN CARTA CALCOLATRICE 10X10PZ MM57X40MT POS", "MATERIALE DI CONSUMO"),
            ("BUSTINA FORNO 12CMX27CM", "MATERIALE DI CONSUMO"),
            # Utensili -> MANUTENZIONE E ATTREZZATURE
            ("UTENSILI CUCINA SET", "MANUTENZIONE E ATTREZZATURE"),
            ("KG1 ALBUME MC", "UOVA"),
            ("INS. ROMANA PAD. (IT II)", "VERDURE"),
            ("TABASCO BT ML60 (12) MC.ILHENNY", "SALSE E CREME"),
            ("PRODUCTS (::P887101::2026-01-16:2026-01-31)", "SERVIZI E CONSULENZE"),
            ("LAMPONI GR125 IL MERCATO", "FRUTTA"),
            ("SHOCK SENSOR", "MATERIALE DI CONSUMO"),
            ("SAN BENEDETTO CHIANTI TRAD. DOCG ML 750", "VINI"),
            ("VAL D'OCA NERO DOCG ML 750 (5X6)", "VINI"),
            ("PANETTONE KG 1", "PASTICCERIA"),
            ("PANDORO 1 KG", "PASTICCERIA"),
            ("MACARONS ARTISANALE PZ 432 (12X36) ASSORTITI", "PASTICCERIA"),
            ("MARITOZZO MIDI FARCITO SURG GR 50 PZ 15", "PASTICCERIA"),
            ("MOCCHI CIOCCOLATO 1X10X6PZ", "GELATI E DESSERT"),
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
            ("RAVIOLI DI GAMBERI HAUKAU - AT ( )5*2KG", "PASTA E CEREALI"),
            ("SHAOMAI DI GAMBERI 20PZ", "PASTA E CEREALI"),
            ("GYOZA DI CARNE 600G", "PASTA E CEREALI"),
            # --- Regole apr20 batch 2: prodotti Da Classificare ---
            ("LIQ.ANIMA NERA CL.70 21GR MARZADRO", "AMARI/LIQUORI"),
            ("DENTICI O PAGARO MAGGIORE 1000+ FRESCO PAGRUS MAJOR ALLEVATE GRECIA (FIO", "PESCE"),
            ("UNICUM CL.70", "AMARI/LIQUORI"),
            ("MALIBU' CL.100", "AMARI/LIQUORI"),
            ("PISELLI FINI KG.2,5", "VERDURE"),
            ("LIEVITO FRESCO G.25X2 LIEVITAL", "PASTA E CEREALI"),
            ("PAGRO MAGGIORE 600+ FRESCO ALLEVATO PAGRUS MAJOR ALLEVATE GRECIA (COP0", "PESCE"),
            # --- Errori di categorizzazione ---
            ("SALV.LIMONE X100 TNT 70X100", "MATERIALE DI CONSUMO"),
            ("TORTELLI AL RADICCH.ROSSO KG.3 SURGITAL", "PASTA E CEREALI"),
            ("RICE FLAKES 30X227G", "PASTA E CEREALI"),
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

    def test_guardrail_iva_bassa_blocca_spese_generali_ai(self):
        fake_client = MagicMock()
        with patch('services.ai_service._chiama_gpt_classificazione', return_value=['MATERIALE DI CONSUMO']):
            result = ai_mod.classifica_con_ai(
                ['HEINZ BUST. KETCHUP 10MLX200PZ 76023044'],
                lista_iva=[10],
                openai_client=fake_client,
            )
        assert result == ['SALSE E CREME']


class TestGuardrailIvaBassaSoft:
    def test_guardrail_recupera_food_da_spese_generali(self):
        result = _applica_guardrail_iva_bassa_spese_generali(
            'HEINZ BUST. KETCHUP 10MLX200PZ 76023044',
            'MATERIALE DI CONSUMO',
            10,
        )
        assert result == 'SALSE E CREME'

    def test_guardrail_soft_mantiene_categoria_se_non_recupera(self):
        result = _applica_guardrail_iva_bassa_spese_generali(
            'ZHUYE',
            'MATERIALE DI CONSUMO',
            4,
        )
        assert result == 'MATERIALE DI CONSUMO'


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

    def test_categorizza_con_memoria_dicitura_admin_con_importo_positivo_va_in_servizi(self):
        """Una dicitura con importo positivo non puo' restare NOTE E DICITURE."""
        self._inject_cache(
            classificazioni_manuali={
                'FATTURA DI ACCONTO FORNITURA MERCE': {'categoria': 'QUALSIASI', 'is_dicitura': True}
            },
            prodotti_utente={},
            prodotti_master={},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='FATTURA DI ACCONTO FORNITURA MERCE',
            prezzo=2701.64,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
            fornitore='FORNITORE TEST',
            unita_misura='PZ',
        )
        assert result == 'SERVIZI E CONSULENZE'

    def test_categorizza_con_memoria_dicitura_admin_importo_zero_restano_note(self):
        """Le vere diciture a importo zero restano NOTE E DICITURE."""
        self._inject_cache(
            classificazioni_manuali={
                'RIGA FATTURA': {'categoria': 'QUALSIASI', 'is_dicitura': True}
            },
            prodotti_utente={},
            prodotti_master={},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='RIGA FATTURA',
            prezzo=0.0,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
            fornitore='FORNITORE TEST',
            unita_misura='PZ',
        )
        assert result == '📝 NOTE E DICITURE'

    # ----------------------------------------------------------------
    # TEST T1: guardrail NOTE su memoria locale con prezzo positivo
    # ----------------------------------------------------------------
    def test_memoria_locale_dicitura_con_importo_positivo_va_in_servizi(self):
        """T1: memoria locale ha DICITURA stale; con prezzo>0 il guardrail deve convertire."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'FATTURA DI ACCONTO': '📝 NOTE E DICITURE'},
            prodotti_master={},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='FATTURA DI ACCONTO',
            prezzo=500.0,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
        )
        assert result == 'SERVIZI E CONSULENZE', (
            "La memoria locale stale (DICITURA) con prezzo>0 deve essere corretta dal guardrail"
        )

    def test_memoria_locale_dicitura_con_importo_zero_resta_nota(self):
        """T1b: memoria locale DICITURA con prezzo=0 deve restare NOTE E DICITURE."""
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'RIGA TECNICA DDT': '📝 NOTE E DICITURE'},
            prodotti_master={},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='RIGA TECNICA DDT',
            prezzo=0.0,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
        )
        assert result == '📝 NOTE E DICITURE'

    # ----------------------------------------------------------------
    # TEST T3: memoria locale batte FORNITORE (by design)
    # ----------------------------------------------------------------
    def test_memoria_locale_batte_fornitore_per_design(self):
        """T3: personalizzazione cliente (memoria locale) ha priorità su regola FORNITORE.
        Questo è DESIGN INTENZIONALE: l'utente sceglie la sua categoria, non viene sovrascritta.
        """
        self._inject_cache(
            classificazioni_manuali={},
            prodotti_utente={'CARNE BOVINA KG1': 'SHOP'},
            prodotti_master={},
        )
        result = ai_mod.categorizza_con_memoria(
            descrizione='CARNE BOVINA KG1',
            prezzo=10.0,
            quantita=1,
            user_id='user_test',
            supabase_client=None,
            fornitore='MACELLERIA TEST SRL',
        )
        # La memoria locale (SHOP, scelta manuale utente) deve vincere sul fornitore
        assert result == 'SHOP', (
            "La memoria locale manuale cliente deve sempre prevalere sulle regole automatiche FORNITORE"
        )

    # ----------------------------------------------------------------
    # TEST BUG4: guardrail applicato dopo FORNITORE e UM
    # ----------------------------------------------------------------
    def test_guardrail_applicato_dopo_fornitore(self):
        """BUG4: se FORNITORE restituisse DICITURA (caso ipotetico futuro), il guardrail deve correggere."""
        # Patcha CATEGORIA_PER_FORNITORE con un fornitore che mappa a DICITURA
        from unittest.mock import patch
        with patch('config.constants.CATEGORIA_PER_FORNITORE', {'FORNITORE SPECIALE': '📝 NOTE E DICITURE'}):
            self._inject_cache(
                classificazioni_manuali={},
                prodotti_utente={},
                prodotti_master={},
            )
            result = ai_mod.categorizza_con_memoria(
                descrizione='PRODOTTO QUALSIASI',
                prezzo=150.0,
                quantita=1,
                user_id='user_test',
                supabase_client=None,
                fornitore='FORNITORE SPECIALE',
            )
        assert result == 'SERVIZI E CONSULENZE', (
            "Il guardrail deve correggere DICITURA→SERVIZI anche quando arriva dal livello FORNITORE"
        )

    # ----------------------------------------------------------------
    # TEST BUG3: categoria_finale corretta nel DB (via invoice_service flow)
    # ----------------------------------------------------------------
    def test_guardrail_note_con_importo_non_salva_dicitura_positiva(self):
        """BUG3/T4: _applica_guardrail_note_con_importo deve convertire DICITURA+prezzo>0."""
        from services.ai_service import _applica_guardrail_note_con_importo
        result = _applica_guardrail_note_con_importo(
            descrizione='SERVIZIO DI DISOSSO E LAVORAZIONE',
            categoria='📝 NOTE E DICITURE',
            prezzo=250.0,
        )
        assert result == 'SERVIZI E CONSULENZE', (
            "Una riga DISOSSO con prezzo>0 non può restare NOTE E DICITURE"
        )

    def test_guardrail_note_alias_senza_emoji(self):
        """BUG6: l'alias 'NOTE E DICITURE' (senza emoji) deve essere normalizzato e correggere su prezzo>0."""
        from services.ai_service import _applica_guardrail_note_con_importo
        result = _applica_guardrail_note_con_importo(
            descrizione='RIGA DI CREDITO',
            categoria='NOTE E DICITURE',
            prezzo=100.0,
        )
        assert result == 'SERVIZI E CONSULENZE', (
            "L'alias senza emoji deve essere riconosciuto come DICITURA e convertito su prezzo>0"
        )


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
