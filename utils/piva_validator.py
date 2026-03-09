"""
Validatore Partita IVA italiana.
Conforme a normativa: 11 cifre numeriche + checksum Luhn modificato.

Questo modulo fornisce:
- Validazione formato P.IVA italiana
- Verifica checksum (algoritmo Luhn per P.IVA)
- Normalizzazione (rimozione spazi e caratteri non numerici)

Note:
    - NON include verifica API VIES (posticipata)
    - Validazione solo formato, non esistenza reale
"""

import re
from typing import Tuple
import logging
from config.logger_setup import get_logger

# Logger
logger = get_logger('piva')


def valida_formato_piva(piva: str) -> Tuple[bool, str]:
    """
    Valida formato P.IVA italiana.
    
    Regole validazione:
    1. Esattamente 11 caratteri (dopo pulizia)
    2. Solo cifre numeriche
    3. Checksum valido (algoritmo Luhn modificato per P.IVA italiana)
    
    Args:
        piva: Stringa P.IVA da validare (può contenere spazi)
    
    Returns:
        Tuple[bool, str]:
            - (True, "") se P.IVA valida
            - (False, "messaggio errore") se P.IVA invalida
    
    Esempi:
        >>> valida_formato_piva("12345678903")
        (True, "")
        
        >>> valida_formato_piva("123")
        (False, "❌ La P.IVA deve contenere esattamente 11 cifre (trovate: 3)")
        
        >>> valida_formato_piva("1234567890A")
        (False, "❌ La P.IVA può contenere solo numeri")
    """
    if not piva:
        return False, "❌ P.IVA obbligatoria"
    
    # Normalizza: rimuovi spazi, trattini, punti
    piva_pulita = normalizza_piva(piva)
    
    # 1. Verifica lunghezza esatta 11 cifre
    if len(piva_pulita) != 11:
        return False, f"❌ La P.IVA deve contenere esattamente 11 cifre (trovate: {len(piva_pulita)})"
    
    # 2. Verifica solo numeri
    if not piva_pulita.isdigit():
        return False, "❌ La P.IVA può contenere solo numeri"
    
    # 3. Verifica checksum
    if not _verifica_checksum_piva(piva_pulita):
        return False, "❌ P.IVA non valida: errore nel codice di controllo"
    
    return True, ""


def _verifica_checksum_piva(piva: str) -> bool:
    """
    Verifica checksum P.IVA italiana.
    
    Algoritmo specifico per P.IVA italiana (diverso da Luhn standard):
    
    1. Somma cifre in posizione dispari (1°, 3°, 5°, 7°, 9°, 11°)
    2. Per cifre in posizione pari (2°, 4°, 6°, 8°, 10°):
       - Moltiplica per 2
       - Se risultato > 9, sottrai 9 (oppure somma le cifre)
    3. Somma totale modulo 10 deve essere 0
    
    Args:
        piva: Stringa di 11 cifre (già validata come numerica)
    
    Returns:
        bool: True se checksum valido, False altrimenti
    """
    if len(piva) != 11 or not piva.isdigit():
        return False
    
    cifre = [int(c) for c in piva]
    
    # Somma cifre in posizione dispari (indici 0, 2, 4, 6, 8, 10)
    somma_dispari = sum(cifre[i] for i in range(0, 11, 2))
    
    # Somma cifre in posizione pari (indici 1, 3, 5, 7, 9)
    somma_pari = 0
    for i in range(1, 10, 2):
        doppio = cifre[i] * 2
        # Se > 9, sottrai 9 (equivalente a sommare le cifre)
        somma_pari += doppio if doppio < 10 else (doppio - 9)
    
    # Totale deve essere divisibile per 10
    totale = somma_dispari + somma_pari
    return totale % 10 == 0


def normalizza_piva(piva: str) -> str:
    """
    Normalizza P.IVA rimuovendo caratteri non numerici.
    
    Rimuove:
    - Spazi
    - Trattini
    - Punti
    - Qualsiasi carattere non numerico
    
    Args:
        piva: Stringa P.IVA con possibili formattazioni
    
    Returns:
        str: P.IVA con sole cifre numeriche
    
    Esempi:
        >>> normalizza_piva("123 456 789 01")
        '12345678901'
        
        >>> normalizza_piva("IT12345678901")
        '12345678901'
        
        >>> normalizza_piva("123-456-789-01")
        '12345678901'
    """
    if not piva:
        return ""
    
    # Rimuovi prefisso IT se presente
    piva_upper = piva.upper().strip()
    if piva_upper.startswith('IT'):
        piva_upper = piva_upper[2:]
    
    # Rimuovi tutti i caratteri non numerici
    return re.sub(r'[^0-9]', '', piva_upper)


def verifica_piva_duplicata(piva: str, supabase_client, exclude_user_id: str = None) -> Tuple[bool, str]:
    """
    Verifica se P.IVA è già registrata da altro utente.
    
    Args:
        piva: P.IVA da verificare (già normalizzata)
        supabase_client: Client Supabase per query
        exclude_user_id: ID utente da escludere (per modifica profilo)
    
    Returns:
        Tuple[bool, str]:
            - (True, "") se P.IVA disponibile
            - (False, "email@esistente.it") se già registrata
    """
    try:
        piva_norm = normalizza_piva(piva)
        
        if not piva_norm:
            return True, ""  # P.IVA vuota permessa (NULL)
        
        query = supabase_client.table('users')\
            .select('email')\
            .eq('partita_iva', piva_norm)
        
        # Escludi utente corrente se sta modificando il proprio profilo
        if exclude_user_id:
            query = query.neq('id', exclude_user_id)
        
        result = query.execute()
        
        if result.data and len(result.data) > 0:
            email_esistente = result.data[0].get('email', 'altro utente')
            return False, email_esistente
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Errore verifica P.IVA duplicata: {e}")
        return True, ""  # In caso di errore DB, non bloccare


# ============================================================
# TEST UNIT (esegui con: python -m utils.piva_validator)
# ============================================================
if __name__ == "__main__":
    # Test casi validi
    test_valide = [
        "12345678903",  # P.IVA di test valida
        "00000000000",  # Tutti zeri (checksum valido)
    ]
    
    # Test casi invalidi
    test_invalide = [
        ("123", "troppo corta"),
        ("1234567890123", "troppo lunga"),
        ("1234567890A", "contiene lettera"),
        ("12345678901", "checksum errato"),
    ]
    
    print("=== TEST P.IVA VALIDE ===")
    for piva in test_valide:
        valida, msg = valida_formato_piva(piva)
        print(f"{piva}: {'✅ VALIDA' if valida else f'❌ INVALIDA - {msg}'}")
    
    print("\n=== TEST P.IVA INVALIDE ===")
    for piva, motivo in test_invalide:
        valida, msg = valida_formato_piva(piva)
        print(f"{piva} ({motivo}): {'❌ CORRETTO - ' + msg if not valida else '⚠️ FALSO POSITIVO'}")
    
    print("\n=== TEST NORMALIZZAZIONE ===")
    test_normalizza = [
        "IT 123 456 789 01",
        "12-345-678-901",
        "  12345678901  ",
    ]
    for piva in test_normalizza:
        print(f"'{piva}' → '{normalizza_piva(piva)}'")
