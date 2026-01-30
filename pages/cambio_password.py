"""
🔐 CAMBIO PASSWORD - CHECK FORNITORI AI
========================================
Permette ai clienti di cambiare la propria password in autonomia
"""

import streamlit as st
from argon2 import PasswordHasher
import logging
import time
import hashlib

# Import singleton Supabase e logger
from services import get_supabase_client
from config.logger_setup import get_logger

# ============================================================
# CONFIGURAZIONE
# ============================================================

st.set_page_config(
    page_title="Cambio Password - Analisi Fatture AI",
    page_icon="🔐",
    layout="centered"
)

# Logger (usa configurazione centralizzata)
logger = get_logger('cambio_password')

# Supabase client (singleton condiviso - evita multiple connessioni)
try:
    supabase = get_supabase_client()
except Exception as e:
    st.error(f"⛔ Errore connessione database: {e}")
    logger.exception("Errore connessione Supabase")
    st.stop()

# Hasher password
ph = PasswordHasher()

# ============================================================
# CONTROLLO LOGIN
# ============================================================

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.error("🔒 **Accesso Negato**")
    st.warning("Devi effettuare il login per cambiare la password.")
    st.info("👉 Torna alla [pagina principale](/) per accedere.")
    st.stop()

user = st.session_state.user_data

# ============================================================
# INTERFACCIA
# ============================================================

st.title("🔐 Cambio Password")
st.markdown(f"**Utente:** {user.get('email')}")
st.markdown("---")

st.info("💡 **Consiglio:** Usa una password forte con almeno 8 caratteri, maiuscole, minuscole e numeri.")

with st.form("form_cambio_password"):
    vecchia_password = st.text_input(
        "🔑 Password Attuale",
        type="password",
        help="Inserisci la tua password attuale per confermare l'identità"
    )
    
    st.markdown("---")
    
    nuova_password = st.text_input(
        "🆕 Nuova Password",
        type="password",
        help="Minimo 8 caratteri"
    )
    
    conferma_password = st.text_input(
        "✅ Conferma Nuova Password",
        type="password"
    )
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.form_submit_button("🔄 Cambia Password", use_container_width=True, type="primary"):
            # Validazioni
            if not vecchia_password or not nuova_password or not conferma_password:
                st.error("⚠️ Compila tutti i campi!")
            elif nuova_password != conferma_password:
                st.error("❌ Le nuove password non coincidono!")
            elif len(nuova_password) < 8:
                st.error("❌ La nuova password deve essere di almeno 8 caratteri!")
            elif vecchia_password == nuova_password:
                st.warning("⚠️ La nuova password deve essere diversa da quella attuale!")
            else:
                try:
                    # Verifica password attuale (supporta sia Argon2 che SHA256 legacy)
                    stored_hash = user.get('password_hash', '').strip()
                    password_corretta = False
                    
                    # Prova prima con Argon2 (formato moderno)
                    if stored_hash.startswith('$argon2'):
                        try:
                            ph.verify(stored_hash, vecchia_password)
                            password_corretta = True
                        except Exception:
                            password_corretta = False
                    else:
                        # Fallback SHA256 legacy
                        sha_hash = hashlib.sha256(vecchia_password.encode()).hexdigest()
                        password_corretta = (sha_hash == stored_hash)
                    
                    if not password_corretta:
                        st.error("❌ Password attuale errata!")
                        st.stop()
                    
                    # Crea nuovo hash con Argon2 (formato moderno)
                    nuovo_hash = ph.hash(nuova_password)
                    
                    # Aggiorna nel database con gestione errori
                    try:
                        response = supabase.table('users').update({
                            'password_hash': nuovo_hash
                        }).eq('id', user['id']).execute()
                        
                        if not response.data:
                            st.error("❌ Errore aggiornamento database: nessun record modificato")
                            logger.error(f"Update fallito per user_id={user['id']}")
                            st.stop()
                    except Exception as db_error:
                        st.error(f"❌ Errore database: {str(db_error)}")
                        logger.exception(f"Errore update password per {user.get('email')}")
                        st.stop()
                    
                    logger.info(f"✅ Password cambiata per: {user.get('email')}")
                    
                    # Mostra successo
                    st.success("✅ **Password cambiata con successo!**")
                    st.balloons()
                    st.info("🔄 **Reindirizzamento al login tra 2 secondi...**")
                    st.warning("⚠️ Dovrai effettuare il login con la nuova password")
                    
                    # Aspetta 2 secondi per far vedere i messaggi
                    time.sleep(2)
                    
                    # Logout automatico
                    st.session_state.logged_in = False
                    st.session_state.user_data = None
                    
                    # Reindirizza al login
                    st.switch_page("app.py")
                    
                except Exception as e:
                    logger.exception(f"Errore cambio password per {user.get('email')}")
                    st.error(f"❌ Errore durante il cambio password: {str(e)}")
    
    with col2:
        if st.form_submit_button("↩️ Annulla", use_container_width=True):
            st.switch_page("app.py")

# ============================================================
# CONSIGLI SICUREZZA
# ============================================================

st.markdown("---")

with st.expander("🛡️ Consigli per una password sicura"):
    st.markdown("""
    **Una password forte dovrebbe:**
    - ✅ Essere lunga almeno 8 caratteri (meglio 12+)
    - ✅ Contenere lettere maiuscole e minuscole
    - ✅ Includere numeri
    - ✅ Avere simboli speciali (!@#$%&*)
    - ✅ Non contenere informazioni personali (nome, data di nascita, ecc.)
    - ✅ Essere unica per ogni servizio
    
    **Evita:**
    - ❌ Password comuni (password123, 12345678, ecc.)
    - ❌ Sequenze di tastiera (qwerty, asdfgh)
    - ❌ Informazioni facilmente reperibili
    - ❌ Riutilizzare la stessa password su più siti
    
    **Esempi di password forti:**
    - `M1aP@ssw0rd!Sicura`
    - `Caf3$Espresso#2025`
    - `R1stor@nte&Mare!`
    """)

st.markdown("---")
st.caption("🔐 Cambio Password - Check Fornitori AI | © 2025")
