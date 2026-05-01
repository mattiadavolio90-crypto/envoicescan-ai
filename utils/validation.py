"""
Modulo validation per OH YEAH! Hub.

Funzioni per:
- Validazione diciture vs prodotti
- Classificazione righe speciali (diciture / omaggi / storni)
- Validazione integrità fatture
- Validazione prezzi
"""

import logging
from typing import Optional, Dict

from config.constants import (
    REGEX_LETTERE_MINIME,
    REGEX_PATTERN_BOLLA
)
from config.logger_setup import get_logger

logger = get_logger('validation')


SPECIAL_ROW_DICITURA = 'dicitura'
SPECIAL_ROW_SCONTO_OMAGGIO = 'sconto_omaggio'
SPECIAL_ROW_STORNO = 'storno'
SPECIAL_ROW_NORMALE = 'normale'
SPECIAL_ROW_DA_VERIFICARE = 'da_verificare'

_NOTE_EQUIVALENTS = {'📝 NOTE E DICITURE', 'NOTE E DICITURE'}

_PURE_DICITURE_EXACT = {
    'FUSTI',
    'CASSA 750/LITRO X12',
    'COSTI DI SPEDIZIONE',
}

_PURE_DICITURE_PREFIXES = (
    'DDT ',
    'BOLLA ',
    'RIF. FATTURA',
    'DOCUMENTO ',
    'ORDINE ',
)

_ECONOMIC_SERVICE_KEYWORDS = (
    'LAVORAZ',
    'DISOSSO',
    'PORZIONAT',
    'FILETT',
    'AFFETT',
    'NOLEGG',
    'DIRITTO DI CHIAMATA',
    'USCITA TECNICA',
    'INTERVENTO',
    'ASSISTENZA',
    'INSTALLAZ',
    'CAUZION',
    'VUOTO A RENDERE',
)

_ZERO_DISCOUNT_KEYWORDS = (
    'OMAGGIO',
    'OMAGGI',
    'CAMPIONE GRATUITO',
    'MERCE IN OMAGGIO',
    'PRODOTTO IN OMAGGIO',
    'SCONTO',
    'PROMO',
)

_STORNO_KEYWORDS = (
    'RESO',
    'ACCREDITO',
    'NOTA CREDITO',
    'N.C.',
    'STORNO',
    'ABBUONO',
    'PREMIO POSTICIPATO',
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def is_note_e_diciture(categoria: str) -> bool:
    return str(categoria or '').strip() in _NOTE_EQUIVALENTS


def _is_pure_dicitura_extra(desc_upper: str) -> bool:
    if desc_upper in _PURE_DICITURE_EXACT:
        return True
    return desc_upper.startswith(_PURE_DICITURE_PREFIXES)


def classify_special_row(
    descrizione: str,
    categoria: str = '',
    prezzo: float = 0.0,
    totale_riga: float = 0.0,
    quantita: float = 1.0,
    tipo_documento: str = '',
    needs_review: bool = False,
) -> Dict[str, object]:
    """Classifica una riga speciale senza richiedere colonne aggiuntive nel DB."""
    desc_upper = str(descrizione or '').strip().upper()
    categoria_clean = str(categoria or '').strip()

    try:
        prezzo_num = float(prezzo or 0)
    except (TypeError, ValueError):
        prezzo_num = 0.0

    try:
        totale_num = float(totale_riga or 0)
    except (TypeError, ValueError):
        totale_num = 0.0

    try:
        quantita_num = float(quantita or 1)
    except (TypeError, ValueError):
        quantita_num = 1.0

    tipo_documento = str(tipo_documento or '').strip().upper()

    is_zero_amount = abs(prezzo_num) < 1e-9 or abs(totale_num) < 1e-9
    is_negative_amount = prezzo_num < -1e-9 or totale_num < -1e-9 or tipo_documento == 'TD04'
    note_category = is_note_e_diciture(categoria_clean)
    meaningful_category = categoria_clean not in {'', 'Da Classificare', *list(_NOTE_EQUIVALENTS)}

    strong_dicitura = is_dicitura_sicura(descrizione, prezzo_num, quantita_num) or _is_pure_dicitura_extra(desc_upper)
    economic_service = _contains_any(desc_upper, _ECONOMIC_SERVICE_KEYWORDS)
    omaggio_marker = _contains_any(desc_upper, _ZERO_DISCOUNT_KEYWORDS)
    storno_marker = _contains_any(desc_upper, _STORNO_KEYWORDS)
    economic_hint = economic_service or omaggio_marker or storno_marker or meaningful_category

    if is_negative_amount:
        bucket = SPECIAL_ROW_DICITURA if strong_dicitura and not economic_hint else SPECIAL_ROW_STORNO
    elif is_zero_amount:
        if storno_marker and not omaggio_marker:
            bucket = SPECIAL_ROW_STORNO
        elif strong_dicitura and not economic_hint:
            bucket = SPECIAL_ROW_DICITURA
        elif note_category and not (economic_service or omaggio_marker or storno_marker):
            bucket = SPECIAL_ROW_DICITURA
        elif economic_hint:
            bucket = SPECIAL_ROW_SCONTO_OMAGGIO
        else:
            bucket = SPECIAL_ROW_DA_VERIFICARE
    else:
        if strong_dicitura and not economic_hint:
            bucket = SPECIAL_ROW_DICITURA
        else:
            bucket = SPECIAL_ROW_NORMALE

    return {
        'bucket': bucket,
        'is_special': bucket != SPECIAL_ROW_NORMALE,
        'include_in_dashboard': bucket in {SPECIAL_ROW_NORMALE, SPECIAL_ROW_SCONTO_OMAGGIO},
        'include_in_price_average': bucket in {SPECIAL_ROW_NORMALE, SPECIAL_ROW_SCONTO_OMAGGIO},
        'should_review': bool(needs_review) or bucket == SPECIAL_ROW_DA_VERIFICARE,
        'force_categoria': '📝 NOTE E DICITURE' if bucket == SPECIAL_ROW_DICITURA else None,
    }


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
        "SCONTO QUANTITÀ", "SCONTO VOLUME", "SCONTO FINALE", "SCONTI FINALI", "ABBUONO",
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


def is_sconto_omaggio_sicuro(descrizione: str) -> bool:
    """
    Identifica sconti, omaggi e abbuoni con ALTA confidenza.
    Ritorna True SOLO se certissimi che è sconto/omaggio, non dicitura.
    
    Se True → la categoria assegnata da AI/keyword è corretta (es: CARNI per "SCONTO MERCE CARNI"),
    quindi va confermata e salvata in memoria globale.
    
    Args:
        descrizione: testo descrizione riga
    
    Returns:
        bool: True se sconto/omaggio certo
    """
    if not descrizione:
        return False
    
    desc_upper = descrizione.upper().strip()
    
    KEYWORD_SCONTO_OMAGGIO = [
        # Sconti merce
        "SCONTO MERCE", "SC. MERCE", "SCONTO IN MERCE", "SCONTO PROMOZIONALE",
        "SCONTO INCONDIZ", "SCONTO CONDIZ", "SCONTO QUANTITA", "SCONTO CLIENTE",
        "SCONTO FINE ANNO", "SCONTO VOLUME", "SCONTO EXTRA", "SC.MERCE",
        "SCONTO COMM", "SCONTO COMMER",
        
        # Omaggi
        "OMAGGIO", "CAMPIONE GRATUITO", "CAMPIONE OMAGGIO",
        "MERCE IN OMAGGIO", "PRODOTTO IN OMAGGIO", "OMAGGI",
        
        # Abbuoni / resi
        "ABBUONO MERCE", "ABBUONO SU MERCE", "ABBUONO",
        "RESO MERCE", "MERCE RESA", "RESO SU MERCE",
        "NOTA CREDITO MERCE", "NC MERCE",
        
        # Promo
        "PROMOZIONE", "PROMO ", "OFFERTA SPECIALE",
    ]
    
    if any(kw in desc_upper for kw in KEYWORD_SCONTO_OMAGGIO):
        logger.info(f"✓ Sconto/omaggio identificato: {descrizione}")
        return True
    
    return False


# ============================================================
# VALIDAZIONE INTEGRITÀ FATTURE
# ============================================================

def verifica_integrita_fattura(
    nome_file: str,
    dati_prodotti: list,
    user_id: str,
    supabase_client,
    righe_db_override: Optional[int] = None,
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
        
        # Se disponibile, usa il numero righe confermate della singola insert appena eseguita.
        # Evita falsi positivi quando lo stesso file_origine è già presente storicamente.
        if righe_db_override is not None:
            righe_db = int(righe_db_override)
        else:
            # Fallback legacy: conteggio storico per file_origine.
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
