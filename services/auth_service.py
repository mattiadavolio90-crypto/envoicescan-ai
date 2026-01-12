"""
Servizio di autenticazione - Gestione login, password e reset password.

Questo modulo fornisce:
- Verifica credenziali con supporto Argon2 e migrazione da SHA256
- Sistema di reset password con codici temporanei
- Invio email tramite Brevo SMTP API

Dipendenze:
- argon2: Password hashing sicuro
- supabase: Database users
- streamlit: Secrets e session state
- requests: API Brevo
"""

import argon2
import secrets
import requests
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

# Logger
logger = logging.getLogger('fci_app.auth')

# Hasher globale Argon2
ph = argon2.PasswordHasher()


def verify_and_migrate_password(user_record: dict, password: str) -> bool:
    """
    Verifica password con supporto Argon2 e migrazione automatica da SHA256 legacy.
    
    Args:
        user_record: Record utente dal database con 'password_hash' e 'id'
        password: Password in chiaro da verificare
        
    Returns:
        bool: True se password corretta, False altrimenti
        
    Note:
        - Se la password è in SHA256, viene automaticamente migrata ad Argon2
        - Richiede parametro supabase_client per la migrazione
    """
    stored = (user_record.get('password_hash') or '').strip()
    if not stored:
        return False

    # Verifica Argon2 (formato moderno)
    if stored.startswith('$argon2'):
        try:
            ph.verify(stored, password)
            return True
        except Exception:
            logger.exception('Verifica Argon2 fallita')
            return False

    # Fallback SHA256 con migrazione automatica
    try:
        import streamlit as st
        from supabase import create_client
        
        sha = hashlib.sha256(password.encode()).hexdigest()
        if sha == stored:
            # Password corretta - migra ad Argon2
            try:
                new_hash = ph.hash(password)
                supabase_url = st.secrets["supabase"]["url"]
                supabase_key = st.secrets["supabase"]["key"]
                supabase = create_client(supabase_url, supabase_key)
                supabase.table('users').update({'password_hash': new_hash}).eq('id', user_record.get('id')).execute()
                logger.info(f"Password migrata ad Argon2 per user_id={user_record.get('id')}")
            except Exception:
                logger.exception('Migrazione password fallita')
            return True
        return False
    except Exception:
        logger.exception('Verifica SHA256 fallita')
        return False


def verifica_credenziali(email: str, password: str, supabase_client=None) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Verifica credenziali utente e aggiorna last_login.
    
    Args:
        email: Email utente
        password: Password in chiaro
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
        
    Returns:
        Tuple[Optional[Dict], Optional[str]]: (user_data, error_message)
        - Se successo: (user_dict, None)
        - Se fallito: (None, "messaggio errore")
        
    Note:
        - Verifica account attivo (attivo=True)
        - Aggiorna automaticamente last_login su successo
        - Supporta sia Argon2 che SHA256 legacy
    """
    try:
        import streamlit as st
        from supabase import create_client
        
        # Ottieni client Supabase
        if supabase_client is None:
            supabase_url = st.secrets["supabase"]["url"]
            supabase_key = st.secrets["supabase"]["key"]
            supabase_client = create_client(supabase_url, supabase_key)
        
        # Query utente attivo
        response = supabase_client.table("users").select("*").eq("email", email).eq("attivo", True).execute()
        
        if not response.data:
            return None, "Credenziali errate o account disattivato"
        
        user = response.data[0]
        
        # Verifica password
        if verify_and_migrate_password(user, password):
            # Aggiorna last_login
            try:
                supabase_client.table('users').update({
                    'last_login': datetime.utcnow().isoformat()
                }).eq('id', user['id']).execute()
            except Exception:
                logger.exception('Errore aggiornamento last_login')
            
            return user, None
        else:
            return None, "Credenziali errate"
            
    except Exception as e:
        logger.exception("Errore verifica credenziali")
        return None, f"Errore: {str(e)}"


def invia_codice_reset(email: str, supabase_client=None) -> Tuple[bool, str]:
    """
    Genera codice reset password e lo invia via email tramite Brevo SMTP API.
    
    Args:
        email: Email utente per reset
        supabase_client: Client Supabase (opzionale)
        
    Returns:
        Tuple[bool, str]: (success, message)
        - Se successo: (True, "Email inviata")
        - Se fallito: (False, "Errore generico")
        
    Note:
        - Codice valido 1 ora
        - Salva in DB se possibile, altrimenti in session_state
        - Non espone mai il codice nell'interfaccia
        - Usa Brevo SMTP API v3
        
    Configurazione secrets.toml:
        [brevo]
        api_key = "xkeysib-..."
        sender_email = "noreply@domain.com"
        sender_name = "App Name"
    """
    try:
        import streamlit as st
        from supabase import create_client
        
        # Genera codice sicuro
        code = secrets.token_urlsafe(8)
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        
        # Ottieni client Supabase
        if supabase_client is None:
            supabase_url = st.secrets["supabase"]["url"]
            supabase_key = st.secrets["supabase"]["key"]
            supabase_client = create_client(supabase_url, supabase_key)
        
        # Salva codice nel DB
        stored_in_db = True
        try:
            supabase_client.table('users').update({
                'reset_code': code,
                'reset_expires': expires
            }).eq('email', email).execute()
        except Exception:
            logger.exception(f"Errore salvataggio codice per {email}")
            stored_in_db = False
        
        # Fallback: salva in session state
        if not stored_in_db:
            if 'reset_codes' not in st.session_state:
                st.session_state.reset_codes = {}
            st.session_state.reset_codes[email] = {'code': code, 'expires': expires}
        
        # Configurazione Brevo
        brevo_cfg = st.secrets.get('brevo')
        if not brevo_cfg:
            logger.error('Sezione [brevo] non trovata in secrets.toml')
            return False, "Errore nell'invio email"
        
        api_key = brevo_cfg.get('api_key')
        if not api_key:
            logger.error('Brevo API key non configurata')
            return False, "Errore nell'invio email"
        
        sender_email = brevo_cfg.get('sender_email', 'contact@updates.brevo.com')
        sender_name = brevo_cfg.get('sender_name', 'Analisi Fatture AI')
        
        # Payload email
        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": email}],
            "subject": "Codice Reset Password",
            "htmlContent": f"""
            <html>
            <body>
                <h2>Reset Password</h2>
                <p>Hai richiesto di reimpostare la password.</p>
                <p>Il tuo codice di reset è: <strong>{code}</strong></p>
                <p>Il codice scadrà tra 1 ora.</p>
                <p>Se non hai richiesto questo reset, ignora questa email.</p>
            </body>
            </html>
            """
        }
        
        # Invio tramite Brevo API v3
        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        }
        
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code in (200, 201):
            logger.info(f"Email reset inviata a {email}")
            return True, "Email inviata con successo"
        else:
            logger.error(f"Brevo API error: {response.status_code} - {response.text}")
            return False, "Errore nell'invio email"
            
    except requests.exceptions.Timeout:
        logger.error("Timeout invio email Brevo")
        return False, "Errore nell'invio email"
    except Exception as e:
        logger.exception("Errore invio codice reset")
        return False, "Errore nell'invio email"


def hash_password(password: str) -> str:
    """Hash password con Argon2"""
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    return ph.hash(password)


__all__ = [
    'verify_and_migrate_password',
    'verifica_credenziali',
    'invia_codice_reset',
    'hash_password',
]
