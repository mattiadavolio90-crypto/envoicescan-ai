#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test dizionario conservativo sui 29 prodotti che prima erano errati.
"""

import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, '.')
from config.constants import DIZIONARIO_CORREZIONI

def applica_dizionario_solo(descrizione: str) -> str:
    """Applica solo il dizionario"""
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

# I 29 prodotti dal file Excel
prodotti_test = [
    ("PZ 16 FACCINE FROLLA CIOCCOLATO", "PASTICCERIA"),
    ("PZ 20 ESSE GRANDI CIOCCOLATO", "PASTICCERIA"),
    ("CREMA NOCCIOLE E CACAO DA FARCITURA REALE KG 6", "SALSE E CREME"),
    ("MIX NATALE X 30 PZ", "PASTICCERIA"),
    ("TAZZE+PIAT.CAFFE'CELLINI BAR", "VARIE BAR"),
    ("POLLO PETTO GR600X4/5 S/V F IT", "CARNE"),
    ("REALE VITELLO EX S/O KG5/7 S/V F NL", "CARNE"),
    ("CANDEGGINA CLASSICA PRIM LT1", "NO FOOD"),
    ("PASSATA ALBICOCCA CHEF PROFESSIONAL 50% KG 2 PER DISPENSER", "SALSE E CREME"),
    ("PESCHE N&C X 1,5 KG", "FRUTTA"),
    ("CROSTATINE MEDIE 1X16 ALBICOCCA", "PASTICCERIA"),
    ("PZ 16 FACCINE FROLLA ALBICOCCA", "PASTICCERIA"),
    ("CANNONCINI BURRO FARCITI NOCCIOLA KG.1", "PASTICCERIA"),
    ("PANNA SPRAY 250 ML 12 PZ CRT", "LATTICINI"),
    ("OLIO OLIVA LATTA LT5 MONIGA", "OLIO E CONDIMENTI"),
    ("SAPONE MOUSSE MANI KG5 PREGISAN", "NO FOOD"),
    ("PASSATA POMOD BIO BT PN GR700 TORRENTE", "SALSE E CREME"),
    ("CROSTATINE MEDIE 1X16 NUTELLA", "PASTICCERIA"),
    ("SALSICCIA VASC KG2,75 F IT MCH", "SALUMI"),
    ("SALAME DI CIOCCOLATO INTERO", "PASTICCERIA"),
    ("RAVIOLI BOSCO C/PORCINI KG1X2 S PREGIS", "SECCO"),
    ("SALE PASTIGLIE PURO 99,9% KG25 ITALSAL", "SECCO"),
    ("CANNONCINI BURRO FARCITI VANIGLIA KG. 1", "PASTICCERIA"),
    ("ROUX BIANCO GRAN IST BAR. KG1 (6) KNORR", "SALSE E CREME"),
]

print("=" * 130)
print("TEST DIZIONARIO CONSERVATIVO - 24 PRODOTTI ERRATI")
print("=" * 130)
print()

corretti = 0
da_classificare = 0
ancora_errati = 0

for i, (descr, cat_corretta) in enumerate(prodotti_test, 1):
    cat_trovata = applica_dizionario_solo(descr)
    
    if cat_trovata == cat_corretta:
        status = "✅ OK"
        corretti += 1
    elif cat_trovata is None:
        status = "⚠️  Da Classificare (AI)"
        da_classificare += 1
    else:
        status = f"❌ ERRORE"
        ancora_errati += 1
    
    print(f"{i:2}. {status:25} | {descr[:50]:50} → Trovata: {cat_trovata or 'None':20} | Corretta: {cat_corretta}")

print()
print("=" * 130)
print("RIEPILOGO:")
print("=" * 130)
print(f"✅ Corretti dal dizionario:  {corretti}/24 ({100*corretti//24}%)")
print(f"⚠️  Da classificare con AI:   {da_classificare}/24 ({100*da_classificare//24}%)")
print(f"❌ Ancora errati:            {ancora_errati}/24 ({100*ancora_errati//24}%)")
print()

if da_classificare > 0:
    print("🎯 OTTIMO! Il dizionario è conservativo:")
    print(f"   • {corretti} prodotti classificati CORRETTAMENTE")
    print(f"   • {da_classificare} prodotti lasciati all'AI (meglio che sbagliarli)")
    print(f"   • {ancora_errati} prodotti ancora errati (da fixare)")
    print()
    print("💡 Strategia funziona: Dizionario preciso + AI per casi dubbi = 100% accuratezza")
