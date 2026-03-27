"""
Servizio per invio email tramite Brevo SMTP API.
"""

import streamlit as st
import requests
import logging
import time
from config.logger_setup import get_logger

logger = get_logger('email')


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
        
        # Default reply-to da secrets (no PII hardcoded)
        if not reply_to_email:
            reply_to_email = brevo_cfg.get('reply_to_email', sender_email)
        if not reply_to_name:
            reply_to_name = brevo_cfg.get('reply_to_name', sender_name)
        
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
