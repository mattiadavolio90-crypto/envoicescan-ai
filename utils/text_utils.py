"""
Modulo text_utils per OH YEAH! Hub.

Funzioni per:
- Normalizzazione descrizioni (memoria globale)
- Normalizzazione stringhe generiche
- Estrazione nomi da categorie
- Estrazione fornitori da XML
- Aggiunta icone a categorie
"""

import re
import logging
from typing import Tuple

from config.constants import (
    REGEX_UNITA_MISURA,
    REGEX_NUMERI_UNITA,
    REGEX_SOSTITUZIONI,
    REGEX_PUNTEGGIATURA,
    REGEX_ARTICOLI,
    REGEX_PUNTEGGIATURA_FINALE
)
from config.logger_setup import get_logger

logger = get_logger('text_utils')


# ============================================================
# PULIZIA CARATTERI CORROTTI
# ============================================================

def escape_ilike(text: str) -> str:
    """Escape caratteri speciali PostgreSQL ILIKE (% e _) per evitare match indesiderati."""
    return text.replace('%', r'\%').replace('_', r'\_')


def pulisci_caratteri_corrotti(testo: str) -> str:
    """
    Rimuove caratteri corrotti (encoding errato) dalle descrizioni.
    
    Rimuove:
    - Caratteri non ASCII stampabili
    - Caratteri Unicode corrotti (�, replacement character)
    - Caratteri cinesi, giapponesi, coreani mal encodati
    - Sequenze di caratteri strani tipici di encoding errato
    
    Mantiene:
    - Lettere latine A-Z (maiuscole/minuscole)
    - Lettere italiane accentate (à, è, é, ì, ò, ù, ä, ö, ü, ñ)
    - Numeri 0-9
    - Spazi e punteggiatura comune
    
    Args:
        testo: Stringa da pulire
    
    Returns:
        str: Stringa pulita con solo caratteri leggibili
    
    Esempi:
        >>> pulisci_caratteri_corrotti("SAKE PER CUCINA °×º×³øÓÃÇå¾Æ1*18LT")
        'SAKE PER CUCINA 1*18LT'
        >>> pulisci_caratteri_corrotti("RISO THAI ½ðÁ«»¨Ì©¹úÏãÃ×18KG")
        'RISO THAI 18KG'
    """
    if not testo:
        return ""
    
    # Step 1: Rimuove caratteri replacement Unicode
    testo = testo.replace('�', ' ')
    testo = testo.replace('\ufffd', ' ')
    
    # Step 2: Approccio drastico - mantiene SOLO caratteri ASCII estesi (Latin-1)
    # e rimuove tutto il resto (caratteri cinesi, giapponesi, coreani, ecc.)
    try:
        # Encode in Latin-1 ignorando errori, poi decode
        testo_bytes = testo.encode('latin-1', errors='ignore')
        testo = testo_bytes.decode('latin-1')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    
    # Step 3: Rimuove TUTTI i caratteri Unicode > 255 (non-Latin-1)
    # Questo elimina caratteri cinesi, giapponesi, coreani, simboli strani
    testo = ''.join(char if ord(char) < 256 else ' ' for char in testo)
    
    # Step 4: Mantiene SOLO caratteri ASCII puri (0-127)
    # Rimuove TUTTI i caratteri accentati per evitare residui di encoding corrotto
    # Le descrizioni prodotti possono sopravverer senza accenti
    pulito = re.sub(
        r'[^A-Za-z0-9\s.,;:/()\[\]\-*+%€$\'\"!?&@#]',
        ' ',
        testo
    )
    
    # Step 5: Rimuove sequenze multiple di spazi
    pulito = ' '.join(pulito.split())
    
    # Step 6: Rimuove simboli isolati strani rimasti
    # Es: "SAKE ° × 18LT" → "SAKE 18LT"
    pulito = re.sub(r'\s[°×+*·§¨©ª«¬®¯]+\s', ' ', pulito)
    pulito = re.sub(r'\s[°×+*·§¨©ª«¬®¯]+$', '', pulito)
    pulito = re.sub(r'^[°×+*·§¨©ª«¬®¯]+\s', '', pulito)
    
    # Step 7: Pulizia finale spazi
    pulito = ' '.join(pulito.split())
    
    return pulito.strip()


# ============================================================
# NORMALIZZAZIONE DESCRIZIONI (MEMORIA GLOBALE)
# ============================================================

def normalizza_descrizione(descrizione: str) -> str:
    """
    Normalizza descrizione per matching intelligente in memoria globale.
    
    Operazioni:
    1. Rimuove unità di misura (KG, L, ML, PZ, ecc.)
    2. Rimuove numeri (pesi, quantità, prezzi)
    3. Normalizza abbreviazioni comuni
    4. Rimuove punteggiatura superflua
    5. Uniforma spazi
    
    Esempi:
        >>> normalizza_descrizione("POLLO INTERO KG 2.5")
        'POLLO INTERO'
        >>> normalizza_descrizione("OLIO EVO 1L BOT.")
        'OLIO EVO BOTTIGLIA'
        >>> normalizza_descrizione("PASTA PENNE 500G")
        'PASTA PENNE'
    
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


def get_descrizione_normalizzata_e_originale(descrizione: str) -> Tuple[str, str]:
    """
    Restituisce sia descrizione normalizzata che originale.
    
    Args:
        descrizione: descrizione da normalizzare
    
    Returns:
        tuple: (descrizione_normalizzata, descrizione_originale)
    
    Esempi:
        >>> get_descrizione_normalizzata_e_originale("Pasta Penne 500g")
        ('PASTA PENNE', 'PASTA PENNE 500G')
    """
    desc_original = descrizione.strip().upper()
    desc_normalized = normalizza_descrizione(descrizione)
    
    return desc_normalized, desc_original


def normalizza_stringa(testo: str) -> str:
    """
    Normalizza stringhe per ridurre duplicati AI.
    
    - Converte in MAIUSCOLO
    - Rimuove punteggiatura finale
    - Normalizza spazi
    - Tronca a 100 caratteri
    
    Args:
        testo: stringa da normalizzare
    
    Returns:
        str: stringa normalizzata (max 100 char)
    
    Esempi:
        >>> normalizza_stringa("Pollo Intero...")
        'POLLO INTERO'
        >>> normalizza_stringa("  pasta   penne  ")
        'PASTA PENNE'
    """
    if not testo or not isinstance(testo, str):
        return ""
    
    testo = testo.upper()
    testo = REGEX_PUNTEGGIATURA_FINALE.sub('', testo)  # Regex precompilata
    testo = ' '.join(testo.split())
    return testo[:100].strip()


# ============================================================
# ESTRAZIONE NOMI E PARSING
# ============================================================

def estrai_nome_categoria(categoria_con_icona: str) -> str:
    """
    Estrae solo il nome dalla categoria con icona.
    
    Args:
        categoria_con_icona: "🍖 CARNE" o "CARNE" o "MATERIALE DI CONSUMO"
    
    Returns:
        str: "CARNE" o "MATERIALE DI CONSUMO" (solo nome, senza emoji)
    
    Esempi:
        >>> estrai_nome_categoria("🍖 CARNE")
        'CARNE'
        >>> estrai_nome_categoria("CARNE")
        'CARNE'
        >>> estrai_nome_categoria("📦 MATERIALE DI CONSUMO")
        'MATERIALE DI CONSUMO'
        >>> estrai_nome_categoria("MATERIALE DI CONSUMO")
        'MATERIALE DI CONSUMO'
        >>> estrai_nome_categoria("")
        'Da Classificare'
        >>> estrai_nome_categoria(None)
        'Da Classificare'
    """
    if not categoria_con_icona:
        return "Da Classificare"
    
    categoria_clean = categoria_con_icona.strip()
    
    # ✅ FIX: Rimuovi solo emoji iniziali (caratteri non-ASCII all'inizio)
    # NON splittare su spazi interni (es: "MATERIALE DI CONSUMO" deve restare intatto)
    # Pattern: rimuove emoji/simboli non-ASCII all'inizio + eventuali spazi dopo
    categoria_clean = re.sub(r'^[^\w\s]+\s*', '', categoria_clean)
    
    return categoria_clean


def estrai_fornitore_xml(fattura: dict) -> str:
    """
    Estrae il nome del fornitore gestendo sia società che persone fisiche.
    
    Priorità:
    1. Denominazione (società)
    2. Nome + Cognome (persona fisica) 
    3. Solo Nome (fallback)
    4. "Fornitore Sconosciuto"
    
    Args:
        fattura: dizionario parsed da xmltodict
    
    Returns:
        str: Nome fornitore normalizzato (MAIUSCOLO)
    
    Esempi:
        >>> # Mock XML con società
        >>> fattura = {"FatturaElettronicaHeader": {"CedentePrestatore": 
        ...     {"DatiAnagrafici": {"Anagrafica": {"Denominazione": "ACME SRL"}}}}}
        >>> estrai_fornitore_xml(fattura)
        'ACME SRL'
    """
    # Import locale per evitare circular dependency
    from .formatters import safe_get
    
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
            return fornitore
        
        # Priorità 2: Nome + Cognome (persona fisica)
        nome = safe_get(anagrafica, ['Nome'], default=None, keep_list=False)
        cognome = safe_get(anagrafica, ['Cognome'], default=None, keep_list=False)
        
        nome_str = nome.strip() if nome and isinstance(nome, str) else ""
        cognome_str = cognome.strip() if cognome and isinstance(cognome, str) else ""
        
        if nome_str and cognome_str:
            fornitore = f"{nome_str} {cognome_str}".upper()
            return fornitore
        elif cognome_str:  # Solo cognome
            fornitore = cognome_str.upper()
            return fornitore
        elif nome_str:  # Solo nome
            fornitore = nome_str.upper()
            return fornitore
        
        # Fallback finale
        logger.warning("⚠️ Nessun campo fornitore trovato in Anagrafica")
        return 'Fornitore Sconosciuto'
        
    except Exception as e:
        logger.warning(f"⚠️ Errore estrazione fornitore: {e}")
        return 'Fornitore Sconosciuto'


def format_fattura_label(
    file_name: str,
    fornitore: str = 'Sconosciuto',
    totale: float = 0.0,
    num_righe: int = 0,
    data: str = '',
    max_file_chars: int = 0,
) -> str:
    """Formato label fattura: FORNITORE — €123,00 · 6 righe · 2026-03-19 · nome_file.xml"""
    fornitore_upper = (fornitore or 'Sconosciuto').strip().upper()
    # Mostra filename completo; eventuale ellissi visiva viene gestita dal componente UI.
    fname = str(file_name or '').strip()
    if max_file_chars and len(fname) > max_file_chars:
        ext = ''
        if '.' in fname:
            ext = fname[fname.rfind('.'):]
        chars_for_name = max(3, max_file_chars - len(ext))
        fname_short = fname[:chars_for_name] + '\u2026' + ext
    else:
        fname_short = fname
    righe_label = 'riga' if num_righe == 1 else 'righe'
    data_str = str(data or 'N/D').strip()
    return (
        f"🏭 {fornitore_upper} \u2014 💶 \u20ac{totale:,.2f} \u00b7 "
        f"📦 {num_righe} {righe_label} \u00b7 📅 {data_str} \u00b7 📄 {fname_short}"
    )


def aggiungi_icona_categoria(
    nome_categoria: str,
    supabase_client=None
) -> str:
    """
    Aggiunge icona emoji al nome categoria (query DB).
    
    Args:
        nome_categoria: "CARNE"
        supabase_client: istanza Supabase client (opzionale)
    
    Returns:
        str: "🍖 CARNE" (con icona da DB) o "CARNE" se fallback
    
    Note:
        - Richiede connessione Supabase (tabella 'categorie')
        - Fallback graceful senza icona se DB non disponibile
    
    Esempi:
        >>> aggiungi_icona_categoria("CARNE", None)
        'CARNE'
        >>> # Con DB mockato: aggiungi_icona_categoria("CARNE", mock_client)
        >>> # '🍖 CARNE'
    """
    if supabase_client is None:
        # Fallback: ritorna senza icona
        return nome_categoria
    
    try:
        # Query icona da database
        response = supabase_client.table('categorie')\
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
        
    except Exception as e:
        logger.warning(f"Errore query icona per categoria '{nome_categoria}': {e}")
        return nome_categoria
