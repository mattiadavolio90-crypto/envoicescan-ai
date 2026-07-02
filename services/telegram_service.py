"""Invio messaggi Telegram per notifiche operative (down/lento, digest agent
notturno). Canale PUSH per Mattia (unico admin/sviluppatore): a differenza di
notification_inbox (pull, l'utente deve aprire l'app), questi messaggi arrivano
sul telefono senza bisogno di aprire nulla.

Config via env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. Se mancanti, invia_messaggio
ritorna False senza sollevare — un alert che non parte non deve MAI rompere il
chiamante (agent notturno, endpoint di health).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("fastapi_worker")

_API_BASE = "https://api.telegram.org"
_TIMEOUT_S = 10.0


def _config() -> tuple[Optional[str], Optional[str]]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return token, chat_id


def telegram_configurato() -> bool:
    token, chat_id = _config()
    return bool(token and chat_id)


def invia_messaggio(testo: str, *, silenzioso: bool = False) -> bool:
    """Invia un messaggio Telegram (testo semplice, NO parse_mode). Ritorna
    True/False, non solleva mai.

    Testo semplice deliberatamente: il Markdown di Telegram rifiuta come 400 Bad
    Request qualunque messaggio con entità non bilanciate (es. un punto dopo
    caratteri come '_' o '*' nei nomi file '.py', percentuali, ecc.) — troppo
    fragile per messaggi generati da template con dati variabili. Niente
    formattazione ma zero rischio che l'alert non parta per colpa della sintassi.

    `silenzioso=True` -> notifica senza suono (per digest non urgenti, es. quello
    notturno: Mattia lo legge al mattino, non deve svegliarlo).
    """
    token, chat_id = _config()
    if not token or not chat_id:
        logger.info("telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID non configurati, alert saltato")
        return False
    try:
        resp = httpx.post(
            f"{_API_BASE}/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": testo[:4096],  # limite Telegram per messaggio
                "disable_notification": silenzioso,
            },
            timeout=_TIMEOUT_S,
        )
        if resp.status_code != 200:
            logger.warning("telegram: invio fallito HTTP %d: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("telegram: invio fallito: %s", exc)
        return False
