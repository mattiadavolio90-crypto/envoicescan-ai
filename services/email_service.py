"""
Servizio per invio email tramite Brevo SMTP API.
"""

import streamlit as st
import requests
import logging
import time
import hashlib
from datetime import datetime, timedelta, timezone
from config.logger_setup import get_logger

logger = get_logger('email')


# === [M3] Rate-limit invio email (anti-spam/loop) ===
EMAIL_RATE_LIMIT_PER_DEST_5MIN = 5     # max 5 email allo stesso destinatario in 5 min
EMAIL_RATE_LIMIT_PER_DEST_1H = 20      # max 20 email allo stesso destinatario in 1 ora


def _check_email_rate_limit(destinatario: str, oggetto: str) -> tuple[bool, str]:
    """Verifica se l'invio email è consentito. Ritorna (allowed, reason)."""
    try:
        from services import get_supabase_client
        sb = get_supabase_client()
        now = datetime.now(timezone.utc)
        since_5min = (now - timedelta(minutes=5)).isoformat()
        since_1h = (now - timedelta(hours=1)).isoformat()

        # Conteggio ultimi 5 min
        resp5 = (
            sb.table('email_rate_log')
            .select('id', count='exact')
            .eq('destinatario', destinatario.strip().lower())
            .gte('created_at', since_5min)
            .execute()
        )
        count_5min = int(resp5.count or 0)
        if count_5min >= EMAIL_RATE_LIMIT_PER_DEST_5MIN:
            return False, f"Rate limit 5min: {count_5min}/{EMAIL_RATE_LIMIT_PER_DEST_5MIN}"

        # Conteggio ultima ora
        resp1h = (
            sb.table('email_rate_log')
            .select('id', count='exact')
            .eq('destinatario', destinatario.strip().lower())
            .gte('created_at', since_1h)
            .execute()
        )
        count_1h = int(resp1h.count or 0)
        if count_1h >= EMAIL_RATE_LIMIT_PER_DEST_1H:
            return False, f"Rate limit 1h: {count_1h}/{EMAIL_RATE_LIMIT_PER_DEST_1H}"

        return True, "ok"
    except Exception as exc:
        # Se DB irraggiungibile: fail-open per non bloccare email critiche (reset password)
        logger.warning(f"⚠️ Rate limit check fallito (fail-open): {exc}")
        return True, "fail-open"


def _log_email_sent(destinatario: str, oggetto: str) -> None:
    """Registra un invio email nel log rate-limit. Fail-safe (non blocca)."""
    try:
        from services import get_supabase_client
        sb = get_supabase_client()
        _hash = hashlib.sha256(oggetto.encode('utf-8')).hexdigest()[:32]
        sb.table('email_rate_log').insert({
            'destinatario': destinatario.strip().lower(),
            'oggetto_hash': _hash,
        }).execute()
    except Exception as exc:
        logger.warning(f"⚠️ Errore log email_rate_log (non blocca invio): {exc}")


def invia_email(destinatario: str, oggetto: str, corpo_html: str, reply_to_email: str = None, reply_to_name: str = None) -> bool:
    """
    Invia email tramite Brevo SMTP API v3.
    
    Args:
        destinatario: Email destinatario
        oggetto: Oggetto email
        corpo_html: Contenuto HTML email
        reply_to_email: Email per reply-to (default: mattiadavolio90@gmail.com)
        reply_to_name: Nome per reply-to (default: Support)
        
    Returns:
        bool: True se email inviata con successo, False altrimenti
        
    Example:
        >>> invia_email(
        ...     destinatario="cliente@example.com",
        ...     oggetto="Reset Password",
        ...     corpo_html="<h1>Ciao</h1>"
        ... )
        True
    """
    # 🛡️ [M3] Rate-limit: blocca spam/loop notifiche allo stesso destinatario
    if not destinatario or not str(destinatario).strip():
        logger.error("invia_email: destinatario vuoto")
        return False
    _allowed, _reason = _check_email_rate_limit(str(destinatario), str(oggetto or ''))
    if not _allowed:
        logger.warning(
            "🚫 Email NON inviata (rate limit) — dest=%s oggetto=%r motivo=%s",
            destinatario,
            (oggetto or '')[:80],
            _reason,
        )
        return False

    try:
        # Configurazione Brevo
        brevo_cfg = st.secrets.get('brevo')
        if not brevo_cfg:
            logger.error('Sezione [brevo] non trovata in secrets.toml')
            return False
        
        api_key = brevo_cfg.get('api_key')
        if not api_key:
            logger.error('Brevo API key non configurata')
            return False
        
        sender_email = brevo_cfg.get('sender_email', 'noreply@example.com')
        sender_name = brevo_cfg.get('sender_name', 'OH YEAH! Hub')

        # 🔒 Validazione email: previene spoofing/misconfig in secrets.toml
        import re as _re
        _email_re = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
        if not _re.match(_email_re, str(sender_email)):
            logger.error("sender_email configurata male in secrets.toml: %r", sender_email)
            return False

        # Default reply-to da secrets (no PII hardcoded)
        if not reply_to_email:
            reply_to_email = brevo_cfg.get('reply_to_email', sender_email)
        if not reply_to_name:
            reply_to_name = brevo_cfg.get('reply_to_name', sender_name)

        if reply_to_email and not _re.match(_email_re, str(reply_to_email)):
            logger.error("reply_to_email configurata male: %r", reply_to_email)
            return False
        
        # Costruisci payload
        payload = {
            "sender": {"email": sender_email, "name": sender_name},
            "to": [{"email": destinatario}],
            "replyTo": {"email": reply_to_email, "name": reply_to_name},
            "subject": oggetto,
            "htmlContent": corpo_html
        }
        
        # BCC opzionale: solo se configurato in secrets
        bcc_email = brevo_cfg.get('bcc_email')
        if bcc_email:
            payload["bcc"] = [{"email": bcc_email}]
        
        # Invio tramite Brevo API v3 (con retry per errori transitori)
        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    json=payload,
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json"
                    },
                    timeout=[8, 10, 15][attempt]
                )
                
                if response.status_code in (200, 201, 202):
                    logger.info(f"✅ Email inviata a {destinatario}: {oggetto}")
                    # 📊 [M3] Log invio per rate-limit (fail-safe)
                    _log_email_sent(str(destinatario), str(oggetto or ''))
                    return True
                elif response.status_code >= 500:
                    resp_excerpt = response.text[:200] if response.text else ''
                    last_error = f"Brevo API {response.status_code}: {resp_excerpt}"
                    logger.warning(f"⚠️ Tentativo {attempt + 1}/3 fallito (server error): {last_error}")
                else:
                    resp_excerpt = response.text[:200] if response.text else ''
                    logger.error(f"❌ Brevo API error: {response.status_code} - {resp_excerpt}")
                    return False
            except requests.Timeout:
                last_error = "Timeout"
                logger.warning(f"⚠️ Tentativo {attempt + 1}/3 timeout invio email Brevo")
            except requests.ConnectionError as e:
                last_error = str(e)
                logger.warning(f"⚠️ Tentativo {attempt + 1}/3 errore connessione: {e}")
            
            if attempt < 2:
                time.sleep(2 ** attempt)
        
        logger.error(f"❌ Email non inviata dopo 3 tentativi. Ultimo errore: {last_error}")
        return False
    except Exception as e:
        logger.exception(f"❌ Errore invio email: {e}")
        return False
