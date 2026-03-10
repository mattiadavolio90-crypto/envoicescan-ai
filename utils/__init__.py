"""
Utils package per FCI_PROJECT.

Moduli:
- text_utils: Normalizzazione e manipolazione testo
- validation: Validazioni business logic
- formatters: Formattazione e conversione dati
"""

# Esporta funzioni principali per import semplificato
from .text_utils import (
    normalizza_descrizione,
    get_descrizione_normalizzata_e_originale,
    normalizza_stringa,
    estrai_nome_categoria,
    estrai_fornitore_xml,
    aggiungi_icona_categoria
)

from .validation import (
    is_dicitura_sicura,
    is_sconto_omaggio_sicuro,
    verifica_integrita_fattura,
    is_prezzo_valido
)

from .formatters import (
    converti_in_base64,
    safe_get,
    calcola_prezzo_standard_intelligente,
    carica_categorie_da_db,
    log_upload_event
)

__all__ = [
    # text_utils
    'normalizza_descrizione',
    'get_descrizione_normalizzata_e_originale',
    'normalizza_stringa',
    'estrai_nome_categoria',
    'estrai_fornitore_xml',
    'aggiungi_icona_categoria',
    # validation
    'is_dicitura_sicura',
    'is_sconto_omaggio_sicuro',
    'verifica_integrita_fattura',
    'is_prezzo_valido',
    # formatters
    'converti_in_base64',
    'safe_get',
    'calcola_prezzo_standard_intelligente',
    'carica_categorie_da_db',
    'log_upload_event'
]
