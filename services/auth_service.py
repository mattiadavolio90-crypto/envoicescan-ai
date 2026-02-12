"""
Servizio di autenticazione - Gestione login, password e reset password.

Questo modulo fornisce:
- Verifica credenziali con supporto Argon2 e migrazione da SHA256
- Sistema di reset password con codici temporanei
- Invio email tramite Brevo SMTP API
- Validazione password GDPR compliant (Art.32 + Garante Privacy)
- Gestione creazione cliente con token attivazione

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
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any, List

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('auth')

# Hasher globale Argon2
ph = argon2.PasswordHasher()


# ============================================================
# VALIDAZIONE PASSWORD GDPR COMPLIANT
# ============================================================

# Blacklist password comuni (OWASP Top 10 + varianti italiane)
PASSWORD_COMUNI = [
    'password', 'password123', 'password1', 'passw0rd',
    '12345678', '123456789', '1234567890', '87654321',
    'qwerty123', 'qwertyuiop', 'abc12345', 'abcd1234',
    '11111111', '00000000', 'admin123', 'welcome1',
    'changeme', 'letmein', 'iloveyou', 'sunshine',
    'ristorante', 'trattoria', 'pizzeria', 'osteria'
]


def valida_password_compliance(
    password: str, 
    email: str, 
    nome_ristorante: str = ""
) -> List[str]:
    """
    Valida password secondo GDPR Art.32 + Garante Privacy Italia.
    
    Requisiti normativi implementati:
    1. Lunghezza ≥10 caratteri (best practice 2026, minimo GDPR è 8)
    2. Complessità: almeno 3 su 4 tra maiuscola, minuscola, numero, simbolo
    3. NO dati personali: email o nome ristorante nella password
    4. NO password comuni: blacklist TOP 20
    
    Args:
        password: Password da validare
        email: Email utente (per check dati personali)
        nome_ristorante: Nome locale (opzionale, per check dati personali)
    
    Returns:
        List[str]: Lista errori (vuota se password valida)
    
    Esempi:
        >>> valida_password_compliance("Ab1!defghi", "test@email.com", "")
        []  # Valida
        
        >>> valida_password_compliance("password", "test@email.com", "")
        ["⚠️ Usa almeno 10 caratteri...", "🚫 Password troppo comune..."]
    """
    errori = []
    
    if not password:
        errori.append("⚠️ La password è obbligatoria")
        return errori
    
    # 1. LUNGHEZZA MINIMA (GDPR + Best Practice 2026)
    if len(password) < 10:
        errori.append("⚠️ Usa almeno 10 caratteri per maggiore sicurezza")
    
    # 2. COMPLESSITÀ 3/4 (Garante Privacy Italia)
    checks = {
        'maiuscola': bool(re.search(r'[A-Z]', password)),
        'minuscola': bool(re.search(r'[a-z]', password)),
        'numero': bool(re.search(r'[0-9]', password)),
        'simbolo': bool(re.search(r'[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`\'\"\\]', password))
    }
    
    categorie_presenti = sum(checks.values())
    
    if categorie_presenti < 3:
        mancanti = [k for k, v in checks.items() if not v]
        suggerimento = ', '.join(mancanti[:2])
        errori.append(f"⚠️ Aggiungi almeno: {suggerimento}")
    
    # 3. NO DATI PERSONALI (GDPR Art.32)
    password_lower = password.lower()
    
    # Check email (parte prima di @)
    if email:
        email_username = email.split('@')[0].lower()
        if len(email_username) >= 4 and email_username in password_lower:
            errori.append("🚫 Non usare la tua email nella password")
    
    # Check nome ristorante
    if nome_ristorante and len(nome_ristorante) >= 4:
        # Normalizza: rimuovi spazi, articoli comuni
        nome_norm = nome_ristorante.lower()
        for articolo in ['il ', 'la ', 'lo ', 'i ', 'le ', 'gli ', 'da ', 'di ']:
            nome_norm = nome_norm.replace(articolo, '')
        nome_norm = nome_norm.replace(' ', '')
        
        if len(nome_norm) >= 4 and nome_norm in password_lower:
            errori.append("🚫 Non usare il nome del ristorante nella password")
    
    # 4. BLACKLIST PASSWORD COMUNI (OWASP Best Practice)
    if password_lower in PASSWORD_COMUNI:
        errori.append("🚫 Password troppo comune. Scegli qualcosa di più unico")
    
    # Check pattern semplici
    if re.match(r'^(.)\1+$', password):  # Carattere ripetuto (es: "aaaaaaaaaa")
        errori.append("🚫 La password non può essere un singolo carattere ripetuto")
    
    if re.match(r'^(012|123|234|345|456|567|678|789|890)+', password):
        errori.append("🚫 La password non può essere una sequenza numerica")
    
    return errori


def valida_e_mostra_errori_password(
    password: str, 
    email: str, 
    nome_ristorante: str = ""
) -> bool:
    """
    Helper Streamlit: valida password e mostra errori con st.error().
    
    Args:
        password: Password da validare
        email: Email utente
        nome_ristorante: Nome locale (opzionale)
    
    Returns:
        bool: True se password valida, False se ci sono errori
    
    Note:
        - Importa streamlit solo quando necessario
        - Mostra tutti gli errori trovati
    """
    import streamlit as st
    
    errori = valida_password_compliance(password, email, nome_ristorante)
    
    if errori:
        for errore in errori:
            st.error(errore)
        return False
    
    return True


# ============================================================
# CREAZIONE CLIENTE CON TOKEN (GDPR COMPLIANT)
# ============================================================

def crea_cliente_con_token(
    email: str,
    nome_ristorante: str,
    partita_iva: str,
    ragione_sociale: str = None,
    supabase_client = None
) -> Tuple[bool, str, str]:
    """
    Crea nuovo cliente SENZA password (GDPR compliant).
    
    Genera token di attivazione e invia email al cliente per impostare password.
    L'admin NON conosce mai la password del cliente.
    
    Args:
        email: Email cliente (obbligatoria, unica)
        nome_ristorante: Nome locale (obbligatorio)
        partita_iva: P.IVA normalizzata (obbligatoria)
        ragione_sociale: Nome azienda (opzionale)
        supabase_client: Client Supabase
    
    Returns:
        Tuple[bool, str, str]:
            - (True, "Messaggio successo", token) se creato
            - (False, "Messaggio errore", "") se fallito
    
    Note:
        - Token valido 24 ore (più lungo di reset password standard)
        - Account creato con attivo=False, diventa True dopo set password
        - password_hash = NULL finché cliente non imposta
    """
    try:
        import streamlit as st
        from services import get_supabase_client
        from utils.piva_validator import normalizza_piva, valida_formato_piva
        
        if supabase_client is None:
            supabase_client = get_supabase_client()
        
        # Validazioni base
        if not email or '@' not in email:
            return False, "❌ Email non valida", ""
        
        if not nome_ristorante:
            return False, "❌ Nome ristorante obbligatorio", ""
        
        # Validazione P.IVA
        piva_norm = normalizza_piva(partita_iva) if partita_iva else None
        if piva_norm:
            valida, msg = valida_formato_piva(piva_norm)
            if not valida:
                return False, msg, ""
        
        # Check email duplicata
        check_email = supabase_client.table('users')\
            .select('id')\
            .eq('email', email.lower())\
            .execute()
        
        if check_email.data:
            return False, f"❌ Email {email} già registrata", ""
        
        # Check P.IVA duplicata
        if piva_norm:
            check_piva = supabase_client.table('users')\
                .select('email')\
                .eq('partita_iva', piva_norm)\
                .execute()
            
            if check_piva.data:
                email_esistente = check_piva.data[0].get('email', 'altro utente')
                return False, f"⚠️ P.IVA già registrata da: {email_esistente}", ""
        
        # Genera token univoco (24h validità per primo accesso)
        # secrets.token_urlsafe(32) = 192 bit entropia, URL-safe (superiore a uuid4)
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Placeholder password_hash (NON usabile per login, sarà sovrascritto)
        # Usa hash di un UUID random - impossibile da indovinare
        placeholder_hash = hashlib.sha256(f"PENDING_ACTIVATION_{uuid.uuid4()}".encode()).hexdigest()
        
        # Inserisci cliente
        nuovo_cliente = {
            'email': email.lower().strip(),
            'nome_ristorante': nome_ristorante.strip(),
            'partita_iva': piva_norm,
            'ragione_sociale': ragione_sociale.strip() if ragione_sociale else None,
            'password_hash': placeholder_hash,  # Placeholder, sovrascritto al primo accesso
            'reset_code': token,
            'reset_expires': expires.isoformat(),
            'attivo': False,  # Attivo solo dopo set password
            'created_at': datetime.now(timezone.utc).isoformat(),
            'login_attempts': 0,
            'password_changed_at': None
        }
        
        result = supabase_client.table('users').insert(nuovo_cliente).execute()
        
        if not result.data:
            return False, "❌ Errore database durante creazione", ""
        
        user_id = result.data[0]['id']
        
        # Crea record ristorante associato (tabella multi-ristorante)
        try:
            nuovo_ristorante = {
                'user_id': user_id,
                'nome_ristorante': nome_ristorante.strip(),
                'partita_iva': piva_norm,
                'ragione_sociale': ragione_sociale.strip() if ragione_sociale else None,
                'attivo': True
            }
            
            rist_result = supabase_client.table('ristoranti').insert(nuovo_ristorante).execute()
            
            if rist_result.data:
                logger.info(f"✅ Ristorante creato per cliente: {nome_ristorante} (P.IVA: {piva_norm})")
            else:
                logger.warning(f"⚠️ Cliente creato ma ristorante non inserito: {email}")
        except Exception as rist_err:
            logger.warning(f"⚠️ Errore creazione ristorante per {email}: {rist_err}")
            # Non fallire la creazione cliente se il ristorante fallisce
        
        logger.info(f"✅ Cliente creato: {email} (P.IVA: {piva_norm})")
        
        return True, f"✅ Cliente {email} creato con successo!", token
        
    except Exception as e:
        logger.exception(f"Errore creazione cliente {email}")
        return False, f"❌ Errore: {str(e)}", ""


def imposta_password_da_token(
    token: str,
    nuova_password: str,
    supabase_client = None
) -> Tuple[bool, str, Dict]:
    """
    Imposta password per nuovo cliente da token email.
    
    Verifica token valido, valida password compliance, salva hash.
    
    Args:
        token: Token univoco da email
        nuova_password: Password scelta dal cliente
        supabase_client: Client Supabase
    
    Returns:
        Tuple[bool, str, Dict]:
            - (True, "Successo", user_data) se impostata
            - (False, "Errore", {}) se fallito
    """
    try:
        import streamlit as st
        from services import get_supabase_client
        
        if supabase_client is None:
            supabase_client = get_supabase_client()
        
        # 1. Cerca utente con token valido
        result = supabase_client.table('users')\
            .select('*')\
            .eq('reset_code', token)\
            .execute()
        
        if not result.data:
            return False, "❌ Link non valido o già utilizzato", {}
        
        user = result.data[0]
        
        # 2. Verifica scadenza token
        expires_str = user.get('reset_expires')
        if expires_str:
            expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
            # Timezone-aware comparison
            now_utc = datetime.now(timezone.utc)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            
            if now_utc > expires:
                return False, "⏰ Link scaduto. Contatta il supporto per un nuovo link.", {}
        
        # 3. Valida password compliance
        errori = valida_password_compliance(
            nuova_password,
            user.get('email', ''),
            user.get('nome_ristorante', '')
        )
        
        if errori:
            return False, errori[0], {}  # Ritorna primo errore
        
        # 4. Hash password e salva
        password_hash = ph.hash(nuova_password)
        
        supabase_client.table('users').update({
            'password_hash': password_hash,
            'reset_code': None,  # Invalida token
            'reset_expires': None,
            'attivo': True,  # Attiva account
            'password_changed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', user['id']).execute()
        
        logger.info(f"✅ Password impostata per: {user.get('email')}")
        
        return True, "🎉 Password impostata con successo!", user
        
    except Exception as e:
        logger.exception("Errore impostazione password da token")
        return False, f"❌ Errore: {str(e)}", {}


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
                    'last_login': datetime.now(timezone.utc).isoformat()
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
        
        # Genera codice sicuro (12 bytes = 96 bit entropia)
        code = secrets.token_urlsafe(12)
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
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
        from datetime import datetime
        from services import get_supabase_client
        
        supabase = get_supabase_client()
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
        from datetime import datetime
        from services import get_supabase_client
        
        supabase = get_supabase_client()
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
    # Nuove funzioni GDPR password + P.IVA
    'valida_password_compliance',
    'valida_e_mostra_errori_password',
    'crea_cliente_con_token',
    'imposta_password_da_token',
]
