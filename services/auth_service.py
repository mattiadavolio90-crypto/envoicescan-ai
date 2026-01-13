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
        from services import get_supabase_client
        
        sha = hashlib.sha256(password.encode()).hexdigest()
        if sha == stored:
            # Password corretta - migra ad Argon2
            try:
                new_hash = ph.hash(password)
                supabase = get_supabase_client()
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
        from services import get_supabase_client
        
        # Ottieni client Supabase (singleton)
        if supabase_client is None:
            supabase_client = get_supabase_client()
        
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
        from services import get_supabase_client
        
        # Genera codice sicuro
        code = secrets.token_urlsafe(8)
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        
        # Ottieni client Supabase (singleton)
        if supabase_client is None:
            supabase_client = get_supabase_client()
        
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


def registra_logout_utente(email: str) -> bool:
    """
    Salva timestamp di logout nel database.
    Ogni volta che l'utente fa logout, aggiorniamo un campo nel DB.
    """
    try:
        import streamlit as st
        from datetime import datetime
        
        supabase = st.session_state.get('supabase_client')
        if not supabase:
            return False
            
        # Aggiorna campo last_logout nella tabella users
        result = supabase.table('users').update({
            'last_logout': datetime.now().isoformat()
        }).eq('email', email).execute()
        
        logger.info(f"✅ Logout registrato per {email}")
        return True
    except Exception as e:
        logger.exception(f"Errore registrazione logout per {email}")
        return False


def verifica_sessione_valida(email: str, session_timestamp: float) -> bool:
    """
    Verifica se la sessione è ancora valida confrontando con last_logout nel DB.
    Se l'utente ha fatto logout DOPO il login corrente, la sessione è invalida.
    """
    try:
        import streamlit as st
        from datetime import datetime
        
        supabase = st.session_state.get('supabase_client')
        if not supabase:
            return True  # Fallback: se non c'è DB, non blocchiamo
            
        # Recupera last_logout dal database
        result = supabase.table('users').select('last_logout').eq('email', email).execute()
        
        if not result.data:
            return True
            
        user = result.data[0]
        last_logout = user.get('last_logout')
        
        if not last_logout:
            return True  # Nessun logout mai effettuato
            
        # Converti last_logout in timestamp
        logout_dt = datetime.fromisoformat(last_logout.replace('Z', '+00:00'))
        logout_timestamp = logout_dt.timestamp()
        
        # Se il logout è DOPO il login della sessione corrente, invalida la sessione
        if logout_timestamp > session_timestamp:
            logger.warning(f"⚠️ Sessione invalida per {email}: logout {logout_dt} > login sessione")
            return False
            
        return True
    except Exception as e:
        logger.exception(f"Errore verifica sessione per {email}")
        return True  # In caso di errore, non blocchiamo


__all__ = [
    'verify_and_migrate_password',
    'verifica_credenziali',
    'invia_codice_reset',
    'hash_password',
    'registra_logout_utente',
    'verifica_sessione_valida',
]
