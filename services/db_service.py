"""
Servizio di gestione database - Query, analisi e preparazione dati

Funzioni:
- carica_e_prepara_dataframe: Caricamento fatture da Supabase con cache
- ricalcola_prezzi_con_sconti: Fix retroattivo prezzi con sconti
- calcola_alert: Calcolo alert aumenti prezzi prodotti
- carica_sconti_e_omaggi: Estrazione sconti e omaggi periodo

Pattern: Dependency Injection per Supabase client
"""

import logging
import re
import time
from typing import Dict, Any, List
import pandas as pd
import streamlit as st

# Import config
from config.constants import CATEGORIE_SPESE_GENERALI, LEGACY_CATEGORY_ALIASES

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('db')

RETENTION_JOB_NAME = "fatture_retention_2y"
RETENTION_BATCH_SIZE = 500


def _normalize_custom_tag_key(text: str) -> str:
    """Normalizza una descrizione libera in chiave stabile lato Python."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip().upper())


@st.cache_data(ttl=120, show_spinner=False)
def _carica_fatture_da_supabase(user_id: str, ristorante_id=None):
    """
    Funzione interna cached: carica fatture da Supabase.
    Parametri hashable per @st.cache_data.
    """
    # [DEBUG]
    logger.debug(f"[CACHE MISS] Query reale DB — user_id={user_id} ristorante_id={ristorante_id} ts={time.time():.3f}")
    from services import get_supabase_client
    supabase_client = get_supabase_client()
    
    if supabase_client is None:
        logger.critical("❌ CRITICAL: Supabase client non inizializzato!")
        return pd.DataFrame()
    
    logger.info(f"📊 LOAD START (cached): user_id={user_id}, ristorante_id={ristorante_id}")
    
    dati = []
    try:
        # Prima query per ottenere il count totale (usa head per performance)
        query_count = supabase_client.table("fatture").select("id", count="exact", head=True).eq("user_id", user_id).is_("deleted_at", "null")
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        response_count = query_count.execute()
        total_rows = response_count.count if response_count.count else 0
        logger.info(f"📊 CARICAMENTO: user_id={user_id} ristorante_id={ristorante_id} ha {total_rows} righe su Supabase")
        
        # Paginazione per caricare tutte le righe
        page_size = 1000
        page = 0
        max_pages = 200  # Safety guard: max 200k righe
        
        # 🚀 OTTIMIZZAZIONE: Select solo colonne necessarie (non "*")
        columns = "file_origine,numero_riga,data_documento,fornitore,descrizione,quantita,unita_misura,prezzo_unitario,iva_percentuale,totale_riga,categoria,codice_articolo,prezzo_standard,ristorante_id,needs_review,tipo_documento,sconto_percentuale,created_at"
        
        while page < max_pages:
            offset = page * page_size
            query_select = supabase_client.table("fatture").select(columns).eq("user_id", user_id).is_("deleted_at", "null")
            if ristorante_id:
                query_select = query_select.eq("ristorante_id", ristorante_id)
            response = query_select.range(offset, offset + page_size - 1).execute()
            
            if not response.data:
                break
            
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
                    "PrezzoStandard": row.get("prezzo_standard"),
                    "NeedsReview": row.get("needs_review", False),
                    "RistoranteId": row.get("ristorante_id"),
                    "TipoDocumento": row.get("tipo_documento", "TD01"),
                    "ScontoPercentuale": row.get("sconto_percentuale", 0.0),
                    "CreatedAt": row.get("created_at", "")
                })
            
            # Se questa pagina ha meno di page_size record, abbiamo finito
            if len(response.data) < page_size:
                break
                
            page += 1
        
        # [DEBUG]
        logger.debug(f"[CACHE MISS] Risultato: {len(dati)} righe restituite")
        if len(dati) > 0:
            logger.info(f"✅ LOAD SUCCESS: {len(dati)} righe caricate da Supabase per user_id={user_id}")
            return pd.DataFrame(dati)
        else:
            logger.info(f"ℹ️ LOAD EMPTY: Nessuna fattura per user_id={user_id}")
            return pd.DataFrame()
            
    except (ConnectionError, TimeoutError) as e:
        logger.error(f"❌ LOAD ERROR: Connessione Supabase fallita per user_id={user_id}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"❌ LOAD ERROR: Errore Supabase per user_id={user_id}: {type(e).__name__}: {e}")
        logger.exception("Errore query Supabase")
        return pd.DataFrame()


def carica_e_prepara_dataframe(user_id: str, force_refresh: bool = False, supabase_client=None, ristorante_id=None):
    """
    🔥 SINGLE SOURCE OF TRUTH: Carica fatture SOLO da Supabase
    
    Args:
        user_id: ID utente per filtro multi-tenancy
        force_refresh: Se True, bypassa cache (usato dopo delete)
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
    
    Returns:
        DataFrame con fatture dell'utente o DataFrame vuoto
    
    GARANZIE:
    - Legge SOLO da tabella 'fatture' su Supabase
    - Filtra per user_id (isolamento utenti)
    - Nessun fallback JSON o altre fonti
    - Cache invalidata SOLO con clear() esplicito
    """
    # 🔥 FORCE EMPTY: Se c'è flag force_empty, ritorna DataFrame vuoto senza query
    # Questo previene che dati cached riappaiano dopo eliminazione massiva
    try:
        if hasattr(st, 'session_state') and st.session_state.get('force_empty_until_upload', False):
            logger.info(f"🚫 FORCE EMPTY attivo: ritorno DataFrame vuoto per user_id={user_id}")
            return pd.DataFrame()
    except Exception as e:
        logger.warning(f"⚠️ Impossibile controllare force_empty flag: {e}")
    
    # Se force_refresh, invalida cache prima di ricaricare
    if force_refresh:
        _carica_fatture_da_supabase.clear()
        get_fatture_stats.clear()
        logger.info("🔄 Cache invalidata per force_refresh")
    
    # 🚀 CACHED: Carica dati da Supabase (cached per 120s)
    df_result = _carica_fatture_da_supabase(user_id, ristorante_id)
    
    if df_result.empty:
        return pd.DataFrame()
    
    # Normalizzazione categorie (veloce, in-memory)
    df_result = df_result.copy()  # Non modificare il cached DataFrame
    
    if 'Categoria' in df_result.columns:
        df_result['Categoria'] = df_result['Categoria'].replace(
            to_replace=[None, '', 'None', 'null', 'NULL', ' '], 
            value=pd.NA
        )
        # Converti spazi bianchi in NaN
        df_result.loc[df_result['Categoria'].astype(str).str.strip() == '', 'Categoria'] = pd.NA
        df_result['Categoria'] = df_result['Categoria'].apply(lambda v: v.strip() if isinstance(v, str) else v)
        
        # 🔄 MIGRAZIONE AUTOMATICA: Aggiorna vecchi nomi categorie
        mapping_categorie = {
            'SALSE': 'SALSE E CREME',
            'BIBITE E BEVANDE': 'BEVANDE',
            'PANE': 'PRODOTTI DA FORNO',
            'DOLCI': 'PASTICCERIA',
            'OLIO': 'OLIO E CONDIMENTI',
            'CONSERVE': 'SCATOLAME E CONSERVE',
            'CAFFÈ': 'CAFFE E THE',
            **LEGACY_CATEGORY_ALIASES,
        }
        
        righe_migrate = 0
        for vecchio, nuovo in mapping_categorie.items():
            mask = df_result['Categoria'] == vecchio
            if mask.any():
                df_result.loc[mask, 'Categoria'] = nuovo
                righe_migrate += mask.sum()
        
        if righe_migrate > 0:
            logger.info(f"✅ MIGRAZIONE: {righe_migrate} righe aggiornate")
        
        # 🎯 FIX CELLE BIANCHE DEFINITIVO
        null_count_before = df_result['Categoria'].isna().sum()
        logger.debug(f"🔍 PRE-NORMALIZZAZIONE: {null_count_before} valori NA")
        
        df_result['Categoria'] = df_result['Categoria'].fillna("Da Classificare")
        
        df_result['Categoria'] = df_result['Categoria'].replace(
            to_replace=[None, '', 'None', 'null', 'NULL', ' ', '  ', '   ', '    '],
            value='Da Classificare'
        )
        
        mask_empty = df_result['Categoria'].astype(str).str.strip() == ''
        if mask_empty.any():
            df_result.loc[mask_empty, 'Categoria'] = 'Da Classificare'
            logger.debug(f"🔧 Convertiti {mask_empty.sum()} valori con solo spazi in Da Classificare")
        
        da_class_count = (df_result['Categoria'] == 'Da Classificare').sum()
        logger.info(f"✅ CELLE BIANCHE RISOLTE: {da_class_count} celle mostrano 'Da Classificare'")
    
    return df_result


# DEPRECATED: prezzi calcolati direttamente in invoice_service.py
# Mantenuta per compatibilità, non chiamare.
def ricalcola_prezzi_con_sconti(user_id: str, supabase_client=None) -> int:
    """
    Ricalcola prezzi unitari per fatture già caricate (fix retroattivo sconti).
    
    Questa funzione serve per correggere i prezzi delle fatture caricate PRIMA
    del fix che calcola il prezzo effettivo da PrezzoTotale ÷ Quantità.
    
    Args:
        user_id: ID utente per filtro
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
    
    Returns:
        int: Numero di righe aggiornate
    """
    logger.warning("DEPRECATED: ricalcola_prezzi_con_sconti non dovrebbe essere chiamata. I prezzi vengono calcolati in invoice_service.py.")
    # Inizializza client Supabase (singleton)
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return 0
    
    try:
        # Leggi tutte le fatture dell'utente (con paginazione per >1000 righe)
        from utils.ristorante_helper import get_current_ristorante_id
        ristorante_id = get_current_ristorante_id()
        
        all_rows = []
        page = 0
        page_size = 1000
        max_pages = 200
        
        while page < max_pages:
            offset = page * page_size
            query = supabase_client.table("fatture") \
                .select("id, descrizione, quantita, prezzo_unitario, totale_riga") \
                .eq("user_id", user_id)
            if ristorante_id:
                query = query.eq("ristorante_id", ristorante_id)
            response = query.range(offset, offset + page_size - 1).execute()
            
            if not response.data:
                break
            
            all_rows.extend(response.data)
            
            if len(response.data) < page_size:
                break
            page += 1
        
        if not all_rows:
            return 0
        
        # Calcola tutti i prezzi da aggiornare PRIMA, poi batch update
        updates_needed = []
        
        for row in all_rows:
            totale = row.get('totale_riga', 0)
            quantita = row.get('quantita', 0)
            prezzo_attuale = row.get('prezzo_unitario', 0)
            
            if quantita > 0 and totale > 0:
                # Ricalcola prezzo effettivo
                prezzo_effettivo = round(totale / quantita, 4)
                
                # Solo se diverso (c'era uno sconto)
                if abs(prezzo_effettivo - prezzo_attuale) > 0.01:
                    updates_needed.append({
                        'id': row['id'],
                        'prezzo_effettivo': prezzo_effettivo,
                        'descrizione': row.get('descrizione', ''),
                        'prezzo_attuale': prezzo_attuale
                    })
        
        if not updates_needed:
            return 0
        
        # Batch update: raggruppa per prezzo_effettivo per fare meno query
        from collections import defaultdict
        prezzo_groups = defaultdict(list)
        for u in updates_needed:
            prezzo_groups[u['prezzo_effettivo']].append(u['id'])
        
        righe_aggiornate = 0
        for prezzo_effettivo, ids in prezzo_groups.items():
            # Aggiorna batch di IDs con stesso prezzo in una sola query
            for batch_start in range(0, len(ids), 50):  # Batch da 50
                batch_ids = ids[batch_start:batch_start + 50]
                supabase_client.table("fatture").update({
                    'prezzo_unitario': prezzo_effettivo
                }).in_('id', batch_ids).execute()
                righe_aggiornate += len(batch_ids)
        
        logger.info(f"🔄 Batch update prezzi: {righe_aggiornate} righe aggiornate in {len(prezzo_groups)} gruppi")
        
        return righe_aggiornate
    
    except Exception as e:
        logger.error(f"Errore ricalcolo prezzi: {e}")
        return 0


def calcola_alert(df: pd.DataFrame, soglia_minima: float, filtro_prodotto: str = "") -> pd.DataFrame:
    """
    Calcola alert aumenti prezzi confrontando il PREZZO UNITARIO EFFETTIVO
    (con sconti applicati) tra acquisti successivi dello stesso prodotto.

    IMPORTANTE: Escludi tutte le categorie di Spese Generali definite in constants.py.
    MATERIALE DI CONSUMO rientra ora in Spese Generali.

    Logica:
    - Confronta Prezzo Unit. Effettivo (€/PZ, €/Kg, etc.)
    - Indipendente da quantità acquistata
    - Rileva anche ribassi (valore negativo)
    - Espone trend sintetico e impatto economico stimato per il mese

    Args:
        df: DataFrame con colonne Descrizione, Fornitore, DataDocumento, PrezzoUnitario, Categoria
        soglia_minima: Percentuale minima per alert (es. 5.0 = 5%)
        filtro_prodotto: Stringa per filtrare prodotti (opzionale)

    Returns:
        DataFrame con alert ordinati per aumento decrescente
    """
    _ALERT_COLUMNS = [
        'Prodotto', 'Categoria', 'Fornitore', 'Storico', 'Media',
        'Ultimo', 'Aumento_Perc', 'Data', 'N_Fattura',
        'Trend', 'Impatto_Stimato', 'Delta_Euro'
    ]
    if df.empty:
        return pd.DataFrame(columns=_ALERT_COLUMNS)

    # Verifica colonne necessarie
    required_cols = ['Descrizione', 'Fornitore', 'DataDocumento', 'PrezzoUnitario', 'Categoria', 'FileOrigine']
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame(columns=_ALERT_COLUMNS)

    # ============================================================
    # FILTRO: ESCLUDI SOLO LE CATEGORIE SPESE GENERALI
    # ============================================================
    df_fb = df[~df['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()

    if df_fb.empty:
        return pd.DataFrame(columns=_ALERT_COLUMNS)

    # ============================================================
    # FILTRO 2: SEARCH PRODOTTO (se specificato)
    # ============================================================
    if filtro_prodotto:
        df_fb = df_fb[df_fb['Descrizione'].str.contains(filtro_prodotto, case=False, na=False, regex=False)]

    df = df_fb  # Usa solo prodotti F&B

    if df.empty:
        return pd.DataFrame(columns=_ALERT_COLUMNS)

    alert_list = []

    # Normalizza chiavi groupby (case-insensitive, strip spazi)
    df = df.copy()
    df['_desc_key'] = df['Descrizione'].astype(str).str.strip().str.upper()
    df['_forn_key'] = df['Fornitore'].astype(str).str.strip().str.upper()

    # Raggruppa per Descrizione + Fornitore (case-insensitive)
    for (_dk, _fk), group in df.groupby(['_desc_key', '_forn_key']):
        prodotto = group['Descrizione'].mode()[0]
        fornitore = group['Fornitore'].mode()[0]
        group = group.sort_values('DataDocumento')

        acquisti_validi = group[group['PrezzoUnitario'] > 0].copy()

        if len(acquisti_validi) < 2:
            continue

        ultimo = acquisti_validi.iloc[-1]
        penultimo = acquisti_validi.iloc[-2]

        prezzo_ultimo = float(ultimo['PrezzoUnitario'])
        prezzo_penultimo = float(penultimo['PrezzoUnitario'])
        delta_euro = prezzo_ultimo - prezzo_penultimo

        nota_stagionale = ""
        try:
            data_penultimo = pd.to_datetime(penultimo['DataDocumento'], utc=True)
            data_ultimo = pd.to_datetime(ultimo['DataDocumento'], utc=True)
            giorni_diff = (data_ultimo - data_penultimo).days

            if giorni_diff > 180:
                nota_stagionale = " ⚠️ >6m"
        except (ValueError, TypeError):
            pass

        variazione_perc = ((prezzo_ultimo - prezzo_penultimo) / prezzo_penultimo) * 100

        if abs(variazione_perc) >= soglia_minima:
            file_origine = str(ultimo.get('FileOrigine', ''))
            n_acquisti = len(acquisti_validi)

            if n_acquisti >= 2:
                ultimi_cinque = acquisti_validi.tail(5)
                prezzi_storici = [f"€{p:.2f}" for p in ultimi_cinque['PrezzoUnitario'].tolist()]
                storico_str = " → ".join(prezzi_storici)
                media_storico = float(ultimi_cinque['PrezzoUnitario'].mean())
            else:
                storico_str = "-"
                media_storico = prezzo_penultimo

            # Trend sintetico sulle ultime variazioni
            prezzi_recenti = pd.to_numeric(acquisti_validi['PrezzoUnitario'].tail(4), errors='coerce').dropna().tolist()
            variazioni_recenti = [
                prezzi_recenti[i] - prezzi_recenti[i - 1]
                for i in range(1, len(prezzi_recenti))
                if abs(prezzi_recenti[i] - prezzi_recenti[i - 1]) > 0.0001
            ]
            if len(variazioni_recenti) >= 3 and all(v > 0 for v in variazioni_recenti[-3:]):
                trend = '⬆️⬆️'
            elif len(variazioni_recenti) >= 3 and all(v < 0 for v in variazioni_recenti[-3:]):
                trend = '⬇️⬇️'
            elif any(v > 0 for v in variazioni_recenti) and any(v < 0 for v in variazioni_recenti):
                trend = '↕️'
            elif delta_euro > 0:
                trend = '⬆️'
            elif delta_euro < 0:
                trend = '⬇️'
            else:
                trend = '↕️'

            # Impatto economico stimato: delta ultimo vs penultimo × q.tà media recente × frequenza acquisto stimata
            if 'Quantita' in acquisti_validi.columns:
                quantita_recenti = pd.to_numeric(acquisti_validi['Quantita'].tail(3), errors='coerce').dropna()
            else:
                quantita_recenti = pd.Series(dtype=float)
            quantita_riferimento = float(quantita_recenti.mean()) if not quantita_recenti.empty else 1.0

            date_recenti = pd.to_datetime(acquisti_validi['DataDocumento'].tail(4), errors='coerce').dropna().sort_values()
            frequenza_mensile = 1.0
            if len(date_recenti) >= 2:
                intervalli = date_recenti.diff().dt.days.dropna()
                intervalli = intervalli[intervalli > 0]
                if not intervalli.empty:
                    frequenza_mensile = max(1.0, min(6.0, 30.0 / float(intervalli.mean())))

            impatto_stimato = float(delta_euro * quantita_riferimento * frequenza_mensile)

            alert_list.append({
                'Prodotto': (prodotto + nota_stagionale)[:50],
                'Categoria': str(ultimo['Categoria'])[:15],
                'Fornitore': str(fornitore)[:20],
                'Storico': storico_str,
                'Media': media_storico,
                'Ultimo': prezzo_ultimo,
                'Aumento_Perc': variazione_perc,
                'Data': ultimo['DataDocumento'],
                'N_Fattura': file_origine,
                'Trend': trend,
                'Impatto_Stimato': impatto_stimato,
                'Delta_Euro': delta_euro,
            })

    if not alert_list:
        return pd.DataFrame(columns=_ALERT_COLUMNS)

    df_alert = pd.DataFrame(alert_list)
    df_alert = df_alert.sort_values('Aumento_Perc', ascending=False).reset_index(drop=True)

    return df_alert


def carica_sconti_e_omaggi(user_id: str, data_inizio, data_fine, ristorante_id: str = None, supabase_client=None) -> Dict[str, Any]:
    """
    Carica sconti e omaggi ricevuti dal cliente nel periodo specificato.
    
    IMPORTANTE: Usa stesso periodo dei grafici (non fisso 30gg).
    
    Args:
        user_id: UUID cliente
        data_inizio: Data inizio periodo (datetime.date o string ISO)
        data_fine: Data fine periodo (datetime.date o string ISO)
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
        
    Returns:
        dict con:
        - sconti: DataFrame (prezzi negativi)
        - omaggi: DataFrame (prezzi €0)
        - totale_risparmiato: float
    """
    # Inizializza client Supabase
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return {
                'sconti': pd.DataFrame(),
                'omaggi': pd.DataFrame(),
                'totale_risparmiato': 0.0
            }
    
    try:
        from datetime import datetime
        
        # Converti date a string ISO se necessario
        if hasattr(data_inizio, 'isoformat'):
            data_inizio = data_inizio.isoformat()
        if hasattr(data_fine, 'isoformat'):
            data_fine = data_fine.isoformat()
        
        # 🏢 MULTI-RISTORANTE: ristorante_id passato come parametro (non da session_state)
        if not ristorante_id:
            logger.warning("ristorante_id mancante in carica_sconti_e_omaggi - operazione annullata")
            return {'sconti': pd.DataFrame(), 'omaggi': pd.DataFrame(), 'totale_risparmiato': 0.0}
        
        # Query righe del cliente NEL PERIODO SPECIFICATO (con paginazione per >1000 righe)
        all_rows = []
        page = 0
        page_size = 1000
        max_pages = 200
        
        while page < max_pages:
            offset = page * page_size
            # Usa .lte (<=) per includere le fatture del giorno finale del periodo.
            query = supabase_client.table('fatture')\
                .select('id, descrizione, categoria, fornitore, prezzo_unitario, quantita, totale_riga, data_documento, file_origine')\
                .eq('user_id', user_id)\
                .gte('data_documento', data_inizio)\
                .lte('data_documento', data_fine)
            
            # 🔒 FILTRO MULTI-RISTORANTE: Include solo fatture del ristorante attivo
            if ristorante_id:
                query = query.eq('ristorante_id', ristorante_id)
            
            response = query.range(offset, offset + page_size - 1).execute()
            
            if not response.data:
                break
            
            all_rows.extend(response.data)
            
            if len(response.data) < page_size:
                break
            page += 1
        
        if not all_rows:
            return {
                'sconti': pd.DataFrame(),
                'omaggi': pd.DataFrame(),
                'totale_risparmiato': 0.0
            }
        
        df = pd.DataFrame(all_rows)
        
        # ============================================================
        # FILTRO: ESCLUDI SOLO LE CATEGORIE SPESE GENERALI definite in constants.py
        # ============================================================
        df_food = df[~df['categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
        
        # 🔒 FILTRO AGGIUNTIVO: Escludi anche fornitori SEMPRE spese generali (utenze, tech)
        # Previene leak di utenze con categoria NULL o non mappata
        from config.constants import FORNITORI_SPESE_GENERALI_KEYWORDS
        
        # Crea pattern regex per escludere tutti i fornitori in una sola passata
        pattern = '|'.join(re.escape(k) for k in FORNITORI_SPESE_GENERALI_KEYWORDS)
        df_food = df_food[~df_food['fornitore'].str.contains(pattern, case=False, na=False, regex=True)].copy()
        
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
        # OMAGGI: Prezzi €0 (INCLUDE descrizioni con parole omaggio/gratis)
        # ============================================================
        df_omaggi = df_food[
            (df_food['prezzo_unitario'] == 0) &
            (df_food['descrizione'].str.strip().str.len() > 3)  # Escludi righe senza descrizione significativa
        ].copy()
        
        if not df_omaggi.empty:
            # Ordina per data
            df_omaggi = df_omaggi.sort_values('data_documento', ascending=False)
        
        # ============================================================
        # CALCOLO TOTALE RISPARMIATO + ULTIMO PREZZO OMAGGI
        # ============================================================
        totale_sconti = df_sconti['importo_sconto'].sum() if not df_sconti.empty else 0.0
        
        totale_omaggi = 0.0
        if not df_omaggi.empty:
            # Recupera tutto lo storico prezzi positivo del ristorante per stimare il valore degli omaggi
            all_historical = []
            try:
                hist_query = supabase_client.table('fatture')\
                    .select('descrizione, fornitore, prezzo_unitario, data_documento')\
                    .eq('user_id', user_id)\
                    .gt('prezzo_unitario', 0)

                if ristorante_id:
                    hist_query = hist_query.eq('ristorante_id', ristorante_id)

                _hist_page = 0
                while True:
                    _hr = hist_query.order('data_documento', desc=True)\
                                    .range(_hist_page * 1000, (_hist_page + 1) * 1000 - 1)\
                                    .execute()
                    if not _hr.data:
                        break
                    all_historical.extend(_hr.data)
                    if len(_hr.data) < 1000:
                        break
                    _hist_page += 1
            except Exception as e:
                logger.warning(f"Errore query storico omaggi: {e}")

            df_hist = pd.DataFrame(all_historical) if all_historical else pd.DataFrame()

            # Normalizza dati per matching robusto
            df_omaggi = df_omaggi.reset_index(drop=True)
            df_omaggi['data_documento'] = pd.to_datetime(df_omaggi['data_documento'], errors='coerce')
            df_omaggi['quantita'] = pd.to_numeric(df_omaggi['quantita'], errors='coerce').fillna(1.0)
            df_omaggi['ultimo_prezzo'] = pd.NA

            def _norm_key(value):
                return re.sub(r'\s+', ' ', str(value).strip().upper()) if pd.notna(value) else ''

            if not df_hist.empty:
                df_hist['data_documento'] = pd.to_datetime(df_hist['data_documento'], errors='coerce')
                df_hist['prezzo_unitario'] = pd.to_numeric(df_hist['prezzo_unitario'], errors='coerce')
                df_hist = df_hist.dropna(subset=['data_documento', 'prezzo_unitario']).sort_values('data_documento', ascending=False)
                df_hist['descrizione_key'] = df_hist['descrizione'].apply(_norm_key)
                df_hist['fornitore_key'] = df_hist['fornitore'].apply(_norm_key)

                df_omaggi['descrizione_key'] = df_omaggi['descrizione'].apply(_norm_key)
                df_omaggi['fornitore_key'] = df_omaggi['fornitore'].apply(_norm_key)

                for idx, row in df_omaggi.iterrows():
                    mask_same_supplier = (
                        (df_hist['descrizione_key'] == row['descrizione_key']) &
                        (df_hist['fornitore_key'] == row['fornitore_key']) &
                        (df_hist['data_documento'] < row['data_documento'])
                    )
                    candidati = df_hist[mask_same_supplier]

                    if candidati.empty:
                        mask_same_product = (
                            (df_hist['descrizione_key'] == row['descrizione_key']) &
                            (df_hist['data_documento'] < row['data_documento'])
                        )
                        candidati = df_hist[mask_same_product]

                    if not candidati.empty:
                        df_omaggi.at[idx, 'ultimo_prezzo'] = float(candidati.iloc[0]['prezzo_unitario'])

            df_omaggi['valore_stimato'] = df_omaggi.apply(
                lambda r: abs(float(r['ultimo_prezzo']) * float(r['quantita'])) if pd.notna(r['ultimo_prezzo']) else pd.NA,
                axis=1
            )

            totale_omaggi = float(df_omaggi['valore_stimato'].sum(min_count=1))
            if pd.isna(totale_omaggi):
                totale_omaggi = 0.0
        
        totale_risparmiato = totale_sconti + totale_omaggi
        
        return {
            'sconti': df_sconti,
            'omaggi': df_omaggi,
            'totale_omaggi': totale_omaggi,
            'totale_risparmiato': totale_risparmiato
        }
        
    except Exception as e:
        logger.error(f"Errore caricamento sconti/omaggi: {e}")
        return {
            'sconti': pd.DataFrame(),
            'omaggi': pd.DataFrame(),
            'totale_risparmiato': 0.0
        }


def elimina_fattura_completa(file_origine: str, user_id: str, supabase_client=None, ristoranteid: str = None, soft_delete: bool = True) -> Dict[str, Any]:
    """
    Elimina una fattura completa (tutti i prodotti) dal database.
    
    Args:
        file_origine: Nome del file XML della fattura
        user_id: ID utente (per controllo sicurezza)
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
        ristoranteid: ID ristorante per filtro multi-tenant
        soft_delete: Se True (default) sposta nel cestino, se False elimina definitivamente
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int}
    """
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return {"success": False, "error": "connection_error", "righe_eliminate": 0}
    
    try:
        if not user_id:
            return {"success": False, "error": "not_authenticated", "righe_eliminate": 0}
        
        # Prima conta quante righe verranno eliminate
        ristorante_id = ristoranteid

        if not ristorante_id:
            logger.warning("ristorante_id mancante in elimina_fattura_completa - filtro solo per user_id")
        
        query_count = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine)
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        if soft_delete:
            query_count = query_count.is_("deleted_at", "null")
        count_response = query_count.execute()
        # Usa count esatto dalle metadata (non len(data) che è cappato a 1000 righe da Supabase)
        num_righe = count_response.count if count_response.count is not None else (len(count_response.data) if count_response.data else 0)
        
        if num_righe == 0:
            return {"success": False, "error": "not_found", "righe_eliminate": 0}
        
        if soft_delete:
            # SOFT DELETE: sposta nel cestino impostando deleted_at
            query_update = supabase_client.table("fatture").update({"deleted_at": "now()"}).eq("user_id", user_id).eq("file_origine", file_origine).is_("deleted_at", "null")
            if ristorante_id:
                query_update = query_update.eq("ristorante_id", ristorante_id)
            query_update.execute()
            
            # Verifica post-update
            query_verify = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine).is_("deleted_at", "null")
            if ristorante_id:
                query_verify = query_verify.eq("ristorante_id", ristorante_id)
            verify_response = query_verify.execute()
            num_rimaste = verify_response.count if verify_response.count is not None else len(verify_response.data) if verify_response.data else 0
            
            if num_rimaste > 0:
                logger.error(f"❌ SOFT-DELETE PARZIALE: {num_rimaste} righe non spostate nel cestino per '{file_origine}', retry...")
                query_retry = supabase_client.table("fatture").update({"deleted_at": "now()"}).eq("user_id", user_id).eq("file_origine", file_origine).is_("deleted_at", "null")
                if ristorante_id:
                    query_retry = query_retry.eq("ristorante_id", ristorante_id)
                query_retry.execute()
            
            logger.info(f"🗑️ Fattura spostata nel cestino: {file_origine} ({num_righe} righe) da user {user_id}")
        else:
            # HARD DELETE: eliminazione definitiva (usato per rifiuto automatico)
            query_delete = supabase_client.table("fatture").delete().eq("user_id", user_id).eq("file_origine", file_origine)
            if ristorante_id:
                query_delete = query_delete.eq("ristorante_id", ristorante_id)
            query_delete.execute()
            
            # Verifica post-delete
            query_verify = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine)
            if ristorante_id:
                query_verify = query_verify.eq("ristorante_id", ristorante_id)
            verify_response = query_verify.execute()
            num_rimaste = verify_response.count if verify_response.count is not None else len(verify_response.data) if verify_response.data else 0
            
            if num_rimaste > 0:
                logger.error(f"❌ DELETE PARZIALE: {num_rimaste} righe ancora presenti per '{file_origine}', retry...")
                query_retry = supabase_client.table("fatture").delete().eq("user_id", user_id).eq("file_origine", file_origine)
                if ristorante_id:
                    query_retry = query_retry.eq("ristorante_id", ristorante_id)
                query_retry.execute()
                verify2 = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine)
                if ristorante_id:
                    verify2 = verify2.eq("ristorante_id", ristorante_id)
                v2 = verify2.execute()
                if (v2.count or 0) > 0:
                    return {"success": False, "error": f"Eliminazione parziale: {v2.count} righe non eliminate", "righe_eliminate": num_righe - (v2.count or 0)}
            
            logger.info(f"❌ Fattura eliminata definitivamente: {file_origine} ({num_righe} righe) da user {user_id}")
        
        return {"success": True, "error": None, "righe_eliminate": num_righe}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione fattura {file_origine} per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0}


def elimina_tutte_fatture(user_id: str, supabase_client=None, ristoranteid: str = None) -> Dict[str, Any]:
    """
    Sposta TUTTE le fatture attive dell'utente nel cestino (soft-delete).
    
    Args:
        user_id: ID utente (per controllo sicurezza)
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
        ristoranteid: ID ristorante per filtro multi-tenant
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int, "fatture_eliminate": int}
    """
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return {"success": False, "error": "connection_error", "righe_eliminate": 0, "fatture_eliminate": 0}
    
    try:
        if not user_id:
            return {"success": False, "error": "not_authenticated", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Prima conta quante righe e fatture attive verranno spostate nel cestino
        ristorante_id = ristoranteid

        if not ristorante_id:
            logger.warning("ristorante_id mancante in elimina_tutte_fatture - filtro solo per user_id")
        
        query_count = supabase_client.table("fatture").select("id, file_origine", count="exact").eq("user_id", user_id).is_("deleted_at", "null")
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        count_response = query_count.execute()
        num_righe = count_response.count if count_response.count else 0
        files_set = set()
        for r in (count_response.data or []):
            if r.get('file_origine'):
                files_set.add(r['file_origine'])
        # Se ci sono potenzialmente più di 1000 righe, fai una query distinct separata
        if len(count_response.data or []) >= 1000:
            try:
                rpc_params = {'p_user_id': user_id}
                if ristorante_id:
                    rpc_params['p_ristorante_id'] = ristorante_id
                rpc_resp = supabase_client.rpc('get_distinct_files', rpc_params).execute()
                if rpc_resp.data:
                    files_set = {row['file_origine'] for row in rpc_resp.data if row.get('file_origine')}
            except Exception as rpc_err:
                logger.warning(f"RPC get_distinct_files fallita, uso conteggio parziale: {rpc_err}")
        num_fatture = len(files_set)
        
        logger.info(f"SOFT-DELETE MASSIVO: user_id={user_id} ristorante_id={ristorante_id}, {num_fatture} fatture ({num_righe} righe)")
        
        if num_righe == 0:
            return {"success": False, "error": "no_data", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Esegui SOFT-DELETE: imposta deleted_at su tutte le righe attive
        logger.info(f"🗑️ Esecuzione SOFT-DELETE per user_id={user_id} ristorante_id={ristorante_id}...")
        
        try:
            query_update = supabase_client.table("fatture").update({"deleted_at": "now()"}).eq("user_id", user_id).is_("deleted_at", "null")
            if ristorante_id:
                query_update = query_update.eq("ristorante_id", ristorante_id)
            query_update.execute()
            logger.info(f"📊 SOFT-DELETE executed for user_id={user_id}")
        except Exception as update_error:
            logger.error(f"❌ ERRORE SOFT-DELETE: {update_error}")
            raise
        
        # Verifica post-update: conta righe ancora attive
        query_verify = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).is_("deleted_at", "null")
        if ristorante_id:
            query_verify = query_verify.eq("ristorante_id", ristorante_id)
        verify_response = query_verify.execute()
        num_rimaste = verify_response.count if verify_response.count else 0
        
        logger.info(f"✅ Verifica post-soft-delete: {num_rimaste} righe attive rimaste")
        
        if num_rimaste > 0:
            logger.error(f"❌ SOFT-DELETE PARZIALE: {num_rimaste} righe ancora attive per user {user_id}")
            
            # Tentativo 2: Re-UPDATE
            try:
                logger.info(f"🔄 TENTATIVO 2: Ri-esecuzione SOFT-DELETE per {num_rimaste} righe rimaste...")
                query_update2 = supabase_client.table("fatture").update({"deleted_at": "now()"}).eq("user_id", user_id).is_("deleted_at", "null")
                if ristorante_id:
                    query_update2 = query_update2.eq("ristorante_id", ristorante_id)
                query_update2.execute()
                
                # Verifica finale
                query_verify_final = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).is_("deleted_at", "null")
                if ristorante_id:
                    query_verify_final = query_verify_final.eq("ristorante_id", ristorante_id)
                verify_final = query_verify_final.execute()
                num_finali = verify_final.count if verify_final.count else 0
                
                if num_finali > 0:
                    logger.critical(f"🚨 SOFT-DELETE FALLITO ANCHE DOPO RETRY: {num_finali} righe ancora attive")
                    return {
                        "success": False, 
                        "error": f"Soft-delete parziale: {num_finali} righe non spostate", 
                        "righe_eliminate": num_righe - num_finali, 
                        "fatture_eliminate": num_fatture
                    }
                else:
                    logger.info(f"✅ SOFT-DELETE completato al secondo tentativo")
            except Exception as retry_error:
                logger.critical(f"❌ ERRORE nel retry SOFT-DELETE: {retry_error}")
                return {
                    "success": False, 
                    "error": f"Soft-delete fallito: {str(retry_error)}", 
                    "righe_eliminate": 0, 
                    "fatture_eliminate": 0
                }
        
        logger.warning(f"⚠️ SOFT-DELETE MASSIVO SUCCESSO: {num_fatture} fatture ({num_righe} righe) spostate nel cestino per user {user_id}")
        
        try:
            from services.ai_service import invalida_cache_memoria
            invalida_cache_memoria()
        except Exception:
            pass
        
        return {"success": True, "error": None, "righe_eliminate": num_righe, "fatture_eliminate": num_fatture}
        
    except Exception as e:
        logger.exception(f"Errore soft-delete massivo per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0, "fatture_eliminate": 0}


@st.cache_data(ttl=60, show_spinner=False)
def get_fatture_stats(user_id: str, ristorante_id: str = None) -> Dict[str, Any]:
    """
    Ottiene statistiche fatture da Supabase (cachate 60s).
    
    Args:
        user_id: ID utente per filtro multi-tenancy
        ristorante_id: ID ristorante (opzionale)
    
    Returns:
        dict con:
        - num_uniche: Numero fatture uniche (FileOrigine distinti)
        - num_righe: Numero totale righe/prodotti
        - success: bool (True se query riuscita)
    """
    try:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
    except Exception as e:
        logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
        return {"num_uniche": 0, "num_righe": 0, "success": False}
    
    try:
        # NOTA: queste due query non sono atomiche, può esserci una lieve
        # inconsistenza tra numrighe e numuniche in caso di upload concorrenti.
        # Query 1: Conta righe totali con count='exact' senza scaricare dati
        query_count = supabase_client.table("fatture") \
            .select("id", count='exact') \
            .eq("user_id", user_id) \
            .is_("deleted_at", "null") \
            .limit(1)
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        response_count = query_count.execute()
        total_rows = response_count.count if response_count.count else 0
        
        if total_rows == 0:
            return {"num_uniche": 0, "num_righe": 0, "success": True}
        
        # Query 2: Scarica solo file_origine distinti (molto più leggero)
        file_unici_set = set()
        page = 0
        page_size = 1000
        max_pages = 200
        
        while page < max_pages:
            offset = page * page_size
            query_files = supabase_client.table("fatture") \
                .select("file_origine") \
                .eq("user_id", user_id) \
                .is_("deleted_at", "null")
            if ristorante_id:
                query_files = query_files.eq("ristorante_id", ristorante_id)
            response = query_files.range(offset, offset + page_size - 1).execute()
            
            if not response.data:
                break
            
            for r in response.data:
                if r.get("file_origine"):
                    file_unici_set.add(r["file_origine"])
            
            if len(response.data) < page_size:
                break
                
            page += 1
        
        return {
            "num_uniche": len(file_unici_set),
            "num_righe": total_rows,
            "success": True
        }
    except Exception as e:
        logger.error(f"Errore get_fatture_stats per user {user_id}: {e}")
        return {"num_uniche": 0, "num_righe": 0, "success": False}


def clear_fatture_cache() -> None:
    """Invalida solo la cache fatture (non tutte le cache Streamlit)."""
    # [DEBUG]
    logger.debug(f"[CACHE] clear_fatture_cache() chiamata — ts={time.time():.3f}")
    _carica_fatture_da_supabase.clear()
    get_fatture_stats.clear()


# ============================================================
# CESTINO FATTURE (soft-delete)
# ============================================================

def get_fatture_cestino(user_id: str, ristorante_id: str = None, supabase_client=None) -> List[Dict[str, Any]]:
    """
    Restituisce le fatture nel cestino raggruppate per file_origine.
    
    Returns:
        Lista di dict con: file_origine, fornitore, num_righe, totale, deleted_at
    """
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
    
    try:
        query = (
            supabase_client.table("fatture")
            .select("file_origine,fornitore,totale_riga,deleted_at,data_documento")
            .eq("user_id", user_id)
            .not_.is_("deleted_at", "null")
        )
        if ristorante_id:
            query = query.eq("ristorante_id", ristorante_id)
        
        # Paginazione per supportare >1000 righe nel cestino
        all_rows = []
        page_size = 1000
        offset = 0
        while True:
            resp = query.range(offset, offset + page_size - 1).execute()
            if not resp.data:
                break
            all_rows.extend(resp.data)
            if len(resp.data) < page_size:
                break
            offset += page_size
        
        if not all_rows:
            return []
        
        # Raggruppa per file_origine
        from collections import defaultdict
        grouped = defaultdict(lambda: {"num_righe": 0, "totale": 0.0, "fornitore": "", "deleted_at": "", "data_documento": ""})
        for row in all_rows:
            key = row["file_origine"]
            grouped[key]["num_righe"] += 1
            grouped[key]["totale"] += float(row.get("totale_riga") or 0)
            if not grouped[key]["fornitore"]:
                grouped[key]["fornitore"] = row.get("fornitore", "")
            if not grouped[key]["deleted_at"]:
                grouped[key]["deleted_at"] = row.get("deleted_at", "")
            if not grouped[key]["data_documento"]:
                grouped[key]["data_documento"] = row.get("data_documento", "")
        
        result = []
        for file_orig, info in grouped.items():
            result.append({
                "file_origine": file_orig,
                "fornitore": info["fornitore"],
                "num_righe": info["num_righe"],
                "totale": info["totale"],
                "deleted_at": info["deleted_at"],
                "data_documento": info["data_documento"],
            })
        
        # Ordina per deleted_at decrescente (più recenti prima)
        result.sort(key=lambda x: x["deleted_at"], reverse=True)
        return result
    except Exception as e:
        logger.error(f"Errore get_fatture_cestino user_id={user_id}: {e}")
        return []


def ripristina_fattura(file_origine: str, user_id: str, ristorante_id: str = None, supabase_client=None) -> Dict[str, Any]:
    """
    Ripristina una fattura dal cestino (rimuove deleted_at).
    
    Returns:
        dict: {"success": bool, "error": str, "righe_ripristinate": int}
    """
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
    
    try:
        # Conta righe da ripristinare
        query_count = (
            supabase_client.table("fatture")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .not_.is_("deleted_at", "null")
        )
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        count_resp = query_count.execute()
        num_righe = count_resp.count if count_resp.count is not None else 0
        
        if num_righe == 0:
            return {"success": False, "error": "not_found", "righe_ripristinate": 0}
        
        # Ripristina: rimuovi deleted_at
        query_update = (
            supabase_client.table("fatture")
            .update({"deleted_at": None})
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .not_.is_("deleted_at", "null")
        )
        if ristorante_id:
            query_update = query_update.eq("ristorante_id", ristorante_id)
        query_update.execute()
        
        logger.info(f"♻️ Fattura ripristinata dal cestino: {file_origine} ({num_righe} righe) user {user_id}")
        return {"success": True, "error": None, "righe_ripristinate": num_righe}
    except Exception as e:
        logger.error(f"Errore ripristina_fattura {file_origine} user {user_id}: {e}")
        return {"success": False, "error": str(e), "righe_ripristinate": 0}


def svuota_cestino(user_id: str, ristorante_id: str = None, supabase_client=None) -> Dict[str, Any]:
    """
    Svuota il cestino: elimina definitivamente tutte le fatture soft-deleted.
    Solo admin. Pulisce anche prodotti_utente e classificazioni_manuali.
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int}
    """
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
    
    try:
        # Conta righe nel cestino
        query_count = (
            supabase_client.table("fatture")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .not_.is_("deleted_at", "null")
        )
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        count_resp = query_count.execute()
        num_righe = count_resp.count if count_resp.count is not None else 0
        
        if num_righe == 0:
            return {"success": True, "error": None, "righe_eliminate": 0}
        
        # Hard-delete definitivo
        query_delete = (
            supabase_client.table("fatture")
            .delete()
            .eq("user_id", user_id)
            .not_.is_("deleted_at", "null")
        )
        if ristorante_id:
            query_delete = query_delete.eq("ristorante_id", ristorante_id)
        query_delete.execute()
        
        # Cleanup dati correlati (solo se non ci sono più fatture attive per l'utente)
        active_count_query = (
            supabase_client.table("fatture")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
        )
        if ristorante_id:
            active_count_query = active_count_query.eq("ristorante_id", ristorante_id)
        active_resp = active_count_query.execute()
        active_count = active_resp.count if active_resp.count else 0
        
        if active_count == 0:
            try:
                supabase_client.table("prodotti_utente").delete().eq("user_id", user_id).execute()
                logger.info(f"🧹 prodotti_utente resettati per user {user_id}")
            except Exception as e_pu:
                logger.warning(f"⚠️ Impossibile resettare prodotti_utente: {e_pu}")
            try:
                supabase_client.table("classificazioni_manuali").delete().eq("user_id", user_id).execute()
                logger.info(f"🧹 classificazioni_manuali resettate per user {user_id}")
            except Exception as e_cm:
                logger.warning(f"⚠️ Impossibile resettare classificazioni_manuali: {e_cm}")
        
        logger.warning(f"🗑️ CESTINO SVUOTATO: {num_righe} righe eliminate definitivamente per user {user_id}")
        return {"success": True, "error": None, "righe_eliminate": num_righe}
    except Exception as e:
        logger.error(f"Errore svuota_cestino user {user_id}: {e}")
        return {"success": False, "error": str(e), "righe_eliminate": 0}


def purge_cestino_scaduto(supabase_client=None) -> Dict[str, Any]:
    """
    Elimina definitivamente le fatture nel cestino da più di 30 giorni.
    Chiamata periodicamente dal worker.
    
    Returns:
        dict: {"success": bool, "righe_eliminate": int, "error": str}
    """
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
    
    try:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        
        # Conta righe scadute
        count_resp = (
            supabase_client.table("fatture")
            .select("id,user_id", count="exact")
            .not_.is_("deleted_at", "null")
            .lt("deleted_at", cutoff)
            .execute()
        )
        num_righe = count_resp.count if count_resp.count is not None else 0
        
        if num_righe == 0:
            return {"success": True, "righe_eliminate": 0, "error": None}
        
        # Raccogli user_id coinvolti per cleanup successivo
        affected_users = set()
        for row in (count_resp.data or []):
            if row.get("user_id"):
                affected_users.add(row["user_id"])
        
        # Hard-delete
        (
            supabase_client.table("fatture")
            .delete()
            .not_.is_("deleted_at", "null")
            .lt("deleted_at", cutoff)
            .execute()
        )
        
        logger.warning(f"🗑️ PURGE CESTINO: {num_righe} righe scadute eliminate definitivamente ({len(affected_users)} utenti)")
        return {"success": True, "righe_eliminate": num_righe, "error": None}
    except Exception as e:
        logger.error(f"Errore purge_cestino_scaduto: {e}")
        return {"success": False, "righe_eliminate": 0, "error": str(e)}


def _upsert_retention_status(rows_deleted: int, rows_from_trash: int, status: str, error_message: str = None, supabase_client=None) -> None:
    """Aggiorna il record singolo di stato retention per il pannello admin."""
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()

    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "job_name": RETENTION_JOB_NAME,
            "last_run_at": now_iso,
            "rows_deleted": int(rows_deleted or 0),
            "rows_from_trash": int(rows_from_trash or 0),
            "status": status,
            "error_message": (str(error_message)[:1000] if error_message else None),
            "updated_at": now_iso,
        }
        supabase_client.table("system_maintenance_status").upsert(payload, on_conflict="job_name").execute()
    except Exception as exc:
        logger.warning(f"Errore aggiornamento stato retention: {exc}")


def get_retention_last_status(supabase_client=None) -> Dict[str, Any]:
    """Restituisce lo stato dell'ultimo ciclo di retention fatture."""
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()

    try:
        resp = (
            supabase_client.table("system_maintenance_status")
            .select("job_name,last_run_at,rows_deleted,rows_from_trash,status,error_message,updated_at")
            .eq("job_name", RETENTION_JOB_NAME)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]
    except Exception as exc:
        logger.warning(f"Errore get_retention_last_status: {exc}")

    return {
        "job_name": RETENTION_JOB_NAME,
        "last_run_at": None,
        "rows_deleted": 0,
        "rows_from_trash": 0,
        "status": "ok",
        "error_message": None,
        "updated_at": None,
    }


def purge_fatture_retention(batch_size: int = RETENTION_BATCH_SIZE, supabase_client=None) -> Dict[str, Any]:
    """
    Elimina definitivamente fino a N righe dalla tabella fatture con created_at più vecchio di 2 anni.
    Include anche le righe che si trovano già nel cestino.
    
    Returns:
        dict: {"success": bool, "righe_eliminate": int, "righe_da_cestino": int, "error": str}
    """
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()

    try:
        from datetime import datetime, timedelta, timezone

        safe_batch_size = max(1, int(batch_size or RETENTION_BATCH_SIZE))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=365 * 2)).isoformat()

        resp = (
            supabase_client.table("fatture")
            .select("id,deleted_at,created_at")
            .lt("created_at", cutoff)
            .order("created_at")
            .limit(safe_batch_size)
            .execute()
        )

        rows = resp.data or []
        if not rows:
            _upsert_retention_status(0, 0, "ok", None, supabase_client=supabase_client)
            return {"success": True, "righe_eliminate": 0, "righe_da_cestino": 0, "error": None}

        ids_to_delete = [row["id"] for row in rows if row.get("id") is not None]
        rows_from_trash = sum(1 for row in rows if row.get("deleted_at") is not None)

        if ids_to_delete:
            supabase_client.table("fatture").delete().in_("id", ids_to_delete).execute()

        deleted_count = len(ids_to_delete)
        _upsert_retention_status(deleted_count, rows_from_trash, "ok", None, supabase_client=supabase_client)

        logger.warning(
            f"🧹 RETENTION FATTURE: eliminate {deleted_count} righe >2 anni (di cui {rows_from_trash} dal cestino)"
        )
        return {
            "success": True,
            "righe_eliminate": deleted_count,
            "righe_da_cestino": rows_from_trash,
            "error": None,
        }
    except Exception as e:
        _upsert_retention_status(0, 0, "error", str(e), supabase_client=supabase_client)
        logger.error(f"Errore purge_fatture_retention: {e}")
        return {"success": False, "righe_eliminate": 0, "righe_da_cestino": 0, "error": str(e)}


@st.cache_data(ttl=300, show_spinner=False)
def get_custom_tags(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    """Carica i custom tag dell'utente per il ristorante corrente."""
    try:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
        response = (
            supabase_client.table("custom_tags")
            .select("id,nome,emoji,colore,created_at")
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .order("nome")
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Errore get_custom_tags user_id={user_id} ristorante_id={ristorante_id}: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def get_custom_tag_prodotti(tag_id: int, user_id: str) -> List[Dict[str, Any]]:
    """Carica le associazioni descrizione per un singolo tag."""
    try:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
        response = (
            supabase_client.table("custom_tag_prodotti")
            .select("id,tag_id,descrizione,descrizione_key,fattore_kg,created_at")
            .eq("tag_id", tag_id)
            .eq("user_id", user_id)
            .order("descrizione")
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Errore get_custom_tag_prodotti tag_id={tag_id}: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def get_descrizioni_distinte(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
    """
    Carica le descrizioni fattura e le aggrega in Python per descrizione_key.
    Questa lista e la base per la ricerca live nella UI.
    """
    try:
        from services import get_supabase_client
        supabase_client = get_supabase_client()

        rows = []
        page = 0
        page_size = 1000
        max_pages = 200

        while page < max_pages:
            if page > 50:
                logger.warning(
                    f"⚠️ get_descrizioni_distinte oltre 50 pagine per user_id={user_id} ristorante_id={ristorante_id}"
                )

            offset = page * page_size
            response = (
                supabase_client.table("fatture")
                .select("descrizione,fornitore,data_documento,unita_misura")
                .eq("user_id", user_id)
                .eq("ristorante_id", ristorante_id)
                .range(offset, offset + page_size - 1)
                .execute()
            )

            if not response.data:
                break

            rows.extend(response.data)

            if len(response.data) < page_size:
                break

            page += 1

        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            descrizione = (row.get("descrizione") or "").strip()
            if not descrizione:
                continue

            descrizione_key = _normalize_custom_tag_key(descrizione)
            if not descrizione_key:
                continue

            item = grouped.setdefault(
                descrizione_key,
                {
                    "descrizione": descrizione,
                    "descrizione_key": descrizione_key,
                    "occorrenze": 0,
                    "fornitori": set(),
                    "ultima_data": row.get("data_documento"),
                    "unita_misura_set": set(),
                },
            )

            item["occorrenze"] += 1

            fornitore = (row.get("fornitore") or "").strip()
            if fornitore:
                item["fornitori"].add(fornitore)

            unita_misura = (row.get("unita_misura") or "").strip()
            if unita_misura:
                item["unita_misura_set"].add(unita_misura)

            data_documento = row.get("data_documento")
            if data_documento and (not item["ultima_data"] or data_documento > item["ultima_data"]):
                item["ultima_data"] = data_documento

        results = []
        for item in grouped.values():
            results.append(
                {
                    "descrizione": item["descrizione"],
                    "descrizione_key": item["descrizione_key"],
                    "occorrenze": item["occorrenze"],
                    "num_fornitori": len(item["fornitori"]),
                    "fornitori": sorted(item["fornitori"]),
                    "ultima_data": item["ultima_data"],
                    "unita_misura": sorted(item["unita_misura_set"]),
                }
            )

        results.sort(key=lambda x: (-x["occorrenze"], x["descrizione"]))
        return results
    except Exception as e:
        logger.error(f"Errore get_descrizioni_distinte user_id={user_id} ristorante_id={ristorante_id}: {e}")
        return []


def clear_tags_cache() -> None:
    """Invalida solo la cache legata ai custom tag."""
    logger.debug(f"[CACHE] clear_tags_cache() chiamata — ts={time.time():.3f}")
    get_custom_tags.clear()
    get_custom_tag_prodotti.clear()
    get_descrizioni_distinte.clear()


def crea_tag(user_id: str, ristorante_id: str, nome: str, emoji: str = None, colore: str = None) -> Dict[str, Any]:
    """Crea un nuovo custom tag e invalida la cache dedicata."""
    from services import get_supabase_client
    supabase_client = get_supabase_client()

    payload = {
        "user_id": user_id,
        "ristorante_id": ristorante_id,
        "nome": (nome or "").strip(),
        "emoji": (emoji or None),
        "colore": (colore or None),
    }
    response = supabase_client.table("custom_tags").insert(payload).execute()
    clear_tags_cache()
    return (response.data or [{}])[0]


def aggiorna_tag(tag_id: int, user_id: str, nome: str, emoji: str = None, colore: str = None) -> Dict[str, Any]:
    """Aggiorna metadata del tag e invalida la cache dedicata."""
    from services import get_supabase_client
    supabase_client = get_supabase_client()

    payload = {
        "nome": (nome or "").strip(),
        "emoji": (emoji or None),
        "colore": (colore or None),
    }
    response = (
        supabase_client.table("custom_tags")
        .update(payload)
        .eq("id", tag_id)
        .eq("user_id", user_id)
        .execute()
    )
    clear_tags_cache()
    return (response.data or [{}])[0]


def elimina_tag(tag_id: int, user_id: str) -> bool:
    """Elimina un tag; le associazioni vengono rimosse via ON DELETE CASCADE."""
    from services import get_supabase_client
    supabase_client = get_supabase_client()

    supabase_client.table("custom_tags").delete().eq("id", tag_id).eq("user_id", user_id).execute()
    clear_tags_cache()
    return True


def aggiungi_associazioni(tag_id: int, descrizioni: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Inserisce associazioni per un tag usando descrizione_key come chiave interna.
    Usa upsert per evitare rollback di batch interi su duplicati.
    """
    if not descrizioni:
        return []

    from services import get_supabase_client
    supabase_client = get_supabase_client()

    payload = []
    for item in descrizioni:
        descrizione = (item.get("descrizione") or "").strip()
        if not descrizione:
            continue
        payload.append(
            {
                "tag_id": tag_id,
                "descrizione": descrizione,
                "descrizione_key": _normalize_custom_tag_key(item.get("descrizione_key") or descrizione),
                "fattore_kg": item.get("fattore_kg"),
            }
        )

    if not payload:
        return []

    response = (
        supabase_client.table("custom_tag_prodotti")
        .upsert(payload, on_conflict="tag_id,descrizione_key")
        .execute()
    )
    clear_tags_cache()
    return response.data or []


def rimuovi_associazione(associazione_id: int, user_id: str) -> bool:
    """Rimuove una singola associazione tag-prodotto."""
    from services import get_supabase_client
    supabase_client = get_supabase_client()

    supabase_client.table("custom_tag_prodotti").delete().eq("id", associazione_id).eq("user_id", user_id).execute()
    clear_tags_cache()
    return True


__all__ = [
    'carica_e_prepara_dataframe',
    'ricalcola_prezzi_con_sconti',
    'calcola_alert',
    'carica_sconti_e_omaggi',
    'elimina_fattura_completa',
    'elimina_tutte_fatture',
    'get_fatture_stats',
    'clear_fatture_cache',
    'get_custom_tags',
    'get_custom_tag_prodotti',
    'get_descrizioni_distinte',
    'clear_tags_cache',
    'crea_tag',
    'aggiorna_tag',
    'elimina_tag',
    'aggiungi_associazioni',
    'rimuovi_associazione',
]
