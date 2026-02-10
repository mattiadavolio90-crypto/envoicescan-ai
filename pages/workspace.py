"""
Workspace - Area di Lavoro
Pagina dedicata alla gestione operativa del ristorante
"""

import streamlit as st
import pandas as pd
import json
import io
import time
from datetime import datetime
from supabase import create_client, Client
from config.logger_setup import get_logger
from utils.ristorante_helper import get_current_ristorante_id
from utils.sidebar_helper import render_sidebar
from config.constants import CATEGORIE_SPESE_OPERATIVE

# Logger
logger = get_logger('workspace')

# ============================================
# SUPABASE CLIENT (senza import da app.py)
# ============================================
@st.cache_resource
def get_supabase_client() -> Client:
    """Client Supabase singleton per questa pagina"""
    try:
        supabase_url = st.secrets["supabase"]["url"]
        supabase_key = st.secrets["supabase"]["key"]
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        logger.exception("Connessione Supabase fallita")
        st.error(f"⛔ Errore connessione Supabase: {e}")
        st.stop()

# Inizializza client
supabase = get_supabase_client()

# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Workspace - FCI",
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
            except:
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


@st.cache_data(ttl=60, show_spinner="Caricamento articoli dalle fatture...")
def get_articoli_da_fatture(_user_id: str) -> tuple:
    """
    Carica articoli unici da fatture con ultimo prezzo.
    Ritorna (lista_articoli, messaggi_debug)
    """
    debug_msgs = []
    try:
        debug_msgs.append(f"🔍 Cerco fatture per user_id: {_user_id}")
        
        # Query articoli escludendo spese operative (servizi, utenze, manutenzione)
        response = supabase.table('fatture')\
            .select('descrizione, prezzo_unitario, unita_misura, data_documento, categoria')\
            .eq('user_id', _user_id)\
            .not_.in_('categoria', CATEGORIE_SPESE_OPERATIVE)\
            .order('data_documento', desc=True)\
            .execute()
        
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
def get_ricette_come_ingredienti(_user_id: str, _ristorante_id: str, exclude_id: str = None) -> list:
    """
    Carica ricette salvate utilizzabili come ingredienti.
    Cache 5 minuti per performance.
    """
    try:
        query = supabase.table('ricette')\
            .select('id, nome, foodcost_totale, categoria')\
            .eq('userid', _user_id)
        
        # Aggiungi filtro ristorante solo se specificato
        if _ristorante_id:
            query = query.eq('ristorante_id', _ristorante_id)
        
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


def get_ingredienti_dropdown(user_id: str, ristorante_id: str, exclude_ricetta_id: str = None) -> tuple:
    """
    Merge articoli da fatture + ingredienti workspace + ricette in lista unica per dropdown.
    Ritorna (lista_ingredienti, debug_messages)
    """
    ingredienti_options = []
    debug_messages = []
    
    # 1. Articoli da fatture (prodotti reali)
    articoli, debug_msgs = get_articoli_da_fatture(user_id)
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
    
    # 2. Ingredienti workspace (manuali/test)
    try:
        workspace_response = supabase.table('ingredienti_workspace')\
            .select('*')\
            .eq('userid', user_id)\
            .eq('ristorante_id', ristorante_id)\
            .order('nome')\
            .execute()
        
        for ing in workspace_response.data:
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
        
        debug_messages.append(f"✅ Ingredienti workspace caricati: {len(workspace_response.data)}")
    except Exception as e:
        debug_messages.append(f"⚠️ Errore caricamento ingredienti workspace: {str(e)}")
        logger.warning(f"Errore ingredienti workspace: {e}")
    
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
        if grammatura_conf:
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
    
    st.cache_data.clear()  # Clear cache per refresh dati


# ============================================
# HEADER
# ============================================
st.markdown("""
<h1 style="font-size: 48px; font-weight: 700; margin: 0; margin-bottom: 10px;">
    🍴 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Workspace - Gestione Ricette e Foodcost</span>
</h1>
""", unsafe_allow_html=True)

# ============================================
# TAB NAVIGATION
# ============================================
tab1, tab2, tab_export, tab_diario = st.tabs(["📋 Ricette Salvate", "➕ Nuova Ricetta", "📊 Export Excel", "📓 Diario"])

# ============================================
# TAB 1: RICETTE SALVATE
# ============================================
with tab1:
    st.markdown("### 📋 Le Tue Ricette")
    
    # Banner modalità modifica
    if st.session_state.ricetta_edit_mode:
        st.info(f"✏️ **Modalità modifica attiva** per ricetta: **{st.session_state.ricetta_edit_data['nome']}**. Vai al tab **➕ Nuova Ricetta** per modificarla.")
        if st.button("🔙 Annulla modifica", key="cancel_edit_tab1"):
            clear_edit_mode()
            st.rerun()
    
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
            # Filtro categoria
            col_filtro1, col_filtro2 = st.columns([2, 3])
            with col_filtro1:
                categorie_disponibili = ["TUTTE"] + sorted(set(r['categoria'] for r in response.data))
                filtro_categoria = st.selectbox(
                    "🔍 Filtra per categoria",
                    options=categorie_disponibili,
                    key="filtro_categoria_tab1"
                )
            
            with col_filtro2:
                filtro_nome = st.text_input(
                    "🔍 Cerca per nome",
                    placeholder="Digita nome ricetta...",
                    key="filtro_nome_tab1"
                )
            
            # Applica filtri
            ricette_filtrate = response.data
            if filtro_categoria != "TUTTE":
                ricette_filtrate = [r for r in ricette_filtrate if r['categoria'] == filtro_categoria]
            if filtro_nome:
                ricette_filtrate = [r for r in ricette_filtrate if filtro_nome.lower() in r['nome'].lower()]
            
            st.markdown(f"**{len(ricette_filtrate)}** ricette trovate")
            
            # Header tabella con styling personalizzato
            st.markdown("""
            <style>
            .header-ricette {
                background: linear-gradient(90deg, #1e40af 0%, #3b82f6 100%);
                color: white;
                padding: 12px 10px;
                border-radius: 8px;
                font-weight: 700;
                font-size: 14px;
                margin-bottom: 0px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            </style>
            <div class="header-ricette" style="display: grid; grid-template-columns: 0.5fr 3fr 1.5fr 1fr 1fr 2fr; gap: 10px; align-items: center;">
                <div style="text-align: center;">#</div>
                <div>📋 NOME RICETTA</div>
                <div>🏷️ CATEGORIA</div>
                <div>💰 FOOD COST</div>
                <div>🥄 INGREDIENTI</div>
                <div style="text-align: center;">⚙️ AZIONI</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Tabella ricette
            for idx, ricetta in enumerate(ricette_filtrate):
                # Container con bordo per ogni ricetta
                with st.container(border=True):
                    
                    # Prepara dati per visualizzazione tabella
                    ingredienti = json.loads(ricetta['ingredienti']) if isinstance(ricetta['ingredienti'], str) else ricetta['ingredienti']
                    num_ingredienti = len(ingredienti)
                    
                    categoria_emoji = {
                        'ANTIPASTI': '🥗',
                        'PRIMI': '🍝',
                        'SECONDI': '🥩',
                        'PIZZE': '🍕',
                        'DOLCI': '🍰',
                        'SEMILAVORATI': '🥘'
                    }
                    emoji = categoria_emoji.get(ricetta['categoria'], '📋')
                    
                    # Riga tabella con colonne
                    col_ord, col_nome, col_cat, col_fc, col_ing, col_azioni = st.columns([0.5, 3, 1.5, 1, 1, 2])
                    
                    with col_ord:
                        st.markdown(f"**#{ricetta['ordine_visualizzazione']}**")
                    
                    with col_nome:
                        st.markdown(f"**{emoji} {ricetta['nome']}**")
                    
                    with col_cat:
                        st.caption(ricetta['categoria'])
                    
                    with col_fc:
                        st.markdown(f"**€{ricetta['foodcost_totale']:.2f}**")
                    
                    with col_ing:
                        st.caption(f"{num_ingredienti} ing.")
                    
                    with col_azioni:
                        col_up, col_down, col_edit, col_del = st.columns(4)
                        
                        # Bottone SU
                        with col_up:
                            if idx > 0:
                                if st.button("⬆️", key=f"up_{ricetta['id']}", help="Sposta su"):
                                    try:
                                        prev_ricetta = ricette_filtrate[idx - 1]
                                        supabase.rpc('swap_ricette_order', {
                                            'ricetta_id_1': ricetta['id'],
                                            'ricetta_id_2': prev_ricetta['id']
                                        }).execute()
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore: {e}")
                        
                        # Bottone GIÙ
                        with col_down:
                            if idx < len(ricette_filtrate) - 1:
                                if st.button("⬇️", key=f"down_{ricetta['id']}", help="Sposta giù"):
                                    try:
                                        next_ricetta = ricette_filtrate[idx + 1]
                                        supabase.rpc('swap_ricette_order', {
                                            'ricetta_id_1': ricetta['id'],
                                            'ricetta_id_2': next_ricetta['id']
                                        }).execute()
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore: {e}")
                        
                        # Bottone MODIFICA
                        with col_edit:
                            if st.button("✏️", key=f"edit_{ricetta['id']}", help="Modifica ricetta"):
                                try:
                                    st.session_state.ricetta_edit_mode = True
                                    st.session_state.ricetta_edit_data = ricetta
                                    
                                    # Imposta nome ricetta nel session state per il text_input
                                    st.session_state['nome_ricetta'] = ricetta['nome']
                                    st.session_state['categoria_ricetta'] = ricetta['categoria']
                                    
                                    # Carica ingredienti salvati
                                    ingredienti_raw = json.loads(ricetta['ingredienti']) if isinstance(ricetta['ingredienti'], str) else ricetta['ingredienti']
                                    
                                    # Ricarica dropdown per ottenere riferimenti
                                    ingredienti_disp_reload, _ = get_ingredienti_dropdown(user_id, current_ristorante, ricetta['id'])
                                    
                                    # Converti formato salvato → formato temp
                                    ingredienti_temp = []
                                    for ing_salvato in ingredienti_raw:
                                        ing_match = next((x for x in ingredienti_disp_reload if x['data']['nome'] == ing_salvato['nome']), None)
                                        
                                        # Determina tipo riga basato su is_ricetta
                                        tipo_riga = 'semilavorato' if ing_salvato.get('is_ricetta', False) else 'normale'
                                        
                                        ingredienti_temp.append({
                                            'nome': ing_salvato['nome'],
                                            'quantita': ing_salvato['quantita'],
                                            'um': ing_salvato['um'],
                                            'prezzo_unitario': ing_salvato.get('prezzo_unitario', 0),
                                            'is_ricetta': ing_salvato.get('is_ricetta', False),
                                            'ricetta_id': ing_salvato.get('ricetta_id'),
                                            'ingrediente_ref': ing_match['label'] if ing_match else None,
                                            'grammatura_confezione': None,
                                            'prezzo_override': None,
                                            'tipo_riga': tipo_riga
                                        })
                                    
                                    st.session_state.ingredienti_temp = ingredienti_temp
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore caricamento modifica: {e}")
                                    logger.exception("Errore modifica ricetta")
                        
                        # Bottone ELIMINA
                        with col_del:
                            if st.button("🗑️", key=f"del_{ricetta['id']}", help="Elimina ricetta"):
                                st.session_state[f'confirm_delete_{ricetta["id"]}'] = True
                    
                    # Conferma eliminazione
                    if st.session_state.get(f'confirm_delete_{ricetta["id"]}', False):
                        st.warning(f"⚠️ Confermi eliminazione di **{ricetta['nome']}**?")
                        col_conf1, col_conf2 = st.columns(2)
                        with col_conf1:
                            if st.button("✅ Sì, elimina", key=f"confirm_yes_{ricetta['id']}"):
                                try:
                                    supabase.table('ricette').delete().eq('id', ricetta['id']).execute()
                                    st.success(f"Ricetta eliminata")
                                    st.cache_data.clear()
                                    del st.session_state[f'confirm_delete_{ricetta["id"]}']
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                        with col_conf2:
                            if st.button("❌ Annulla", key=f"confirm_no_{ricetta['id']}"):
                                del st.session_state[f'confirm_delete_{ricetta["id"]}']
                                st.rerun()
                    
                    # Expander ingredienti
                    with st.expander("📝 Dettagli ingredienti"):
                        if ingredienti:
                            df_ing = pd.DataFrame(ingredienti)
                            df_ing['prezzo_totale'] = df_ing['quantita'] * df_ing['prezzo_unitario']
                            st.dataframe(
                                df_ing[['nome', 'quantita', 'um', 'prezzo_unitario', 'prezzo_totale']],
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.caption("Nessun ingrediente")
                    
                    # Expander note
                    with st.expander("📌 Aggiungi nota"):
                        nota_attuale = ricetta.get('note', '') or ''
                        nota_key = f"nota_{ricetta['id']}"
                        
                        # Inizializza session state per questa nota se non esiste
                        if nota_key not in st.session_state:
                            st.session_state[nota_key] = nota_attuale
                        
                        # Text area per la nota
                        nota_nuova = st.text_area(
                            "Scrivi qui le tue annotazioni",
                            value=st.session_state[nota_key],
                            placeholder="Es: Ricetta della nonna, aumentare sale, ottima per eventi...",
                            height=100,
                            key=f"textarea_{ricetta['id']}"
                        )
                        
                        # Aggiorna session state
                        st.session_state[nota_key] = nota_nuova
                        
                        # Bottone salva nota
                        col_save, col_clear = st.columns([1, 1])
                        with col_save:
                            if st.button("💾 Salva nota", key=f"save_nota_{ricetta['id']}", use_container_width=True):
                                try:
                                    supabase.table('ricette').update({
                                        'note': nota_nuova if nota_nuova.strip() else None
                                    }).eq('id', ricetta['id']).execute()
                                    st.success("✅ Nota salvata!")
                                    st.cache_data.clear()
                                    time.sleep(0.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore salvataggio: {e}")
                        
                        with col_clear:
                            if st.button("🗑️ Cancella nota", key=f"clear_nota_{ricetta['id']}", use_container_width=True):
                                try:
                                    supabase.table('ricette').update({
                                        'note': None
                                    }).eq('id', ricetta['id']).execute()
                                    st.session_state[nota_key] = ''
                                    st.success("✅ Nota cancellata!")
                                    st.cache_data.clear()
                                    time.sleep(0.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore cancellazione: {e}")

    
    except Exception as e:
        st.error(f"❌ Errore caricamento ricette: {e}")
        logger.exception("Errore tab ricette salvate")


# ============================================
# TAB 2: NUOVA RICETTA
# ============================================
with tab2:
    st.markdown("### ➕ Crea/Modifica Ricetta")
    
    # Mostra banner se in modalità modifica
    if st.session_state.ricetta_edit_mode and st.session_state.ricetta_edit_data:
        ricetta_edit = st.session_state.ricetta_edit_data
        st.info(f"✏️ **Modalità Modifica**: {ricetta_edit['nome']}")
        if st.button("❌ Annulla Modifica"):
            clear_edit_mode()
            st.rerun()
    
    # Info box guida
    st.info("""
    💡 **Come creare una ricetta:**
    
    1️⃣ Seleziona la **categoria** e inserisci il **nome** della ricetta  
    2️⃣ Aggiungi gli **ingredienti** cercandoli nel menu o creandoli manualmente  
    3️⃣ Puoi creare **semilavorati** (es: Besciamella, Ragù) impostando la categoria **SEMILAVORATI** per riutilizzarli in altre ricette  
    """)
    
    # Form header
    col_cat, col_nome = st.columns([1, 2])
    
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
            except:
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
    
    # Spazio tra form ricetta e sezione ingredienti
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    st.markdown("### 🥄 Ingredienti")
    
    # Info semilavorati
    if categoria_sel == 'SEMILAVORATI':
        st.info("💡 **Semilavorati** possono essere usati come ingredienti in altre ricette (max 2 livelli profondità)")
    
    # Carica opzioni ingredienti
    exclude_id = st.session_state.ricetta_edit_data['id'] if st.session_state.ricetta_edit_mode else None
    ingredienti_disponibili, debug_messages = get_ingredienti_dropdown(user_id, current_ristorante, exclude_id)
    
    # Verifica ingredienti disponibili
    if not ingredienti_disponibili:
        st.warning("⚠️ **Nessun ingrediente disponibile**")
        st.info("💡 **Soluzioni**:\n- Carica fatture nella sezione principale per usare prodotti reali\n- Oppure crea **Ingredienti Manuali** qui sotto per iniziare a testare le ricette")
        
        # Bottone refresh cache
        if st.button("🔄 Forza Refresh Cache"):
            st.cache_data.clear()
            st.rerun()
        
        # NON uso st.stop() per permettere al footer di caricarsi
    
    # Mostra form solo se ci sono ingredienti disponibili
    if ingredienti_disponibili:
        # Limita numero ingredienti (DoS protection)
        if len(st.session_state.ingredienti_temp) >= MAX_INGREDIENTI:
            st.error(f"⚠️ Limite massimo di {MAX_INGREDIENTI} ingredienti raggiunto")
        
        # Guida generale a inizio pagina (con sfondo azzurro chiaro)
        st.markdown("""
        <style>
        /* Colora solo il primo expander (guida) di azzurro chiaro */
        div[data-testid="stExpander"]:first-of-type summary {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%) !important;
            border-radius: 8px !important;
            padding: 12px 16px !important;
            color: #1e40af !important;
            font-weight: 600 !important;
        }
        div[data-testid="stExpander"]:first-of-type {
            margin-bottom: 24px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        with st.expander("ℹ️ Guida: come usare la sezione Ricette", expanded=False):
            st.markdown("""
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
        
        # Expander per creare ingredienti manuali
        with st.expander("📝 Crea Ingrediente Manuale", expanded=False):
            st.caption("💡 **Per ristoranti non ancora aperti o per test**: crea ingredienti personalizzati con prezzi stimati. Questi ingredienti rimangono isolati in questa sezione.")
            
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
                            # Inserisci in DB
                            result = supabase.table('ingredienti_workspace').insert({
                                'userid': user_id,
                                'ristorante_id': current_ristorante,
                                'nome': nuovo_ing_nome.strip(),
                                'prezzo_per_um': nuovo_ing_prezzo,
                                'um': nuovo_ing_um
                            }).execute()
                            
                            st.success(f"✅ Ingrediente '{nuovo_ing_nome}' creato!")
                            
                            # Clear cache e rerun
                            st.cache_data.clear()
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
                    
                    # Header tabella
                    cols_ing = st.columns([3, 2, 1.5, 0.8, 0.8])
                    cols_ing[0].markdown("**Nome**")
                    cols_ing[1].markdown("**Prezzo**")
                    cols_ing[2].markdown("**UM**")
                    cols_ing[3].markdown("**Modifica**")
                    cols_ing[4].markdown("**Elimina**")
                    
                    # Marker per identificare inizio lista scrollabile
                    st.markdown('<div class="workspace-ingredients-list"></div>', unsafe_allow_html=True)
                    
                    # CSS per rendere scrollabile la lista (max 5 righe = ~350px)
                    st.markdown("""
                    <style>
                    /* Scrollable container per ingredienti workspace */
                    .workspace-ingredients-list + div {
                        max-height: 350px;
                        overflow-y: auto;
                        padding-right: 8px;
                        margin-top: 8px;
                    }
                    /* Scrollbar personalizzata */
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
                        # Controlla se questo ingrediente è in modalità modifica
                        is_editing = st.session_state.get(f"edit_ing_{ing['id']}", False)
                        
                        if is_editing:
                            # Modalità modifica: mostra campi editabili
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
                                # Bottone salva modifiche
                                if st.button("💾", key=f"save_ing_{ing['id']}", help="Salva modifiche"):
                                    if not edit_nome or not edit_nome.strip():
                                        st.error("⚠️ Nome obbligatorio")
                                    elif edit_prezzo <= 0:
                                        st.error("⚠️ Prezzo non valido")
                                    else:
                                        try:
                                            supabase.table('ingredienti_workspace')\
                                                .update({
                                                    'nome': edit_nome.strip(),
                                                    'prezzo_per_um': edit_prezzo,
                                                    'um': edit_um
                                                })\
                                                .eq('id', ing['id'])\
                                                .execute()
                                            
                                            st.success("✅ Modifiche salvate")
                                            st.session_state[f"edit_ing_{ing['id']}"] = False
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                                                st.error(f"⚠️ Nome '{edit_nome}' già esistente")
                                            else:
                                                st.error(f"❌ Errore: {str(e)}")
                            
                            with cols[4]:
                                # Bottone annulla
                                if st.button("❌", key=f"cancel_ing_{ing['id']}", help="Annulla"):
                                    st.session_state[f"edit_ing_{ing['id']}"] = False
                                    st.rerun()
                        
                        else:
                            # Modalità visualizzazione normale
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
                                        supabase.table('ingredienti_workspace').delete().eq('id', ing['id']).execute()
                                        st.success("✅ Ingrediente eliminato")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Errore eliminazione: {str(e)}")
            except Exception as e:
                st.warning(f"⚠️ Impossibile caricare ingredienti workspace: {str(e)}")
        
        # Spazio tra expander e header
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Header tabella SEMPRE visibile con sfondo colorato
        st.markdown("""
        <div style="display: flex; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; padding: 10px 8px; border-radius: 8px; font-weight: 600; 
                    font-size: 13px; margin-bottom: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);">
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
        /* Forza testo a sinistra su TUTTI i bottoni secondary full-width */
        button[kind="secondary"] {
            text-align: left !important;
            display: flex !important;
            justify-content: flex-start !important;
            align-items: center !important;
        }
        button[kind="secondary"] > div {
            text-align: left !important;
            justify-content: flex-start !important;
            display: flex !important;
            width: 100% !important;
        }
        button[kind="secondary"] > div > p,
        button[kind="secondary"] p {
            text-align: left !important;
            width: 100% !important;
        }
        /* Anche BaseButton-secondary */
        .stButton button {
            justify-content: flex-start !important;
        }
        .stButton button div {
            justify-content: flex-start !important;
        }
        .stButton button div p {
            text-align: left !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        if st.button("➕ Aggiungi Ingrediente / Semilavorato / Creato Manualmente", 
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
                col1, col2, col3, col4, col5, col6, col7 = st.columns([2.5, 1.2, 1, 0.6, 1, 1.2, 0.5])
                
                with col1:
                    # Mostra tutti gli ingredienti disponibili (articoli, workspace, ricette/semilavorati)
                    ingredienti_filtrati = ingredienti_disponibili
                    
                    # Trova indice default se modifica
                    default_idx = 0
                    if ing.get('ingrediente_ref'):
                        try:
                            default_idx = [i for i, x in enumerate(ingredienti_filtrati) if x['label'] == ing['ingrediente_ref']][0]
                        except:
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
                    except:
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
                        
                        ing['prezzo_unitario'] = prezzo_riga / ing['quantita']
                        st.markdown(f"<div style='background: #e0f2fe; "
                                    f"color: #0369a1; padding: 8px; border-radius: 6px; text-align: center; "
                                    f"font-weight: 600; font-size: 15px; border: 1px solid #bae6fd;'>€{prezzo_riga:.2f}</div>", 
                                    unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='background: #f1f5f9; color: #94a3b8; padding: 8px; "
                                    "border-radius: 6px; text-align: center; border: 1px solid #e2e8f0;'>€0.00</div>", unsafe_allow_html=True)
                
                with col7:
                    # Conferma eliminazione per righe costose (considera prezzo override)
                    if ing_data:
                        grammatura_per_calcolo = ing.get('grammatura_confezione')
                        prezzo_override = ing.get('prezzo_override')
                        
                        # Calcola con override se presente
                        if prezzo_override is not None and ing_data['tipo'] in ['articolo', 'workspace']:
                            ing_data_temp = ing_data.copy()
                            ing_data_temp['data'] = ing_data['data'].copy()
                            ing_data_temp['data']['prezzo_unitario'] = prezzo_override
                            prezzo_riga_calc = calcola_foodcost_riga(ing_data_temp, ing['quantita'], ing['um'], grammatura_per_calcolo)
                        else:
                            prezzo_riga_calc = calcola_foodcost_riga(ing_data, ing['quantita'], ing['um'], grammatura_per_calcolo)
                    else:
                        prezzo_riga_calc = 0
                    
                    if prezzo_riga_calc > 5:
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
            
            # TOTALE FOOD COST - Allineato alla colonna costo
            totale_foodcost = 0
            for ing in st.session_state.ingredienti_temp:
                if ing.get('ingrediente_ref'):
                    ing_data = next((x for x in ingredienti_disponibili if x['label'] == ing['ingrediente_ref']), None)
                    if ing_data:
                        grammatura_per_calcolo = ing.get('grammatura_confezione')
                        prezzo_override = ing.get('prezzo_override')
                        
                        # Usa prezzo override se presente
                        if prezzo_override is not None and ing_data['tipo'] == 'articolo':
                            ing_data_modified = ing_data.copy()
                            ing_data_modified['data'] = ing_data['data'].copy()
                            ing_data_modified['data']['prezzo_unitario'] = prezzo_override
                            totale_foodcost += calcola_foodcost_riga(ing_data_modified, ing['quantita'], ing['um'], grammatura_per_calcolo)
                        else:
                            totale_foodcost += calcola_foodcost_riga(ing_data, ing['quantita'], ing['um'], grammatura_per_calcolo)
            
            # Colonne vuote per allineamento + totale nella colonna 6
            col_t1, col_t2, col_t3, col_t4, col_t5, col_t6, col_t7 = st.columns([2.5, 1.2, 1, 0.6, 1, 1.2, 0.5])
            with col_t6:
                st.markdown(f"""
                <div style="background: #e0f2fe; 
                            color: #0369a1; 
                            padding: 12px; 
                            border-radius: 8px; 
                            text-align: center;
                            border: 2px solid #0ea5e9;
                            box-shadow: 0 2px 8px rgba(14, 165, 233, 0.15);
                            margin-top: 10px;">
                    <div style="font-size: 11px; font-weight: 600; opacity: 0.8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">
                        👨‍🍳 Totale
                    </div>
                    <div style="font-size: 20px; font-weight: 700;">
                        €{totale_foodcost:.2f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
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
                                            if prezzo_override is not None and ing_data['tipo'] == 'articolo':
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
                                                'prezzo_unitario': prezzo_riga / ing['quantita'],  # Normalizzato
                                                'is_ricetta': ing['is_ricetta'],
                                                'ricetta_id': ing.get('ricetta_id')
                                            })
                                    
                                    # Prepara dati per insert/update
                                    ricetta_data = {
                                        'userid': user_id,
                                        'nome': nome_ricetta.strip(),
                                        'categoria': categoria_sel,
                                        'ingredienti': json.dumps(ingredienti_json),
                                        'foodcost_totale': round(foodcost_totale, 2)
                                    }
                                    
                                    # Aggiungi ristorante_id solo se disponibile
                                    if current_ristorante:
                                        ricetta_data['ristorante_id'] = current_ristorante
                                    
                                    if st.session_state.ricetta_edit_mode:
                                        # UPDATE
                                        ricetta_id = st.session_state.ricetta_edit_data['id']
                                        response = supabase.table('ricette')\
                                            .update(ricetta_data)\
                                            .eq('id', ricetta_id)\
                                            .execute()
                                        
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
                                            except:
                                                next_ordine = 1
                                        
                                        ricetta_data['ordine_visualizzazione'] = next_ordine
                                        
                                        response = supabase.table('ricette')\
                                            .insert(ricetta_data)\
                                            .execute()
                                        
                                        st.success(f"✅ Ricetta **{nome_ricetta}** salvata! Food cost: €{foodcost_totale:.2f}")
                                    
                                    # Clear form e cache
                                    clear_edit_mode()
                                    st.cache_data.clear()
                                    
                                    # Redirect a tab 1
                                    time.sleep(1.5)
                                    st.session_state.active_tab = 0
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
# TAB 3: EXPORT EXCEL
# ============================================
with tab_export:
    st.markdown("### 📊 Export Ricette in Excel")
    
    st.info("""
    **📥 Scarica tutte le ricette**
    
    Il file Excel conterrà:
    - 📋 Elenco ricette con food cost
    - 🥄 Dettagli ingredienti per ogni ricetta
    - 💰 Analisi costi per categoria
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
            st.success(f"✅ Pronte {num_ricette} ricette per l'export")
            
            # Bottone export
            if st.button("📥 Scarica Excel", type="primary", use_container_width=True):
                try:
                    # Prepara DataFrame principale
                    ricette_export = []
                    ingredienti_export = []
                    
                    for ricetta in response.data:
                        ricette_export.append({
                            'Nome': ricetta['nome'],
                            'Categoria': ricetta['categoria'],
                            'Food Cost (€)': float(ricetta['foodcost_totale']),
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
                    
                    # Analisi per categoria
                    df_categorie = df_ricette.groupby('Categoria').agg({
                        'Nome': 'count',
                        'Food Cost (€)': ['sum', 'mean', 'min', 'max']
                    }).round(2)
                    df_categorie.columns = ['Num. Ricette', 'Food Cost Totale', 'Food Cost Medio', 'Min', 'Max']
                    df_categorie = df_categorie.reset_index()
                    
                    # Crea Excel in memoria
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_ricette.to_excel(writer, sheet_name='Ricette', index=False)
                        df_ingredienti.to_excel(writer, sheet_name='Ingredienti Dettaglio', index=False)
                        df_categorie.to_excel(writer, sheet_name='Analisi Categorie', index=False)
                        
                        # Formattazione
                        workbook = writer.book
                        money_fmt = workbook.add_format({'num_format': '€#,##0.00'})
                        header_fmt = workbook.add_format({
                            'bold': True,
                            'bg_color': '#4472C4',
                            'font_color': 'white'
                        })
                        
                        # Applica formattazione ricette
                        worksheet_ricette = writer.sheets['Ricette']
                        worksheet_ricette.set_column('C:C', 12, money_fmt)
                        
                        # Applica formattazione ingredienti
                        worksheet_ing = writer.sheets['Ingredienti Dettaglio']
                        worksheet_ing.set_column('F:G', 14, money_fmt)
                    
                    output.seek(0)
                    
                    # Download button
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"ricette_export_{timestamp}.xlsx"
                    
                    st.download_button(
                        label="💾 Scarica File Excel",
                        data=output.getvalue(),
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
                    st.success(f"✅ File **{filename}** pronto per il download!")
                
                except Exception as e:
                    st.error(f"❌ Errore generazione Excel: {e}")
                    logger.exception("Errore export Excel")
    
    except Exception as e:
        st.error(f"❌ Errore caricamento dati: {e}")
        logger.exception("Errore tab export")


# ============================================
# TAB 4: DIARIO
# ============================================
with tab_diario:
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
                        supabase.table('note_diario').insert({
                            'userid': user_id,
                            'ristorante_id': current_ristorante,
                            'testo': nuova_nota_testo.strip()
                        }).execute()
                        
                        st.success("✅ Nota salvata!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Errore salvataggio: {str(e)}")
                        logger.exception("Errore salvataggio nota diario")
    
    # Carica note esistenti in ordine cronologico
    try:
        note_response = supabase.table('note_diario')\
            .select('*')\
            .eq('userid', user_id)\
            .eq('ristorante_id', current_ristorante)\
            .order('created_at', desc=True)\
            .execute()
        
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
                                            padding: 15px; 
                                            border-radius: 8px; 
                                            box-shadow: 3px 3px 8px rgba(0,0,0,0.15);
                                            min-height: 250px;
                                            margin-bottom: 15px;
                                            border: 1px solid {colore_text}20;'>
                                    <div style='color: {colore_text}; opacity: 0.7; font-size: 11px; margin-bottom: 10px;'>
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
                                                supabase.table('note_diario')\
                                                    .update({'testo': edit_testo.strip()})\
                                                    .eq('id', nota['id'])\
                                                    .execute()
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
                                            padding: 15px; 
                                            border-radius: 8px; 
                                            box-shadow: 3px 3px 8px rgba(0,0,0,0.15);
                                            min-height: 200px;
                                            margin-bottom: 15px;
                                            position: relative;
                                            border: 1px solid {colore_text}20;
                                            cursor: pointer;'>
                                    <div style='color: {colore_text}; opacity: 0.7; font-size: 11px; margin-bottom: 10px;'>
                                        📅 {data_str} {'✏️' if modificata else ''}
                                    </div>
                                    <div style='color: {colore_text}; 
                                                font-size: 14px; 
                                                line-height: 1.5;
                                                white-space: pre-wrap;
                                                word-wrap: break-word;
                                                max-height: 140px;
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
                                            supabase.table('note_diario').delete().eq('id', nota['id']).execute()
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
