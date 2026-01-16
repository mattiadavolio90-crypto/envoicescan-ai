#!/usr/bin/env python3
"""
Script per analizzare quali prodotti si classificano con il nuovo dizionario
"""

import os
import sys
from pathlib import Path

# Aggiungi il path al progetto
sys.path.insert(0, str(Path(__file__).parent))

from config.constants import DIZIONARIO_CORREZIONI, TUTTE_LE_CATEGORIE

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

# I 39 prodotti non categorizzati dal report
prodotti_da_classificare = [
    "CARCIOFI CUORE O.GIR VT PN KG2,9 ITALCAR",
    "SAVOIARDI VICENZOVO GR100X24 (KG2,4)",
    "RIF SAN PREGISAN LIQ LAVASTOV KG12",
    "BRILL X PREGISAN BRILLANTANTE LIQ KG5",
    "MISTER X PREGISAN LIQ STOV MANO KG5",
    "NOCE BOV ADULTO KG3,5/5 S/V F TERNERA",
    "CREMA GIANDUIA FONDENTE DA FARCITURA CACAO 25% KG 6",
    "MISTO FROLLA 1,5 KG",
    "CANES.GENOVESI GRANDI X 1,5 KG",
    "CANNONCINI MISTI X 18 PZ",
    "STRUDEL",
    "OCCHI DI BUE ALBIC. PZ 17",
    "OCCHI DI BUE CIOCC. PZ 17",
    "KG 1.5 ARAGOSTINE CREMA GIANDUJA",
    "KG 1.5 ARAGOSTINE PISTACCHIO",
    "PZ 20 ESSE GIGANTI",
    "SICILIANI CANNOLO M. GIANDUIA",
    "SICILIANI CANNOLO M. AVORIO",
    "SICILIANO CANNOLO M. PISTACCHIO",
    "KG 1.5 ARAGOSTINE CREMA GIANDUJA",
    "KG 1.5 ARAGOSTINE PISTACCHIO",
    "OCCHI DI BUE ALBIC. PZ 17",
    "PARMA S/O KG 7/8 ADD. CTX1 NGR",
    "PREMI 2025",
    "SPESE DI BOLLO SPESA",
    "EDAMINO",
    "CAPPUCCINO LOVERS BEVANDA DI SOJA LT1",
    "CAPRINO VACCINO 80 GR X 10 PZ",
    "CAPPUCCINO LOVERS BEVANDA DI SOJA LT1",
    "CAPPUCCINO LOVERS BEVANDA DI SOJA LT1",
    "BRIE KG 1 CIRCA",
    "EDAMINO",
    "CAPPUCCINO LOVERS BEVANDA DI SOJA LT1",
    "CAPRINO VACCINO 80 GR X 10 PZ",
    "CAPPUCCINO LOVERS BEVANDA DI SOJA LT1",
    "CAPPUCCINO LOVERS BEVANDA DI SOJA LT1",
    "BRIE KG 1 CIRCA",
    "PIADINA CLASSICA CT. DA 9 CONF. X 6 PZ",
    "PIADINA CLASSICA CT. DA 9 CONF. X 6 PZ",
]

def main():
    print("=" * 100)
    print("TEST CLASSIFICAZIONE CON NUOVO DIZIONARIO")
    print("=" * 100)
    print()
    
    # Rimuovi duplicati ma mantieni ordine
    seen = set()
    prodotti_unici = []
    for p in prodotti_da_classificare:
        if p not in seen:
            prodotti_unici.append(p)
            seen.add(p)
    
    classificati = 0
    non_classificati = []
    
    print(f"Analizzando {len(prodotti_unici)} prodotti unici...")
    print()
    
    for i, descr in enumerate(prodotti_unici, 1):
        categoria = applica_dizionario_solo(descr)
        
        if categoria:
            status = "✅"
            classificati += 1
        else:
            status = "⚠️"
            non_classificati.append(descr)
        
        print(f"{i:2}. {status} {descr[:60]:60} → {categoria or 'NON CLASSIFICATO'}")
    
    print()
    print("=" * 100)
    print(f"✅ CLASSIFICATI: {classificati}/{len(prodotti_unici)} ({100*classificati//len(prodotti_unici)}%)")
    print(f"⚠️  NON CLASSIFICATI: {len(non_classificati)}/{len(prodotti_unici)}")
    print("=" * 100)
    
    if non_classificati:
        print()
        print("PRODOTTI CHE RICHIEDONO ANCORA CLASSIFICAZIONE:")
        print("-" * 100)
        for p in non_classificati:
            print(f"  • {p}")
        
        print()
        print("SUGGERIMENTO: Questi prodotti richiedono:")
        print("  1. Aggiunta di keywords specifiche al dizionario")
        print("  2. O classificazione manuale via 'Avvia AI'")

if __name__ == '__main__':
    main()
