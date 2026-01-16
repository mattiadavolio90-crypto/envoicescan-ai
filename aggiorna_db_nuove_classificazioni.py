#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script per aggiornare il database con le nuove classificazioni basate sul dizionario aggiornato.
"""

import os
import sys
import json
from pathlib import Path
import io

# Fix encoding per Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Aggiungi il path al progetto
sys.path.insert(0, str(Path(__file__).parent))

from config.constants import DIZIONARIO_CORREZIONI
import streamlit as st

# Importa i secrets
try:
    from config.secrets import SUPABASE_URL, SUPABASE_KEY
except ImportError:
    # Prova da streamlit secrets
    try:
        SUPABASE_URL = st.secrets["supabase"]["url"]
        SUPABASE_KEY = st.secrets["supabase"]["key"]
    except:
        print("❌ Impossibile caricare SUPABASE_URL e SUPABASE_KEY")
        sys.exit(1)

# Importa Supabase
from supabase import create_client

def applica_dizionario_solo(descrizione: str) -> str:
    """Applica solo il dizionario senza AI fallback"""
    if not descrizione or not isinstance(descrizione, str):
        return None
    
    desc_upper = descrizione.upper()
    
    # Ordina keyword per lunghezza decrescente
    sorted_keywords = sorted(DIZIONARIO_CORREZIONI.items(), 
                            key=lambda x: len(x[0]), 
                            reverse=True)
    
    for keyword, categoria in sorted_keywords:
        if keyword in desc_upper:
            return categoria
    
    return None

def aggiorna_database():
    """Aggiorna il database con le nuove classificazioni"""
    
    print("=" * 100)
    print("AGGIORNAMENTO DATABASE - NUOVE CLASSIFICAZIONI")
    print("=" * 100)
    print()
    
    try:
        # Connetti a Supabase
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connesso a Supabase")
    except Exception as e:
        print(f"❌ Errore di connessione: {e}")
        return
    
    # Carica i prodotti non categorizzati
    print("📥 Caricamento prodotti non categorizzati...")
    
    try:
        response = supabase.table('fatture').select('id, descrizione, categoria').execute()
        all_rows = response.data if response.data else []
        
        # Filtra quelli "Da Classificare"
        non_categorizzati = [
            r for r in all_rows 
            if not r.get('categoria') or r.get('categoria') in ['Da Classificare', None, '']
        ]
        
        print(f"✅ Caricate {len(non_categorizzati)} righe non categorizzate")
        print()
        
    except Exception as e:
        print(f"❌ Errore nel caricamento: {e}")
        return
    
    # Classifica e aggiorna
    aggiornati_count = 0
    gia_cat_count = 0
    errori = []
    
    print("=" * 100)
    print("CLASSIFICAZIONE E AGGIORNAMENTO")
    print("=" * 100)
    print()
    
    for i, row in enumerate(non_categorizzati, 1):
        descr = row.get('descrizione', '').upper()
        row_id = row.get('id')
        cat_attuale = row.get('categoria')
        
        # Applica il dizionario
        categoria_nuova = applica_dizionario_solo(row.get('descrizione', ''))
        
        if categoria_nuova:
            try:
                supabase.table('fatture').update({'categoria': categoria_nuova}).eq('id', row_id).execute()
                print(f"{i:3}. ✅ {descr[:50]:50} → {categoria_nuova}")
                aggiornati_count += 1
            except Exception as e:
                print(f"{i:3}. ❌ {descr[:50]:50} - ERRORE: {e}")
                errori.append({'id': row_id, 'descrizione': descr, 'errore': str(e)})
        else:
            print(f"{i:3}. ⏭️  {descr[:50]:50} - Nessuna categoria trovata")
    
    print()
    print("=" * 100)
    print("RIEPILOGO")
    print("=" * 100)
    print(f"✅ Aggiornati: {aggiornati_count}")
    print(f"❌ Errori: {len(errori)}")
    print()
    
    if errori:
        print("ERRORI RISCONTRATI:")
        for err in errori:
            print(f"  - {err['descrizione']}: {err['errore']}")

if __name__ == '__main__':
    aggiorna_database()
