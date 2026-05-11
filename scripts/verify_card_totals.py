#!/usr/bin/env python3
"""Verifica coerenza totali card vs DB Supabase."""

import sys
import os
from datetime import datetime, date
import pandas as pd

# Aggiungi parent dir al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import get_supabase_client

def verify_totals(user_id: str):
    """Verifica totali card vs DB."""
    supabase = get_supabase_client()
    
    data_inizio = date(2026, 1, 1)
    data_fine = date(2026, 5, 11)
    
    print(f"🔍 Verifica totali per user_id: {user_id}")
    print(f"   Periodo: {data_inizio} → {data_fine}\n")
    
    # Carica tutte le righe per il periodo
    print("📊 Caricamento dati...")
    resp = (
        supabase.table("fatture")
        .select("totale_riga, categoria, needs_review")
        .eq("user_id", user_id)
        .gte("data_documento", data_inizio.isoformat())
        .lte("data_documento", data_fine.isoformat())
        .is_("deleted_at", "null")
        .execute()
    )
    
    data_all = resp.data or []
    print(f"   Righe totali caricate: {len(data_all)}\n")
    
    # Categorie spese generali
    categorie_spese = {"SERVIZI E CONSULENZE", "UTENZE E LOCALI", "MANUTENZIONE E ATTREZZATURE"}
    categorie_escluse = {"📝 NOTE E DICITURE", "NOTE E DICITURE", "Da Classificare"}
    
    # Filtra F&B
    data_fb = [
        r for r in data_all
        if r.get("needs_review") is False
        and str(r.get("categoria", "")).strip() not in categorie_spese
        and str(r.get("categoria", "")).strip() not in categorie_escluse
    ]
    
    totale_fb_db = sum(float(r.get("totale_riga", 0)) for r in data_fb if r.get("totale_riga"))
    
    print("📊 Query F&B...")
    print(f"   Righe F&B: {len(data_fb)}")
    print(f"   Totale DB: €{totale_fb_db:,.2f}")
    print(f"   Totale Card: €690.997")
    diff_fb = abs(totale_fb_db - 690997)
    print(f"   Differenza: €{diff_fb:,.2f} {'✅' if diff_fb < 1 else '❌'}\n")
    
    # Filtra Spese Generali
    data_spese = [
        r for r in data_all
        if r.get("needs_review") is False
        and str(r.get("categoria", "")).strip() in categorie_spese
    ]
    
    totale_spese_db = sum(float(r.get("totale_riga", 0)) for r in data_spese if r.get("totale_riga"))
    
    print("📊 Query Spese Generali...")
    print(f"   Righe Spese: {len(data_spese)}")
    print(f"   Totale DB: €{totale_spese_db:,.2f}")
    print(f"   Totale Card: €212.084")
    diff_spese = abs(totale_spese_db - 212084)
    print(f"   Differenza: €{diff_spese:,.2f} {'✅' if diff_spese < 1 else '❌'}\n")
    
    # Totale complessivo
    totale_complessivo_db = totale_fb_db + totale_spese_db
    totale_complessivo_card = 903080
    
    print("📊 Totale Complessivo")
    print(f"   DB: €{totale_complessivo_db:,.2f}")
    print(f"   Card: €{totale_complessivo_card:,.2f}")
    diff_total = abs(totale_complessivo_db - totale_complessivo_card)
    print(f"   Differenza: €{diff_total:,.2f} {'✅' if diff_total < 1 else '❌'}\n")
    
    if diff_fb < 1 and diff_spese < 1:
        print("✅ Tutti i totali sono COERENTI con il DB!")
    else:
        print("❌ Rilevate discrepanze!")
        
        if diff_fb >= 1:
            print(f"   → F&B: differenza di €{diff_fb:,.2f}")
        if diff_spese >= 1:
            print(f"   → Spese Generali: differenza di €{diff_spese:,.2f}")

if __name__ == "__main__":
    # Chiedi l'user_id come argomento della riga di comando
    if len(sys.argv) < 2:
        print("❌ Uso: python verify_card_totals.py <user_id>")
        print("\nEsempio: python verify_card_totals.py 550e8400-e29b-41d4-a716-446655440000")
        sys.exit(1)
    
    user_id = sys.argv[1]
    verify_totals(user_id)
