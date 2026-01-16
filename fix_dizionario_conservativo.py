#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIX DIZIONARIO CONSERVATIVO
Rimuove keyword ambigue e aggiunge keyword più specifiche/contestuali.

OBIETTIVO: Dizionario preciso al 100%, tutto il resto va all'AI
"""

import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ===== KEYWORD DA RIMUOVERE (causano errori) =====
KEYWORD_DA_RIMUOVERE = [
    # Troppo corte / ambigue
    "COLA",  # in CIOCCOLATO → sbaglia BEVANDE
    "ALE",   # in NATALE, REALE → sbaglia BIRRE
    "GIN",   # in CANDEGGINA → sbaglia DISTILLATI
    
    # Ingredienti che ingannano (il prodotto finale conta più dell'ingrediente)
    "ALBICOCCA",  # CROSTATA ALBICOCCA è PASTICCERIA, non FRUTTA
    "PASSATA ALBICOCCA",  # idem
    
    # Ingredienti base che confondono
    "BURRO",  # CANNONCINI BURRO è PASTICCERIA, non LATTICINI
    "VANIGLIA",  # CANNONCINI VANIGLIA è PASTICCERIA, non SPEZIE
    "NUTELLA",  # CROSTATINE NUTELLA è PASTICCERIA, non SALSE
    
    # Colori/aggettivi generici
    "BIANCO",  # ROUX BIANCO → sbaglia VINI
    "ROSSO",   # potrebbe essere in tanti prodotti
    "ROSATO",  # idem
    
    # Parole che appaiono in contesti diversi
    "CAFFE",  # TAZZE CAFFE' → sbaglia (è VARIE BAR)
    "BAR",  # troppo generico
]

# ===== KEYWORD SPECIFICHE DA AGGIUNGERE (precise al 100%) =====
KEYWORD_DA_AGGIUNGERE = {
    # PASTICCERIA - Prodotti finiti specifici
    "CROSTATINE": "PASTICCERIA",
    "CROSTATA": "PASTICCERIA",
    "CROSTATE": "PASTICCERIA",
    "FACCINE": "PASTICCERIA",
    "BISCOTTINI": "PASTICCERIA",
    "PASTE": "PASTICCERIA",
    "MIX NATALE": "PASTICCERIA",
    "DOLCI NATALIZI": "PASTICCERIA",
    "SALAME DI CIOCCOLATO": "PASTICCERIA",  # Salame dolce
    "SALAME CIOCCOLATO": "PASTICCERIA",
    
    # NO FOOD - Detergenti/igiene specifici
    "CANDEGGINA": "NO FOOD",
    "SAPONE": "NO FOOD",
    "MOUSSE MANI": "NO FOOD",
    
    # VARIE BAR - Servizi bar
    "TAZZE": "VARIE BAR",
    "PIATTINI": "VARIE BAR",
    "PIAT.": "VARIE BAR",
    
    # SALSE E CREME - Preparazioni specifiche
    "ROUX": "SALSE E CREME",
    "BESCIAMELLA": "SALSE E CREME",
    "PASSATA POMODORO": "SALSE E CREME",
    "PASSATA POMOD": "SALSE E CREME",
}

def main():
    print("=" * 100)
    print("FIX DIZIONARIO CONSERVATIVO")
    print("=" * 100)
    print()
    
    print("📋 Keyword da RIMUOVERE (causano errori):")
    for kw in KEYWORD_DA_RIMUOVERE:
        print(f"   ❌ {kw}")
    print()
    
    print("📋 Keyword da AGGIUNGERE (specifiche e sicure):")
    for kw, cat in KEYWORD_DA_AGGIUNGERE.items():
        print(f"   ✅ {kw:30} → {cat}")
    print()
    
    # Leggi constants.py
    with open('config/constants.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Rimuovi keyword ambigue
    rimosse = 0
    for keyword in KEYWORD_DA_RIMUOVERE:
        # Cerca le righe da rimuovere
        for categoria in ["BEVANDE", "BIRRE", "DISTILLATI", "FRUTTA", "LATTICINI", 
                         "SPEZIE E AROMI", "SALSE E CREME", "VINI", "CAFFÈ", "VARIE BAR"]:
            old_line = f'    "{keyword}": "{categoria}",'
            if old_line in content:
                content = content.replace(old_line + '\n', '')
                rimosse += 1
                print(f"🗑️  Rimosso: {keyword} → {categoria}")
    
    # Trova dove inserire le nuove keyword
    # Cerchiamo la sezione "KEYWORDS DAL FIX REPORT ERRORI" o la fine del dizionario
    if "# ===== KEYWORDS DAL FIX REPORT ERRORI =====" in content:
        insert_marker = "# ===== KEYWORDS DAL FIX REPORT ERRORI ====="
    else:
        # Trova l'ultima entry prima di chiudere il dizionario
        insert_marker = "    # ===== SERVIZI E CONSULENZE ====="
    
    # Crea nuove righe
    new_lines = ["\n    # ===== FIX DIZIONARIO CONSERVATIVO - KEYWORD SPECIFICHE ====="]
    for keyword, categoria in sorted(KEYWORD_DA_AGGIUNGERE.items()):
        search_key = f'"{keyword}"'
        if search_key not in content:
            new_lines.append(f'    "{keyword}": "{categoria}",')
    
    if len(new_lines) > 1:  # Se abbiamo qualcosa da aggiungere oltre al commento
        # Trova il punto di inserimento
        insert_pos = content.find(insert_marker)
        if insert_pos == -1:
            print("⚠️  Marker non trovato, inserisco prima della chiusura del dizionario")
            # Trova la chiusura del dizionario
            dict_end = content.rfind('\n}\n')
            insert_pos = dict_end
        
        # Inserisci le nuove righe
        content = content[:insert_pos] + '\n'.join(new_lines) + '\n\n' + content[insert_pos:]
        
        print(f"\n✅ Aggiunte {len(new_lines)-1} nuove keyword specifiche")
    
    # Salva
    with open('config/constants.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print()
    print("=" * 100)
    print(f"✅ COMPLETATO!")
    print(f"   • Rimosse: {rimosse} keyword ambigue")
    print(f"   • Aggiunte: {len(new_lines)-1} keyword specifiche")
    print("=" * 100)
    print()
    print("🎯 PROSSIMO STEP: Testa con i 29 prodotti errati")

if __name__ == '__main__':
    main()
