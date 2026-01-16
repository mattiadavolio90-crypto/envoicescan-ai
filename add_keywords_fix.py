#!/usr/bin/env python3
"""
Script per aggiungere le keywords mancanti dal report di analizza_errori.py
Basato sui 39 prodotti non categorizzati.
"""

import os
import sys

# Keywords mancanti dal report di analisi
keywords_da_aggiungere = {
    # PASTICCERIA - Dolci fine (Romanoni + Dolcemagic)
    "CANNOLO": "PASTICCERIA",
    "CANNOLI": "PASTICCERIA",  # già presente, ma assicuriamo
    "ARAGOSTINE": "PASTICCERIA",
    "ARAGONOSTINE": "PASTICCERIA",
    "OCCHI DI BUE": "PASTICCERIA",
    "OCCHI BUE": "PASTICCERIA",
    "STRUDEL": "PASTICCERIA",
    "FROLLA": "PASTICCERIA",
    "FROLLA MISTA": "PASTICCERIA",
    "MISTO FROLLA": "PASTICCERIA",
    "CANESTRELLI": "PASTICCERIA",
    "CANES": "PASTICCERIA",
    "CANESTRELLO": "PASTICCERIA",
    "GENOVESI": "PASTICCERIA",
    "CANNONCINI": "PASTICCERIA",
    "CANNONCINO": "PASTICCERIA",
    "MISTI": "PASTICCERIA",  # In context di dolci
    "ESSENCE": "PASTICCERIA",
    "ESSE": "PASTICCERIA",  # In context di dolci (tipo ESSE GIGANTI)
    "ESSE GIGANTI": "PASTICCERIA",
    "SICILIANI CANNOLO": "PASTICCERIA",
    "SICILIANO CANNOLO": "PASTICCERIA",
    
    # LATTICINI - Formaggi non categorizzati (Gioiella)
    "BRIE": "LATTICINI",
    "CAPRINO": "LATTICINI",
    "CAPRINO VACCINO": "LATTICINI",
    "CAPRA": "LATTICINI",
    
    # BEVANDE - Bevande non convenzionali (Gioiella)
    "CAPPUCCINO LOVERS": "BEVANDE",
    "CAPPUCCINO": "BEVANDE",
    "BEVANDA DI SOJA": "BEVANDE",
    "BEVANDA SOJA": "BEVANDE",
    "SOIA": "BEVANDE",
    "SOJA": "BEVANDE",
    
    # FRUTTA/VERDURE - Prodotti freschi (vari)
    "CARCIOFI": "FRUTTA",  # Tecnicamente verdura, ma nella categoria FRUTTA non abbiamo categorizzato bene
    "CARCIOFO": "FRUTTA",
    "EDAMINO": "VERDURE",
    "EDAMAME": "VERDURE",
    
    # PRODOTTI DA FORNO - Piadine (Greg SRL)
    "PIADINA": "PRODOTTI DA FORNO",
    "PIADINE": "PRODOTTI DA FORNO",
    
    # CARNE - Carni rare (A.I.A.)
    "NOCE BOVINO": "CARNE",
    "NOCE BOV": "CARNE",
    "PARMA": "CARNE",  # S/O KG 7/8 - Prosciutto di Parma
    
    # SAVOIARDI - Biscotti (Pregis)
    "SAVOIARDI": "PASTICCERIA",
    "SAVOIARDO": "PASTICCERIA",
    
    # CREMA - Farcitura (Arte Bianca)
    "CREMA GIANDUIA": "SALSE E CREME",
    "CREMA GIANDUJA": "SALSE E CREME",
    "GIANDUIA": "SALSE E CREME",
    "GIANDUJA": "SALSE E CREME",
    "FARCITURA": "SALSE E CREME",
    "FARCITURA CACAO": "SALSE E CREME",
    
    # SPESE GENERALI - Voci speciali (S.I.P.A.)
    "PREMI": "SERVIZI E CONSULENZE",  # PREMI 2025 -> Spese
    "SPESE DI BOLLO": "SERVIZI E CONSULENZE",  # Tassa
    "BOLLO SPESA": "SERVIZI E CONSULENZE",
    
    # DETERGENTI - Prodotti pulizia (Pregis)
    "RIF SAN PREGISAN": "NO FOOD",
    "PREGISAN": "NO FOOD",
    "LAVASTOV": "NO FOOD",
    "BRILL": "NO FOOD",
    "MISTER X": "NO FOOD",
}

def main():
    constants_path = "config/constants.py"
    
    if not os.path.exists(constants_path):
        print(f"❌ File {constants_path} non trovato")
        sys.exit(1)
    
    # Leggi il file
    with open(constants_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Trova l'ultimo elemento del DIZIONARIO prima della chiusura
    dizionario_marker = 'DIZIONARIO_CORREZIONI = {'
    if dizionario_marker not in content:
        print("❌ DIZIONARIO_CORREZIONI non trovato")
        sys.exit(1)
    
    # Trova dove comincia il dizionario
    start_idx = content.find(dizionario_marker)
    
    # Trova la chiusura del dizionario (cerca } seguito da nuovo statement)
    # Cerchiamo la fine del dict prima del prossimo statement
    remaining_content = content[start_idx:]
    
    # Cerchiamo il punto dove termina il dict - la riga con soli }
    dict_end_search = remaining_content.find('\n}\n')
    if dict_end_search == -1:
        dict_end_search = remaining_content.rfind('}')
    
    insertion_point = start_idx + dict_end_search
    
    # Crea le nuove linee da inserire
    new_lines = []
    for keyword, categoria in sorted(keywords_da_aggiungere.items()):
        # Controlla che non sia già presente
        search_key = f'"{keyword}"'
        if search_key in content:
            print(f"⏭️  Keyword già presente: {keyword}")
            continue
        new_lines.append(f'    "{keyword}": "{categoria}",')
    
    if not new_lines:
        print("⚠️  Nessuna nuova keyword da aggiungere")
        return
    
    # Inserisci prima della chiusura
    new_content = content[:insertion_point] + '\n\n    # ===== KEYWORDS DAL FIX REPORT ERRORI =====\n' + '\n'.join(new_lines) + '\n' + content[insertion_point:]
    
    # Salva il file
    with open(constants_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ Aggiunte {len(new_lines)} nuove keywords al DIZIONARIO_CORREZIONI")
    for line in new_lines:
        print(f"  ✓ {line.strip()}")

if __name__ == '__main__':
    main()
