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
import json
import re
import uuid
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any, List

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('auth')

# Hasher globale Argon2
ph = argon2.PasswordHasher()

# ============================================================
# RATE LIMITING LOGIN (persistente su DB — tabella login_attempts)
# ============================================================
_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


class AuthServiceUnavailableError(RuntimeError):
    """Errore funzionale quando il servizio auth non e' raggiungibile."""


def _is_connectivity_error(error: Exception) -> bool:
    """Riconosce errori di rete o timeout dai client HTTP/DB."""
    if isinstance(error, (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError)):
        return True

    message = f"{type(error).__name__}: {error}".lower()
    connectivity_markers = (
        'connection',
        'connecterror',
        'network',
        'timeout',
        'timed out',
        'getaddrinfo',
        'name or service not known',
        'temporary failure in name resolution',
        'failed to establish a new connection',
        'server disconnected',
        'dns',
        'nodename nor servname',
    )
    return any(marker in message for marker in connectivity_markers)


def controlla_rate_limit(email: str, supabase_client=None) -> Tuple[bool, int]:
    """
    Controlla se l'email e' in lockout interrogando la tabella login_attempts.

    Returns:
        (True, minuti_rimanenti) se bloccato,
        (False, 0) se può procedere.
    """
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()

        email_lower = email.lower().strip()
        since = (datetime.now(timezone.utc) - timedelta(minutes=_LOCKOUT_MINUTES)).isoformat()

        resp = supabase_client.table('login_attempts') \
            .select('id', count='exact') \
            .eq('email', email_lower) \
            .eq('success', False) \
            .gte('attempted_at', since) \
            .execute()

        fail_count = resp.count if resp.count is not None else 0

        if fail_count >= _MAX_LOGIN_ATTEMPTS:
            # Calcola minuti rimanenti dal tentativo più vecchio nella finestra
            remaining = _LOCKOUT_MINUTES  # worst-case
            try:
                oldest = supabase_client.table('login_attempts') \
                    .select('attempted_at') \
                    .eq('email', email_lower) \
                    .eq('success', False) \
                    .gte('attempted_at', since) \
                    .order('attempted_at') \
                    .limit(1) \
                    .execute()
                if oldest.data:
                    oldest_dt = datetime.fromisoformat(oldest.data[0]['attempted_at'].replace('Z', '+00:00'))
                    if oldest_dt.tzinfo is None:
                        oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
                    expires_at = oldest_dt + timedelta(minutes=_LOCKOUT_MINUTES)
                    remaining = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds() / 60) + 1)
            except Exception as rate_err:
                logger.warning(f"Errore calcolo minuti lockout: {rate_err}")
            logger.warning(f"⛔ Login bloccato: lockout {remaining} min rimanenti")
            return True, remaining

        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            supabase_client.table('login_attempts') \
                .delete() \
                .eq('email', email_lower) \
                .lt('attempted_at', cutoff) \
                .execute()
        except Exception:
            pass

        return False, 0
    except Exception as exc:
        logger.exception('Errore controlla_rate_limit')
        if _is_connectivity_error(exc):
            raise AuthServiceUnavailableError(
                "Connessione internet assente o server di autenticazione non raggiungibile."
            ) from exc
        raise AuthServiceUnavailableError(
            "Servizio di autenticazione temporaneamente non disponibile."
        ) from exc


def registra_tentativo(email: str, success: bool, supabase_client=None):
    """
    Inserisce un record in login_attempts.
    Se success=True elimina i tentativi falliti precedenti per quell'email.
    Pulisce automaticamente i record più vecchi di 24h per quell'email.
    """
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()

        email_lower = email.lower().strip()

        # Inserisci il tentativo
        supabase_client.table('login_attempts').insert({
            'email': email_lower,
            'success': success,
        }).execute()

        if success:
            # Login riuscito: elimina tentativi falliti precedenti
            supabase_client.table('login_attempts') \
                .delete() \
                .eq('email', email_lower) \
                .eq('success', False) \
                .execute()

        # Pulizia record > 24h per questa email
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        supabase_client.table('login_attempts') \
            .delete() \
            .eq('email', email_lower) \
            .lt('attempted_at', cutoff) \
            .execute()

    except Exception as reg_err:
        logger.exception(f"Errore registra_tentativo per {email}: {reg_err}")


# ============================================================
# RATE LIMITING RESET PASSWORD (persistente su DB — colonna users.last_reset_requested_at)
# Non usa più dict in-memory: sopravvive ai restart di Streamlit Cloud.
# Migration richiesta: 046_add_reset_rate_limit_column.sql
# ============================================================
_RESET_COOLDOWN_SECONDS = 300  # 5 minuti tra una richiesta e l'altra


def _check_reset_rate_limit(email: str, supabase_client=None) -> Optional[str]:
    """
    Controlla se l'email può richiedere un nuovo reset leggendo dal DB.
    Ritorna messaggio errore (str) se in cooldown, oppure None se OK.
    Persiste attraverso i restart di Streamlit Cloud.
    """
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()
        email_lower = email.lower().strip()
        resp = supabase_client.table('users') \
            .select('last_reset_requested_at') \
            .eq('email', email_lower) \
            .maybe_single() \
            .execute()
        if resp.data and resp.data.get('last_reset_requested_at'):
            last_str = resp.data['last_reset_requested_at']
            last = datetime.fromisoformat(last_str.replace('Z', '+00:00'))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < _RESET_COOLDOWN_SECONDS:
                remaining = int((_RESET_COOLDOWN_SECONDS - elapsed) / 60) + 1
                logger.warning("⛔ Reset password bloccato: cooldown DB attivo")
                return f"Attendi {remaining} minuti prima di richiedere un altro reset."
    except Exception as e:
        logger.warning(f"Errore check_reset_rate_limit DB: {e} — reset bloccato per sicurezza")
        return "Servizio temporaneamente non disponibile. Riprova tra qualche minuto."
    return None


def _record_reset_request(email: str, supabase_client=None):
    """Registra la timestamp dell'ultima richiesta di reset nel DB (non in memoria)."""
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()
        email_lower = email.lower().strip()
        supabase_client.table('users').update({
            'last_reset_requested_at': datetime.now(timezone.utc).isoformat()
        }).eq('email', email_lower).execute()
    except Exception as e:
        logger.warning(f"Errore record_reset_request DB: {e}")


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
    if re.fullmatch(r'(.)\1+', password):  # Carattere ripetuto (es: "aaaaaaaaaa")
        errori.append("🚫 La password non può essere un singolo carattere ripetuto")
    
    if re.search(r'(012|123|234|345|456|567|678|789|890){2,}', password):
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
        
        # Check P.IVA duplicata nella tabella users
        # (P.IVA può coesistere in ristoranti diversi di utenti diversi,
        #  es. admin che replica ristorante cliente per test)
        if piva_norm:
            check_piva = supabase_client.table('users')\
                .select('email')\
                .eq('partita_iva', piva_norm)\
                .execute()
            
            if check_piva.data:
                email_esistente = check_piva.data[0].get('email', 'altro utente')
                logger.warning(f"⚠️ P.IVA {piva_norm} già presente in users (utente: {email_esistente}), procedo comunque")
        
        # Genera token univoco (24h validità per primo accesso)
        # secrets.token_urlsafe(32) = 192 bit entropia, URL-safe (superiore a uuid4)
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Placeholder password_hash (NON usabile per login, sarà sovrascritto)
        # Token crittografico random - impossibile da indovinare
        placeholder_hash = secrets.token_hex(32)
        
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
        # ⚠️ CRITICO: senza questo record il cliente NON può caricare fatture
        ristorante_creato = False
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
                logger.info(f"✅ Ristorante creato per user_id={user_id}")
                ristorante_creato = True
            else:
                logger.error(f"❌ Cliente creato ma ristorante non inserito (response vuota): user_id={user_id}")
        except Exception as rist_err:
            logger.error(f"❌ Errore creazione ristorante per user_id={user_id}: {rist_err}")
        
        logger.info(f"✅ Cliente creato: user_id={user_id}")
        
        if ristorante_creato:
            return True, f"✅ Cliente {email} creato con successo!", token
        else:
            return True, f"⚠️ Cliente {email} creato, ma il ristorante NON è stato configurato. Verifica nel pannello admin.", token
        
    except Exception as e:
        logger.exception("Errore creazione cliente")
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
        result = supabase_client.table('users') \
            .select("id, email, nome_ristorante, attivo, "
                    "reset_code, reset_expires, password_hash") \
            .eq('reset_code', token) \
            .execute()
        
        if not result.data:
            return False, "❌ Link non valido o già utilizzato", {}
        
        user = result.data[0]
        
        # 2. Verifica scadenza token
        expires_str = user.get('reset_expires')
        if not expires_str:
            return False, "Link non valido o scaduto.", {}
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
        
        # 4. Invalida token + salva nuova password in un'unica operazione atomica
        password_hash = ph.hash(nuova_password)
        user_id = user['id']
        
        supabase_client.table('users').update({
            'reset_code': None,
            'reset_expires': None,
            'password_hash': password_hash,
            'attivo': True,
            'password_changed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', user_id).execute()
        
        logger.info(f"✅ Password impostata per user_id={user_id}")
        
        # Rimuovi dati sensibili prima di restituire
        for _sensitive_key in ('password_hash', 'reset_code', 'reset_expires'):
            user.pop(_sensitive_key, None)
        
        return True, "🎉 Password impostata con successo!", user
        
    except Exception as e:
        logger.exception("Errore impostazione password da token")
        return False, "❌ Errore durante l'impostazione della password. Riprova.", {}


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
        import hmac as _hmac
        
        sha = hashlib.sha256(password.encode()).hexdigest()
        if _hmac.compare_digest(sha, stored):
            # Password corretta - migra ad Argon2
            try:
                new_hash = ph.hash(password)
                supabase = get_supabase_client()
                supabase.table('users').update({'password_hash': new_hash}).eq('id', user_record.get('id')).execute()
                logger.info(f"Password migrata ad Argon2 per user_id={user_record.get('id')}")
            except Exception as mig_err:
                logger.warning(f"Migrazione Argon2 fallita per user {user_record.get('id')} - hash SHA256 mantenuto: {mig_err}")
            return True
        return False
    except Exception:
        logger.exception('Verifica SHA256 fallita')
        return False


def verifica_credenziali(email: str, password: str, supabase_client=None) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Verifica credenziali utente e aggiorna last_login / last_seen_at.
    
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
        - Aggiorna automaticamente last_login e last_seen_at su successo
        - Supporta sia Argon2 che SHA256 legacy
    """
    try:
        import streamlit as st
        from services import get_supabase_client
        
        # Ottieni client Supabase (singleton)
        if supabase_client is None:
            supabase_client = get_supabase_client()
        
        # Rate limiting su DB: controlla lockout
        bloccato, minuti = controlla_rate_limit(email, supabase_client)
        if bloccato:
            return None, f"Troppi tentativi falliti. Riprova tra {minuti} minuti."
        
        # Query base utente attivo: deve restare compatibile anche con schema legacy.
        response = supabase_client.table("users") \
            .select("id, email, nome_ristorante, attivo, pagine_abilitate, "
                "password_hash, partita_iva, created_at, last_login") \
            .eq("email", email) \
            .eq("attivo", True) \
            .execute()
        
        if not response.data:
            registra_tentativo(email, False, supabase_client)
            return None, "Credenziali errate o account disattivato"
        
        user = response.data[0]
        
        # Verifica password
        if verify_and_migrate_password(user, password):
            trial_active = False
            trial_activated_at = None
            try:
                trial_resp = supabase_client.table('users') \
                    .select('trial_active, trial_activated_at') \
                    .eq('id', user['id']) \
                    .maybe_single() \
                    .execute()
                if trial_resp.data:
                    trial_active = trial_resp.data.get('trial_active') is True
                    trial_activated_at = trial_resp.data.get('trial_activated_at')
            except Exception as trial_query_err:
                logger.warning(f"Check trial saltato durante login: {trial_query_err}")

            # 🔒 CHECK TRIAL SCADUTO: se trial attiva ma scaduta, disattiva account
            if trial_active and trial_activated_at:
                try:
                    _trial_start = datetime.fromisoformat(
                        str(trial_activated_at).replace('Z', '+00:00')
                    )
                    if _trial_start.tzinfo is None:
                        _trial_start = _trial_start.replace(tzinfo=timezone.utc)
                    _trial_end = _trial_start + timedelta(days=7)
                    if datetime.now(timezone.utc) > _trial_end:
                        # Trial scaduto: disattiva utente
                        supabase_client.table('users').update({
                            'trial_active': False,
                            'attivo': False,
                        }).eq('id', user['id']).execute()
                        logger.warning(
                            f"⏰ Trial scaduto per user_id={user['id']} "
                            f"(email={email}, attivato={trial_activated_at})"
                        )
                        return None, "Il tuo periodo di prova è scaduto. Contatta il supporto."
                except Exception as _trial_err:
                    logger.warning(f"Errore check trial scaduto: {_trial_err}")

            registra_tentativo(email, True, supabase_client)
            previous_last_login = user.get('last_login')
            login_now_iso = datetime.now(timezone.utc).isoformat()
            # Aggiorna last_login e last_seen_at
            try:
                supabase_client.table('users').update({
                    'last_login': login_now_iso,
                    'last_seen_at': login_now_iso,
                }).eq('id', user['id']).execute()
            except Exception:
                logger.exception('Errore aggiornamento last_login/last_seen_at')

            user['last_login_precedente'] = previous_last_login
            user['last_login'] = login_now_iso
            user['login_at'] = login_now_iso
            
            # Rimuovi dati sensibili prima di restituire (non devono finire in session_state)
            for _sensitive_key in ('password_hash', 'reset_code', 'reset_expires'):
                user.pop(_sensitive_key, None)
            
            return user, None
        else:
            registra_tentativo(email, False, supabase_client)
            return None, "Credenziali errate"
            
    except AuthServiceUnavailableError as e:
        logger.warning(f"Login non disponibile: {e}")
        return None, str(e)
    except Exception as e:
        logger.exception("Errore verifica credenziali")
        if _is_connectivity_error(e):
            return None, "Connessione internet assente o server non raggiungibile. Verifica la connessione e riprova."
        return None, "Errore durante la verifica delle credenziali. Riprova tra qualche minuto."


def riepilogo_fatture_auto_da_ultimo_login(
    user_id: str,
    last_login_precedente: Optional[str],
    login_at: Optional[str] = None,
    supabase_client=None,
) -> Dict[str, Any]:
    """
    Restituisce le fatture auto-ricevute (Invoicetronic) non ancora confermate
    dall'utente (needs_ack=true). Non usa finestre temporali: le fatture appaiono
    finché l'utente non fa Salva/Rifiuta/Salva tutte.
    """
    riepilogo: Dict[str, Any] = {
        'has_new': False,
        'file_count': 0,
        'new_count': 0,
        'pending_count': 0,
        'total_pending_count': 0,
        'row_count': 0,
        'event_count': 0,
        'needs_review_count': 0,
        'recent_files': [],
        'files_detail': [],
        'window_start': last_login_precedente,
        'window_end': login_at,
    }

    if not user_id:
        return riepilogo

    try:
        from services import get_supabase_client

        if supabase_client is None:
            supabase_client = get_supabase_client()

        # Query per needs_ack=true — nessuna finestra temporale.
        # Questo risolve il bug: dopo "Elimina Tutto" + re-run worker,
        # i nuovi record hanno created_at > login_at ma needs_ack=true,
        # quindi compaiono comunque.
        res = supabase_client.table('upload_events') \
            .select('id, file_name, rows_saved, created_at, details, status') \
            .eq('user_id', user_id) \
            .eq('needs_ack', True) \
            .in_('status', ['SAVED_OK', 'SAVED_PARTIAL']) \
            .order('created_at', desc=True) \
            .limit(500) \
            .execute()

        rows = res.data or []

        def _is_invoicetronic_event(event_row: Dict[str, Any]) -> bool:
            details = event_row.get('details') or {}
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except Exception:
                    details = {}
            source = ''
            if isinstance(details, dict):
                source = str(details.get('source') or '').strip().lower()
            return source.startswith('invoicetronic')

        # Mostra in dashboard solo fatture arrivate da Invoicetronic.
        rows = [row for row in rows if _is_invoicetronic_event(row)]

        # Dedup logico per file_name con ACK per-evento: mantieni tutti gli id evento
        # e usa l'evento più recente per i conteggi "nuove" / "in sospeso".
        from collections import defaultdict
        grouped_by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            fname = str(row.get('file_name') or '').strip()
            if not fname:
                continue
            try:
                rows_saved = int(row.get('rows_saved') or 0)
            except (TypeError, ValueError):
                rows_saved = 0
            if rows_saved <= 0:
                continue
            grouped_by_file[fname].append(row)

        auto_events = []
        for fname, frows in grouped_by_file.items():
            latest_row = sorted(
                frows,
                key=lambda r: str(r.get('created_at') or ''),
                reverse=True,
            )[0]
            event_ids = [r.get('id') for r in frows if r.get('id') is not None]
            latest_row = dict(latest_row)
            latest_row['event_ids'] = event_ids
            latest_row['event_count_for_file'] = len(event_ids)
            latest_row['file_name'] = fname
            auto_events.append(latest_row)

        auto_events = sorted(
            auto_events,
            key=lambda r: str(r.get('created_at') or ''),
            reverse=True,
        )

        if not auto_events:
            return riepilogo

        unique_files = []
        row_count = 0

        login_ts = pd.to_datetime(login_at, utc=True, errors='coerce') if login_at else pd.NaT
        nuove_count = 0

        for row in auto_events:
            fname = str(row.get('file_name') or '').strip()
            if fname:
                unique_files.append(fname)
            created_ts = pd.to_datetime(row.get('created_at'), utc=True, errors='coerce')
            if pd.notna(login_ts) and pd.notna(created_ts) and created_ts >= login_ts:
                nuove_count += 1
            try:
                row_count += int(row.get('rows_saved') or 0)
            except (TypeError, ValueError):
                pass

        total_pending_count = len(unique_files)
        pending_count = max(0, total_pending_count - nuove_count)

        # Carica dettagli per-file dalla tabella fatture (singola query batch)
        files_detail = []
        needs_review_count = 0
        if unique_files:
            try:
                fres = supabase_client.table('fatture') \
                    .select('file_origine, fornitore, data_documento, totale_riga, created_at, needs_review') \
                    .eq('user_id', user_id) \
                    .in_('file_origine', unique_files) \
                    .order('created_at', desc=True) \
                    .execute()
                all_rows = fres.data or []
                # Raggruppa per file_origine
                from collections import defaultdict
                grouped = defaultdict(list)
                for r in all_rows:
                    grouped[r.get('file_origine', '')].append(r)
                for fname in unique_files:
                    frows = grouped.get(fname, [])
                    if frows:
                        event_row = next((r for r in auto_events if r.get('file_name') == fname), {})
                        fornitore = frows[0].get('fornitore', 'Sconosciuto')
                        data_doc = frows[0].get('data_documento', '')
                        created = event_row.get('created_at', frows[0].get('created_at', ''))
                        totale = sum(float(r.get('totale_riga') or 0) for r in frows)
                        file_needs_review = sum(1 for r in frows if bool(r.get('needs_review')))
                        needs_review_count += file_needs_review
                        files_detail.append({
                            'file_name': fname,
                            'fornitore': fornitore,
                            'data_documento': data_doc,
                            'created_at': created,
                            'num_righe': len(frows),
                            'totale': round(totale, 2),
                            'needs_review_count': file_needs_review,
                            'event_ids': event_row.get('event_ids', []),
                            'event_count_for_file': event_row.get('event_count_for_file', 1),
                        })
            except Exception:
                logger.exception('Errore caricamento dettagli per-file fatture auto')

        riepilogo.update({
            'has_new': len(unique_files) > 0,
            'file_count': len(unique_files),
            'new_count': nuove_count,
            'pending_count': pending_count,
            'total_pending_count': total_pending_count,
            'row_count': row_count,
            'event_count': len(auto_events),
            'needs_review_count': needs_review_count,
            'recent_files': unique_files[:3],
            'files_detail': files_detail,
        })
        return riepilogo

    except Exception:
        logger.exception('Errore calcolo riepilogo fatture auto da ultimo login')
        return riepilogo


def verifica_sessione_da_cookie(
    token: str,
    inactivity_hours: int = 8,
    supabase_client=None,
) -> Optional[Dict]:
    """
    Verifica un session_token da cookie e controlla timeout inattività.

    Returns:
        - dict user_data (senza campi sensibili) se valido
        - None se token non valido, scaduto o inattivo

    Side-effects:
        - Se la sessione è scaduta per inattività, invalida il token nel DB.
    """
    try:
        from services import get_supabase_client

        if not token:
            return None

        if supabase_client is None:
            supabase_client = get_supabase_client()

        response = supabase_client.table('users') \
            .select("id, email, nome_ristorante, attivo, pagine_abilitate, "
                    "session_token, session_token_created_at, last_seen_at") \
            .eq('session_token', token) \
            .eq('attivo', True) \
            .execute()

        if not response or not getattr(response, 'data', None) or len(response.data) == 0:
            return None

        user = response.data[0]
        now_utc = datetime.now(timezone.utc)

        # Verifica inattività: usa last_seen_at, fallback su session_token_created_at
        last_seen_raw = user.get('last_seen_at') or user.get('session_token_created_at')
        inactive_expired = False
        if last_seen_raw:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen_raw.replace('Z', '+00:00'))
                if last_seen_dt.tzinfo is None:
                    last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
                inactive_expired = (now_utc - last_seen_dt) > timedelta(hours=inactivity_hours)
            except (ValueError, TypeError):
                inactive_expired = True
        else:
            inactive_expired = True

        if inactive_expired:
            # Sessione inattiva → invalida token nel DB
            supabase_client.table('users').update({
                'session_token': None,
                'session_token_created_at': None,
                'last_seen_at': None,
            }).eq('id', user.get('id')).execute()
            logger.info(f"🔒 Sessione scaduta per inattività (>{inactivity_hours}h) - user_id={user.get('id')}")
            return None

        # Rimuovi dati sensibili
        for _sensitive_key in ('password_hash', 'reset_code', 'reset_expires'):
            user.pop(_sensitive_key, None)

        return user

    except Exception as e:
        logger.exception('Errore verifica sessione da cookie')
        return None


def aggiorna_last_seen(user_id: str, supabase_client=None) -> bool:
    """Aggiorna last_seen_at per l'utente indicato. Ritorna True se ok, False se errore."""
    try:
        from services import get_supabase_client

        if not user_id:
            return False

        if supabase_client is None:
            supabase_client = get_supabase_client()

        supabase_client.table('users').update({
            'last_seen_at': datetime.now(timezone.utc).isoformat(),
        }).eq('id', user_id).execute()
        return True
    except Exception:
        logger.exception('Errore aggiornamento last_seen_at')
        return False


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
        
        # Rate limiting: max 1 richiesta reset ogni 5 minuti per email (DB-backed)
        rate_limit_msg = _check_reset_rate_limit(email, supabase_client)
        if rate_limit_msg:
            return False, rate_limit_msg
        
        # Genera codice sicuro (12 bytes = 96 bit entropia)
        code = secrets.token_urlsafe(12)
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
        # Ottieni client Supabase (singleton)
        if supabase_client is None:
            supabase_client = get_supabase_client()
        
        # Verifica esistenza utente PRIMA di salvare il codice (anti-email-relay abuse)
        # Risposta sempre generica per non rivelare se l'email è registrata
        _MSG_GENERICO = "Se l'email è registrata riceverai un codice. Controlla la casella di posta."
        try:
            check_utente = supabase_client.table('users') \
                .select('id') \
                .eq('email', email.lower().strip()) \
                .maybe_single() \
                .execute()
            if not check_utente.data:
                logger.info(f"Reset richiesto per email non registrata: {email}")
                return True, _MSG_GENERICO
        except Exception:
            logger.exception(f"Errore verifica esistenza utente per {email}")
            return False, "Errore temporaneo, riprova tra qualche minuto"

        # Salva codice nel DB
        stored_in_db = True
        try:
            supabase_client.table('users').update({
                'reset_code': code,
                'reset_expires': expires
            }).eq('email', email.lower().strip()).execute()
        except Exception:
            logger.exception(f"Errore salvataggio codice per {email}")
            stored_in_db = False
        
        if not stored_in_db:
            logger.error(f"Impossibile salvare codice reset per {email} — né DB né alternativa disponibile")
            return False, "Errore temporaneo, riprova tra qualche minuto"
        
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
        sender_name = brevo_cfg.get('sender_name', 'OH YEAH! Hub')
        
        # Payload email
        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": email}],
            "subject": "🔑 Codice Recupero Password - OH YEAH! Hub",
            "htmlContent": f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c5aa0;">🔑 Recupero Password</h2>
                <p>Hai richiesto di reimpostare la password per il tuo account <strong>OH YEAH! Hub</strong>.</p>
                <p>Il tuo codice di reset è:</p>
                <div style="text-align: center; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #1e3a8a; background: #f0f4ff; padding: 12px 24px; border-radius: 8px; display: inline-block;">{code}</span>
                </div>
                <p>Il codice scadrà tra <strong>1 ora</strong>.</p>
                <p style="color: #888; font-size: 13px;">Se non hai richiesto questo reset, ignora questa email.</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                <p style="color: #666; font-size: 13px;">---<br><strong>OH YEAH! Hub Team</strong><br>📧 Support: mattiadavolio90@gmail.com</p>
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
            _record_reset_request(email, supabase_client)
            logger.info("Email reset inviata con successo")
            return True, "Email inviata con successo"
        else:
            # Log solo status code, non il body completo (potrebbe contenere headers/token)
            logger.error(f"Brevo API error: {response.status_code} (body omesso per sicurezza)")
            return False, "Errore nell'invio email. Riprova o contatta il supporto."
            
    except requests.exceptions.Timeout:
        logger.error("Timeout invio email Brevo")
        return False, "Errore: timeout connessione a Brevo"
    except Exception:
        logger.exception("Errore invio codice reset")
        return False, "Errore nell'invio email. Riprova o contatta il supporto."


def hash_password(password: str) -> str:
    """Hash password con Argon2 (usa hasher globale)"""
    return ph.hash(password)


def registra_logout_utente(email: str) -> bool:
    """
    Salva timestamp di logout nel database.
    Ogni volta che l'utente fa logout, aggiorniamo un campo nel DB.
    """
    try:
        from services import get_supabase_client
        
        supabase = get_supabase_client()
        if not supabase:
            return False
            
        # Aggiorna last_logout e invalida session_token per sicurezza
        result = supabase.table('users').update({
            'last_logout': datetime.now(timezone.utc).isoformat(),
            'session_token': None,
            'session_token_created_at': None,
        }).eq('email', email).execute()
        
        logger.info(f"✅ Logout registrato per {email}")
        return True
    except Exception as e:
        logger.exception(f"Errore registrazione logout per {email}")
        return False


__all__ = [
    'verify_and_migrate_password',
    'verifica_credenziali',
    'invia_codice_reset',
    'riepilogo_fatture_auto_da_ultimo_login',
    'hash_password',
    'registra_logout_utente',
    # Nuove funzioni GDPR password + P.IVA
    'valida_password_compliance',
    'valida_e_mostra_errori_password',
    'crea_cliente_con_token',
    'imposta_password_da_token',
    # Trial 7 giorni
    'get_trial_info',
    'attiva_trial',
    'disattiva_trial_scaduta',
]


# ============================================================
# TRIAL 7 GIORNI GRATUITI
# ============================================================

_TRIAL_DURATION_DAYS = 7


def get_trial_info(user_id: str, supabase_client=None) -> Dict[str, Any]:
    """
    Legge lo stato trial dell'utente da DB.

    Returns dict:
        is_trial (bool): trial attiva e non ancora scaduta
        days_left (int): giorni interi rimanenti (0 se scaduta o non trial)
        trial_month (int|None): mese numerico corrente durante il trial (1-12)
        trial_year (int|None): anno attivazione trial
        expired (bool): True se trial era attiva ma è scaduta (account da disattivare)
    """
    _default: Dict[str, Any] = {
        'is_trial': False, 'days_left': 0,
        'trial_month': None, 'trial_year': None, 'expired': False,
    }
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()

        resp = supabase_client.table('users') \
            .select('trial_active, trial_activated_at') \
            .eq('id', user_id) \
            .limit(1) \
            .execute()

        if not resp.data:
            return _default

        row = resp.data[0]
        trial_active = row.get('trial_active', False)
        activated_raw = row.get('trial_activated_at')

        if not trial_active or not activated_raw:
            return _default

        activated_at = datetime.fromisoformat(activated_raw.replace('Z', '+00:00'))
        if activated_at.tzinfo is None:
            activated_at = activated_at.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        expires_at = activated_at + timedelta(days=_TRIAL_DURATION_DAYS)

        # Mese/anno in orario italiano (Europa/Roma) per coerenza con l'utente.
        # Evita il boundary fine mese dove UTC è già nel mese successivo (23:30 CEST = 01:30 UTC+1).
        try:
            from zoneinfo import ZoneInfo as _ZI
            _now_it = datetime.now(_ZI('Europe/Rome'))
        except Exception:
            _now_it = datetime.now(timezone.utc)  # fallback Python < 3.9

        if now_utc >= expires_at:
            return {
                'is_trial': False,
                'days_left': 0,
                'trial_month': activated_at.month,
                'trial_year': activated_at.year,
                'expired': True,
            }

        return {
            'is_trial': True,
            'days_left': max(0, (expires_at - now_utc).days),
            'trial_month': _now_it.month,
            'trial_year': _now_it.year,
            'expired': False,
        }
    except Exception:
        logger.exception(f'Errore get_trial_info user_id={user_id}')
        return _default


def attiva_trial(user_id: str, admin_email: str, supabase_client=None) -> Tuple[bool, str]:
    """
    Attiva la trial 7 giorni per un utente (chiamabile solo da admin).

    Returns (True, msg) se ok, (False, errore) altrimenti.
    Non sovrascrive una trial già attiva.
    """
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()

        resp = supabase_client.table('users') \
            .select('email, attivo') \
            .eq('id', user_id) \
            .limit(1) \
            .execute()

        if not resp.data:
            return False, 'Utente non trovato'

        u = resp.data[0]

        if not u.get('attivo'):
            return False, f'Account {u["email"]} disattivato — riattivarlo prima di attivare la trial'

        now_utc = datetime.now(timezone.utc)

        # UPDATE ATOMICO: aggiorna SOLO se trial_active è ancora FALSE.
        # Previene doppia attivazione in caso di click concorrenti da più admin.
        result = supabase_client.table('users').update({
            'trial_active': True,
            'trial_activated_at': now_utc.isoformat(),
        }).eq('id', user_id).eq('trial_active', False).execute()

        if not result.data:
            # 0 righe aggiornate: trial già attiva (race condition o doppio click)
            return False, f'Trial già attiva per {u["email"]} (attivata nel frattempo)'

        logger.info(
            f"🎟️ Trial attivata: user={u['email']} | admin={admin_email} | at={now_utc.isoformat()}"
        )
        return True, f"Trial 7 giorni attivata per {u['email']}"

    except Exception as e:
        logger.exception(f'Errore attiva_trial user_id={user_id}')
        return False, f'Errore: {e}'


def disattiva_trial_scaduta(user_id: str, supabase_client=None) -> bool:
    """
    Disattiva account di un utente la cui trial è scaduta.
    Imposta attivo=False e trial_active=False.
    Chiamata automaticamente nel page-load di app.py quando get_trial_info() ritorna expired=True.
    """
    try:
        from services import get_supabase_client
        if supabase_client is None:
            supabase_client = get_supabase_client()

        result = supabase_client.table('users').update({
            'trial_active': False,
            'attivo': False,
        }).eq('id', user_id).execute()

        if not result.data:
            logger.warning(f"⚠️ disattiva_trial_scaduta: nessuna riga aggiornata per user_id={user_id}")
            return False

        logger.info(f"🔒 Account disattivato per trial scaduta: user_id={user_id}")
        return True
    except Exception:
        logger.exception(f'Errore disattiva_trial_scaduta user_id={user_id}')
        return False
