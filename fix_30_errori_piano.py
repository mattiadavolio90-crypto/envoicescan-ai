#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script per correggere le keywords problematiche nel dizionario.
Elimina i 30 errori critici mantenendo la copertura.
"""

# KEYWORDS DA RIMUOVERE (troppo generiche, causano falsi positivi)
RIMUOVI_KEYWORDS = [
    'RUM',  # Match in "GOLIA F**RUM**TA" → DISTILLATI invece di SHOP
    'NATURALE',  # Match in "YOGURT NATURALE" → ACQUA invece di LATTICINI
    'CAPPUCCINO',  # Match in "TAZZA CAPPUCCINO" → BEVANDE invece di NO FOOD
    'MELA',  # Match in "PAIN AU CHOCOLAT **MELA**NGE" → FRUTTA
    'AGLIO',  # Match in "CONGU**AGLIO**" → VERDURE
    'CHAMPAGNE',  # Match in "GREMBIULE CHAMPAGNE" → VINI
    'SALE',  # Troppo generico: "SALE PASTIGLIE", "RIBOLLA ... **SALE**T"
    'MISTI',  # Match in "MISTICANZA" → PASTICCERIA invece di VERDURE
    'EDAMINO',  # Prodotto specifico, non serve nel dizionario
    'PAPRIKA',  # Match in "PATATINE PAPRIKA" → SPEZIE invece di SHOP
]

# KEYWORDS DA SPOSTARE (categoria sbagliata)
SPOSTA_KEYWORDS = {
    'PARMA': 'SALUMI',  # Era CARNE, ma è prosciutto di Parma
    'CARCIOFI': 'VERDURE',  # Era FRUTTA
    'PESCA': 'FRUTTA',  # Mantieni FRUTTA (i succhi li gestisce "SUCCO" → BEVANDE)
    'ANANAS': 'FRUTTA',  # Mantieni FRUTTA
    'LIMONE': 'FRUTTA',  # Mantieni FRUTTA
    'PANNA': 'LATTICINI',  # Mantieni LATTICINI (i casi VARIE BAR/PASTICCERIA servono keywords più specifiche)
    'LATTE': 'LATTICINI',  # Mantieni LATTICINI
    'PIZZA': 'PRODOTTI DA FORNO',  # Mantieni
    'ROUX': 'SECCO',  # Era SALSE E CREME, è prodotto secco
    'PASSATA': 'SCATOLAME E CONSERVE',  # Era SALSE E CREME
    'PASSATA POMOD': 'SCATOLAME E CONSERVE',  # Era SALSE E CREME
    'PASSATA POMODORO': 'SCATOLAME E CONSERVE',  # Era SALSE E CREME
    'ZUCCHERO': 'SECCO',  # Mantieni SECCO (ZUCCHERO BAR va in VARIE BAR)
}

# KEYWORDS DA AGGIUNGERE (specifiche per casi problematici)
AGGIUNGI_KEYWORDS = {
    # Bevande (per evitare FRUTTA quando c'è SUCCO)
    'SUCCO': 'BEVANDE',
    'DERBY SUCCO': 'BEVANDE',
    'ESTATHE': 'BEVANDE',
    
    # VARIE BAR (prodotti specifici bar)
    'ZUCCHERO BUSTINE': 'VARIE BAR',
    'ZUCCHERO BAR': 'VARIE BAR',
    'PANNA SPRAY': 'VARIE BAR',
    
    # PASTICCERIA (prodotti specifici)
    'CONCHIGLIA PANNA': 'PASTICCERIA',
    'ARAGOSTINE': 'PASTICCERIA',
    'CANNOLI SFOGLIA': 'PASTICCERIA',
    'CREMA GIANDUJA': 'PASTICCERIA',
    'GIANDUJA': 'PASTICCERIA',
    'GIANDUIA': 'PASTICCERIA',
    
    # NO FOOD (materiali)
    'TAZZA': 'NO FOOD',
    'GREMBIULE': 'NO FOOD',
    'SALE PASTIGLIE': 'NO FOOD',  # È per lavastoviglie
    
    # LATTICINI (formaggio specifico)
    'PIZZA JULIENNE': 'LATTICINI',  # È formaggio grattugiato
    'EDAMER': 'LATTICINI',
    
    # VERDURE
    'MISTICANZA': 'VERDURE',
    
    # SHOP (snack confezionati)
    'PATATINE': 'SHOP',
}

print("=" * 80)
print("🔧 CORREZIONI DIZIONARIO PER ELIMINARE I 30 ERRORI")
print("=" * 80)

print(f"\n1️⃣ Keywords DA RIMUOVERE: {len(RIMUOVI_KEYWORDS)}")
for kw in RIMUOVI_KEYWORDS:
    print(f"   ❌ {kw}")

print(f"\n2️⃣ Keywords DA SPOSTARE: {len(SPOSTA_KEYWORDS)}")
for kw, nuova_cat in SPOSTA_KEYWORDS.items():
    print(f"   ↔️  {kw} → {nuova_cat}")

print(f"\n3️⃣ Keywords DA AGGIUNGERE: {len(AGGIUNGI_KEYWORDS)}")
for kw, cat in AGGIUNGI_KEYWORDS.items():
    print(f"   ✅ {kw} → {cat}")

print("\n" + "=" * 80)
print("💡 PROSSIMO STEP:")
print("   Applicare queste modifiche a config/constants.py → DIZIONARIO_CORREZIONI")
print("=" * 80)
