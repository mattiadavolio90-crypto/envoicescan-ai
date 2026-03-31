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
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple
import streamlit as st
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, APIError

# Import da moduli interni
from config.constants import DIZIONARIO_CORREZIONI, BRAND_AMBIGUI_NO_DICT, TUTTE_LE_CATEGORIE, MEMORIA_SESSION_CAP, MAX_DESC_LENGTH_DB
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
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 3600  # Ricarica la cache globale dopo 1 ora (evita memory leak a lungo termine)
_memoria_cache = {
    'prodotti_utente': {},         # {user_id: {descrizione: categoria}}
    'prodotti_master': {},         # {descrizione: categoria} — solo confidence alta/altissima → bypass AI
    'prodotti_master_hint': {},    # {descrizione: categoria} — confidence media/None → hint per AI
    'classificazioni_manuali': {},  # {descrizione: {categoria, is_dicitura}}
    'brand_ambigui': set(),        # set di brand dinamici da Supabase (UNION con BRAND_AMBIGUI_NO_DICT)
    'version': 0,               # Incrementato ad ogni invalidazione
    'loaded': False,
    '_loaded_at': 0.0,          # Timestamp ultimo caricamento globale (TTL eviction)
    '_loaded_user_ids': set()   # user_id già caricati (isola dati per utente)
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

_PAGE_SIZE = 1000  # Supabase default limit


def _fetch_all_rows(supabase_client, table: str, select: str, filters: dict | None = None) -> list:
    """Paginazione generica per superare il limite di 1000 righe di Supabase."""
    all_rows = []
    offset = 0
    while True:
        q = supabase_client.table(table).select(select)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        result = q.range(offset, offset + _PAGE_SIZE - 1).execute()
        batch = result.data or []
        all_rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return all_rows


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
    
    with _cache_lock:
        global_loaded = _memoria_cache['loaded']
        # TTL eviction: se la cache globale è scaduta, forza ricaricamento
        if global_loaded and (time.time() - _memoria_cache.get('_loaded_at', 0.0)) > _CACHE_TTL_SECONDS:
            logger.info("Cache globale scaduta (TTL 1h), forzo ricaricamento")
            _memoria_cache['loaded'] = False
            _memoria_cache['_loaded_at'] = 0.0
            global_loaded = False
        user_already_loaded = user_id in _memoria_cache.get('_loaded_user_ids', set())

    # I due stati sono gestiti indipendentemente nel try-block:
    # – global_loaded=False       → ricarica prodotti_master + classificazioni_manuali
    # – user_already_loaded=False → ricarica prodotti_utente per questo user_id
    if user_already_loaded and global_loaded:
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
        # Carica dati LOCALE utente solo se non già caricati per questo user_id
        if not user_already_loaded:
            rows_locale = _fetch_all_rows(
                supabase_client, 'prodotti_utente',
                'descrizione, categoria',
                filters={'user_id': user_id}
            )

            if rows_locale:
                _memoria_cache['prodotti_utente'][user_id] = {
                    row['descrizione']: row['categoria']
                    for row in rows_locale
                }
                logger.info(f"📦 Cache LOCALE caricata: {len(rows_locale)} prodotti per user {user_id[:8]}")
            else:
                _memoria_cache['prodotti_utente'][user_id] = {}

            _memoria_cache.setdefault('_loaded_user_ids', set()).add(user_id)

        # Carica dati GLOBALI solo se non già caricati
        if not global_loaded:
            # Query 2: Carica TUTTA la memoria globale (paginata)
            rows_globale = _fetch_all_rows(
                supabase_client, 'prodotti_master',
                'descrizione, categoria, confidence, consecutive_correct_classifications'
            )

            if rows_globale:
                _bypass = {}   # alta/altissima o streak>=3 → skip AI direttamente
                _hint = {}     # media/None → passa come hint, AI ha l'ultima parola
                _streak_promo = 0
                for row in rows_globale:
                    desc = row['descrizione']
                    cat = row['categoria']
                    conf = row.get('confidence')
                    streak = row.get('consecutive_correct_classifications', 0) or 0
                    if conf in ('alta', 'altissima') or streak >= 3:
                        _bypass[desc] = cat
                        if streak >= 3 and conf not in ('alta', 'altissima'):
                            _streak_promo += 1
                    else:
                        _hint[desc] = cat
                _memoria_cache['prodotti_master'] = _bypass
                _memoria_cache['prodotti_master_hint'] = _hint
                logger.info(f"📦 Cache GLOBALE caricata: {len(_bypass)} bypass (alta/altissima + {_streak_promo} streak>=3), {len(_hint)} hint (media/None)")

            # Query 3: Carica TUTTE le classificazioni manuali admin (paginata)
            rows_manuali = _fetch_all_rows(
                supabase_client, 'classificazioni_manuali',
                'descrizione, categoria_corretta, is_dicitura'
            )

            if rows_manuali:
                _memoria_cache['classificazioni_manuali'] = {
                    row['descrizione']: {
                        'categoria': row['categoria_corretta'],
                        'is_dicitura': row.get('is_dicitura', False)
                    }
                    for row in rows_manuali
                }
                logger.info(f"📦 Cache MANUALI caricata: {len(rows_manuali)} classificazioni")

            # Query 4: Carica brand ambigui dinamici da Supabase
            try:
                result_brand = supabase_client.table('brand_ambigui')\
                    .select('brand')\
                    .eq('aggiunto_automaticamente', True)\
                    .execute()
                brand_dinamici = {row['brand'] for row in result_brand.data} if result_brand.data else set()
                _memoria_cache['brand_ambigui'] = brand_dinamici
                if brand_dinamici:
                    logger.info(f"📦 Cache BRAND AMBIGUI caricata: {len(brand_dinamici)} brand dinamici")
            except Exception as brand_err:
                # Tabella potrebbe non esistere ancora (migration non eseguita)
                logger.warning(f"⚠️ brand_ambigui non caricati (tabella assente?): {brand_err}")
                _memoria_cache['brand_ambigui'] = set()

            _memoria_cache['loaded'] = True
            _memoria_cache['_loaded_at'] = time.time()

        _memoria_cache['version'] += 1
        logger.info(f"✅ Cache caricata (v{_memoria_cache['version']}) per user {user_id[:8]}")
        return _memoria_cache

    except Exception as e:
        logger.error(f"Errore caricamento cache completa: {e}")
        return _memoria_cache


def invalida_cache_memoria():
    """
    Invalida la cache in-memory forzando ricaricamento al prossimo accesso.
    Da chiamare dopo INSERT/UPDATE/DELETE su tabelle memoria.
    Thread-safe: crea nuovo dict per evitare race condition su letture concorrenti.
    """
    global _memoria_cache
    with _cache_lock:
        _memoria_cache = {
            'loaded': False,
            'prodotti_utente': {},
            'prodotti_master': {},
            'prodotti_master_hint': {},
            'classificazioni_manuali': {},
            'brand_ambigui': set(),
            'version': (_memoria_cache.get('version', 0) + 1),
            'timestamp': None,
            '_loaded_at': 0.0,
            '_loaded_user_ids': set()
        }
    logger.info("🔄 Cache memoria invalidata")


def aggiorna_streak_classificazione(
    descrizione: str,
    categoria_gpt: str,
    supabase_client,
) -> None:
    """Dopo che il GPT classifica una descrizione, incrementa (o resetta) lo streak
    su prodotti_master. Quando lo streak raggiunge 3, il prodotto viene auto-promosso
    a confidence='alta', entrando nel bypass cache e riducendo le chiamate GPT future.

    Logica:
    - Se la categoria GPT coincide con quella già in prodotti_master → streak +1
    - Se la categoria è diversa → streak reset a 1 (nuova categoria)
    - Se il prodotto non esiste → inserimento con streak=1
    - A streak >= 3 → confidence impostata ad 'alta' + cache invalidata
    """
    if not categoria_gpt or categoria_gpt.strip() in ('', 'Da Classificare'):
        return
    if not descrizione or not supabase_client:
        return

    try:
        # Leggi lo stato attuale del prodotto
        res = supabase_client.table('prodotti_master') \
            .select('id, categoria, confidence, consecutive_correct_classifications, verified') \
            .eq('descrizione', descrizione) \
            .limit(1) \
            .execute()

        now_streak = 0
        new_confidence = None

        if res.data:
            row = res.data[0]
            # Non toccare prodotti verificati manualmente dall'admin
            if row.get('verified'):
                return

            current_cat = row.get('categoria', '')
            current_streak = row.get('consecutive_correct_classifications', 0) or 0
            current_conf = row.get('confidence')

            # Non degradare prodotti già alta/altissima (sono già al massimo)
            if current_conf in ('alta', 'altissima'):
                return

            if current_cat == categoria_gpt:
                now_streak = current_streak + 1
            else:
                # Categoria cambiata: nuovo ciclo di streak con la nuova categoria
                now_streak = 1

            update_data: dict = {
                'categoria': categoria_gpt,
                'consecutive_correct_classifications': now_streak,
            }
            if now_streak >= 3:
                update_data['confidence'] = 'alta'
                new_confidence = 'alta'

            supabase_client.table('prodotti_master') \
                .update(update_data) \
                .eq('id', row['id']) \
                .execute()

        else:
            # Prodotto non presente: upsert con streak=1 e confidence='media'
            supabase_client.table('prodotti_master') \
                .upsert({
                    'descrizione': descrizione,
                    'categoria': categoria_gpt,
                    'confidence': 'media',
                    'consecutive_correct_classifications': 1,
                }, on_conflict='descrizione') \
                .execute()
            now_streak = 1

        if new_confidence == 'alta':
            logger.info(
                f"🚀 STREAK PROMO: '{descrizione[:60]}' → '{categoria_gpt}' "
                f"(streak={now_streak}) promosso a bypass!"
            )
            invalida_cache_memoria()
        else:
            logger.debug(
                f"📈 Streak '{descrizione[:60]}': {now_streak} "
                f"→ '{categoria_gpt}'"
            )

    except Exception as e:
        # Non bloccare mai la classificazione principale per un errore di streak
        logger.warning(f"⚠️ aggiorna_streak_classificazione errore: {e}")


_MEMORIA_CAP = MEMORIA_SESSION_CAP

# Stop-word per estrazione brand (non sono brand)
_STOP_WORDS_BRAND = frozenset({
    'KG', 'GR', 'LT', 'ML', 'PZ', 'CF', 'CT', 'NR', 'X',
    'DI', 'DA', 'DEL', 'DELLA', 'DELLO', 'DEGLI', 'DELLE',
    'AL', 'ALLO', 'ALLA', 'AI', 'ALLE', 'IL', 'LO', 'LA',
    'I', 'GLI', 'LE', 'UN', 'UNA', 'CON', 'PER', 'IN',
    'CONF', 'CONFEZIONE', 'SURG', 'SURGELATO', 'BIO', 'BIOLOGICO',
    'FRESCO', 'FRESCA', 'INTERO', 'INTERA', 'LIGHT', 'ZERO',
    'CLASSIC', 'ORIGINAL', 'PREMIUM', 'SPECIALE', 'SPECIALI',
})


def estrai_brand_da_descrizione(descrizione: str) -> Optional[str]:
    """
    Estrae il brand (prima parola significativa) da una descrizione prodotto.
    Restituisce None se non riesce a identificare un brand attendibile.

    Criteri brand valido:
    - Almeno 3 caratteri alfabetici
    - Non è un numero o codice numerico
    - Non è una stop-word generica (KG, LT, DI, CONF...)
    """
    if not descrizione or not isinstance(descrizione, str):
        return None
    tokens = descrizione.upper().split()
    for token in tokens:
        # Rimuovi punteggiatura attaccata
        cleaned = re.sub(r'[^A-Z]', '', token)
        if (
            len(cleaned) >= 3
            and cleaned.isalpha()
            and cleaned not in _STOP_WORDS_BRAND
        ):
            return cleaned
    return None


def _aggiorna_brand_tracking(
    descrizione: str,
    vecchia_categoria: str,
    nuova_categoria: str,
    supabase_client=None
) -> None:
    """
    Traccia la correzione manuale nella tabella brand_ambigui.
    Se il brand raggiunge le soglie (>= 3 correzioni, >= 2 categorie, tasso > 20%)
    viene marcato aggiunto_automaticamente=TRUE e la cache brand viene invalidata.

    Chiamata in modo silenzioso (try/except totale) — non blocca mai il flusso principale.
    """
    if vecchia_categoria == nuova_categoria:
        return  # Correzione no-op, non tracciare

    brand = estrai_brand_da_descrizione(descrizione)
    if not brand:
        return

    # Non tracciare brand già nel set statico (già noti)
    if brand in BRAND_AMBIGUI_NO_DICT:
        return

    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception:
            return

    try:
        # Leggi record attuale (se esiste)
        existing = supabase_client.table('brand_ambigui')\
            .select('id, num_correzioni, categorie_viste, aggiunto_automaticamente')\
            .eq('brand', brand)\
            .limit(1)\
            .execute()

        if existing.data:
            rec = existing.data[0]
            num_corr = rec['num_correzioni'] + 1
            cat_viste = list(set(rec.get('categorie_viste') or []) | {vecchia_categoria, nuova_categoria})
        else:
            num_corr = 1
            cat_viste = list({vecchia_categoria, nuova_categoria})

        # Calcola tasso: num_correzioni / prodotti in prodotti_master con questo brand
        try:
            count_res = supabase_client.table('prodotti_master')\
                .select('id', count='exact', head=True)\
                .ilike('descrizione', f'{brand}%')\
                .execute()
            totale = count_res.count or 1
        except Exception:
            totale = max(num_corr, 1)

        tasso = round(num_corr / totale, 4)

        # Criteri per promozione automatica
        soglia_raggiunta = (
            not (existing.data and existing.data[0].get('aggiunto_automaticamente'))
            and num_corr >= 3
            and len(cat_viste) >= 2
            and tasso > 0.20
        )
        auto = soglia_raggiunta or (existing.data and existing.data[0].get('aggiunto_automaticamente', False))

        upsert_data = {
            'brand': brand,
            'num_correzioni': num_corr,
            'categorie_viste': cat_viste,
            'tasso_correzione': tasso,
            'aggiunto_automaticamente': auto,
            'ultima_modifica': datetime.now(timezone.utc).isoformat(),
        }
        if not existing.data:
            upsert_data['prima_vista'] = datetime.now(timezone.utc).isoformat()

        supabase_client.table('brand_ambigui').upsert(
            upsert_data, on_conflict='brand'
        ).execute()

        if soglia_raggiunta:
            # Invalida SOLO brand_ambigui nella cache (ottimizzazione: evita full reload)
            with _cache_lock:
                _memoria_cache['brand_ambigui'].add(brand)
            logger.warning(
                f"🚨 AUTO-BRAND: '{brand}' aggiunto a brand_ambigui "
                f"({num_corr} correzioni, {len(cat_viste)} categorie, tasso={tasso:.0%})"
            )
        else:
            logger.debug(
                f"📊 Brand tracking: '{brand}' — {num_corr} corr., "
                f"{len(cat_viste)} cat., tasso={tasso:.0%}"
            )

    except Exception as e:
        # Mai bloccare il flusso principale per un errore di tracking
        logger.debug(f"Brand tracking silenzioso fallito per '{brand}': {e}")


def ottieni_hint_per_ai(descrizione: str, user_id: str) -> Optional[str]:
    """
    Restituisce la categoria hint per l'AI (prodotti_master con confidence 'media' o NULL).
    Se trovato, l'AI usa questa come suggerimento debole nel payload.
    Restituisce None se il prodotto non è in memoria o ha confidence alta/altissima
    (in quel caso viene già bypassata l'AI completamente da categorizza_con_memoria).
    """
    try:
        desc_normalized, _ = get_descrizione_normalizzata_e_originale(descrizione)
        return _memoria_cache.get('prodotti_master_hint', {}).get(desc_normalized)
    except Exception:
        return None


def _traccia_memoria_categorizzata(descrizione: str):
    """Traccia descrizione come categorizzata da memoria (icona 🧠), cap a _MEMORIA_CAP."""
    if 'righe_memoria_appena_categorizzate' not in st.session_state:
        st.session_state.righe_memoria_appena_categorizzate = []
    lista = st.session_state.righe_memoria_appena_categorizzate
    if descrizione not in lista:
        if len(lista) < _MEMORIA_CAP:
            lista.append(descrizione)
        elif len(lista) == _MEMORIA_CAP:
            logger.warning(f"⚠️ Raggiunto limite {_MEMORIA_CAP} righe memoria categorizzate nella sessione")


def ottieni_categoria_prodotto(descrizione: str, user_id: str, supabase_client=None) -> str:
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
        # Carica cache se non già caricata per questo utente
        if not _memoria_cache['loaded'] or user_id not in _memoria_cache.get('_loaded_user_ids', set()):
            carica_memoria_completa(user_id, supabase_client=supabase_client)

        # Snapshot locale: protegge da invalidazioni parallele durante la lettura.
        # Se un altro thread chiama invalida_cache_memoria() ora, _memoria_cache viene
        # sostituito ma questo thread continua a lavorare sul riferimento stabile.
        cache = _memoria_cache

        # Normalizza per matching consistente (stesso trattamento di categorizza_con_memoria)
        desc_stripped = descrizione.strip()

        # 0️⃣ Check memoria ADMIN (classificazioni_manuali) - PRIORITÀ ASSOLUTA
        if desc_stripped in cache['classificazioni_manuali']:
            record = cache['classificazioni_manuali'][desc_stripped]
            if record.get('is_dicitura'):
                logger.info(f"📋 Memoria Admin (cache/ottieni): '{descrizione[:40]}' → DICITURA")
                return "📝 NOTE E DICITURE"
            else:
                logger.info(f"📋 Memoria Admin (cache/ottieni): '{descrizione[:40]}' → {record['categoria']}")
                return record['categoria']
        
        # 1️⃣ Check memoria LOCALE utente (da cache, 0 query!)
        if user_id in cache['prodotti_utente']:
            locale_dict = cache['prodotti_utente'][user_id]
            if descrizione in locale_dict:
                categoria = locale_dict[descrizione]
                _traccia_memoria_categorizzata(descrizione)
                return categoria
        
        # 2️⃣ Check memoria GLOBALE (da cache, 0 query!) se abilitata
        if not _disable_global_memory:
            # Prova con descrizione esatta
            if descrizione in cache['prodotti_master']:
                categoria = cache['prodotti_master'][descrizione]
                _traccia_memoria_categorizzata(descrizione)
                return categoria

            # Prova anche con descrizione normalizzata (per matching consistente)
            desc_normalized, _ = get_descrizione_normalizzata_e_originale(descrizione)
            if desc_normalized != descrizione and desc_normalized in cache['prodotti_master']:
                categoria = cache['prodotti_master'][desc_normalized]
                _traccia_memoria_categorizzata(descrizione)
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
    "CONFEZIONE", "CONF", "BUSTA", "BUSTE", "SCATOLA", "CARTONE",
    "PACCO", "BARATTOLO", "BOTTIGLIA", "LATTINA",
    "SACCHETTI", "SACCHETTO", "SACCHI", "SACCO",
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
try:
    _PATTERNS_ALIMENTI, _PATTERNS_CONTENITORI = _build_compiled_patterns()
except Exception as e:
    logger.error(f"Errore buildcompiledpatterns: {e}")
    _PATTERNS_ALIMENTI, _PATTERNS_CONTENITORI = [], []

# Regex controllo caratteri (compilata a livello modulo, non ad ogni chiamata)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


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

    # Brand multi-categoria → bypass dizionario, forza AI per classificazione per-prodotto.
    # Check ibrido: set statico (constants.py) UNION set dinamico (Supabase brand_ambigui).
    desc_upper = descrizione.upper()
    _brand_set = BRAND_AMBIGUI_NO_DICT | _memoria_cache.get('brand_ambigui', set())
    if any(brand in desc_upper for brand in _brand_set):
        return categoria_ai

    # Padding per garantire match ai bordi (i pattern usano boundary [\s\W])
    desc_padded = ' ' + desc_upper + ' '

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
    supabase_client=None,
    vecchia_categoria: Optional[str] = None
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
        
        # Sanitizza: rimuovi null bytes e limita lunghezza
        desc_normalized = desc_normalized.replace('\x00', '').strip()[:MAX_DESC_LENGTH_DB]
        if not desc_normalized:
            logger.warning("Descrizione vuota dopo sanitizzazione, skip salvataggio locale")
            return False
        
        logger.info(f"💾 SALVATAGGIO LOCALE: '{desc_normalized}' → {nuova_categoria} (user={user_email})")
        
        # Colonne ESSENZIALI (sicuramente presenti nella tabella)
        upsert_data = {
            'user_id': user_id,
            'descrizione': desc_normalized,
            'categoria': nuova_categoria,
            'updated_at': datetime.now(timezone.utc).isoformat()
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

        # Tracking brand ambigui (silenzioso, non blocca il return)
        if vecchia_categoria:
            _aggiorna_brand_tracking(
                descrizione=descrizione,
                vecchia_categoria=vecchia_categoria,
                nuova_categoria=nuova_categoria,
                supabase_client=supabase_client
            )

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
        
        # Sanitizza: rimuovi null bytes e limita lunghezza
        desc_normalized = desc_normalized.replace('\x00', '').strip()[:MAX_DESC_LENGTH_DB]
        if not desc_normalized:
            logger.warning("Descrizione vuota dopo sanitizzazione, skip salvataggio globale")
            return False
        
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
                'ultima_modifica': datetime.now(timezone.utc).isoformat()
            }).eq('id', record['id']).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()

            # Tracking brand ambigui
            _aggiorna_brand_tracking(descrizione, vecchia_categoria, nuova_categoria, supabase_client)

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
                'created_at': datetime.now(timezone.utc).isoformat(),
                'ultima_modifica': datetime.now(timezone.utc).isoformat()
            }).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()

            # Tracking brand ambigui
            _aggiorna_brand_tracking(descrizione, vecchia_categoria, nuova_categoria, supabase_client)

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
        except Exception as e:
            logger.warning(f"Impossibile inizializzare Supabase client: {e}")

    try:
        # Carica cache se non già caricata per questo utente
        if user_id and (not _memoria_cache['loaded'] or user_id not in _memoria_cache.get('_loaded_user_ids', set())):
            carica_memoria_completa(user_id, supabase_client)

        # Snapshot locale: protegge da invalidazioni parallele durante la lettura.
        # Con integrazione invoicetronic (flusso multi-client parallelo), senza snapshot
        # un thread potrebbe leggere la cache già svuotata da un altro thread.
        cache = _memoria_cache

        # LIVELLO 1: Check memoria admin (da cache, 0 query!)
        desc_stripped = descrizione.strip()
        if desc_stripped in cache['classificazioni_manuali']:
            record = cache['classificazioni_manuali'][desc_stripped]
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
        if user_id and user_id in cache['prodotti_utente']:
            locale_dict = cache['prodotti_utente'][user_id]
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
            if desc_normalized in cache['prodotti_master']:
                categoria = cache['prodotti_master'][desc_normalized]
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
    # 🛡️ QUARANTENA: NON salvare righe con prezzo = 0 in memoria globale
    # Le righe €0 vanno revisionate dall'admin nel tab "Review Righe 0€" prima di entrare in memoria
    if categoria_keyword != "Da Classificare" and supabase_client and prezzo != 0:
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
                'created_at': datetime.now(timezone.utc).isoformat(),
                'ultima_modifica': datetime.now(timezone.utc).isoformat()
            }, on_conflict='descrizione').execute()
            logger.info(f"💾 MEMORIA GLOBALE (auto-save): '{desc_normalized}' (orig: '{desc_original}') → {categoria_keyword} (keyword) - disponibile per TUTTI i clienti")
        except Exception as e:
            logger.warning(f"❌ Errore salvataggio memoria globale per '{descrizione[:40]}': {e}")
    elif categoria_keyword != "Da Classificare" and prezzo == 0:
        # 🛡️ QUARANTENA: Riga €0 categorizzata ma NON salvata in memoria globale
        # Andrà nel tab "Review Righe 0€" per validazione admin
        logger.info(f"🛡️ QUARANTENA €0: '{descrizione[:60]}' → {categoria_keyword} (NON salvato in memoria globale, in attesa review)")
    else:
        # AUTO-CATEGORIZZAZIONE FALLITA: nessun match nel dizionario
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
def _chiama_gpt_classificazione(
    da_chiedere_gpt: List[str],
    openai_client,
    max_tokens: int = 4096,
    lista_fornitori: Optional[List[str]] = None,
    lista_iva: Optional[List[int]] = None,
    lista_hint: Optional[List[Optional[str]]] = None,
) -> List[str]:
    """
    Singola chiamata GPT per classificazione. Ritorna lista categorie (stesso ordine input).
    Se GPT ritorna meno categorie del previsto, le mancanti saranno "Da Classificare".

    Quando lista_fornitori e/o lista_iva sono fornite (allineate con da_chiedere_gpt),
    il payload inviato a GPT è arricchito: {articolo, fornitore, iva} invece di semplici stringhe.
    Le descrizioni vengono inoltre normalizzate (rimozione prefissi peso GDO, espansione
    abbreviazioni) prima di essere inviate, per migliorare l'accuratezza.
    """
    from config.prompt_ai_potenziato import get_prompt_classificazione
    from utils.text_utils import normalizza_descrizione

    # 🔒 Sanitizza input: rimuovi caratteri di controllo, limita lunghezza per descrizione
    _MAX_DESC_LEN = 300
    da_chiedere_sanitized = [
        _CTRL_RE.sub('', desc)[:_MAX_DESC_LEN] for desc in da_chiedere_gpt
    ]

    # 🧹 Normalizza descrizioni per rimuovere prefissi GDO (es: "G100 PANBURGER" → "PANBURGER")
    # ed espandere abbreviazioni (es: "INS.NOVELLA" → "INSALATA NOVELLA").
    # Usiamo la versione normalizzata SOLO nel payload inviato a GPT; la mappatura risultati
    # avviene per indice, quindi il cambio di testo non crea disallineamenti.
    da_chiedere_normalizzate = [
        normalizza_descrizione(desc) or desc  # fallback a originale se normalizzazione svuota
        for desc in da_chiedere_sanitized
    ]

    # 📦 Costruisci payload: arricchito (dict) se i metadati sono disponibili, altrimenti plain list
    _ha_fornitori = lista_fornitori and len(lista_fornitori) == len(da_chiedere_gpt)
    _ha_iva = lista_iva and len(lista_iva) == len(da_chiedere_gpt)
    _ha_hint = lista_hint and len(lista_hint) == len(da_chiedere_gpt)
    if _ha_fornitori or _ha_iva or _ha_hint:
        payload = []
        for idx, desc_norm in enumerate(da_chiedere_normalizzate):
            item: Dict[str, Any] = {"articolo": desc_norm}
            if _ha_fornitori:
                forn = (lista_fornitori[idx] or "").strip()
                if forn:
                    item["fornitore"] = forn
            if _ha_iva:
                iva_val = lista_iva[idx]
                if iva_val:
                    item["iva"] = iva_val
            if _ha_hint:
                hint_val = lista_hint[idx]
                if hint_val:
                    item["hint"] = hint_val
            payload.append(item)
        articoli_json = json.dumps(payload, ensure_ascii=False)
    else:
        articoli_json = json.dumps(da_chiedere_normalizzate, ensure_ascii=False)

    prompt = get_prompt_classificazione(articoli_json)
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1,
        response_format={"type": "json_object"}
    )
    
    # 💰 TRACKING COSTI AI - Categorizzazione
    try:
        usage = response.usage
        if usage:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            
            cost_input = (prompt_tokens / 1_000_000) * 0.15
            cost_output = (completion_tokens / 1_000_000) * 0.60
            total_cost = cost_input + cost_output
            
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
    
    # Valida e costruisci lista risultati
    risultati = []
    for idx, desc in enumerate(da_chiedere_gpt):
        if idx < len(categorie_gpt):
            cat = categorie_gpt[idx]
            
            # ⚠️ VALIDAZIONE: Blocca categorie non valide (incluso NOTE E DICITURE)
            if cat not in TUTTE_LE_CATEGORIE and cat != "Da Classificare":
                logger.warning(f"⚠️ AI ha generato categoria non valida '{cat}' per '{desc}' → applicando dizionario")
                cat = applica_correzioni_dizionario(desc, "Da Classificare")
            risultati.append(cat)
        else:
            logger.warning(f"⚠️ AI non ha restituito categoria per indice {idx}: '{desc[:40]}' → Da Classificare")
            risultati.append("Da Classificare")
    
    if len(categorie_gpt) != len(da_chiedere_gpt):
        logger.warning(f"⚠️ MISMATCH: inviate {len(da_chiedere_gpt)} descrizioni, ricevute {len(categorie_gpt)} categorie")
    
    return risultati


def classifica_con_ai(
    lista_descrizioni: List[str],
    lista_fornitori: Optional[List[str]] = None,
    lista_iva: Optional[List[int]] = None,
    lista_hint: Optional[List[Optional[str]]] = None,
    openai_client: Optional[OpenAI] = None
) -> List[str]:
    """
    Classificazione AI con JSON strutturato + correzioni dizionario.
    Usa retry automatico per gestire rate limits OpenAI e risposte incomplete.
    
    Se la prima chiamata GPT restituisce "Da Classificare" per alcuni item,
    ritenta automaticamente (max 2 retry) con batch più piccoli.
    
    Args:
        lista_descrizioni: Lista descrizioni prodotti da classificare
        lista_fornitori: Lista fornitori ALLINEATA con lista_descrizioni (opzionale)
        lista_iva: Lista IVA% ALLINEATA con lista_descrizioni (es: 4, 10, 22) (opzionale)
        lista_hint: Lista hint categoria ALLINEATA con lista_descrizioni (opzionale).
                    Ogni elemento è una categoria suggerita (confidence 'media') o None.
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

    # Costruisci indici posizionali per fornitori e IVA (allineati con da_chiedere_gpt)
    _idx_map = {desc: i for i, desc in enumerate(lista_descrizioni)}

    def _get_fornitori_aligned(descs: List[str]) -> Optional[List[str]]:
        if not lista_fornitori or len(lista_fornitori) != len(lista_descrizioni):
            return None
        return [lista_fornitori[_idx_map[d]] for d in descs if d in _idx_map]

    def _get_iva_aligned(descs: List[str]) -> Optional[List[int]]:
        if not lista_iva or len(lista_iva) != len(lista_descrizioni):
            return None
        return [lista_iva[_idx_map[d]] for d in descs if d in _idx_map]

    def _get_hint_aligned(descs: List[str]) -> Optional[List[Optional[str]]]:
        if not lista_hint or len(lista_hint) != len(lista_descrizioni):
            return None
        return [lista_hint[_idx_map[d]] for d in descs if d in _idx_map]

    if not da_chiedere_gpt:
        return [
            risultati[d] if d in risultati 
            else applica_correzioni_dizionario(d, "MATERIALE DI CONSUMO")
            for d in lista_descrizioni
        ]

    try:
        # 🧠 PRIMA CHIAMATA GPT (max_tokens=4096 per evitare troncamenti)
        cats_prima = _chiama_gpt_classificazione(
            da_chiedere_gpt, openai_client, max_tokens=4096,
            lista_fornitori=_get_fornitori_aligned(da_chiedere_gpt),
            lista_iva=_get_iva_aligned(da_chiedere_gpt),
            lista_hint=_get_hint_aligned(da_chiedere_gpt),
        )
        
        for desc, cat in zip(da_chiedere_gpt, cats_prima):
            risultati[desc] = cat
        
        # 🔄 RETRY AUTOMATICO: Se ci sono "Da Classificare", ritenta con batch più piccoli
        MAX_RETRY = 2
        for retry_num in range(1, MAX_RETRY + 1):
            # Trova descrizioni ancora "Da Classificare"
            da_ritentare = [d for d in da_chiedere_gpt if risultati.get(d) == "Da Classificare"]
            
            if not da_ritentare:
                break  # Tutto classificato!
            
            logger.info(f"🔄 RETRY {retry_num}/{MAX_RETRY}: {len(da_ritentare)} descrizioni ancora Da Classificare, ritentando...")
            
            try:
                # Usa batch più piccoli nei retry per migliorare precisione
                retry_chunk_size = min(20, len(da_ritentare))
                for i in range(0, len(da_ritentare), retry_chunk_size):
                    chunk_retry = da_ritentare[i:i+retry_chunk_size]
                    cats_retry = _chiama_gpt_classificazione(
                        chunk_retry, openai_client, max_tokens=4096,
                        lista_fornitori=_get_fornitori_aligned(chunk_retry),
                        lista_iva=_get_iva_aligned(chunk_retry),
                        lista_hint=_get_hint_aligned(chunk_retry),
                    )
                    
                    for desc, cat in zip(chunk_retry, cats_retry):
                        if cat and cat != "Da Classificare":
                            risultati[desc] = cat
                            logger.info(f"✅ RETRY {retry_num}: '{desc[:40]}' → {cat}")
            except Exception as retry_err:
                logger.warning(f"⚠️ Errore durante retry {retry_num}: {retry_err}")
                # Continua con i risultati che abbiamo
        
        # Log finale
        ancora_da_class = sum(1 for d in da_chiedere_gpt if risultati.get(d) == "Da Classificare")
        if ancora_da_class > 0:
            logger.warning(f"⚠️ Dopo {MAX_RETRY} retry, {ancora_da_class}/{len(da_chiedere_gpt)} descrizioni rimangono Da Classificare")
        else:
            logger.info(f"✅ Tutte le {len(da_chiedere_gpt)} descrizioni classificate con successo")
        
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
