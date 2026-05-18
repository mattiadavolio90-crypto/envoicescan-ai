#!/usr/bin/env python3
"""Trova l'user_id corretto per ghyl.888@gmail.com."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import get_supabase_client

supabase = get_supabase_client()
email = "ghyl.888@gmail.com"

print(f"🔍 Ricerca user_id per email: {email}\n")

# Ricerca nella tabella users
print("📊 Ricerca in tabella users...")
try:
    resp_users = (
        supabase.table("users")
        .select("id, email, username")
        .ilike("email", f"%{email}%")
        .limit(1)
        .execute()
    )
    if resp_users.data:
        user_id = resp_users.data[0].get("id")
        user_email = resp_users.data[0].get("email")
        username = resp_users.data[0].get("username")
        print(f"✅ Trovato in users!")
        print(f"   ID: {user_id}")
        print(f"   Email: {user_email}")
        print(f"   Username: {username}")
    else:
        print(f"❌ Non trovato in users")
except Exception as e:
    print(f"   Errore users: {e}")

# Prova tabella oauth_sessions o other
print("\n📊 Ricerca in fatture per qualsiasi email...")
try:
    resp_count = (
        supabase.table("fatture")
        .select("id, user_id", count="exact")
        .limit(1)
        .execute()
    )
    if resp_count.count and resp_count.count > 0:
        # Carica un'altra colonna se esiste
        resp_one = supabase.table("fatture").select("*").limit(1).execute()
        if resp_one.data:
            print(f"   Colonne in fatture: {list(resp_one.data[0].keys())}")
except Exception as e:
    print(f"   Errore: {e}")
