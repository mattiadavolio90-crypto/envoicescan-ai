#!/usr/bin/env python3
"""
Script per riclassificare i 39 prodotti non categorizzati
usando il dizionario appena aggiornato.
"""

import os
import sys
from pathlib import Path

# Aggiungi il path al progetto
sys.path.insert(0, str(Path(__file__).parent))

from config.constants import DIZIONARIO_CORREZIONI, TUTTE_LE_CATEGORIE
from services.db_service import get_supabase
from services.ai_service import applica_correzioni_dizionario

def riclassifica_non_categorizzati():
    """Riclassifica i prodotti non categorizzati usando il nuovo dizionario"""
    
    supabase = get_supabase()
    
    print("=" * 80)
    print("RICLASSIFICAZIONE PRODOTTI NON CATEGORIZZATI")
    print("=" * 80)
    print()
    
    # Query i prodotti non categorizzati
    print("📥 Caricamento prodotti non categorizzati...")
    
    try:
        response = supabase.table('fatture').select('*').or_(
            'categoria.eq.Da Classificare,categoria.is.NULL,categoria.eq.'
        ).execute()
        
        all_rows = response.data if response.data else []
        non_categorizzati = [
            r for r in all_rows 
            if not r.get('categoria') or r.get('categoria') in ['Da Classificare', None, '']
        ]
        
        print(f"✅ Caricati {len(non_categorizzati)} prodotti non categorizzati")
        print()
        
    except Exception as e:
        print(f"❌ Errore nel caricamento: {e}")
        return
    
    # Analizza ogni prodotto
    risultati = {
        'classificati': [],
        'rimasti_non_cat': [],
        'errori': []
    }
    
    print("=" * 80)
    print("ANALISI PRODOTTI")
    print("=" * 80)
    print()
    
    for i, row in enumerate(non_categorizzati, 1):
        descr = row.get('descrizione_riga', '').upper()
        row_id = row.get('id')
        
        # Applica il dizionario
        categoria_trovata = applica_correzioni_dizionario(descr)
        
        status = "✅" if categoria_trovata and categoria_trovata != "Da Classificare" else "⚠️"
        
        print(f"{i}. {status} {descr[:60]:60} → {categoria_trovata}")
        
        if categoria_trovata and categoria_trovata != "Da Classificare":
            risultati['classificati'].append({
                'id': row_id,
                'descrizione': descr,
                'categoria': categoria_trovata
            })
        else:
            risultati['rimasti_non_cat'].append({
                'id': row_id,
                'descrizione': descr
            })
    
    print()
    print("=" * 80)
    print("STATISTICHE")
    print("=" * 80)
    print()
    print(f"✅ Nuovi classificati: {len(risultati['classificati'])} prodotti")
    print(f"⚠️  Rimasti non categorizzati: {len(risultati['rimasti_non_cat'])} prodotti")
    print(f"❌ Errori: {len(risultati['errori'])} prodotti")
    print()
    
    if risultati['classificati']:
        print("=" * 80)
        print("AGGIORNAMENTO DATABASE")
        print("=" * 80)
        print()
        
        aggiornati = 0
        for item in risultati['classificati']:
            try:
                supabase.table('fatture').update({
                    'categoria': item['categoria']
                }).eq('id', item['id']).execute()
                aggiornati += 1
                print(f"✓ Aggiornato: {item['descrizione'][:50]:50} → {item['categoria']}")
            except Exception as e:
                print(f"✗ Errore: {item['descrizione'][:50]:50} - {e}")
        
        print()
        print(f"✅ Aggiornati {aggiornati}/{len(risultati['classificati'])} prodotti nel database")
    
    if risultati['rimasti_non_cat']:
        print()
        print("=" * 80)
        print("PRODOTTI CHE RICHIEDONO CLASSIFICAZIONE MANUALE")
        print("=" * 80)
        print()
        for item in risultati['rimasti_non_cat']:
            print(f"• {item['descrizione']}")

if __name__ == '__main__':
    riclassifica_non_categorizzati()
