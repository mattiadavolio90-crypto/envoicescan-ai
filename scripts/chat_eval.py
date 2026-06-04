"""Valutazione qualita' assistente chat su dati reali (operativo, non runtime).

Esercita la pipeline chat VERA (system prompt + tools + loop OpenAI gpt-4.1-mini)
contro un utente reale, simulando conversazioni multi-turno per scovare i 3
sintomi: contesto perso, dati mancanti, risposte vaghe.

Bypassa solo l'auth (monkeypatch _resolve_user_from_token con l'utente scelto).
Tutto il resto e' identico alla produzione.

Uso:
    python scripts/chat_eval.py
"""
from __future__ import annotations

import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# I logger del backend stampano emoji: su console Windows (cp1252) sollevano
# UnicodeEncodeError. Silenzio i log durante l'eval: ci interessano le risposte.
logging.disable(logging.CRITICAL)

from dotenv import load_dotenv

load_dotenv()

import services.fastapi_worker as fw
from services import get_supabase_client

EMAIL_TEST = "md@oneflux.it"


def _carica_user(email: str) -> dict:
    sb = get_supabase_client()
    r = sb.table("users").select("*").eq("email", email).single().execute()
    if not r.data:
        raise SystemExit(f"Utente {email} non trovato")
    return r.data


def main() -> None:
    user = _carica_user(EMAIL_TEST)
    print(f"== Eval chat su {EMAIL_TEST} ({user.get('nome_ristorante')}) | model={fw.CHAT_MODEL} ==\n")

    # Bypass auth: tutta la pipeline (chat + home_kpi) usa questo utente.
    fw._resolve_user_from_token = lambda authorization=None: user

    # Conversazioni: ESATTAMENTE quelle della conversazione mobile reale che ha
    # rivelato i difetti (anno 2024 inventato, "birra" non trovata, ecc.) +
    # qualche regressione da tenere d'occhio.
    conversazioni = [
        # === I 2 NUOVI tool ===
        # 1. trend prezzo prodotto (nuovo tool trend_prezzo)
        ["La mozzarella e' aumentata di prezzo negli ultimi mesi?"],
        # 2. confronto tra periodi (2x query_costi + confronto)
        ["Ho speso piu' in carne a marzo o ad aprile?"],
        # 3. trend su prodotto carne
        ["Il prezzo della carne e' salito?"],
        # === Regressioni dalle fix precedenti (devono restare ok) ===
        # 4. ultimo acquisto
        ["Qual e' l'ultimo acquisto che ho fatto e da quale fornitore?"],
        # 5. carne a marzo senza anno
        ["Quanto ho speso in carne a marzo?"],
    ]

    for idx, turni in enumerate(conversazioni, 1):
        print(f"\n{'='*70}\nCONVERSAZIONE {idx}")
        history: list = []
        for turno in turni:
            history.append(fw.ChatMessage(role="user", content=turno))
            print(f"\n  UTENTE: {turno}")
            t0 = time.time()
            try:
                req = fw.ChatRequest(messages=list(history))
                resp = fw.chat_ai(req, authorization="Bearer fake")
                dt = time.time() - t0
                print(f"  AI ({dt:.1f}s): {resp.reply}")
                history.append(fw.ChatMessage(role="assistant", content=resp.reply))
            except Exception as exc:
                print(f"  ERRORE: {type(exc).__name__}: {exc}")
                break

    print(f"\n{'='*70}\nFine eval.")


if __name__ == "__main__":
    main()
