"""
Servizio per invio email tramite Brevo SMTP API.
"""

import streamlit as st
import requests
import logging

logger = logging.getLogger('fci_app.email')


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
        sender_name = brevo_cfg.get('sender_name', 'Analisi Fatture AI')
        
        # Default reply-to (support Gmail)
        if not reply_to_email:
            reply_to_email = "mattiadavolio90@gmail.com"
        if not reply_to_name:
            reply_to_name = "Mattia Davolio - Support"
        
        # Costruisci payload
        payload = {
            "sender": {"email": sender_email, "name": sender_name},
            "to": [{"email": destinatario}],
            "replyTo": {"email": reply_to_email, "name": reply_to_name},
            "bcc": [{"email": "mattiadavolio90@gmail.com"}],  # Copia nascosta per log
            "subject": oggetto,
            "htmlContent": corpo_html
        }
        
        # Invio tramite Brevo API v3
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code == 201:
            logger.info(f"✅ Email inviata a {destinatario}: {oggetto}")
            return True
        else:
            logger.error(f"❌ Brevo API error: {response.status_code} - {response.text}")
            return False
            
    except requests.Timeout:
        logger.error("⏱️ Timeout invio email Brevo")
        return False
    except Exception as e:
        logger.exception(f"❌ Errore invio email: {e}")
        return False
