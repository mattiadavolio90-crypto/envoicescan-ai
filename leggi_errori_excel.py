#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import sys
import io

# Fix encoding per Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file = 'dettaglio_20260116_1237.xlsx'

try:
    df = pd.read_excel(file)
    
    print("=" * 120)
    print(f"FILE: {file}")
    print("=" * 120)
    print()
    print(f"📊 Righe: {len(df)}")
    print(f"📋 Colonne: {list(df.columns)}")
    print()
    print(df.to_string())
    
except Exception as e:
    print(f"❌ Errore: {e}")
    import traceback
    traceback.print_exc()
