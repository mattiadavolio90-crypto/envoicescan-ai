"""
Workspace - Area di Lavoro
Pagina dedicata alla gestione operativa del ristorante
"""

import streamlit as st
import pandas as pd
import json
import io
from datetime import datetime
from supabase import Client
from config.logger_setup import get_logger
from utils.ristorante_helper import get_current_ristorante_id
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from config.constants import CATEGORIE_SPESE_OPERATIVE
from services import get_supabase_client

# Logger
logger = get_logger('workspace')

def get_fresh_supabase_client() -> Client:
    """Ritorna client Supabase, ricreandolo se disconnesso"""
    try:
        client = get_supabase_client()
        # Nessun test query - fidarsi del singleton; retry su errore reale
        return client
    except Exception:
        # Client stale, ricrea
        logger.warning("Client Supabase disconnesso, ricreo connessione...")
        get_supabase_client.clear()
        return get_supabase_client()


def invalidate_workspace_cache():
    """Invalida SOLO le cache specifiche del workspace, senza toccare le altre pagine."""
    get_articoli_da_fatture.clear()
    get_ricette_come_ingredienti.clear()
    _get_ingredienti_workspace_cached.clear()


def safe_db_execute(operation_fn, description: str = "operazione DB"):
    """
    Esegue un'operazione DB con retry automatico su disconnessione.
    operation_fn: lambda che riceve il client supabase e ritorna il risultato.
    """
    global supabase
    try:
        return operation_fn(supabase)
    except Exception as e:
        if 'disconnect' in str(e).lower() or 'closed' in str(e).lower():
            logger.warning(f"Riconnessione Supabase per {description}...")
            supabase = get_fresh_supabase_client()
            return operation_fn(supabase)
        raise

# Inizializza client
supabase = get_supabase_client()

# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Workspace - OH YEAH!",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Nascondi sidebar immediatamente se non loggato
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.markdown("""
        <style>
        [data-testid="stSidebar"],
        section[data-testid="stSidebar"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

# ============================================
# AUTENTICAZIONE RICHIESTA
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")

user = st.session_state.user_data
user_id = user["id"]
current_ristorante = get_current_ristorante_id()

# ============================================
# CONTROLLO PAGINA ABILITATA (legge sempre dal DB per riflettere modifiche admin)
# ============================================
from utils.page_setup import check_page_enabled
check_page_enabled('workspace', user_id)

# ============================================
# SIDEBAR CONDIVISA
# ============================================
render_sidebar(user)

# ============================================
# INIZIALIZZA SESSION STATE
# ============================================
if 'ingredienti_temp' not in st.session_state:
    st.session_state.ingredienti_temp = []
if 'ricetta_edit_mode' not in st.session_state:
    st.session_state.ricetta_edit_mode = False
if 'ricetta_edit_data' not in st.session_state:
    st.session_state.ricetta_edit_data = None
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

# ============================================
# FUNZIONI HELPER
# ============================================

MAX_INGREDIENTI = 50  # Limite DoS protection

import re

def estrai_grammatura_da_nome(nome: str) -> dict:
    """
    Estrae grammatura/volume dalla descrizione prodotto.
    Es: "BARILLA KG5 SPAGHETTINI" → {'valore': 5000, 'um': 'G'}
        "OLIO LT 1" → {'valore': 1000, 'um': 'ML'}
        "MOZZARELLA GR 500" → {'valore': 500, 'um': 'G'}
    
    Returns:
        dict con 'valore' (in g/ml) e 'um' base, oppure None se non trovato
    """
    nome_upper = nome.upper()
    
    # Pattern comuni per grammature
    patterns = [
        # KG seguiti da numero: KG5, KG 5, KG.5
        (r'KG[\s\.]*(\d+(?:[.,]\d+)?)', 'KG'),
        # Numero seguito da KG: 5KG, 5 KG
        (r'(\d+(?:[.,]\d+)?)[\s]*KG', 'KG'),
        
        # GR/GRAMMI: GR 500, 500GR, 500 GRAMMI
        (r'GR[\s\.]*(\d+)', 'G'),
        (r'(\d+)[\s]*GR\b', 'G'),
        (r'(\d+)[\s]*GRAMM', 'G'),
        
        # LT/LITRI: LT 1, 1LT, 1 LITRO
        (r'LT[\s\.]*(\d+(?:[.,]\d+)?)', 'LT'),
        (r'(\d+(?:[.,]\d+)?)[\s]*LT', 'LT'),
        (r'(\d+(?:[.,]\d+)?)[\s]*LITR', 'LT'),
        
        # ML: ML 200, 200ML
        (r'ML[\s\.]*(\d+)', 'ML'),
        (r'(\d+)[\s]*ML', 'ML'),
        
        # CL: CL 75, 75CL (bottiglie vino)
        (r'CL[\s\.]*(\d+)', 'CL'),
        (r'(\d+)[\s]*CL', 'CL'),
    ]
    
    for pattern, um_tipo in patterns:
        match = re.search(pattern, nome_upper)
        if match:
            try:
                valore_str = match.group(1).replace(',', '.')
                valore = float(valore_str)
                
                # Converti tutto in grammi o millilitri (unità base)
                if um_tipo == 'KG':
                    return {'valore': valore * 1000, 'um': 'G', 'originale': f"{valore}KG"}
                elif um_tipo == 'G':
                    return {'valore': valore, 'um': 'G', 'originale': f"{valore}G"}
                elif um_tipo == 'LT':
                    return {'valore': valore * 1000, 'um': 'ML', 'originale': f"{valore}LT"}
                elif um_tipo == 'ML':
                    return {'valore': valore, 'um': 'ML', 'originale': f"{valore}ML"}
                elif um_tipo == 'CL':
                    return {'valore': valore * 10, 'um': 'ML', 'originale': f"{valore}CL"}
            except (ValueError, AttributeError):
                continue
    
    return None


def converti_unita_misura(quantita: float, um_src: str, prezzo_per_unita_base: float) -> float:
    """
    Converte quantità con unità misura in prezzo normalizzato.
    Assume che prezzi da DB siano per kg/lt/pz.
    
    Args:
        quantita: Quantità richiesta (es: 200)
        um_src: Unità misura richiesta (es: "g")
        prezzo_per_unita_base: Prezzo per kg/lt/pz (es: 8.5 €/kg)
    
    Returns:
        Prezzo calcolato per la quantità richiesta
    """
    um_src = um_src.lower().strip()
    
    # Conversioni peso (base: kg)
    if um_src in ['g', 'gr', 'grammi']:
        return (quantita / 1000) * prezzo_per_unita_base
    elif um_src in ['kg', 'kilogrammi', 'kilo']:
        return quantita * prezzo_per_unita_base
    
    # Conversioni volume (base: lt)
    elif um_src in ['ml', 'millilitri']:
        return (quantita / 1000) * prezzo_per_unita_base
    elif um_src in ['cl', 'centilitri']:
        return (quantita / 100) * prezzo_per_unita_base
    elif um_src in ['lt', 'l', 'litri']:
        return quantita * prezzo_per_unita_base
    
    # Unità pezzi (prezzo già per pezzo)
    elif um_src in ['pz', 'pezzi', 'n', 'nr']:
        return quantita * prezzo_per_unita_base
    
    # Default: assume quantità diretta
    else:
        logger.warning(f"Unità misura sconosciuta: {um_src}, uso calcolo diretto")
        return quantita * prezzo_per_unita_base


@st.cache_data(ttl=300, show_spinner="Caricamento articoli dalle fatture...")
def get_articoli_da_fatture(user_id: str, ristorante_id: str = None) -> tuple:
    """
    Carica articoli unici da fatture con ultimo prezzo.
    Filtra per user_id e ristorante_id.
    Ritorna (lista_articoli, messaggi_debug)
    """
    debug_msgs = []
    try:
        debug_msgs.append(f"🔍 Cerco fatture per user_id: {user_id}")
        
        # Query articoli escludendo spese operative (servizi, utenze, manutenzione)
        query_fatture = supabase.table('fatture')\
            .select('descrizione, prezzo_unitario, unita_misura, data_documento, categoria')\
            .eq('user_id', user_id)\
            .not_.in_('categoria', CATEGORIE_SPESE_OPERATIVE)
        
        if ristorante_id:
            query_fatture = query_fatture.eq('ristorante_id', ristorante_id)
        
        response = query_fatture.order('data_documento', desc=True).execute()
        
        debug_msgs.append(f"📊 Query eseguita. Response.data type: {type(response.data)}")
        
        if not response.data:
            debug_msgs.append("⚠️ response.data è vuoto/None")
            return [], debug_msgs
        
        debug_msgs.append(f"✅ Trovate {len(response.data)} righe fatture")
        
        # Mostra prime 5 per debug
        debug_msgs.append("📋 Prime 5 righe:")
        for i, row in enumerate(response.data[:5]):
            desc = row.get('descrizione', 'N/A')
            prezzo = row.get('prezzo_unitario', 0)
            um = row.get('unita_misura', 'N/A')
            debug_msgs.append(f"  {i+1}. '{desc}' | €{prezzo} | {um}")
        
        # Raggruppa per descrizione (prendi primo = più recente)
        articoli_map = {}
        righe_saltate = 0
        grammature_rilevate = 0
        
        for row in response.data:
            desc = (row.get('descrizione') or '').strip()
            if desc and desc not in articoli_map:
                # Estrai grammatura dal nome
                grammatura_info = estrai_grammatura_da_nome(desc)
                
                if grammatura_info:
                    grammature_rilevate += 1
                
                articoli_map[desc] = {
                    'nome': desc,
                    'prezzo_unitario': float(row.get('prezzo_unitario') or 0),
                    'um': (row.get('unita_misura') or 'PZ').upper(),
                    'grammatura_confezione': grammatura_info['valore'] if grammatura_info else None,
                    'grammatura_um': grammatura_info['um'] if grammatura_info else None,
                    'grammatura_str': grammatura_info['originale'] if grammatura_info else None
                }
            elif not desc:
                righe_saltate += 1
        
        if righe_saltate > 0:
            debug_msgs.append(f"⚠️ Saltate {righe_saltate} righe senza descrizione")
        
        debug_msgs.append(f"✅ Grammature rilevate automaticamente: {grammature_rilevate}/{len(articoli_map)}")
        
        result = list(articoli_map.values())
        debug_msgs.append(f"✅ Articoli unici estratti: {len(result)}")
        
        return result, debug_msgs
    
    except Exception as e:
        debug_msgs.append(f"❌ ERRORE: {type(e).__name__}: {str(e)}")
        logger.exception("Errore caricamento articoli")
        return [], debug_msgs


@st.cache_data(ttl=300, show_spinner=False)
def get_ricette_come_ingredienti(user_id: str, ristorante_id: str, exclude_id: str = None) -> list:
    """
    Carica ricette salvate utilizzabili come ingredienti.
    Cache 5 minuti per performance.
    """
    try:
        query = supabase.table('ricette')\
            .select('id, nome, foodcost_totale, categoria')\
            .eq('userid', user_id)
        
        # Aggiungi filtro ristorante solo se specificato
        if ristorante_id:
            query = query.eq('ristorante_id', ristorante_id)
        
        # Escludi ricetta corrente per evitare loop
        if exclude_id:
            query = query.neq('id', exclude_id)
        
        response = query.execute()
        
        if not response.data:
            return []
        
        # Filtra solo SEMILAVORATI per massimo 2 livelli profondità
        ricette = [
            {
                'id': r['id'],
                'nome': r['nome'],
                'foodcost': float(r['foodcost_totale']),
                'categoria': r['categoria']
            }
            for r in response.data
            if r['categoria'] == 'SEMILAVORATI'  # Solo semilavorati come ingredienti
        ]
        
        return ricette
    
    except Exception as e:
        logger.error(f"Errore caricamento ricette ingredienti: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _get_ingredienti_workspace_cached(user_id: str, ristorante_id: str) -> list:
    """Cache ingredienti workspace per 5 minuti."""
    try:
        workspace_response = supabase.table('ingredienti_workspace')\
            .select('*')\
            .eq('userid', user_id)\
            .eq('ristorante_id', ristorante_id)\
            .order('nome')\
            .execute()
        return workspace_response.data or []
    except Exception as e:
        logger.warning(f"Errore ingredienti workspace: {e}")
        return []


def get_ingredienti_dropdown(user_id: str, ristorante_id: str, exclude_ricetta_id: str = None) -> tuple:
    """
    Merge articoli da fatture + ingredienti workspace + ricette in lista unica per dropdown.
    Ritorna (lista_ingredienti, debug_messages)
    """
    ingredienti_options = []
    debug_messages = []
    
    # 1. Articoli da fatture (prodotti reali)
    articoli, debug_msgs = get_articoli_da_fatture(user_id, ristorante_id)
    debug_messages.extend(debug_msgs)
    
    for art in articoli:
        # Mostra grammatura rilevata nel label se presente
        if art.get('grammatura_str'):
            label = f"🟢 {art['nome']} (€{art['prezzo_unitario']:.2f}/{art['um']} - Conf: {art['grammatura_str']})"
        else:
            label = f"🟢 {art['nome']} (€{art['prezzo_unitario']:.2f}/{art['um']})"
        
        ingredienti_options.append({
            'label': label,
            'tipo': 'articolo',
            'data': art
        })
    
    # 2. Ingredienti workspace (manuali/test) - cached
    workspace_data = _get_ingredienti_workspace_cached(user_id, ristorante_id)
    
    for ing in workspace_data:
        label = f"📝 {ing['nome']} (€{ing['prezzo_per_um']:.2f}/{ing['um']} - manuale)"
        ingredienti_options.append({
            'label': label,
            'tipo': 'workspace',
            'data': {
                'nome': ing['nome'],
                'prezzo_unitario': float(ing['prezzo_per_um']),
                'um': ing['um'],
                'id': ing['id']
            }
        })
    
    debug_messages.append(f"✅ Ingredienti workspace caricati: {len(workspace_data)}")
    
    # 3. Ricette salvate (solo SEMILAVORATI)
    ricette = get_ricette_come_ingredienti(user_id, ristorante_id, exclude_ricetta_id)
    for ric in ricette:
        label = f"🥘 {ric['nome']} (€{ric['foodcost']:.2f} - ricetta)"
        ingredienti_options.append({
            'label': label,
            'tipo': 'ricetta',
            'data': ric
        })
    
    # Ordina alfabeticamente
    ingredienti_options.sort(key=lambda x: x['label'])
    
    return ingredienti_options, debug_messages


def calcola_foodcost_riga(ingrediente_data: dict, quantita: float, um: str, grammatura_override: float = None) -> float:
    """
    Calcola prezzo di una riga ingrediente.
    Gestisce: articoli da fatture, ricette come ingredienti, ingredienti workspace.
    Usa la grammatura della confezione per calcolare il prezzo reale.
    
    Args:
        ingrediente_data: Dati ingrediente
        quantita: Quantità richiesta
        um: Unità di misura richiesta
        grammatura_override: Grammatura confezione personalizzata (g/ml)
    """
    if ingrediente_data['tipo'] == 'ricetta':
        # Ricetta: foodcost è già normalizzato
        foodcost_base = ingrediente_data['data']['foodcost']
        return converti_unita_misura(quantita, um, foodcost_base)
    
    elif ingrediente_data['tipo'] == 'workspace':
        # Ingrediente manuale: prezzo diretto per unità base
        prezzo_base = ingrediente_data['data']['prezzo_unitario']
        return converti_unita_misura(quantita, um, prezzo_base)
    
    else:  # articolo
        prezzo_confezione = ingrediente_data['data']['prezzo_unitario']
        
        # PASSO 1: Determina grammatura confezione
        grammatura_conf = grammatura_override  # Override manuale ha priorità
        
        if not grammatura_conf:
            # Usa grammatura rilevata automaticamente
            grammatura_conf = ingrediente_data['data'].get('grammatura_confezione')
        
        # PASSO 2: Calcola prezzo unitario reale
        if grammatura_conf and grammatura_conf > 0:
            # Abbiamo la grammatura confezione!
            # Es: Barilla 5KG a €8.30 → €8.30 / 5000g = €0.00166 al grammo
            grammatura_um = ingrediente_data['data'].get('grammatura_um', 'G')
            
            # Converti prezzo confezione a prezzo per kg/lt (unità base)
            if grammatura_um in ['G', 'GR']:
                # Prezzo per KG
                prezzo_base_kg = (prezzo_confezione / grammatura_conf) * 1000
            elif grammatura_um in ['ML']:
                # Prezzo per LT
                prezzo_base_kg = (prezzo_confezione / grammatura_conf) * 1000
            else:
                # Fallback: assume KG
                prezzo_base_kg = (prezzo_confezione / grammatura_conf) * 1000
            
            # Calcola prezzo per quantità richiesta
            return converti_unita_misura(quantita, um, prezzo_base_kg)
        
        else:
            # FALLBACK: Non abbiamo grammatura, usa vecchia logica
            um_db = ingrediente_data['data']['um'].upper()
            
            if um_db in ['G', 'GR', 'GRAMMI']:
                prezzo_base_kg = prezzo_confezione * 1000
            elif um_db in ['KG', 'KILOGRAMMI', 'KILO']:
                prezzo_base_kg = prezzo_confezione
            elif um_db in ['ML', 'MILLILITRI']:
                prezzo_base_kg = prezzo_confezione * 1000
            elif um_db in ['CL', 'CENTILITRI']:
                prezzo_base_kg = prezzo_confezione * 100
            elif um_db in ['LT', 'L', 'LITRI', 'LITRO']:
                prezzo_base_kg = prezzo_confezione
            elif um_db in ['PZ', 'PEZZO', 'PEZZI', 'N', 'NR']:
                prezzo_base_kg = prezzo_confezione
            else:
                prezzo_base_kg = prezzo_confezione
            
            return converti_unita_misura(quantita, um, prezzo_base_kg)


def clear_edit_mode():
    """Reset modalità modifica"""
    st.session_state.ricetta_edit_mode = False
    st.session_state.ricetta_edit_data = None
    st.session_state.ingredienti_temp = []
    
    # Pulisci anche i campi del form
    if 'nome_ricetta' in st.session_state:
        del st.session_state['nome_ricetta']
    if 'categoria_ricetta' in st.session_state:
        del st.session_state['categoria_ricetta']
    if 'search_ingredienti' in st.session_state:
        st.session_state['search_ingredienti'] = ""
    if 'prezzo_vendita_ricetta' in st.session_state:
        del st.session_state['prezzo_vendita_ricetta']
    
    invalidate_workspace_cache()  # Invalida solo cache workspace


# ============================================
# HEADER
# ============================================
render_oh_yeah_header()

st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 0.625rem;">
    🍴 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Workspace - Gestione Ricette e Foodcost</span>
</h2>
""", unsafe_allow_html=True)

st.markdown("""
<div style='background-color: #e7f3ff; padding: clamp(0.625rem, 1.5vw, 0.75rem); border-radius: 5px; border-left: 4px solid #2196F3;'>
<p style='margin: 0; color: #014361; font-size: clamp(0.75rem, 1.8vw, 0.875rem); line-height: 1.4; word-wrap: break-word;'>🍴 <strong>Workspace:</strong> Gestisci ricette, calcola il foodcost per piatto, monitora la marginalità e tieni il diario operativo.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# Session state per tab attivo
if 'workspace_tab' not in st.session_state:
    st.session_state.workspace_tab = "analisi"

# Se modalità edit attiva, forza apertura Lab Ricette
if st.session_state.ricetta_edit_mode:
    st.session_state.workspace_tab = "lab"

# Navigazione tab con bottoni - stile identico ad Analisi Fatture
col_t1, col_t2, col_t3, col_t4 = st.columns(4)
with col_t1:
    if st.button("📋 ANALISI\nRICETTE E MENÙ", key="btn_ws_analisi", use_container_width=True,
                 type="primary" if st.session_state.workspace_tab == "analisi" else "secondary"):
        if st.session_state.workspace_tab != "analisi":
            st.session_state.workspace_tab = "analisi"
            st.rerun()
with col_t2:
    if st.button("🧪 LAB\nRICETTE", key="btn_ws_lab", use_container_width=True,
                 type="primary" if st.session_state.workspace_tab == "lab" else "secondary"):
        if st.session_state.workspace_tab != "lab":
            st.session_state.workspace_tab = "lab"
            st.rerun()
with col_t3:
    if st.button("📓 DIARIO", key="btn_ws_diario", use_container_width=True,
                 type="primary" if st.session_state.workspace_tab == "diario" else "secondary"):
        if st.session_state.workspace_tab != "diario":
            st.session_state.workspace_tab = "diario"
            st.rerun()
with col_t4:
    if st.button("📊 EXPORT\nEXCEL", key="btn_ws_export", use_container_width=True,
                 type="primary" if st.session_state.workspace_tab == "export" else "secondary"):
        if st.session_state.workspace_tab != "export":
            st.session_state.workspace_tab = "export"
            st.rerun()

# CSS per bottoni tab - stile identico a Analisi Fatture
st.markdown("""
    <style>
    /* Globale: primary button azzurro */
    button[kind="primary"] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        font-weight: bold !important;
    }
    button[kind="primary"]:hover {
        background-color: #0284c7 !important;
        border-color: #0369a1 !important;
    }
    button[kind="primary"]:disabled,
    button[kind="primary"][disabled] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        opacity: 0.5 !important;
    }
    div[data-testid="column"] button[kind="primary"] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        font-weight: bold !important;
    }
    div[data-testid="column"] button[kind="primary"]:hover {
        background-color: #0284c7 !important;
        border-color: #0369a1 !important;
    }
    div[data-testid="column"] button[kind="secondary"] {
        background-color: #f0f2f6 !important;
        color: #31333F !important;
        border: 2px solid #e0e0e0 !important;
    }
    div[data-testid="column"] button[kind="secondary"]:hover {
        background-color: #e0e5eb !important;
        border-color: #0ea5e9 !important;
    }
    div[data-testid="column"] button p {
        font-size: clamp(0.7rem, 1.8vw, 0.95rem) !important;
        line-height: 1.3 !important;
        word-wrap: break-word !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
    }
    div[data-testid="column"] button {
        padding: 0.5rem 0.25rem !important;
        min-height: 3rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# Mappa session state a selected_tab per compatibilità con codice esistente
_tab_map = {
    "analisi": "📋 Analisi Ricette e Menù",
    "lab": "🧪 Lab Ricette",
    "diario": "📓 Diario",
    "export": "📊 Export Excel"
}
selected_tab = _tab_map[st.session_state.workspace_tab]

# ============================================
# TAB 1: ANALISI RICETTE E MENÙ
# ============================================
if selected_tab == "📋 Analisi Ricette e Menù":
    st.markdown("### 📊 Analisi Globale del Menu")

    try:
        # Carica ricette da Supabase
        query = supabase.table('ricette')\
            .select('*')\
            .eq('userid', user_id)\
            .order('ordine_visualizzazione', desc=False)
        
        # Aggiungi filtro ristorante solo se disponibile
        if current_ristorante:
            query = query.eq('ristorante_id', current_ristorante)
        
        response = query.execute()
        
        if not response.data or len(response.data) == 0:
            st.info("📭 Nessuna ricetta salvata. Vai al tab **Nuova Ricetta** per iniziare!")
        
        else:
            # ============================================
            # ANALISI COSTI PER CATEGORIA E MENU
            # ============================================
            # Prepara DataFrame per analisi (con tutte le ricette prima di filtrare)
            analisi_data = []
            for r in response.data:
                prezzo_ivainc = r.get('prezzo_vendita_ivainc')
                prezzo_netto = (float(prezzo_ivainc) / 1.10) if prezzo_ivainc and float(prezzo_ivainc) > 0 else None
                foodcost = float(r['foodcost_totale'])
                margine = round(prezzo_netto - foodcost, 2) if prezzo_netto else None
                incidenza = round((foodcost / prezzo_netto) * 100, 1) if prezzo_netto and prezzo_netto > 0 else None
                
                analisi_data.append({
                    'categoria': r['categoria'],
                    'nome': r['nome'],
                    'foodcost': foodcost,
                    'prezzo_vendita_ivainc': float(prezzo_ivainc) if prezzo_ivainc else None,
                    'prezzo_netto': prezzo_netto,
                    'margine': margine,
                    'incidenza': incidenza
                })
            
            df_analisi = pd.DataFrame(analisi_data)
            
            # Conta ricette con prezzo impostato
            ricette_con_prezzo = df_analisi['prezzo_netto'].notna().sum()
            
            # CSS per KPI con sfondo grigio argentato traslucido e bordo
            st.markdown("""
            <style>
            /* Altezza uniforme tra tutte le card KPI al variare dello zoom */
            [data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div[data-testid="column"] {
                display: flex !important;
                flex-direction: column !important;
                align-items: stretch !important;
            }
            [data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div[data-testid="column"] > div {
                flex: 1 !important;
                display: flex !important;
                flex-direction: column !important;
            }
            div[data-testid="stMetric"] {
                background: linear-gradient(135deg, rgba(248, 249, 250, 0.95), rgba(233, 236, 239, 0.95));
                padding: clamp(1rem, 2.5vw, 1.25rem);
                border-radius: 12px;
                border: 1px solid rgba(206, 212, 218, 0.5);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.05);
                backdrop-filter: blur(10px);
                height: 100%;
                min-height: 100px;
                box-sizing: border-box;
                justify-content: center;
            }
            div[data-testid="stMetric"] label {
                color: #2563eb !important;
                font-weight: 600 !important;
                font-size: clamp(0.75rem, 1.8vw, 0.875rem) !important;
            }
            div[data-testid="stMetric"] [data-testid="stMetricValue"] {
                color: #1e40af !important;
                font-size: clamp(1.25rem, 3.5vw, 1.75rem) !important;
                font-weight: 700 !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # KPI generali del menu - Tutti su una riga
            col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
            with col_kpi1:
                st.metric("📚 Ricette Totali", len(response.data))
            with col_kpi2:
                st.metric("💵 Costo Totale Menu", f"€{df_analisi['foodcost'].sum():.0f}")
            with col_kpi3:
                st.metric("📊 Costo Medio Ricetta", f"€{df_analisi['foodcost'].mean():.0f}")
            
            # KPI margine e incidenza (solo se ci sono ricette con prezzo)
            if ricette_con_prezzo > 0:
                df_con_prezzo = df_analisi[df_analisi['prezzo_netto'].notna()]
                
                with col_kpi4:
                    margine_medio = df_con_prezzo['margine'].mean()
                    st.metric("💹 Margine Medio", f"€{margine_medio:.0f}")
                with col_kpi5:
                    incidenza_media = df_con_prezzo['incidenza'].mean()
                    st.metric("📈 Incidenza% Media FC", f"{incidenza_media:.1f}%")
                
                if ricette_con_prezzo < len(response.data):
                    st.caption(f"⚠️ {len(response.data) - int(ricette_con_prezzo)} ricette senza prezzo di vendita — imposta il prezzo nel Lab Ricette per analisi complete")
            else:
                st.info("💡 Imposta il **Prezzo di Vendita** nelle ricette (tab Lab Ricette) per visualizzare margini e incidenza% food cost")
            
            # Analisi per categoria
            st.markdown("### 📊 Analisi per Categoria")
            
            # Costruisci tabella categorie con margine/incidenza
            cat_groups = df_analisi.groupby('categoria')
            cat_rows = []
            for cat_name, cat_df in cat_groups:
                row = {
                    'Categoria': cat_name,
                    'N. Ricette': len(cat_df),
                    'FC Tot. €': round(cat_df['foodcost'].sum(), 2),
                    'FC Medio €': round(cat_df['foodcost'].mean(), 2),
                }
                # Aggiungi colonne margine/incidenza solo se ci sono dati
                cat_con_prezzo = cat_df[cat_df['prezzo_netto'].notna()]
                if len(cat_con_prezzo) > 0:
                    row['Margine Medio €'] = round(cat_con_prezzo['margine'].mean(), 2)
                    row['Incidenza% Media'] = round(cat_con_prezzo['incidenza'].mean(), 1)
                else:
                    row['Margine Medio €'] = None
                    row['Incidenza% Media'] = None
                cat_rows.append(row)
            
            df_categorie = pd.DataFrame(cat_rows)
            
            # Emoji per categorie
            emoji_map = {
                'ANTIPASTI': '🥗',
                'BRACE': '🔥',
                'CARNE': '🥩',
                'CONTORNI': '🥦',
                'CRUDI': '🐟',
                'DOLCI': '🍰',
                'FOCACCE': '🫓',
                'FRITTI': '🍟',
                'GRIGLIA': '🔥',
                'INSALATE': '🥗',
                'PANINI': '🥖',
                'PESCE': '🐠',
                'PIADINE': '🫓',
                'PINZE': '🥐',
                'PIZZE': '🍕',
                'POKE': '🥗',
                'PRIMI': '🍝',
                'RISOTTI': '🍚',
                'SALTATI': '🥘',
                'SECONDI': '🍖',
                'SEMILAVORATI': '🥘',
                'SUSHI': '🍣',
                'TEMPURA': '🍤',
                'VAPORE': '♨️',
                'VERDURE': '🥬'
            }
            df_categorie['Categoria'] = df_categorie['Categoria'].apply(
                lambda x: f"{emoji_map.get(x, '📋')} {x}"
            )
            
            st.dataframe(
                df_categorie,
                use_container_width=True,
                hide_index=True
            )
    
    except Exception as e:
        st.error(f"❌ Errore caricamento ricette: {e}")
        logger.exception("Errore tab ricette salvate")


# ============================================
# TAB 2: NUOVA RICETTA
# ============================================
if selected_tab == "🧪 Lab Ricette":
    
    # Guida alla sezione (con sfondo azzurro chiaro) - PRIMA DI TUTTO
    st.markdown("""
    <style>
    div[data-testid="stExpander"]:first-of-type summary {
        background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%) !important;
        border-radius: 8px !important;
        padding: clamp(0.625rem, 1.5vw, 1rem) clamp(0.75rem, 2vw, 1rem) !important;
        color: #1e40af !important;
        font-weight: 600 !important;
    }
    div[data-testid="stExpander"]:first-of-type {
        margin-bottom: 24px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    with st.expander("ℹ️ Guida alla sezione Ricette", expanded=False):
        st.markdown("""
### 💡 Come creare una ricetta
1️⃣ Seleziona la **categoria** e inserisci il **nome** della ricetta  
2️⃣ Aggiungi gli **ingredienti** cercandoli nel menu o creandoli manualmente  
3️⃣ Puoi creare **semilavorati** (es: Besciamella, Ragù) impostando la categoria **SEMILAVORATI** per riutilizzarli in altre ricette

---

### 📝 Crea Ingrediente Manuale
Puoi creare ingredienti manualmente con prezzi stimati.  
Questi ingredienti rimangono isolati nel workspace e puoi modificarli/eliminarli in qualsiasi momento o sostituirli con quelli reali.

### 🍽️ Compila la Ricetta
**🔍 Ingrediente**: Cerca nel dropdown (es: scrivi "mozz" per trovare mozzarella). Vicino ad ogni ingrediente puoi trovare:
- Ingredienti dalle fatture caricate (icona 🟢)
- Ingredienti creati manualmente (icona 📝)
- Semilavorati salvati come ricette (icona 🍲)

- Ogni ingrediente ha il **💰 Prezzo** come indicato in fattura (modificabile se necessario)

**⚙️ Gram. Conf.** (Grammatura Confezione):  
è il Prezzo per confezione specifica → inserisci i gr/ml della confezione  
Esempio: Latta pomodoro 5KG a €10 → inserisci 5000

**📏 UM**: Unità di misura per il calcolo (g, kg, ml, lt, pz)  
**📊 Quantità**: Quanto ne usi nella ricetta (es: 200g di pomodoro)  
**💵 Costo**: in automatico attribuisce il costo proporzionato all'utilizzo.

Se necessario contattare l'assistenza.
        """)
    
    st.divider()
    
    # --- Crea Ingrediente Manuale (expander con intestazione verde chiaro) ---
    st.markdown("""
    <style>
    /* Sfondo verde chiaro SOLO per l'expander Crea Ingrediente Manuale */
    div[data-testid="stExpander"] details summary:has(span:where(:is([data-testid="stMarkdownContainer"])) ) {
    }
    div.st-key-expander_crea_ing > div[data-testid="stExpander"] > details > summary {
        background: #d4edda !important;
        border: 1px solid #c3e6cb !important;
        border-radius: 8px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.container(key="expander_crea_ing"):
        with st.expander("📝 Crea Ingrediente Manuale", expanded=False):
        
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        
            with col1:
                nuovo_ing_nome = st.text_input(
                    "Nome ingrediente",
                    placeholder="Es: Mozzarella, Pomodoro, Farina...",
                    key="nuovo_ing_nome",
                    help="Nome dell'ingrediente che vuoi creare"
                )
        
            with col2:
                nuovo_ing_prezzo = st.number_input(
                    "Prezzo €/unità",
                    min_value=0.0,
                    max_value=9999.99,
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                    key="nuovo_ing_prezzo",
                    help="Prezzo stimato per unità di misura"
                )
        
            with col3:
                nuovo_ing_um = st.selectbox(
                    "Unità Misura",
                    options=["KG", "LT", "PZ", "G", "ML"],
                    index=0,
                    key="nuovo_ing_um",
                    help="Unità di misura del prezzo"
                )
        
            with col4:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if st.button("💾 Salva", key="btn_salva_ing_workspace", use_container_width=True):
                    if not nuovo_ing_nome or not nuovo_ing_nome.strip():
                        st.error("⚠️ Inserisci un nome ingrediente")
                    elif nuovo_ing_prezzo <= 0:
                        st.error("⚠️ Inserisci un prezzo valido")
                    else:
                        try:
                            ing_payload = {
                                'userid': user_id,
                                'ristorante_id': current_ristorante,
                                'nome': nuovo_ing_nome.strip(),
                                'prezzo_per_um': nuovo_ing_prezzo,
                                'um': nuovo_ing_um
                            }
                            result = safe_db_execute(
                                lambda db: db.table('ingredienti_workspace').insert(ing_payload).execute(),
                                "insert ingrediente workspace"
                            )
                        
                            st.success(f"✅ Ingrediente '{nuovo_ing_nome}' creato!")
                            invalidate_workspace_cache()
                            st.rerun()
                        
                        except Exception as e:
                            if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                                st.error(f"⚠️ Ingrediente '{nuovo_ing_nome}' già esistente")
                            elif 'row-level security' in str(e).lower() or '42501' in str(e):
                                st.error("❌ Errore permessi database (RLS). Esegui la migrazione `024_fix_rls_custom_auth.sql` nel SQL Editor di Supabase.")
                                logger.error(f"RLS error ingredienti_workspace: {e}")
                            else:
                                st.error(f"❌ Errore: {str(e)}")
                                logger.exception("Errore creazione ingrediente workspace")
        
            # Lista ingredienti workspace esistenti
            try:
                workspace_ings = supabase.table('ingredienti_workspace')\
                    .select('*')\
                    .eq('userid', user_id)\
                    .eq('ristorante_id', current_ristorante)\
                    .order('nome')\
                    .execute()
            
                if workspace_ings.data:
                    st.markdown("**📦 Ingredienti manuali esistenti:**")
                
                    cols_ing = st.columns([3, 2, 1.5, 0.8, 0.8])
                    cols_ing[0].markdown("**Nome**")
                    cols_ing[1].markdown("**Prezzo**")
                    cols_ing[2].markdown("**UM**")
                    cols_ing[3].markdown("**Modifica**")
                    cols_ing[4].markdown("**Elimina**")
                
                    st.markdown('<div class="workspace-ingredients-list"></div>', unsafe_allow_html=True)
                
                    st.markdown("""
                    <style>
                    .workspace-ingredients-list + div {
                        max-height: 350px;
                        overflow-y: auto;
                        padding-right: 8px;
                        margin-top: 8px;
                    }
                    .workspace-ingredients-list + div::-webkit-scrollbar {
                        width: 8px;
                    }
                    .workspace-ingredients-list + div::-webkit-scrollbar-track {
                        background: #f1f5f9;
                        border-radius: 4px;
                    }
                    .workspace-ingredients-list + div::-webkit-scrollbar-thumb {
                        background: #94a3b8;
                        border-radius: 4px;
                    }
                    .workspace-ingredients-list + div::-webkit-scrollbar-thumb:hover {
                        background: #64748b;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                
                    for ing in workspace_ings.data:
                        is_editing = st.session_state.get(f"edit_ing_{ing['id']}", False)
                    
                        if is_editing:
                            cols = st.columns([3, 2, 1.5, 0.8, 0.8])
                        
                            with cols[0]:
                                edit_nome = st.text_input(
                                    "Nome",
                                    value=ing['nome'],
                                    key=f"edit_nome_{ing['id']}",
                                    label_visibility="collapsed"
                                )
                        
                            with cols[1]:
                                edit_prezzo = st.number_input(
                                    "Prezzo",
                                    min_value=0.0,
                                    value=float(ing['prezzo_per_um']),
                                    step=0.1,
                                    format="%.2f",
                                    key=f"edit_prezzo_{ing['id']}",
                                    label_visibility="collapsed"
                                )
                        
                            with cols[2]:
                                edit_um = st.selectbox(
                                    "UM",
                                    options=["KG", "LT", "PZ", "G", "ML"],
                                    index=["KG", "LT", "PZ", "G", "ML"].index(ing['um']) if ing['um'] in ["KG", "LT", "PZ", "G", "ML"] else 0,
                                    key=f"edit_um_{ing['id']}",
                                    label_visibility="collapsed"
                                )
                        
                            with cols[3]:
                                if st.button("💾", key=f"save_ing_{ing['id']}", help="Salva modifiche"):
                                    if not edit_nome or not edit_nome.strip():
                                        st.error("⚠️ Nome obbligatorio")
                                    elif edit_prezzo <= 0:
                                        st.error("⚠️ Prezzo non valido")
                                    else:
                                        try:
                                            upd_payload = {
                                                'nome': edit_nome.strip(),
                                                'prezzo_per_um': edit_prezzo,
                                                'um': edit_um
                                            }
                                            upd_id = ing['id']
                                            safe_db_execute(
                                                lambda db, _p=upd_payload, _id=upd_id: db.table('ingredienti_workspace').update(_p).eq('id', _id).execute(),
                                                "update ingrediente workspace"
                                            )
                                        
                                            st.success("✅ Modifiche salvate")
                                            st.session_state[f"edit_ing_{ing['id']}"] = False
                                            invalidate_workspace_cache()
                                            st.rerun()
                                        except Exception as e:
                                            if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                                                st.error(f"⚠️ Nome '{edit_nome}' già esistente")
                                            else:
                                                st.error(f"❌ Errore: {str(e)}")
                        
                            with cols[4]:
                                if st.button("❌", key=f"cancel_ing_{ing['id']}", help="Annulla"):
                                    st.session_state[f"edit_ing_{ing['id']}"] = False
                                    st.rerun()
                    
                        else:
                            cols = st.columns([3, 2, 1.5, 0.8, 0.8])
                            cols[0].text(ing['nome'])
                            cols[1].text(f"€{ing['prezzo_per_um']:.2f}")
                            cols[2].text(ing['um'])
                        
                            with cols[3]:
                                if st.button("✏️", key=f"edit_btn_ing_{ing['id']}", help="Modifica ingrediente"):
                                    st.session_state[f"edit_ing_{ing['id']}"] = True
                                    st.rerun()
                        
                            with cols[4]:
                                if st.button("🗑️", key=f"del_ing_{ing['id']}", help="Elimina ingrediente"):
                                    try:
                                        del_id = ing['id']
                                        safe_db_execute(
                                            lambda db, _id=del_id: db.table('ingredienti_workspace').delete().eq('id', _id).execute(),
                                            "delete ingrediente workspace"
                                        )
                                        st.success("✅ Ingrediente eliminato")
                                        invalidate_workspace_cache()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Errore eliminazione: {str(e)}")
            except Exception as e:
                st.warning(f"⚠️ Impossibile caricare ingredienti workspace: {str(e)}")
    
    st.divider()
    
    st.markdown("### ➕ Crea Ricetta")
    
    # Mostra banner se in modalità modifica
    if st.session_state.ricetta_edit_mode and st.session_state.ricetta_edit_data:
        ricetta_edit = st.session_state.ricetta_edit_data
        st.info(f"✏️ **Modalità Modifica**: {ricetta_edit['nome']}")
        if st.button("❌ Annulla Modifica"):
            clear_edit_mode()
            st.rerun()
    
    # Form header
    col_cat, col_nome, col_prezzo_vendita = st.columns([1, 2, 1])
    
    with col_cat:
        # Categorie in ordine alfabetico (include vecchie per compatibilità)
        categorie_ricette = [
            'ANTIPASTI',
            'BRACE',
            'CARNE',
            'CONTORNI',
            'CRUDI',
            'DOLCI',
            'FOCACCE',
            'FRITTI',
            'GRIGLIA',
            'INSALATE',
            'PANINI',
            'PESCE',
            'PIADINE',
            'PINZE',
            'PIZZE',
            'POKE',
            'PRIMI',
            'RISOTTI',
            'SALTATI',
            'SECONDI',
            'SEMILAVORATI',
            'SUSHI',
            'TEMPURA',
            'VAPORE',
            'VERDURE'
        ]
        
        default_cat = 0
        if st.session_state.ricetta_edit_mode:
            try:
                default_cat = categorie_ricette.index(st.session_state.ricetta_edit_data['categoria'])
            except (ValueError, KeyError):
                default_cat = 0
        
        categoria_sel = st.selectbox(
            "📂 Categoria",
            options=categorie_ricette,
            index=default_cat,
            key="categoria_ricetta"
        )
    
    with col_nome:
        # Inizializza il campo nome se in modalità modifica e non già impostato
        if st.session_state.ricetta_edit_mode and 'nome_ricetta' not in st.session_state:
            st.session_state['nome_ricetta'] = st.session_state.ricetta_edit_data['nome']
        elif not st.session_state.ricetta_edit_mode and 'nome_ricetta' not in st.session_state:
            st.session_state['nome_ricetta'] = ""
        
        nome_ricetta = st.text_input(
            "📝 Nome ricetta/semilavorato *",
            placeholder="Es: Lasagna al ragù, Besciamella, Pizza Margherita...",
            key="nome_ricetta"
        )
    
    with col_prezzo_vendita:
        # Inizializza prezzo vendita se in modalità modifica
        if st.session_state.ricetta_edit_mode and 'prezzo_vendita_ricetta' not in st.session_state:
            prezzo_edit = st.session_state.ricetta_edit_data.get('prezzo_vendita_ivainc') or 0.0
            st.session_state['prezzo_vendita_ricetta'] = float(prezzo_edit)
        elif not st.session_state.ricetta_edit_mode and 'prezzo_vendita_ricetta' not in st.session_state:
            st.session_state['prezzo_vendita_ricetta'] = 0.0
        
        prezzo_vendita = st.number_input(
            "💰 Prezzo Vendita (IVA 10% incl.)",
            min_value=0.0,
            max_value=9999.99,
            step=0.50,
            format="%.2f",
            key="prezzo_vendita_ricetta",
            help="Prezzo di vendita al pubblico IVA 10% inclusa"
        )
    
    # Info semilavorati
    if categoria_sel == 'SEMILAVORATI':
        st.info("💡 **Semilavorati** possono essere usati come ingredienti in altre ricette (max 2 livelli profondità)")
    
    # Carica opzioni ingredienti
    exclude_id = st.session_state.ricetta_edit_data['id'] if st.session_state.ricetta_edit_mode else None
    ingredienti_disponibili, debug_messages = get_ingredienti_dropdown(user_id, current_ristorante, exclude_id)
    
    # Verifica ingredienti disponibili
    if not ingredienti_disponibili:
        st.warning("⚠️ **Nessun ingrediente disponibile**")
        st.info("💡 **Soluzioni**:\n- Carica fatture nella sezione principale per usare prodotti reali\n- Oppure usa il bottone **📝 Crea Ingrediente Manuale** qui sopra per iniziare a testare le ricette")
        
        # Bottone refresh cache
        if st.button("🔄 Forza Refresh Cache"):
            invalidate_workspace_cache()
            st.rerun()
        
        # NON uso st.stop() per permettere al footer di caricarsi
    
    # Mostra form solo se ci sono ingredienti disponibili
    if ingredienti_disponibili:
        # Limita numero ingredienti (DoS protection)
        if len(st.session_state.ingredienti_temp) >= MAX_INGREDIENTI:
            st.error(f"⚠️ Limite massimo di {MAX_INGREDIENTI} ingredienti raggiunto")
        
        # Header tabella SEMPRE visibile con sfondo colorato
        st.markdown("""
        <div style="display: flex; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; padding: clamp(0.5rem, 1.5vw, 0.625rem) clamp(0.4rem, 1.2vw, 0.5rem); border-radius: 8px; font-weight: 600; 
                    font-size: clamp(0.7rem, 1.6vw, 0.8rem); margin-bottom: 0.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.15); 
                    white-space: nowrap; overflow-x: auto;">
            <div style="flex: 2.5;">🍽️ Ingrediente</div>
            <div style="flex: 1.2;">💰 Prezzo</div>
            <div style="flex: 1;">⚙️ Gram.Conf.</div>
            <div style="flex: 0.6;">📏 UM</div>
            <div style="flex: 1;">📊 Qtà</div>
            <div style="flex: 1.2;">💵 Costo</div>
            <div style="flex: 0.5; text-align: center;">🗑️</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Bottone per aggiungere ingredienti con testo allineato a sinistra
        st.markdown("""
        <style>
        /* Testo a sinistra SOLO sul bottone Aggiungi Ingrediente */
        div.st-key-add_ingredient_btn button[kind="secondary"] {
            text-align: left !important;
            display: flex !important;
            justify-content: flex-start !important;
            align-items: center !important;
        }
        div.st-key-add_ingredient_btn button[kind="secondary"] > div {
            text-align: left !important;
            justify-content: flex-start !important;
            display: flex !important;
            width: 100% !important;
        }
        div.st-key-add_ingredient_btn button[kind="secondary"] > div > p,
        div.st-key-add_ingredient_btn button[kind="secondary"] p {
            text-align: left !important;
            width: 100% !important;
        }
        div.st-key-add_ingredient_btn .stButton button {
            justify-content: flex-start !important;
        }
        div.st-key-add_ingredient_btn .stButton button div {
            justify-content: flex-start !important;
        }
        div.st-key-add_ingredient_btn .stButton button div p {
            text-align: left !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        if st.button("➕ Aggiungi Ingrediente", 
                     disabled=len(st.session_state.ingredienti_temp) >= MAX_INGREDIENTI,
                     use_container_width=True,
                     key="add_ingredient_btn"):
            st.session_state.ingredienti_temp.append({
                'nome': '',
                'quantita': 1.0,
                'um': 'g',
                'prezzo_unitario': 0.0,
                'is_ricetta': False,
                'ricetta_id': None,
                'ingrediente_ref': None,
                'grammatura_confezione': None,
                'prezzo_override': None,
                'tipo_riga': 'normale'
            })
            st.rerun()
        
        # Tabella dinamica ingredienti
        if len(st.session_state.ingredienti_temp) > 0:
            
            ingredienti_da_rimuovere = []
            
            for idx, ing in enumerate(st.session_state.ingredienti_temp):
                prezzo_riga = 0  # Calcolato in col6, riusato in col7
                col1, col2, col3, col4, col5, col6, col7 = st.columns([2.5, 1.2, 1, 0.6, 1, 1.2, 0.5])
                
                with col1:
                    # Mostra tutti gli ingredienti disponibili (articoli, workspace, ricette/semilavorati)
                    ingredienti_filtrati = ingredienti_disponibili
                    
                    # Trova indice default se modifica
                    default_idx = 0
                    if ing.get('ingrediente_ref'):
                        try:
                            default_idx = [i for i, x in enumerate(ingredienti_filtrati) if x['label'] == ing['ingrediente_ref']][0]
                        except (IndexError, ValueError):
                            default_idx = 0
                    
                    ing_sel = st.selectbox(
                        "Ingrediente",
                        options=[x['label'] for x in ingredienti_filtrati],
                        index=default_idx,
                        key=f"ing_nome_{idx}",
                        label_visibility="collapsed"
                    )
                    
                    # Trova dati ingrediente selezionato
                    ing_data = next((x for x in ingredienti_disponibili if x['label'] == ing_sel), None)
                    if ing_data:
                        ing['ingrediente_ref'] = ing_sel
                        ing['nome'] = ing_data['data']['nome']
                        ing['is_ricetta'] = (ing_data['tipo'] == 'ricetta')
                        if ing['is_ricetta']:
                            ing['ricetta_id'] = ing_data['data']['id']
                        else:
                            ing['ricetta_id'] = None
                
                with col2:
                    # Prezzo base articolo/workspace (MODIFICABILE per override manuale)
                    if ing_data and ing_data['tipo'] in ['articolo', 'workspace']:
                        prezzo_base = ing_data['data']['prezzo_unitario']
                        um_base = ing_data['data']['um']
                        
                        # Usa prezzo override se presente, altrimenti usa il prezzo base
                        prezzo_override_val = ing.get('prezzo_override')
                        prezzo_attuale = prezzo_override_val if prezzo_override_val is not None else prezzo_base
                        
                        # Key unica per ogni riga per evitare conflitti
                        prezzo_key = f"ing_prezzo_base_{idx}_{hash(ing_sel) % 10000}"
                        
                        # Indica se è manuale con icona
                        help_text = f"Prezzo per {um_base}. Originale: €{prezzo_base:.2f}"
                        if ing_data['tipo'] == 'workspace':
                            help_text = f"Prezzo per {um_base} (ingrediente manuale)"
                        
                        prezzo_modificato = st.number_input(
                            "Prezzo",
                            min_value=0.0,
                            value=float(prezzo_attuale),
                            step=0.01,
                            format="%.2f",
                            key=prezzo_key,
                            label_visibility="collapsed",
                            help=help_text
                        )
                        
                        # Salva override se diverso dal prezzo base
                        if abs(prezzo_modificato - prezzo_base) > 0.001:
                            ing['prezzo_override'] = prezzo_modificato
                        else:
                            ing['prezzo_override'] = None
                    else:
                        st.text_input("", value="-", disabled=True, key=f"ing_prezzo_base_{idx}", label_visibility="collapsed")
                
                with col3:
                    # Campo grammatura confezione (solo per articoli da fatture)
                    if ing_data and ing_data['tipo'] == 'articolo':
                        grammatura_auto = ing_data['data'].get('grammatura_confezione')
                        grammatura_attuale = ing.get('grammatura_confezione', grammatura_auto)
                        
                        grammatura_input = st.number_input(
                            "Grammatura Conf.",
                            min_value=0.0,
                            value=float(grammatura_attuale) if grammatura_attuale else 0.0,
                            step=100.0,
                            key=f"ing_gramm_{idx}",
                            label_visibility="collapsed",
                            help="Peso/volume totale a cui si riferisce il prezzo. 0 = prezzo già al KG/LT"
                        )
                        
                        ing['grammatura_confezione'] = grammatura_input if grammatura_input > 0 else None
                    elif ing_data and ing_data['tipo'] == 'workspace':
                        # Ingredienti workspace: prezzo già normalizzato, grammatura non necessaria
                        st.text_input("", value="N/A", disabled=True, key=f"ing_gramm_{idx}", 
                                     label_visibility="collapsed", help="Ingrediente manuale: prezzo già normalizzato")
                        ing['grammatura_confezione'] = None
                    else:
                        st.text_input("", value="-", disabled=True, key=f"ing_gramm_{idx}", label_visibility="collapsed")
                        ing['grammatura_confezione'] = None
                
                with col4:
                    unita_misura_options = ['g', 'kg', 'ml', 'lt', 'pz']
                    default_um_idx = 0
                    try:
                        default_um_idx = unita_misura_options.index(ing.get('um', 'g'))
                    except ValueError:
                        default_um_idx = 0
                    
                    ing['um'] = st.selectbox(
                        "U.M.",
                        options=unita_misura_options,
                        index=default_um_idx,
                        key=f"ing_um_{idx}",
                        label_visibility="collapsed"
                    )
                
                with col5:
                    # Quantità ingrediente
                    um_corrente = ing.get('um', 'g')
                    if um_corrente == 'pz':
                        min_val = 1.0
                        step = 1.0
                    elif um_corrente in ['g', 'ml']:
                        min_val = 1.0
                        step = 10.0
                    else:
                        min_val = 0.1
                        step = 0.1
                    
                    ing['quantita'] = st.number_input(
                        "Quantità",
                        min_value=min_val,
                        value=float(ing.get('quantita', 1.0)),
                        step=step,
                        key=f"ing_qta_{idx}",
                        label_visibility="collapsed"
                    )
                
                with col6:
                    # Calcolo costo riga (usa prezzo override se presente)
                    if ing_data and ing.get('quantita', 0) > 0:
                        grammatura_per_calcolo = ing.get('grammatura_confezione')
                        prezzo_override = ing.get('prezzo_override')
                        
                        # Se c'è un override, crea una copia di ing_data con il prezzo modificato
                        if prezzo_override is not None and ing_data['tipo'] in ['articolo', 'workspace']:
                            ing_data_modified = ing_data.copy()
                            ing_data_modified['data'] = ing_data['data'].copy()
                            ing_data_modified['data']['prezzo_unitario'] = prezzo_override
                            prezzo_riga = calcola_foodcost_riga(ing_data_modified, ing['quantita'], ing['um'], grammatura_per_calcolo)
                        else:
                            prezzo_riga = calcola_foodcost_riga(ing_data, ing['quantita'], ing['um'], grammatura_per_calcolo)
                        
                        ing['prezzo_unitario'] = (prezzo_riga / ing['quantita']) if ing['quantita'] > 0 else 0
                        st.markdown(f"<div style='background: #e0f2fe; "
                                    f"color: #0369a1; padding: clamp(0.4rem, 1.2vw, 0.5rem); border-radius: 6px; text-align: center; "
                                    f"font-weight: 600; font-size: clamp(0.8rem, 2vw, 0.95rem); border: 1px solid #bae6fd; word-wrap: break-word;'>€{prezzo_riga:.2f}</div>", 
                                    unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='background: #f1f5f9; color: #94a3b8; padding: clamp(0.4rem, 1.2vw, 0.5rem); "
                                    "border-radius: 6px; text-align: center; border: 1px solid #e2e8f0; word-wrap: break-word;'>€0.00</div>", unsafe_allow_html=True)
                
                with col7:
                    # Conferma eliminazione per righe costose (usa prezzo_riga calcolato in col6)
                    if prezzo_riga > 5:
                        if st.button("🗑️", key=f"del_ing_{idx}", help="Elimina ingrediente"):
                            st.session_state[f'confirm_del_ing_{idx}'] = True
                        
                        if st.session_state.get(f'confirm_del_ing_{idx}', False):
                            col_c1, col_c2 = st.columns(2)
                            with col_c1:
                                if st.button("✅", key=f"conf_yes_ing_{idx}"):
                                    ingredienti_da_rimuovere.append(idx)
                                    if f'confirm_del_ing_{idx}' in st.session_state:
                                        del st.session_state[f'confirm_del_ing_{idx}']
                            with col_c2:
                                if st.button("❌", key=f"conf_no_ing_{idx}"):
                                    del st.session_state[f'confirm_del_ing_{idx}']
                                    st.rerun()
                    else:
                        if st.button("❌", key=f"del_ing_{idx}", help="Rimuovi"):
                            ingredienti_da_rimuovere.append(idx)
            
            # Rimuovi ingredienti marcati
            if ingredienti_da_rimuovere:
                for idx in sorted(ingredienti_da_rimuovere, reverse=True):
                    del st.session_state.ingredienti_temp[idx]
                st.rerun()
            
            # BOTTONE SALVA (visibile solo quando ci sono ingredienti)
            st.markdown("<br>", unsafe_allow_html=True)  # Spazio sopra
            if st.button("💾 SALVA RICETTA", type="secondary"):
                # Validazioni
                errori = []
                
                if not nome_ricetta or nome_ricetta.strip() == "":
                    errori.append("⚠️ Il nome della ricetta è obbligatorio")
                
                if not categoria_sel:
                    errori.append("⚠️ Seleziona una categoria")
                
                if len(st.session_state.ingredienti_temp) == 0:
                    errori.append("⚠️ Aggiungi almeno 1 ingrediente con il bottone '➕ Aggiungi Ingrediente'")
                
                # Verifica ingredienti completi
                for idx, ing in enumerate(st.session_state.ingredienti_temp):
                    if not ing.get('ingrediente_ref') or ing.get('quantita', 0) <= 0:
                        errori.append(f"⚠️ Ingrediente #{idx+1}: dati incompleti")
                
                if errori:
                    st.error("❌ **Impossibile salvare la ricetta:**")
                    for err in errori:
                        st.error(err)
                else:
                    with st.spinner("💾 Salvataggio in corso..."):
                        try:
                            # Calcola food cost totale
                            foodcost_totale = 0
                            ingredienti_json = []
                            
                            for ing in st.session_state.ingredienti_temp:
                                ing_data = next((x for x in ingredienti_disponibili if x['label'] == ing['ingrediente_ref']), None)
                                if ing_data:
                                    grammatura_per_calcolo = ing.get('grammatura_confezione')
                                    prezzo_override = ing.get('prezzo_override')
                                    
                                    # Usa prezzo override se presente
                                    if prezzo_override is not None and ing_data['tipo'] in ['articolo', 'workspace']:
                                        ing_data_modified = ing_data.copy()
                                        ing_data_modified['data'] = ing_data['data'].copy()
                                        ing_data_modified['data']['prezzo_unitario'] = prezzo_override
                                        prezzo_riga = calcola_foodcost_riga(ing_data_modified, ing['quantita'], ing['um'], grammatura_per_calcolo)
                                    else:
                                        prezzo_riga = calcola_foodcost_riga(ing_data, ing['quantita'], ing['um'], grammatura_per_calcolo)
                                    
                                    foodcost_totale += prezzo_riga
                                    
                                    ingredienti_json.append({
                                        'nome': ing['nome'],
                                        'quantita': ing['quantita'],
                                        'um': ing['um'],
                                        'prezzo_unitario': (prezzo_riga / ing['quantita']) if ing['quantita'] > 0 else 0,
                                        'is_ricetta': ing['is_ricetta'],
                                        'ricetta_id': ing.get('ricetta_id'),
                                        'grammatura_confezione': ing.get('grammatura_confezione'),
                                        'prezzo_override': ing.get('prezzo_override')
                                    })
                            
                            # Prepara dati per insert/update
                            ricetta_data = {
                                'userid': user_id,
                                'nome': nome_ricetta.strip(),
                                'categoria': categoria_sel,
                                'ingredienti': json.dumps(ingredienti_json),
                                'foodcost_totale': round(foodcost_totale, 2),
                                'prezzo_vendita_ivainc': round(prezzo_vendita, 2) if prezzo_vendita > 0 else None
                            }
                            
                            # Aggiungi ristorante_id solo se disponibile
                            if current_ristorante:
                                ricetta_data['ristorante_id'] = current_ristorante
                            
                            if st.session_state.ricetta_edit_mode:
                                # UPDATE
                                ricetta_id = st.session_state.ricetta_edit_data['id']
                                safe_db_execute(
                                    lambda db, _d=ricetta_data, _id=ricetta_id: db.table('ricette').update(_d).eq('id', _id).execute(),
                                    "update ricetta"
                                )
                                
                                st.success(f"✅ Ricetta **{nome_ricetta}** aggiornata! Food cost: €{foodcost_totale:.2f}")
                            
                            else:
                                # INSERT
                                # Ottieni prossimo ordine disponibile
                                try:
                                    response_max = supabase.rpc('get_next_ordine_ricetta', {
                                        'p_userid': user_id,
                                        'p_ristorante_id': current_ristorante
                                    }).execute()
                                    next_ordine = response_max.data if response_max.data else 1
                                except Exception as e:
                                    logger.warning(f"Errore chiamata RPC get_next_ordine_ricetta: {e}")
                                    # Fallback: calcola max ordine manualmente
                                    try:
                                        q = supabase.table('ricette').select('ordine_visualizzazione').eq('userid', user_id)
                                        if current_ristorante:
                                            q = q.eq('ristorante_id', current_ristorante)
                                        resp = q.order('ordine_visualizzazione', desc=True).limit(1).execute()
                                        next_ordine = (resp.data[0]['ordine_visualizzazione'] + 1) if resp.data else 1
                                    except Exception:
                                        next_ordine = 1
                                
                                ricetta_data['ordine_visualizzazione'] = next_ordine
                                
                                safe_db_execute(
                                    lambda db, _d=ricetta_data: db.table('ricette').insert(_d).execute(),
                                    "insert ricetta"
                                )
                                
                                st.success(f"✅ Ricetta **{nome_ricetta}** salvata! Food cost: €{foodcost_totale:.2f}")
                            
                            # Clear form e cache
                            clear_edit_mode()
                            
                            # Ricarica la pagina
                            st.rerun()
                        
                        except Exception as e:
                            if 'row-level security' in str(e).lower() or '42501' in str(e):
                                st.error("❌ Errore permessi database (RLS). Esegui la migrazione `024_fix_rls_custom_auth.sql` nel SQL Editor di Supabase.")
                                logger.error(f"RLS error ricette: {e}")
                            else:
                                st.error(f"❌ **Errore durante il salvataggio:**")
                                st.error(f"Dettagli: {str(e)}")
                            logger.exception("Errore salvataggio ricetta")

    # ============================================
    # RICETTE SALVATE (in fondo al tab Nuova Ricetta)
    # ============================================
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 📋 Ricette Salvate")
    
    try:
        query_salvate = supabase.table('ricette')\
            .select('*')\
            .eq('userid', user_id)\
            .order('ordine_visualizzazione', desc=False)
        
        if current_ristorante:
            query_salvate = query_salvate.eq('ristorante_id', current_ristorante)
        
        response_salvate = query_salvate.execute()
        
        if not response_salvate.data or len(response_salvate.data) == 0:
            st.info("📭 Nessuna ricetta salvata ancora.")
        else:
            # Filtro rapido
            col_f1, col_f2 = st.columns([2, 3])
            with col_f1:
                cat_disp = ["TUTTE"] + sorted(set(r['categoria'] for r in response_salvate.data))
                filtro_cat = st.selectbox("🔍 Filtra categoria", options=cat_disp, key="filtro_cat_salvate")
            with col_f2:
                filtro_nm = st.text_input("🔍 Cerca nome", placeholder="Digita nome...", key="filtro_nome_salvate")
            
            ricette_vis = response_salvate.data
            if filtro_cat != "TUTTE":
                ricette_vis = [r for r in ricette_vis if r['categoria'] == filtro_cat]
            if filtro_nm:
                ricette_vis = [r for r in ricette_vis if filtro_nm.lower() in r['nome'].lower()]
            
            st.caption(f"**{len(ricette_vis)}** ricette trovate")
            
            categoria_emoji = {
                'ANTIPASTI': '🥗', 'PRIMI': '🍝', 'SECONDI': '🥩',
                'PIZZE': '🍕', 'DOLCI': '🍰', 'SEMILAVORATI': '🥘'
            }
            
            for idx, ricetta in enumerate(ricette_vis):
                ingredienti_ricetta = json.loads(ricetta['ingredienti']) if isinstance(ricetta['ingredienti'], str) else ricetta['ingredienti']
                
                # Calcola margine e incidenza per l'intestazione
                prezzo_ivainc = ricetta.get('prezzo_vendita_ivainc')
                extra_info = ""
                if prezzo_ivainc and float(prezzo_ivainc) > 0:
                    p_netto = float(prezzo_ivainc) / 1.10
                    fc = float(ricetta['foodcost_totale'])
                    margine_r = p_netto - fc
                    incidenza_r = (fc / p_netto * 100) if p_netto > 0 else 0
                    extra_info = f" │ 💶 **€{p_netto:.2f}** (prezzo vendita senza iva) │ 💹 **€{margine_r:.2f}** margine (prezzo - costo) │ 📈 **{incidenza_r:.1f}%** Foodcost"
                
                with st.expander(f"🍽️ **{ricetta['nome']}** │ 📂 **{ricetta['categoria']}** │ 💰 Costo: **€{ricetta['foodcost_totale']:.2f}** │ 🧪 n.ingredienti: **{len(ingredienti_ricetta)}**{extra_info}", expanded=False):
                    # Tabella ingredienti
                    if ingredienti_ricetta:
                        df_ing_s = pd.DataFrame(ingredienti_ricetta)
                        df_ing_s['costo_totale'] = df_ing_s['quantita'] * df_ing_s['prezzo_unitario']
                        st.dataframe(
                            df_ing_s[['nome', 'quantita', 'um', 'prezzo_unitario', 'costo_totale']],
                            use_container_width=True,
                            hide_index=True
                        )
                    
                    # Bottoni azione
                    col_a1, col_a2, col_a3, col_a4 = st.columns(4)
                    
                    with col_a1:
                        if idx > 0:
                            if st.button("⬆️ Su", key=f"s_up_{ricetta['id']}", use_container_width=True):
                                try:
                                    prev = ricette_vis[idx - 1]
                                    supabase.rpc('swap_ricette_order', {
                                        'ricetta_id_1': ricetta['id'],
                                        'ricetta_id_2': prev['id']
                                    }).execute()
                                    invalidate_workspace_cache()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                    
                    with col_a2:
                        if idx < len(ricette_vis) - 1:
                            if st.button("⬇️ Giù", key=f"s_down_{ricetta['id']}", use_container_width=True):
                                try:
                                    nxt = ricette_vis[idx + 1]
                                    supabase.rpc('swap_ricette_order', {
                                        'ricetta_id_1': ricetta['id'],
                                        'ricetta_id_2': nxt['id']
                                    }).execute()
                                    invalidate_workspace_cache()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                    
                    with col_a3:
                        if st.button("✏️ Modifica", key=f"s_edit_{ricetta['id']}", use_container_width=True):
                            try:
                                st.session_state.ricetta_edit_mode = True
                                st.session_state.ricetta_edit_data = ricetta
                                # Rimuovi le chiavi widget per evitare conflitti con widget già istanziati
                                if 'nome_ricetta' in st.session_state:
                                    del st.session_state['nome_ricetta']
                                if 'categoria_ricetta' in st.session_state:
                                    del st.session_state['categoria_ricetta']
                                if 'prezzo_vendita_ricetta' in st.session_state:
                                    del st.session_state['prezzo_vendita_ricetta']
                                
                                ingredienti_raw = json.loads(ricetta['ingredienti']) if isinstance(ricetta['ingredienti'], str) else ricetta['ingredienti']
                                ingredienti_disp_reload, _ = get_ingredienti_dropdown(user_id, current_ristorante, ricetta['id'])
                                
                                ingredienti_temp = []
                                for ing_salvato in ingredienti_raw:
                                    ing_match = next((x for x in ingredienti_disp_reload if x['data']['nome'] == ing_salvato['nome']), None)
                                    tipo_riga = 'semilavorato' if ing_salvato.get('is_ricetta', False) else 'normale'
                                    ingredienti_temp.append({
                                        'nome': ing_salvato['nome'],
                                        'quantita': ing_salvato['quantita'],
                                        'um': ing_salvato['um'],
                                        'prezzo_unitario': ing_salvato.get('prezzo_unitario', 0),
                                        'is_ricetta': ing_salvato.get('is_ricetta', False),
                                        'ricetta_id': ing_salvato.get('ricetta_id'),
                                        'ingrediente_ref': ing_match['label'] if ing_match else None,
                                        'grammatura_confezione': ing_salvato.get('grammatura_confezione'),
                                        'prezzo_override': ing_salvato.get('prezzo_override'),
                                        'tipo_riga': tipo_riga
                                    })
                                
                                st.session_state.ingredienti_temp = ingredienti_temp
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Errore: {e}")
                    
                    with col_a4:
                        if st.button("🗑️ Elimina", key=f"s_del_{ricetta['id']}", use_container_width=True):
                            st.session_state[f's_confirm_del_{ricetta["id"]}'] = True
                    
                    # Conferma eliminazione
                    if st.session_state.get(f's_confirm_del_{ricetta["id"]}', False):
                        st.warning(f"⚠️ Confermi eliminazione di **{ricetta['nome']}**?")
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            if st.button("✅ Sì, elimina", key=f"s_cyes_{ricetta['id']}"):
                                try:
                                    del_ricetta_id = ricetta['id']
                                    safe_db_execute(
                                        lambda db, _id=del_ricetta_id: db.table('ricette').delete().eq('id', _id).execute(),
                                        "delete ricetta"
                                    )
                                    st.success("Ricetta eliminata")
                                    invalidate_workspace_cache()
                                    del st.session_state[f's_confirm_del_{ricetta["id"]}']
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                        with col_c2:
                            if st.button("❌ Annulla", key=f"s_cno_{ricetta['id']}"):
                                del st.session_state[f's_confirm_del_{ricetta["id"]}']
                                st.rerun()
    
    except Exception as e:
        st.error(f"❌ Errore caricamento ricette salvate: {e}")
        logger.exception("Errore ricette salvate in tab2")


# ============================================
# TAB 3: EXPORT EXCEL
# ============================================
if selected_tab == "📊 Export Excel":
    st.markdown("### 📊 Export Ricette in Excel")
    
    st.info("""
    **📥 Scarica tutte le ricette**
    
    Il file Excel conterrà:
    - 📋 Elenco ricette con food cost, prezzi e margini
    - 🥄 Dettagli ingredienti per ogni ricetta
    - 💰 Analisi costi e margini per categoria
    - 📊 KPI globali del menù
    """)
    
    try:
        # Carica tutte le ricette
        query = supabase.table('ricette')\
            .select('*')\
            .eq('userid', user_id)\
            .order('categoria', desc=False)\
            .order('nome', desc=False)
        
        # Aggiungi filtro ristorante solo se disponibile
        if current_ristorante:
            query = query.eq('ristorante_id', current_ristorante)
        
        response = query.execute()
        
        if not response.data or len(response.data) == 0:
            st.warning("📭 Nessuna ricetta da esportare")
        else:
            num_ricette = len(response.data)
            st.caption(f"✅ **{num_ricette}** ricette pronte per l'export")
            
            try:
                # Prepara DataFrame principale
                ricette_export = []
                ingredienti_export = []
                
                for ricetta in response.data:
                    # Calcola prezzo netto, margine e incidenza
                    foodcost = float(ricetta['foodcost_totale'])
                    prezzo_ivainc = ricetta.get('prezzo_vendita_ivainc')
                    
                    if prezzo_ivainc and float(prezzo_ivainc) > 0:
                        prezzo_netto = float(prezzo_ivainc) / 1.10
                        margine = prezzo_netto - foodcost
                        incidenza = (foodcost / prezzo_netto * 100) if prezzo_netto > 0 else 0
                    else:
                        prezzo_netto = None
                        margine = None
                        incidenza = None
                    
                    ricette_export.append({
                        'Nome': ricetta['nome'],
                        'Categoria': ricetta['categoria'],
                        'Food Cost (€)': foodcost,
                        'Prezzo Vendita IVA inc. (€)': float(prezzo_ivainc) if prezzo_ivainc else None,
                        'Prezzo Vendita Netto (€)': round(prezzo_netto, 2) if prezzo_netto else None,
                        'Margine (€)': round(margine, 2) if margine else None,
                        'Incidenza FC (%)': round(incidenza, 1) if incidenza else None,
                        'Num. Ingredienti': len(json.loads(ricetta['ingredienti']) if isinstance(ricetta['ingredienti'], str) else ricetta['ingredienti']),
                        'Data Creazione': ricetta['created_at'][:10] if ricetta.get('created_at') else ''
                    })
                    
                    # Dettagli ingredienti
                    ingredienti = json.loads(ricetta['ingredienti']) if isinstance(ricetta['ingredienti'], str) else ricetta['ingredienti']
                    for ing in ingredienti:
                        ingredienti_export.append({
                            'Ricetta': ricetta['nome'],
                            'Categoria Ricetta': ricetta['categoria'],
                            'Ingrediente': ing['nome'],
                            'Quantità': ing['quantita'],
                            'U.M.': ing['um'],
                            'Prezzo Unitario (€)': float(ing['prezzo_unitario']),
                            'Prezzo Totale (€)': float(ing['quantita'] * ing['prezzo_unitario']),
                            'Tipo': 'Ricetta' if ing.get('is_ricetta') else 'Articolo'
                        })
                
                df_ricette = pd.DataFrame(ricette_export)
                df_ingredienti = pd.DataFrame(ingredienti_export)
                
                # Analisi per categoria (con margini e incidenza)
                cat_groups = df_ricette.groupby('Categoria')
                cat_rows = []
                for cat_name, cat_df in cat_groups:
                    row = {
                        'Categoria': cat_name,
                        'Num. Ricette': len(cat_df),
                        'Food Cost Totale (€)': round(cat_df['Food Cost (€)'].sum(), 2),
                        'Food Cost Medio (€)': round(cat_df['Food Cost (€)'].mean(), 2),
                    }
                    # Aggiungi margine e incidenza se disponibili
                    cat_con_prezzo = cat_df[cat_df['Margine (€)'].notna()]
                    if len(cat_con_prezzo) > 0:
                        row['Margine Medio (€)'] = round(cat_con_prezzo['Margine (€)'].mean(), 2)
                        row['Incidenza% FC Media'] = round(cat_con_prezzo['Incidenza FC (%)'].mean(), 1)
                    else:
                        row['Margine Medio (€)'] = None
                        row['Incidenza% FC Media'] = None
                    cat_rows.append(row)
                
                df_categorie = pd.DataFrame(cat_rows)
                
                # KPI globali menù
                kpi_data = {
                    'Ricette Totali': [len(df_ricette)],
                    'Food Cost Totale Menu (€)': [round(df_ricette['Food Cost (€)'].sum(), 2)],
                    'Food Cost Medio Ricetta (€)': [round(df_ricette['Food Cost (€)'].mean(), 2)]
                }
                # Aggiungi KPI margine/incidenza se disponibili
                ricette_con_prezzo = df_ricette[df_ricette['Margine (€)'].notna()]
                if len(ricette_con_prezzo) > 0:
                    kpi_data['Margine Medio (€)'] = [round(ricette_con_prezzo['Margine (€)'].mean(), 2)]
                    kpi_data['Incidenza% FC Media'] = [round(ricette_con_prezzo['Incidenza FC (%)'].mean(), 1)]
                    kpi_data['Ricette con Prezzo'] = [f"{len(ricette_con_prezzo)}/{len(df_ricette)}"]
                
                df_kpi = pd.DataFrame(kpi_data)
                
                # Crea Excel in memoria
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_kpi.to_excel(writer, sheet_name='KPI Globali', index=False)
                    df_ricette.to_excel(writer, sheet_name='Ricette', index=False)
                    df_ingredienti.to_excel(writer, sheet_name='Ingredienti Dettaglio', index=False)
                    df_categorie.to_excel(writer, sheet_name='Analisi Categorie', index=False)
                    
                    # Formattazione
                    workbook = writer.book
                    money_fmt = workbook.add_format({'num_format': '€#,##0.00'})
                    percent_fmt = workbook.add_format({'num_format': '0.0"%"'})
                    
                    # Applica formattazione KPI
                    worksheet_kpi = writer.sheets['KPI Globali']
                    worksheet_kpi.set_column('B:D', 18, money_fmt)
                    worksheet_kpi.set_column('E:E', 16, percent_fmt)
                    
                    # Applica formattazione ricette
                    worksheet_ricette = writer.sheets['Ricette']
                    worksheet_ricette.set_column('C:F', 18, money_fmt)
                    worksheet_ricette.set_column('G:G', 14, percent_fmt)
                    
                    # Applica formattazione categorie
                    worksheet_cat = writer.sheets['Analisi Categorie']
                    worksheet_cat.set_column('C:E', 18, money_fmt)
                    worksheet_cat.set_column('F:F', 16, percent_fmt)
                    
                    # Applica formattazione ingredienti
                    worksheet_ing = writer.sheets['Ingredienti Dettaglio']
                    worksheet_ing.set_column('F:G', 14, money_fmt)
                
                output.seek(0)
                
                # Download diretto con un solo click
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ricette_export_{timestamp}.xlsx"
                
                # CSS scoped per bottone verde solo in questo container
                st.markdown("""
                <style>
                div.st-key-export_excel_btn_container .stDownloadButton button {
                    background-color: #22c55e !important;
                    color: white !important;
                    border: none !important;
                    border-radius: 8px !important;
                    font-weight: 600 !important;
                }
                div.st-key-export_excel_btn_container .stDownloadButton button:hover {
                    background-color: #16a34a !important;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # Posiziona bottone a sinistra con colonne
                col_btn, col_spacer = st.columns([1, 3])
                with col_btn:
                    with st.container(key="export_excel_btn_container"):
                        st.download_button(
                            label="📥 Scarica Excel",
                            data=output.getvalue(),
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
            
            except Exception as e:
                st.error(f"❌ Errore generazione Excel: {e}")
                logger.exception("Errore export Excel")
    
    except Exception as e:
        st.error(f"❌ Errore caricamento dati: {e}")
        logger.exception("Errore tab export")


# ============================================
# TAB 4: DIARIO
# ============================================
if selected_tab == "📓 Diario":
    st.markdown("### 📓 Diario - Note e Appunti")
    st.caption("💡 Tieni traccia di attività, decisioni e appunti importanti per il tuo ristorante")
    
    # Form per nuova nota
    with st.expander("➕ Crea Nuova Nota", expanded=False):
        nuova_nota_testo = st.text_area(
            "Scrivi la tua nota",
            placeholder="Es: Oggi ho testato una nuova ricetta per la pizza...",
            height=150,
            key="nuova_nota_testo"
        )
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn2:
            if st.button("💾 Salva Nota", use_container_width=True, type="primary"):
                if not nuova_nota_testo or not nuova_nota_testo.strip():
                    st.error("⚠️ Inserisci del testo per la nota")
                else:
                    try:
                        nota_payload = {
                            'userid': user_id,
                            'ristorante_id': current_ristorante,
                            'testo': nuova_nota_testo.strip()
                        }
                        try:
                            supabase.table('note_diario').insert(nota_payload).execute()
                        except Exception as conn_err:
                            if 'disconnect' in str(conn_err).lower() or 'closed' in str(conn_err).lower():
                                logger.warning("Riconnessione Supabase per insert nota...")
                                fresh = get_fresh_supabase_client()
                                fresh.table('note_diario').insert(nota_payload).execute()
                            else:
                                raise conn_err
                        
                        st.success("✅ Nota salvata!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Errore salvataggio: {str(e)}")
                        logger.exception("Errore salvataggio nota diario")
    
    # Carica note esistenti in ordine cronologico
    try:
        try:
            query_note = supabase.table('note_diario')\
                .select('*')\
                .eq('userid', user_id)
            if current_ristorante:
                query_note = query_note.eq('ristorante_id', current_ristorante)
            note_response = query_note.order('created_at', desc=True).execute()
        except Exception as conn_err:
            if 'disconnect' in str(conn_err).lower() or 'closed' in str(conn_err).lower():
                logger.warning("Riconnessione Supabase per select note...")
                fresh = get_fresh_supabase_client()
                query_note = fresh.table('note_diario')\
                    .select('*')\
                    .eq('userid', user_id)
                if current_ristorante:
                    query_note = query_note.eq('ristorante_id', current_ristorante)
                note_response = query_note.order('created_at', desc=True).execute()
            else:
                raise conn_err
        
        if note_response.data:
            st.markdown(f"**📝 {len(note_response.data)} note salvate**")
            st.markdown("---")
            
            # Colori post-it (rotazione)
            colori_postit = [
                ('#fef3c7', '#78350f'),  # Giallo
                ('#d1fae5', '#064e3b'),  # Verde
                ('#dbeafe', '#1e3a8a'),  # Azzurro
                ('#fce7f3', '#831843'),  # Rosa
                ('#e0e7ff', '#3730a3'),  # Indaco
            ]
            
            # Layout a griglia: 3 post-it per riga
            note_list = note_response.data
            num_cols = 3
            
            for i in range(0, len(note_list), num_cols):
                cols = st.columns(num_cols)
                
                for j, col in enumerate(cols):
                    if i + j < len(note_list):
                        nota = note_list[i + j]
                        colore_bg, colore_text = colori_postit[(i + j) % len(colori_postit)]
                        
                        with col:
                            # Controlla se in modalità modifica
                            is_editing = st.session_state.get(f"edit_nota_{nota['id']}", False)
                            
                            # Data formattata
                            data_creazione = datetime.fromisoformat(nota['created_at'].replace('Z', '+00:00'))
                            data_modifica = datetime.fromisoformat(nota['updated_at'].replace('Z', '+00:00'))
                            data_str = data_creazione.strftime("%d/%m/%y %H:%M")
                            modificata = data_creazione != data_modifica
                            
                            if is_editing:
                                # Modalità modifica - full size
                                st.markdown(f"""
                                <div style='background: {colore_bg}; 
                                            padding: clamp(0.75rem, 2vw, 1rem); 
                                            border-radius: 8px; 
                                            box-shadow: 3px 3px 8px rgba(0,0,0,0.15);
                                            min-height: 15.5rem;
                                            margin-bottom: 0.9rem;
                                            border: 1px solid {colore_text}20;'>
                                    <div style='color: {colore_text}; opacity: 0.7; font-size: clamp(0.6rem, 1.4vw, 0.7rem); margin-bottom: 0.625rem; word-wrap: break-word;'>
                                        📅 {data_str}
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                edit_testo = st.text_area(
                                    "Modifica",
                                    value=nota['testo'],
                                    height=150,
                                    key=f"edit_testo_{nota['id']}",
                                    label_visibility="collapsed"
                                )
                                
                                col_save, col_cancel = st.columns(2)
                                with col_save:
                                    if st.button("💾", key=f"save_{nota['id']}", use_container_width=True, help="Salva"):
                                        if edit_testo and edit_testo.strip():
                                            try:
                                                try:
                                                    supabase.table('note_diario')\
                                                        .update({'testo': edit_testo.strip()})\
                                                        .eq('id', nota['id'])\
                                                        .execute()
                                                except Exception as conn_err:
                                                    if 'disconnect' in str(conn_err).lower() or 'closed' in str(conn_err).lower():
                                                        fresh = get_fresh_supabase_client()
                                                        fresh.table('note_diario')\
                                                            .update({'testo': edit_testo.strip()})\
                                                            .eq('id', nota['id'])\
                                                            .execute()
                                                    else:
                                                        raise conn_err
                                                st.session_state[f"edit_nota_{nota['id']}"] = False
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"❌ {str(e)}")
                                
                                with col_cancel:
                                    if st.button("❌", key=f"cancel_{nota['id']}", use_container_width=True, help="Annulla"):
                                        st.session_state[f"edit_nota_{nota['id']}"] = False
                                        st.rerun()
                            else:
                                # Modalità visualizzazione - post-it compatto
                                testo_troncato = nota['testo'][:120] + "..." if len(nota['testo']) > 120 else nota['testo']
                                
                                st.markdown(f"""
                                <div style='background: {colore_bg}; 
                                            padding: clamp(0.75rem, 2vw, 1rem); 
                                            border-radius: 8px; 
                                            box-shadow: 3px 3px 8px rgba(0,0,0,0.15);
                                            min-height: 12.5rem;
                                            margin-bottom: 0.9rem;
                                            position: relative;
                                            border: 1px solid {colore_text}20;
                                            cursor: pointer;'>
                                    <div style='color: {colore_text}; opacity: 0.7; font-size: clamp(0.6rem, 1.4vw, 0.7rem); margin-bottom: 0.625rem; word-wrap: break-word;'>
                                        📅 {data_str} {'✏️' if modificata else ''}
                                    </div>
                                    <div style='color: {colore_text}; 
                                                font-size: clamp(0.75rem, 1.8vw, 0.875rem); 
                                                line-height: 1.5;
                                                white-space: pre-wrap;
                                                word-wrap: break-word;
                                                max-height: 8.75rem;
                                                overflow: hidden;'>
                                        {testo_troncato}
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Pulsanti azione piccoli
                                col_edit, col_del = st.columns(2)
                                with col_edit:
                                    if st.button("✏️", key=f"edit_{nota['id']}", use_container_width=True, help="Modifica"):
                                        st.session_state[f"edit_nota_{nota['id']}"] = True
                                        st.rerun()
                                
                                with col_del:
                                    if st.button("🗑️", key=f"del_{nota['id']}", use_container_width=True, help="Elimina"):
                                        try:
                                            try:
                                                supabase.table('note_diario').delete().eq('id', nota['id']).execute()
                                            except Exception as conn_err:
                                                if 'disconnect' in str(conn_err).lower() or 'closed' in str(conn_err).lower():
                                                    fresh = get_fresh_supabase_client()
                                                    fresh.table('note_diario').delete().eq('id', nota['id']).execute()
                                                else:
                                                    raise conn_err
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ {str(e)}")
                
                # Spaziatura tra righe
                st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.info("📝 Non hai ancora creato nessuna nota. Clicca su 'Crea Nuova Nota' per iniziare!")
    
    except Exception as e:
        st.error(f"❌ Errore caricamento note: {str(e)}")
        logger.exception("Errore caricamento note diario")
