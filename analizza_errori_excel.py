#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analizza i 29 prodotti errati nel file Excel.
Identifica il pattern di errore e le keyword che causano il mismatch.
"""

import pandas as pd
import sys
import io
from collections import defaultdict

# Fix encoding per Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, '.')
from config.constants import DIZIONARIO_CORREZIONI

file = 'dettaglio_20260116_1237.xlsx'
df = pd.read_excel(file)

print("=" * 130)
print("ANALISI ERRORI DI CATEGORIZZAZIONE - 29 PRODOTTI")
print("=" * 130)
print()

# Mapping categoria corretta (manuali - quello che dovrebbe essere)
categoria_corretta_map = {
    "PZ 16 FACCINE FROLLA CIOCCOLATO": "PASTICCERIA",  # Dolce
    "PZ 20 ESSE GRANDI CIOCCOLATO": "PASTICCERIA",  # Dolce
    "CREMA NOCCIOLE E CACAO DA FARCITURA REALE KG 6": "SALSE E CREME",  # Crema (non BIRRE)
    "MIX NATALE X 30 PZ": "PASTICCERIA",  # Dolci (non BIRRE)
    "TAZZE+PIAT.CAFFE'CELLINI BAR": "VARIE BAR",  # Servizio bar (non CAFFÈ)
    "POLLO PETTO GR600X4/5 S/V F IT": "CARNE",  # OK
    "REALE VITELLO EX S/O KG5/7 S/V F NL": "CARNE",  # OK
    "CANDEGGINA CLASSICA PRIM LT1": "NO FOOD",  # Detersivo (non DISTILLATI)
    "PASSATA ALBICOCCA CHEF PROFESSIONAL 50% KG 2 PER DISPENSER": "SALSE E CREME",  # Salsa (non FRUTTA)
    "PESCHE N&C X 1,5 KG": "FRUTTA",  # OK
    "CROSTATINE MEDIE 1X16 ALBICOCCA": "PASTICCERIA",  # Dolce (non FRUTTA)
    "PZ 16 FACCINE FROLLA ALBICOCCA": "PASTICCERIA",  # Dolce (non FRUTTA)
    "CANNONCINI BURRO FARCITI NOCCIOLA KG.1": "PASTICCERIA",  # Dolce (non LATTICINI)
    "PANNA SPRAY 250 ML 12 PZ CRT": "LATTICINI",  # OK (panna è latticino)
    "OLIO OLIVA LATTA LT5 MONIGA": "OLIO E CONDIMENTI",  # OK
    "SAPONE MOUSSE MANI KG5 PREGISAN": "NO FOOD",  # Sapone/igiene (non PASTICCERIA)
    "PASSATA POMOD BIO BT PN GR700 TORRENTE": "SALSE E CREME",  # Salsa (non OK)
    "CROSTATINE MEDIE 1X16 NUTELLA": "PASTICCERIA",  # Dolce (non SALSE E CREME)
    "SALSICCIA VASC KG2,75 F IT MCH": "SALUMI",  # OK
    "SALAME DI CIOCCOLATO INTERO": "SALUMI",  # OK ma cioccolato confonde
    "RAVIOLI BOSCO C/PORCINI KG1X2 S PREGIS": "SECCO",  # OK (pasta)
    "SALE PASTIGLIE PURO 99,9% KG25 ITALSAL": "SECCO",  # OK
    "CANNONCINI BURRO FARCITI VANIGLIA KG. 1": "PASTICCERIA",  # Dolce (non SPEZIE E AROMI)
    "ROUX BIANCO GRAN IST BAR. KG1 (6) KNORR": "SALSE E CREME",  # Roux è salsa/condimento (non VINI)
}

# Analizza
errori_count = 0
errori_per_tipo = defaultdict(list)
keyword_problematici = defaultdict(int)

print("LISTA ERRORI DETTAGLIATA:")
print("-" * 130)
print()

for idx, row in df.iterrows():
    descr = row['Descrizione']
    cat_assegnata = row['Categoria']
    cat_corretta = categoria_corretta_map.get(descr, "???")
    
    if cat_assegnata != cat_corretta and cat_corretta != "???":
        errori_count += 1
        
        # Analizza quale keyword ha causato l'errore
        desc_upper = descr.upper()
        keywords_found = []
        for keyword, cat in sorted(DIZIONARIO_CORREZIONI.items(), key=lambda x: len(x[0]), reverse=True):
            if keyword in desc_upper:
                keywords_found.append((keyword, cat))
                if cat == cat_assegnata:  # Questo è il colpevole!
                    keyword_problematici[f"{keyword} → {cat}"] += 1
                    break
        
        status = f"{errori_count:2}. ❌"
        print(f"{status}")
        print(f"   Descrizione: {descr[:80]}")
        print(f"   Assegnata:   {cat_assegnata}")
        print(f"   Corretta:    {cat_corretta}")
        print(f"   Keywords:    {keywords_found[:3] if keywords_found else 'Nessuna'}")
        print()
        
        errori_per_tipo[f"{cat_assegnata} → {cat_corretta}"].append(descr)

print()
print("=" * 130)
print("RIEPILOGO ERRORI PER TIPO DI MISMATCH")
print("=" * 130)
print()

for key, prodotti in sorted(errori_per_tipo.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"🔴 {key}: {len(prodotti)} prodotti")
    for p in prodotti:
        print(f"   • {p[:100]}")
    print()

print("=" * 130)
print("KEYWORD PROBLEMATICHE (che causano errori)")
print("=" * 130)
print()

for keyword_cat, count in sorted(keyword_problematici.items(), key=lambda x: x[1], reverse=True):
    print(f"⚠️  {keyword_cat}: {count} errori causati")

print()
print(f"TOTALE ERRORI: {errori_count}/29")
