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

logger = logging.getLogger(__name__)


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
    # Inizializza client Supabase
    if supabase_client is None:
        try:
            from supabase import create_client
            supabase_client = create_client(
                st.secrets["supabase"]["url"],
                st.secrets["supabase"]["key"]
            )
        except Exception as e:
            logger.critical(f"❌ CRITICAL: Impossibile inizializzare Supabase: {e}")
            return pd.DataFrame()
    
    logger.info(f"📊 LOAD START: user_id={user_id}, force_refresh={force_refresh}")
    print(f"🔍 DEBUG: INIZIO carica_e_prepara_dataframe(user_id={user_id}, force_refresh={force_refresh})")
    
    dati = []
    
    # 🔥 CARICA DA SUPABASE
    if supabase_client is not None:
        print("🔍 DEBUG: Tentativo caricamento da Supabase...")
        try:
            response = supabase_client.table("fatture").select("*", count="exact").eq("user_id", user_id).execute()
            print(f"🔍 DEBUG: Supabase response.count = {response.count}")
            logger.info(f"📊 CARICAMENTO: user_id={user_id} ha {response.count} righe su Supabase")
            
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
            
            if len(dati) > 0:
                logger.info(f"✅ LOAD SUCCESS: {len(dati)} righe caricate da Supabase per user_id={user_id}")
                print(f"✅ DEBUG: Caricati {len(dati)} record da Supabase")
                df_result = pd.DataFrame(dati)
                
                # 🔧 NORMALIZZA CATEGORIA: Converti NULL/None/vuoti in NaN per uniformità
                if 'Categoria' in df_result.columns:
                    # Log PRIMA della normalizzazione
                    null_count_before = df_result['Categoria'].isna().sum()
                    none_count_before = (df_result['Categoria'] == None).sum()
                    empty_count_before = (df_result['Categoria'] == '').sum()
                    logger.info(f"🔍 PRE-NORMALIZZAZIONE: NA={null_count_before}, None={none_count_before}, vuoti={empty_count_before}")
                    
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
                        'OLIO': 'OLIO E CONDIMENTI'
                    }
                    
                    righe_migrate = 0
                    for vecchio, nuovo in mapping_categorie.items():
                        mask = df_result['Categoria'] == vecchio
                        if mask.any():
                            df_result.loc[mask, 'Categoria'] = nuovo
                            righe_migrate += mask.sum()
                            logger.info(f"🔄 MIGRAZIONE AUTO: '{vecchio}' → '{nuovo}' ({mask.sum()} righe)")
                    
                    if righe_migrate > 0:
                        logger.info(f"✅ MIGRAZIONE COMPLETATA: {righe_migrate} righe aggiornate")
                    
                    # Log DOPO la normalizzazione
                    null_count_after = df_result['Categoria'].isna().sum()
                    empty_count = (df_result['Categoria'].astype(str).str.strip() == '').sum()
                    logger.info(f"🔧 POST-NORMALIZZAZIONE: {null_count_after} NULL + {empty_count} vuote")
                    print(f"🔧 DEBUG: Categorie - {null_count_after} NULL + {empty_count} vuote")
                    
                    # 🎯 FIX CELLE BIANCHE DEFINITIVO: Riempie NA E vuoti con "Da Classificare"
                    # Step 1: fillna per NULL/pd.NA
                    df_result['Categoria'] = df_result['Categoria'].fillna("Da Classificare")
                    
                    # Step 2: converti stringhe vuote/None in "Da Classificare"
                    df_result['Categoria'] = df_result['Categoria'].apply(
                        lambda x: "Da Classificare" if x is None or str(x).strip() == '' else x
                    )
                    
                    # Verifica finale
                    da_class_count = (df_result['Categoria'] == 'Da Classificare').sum()
                    logger.info(f"✅ CELLE BIANCHE RISOLTE: {da_class_count} celle mostrano 'Da Classificare'")
                    print(f"✅ DEBUG: {da_class_count} celle con 'Da Classificare' (pronte per AI)")
                
                print(f"✅ DEBUG: DataFrame shape={df_result.shape}, files={df_result['FileOrigine'].nunique() if not df_result.empty else 0}")
                return df_result
            else:
                logger.info(f"ℹ️ LOAD EMPTY: Nessuna fattura per user_id={user_id}")
                print("ℹ️ DEBUG: Supabase vuoto (nessuna fattura per questo utente)")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ LOAD ERROR: Errore Supabase per user_id={user_id}: {e}")
            print(f"❌ DEBUG: Errore Supabase: {e}")
            logger.exception("Errore query Supabase")
            return pd.DataFrame()
    
    # Supabase non configurato (impossibile in produzione)
    logger.critical("❌ CRITICAL: Supabase client non inizializzato!")
    print("❌ DEBUG: Supabase non configurato")
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
    # Inizializza client Supabase
    if supabase_client is None:
        try:
            from supabase import create_client
            supabase_client = create_client(
                st.secrets["supabase"]["url"],
                st.secrets["supabase"]["key"]
            )
        except Exception as e:
            logger.error(f"❌ Impossibile inizializzare Supabase: {e}")
            return 0
    
    try:
        # Leggi tutte le fatture dell'utente
        response = supabase_client.table("fatture") \
            .select("id, descrizione, quantita, prezzo_unitario, totale_riga") \
            .eq("user_id", user_id) \
            .execute()
        
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
    NO FOOD È F&B! (tovaglioli, piatti usa e getta, pellicole = materiali consumo ristorante)
    
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
    # TUTTO IL RESTO È F&B (incluso NO FOOD!)
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
            from supabase import create_client
            supabase_client = create_client(
                st.secrets["supabase"]["url"],
                st.secrets["supabase"]["key"]
            )
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
        
        # Query righe del cliente NEL PERIODO SPECIFICATO
        response = supabase_client.table('fatture')\
            .select('id, descrizione, categoria, fornitore, prezzo_unitario, quantita, totale_riga, data_documento, file_origine')\
            .eq('user_id', user_id)\
            .gte('data_documento', data_inizio)\
            .lte('data_documento', data_fine)\
            .execute()
        
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
        # TUTTO IL RESTO È F&B (incluso NO FOOD!)
        # NO FOOD contiene materiali di consumo ristorante (tovaglioli, piatti, pellicole, etc.)
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


__all__ = [
    'carica_e_prepara_dataframe',
    'ricalcola_prezzi_con_sconti',
    'calcola_alert',
    'carica_sconti_e_omaggi'
]
