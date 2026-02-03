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
from typing import Optional, Dict, Any
import pandas as pd
import streamlit as st

# Import config
from config.constants import CATEGORIE_SPESE_GENERALI

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('db')


def carica_e_prepara_dataframe(user_id: str, force_refresh: bool = False, supabase_client=None):
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
        import streamlit as st
        if hasattr(st, 'session_state') and st.session_state.get('force_empty_until_upload', False):
            logger.info(f"🚫 FORCE EMPTY attivo: ritorno DataFrame vuoto per user_id={user_id}")
            return pd.DataFrame()
    except Exception as e:
        logger.warning(f"⚠️ Impossibile controllare force_empty flag: {e}")
    
    # Inizializza client Supabase (singleton)
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.critical(f"❌ CRITICAL: Impossibile inizializzare Supabase: {e}")
            return pd.DataFrame()
    
    logger.info(f"📊 LOAD START: user_id={user_id}, force_refresh={force_refresh}")
    
    dati = []
    
    # Carica da Supabase con paginazione
    if supabase_client is not None:
        try:
            # Recupera ristorante_id dalla sessione (per multi-ristorante)
            ristorante_id = st.session_state.get('ristorante_id') if 'session_state' in dir(st) else None
            
            # Prima query per ottenere il count totale (usa head per performance)
            query_count = supabase_client.table("fatture").select("id", count="exact", head=True).eq("user_id", user_id)
            if ristorante_id:
                query_count = query_count.eq("ristorante_id", ristorante_id)
            response_count = query_count.execute()
            total_rows = response_count.count if response_count.count else 0
            logger.info(f"📊 CARICAMENTO: user_id={user_id} ristorante_id={ristorante_id} ha {total_rows} righe su Supabase")
            
            # Paginazione per caricare tutte le righe
            page_size = 1000
            page = 0
            
            # 🚀 OTTIMIZZAZIONE: Select solo colonne necessarie (non "*")
            columns = "file_origine,numero_riga,data_documento,fornitore,descrizione,quantita,unita_misura,prezzo_unitario,iva_percentuale,totale_riga,categoria,codice_articolo,prezzo_standard,ristorante_id"
            
            while True:
                offset = page * page_size
                query_select = supabase_client.table("fatture").select(columns).eq("user_id", user_id)
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
                        "PrezzoStandard": row.get("prezzo_standard")
                    })
                
                # Se questa pagina ha meno di page_size record, abbiamo finito
                if len(response.data) < page_size:
                    break
                    
                page += 1
            
            if len(dati) > 0:
                logger.info(f"✅ LOAD SUCCESS: {len(dati)} righe caricate da Supabase per user_id={user_id}")
                df_result = pd.DataFrame(dati)
                
                # 🔧 NORMALIZZA CATEGORIA: Converti NULL/None/vuoti in NaN per uniformità
                if 'Categoria' in df_result.columns:
                    df_result['Categoria'] = df_result['Categoria'].replace(
                        to_replace=[None, '', 'None', 'null', 'NULL', ' '], 
                        value=pd.NA
                    )
                    # Converti spazi bianchi in NaN
                    df_result.loc[df_result['Categoria'].astype(str).str.strip() == '', 'Categoria'] = pd.NA
                    
                    # 🔄 MIGRAZIONE AUTOMATICA: Aggiorna vecchi nomi categorie
                    mapping_categorie = {
                        'SALSE': 'SALSE E CREME',
                        'BIBITE E BEVANDE': 'BEVANDE',
                        'PANE': 'PRODOTTI DA FORNO',
                        'DOLCI': 'PASTICCERIA',
                        'OLIO': 'OLIO E CONDIMENTI',
                        'CONSERVE': 'SCATOLAME E CONSERVE',
                        'CAFFÈ': 'CAFFE E THE'
                    }
                    
                    righe_migrate = 0
                    for vecchio, nuovo in mapping_categorie.items():
                        mask = df_result['Categoria'] == vecchio
                        if mask.any():
                            df_result.loc[mask, 'Categoria'] = nuovo
                            righe_migrate += mask.sum()
                    
                    if righe_migrate > 0:
                        logger.info(f"✅ MIGRAZIONE: {righe_migrate} righe aggiornate")
                    
                    # 🎯 FIX CELLE BIANCHE DEFINITIVO: Riempie NA E vuoti con "Da Classificare"
                    # Log diagnostico PRIMA della normalizzazione
                    null_count_before = df_result['Categoria'].isna().sum()
                    logger.debug(f"🔍 PRE-NORMALIZZAZIONE: {null_count_before} valori NA")
                    
                    # Step 1: fillna per NULL/pd.NA
                    df_result['Categoria'] = df_result['Categoria'].fillna("Da Classificare")
                    
                    # Step 2: ⭐ FIX SPAZI BIANCHI - Gestisci ANCHE stringhe con spazi multipli
                    df_result['Categoria'] = df_result['Categoria'].replace(
                        to_replace=[None, '', 'None', 'null', 'NULL', ' ', '  ', '   ', '    '],
                        value='Da Classificare'
                    )
                    
                    # Step 3: Converti spazi bianchi (anche multipli) in "Da Classificare"
                    mask_empty = df_result['Categoria'].astype(str).str.strip() == ''
                    if mask_empty.any():
                        df_result.loc[mask_empty, 'Categoria'] = 'Da Classificare'
                        logger.debug(f"🔧 Convertiti {mask_empty.sum()} valori con solo spazi in Da Classificare")
                    
                    # Verifica finale
                    da_class_count = (df_result['Categoria'] == 'Da Classificare').sum()
                    logger.info(f"✅ CELLE BIANCHE RISOLTE: {da_class_count} celle mostrano 'Da Classificare'")
                
                return df_result
            else:
                logger.info(f"ℹ️ LOAD EMPTY: Nessuna fattura per user_id={user_id}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ LOAD ERROR: Errore Supabase per user_id={user_id}: {e}")
            logger.exception("Errore query Supabase")
            return pd.DataFrame()
    
    # Supabase non configurato (impossibile in produzione)
    logger.critical("❌ CRITICAL: Supabase client non inizializzato!")
    return pd.DataFrame()


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
    # Inizializza client Supabase (singleton)
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return 0
    
    try:
        # Leggi tutte le fatture dell'utente
        from utils.ristorante_helper import get_current_ristorante_id
        ristorante_id = get_current_ristorante_id()
        query = supabase_client.table("fatture") \
            .select("id, descrizione, quantita, prezzo_unitario, totale_riga") \
            .eq("user_id", user_id)
        if ristorante_id:
            query = query.eq("ristorante_id", ristorante_id)
        response = query.execute()
        
        if not response.data:
            return 0
        
        righe_aggiornate = 0
        
        for row in response.data:
            totale = row.get('totale_riga', 0)
            quantita = row.get('quantita', 0)
            prezzo_attuale = row.get('prezzo_unitario', 0)
            
            if quantita > 0 and totale > 0:
                # Ricalcola prezzo effettivo
                prezzo_effettivo = round(totale / quantita, 4)
                
                # Solo se diverso (c'era uno sconto)
                if abs(prezzo_effettivo - prezzo_attuale) > 0.01:
                    # Aggiorna database
                    supabase_client.table("fatture").update({
                        'prezzo_unitario': prezzo_effettivo
                    }).eq('id', row['id']).execute()
                    
                    righe_aggiornate += 1
                    logger.info(f"🔄 Prezzo aggiornato: {row.get('descrizione', '')[:40]} | "
                               f"€{prezzo_attuale:.2f} → €{prezzo_effettivo:.2f}")
        
        return righe_aggiornate
    
    except Exception as e:
        logger.error(f"Errore ricalcolo prezzi: {e}")
        return 0


def calcola_alert(df: pd.DataFrame, soglia_minima: float, filtro_prodotto: str = "") -> pd.DataFrame:
    """
    Calcola alert aumenti prezzi confrontando il PREZZO UNITARIO EFFETTIVO
    (con sconti applicati) tra acquisti successivi dello stesso prodotto.
    
    IMPORTANTE: Escludi SOLO le 3 categorie spese generali reali.
    MATERIALE DI CONSUMO È F&B! (tovaglioli, piatti usa e getta, pellicole = materiali consumo ristorante)
    
    Logica:
    - Confronta Prezzo Unit. Effettivo (€/PZ, €/Kg, etc.)
    - Indipendente da quantità acquistata
    - Rileva anche ribassi (valore negativo)
    
    Args:
        df: DataFrame con colonne Descrizione, Fornitore, DataDocumento, PrezzoUnitario, Categoria
        soglia_minima: Percentuale minima per alert (es. 5.0 = 5%)
        filtro_prodotto: Stringa per filtrare prodotti (opzionale)
    
    Returns:
        DataFrame con alert ordinati per aumento decrescente
    """
    if df.empty:
        return pd.DataFrame()
    
    # Verifica colonne necessarie
    required_cols = ['Descrizione', 'Fornitore', 'DataDocumento', 'PrezzoUnitario', 'Categoria', 'FileOrigine']
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame()
    
    # ============================================================
    # FILTRO: ESCLUDI SOLO LE 3 CATEGORIE SPESE GENERALI
    # ============================================================
    # Le uniche 3 categorie NON F&B sono:
    # 1. MANUTENZIONE E ATTREZZATURE
    # 2. UTENZE E LOCALI
    # 3. SERVIZI E CONSULENZE
    #
    # TUTTO IL RESTO È F&B (incluso MATERIALE DI CONSUMO!)
    df_fb = df[~df['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
    
    if df_fb.empty:
        return pd.DataFrame()
    
    # ============================================================
    # FILTRO 2: SEARCH PRODOTTO (se specificato)
    # ============================================================
    if filtro_prodotto:
        df_fb = df_fb[df_fb['Descrizione'].str.contains(filtro_prodotto, case=False, na=False)]
    
    df = df_fb  # Usa solo prodotti F&B
    
    if df.empty:
        return pd.DataFrame()
    
    alert_list = []
    
    # Raggruppa per Descrizione + Fornitore
    for (prodotto, fornitore), group in df.groupby(['Descrizione', 'Fornitore']):
        # Ordina per data
        group = group.sort_values('DataDocumento')
        
        # Serve almeno 2 acquisti per confrontare
        if len(group) < 2:
            continue
        
        # Confronta acquisti consecutivi
        for i in range(1, len(group)):
            prev_row = group.iloc[i-1]
            curr_row = group.iloc[i]
            
            # 🎯 USA PREZZO UNITARIO EFFETTIVO (con sconti già applicati)
            prezzo_prec = prev_row['PrezzoUnitario']
            prezzo_nuovo = curr_row['PrezzoUnitario']
            
            # Validazione prezzi
            if prezzo_prec <= 0 or prezzo_nuovo <= 0:
                continue
            
            # 🛡️ PROTEZIONE: Ignora se troppo tempo tra acquisti (>180 giorni)
            try:
                data_prec = pd.to_datetime(prev_row['DataDocumento'])
                data_corr = pd.to_datetime(curr_row['DataDocumento'])
                giorni_diff = (data_corr - data_prec).days
                
                if giorni_diff > 180:
                    continue  # Troppo vecchio, ignora
            except (ValueError, TypeError):
                pass  # Se parsing date fallisce, continua comunque
            
            # CALCOLA SCOSTAMENTO PERCENTUALE
            aumento_perc = ((prezzo_nuovo - prezzo_prec) / prezzo_prec) * 100
            
            # Filtra per soglia minima (include anche ribassi negativi)
            if abs(aumento_perc) >= soglia_minima:
                # Usa nome file completo per N_Fattura
                file_origine = str(curr_row.get('FileOrigine', ''))
                
                alert_list.append({
                    'Prodotto': prodotto[:50],  # limita lunghezza
                    'Categoria': str(curr_row['Categoria'])[:15],
                    'Fornitore': str(fornitore)[:20],
                    'Data': curr_row['DataDocumento'],
                    'Prezzo_Prec': prezzo_prec,
                    'Prezzo_Nuovo': prezzo_nuovo,
                    'Aumento_Perc': aumento_perc,
                    'N_Fattura': file_origine
                })
    
    if not alert_list:
        return pd.DataFrame()
    
    df_alert = pd.DataFrame(alert_list)
    # Ordina per Aumento_Perc DECRESCENTE (maggiori aumenti prima, ribassi alla fine)
    df_alert = df_alert.sort_values('Aumento_Perc', ascending=False).reset_index(drop=True)
    
    return df_alert


def carica_sconti_e_omaggi(user_id: str, data_inizio, data_fine, supabase_client=None) -> Dict[str, Any]:
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
        
        # 🏢 MULTI-RISTORANTE: Recupera ristorante_id dalla sessione
        ristorante_id = st.session_state.get('ristorante_id') if 'session_state' in dir(st) else None
        
        # Query righe del cliente NEL PERIODO SPECIFICATO
        query = supabase_client.table('fatture')\
            .select('id, descrizione, categoria, fornitore, prezzo_unitario, quantita, totale_riga, data_documento, file_origine')\
            .eq('user_id', user_id)\
            .gte('data_documento', data_inizio)\
            .lte('data_documento', data_fine)
        
        # 🔒 FILTRO MULTI-RISTORANTE: Include solo fatture del ristorante attivo
        if ristorante_id:
            query = query.eq('ristorante_id', ristorante_id)
            logger.debug(f"🔍 Sconti/Omaggi filtrati per ristorante_id: {ristorante_id}")
        
        response = query.execute()
        
        if not response.data:
            return {
                'sconti': pd.DataFrame(),
                'omaggi': pd.DataFrame(),
                'totale_risparmiato': 0.0
            }
        
        df = pd.DataFrame(response.data)
        
        # ============================================================
        # FILTRO: ESCLUDI SOLO LE 3 CATEGORIE SPESE GENERALI
        # ============================================================
        # Le uniche 3 categorie NON F&B sono:
        # 1. MANUTENZIONE E ATTREZZATURE
        # 2. UTENZE E LOCALI
        # 3. SERVIZI E CONSULENZE
        #
        # TUTTO IL RESTO È F&B (incluso MATERIALE DI CONSUMO!)
        # MATERIALE DI CONSUMO contiene materiali di consumo ristorante (tovaglioli, piatti, pellicole, etc.)
        df_food = df[~df['categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
        
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
        # OMAGGI: Prezzi €0 (escludi descrizioni "omaggio" esplicite)
        # ============================================================
        pattern_omaggio = r'(?i)(omaggio|campione|prova|test|gratis|gratuito)'
        
        df_omaggi = df_food[
            (df_food['prezzo_unitario'] == 0) &
            (~df_food['descrizione'].str.contains(pattern_omaggio, na=False))
        ].copy()
        
        if not df_omaggi.empty:
            # Ordina per data
            df_omaggi = df_omaggi.sort_values('data_documento', ascending=False)
        
        # ============================================================
        # CALCOLO TOTALE RISPARMIATO
        # ============================================================
        totale_sconti = df_sconti['importo_sconto'].sum() if not df_sconti.empty else 0.0
        
        # Omaggi: stima valore medio categoria (se disponibile)
        # Per semplicità usiamo 0 (difficile stimare valore omaggi)
        totale_omaggi = 0.0
        
        totale_risparmiato = totale_sconti + totale_omaggi
        
        return {
            'sconti': df_sconti,
            'omaggi': df_omaggi,
            'totale_risparmiato': totale_risparmiato
        }
        
    except Exception as e:
        logger.error(f"Errore caricamento sconti/omaggi: {e}")
        return {
            'sconti': pd.DataFrame(),
            'omaggi': pd.DataFrame(),
            'totale_risparmiato': 0.0
        }


def elimina_fattura_completa(file_origine: str, user_id: str, supabase_client=None) -> Dict[str, Any]:
    """
    Elimina una fattura completa (tutti i prodotti) dal database.
    
    Args:
        file_origine: Nome del file XML della fattura
        user_id: ID utente (per controllo sicurezza)
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
    
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
        ristorante_id = st.session_state.get('ristorante_id') if 'session_state' in dir(st) else None
        query_count = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine)
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        count_response = query_count.execute()
        num_righe = len(count_response.data) if count_response.data else 0
        
        if num_righe == 0:
            return {"success": False, "error": "not_found", "righe_eliminate": 0}
        
        # Elimina dal database (con controllo user_id per sicurezza)
        query_delete = supabase_client.table("fatture").delete().eq("user_id", user_id).eq("file_origine", file_origine)
        if ristorante_id:
            query_delete = query_delete.eq("ristorante_id", ristorante_id)
        response = query_delete.execute()
        
        logger.info(f"❌ Fattura eliminata: {file_origine} ({num_righe} righe) da user {user_id}")
        
        return {"success": True, "error": None, "righe_eliminate": num_righe}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione fattura {file_origine} per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0}


def elimina_tutte_fatture(user_id: str, supabase_client=None) -> Dict[str, Any]:
    """
    Elimina TUTTE le fatture dell'utente dal database.
    
    Args:
        user_id: ID utente (per controllo sicurezza)
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int, "fatture_eliminate": int}
    """
    import time
    
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
        
        # Prima conta quante righe e fatture verranno eliminate
        ristorante_id = st.session_state.get('ristorante_id') if 'session_state' in dir(st) else None
        query_count = supabase_client.table("fatture").select("id, file_origine", count="exact").eq("user_id", user_id)
        if ristorante_id:
            query_count = query_count.eq("ristorante_id", ristorante_id)
        count_response = query_count.execute()
        num_righe = count_response.count if count_response.count else 0
        num_fatture = len(set([r['file_origine'] for r in count_response.data])) if count_response.data else 0
        
        logger.info(f"DELETE: user_id={user_id} ristorante_id={ristorante_id}, {num_fatture} fatture ({num_righe} righe)")
        
        if num_righe == 0:
            return {"success": False, "error": "no_data", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Esegui DELETE
        logger.info(f"🗑️ Esecuzione DELETE per user_id={user_id} ristorante_id={ristorante_id}...")
        
        try:
            query_delete = supabase_client.table("fatture").delete().eq("user_id", user_id)
            if ristorante_id:
                query_delete = query_delete.eq("ristorante_id", ristorante_id)
            response = query_delete.execute()
            logger.info(f"📊 DELETE executed for user_id={user_id}")
        except Exception as delete_error:
            logger.error(f"❌ ERRORE DELETE: {delete_error}")
            raise
        
        # Verifica post-delete
        query_verify = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id)
        if ristorante_id:
            query_verify = query_verify.eq("ristorante_id", ristorante_id)
        verify_response = query_verify.execute()
        num_rimaste = verify_response.count if verify_response.count else 0
        
        logger.info(f"✅ Verifica post-delete: {num_rimaste} righe rimaste")
        
        if num_rimaste > 0:
            logger.error(f"❌ DELETE FALLITA: {num_rimaste} righe ancora presenti per user {user_id}")
            
            # Tentativo 2: Re-DELETE
            try:
                logger.info(f"🔄 TENTATIVO 2: Ri-esecuzione DELETE per {num_rimaste} righe rimaste...")
                query_delete2 = supabase_client.table("fatture").delete().eq("user_id", user_id)
                if ristorante_id:
                    query_delete2 = query_delete2.eq("ristorante_id", ristorante_id)
                response2 = query_delete2.execute()
                
                # Verifica finale
                query_verify_final = supabase_client.table("fatture").select("id", count="exact").eq("user_id", user_id)
                if ristorante_id:
                    query_verify_final = query_verify_final.eq("ristorante_id", ristorante_id)
                verify_final = query_verify_final.execute()
                num_finali = verify_final.count if verify_final.count else 0
                
                if num_finali > 0:
                    logger.critical(f"🚨 DELETE FALLITA ANCHE DOPO RETRY: {num_finali} righe ancora presenti")
                    return {
                        "success": False, 
                        "error": f"Eliminazione parziale: {num_finali} righe non eliminate", 
                        "righe_eliminate": num_righe - num_finali, 
                        "fatture_eliminate": num_fatture
                    }
                else:
                    logger.info(f"✅ DELETE completata al secondo tentativo")
            except Exception as retry_error:
                logger.critical(f"❌ ERRORE nel retry DELETE: {retry_error}")
                return {
                    "success": False, 
                    "error": f"Delete fallita: {str(retry_error)}", 
                    "righe_eliminate": 0, 
                    "fatture_eliminate": 0
                }
        
        logger.warning(f"⚠️ ELIMINAZIONE MASSIVA SUCCESSO: {num_fatture} fatture ({num_righe} righe) da user {user_id}")
        
        return {"success": True, "error": None, "righe_eliminate": num_righe, "fatture_eliminate": num_fatture}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione massiva per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0, "fatture_eliminate": 0}


def audit_data_consistency(user_id: str, context: str = "unknown", supabase_client=None) -> Dict[str, Any]:
    """
    Verifica coerenza dati tra DB e Cache.
    
    Args:
        user_id: ID utente da verificare
        context: Contesto della chiamata (es. "post-delete", "post-upload")
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
    
    Returns:
        dict con dettagli verifica:
        - db_count: righe su Supabase
        - db_files: file unici su Supabase
        - cache_count: righe in cache
        - cache_files: file unici in cache
        - consistent: bool (True se DB = Cache)
    """
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return {"context": context, "user_id": user_id, "error": "connection_error", "consistent": False}
    
    result = {
        "context": context,
        "user_id": user_id,
        "db_count": 0,
        "db_files": 0,
        "cache_count": 0,
        "cache_files": 0,
        "consistent": False,
        "error": None
    }
    
    try:
        # Query diretta DB
        ristorante_id = st.session_state.get('ristorante_id') if 'session_state' in dir(st) else None
        query_audit = supabase_client.table("fatture").select("file_origine", count="exact").eq("user_id", user_id)
        if ristorante_id:
            query_audit = query_audit.eq("ristorante_id", ristorante_id)
        db_response = query_audit.execute()
        result["db_count"] = db_response.count if db_response.count else 0
        result["db_files"] = len(set([r['file_origine'] for r in db_response.data])) if db_response.data else 0
        
        # Query cache
        df_cached = carica_e_prepara_dataframe(user_id, supabase_client=supabase_client)
        result["cache_count"] = len(df_cached)
        result["cache_files"] = df_cached['FileOrigine'].nunique() if not df_cached.empty else 0
        
        # Verifica coerenza
        result["consistent"] = (result["db_count"] == result["cache_count"])
        
        if result["consistent"]:
            logger.info(f"✅ AUDIT OK [{context}]: DB={result['db_count']} Cache={result['cache_count']} (user={user_id})")
        else:
            logger.warning(f"⚠️ AUDIT FAIL [{context}]: DB={result['db_count']} ≠ Cache={result['cache_count']} (user={user_id})")
        
        return result
        
    except Exception as e:
        logger.exception(f"Errore audit per user {user_id}")
        result["error"] = str(e)
        return result


def get_fatture_stats(user_id: str, supabase_client=None) -> Dict[str, Any]:
    """
    Ottiene statistiche fatture da Supabase.
    
    Args:
        user_id: ID utente per filtro multi-tenancy
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
    
    Returns:
        dict con:
        - num_uniche: Numero fatture uniche (FileOrigine distinti)
        - num_righe: Numero totale righe/prodotti
        - success: bool (True se query riuscita)
    """
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return {"num_uniche": 0, "num_righe": 0, "success": False}
    
    try:
        file_unici_set = set()
        total_rows = 0
        page = 0
        page_size = 1000
        ristorante_id = st.session_state.get('ristorante_id') if 'session_state' in dir(st) else None
        
        while True:
            offset = page * page_size
            query_stats_page = supabase_client.table("fatture") \
                .select("file_origine", count='exact') \
                .eq("user_id", user_id)
            if ristorante_id:
                query_stats_page = query_stats_page.eq("ristorante_id", ristorante_id)
            response = query_stats_page.range(offset, offset + page_size - 1).execute()
            
            if not response.data:
                break
            
            for r in response.data:
                if r.get("file_origine"):
                    file_unici_set.add(r["file_origine"])
            
            if page == 0:
                total_rows = response.count if response.count else 0
            
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


__all__ = [
    'carica_e_prepara_dataframe',
    'ricalcola_prezzi_con_sconti',
    'calcola_alert',
    'carica_sconti_e_omaggi'
]
