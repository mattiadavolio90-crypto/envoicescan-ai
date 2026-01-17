#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script per normalizzare le categorie nel file Excel di test.
Applica le mappature corrette fornite dall'utente.
"""
import pandas as pd

# Leggi il file
df = pd.read_excel('dettaglio_20260116_1710.xlsx')

# Mappature di normalizzazione
mappature = {
    'CAFFETTERIA': 'CAFFÈ',
    'PESAE': 'PESCE',
    'SALù': 'SALUMI',
    'VERDURA': 'VERDURE',
    'NOFOOD': 'NO FOOD',
    'CONSERVE': 'SCATOLAME E CONSERVE'
}

# Normalizza la colonna CORRETTA
df['CORRETTA'] = df['CORRETTA'].replace(mappature)

# Salva il file normalizzato
output_file = 'dettaglio_20260116_1710_NORMALIZZATO.xlsx'
df.to_excel(output_file, index=False)

print(f'✅ File normalizzato salvato: {output_file}')
print(f'\nMappature applicate:')
for vecchio, nuovo in mappature.items():
    count = df[df['CORRETTA'] == nuovo].shape[0]
    if count > 0:
        print(f'  {vecchio} → {nuovo}: {count} righe')

print(f'\nCategorie nel file normalizzato:')
print(df['CORRETTA'].value_counts().sort_index())

print(f'\nRiepilogo:')
print(f'- Righe totali: {len(df)}')
print(f'- Righe con correzione: {df["CORRETTA"].notna().sum()}')
print(f'- Categorie uniche: {df["CORRETTA"].nunique()}')
