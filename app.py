import extra_streamlit_components as stx
import tempfile
import shutil
import streamlit as st
import pandas as pd
import xmltodict
import os
import json
from openai import OpenAI
import plotly.express as px
import plotly.graph_objects as go
import io
import time
import re
import base64
import fitz  # PyMuPDF - conversione PDF senza dipendenze esterne
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError


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
# FUNZIONI NORMALIZZAZIONE DESCRIZIONI (MEMORIA GLOBALE)
# ============================================================

def normalizza_descrizione(descrizione):
    """
    Normalizza descrizione per matching intelligente in memoria globale.
    
    Operazioni:
    1. Rimuove unità di misura (KG, L, ML, PZ, ecc.)
    2. Rimuove numeri (pesi, quantità, prezzi)
    3. Normalizza abbreviazioni comuni
    4. Rimuove punteggiatura superflua
    5. Uniforma spazi
    
    Esempi:
    - "POLLO INTERO KG 2.5" → "POLLO INTERO"
    - "OLIO EVO 1L BOT." → "OLIO EVO BOTTIGLIA"
    - "PASTA PENNE 500G" → "PASTA PENNE"
    
    Args:
        descrizione: stringa descrizione originale
    
    Returns:
        str: descrizione normalizzata
    """
    if not descrizione:
        return ""
    
    desc = descrizione.strip().upper()
    
    # Step 1: Rimuovi unità di misura comuni (regex precompilate)
    for regex_unita in REGEX_UNITA_MISURA:
        desc = regex_unita.sub('', desc)
    
    # Step 2: Rimuovi numeri (quantità, pesi, misure) - regex precompilata
    # Mantieni solo numeri che fanno parte del nome (es: "COCA COLA 330")
    desc = REGEX_NUMERI_UNITA.sub('', desc)
    
    # Step 3: Normalizza abbreviazioni comuni (regex precompilate)
    for regex_pattern, replacement in REGEX_SOSTITUZIONI.items():
        desc = regex_pattern.sub(replacement, desc)
    
    # Step 4: Rimuovi punteggiatura superflua (regex precompilata)
    desc = REGEX_PUNTEGGIATURA.sub(' ', desc)
    
    # Step 5: Rimuovi articoli e preposizioni comuni (regex precompilate)
    for regex_articolo in REGEX_ARTICOLI:
        desc = regex_articolo.sub(' ', desc)
    
    # Step 6: Normalizza spazi multipli
    desc = ' '.join(desc.split())
    
    # Step 7: Rimuovi spazi iniziali/finali
    desc = desc.strip()
    
    return desc


def get_descrizione_normalizzata_e_originale(descrizione):
    """
    Restituisce sia descrizione normalizzata che originale.
    
    Returns:
        tuple: (descrizione_normalizzata, descrizione_originale)
    """
    desc_original = descrizione.strip().upper()
    desc_normalized = normalizza_descrizione(descrizione)
    
    return desc_normalized, desc_original


def test_normalizzazione():
    """Testa funzione normalizzazione con casi comuni"""
    test_cases = [
        "POLLO INTERO KG 2.5",
        "POLLO INT. KG",
        "POLLO INTERO",
        "OLIO EVO 1L BOT.",
        "OLIO EVO BOTTIGLIA 1 LITRO",
        "PASTA PENNE 500G CONF.",
        "PASTA PENNE CONFEZIONE",
        "COCA COLA 330 ML LAT.",
        "COCA COLA LATTINA"
    ]
    
    print("\n=== TEST NORMALIZZAZIONE ===")
    for test in test_cases:
        normalized = normalizza_descrizione(test)
        print(f"{test:<40} → {normalized}")
    print("=" * 70)


def salva_correzione_in_memoria_globale(descrizione, vecchia_categoria, nuova_categoria, user_email):
    """
    Salva correzione utente in memoria globale.
    Quando un utente corregge manualmente una categoria, aggiorna memoria
    così tutti i futuri clienti beneficiano della correzione.
    
    Args:
        descrizione: descrizione prodotto
        vecchia_categoria: categoria assegnata da AI (sbagliata)
        nuova_categoria: categoria corretta dall'utente
        user_email: email utente che ha corretto
    """
    try:
        from datetime import datetime
        
        # Normalizza descrizione
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        # Check se esiste già in memoria
        existing = supabase.table('prodotti_master')\
            .select('id, volte_visto')\
            .eq('descrizione', desc_normalized)\
            .limit(1)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            # AGGIORNA esistente con categoria corretta
            record = existing.data[0]
            
            supabase.table('prodotti_master').update({
                'categoria': nuova_categoria,
                'classificato_da': f'Utente ({user_email})',
                'confidence': 'altissima',
                'ultima_modifica': datetime.now().isoformat()
            }).eq('id', record['id']).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()
            
            logger.info(f"📚 CORREZIONE UTENTE aggiornata in memoria: '{desc_normalized}' {vecchia_categoria} → {nuova_categoria} (by {user_email})")
        
        else:
            # INSERISCI nuovo record con categoria corretta
            supabase.table('prodotti_master').insert({
                'descrizione': desc_normalized,
                'categoria': nuova_categoria,
                'classificato_da': f'Utente ({user_email})',
                'confidence': 'altissima',
                'volte_visto': 1,
                'created_at': datetime.now().isoformat(),
                'ultima_modifica': datetime.now().isoformat()
            }).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()
            
            logger.info(f"📚 CORREZIONE UTENTE salvata in memoria: '{desc_normalized}' → {nuova_categoria} (by {user_email})")
        
        return True
    
    except Exception as e:
        logger.error(f"Errore salvataggio correzione in memoria: {e}")
        return False


# ============================================================
# 🏪 CHECK FORNITORI AI - VERSIONE 3.2 FINAL COMPLETA
# ============================================================
# CHANGELOG V3.2 FINAL:
# ✅ BUGFIX CRITICO: safe_get con keep_list per DettaglioLinee
# ✅ Ripristinato (F&B) nelle etichette Tab
# ✅ Rimossi KPI ridondanti Tab Spese Generali
# ✅ Grafici identici originale (no etichette sotto)
# ✅ Ottimizzazioni Gemini complete
# ✅ CODICE COMPLETO 1800+ RIGHE
# ✅ PDF con PyMuPDF (no Poppler richiesto)
# ============================================================



COLORI_PLOTLY = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"
]


# ============================================
# CATEGORIE FOOD & BEVERAGE (prodotti vendibili)
# ============================================
CATEGORIE_FOOD_BEVERAGE = [
    "CARNE", "PESCE", "LATTICINI", "SALUMI", "UOVA", "SCATOLAME",
    "OLIO E CONDIMENTI", "SECCO", "VERDURE", "FRUTTA", "SALSE E CREME",
    "ACQUA", "BEVANDE", "CAFFÈ", "BIRRE", "VINI",
    "VARIE BAR", "DISTILLATI", "AMARI/LIQUORI", "PASTICCERIA",
    "PRODOTTI DA FORNO", "SPEZIE E AROMI", "GELATI", "SURGELATI", "CONSERVE"
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
# DIZIONARIO CORREZIONI INTELLIGENTE
# ============================================
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
    "BURRO": "LATTICINI",
    
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
    "AGLIO": "VERDURE",
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
    
    # ===== FRUTTA =====
    "PASSATA ALBICOCCA": "FRUTTA",
    "MELA": "FRUTTA",
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
    "ALBICOCCA": "FRUTTA",
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
    "PIZZA": "PRODOTTI DA FORNO",
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
    "RISO": "SECCO",
    "FARINA": "SECCO",
    "ZUCCHERO": "SECCO",
    "SALE": "SECCO",
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
    "PAPRIKA": "SPEZIE E AROMI",
    "ZAFFERANO": "SPEZIE E AROMI",
    "CANNELLA": "SPEZIE E AROMI",
    "NOCE MOSCATA": "SPEZIE E AROMI",
    "VANIGLIA": "SPEZIE E AROMI",
    
    # ===== SALSE E CREME =====
    "CREMA PISTACCHIO": "SALSE E CREME",
    "CREMA NOCCIOLA": "SALSE E CREME",
    "NUTELLA": "SALSE E CREME",
    "PASSATA": "SALSE E CREME",
    "PESTO": "SALSE E CREME",
    "KETCHUP": "SALSE E CREME",
    "MAIONESE": "SALSE E CREME",
    "SENAPE": "SALSE E CREME",
    "RAGÙ": "SALSE E CREME",
    "SUGO": "SALSE E CREME",
    "BESCIAMELLA": "SALSE E CREME",
    "SALSA": "SALSE E CREME",
    
    # ===== SCATOLAME =====
    "PELATI": "SCATOLAME",
    "POMODORI PELATI": "SCATOLAME",
    "LEGUMI": "SCATOLAME",
    "FAGIOLI": "SCATOLAME",
    "CECI": "SCATOLAME",
    "LENTICCHIE": "SCATOLAME",
    "TONNO SCATOLA": "SCATOLAME",
    "TONNO": "SCATOLAME",
    "MAIS": "SCATOLAME",
    "PISELLI": "SCATOLAME",
    
    # ===== CAFFÈ =====
    "CAFFÈ": "CAFFÈ",
    "CAFFE": "CAFFÈ",
    "ESPRESSO": "CAFFÈ",
    "CAPSULE": "CAFFÈ",
    "CIALDE": "CAFFÈ",
    "THE": "CAFFÈ",
    "TÈ": "CAFFÈ",
    "TISANA": "CAFFÈ",
    "TISANE": "CAFFÈ",
    "INFUSO": "CAFFÈ",
    
    # ===== ACQUA =====
    "ACQUA": "ACQUA",
    "NATURALE": "ACQUA",
    "FRIZZANTE": "ACQUA",
    "EFFERVESCENTE": "ACQUA",
    
    # ===== BEVANDE =====
    "COCA": "BEVANDE",
    "COLA": "BEVANDE",
    "ARANCIATA": "BEVANDE",
    "LIMONATA": "BEVANDE",
    "THE FREDDO": "BEVANDE",
    "SUCCO": "BEVANDE",
    "SPREMUTA": "BEVANDE",
    "BIBITA": "BEVANDE",
    "CHINOTTO": "BEVANDE",
    "GASSOSA": "BEVANDE",
    
    # ===== VINI =====
    "VINO": "VINI",
    "ROSSO": "VINI",
    "BIANCO": "VINI",
    "ROSATO": "VINI",
    "PROSECCO": "VINI",
    "SPUMANTE": "VINI",
    "CHAMPAGNE": "VINI",
    "LAMBRUSCO": "VINI",
    "CHIANTI": "VINI",
    "BAROLO": "VINI",
    "BARBARESCO": "VINI",
    
    # ===== BIRRE =====
    "BIRRA": "BIRRE",
    "LAGER": "BIRRE",
    "ALE": "BIRRE",
    "WEISS": "BIRRE",
    "STOUT": "BIRRE",
    
    # ===== DISTILLATI =====
    "VODKA": "DISTILLATI",
    "GIN": "DISTILLATI",
    "RUM": "DISTILLATI",
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
    
    # ===== CONSERVE =====
    "CONSERVA": "CONSERVE",
    "CONSERVE": "CONSERVE",
    "MARMELLATA": "CONSERVE",
    "CONFETTURA": "CONSERVE",
    "COMPOSTA": "CONSERVE",
    "GELATINA": "CONSERVE",
    "SOTT'OLIO": "CONSERVE",
    "SOTTACETO": "CONSERVE",
    "SOTTACETI": "CONSERVE",
    "OLIVE": "CONSERVE",
    "CAPPERI": "CONSERVE",
    "CETRIOLINI": "CONSERVE",
    "GIARDINIERA": "CONSERVE",
    
    # ===== VARIE BAR =====
    "GHIACCIO": "VARIE BAR",
    "ZUCCHERO BAR": "VARIE BAR",
    "BUSTINE": "VARIE BAR",
    "PALETTE": "VARIE BAR",
    "CANNUCCE": "VARIE BAR",
    "TOVAGLIETTE": "VARIE BAR",
    
    # ===== MATERIALI CONSUMO -> NO FOOD =====
    "VASCHETTA": "NO FOOD",
    "VASCHETTE": "NO FOOD",
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
    "CANNUCCE": "NO FOOD",
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
    "TAZZE": "NO FOOD",
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
}


# ============================================
# FUNZIONE CORREZIONE INTELLIGENTE
# ============================================
def applica_correzioni_dizionario(descrizione, categoria_ai):
    """Applica correzioni basate su keyword nel dizionario"""
    if not descrizione or not isinstance(descrizione, str):
        return categoria_ai
    
    desc_upper = descrizione.upper()
    
    # Ordina keyword per lunghezza decrescente (più lunghe prima)
    # Così 'PASSATA ALBICOCCA' matcha prima di 'PASSATA'
    keyword_ordinate = sorted(
        DIZIONARIO_CORREZIONI.items(), 
        key=lambda x: len(x[0]), 
        reverse=True
    )
    
    for keyword, cat_corretta in keyword_ordinate:
        if keyword in desc_upper:
            return cat_corretta
    
    return categoria_ai



# ============================================
# CLASSIFICAZIONE DICITURE E SISTEMA MEMORIA
# ============================================

def is_dicitura_sicura(descrizione, prezzo, quantita):
    """
    Identifica diciture con ALTA confidenza (approccio conservativo).
    Ritorna True SOLO se CERTISSIMI che è dicitura, non prodotto.
    
    Args:
        descrizione: testo descrizione riga
        prezzo: prezzo_unitario
        quantita: quantità
    
    Returns:
        bool: True se dicitura certa, False altrimenti
    """
    if not descrizione:
        return False
    
    desc_upper = descrizione.upper().strip()
    
    # Keyword ad ALTISSIMA confidenza (zero ambiguità)
    KEYWORD_CERTE = [
        # Riferimenti documenti
        "DATI N.", "DATI NUMERO", "NUMERO BOLL", "BOLL N.", "BOLLA N.",
        "DDT N.", "DDT NR.", "DDT DEL", "DDT -", "DOCUMENTO N.", "FATTURA N.",
        "RIFERIMENTO:", "RIF.:", "RIF N.", "RIF.", "VEDI ALLEGATO",
        "COME DA ACCORDI", "SECONDO ACCORDI", "VS ORDINE", "VOSTRO ORDINE",
        "NS ORDINE", "NOSTRO ORDINE", "ORDINE DEL", "ORDINE CL.", "ORDINE NUM.",
        "CONSEGNA DEL", "BOLLA DI CONSEGNA", "DOCUMENTO DI TRASPORTO",
        "DEST.:", "DESTINAZIONE:", "DESTINATARIO:",
        
        # Trasporto/spedizione
        "TRASPORTO", "SPEDIZIONE", "CORRIERE",
        "TRASPORTO GRATUITO", "SPEDIZIONE GRATUITA", "IMBALLO GRATUITO",
        "TRASPORTO ESENTE", "SPESE TRASPORTO", "SPESE SPEDIZIONE",
        "SPESE CORRIERE", "PORTO FRANCO", "FRANCO DESTINO",
        "COSTO TRASPORTO", "COSTO SPEDIZIONE",
        
        # Contributi
        "CONTRIBUTO CONAI", "CONAI", "CONTRIBUTO AMBIENTALE",
        "RAEE", "CONTRIBUTO RAEE", "ECO-CONTRIBUTO",
        
        # Imballi
        "IMBALLO", "IMBALLAGGIO", "PALLET", "BANCALE",
        "COSTO IMBALLO", "SPESE IMBALLO",
        
        # Sconti/abbuoni
        "SCONTO QUANTITÀ", "SCONTO VOLUME", "ABBUONO",
        "ARROTONDAMENTO", "SUPPLEMENTO", "MAGGIORAZIONE",
        
        # Note generiche
        "NOTA:", "AVVISO:", "COMUNICAZIONE:", "ATTENZIONE:",
        "VEDI NOTA", "COME DA PREVENTIVO", "SECONDO PREVENTIVO"
    ]
    
    # Check 1: Contiene keyword certa?
    if any(kw in desc_upper for kw in KEYWORD_CERTE):
        logger.info(f"✓ Dicitura identificata (keyword forte): {descrizione}")
        return True
    
    # Check 2: Solo numeri/simboli + molto corta?
    if len(descrizione) < 15 and not REGEX_LETTERE_MINIME.search(descrizione):
        logger.info(f"✓ Dicitura identificata (solo simboli): {descrizione}")
        return True
    
    # Check 3: Pattern "X DEL GG-MM-AAAA" (es: "BOLL DEL 12-12-2025")
    if REGEX_PATTERN_BOLLA.match(desc_upper):
        logger.info(f"✓ Dicitura identificata (pattern data): {descrizione}")
        return True
    
    # Check 4: Solo "DDT" o "TRASPORTO" da soli
    if desc_upper in ["DDT", "TRASPORTO", "SPEDIZIONE", "CORRIERE", "BOLLA", "IMBALLO", "RIF", "RIF.", "DEST", "DEST."]:
        logger.info(f"✓ Dicitura identificata (parola singola): {descrizione}")
        return True
    
    # IN TUTTI GLI ALTRI CASI → False (mantieni come prodotto)
    return False


# ============================================================
# CACHE IN-MEMORY PER ELIMINARE N+1 QUERY
# ============================================================

# Cache globale in-memory (condivisa tra tutti i thread della stessa sessione)
_memoria_cache = {
    'prodotti_utente': {},      # {user_id: {descrizione: categoria}}
    'prodotti_master': {},      # {descrizione: categoria}
    'classificazioni_manuali': {},  # {descrizione: {categoria, is_dicitura}}
    'version': 0,               # Incrementato ad ogni invalidazione
    'loaded': False
}


def carica_memoria_completa(user_id):
    """
    Carica TUTTE le memorie in una volta sola (1 query per tabella invece di N query).
    Elimina completamente il problema N+1 query.
    
    Args:
        user_id: UUID utente corrente
    
    Returns:
        dict: Cache completa con tutte le memorie
    """
    global _memoria_cache
    
    # Se già caricata, ritorna cache esistente
    if _memoria_cache['loaded']:
        return _memoria_cache
    
    try:
        # Query 1: Carica TUTTA la memoria locale utente (1 query sola)
        result_locale = supabase.table('prodotti_utente')\
            .select('descrizione, categoria')\
            .eq('user_id', user_id)\
            .execute()
        
        if result_locale.data:
            _memoria_cache['prodotti_utente'][user_id] = {
                row['descrizione']: row['categoria'] 
                for row in result_locale.data
            }
            logger.info(f"📦 Cache LOCALE caricata: {len(result_locale.data)} prodotti")
        
        # Query 2: Carica TUTTA la memoria globale (1 query sola)
        result_globale = supabase.table('prodotti_master')\
            .select('descrizione, categoria')\
            .execute()
        
        if result_globale.data:
            _memoria_cache['prodotti_master'] = {
                row['descrizione']: row['categoria'] 
                for row in result_globale.data
            }
            logger.info(f"📦 Cache GLOBALE caricata: {len(result_globale.data)} prodotti")
        
        # Query 3: Carica TUTTE le classificazioni manuali admin (1 query sola)
        result_manuali = supabase.table('classificazioni_manuali')\
            .select('descrizione, categoria_corretta, is_dicitura')\
            .execute()
        
        if result_manuali.data:
            _memoria_cache['classificazioni_manuali'] = {
                row['descrizione']: {
                    'categoria': row['categoria_corretta'],
                    'is_dicitura': row.get('is_dicitura', False)
                }
                for row in result_manuali.data
            }
            logger.info(f"📦 Cache MANUALI caricata: {len(result_manuali.data)} classificazioni")
        
        _memoria_cache['loaded'] = True
        _memoria_cache['version'] += 1
        
        logger.info(f"✅ Cache completa caricata (v{_memoria_cache['version']})")
        return _memoria_cache
        
    except Exception as e:
        logger.error(f"Errore caricamento cache completa: {e}")
        return _memoria_cache


def invalida_cache_memoria():
    """
    Invalida la cache in-memory forzando ricaricamento al prossimo accesso.
    Da chiamare dopo INSERT/UPDATE/DELETE su tabelle memoria.
    """
    global _memoria_cache
    _memoria_cache['loaded'] = False
    _memoria_cache['prodotti_utente'] = {}
    _memoria_cache['prodotti_master'] = {}
    _memoria_cache['classificazioni_manuali'] = {}
    logger.info("🔄 Cache memoria invalidata")


def ottieni_categoria_prodotto(descrizione, user_id):
    """
    Ottiene categoria prodotto con priorità IBRIDA usando CACHE IN-MEMORY.
    ELIMINA N+1 QUERY: usa cache invece di query ripetute.
    
    1. Memoria LOCALE utente (massima priorità) - personalizzazioni cliente
    2. Memoria GLOBALE (fallback) - condivisa tra tutti i clienti
    3. "Da Classificare" (se non trovato in nessuna memoria)
    
    Args:
        descrizione: descrizione prodotto
        user_id: UUID utente
    
    Returns:
        str: categoria trovata
    """
    global _memoria_cache
    
    try:
        # Carica cache se non già caricata (solo 1 volta per sessione)
        if not _memoria_cache['loaded']:
            carica_memoria_completa(user_id)
        
        # 1️⃣ Check memoria LOCALE utente (da cache, 0 query!)
        if user_id in _memoria_cache['prodotti_utente']:
            locale_dict = _memoria_cache['prodotti_utente'][user_id]
            if descrizione in locale_dict:
                categoria = locale_dict[descrizione]
                logger.debug(f"🔵 LOCALE (cache): '{descrizione[:40]}...' → {categoria}")
            categoria = _memoria_cache['prodotti_master'][descrizione]
            logger.debug(f"🟢 GLOBALE (cache): '{descrizione[:40]}...' → {categoria}")
            return categoria
        
        # 3️⃣ Fallback
        logger.debug(f"⚪ NUOVO: '{descrizione[:40]}...' → Da Classificare")
        return "Da Classificare"
        
    except Exception as e:
        logger.warning(f"Errore ottieni_categoria (cache) per '{descrizione[:40]}...': {e}")
        return "Da Classificare"


def categorizza_con_memoria(descrizione, prezzo, quantita, user_id=None):
    """
    Categorizza usando memoria GLOBALE multi-livello con CACHE IN-MEMORY.
    ELIMINA N+1 QUERY: usa cache invece di query ripetute.
    
    PRIORITÀ CORRETTA:
    1. Memoria correzioni admin (classificazioni_manuali) - PRIORITÀ ASSOLUTA
    2. Memoria LOCALE utente (prodotti_utente) - personalizzazioni cliente
    3. Memoria GLOBALE prodotti (prodotti_master) - condivisa tra tutti
    4. Check dicitura (se prezzo = 0)
    5. Dizionario keyword - FALLBACK FINALE
    
    Args:
        descrizione: testo descrizione
        prezzo: prezzo_unitario
        quantita: quantità
        user_id: ID utente (per log)
    
    Returns:
        str: categoria finale
    """
    global _memoria_cache
    
    try:
        # Carica cache se non già caricata
        if not _memoria_cache['loaded']:
            carica_memoria_completa(user_id)
        
        # LIVELLO 1: Check memoria admin (da cache, 0 query!)
        desc_stripped = descrizione.strip()
        if desc_stripped in _memoria_cache['classificazioni_manuali']:
            record = _memoria_cache['classificazioni_manuali'][desc_stripped]
            if record.get('is_dicitura'):
                logger.info(f"📋 Memoria Admin (cache): '{descrizione}' → DICITURA (validata admin)")
                return "📝 NOTE E DICITURE"
            else:
                logger.info(f"📋 Memoria Admin (cache): '{descrizione}' → {record['categoria']} (validata admin)")
                return record['categoria']
    
    except Exception as e:
        logger.warning(f"Errore check memoria admin (cache): {e}")
    
    # LIVELLO 2: Check memoria LOCALE utente (personalizzazioni cliente - priorità alta)
    try:
        if user_id and user_id in _memoria_cache['prodotti_utente']:
            locale_dict = _memoria_cache['prodotti_utente'][user_id]
            if descrizione in locale_dict:
                categoria = locale_dict[descrizione]
                logger.info(f"🔵 LOCALE UTENTE (cache): '{descrizione}' → {categoria} (personalizzazione cliente)")
                return categoria
    
    except Exception as e:
        logger.warning(f"Errore check memoria locale utente (cache): {e}")
    
    # LIVELLO 3: Check memoria GLOBALE (da cache, 0 query!)
    try:
        # Normalizza descrizione per matching intelligente
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        if desc_normalized in _memoria_cache['prodotti_master']:
            categoria = _memoria_cache['prodotti_master'][desc_normalized]
            logger.info(f"🟢 MEMORIA GLOBALE (cache): '{descrizione}' → {categoria} (norm: '{desc_normalized}')")
            return categoria
    
    except Exception as e:
        logger.warning(f"Errore check memoria globale (cache): {e}")
    
    # LIVELLO 4: Check dicitura (se prezzo = 0)
    if prezzo == 0 and is_dicitura_sicura(descrizione, prezzo, quantita):
        return "📝 NOTE E DICITURE"
    
    # LIVELLO 5: Dizionario keyword (fallback)
    categoria_keyword = applica_correzioni_dizionario(descrizione, "Da Classificare")
    
    # Se la categoria è diversa da "Da Classificare", salva in memoria globale per futuri clienti
    if categoria_keyword != "Da Classificare":
        try:
            from datetime import datetime
            # Normalizza descrizione per salvataggio
            desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
            
            supabase.table('prodotti_master').insert({
                'descrizione': desc_normalized,
                'categoria': categoria_keyword,
                'confidence': 'media',
                'volte_visto': 1,
                'classificato_da': 'keyword',
                'created_at': datetime.now().isoformat(),
                'ultima_modifica': datetime.now().isoformat()
            }).execute()
            logger.info(f"💾 SALVATO in memoria globale: '{desc_normalized}' (orig: '{desc_original}') → {categoria_keyword} (keyword)")
        except Exception as e:
            # Ignora errore duplicato (race condition)
            if 'duplicate key' not in str(e).lower() and 'unique constraint' not in str(e).lower():
                logger.warning(f"Errore salvataggio memoria globale: {e}")
    
    return categoria_keyword


# ============================================
# FUNZIONE LOADING AI (animazione personalizzata)
# ============================================
def mostra_loading_ai(placeholder, messaggio="Elaborazione in corso"):
    """
    Mostra animazione loading a tema AI/Neural Network in un placeholder.
    Usa st.empty() placeholder per garantire rimozione anche in caso di errore.
    """
    placeholder.markdown(f"""
    <div style="text-align: center; padding: 50px;">
        <div class="loading-container">
            <div class="ai-brain">🧠</div>
            <h3 style="color: #1f77b4; margin-top: 20px;">🧠 {messaggio}</h3>
            <p style="color: #666;">Intelligenza artificiale in elaborazione...</p>
        </div>
    </div>
    
    <style>
        @keyframes pulse-brain {{
            0%, 100% {{ 
                transform: scale(1); 
                opacity: 1; 
                filter: drop-shadow(0 0 10px rgba(31, 119, 180, 0.3));
            }}
            50% {{ 
                transform: scale(1.15); 
                opacity: 0.7; 
                filter: drop-shadow(0 0 20px rgba(31, 119, 180, 0.7));
            }}
        }}
        
        .ai-brain {{
            font-size: 70px;
            animation: pulse-brain 1.8s ease-in-out infinite;
            display: inline-block;
        }}
        
        .loading-container {{
            position: relative;
        }}
        
        .loading-container p {{
            font-style: italic;
            animation: fade 2s ease-in-out infinite;
        }}
        
        @keyframes fade {{
            0%, 100% {{ opacity: 0.5; }}
            50% {{ opacity: 1; }}
        }}
    </style>
    """, unsafe_allow_html=True)



# ============================================
# FUNZIONE CALCOLO PREZZO STANDARDIZZATO
# ============================================
# ============================================
# FUNZIONE CALCOLO PREZZO STANDARDIZZATO INTELLIGENTE
# ============================================
def calcola_prezzo_standard_intelligente(descrizione, um, prezzo_unitario):
    """
    Calcola prezzo standardizzato usando SOLO pattern universali.
    NON dipende da prodotti specifici, applicabile a QUALSIASI ristorante.
    
    Pattern riconosciuti (in ordine di priorità):
    1. U.M. unitaria (PZ, CT, NR, FS, UN, SC)
    2. Quantità nella descrizione (KG<num>, GR<num>, ML<num>, PZ<num>)
    3. Confezioni (X<num>, (<num>))
    4. Default per KG/LT
    """
    import re
    
    try:
        prezzo = float(prezzo_unitario)
        if prezzo <= 0:
            return None
    except (ValueError, TypeError):
        return None
    
    # Normalizza input
    um_norm = (um or '').strip().upper()
    desc = (descrizione or '').upper().strip()
    
    # =======================================================
    # PATTERN 1: U.M. UNITARIA (PZ, CT, NR, FS, UN, SC)
    # =======================================================
    # Se U.M. è unitaria, il prezzo unitario È il prezzo standard
    if um_norm in ['PZ', 'CT', 'NR', 'FS', 'UN', 'SC', 'NUMERO', 'PEZZI']:
        if 0.001 <= prezzo <= 10000:
            return prezzo
        return None
    
    # =======================================================
    # PATTERN 2: QUANTITÀ NELLA DESCRIZIONE
    # =======================================================
    
    # 2A. Pattern "KG<numero>" (es. KG5, KG12)
    match = REGEX_KG_NUMERO.search(desc)
    if match:
        try:
            kg = float(match.group(1).replace(',', '.'))
            if 0.01 <= kg <= 10000:
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # 2B. Pattern "GR<numero>" (es. GR500, GR800)
    match = REGEX_GR_NUMERO.search(desc)
    if match:
        try:
            gr = float(match.group(1))
            if 1 <= gr <= 100000:
                kg = gr / 1000.0
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # 2C. Pattern "ML<numero>" (es. ML750, ML500)
    match = REGEX_ML_NUMERO.search(desc)
    if match:
        try:
            ml = float(match.group(1))
            if 1 <= ml <= 100000:
                lt = ml / 1000.0
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 2D. Pattern "CL<numero>" (es. CL50)
    match = REGEX_CL_NUMERO.search(desc)
    if match:
        try:
            cl = float(match.group(1))
            if 1 <= cl <= 10000:
                lt = cl / 100.0
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 2E. Pattern "LT<numero>" o "L<numero>" (es. LT5, L30)
    match = REGEX_LT_NUMERO.search(desc)
    if match:
        try:
            lt = float(match.group(1).replace(',', '.'))
            if 0.01 <= lt <= 10000:
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 2F. Pattern "PZ<numero>" nella descrizione (es. PZ100, PZ50)
    match = REGEX_PZ_NUMERO.search(desc)
    if match:
        try:
            pz = float(match.group(1))
            if 2 <= pz <= 10000:
                return prezzo / pz
        except (ValueError, TypeError):
            pass
    
    # =======================================================
    # PATTERN 3: CONFEZIONI/MULTIPLI
    # =======================================================
    
    # 3A. Pattern "X<numero>" (es. X12, X24)
    match = REGEX_X_NUMERO.search(desc)
    if match:
        try:
            num = float(match.group(1))
            if 2 <= num <= 1000:
                return prezzo / num
        except (ValueError, TypeError):
            pass
    
    # 3B. Pattern "(<numero>)" (es. (12), (50))
    match = REGEX_PARENTESI_NUMERO.search(desc)
    if match:
        try:
            num = float(match.group(1))
            if 2 <= num <= 1000:
                return prezzo / num
        except (ValueError, TypeError):
            pass
    
    # =======================================================
    # PATTERN 4: PESO/VOLUME IN FORMATO TESTUALE
    # =======================================================
    
    # 4A. Pattern "<numero> KG" o "<numero>,<numero> KG"
    match = REGEX_NUMERO_KG.search(desc)
    if match:
        try:
            kg = float(match.group(1).replace(',', '.'))
            if 0.01 <= kg <= 10000:
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # 4B. Pattern "<numero> LT" o "<numero> LITRI"
    match = REGEX_NUMERO_LT.search(desc)
    if match:
        try:
            lt = float(match.group(1).replace(',', '.'))
            if 0.01 <= lt <= 10000:
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 4C. Pattern "<numero> GR" o "<numero> GRAMMI"
    match = REGEX_NUMERO_GR.search(desc)
    if match:
        try:
            gr = float(match.group(1))
            if 1 <= gr <= 100000:
                kg = gr / 1000.0
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # =======================================================
    # PATTERN 5: DEFAULT PER U.M. STANDARD
    # =======================================================
    
    # Se U.M. è KG o LT e nessun pattern trovato, il prezzo è già standard
    if um_norm in ['KG', 'LT', 'KILOGRAMMI', 'LITRI']:
        return prezzo
    
    # =======================================================
    # NESSUN PATTERN RICONOSCIUTO
    # =======================================================
    return None



st.set_page_config(
    page_title="CHECK FORNITORI AI",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": ""
    }
)


# Elimina completamente sidebar in tutta l'app
st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        display: none !important;
    }
    section[data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)


# Nasconde il menu principale (tre puntini) e l'header per utenti finali
st.markdown(
    """
    <style>
      #MainMenu { visibility: hidden !important; }
      header[role="banner"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# CSS addizionale per nascondere bottoni/elementi con attributi che contengono Deploy/Share
st.markdown(
        """
        <style>
            button[title*="Deploy" i], a[title*="Deploy" i], [aria-label*="Deploy" i], [data-testid*="deploy" i] { display: none !important; }
            button[title*="Share" i], a[title*="Share" i], [aria-label*="Share" i], [data-testid*="share" i] { display: none !important; }
            /* italiano */
            button[title*="Condividi" i], a[title*="Condividi" i], [aria-label*="Condividi" i] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
)


# Rimuove dinamicamente eventuale bottone "Deploy"/"Share" in ambienti Streamlit Cloud
st.markdown(
        """
        <script>
            (function(){
                const keywords = ['deploy','share','deploy app','share app','condividi','pubblica'];
                function hideCandidates(){
                    try{
                        // scan common elements
                        const candidates = Array.from(document.querySelectorAll('button, a, div, span'));
                        candidates.forEach(el=>{
                            try{
                                const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                                const title = (el.title || '').toLowerCase();
                                const aria = (el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('data-testid') || '')) || '';
                                const attrs = (aria || '').toLowerCase();
                                const combined = [text, title, attrs].join(' ');
                                for(const k of keywords){
                                    if(k && combined.indexOf(k) !== -1){
                                        el.style.display = 'none';
                                        // also try to hide parent nodes to remove wrappers
                                        if(el.parentElement) el.parentElement.style.display = 'none';
                                        break;
                                    }
                                }
                            }catch(e){}
                        });
                    }catch(e){}
                }
                // initial run + repeated attempts (Streamlit may inject later)
                hideCandidates();
                const interval = setInterval(hideCandidates, 800);
                // observe DOM mutations as well
                const obs = new MutationObserver(hideCandidates);
                obs.observe(document.body, {childList:true, subtree:true});
                // stop interval after some time to avoid perf issues
                setTimeout(()=>{ clearInterval(interval); }, 20000);
            })();
        </script>
        """,
        unsafe_allow_html=True,
)


# ============================================================
# 🔒 SISTEMA AUTENTICAZIONE CON RECUPERO PASSWORD
# ============================================================

import argon2
import secrets
import requests
import hashlib
from supabase import create_client, Client
from datetime import datetime, timedelta
import logging
import sys


# Logger con fallback cloud-compatible
logger = logging.getLogger('fci_app')
if not logger.handlers:
    try:
        # Prova filesystem locale (sviluppo)
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler('debug.log', maxBytes=5_000_000, backupCount=5, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.info("✅ Logging su file locale attivo")
    except (OSError, PermissionError) as e:
        # Fallback: stdout per cloud read-only
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info("✅ Logging su stdout attivo (cloud mode)")


# Inizializza Supabase
try:
    supabase_url = st.secrets["supabase"]["url"]
    supabase_key = st.secrets["supabase"]["key"]
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    logger.exception("Connessione Supabase fallita")
    st.error(f"⛔ Errore connessione Supabase: {e}")
    st.stop()


# RIPRISTINO SESSIONE DA COOKIE (dopo inizializzazione Supabase)
try:
    # Inizializza logged_in se non esiste
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Inizializza logout_in_progress se non esiste
    if 'logout_in_progress' not in st.session_state:
        st.session_state.logout_in_progress = False
    
    # Ripristina sessione da cookie SOLO se:
    # 1. NON è già loggato
    # 2. NON sta facendo logout
    if not st.session_state.logged_in and not st.session_state.logout_in_progress:
        cookie_manager = stx.CookieManager(key="cookie_manager_init")
        user_email_cookie = cookie_manager.get("user_email")
        logger.debug(f"Cookie recuperato all'avvio: {user_email_cookie}")
        if user_email_cookie:
            try:
                response = supabase.table("users").select("*").eq("email", user_email_cookie).eq("attivo", True).execute()
                if response and getattr(response, 'data', None):
                    st.session_state.logged_in = True
                    st.session_state.user_data = response.data[0]
                    logger.debug(f"Sessione ripristinata per: {user_email_cookie}")
            except Exception:
                logger.exception('Errore recupero utente da cookie')
    
    # Reset del flag logout dopo il primo rerun
    if st.session_state.logout_in_progress:
        st.session_state.logout_in_progress = False
except Exception:
    # Non fatale: se qualcosa va storto non blocchiamo l'app
    logger.exception('Errore controllo cookie sessione')


# Hasher password
ph = argon2.PasswordHasher()


def verify_and_migrate_password(user_record: dict, password: str) -> bool:
    """Verifica password con supporto Argon2 e SHA256 legacy"""
    stored = (user_record.get('password_hash') or '').strip()
    if not stored:
        return False


    # Argon2
    if stored.startswith('$argon2'):
        try:
            ph.verify(stored, password)
            return True
        except Exception:
            logger.exception('Verifica Argon2 fallita')
            return False


    # Fallback SHA256
    try:
        sha = hashlib.sha256(password.encode()).hexdigest()
        if sha == stored:
            try:
                new_hash = ph.hash(password)
                supabase.table('users').update({'password_hash': new_hash}).eq('id', user_record.get('id')).execute()
            except Exception:
                logger.exception('Migrazione password fallita')
            return True
        return False
    except Exception:
        logger.exception('Verifica SHA256 fallita')
        return False


def verifica_credenziali(email, password):
    """Verifica login con Supabase"""
    try:
        response = supabase.table("users").select("*").eq("email", email).eq("attivo", True).execute()
        
        if not response.data:
            return None, "Credenziali errate o account disattivato"
        
        user = response.data[0]
        
        if verify_and_migrate_password(user, password):
            try:
                supabase.table('users').update({'last_login': datetime.utcnow().isoformat()}).eq('id', user['id']).execute()
            except Exception:
                logger.exception('Errore aggiornamento last_login')
            return user, None
        else:
            return None, "Credenziali errate"
            
    except Exception as e:
        logger.exception("Errore verifica credenziali")
        return None, f"Errore: {str(e)}"


def invia_codice_reset(email):
    """
    Genera codice reset, salva DB o sessione e invia via Brevo SMTP API
    in modo sicuro. Non espone MAI il codice nell'interfaccia.
    Se l'invio fallisce ritorna un messaggio generico.
    """
    code = secrets.token_urlsafe(8)
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    
    # Proviamo a salvare nel DB; se fallisce salviamo in sessione temporanea
    stored_in_db = True
    try:
        supabase.table('users').update({
            'reset_code': code,
            'reset_expires': expires
        }).eq('email', email).execute()
    except Exception:
        logger.exception(f"Errore salvataggio codice per {email}")
        stored_in_db = False
    
    if not stored_in_db:
        if 'reset_codes' not in st.session_state:
            st.session_state.reset_codes = {}
        st.session_state.reset_codes[email] = {'code': code, 'expires': expires}
    
    # Prepariamo invio via Brevo API
    brevo_cfg = st.secrets.get('brevo')
    if not brevo_cfg:
        logger.error('Sezione [brevo] non trovata in secrets.toml')
        return False, "Errore nell'invio email"
    
    api_key = brevo_cfg.get('api_key')
    if not api_key:
        logger.error('Brevo API key non configurata')
        return False, "Errore nell'invio email"
    
    sender_email = brevo_cfg.get('sender_email', 'contact@updates.brevo.com')
    sender_name = brevo_cfg.get('sender_name', 'Check Fornitori AI')
    
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": email}],
        "subject": "Reset Password - CHECK FORNITORI AI",
        "htmlContent": f"""<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: #f8f9fa; padding: 30px; border-radius: 10px;">
        <h2 style="color: #0284c7;">Reset Password</h2>
        <p>Hai richiesto il reset della password per il tuo account <strong>Check Fornitori AI</strong>.</p>
        <p>Usa questo codice per reimpostare la tua password:</p>
        <div style="background: white; padding: 20px; border-radius: 5px; text-align: center; margin: 20px 0;">
            <h1 style="color: #0284c7; letter-spacing: 5px; font-size: 32px;">{code}</h1>
        </div>
        <p><strong>Il codice scade tra 1 ora.</strong></p>
        <p style="color: #dc2626;">Se non hai richiesto tu questo reset, ignora questa email.</p>
        <hr style="margin: 20px 0; border: none; border-top: 1px solid #e5e7eb;">
        <p style="font-size: 12px; color: #6b7280;">Check Fornitori AI 2025</p>
    </div>
</body>
</html>"""
    }
    
    headers = {
        'api-key': api_key,
        'Content-Type': 'application/json'
    }
    
    try:
        resp = requests.post('https://api.brevo.com/v3/smtp/email', json=payload, headers=headers, timeout=10)
        
        print(f"📧 DEBUG BREVO: Status={resp.status_code}, Response={resp.text}")
        
        if resp.status_code == 201:
            logger.info(f"Email reset inviata con successo a {email}")
            print(f"✅ DEBUG BREVO: Email inviata! MessageID={resp.text}")
            return True, "Email inviata! Controlla la tua casella di posta."
        else:
            logger.error(f"Brevo invio fallito per {email}: {resp.status_code} {resp.text}")
            print(f"❌ DEBUG BREVO: Invio fallito! Status={resp.status_code}")
            return False, "Errore nell'invio email"
    except Exception as e:
        logger.exception(f"Eccezione invio Brevo per {email}")
        print(f"💥 DEBUG BREVO: Eccezione={str(e)}")
        return False, "Errore nell'invio email"


def verifica_codice_reset(email, code, new_password):
    """Verifica codice e aggiorna password"""
    try:
        resp = supabase.table('users').select('*').eq('email', email).limit(1).execute()
        user = resp.data[0] if resp.data else None
        
        valid = False
        
        if user:
            stored_code = user.get('reset_code')
            if stored_code == code:
                valid = True
        
        if not valid:
            codes = st.session_state.get('reset_codes', {})
            entry = codes.get(email)
            if entry and entry.get('code') == code:
                valid = True
        
        if not valid:
            return None, "Codice errato o scaduto"
        
        new_hash = ph.hash(new_password)
        supabase.table('users').update({
            'password_hash': new_hash,
            'reset_code': None,
            'reset_expires': None
        }).eq('email', email).execute()
        
        if 'reset_codes' in st.session_state and email in st.session_state.reset_codes:
            del st.session_state.reset_codes[email]
        
        resp = supabase.table('users').select('*').eq('email', email).execute()
        return resp.data[0] if resp.data else None, None
        
    except Exception as e:
        logger.exception("Errore reset password")
        return None, str(e)


def mostra_pagina_login():
    """Form login con recupero password - ESTETICA STREAMLIT PULITA"""
    # Elimina completamente sidebar e pulsante
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            min-width: 0 !important;
        }
        section[data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        button[kind="header"] {
            display: none !important;
        }
        .css-1d391kg {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("## 🏪 CHECK FORNITORI AI")
    st.markdown("### Accedi al Sistema")
    
    tab1, tab2 = st.tabs(["🔑 Login", "🔄 Recupera Password"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input("🔑 Password", type="password", placeholder="Password")
            
            # CSS per bottone blu chiaro
            st.markdown("""
                <style>
                div[data-testid="stFormSubmitButton"] button {
                    background-color: #0ea5e9 !important;
                    color: white !important;
                }
                div[data-testid="stFormSubmitButton"] button:hover {
                    background-color: #0284c7 !important;
                }
                </style>
            """, unsafe_allow_html=True)
            
            submit = st.form_submit_button("🚀 Accedi", use_container_width=True)
            
            if submit:
                if not email or not password:
                    st.error("⚠️ Compila tutti i campi!")
                else:
                    with st.spinner("Verifica credenziali..."):
                        user, errore = verifica_credenziali(email, password)
                        
                        if user:
                            st.session_state.logged_in = True
                            st.session_state.user_data = user


                            # SALVA COOKIE PER MANTENERE SESSIONE
                            cookie_manager = stx.CookieManager(key="cookie_manager_login")
                            try:
                                # Impostiamo expires_at come oggetto datetime (expectation di CookieManager)
                                expires_at = datetime.now() + timedelta(days=7)
                                res = cookie_manager.set("user_email", user['email'], expires_at=expires_at)
                                logger.debug(f"Cookie set result: {res}")
                                # Leggiamo immediatamente il cookie per verifica
                                read_back = cookie_manager.get("user_email")
                                logger.debug(f"Cookie letto dopo set: {read_back}")
                            except Exception:
                                logger.exception('Impossibile impostare cookie')


                            st.success("✅ Accesso effettuato!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {errore}")
    
    with tab2:
        st.markdown("#### Reset Password via Email")
        
        reset_email = st.text_input("📧 Email per reset", placeholder="tua@email.com", key="reset_email")
        
        if st.button("📨 Invia Codice", use_container_width=True):
            if not reset_email:
                st.warning("⚠️ Inserisci un'email")
            else:
                success, msg = invia_codice_reset(reset_email)
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.info(f"ℹ️ {msg}")
        
        st.markdown("---")
        
        code_input = st.text_input("🔢 Codice ricevuto", placeholder="Inserisci il codice", key="code_input")
        new_pwd = st.text_input("🔑 Nuova password (min 8 caratteri)", type="password", key="new_pwd")
        confirm_pwd = st.text_input("🔑 Conferma password", type="password", key="confirm_pwd")
        
        if st.button("✅ Conferma Reset", use_container_width=True, type="primary"):
            if not reset_email or not code_input or not new_pwd or not confirm_pwd:
                st.warning("⚠️ Compila tutti i campi")
            elif new_pwd != confirm_pwd:
                st.error("❌ Le password non coincidono")
            elif len(new_pwd) < 8:
                st.error("❌ Password troppo corta (min 8 caratteri)")
            else:
                user, errore = verifica_codice_reset(reset_email, code_input, new_pwd)
                
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user_data = user
                    st.success("✅ Password aggiornata! Accesso automatico...")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error(f"❌ {errore}")


# ============================================================
# CHECK LOGIN ALL'AVVIO
# ============================================================


# logged_in già inizializzato nella sezione RIPRISTINO SESSIONE DA COOKIE


if not st.session_state.logged_in:
    mostra_pagina_login()
    st.stop()


# Se arrivi qui, sei loggato! Vai DIRETTO ALL'APP
user = st.session_state.user_data


# ============================================
# BANNER IMPERSONAZIONE (solo per admin che impersonano)
# ============================================

if st.session_state.get('impersonating', False):
    # Banner visibile quando l'admin sta impersonando un cliente
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f59e0b 0%, #dc2626 100%); 
                padding: 15px; 
                border-radius: 10px; 
                margin-bottom: 20px; 
                text-align: center;
                border: 3px solid #dc2626;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
        <h3 style="color: white; margin: 0;">
            ⚠️ MODALITÀ IMPERSONAZIONE
        </h3>
        <p style="color: #fef3c7; margin: 10px 0 0 0; font-size: 16px;">
            Stai visualizzando l'account di: <strong>{user.get('nome_ristorante', 'Cliente')}</strong> ({user.get('email')})
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Bottone "Torna Admin" in colonna separata
    col_back_admin, col_spacer = st.columns([2, 8])
    with col_back_admin:
        if st.button("🔙 Torna Admin", type="primary", use_container_width=True, key="back_to_admin_btn"):
            # Ripristina dati admin originali
            if 'admin_original_user' in st.session_state:
                st.session_state.user_data = st.session_state.admin_original_user.copy()
                del st.session_state.admin_original_user
                st.session_state.impersonating = False
                
                # Log uscita impersonazione
                logger.info(f"FINE IMPERSONAZIONE: Ritorno a admin {st.session_state.user_data.get('email')}")
                
                # Redirect al pannello admin
                st.switch_page("pages/admin.py")
            else:
                st.error("⚠️ Errore: dati admin originali non trovati")
                st.session_state.impersonating = False
                st.rerun()
    
    st.markdown("---")


# ============================================
# HEADER CON LOGOUT, LINK ADMIN E CAMBIO PASSWORD
# ============================================


# Lista admin (deve coincidere con quella in pages/admin.py)
ADMIN_EMAILS = ["mattiadavolio90@gmail.com"]


# Struttura colonne: se admin mostra 4 colonne, altrimenti 3
if user.get('email') in ADMIN_EMAILS:
    col1, col2, col3, col4 = st.columns([6, 1.5, 1.5, 1])
else:
    col1, col2, col3 = st.columns([7, 2, 1])


with col1:
    st.markdown(f"## 🏪 CHECK FORNITORI AI")
    st.caption(f"👤 {user.get('nome_ristorante', 'Utente')} | 📧 {user.get('email')}")


# Pulsanti diversi per admin e clienti
if user.get('email') in ADMIN_EMAILS:
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔧 Pannello Admin", use_container_width=True, key="admin_panel_btn"):
            st.switch_page("pages/admin.py")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Password", use_container_width=True, key="change_pwd_btn"):
            st.switch_page("pages/cambio_password.py")
    
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", type="primary", use_container_width=True, key="logout_btn"):
            # Imposta flag per evitare auto-login dal cookie
            st.session_state.logout_in_progress = True
            
            # Cancella il cookie per evitare auto-login al prossimo refresh
            try:
                cookie_manager = stx.CookieManager(key="cookie_manager_logout")
                cookie_manager.delete("user_email")
            except Exception:
                logger.exception('Errore cancellazione cookie al logout')
            
            st.session_state.logged_in = False
            st.session_state.user_data = None
            st.rerun()
else:
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Cambio Password", use_container_width=True, key="change_pwd_btn"):
            st.switch_page("pages/cambio_password.py")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", type="primary", use_container_width=True, key="logout_btn_alt"):
            # Imposta flag per evitare auto-login dal cookie
            st.session_state.logout_in_progress = True
            
            # Cancella il cookie per evitare auto-login al prossimo refresh
            try:
                cookie_manager = stx.CookieManager(key="cookie_manager_logout2")
                cookie_manager.delete("user_email")
            except Exception:
                logger.exception('Errore cancellazione cookie al logout')
            
            st.session_state.logged_in = False
            st.session_state.user_data = None
            st.rerun()


st.markdown("---")

# ============================================================
# PROSEGUE CODICE NORMALE APP
# ============================================================
# ============================================================
# FILE DI MEMORIA
# ============================================================
# MEMORIA_FILE rimosso - usa solo Supabase
MEMORIA_AI_FILE = "memoria_ai_correzioni.json"
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    logger.exception("API Key OpenAI non trovata o accesso a st.secrets fallito")
    st.error("⛔ ERRORE: API Key non trovata!")
    st.stop()



client = OpenAI(api_key=api_key)


# ============================================
# 🔥 USA STESSA CONNESSIONE SUPABASE GIÀ INIZIALIZZATA
# ============================================
# Non serve ricreare la connessione, usiamo quella già creata sopra!
# La variabile 'supabase' è già disponibile globalmente


# ============================================================
# CARICAMENTO CATEGORIE DINAMICHE DA DATABASE
# ============================================================

@st.cache_data(ttl=600, show_spinner=False, max_entries=50)
def carica_categorie_da_db():
    """
    Carica categorie dinamiche da Supabase con cache di 5 minuti.
    
    Returns:
        list: Lista categorie formato "CARNE", ordinata alfabeticamente (SENZA EMOJI)
        
    Fallback a lista hardcoded se database non disponibile.
    """
    
    # 🔥 USA SOLO FALLBACK hardcoded (categorie pulite senza emoji)
    # Questo bypassa completamente il database Supabase
    logger.info("✅ USANDO FALLBACK HARDCODED (senza emoji garantito)")
    return _get_categorie_fallback()


def _get_categorie_fallback():
    """
    Categorie hardcoded di fallback se DB non disponibile (SENZA EMOJI - v2 cleaned).
    
    Ordine:
    1. NOTE E DICITURE (prima - per righe €0)
    2. Spese generali (MANUTENZIONE, SERVIZI, UTENZE)
    3. F&B alfabetico (incluso NO FOOD)
    """
    # ============================================================
    # 1. CATEGORIA PRIORITARIA (per righe €0 e problemi)
    # ============================================================
    categorie_prioritarie = [
        "NOTE E DICITURE"
    ]
    
    # ============================================================
    # 2. CATEGORIE SPESE GENERALI
    # ============================================================
    categorie_spese = [
        "MANUTENZIONE E ATTREZZATURE",
        "SERVIZI E CONSULENZE",
        "UTENZE E LOCALI"
    ]
    
    # ============================================================
    # 3. CATEGORIE F&B (ordine alfabetico, include NO FOOD)
    # ============================================================
    categorie_prodotti = [
        "ACQUA",
        "AMARI",
        "BEVANDE",
        "BIRRE",
        "CAFFÈ",
        "CARNE",
        "CONSERVE",
        "DISTILLATI",
        "FRUTTA",
        "GELATI",
        "LATTICINI",
        "NO FOOD",  # Materiali cucina (pellicole, rotoloni) - parte di F&B
        "OLIO E CONDIMENTI",
        "PASTICCERIA",
        "PESCE",
        "PRODOTTI DA FORNO",
        "SALSE E CREME",
        "SALUMI",
        "SCATOLAME",
        "SECCO",
        "SPEZIE E AROMI",
        "SURGELATI",
        "UOVA",
        "VARIE BAR",
        "VERDURE",
        "VINI"
    ]
    
    # Ordina alfabeticamente solo prodotti F&B
    categorie_prodotti.sort()
    
    # Combina nell'ordine corretto: prioritarie → spese → F&B
    return categorie_prioritarie + categorie_spese + categorie_prodotti


def estrai_nome_categoria(categoria_con_icona):
    """
    Estrae solo il nome dalla categoria con icona.
    
    Args:
        categoria_con_icona: "🍖 CARNE" o "CARNE"
    
    Returns:
        str: "CARNE" (solo nome, senza emoji)
    """
    if not categoria_con_icona:
        return "Da Classificare"
    
    # Se contiene spazio, prendi parte dopo primo spazio
    if ' ' in categoria_con_icona:
        return categoria_con_icona.split(' ', 1)[1].strip()
    
    # Altrimenti ritorna come è (già senza emoji)
    return categoria_con_icona.strip()


def aggiungi_icona_categoria(nome_categoria):
    """
    Aggiunge icona emoji al nome categoria.
    
    Args:
        nome_categoria: "CARNE"
    
    Returns:
        str: "🍖 CARNE"
    """
    try:
        # Query icona da database
        response = supabase.table('categorie')\
            .select('icona')\
            .eq('nome', nome_categoria.strip())\
            .eq('attiva', True)\
            .limit(1)\
            .execute()
        
        if response.data and len(response.data) > 0:
            icona = response.data[0].get('icona', '📦')
            return f"{icona} {nome_categoria}"
        
        # Fallback: ritorna senza icona
        return nome_categoria
        
    except Exception:
        return nome_categoria


# ============================================================
# NORMALIZZAZIONE STRINGHE (-20% COSTI)
# ============================================================



def normalizza_stringa(testo):
    """Normalizza stringhe per ridurre duplicati AI"""
    if not testo or not isinstance(testo, str):
        return ""
    
    testo = testo.upper()
    testo = REGEX_PUNTEGGIATURA_FINALE.sub('', testo)  # Regex precompilata
    testo = ' '.join(testo.split())
    return testo[:100].strip()



# ============================================================
# SAFE GET CORRETTO (BUGFIX GEMINI)
# ============================================================



def safe_get(dizionario, percorso_chiavi, default=None, keep_list=False):
    """
    Naviga dizionario annidato in sicurezza
    
    Args:
        keep_list: Se True, mantiene le liste (per DettaglioLinee)
                   Se False, estrae primo elemento (per Body)
    """
    valore_corrente = dizionario
    
    for chiave in percorso_chiavi:
        if isinstance(valore_corrente, dict):
            valore_corrente = valore_corrente.get(chiave)
            if valore_corrente is None:
                return default
            
            if isinstance(valore_corrente, list):
                if keep_list:
                    return valore_corrente if valore_corrente else default
                else:
                    if len(valore_corrente) > 0:
                        valore_corrente = valore_corrente[0]
                    else:
                        return default
        else:
            return default
    
    # Preserva valori falsy come 0 o ""; ritorna default solo se None
    return valore_corrente if valore_corrente is not None else default



# ============================================================
# FUNZIONI MEMORIA AI
# ============================================================


@st.cache_data(ttl=300, max_entries=1)  # Cache 5 minuti, evita letture disco ripetute
def carica_memoria_ai():
    """
    Carica memoria AI da file JSON con cache.
    Cache invalidata automaticamente ogni 5 minuti o manualmente dopo modifiche.
    """
    if os.path.exists(MEMORIA_AI_FILE):
        try:
            with open(MEMORIA_AI_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            # Mostra un warning per facilitare il debug del file di memoria AI
            st.warning(f"⚠️ Impossibile caricare {MEMORIA_AI_FILE}: {e}")
            return {}
    return {}


def salva_memoria_ai(memoria_ai):
    """Salvataggio atomico per prevenire corruzione file"""
    try:
        temp_file = MEMORIA_AI_FILE + '.tmp'
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(memoria_ai, f, ensure_ascii=False, indent=2)
        
        shutil.move(temp_file, MEMORIA_AI_FILE)
        
        # Invalida cache dopo modifica file
        carica_memoria_ai.clear()
        logger.info("🔄 Cache memoria AI invalidata dopo salvataggio")
        
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        st.error(f"Errore salvataggio memoria AI: {e}")


def aggiorna_memoria_ai(descrizione, categoria):
    memoria = carica_memoria_ai()
    memoria[descrizione] = categoria
    salva_memoria_ai(memoria)



def ricalcola_prezzi_con_sconti(user_id):
    """
    Ricalcola prezzi unitari per fatture già caricate (fix retroattivo sconti).
    
    Questa funzione serve per correggere i prezzi delle fatture caricate PRIMA
    del fix che calcola il prezzo effettivo da PrezzoTotale ÷ Quantità.
    
    Returns:
        int: Numero di righe aggiornate
    """
    try:
        # Leggi tutte le fatture dell'utente
        response = supabase.table("fatture") \
            .select("id, descrizione, quantita, prezzo_unitario, totale_riga") \
            .eq("user_id", user_id) \
            .execute()
        
        if not response.data:
            return 0
        
        righe_aggiornate = 0
        
        for row in response.data:
            totale = row.get('totale_riga', 0)
            quantita = row.get('quantita', 0)
            prezzo_attuale = row.get('prezzo_unitario', 0)
            
            if quantita > 0 and totale > 0:
                # Ricalcola prezzo effettivo
                prezzo_effettivo = round(totale / quantita, 4)
                
                # Solo se diverso (c'era uno sconto)
                if abs(prezzo_effettivo - prezzo_attuale) > 0.01:
                    # Aggiorna database
                    supabase.table("fatture").update({
                        'prezzo_unitario': prezzo_effettivo
                    }).eq('id', row['id']).execute()
                    
                    righe_aggiornate += 1
                    logger.info(f"🔄 Prezzo aggiornato: {row.get('descrizione', '')[:40]} | "
                               f"€{prezzo_attuale:.2f} → €{prezzo_effettivo:.2f}")
        
        return righe_aggiornate
    
    except Exception as e:
        logger.error(f"Errore ricalcolo prezzi: {e}")
        return 0



# ============================================================
# FUNZIONI MEMORIA PRINCIPALE
# ============================================================



# Funzioni carica_memoria() e salva_memoria() RIMOSSE
# Usa solo Supabase come unica fonte dati


# ============================================================
# FUNZIONE LOGGING UPLOAD EVENTS
# ============================================================

def log_upload_event(
    user_id: str,
    user_email: str,
    file_name: str,
    status: str,
    rows_parsed: int = 0,
    rows_saved: int = 0,
    rows_excluded: int = 0,
    error_stage: str = None,
    error_message: str = None,
    details: dict = None
):
    """
    Logga evento di upload su Supabase per supporto tecnico.
    Non solleva mai eccezioni per non bloccare l'upload principale.
    
    IMPORTANTE: Non logga duplicati (comportamento corretto).
    
    Args:
        user_id: UUID utente
        user_email: Email utente
        file_name: Nome file caricato
        status: SAVED_OK | SAVED_PARTIAL | FAILED (NO DUPLICATE)
        rows_parsed: Numero righe estratte dal parsing
        rows_saved: Numero righe effettivamente salvate
        rows_excluded: Numero righe escluse per "diciture" (comportamento normale)
        error_stage: Stage dove è avvenuto errore (PARSING | VISION | SUPABASE_INSERT | POSTCHECK)
        error_message: Messaggio errore (max 500 char)
        details: Dict con dettagli aggiuntivi (salvato come JSONB)
    """
    try:
        # Determina file_type
        file_type = "xml" if file_name.lower().endswith(".xml") else \
                   "pdf" if file_name.lower().endswith(".pdf") else \
                   "image" if file_name.lower().endswith((".jpg", ".jpeg", ".png")) else "unknown"
        
        # Tronca error_message se troppo lungo
        if error_message and len(error_message) > 500:
            error_message = error_message[:497] + "..."
        
        event_data = {
            'user_id': user_id,
            'user_email': user_email,
            'file_name': file_name,
            'file_type': file_type,
            'status': status,
            'rows_parsed': rows_parsed,
            'rows_saved': rows_saved,
            'rows_excluded': rows_excluded,
            'error_stage': error_stage,
            'error_message': error_message,
            'details': details
        }
        
        supabase.table('upload_events').insert(event_data).execute()
        logger.info(f"✅ LOG EVENT: {status} - {file_name} - user {user_email}")
        
    except Exception as e:
        # Non solleva eccezione per non bloccare l'upload
        logger.error(f"❌ Errore logging upload event: {e}")


def verifica_integrita_fattura(nome_file, dati_prodotti, user_id):
    """
    Verifica che tutte le righe del file siano state salvate su Supabase.
    
    Returns:
        dict con risultati verifica: {
            "file": nome_file,
            "righe_parsed": int,
            "righe_db": int,
            "perdite": int,
            "integrita_ok": bool
        }
    """
    try:
        # Conta righe nel DataFrame parsed
        righe_parsed = len(dati_prodotti)
        
        # Conta righe effettivamente salvate su Supabase
        response = supabase.table("fatture") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("file_origine", nome_file) \
            .execute()
        
        righe_db = len(response.data) if response.data else 0
        
        # Risultato verifica
        risultato = {
            "file": nome_file,
            "righe_parsed": righe_parsed,
            "righe_db": righe_db,
            "perdite": righe_parsed - righe_db,
            "integrita_ok": (righe_parsed == righe_db)
        }
        
        # Log dettagliato
        if not risultato["integrita_ok"]:
            logger.error(f"⚠️ PERDITA DATI: {risultato}")
        else:
            logger.info(f"✅ Integrità OK: {nome_file} - {righe_db} righe")
        
        return risultato
    
    except Exception as e:
        logger.error(f"Errore verifica integrità {nome_file}: {e}")
        return None



def salva_fattura_processata(nome_file, dati_prodotti, silent=False):
    """
    Salva fatture SEMPRE su Supabase come priorità + JSON come backup
    silent=True nasconde tutti i messaggi (usato durante batch upload)
    """
    # Verifica user_id dalla sessione
    if "user_data" not in st.session_state or "id" not in st.session_state.user_data:
        if not silent:
            st.error("❌ Errore: Utente non autenticato. Effettua il login.")
        return {"success": False, "error": "not_authenticated", "righe": 0, "location": None}
    
    user_id = st.session_state.user_data["id"]
    salvato_supabase = False
    salvato_json = False
    num_righe = len(dati_prodotti)
    
    # 🔥 PRIORITÀ 1: SALVA SU SUPABASE
    if supabase is not None:
        try:
            # Verifica che ci siano dati da salvare
            if not dati_prodotti:
                return {"success": False, "error": "no_data", "righe": 0, "location": None}
            
            # 📋 LOG: Inizio elaborazione
            logger.info(f"🔥 Inizio elaborazione: {nome_file}")
            logger.info(f"📄 {nome_file}: {len(dati_prodotti)} righe estratte dal file")
            
            # Prepara i record per Supabase
            records = []
            for prod in dati_prodotti:
                # Usa prezzo_standard già calcolato durante l'estrazione
                prezzo_std = prod.get("PrezzoStandard", prod.get("Prezzo_Standard"))
                
                # ⚡ FORZA categoria valida - MAI NULL o vuoto
                categoria_raw = prod.get("Categoria", "Da Classificare")
                if not categoria_raw or pd.isna(categoria_raw) or str(categoria_raw).strip() == '':
                    categoria_raw = "Da Classificare"
                
                records.append({
                    "user_id": user_id,
                    "file_origine": nome_file,
                    "numero_riga": prod.get("NumeroRiga", prod.get("Numero_Riga", 0)),
                    "data_documento": prod.get("DataDocumento", prod.get("Data_Documento", None)),
                    "fornitore": prod.get("Fornitore", "Sconosciuto"),
                    "descrizione": prod.get("Descrizione", ""),
                    "quantita": prod.get("Quantita", 1),
                    "unita_misura": prod.get("UnitaMisura", prod.get("Unita_Misura", "")),
                    "prezzo_unitario": prod.get("PrezzoUnitario", prod.get("Prezzo_Unitario", 0)),
                    "iva_percentuale": prod.get("IVAPercentuale", prod.get("IVA_Percentuale", 0)),
                    "totale_riga": prod.get("TotaleRiga", prod.get("Totale_Riga", 0)),
                    "categoria": categoria_raw,  # ⚡ Sempre valida, mai NULL
                    "codice_articolo": prod.get("CodiceArticolo", prod.get("Codice_Articolo", "")),
                    "prezzo_standard": float(prezzo_std) if prezzo_std and pd.notna(prezzo_std) else None
                })
            
            # 📋 LOG: Prima di salvare
            logger.info(f"💾 {nome_file}: invio {len(records)} record a Supabase")
            
            # Inserimento su Supabase
            response = supabase.table("fatture").insert(records).execute()
            salvato_supabase = True
            
            # 📋 LOG: Dopo salvataggio
            righe_confermate = len(response.data) if response.data else len(records)
            logger.info(f"✅ {nome_file}: {righe_confermate} righe confermate su DB")
            
            # 🧪 VERIFICA INTEGRITÀ
            verifica = verifica_integrita_fattura(nome_file, dati_prodotti, user_id)
            
            # ============================================================
            # LOG UPLOAD EVENT
            # ============================================================
            try:
                user_email = st.session_state.user_data.get("email", "unknown")
                
                if verifica and verifica["integrita_ok"]:
                    # Salvataggio completato con successo
                    log_upload_event(
                        user_id=user_id,
                        user_email=user_email,
                        file_name=nome_file,
                        status="SAVED_OK",
                        rows_parsed=verifica["righe_parsed"],
                        rows_saved=verifica["righe_db"],
                        error_stage=None,
                        error_message=None,
                        details=None
                    )
                elif verifica:
                    # Salvataggio parziale - ci sono perdite
                    log_upload_event(
                        user_id=user_id,
                        user_email=user_email,
                        file_name=nome_file,
                        status="SAVED_PARTIAL",
                        rows_parsed=verifica["righe_parsed"],
                        rows_saved=verifica["righe_db"],
                        error_stage="POSTCHECK",
                        error_message=f"Perdita dati: {verifica['perdite']} righe mancanti",
                        details={
                            "righe_parsed": verifica["righe_parsed"],
                            "righe_db": verifica["righe_db"],
                            "perdite": verifica["perdite"]
                        }
                    )
            except Exception as log_error:
                logger.error(f"Errore logging upload event: {log_error}")
            # ============================================================
            
            # Se c'è discrepanza, LOG ERRORE
            if verifica and not verifica["integrita_ok"]:
                logger.error(f"🚨 DISCREPANZA {nome_file}: parsed={verifica['righe_parsed']} vs db={verifica['righe_db']}")
                # Salva risultato verifica per mostrarlo dopo
                if not silent:
                    if 'verifica_integrita' not in st.session_state:
                        st.session_state.verifica_integrita = []
                    st.session_state.verifica_integrita.append(verifica)
            
        except Exception as e:
            logger.exception(f"Errore salvataggio Supabase per {nome_file}")
            
            # ============================================================
            # LOG UPLOAD EVENT - FAILED
            # ============================================================
            try:
                user_email = st.session_state.user_data.get("email", "unknown")
                log_upload_event(
                    user_id=user_id,
                    user_email=user_email,
                    file_name=nome_file,
                    status="FAILED",
                    rows_parsed=num_righe,
                    rows_saved=0,
                    error_stage="SUPABASE_INSERT",
                    error_message=str(e)[:500],
                    details={"exception_type": type(e).__name__}
                )
            except Exception as log_error:
                logger.error(f"Errore logging failed event: {log_error}")
            # ============================================================
            
            if not silent:
                st.error(f"❌ Errore Supabase: {str(e)[:100]}")
    
    # ❌ NESSUN FALLBACK: Supabase è l'unica fonte dati
    if not salvato_supabase:
        error_msg = "Impossibile salvare su Supabase. Verifica la connessione."
        if not silent:
            st.error(f"❌ {error_msg}")
        return {"success": False, "error": "supabase_failed", "righe": num_righe, "location": None}
    
    return {"success": True, "error": None, "righe": num_righe, "location": "supabase"}


# ============================================================
# ELIMINAZIONE FATTURE
# ============================================================


def elimina_fattura_completa(file_origine, user_id):
    """
    Elimina una fattura completa (tutti i prodotti) dal database.
    
    Args:
        file_origine: Nome del file XML della fattura
        user_id: ID utente (per controllo sicurezza)
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int}
    """
    try:
        # Verifica che l'utente sia autenticato
        if not user_id:
            return {"success": False, "error": "not_authenticated", "righe_eliminate": 0}
        
        # Prima conta quante righe verranno eliminate
        count_response = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine).execute()
        num_righe = len(count_response.data) if count_response.data else 0
        
        if num_righe == 0:
            return {"success": False, "error": "not_found", "righe_eliminate": 0}
        
        # Elimina dal database (con controllo user_id per sicurezza)
        response = supabase.table("fatture").delete().eq("user_id", user_id).eq("file_origine", file_origine).execute()
        
        # Log operazione
        logger.info(f"❌ Fattura eliminata: {file_origine} ({num_righe} righe) da user {user_id}")
        
        # Invalida cache per ricaricare dati
        st.cache_data.clear()
        invalida_cache_memoria()
        
        return {"success": True, "error": None, "righe_eliminate": num_righe}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione fattura {file_origine} per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0}


def elimina_tutte_fatture(user_id):
    """
    Elimina TUTTE le fatture dell'utente dal database.
    
    Args:
        user_id: ID utente (per controllo sicurezza)
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int, "fatture_eliminate": int}
    """
    try:
        # Verifica che l'utente sia autenticato
        if not user_id:
            return {"success": False, "error": "not_authenticated", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Prima conta quante righe e fatture verranno eliminate
        count_response = supabase.table("fatture").select("id, file_origine", count="exact").eq("user_id", user_id).execute()
        num_righe = count_response.count if count_response.count else 0
        num_fatture = len(set([r['file_origine'] for r in count_response.data])) if count_response.data else 0
        
        print(f"🔍 PRIMA DELETE: user_id={user_id} ha {num_fatture} fatture ({num_righe} righe)")
        logger.info(f"🔍 PRIMA DELETE: user_id={user_id} ha {num_fatture} fatture ({num_righe} righe)")
        
        if num_righe == 0:
            return {"success": False, "error": "no_data", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Elimina TUTTO per questo user_id
        response = supabase.table("fatture").delete().eq("user_id", user_id).execute()
        
        # 🔍 LOG DETTAGLIATO NUOVO
        print(f"🗑️ DELETE executed for user_id={user_id}")
        print(f"📊 DELETE result: {response}")
        logger.info(f"🗑️ DELETE executed for user_id={user_id}")
        logger.info(f"📊 DELETE result: {response}")
        
        # Verifica post-delete (conferma eliminazione)
        verify_response = supabase.table("fatture").select("id, file_origine, data_documento").eq("user_id", user_id).execute()
        num_rimaste = len(verify_response.data) if verify_response.data else 0
        
        print(f"✅ Righe rimaste dopo DELETE: {num_rimaste}")
        logger.info(f"✅ Righe rimaste dopo DELETE: {num_rimaste}")
        
        if num_rimaste > 0:
            print(f"⚠️ ATTENZIONE: DELETE NON COMPLETA!")
            print(f"📋 Prime 5 righe rimaste: {verify_response.data[:5]}")
            
            # Analizza QUALI righe sono sopravvissute
            fornitori_rimasti = set([r.get('file_origine', 'N/A') for r in verify_response.data])
            print(f"📊 File rimasti: {list(fornitori_rimasti)[:10]}")
            
            # Verifica se hanno lo stesso user_id
            user_ids_rimasti = set([r.get('user_id', 'N/A') for r in verify_response.data]) if 'user_id' in verify_response.data[0] else {'N/A'}
            print(f"🆔 User IDs delle righe rimaste: {user_ids_rimasti}")
            print(f"🆔 User ID attuale richiesto: {user_id}")
            
            if user_id not in user_ids_rimasti and 'N/A' not in user_ids_rimasti:
                print(f"🚨 PROBLEMA RLS: Le righe rimaste hanno user_id DIVERSO!")
            
            logger.error(f"⚠️ DELETE PARZIALE: {num_rimaste} righe ancora presenti per user {user_id}")
            logger.error(f"📋 Prime 5 righe rimaste: {verify_response.data[:5]}")
        else:
            print(f"✅ DELETE VERIFIED: Database completamente pulito")
            logger.info(f"✅ DELETE COMPLETA: 0 righe rimaste per user {user_id}")
        
        # Log operazione
        logger.warning(f"⚠️ ELIMINAZIONE MASSIVA: {num_fatture} fatture ({num_righe} righe) da user {user_id}")
        
        # Invalida cache per ricaricare dati
        st.cache_data.clear()
        invalida_cache_memoria()
        
        return {"success": True, "error": None, "righe_eliminate": num_righe, "fatture_eliminate": num_fatture}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione massiva per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0, "fatture_eliminate": 0}

# ============================================================
# TEST & AUDIT UTILITIES
# ============================================================


def audit_data_consistency(user_id: str, context: str = "unknown") -> dict:
    """
    🔍 Verifica coerenza dati tra DB, Cache e UI
    
    Args:
        user_id: ID utente da verificare
        context: Contesto della chiamata (es. "post-delete", "post-upload")
    
    Returns:
        dict con dettagli verifica:
        - db_count: righe su Supabase
        - db_files: file unici su Supabase
        - cache_count: righe in cache
        - cache_files: file unici in cache
        - consistent: bool (True se DB = Cache)
    """
    result = {
        "context": context,
        "user_id": user_id,
        "db_count": 0,
        "db_files": 0,
        "cache_count": 0,
        "cache_files": 0,
        "consistent": False,
        "error": None
    }
    
    try:
        # 1. Query diretta DB (bypass cache)
        db_response = supabase.table("fatture").select("file_origine", count="exact").eq("user_id", user_id).execute()
        result["db_count"] = db_response.count if db_response.count else 0
        result["db_files"] = len(set([r['file_origine'] for r in db_response.data])) if db_response.data else 0
        
        # 2. Query cache (potrebbe essere stale)
        df_cached = carica_e_prepara_dataframe(user_id)
        result["cache_count"] = len(df_cached)
        result["cache_files"] = df_cached['FileOrigine'].nunique() if not df_cached.empty else 0
        
        # 3. Verifica coerenza
        result["consistent"] = (result["db_count"] == result["cache_count"])
        
        # 4. Log audit
        if result["consistent"]:
            logger.info(f"✅ AUDIT OK [{context}]: DB={result['db_count']} Cache={result['cache_count']} (user={user_id})")
        else:
            logger.warning(f"⚠️ AUDIT FAIL [{context}]: DB={result['db_count']} ≠ Cache={result['cache_count']} (user={user_id})")
        
        return result
        
    except Exception as e:
        logger.exception(f"Errore audit per user {user_id}")
        result["error"] = str(e)
        return result


def get_fatture_stats(user_id: str) -> dict:
    """
    📊 Ottiene statistiche fatture SOLO da Supabase.
    Fonte unica di verità per tutti i conteggi UI.
    
    Args:
        user_id: ID utente per filtro multi-tenancy
    
    Returns:
        dict con:
        - num_uniche: Numero fatture uniche (FileOrigine distinti)
        - num_righe: Numero totale righe/prodotti
        - success: bool (True se query riuscita)
    
    GARANZIE:
    - Legge SOLO da Supabase (nessun cache/sessione)
    - Coerente con Gestione Fatture
    - Usato per tutti i conteggi pubblici
    """
    try:
        response = supabase.table("fatture") \
            .select("file_origine", count='exact') \
            .eq("user_id", user_id) \
            .execute()
        
        if not response.data:
            return {"num_uniche": 0, "num_righe": 0, "success": True}
        
        # Conta file unici e righe totali
        file_unici_set = set([r["file_origine"] for r in response.data])
        
        return {
            "num_uniche": len(file_unici_set),
            "num_righe": response.count,  # ✅ FIX: usa count reale invece di len()
            "success": True
        }
    except Exception as e:
        logger.error(f"Errore get_fatture_stats per user {user_id}: {e}")
        return {"num_uniche": 0, "num_righe": 0, "success": False}


# ============================================================
# CACHING DATAFRAME OTTIMIZZATO
# ============================================================


@st.cache_data(ttl=None, max_entries=50)  # ← NESSUN TTL: invalidazione SOLO manuale con clear()
def carica_e_prepara_dataframe(user_id: str, force_refresh: bool = False):
    """
    🔥 SINGLE SOURCE OF TRUTH: Carica fatture SOLO da Supabase
    
    Args:
        user_id: ID utente per filtro multi-tenancy
        force_refresh: Se True, bypassa cache (usato dopo delete)
    
    Returns:
        DataFrame con fatture dell'utente o DataFrame vuoto
    
    GARANZIE:
    - Legge SOLO da tabella 'fatture' su Supabase
    - Filtra per user_id (isolamento utenti)
    - Nessun fallback JSON o altre fonti
    - Cache invalidata SOLO con clear() esplicito
    """
    logger.info(f"📊 LOAD START: user_id={user_id}, force_refresh={force_refresh}")
    print(f"🔍 DEBUG: INIZIO carica_e_prepara_dataframe(user_id={user_id}, force_refresh={force_refresh})")
    
    dati = []
    
    # 🔥 CARICA DA SUPABASE (se disponibile)
    if supabase is not None:
        print("🔍 DEBUG: Tentativo caricamento da Supabase...")
        try:
            response = supabase.table("fatture").select("*", count="exact").eq("user_id", user_id).execute()
            print(f"🔍 DEBUG: Supabase response.count = {response.count}")
            logger.info(f"📊 CARICAMENTO: user_id={user_id} ha {response.count} righe su Supabase")
            
            for row in response.data:
                dati.append({
                    "FileOrigine": row["file_origine"],
                    "NumeroRiga": row["numero_riga"],
                    "DataDocumento": row["data_documento"],
                    "Fornitore": row["fornitore"],
                    "Descrizione": row["descrizione"],
                    "Quantita": row["quantita"],
                    "UnitaMisura": row["unita_misura"],
                    "PrezzoUnitario": row["prezzo_unitario"],
                    "IVAPercentuale": row["iva_percentuale"],
                    "TotaleRiga": row["totale_riga"],
                    "Categoria": row["categoria"],
                    "CodiceArticolo": row["codice_articolo"],
                    "PrezzoStandard": row.get("prezzo_standard")
                })
            
            if len(dati) > 0:
                logger.info(f"✅ LOAD SUCCESS: {len(dati)} righe caricate da Supabase per user_id={user_id}")
                print(f"✅ DEBUG: Caricati {len(dati)} record da Supabase")
                df_result = pd.DataFrame(dati)
                
                # 🔧 NORMALIZZA CATEGORIA: Converti NULL/None/vuoti in NaN per uniformità
                if 'Categoria' in df_result.columns:
                    # Log PRIMA della normalizzazione
                    null_count_before = df_result['Categoria'].isna().sum()
                    none_count_before = (df_result['Categoria'] == None).sum()
                    empty_count_before = (df_result['Categoria'] == '').sum()
                    logger.info(f"🔍 PRE-NORMALIZZAZIONE: NA={null_count_before}, None={none_count_before}, vuoti={empty_count_before}")
                    
                    df_result['Categoria'] = df_result['Categoria'].replace(
                        to_replace=[None, '', 'None', 'null', 'NULL', ' '], 
                        value=pd.NA
                    )
                    # Converti spazi bianchi in NaN
                    df_result.loc[df_result['Categoria'].astype(str).str.strip() == '', 'Categoria'] = pd.NA
                    
                    # 🔄 MIGRAZIONE AUTOMATICA: Aggiorna vecchi nomi categorie
                    mapping_categorie = {
                        'SALSE': 'SALSE E CREME',
                        'BIBITE E BEVANDE': 'BEVANDE',
                        'PANE': 'PRODOTTI DA FORNO',
                        'DOLCI': 'PASTICCERIA',
                        'OLIO': 'OLIO E CONDIMENTI'
                    }
                    
                    righe_migrate = 0
                    for vecchio, nuovo in mapping_categorie.items():
                        mask = df_result['Categoria'] == vecchio
                        if mask.any():
                            df_result.loc[mask, 'Categoria'] = nuovo
                            righe_migrate += mask.sum()
                            logger.info(f"🔄 MIGRAZIONE AUTO: '{vecchio}' → '{nuovo}' ({mask.sum()} righe)")
                    
                    if righe_migrate > 0:
                        logger.info(f"✅ MIGRAZIONE COMPLETATA: {righe_migrate} righe aggiornate")
                    
                    # Log DOPO la normalizzazione
                    null_count_after = df_result['Categoria'].isna().sum()
                    empty_count = (df_result['Categoria'].astype(str).str.strip() == '').sum()
                    logger.info(f"🔧 POST-NORMALIZZAZIONE: {null_count_after} NULL + {empty_count} vuote")
                    print(f"🔧 DEBUG: Categorie - {null_count_after} NULL + {empty_count} vuote")
                    
                    # 🎯 FIX CELLE BIANCHE DEFINITIVO: Riempie NA E vuoti con "Da Classificare"
                    # Step 1: fillna per NULL/pd.NA
                    df_result['Categoria'] = df_result['Categoria'].fillna("Da Classificare")
                    
                    # Step 2: converti stringhe vuote/None in "Da Classificare"
                    df_result['Categoria'] = df_result['Categoria'].apply(
                        lambda x: "Da Classificare" if x is None or str(x).strip() == '' else x
                    )
                    
                    # Verifica finale
                    da_class_count = (df_result['Categoria'] == 'Da Classificare').sum()
                    logger.info(f"✅ CELLE BIANCHE RISOLTE: {da_class_count} celle mostrano 'Da Classificare'")
                    print(f"✅ DEBUG: {da_class_count} celle con 'Da Classificare' (pronte per AI)")
                
                print(f"✅ DEBUG: DataFrame shape={df_result.shape}, files={df_result['FileOrigine'].nunique() if not df_result.empty else 0}")
                return df_result
            else:
                logger.info(f"ℹ️ LOAD EMPTY: Nessuna fattura per user_id={user_id}")
                print("ℹ️ DEBUG: Supabase vuoto (nessuna fattura per questo utente)")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ LOAD ERROR: Errore Supabase per user_id={user_id}: {e}")
            print(f"❌ DEBUG: Errore Supabase: {e}")
            logger.exception("Errore query Supabase")
            return pd.DataFrame()
    
    # Supabase non configurato (impossibile in produzione)
    logger.critical("❌ CRITICAL: Supabase client non inizializzato!")
    print("❌ DEBUG: Supabase non configurato")
    return pd.DataFrame()



# ============================================================
# CONVERSIONE FILE IN BASE64 PER VISION
# ============================================================


def converti_in_base64(file_obj, nome_file):
    """Converte PDF/IMG in base64 per OpenAI Vision usando PyMuPDF (no Poppler richiesto)."""
    try:
        content = file_obj.read()
        
        # Se è PDF, converti prima pagina in immagine con PyMuPDF
        if nome_file.lower().endswith('.pdf'):
            try:
                # Apri PDF con PyMuPDF
                pdf_document = fitz.open(stream=content, filetype="pdf")
                
                if pdf_document.page_count == 0:
                    errore = "PDF vuoto o senza pagine"
                    logger.error(f"Conversione PDF {nome_file}: {errore}")
                    st.session_state.files_con_errori[nome_file] = errore
                    pdf_document.close()
                    return None
                
                # Carica prima pagina
                page = pdf_document[0]
                
                # Converti in immagine ad alta risoluzione (300 DPI per OCR ottimale)
                # zoom = 300/72 = 4.166 (72 DPI è il default)
                zoom = 300 / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # Converti pixmap in bytes PNG
                img_bytes = pix.tobytes("png")
                pdf_document.close()
                
                # Usa i bytes PNG come content
                content = img_bytes
                
            except fitz.fitz.FileDataError as fitz_err:
                errore = f"PDF corrotto o non valido: {str(fitz_err)[:80]}"
                logger.error(f"Errore PyMuPDF per {nome_file}: {fitz_err}")
                st.session_state.files_con_errori[nome_file] = errore
                return None
            
            except Exception as pdf_err:
                errore = f"Errore conversione PDF: {str(pdf_err)[:100]}"
                logger.exception(f"Errore conversione PDF {nome_file}: {pdf_err}")
                st.session_state.files_con_errori[nome_file] = errore
                return None
        
        # Converti in base64
        return base64.b64encode(content).decode('utf-8')
    
    except Exception as e:
        errore = f"Errore lettura file: {str(e)[:100]}"
        logger.exception(f"Errore conversione file in immagine: {nome_file}")
        st.session_state.files_con_errori[nome_file] = errore
        return None



# ============================================================
# PARSING XML CORRETTO (BUGFIX GEMINI)
# ============================================================



def estrai_fornitore_xml(fattura):
    """
    Estrae il nome del fornitore gestendo sia società che persone fisiche.
    
    Priorità:
    1. Denominazione (società)
    2. Nome + Cognome (persona fisica) 
    3. Solo Nome (fallback)
    4. "Fornitore Sconosciuto"
    """
    try:
        # Estrai nodo Anagrafica
        anagrafica = safe_get(
            fattura,
            ['FatturaElettronicaHeader', 'CedentePrestatore', 'DatiAnagrafici', 'Anagrafica'],
            default=None,
            keep_list=False
        )
        
        if anagrafica is None:
            return 'Fornitore Sconosciuto'
        
        # Priorità 1: Denominazione (società)
        denominazione = safe_get(anagrafica, ['Denominazione'], default=None, keep_list=False)
        if denominazione and isinstance(denominazione, str) and denominazione.strip():
            fornitore = normalizza_stringa(denominazione)
            logger.debug(f"🏢 Fornitore estratto da Denominazione: {fornitore}")
            return fornitore
        
        # Priorità 2: Nome + Cognome (persona fisica)
        nome = safe_get(anagrafica, ['Nome'], default=None, keep_list=False)
        cognome = safe_get(anagrafica, ['Cognome'], default=None, keep_list=False)
        
        nome_str = nome.strip() if nome and isinstance(nome, str) else ""
        cognome_str = cognome.strip() if cognome and isinstance(cognome, str) else ""
        
        if nome_str and cognome_str:
            fornitore = f"{nome_str} {cognome_str}".upper()
            logger.debug(f"👤 Fornitore estratto da Nome+Cognome: {fornitore}")
            return fornitore
        elif cognome_str:  # Solo cognome
            fornitore = cognome_str.upper()
            logger.debug(f"👤 Fornitore estratto da Cognome: {fornitore}")
            return fornitore
        elif nome_str:  # Solo nome
            fornitore = nome_str.upper()
            logger.debug(f"👤 Fornitore estratto da Nome: {fornitore}")
            return fornitore
        
        # Fallback finale
        logger.warning("⚠️ Nessun campo fornitore trovato in Anagrafica")
        return 'Fornitore Sconosciuto'
        
    except Exception as e:
        logger.warning(f"⚠️ Errore estrazione fornitore: {e}")
        return 'Fornitore Sconosciuto'



def estrai_dati_da_xml(file_caricato):
    try:
        # Carica cache memoria globale SUBITO (1 volta sola per tutte le righe)
        current_user_id = st.session_state.get('user_data', {}).get('id')
        if current_user_id:
            carica_memoria_completa(current_user_id)
            logger.info("✅ Cache memoria precaricata per elaborazione XML")
        
        contenuto = file_caricato.read()
        doc = xmltodict.parse(contenuto)
        
        root_key = list(doc.keys())[0]
        fattura = doc[root_key]
        
        data_documento = safe_get(
            fattura,
            ['FatturaElettronicaBody', 'DatiGenerali', 'DatiGeneraliDocumento', 'Data'],
            default='N/A',
            keep_list=False
        )
        
        # Estrai fornitore con logica robusta (società + persone fisiche)
        fornitore = estrai_fornitore_xml(fattura)
        
        body = safe_get(fattura, ['FatturaElettronicaBody'], default={}, keep_list=False)
        
        linee = safe_get(
            body, 
            ['DatiBeniServizi', 'DettaglioLinee'], 
            default=[],
            keep_list=True
        )
        
        if not linee:
            linee = safe_get(body, ['DettaglioLinee'], default=[], keep_list=True)
        
        if isinstance(linee, dict):
            linee = [linee]
        
        memoria_ai = carica_memoria_ai()
        
        righe_prodotti = []
        for idx, riga in enumerate(linee, start=1):
            if not isinstance(riga, dict):
                continue
            
            try:
                codice_articolo = ""
                codice_articolo_raw = riga.get('CodiceArticolo', [])
                if isinstance(codice_articolo_raw, list) and len(codice_articolo_raw) > 0:
                    codice_articolo = codice_articolo_raw[0].get('CodiceValore', '')
                elif isinstance(codice_articolo_raw, dict):
                    codice_articolo = codice_articolo_raw.get('CodiceValore', '')
                
                descrizione_raw = riga.get('Descrizione', 'Articolo senza nome')
                descrizione = normalizza_stringa(descrizione_raw)
                
                quantita = float(riga.get('Quantita', 0) or 1)
                unita_misura = riga.get('UnitaMisura', '')
                prezzo_base = float(riga.get('PrezzoUnitario', 0))
                aliquota_iva = float(riga.get('AliquotaIVA', 0))
                totale_riga = float(riga.get('PrezzoTotale', 0))
                
                # 🎯 CALCOLA PREZZO EFFETTIVO (include sconti automaticamente)
                if quantita > 0 and totale_riga > 0:
                    # Usa il totale riga diviso quantità = prezzo reale pagato
                    prezzo_unitario = totale_riga / quantita
                else:
                    # Fallback: usa prezzo base se totale non disponibile
                    prezzo_unitario = prezzo_base
                    if totale_riga == 0:
                        totale_riga = quantita * prezzo_unitario
                
                # Arrotonda a 4 decimali per precisione
                prezzo_unitario = round(prezzo_unitario, 4)
                
                # 📊 LOGGING: Rileva sconti applicati
                if abs(prezzo_unitario - prezzo_base) > 0.01:
                    sconto_percentuale = ((prezzo_base - prezzo_unitario) / prezzo_base) * 100
                    logger.info(f"🎁 SCONTO rilevato: {descrizione[:40]} | "
                                f"Base: €{prezzo_base:.2f} → Effettivo: €{prezzo_unitario:.2f} "
                                f"({sconto_percentuale:.1f}%)")
                
                # ===== AUTO-CATEGORIZZAZIONE CON SISTEMA IBRIDO (RISPARMIA OPENAI) =====
                # Ottieni user_id per memoria ibrida
                current_user_id = st.session_state.get('user_data', {}).get('id')
                
                # Usa sistema completo: memoria (admin + locale + globale) + dizionario keyword
                # Risparmia chiamate OpenAI categorizzando automaticamente prodotti conosciuti
                # Se NON trova niente → restituisce "Da Classificare" (poi si usa AI)
                categoria_finale = categorizza_con_memoria(
                    descrizione=descrizione,
                    prezzo=prezzo_unitario,
                    quantita=quantita,
                    user_id=current_user_id
                )
                
                # Se è dicitura CERTA, NON salvare nel database
                if categoria_finale == "📝 NOTE E DICITURE":
                    logger.info(f"⊗ Riga ESCLUSA (dicitura): {descrizione}")
                    continue  # Salta al prossimo ciclo, non aggiunge questa riga
                # ===== FINE CATEGORIZZAZIONE =====
                
                # ===== CALCOLO PREZZO STANDARD INTELLIGENTE =====
                prezzo_std = calcola_prezzo_standard_intelligente(
                    descrizione=descrizione,
                    um=unita_misura,
                    prezzo_unitario=prezzo_unitario
                )
                # ===== FINE CALCOLO =====
                
                righe_prodotti.append({
                    'Numero_Riga': idx,
                    'Codice_Articolo': codice_articolo,
                    'Descrizione': descrizione,
                    'Quantita': quantita,
                    'Unita_Misura': unita_misura,
                    'Prezzo_Unitario': round(prezzo_unitario, 2),
                    'IVA_Percentuale': aliquota_iva,
                    'Totale_Riga': round(totale_riga, 2),
                    'Fornitore': fornitore,
                    'Categoria': categoria_finale,  # Usa categoria finale
                    'Data_Documento': data_documento,
                    'File_Origine': file_caricato.name,
                    'Prezzo_Standard': prezzo_std
                })
            except Exception as e:
                continue
        
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore lettura file caricato: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.warning(f"⚠️ File {file_caricato.name}: impossibile leggere")
        return []



# ============================================================
# ESTRAZIONE DATI CON VISION (PDF/IMMAGINI)
# ============================================================


def estrai_dati_da_scontrino_vision(file_caricato):
    """Estrae dati da scontrini/PDF usando OpenAI Vision."""
    try:
        file_caricato.seek(0)
        base64_image = converti_in_base64(file_caricato, file_caricato.name)
        if not base64_image:
            return []
        
        prompt = """Sei un esperto contabile per ristoranti italiani. Analizza questo documento (scontrino/fattura) ed estrai i dati.


INFORMAZIONI DA ESTRARRE:
1. **Fornitore**: Nome completo del fornitore. Può essere:
   - Società/Azienda (es. "METRO SRL", "CRAI", "EKAF")
   - Persona fisica/Professionista (es. "MARIO ROSSI", "Studio BIANCHI")
   Cerca in: Ragione Sociale, Denominazione, Cedente/Prestatore, Nome e Cognome
2. **Data**: Data del documento in formato YYYY-MM-DD
3. **Righe articoli**: Lista completa di TUTTI i prodotti acquistati


PER OGNI ARTICOLO:
- Descrizione (normalizzata in MAIUSCOLO)
- Quantità (numero, se non specificato usa 1.0)
- Prezzo unitario in € (numero decimale)
- Totale riga in € (numero decimale)


REGOLE IMPORTANTI:
- Estrai SOLO le righe articolo vere (ignora intestazioni, note, pubblicità)
- Se manca la quantità, usa 1.0
- Se manca prezzo unitario ma c'è il totale, calcola: prezzo_unitario = totale / quantità
- Normalizza descrizioni: "parmigiano reggiano" → "PARMIGIANO REGGIANO"
- Date italiane (es. 08/12/2024) converti in 2024-12-08


FORMATO RISPOSTA (SOLO JSON):
{
  "fornitore": "NOME FORNITORE",
  "data": "YYYY-MM-DD",
  "righe": [
    {
      "descrizione": "DESCRIZIONE ARTICOLO",
      "quantita": 2.5,
      "prezzo_unitario": 12.50,
      "totale": 31.25
    }
  ]
}


IMPORTANTE: Rispondi SOLO con il JSON, niente altro testo."""


        with st.spinner(f"🔍 Analizzo {file_caricato.name} con AI..."):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}}
                    ]
                }],
                max_tokens=1500,
                temperature=0
            )
        
        testo = response.choices[0].message.content.strip()


        # Rimuovi eventuali code-fence markdown
        try:
            # Rimuove triple backtick iniziali (con o senza "json")
            if testo.startswith('```'):
                lines = testo.split('\n')
                if lines[0].strip().lower() in ['```', '```json']:
                    lines = lines[1:]
                testo = '\n'.join(lines)
            
            # Rimuove triple backtick finali
            if testo.endswith('```'):
                lines = testo.split('\n')
                if lines[-1].strip() == '```':
                    lines = lines[:-1]
                testo = '\n'.join(lines)
        except Exception:
            # In caso di problemi, manteniamo il testo originale
            pass


        testo = testo.strip()
        
        try:
            dati = json.loads(testo)
        except json.JSONDecodeError:
            st.error(f"❌ Risposta Vision non valida per {file_caricato.name}")
            st.code(testo[:500])
            return []
        
        fornitore = normalizza_stringa(dati.get('fornitore', 'Fornitore Sconosciuto'))
        data_documento = dati.get('data', 'N/A')
        
        try:
            pd.to_datetime(data_documento)
        except Exception as e:
            data_documento = pd.Timestamp.now().strftime('%Y-%m-%d')
            st.warning(f"⚠️ Data non valida in {file_caricato.name}, uso data odierna: {e}")
        
        righe_prodotti = []
        memoria_ai = carica_memoria_ai()
        
        for idx, riga in enumerate(dati.get('righe', []), start=1):
            descrizione = normalizza_stringa(riga.get('descrizione', 'Articolo senza nome'))
            try:
                quantita = float(riga.get('quantita', 1.0))
            except (ValueError, TypeError):
                quantita = 1.0
            try:
                prezzo_unitario = float(riga.get('prezzo_unitario', 0))
            except (ValueError, TypeError):
                prezzo_unitario = 0
            
            # Unità di misura (default PZ per Vision)
            unita_misura = riga.get('unita_misura', 'PZ')
            
            try:
                totale_riga = float(riga.get('totale', 0))
            except (ValueError, TypeError):
                totale_riga = 0
            
            if totale_riga == 0 and prezzo_unitario > 0:
                totale_riga = quantita * prezzo_unitario
            if prezzo_unitario == 0 and totale_riga > 0 and quantita > 0:
                prezzo_unitario = totale_riga / quantita
            
            # ===== CATEGORIZZAZIONE CON SISTEMA IBRIDO (LOCALE + GLOBALE) =====
            # Ottieni user_id per memoria ibrida
            current_user_id = st.session_state.get('user_data', {}).get('id')
            
            if current_user_id:
                # Usa sistema priorità: LOCALE > GLOBALE > Da Classificare
                categoria_iniziale = ottieni_categoria_prodotto(descrizione, current_user_id)
            else:
                # Fallback se user_id non disponibile
                categoria_iniziale = memoria_ai.get(descrizione, "Da Classificare")
            
            # ===== CALCOLO PREZZO STANDARD INTELLIGENTE =====
            prezzo_std = calcola_prezzo_standard_intelligente(
                descrizione=descrizione,
                um=unita_misura,
                prezzo_unitario=prezzo_unitario
            )
            # ===== FINE CALCOLO =====
            
            righe_prodotti.append({
                'Numero_Riga': idx,
                'Codice_Articolo': '',
                'Descrizione': descrizione,
                'Quantita': quantita,
                'Unita_Misura': unita_misura,
                'Prezzo_Unitario': round(prezzo_unitario, 2),
                'IVA_Percentuale': 0,
                'Totale_Riga': round(totale_riga, 2),
                'Fornitore': fornitore,
                'Categoria': categoria_iniziale,
                'Data_Documento': data_documento,
                'File_Origine': file_caricato.name,
                'Prezzo_Standard': prezzo_std
            })
        
        if righe_prodotti:
            st.success(f"✅ Estratte {len(righe_prodotti)} righe da {file_caricato.name}")
        else:
            st.warning(f"⚠️ Nessuna riga trovata in {file_caricato.name}")
        
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore OpenAI Vision su: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.error(f"❌ Errore Vision su {file_caricato.name}: {str(e)}")
        return []



# ============================================================
# CLASSIFICAZIONE AI CON OUTPUT JSON STRUTTURATO
# ============================================================

# Configurazione OpenAI Retry
RETRIABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, APIError)
MAX_TOKENS_PER_BATCH = 12000  # Limite sicuro per evitare timeout

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRIABLE_ERRORS)
)
def classifica_con_ai(lista_descrizioni, lista_fornitori=None):
    """Classificazione AI con JSON strutturato + correzioni dizionario"""
    if not lista_descrizioni:
        return []


    memoria_ai = carica_memoria_ai()
    risultati = {}
    da_chiedere_gpt = []
    
    for desc in lista_descrizioni:
        if desc in memoria_ai:
            risultati[desc] = memoria_ai[desc]
        else:
            da_chiedere_gpt.append(desc)
    
    if not da_chiedere_gpt:
        # Memoria AI ha priorità massima (correzioni manuali utente)
        # Dizionario applicato SOLO se descrizione non in memoria
        return [
            risultati[d] if d in risultati 
            else applica_correzioni_dizionario(d, "NO FOOD")
            for d in lista_descrizioni
        ]


    prompt = f"""
Sei un esperto controller per ristoranti. Classifica questi articoli usando RAGIONAMENTO INTELLIGENTE.


CATEGORIE DISPONIBILI:
{', '.join(TUTTE_LE_CATEGORIE)}


RAGIONAMENTO INTELLIGENTE - ANALIZZA IL CONTESTO:

1. INGREDIENTI E PREPARAZIONI:
   - "ARAGOSTELLE" con pistacchio/cioccolato/crema = PASTICCERIA (dolci a forma di aragosta)
   - "ARAGOSTELLE" con limone/aglio/olio = PESCE (vero crostaceo)
   - "TARTUFI" con cioccolato/praline = PASTICCERIA (dolci)
   - "TARTUFI" con funghi/olio/nero = SPEZIE E AROMI (tartufo vero)

2. ANALISI PREZZO (se disponibile):
   - Prezzo €2-8/kg → probabile VERDURE, FRUTTA, SECCO
   - Prezzo €10-25/kg → probabile CARNE, PESCE, LATTICINI
   - Prezzo €30-100/kg → probabile PESCE PREGIATO, TARTUFO
   - Prezzo €0.50-2/pz → probabile PASTICCERIA, PRODOTTI DA FORNO

3. PAROLE CHIAVE DISAMBIGUANTI:
   - Con "CREMA", "PISTACCHIO", "CIOCCOLATO", "PRALINATO" → PASTICCERIA
   - Con "FRESCO", "DECONGELATO", "AL LIMONE" (pesce) → PESCE
   - Con "STAGIONATO", "DOP", "GRATTUGIATO" → LATTICINI
   - Con "SURGELATO", "FROZEN", "-18°C" → SURGELATI

4. FORMATO E CONFEZIONE:
   - "VASCHETTA", "MONOPORZIONE", "MIGNON" → spesso PASTICCERIA
   - "FILETTO", "TRANCIO", "SUPREMA" → CARNE o PESCE
   - "BUSTA", "SACCO", "CF" → SECCO o SPEZIE


REGOLE PRIORITARIE (come prima):
- FORMAGGI STAGIONATI (grana padano, parmigiano, pecorino, gorgonzola, taleggio) → LATTICINI
- PESCE (salmone, tonno, branzino, gamberi, calamari, orata, trota) → PESCE
- PRODOTTI DA FORNO (pane, focaccia, pizza, grissini, ciabatta, brioche, croissant) → PRODOTTI DA FORNO
- PASTA E RISO (spaghetti, penne, riso, farina) → SECCO
- SALSE E CREME (crema pistacchio, nutella, pesto, ketchup, maionese, besciamella) → SALSE E CREME
- PASSATE FRUTTA (passata albicocca, purea mango) → FRUTTA
- CONTORNI PREPARATI (contorno fantasia, contorno mediterraneo) → VERDURE
- SPEZIE (pepe, origano, curry, paprika, cannella) → SPEZIE E AROMI
- GELATI (gelato, sorbetto, semifreddo) → GELATI
- SURGELATI (surgelato, congelato, frozen) → SURGELATI
- CONSERVE (marmellata, confettura, olive, capperi, sottaceti) → CONSERVE
- MATERIALI CONSUMO (vaschette, tovaglioli, piatti, bicchieri, palette legno, sac a poche) → NO FOOD
- SERVIZI (google workspace, consulenze, diritti, canoni software, bonus, fatturazione) → SERVIZI E CONSULENZE
- UTENZE (energia elettrica, fibra, internet, gas, affitto, tim, vodafone, imposte) → UTENZE E LOCALI
- MANUTENZIONE (vassoi inox, carrelli, riparazioni, frigorifero, forno, climatizzatore) → MANUTENZIONE E ATTREZZATURE


ARTICOLI DA CLASSIFICARE:
{json.dumps(da_chiedere_gpt, ensure_ascii=False, indent=2)}


RISPONDI IN FORMATO JSON:
{{
  "classificazioni": [
    {{"descrizione": "testo_esatto", "categoria": "CATEGORIA"}},
    ...
  ]
}}
"""


    try:
        # Timeout dinamico basato su numero descrizioni
        timeout_seconds = min(60, max(30, len(da_chiedere_gpt) * 0.5))
        
        # Stima token per batch splitting automatico
        estimated_tokens = sum(len(d.split()) * 1.3 for d in da_chiedere_gpt) * 2
        
        if estimated_tokens > MAX_TOKENS_PER_BATCH:
            # Split automatico batch troppo grande
            mid = len(da_chiedere_gpt) // 2
            batch1_desc = da_chiedere_gpt[:mid]
            batch2_desc = da_chiedere_gpt[mid:]
            
            # Ricorsione con batch più piccoli
            risultati_batch1 = classifica_con_ai(batch1_desc, lista_fornitori)
            risultati_batch2 = classifica_con_ai(batch2_desc, lista_fornitori)
            
            # Merge risultati
            for i, desc in enumerate(batch1_desc):
                risultati[desc] = risultati_batch1[i]
            for i, desc in enumerate(batch2_desc):
                risultati[desc] = risultati_batch2[i]
            
            # Return anticipato dopo split
            memoria_originale = carica_memoria_ai()
            return [
                memoria_originale[d] if d in memoria_originale 
                else applica_correzioni_dizionario(d, risultati.get(d, "NO FOOD"))
                for d in lista_descrizioni
            ]
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000,
            response_format={"type": "json_object"},
            timeout=timeout_seconds
        )


        testo = response.choices[0].message.content.strip()
        dati = json.loads(testo)
        
        for item in dati.get("classificazioni", []):
            desc_ai = item.get("descrizione", "").strip()
            cat_ai = item.get("categoria", "NO FOOD").strip()
            
            if desc_ai in da_chiedere_gpt and cat_ai in TUTTE_LE_CATEGORIE:
                risultati[desc_ai] = cat_ai
            else:
                for desc_originale in da_chiedere_gpt:
                    if desc_ai.upper() in desc_originale.upper():
                        risultati[desc_originale] = cat_ai if cat_ai in TUTTE_LE_CATEGORIE else "NO FOOD"
                        break


        for desc in da_chiedere_gpt:
            if desc not in risultati:
                risultati[desc] = "NO FOOD"


        # ============================================
        # APPLICA CORREZIONI SMART CON PRIORITÀ
        # ============================================
        # 1. MEMORIA AI (correzioni manuali) → PRIORITÀ MASSIMA
        # 2. GPT + Dizionario → Per descrizioni nuove
        # 3. NO FOOD → Default
        memoria_originale = carica_memoria_ai()
        return [
            memoria_originale[d] if d in memoria_originale 
            else applica_correzioni_dizionario(d, risultati.get(d, "NO FOOD"))
            for d in lista_descrizioni
        ]


    except Exception as e:
        logger.exception("Errore durante elaborazione AI testo")
        st.error(f"Errore AI: {e}")
        return ["NO FOOD" for _ in lista_descrizioni]



# ============================================================
# FUNZIONI CALCOLO ALERT PREZZI - NUOVA VERSIONE SEMPLIFICATA
# ============================================================


@st.cache_data(ttl=None, show_spinner=False, max_entries=50)
def calcola_alert(df, soglia_minima, filtro_prodotto=""):
    """
    Calcola alert aumenti prezzi confrontando il PREZZO UNITARIO EFFETTIVO
    (con sconti applicati) tra acquisti successivi dello stesso prodotto.
    
    IMPORTANTE: Escludi SOLO le 3 categorie spese generali reali.
    NO FOOD È F&B! (tovaglioli, piatti usa e getta, pellicole = materiali consumo ristorante)
    
    Logica:
    - Confronta Prezzo Unit. Effettivo (€/PZ, €/Kg, etc.)
    - Indipendente da quantità acquistata
    - Rileva anche ribassi (valore negativo)
    
    Returns:
        DataFrame con alert ordinati per aumento decrescente
    """
    if df.empty:
        return pd.DataFrame()
    
    # Verifica colonne necessarie
    required_cols = ['Descrizione', 'Fornitore', 'DataDocumento', 'PrezzoUnitario', 'Categoria', 'FileOrigine']
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame()
    
    # ============================================================
    # FILTRO: ESCLUDI SOLO LE 3 CATEGORIE SPESE GENERALI
    # ============================================================
    # Le uniche 3 categorie NON F&B sono:
    # 1. MANUTENZIONE E ATTREZZATURE
    # 2. UTENZE E LOCALI
    # 3. SERVIZI E CONSULENZE
    #
    # TUTTO IL RESTO È F&B (incluso NO FOOD!)
    df_fb = df[~df['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
    
    if df_fb.empty:
        return pd.DataFrame()
    
    # ============================================================
    # FILTRO 2: SEARCH PRODOTTO (se specificato)
    # ============================================================
    if filtro_prodotto:
        df_fb = df_fb[df_fb['Descrizione'].str.contains(filtro_prodotto, case=False, na=False)]
    
    df = df_fb  # Usa solo prodotti F&B
    
    if df.empty:
        return pd.DataFrame()
    
    alert_list = []
    
    # Raggruppa per Descrizione + Fornitore
    for (prodotto, fornitore), group in df.groupby(['Descrizione', 'Fornitore']):
        # Ordina per data
        group = group.sort_values('DataDocumento')
        
        # Serve almeno 2 acquisti per confrontare
        if len(group) < 2:
            continue
        
        # Confronta acquisti consecutivi
        for i in range(1, len(group)):
            prev_row = group.iloc[i-1]
            curr_row = group.iloc[i]
            
            # 🎯 USA PREZZO UNITARIO EFFETTIVO (con sconti già applicati)
            prezzo_prec = prev_row['PrezzoUnitario']
            prezzo_nuovo = curr_row['PrezzoUnitario']
            
            # Validazione prezzi
            if prezzo_prec <= 0 or prezzo_nuovo <= 0:
                continue
            
            # 🛡️ PROTEZIONE: Ignora se troppo tempo tra acquisti (>180 giorni)
            try:
                data_prec = pd.to_datetime(prev_row['DataDocumento'])
                data_corr = pd.to_datetime(curr_row['DataDocumento'])
                giorni_diff = (data_corr - data_prec).days
                
                if giorni_diff > 180:
                    continue  # Troppo vecchio, ignora
            except (ValueError, TypeError):
                pass  # Se parsing date fallisce, continua comunque
            
            # CALCOLA SCOSTAMENTO PERCENTUALE
            aumento_perc = ((prezzo_nuovo - prezzo_prec) / prezzo_prec) * 100
            
            # Filtra per soglia minima (include anche ribassi negativi)
            if abs(aumento_perc) >= soglia_minima:
                # Usa nome file completo per N_Fattura
                file_origine = str(curr_row.get('FileOrigine', ''))
                
                alert_list.append({
                    'Prodotto': prodotto[:50],  # limita lunghezza
                    'Categoria': str(curr_row['Categoria'])[:15],
                    'Fornitore': str(fornitore)[:20],
                    'Data': curr_row['DataDocumento'],
                    'Prezzo_Prec': prezzo_prec,
                    'Prezzo_Nuovo': prezzo_nuovo,
                    'Aumento_Perc': aumento_perc,
                    'N_Fattura': file_origine
                })
    
    if not alert_list:
        return pd.DataFrame()
    
    df_alert = pd.DataFrame(alert_list)
    # Ordina per Aumento_Perc DECRESCENTE (maggiori aumenti prima, ribassi alla fine)
    df_alert = df_alert.sort_values('Aumento_Perc', ascending=False).reset_index(drop=True)
    
    return df_alert


def carica_sconti_e_omaggi(user_id, data_inizio, data_fine):
    """
    Carica sconti e omaggi ricevuti dal cliente nel periodo specificato.
    
    IMPORTANTE: Usa stesso periodo dei grafici (non fisso 30gg).
    
    Args:
        user_id: UUID cliente
        data_inizio: Data inizio periodo (datetime.date o string ISO)
        data_fine: Data fine periodo (datetime.date o string ISO)
        
    Returns:
        dict con:
        - sconti: DataFrame (prezzi negativi)
        - omaggi: DataFrame (prezzi €0)
        - totale_risparmiato: float
    """
    try:
        from datetime import datetime
        
        # Converti date a string ISO se necessario
        if hasattr(data_inizio, 'isoformat'):
            data_inizio = data_inizio.isoformat()
        if hasattr(data_fine, 'isoformat'):
            data_fine = data_fine.isoformat()
        
        # Query righe del cliente NEL PERIODO SPECIFICATO
        response = supabase.table('fatture')\
            .select('id, descrizione, categoria, fornitore, prezzo_unitario, quantita, totale_riga, data_documento, file_origine')\
            .eq('user_id', user_id)\
            .gte('data_documento', data_inizio)\
            .lte('data_documento', data_fine)\
            .execute()
        
        if not response.data:
            return {
                'sconti': pd.DataFrame(),
                'omaggi': pd.DataFrame(),
                'totale_risparmiato': 0.0
            }
        
        df = pd.DataFrame(response.data)
        
        # ============================================================
        # FILTRO: ESCLUDI SOLO LE 3 CATEGORIE SPESE GENERALI
        # ============================================================
        # Le uniche 3 categorie NON F&B sono:
        # 1. MANUTENZIONE E ATTREZZATURE
        # 2. UTENZE E LOCALI
        # 3. SERVIZI E CONSULENZE
        #
        # TUTTO IL RESTO È F&B (incluso NO FOOD!)
        # NO FOOD contiene materiali di consumo ristorante (tovaglioli, piatti, pellicole, etc.)
        df_food = df[~df['categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
        
        # Logging conteggi per verifica filtro
        logger.info(f"Sconti/Omaggi - Righe totali: {len(df)}")
        logger.info(f"Sconti/Omaggi - Righe FOOD filtrate: {len(df_food)}")
        logger.info(f"Sconti/Omaggi - Righe con prezzo <0: {len(df[df['prezzo_unitario'] < 0])}")
        logger.info(f"Sconti/Omaggi - Righe FOOD con prezzo <0: {len(df_food[df_food['prezzo_unitario'] < 0])}")
        
        # ============================================================
        # SCONTI: Prezzi negativi (SOLO F&B)
        # ============================================================
        df_sconti = df_food[df_food['prezzo_unitario'] < 0].copy()
        
        if not df_sconti.empty:
            # Calcola valore assoluto sconto
            df_sconti['importo_sconto'] = df_sconti['totale_riga'].abs()
            
            # Ordina per data decrescente
            df_sconti = df_sconti.sort_values('data_documento', ascending=False)
        
        # ============================================================
        # OMAGGI: Prezzi €0 (escludi descrizioni "omaggio" esplicite)
        # ============================================================
        pattern_omaggio = r'(?i)(omaggio|campione|prova|test|gratis|gratuito)'
        
        df_omaggi = df_food[
            (df_food['prezzo_unitario'] == 0) &
            (~df_food['descrizione'].str.contains(pattern_omaggio, na=False))
        ].copy()
        
        if not df_omaggi.empty:
            # Ordina per data
            df_omaggi = df_omaggi.sort_values('data_documento', ascending=False)
        
        # ============================================================
        # CALCOLO TOTALE RISPARMIATO
        # ============================================================
        totale_sconti = df_sconti['importo_sconto'].sum() if not df_sconti.empty else 0.0
        
        # Omaggi: stima valore medio categoria (se disponibile)
        # Per semplicità usiamo 0 (difficile stimare valore omaggi)
        totale_omaggi = 0.0
        
        totale_risparmiato = totale_sconti + totale_omaggi
        
        return {
            'sconti': df_sconti,
            'omaggi': df_omaggi,
            'totale_risparmiato': totale_risparmiato
        }
        
    except Exception as e:
        logger.error(f"Errore caricamento sconti/omaggi: {e}")
        return {
            'sconti': pd.DataFrame(),
            'omaggi': pd.DataFrame(),
            'totale_risparmiato': 0.0
        }


# ============================================================
# FUNZIONE PIVOT MENSILE
# ============================================================


@st.cache_data(ttl=None, show_spinner=False, max_entries=50)
def crea_pivot_mensile(df, index_col):
    if df.empty:
        return pd.DataFrame()
    
    df_temp = df.copy()
    df_temp['Data_DT'] = pd.to_datetime(df_temp['DataDocumento'], errors='coerce')


    # Controlla date invalide
    date_invalide = df_temp['Data_DT'].isna().sum()
    if date_invalide > 0:
        st.warning(
            f"⚠️ ATTENZIONE: {date_invalide} fatture hanno date non valide e non appariranno nei grafici temporali."
        )
        
        fatture_problema = df_temp[df_temp['Data_DT'].isna()][['Fornitore', 'Numero_Fattura', 'Data_Documento']].head(5)
        if not fatture_problema.empty:
            with st.expander("📋 Mostra fatture con date problematiche"):
                st.dataframe(fatture_problema)


    # Mesi in italiano maiuscolo
    mesi_ita = {
        1: 'GENNAIO', 2: 'FEBBRAIO', 3: 'MARZO', 4: 'APRILE',
        5: 'MAGGIO', 6: 'GIUGNO', 7: 'LUGLIO', 8: 'AGOSTO',
        9: 'SETTEMBRE', 10: 'OTTOBRE', 11: 'NOVEMBRE', 12: 'DICEMBRE'
    }
    df_temp['Mese'] = df_temp['Data_DT'].apply(
        lambda x: f"{mesi_ita[x.month]} {x.year}" if pd.notna(x) else ''
    )


    pivot = df_temp.pivot_table(
        index=index_col,
        columns='Mese',
        values='TotaleRiga',
        aggfunc='sum',
        fill_value=0
    )


    cols_sorted = sorted(list(pivot.columns))
    pivot = pivot[cols_sorted]
    pivot['TOTALE ANNO'] = pivot.sum(axis=1)
    pivot = pivot.reset_index()
    pivot = pivot.sort_values('TOTALE ANNO', ascending=False)


    return pivot


def genera_box_recap(num_righe, totale):
    return f"""
    <div style="background-color: #E3F2FD; padding: 17px 20px; border-radius: 8px; border: 2px solid #2196F3; display: inline-block; width: auto;">
        <p style="color: #1565C0; font-size: 18px; font-weight: bold; margin: 0; line-height: 1; white-space: nowrap;">
            📋 N. Righe Elaborate: {num_righe:,} | 💰 Totale: € {totale:.2f}
        </p>
    </div>
    """

# ============================================================
# FUNZIONE RENDERING STATISTICHE
# ============================================================



def mostra_statistiche(df_completo):
    """Mostra grafici, filtri e tabella dati"""
    
    # ===== 🔍 DEBUG CATEGORIZZAZIONE (SOLO ADMIN/IMPERSONIFICATO) =====
    if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
        with st.expander("🔍 DEBUG: Verifica Categorie", expanded=False):
            st.markdown("**Statistiche DataFrame Completo:**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Righe Totali", len(df_completo))
            with col2:
                st.metric("Categorie NULL", df_completo['Categoria'].isna().sum())
            with col3:
                st.metric("Categorie Vuote", (df_completo['Categoria'] == '').sum())
            
            st.markdown("**Conteggio per Categoria:**")
            conteggio_cat = df_completo.groupby('Categoria', dropna=False).size().reset_index(name='Righe')
            conteggio_cat = conteggio_cat.sort_values('Righe', ascending=False)
            st.dataframe(conteggio_cat, hide_index=True, use_container_width=True)
            
            st.markdown("**Sample 15 righe (verifica categoria):**")
            sample_df = df_completo[['FileOrigine', 'Descrizione', 'Categoria', 'Fornitore', 'TotaleRiga']].head(15)
            st.dataframe(sample_df, hide_index=True, use_container_width=True)
            
            # Test query diretta Supabase
            if st.button("🔄 Ricarica da Supabase (bypass cache)", key="debug_reload"):
                st.cache_data.clear()
                st.rerun()
    # ===== FINE DEBUG =====
    
    # ===== FILTRA DICITURE DA TUTTA L'ANALISI =====
    righe_prima = len(df_completo)
    na_prima = df_completo['Categoria'].isna().sum()
    logger.info(f"🔍 PRE-FILTRO DICITURE: {righe_prima} righe totali, {na_prima} con categoria NA")
    
    # 🔧 FIX: Usa fillna per mantenere righe con categoria NA/NULL (non sono diciture!)
    df_completo = df_completo[df_completo['Categoria'].fillna('') != '📝 NOTE E DICITURE'].copy()
    righe_dopo = len(df_completo)
    na_dopo = df_completo['Categoria'].isna().sum()
    logger.info(f"🔍 POST-FILTRO DICITURE: {righe_dopo} righe totali, {na_dopo} con categoria NA")
    
    if righe_prima > righe_dopo:
        logger.info(f"Diciture escluse dall'analisi: {righe_prima - righe_dopo} righe")
    
    if df_completo.empty:
        st.info("📭 Nessun dato disponibile dopo i filtri.")
        return
    # ===== FINE FILTRO DICITURE =====
    
    # Recupera user_id da session_state (necessario per get_fatture_stats)
    user_id = st.session_state.user_data["id"]
    
    # Lista fornitori che sono SEMPRE NO FOOD (telecom, utilities, tech)
    fornitori_no_food_keywords = [
        'TIM', 'TELECOM', 'VODAFONE', 'WIND', 'ILIAD', 'FASTWEB',
        'ENEL', 'ENI', 'A2A', 'EDISON', 'GAS', 'LUCE', 'ENERGIA',
        'AMAZON', 'MEDIAWORLD', 'UNIEURO', 'LEROY MERLIN',
        'BANCA', 'ASSICURAZ', 'POSTALE', 'POSTE ITALIANE'
    ]
    
    # Crea pattern per esclusione fornitori NO FOOD
    pattern_no_food = '|'.join(fornitori_no_food_keywords)
    mask_fornitori_no_food = df_completo['Fornitore'].str.upper().str.contains(pattern_no_food, na=False, regex=True)
    
    mask_spese = df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
    df_spese_generali_completo = df_completo[mask_spese].copy()
    
    # F&B: Escludi spese generali E fornitori sicuramente NO FOOD
    df_food_completo = df_completo[(~mask_spese) & (~mask_fornitori_no_food)].copy()
    
    # Spazio sotto il box arancione
    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)


    # ============================================
    # CATEGORIZZAZIONE AI
    # ============================================
    
    # Conta righe da classificare PRIMA del bottone
    maschera_ai = (
        df_completo['Categoria'].isna()
        | (df_completo['Categoria'] == 'Da Classificare')
    )
    righe_da_classificare = maschera_ai.sum()
    
    # ============================================================
    # LAYOUT: BOTTONE + TESTO INFORMATIVO
    # ============================================================
    col_btn, col_info = st.columns([1, 2])
    
    with col_btn:
        # Bottone categorizzazione AI (disabilitato se nulla da classificare)
        if st.button(
            "🧠 Avvia AI per Categorizzare", 
            use_container_width=True, 
            type="secondary",  # ← GRIGIO
            key="btn_ai_categorizza",
            disabled=(righe_da_classificare == 0)
        ):
            # ============================================================
            # VERIFICA FINALE (sicurezza)
            # ============================================================
            if righe_da_classificare == 0:
                st.warning("⚠️ Nessun prodotto da classificare")
                st.stop()
            
            # ============================================================
            # CHIAMATA AI (SOLO DESCRIZIONI DA CLASSIFICARE)
            # ============================================================
            with st.spinner(f"L'AI sta analizzando i tuoi prodotti..."):
                descrizioni_da_classificare = df_completo[maschera_ai]['Descrizione'].unique().tolist()
                fornitori_da_classificare = df_completo[maschera_ai]['Fornitore'].unique().tolist()

                if descrizioni_da_classificare:
                    with st.spinner(f"🧠 Classificazione AI in corso... ({len(descrizioni_da_classificare)} prodotti)"):
                        mappa_categorie = {}
                        chunk_size = 50
                        for i in range(0, len(descrizioni_da_classificare), chunk_size):
                            chunk = descrizioni_da_classificare[i:i+chunk_size]
                            cats = classifica_con_ai(chunk, fornitori_da_classificare)
                            for desc, cat in zip(chunk, cats):
                                mappa_categorie[desc] = cat
                                aggiorna_memoria_ai(desc, cat)
                                
                                # Salva anche in memoria GLOBALE su Supabase
                                try:
                                    from datetime import datetime
                                    supabase.table('prodotti_master').upsert({
                                        'descrizione': desc,
                                        'categoria': cat,
                                        'volte_visto': 1,
                                        'classificato_da': 'AI',
                                        'updated_at': datetime.now().isoformat()
                                    }, on_conflict='descrizione').execute()
                                    
                                    # Invalida cache per forzare ricaricamento
                                    invalida_cache_memoria()
                                    
                                    logger.info(f"💾 GLOBALE salvato: '{desc[:40]}...' → {cat}")
                                except Exception as e:
                                    logger.error(f"Errore salvataggio globale '{desc[:40]}...': {e}")


                    # Aggiorna categorie su Supabase
                    try:
                        user_id = st.session_state.user_data["id"]
                        
                        for desc, cat in mappa_categorie.items():
                            # Aggiorna tutte le righe con questa descrizione
                            supabase.table("fatture").update(
                                {"categoria": cat}
                            ).eq("user_id", user_id).eq("descrizione", desc).execute()
                        
                        st.toast(f"✅ Categorizzati {len(descrizioni_da_classificare)} prodotti su Supabase!")
                        logger.info(f"🔄 CATEGORIZZAZIONE AI: Aggiornate {len(descrizioni_da_classificare)} descrizioni")
                        
                        # Pulisci cache PRIMA del delay per garantire ricaricamento
                        st.cache_data.clear()
                        invalida_cache_memoria()
                        
                        # Delay per garantire propagazione modifiche su Supabase
                        time.sleep(2)
                        
                        # Rerun per ricaricare dati freschi
                        st.rerun()
                        
                    except Exception as e:
                        logger.exception("Errore aggiornamento categorie AI su Supabase")
                        st.error(f"❌ Errore aggiornamento categorie: {e}")
    
    with col_info:
        # ============================================================
        # BOX INFO CON ALTEZZA FISSA = ALTEZZA BOTTONE (38px)
        # ============================================================
        if righe_da_classificare == 0:
            st.markdown("""
            <div style="
                background-color: #d4edda;
                border-left: 4px solid #28a745;
                padding: 0px 15px;
                border-radius: 4px;
                height: 38px;
                display: flex;
                align-items: center;
                margin-top: 0px;
            ">
                <span style="color: #155724; font-weight: 600; font-size: 14px;">✅ NON CI SONO prodotti da categorizzare</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="
                background-color: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 0px 15px;
                border-radius: 4px;
                height: 38px;
                display: flex;
                align-items: center;
                margin-top: 0px;
            ">
                <span style="color: #856404; font-weight: 600; font-size: 14px;">⚠️ CI SONO {righe_da_classificare} prodotti da categorizzare</span>
            </div>
            """, unsafe_allow_html=True)
    
    # ============================================
    # FILTRO DROPDOWN PERIODO
    # ============================================
    st.subheader("📅 Filtra per Periodo")
    
    # Calcola date dinamiche per i filtri
    oggi = pd.Timestamp.now()
    oggi_date = oggi.date()
    inizio_mese = oggi.replace(day=1).date()
    inizio_trimestre = oggi.replace(month=((oggi.month-1)//3)*3+1, day=1).date()
    inizio_semestre = oggi.replace(month=1 if oggi.month <= 6 else 7, day=1).date()
    inizio_anno = oggi.replace(month=1, day=1).date()
    
    # Opzioni filtro periodo
    periodo_options = [
        "📅 Mese in Corso",
        "📊 Trimestre in Corso",
        "📈 Semestre in Corso",
        "🗓️ Anno in Corso",
        "📋 Anno Scorso",
        "⚙️ Periodo Personalizzato"
    ]
    
    # Default: Mese in Corso
    if 'periodo_dropdown' not in st.session_state:
        st.session_state.periodo_dropdown = " Mese in Corso"
    
    # Selectbox
    periodo_selezionato = st.selectbox(
        "",
        options=periodo_options,
        index=periodo_options.index(st.session_state.periodo_dropdown) if st.session_state.periodo_dropdown in periodo_options else 0,
        key="filtro_periodo_main"
    )
    
    # Aggiorna session state
    st.session_state.periodo_dropdown = periodo_selezionato
    
    # Gestione logica periodo
    data_inizio_filtro = None
    data_fine_filtro = oggi_date
    
    if periodo_selezionato == " Mese in Corso":
        data_inizio_filtro = inizio_mese
        label_periodo = f"Mese in corso ({inizio_mese.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == " Trimestre in Corso":
        data_inizio_filtro = inizio_trimestre
        label_periodo = f"Trimestre in corso ({inizio_trimestre.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == " Semestre in Corso":
        data_inizio_filtro = inizio_semestre
        label_periodo = f"Semestre in corso ({inizio_semestre.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == " Anno in Corso":
        data_inizio_filtro = inizio_anno
        label_periodo = f"Anno in corso ({inizio_anno.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📋 Anno Scorso":
        inizio_anno_scorso = (oggi.replace(year=oggi.year - 1, month=1, day=1)).date()
        fine_anno_scorso = (oggi.replace(year=oggi.year - 1, month=12, day=31)).date()
        data_inizio_filtro = inizio_anno_scorso
        data_fine_filtro = fine_anno_scorso
        label_periodo = f"Anno scorso ({inizio_anno_scorso.strftime('%d/%m/%Y')} → {fine_anno_scorso.strftime('%d/%m/%Y')})"
    
    else:  # Periodo Personalizzato
        st.markdown("##### Seleziona Range Date")
        col_da, col_a = st.columns(2)
        
        # Inizializza date personalizzate se non esistono
        if 'data_inizio_filtro' not in st.session_state:
            st.session_state.data_inizio_filtro = inizio_anno
        if 'data_fine_filtro' not in st.session_state:
            st.session_state.data_fine_filtro = oggi_date
        
        with col_da:
            data_inizio_custom = st.date_input(
                "📅 Da", 
                value=st.session_state.data_inizio_filtro, 
                key="data_da_custom"
            )
        
        with col_a:
            data_fine_custom = st.date_input(
                "📅 A", 
                value=st.session_state.data_fine_filtro, 
                key="data_a_custom"
            )
        
        # Valida date
        if data_inizio_custom > data_fine_custom:
            st.error("⚠️ La data iniziale deve essere precedente alla data finale!")
            data_inizio_filtro = st.session_state.data_inizio_filtro
            data_fine_filtro = st.session_state.data_fine_filtro
        else:
            # Salva le date valide
            st.session_state.data_inizio_filtro = data_inizio_custom
            st.session_state.data_fine_filtro = data_fine_custom
            data_inizio_filtro = data_inizio_custom
            data_fine_filtro = data_fine_custom
        
        label_periodo = f"{data_inizio_filtro.strftime('%d/%m/%Y')} → {data_fine_filtro.strftime('%d/%m/%Y')}"
    
    # Fallback se data_inizio_filtro è None (non dovrebbe mai accadere)
    if data_inizio_filtro is None:
        data_inizio_filtro = inizio_mese
        label_periodo = "Periodo non valido"
    
    # APPLICA FILTRO AI DATI
    df_food_completo["Data_DT"] = pd.to_datetime(df_food_completo["DataDocumento"], errors='coerce').dt.date
    mask = (df_food_completo["Data_DT"] >= data_inizio_filtro) & (df_food_completo["Data_DT"] <= data_fine_filtro)
    df_food = df_food_completo[mask].copy()
    
    df_spese_generali_completo["Data_DT"] = pd.to_datetime(df_spese_generali_completo["DataDocumento"], errors='coerce').dt.date
    mask_spese = (df_spese_generali_completo["Data_DT"] >= data_inizio_filtro) & (df_spese_generali_completo["Data_DT"] <= data_fine_filtro)
    df_spese_generali = df_spese_generali_completo[mask_spese].copy()
    
    # Calcola giorni nel periodo
    giorni = (data_fine_filtro - data_inizio_filtro).days + 1
    
    # Stats globali
    stats_totali = get_fatture_stats(user_id)
    df_completo_filtrato = df_completo[df_completo['DataDocumento'].isin(df_food['DataDocumento'])]
    num_doc_filtrati = df_completo_filtrato['FileOrigine'].nunique()
    
    # Mostra info periodo
    st.info(f"🔍 **{label_periodo}** ({giorni} giorni) | Righe F&B: **{len(df_food):,}** | Righe Totali: {stats_totali['num_righe']:,} | Fatture: {num_doc_filtrati} di {stats_totali['num_uniche']}")
    
    if df_food.empty and df_spese_generali.empty:
        st.warning("⚠️ Nessuna fattura nel periodo selezionato")
        st.stop()
    
    st.markdown("---")


    # KPI
    col1, col2, col3 = st.columns(3)
    col1.metric("🍽️ Spesa F&B", f"€ {df_food['TotaleRiga'].sum():.2f}")
    col2.metric("🏢 Spese Generali", f"€ {df_spese_generali['TotaleRiga'].sum():.2f}")
    col3.metric("🏪 N. Fornitori", f"{df_food['Fornitore'].nunique()}")


    c1, c2 = st.columns(2)


    # GRAFICI
    with c1:
        st.subheader("📊 Spesa per Categoria")
        spesa_cat = (
            df_food.groupby("Categoria")["TotaleRiga"]
              .sum()
              .reset_index()
              .sort_values("TotaleRiga", ascending=False)
        )


        fig1 = px.bar(
            spesa_cat,
            x="Categoria",
            y="TotaleRiga",
            text="TotaleRiga",
            color="Categoria",
            color_discrete_sequence=COLORI_PLOTLY,
        )


        fig1.update_traces(
            texttemplate="€ %{text:.2f}",
            textposition="outside",
            textfont_size=18,
            hovertemplate="<b>%{x}</b><br>Spesa: € %{y:.2f}<extra></extra>",
        )


        fig1.update_layout(
            font=dict(size=20),
            xaxis_title="Categoria",
            yaxis_title="Spesa (€)",
            yaxis_title_font=dict(size=24, color="#333"),
            xaxis=dict(tickfont=dict(size=1), showticklabels=False),
            yaxis=dict(tickfont=dict(size=18)),
            showlegend=False,
            height=600,
            hoverlabel=dict(bgcolor="white", font_size=16, font_family="Arial"),
        )


        st.plotly_chart(
            fig1,
            use_container_width=True,
            key="grafico_categorie",
            config={"displayModeBar": False},
        )


    with c2:
        st.subheader("🏪 Spesa per Fornitore")
        spesa_forn = (
            df_food.groupby("Fornitore")["TotaleRiga"]
              .sum()
              .reset_index()
              .sort_values("TotaleRiga", ascending=False)
        )


        fig2 = px.bar(
            spesa_forn,
            x="Fornitore",
            y="TotaleRiga",
            text="TotaleRiga",
            color="Fornitore",
            color_discrete_sequence=COLORI_PLOTLY,
        )


        fig2.update_traces(
            texttemplate="€ %{text:.2f}",
            textposition="outside",
            textfont_size=18,
            hovertemplate="<b>%{x}</b><br>Spesa: € %{y:.2f}<extra></extra>",
        )


        fig2.update_layout(
            font=dict(size=20),
            xaxis_title="Fornitore",
            yaxis_title="Spesa (€)",
            yaxis_title_font=dict(size=24, color="#333"),
            xaxis=dict(tickfont=dict(size=1), showticklabels=False),
            yaxis=dict(tickfont=dict(size=18)),
            showlegend=False,
            height=600,
            hoverlabel=dict(bgcolor="white", font_size=16, font_family="Arial"),
        )


        st.plotly_chart(
            fig2,
            use_container_width=True,
            key="grafico_fornitori",
            config={"displayModeBar": False},
        )


    st.markdown("---")
    
    # 🎨 NAVIGAZIONE CON BOTTONI COLORATI (invece di tab)
    if 'sezione_attiva' not in st.session_state:
        st.session_state.sezione_attiva = "dettaglio"
    if 'is_loading' not in st.session_state:
        st.session_state.is_loading = False
    
    st.markdown("### 📊 Naviga tra le Sezioni")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if st.button("📦 DETTAGLIO\nARTICOLI", key="btn_dettaglio", use_container_width=True, 
                     type="primary" if st.session_state.sezione_attiva == "dettaglio" else "secondary"):
            if st.session_state.sezione_attiva != "dettaglio":
                st.session_state.sezione_attiva = "dettaglio"
                st.session_state.is_loading = True
                st.rerun()
    
    with col2:
        if st.button("🚨 ALERT\nARTICOLI (F&B)", key="btn_alert", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "alert" else "secondary"):
            if st.session_state.sezione_attiva != "alert":
                st.session_state.sezione_attiva = "alert"
                st.session_state.is_loading = True
                st.rerun()
    
    with col3:
        if st.button("📈 CATEGORIE\n(F&B)", key="btn_categorie", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "categorie" else "secondary"):
            if st.session_state.sezione_attiva != "categorie":
                st.session_state.sezione_attiva = "categorie"
                st.session_state.is_loading = True
                st.rerun()
    
    with col4:
        if st.button("🚚 FORNITORI\n(F&B)", key="btn_fornitori", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "fornitori" else "secondary"):
            if st.session_state.sezione_attiva != "fornitori":
                st.session_state.sezione_attiva = "fornitori"
                st.session_state.is_loading = True
                st.rerun()
    
    with col5:
        if st.button("🏢 SPESE\nGENERALI", key="btn_spese", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "spese" else "secondary"):
            if st.session_state.sezione_attiva != "spese":
                st.session_state.sezione_attiva = "spese"
                st.session_state.is_loading = True
                st.rerun()
    
    # CSS per bottoni colorati personalizzati
    st.markdown("""
        <style>
        div[data-testid="column"] button[kind="secondary"] {
            background-color: #f0f2f6 !important;
            color: #31333F !important;
            border: 2px solid #e0e0e0 !important;
        }
        div[data-testid="column"] button[kind="secondary"]:hover {
            background-color: #e0e5eb !important;
            border-color: #0ea5e9 !important;
        }
        div[data-testid="column"] button[kind="primary"] {
            background-color: #0ea5e9 !important;
            color: white !important;
            border: 2px solid #0284c7 !important;
            font-weight: bold !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Resetta il flag is_loading dopo il rerun
    if st.session_state.is_loading:
        st.session_state.is_loading = False
    
    # ========================================================
    # SEZIONE 1: DETTAGLIO ARTICOLI
    # ========================================================
    if st.session_state.sezione_attiva == "dettaglio":
        # Placeholder se dataset mancanti/vuoti
        if ('df_completo' not in locals()) or ('df_food' not in locals()) or ('df_spese_generali' not in locals()) or df_completo.empty:
            st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


        
        # 📦 SEZIONE DETTAGLIO ARTICOLI
        st.markdown("### 📦 Dettaglio Articoli")
        st.caption("🔍 Analisi dettagliata degli articoli con filtri per tipologia e ricerca avanzata.")
        
        # Avviso salvataggio modifiche
        st.warning("⚠️ ATTENZIONE: Se hai modificato dati nella tabella, **clicca SALVA** prima di cambiare filtro, altrimenti le modifiche andranno perse!")
        
        # ===== FILTRO TIPO PRODOTTI =====
        col_tipo, col_search_type, col_search, col_save = st.columns([2, 2, 3, 2])
        
        with col_tipo:
            tipo_filtro = st.selectbox(
                "📦 Tipo Prodotti:",
                options=["Food & Beverage", "Spese Generali", "Tutti"],
                key="tipo_filtro_prodotti",
                help="Filtra per tipologia di prodotto"
            )

        with col_search_type:
            search_type = st.selectbox(
                "🔍 Cerca per:",
                options=["Prodotto", "Categoria", "Fornitore"],
                key="search_type"
            )


        with col_search:
            if search_type == "Prodotto":
                placeholder_text = "Es: pollo, salmone, caffè..."
                label_text = "🔍 Cerca nella descrizione:"
            elif search_type == "Categoria":
                placeholder_text = "Es: CARNE, PESCE, CAFFÈ..."
                label_text = "🔍 Cerca per categoria:"
            else:
                placeholder_text = "Es: EKAF, PREGIS..."
                label_text = "🔍 Cerca per fornitore:"
            
            search_term = st.text_input(
                label_text,
                placeholder=placeholder_text,
                key="search_prodotto"
            )


        with col_save:
            st.markdown("<br>", unsafe_allow_html=True)
            salva_modifiche = st.button(
                "💾 Salva Modifiche Categorie",
                type="primary",
                use_container_width=True,
                key="salva_btn",
                help="Salva le modifiche manuali che hai fatto nella tabella (es. cambi categoria da 'SECCO' a 'VERDURE')"
            )
        
        # ✅ FILTRO DINAMICO IN BASE ALLA SELEZIONE
        fornitori_no_food = [
            'TIM', 'TELECOM', 'VODAFONE', 'WIND', 'ILIAD', 'FASTWEB',
            'ENEL', 'ENI', 'A2A', 'EDISON', 'GAS', 'LUCE',
            'AMAZON', 'MEDIAWORLD', 'UNIEURO', 'LEROY MERLIN',
            'BANCA', 'ASSICURAZ', 'POSTALE', 'GOOGLE'
        ]
        
        if tipo_filtro == "Food & Beverage":
            # Solo F&B + NO FOOD, escludi spese generali
            df_base = df_completo[
                (~df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)) &
                (~df_completo['Fornitore'].str.upper().str.contains('|'.join(fornitori_no_food), na=False))
            ].copy()
        elif tipo_filtro == "Spese Generali":
            # Solo spese generali
            df_base = df_completo[
                df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
            ].copy()
        else:  # "Tutti"
            # Tutti i prodotti, escludi solo fornitori non-food
            df_base = df_completo[
                ~df_completo['Fornitore'].str.upper().str.contains('|'.join(fornitori_no_food), na=False)
            ].copy()
        
        # Applica struttura colonne nell'ordine corretto
        cols_base = ['FileOrigine', 'DataDocumento', 'Fornitore', 'Descrizione',
                    'Quantita', 'UnitaMisura', 'PrezzoUnitario', 'IVAPercentuale', 'TotaleRiga', 'Categoria']
        
        # Aggiungi prezzo_standard se esiste nel database
        if 'PrezzoStandard' in df_base.columns:
            cols_base.append('PrezzoStandard')
        
        df_editor = df_base[cols_base].copy()
        
        # 🔧 CONVERTI pd.NA/vuoti in "Da Classificare" (placeholder visibile per celle non categorizzate)
        # SelectboxColumn ora include "Da Classificare" come opzione valida
        # L'AI li categorizza correttamente quando si usa "AVVIA AI PER CATEGORIZZARE"
        if 'Categoria' in df_editor.columns:
            # Converti pd.NA, None, stringhe vuote in "Da Classificare"
            # NON toccare "SECCO" perché è una categoria valida (pasta, riso, farina)
            
            vuote_prima = df_editor['Categoria'].apply(lambda x: pd.isna(x) or x is None or str(x).strip() == '').sum()
            
            df_editor['Categoria'] = df_editor['Categoria'].apply(
                lambda x: 'Da Classificare' if pd.isna(x) or x is None or str(x).strip() == '' else x
            )
            
            da_class_dopo = (df_editor['Categoria'] == 'Da Classificare').sum()
            
            if vuote_prima > 0 or da_class_dopo > 0:
                logger.info(f"📋 CATEGORIA: {vuote_prima} vuote → {da_class_dopo} 'Da Classificare'")
                print(f"📋 DEBUG CATEGORIA: {vuote_prima} vuote → {da_class_dopo} 'Da Classificare'")
        
        # Inizializza colonna prezzo_standard se non esiste
        if 'PrezzoStandard' not in df_editor.columns:
            df_editor['PrezzoStandard'] = None


        if search_term:
            if search_type == "Prodotto":
                mask = df_editor['Descrizione'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe con '{search_term}' nella descrizione")
            elif search_type == "Categoria":
                mask = df_editor['Categoria'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe nella categoria '{search_term}'")
            else:
                mask = df_editor['Fornitore'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe del fornitore '{search_term}'")
            
            df_editor = df_editor[mask]
        
        # ===== CALCOLO INTELLIGENTE PREZZO STANDARDIZZATO =====
        
        # Calcola prezzo_standard per ogni riga F&B
        for idx in df_editor.index:
            row = df_editor.loc[idx]
            
            # SKIP se già presente (manuale)
            prezzo_attuale = row.get('PrezzoStandard')
            if prezzo_attuale is not None and pd.notna(prezzo_attuale) and prezzo_attuale > 0:
                continue
            
            # Calcola intelligentemente
            prezzo_std = calcola_prezzo_standard_intelligente(
                descrizione=row.get('Descrizione'),
                um=row.get('UnitaMisura'),
                prezzo_unitario=row.get('PrezzoUnitario')
            )
            
            if prezzo_std is not None:
                df_editor.at[idx, 'PrezzoStandard'] = prezzo_std
        
        # ===== FINE CALCOLO =====
        
        st.info("""
🤖 **Calcolo Automatico Prezzo di Listino**  
L'app estrae automaticamente dalla descrizione e calcola il prezzo di Listino.  
✏️ Se il calcolo non è disponibile, puoi modificarlo manualmente nella colonna Listino.
        """)


        num_righe = len(df_editor)
        altezza_dinamica = min(max(num_righe * 35 + 50, 200), 500)

        # ===== CARICA CATEGORIE DINAMICHE =====
        categorie_disponibili = carica_categorie_da_db()
        
        # Rimuovi TUTTI i valori non validi (None, vuoti, solo spazi)
        categorie_disponibili = [
            cat for cat in categorie_disponibili 
            if cat is not None and str(cat).strip() != ''
        ]
        
        # Rimuovi duplicati mantenendo l'ordine
        categorie_temp = []
        for cat in categorie_disponibili:
            if cat not in categorie_temp:
                categorie_temp.append(cat)
        categorie_disponibili = categorie_temp
        
        # ⭐ AGGIUNGI "Da Classificare" come prima opzione (per celle non ancora categorizzate)
        # NON ordinare! carica_categorie_da_db() restituisce già l'ordine corretto:
        # 1. NOTE E DICITURE
        # 2. Spese generali (NO FOOD, MANUTENZIONE, ecc.)
        # 3. Prodotti alfabetici
        categorie_disponibili = ['Da Classificare'] + categorie_disponibili
        
        # ✅ "Da Classificare" è ora un'opzione valida - le celle non categorizzate la mostrano chiaramente
        
        # � FIX CELLE BIANCHE ULTRA-AGGRESSIVO (Streamlit bug workaround)
        # Se una cella ha un valore NON nelle opzioni, Streamlit la mostra VUOTA
        # FORZA che ogni categoria nel DataFrame sia nelle opzioni disponibili
        categorie_valide_set = set(categorie_disponibili)
        
        def valida_categoria(cat):
            """Assicura che categoria sia nelle opzioni disponibili"""
            if pd.isna(cat) or cat is None or str(cat).strip() == '':
                return 'Da Classificare'
            cat_str = str(cat).strip()
            if cat_str not in categorie_valide_set:
                logger.warning(f"⚠️ Categoria '{cat_str}' non nelle opzioni! → 'Da Classificare'")
                return 'Da Classificare'
            return cat_str
        
        # Applica validazione a TUTTE le categorie
        df_editor['Categoria'] = df_editor['Categoria'].apply(valida_categoria)
        
        # Log finale per debug
        invalid_count = (df_editor['Categoria'] == 'Da Classificare').sum()
        logger.info(f"📋 VALIDAZIONE: {invalid_count} celle con 'Da Classificare' (valide: {len(df_editor) - invalid_count})")
        print(f"📋 DEBUG: {invalid_count} 'Da Classificare', {len(df_editor) - invalid_count} categorizzate")
        
        # �🔒 FILTRA "NOTE E DICITURE" per utenti NON admin
        # Solo admin e impersonificati possono usare questa categoria
        is_admin_or_impersonating = (
            st.session_state.get('user_is_admin', False) or 
            st.session_state.get('impersonating', False)
        )
        
        if not is_admin_or_impersonating:
            # Rimuovi "NOTE E DICITURE" dalla lista disponibile per clienti
            categorie_disponibili = [
                cat for cat in categorie_disponibili 
                if 'NOTE E DICITURE' not in cat.upper() and 'DICITURE' not in cat.upper()
            ]
            logger.info("🔒 Categoria 'NOTE E DICITURE' nascosta per utente non-admin")
        
        # ⚡ ASSICURA che "Da Classificare" sia SEMPRE presente (anche dopo filtri)
        if 'Da Classificare' not in categorie_disponibili:
            categorie_disponibili = ['Da Classificare'] + categorie_disponibili
            logger.info("⚡ 'Da Classificare' ri-aggiunto dopo filtri")
        
        # ✅ Le categorie vengono normalizzate automaticamente al caricamento
        # Migrazione vecchi nomi → nuovi nomi avviene in carica_e_prepara_dataframe()

        edited_df = st.data_editor(
            df_editor,
            column_config={
                "DataDocumento": st.column_config.TextColumn("Data", disabled=True),
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria",
                    help="Seleziona la categoria corretta (le celle 'Da Classificare' devono essere categorizzate)",
                    width="medium",
                    options=categorie_disponibili,
                    required=False
                ),
                "TotaleRiga": st.column_config.NumberColumn("Totale (€)", format="€ %.2f", disabled=True),
                "PrezzoUnitario": st.column_config.NumberColumn("Prezzo Unit.", format="€ %.2f", disabled=True),
                "Descrizione": st.column_config.TextColumn("Descrizione", disabled=True),
                "Fornitore": st.column_config.TextColumn("Fornitore", disabled=True),
                "FileOrigine": st.column_config.TextColumn("File", disabled=True),
                "Quantita": st.column_config.NumberColumn("Q.tà", disabled=True),
                "UnitaMisura": st.column_config.TextColumn("U.M.", disabled=True, width="small"),
                "PrezzoStandard": st.column_config.NumberColumn(
                    "LISTINO",
                    help="Prezzo di listino standardizzato - calcolato automaticamente per confronti. Puoi modificarlo manualmente.",
                    format="€%.2f",
                    min_value=0.01,
                    max_value=10000,
                    step=0.01,
                    width="small"
                )
            },
            hide_index=True,
            use_container_width=True,
            height=altezza_dinamica,
            key="editor_dati"
        )
        
        st.markdown("""
            <style>
            [data-testid="stDownloadButton"] {
                margin-top: 10px !important;
            }
            [data-testid="stDownloadButton"] button {
                background-color: #28a745 !important;
                color: white !important;
                font-weight: 600 !important;
                font-size: 13px !important;
                border-radius: 6px !important;
                border: none !important;
                width: 140px !important;
                height: 38px !important;
                padding: 0 !important;
            }
            [data-testid="stDownloadButton"] button:hover {
                background-color: #218838 !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        totale_tabella = edited_df['TotaleRiga'].sum()
        num_righe = len(edited_df)
        
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown(genera_box_recap(num_righe, totale_tabella), unsafe_allow_html=True)
        
        with col_right:
            df_export = edited_df.copy()
            
            # 🧼 STEP 1: NORMALIZZA Unità di Misura (PRIMA di tutto)
            um_mapping = {
                # PESO
                'KG': 'KG', 'KG.': 'KG', 'Kg': 'KG', 'kg': 'KG',
                'KILOGRAMMI': 'KG', 'Kilogrammi': 'KG', 'kilogrammi': 'KG',
                'GR': 'GR', 'Gr': 'GR', 'gr': 'GR', 'GRAMMI': 'GR', 'Grammi': 'GR',
                # LITRI
                'LT': 'LT', 'Lt': 'LT', 'lt': 'LT', 'LT.': 'LT',
                'LITRI': 'LT', 'Litri': 'LT', 'litri': 'LT', 'LITRO': 'LT',
                'L': 'LT', 'l': 'LT',
                'ML': 'ML', 'ml': 'ML', 'MILLILITRI': 'ML',
                # PEZZI/NUMERO
                'PZ': 'PZ', 'Pz': 'PZ', 'pz': 'PZ',
                'NR': 'PZ', 'Nr': 'PZ', 'nr': 'PZ', 'NR.': 'PZ',
                'NUMERO': 'PZ', 'Numero': 'PZ', 'numero': 'PZ',
                'PEZZI': 'PZ', 'Pezzi': 'PZ', 'pezzi': 'PZ', 'PEZZO': 'PZ',
                # CONFEZIONI
                'CT': 'CT', 'Ct': 'CT', 'ct': 'CT', 'CARTONE': 'CT',
                # FUSTI
                'FS': 'FS', 'Fs': 'FS', 'fs': 'FS', 'FUSTO': 'FS',
            }
            
            if 'UnitaMisura' in df_export.columns:
                # Rimuovi spazi e normalizza
                df_export['UnitaMisura'] = df_export['UnitaMisura'].astype(str).str.strip()
                df_export['UnitaMisura'] = df_export['UnitaMisura'].map(lambda x: um_mapping.get(x, x))
            
            # 🧼 STEP 2: FILTRA righe informative (DDT, CASSA, BOLLO)
            righe_prima = len(df_export)
            df_export = df_export[
                (~df_export['Descrizione'].str.contains('DDT|DIT|BOLLO|CASSA', na=False, case=False)) &
                (df_export['TotaleRiga'] != 0)
            ]
            righe_dopo = len(df_export)
            righe_filtrate = righe_prima - righe_dopo
            
            if righe_filtrate > 0:
                logger.info(f"✅ Export: filtrate {righe_filtrate} righe informative (DDT/CASSA/BOLLO)")
            
            # 🧼 STEP 3: RICALCOLA Prezzo Standard (DOPO normalizzazione U.M.)
            if 'PrezzoStandard' in df_export.columns:
                df_export['PrezzoStandard'] = df_export.apply(
                    lambda row: calcola_prezzo_standard_intelligente(
                        row['Descrizione'],
                        row['UnitaMisura'],
                        row['PrezzoUnitario']
                    ),
                    axis=1
                )
                # Arrotonda a 4 decimali
                df_export['PrezzoStandard'] = df_export['PrezzoStandard'].round(4)
            
            # Prepara nomi colonne per export
            col_names = ['File', 'Data', 'Fornitore', 'Descrizione',
                        'Quantità', 'U.M.', 'Prezzo Unit.', 'IVA %', 'Totale (€)', 'Categoria']
            
            # Aggiungi prezzo_standard se presente
            if 'PrezzoStandard' in df_export.columns:
                col_names.append('LISTINO')
            
            df_export.columns = col_names


            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Articoli')
            
            col_spacer, col_btn = st.columns([4, 2])
            with col_btn:
                st.download_button(
                    label="📊 Excel",
                    data=excel_buffer.getvalue(),
                    file_name=f"dettaglio_articoli_FB_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel",
                    type="primary",
                    use_container_width=False,
                    help="Scarica dettaglio articoli Food & Beverage"
                )


        if salva_modifiche:
            try:
                user_id = st.session_state.user_data["id"]
                user_email = st.session_state.user_data.get("email", "unknown")
                modifiche_effettuate = 0
                
                # ========================================
                # ✅ CHECK: Quale tabella stiamo modificando?
                # ========================================
                colonne_df = edited_df.columns.tolist()
                
                # Check flessibile per Editor Fatture (supporta nomi alternativi)
                ha_file = any(col in colonne_df for col in ['File', 'FileOrigine'])
                ha_numero_riga = any(col in colonne_df for col in ['NumeroRiga', 'Numero Riga', 'Riga', '#'])
                ha_fornitore = 'Fornitore' in colonne_df
                ha_descrizione = 'Descrizione' in colonne_df
                ha_categoria = 'Categoria' in colonne_df
                
                # Se ha colonne tipiche editor fatture (almeno File + Categoria + Descrizione)
                if (ha_file or ha_numero_riga) and ha_categoria and ha_descrizione and ha_fornitore:
                    logger.info("🔄 Rilevato: EDITOR FATTURE CLIENTE - Salvataggio modifiche...")
                    
                    for index, row in edited_df.iterrows():
                        try:
                            # Recupera valori con nomi alternativi
                            f_name = row.get('File') or row.get('FileOrigine')
                            riga_idx = row.get('NumeroRiga') or row.get('Numero Riga') or row.get('Riga') or (index + 1)
                            nuova_cat_raw = row['Categoria']
                            descrizione = row['Descrizione']
                            
                            # ✅ ESTRAI SOLO NOME CATEGORIA (rimuovi emoji se presente)
                            nuova_cat = estrai_nome_categoria(nuova_cat_raw)
                            
                            # ⛔ SKIP se categoria è "Da Classificare" (non salvare categorie placeholder)
                            if nuova_cat == "Da Classificare":
                                logger.info(f"⏭️ SKIP: Categoria 'Da Classificare' non salvata per {descrizione[:30]}")
                                continue
                            
                            # Recupera categoria originale per tracciare correzione
                            vecchia_cat_raw = df_editor.loc[index, 'Categoria'] if index in df_editor.index else None
                            vecchia_cat = estrai_nome_categoria(vecchia_cat_raw) if vecchia_cat_raw else None
                            
                            # Prepara dati da aggiornare
                            update_data = {
                                "categoria": nuova_cat
                            }
                            
                            # Aggiungi prezzo_standard solo se presente e valido
                            prezzo_std = row.get('PrezzoStandard')
                            if prezzo_std is not None and pd.notna(prezzo_std):
                                try:
                                    update_data["prezzo_standard"] = float(prezzo_std)
                                except (ValueError, TypeError):
                                    pass
                            
                            # 🔄 MODIFICA BATCH: Se categoria è cambiata, aggiorna TUTTE le righe con stessa descrizione
                            if vecchia_cat and vecchia_cat != nuova_cat:
                                logger.info(f"🔄 BATCH UPDATE: '{descrizione}' {vecchia_cat} → {nuova_cat}")
                                
                                # Aggiorna tutte le righe con stessa descrizione (normalizzata)
                                result = supabase.table("fatture").update(update_data).eq(
                                    "user_id", user_id
                                ).eq(
                                    "descrizione", descrizione
                                ).execute()
                                
                                righe_aggiornate = len(result.data) if result.data else 0
                                logger.info(f"✅ BATCH: {righe_aggiornate} righe aggiornate per '{descrizione[:40]}'")
                                
                                # Aggiorna memoria AI
                                aggiorna_memoria_ai(descrizione, nuova_cat)
                                
                                # Salva correzione in memoria globale
                                salva_correzione_in_memoria_globale(
                                    descrizione=descrizione,
                                    vecchia_categoria=vecchia_cat,
                                    nuova_categoria=nuova_cat,
                                    user_email=user_email
                                )
                                
                                modifiche_effettuate += righe_aggiornate
                                
                            else:
                                # Aggiorna solo questa riga specifica (nessun cambio categoria)
                                result = supabase.table("fatture").update(update_data).eq(
                                    "user_id", user_id
                                ).eq(
                                    "file_origine", f_name
                                ).eq(
                                    "numero_riga", riga_idx
                                ).eq(
                                    "descrizione", descrizione
                                ).execute()
                                
                                if result.data:
                                    modifiche_effettuate += 1
                                
                        except Exception as e_single:
                            logger.exception(f"Errore aggiornamento singola riga {f_name}:{riga_idx}")
                            continue
                
                # ⚠️ Se ha 'ID' ma NON colonne fatture → Memoria Globale (admin.py TAB 4)
                elif 'ID' in colonne_df and not ha_file and not ha_fornitore:
                    st.warning("⚠️ Questa è una tabella Memoria Globale!")
                    st.error("❌ Usa il bottone 'Salva Modifiche' nella sezione dedicata sotto la tabella.")
                    st.info("💡 Questo bottone è solo per modifiche alle fatture, non per la memoria globale.")
                
                else:
                    # Tipo di modifica non riconosciuto
                    st.error("❌ Tipo di modifica non riconosciuto")
                    st.info(f"📋 Colonne trovate: {colonne_df}")
                    logger.warning(f"Tentativo salvataggio su tabella non riconosciuta. Colonne: {colonne_df}")


                if modifiche_effettuate > 0:
                    # Conta quanti prodotti saranno rimossi dalla vista (categorie spese generali)
                    prodotti_spostati = edited_df[edited_df['Categoria'].apply(
                        lambda cat: estrai_nome_categoria(cat) in CATEGORIE_SPESE_GENERALI
                    )].shape[0]
                    
                    if prodotti_spostati > 0:
                        st.toast(f"✅ Salvate {modifiche_effettuate} modifiche! {prodotti_spostati} prodotti spostati in Spese Generali.")
                    else:
                        st.toast(f"✅ Salvate {modifiche_effettuate} modifiche su Supabase! L'AI imparerà da questo.")
                    
                    time.sleep(1.5)
                    st.cache_data.clear()
                    invalida_cache_memoria()
                    st.session_state.force_reload = True  # ← Forza ricaricamento completo
                    st.rerun()
                elif (ha_file or ha_numero_riga) and ha_categoria and ha_descrizione:
                    # Solo se era davvero l'editor fatture
                    st.toast("⚠️ Nessuna modifica rilevata.")


            except Exception as e:
                logger.exception("Errore durante il salvataggio modifiche categorie")
                st.error(f"❌ Errore durante il salvataggio: {e}")
    
    # ========================================================
    # SEZIONE 2: ALERT AUMENTI PREZZI - VERSIONE SEMPLIFICATA
    # ========================================================
    if st.session_state.sezione_attiva == "alert":
        st.markdown("### 🚨 Alert Aumenti Prezzi")
        st.caption("ℹ️ Ogni acquisto viene confrontato con quello precedente dello stesso prodotto/fornitore. Le Spese Generali sono escluse.")
        
        # Verifica dataset
        if ('df_completo' not in locals()) or df_completo.empty:
            st.warning("📊 Carica delle fatture per vedere gli alert.")
        else:
            
            # FILTRI
            col_search, col_soglia = st.columns([3, 1])
            
            with col_search:
                filtro_prodotto = st.text_input(
                    "🔍 Cerca Prodotto", 
                    "", 
                    placeholder="Digita per filtrare per nome prodotto...",
                    key="filtro_alert_prodotto"
                )
            
            with col_soglia:
                soglia_aumento = st.number_input(
                    "Soglia Aumento Minimo %", 
                    min_value=0, 
                    max_value=100, 
                    value=5,
                    step=1,
                    key="soglia_alert",
                    help="Mostra solo aumenti ≥ +X%"
                )
            
            # CALCOLA ALERT (SOLO F&B)
            df_alert = calcola_alert(df_completo, soglia_aumento, filtro_prodotto)
            
            # BADGE CONTEGGIO
            if not df_alert.empty:
                st.info(f"⚠️ **{len(df_alert)} Aumenti Rilevati** (soglia ≥ +{soglia_aumento}%) - Solo prodotti Food & Beverage")
                
                # Prepara colonne display
                df_display = df_alert.copy()
                df_display['Data'] = pd.to_datetime(df_display['Data']).dt.strftime('%d/%m/%y')
                df_display['Prezzo_Prec'] = df_display['Prezzo_Prec'].apply(lambda x: f"€{x:.2f}")
                df_display['Prezzo_Nuovo'] = df_display['Prezzo_Nuovo'].apply(lambda x: f"€{x:.2f}")
                
                # PALLINI COLORATI: 🔴 Aumento / 🟢 Diminuzione
                def formatta_variazione(perc):
                    if perc > 0:
                        return f"🔴 +{perc:.1f}%"
                    elif perc < 0:
                        return f"🟢 {perc:.1f}%"
                    else:
                        return f"{perc:.1f}%"
                
                df_display['Aumento_Perc'] = df_display['Aumento_Perc'].apply(formatta_variazione)
                
                # Rinomina colonne per display (NO EMOJI)
                df_display.columns = ['Prodotto', 'Cat.', 'Fornitore', 'Data', 'Prec.', 'Nuovo', 'Variazione', 'N.Fattura']
                
                # ============================================================
                # ALTEZZA SCROLLABILE (min 200px, max 500px)
                # ============================================================
                num_righe_alert = len(df_display)
                altezza_alert = min(max(num_righe_alert * 35 + 50, 200), 500)
                
                # Mostra tabella SCROLLABILE
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    height=altezza_alert,  # MAX 500px con scroll
                    hide_index=True
                )
                
                # CSS per bottone Excel
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                # EXPORT EXCEL
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_alert.to_excel(writer, sheet_name='Alert Aumenti', index=False)
                
                col_spacer, col_btn = st.columns([4, 2])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer.getvalue(),
                        file_name=f"alert_aumenti_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_alert",
                        type="primary",
                        use_container_width=False
                    )
            else:
                st.success(f"✅ Nessun aumento rilevato con soglia ≥ +{soglia_aumento}%. Tutto sotto controllo!")
            
            st.markdown("---")
            
            # ============================================================
            # NUOVA SEZIONE: SCONTI E OMAGGI
            # ============================================================
            st.markdown("### 🎁 Sconti e Omaggi Ricevuti")
            
            # Caption dinamica con periodo (usa label_periodo già calcolato sopra)
            st.caption(f"{label_periodo} - Solo prodotti Food & Beverage")
            
            # Carica dati CON PERIODO DINAMICO
            with st.spinner("Caricamento sconti e omaggi..."):
                dati_sconti = carica_sconti_e_omaggi(user_id, data_inizio_filtro, data_fine_filtro)
            
            df_sconti = dati_sconti['sconti']
            df_omaggi = dati_sconti['omaggi']
            totale_risparmiato = dati_sconti['totale_risparmiato']
            
            # ============================================================
            # METRICHE COMPATTE (STESSA ALTEZZA - HTML) - NO EMOJI
            # ============================================================
            col_metric1, col_metric2, col_metric3 = st.columns(3)
            
            with col_metric1:
                st.markdown("""
                <div style="
                    background-color: #fff5f0;
                    border-left: 4px solid #dc3545;
                    padding: 15px;
                    border-radius: 5px;
                    height: 110px;
                ">
                    <div style="font-size: 14px; color: #666;">Sconti Applicati</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0;">{} righe</div>
                    <div style="font-size: 16px; color: #dc3545;">-€{:.2f}</div>
                </div>
                """.format(len(df_sconti), totale_risparmiato if totale_risparmiato > 0 else 0), 
                unsafe_allow_html=True)
            
            with col_metric2:
                st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    border-left: 4px solid #0d6efd;
                    padding: 15px;
                    border-radius: 5px;
                    height: 110px;
                ">
                    <div style="font-size: 14px; color: #666;">Omaggi Ricevuti</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0;">{} righe</div>
                    <div style="font-size: 16px; color: #999;">Prodotti gratuiti</div>
                </div>
                """.format(len(df_omaggi)), 
                unsafe_allow_html=True)
            
            with col_metric3:
                st.markdown("""
                <div style="
                    background-color: #f0fff0;
                    border-left: 4px solid #28a745;
                    padding: 15px;
                    border-radius: 5px;
                    height: 110px;
                ">
                    <div style="font-size: 14px; color: #666;">Totale Risparmiato</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0; color: #28a745;">€{:.2f}</div>
                    <div style="font-size: 16px; color: #999;">{}</div>
                </div>
                """.format(totale_risparmiato if totale_risparmiato > 0 else 0, label_periodo), 
                unsafe_allow_html=True)
            
            # ============================================================
            # SPACING EXTRA (3 righe vuote)
            # ============================================================
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            
            # ============================================================
            # TABELLA SCONTI COMPLETA (SOLO F&B)
            # ============================================================
            if not df_sconti.empty:
                with st.expander("💸 Dettaglio Sconti Applicati", expanded=True):
                    st.markdown(f"**{len(df_sconti)} sconti** ricevuti dai fornitori")
                    st.caption("Solo prodotti Food & Beverage - Escluse spese generali")
                    
                    # Prepara dati completi (come tabella alert sopra)
                    df_sconti_view = df_sconti[[
                        'descrizione',
                        'categoria',
                        'fornitore',
                        'importo_sconto',
                        'data_documento',
                        'file_origine'
                    ]].copy()
                    
                    df_sconti_view.columns = [
                        'Prodotto',
                        'Categoria',
                        'Fornitore',
                        'Sconto',
                        'Data',
                        'Fattura'
                    ]
                    
                    # Altezza dinamica scrollabile
                    num_righe_sconti = len(df_sconti_view)
                    altezza_sconti = min(max(num_righe_sconti * 35 + 50, 200), 500)
                    
                    st.dataframe(
                        df_sconti_view,
                        hide_index=True,
                        use_container_width=True,
                        height=altezza_sconti,
                        column_config={
                            'Prodotto': st.column_config.TextColumn(
                                'Prodotto',
                                width="large"
                            ),
                            'Categoria': st.column_config.TextColumn(
                                'Categoria',
                                width="medium"
                            ),
                            'Fornitore': st.column_config.TextColumn(
                                'Fornitore',
                                width="medium"
                            ),
                            'Sconto': st.column_config.NumberColumn(
                                'Sconto',
                                format="€%.2f",
                                help="Importo sconto ricevuto"
                            ),
                            'Data': st.column_config.DateColumn(
                                'Data',
                                format="DD/MM/YYYY"
                            ),
                            'Fattura': st.column_config.TextColumn(
                                'Fattura',
                                width="medium"
                            )
                        }
                    )
            
            else:
                st.info(f"📊 Nessuno sconto applicato nel periodo {label_periodo.lower()}")
            
            # ============================================================
            # TABELLA OMAGGI
            # ============================================================
            if not df_omaggi.empty:
                with st.expander(f"🎁 Dettaglio Omaggi ({len(df_omaggi)})", expanded=False):
                    st.markdown(f"**{len(df_omaggi)} omaggi** ricevuti dai fornitori")
                    st.caption("Solo prodotti Food & Beverage - Escluse spese generali")
                    
                    df_omaggi_view = df_omaggi[[
                        'descrizione',
                        'fornitore',
                        'quantita',
                        'data_documento',
                        'file_origine'
                    ]].copy()
                    
                    df_omaggi_view.columns = [
                        'Prodotto',
                        'Fornitore',
                        'Quantità',
                        'Data',
                        'Fattura'
                    ]
                    
                    # Altezza dinamica scrollabile
                    num_righe_omaggi = len(df_omaggi_view)
                    altezza_omaggi = min(max(num_righe_omaggi * 35 + 50, 200), 500)
                    
                    st.dataframe(
                        df_omaggi_view,
                        hide_index=True,
                        use_container_width=True,
                        height=altezza_omaggi,
                        column_config={
                            'Data': st.column_config.DateColumn(
                                'Data',
                                format="DD/MM/YYYY"
                            )
                        }
                    )
                    
                    st.info("ℹ️ Gli omaggi sono prodotti con prezzo €0 (escluse diciture e note)")
            
            # ============================================================
            # INFO SE NESSUN DATO + DEBUG
            # ============================================================
            if df_sconti.empty and df_omaggi.empty:
                st.info(f"📊 Nessuno sconto o omaggio ricevuto nel periodo {label_periodo.lower()}")
                
                # Mostra statistiche utili per debug (solo admin/impersonificato)
                if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
                    with st.expander("🔍 Info Debug", expanded=False):
                        try:
                            # Ricarica dati per debug con stesso periodo
                            if hasattr(data_inizio_filtro, 'isoformat'):
                                data_inizio_str = data_inizio_filtro.isoformat()
                            else:
                                data_inizio_str = str(data_inizio_filtro)
                            
                            debug_response = supabase.table('fatture')\
                                .select('id, descrizione, categoria, prezzo_unitario')\
                                .eq('user_id', user_id)\
                                .gte('data_documento', data_limite)\
                                .execute()
                            
                            if debug_response.data:
                                df_debug = pd.DataFrame(debug_response.data)
                                st.write(f"📄 Righe totali caricate: {len(df_debug)}")
                                st.write(f"💸 Righe con prezzo <0: {len(df_debug[df_debug['prezzo_unitario'] < 0])}")
                                st.write(f"🎁 Righe con prezzo =0: {len(df_debug[df_debug['prezzo_unitario'] == 0])}")
                                
                                # Mostra categorie presenti
                                st.write("🏷️ Categorie presenti:", sorted(df_debug['categoria'].unique().tolist()))
                                
                                # Mostra sample prezzi negativi
                                if len(df_debug[df_debug['prezzo_unitario'] < 0]) > 0:
                                    st.markdown("**Sample prezzi negativi:**")
                                    st.dataframe(
                                        df_debug[df_debug['prezzo_unitario'] < 0][['descrizione', 'categoria', 'prezzo_unitario']].head(5),
                                        hide_index=True
                                    )
                            else:
                                st.warning("⚠️ Nessun dato nel periodo")
                        except Exception as e:
                            st.error(f"❌ Errore debug: {e}")
                
# ========================================================
    # ========================================================
    # SEZIONE 3: CATEGORIE
    # ========================================================
    if st.session_state.sezione_attiva == "categorie":
        # Placeholder se dataset mancanti/vuoti
        if ('df_food' not in locals()) or df_food.empty:
            st.info("📊 Nessun dato disponibile per i fornitori.")
        else:
            st.caption("ℹ️ Le Spese Generali sono automaticamente escluse da questo controllo")
        
        pivot_cat = crea_pivot_mensile(df_food, "Categoria")
        
        if not pivot_cat.empty:
            num_righe_cat = len(pivot_cat)
            altezza_cat = max(num_righe_cat * 35 + 50, 200)
            
            st.dataframe(
                pivot_cat,
                hide_index=True,
                use_container_width=True,
                height=altezza_cat,
                column_config={
                    "TOTALE ANNO": st.column_config.NumberColumn(format="€ %.2f")
                }
            )
            
            totale_cat = pivot_cat['TOTALE ANNO'].sum()
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.markdown(genera_box_recap(num_righe_cat, totale_cat), unsafe_allow_html=True)
            
            with col_right:
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_cat = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_cat, engine='openpyxl') as writer:
                    pivot_cat.to_excel(writer, index=False, sheet_name='Categorie')
                
                col_spacer, col_btn = st.columns([4, 2])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer_cat.getvalue(),
                        file_name=f"categorie_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_categorie",
                        type="primary",
                        use_container_width=False
                    )
        else:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")

    # ======================================================
    # ========================================================
    # SEZIONE 4: FORNITORI
    # ========================================================
    if st.session_state.sezione_attiva == "fornitori":
        # Placeholder se dataset mancanti/vuoti
        if ('df_food' not in locals()) or df_food.empty:
            st.info("📊 Nessun dato disponibile per i fornitori.")
        else:
            st.caption("ℹ️ Le Spese Generali sono automaticamente escluse da questo controllo")
        
        pivot_forn = crea_pivot_mensile(df_food, "Fornitore")
        
        if not pivot_forn.empty:
            num_righe_forn = len(pivot_forn)
            altezza_forn = max(num_righe_forn * 35 + 50, 200)
            
            st.dataframe(
                pivot_forn,
                hide_index=True,
                use_container_width=True,
                height=altezza_forn,
                column_config={
                    "TOTALE ANNO": st.column_config.NumberColumn(format="€ %.2f")
                }
            )
            
            totale_forn = pivot_forn['TOTALE ANNO'].sum()
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.markdown(genera_box_recap(num_righe_forn, totale_forn), unsafe_allow_html=True)
            
            with col_right:
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_forn = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_forn, engine='openpyxl') as writer:
                    pivot_forn.to_excel(writer, index=False, sheet_name='Fornitori')
                
                col_spacer, col_btn = st.columns([4, 2])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer_forn.getvalue(),
                        file_name=f"fornitori_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_fornitori",
                        type="primary",
                        use_container_width=False
                    )
        else:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")


    # ========================================================
    # ========================================================
    # SEZIONE 5: SPESE GENERALI
    # ========================================================
    if st.session_state.sezione_attiva == "spese":
        if df_spese_generali.empty:
            st.info("📊 Nessuna spesa generale nel periodo selezionato")
        else:
            # ============================================
            # TABELLA 1: CATEGORIE × MESI
            # ============================================
            st.markdown("#### 📊 Spesa per Categoria per Mese")
            
            # Aggiungi colonna Mese
            df_spese_con_mese = df_spese_generali.copy()
            df_spese_con_mese['Mese'] = pd.to_datetime(df_spese_con_mese['DataDocumento']).dt.to_period('M').astype(str)
            
            # Pivot: Categorie × Mesi
            pivot_cat = df_spese_con_mese.pivot_table(
                index='Categoria',
                columns='Mese',
                values='TotaleRiga',
                aggfunc='sum',
                fill_value=0
            )
            
            # Aggiungi colonna TOTALE
            pivot_cat['TOTALE'] = pivot_cat.sum(axis=1)
            
            # Ordina per totale decrescente
            pivot_cat = pivot_cat.sort_values('TOTALE', ascending=False)
            
            # Formatta come €
            pivot_cat_display = pivot_cat.map(lambda x: f"€ {x:,.2f}")
            
            num_righe_spese_cat = len(pivot_cat_display)
            altezza_spese_cat = max(num_righe_spese_cat * 35 + 50, 200)
            st.dataframe(pivot_cat_display, use_container_width=True, height=altezza_spese_cat)
            
            st.markdown("---")
            
            # ============================================
            # TABELLA 2: FORNITORI × MESI
            # ============================================
            st.markdown("#### 🏪 Spesa per Fornitore per Mese")
            
            # Pivot: Fornitori × Mesi
            pivot_forn = df_spese_con_mese.pivot_table(
                index='Fornitore',
                columns='Mese',
                values='TotaleRiga',
                aggfunc='sum',
                fill_value=0
            )
            
            # Aggiungi colonna TOTALE
            pivot_forn['TOTALE'] = pivot_forn.sum(axis=1)
            
            # Ordina per totale decrescente
            pivot_forn = pivot_forn.sort_values('TOTALE', ascending=False)
            
            # Formatta come €
            pivot_forn_display = pivot_forn.map(lambda x: f"€ {x:,.2f}")
            
            num_righe_spese_forn = len(pivot_forn_display)
            altezza_spese_forn = max(num_righe_spese_forn * 35 + 50, 200)
            st.dataframe(pivot_forn_display, use_container_width=True, height=altezza_spese_forn)
            
            st.markdown("---")
            
            # ============================================
            # BOX RIEPILOGATIVO + EXCEL EXPORT
            # ============================================
            totale_spese_generali = df_spese_generali['TotaleRiga'].sum()
            num_righe_spese = len(df_spese_generali)
            
            col_recap, col_excel = st.columns([3, 1])
            
            with col_recap:
                st.markdown(genera_box_recap(num_righe_spese, totale_spese_generali), unsafe_allow_html=True)
            
            with col_excel:
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                # Prepara Excel con entrambe le tabelle
                excel_buffer_spese = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_spese, engine='openpyxl') as writer:
                    pivot_cat.to_excel(writer, sheet_name='Per Categoria')
                    pivot_forn.to_excel(writer, sheet_name='Per Fornitore')
                
                col_spacer, col_btn = st.columns([3, 3])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer_spese.getvalue(),
                        file_name=f"spese_generali_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_spese",
                        type="primary",
                        use_container_width=False
                    )

# ============================================================
# STILI CSS (COMPLETI)
# ============================================================



st.markdown("""
    <style>
    [data-testid="stTab"] {
        font-size: 20px !important;
        font-weight: bold !important;
        text-transform: uppercase !important;
        padding: 15px 30px !important;
    }
    
    [data-testid="stFileUploader"] > div > div:not(:first-child) { display: none !important; }
    [data-testid="stFileUploader"] ul { display: none !important; }
    [data-testid="stFileUploader"] button[kind="icon"] { display: none !important; }
    [data-testid="stFileUploader"] small { display: none !important; }
    [data-testid="stFileUploader"] svg { display: none !important; }
    [data-testid="stFileUploader"] section > div > span { display: none !important; }
    [data-testid="stFileUploader"] section > div:last-child { display: none !important; }
    
    [data-testid="stFileUploader"] { margin: 20px 0; }
    [data-testid="stFileUploader"] > div { width: 100%; max-width: 700px; }
    [data-testid="stFileUploader"] section {
        padding: 50px 80px !important;
        border: 5px dashed #4CAF50 !important;
        border-radius: 25px !important;
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%) !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 6px 12px rgba(0,0,0,0.1) !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #2E7D32 !important;
        background: linear-gradient(135deg, #c8e6c9 0%, #a5d6a7 100%) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 20px rgba(0,0,0,0.15) !important;
    }
    [data-testid="stFileUploader"] label {
        font-size: 32px !important;
        font-weight: bold !important;
        color: #1b5e20 !important;
        letter-spacing: 1px !important;
        text-transform: uppercase !important;
    }
    [data-testid="stFileUploader"] button {
        padding: 15px 40px !important;
        font-size: 18px !important;
        font-weight: bold !important;
        background-color: #4CAF50 !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploader"] button:hover {
        background-color: #45a049 !important;
        transform: scale(1.05) !important;
    }
    
    .file-status-table {
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        background-color: #fafafa;
    }
    .file-status-table table { width: 100%; border-collapse: collapse; }
    .file-status-table th {
        background-color: #f0f0f0;
        padding: 15px 10px !important;
        text-align: left;
        position: sticky;
        top: 0;
        z-index: 10;
        font-size: 18px !important;
        font-weight: bold !important;
    }
    .file-status-table td {
        padding: 12px 10px !important;
        border-bottom: 1px solid #eee;
        font-size: 16px !important;
    }
    
    [data-testid="stMetricValue"] > div { font-size: 48px !important; font-weight: bold !important; }
    [data-testid="stMetricLabel"] > div { font-size: 22px !important; font-weight: 600 !important; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #f0f4f8 0%, #e1e8ed 100%) !important;
        border: 4px solid #cbd5e0 !important;
        border-radius: 20px !important;
        padding: 30px 20px !important;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15) !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-8px) !important;
        box-shadow: 0 12px 24px rgba(0,0,0,0.2) !important;
    }
    
    [data-testid="column"]:nth-child(1) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%) !important;
        border-color: #2196f3 !important;
    }
    [data-testid="column"]:nth-child(1) [data-testid="stMetricValue"] { color: #1565c0 !important; }
    [data-testid="column"]:nth-child(1) [data-testid="stMetricLabel"] { color: #1976d2 !important; }
    [data-testid="column"]:nth-child(2) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%) !important;
        border-color: #4caf50 !important;
    }
    [data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] { color: #2e7d32 !important; }
    [data-testid="column"]:nth-child(2) [data-testid="stMetricLabel"] { color: #388e3c !important; }
    [data-testid="column"]:nth-child(3) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%) !important;
        border-color: #ff9800 !important;
    }
    [data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] { color: #e65100 !important; }
    [data-testid="column"]:nth-child(3) [data-testid="stMetricLabel"] { color: #f57c00 !important; }
    [data-testid="column"]:nth-child(4) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%) !important;
        border-color: #f44336 !important;
    }
    [data-testid="column"]:nth-child(4) [data-testid="stMetricValue"] { color: #c62828 !important; }
    [data-testid="column"]:nth-child(4) [data-testid="stMetricLabel"] { color: #d32f2f !important; }
            
    #MainMenu { visibility: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)


# ============================================================
# INTERFACCIA PRINCIPALE CON CACHING OTTIMIZZATO
# ============================================================


if 'timestamp_ultimo_caricamento' not in st.session_state:
    st.session_state.timestamp_ultimo_caricamento = time.time()


# 🔒 IMPORTANTE: user_id per cache isolata (multi-tenancy)
user_id = st.session_state.user_data["id"]


with st.spinner("⏳ Caricamento dati..."):
    df_cache = carica_e_prepara_dataframe(user_id)


# 🗂️ GESTIONE FATTURE - Eliminazione (prima del file uploader)
if not df_cache.empty:
    with st.expander("🗂️ Gestione Fatture Caricate (Elimina)", expanded=False):
        
        # ========================================
        # BOX STATISTICHE
        # ========================================
        stats_db = get_fatture_stats(user_id)
        st.markdown(f"""
<div style="
    background: linear-gradient(135deg, rgba(255, 140, 0, 0.15) 0%, rgba(255, 165, 0, 0.20) 100%);
    padding: 14px 22px;
    border-radius: 10px;
    border-left: 5px solid rgba(255, 107, 0, 0.6);
    box-shadow: 0 3px 6px rgba(255, 140, 0, 0.15);
    margin: 0 0 20px 0;
    display: inline-block;
    min-width: 400px;
    backdrop-filter: blur(10px);
">
    <span style="color: #FF6B00; font-size: 1.05em; font-weight: 700;">
        📊 Fatture: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_uniche"]:,}</strong> | 
        📋 Righe Totali: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_righe"]:,}</strong>
    </span>
</div>
""", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("**Fatture nel tuo account:**")
        
        # Raggruppa per file origine per creare summary
        fatture_summary = df_cache.groupby('FileOrigine').agg({
            'Fornitore': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],
            'TotaleRiga': 'sum',
            'NumeroRiga': 'count',
            'DataDocumento': 'first'
        }).reset_index()
        
        fatture_summary.columns = ['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data']
        fatture_summary = fatture_summary.sort_values('Data', ascending=False)
        
        # 🔍 DEBUG TOOL: Rimosso - Usa Upload Events in Admin Panel per diagnostica
        
        # 🗑️ PULSANTE SVUOTA TUTTO CON CONFERMA INLINE
        st.markdown("### 🗑️ Eliminazione Massiva")
        
        col_check, col_btn = st.columns([3, 1])
        
        with col_check:
            conferma_check = st.checkbox(
                "⚠️ **Confermo di voler eliminare TUTTE le fatture**",
                key="check_conferma_svuota",
                help="Questa azione è irreversibile"
            )
        
        with col_btn:
            if st.button(
                "🗑️ ELIMINA TUTTO", 
                type="primary" if conferma_check else "secondary",
                disabled=not conferma_check,
                use_container_width=True,
                key="btn_svuota_definitivo"
            ):
                with st.spinner("🗑️ Eliminazione in corso..."):
                    # Progress bar per UX
                    progress = st.progress(0)
                    progress.progress(20, text="Eliminazione da Supabase...")
                    
                    result = elimina_tutte_fatture(user_id)
                    
                    progress.progress(40, text="Pulizia file JSON locali...")
                    
                    # HARD RESET: Elimina file JSON obsoleti
                    json_files = ['fattureprocessate.json', 'fatture.json', 'data.json']
                    for json_file in json_files:
                        if os.path.exists(json_file):
                            try:
                                os.remove(json_file)
                                logger.info(f"🗑️ Rimosso file JSON obsoleto: {json_file}")
                            except Exception as e:
                                logger.warning(f"⚠️ Impossibile rimuovere {json_file}: {e}")
                    
                    progress.progress(60, text="Pulizia cache Streamlit...")
                    
                    # HARD RESET: Pulisci TUTTE le cache
                    st.cache_data.clear()
                    try:
                        st.cache_resource.clear()
                    except:
                        pass
                    
                    progress.progress(80, text="Reset session state...")
                    
                    # HARD RESET: Rimuovi session state specifici (mantieni login)
                    keys_to_remove = [k for k in st.session_state.keys() 
                                     if k not in ['user_data', 'logged_in', 'check_conferma_svuota']]
                    for key in keys_to_remove:
                        try:
                            del st.session_state[key]
                        except:
                            pass
                    
                    progress.progress(100, text="Completato!")
                    time.sleep(0.3)
                    
                    # Mostra risultato DENTRO lo spinner (indentazione corretta)
                    if result["success"]:
                        st.success(f"✅ **{result['fatture_eliminate']} fatture** eliminate! ({result['righe_eliminate']} prodotti)")
                        st.info("🧹 **Hard Reset completato**: Cache, JSON locali e session state puliti")
                        
                        # LOG AUDIT: Verifica immediata post-delete
                        try:
                            verify = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id).execute()
                            num_residue = len(verify.data) if verify.data else 0
                            if num_residue == 0:
                                logger.info(f"✅ DELETE VERIFIED: 0 righe rimaste per user_id={user_id}")
                                st.success(f"✅ Verifica: Database pulito (0 righe)")
                            else:
                                logger.error(f"⚠️ DELETE INCOMPLETE: {num_residue} righe ancora presenti per user_id={user_id}")
                                st.error(f"⚠️ Attenzione: {num_residue} righe ancora presenti (possibile problema RLS)")
                        except Exception as e:
                            logger.exception("Errore verifica post-delete")
                        
                        # Reset checkbox prima del rerun
                        if 'check_conferma_svuota' in st.session_state:
                            del st.session_state.check_conferma_svuota
                        
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(f"❌ Errore: {result['error']}")
        
        st.markdown("---")
        
        # ========== ELIMINA SINGOLA FATTURA ==========
        st.markdown("### 🗑️ Elimina Fattura Singola")
        st.caption("Seleziona una fattura specifica per eliminarla usando il menu a tendina.")
        
        # Usa fatture_summary già creato sopra
        if len(fatture_summary) > 0:
            # Crea opzioni dropdown con dict per passare tutti i dati
            fatture_options = []
            for idx, row in fatture_summary.iterrows():
                fatture_options.append({
                    'File': row['File'],
                    'Fornitore': row['Fornitore'],
                    'NumProdotti': int(row['NumProdotti']),
                    'Totale': row['Totale']
                })
            
            fattura_selezionata = st.selectbox(
                "Seleziona fattura da eliminare:",
                options=fatture_options,
                format_func=lambda x: f"📄 {x['File']} - {x['Fornitore']} (📦 {x['NumProdotti']} prodotti, 💰 €{x['Totale']:.2f})",
                key="select_fattura_elimina"
            )
            
            col_btn, col_spacer = st.columns([1, 3])
            with col_btn:
                if st.button("🗑️ Elimina Fattura", type="secondary", use_container_width=True):
                    with st.spinner(f"🗑️ Eliminazione in corso..."):
                        result = elimina_fattura_completa(fattura_selezionata['File'], user_id)
                        
                        if result["success"]:
                            st.success(f"✅ Fattura **{fattura_selezionata['File']}** eliminata! ({result['righe_eliminate']} prodotti)")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Errore: {result['error']}")
        else:
            st.info("🔭 Nessuna fattura da eliminare.")
        
        st.caption("⚠️ L'eliminazione è immediata e irreversibile")


# File uploader sempre visibile (solo Supabase, no JSON)
uploaded_files = st.file_uploader(
    "Carica file XML, PDF o Immagini", 
    accept_multiple_files=True, 
    type=['xml', 'pdf', 'jpg', 'jpeg', 'png'], 
    label_visibility="collapsed"
)


if 'files_processati_sessione' not in st.session_state:
    st.session_state.files_processati_sessione = set()

if 'files_con_errori' not in st.session_state:
    st.session_state.files_con_errori = {}


# 🔥 GESTIONE FILE CARICATI
if uploaded_files:
    # File già processati: solo da Supabase + sessione
    try:
        user_id = st.session_state.user_data["id"]
        response = supabase.table("fatture").select("file_origine", count="exact").eq("user_id", user_id).execute()
        file_su_supabase = set([row["file_origine"] for row in response.data])
    except Exception as e:
        logger.exception(f"Errore lettura file già processati da Supabase per user_id={st.session_state.user_data.get('id')}")
        file_su_supabase = set()


    tutti_file_processati = st.session_state.files_processati_sessione | file_su_supabase
    
    file_unici = []
    duplicati_interni = []
    visti = set()
    
    for file in uploaded_files:
        if file.name not in visti:
            file_unici.append(file)
            visti.add(file.name)
        else:
            duplicati_interni.append(file.name)
    
    file_nuovi = []
    file_gia_processati = []
    
    for file in file_unici:
        if file.name in tutti_file_processati:
            file_gia_processati.append(file)
        else:
            file_nuovi.append(file)
    
    # Messaggio semplice di conferma upload (senza lista ridondante)
    if file_nuovi:
        st.info(f"✅ **{len(file_nuovi)} nuove fatture** da elaborare")
    if file_gia_processati:
        st.info(f"♻️ **{len(file_gia_processati)} fatture** già in memoria (ignorate)")
        # NOTA: I duplicati NON vengono loggati (comportamento corretto, non problema)
        
    if duplicati_interni:
        st.warning(f"⚠️ **{len(duplicati_interni)} duplicati** nell'upload (ignorati)")
    
    if file_nuovi:
        # Crea placeholder per loading AI
        upload_placeholder = st.empty()
        
        try:
            # Mostra animazione AI
            mostra_loading_ai(upload_placeholder, f"Analisi AI di {len(file_nuovi)} Fatture")
            
            # Contatori per statistiche
            file_processati = 0
            righe_totali = 0
            salvati_supabase = 0
            salvati_json = 0
            errori = []
            
            # Elabora tutti i file
            for idx, file in enumerate(file_nuovi, 1):
                nome_file = file.name.lower()
                
                # Routing automatico per tipo file (SILENZIOSO)
                try:
                    if nome_file.endswith('.xml'):
                        items = estrai_dati_da_xml(file)
                    elif nome_file.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                        items = estrai_dati_da_scontrino_vision(file)
                    else:
                        errori.append(f"{file.name}: Formato non supportato")
                        # CRITICO: Aggiungi a processati per evitare loop
                        st.session_state.files_processati_sessione.add(file.name)
                        continue
                    
                    # Salva in memoria se trovati dati (SILENZIOSO)
                    if items:
                        result = salva_fattura_processata(file.name, items, silent=True)
                        
                        if result["success"]:
                            file_processati += 1
                            righe_totali += result["righe"]
                            if result["location"] == "supabase":
                                salvati_supabase += 1
                            elif result["location"] == "json":
                                salvati_json += 1
                            
                            # Aggiungi a processati
                            st.session_state.files_processati_sessione.add(file.name)
                        else:
                            errori.append(f"{file.name}: Errore salvataggio")
                            # CRITICO: Aggiungi a processati anche se salvataggio fallito
                            st.session_state.files_processati_sessione.add(file.name)
                    else:
                        # Nessun dato estratto - controlla se c'è errore specifico
                        if file.name in st.session_state.files_con_errori:
                            errore_dettaglio = st.session_state.files_con_errori[file.name]
                            errori.append(f"{file.name}: {errore_dettaglio}")
                        else:
                            errori.append(f"{file.name}: Nessun dato estratto")
                        
                        # CRITICO: Aggiungi a processati per evitare loop infinito
                        st.session_state.files_processati_sessione.add(file.name)
                
                except Exception as e:
                    logger.exception(f"Errore elaborazione {file.name}")
                    errori.append(f"{file.name}: {str(e)[:50]}")
                    
                    # ============================================================
                    # LOG UPLOAD EVENT - FAILED (parsing/vision error)
                    # ============================================================
                    try:
                        user_id = st.session_state.user_data.get("id")
                        user_email = st.session_state.user_data.get("email", "unknown")
                        
                        # Determina error_stage in base al tipo di file
                        error_stage = "PARSING" if file.name.endswith('.xml') else "VISION"
                        
                        log_upload_event(
                            user_id=user_id,
                            user_email=user_email,
                            file_name=file.name,
                            status="FAILED",
                            rows_parsed=0,
                            rows_saved=0,
                            error_stage=error_stage,
                            error_message=str(e)[:500],
                            details={"exception_type": type(e).__name__}
                        )
                    except Exception as log_error:
                        logger.error(f"Errore logging failed event: {log_error}")
                    # ============================================================
                    
                    # CRITICO: Aggiungi a processati per evitare loop infinito
                    st.session_state.files_processati_sessione.add(file.name)
            
            # Rimuovi loading SEMPRE
            upload_placeholder.empty()
            
            # MESSAGGIO FINALE RIASSUNTIVO
            if file_processati > 0:
                # Messaggio di successo
                location_text = ""
                if salvati_supabase > 0 and salvati_json == 0:
                    location_text = " su **Supabase Cloud** ☁️"
                elif salvati_json > 0 and salvati_supabase == 0:
                    location_text = " su **JSON locale** 💾"
                elif salvati_supabase > 0 and salvati_json > 0:
                    location_text = f" (☁️ {salvati_supabase} su Supabase, 💾 {salvati_json} su JSON)"
                
                st.success(f"✅ **Caricate {file_processati} fatture con successo!** ({righe_totali} righe elaborate){location_text}")
            
            # Mostra errori se presenti (SOLO ERRORI CRITICI)
            if errori:
                with st.expander(f"⚠️ {len(errori)} file con problemi", expanded=False):
                    for errore in errori:
                        st.warning(errore)
            
            # Piccola pausa per vedere il messaggio di successo
            if file_processati > 0:
                time.sleep(0.3)
                
                # 🔍 AUDIT: Verifica coerenza post-upload
                audit_result = audit_data_consistency(user_id, context="post-upload")
                if not audit_result["consistent"]:
                    st.warning(f"⚠️ Audit: DB ha {audit_result['db_count']} righe ma cache ne mostra {audit_result['cache_count']}")
            
            # Ricarica cache e aggiorna automaticamente
            st.cache_data.clear()
            st.rerun()
        
        except Exception as e:
            # CRITICO: rimuovi loading anche in caso di errore
            upload_placeholder.empty()
            st.error(f"❌ Errore durante l'elaborazione: {e}")
            logger.exception("Errore upload fatture")


# 🔥 CARICA E MOSTRA STATISTICHE SEMPRE (da Supabase)
# 🔒 IMPORTANTE: user_id per cache isolata (multi-tenancy)


# Crea placeholder per loading
loading_placeholder = st.empty()


try:
    # Mostra animazione AI durante caricamento
    mostra_loading_ai(loading_placeholder, "Caricamento Dashboard AI")
    
    # Carica dati (con force_refresh se richiesto dopo categorizzazione AI)
    user_id = st.session_state.user_data["id"]
    force_refresh = st.session_state.get('force_reload', False)
    if force_refresh:
        st.session_state.force_reload = False  # Reset flag
        logger.info("🔄 FORCE RELOAD attivato dopo categorizzazione AI")
    df_completo = carica_e_prepara_dataframe(user_id, force_refresh=force_refresh)
    
    # Logging shape e verifica dati (solo console)
    logger.debug(f"DataFrame shape = {df_completo.shape}")
    logger.debug(f"DataFrame empty = {df_completo.empty}")
    if not df_completo.empty:
        logger.debug(f"Colonne = {df_completo.columns.tolist()}")
        logger.debug(f"Prime 3 righe:\n{df_completo.head(3)}")
    
    # Rimuovi loading SEMPRE prima di mostrare contenuto
    loading_placeholder.empty()
    
    # Mostra dashboard direttamente senza messaggi
    if not df_completo.empty:
        mostra_statistiche(df_completo)
    else:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


except Exception as e:
    # CRITICO: rimuovi loading anche in caso di errore
    loading_placeholder.empty()
    st.error(f"❌ Errore durante il caricamento: {e}")
    logger.exception("Errore caricamento dashboard")
