#!/usr/bin/env python3
"""Verifica coerenza totali card vs DB Supabase."""

import sys
import os
from datetime import datetime, date
import pandas as pd

# Aggiungi parent dir al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import get_supabase_client
from utils.validation import classify_special_row
from config.constants import CATEGORIE_SPESE_GENERALI

def verify_totals(user_id: str):
    """Verifica totali card vs DB."""
    supabase = get_supabase_client()
    
    data_inizio = date(2026, 1, 1)
    data_fine = date(2026, 5, 11)
    
    print(f"🔍 Verifica totali per user_id: {user_id}")
    print(f"   Periodo: {data_inizio} → {data_fine}\n")
    
    # Carica tutte le righe per il periodo (paginazione)
    print("📊 Caricamento dati (paginato)...")
    data_all = []
    offset = 0
    page_size = 1000
    while True:
        resp = (
            supabase.table("fatture")
            .select("totale_riga, categoria, needs_review, descrizione, prezzo_unitario, quantita, tipo_documento")
            .eq("user_id", user_id)
            .gte("data_documento", data_inizio.isoformat())
            .lte("data_documento", data_fine.isoformat())
            .is_("deleted_at", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        if not batch:
            break
        data_all.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    
    print(f"   Righe totali caricate: {len(data_all)}\n")
    
    # Replica esattamente la logica dashboard
    df = pd.DataFrame(data_all)
    if df.empty:
        print("❌ Nessun dato!")
        return
    
    # Normalizza colonne
    df['totale_riga'] = pd.to_numeric(df['totale_riga'], errors='coerce').fillna(0.0)
    df['prezzo_unitario'] = pd.to_numeric(df.get('prezzo_unitario'), errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita'), errors='coerce').fillna(1.0)
    
    print(f"📊 Totale grezzo (TUTTE le righe): €{df['totale_riga'].sum():,.2f}")
    print(f"   Righe needs_review: {df['needs_review'].fillna(False).astype(bool).sum()}")
    print(f"   Righe con totale negativo: {(df['totale_riga'] < 0).sum()}")
    print(f"   Righe con totale zero: {(df['totale_riga'] == 0).sum()}\n")
    
    # Applica classify_special_row per ogni riga
    print("📊 Applicazione filtri dashboard (classify_special_row)...")
    
    def _check_include(row):
        meta = classify_special_row(
            descrizione=row.get('descrizione', ''),
            categoria=row.get('categoria', ''),
            prezzo=row.get('prezzo_unitario', 0),
            totale_riga=row.get('totale_riga', 0),
            quantita=row.get('quantita', 1),
            tipo_documento=row.get('tipo_documento', ''),
            needs_review=bool(row.get('needs_review', False)),
        )
        return meta['include_in_dashboard']
    
    df['_include'] = df.apply(_check_include, axis=1)
    
    # Esclude righe needs_review e note/diciture
    mask_escludi = ~df['_include']
    mask_escludi |= df['needs_review'].fillna(False).astype(bool)
    cat_norm = df['categoria'].fillna('').astype(str).str.upper().str.strip()
    mask_escludi |= cat_norm.isin({'📝 NOTE E DICITURE', 'NOTE E DICITURE'})
    
    df_clean = df[~mask_escludi].copy()
    print(f"   Righe escluse: {mask_escludi.sum()}")
    print(f"   Righe rimaste: {len(df_clean)}\n")
    
    # Separa F&B da Spese Generali
    mask_spese = df_clean['categoria'].isin(CATEGORIE_SPESE_GENERALI)
    df_fb = df_clean[~mask_spese]
    df_spese = df_clean[mask_spese]
    
    totale_fb = df_fb['totale_riga'].sum()
    totale_spese = df_spese['totale_riga'].sum()
    totale = totale_fb + totale_spese
    
    print("=" * 60)
    print("📊 RISULTATI DOPO FILTRI DASHBOARD")
    print("=" * 60)
    
    print(f"\n📊 SPESA F&B")
    print(f"   Righe F&B: {len(df_fb)}")
    print(f"   Totale DB: €{totale_fb:,.2f}")
    print(f"   Card mostra: €690.997")
    diff_fb = abs(totale_fb - 690997)
    print(f"   Differenza: €{diff_fb:,.2f} {'✅' if diff_fb < 100 else '❌'}")
    
    print(f"\n📊 SPESA GENERALE")
    print(f"   Righe Spese: {len(df_spese)}")
    print(f"   Totale DB: €{totale_spese:,.2f}")
    print(f"   Card mostra: €212.084")
    diff_spese = abs(totale_spese - 212084)
    print(f"   Differenza: €{diff_spese:,.2f} {'✅' if diff_spese < 100 else '❌'}")
    
    print(f"\n📊 TOTALE COMPLESSIVO")
    print(f"   DB: €{totale:,.2f}")
    print(f"   Card: €903.080")
    diff_tot = abs(totale - 903080)
    print(f"   Differenza: €{diff_tot:,.2f} {'✅' if diff_tot < 100 else '❌'}")
    
    # Distribuzione per categoria (top 10)
    print(f"\n📊 TOP 10 CATEGORIE (per totale)")
    top_cat = df_clean.groupby('categoria')['totale_riga'].sum().sort_values(ascending=False).head(15)
    for cat, val in top_cat.items():
        print(f"   {cat:40s} €{val:>15,.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Uso: python verify_card_totals.py <user_id>")
        sys.exit(1)
    
    user_id = sys.argv[1]
    verify_totals(user_id)
