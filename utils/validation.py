"""
Modulo validation per FCI_PROJECT.

Funzioni per:
- Validazione diciture vs prodotti
- Validazione integrità fatture
- Validazione prezzi
"""

import logging
from typing import Optional, Dict

from config.constants import (
    REGEX_LETTERE_MINIME,
    REGEX_PATTERN_BOLLA
)

logger = logging.getLogger(__name__)


# ============================================================
# VALIDAZIONE DICITURE
# ============================================================

def is_dicitura_sicura(descrizione: str, prezzo: float, quantita: float) -> bool:
    """
    Identifica diciture con ALTA confidenza (approccio conservativo).
    Ritorna True SOLO se CERTISSIMI che è dicitura, non prodotto.
    
    Controlli:
    1. Keyword ad ALTISSIMA confidenza (zero ambiguità)
    2. Solo numeri/simboli + molto corta
    3. Pattern "X DEL GG-MM-AAAA" (es: "BOLL DEL 12-12-2025")
    4. Parole singole specifiche (DDT, TRASPORTO, ecc.)
    
    Args:
        descrizione: testo descrizione riga
        prezzo: prezzo_unitario (non usato ma disponibile)
        quantita: quantità (non usato ma disponibile)
    
    Returns:
        bool: True se dicitura certa, False altrimenti
    
    Esempi:
        >>> is_dicitura_sicura("BOLLA N. 12345", 0, 1)
        True
        >>> is_dicitura_sicura("TRASPORTO GRATUITO", 0, 1)
        True
        >>> is_dicitura_sicura("CONTRIBUTO CONAI", 0.50, 1)
        True
        >>> is_dicitura_sicura("PASTA PENNE 500G", 2.50, 1)
        False
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
# VALIDAZIONE INTEGRITÀ FATTURE
# ============================================================

def verifica_integrita_fattura(
    nome_file: str,
    dati_prodotti: list,
    user_id: str,
    supabase_client
) -> Optional[Dict]:
    """
    Verifica che tutte le righe del file siano state salvate su Supabase.
    
    ⚠️ CRITICO: Conta SOLO le righe di QUESTO FILE, non l'utente intero!
    
    Args:
        nome_file: nome file fattura
        dati_prodotti: lista righe parsed
        user_id: UUID utente
        supabase_client: istanza Supabase client
    
    Returns:
        dict: {
            "file": str,
            "righe_parsed": int,
            "righe_db": int (SOLO questo file),
            "perdite": int,
            "integrita_ok": bool
        } o None se errore
    
    Esempi:
        >>> # Mock result
        >>> {"file": "fattura.xml", "righe_parsed": 50, "righe_db": 50, 
        ...  "perdite": 0, "integrita_ok": True}
    """
    if supabase_client is None:
        logger.warning("verifica_integrita_fattura: supabase_client non fornito")
        return None
    
    try:
        # Conta righe nel DataFrame parsed
        righe_parsed = len(dati_prodotti)
        
        # Query specifica per il file_origine (doppio filtro user_id + file_origine)
        response = supabase_client.table("fatture") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .eq("file_origine", nome_file) \
            .execute()
        
        
        # Usa count esatto dalle metadata della query (più affidabile)
        righe_db = response.count if response.count is not None else len(response.data) if response.data else 0
        
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
            logger.error(f"🚨 DISCREPANZA {nome_file}: parsed={righe_parsed} vs db={righe_db}")
        else:
            logger.info(f"✅ Integrità OK: {nome_file} - {righe_db} righe confermate")
        
        return risultato
    
    except Exception as e:
        logger.error(f"Errore verifica integrità {nome_file}: {e}")
        return None


# ============================================================
# VALIDAZIONE PREZZI
# ============================================================

def is_prezzo_valido(prezzo: float, min_val: float = 0.001, max_val: float = 100000) -> bool:
    """
    Verifica se un prezzo è in range valido.
    
    Args:
        prezzo: valore da validare
        min_val: valore minimo accettabile (default 0.001)
        max_val: valore massimo accettabile (default 100000)
    
    Returns:
        bool: True se valido, False altrimenti
    
    Esempi:
        >>> is_prezzo_valido(10.50)
        True
        >>> is_prezzo_valido(0)
        False
        >>> is_prezzo_valido(-5)
        False
        >>> is_prezzo_valido(150000)
        False
        >>> is_prezzo_valido(0.5, min_val=1.0)
        False
    """
    try:
        p = float(prezzo)
        return min_val <= p <= max_val
    except (ValueError, TypeError):
        return False
