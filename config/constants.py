"""
Costanti, categorie e regex precompilate per OH YEAH! Hub.

Questo modulo contiene:
- Regex precompilate per parsing e normalizzazione
- Categorie Food & Beverage e Spese Generali
- Dizionario correzioni intelligente per classificazione
- Lista fornitori Spese Generali
- Colori per grafici Plotly

Tutte le regex sono precompilate all'avvio per ottimizzazione performance.
"""
import re

# Costanti sessione (timeout e throttling) — fonte unica di verità
SESSION_INACTIVITY_HOURS = 8        # Ore: sessione scade dopo inattività prolungata
LAST_SEEN_WRITE_THROTTLE_SECONDS = 300  # Secondi minimi tra due scritture di last_seen_at


# ============================================================
# REGEX PRECOMPILATE (OTTIMIZZAZIONE PERFORMANCE)
# ============================================================
# Compilate una volta sola all'avvio, riutilizzate migliaia di volte

# Normalizzazione descrizioni
REGEX_UNITA_MISURA = [
    # Prefissi peso GDO attaccati a cifre (es: "G100", "KG1", "GR.80") ---
    # DEVE stare PRIMA dei pattern singola-lettera (\bG\b non cattura G100 perché G-1 non ha word-boundary)
    re.compile(r'\b(?:KG|GR|G|ML|LT|L)\s*\d+(?:[.,]\d+)?\b', re.IGNORECASE),
    re.compile(r'\bKG\b', re.IGNORECASE),
    re.compile(r'\bG\b', re.IGNORECASE),
    re.compile(r'\bGR\b', re.IGNORECASE),
    re.compile(r'\bGRAMMI\b', re.IGNORECASE),
    re.compile(r'\bL\b', re.IGNORECASE),
    re.compile(r'\bLT\b', re.IGNORECASE),
    re.compile(r'\bLITRI\b', re.IGNORECASE),
    re.compile(r'\bML\b', re.IGNORECASE),
    re.compile(r'\bPZ\b', re.IGNORECASE),
    re.compile(r'\bPZZ\b', re.IGNORECASE),
    re.compile(r'\bPEZZI\b', re.IGNORECASE),
    re.compile(r'\bPEZZO\b', re.IGNORECASE),
    re.compile(r'\bCF\b', re.IGNORECASE),
    re.compile(r'\bCONF\b', re.IGNORECASE),
    re.compile(r'\bCONFEZIONE\b', re.IGNORECASE),
    re.compile(r'\bNR\b', re.IGNORECASE),
    re.compile(r'\bNÂ°\b', re.IGNORECASE),
    re.compile(r'\bNUMERO\b', re.IGNORECASE),
    re.compile(r'\bCT\b', re.IGNORECASE),
    re.compile(r'\bCTN\b', re.IGNORECASE),
    re.compile(r'\bCARTONE\b', re.IGNORECASE),
    re.compile(r'\bSCAT\b', re.IGNORECASE),
    re.compile(r'\bSCATOLA\b', re.IGNORECASE),
    re.compile(r'\bBAR\b', re.IGNORECASE),
    re.compile(r'\bBARATTOLO\b', re.IGNORECASE),
    re.compile(r'\bBUST\b', re.IGNORECASE),
    re.compile(r'\bBUSTA\b', re.IGNORECASE),
    re.compile(r'\bVAS\b', re.IGNORECASE),
    re.compile(r'\bVASETTO\b', re.IGNORECASE)
]

REGEX_NUMERI_UNITA = re.compile(r'\b\d+[.,]?\d*\s*(?:KG|G|L|ML|PZ|%|EUR|â‚¬)?\b', re.IGNORECASE)

REGEX_SOSTITUZIONI = {
    # Abbreviazioni GDO (Metro, Esselunga, ecc.) ---
    re.compile(r'\bINS\.?\b', re.IGNORECASE): 'INSALATA',
    re.compile(r'\bCIP\.?\b', re.IGNORECASE): 'CIPOLLA',
    re.compile(r'\bPOM\.?\b', re.IGNORECASE): 'POMODORO',
    re.compile(r'\bPETT\.?\b', re.IGNORECASE): 'PETTO',
    re.compile(r'\bFIL\.?\b', re.IGNORECASE): 'FILETTO',
    re.compile(r'\bSPALL\.?\b', re.IGNORECASE): 'SPALLA',
    re.compile(r'\bINT\.?\b', re.IGNORECASE): 'INTERO',
    re.compile(r'\bCONF\.?\b', re.IGNORECASE): 'CONFEZIONE',
    re.compile(r'\bPZ\.?\b', re.IGNORECASE): 'PEZZO',
    re.compile(r'\bBOT\.?\b', re.IGNORECASE): 'BOTTIGLIA',
    re.compile(r'\bLAT\.?\b', re.IGNORECASE): 'LATTINA',
    re.compile(r'\bVAS\.?\b', re.IGNORECASE): 'VASETTO',
    re.compile(r'\bBAR\.?\b', re.IGNORECASE): 'BARATTOLO',
    re.compile(r'\bFR\.?\b', re.IGNORECASE): 'FRESCO',
    re.compile(r'\bFRESC\.?\b', re.IGNORECASE): 'FRESCO',
    re.compile(r'\bSURG\.?\b', re.IGNORECASE): 'SURGELATO',
    re.compile(r'\bBIO\.?\b', re.IGNORECASE): 'BIOLOGICO',
    re.compile(r'\bS\.?\s*GLUT\.?\b', re.IGNORECASE): 'SENZA GLUTINE',
    re.compile(r'\bS\.?\s*LATT\.?\b', re.IGNORECASE): 'SENZA LATTOSIO'
}

REGEX_PUNTEGGIATURA = re.compile(r'[.,;:\-_/\\]+')

REGEX_ARTICOLI = [
    re.compile(r'\bIL\b', re.IGNORECASE),
    re.compile(r'\bLO\b', re.IGNORECASE),
    re.compile(r'\bLA\b', re.IGNORECASE),
    re.compile(r'\bI\b', re.IGNORECASE),
    re.compile(r'\bGLI\b', re.IGNORECASE),
    re.compile(r'\bLE\b', re.IGNORECASE),
    re.compile(r'\bUN\b', re.IGNORECASE),
    re.compile(r'\bUNA\b', re.IGNORECASE),
    re.compile(r'\bDI\b', re.IGNORECASE),
    re.compile(r'\bDA\b', re.IGNORECASE)
]

# Dicitura vs prodotto
REGEX_LETTERE_MINIME = re.compile(r'[A-Za-z]{3,}')
REGEX_PATTERN_BOLLA = re.compile(r'^[A-Z\s]{3,15}\sDEL\s\d{2}[-/]\d{2}[-/]\d{4}')

# Estrazione peso dalla descrizione
REGEX_KG_NUMERO = re.compile(r'KG\s*(\d+[.,]?\d*)', re.IGNORECASE)
REGEX_GR_NUMERO = re.compile(r'GR\s*(\d+)', re.IGNORECASE)
REGEX_ML_NUMERO = re.compile(r'ML\s*(\d+)', re.IGNORECASE)
REGEX_CL_NUMERO = re.compile(r'CL\s*(\d+)', re.IGNORECASE)
REGEX_LT_NUMERO = re.compile(r'L(?:T)?\s*(\d+[.,]?\d*)', re.IGNORECASE)
REGEX_PZ_NUMERO = re.compile(r'PZ\s*(\d+)', re.IGNORECASE)
REGEX_X_NUMERO = re.compile(r'X\s*(\d+)', re.IGNORECASE)
REGEX_PARENTESI_NUMERO = re.compile(r'\((\d+)\)')
REGEX_NUMERO_KG = re.compile(r'(\d+[.,]?\d*)\s*KG', re.IGNORECASE)
REGEX_NUMERO_LT = re.compile(r'(\d+[.,]?\d*)\s*(?:LT|LITRI)', re.IGNORECASE)
REGEX_NUMERO_GR = re.compile(r'(\d+)\s*(?:GR|GRAMMI)', re.IGNORECASE)

# Pulizia testo
REGEX_PUNTEGGIATURA_FINALE = re.compile(r'[.,;:!?]+$')


# ============================================================
# COLORI GRAFICI PLOTLY
# ============================================================
COLORI_PLOTLY = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"
]


# ============================================
# CATEGORIE FOOD & BEVERAGE (prodotti vendibili)
# ============================================
CATEGORIE_FOOD_BEVERAGE = [
    "CARNE", "PESCE", "LATTICINI", "SALUMI", "UOVA", "SCATOLAME E CONSERVE",
    "OLIO E CONDIMENTI", "PASTA E CEREALI", "VERDURE", "FRUTTA", "SALSE E CREME",
    "ACQUA", "BEVANDE", "CAFFE E THE", "BIRRE", "VINI",
    "VARIE BAR", "DISTILLATI", "AMARI/LIQUORI", "PASTICCERIA",
    "PRODOTTI DA FORNO", "SPEZIE E AROMI", "GELATI E DESSERT", "SHOP", "SUSHI VARIE"
]


# ============================================
# GRUPPI LOGICI CATEGORIE
# ============================================
# IMPORTANTE: "MATERIALE DI CONSUMO" NON cambia come stringa nel DB,
# ma dal punto di vista logico rientra ora nelle SPESE GENERALI.
# Il gruppo separato "Materiali" viene rimosso.
CATEGORIE_MATERIALI = []  # legacy compat: gruppo logico rimosso

# Alias storici da normalizzare per clienti e dati legacy
LEGACY_CATEGORY_ALIASES = {
    "NO FOOD": "MATERIALE DI CONSUMO",
    "MATERIALI": "MATERIALE DI CONSUMO",
    "MATERIALE CONSUMO": "MATERIALE DI CONSUMO",
    "MATERIALI CONSUMO": "MATERIALE DI CONSUMO",
    "SECCO": "PASTA E CEREALI",
    "GELATI": "GELATI E DESSERT",
    # BUG6 FIX: normalizza alias senza emoji alla variante canonica con emoji
    "NOTE E DICITURE": "📝 NOTE E DICITURE",
}


# ============================================
# CATEGORIE SPESE OPERATIVE / GENERALI (NON F&B)
# ============================================
# Le 4 categorie NON considerate Food & Beverage sono:
# - SERVIZI E CONSULENZE
# - UTENZE E LOCALI
# - MANUTENZIONE E ATTREZZATURE
# - MATERIALE DI CONSUMO
CATEGORIE_SPESE_OPERATIVE = [
    "SERVIZI E CONSULENZE",        # Es: Consulenze HACCP, Commercialista
    "UTENZE E LOCALI",             # Es: Bollette ENEL, Affitto locale
    "MANUTENZIONE E ATTREZZATURE"  # Es: Riparazione forno, Manutenzione cappa
]
CATEGORIE_SPESE_GENERALI = CATEGORIE_SPESE_OPERATIVE + ["MATERIALE DI CONSUMO"]


# ============================================
# TUTTE LE CATEGORIE (per AI e retrocompatibilitÃ )
# ============================================
# NOTA: F&B = 25 categorie, Spese Generali = 4 categorie
TUTTE_LE_CATEGORIE = CATEGORIE_FOOD_BEVERAGE + CATEGORIE_SPESE_GENERALI


# RetrocompatibilitÃ  con codice esistente
CATEGORIE_FOOD = CATEGORIE_FOOD_BEVERAGE


# ============================================
# CENTRI DI PRODUZIONE (macro-categorie F&B)
# ============================================
# Mappatura: ogni centro raggruppa più categorie F&B
# Usato nel tab "Centri" per analisi aggregata
CENTRI_DI_PRODUZIONE = {
    "FOOD": [
        "CARNE", "PESCE", "LATTICINI", "SALUMI", "UOVA",
        "SCATOLAME E CONSERVE", "OLIO E CONDIMENTI", "PASTA E CEREALI",
        "VERDURE", "FRUTTA", "SALSE E CREME",
        "PRODOTTI DA FORNO", "SPEZIE E AROMI", "SUSHI VARIE"
    ],
    "BEVERAGE": [
        "ACQUA", "BEVANDE", "CAFFE E THE", "VARIE BAR"
    ],
    "ALCOLICI": [
        "BIRRE", "VINI", "DISTILLATI", "AMARI/LIQUORI"
    ],
    "DOLCI": [
        "PASTICCERIA", "GELATI E DESSERT"
    ],
    "SHOP": [
        "SHOP"
    ],
}


# ============================================
# FORNITORI SPESE GENERALI (utenze, telecom, tech)
# ============================================
# Lista unificata di fornitori che sono SEMPRE spese generali/utenze
# NON confondere con MATERIALE DI CONSUMO (pellicole, guanti, detersivi)
# Questi sono fornitori di SERVIZI, non di prodotti
FORNITORI_SPESE_GENERALI_KEYWORDS = [
    'TIM', 'TELECOM', 'VODAFONE', 'WIND', 'ILIAD', 'FASTWEB',
    'ENEL', 'ENI', 'A2A', 'EDISON', 'CP S.P.A', 'CP SPA',
    'AMAZON', 'MEDIAWORLD', 'UNIEURO', 'LEROY MERLIN',
    'BANCA', 'ASSICURAZ', 'POSTALE', 'POSTE ITALIANE', 'GOOGLE'
]


# Fornitori utility/telecom/energia da forzare sempre in UTENZE E LOCALI.
# Usati come hard override a livello fornitore in ai_service.
FORNITORI_UTENZE_SEMPRE = [
    'FASTWEB',
    'TIM',
    'TELECOM',
    'VODAFONE',
    'WIND',
    'WINDTRE',
    'ILIAD',
    'ENI',
    'A2A',
    'ENEL',
    'EDISON',
    'ACEA',
    'HERA',
    'SORGENIA',
]


# ============================================
# REGOLE CATEGORIZZAZIONE PER FORNITORE
# ============================================
# Fornitore specifico → Categoria automatica (priorità ALTA)
# Applicate PRIMA del dizionario keyword
#
# ATTENZIONE: inserire SOLO fornitori mono-categoria (es. enoteche, macellerie,
# fornitori acqua minerale, fornitori energy). Brand multi-categoria (es. Sammontana
# che produce gelati, brioche, succhi) vanno in BRAND_AMBIGUI_NO_DICT e devono
# passare dall'AI per una classificazione per-prodotto.
CATEGORIA_PER_FORNITORE = {
    "CP S.P.A": "UTENZE E LOCALI",              # Bollette energia/gas
    "M&M SRL": "GELATI E DESSERT",                        # Fornitore gelati (solo gelati)
    "SHIDU INTERNATIONAL": "VERDURE",           # Fornitore prodotti asiatici/verdure
    "NOVA HORECA": "MANUTENZIONE E ATTREZZATURE",  # Fornitore attrezzature horeca
}


# ============================================
# REGOLE CATEGORIZZAZIONE PER UNITÀ DI MISURA
# ============================================
# Unità misura → Categoria automatica (priorità ALTA)
# Applicate PRIMA del dizionario keyword
UNITA_MISURA_CATEGORIA = {
    "KWH": "UTENZE E LOCALI",     # Kilowattora (energia elettrica)
    "SMC": "UTENZE E LOCALI",     # Standard Metro Cubo (gas)
    "KW": "UTENZE E LOCALI",      # Kilowatt (potenza elettrica)
    "NREE": "UTENZE E LOCALI",    # Numero (quota fissa bollette)
    "GGQFD": "UTENZE E LOCALI",   # Giorni quota fissa distribuzione
}


# ============================================
# BRAND AMBIGUI — NO DIZIONARIO
# ============================================
# Brand multi-categoria: NON classificati dal dizionario keyword.
# Se la descrizione contiene uno di questi brand, il dizionario viene bypassato
# e il prodotto va all’AI per classificazione per-prodotto.
#
# Regola: un brand va qui se produce prodotti di CATEGORIE DIVERSE.
# Brand mono-prodotto (es. Schweppes, Baileys) restano nel dizionario.
BRAND_AMBIGUI_NO_DICT = {
    'SAMMONTANA',   # Gelati + brioche + merendine + succhi
    'FABBRI',       # Sciroppi + variegati gelato + creme + Amarena
    'RISTORA',      # Zucchero bar + capsule caffe + latte polvere
}


# ============================================
# DIZIONARIO CORREZIONI INTELLIGENTE
# ============================================
# Mappa keyword â†’ categoria per classificazione rapida
# Usato quando AI non Ã¨ disponibile o per validazione
DIZIONARIO_CORREZIONI = {
    # ===== CARNE =====
    "POLLO": "CARNE",
    "PETTO POLLO": "CARNE",
    "COSCE POLLO": "CARNE",
    "ALI POLLO": "CARNE",
    "MANZO": "CARNE",
    "VITELLO": "CARNE",
    "MAIALE": "CARNE",
    "SUINO": "CARNE",
    "AGNELLO": "CARNE",
    "TACCHINO": "CARNE",
    "CONIGLIO": "CARNE",
    "ANATRA": "CARNE",
    "FESA": "CARNE",
    "COSTATA": "CARNE",
    "BISTECCA": "CARNE",
    "HAMBURGER": "CARNE",
    "SPEZZATINO": "CARNE",
    "ARROSTO": "CARNE",
    "BRASATO": "CARNE",
    "SCALOPPINE": "CARNE",
    
    # ===== PESCE =====
    "SALMONE": "PESCE",
    "TONNO FRESCO": "PESCE",
    "TONNO P.GIALLE": "PESCE",
    "BRANZINO": "PESCE",
    "ORATA": "PESCE",
    "GAMBERI": "PESCE",
    "GAMBERETTI": "PESCE",
    "MAZZANCOLLE": "PESCE",
    "SCAMPI": "PESCE",
    "CALAMARI": "PESCE",
    "POLPO": "PESCE",
    "COZZE": "PESCE",
    "COZZA": "PESCE",
    "VONGOLE": "PESCE",
    "TROTA": "PESCE",
    "SPIGOLA": "PESCE",
    "MERLUZZO": "PESCE",
    "BACCALÃ€": "PESCE",
    "SOGLIOLA": "PESCE",
    "PESCE SPADA": "PESCE",
    "ACCIUGHE": "PESCE",
    "ALICI": "PESCE",
    "SARDINE": "PESCE",
    "PANGASIO": "PESCE",
    "TOTANO": "PESCE",
    "CALAMARO": "PESCE",
    "SEPPIA": "PESCE",
    "GRANCHIO": "PESCE",
    "ARAGOSTA": "PESCE",
    "ASTICE": "PESCE",
    "TENTACOLI": "PESCE",
    "CHELE": "PESCE",
    "CODE GAMBERO": "PESCE",
    "GAMBERONE": "PESCE",
    "GAMBERONI": "PESCE",
    "IMITAZIONE": "PESCE",
    "SURIMI": "PESCE",
    # Specie mancanti
    "ROMBO": "PESCE",
    "DENTICE": "PESCE",
    "SGOMBRO": "PESCE",
    "CERNIA": "PESCE",
    "HALIBUT": "PESCE",
    "OMBRINA": "PESCE",
    "LAMPUGA": "PESCE",
    "PAGELLO": "PESCE",
    "SARAGO": "PESCE",
    "GALLINELLA": "PESCE",
    "PERSICO": "PESCE",
    "LAVARELLO": "PESCE",
    "LUCCIO": "PESCE",
    "ANGUILLA": "PESCE",
    "STORIONE": "PESCE",
    "CAVIALE": "PESCE",
    "HAMACHI": "PESCE",
    "HIRAMASA": "PESCE",
    "MUGGINE": "PESCE",
    "SUGARELLO": "PESCE",
    "PALAMITA": "PESCE",
    "PESCE GATTO": "PESCE",
    "LYCHEES": "FRUTTA",
    "LITCHI": "FRUTTA",
    "ARBUTUS": "FRUTTA",
    "CORBEZZOLO": "FRUTTA",
    "SCIROPPATO": "FRUTTA",
    "SCIROPPATA": "FRUTTA",
    "NAVEL": "FRUTTA",
    
    # ===== LATTICINI =====
    "GRANA PADANO": "LATTICINI",
    "PARMIGIANO": "LATTICINI",
    "PECORINO": "LATTICINI",
    "GORGONZOLA": "LATTICINI",
    "TALEGGIO": "LATTICINI",
    "PROVOLONE": "LATTICINI",
    "ASIAGO": "LATTICINI",
    "FONTINA": "LATTICINI",
    "STRACCHINO": "LATTICINI",
    "EMMENTAL": "LATTICINI",
    "MOZZARELLA": "LATTICINI",
    "BURRATA": "LATTICINI",
    "RICOTTA": "LATTICINI",
    "MASCARPONE": "LATTICINI",
    "LATTE": "LATTICINI",
    "PANNA": "LATTICINI",
    "MOZZARELLE PANATE": "LATTICINI",
    "TOFU": "LATTICINI",
    "YOGURT": "LATTICINI",
    "YOGHURT": "LATTICINI",
    "EDAMER": "LATTICINI",
    "PIZZA JULIENNE": "LATTICINI",
    # Formaggi comuni mancanti
    "BURRO": "LATTICINI",
    "FORMAGGIO": "LATTICINI",
    "FORMAGGI": "LATTICINI",
    "GRANA": "LATTICINI",
    "SCAMORZA": "LATTICINI",
    "PROVOLA": "LATTICINI",
    "FIORDILATTE": "LATTICINI",
    "FIOR DI LATTE": "LATTICINI",
    "ROBIOLA": "LATTICINI",
    "GOUDA": "LATTICINI",
    "CHEDDAR": "LATTICINI",
    "CAMEMBERT": "LATTICINI",
    "GRUYERE": "LATTICINI",
    "GRUYÈRE": "LATTICINI",
    "TOMA": "LATTICINI",
    "CASERA": "LATTICINI",
    "BITTO": "LATTICINI",
    "BRANZI": "LATTICINI",
    "CASATELLA": "LATTICINI",
    "SQUACQUERONE": "LATTICINI",
    "QUARTIROLO": "LATTICINI",
    "CRESCENZA": "LATTICINI",
    "PRIMO SALE": "LATTICINI",
    "PRIMOSALE": "LATTICINI",
    
    # ===== SALUMI =====
    "PROSCIUTTO": "SALUMI",
    "CRUDO": "SALUMI",
    "COTTO": "SALUMI",
    "SALAME": "SALUMI",
    "MORTADELLA": "SALUMI",
    "PANCETTA": "SALUMI",
    "SPECK": "SALUMI",
    "BRESAOLA": "SALUMI",
    # NOTA: "COPPA" spostata in sezione GELATI (COPPA = gelato). Per salumi usare "COPPA DI TESTA" o simili
    "COPPA DI TESTA": "SALUMI",
    "LARDO": "SALUMI",
    "GUANCIALE": "SALUMI",
    # âœ… Richiesta: SALSICCIA e varianti â†’ CARNE (non SALUMI)
    # NOTA: Deve stare PRIMA di VASCHETTA nel dizionario (sorted by length)
    "SALSICCIA": "CARNE",
    "SALSICCE": "CARNE",
    "SALSICCINA": "CARNE",
    "SALSICCINE": "CARNE",
    "SALSICC": "CARNE",
    "SALSIC": "CARNE",
    "WURSTEL": "SALUMI",
    "WÃœRSTEL": "SALUMI",
    
    # ===== UOVA =====
    "UOVA": "UOVA",
    "UOVO": "UOVA",
    
    # ===== VERDURE =====
    "CONTORNO": "VERDURE",
    "POMODORO": "VERDURE",
    "POMODORI": "VERDURE",
    "POMO": "VERDURE",
    "POMO GRAPP": "VERDURE",
    "POMODORO GRAPPOLO": "VERDURE",
    "POMODORI GRAPPOLO": "VERDURE",
    "INSALATA": "VERDURE",
    "LATTUGA": "VERDURE",
    "RUCOLA": "VERDURE",
    "CAROTE": "VERDURE",
    "ZUCCHINE": "VERDURE",
    "MELANZANE": "VERDURE",
    "PEPERONI": "VERDURE",
    "PATATE": "VERDURE",
    "CIPOLLE": "VERDURE",
    "SEDANO": "VERDURE",
    "FINOCCHI": "VERDURE",
    "SPINACI": "VERDURE",
    "BROCCOLI": "VERDURE",
    "CAVOLFIORE": "VERDURE",
    "ASPARAGI": "VERDURE",
    "FUNGHI": "VERDURE",
    "RADICCHIO": "VERDURE",
    "BASILICO": "SPEZIE E AROMI",
    "PREZZEMOLO": "SPEZIE E AROMI",
    "CARCIOFI": "VERDURE",
    "MISTICANZA": "VERDURE",
    
    # ===== FRUTTA =====
    "MELE": "FRUTTA",
    "ARANCIA": "FRUTTA",
    "ARANCE": "FRUTTA",
    "BANANA": "FRUTTA",
    "BANANE": "FRUTTA",
    "FRAGOLE": "FRUTTA",
    "LIMONE": "FRUTTA",
    "LIMONI": "FRUTTA",
    "PERA": "FRUTTA",
    "PERE": "FRUTTA",
    "PESCA": "FRUTTA",
    "PESCHE": "FRUTTA",
    "ALBICOCCHE": "FRUTTA",
    "UVA": "FRUTTA",
    "MELONE": "FRUTTA",
    "ANGURIA": "FRUTTA",
    "KIWI": "FRUTTA",
    "ANANAS": "FRUTTA",
    "MANGO": "FRUTTA",
    "AVOCADO": "FRUTTA",
    
    # ===== PRODOTTI DA FORNO =====
    "PANE": "PRODOTTI DA FORNO",
    "FOCACCIA": "PRODOTTI DA FORNO",
    "GRISSINI": "PRODOTTI DA FORNO",

    "PIZZETTA": "PRODOTTI DA FORNO",
    "CIABATTA": "PRODOTTI DA FORNO",
    "FRANCESINO": "PRODOTTI DA FORNO",
    "MICHETTA": "PRODOTTI DA FORNO",
    "BAGUETTE": "PRODOTTI DA FORNO",
    "PANINI": "PRODOTTI DA FORNO",
    "BASE PIZZA": "PRODOTTI DA FORNO",
    "FOCACCINA": "PRODOTTI DA FORNO",
    "SPUNTINELLE": "PRODOTTI DA FORNO",
    "BRIOCHE": "PASTICCERIA",
    "CROISSANT": "PASTICCERIA",
    
    # ===== SECCO (PASTA, RISO, FARINE) =====
    "PASTA": "PASTA E CEREALI",
    "SPAGHETTI": "PASTA E CEREALI",
    "PENNE": "PASTA E CEREALI",
    "FUSILLI": "PASTA E CEREALI",
    "RIGATONI": "PASTA E CEREALI",
    "TORTIGLIONI": "PASTA E CEREALI",
    "FARFALLE": "PASTA E CEREALI",
    "LINGUINE": "PASTA E CEREALI",
    "TAGLIATELLE": "PASTA E CEREALI",
    "LASAGNE": "PASTA E CEREALI",
    "RAVIOLI": "PASTA E CEREALI",
    "TORTELLINI": "PASTA E CEREALI",
    "TORTELLONI": "PASTA E CEREALI",
    "AGNOLOTTI": "PASTA E CEREALI",
    "CAPPELLETTI": "PASTA E CEREALI",
    "GNOCCHI": "PASTA E CEREALI",
    "CANNELLONI": "PASTA E CEREALI",
    "ORECCHIETTE": "PASTA E CEREALI",
    "TROFIE": "PASTA E CEREALI",
    "PACCHERI": "PASTA E CEREALI",
    "BUCATINI": "PASTA E CEREALI",
    "RISO": "PASTA E CEREALI",
    "FARINA": "PASTA E CEREALI",
    "ZUCCHERO": "PASTA E CEREALI",
    "FECOLA": "PASTA E CEREALI",
    "ROUX": "PASTA E CEREALI",
    "CEREALI": "PASTA E CEREALI",
    "BISCOTTI": "PASTA E CEREALI",
    "FETTE BISCOTTATE": "PASTA E CEREALI",
    
    # ===== OLIO E CONDIMENTI =====
    "OLIO": "OLIO E CONDIMENTI",
    "OLIO OLIVA": "OLIO E CONDIMENTI",
    "OLIO EVO": "OLIO E CONDIMENTI",
    "OLIO EXTRAVERGINE": "OLIO E CONDIMENTI",
    "ACETO": "OLIO E CONDIMENTI",
    "ACETO BALSAMICO": "OLIO E CONDIMENTI",
    "ACETO VINO": "OLIO E CONDIMENTI",
    
    # ===== SPEZIE E AROMI =====
    "PEPE": "SPEZIE E AROMI",
    "PEPERONCINO": "SPEZIE E AROMI",
    "ORIGANO": "SPEZIE E AROMI",
    "ROSMARINO": "SPEZIE E AROMI",
    "SALVIA": "SPEZIE E AROMI",
    "TIMO": "SPEZIE E AROMI",
    "ALLORO": "SPEZIE E AROMI",
    "CURRY": "SPEZIE E AROMI",
    "ZAFFERANO": "SPEZIE E AROMI",
    "CANNELLA": "SPEZIE E AROMI",
    "NOCE MOSCATA": "SPEZIE E AROMI",
    
    # ===== SALSE E CREME =====
    "CREMA PISTACCHIO": "SALSE E CREME",
    "CREMA NOCCIOLA": "SALSE E CREME",
    "PESTO": "SALSE E CREME",
    "KETCHUP": "SALSE E CREME",
    "MAIONESE": "SALSE E CREME",
    "SENAPE": "SALSE E CREME",
    "SAUCE": "SALSE E CREME",
    
    # ===== PROBLEMI AI: Aggiunti al dizionario =====
    # Prodotti che l'AI non riesce a classificare correttamente
    "MIXYBAR": "VARIE BAR",
    "ALPRO": "BEVANDE",
    "SOYA DRINK": "BEVANDE",
    "GRANATINA": "BEVANDE",
    "SCHWEPPES": "BEVANDE",
    "CRODINO": "BEVANDE",
    "YOGA": "BEVANDE",
    "BRAVO": "BEVANDE",
    "PFANNER": "BEVANDE",
    "NETTARE": "BEVANDE",
    "NETT": "BEVANDE",
    "DAYGUM": "SHOP",
    "FRESCORI": "SHOP",
    "BISCOTTI FORTUNA": "SHOP",
    "BISCOTTI DELLA FORTUNA": "SHOP",
    "BISCOTTI PORTAFORTUNA": "SHOP",
    "STICK VEGAN": "SHOP",
    "FINTI FRAGOLA": "SHOP",
    "HENDRICKS": "DISTILLATI",
    "HENDRICK": "DISTILLATI",
    "DOLCIFICANTE": "VARIE BAR",
    "SERVIZIO DI PRODUZIONE": "SERVIZI E CONSULENZE",
    "INVIO FATTURA": "SERVIZI E CONSULENZE",
    "MUSICA D'AMBIENTE": "SERVIZI E CONSULENZE",
    "APPARECCHIO RADIORIC": "SERVIZI E CONSULENZE",
    "SPESE SPEDIZIONE": "SERVIZI E CONSULENZE",
    "ANTICIPI": "SERVIZI E CONSULENZE",
    "BOLLI": "SERVIZI E CONSULENZE",
    "SPESE BANCARIE": "SERVIZI E CONSULENZE",
    "COMMISSIONI": "SERVIZI E CONSULENZE",
    "RAGÃ™": "SALSE E CREME",
    "SUGO": "SALSE E CREME",
    "BESCIAMELLA": "SALSE E CREME",
    "SALSA": "SALSE E CREME",
    
    # ===== CONSERVE (include scatolame, marmellate, sott'olio) =====
    # Scatolame
    "PELATI": "SCATOLAME E CONSERVE",
    "POMODORI PELATI": "SCATOLAME E CONSERVE",
    "LEGUMI": "SCATOLAME E CONSERVE",
    "FAGIOLI": "SCATOLAME E CONSERVE",
    "TONNO SCATOLA": "PESCE",
    "TONNO": "PESCE",
    # Conserve/Marmellate
    "CONSERVA": "SCATOLAME E CONSERVE",
    "CONSERVE": "SCATOLAME E CONSERVE",
    "MARMELLATA": "SCATOLAME E CONSERVE",
    "CONFETTURA": "SCATOLAME E CONSERVE",
    "COMPOSTA": "SCATOLAME E CONSERVE",
    "GELATINA": "SCATOLAME E CONSERVE",
    "SOTT'OLIO": "SCATOLAME E CONSERVE",
    "SOTTACETO": "SCATOLAME E CONSERVE",
    "SOTTACETI": "SCATOLAME E CONSERVE",
    "OLIVE": "SCATOLAME E CONSERVE",
    "CAPPERI": "SCATOLAME E CONSERVE",
    "CETRIOLINI": "SCATOLAME E CONSERVE",
    "GIARDINIERA": "SCATOLAME E CONSERVE",
    
    # ===== CAFFE E THE =====
    "CAFFÃˆ": "CAFFE E THE",
    "CAFFE": "CAFFE E THE",
    "CAFFE'": "CAFFE E THE",
    "ESPRESSO": "CAFFE E THE",
    "CAPSULE": "CAFFE E THE",
    "CIALDE": "CAFFE E THE",
    "THE": "CAFFE E THE",
    "TÃˆ": "CAFFE E THE",
    "TISANA": "CAFFE E THE",
    "TISANE": "CAFFE E THE",
    "INFUSO": "CAFFE E THE",
    "DECAFFEINATO": "CAFFE E THE",
    "DECA": "CAFFE E THE",
    "DECAF": "CAFFE E THE",
    "GINSENG": "CAFFE E THE",
    "PREPARATO X GINSENG": "CAFFE E THE",
    "CAMOMILLA": "CAFFE E THE",
    "CAMOMILLE": "CAFFE E THE",
    
    # ===== ACQUA =====
    "ACQUA": "ACQUA",
    "ACQ": "ACQUA",
    "FRIZZANTE": "ACQUA",
    "EFFERVESCENTE": "ACQUA",
    
    # ===== BEVANDE =====
    "COCA": "BEVANDE",
    "ARANCIATA": "BEVANDE",
    "LIMONATA": "BEVANDE",
    "THE FREDDO": "BEVANDE",
    "SUCCO": "BEVANDE",
    "DERBY SUCCO": "BEVANDE",
    "ESTATHE": "BEVANDE",
    "SPREMUTA": "BEVANDE",
    "BIBITA": "BEVANDE",
    "CHINOTTO": "BEVANDE",
    "GASSOSA": "BEVANDE",
    
    # ===== VINI =====
    "VINO": "VINI",
    "PROSECCO": "VINI",
    "SPUMANTE": "VINI",
    "LAMBRUSCO": "VINI",
    "CHIANTI": "VINI",
    "BAROLO": "VINI",
    "BARBARESCO": "VINI",
    
    # ===== BIRRE =====
    "BIRRA": "BIRRE",
    "LAGER": "BIRRE",
    "WEISS": "BIRRE",
    "STOUT": "BIRRE",
    
    # ===== DISTILLATI =====
    "VODKA": "DISTILLATI",
    "WHISKY": "DISTILLATI",
    "WHISKEY": "DISTILLATI",
    "TEQUILA": "DISTILLATI",
    "GRAPPA": "DISTILLATI",
    "BRANDY": "DISTILLATI",
    "COGNAC": "DISTILLATI",
    
    # ===== AMARI/LIQUORI =====
    "AMARO": "AMARI/LIQUORI",
    "LIMONCELLO": "AMARI/LIQUORI",
    "SAMBUCA": "AMARI/LIQUORI",
    "AMARETTO": "AMARI/LIQUORI",
    "BAILEYS": "AMARI/LIQUORI",
    "LIQUORE": "AMARI/LIQUORI",
    "DIGESTIVO": "AMARI/LIQUORI",
    
    # ===== PASTICCERIA =====
    "TORTA": "PASTICCERIA",
    "CROSTATA": "PASTICCERIA",
    "TIRAMISÃ™": "PASTICCERIA",
    "PANNA COTTA": "PASTICCERIA",
    "MOUSSE": "PASTICCERIA",
    "CHEESECAKE": "PASTICCERIA",
    "MILLEFOGLIE": "PASTICCERIA",
    "CANNOLI": "PASTICCERIA",
    "PROFITEROLES": "PASTICCERIA",
    "BIGNÃˆ": "PASTICCERIA",
    "ARAGOSTELLE": "PASTICCERIA",  # Dolci a forma di aragosta (con pistacchio/cioccolato)
    "TARTUFI": "PASTICCERIA",  # Default per dolci (se Ã¨ tartufo vero, viene sovrascritto da admin)
    "SACHER": "PASTICCERIA",
    "NOCCIOL": "PASTICCERIA",
    "MUFFIN": "PASTICCERIA",
    "GROSTOLI": "PASTICCERIA",
    "ZEPPOLE": "PASTICCERIA",
    "NUTELLA": "PASTICCERIA",
    "FIAMME": "SHOP",  # Accendini/fiammiferi
    
    # ===== GELATI =====
    "GELATO": "GELATI E DESSERT",
    "GELATI": "GELATI E DESSERT",
    "SORBETTO": "GELATI E DESSERT",
    "COPPA GELATO": "GELATI E DESSERT",
    # NOTA: "COPPA" generico rimosso: troppo ambiguo tra gelati, dessert, salumi e contenitori.
    "COPPA MARTINI": "MANUTENZIONE E ATTREZZATURE",
    "COPPA CIOCCOLATA VETRO": "MANUTENZIONE E ATTREZZATURE",
    "CAUZIONE FUSTI": "MANUTENZIONE E ATTREZZATURE",
    "CONO": "GELATI E DESSERT",
    "SEMIFREDDO": "GELATI E DESSERT",
    "PANETTONE": "PASTICCERIA",
    "PANDORO": "PASTICCERIA",
    "MACARONS": "PASTICCERIA",
    
    # ===== SHOP (prodotti di compravendita senza produzione) =====
    "CICCHE": "SHOP",
    "SIGARETTE": "SHOP",
    "TABACCHI": "SHOP",
    "ELFBAR": "SHOP",
    "LOST MARY": "SHOP",
    "OCB": "SHOP",
    "SMOKING FILTRI": "SHOP",
    "PREFILLED POD": "SHOP",
    "TOCA AIR POD": "SHOP",
    "TP800": "SHOP",
    "VIVIDENT": "SHOP",
    "VIGORSOL": "SHOP",
    "RICOLA": "SHOP",
    "MOROSITAS": "SHOP",
    "FINI STRIPS": "SHOP",
    "BACI PERUGINA": "SHOP",
    "POCKET COFFEE": "SHOP",
    "FISHERMAN'S": "SHOP",
    "FISHERMANS": "SHOP",
    "CARAMELLE": "SHOP",
    "GOMME": "SHOP",
    "GOMMA": "SHOP",
    "CHEWING GUM": "SHOP",
        "CASHBACK": "SERVIZI E CONSULENZE",
        "SCONTIPOSTE": "SERVIZI E CONSULENZE",
        "ECOMAP": "SERVIZI E CONSULENZE",
        "INFOCERT": "SERVIZI E CONSULENZE",
        "NOLEGGIO ESERCENTE": "SERVIZI E CONSULENZE",
        "SPESE INCASSO": "SERVIZI E CONSULENZE",
    "PATATINE": "SHOP",
    "CHIPS": "SHOP",
    "SNACK": "SHOP",
    "GOLIA": "SHOP",
    "MENTINE": "SHOP",
    "CARAMELLA": "SHOP",
    "LECCA LECCA": "SHOP",
    "LOLLIPOP": "SHOP",
    "MACINATO BOV": "CARNE",
    "MAGATELLO": "CARNE",
    "TRITA BOV": "CARNE",
    "MORT.": "SALUMI",
    "MORT.MODENA": "SALUMI",
    "VENTRICINA": "SALUMI",
    "BARRETTE": "SHOP",
    "BARRETTA": "SHOP",
    "CIOCCOLATINI": "SHOP",
    "OVETTI": "SHOP",
    "KINDER": "SHOP",
    "MARS": "SHOP",
    "SNICKERS": "SHOP",
    "CALAM": "PESCE",
    "TWIX": "SHOP",
    "TAKOYAKI": "PESCE",
    "BOUNTY": "SHOP",
    "CIOCCOLATO CONFEZIONATO": "SHOP",
    "MENTOS": "SHOP",
    
    # ===== VARIE BAR (solo prodotti commestibili per servizio bar) =====
    "GHIACCIO": "VARIE BAR",
    "ZUCCHERO BAR": "VARIE BAR",
    "PORTAZUCCHERO": "VARIE BAR",
    "DOLCIFICANTE": "VARIE BAR",
    
    # ===== MATERIALI CONSUMO -> MATERIALE DI CONSUMO =====
    "BUSTINE": "MATERIALE DI CONSUMO",
    "PALETTE": "MATERIALE DI CONSUMO",
    "CANNUCCE": "MATERIALE DI CONSUMO",
    "TOVAGLIETTE": "MATERIALE DI CONSUMO",
    "TOVAGLIETTA": "MATERIALE DI CONSUMO",
    "VASCHETTA": "MATERIALE DI CONSUMO",
    "VASCHETTE": "MATERIALE DI CONSUMO",
    "VASCHETTINA": "MATERIALE DI CONSUMO",
    "COPPETTA": "MATERIALE DI CONSUMO",
    "CUKI ALLUM": "MATERIALE DI CONSUMO",
    "MYSAC": "MATERIALE DI CONSUMO",
    "PULITUTTO": "MATERIALE DI CONSUMO",
    "RENOLIT": "MATERIALE DI CONSUMO",
    "SPAZZY": "MATERIALE DI CONSUMO",
    "SPRAY VETRI": "MATERIALE DI CONSUMO",
    "SHOCK SENSOR": "MATERIALE DI CONSUMO",
    "COPPETTE": "MATERIALE DI CONSUMO",
    # NOTA: COPPA GELATO già definita nella sezione GELATI principale
    "TOVAGLIOLO": "MATERIALE DI CONSUMO",
    "TOVAGLIOLI": "MATERIALE DI CONSUMO",
    "TOVAGLIOLIN": "MATERIALE DI CONSUMO",
    "PROGETTAZIONE GRAFICA": "SERVIZI E CONSULENZE",
    "STAMPA PANNELLO": "SERVIZI E CONSULENZE",
    "IMPOSTAZIONE GRAFICA": "SERVIZI E CONSULENZE",
    "PACCHETTO FE": "SERVIZI E CONSULENZE",
    "PPT ARRICCHIMENTO": "SERVIZI E CONSULENZE",
    "NOME E PER CONTO": "SERVIZI E CONSULENZE",
    "FEE A TRANSAZIONE": "SERVIZI E CONSULENZE",
        "PEDAGGI": "SERVIZI E CONSULENZE",
        "TRATTENIMENTI DAL VIVO": "SERVIZI E CONSULENZE",
        "UNICAPOS": "SERVIZI E CONSULENZE",
        "INVIO TELEMATICO MODELLO F24": "SERVIZI E CONSULENZE",
        "INVIO TELEMATICO F24": "SERVIZI E CONSULENZE",
    "PIATTI": "MATERIALE DI CONSUMO",
    "PIATTO": "MATERIALE DI CONSUMO",
    "PIATTINO": "MATERIALE DI CONSUMO",
    "BICCHIERI": "MANUTENZIONE E ATTREZZATURE",
    "LAMPONI GR": "FRUTTA",
    "LIME": "FRUTTA",
    "POMPELMI": "FRUTTA",
    "PASSIONFRUIT": "FRUTTA",
    "BICCHIERE": "MANUTENZIONE E ATTREZZATURE",
    "BICCHIERINO": "MANUTENZIONE E ATTREZZATURE",
    "CALICE": "MANUTENZIONE E ATTREZZATURE",
    "RAVANELLI": "VERDURE",
    "POSATE": "MATERIALE DI CONSUMO",
    "FORCHETTA": "MATERIALE DI CONSUMO",
    "FORCHETTE": "MATERIALE DI CONSUMO",
    "CUCCHIAIO": "MATERIALE DI CONSUMO",
        "ROASTBEEF": "CARNE",
    "SCAMONE": "CARNE",
        "SCOTTONA": "CARNE",
    "CUCCHIAI": "MATERIALE DI CONSUMO",
    "CUCCHIAINO": "MATERIALE DI CONSUMO",
    "COLTELLO PLASTICA": "MATERIALE DI CONSUMO",
    "POSATE LEGNO": "MATERIALE DI CONSUMO",
    "POSATE PLASTICA": "MATERIALE DI CONSUMO",
    "CANNUCCIA": "MATERIALE DI CONSUMO",
    "NOODLE": "PASTA E CEREALI",
    "GYOZA": "PASTA E CEREALI",
    "SAC A POCHE": "MATERIALE DI CONSUMO",
    "COP CAFFE CARTA": "MATERIALE DI CONSUMO",
    "BICCH CAFFE CARTA": "MATERIALE DI CONSUMO",
    "CARTA": "MATERIALE DI CONSUMO",
    "CARTA FORNO": "MATERIALE DI CONSUMO",
    "CARTA ASSORBENTE": "MATERIALE DI CONSUMO",
    "ROTOLO": "MATERIALE DI CONSUMO",
    "ROTOLI CUCINA": "MATERIALE DI CONSUMO",
    "SCOTTEX": "MATERIALE DI CONSUMO",
    "SACCHETTI": "MATERIALE DI CONSUMO",
    "SACCHETTO": "MATERIALE DI CONSUMO",
    "SACCHI": "MATERIALE DI CONSUMO",
    "SACCO": "MATERIALE DI CONSUMO",
    "SHOPPER": "MATERIALE DI CONSUMO",
    "BUSTE": "MATERIALE DI CONSUMO",
    "BUSTA": "MATERIALE DI CONSUMO",
    "CONTENITORI": "MATERIALE DI CONSUMO",
    "CONTENITORE": "MATERIALE DI CONSUMO",
    "ASPORTO": "MATERIALE DI CONSUMO",
    "TAKE AWAY": "MATERIALE DI CONSUMO",
    "COPERCHIO": "MATERIALE DI CONSUMO",
    "COPERCHI": "MATERIALE DI CONSUMO",
    "PELLICOLA": "MATERIALE DI CONSUMO",
    "FILM": "MATERIALE DI CONSUMO",
    "ALLUMINIO": "MATERIALE DI CONSUMO",
    "STAGNOLA": "MATERIALE DI CONSUMO",
    "DETERGENTE": "MATERIALE DI CONSUMO",
    "DETERSIVO": "MATERIALE DI CONSUMO",
    "SGRASSATORE": "MATERIALE DI CONSUMO",
    "SAPONE": "MATERIALE DI CONSUMO",
    "DISINFETTANTE": "MATERIALE DI CONSUMO",
    "IGIENIZZANTE": "MATERIALE DI CONSUMO",
    "GEL MANI": "MATERIALE DI CONSUMO",
    "GUANTI": "MATERIALE DI CONSUMO",
    "GUANTO": "MATERIALE DI CONSUMO",
    "SPUGNA": "MATERIALE DI CONSUMO",
    "SPUGNE": "MATERIALE DI CONSUMO",
    "STROFINACCIO": "MATERIALE DI CONSUMO",
    "STROFINACCI": "MATERIALE DI CONSUMO",
    "PANNO": "MATERIALE DI CONSUMO",
    "PANNI": "MATERIALE DI CONSUMO",
    "STRACCIO": "MATERIALE DI CONSUMO",
    "SCOPA": "MATERIALE DI CONSUMO",
    "MOCIO": "MATERIALE DI CONSUMO",
    "SPAZZOLONE": "MATERIALE DI CONSUMO",
    "TOVAGLIA": "MATERIALE DI CONSUMO",
    "TOVAGLIE": "MATERIALE DI CONSUMO",
    "TAZZA": "MANUTENZIONE E ATTREZZATURE",
    "TAZZINA": "MATERIALE DI CONSUMO",
    "POMPETTA": "MATERIALE DI CONSUMO",
    "DOSATORE": "MATERIALE DI CONSUMO",
    "TAPPO": "MATERIALE DI CONSUMO",
    "TAPPI": "MATERIALE DI CONSUMO",
    "SCOTCH": "MATERIALE DI CONSUMO",
    "NASTRO ADESIVO": "MATERIALE DI CONSUMO",
    "CONTEN.MONOP": "MATERIALE DI CONSUMO",
    "FINGERF.": "MATERIALE DI CONSUMO",
    "BARCHETTE": "MATERIALE DI CONSUMO",
    "TOV. APE ECO": "MATERIALE DI CONSUMO",
    "R-PET": "MATERIALE DI CONSUMO",
    "SACCHETTO COMPOST": "MATERIALE DI CONSUMO",
    "COMPOST.LE": "MATERIALE DI CONSUMO",
    "CAMICIA": "MANUTENZIONE E ATTREZZATURE",
    "CRAVATTINO": "MANUTENZIONE E ATTREZZATURE",
    "DIVISA": "MANUTENZIONE E ATTREZZATURE",
    "DIVISE": "MANUTENZIONE E ATTREZZATURE",
    "ETICHETTE": "MATERIALE DI CONSUMO",
    "ETICHETTA": "MATERIALE DI CONSUMO",
    "ETICHETTE ADESIVE": "MATERIALE DI CONSUMO",
    "SPAGO": "MATERIALE DI CONSUMO",
    "ELASTICI": "MATERIALE DI CONSUMO",
    "ELASTICO": "MATERIALE DI CONSUMO",
    "PENNARELLO": "MATERIALE DI CONSUMO",
    "PENNARELLI": "MATERIALE DI CONSUMO",
    "MARKER": "MATERIALE DI CONSUMO",
    "PACKAGING": "MATERIALE DI CONSUMO",
    "CONTEN.MONOP": "MATERIALE DI CONSUMO",
    "FINGERF.": "MATERIALE DI CONSUMO",
    "BARCHETTE": "MATERIALE DI CONSUMO",
    "TOV. APE ECO": "MATERIALE DI CONSUMO",
    "R-PET": "MATERIALE DI CONSUMO",
    "SACCHETTO COMPOST": "MATERIALE DI CONSUMO",
    "COMPOST.LE": "MATERIALE DI CONSUMO",
    "CAMICIA": "MANUTENZIONE E ATTREZZATURE",
    "CRAVATTINO": "MANUTENZIONE E ATTREZZATURE",
    "DIVISA": "MANUTENZIONE E ATTREZZATURE",
    "DIVISE": "MANUTENZIONE E ATTREZZATURE",
    "PORTABACCHETTE": "MATERIALE DI CONSUMO",
    "TAZZE": "MANUTENZIONE E ATTREZZATURE",
    "PIATTINI": "MATERIALE DI CONSUMO",
    "COPERTI": "MATERIALE DI CONSUMO",
    "STOVIGLIE": "MATERIALE DI CONSUMO",
    
    # ===== SERVIZI E CONSULENZE =====
    "GOOGLE WORKSPACE": "SERVIZI E CONSULENZE",
    "WORKSPACE": "SERVIZI E CONSULENZE",
    "CANONE": "SERVIZI E CONSULENZE",
    "CONTRIBUTO ATTIVAZIONE": "SERVIZI E CONSULENZE",
    "DIRITTI": "SERVIZI E CONSULENZE",
    "RICAMO": "SERVIZI E CONSULENZE",
    "CONSULENZA": "SERVIZI E CONSULENZE",
    "COMMERCIALISTA": "SERVIZI E CONSULENZE",
    "CONTABILITÃ€": "SERVIZI E CONSULENZE",
    "CONTABILE": "SERVIZI E CONSULENZE",
    "CONSULENTE FISCALE": "SERVIZI E CONSULENZE",
    "FISCALE": "SERVIZI E CONSULENZE",
    "FATTURAZIONE ELETTRONICA": "SERVIZI E CONSULENZE",
    "PUBBLICITÃ€": "SERVIZI E CONSULENZE",
    "MARKETING": "SERVIZI E CONSULENZE",
    "SOCIAL MEDIA": "SERVIZI E CONSULENZE",
    "PUBBLICITA": "SERVIZI E CONSULENZE",
    "POS": "SERVIZI E CONSULENZE",
    # NOTA: "COMMISSIONI" già definita sopra (sezione PROBLEMI AI)
    "COMMISSIONE BANCARIA": "SERVIZI E CONSULENZE",
    "BONIFICO": "SERVIZI E CONSULENZE",
    "ASSICURAZIONE": "SERVIZI E CONSULENZE",
    "POLIZZA": "SERVIZI E CONSULENZE",
    "SOFTWARE": "SERVIZI E CONSULENZE",
    "GESTIONALE": "SERVIZI E CONSULENZE",
    "ABBONAMENTO": "SERVIZI E CONSULENZE",
    "SMALTIMENTO": "SERVIZI E CONSULENZE",
    "RIFIUTI": "SERVIZI E CONSULENZE",
    "HACCP": "SERVIZI E CONSULENZE",
    "CERTIFICAZIONE": "SERVIZI E CONSULENZE",
    "BONUS INTERNET": "SERVIZI E CONSULENZE",
    "BONUS LINEA": "SERVIZI E CONSULENZE",
    "PROMO VALORE": "SERVIZI E CONSULENZE",
    "NUMERI MOBILI": "SERVIZI E CONSULENZE",
    "RICAVI": "SERVIZI E CONSULENZE",
    "ALTRI IMPORTI": "SERVIZI E CONSULENZE",
    "FORMAZIONE": "SERVIZI E CONSULENZE",
    "CORSO": "SERVIZI E CONSULENZE",
    "HOSTING": "SERVIZI E CONSULENZE",
    "TOP RANK": "SERVIZI E CONSULENZE",
    "TENUTA DELLA CONTABILIT": "SERVIZI E CONSULENZE",
    "ONORARI": "SERVIZI E CONSULENZE",
    "REVISORE LEGALE": "SERVIZI E CONSULENZE",
    "REVISORE": "SERVIZI E CONSULENZE",
    "PREMIO POSTICIPATO": "SERVIZI E CONSULENZE",
    "SPESE TRANSAZIONE": "SERVIZI E CONSULENZE",
    "SPESE DI AMMINISTRAZIONE": "SERVIZI E CONSULENZE",
    "GESTIONE AMMINISTRATIVA": "SERVIZI E CONSULENZE",
    "SPESE ACCESSORIE": "SERVIZI E CONSULENZE",
    "SPESE VARIE": "SERVIZI E CONSULENZE",
    "COUPON": "📝 NOTE E DICITURE",
    "BUONO SCONTO": "📝 NOTE E DICITURE",
    
    # ===== PENALI E INTERESSI =====
    "INDENNITA": "SERVIZI E CONSULENZE",
    "INDENNITÃ€": "SERVIZI E CONSULENZE",
    "MORA": "SERVIZI E CONSULENZE",
    "RITARDATO PAGAMENTO": "SERVIZI E CONSULENZE",
    "INTERESSI": "SERVIZI E CONSULENZE",
    
    # ===== DESCRIZIONI GENERICHE =====
    "SERVIZIO": "SERVIZI E CONSULENZE",
    "VISITA MEDICA": "SERVIZI E CONSULENZE",
    "PRESTAZIONE PROFESSIONALE": "SERVIZI E CONSULENZE",
    "RESTYLING GRAFICO": "SERVIZI E CONSULENZE",
    "APERTURA PRATICA": "SERVIZI E CONSULENZE",
    "MENU MARZO": "SERVIZI E CONSULENZE",
    "PUNTO METALLICO": "SERVIZI E CONSULENZE",
    "OFFERTA": "MANUTENZIONE E ATTREZZATURE",
    "REGISTRAZIONE": "MANUTENZIONE E ATTREZZATURE",
    
    # ===== UTENZE E LOCALI =====
    "ENERGIA ELETTRICA": "UTENZE E LOCALI",
    "RETE ELETTRICA": "UTENZE E LOCALI",
    "ONERI DI SISTEMA": "UTENZE E LOCALI",
    "SPESA PER LA VENDITA": "UTENZE E LOCALI",
    "SPESA PER LA TARIFFA": "UTENZE E LOCALI",
    "LUCE": "UTENZE E LOCALI",
    "ELETTRICITÃ€": "UTENZE E LOCALI",
    "GAS": "UTENZE E LOCALI",
    "METANO": "UTENZE E LOCALI",
    "GPL": "UTENZE E LOCALI",
    "LOCAZIONE": "UTENZE E LOCALI",
    "AFFITTO": "UTENZE E LOCALI",
    "CANONE LOCAZIONE": "UTENZE E LOCALI",
    "CONDOMINIO": "UTENZE E LOCALI",
    "IMU": "UTENZE E LOCALI",
    "TARI": "UTENZE E LOCALI",
    "TASSE": "UTENZE E LOCALI",
    "IMPOSTA": "UTENZE E LOCALI",
    "TELEFONO": "UTENZE E LOCALI",
    "TELECOM": "UTENZE E LOCALI",
    "TIM": "UTENZE E LOCALI",
    "VODAFONE": "UTENZE E LOCALI",
    "WIND": "UTENZE E LOCALI",
    "ILIAD": "UTENZE E LOCALI",
    "FASTWEB": "UTENZE E LOCALI",
    "INTERNET": "UTENZE E LOCALI",
    "ADSL": "UTENZE E LOCALI",
    "FIBRA": "UTENZE E LOCALI",
    "SUPERFIBRA": "UTENZE E LOCALI",
    "TUTTOFIBRA": "UTENZE E LOCALI",
    "TIM GUARDIAN": "UTENZE E LOCALI",
    "5G POWER": "UTENZE E LOCALI",
    "RISCALDAMENTO": "UTENZE E LOCALI",
    "CLIMATIZZAZIONE": "UTENZE E LOCALI",
    "TOTALE IMPOSTE": "UTENZE E LOCALI",
    "ARROTONDAMENTO": "UTENZE E LOCALI",
    # Bollette energia/gas - voci dettagliate
    "SPREAD": "UTENZE E LOCALI",
    "QUOTA FISSA": "UTENZE E LOCALI",
    "QUOTA ENERGIA": "UTENZE E LOCALI",
    "QUOTA TRASPORTO": "UTENZE E LOCALI",
    "QUOTA POTENZA": "UTENZE E LOCALI",
    "QUOTA VARIABILE": "UTENZE E LOCALI",
    "CORRISPETTIVO": "UTENZE E LOCALI",
    "COMPONENTE": "UTENZE E LOCALI",
    "UPLIFT": "UTENZE E LOCALI",
    "DISTRIBUZIONE": "UTENZE E LOCALI",
    "DISPACCIAMENTO": "UTENZE E LOCALI",
    "SBILANCIAMENTO": "UTENZE E LOCALI",
    "ACCISA": "UTENZE E LOCALI",
    "COMMERCIALIZZAZIONE": "UTENZE E LOCALI",
    "ONERI": "UTENZE E LOCALI",
    "ASOS": "UTENZE E LOCALI",
    "ARIM": "UTENZE E LOCALI",
    "SCAGLIONE": "UTENZE E LOCALI",
    "CAPACITA": "UTENZE E LOCALI",
    "CAPACITÀ": "UTENZE E LOCALI",
    "CCR": "UTENZE E LOCALI",
    "MANCATA PRODUZIONE": "UTENZE E LOCALI",
    "COSTI FUNZIONAMENTO TERNA": "UTENZE E LOCALI",
    "PERTITE ECONOMICHE": "UTENZE E LOCALI",
    
    # ===== MANUTENZIONE E ATTREZZATURE =====
    "VASSOIO VETRINA": "MANUTENZIONE E ATTREZZATURE",
    "VASSOIO INOX": "MANUTENZIONE E ATTREZZATURE",
    "CARRELLO": "MANUTENZIONE E ATTREZZATURE",
    "PROLUNGA": "MANUTENZIONE E ATTREZZATURE",
    "RIPARAZIONE": "MANUTENZIONE E ATTREZZATURE",
    "MANUTENZIONE": "MANUTENZIONE E ATTREZZATURE",
    "LIBERATO": "MANUTENZIONE E ATTREZZATURE",
    "RICERCA GUASTO": "MANUTENZIONE E ATTREZZATURE",
    "SOSTITUZIONE": "MANUTENZIONE E ATTREZZATURE",
    "INSTALLAZIONE": "MANUTENZIONE E ATTREZZATURE",
    "UPGRADE": "MANUTENZIONE E ATTREZZATURE",
    "KIT BASE": "MANUTENZIONE E ATTREZZATURE",
    "ZEROVISION": "MANUTENZIONE E ATTREZZATURE",
    "PACK SOS": "MANUTENZIONE E ATTREZZATURE",
    "OFFERTA SCONTO CANONE": "MANUTENZIONE E ATTREZZATURE",
    "FRIGORIFERO": "MANUTENZIONE E ATTREZZATURE",
    "FRIGO": "MANUTENZIONE E ATTREZZATURE",
    "FORNO": "MANUTENZIONE E ATTREZZATURE",
    "LAVASTOVIGLIE": "MANUTENZIONE E ATTREZZATURE",
    "LAVABICCHIERI": "MANUTENZIONE E ATTREZZATURE",
    "IMPIANTO": "MANUTENZIONE E ATTREZZATURE",
    "ELETTRICO": "MANUTENZIONE E ATTREZZATURE",
    "IDRAULICO": "MANUTENZIONE E ATTREZZATURE",
    "CLIMATIZZATORE": "MANUTENZIONE E ATTREZZATURE",
    "CONDIZIONATORE": "MANUTENZIONE E ATTREZZATURE",
    "CAPPA": "MANUTENZIONE E ATTREZZATURE",
    "ASPIRAZIONE": "MANUTENZIONE E ATTREZZATURE",
    "ARREDO": "MANUTENZIONE E ATTREZZATURE",
    "MOBILIO": "MANUTENZIONE E ATTREZZATURE",
    "TAVOLO": "MANUTENZIONE E ATTREZZATURE",
    "SEDIA": "MANUTENZIONE E ATTREZZATURE",
    "ATTREZZATURA": "MANUTENZIONE E ATTREZZATURE",
    "MACCHINA CAFFÃˆ": "MANUTENZIONE E ATTREZZATURE",
    "MACINADOSATORE": "MANUTENZIONE E ATTREZZATURE",
    "MIXER": "MANUTENZIONE E ATTREZZATURE",
    "ROBOT": "MANUTENZIONE E ATTREZZATURE",
    "ABBATTITORE": "MANUTENZIONE E ATTREZZATURE",
    "AFFETTATRICE": "MANUTENZIONE E ATTREZZATURE",
    "BILANCIA": "MANUTENZIONE E ATTREZZATURE",
    "COLTELLO": "MANUTENZIONE E ATTREZZATURE",
    "PENTOLE": "MANUTENZIONE E ATTREZZATURE",
    "PADELLE": "MANUTENZIONE E ATTREZZATURE",
    "UTENSILI": "MANUTENZIONE E ATTREZZATURE",

    
    # ===== GELATI E DESSERT (keywords aggiuntivi, base in sezione GELATI sopra) =====
    # NOTA: GELATO, GELATI, CONO, COPPA GELATO già definiti nella sezione GELATI principale
    "PIRATA": "GELATI E DESSERT",
    "PRINCIPESSA": "GELATI E DESSERT",
    "TARTUFO": "GELATI E DESSERT",
    "SOUFFLE": "GELATI E DESSERT",
    "SOUFFLÉ": "GELATI E DESSERT",
    "MERINGA": "GELATI E DESSERT",
    "CROCCANTE": "GELATI E DESSERT",
    "FR.RI.": "GELATI E DESSERT",
    "FRESCO RIPIENO": "GELATI E DESSERT",
    "COCCO CF": "GELATI E DESSERT",
    "SPAGNOLA CF": "GELATI E DESSERT",
    
    # ===== INGREDIENTI ASIATICI =====
    # NOTA: Ingredienti specifici sushi/decorazione → SUSHI VARIE
    # Salse asiatiche generiche restano in SALSE E CREME
    "NORI": "SUSHI VARIE",
    "YAKI NORI": "SUSHI VARIE",
    "GIKU": "SUSHI VARIE",
    "SUSHI NORI": "SUSHI VARIE",
    "ALGHE": "SUSHI VARIE",
    "ALGA": "SUSHI VARIE",
    "WAKAME": "SUSHI VARIE",
    "IKURA": "SUSHI VARIE",
    "KATSUOBUSHI": "SUSHI VARIE",
    "KONBU": "SUSHI VARIE",
    "PANKO": "SUSHI VARIE",
    "DASHI": "SPEZIE E AROMI",
    "MISO": "SALSE E CREME",
    "ZENZERO SALAMOIA": "SCATOLAME E CONSERVE",
    "ZENZERO IN SALAMOIA": "SCATOLAME E CONSERVE",
    "SESAMO": "SPEZIE E AROMI",
    "SESAMO NERO": "SPEZIE E AROMI",
    "WASABI": "SUSHI VARIE",
    "TEMPURA": "SUSHI VARIE",
    "EDAMAME": "VERDURE",
    "CIPOLLA FRITTA": "SCATOLAME E CONSERVE",
    "BAMBU": "SUSHI VARIE",
    "BAMBÙ": "SUSHI VARIE",
    "FOGLIE BAMBU": "SUSHI VARIE",
    "FOGLIE DI BAMBU": "SUSHI VARIE",
    "TOBIKO": "SUSHI VARIE",
    "EBIKO": "SUSHI VARIE",
    "MASAGO": "SUSHI VARIE",
    "SUSHI": "SUSHI VARIE",
    "TOPPING SUSHI": "SUSHI VARIE",
        "POLPETTI": "PESCE",
        "GAMB.ROSSO": "PESCE",
        "SEPPIOLINE": "PESCE",
    
    # ===== SALSE ASIATICHE =====
    "SAKE CUCINA": "SALSE E CREME",
    "MIRIN": "SALSE E CREME",
    "SAMBAL": "SALSE E CREME",
    "SAMBAL OELEK": "SALSE E CREME",
    "UNAGI": "SALSE E CREME",
    "UNAGI SAUCE": "SALSE E CREME",
    "TERIYAKI": "SALSE E CREME",
    "HAKUTSURU": "SALSE E CREME",
    "MIZKAN": "SALSE E CREME",
    "DRESSING": "SALSE E CREME",
    
    # ===== BEVANDE ASIATICHE =====
    "SPRITE": "BEVANDE",
    "FEVER TREE": "BEVANDE",
        "GEKKEIKAN SAKE": "DISTILLATI",
        "FALANG.": "VINI",
    "SAPPORO": "BIRRE",
    "ASAHI": "BIRRE",
    "KIRIN": "BIRRE",
    "TSINGTAO": "BIRRE",
    "BIRRA CAN": "BIRRE",
    "SILVER CAN": "BIRRE",
    
    # ===== MATERIALE CONSUMO SPECIFICO =====
    "BASTONCINO BAMBU": "MATERIALE DI CONSUMO",
    "BACCHETTE": "MATERIALE DI CONSUMO",
    "BOBINA": "MATERIALE DI CONSUMO",
    "STRAPI": "MATERIALE DI CONSUMO",
    "STRAPPO": "MATERIALE DI CONSUMO",
    "CONTRIBUTO SPESE": "MATERIALE DI CONSUMO",
    "SPESE CONSEGNA": "MATERIALE DI CONSUMO",
    "SODA": "MATERIALE DI CONSUMO",
    "BICARBONATO": "MATERIALE DI CONSUMO",
    "TACO SHELLS": "PASTA E CEREALI",
    "NUVOLE DI DRAGO": "PASTA E CEREALI",
    "PASTO DI GRANO": "PASTA E CEREALI",
    "WHITE PRAWN CRACKERS": "PASTA E CEREALI",
    "CRACKERS": "PASTA E CEREALI",
    
    # ===== FIX DIZIONARIO CONSERVATIVO - KEYWORD SPECIFICHE =====
    "BISCOTTINI": "PASTICCERIA",
    "CANDEGGINA": "MATERIALE DI CONSUMO",
    "CROSTATE": "PASTICCERIA",
    "CROSTATINE": "PASTICCERIA",
    "DOLCI NATALIZI": "PASTICCERIA",
    "FACCINE": "PASTICCERIA",
    "MIX NATALE": "PASTICCERIA",
    "MOUSSE MANI": "MATERIALE DI CONSUMO",
    "PASSATA POMOD": "SCATOLAME E CONSERVE",
    "PASSATA POMODORO": "SCATOLAME E CONSERVE",
    "SALAME CIOCCOLATO": "PASTICCERIA",
    "SALAME DI CIOCCOLATO": "PASTICCERIA",

# ===== KEYWORDS DAL FIX REPORT ERRORI =====
    "ARAGONOSTINE": "PASTICCERIA",
    "ARAGOSTINE": "PASTICCERIA",
    "GIRELLA": "PASTICCERIA",
    "CREMA CATALANA": "PASTICCERIA",
    "CREME BRULEE": "PASTICCERIA",
    "BAO CREMA": "PASTICCERIA",
    "BEVANDA DI SOJA": "BEVANDE",
    "BEVANDA SOJA": "BEVANDE",
    "BOLLO SPESA": "SERVIZI E CONSULENZE",
    "BRIE": "LATTICINI",
    "BRILL": "MATERIALE DI CONSUMO",
    "CANES": "PASTICCERIA",
    "CANESTRELLI": "PASTICCERIA",
    "CANESTRELLO": "PASTICCERIA",
    "CANNOLO": "PASTICCERIA",
    "CANNONCINI": "PASTICCERIA",
    "CANNONCINO": "PASTICCERIA",
    "CANNOLI SFOGLIA": "PASTICCERIA",
    "CONCHIGLIA PANNA": "PASTICCERIA",
    # "ARAGOSTINE": duplicato rimosso (giÃ  definito sopra)
    "CAPRA": "LATTICINI",
    "CAPRINO": "LATTICINI",
    "CAPRINO VACCINO": "LATTICINI",
    "CREMA GIANDUIA": "SALSE E CREME",
    "CREMA GIANDUJA": "SALSE E CREME",
    # NOTA: "EDAMAME" già definita sopra (sezione INGREDIENTI ASIATICI)
    "ESSE": "PASTICCERIA",
    "ESSE GIGANTI": "PASTICCERIA",
    "ESSENCE": "PASTICCERIA",
    "FARCITURA": "SALSE E CREME",
    "FARCITURA CACAO": "SALSE E CREME",
    "FROLLA": "PASTICCERIA",
    "FROLLA MISTA": "PASTICCERIA",
    "GENOVESI": "PASTICCERIA",
    "GIANDUIA": "PASTICCERIA",
    "GIANDUJA": "PASTICCERIA",
    "LAVASTOV": "MATERIALE DI CONSUMO",
    "MISTER X": "MATERIALE DI CONSUMO",
    # NOTA: "TAZZA" già definita sopra (sezione MATERIALI CONSUMO)
    "GREMBIULE": "MANUTENZIONE E ATTREZZATURE",
    "ZOCCOLINO": "MANUTENZIONE E ATTREZZATURE",
    "ACCENDIGAS": "MANUTENZIONE E ATTREZZATURE",
    "SALE PASTIGLIE": "MATERIALE DI CONSUMO",
    "MISTO FROLLA": "PASTICCERIA",
    "NOCE BOV": "CARNE",
    "NOCE BOVINO": "CARNE",
    "OCCHI BUE": "PASTICCERIA",
    "OCCHI DI BUE": "PASTICCERIA",
    "PARMA": "SALUMI",
    # âœ… PASSATA â†’ SCATOLAME E CONSERVE (unificato, rimossi duplicati da righe 819-821)
    "PASSATA": "SCATOLAME E CONSERVE",
    # "PASSATA POMOD": duplicato rimosso (definito sopra come SALSE E CREME, ora unificato)
    # "PASSATA POMODORO": duplicato rimosso (definito sopra come SALSE E CREME, ora unificato)
    "PANNA SPRAY": "VARIE BAR",
    "ZUCCHERO BUSTINE": "VARIE BAR",
    "BUSTINE ZUCCH": "VARIE BAR",
    "BUSTINE ZUCCHERO": "VARIE BAR",
    "CIOK": "VARIE BAR",
    "POLPA ODK": "VARIE BAR",
    "ODK POLPA": "VARIE BAR",
    "DIMSUM": "PASTA E CEREALI",
    "HACCP": "SERVIZI E CONSULENZE",
    # NOTA: "ZUCCHERO BAR" già definita sopra (sezione VARIE BAR)
    "PAIN AU CHOCOLAT": "PASTICCERIA",
    "CROIS": "PASTICCERIA",
    "FAGOTTINO": "PASTICCERIA",
    "WAFFELS": "PASTICCERIA",
    "EDAMINO": "LATTICINI",
    "FRANGELICO": "AMARI/LIQUORI",
    "MARTINI BIANCO": "AMARI/LIQUORI",
    "MARTINI ROSSO": "AMARI/LIQUORI",
    "MARTINI DRY": "AMARI/LIQUORI",
    "ALBUME": "UOVA",
    "LATUHT": "LATTICINI",
    "HOPLA": "SALSE E CREME",
    "PANBURGER": "PRODOTTI DA FORNO",
    "PANCARRE": "PRODOTTI DA FORNO",
    "PETITS PAINS": "PRODOTTI DA FORNO",
    "YOUTIAO": "PRODOTTI DA FORNO",
    "TABASCO": "SALSE E CREME",
    "HEINZ MAYO": "SALSE E CREME",
    "INS.MISTA": "VERDURE",
    "INS. MISTA": "VERDURE",
    "INS.ROMANA": "VERDURE",
    "INS. ROMANA": "VERDURE",
    "INS.NOVELLA": "VERDURE",
    "PEPERONCINI": "SPEZIE E AROMI",
    "PEPE BIANCO": "SPEZIE E AROMI",
    "MENTA GR": "SPEZIE E AROMI",
    "MENTA MIN": "SPEZIE E AROMI",
    "OSTRICHE": "PESCE",
    "TOTANI": "PESCE",
    "RIBOLLA": "VINI",
    "IGT": "VINI",
    "CONGUAGLIO": "SERVIZI E CONSULENZE",
    "CONSUNTIVO": "SERVIZI E CONSULENZE",
    "CORNETTO": "PASTICCERIA",
    "CORNETTI": "PASTICCERIA",
    "KRAPFEN": "PASTICCERIA",
    "SFOGLIATELLA": "PASTICCERIA",
    "SFOGLIATELLE": "PASTICCERIA",
    "BOMBOLONE": "PASTICCERIA",
    "BOMBOLONI": "PASTICCERIA",
    "BIGNE": "PASTICCERIA",
    "PIADINA": "PRODOTTI DA FORNO",
    "PIADINE": "PRODOTTI DA FORNO",
    "PREGISAN": "MATERIALE DI CONSUMO",
    "PREMI": "SERVIZI E CONSULENZE",
    "RIF SAN PREGISAN": "MATERIALE DI CONSUMO",
    "SAVOIARDI": "PASTICCERIA",
    "SAVOIARDO": "PASTICCERIA",
    "SICILIANI CANNOLO": "PASTICCERIA",
    "SICILIANO CANNOLO": "PASTICCERIA",
    "SOIA": "BEVANDE",
    "SOJA": "BEVANDE",
    "SPESE DI BOLLO": "SERVIZI E CONSULENZE",
    "STRUDEL": "PASTICCERIA",

    # ===== BATCH FIX: Plurali/singolari mancanti =====
    # PESCE - varianti plurali/singolari
    "SALMONI": "PESCE",          # plurale di SALMONE (×3 fatture)
    "BRANZINI": "PESCE",         # plurale di BRANZINO (×4 fatture)
    "RICCIOLA": "PESCE",         # ricciola oceanica (×3 fatture)
    "SCAMPO": "PESCE",           # singolare di SCAMPI (×2 fatture)
    "RICCIO": "PESCE",           # riccio di mare
    "CAPPASANTA": "PESCE",       # cappasanta/capasanta
    "CAPPESANTA": "PESCE",       # variante
    # VERDURE - singolari/plurali mancanti
    "CIPOLLA": "VERDURE",        # singolare di CIPOLLE
    "CAVOLFIORI": "VERDURE",     # plurale di CAVOLFIORE
    "CETRIOLI": "VERDURE",
    "CETRIOLO": "VERDURE",
    "CAVOLO": "VERDURE",
    "CAVOLI": "VERDURE",
    "FRAGOLA": "FRUTTA",         # singolare di FRAGOLE
    "MELA": "FRUTTA",            # singolare di MELE

    # ===== BATCH FIX: Keyword verdure semplici =====
    "PAK CHOI": "VERDURE",
    "PACHOI": "VERDURE",
    "BOK CHOY": "VERDURE",
    "ICEBERG": "VERDURE",
    "FIORE DI ZUCCA": "VERDURE",
    "FIORI DI ZUCCA": "VERDURE",
    "AGLIO": "VERDURE",
    "PORRO": "VERDURE",
    "PORRI": "VERDURE",
    "DAIKON": "VERDURE",
    "CRAUTI": "VERDURE",
    "CHAYOTE": "VERDURE",
    "RAPA": "VERDURE",
    "RAPE": "VERDURE",
    "CIPOLOTTO": "VERDURE",
    "CILIEGINO": "VERDURE",      # pomodoro ciliegino
    "CRESS": "VERDURE",          # microgreens/cress mix
    "VALERIANA": "VERDURE",

    # ===== BATCH FIX: Keyword frutta semplici =====
    "PAPAYA": "FRUTTA",
    "MELAGRANA": "FRUTTA",
    "MELOGRANO": "FRUTTA",
    "AVOCADO": "FRUTTA",
    "MANDORLE": "PASTA E CEREALI",         # frutta secca → secco
    "MANDORLA": "PASTA E CEREALI",

    # ===== BATCH FIX: Carne - keyword generiche sicure =====
    "BOVINO": "CARNE",           # copre: roast-beef bovino, coscia bovino, nervetti bovino (×5)
    "ROAST BEEF": "CARNE",
    "ROAST-BEEF": "CARNE",
    "CINGHIALE": "CARNE",
    "NERVETTI": "CARNE",
    "COSCIA": "CARNE",

    # ===== BATCH FIX: Latticini =====
    "PHILADELPHIA": "LATTICINI",  # formaggio spalmabile (×3 fatture)
    "DOUFU": "LATTICINI",         # variante cinese di tofu
    "TOFU": "LATTICINI",
    "GORGONZ": "LATTICINI",

    # ===== BATCH FIX: Spezie e aromi =====
    "FINOCCHIETTO": "SPEZIE E AROMI",  # erba aromatica (non verdura)
    "ZENZERO": "SPEZIE E AROMI",       # radice/spezia

    # ===== BATCH FIX: Salse asiatiche =====
    "SRIRACHA": "SALSE E CREME",
    "SOYSAUCE": "SALSE E CREME",
    "SOY SAUCE": "SALSE E CREME",
    "HADAY": "SALSE E CREME",          # brand salsa soia cinese

    # ===== BATCH FIX: Gelati e dessert pronti =====
    "MONOPORZIONE": "GELATI E DESSERT",  # dessert pronto non da cucinare
    "DESSERT": "GELATI E DESSERT",
    "MOCHI": "GELATI E DESSERT",
    "MOCCHI": "GELATI E DESSERT",
    "MARITOZZO": "PASTICCERIA",
    "MUFFINS": "PASTICCERIA",

    # ===== BATCH FIX: Materiale di consumo =====
    "AMMONIACA": "MATERIALE DI CONSUMO",
    "ALCOOL": "MATERIALE DI CONSUMO",
    "ACCENDIGAS": "MATERIALE DI CONSUMO",
    "CIF": "MATERIALE DI CONSUMO",
    "CANDEG": "MATERIALE DI CONSUMO",
    "MOP": "MATERIALE DI CONSUMO",     # mop/lavapavimenti
    "SGRASS": "MATERIALE DI CONSUMO",  # abbreviazione sgrassatore
    "DEO BAGNO": "MATERIALE DI CONSUMO",

    # ===== BATCH FIX: Shop =====
    "DAYGUM": "SHOP",

    # ===== BATCH FIX: Servizi e consulenze =====
    "SPESE DI INCASSO": "SERVIZI E CONSULENZE",
    "ESTRATTO CONTO": "SERVIZI E CONSULENZE",
    "COSTO A TRANSAZIONE": "SERVIZI E CONSULENZE",
    "COSTO FATTURA ELETTRONICA": "SERVIZI E CONSULENZE",
    "NR.TRANSAZIONI": "SERVIZI E CONSULENZE",
    "TRANSAZIONI": "SERVIZI E CONSULENZE",
    "DISINFESTAZIONE": "SERVIZI E CONSULENZE",
    "BOLLO": "SERVIZI E CONSULENZE",   # bollo pagato, riaddebito bollo
    "RIADDEB": "SERVIZI E CONSULENZE",  # riaddebito
    "ACCREDITO": "SERVIZI E CONSULENZE",
    "RIMBORSO": "SERVIZI E CONSULENZE",
    "PROGRAMMAZIONI": "SERVIZI E CONSULENZE",  # programmazioni menu, software, etc.

    # ===== BATCH FIX: Utenze e locali =====
    "ISTAT": "UTENZE E LOCALI",        # adeguamento ISTAT (affitto)

    # ===== BATCH FIX: Prodotti mancanti dalla categorizzazione =====
    # Latticini - brand/abbreviazioni italiane
    "GALBANINO": "LATTICINI",
    "BIRAGHINI": "LATTICINI",
    "GRANBIRAGHI": "LATTICINI",
    "GRATTUGGIATO": "LATTICINI",
    "SPALMABILE": "LATTICINI",
    "EDAMER": "LATTICINI",
    "OVOLINE": "LATTICINI",
    # Verdure/Ortofrutta
    "ORTOFRUTTA": "VERDURE",
    "ERBETTE": "VERDURE",
    # Scatolame e conserve
    "BONDUELLE": "SCATOLAME E CONSERVE",
    "CIPOLLINE": "SCATOLAME E CONSERVE",
    # Materiale di consumo - pulizia e carta
    "PANNOSPUGNA": "MATERIALE DI CONSUMO",
    "ASCIUGATUTTO": "MATERIALE DI CONSUMO",
    "AIR WICK": "MATERIALE DI CONSUMO",
    "VETRIL": "MATERIALE DI CONSUMO",
    "WC NET": "MATERIALE DI CONSUMO",
    "CEROTTI": "MATERIALE DI CONSUMO",
    "ANTIGRASSO": "MATERIALE DI CONSUMO",
    "CANGURINO": "MATERIALE DI CONSUMO",
    # Manutenzione - pulizia macchine caffè
    "PULYCAFF": "MANUTENZIONE E ATTREZZATURE",
    "PULYMILK": "MANUTENZIONE E ATTREZZATURE",
    # Secco - sale e frutta secca
    "NOVOSAL": "PASTA E CEREALI",
    "SALE IODATO": "PASTA E CEREALI",
    # Shop - snack
    "TARALLINI": "SHOP",
    "ARACHIDI": "SHOP",
    "S.CARLO": "SHOP",
    # Salumi
    "SPIANATA": "SALUMI",
    # Prodotti da forno
    "TORTILLA": "PRODOTTI DA FORNO",
    "STOP-TOAST": "PRODOTTI DA FORNO",
    # Frutta
    "FRUTTI DI BOSCO": "FRUTTA",
    # Spezie
    "VANIGLIA": "SPEZIE E AROMI",
    # Varie bar
    "DOLCIFICANTE": "VARIE BAR",
    # Materiale di consumo - residui
    "BORSA": "MATERIALE DI CONSUMO",
    "SHOPPER": "MATERIALE DI CONSUMO",
    "VASSOIO": "MATERIALE DI CONSUMO",
    "ADDOLCITORE": "MATERIALE DI CONSUMO",
    "TOV.": "MATERIALE DI CONSUMO",          # abbreviazione tovaglioli
    "TOVAGLIETTA": "MATERIALE DI CONSUMO",
    "TRAPUNTATI": "MATERIALE DI CONSUMO",     # tovaglioli trapuntati
    "MONOVELO": "MATERIALE DI CONSUMO",       # tovaglioli monovelo
    "CANGURINO": "MATERIALE DI CONSUMO",      # brand carta/tovaglioli
    # Scatolame
    "SCATOLAME": "SCATOLAME E CONSERVE",
    # Frutta secca
    "NOCI": "PASTA E CEREALI",

}

# ============================================================
# SOGLIE KPI RISTORAZIONE
# ============================================================
# Soglie di riferimento per commenti automatici sui KPI.
# Ogni lista è ordinata per soglia crescente (o decrescente per margini).
# Formato: (soglia_max, emoji, commento)
# L'ultima entry cattura tutto ciò che supera le soglie precedenti.

KPI_SOGLIE = {
    'food_cost': [
        (28, '🟢', 'Food cost eccellente — ottimo controllo acquisti e sprechi'),
        (33, '🟡', 'Food cost nella norma per il settore ristorazione'),
        (38, '🟠', 'Food cost sopra la media — valutare ottimizzazione acquisti o menù'),
        (100, '🔴', 'Food cost critico — necessaria revisione fornitori, porzioni e sprechi'),
    ],
    'spese_generali': [
        (15, '🟢', 'Spese generali contenute — gestione efficiente'),
        (22, '🟡', 'Spese generali nella norma'),
        (28, '🟠', 'Spese generali elevate — verificare utenze e contratti'),
        (100, '🔴', 'Spese generali fuori controllo — necessaria rinegoziazione'),
    ],
    'personale': [
        (24, '🟢', 'Costo del lavoro contenuto — buona efficienza del personale'),
        (30, '🟡', 'Costo del lavoro nella norma per il settore'),
        (35, '🟠', 'Costo del lavoro elevato — verificare turni, produttività e coperti'),
        (100, '🔴', 'Costo del lavoro critico — incidenza troppo alta sul fatturato'),
    ],
    'primo_margine': [
        (55, '🔴', '1° Margine molto basso — costi F&B troppo alti rispetto al fatturato'),
        (62, '🟠', '1° Margine sotto la media — margine di miglioramento sui costi'),
        (70, '🟡', '1° Margine nella norma per il settore'),
        (100, '🟢', '1° Margine eccellente — ottima marginalità sui prodotti'),
    ],
    'mol': [
        (5, '🔴', 'MOL critico — l\'attività non genera margine sufficiente'),
        (12, '🟠', 'MOL basso — necessario contenere costi o incrementare ricavi'),
        (20, '🟡', 'MOL nella norma — margine operativo adeguato'),
        (100, '🟢', 'MOL eccellente — ottima redditività operativa'),
    ],
    # Fatturato: soglie relative (coefficiente di variazione %)
    'fatturato_variabilita': [
        (10, '🟢', 'Fatturato stabile nel periodo — buona costanza nei ricavi'),
        (25, '🟡', 'Fatturato con oscillazioni moderate nel periodo'),
        (100, '🟠', 'Fatturato molto variabile nel periodo — verificare stagionalità o anomalie'),
    ],
}

# ============================================================
# AMMINISTRATORI DI SISTEMA
# ============================================================

import os as _os

# Lista email degli amministratori - caricata da variabile d'ambiente
# Configurare: ADMIN_EMAILS=email1@example.com,email2@example.com
_admin_env = _os.environ.get("ADMIN_EMAILS", "").strip()
ADMIN_EMAILS = [e.strip().lower() for e in _admin_env.split(",") if e.strip()] if _admin_env else ["mattiadavolio90@gmail.com"]
_admin_warning_flag = "OHH_ADMIN_EMAILS_WARNING_EMITTED"
if not _admin_env and _os.environ.get(_admin_warning_flag) != "1":
    import logging as _logging
    _logging.getLogger("config").warning(
        "⚠️  ADMIN_EMAILS env var non impostata — fallback a mattiadavolio90@gmail.com. "
        "In produzione configurare: ADMIN_EMAILS=email1,email2"
    )
    _os.environ[_admin_warning_flag] = "1"


# ============================================================
# LIMITI E COSTANTI APPLICAZIONE
# ============================================================

# Troncamento descrizioni nei log
TRUNCATE_DESC_LOG = 40
TRUNCATE_DESC_QUERY = 30
TRUNCATE_ERROR_DISPLAY = 150

# Limiti upload e batch
MAX_FILE_SIZE_P7M = 50_000_000  # 50 MB
MAX_FILES_PER_UPLOAD = 150       # Max file per singolo upload
MAX_UPLOAD_TOTAL_MB = 200        # Max dimensione totale upload (MB)
MAX_DESC_LENGTH_DB = 500

# Budget AI giornaliero per ristorante
MAX_AI_CALLS_PER_DAY = 1000      # Max classificazioni AI al giorno per ristorante
VISION_DAILY_LIMIT = 50          # Max chiamate Vision (PDF/JPG/PNG) al giorno per ristorante

# Memoria sessione AI
MEMORIA_SESSION_CAP = 500

# Delay UI Streamlit (secondi)
UI_DELAY_QUICK = 0.05
UI_DELAY_SHORT = 0.2
UI_DELAY_MEDIUM = 0.3
UI_DELAY_LONG = 0.5
BATCH_RATE_LIMIT_DELAY = 0.5

# Dizionario mesi italiani (usato in pivot mensili)
MESI_ITA = {
    1: 'GENNAIO', 2: 'FEBBRAIO', 3: 'MARZO', 4: 'APRILE',
    5: 'MAGGIO', 6: 'GIUGNO', 7: 'LUGLIO', 8: 'AGOSTO',
    9: 'SETTEMBRE', 10: 'OTTOBRE', 11: 'NOVEMBRE', 12: 'DICEMBRE'
}

# Limiti upload e database
MAX_RIGHE_GLOBALE = 100000       # Max righe per utente/ristorante
MAX_RIGHE_BATCH = 500            # Max righe per singolo batch upload
BATCH_FILE_SIZE = 20             # Max file per batch

# Limiti feature Analisi Personalizzata
MAX_CUSTOM_TAGS_TRIAL = 1        # Max tag in prova gratuita
MAX_CUSTOM_TAGS = 10             # Max tag per account attivo
MAX_PRODOTTI_PER_TAG = 200       # Max associazioni per singolo tag
ORPHAN_CHECK_DAYS = 90           # Finestra giorni per warning "potenzialmente orfano"
CUSTOM_TAG_SUGGESTION_LIMIT = 20  # Max suggerimenti automatici iniziali
CUSTOM_TAG_SEARCH_RESULT_LIMIT = 100  # Max risultati ricerca descrizioni in UI
CUSTOM_TAG_ALERT_SOGLIA_DEFAULT = 5.0  # Soglia alert % predefinita per trend tag
PRICE_ALERT_THRESHOLD_DEFAULT = 5.0    # Soglia alert % predefinita per notifiche variazione prezzi
CUSTOM_TAG_COLOR_DEFAULT = "#2563EB"   # Colore default tag
CUSTOM_TAG_UNITA_KG = {"KG", "GR"}     # Unita normalizzate riconducibili a KG
CUSTOM_TAG_UNITA_LT = {"LT", "ML", "CL"}  # Unita normalizzate riconducibili a LT

