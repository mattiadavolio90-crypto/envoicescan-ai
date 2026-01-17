"""
Costanti, categorie e regex precompilate per FCI_PROJECT.

Questo modulo contiene:
- Regex precompilate per parsing e normalizzazione
- Categorie Food & Beverage e Spese Generali
- Dizionario correzioni intelligente per classificazione
- Lista fornitori NO FOOD
- Colori per grafici Plotly

Tutte le regex sono precompilate all'avvio per ottimizzazione performance.
"""
import re


# ============================================================
# REGEX PRECOMPILATE (OTTIMIZZAZIONE PERFORMANCE)
# ============================================================
# Compilate una volta sola all'avvio, riutilizzate migliaia di volte

# Normalizzazione descrizioni
REGEX_UNITA_MISURA = [
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
    re.compile(r'\bN°\b', re.IGNORECASE),
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

REGEX_NUMERI_UNITA = re.compile(r'\b\d+[.,]?\d*\s*(?:KG|G|L|ML|PZ|%|EUR|€)?\b', re.IGNORECASE)

REGEX_SOSTITUZIONI = {
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
    "OLIO E CONDIMENTI", "SECCO", "VERDURE", "FRUTTA", "SALSE E CREME",
    "ACQUA", "BEVANDE", "CAFFE E THE", "BIRRE", "VINI",
    "VARIE BAR", "DISTILLATI", "AMARI/LIQUORI", "PASTICCERIA",
    "PRODOTTI DA FORNO", "SPEZIE E AROMI", "GELATI", "SURGELATI", "SHOP"
]


# ============================================
# CATEGORIE MATERIALI E CONSUMABILI (F&B!)
# ============================================
# IMPORTANTE: NO FOOD È CONSIDERATO F&B!
# Contiene materiali di consumo per il ristorante:
# - Tovaglioli, piatti/bicchieri usa e getta
# - Pellicole, contenitori asporto, buste
# - Detergenti per stoviglie, spugne
# Questi prodotti DEVONO apparire negli alert/sconti
CATEGORIE_MATERIALI = ["NO FOOD"]


# ============================================
# CATEGORIE SPESE OPERATIVE (NON F&B)
# ============================================
# IMPORTANTE: Queste sono le UNICHE 3 categorie NON considerate Food & Beverage
# TUTTO IL RESTO è F&B (incluso NO FOOD = materiali consumo ristorante!)
CATEGORIE_SPESE_OPERATIVE = [
    "SERVIZI E CONSULENZE",        # Es: Consulenze HACCP, Commercialista
    "UTENZE E LOCALI",              # Es: Bollette ENEL, Affitto locale
    "MANUTENZIONE E ATTREZZATURE"  # Es: Riparazione forno, Manutenzione cappa
]


# ============================================
# TUTTE LE CATEGORIE (per AI e retrocompatibilità)
# ============================================
# NOTA: Queste liste statiche sono mantenute per retrocompatibilità
# L'app usa carica_categorie_da_db() per dropdown e UI
TUTTE_LE_CATEGORIE = CATEGORIE_FOOD_BEVERAGE + CATEGORIE_MATERIALI + CATEGORIE_SPESE_OPERATIVE


# Retrocompatibilità con codice esistente
CATEGORIE_FOOD = CATEGORIE_FOOD_BEVERAGE + CATEGORIE_MATERIALI
CATEGORIE_SPESE_GENERALI = CATEGORIE_SPESE_OPERATIVE


# ============================================
# FORNITORI NO FOOD (utenze, telecom, tech)
# ============================================
# Lista unificata di fornitori che sono SEMPRE spese generali/utenze
# Usata per filtrare automaticamente fornitori non-food
FORNITORI_NO_FOOD_KEYWORDS = [
    'TIM', 'TELECOM', 'VODAFONE', 'WIND', 'ILIAD', 'FASTWEB',
    'ENEL', 'ENI', 'A2A', 'EDISON', 'GAS', 'LUCE', 'ENERGIA',
    'AMAZON', 'MEDIAWORLD', 'UNIEURO', 'LEROY MERLIN',
    'BANCA', 'ASSICURAZ', 'POSTALE', 'POSTE ITALIANE', 'GOOGLE'
]


# ============================================
# DIZIONARIO CORREZIONI INTELLIGENTE
# ============================================
# Mappa keyword → categoria per classificazione rapida
# Usato quando AI non è disponibile o per validazione
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
    "VONGOLE": "PESCE",
    "TROTA": "PESCE",
    "SPIGOLA": "PESCE",
    "MERLUZZO": "PESCE",
    "BACCALÀ": "PESCE",
    "SOGLIOLA": "PESCE",
    "PESCE SPADA": "PESCE",
    "ACCIUGHE": "PESCE",
    "ALICI": "PESCE",
    "SARDINE": "PESCE",
    
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
    "YOGURT": "LATTICINI",
    "EDAMER": "LATTICINI",
    "PIZZA JULIENNE": "LATTICINI",
    
    # ===== SALUMI =====
    "PROSCIUTTO": "SALUMI",
    "CRUDO": "SALUMI",
    "COTTO": "SALUMI",
    "SALAME": "SALUMI",
    "MORTADELLA": "SALUMI",
    "PANCETTA": "SALUMI",
    "SPECK": "SALUMI",
    "BRESAOLA": "SALUMI",
    "COPPA": "SALUMI",
    "LARDO": "SALUMI",
    "GUANCIALE": "SALUMI",
    # ✅ Richiesta: SALSICCIA e varianti → CARNE (non SALUMI)
    "SALSICCIA": "CARNE",
    "SALSICCE": "CARNE",
    "SALSICC": "CARNE",
    "SALSIC": "CARNE",
    "WURSTEL": "SALUMI",
    "WÜRSTEL": "SALUMI",
    
    # ===== UOVA =====
    "UOVA": "UOVA",
    "UOVO": "UOVA",
    
    # ===== VERDURE =====
    "CONTORNO": "VERDURE",
    "POMODORO": "VERDURE",
    "POMODORI": "VERDURE",
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
    "BASILICO": "VERDURE",
    "PREZZEMOLO": "VERDURE",
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
    "BRIOCHE": "PRODOTTI DA FORNO",
    "CROISSANT": "PRODOTTI DA FORNO",
    
    # ===== SECCO (PASTA, RISO, FARINE) =====
    "PASTA": "SECCO",
    "SPAGHETTI": "SECCO",
    "PENNE": "SECCO",
    "FUSILLI": "SECCO",
    "RIGATONI": "SECCO",
    "FARFALLE": "SECCO",
    "LINGUINE": "SECCO",
    "TAGLIATELLE": "SECCO",
    "LASAGNE": "SECCO",
    "RAVIOLI": "SECCO",
    "TORTELLINI": "SECCO",
    "TORTELLONI": "SECCO",
    "AGNOLOTTI": "SECCO",
    "CAPPELLETTI": "SECCO",
    "GNOCCHI": "SECCO",
    "CANNELLONI": "SECCO",
    "ORECCHIETTE": "SECCO",
    "TROFIE": "SECCO",
    "PACCHERI": "SECCO",
    "BUCATINI": "SECCO",
    "RISO": "SECCO",
    "FARINA": "SECCO",
    "ZUCCHERO": "SECCO",
    "ROUX": "SECCO",
    "CEREALI": "SECCO",
    "BISCOTTI": "SECCO",
    "FETTE BISCOTTATE": "SECCO",
    
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
    "RAGÙ": "SALSE E CREME",
    "SUGO": "SALSE E CREME",
    "BESCIAMELLA": "SALSE E CREME",
    "SALSA": "SALSE E CREME",
    
    # ===== CONSERVE (include scatolame, marmellate, sott'olio) =====
    # Scatolame
    "PELATI": "SCATOLAME E CONSERVE",
    "POMODORI PELATI": "SCATOLAME E CONSERVE",
    "LEGUMI": "SCATOLAME E CONSERVE",
    "FAGIOLI": "SCATOLAME E CONSERVE",
    "CECI": "SCATOLAME E CONSERVE",
    "LENTICCHIE": "SCATOLAME E CONSERVE",
    "TONNO SCATOLA": "SCATOLAME E CONSERVE",
    "TONNO": "SCATOLAME E CONSERVE",
    "MAIS": "SCATOLAME E CONSERVE",
    "PISELLI": "SCATOLAME E CONSERVE",
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
    "CAFFÈ": "CAFFE E THE",
    "CAFFE": "CAFFE E THE",
    "CAFFE'": "CAFFE E THE",
    "ESPRESSO": "CAFFE E THE",
    "CAPSULE": "CAFFE E THE",
    "CIALDE": "CAFFE E THE",
    "THE": "CAFFE E THE",
    "TÈ": "CAFFE E THE",
    "TISANA": "CAFFE E THE",
    "TISANE": "CAFFE E THE",
    "INFUSO": "CAFFE E THE",
    "DECAFFEINATO": "CAFFE E THE",
    "DECA": "CAFFE E THE",
    "DECAF": "CAFFE E THE",
    "CAMOMILLA": "CAFFE E THE",
    "CAMOMILLE": "CAFFE E THE",
    
    # ===== ACQUA =====
    "ACQUA": "ACQUA",
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
    "DOLCE": "PASTICCERIA",
    "CROSTATA": "PASTICCERIA",
    "TIRAMISÙ": "PASTICCERIA",
    "PANNA COTTA": "PASTICCERIA",
    "MOUSSE": "PASTICCERIA",
    "CHEESECAKE": "PASTICCERIA",
    "MILLEFOGLIE": "PASTICCERIA",
    "CANNOLI": "PASTICCERIA",
    "PROFITEROLES": "PASTICCERIA",
    "BIGNÈ": "PASTICCERIA",
    "ARAGOSTELLE": "PASTICCERIA",  # Dolci a forma di aragosta (con pistacchio/cioccolato)
    "TARTUFI": "PASTICCERIA",  # Default per dolci (se è tartufo vero, viene sovrascritto da admin)
    
    # ===== GELATI =====
    "GELATO": "GELATI",
    "GELATI": "GELATI",
    "SORBETTO": "GELATI",
    "COPPA GELATO": "GELATI",
    "CONO": "GELATI",
    "SEMIFREDDO": "GELATI",
    
    # ===== SURGELATI =====
    "SURGELATO": "SURGELATI",
    "SURGELATI": "SURGELATI",
    "CONGELATO": "SURGELATI",
    "FROZEN": "SURGELATI",
    
    # ===== SHOP (prodotti di compravendita senza produzione) =====
    "CICCHE": "SHOP",
    "SIGARETTE": "SHOP",
    "TABACCHI": "SHOP",
    "CARAMELLE": "SHOP",
    "GOMME": "SHOP",
    "GOMMA": "SHOP",
    "CHEWING GUM": "SHOP",
    "PATATINE": "SHOP",
    "CHIPS": "SHOP",
    "SNACK": "SHOP",
    "GOLIA": "SHOP",
    "MENTINE": "SHOP",
    "CARAMELLA": "SHOP",
    "LECCA LECCA": "SHOP",
    "LOLLIPOP": "SHOP",
    "BARRETTE": "SHOP",
    "BARRETTA": "SHOP",
    "CIOCCOLATINI": "SHOP",
    "OVETTI": "SHOP",
    "KINDER": "SHOP",
    "MARS": "SHOP",
    "SNICKERS": "SHOP",
    "TWIX": "SHOP",
    "BOUNTY": "SHOP",
    "CIOCCOLATO CONFEZIONATO": "SHOP",
    
    # ===== VARIE BAR (solo prodotti commestibili per servizio bar) =====
    "GHIACCIO": "VARIE BAR",
    "ZUCCHERO BAR": "VARIE BAR",
    
    # ===== MATERIALI CONSUMO -> NO FOOD =====
    "BUSTINE": "NO FOOD",
    "PALETTE": "NO FOOD",
    "CANNUCCE": "NO FOOD",
    "TOVAGLIETTE": "NO FOOD",
    "VASCHETTA": "NO FOOD",
    "VASCHETTE": "NO FOOD",
    "COPPETTA": "NO FOOD",
    "COPPETTE": "NO FOOD",
    "COPPA GELATO": "GELATI",  # Eccezione: se contiene GELATO è il prodotto
    "TOVAGLIOLO": "NO FOOD",
    "TOVAGLIOLI": "NO FOOD",
    "TOVAGLIOLIN": "NO FOOD",
    "PIATTI": "NO FOOD",
    "PIATTO": "NO FOOD",
    "PIATTINO": "NO FOOD",
    "BICCHIERI": "NO FOOD",
    "BICCHIERE": "NO FOOD",
    "BICCHIERINO": "NO FOOD",
    "CALICE": "NO FOOD",
    "POSATE": "NO FOOD",
    "FORCHETTA": "NO FOOD",
    "FORCHETTE": "NO FOOD",
    "CUCCHIAIO": "NO FOOD",
    "CUCCHIAI": "NO FOOD",
    "CUCCHIAINO": "NO FOOD",
    "COLTELLO PLASTICA": "NO FOOD",
    "POSATE LEGNO": "NO FOOD",
    "POSATE PLASTICA": "NO FOOD",
    "CANNUCCIA": "NO FOOD",
    "SAC A POCHE": "NO FOOD",
    "CARTA": "NO FOOD",
    "CARTA FORNO": "NO FOOD",
    "CARTA ASSORBENTE": "NO FOOD",
    "ROTOLO": "NO FOOD",
    "ROTOLI CUCINA": "NO FOOD",
    "SCOTTEX": "NO FOOD",
    "SACCHETTI": "NO FOOD",
    "SACCHETTO": "NO FOOD",
    "SHOPPER": "NO FOOD",
    "BUSTE": "NO FOOD",
    "BUSTA": "NO FOOD",
    "CONTENITORI": "NO FOOD",
    "CONTENITORE": "NO FOOD",
    "ASPORTO": "NO FOOD",
    "TAKE AWAY": "NO FOOD",
    "COPERCHIO": "NO FOOD",
    "COPERCHI": "NO FOOD",
    "PELLICOLA": "NO FOOD",
    "FILM": "NO FOOD",
    "ALLUMINIO": "NO FOOD",
    "STAGNOLA": "NO FOOD",
    "DETERGENTE": "NO FOOD",
    "DETERSIVO": "NO FOOD",
    "SGRASSATORE": "NO FOOD",
    "SAPONE": "NO FOOD",
    "DISINFETTANTE": "NO FOOD",
    "IGIENIZZANTE": "NO FOOD",
    "GEL MANI": "NO FOOD",
    "GUANTI": "NO FOOD",
    "GUANTO": "NO FOOD",
    "SPUGNA": "NO FOOD",
    "SPUGNE": "NO FOOD",
    "STROFINACCIO": "NO FOOD",
    "STROFINACCI": "NO FOOD",
    "PANNO": "NO FOOD",
    "PANNI": "NO FOOD",
    "STRACCIO": "NO FOOD",
    "SCOPA": "NO FOOD",
    "MOCIO": "NO FOOD",
    "SPAZZOLONE": "NO FOOD",
    "TOVAGLIA": "NO FOOD",
    "TOVAGLIE": "NO FOOD",
    "TAZZA": "NO FOOD",
    "TAZZINA": "NO FOOD",
    "POMPETTA": "NO FOOD",
    "DOSATORE": "NO FOOD",
    "TAPPO": "NO FOOD",
    "TAPPI": "NO FOOD",
    "SCOTCH": "NO FOOD",
    "NASTRO ADESIVO": "NO FOOD",
    "ETICHETTE": "NO FOOD",
    "ETICHETTA": "NO FOOD",
    "ETICHETTE ADESIVE": "NO FOOD",
    "SPAGO": "NO FOOD",
    "ELASTICI": "NO FOOD",
    "ELASTICO": "NO FOOD",
    "PENNARELLO": "NO FOOD",
    "PENNARELLI": "NO FOOD",
    "MARKER": "NO FOOD",
    "PACKAGING": "NO FOOD",
    "TAZZE": "NO FOOD",
    "PIATTINI": "NO FOOD",
    "COPERTI": "NO FOOD",
    "STOVIGLIE": "NO FOOD",
    
    # ===== SERVIZI E CONSULENZE =====
    "GOOGLE WORKSPACE": "SERVIZI E CONSULENZE",
    "WORKSPACE": "SERVIZI E CONSULENZE",
    "CANONE": "SERVIZI E CONSULENZE",
    "CONTRIBUTO ATTIVAZIONE": "SERVIZI E CONSULENZE",
    "DIRITTI": "SERVIZI E CONSULENZE",
    "RICAMO": "SERVIZI E CONSULENZE",
    "CONSULENZA": "SERVIZI E CONSULENZE",
    "COMMERCIALISTA": "SERVIZI E CONSULENZE",
    "CONTABILITÀ": "SERVIZI E CONSULENZE",
    "CONTABILE": "SERVIZI E CONSULENZE",
    "CONSULENTE FISCALE": "SERVIZI E CONSULENZE",
    "FISCALE": "SERVIZI E CONSULENZE",
    "FATTURAZIONE ELETTRONICA": "SERVIZI E CONSULENZE",
    "PUBBLICITÀ": "SERVIZI E CONSULENZE",
    "MARKETING": "SERVIZI E CONSULENZE",
    "SOCIAL MEDIA": "SERVIZI E CONSULENZE",
    "PUBBLICITA": "SERVIZI E CONSULENZE",
    "POS": "SERVIZI E CONSULENZE",
    "COMMISSIONI": "SERVIZI E CONSULENZE",
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
    
    # ===== UTENZE E LOCALI =====
    "ENERGIA ELETTRICA": "UTENZE E LOCALI",
    "RETE ELETTRICA": "UTENZE E LOCALI",
    "ONERI DI SISTEMA": "UTENZE E LOCALI",
    "SPESA PER LA VENDITA": "UTENZE E LOCALI",
    "SPESA PER LA TARIFFA": "UTENZE E LOCALI",
    "LUCE": "UTENZE E LOCALI",
    "ELETTRICITÀ": "UTENZE E LOCALI",
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
    "MACCHINA CAFFÈ": "MANUTENZIONE E ATTREZZATURE",
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

    
    # ===== FIX DIZIONARIO CONSERVATIVO - KEYWORD SPECIFICHE =====
    "BISCOTTINI": "PASTICCERIA",
    "CANDEGGINA": "NO FOOD",
    "CROSTATE": "PASTICCERIA",
    "CROSTATINE": "PASTICCERIA",
    "DOLCI NATALIZI": "PASTICCERIA",
    "FACCINE": "PASTICCERIA",
    "MIX NATALE": "PASTICCERIA",
    "MOUSSE MANI": "NO FOOD",
    "PASSATA POMOD": "SALSE E CREME",
    "PASSATA POMODORO": "SALSE E CREME",
    "SALAME CIOCCOLATO": "PASTICCERIA",
    "SALAME DI CIOCCOLATO": "PASTICCERIA",

# ===== KEYWORDS DAL FIX REPORT ERRORI =====
    "ARAGONOSTINE": "PASTICCERIA",
    "ARAGOSTINE": "PASTICCERIA",
    "BEVANDA DI SOJA": "BEVANDE",
    "BEVANDA SOJA": "BEVANDE",
    "BOLLO SPESA": "SERVIZI E CONSULENZE",
    "BRIE": "LATTICINI",
    "BRILL": "NO FOOD",
    "CANES": "PASTICCERIA",
    "CANESTRELLI": "PASTICCERIA",
    "CANESTRELLO": "PASTICCERIA",
    "CANNOLO": "PASTICCERIA",
    "CANNONCINI": "PASTICCERIA",
    "CANNONCINO": "PASTICCERIA",
    "CANNOLI SFOGLIA": "PASTICCERIA",
    "CONCHIGLIA PANNA": "PASTICCERIA",
    "ARAGOSTINE": "PASTICCERIA",
    "CAPRA": "LATTICINI",
    "CAPRINO": "LATTICINI",
    "CAPRINO VACCINO": "LATTICINI",
    "CREMA GIANDUIA": "PASTICCERIA",
    "CREMA GIANDUJA": "PASTICCERIA",
    "EDAMAME": "VERDURE",
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
    "LAVASTOV": "NO FOOD",
    "MISTER X": "NO FOOD",
    "TAZZA": "NO FOOD",
    "GREMBIULE": "NO FOOD",
    "SALE PASTIGLIE": "NO FOOD",
    "MISTO FROLLA": "PASTICCERIA",
    "NOCE BOV": "CARNE",
    "NOCE BOVINO": "CARNE",
    "OCCHI BUE": "PASTICCERIA",
    "OCCHI DI BUE": "PASTICCERIA",
    "PARMA": "SALUMI",
    "PASSATA": "CONSERVE",
    "PASSATA POMOD": "CONSERVE",
    "PASSATA POMODORO": "CONSERVE",
    "PANNA SPRAY": "VARIE BAR",
    "ZUCCHERO BUSTINE": "VARIE BAR",
    "ZUCCHERO BAR": "VARIE BAR",
    "PAIN AU CHOCOLAT": "PRODOTTI DA FORNO",
    "EDAMINO": "LATTICINI",
    "RIBOLLA": "VINI",
    "IGT": "VINI",
    "CONGUAGLIO": "SERVIZI E CONSULENZE",
    "CONSUNTIVO": "SERVIZI E CONSULENZE",
    "PIADINA": "PRODOTTI DA FORNO",
    "PIADINE": "PRODOTTI DA FORNO",
    "PREGISAN": "NO FOOD",
    "PREMI": "SERVIZI E CONSULENZE",
    "RIF SAN PREGISAN": "NO FOOD",
    "SAVOIARDI": "PASTICCERIA",
    "SAVOIARDO": "PASTICCERIA",
    "SICILIANI CANNOLO": "PASTICCERIA",
    "SICILIANO CANNOLO": "PASTICCERIA",
    "SOIA": "BEVANDE",
    "SOJA": "BEVANDE",
    "SPESE DI BOLLO": "SERVIZI E CONSULENZE",
    "STRUDEL": "PASTICCERIA",

}
