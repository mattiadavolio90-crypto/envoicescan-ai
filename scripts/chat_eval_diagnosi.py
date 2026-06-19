"""Diagnosi qualita' risposte assistente (operativo, non runtime).

Esercita la pipeline chat VERA su un cliente reale con molti dati (SUSHILAND) per
osservare 4 comportamenti prima del potenziamento:
  - VAGA: domande senza specifico -> oggi indovina? dovrebbe chiedere chiarimento.
  - TOOL: sceglie lo strumento giusto? (trend vs spesa vs ultimo acquisto)
  - FUORI FINESTRA: dato oltre la finestra temporale -> e' onesto o muto?
  - BASELINE: domande gia' coperte -> non devono regredire.

Bypassa solo l'auth. CONSUMA QUOTA CHAT REALE del cliente (loggata in
chat_usage_log, source implicito). Cancellare i log di test dopo se serve.

Uso:
    python scripts/chat_eval_diagnosi.py
"""
from __future__ import annotations

import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

from dotenv import load_dotenv

load_dotenv()

import services.fastapi_worker as fw
from services import get_supabase_client

EMAIL_TEST = "ghyl.888@gmail.com"  # SUSHILAND, pro, ~6300 righe


def _carica_user(email: str) -> dict:
    sb = get_supabase_client()
    r = sb.table("users").select("*").eq("email", email).single().execute()
    if not r.data:
        raise SystemExit(f"Utente {email} non trovato")
    return r.data


# (etichetta, domanda) — single-turn, una conversazione per riga.
CASI = [
    ("VAGA",          "Com'e' andata?"),
    ("VAGA",          "Quanto spendo?"),
    ("VAGA",          "Il pesce?"),
    ("VAGA",          "Come sono messo?"),
    ("TOOL-trend",    "Il pesce e' aumentato di prezzo?"),
    ("TOOL-confronto","Chi mi fa il salmone al prezzo migliore?"),
    ("TOOL-ultimo",   "Qual e' l'ultima cosa che ho comprato?"),
    ("FUORI-FINESTRA","Quanto e' costato il pesce a giugno 2025?"),
    ("FUORI-FINESTRA","Com'era il prezzo del riso un anno fa?"),
    ("BASELINE-spesa","Quanto ho speso in pesce a marzo?"),
    ("BASELINE-mol",  "Com'e' andato il MOL negli ultimi mesi?"),
]


def main() -> None:
    user = _carica_user(EMAIL_TEST)
    print(f"== Diagnosi chat su {EMAIL_TEST} ({user.get('nome_ristorante')}) | model={fw.CHAT_MODEL} ==\n")
    fw._resolve_user_from_token = lambda authorization=None: user

    for idx, (tag, domanda) in enumerate(CASI, 1):
        print(f"\n[{idx:02d}] {tag}")
        print(f"  UTENTE: {domanda}")
        t0 = time.time()
        try:
            req = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content=domanda)])
            resp = fw.chat_ai(req, authorization="Bearer fake")
            dt = time.time() - t0
            print(f"  AI ({dt:.1f}s): {resp.reply}")
        except Exception as exc:
            print(f"  ERRORE: {type(exc).__name__}: {exc}")

    print(f"\n{'='*70}\nFine diagnosi.")


if __name__ == "__main__":
    main()
