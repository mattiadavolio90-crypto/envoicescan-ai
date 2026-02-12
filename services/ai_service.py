"""
AI Service - Classificazione Intelligente e Gestione Memoria Prodotti

Gestisce:
- Classificazione automatica prodotti con OpenAI
- Sistema memoria ibrida (admin + locale utente + globale)
- Cache in-memory per eliminare N+1 queries
- Correzioni basate su dizionario keyword
- Retry logic per API OpenAI

ARCHITETTURA MEMORIA (3 livelli):
==============================

1️⃣ MEMORIA ADMIN (classificazioni_manuali)
   - Priorità: MASSIMA
   - Uso: Correzioni manuali amministratore
   - Scope: Globale

2️⃣ MEMORIA LOCALE (prodotti_utente)
   - Priorità: ALTA (dopo admin)
   - Uso: Personalizzazioni cliente specifico
   - Scope: Solo per l'utente proprietario
   - ⭐ QUANDO: Cliente modifica manualmente una categoria

3️⃣ MEMORIA GLOBALE (prodotti_master)
   - Priorità: MEDIA (dopo locale e admin)
   - Uso: Categorizzazioni automatiche condivise
   - Scope: TUTTI i clienti
   - ⭐ QUANDO: AI/Dizionario/Keyword categorizza automaticamente

FLUSSI PRINCIPALI:
==================

📥 CATEGORIZZAZIONE AUTOMATICA (nuovo articolo):
   1. Check memoria admin → se trovato, usa quello
   2. Check memoria locale cliente → se trovato, usa quello
   3. Check memoria globale → se trovato, usa quello
   4. Keyword/Dizionario → categorizza + SALVA in memoria GLOBALE
   5. AI GPT → categorizza + SALVA in memoria GLOBALE

✏️ MODIFICA MANUALE CLIENTE:
   - Salva in memoria LOCALE (prodotti_utente)
   - NON tocca memoria globale
   - Solo il cliente vede la sua personalizzazione
   - Altri clienti continuano a usare memoria globale

🔧 MODIFICA ADMIN (TAB "Memoria Globale"):
   - Salva in memoria GLOBALE (prodotti_master)
   - Propaga a TUTTE le fatture nel database
   - Tutti i clienti futuri vedono la modifica
   - ⚠️ Rispetta personalizzazioni locali esistenti

👁️ ADMIN IMPERSONIFICATO:
   - Comportamento come CLIENTE normale
   - Modifiche salvate in memoria LOCALE del cliente
   - Non impatta altri clienti

Pattern: Dependency Injection per testabilità
"""

import json
import os
import re
import shutil
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import streamlit as st
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, APIError

# Import da moduli interni
from config.constants import DIZIONARIO_CORREZIONI, TUTTE_LE_CATEGORIE
from utils.text_utils import get_descrizione_normalizzata_e_originale, normalizza_stringa
from utils.validation import is_dicitura_sicura

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('ai')

# ============================================================
# COSTANTI
# ============================================================
MEMORIA_AI_FILE = "memoria_ai_correzioni.json"
RETRIABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, APIError)
MAX_TOKENS_PER_BATCH = 12000  # Limite sicuro per evitare timeout

# ============================================================
# CACHE GLOBALE IN-MEMORY (ELIMINA N+1 QUERY)
# ============================================================
_memoria_cache = {
    'prodotti_utente': {},      # {user_id: {descrizione: categoria}}
    'prodotti_master': {},      # {descrizione: categoria}
    'classificazioni_manuali': {},  # {descrizione: {categoria, is_dicitura}}
    'version': 0,               # Incrementato ad ogni invalidazione
    'loaded': False
}

# Flag per disabilitare la memoria globale (solo sessione)
_disable_global_memory = False

def set_global_memory_enabled(enabled: bool):
    """
    Abilita/Disabilita l'uso della memoria globale (prodotti_master) in questa sessione.
    Utile per testare la logica senza influenze della memoria condivisa.
    """
    global _disable_global_memory
    _disable_global_memory = not enabled
    state = "DISABILITATA" if _disable_global_memory else "ABILITATA"
    logger.info(f"⚙️ Memoria Globale: {state}")


# ============================================================
# INIZIALIZZAZIONE OPENAI CLIENT
# ============================================================
@st.cache_resource
def _get_openai_client() -> OpenAI:
    """
    Ottiene client OpenAI singleton (cached).
    
    Returns:
        OpenAI: Client inizializzato e cached per tutta la sessione
        
    Raises:
        ValueError: Se API key non trovata in secrets
    """
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception as e:
        logger.exception("API Key OpenAI non trovata")
        raise ValueError("API Key OpenAI mancante") from e
    
    return OpenAI(api_key=api_key)


# ============================================================
# FUNZIONI MEMORIA CACHE
# ============================================================

def carica_memoria_completa(user_id: str, supabase_client=None) -> Dict[str, Any]:
    """
    Carica TUTTE le memorie in una volta sola (1 query per tabella invece di N query).
    Elimina completamente il problema N+1 query.
    
    Args:
        user_id: UUID utente corrente
        supabase_client: Client Supabase (opzionale, usa default se None)
    
    Returns:
        dict: Cache completa con tutte le memorie
    """
    global _memoria_cache
    
    # Se già caricata, ritorna cache esistente
    if _memoria_cache['loaded']:
        return _memoria_cache
    
    # Usa client iniettato o fallback a singleton
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return _memoria_cache
    
    try:
        # Query 1: Carica TUTTA la memoria locale utente (1 query sola)
        result_locale = supabase_client.table('prodotti_utente')\
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
        result_globale = supabase_client.table('prodotti_master')\
            .select('descrizione, categoria')\
            .execute()
        
        if result_globale.data:
            _memoria_cache['prodotti_master'] = {
                row['descrizione']: row['categoria'] 
                for row in result_globale.data
            }
            logger.info(f"📦 Cache GLOBALE caricata: {len(result_globale.data)} prodotti")
        
        # Query 3: Carica TUTTE le classificazioni manuali admin (1 query sola)
        result_manuali = supabase_client.table('classificazioni_manuali')\
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


def ottieni_categoria_prodotto(descrizione: str, user_id: str) -> str:
    """
    Ottiene categoria prodotto con priorità IBRIDA usando CACHE IN-MEMORY.
    ELIMINA N+1 QUERY: usa cache invece di query ripetute.
    
    PRIORITÀ (allineata con categorizza_con_memoria):
    1. Memoria ADMIN (classificazioni_manuali) - PRIORITÀ ASSOLUTA
    2. Memoria LOCALE utente (prodotti_utente) - personalizzazioni cliente
    3. Memoria GLOBALE (prodotti_master) - condivisa tra tutti i clienti
    4. "Da Classificare" (se non trovato in nessuna memoria)
    
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
        
        # Normalizza per matching consistente (stesso trattamento di categorizza_con_memoria)
        desc_stripped = descrizione.strip()
        
        # 0️⃣ Check memoria ADMIN (classificazioni_manuali) - PRIORITÀ ASSOLUTA
        if desc_stripped in _memoria_cache['classificazioni_manuali']:
            record = _memoria_cache['classificazioni_manuali'][desc_stripped]
            if record.get('is_dicitura'):
                logger.info(f"📋 Memoria Admin (cache/ottieni): '{descrizione[:40]}' → DICITURA")
                return "📝 NOTE E DICITURE"
            else:
                logger.info(f"📋 Memoria Admin (cache/ottieni): '{descrizione[:40]}' → {record['categoria']}")
                return record['categoria']
        
        # 1️⃣ Check memoria LOCALE utente (da cache, 0 query!)
        if user_id in _memoria_cache['prodotti_utente']:
            locale_dict = _memoria_cache['prodotti_utente'][user_id]
            if descrizione in locale_dict:
                categoria = locale_dict[descrizione]
                
                # ✅ Traccia come memoria per icona 🧠
                try:
                    import streamlit as st
                    if 'righe_memoria_appena_categorizzate' not in st.session_state:
                        st.session_state.righe_memoria_appena_categorizzate = []
                    if descrizione not in st.session_state.righe_memoria_appena_categorizzate:
                        st.session_state.righe_memoria_appena_categorizzate.append(descrizione)
                except Exception:
                    pass  # Ignora se streamlit non disponibile
                
                return categoria
        
        # 2️⃣ Check memoria GLOBALE (da cache, 0 query!) se abilitata
        if not _disable_global_memory:
            # Prova con descrizione esatta
            if descrizione in _memoria_cache['prodotti_master']:
                categoria = _memoria_cache['prodotti_master'][descrizione]
                
                # ✅ Traccia come memoria per icona 🧠
                try:
                    import streamlit as st
                    if 'righe_memoria_appena_categorizzate' not in st.session_state:
                        st.session_state.righe_memoria_appena_categorizzate = []
                    if descrizione not in st.session_state.righe_memoria_appena_categorizzate:
                        st.session_state.righe_memoria_appena_categorizzate.append(descrizione)
                except Exception:
                    pass  # Ignora se streamlit non disponibile
                
                return categoria
            
            # Prova anche con descrizione normalizzata (per matching consistente)
            desc_normalized, _ = get_descrizione_normalizzata_e_originale(descrizione)
            if desc_normalized != descrizione and desc_normalized in _memoria_cache['prodotti_master']:
                categoria = _memoria_cache['prodotti_master'][desc_normalized]
                
                try:
                    import streamlit as st
                    if 'righe_memoria_appena_categorizzate' not in st.session_state:
                        st.session_state.righe_memoria_appena_categorizzate = []
                    if descrizione not in st.session_state.righe_memoria_appena_categorizzate:
                        st.session_state.righe_memoria_appena_categorizzate.append(descrizione)
                except Exception:
                    pass
                
                return categoria
        
        # 3️⃣ Fallback
        return "Da Classificare"
        
    except Exception as e:
        logger.warning(f"Errore ottieni_categoria (cache) per '{descrizione[:40]}...': {e}")
        return "Da Classificare"


# ============================================================
# FUNZIONI CORREZIONE E CATEGORIZZAZIONE
# ============================================================

# ── PRE-COMPUTED KEYWORD MATCHING (compilato una volta all'import) ──────────
# Keywords contenitori/packaging → BASSA PRIORITÀ
# Se non c'è nessun alimento, questi matchano e danno MATERIALE DI CONSUMO
_KEYWORDS_CONTENITORI = frozenset({
    "VASCHETTA", "VASCHETTE", "VASCHETTINA", "VASC",
    "CONFEZIONE", "CONF", "BUSTA", "SCATOLA", "CARTONE",
    "PACCO", "BARATTOLO", "BOTTIGLIA", "LATTINA",
})

def _build_compiled_patterns() -> Tuple[list, list]:
    """
    Costruisce le liste di (pattern_compilato, categoria) ordinate per lunghezza keyword decrescente.
    Chiamata UNA VOLTA all'import del modulo. Ritorna (patterns_alimenti, patterns_contenitori).
    """
    patterns_alimenti = []
    patterns_contenitori = []
    
    for keyword, categoria in sorted(DIZIONARIO_CORREZIONI.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(r'(?:^|[\s\W])' + re.escape(keyword) + r'(?:[\s\W]|$)')
        if keyword in _KEYWORDS_CONTENITORI:
            patterns_contenitori.append((pattern, categoria))
        else:
            patterns_alimenti.append((pattern, categoria))
    
    return patterns_alimenti, patterns_contenitori

# Compilati una volta all'avvio (0 overhead nelle chiamate successive)
_PATTERNS_ALIMENTI, _PATTERNS_CONTENITORI = _build_compiled_patterns()


def applica_correzioni_dizionario(descrizione: str, categoria_ai: str) -> str:
    """
    Applica correzioni basate su keyword nel dizionario con PRIORITÀ INTELLIGENTE.
    
    STRATEGIA: I CIBI hanno priorità sui CONTENITORI.
    - Se trova un ALIMENTO (SALSICCIA, CAROTE, etc.), lo classifica per quello
    - Se trova SOLO un CONTENITORE (VASC, CONF, BUSTA, etc.), classifica MATERIALE DI CONSUMO
    - Ignora i contenitori se c'è un alimento presente
    
    Usa pattern regex pre-compilati e pre-ordinati per lunghezza decrescente (ottimizzazione).
    
    Args:
        descrizione: testo descrizione prodotto
        categoria_ai: categoria assegnata da AI (fallback)
    
    Returns:
        str: categoria corretta o categoria_ai se nessun match
    """
    if not descrizione or not isinstance(descrizione, str):
        return categoria_ai
    
    # Padding per garantire match ai bordi (i pattern usano boundary [\s\W])
    desc_padded = ' ' + descrizione.upper() + ' '
    
    # STEP 1: Cerca ALIMENTI (priorità alta) - se trovi uno, ritorna subito
    for pattern, categoria in _PATTERNS_ALIMENTI:
        if pattern.search(desc_padded):
            return categoria
    
    # STEP 2: Cerca CONTENITORI (priorità bassa) - solo se nessun alimento trovato
    for pattern, categoria in _PATTERNS_CONTENITORI:
        if pattern.search(desc_padded):
            return categoria
    
    return categoria_ai


def salva_correzione_in_memoria_locale(
    descrizione: str,
    nuova_categoria: str,
    user_id: str,
    user_email: str,
    supabase_client=None
) -> bool:
    """
    Salva correzione MANUALE del cliente in memoria LOCALE (solo per lui).
    Le modifiche manuali dei clienti NON devono impattare la memoria globale.
    
    PRIORITÀ:
    - Memoria locale (prodotti_utente) ha priorità su memoria globale
    - Se cliente modifica manualmente, vede sempre la sua personalizzazione
    - Altri clienti continuano a usare memoria globale
    
    Args:
        descrizione: descrizione prodotto
        nuova_categoria: categoria scelta dall'utente
        user_id: UUID utente
        user_email: email utente (per log)
        supabase_client: Client Supabase (opzionale)
    
    Returns:
        bool: True se successo, False altrimenti
    """
    # Usa client iniettato o fallback a singleton
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return False
    
    try:
        # Normalizza descrizione
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        logger.info(f"💾 SALVATAGGIO LOCALE: '{desc_normalized}' → {nuova_categoria} (user={user_email})")
        
        # Colonne ESSENZIALI (sicuramente presenti nella tabella)
        upsert_data = {
            'user_id': user_id,
            'descrizione': desc_normalized,
            'categoria': nuova_categoria,
            'updated_at': datetime.now().isoformat()
        }
        
        # Colonne OPZIONALI - aggiungi e rimuovi se il DB le rifiuta
        optional_cols = {
            'volte_visto': 1,
            'classificato_da': f'Manuale ({user_email})'
        }
        
        # Prova con tutte le colonne, rimuovi quelle mancanti una alla volta
        upsert_data.update(optional_cols)
        result = None
        max_retries = len(optional_cols) + 1  # Al massimo rimuoviamo tutte le opzionali
        
        for attempt in range(max_retries):
            try:
                result = supabase_client.table('prodotti_utente').upsert(
                    upsert_data, on_conflict='user_id,descrizione'
                ).execute()
                break  # Successo!
            except Exception as col_err:
                err_msg = str(col_err)
                if 'PGRST204' in err_msg:
                    # Trova quale colonna manca dal messaggio di errore
                    import re
                    match = re.search(r"'(\w+)' column", err_msg)
                    if match:
                        missing_col = match.group(1)
                        logger.warning(f"Colonna '{missing_col}' non trovata nel DB, rimuovo e riprovo")
                        upsert_data.pop(missing_col, None)
                        continue
                raise col_err  # Errore diverso, non gestibile
        
        if result is None:
            logger.error("❌ Upsert fallito dopo rimozione colonne opzionali")
            return False
        
        if result.data:
            logger.info(f"✅ Salvato locale: '{desc_normalized}' → {nuova_categoria}")
        else:
            logger.warning(f"⚠️ Upsert eseguito ma nessun dato restituito")
        
        # Invalida cache per forzare ricaricamento
        invalida_cache_memoria()
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Errore salvataggio memoria locale: {e}")
        logger.exception("Dettaglio errore completo:")
        return False


def salva_correzione_in_memoria_globale(
    descrizione: str,
    vecchia_categoria: str,
    nuova_categoria: str,
    user_email: str,
    supabase_client=None,
    is_admin: bool = False
) -> bool:
    """
    Salva correzione in memoria GLOBALE (condivisa tra tutti i clienti).
    
    ⚠️ USARE SOLO PER:
    - Modifiche dell'admin dalla TAB "Memoria Globale"
    - Admin impersonificato che vuole modificare per tutti
    
    ❌ NON usare per modifiche manuali normali dei clienti → usa salva_correzione_in_memoria_locale()
    
    Args:
        descrizione: descrizione prodotto
        vecchia_categoria: categoria precedente
        nuova_categoria: categoria corretta
        user_email: email utente
        supabase_client: Client Supabase (opzionale)
        is_admin: True se modifica da admin (per log)
    
    Returns:
        bool: True se successo, False altrimenti
    """
    # Usa client iniettato o fallback a singleton
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return False
    
    try:
        # Normalizza descrizione
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        # Check se esiste già in memoria
        existing = supabase_client.table('prodotti_master')\
            .select('id, volte_visto')\
            .eq('descrizione', desc_normalized)\
            .limit(1)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            # AGGIORNA esistente con categoria corretta
            record = existing.data[0]
            
            supabase_client.table('prodotti_master').update({
                'categoria': nuova_categoria,
                'classificato_da': f'Utente ({user_email})',
                'confidence': 'altissima',
                'verified': True,  # ✅ Auto-verifica: correzione manuale = già controllata
                'ultima_modifica': datetime.now().isoformat()
            }).eq('id', record['id']).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()
            
            # Log con prefisso corretto
            prefisso = "🔧 ADMIN" if is_admin else "🟢 GLOBALE"
            logger.info(f"{prefisso}: '{desc_normalized}' {vecchia_categoria} → {nuova_categoria} (by {user_email})")
        
        else:
            # INSERISCI nuovo record con categoria corretta
            supabase_client.table('prodotti_master').insert({
                'descrizione': desc_normalized,
                'categoria': nuova_categoria,
                'classificato_da': f'Admin ({user_email})' if is_admin else f'Utente ({user_email})',
                'confidence': 'altissima',
                'verified': True,  # ✅ Auto-verifica: correzione manuale = già controllata
                'volte_visto': 1,
                'created_at': datetime.now().isoformat(),
                'ultima_modifica': datetime.now().isoformat()
            }).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()
            
            # Log con prefisso corretto
            prefisso = "🔧 ADMIN" if is_admin else "🟢 GLOBALE"
            logger.info(f"{prefisso}: '{desc_normalized}' → {nuova_categoria} (by {user_email})")
        
        return True
    
    except Exception as e:
        logger.error(f"Errore salvataggio correzione in memoria: {e}")
        return False


def categorizza_con_memoria(
    descrizione: str,
    prezzo: float,
    quantita: float,
    user_id: Optional[str] = None,
    supabase_client=None,
    fornitore: Optional[str] = None,
    unita_misura: Optional[str] = None
) -> str:
    """
    Categorizza usando memoria GLOBALE multi-livello con CACHE IN-MEMORY.
    ELIMINA N+1 QUERY: usa cache invece di query ripetute.
    
    PRIORITÀ CORRETTA:
    1. Memoria correzioni admin (classificazioni_manuali) - PRIORITÀ ASSOLUTA
    2. Memoria LOCALE utente (prodotti_utente) - personalizzazioni cliente
    3. Memoria GLOBALE prodotti (prodotti_master) - condivisa tra tutti
    4. Check dicitura (se prezzo = 0)
    5. Regola FORNITORE specifico - categorizzazione automatica
    6. Regola UNITÀ MISURA - categorizzazione automatica
    7. Dizionario keyword - FALLBACK FINALE
    
    Args:
        descrizione: testo descrizione
        prezzo: prezzo_unitario
        quantita: quantità
        user_id: ID utente (per log)
        supabase_client: Client Supabase (opzionale)
        fornitore: Nome fornitore (opzionale)
        unita_misura: Unità di misura normalizzata (opzionale)
    
    Returns:
        str: categoria finale
    """
    global _memoria_cache
    
    # Usa client iniettato o fallback
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception:
            pass  # Procedi senza client
    
    try:
        # Carica cache se non già caricata
        if not _memoria_cache['loaded'] and user_id:
            carica_memoria_completa(user_id, supabase_client)
        
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
        
        if not _disable_global_memory:
            if desc_normalized in _memoria_cache['prodotti_master']:
                categoria = _memoria_cache['prodotti_master'][desc_normalized]
                logger.info(f"🟢 MEMORIA GLOBALE (cache): '{descrizione}' → {categoria} (norm: '{desc_normalized}')")
                return categoria
    
    except Exception as e:
        logger.warning(f"Errore check memoria globale (cache): {e}")
    
    # LIVELLO 4: Check dicitura (se prezzo = 0)
    if prezzo == 0 and is_dicitura_sicura(descrizione, prezzo, quantita):
        return "📝 NOTE E DICITURE"
    
    # LIVELLO 5: Regola FORNITORE specifico (priorità ALTA)
    if fornitore:
        from config.constants import CATEGORIA_PER_FORNITORE
        fornitore_upper = fornitore.strip().upper()
        for fornitore_key, categoria in CATEGORIA_PER_FORNITORE.items():
            if fornitore_key.upper() in fornitore_upper or fornitore_upper in fornitore_key.upper():
                logger.info(f"🏭 FORNITORE: '{descrizione}' → {categoria} (fornitore: {fornitore})")
                return categoria
    
    # LIVELLO 6: Regola UNITÀ MISURA (priorità ALTA)
    if unita_misura:
        from config.constants import UNITA_MISURA_CATEGORIA
        unita_upper = unita_misura.strip().upper()
        if unita_upper in UNITA_MISURA_CATEGORIA:
            categoria = UNITA_MISURA_CATEGORIA[unita_upper]
            logger.info(f"📏 UNITÀ MISURA: '{descrizione}' → {categoria} (U.M.: {unita_misura})")
            return categoria
    
    # LIVELLO 7: Dizionario keyword (fallback)
    categoria_keyword = applica_correzioni_dizionario(descrizione, "Da Classificare")
    
    # 💾 SALVATAGGIO AUTOMATICO IN MEMORIA GLOBALE
    # Se la categoria è diversa da "Da Classificare", salva in memoria globale per futuri clienti
    # QUESTO È CORRETTO: categorizzazioni automatiche (AI/keyword/dizionario) vanno in memoria GLOBALE
    # La memoria globale è condivisa tra TUTTI i clienti per efficienza
    if categoria_keyword != "Da Classificare" and supabase_client:
        try:
            # Normalizza descrizione per salvataggio
            desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
            
            supabase_client.table('prodotti_master').upsert({
                'descrizione': desc_normalized,
                'categoria': categoria_keyword,
                'confidence': 'media',
                'verified': False,  # ⚠️ Da verificare: inserimento automatico
                'volte_visto': 1,
                'classificato_da': 'keyword',
                'created_at': datetime.now().isoformat(),
                'ultima_modifica': datetime.now().isoformat()
            }, on_conflict='descrizione').execute()
            logger.info(f"💾 MEMORIA GLOBALE (auto-save): '{desc_normalized}' (orig: '{desc_original}') → {categoria_keyword} (keyword) - disponibile per TUTTI i clienti")
        except Exception as e:
            logger.warning(f"❌ Errore salvataggio memoria globale per '{descrizione[:40]}': {e}")
    else:
        # AUTO-CATEGORIZZAZIONE FALLITA: nessun match nel dizionario
        # L'articolo NON viene salvato in memoria globale (rimane "Da Classificare")
        # Se il cliente lo categorizza manualmente, andrà in memoria LOCALE (prodotti_utente)
        logger.info(f"⚠️ AUTO-CATEGORIZZAZIONE FALLITA: '{descrizione[:60]}' rimasto 'Da Classificare' (NON salvato in memoria globale)")
    
    return categoria_keyword


# ============================================================
# SVUOTA MEMORIA GLOBALE (DB + file legacy)
# ============================================================

def svuota_memoria_globale(supabase_client=None) -> bool:
    """
    Svuota la memoria globale AI:
    - Cancella tutti i record in 'prodotti_master' su Supabase
    - Invalida cache in-memory
    - Cancella file legacy 'memoria_ai_correzioni.json' se presente
    """
    # Usa client iniettato o fallback
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return False

    try:
        # Preleva tutti gli id per cancellazione batch
        resp = supabase_client.table('prodotti_master').select('id').execute()
        ids = [row['id'] for row in (resp.data or []) if 'id' in row]

        deleted = 0
        if ids:
            # Cancella in batch (blocchi da 1000 per sicurezza)
            batch_size = 1000
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i+batch_size]
                supabase_client.table('prodotti_master').delete().in_('id', batch).execute()
                deleted += len(batch)
        logger.info(f"🗑️ Memoria Globale DB svuotata: {deleted} record rimossi")

        # Invalida cache
        invalida_cache_memoria()

        # Cancella file legacy
        try:
            if os.path.exists(MEMORIA_AI_FILE):
                os.remove(MEMORIA_AI_FILE)
                logger.info("🧹 File legacy memoria AI rimosso")
        except Exception as fe:
            logger.warning(f"Impossibile rimuovere file legacy: {fe}")

        return True

    except Exception as e:
        logger.error(f"Errore svuotamento memoria globale: {e}")
        return False


# ============================================================
# CLASSIFICAZIONE BATCH CON OPENAI
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRIABLE_ERRORS)
)
def classifica_con_ai(
    lista_descrizioni: List[str],
    lista_fornitori: Optional[List[str]] = None,
    openai_client: Optional[OpenAI] = None
) -> List[str]:
    """
    Classificazione AI con JSON strutturato + correzioni dizionario.
    Usa retry automatico per gestire rate limits OpenAI.
    
    Args:
        lista_descrizioni: Lista descrizioni prodotti da classificare
        lista_fornitori: Lista fornitori (opzionale, per contesto)
        openai_client: Client OpenAI (opzionale, crea nuovo se None)
    
    Returns:
        List[str]: Lista categorie classificate (stesso ordine input)
    """
    if not lista_descrizioni:
        return []
    
    # Usa client iniettato o crea nuovo
    if openai_client is None:
        openai_client = _get_openai_client()
    
    # ⚠️ DEPRECATO: Legacy JSON memory ignorata per evitare conflitti con DB Supabase
    # La priorità è ora gestita da carica_memoria_completa() (classificazioni_manuali > locale > globale)
    risultati = {}
    da_chiedere_gpt = list(lista_descrizioni)  # Tutte da classificare via GPT
    
    if not da_chiedere_gpt:
        # Memoria AI ha priorità massima (correzioni manuali utente)
        # Dizionario applicato SOLO se descrizione non in memoria
        return [
            risultati[d] if d in risultati 
            else applica_correzioni_dizionario(d, "MATERIALE DI CONSUMO")
            for d in lista_descrizioni
        ]

    # Importa il prompt potenziato con esempi
    from config.prompt_ai_potenziato import get_prompt_classificazione
    
    prompt = get_prompt_classificazione(json.dumps(da_chiedere_gpt, ensure_ascii=False))

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        # 💰 TRACKING COSTI AI - Categorizzazione
        try:
            usage = response.usage
            if usage:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
                
                # Calcolo costi GPT-4o-mini (Gennaio 2026)
                # Input: $0.15 per 1M token
                # Output: $0.60 per 1M token
                cost_input = (prompt_tokens / 1_000_000) * 0.15
                cost_output = (completion_tokens / 1_000_000) * 0.60
                total_cost = cost_input + cost_output
                
                # Salva in DB se abbiamo ristorante_id
                # NOTA: prodotti_master è GLOBALE (condiviso tra tutti i ristoranti)
                # Non viene filtrato per ristorante_id per design (memoria condivisa)
                if 'ristorante_id' in st.session_state and st.session_state.ristorante_id:
                    try:
                        from services import get_supabase_client
                        supabase = get_supabase_client()
                        
                        supabase.rpc('increment_ai_cost', {
                            'p_ristorante_id': st.session_state.ristorante_id,
                            'p_cost': float(total_cost),
                            'p_tokens': prompt_tokens + completion_tokens,
                            'p_operation_type': 'categorization'
                        }).execute()
                        
                        logger.info(f"💰 Costo AI Categorizzazione tracciato: ${total_cost:.6f} (in={prompt_tokens}, out={completion_tokens})")
                    except Exception as track_err:
                        logger.warning(f"⚠️ Errore tracking costo categorizzazione: {track_err}")
        except Exception as cost_err:
            logger.warning(f"⚠️ Errore calcolo costo categorizzazione: {cost_err}")
        
        testo = response.choices[0].message.content.strip()
        dati = json.loads(testo)
        categorie_gpt = dati.get("categorie", [])
        
        # Combina risultati memoria + GPT con validazione
        for idx, desc in enumerate(da_chiedere_gpt):
            if idx < len(categorie_gpt):
                cat = categorie_gpt[idx]
                
                # ⚠️ VALIDAZIONE: Blocca categorie non valide (incluso NOTE E DICITURE)
                if cat not in TUTTE_LE_CATEGORIE and cat != "Da Classificare":
                    logger.warning(f"⚠️ AI ha generato categoria non valida '{cat}' per '{desc}' → applicando dizionario")
                    cat = applica_correzioni_dizionario(desc, "Da Classificare")
                risultati[desc] = cat
            else:
                risultati[desc] = "Da Classificare"
        
        # Ritorna nell'ordine originale
        return [risultati.get(d, "Da Classificare") for d in lista_descrizioni]
        
    except json.JSONDecodeError as e:
        logger.error(f"Errore parsing JSON da OpenAI: {e}")
        return [applica_correzioni_dizionario(d, "MATERIALE DI CONSUMO") for d in lista_descrizioni]
    except Exception as e:
        logger.error(f"Errore classificazione AI: {e}")
        return [applica_correzioni_dizionario(d, "MATERIALE DI CONSUMO") for d in lista_descrizioni]


# ============================================================
# UI HELPER: LOADING ANIMATION
# ============================================================

def mostra_loading_ai(placeholder, messaggio: str = "Elaborazione in corso"):
    """
    Mostra animazione loading a tema AI/Neural Network in un placeholder.
    Usa st.empty() placeholder per garantire rimozione anche in caso di errore.
    
    Args:
        placeholder: st.empty() placeholder per rendering
        messaggio: Testo messaggio da mostrare
    """
    placeholder.markdown(f"""
        <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 0.4; }}
            50% {{ opacity: 1; }}
        }}
        .loading-ai {{
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            color: white;
            font-weight: 600;
            animation: pulse 2s ease-in-out infinite;
        }}
        .loading-ai::before {{
            content: "🧠";
            font-size: 32px;
            margin-right: 15px;
        }}
        </style>
        <div class="loading-ai">
            {messaggio}...
        </div>
    """, unsafe_allow_html=True)


# ============================================================
# LEGACY FUNCTIONS (DEPRECATED - Usa memoria Supabase)
# ============================================================

def carica_memoria_ai() -> Dict[str, str]:
    """
    [LEGACY] Carica memoria AI da file JSON con cache.
    
    ⚠️ DEPRECATO: Usa carica_memoria_completa() + Supabase invece.
    Mantenuto per compatibilità con codice esistente.
    
    Returns:
        dict: {descrizione: categoria}
    """
    if os.path.exists(MEMORIA_AI_FILE):
        try:
            with open(MEMORIA_AI_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Impossibile caricare {MEMORIA_AI_FILE}: {e}")
            return {}
    return {}


def salva_memoria_ai(memoria_ai: Dict[str, str]) -> bool:
    """
    [LEGACY] Salvataggio atomico per prevenire corruzione file.
    
    ⚠️ DEPRECATO: Usa salva_correzione_in_memoria_globale() invece.
    Mantenuto per compatibilità.
    
    Args:
        memoria_ai: Dict {descrizione: categoria}
    
    Returns:
        bool: True se successo
    """
    try:
        temp_file = MEMORIA_AI_FILE + '.tmp'
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(memoria_ai, f, ensure_ascii=False, indent=2)
        
        shutil.move(temp_file, MEMORIA_AI_FILE)
        logger.info(f"💾 Memoria AI salvata: {len(memoria_ai)} voci")
        return True
        
    except Exception as e:
        logger.error(f"Errore salvataggio memoria AI: {e}")
        return False


def aggiorna_memoria_ai(descrizione: str, categoria: str):
    """
    [LEGACY] Aggiorna entry in memoria AI.
    
    ⚠️ DEPRECATO: Usa salva_correzione_in_memoria_globale() invece.
    """
    memoria_ai = carica_memoria_ai()
    memoria_ai[descrizione] = categoria
    salva_memoria_ai(memoria_ai)
