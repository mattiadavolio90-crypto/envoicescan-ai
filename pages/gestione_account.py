import streamlit as st
import time
import hashlib
from argon2 import PasswordHasher
from services.db_service import elimina_tutte_fatture
from services import get_supabase_client
from services.auth_service import valida_password_compliance
from config.logger_setup import get_logger
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header

# Logger
logger = get_logger('gestione_account')

st.set_page_config(
    page_title="Gestione Account", 
    page_icon="⚙️",
    initial_sidebar_state="expanded"
)

# Nascondi sidebar immediatamente se non loggato
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()

# Verifica autenticazione
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")
    st.stop()

user = st.session_state.user_data
is_admin = st.session_state.get('user_is_admin', False)

# Supabase client
try:
    supabase = get_supabase_client()
except Exception as e:
    st.error("⛔ Errore di connessione al database. Riprova tra qualche minuto.")
    logger.exception("Errore connessione Supabase: %s", e)
    st.stop()

# Hasher password
ph = PasswordHasher()

# ============================================================
# SIDEBAR CONDIVISA
# ============================================================
render_sidebar(user)

render_oh_yeah_header()
st.title("⚙️ Gestione Account")
st.info(f"**Account:** {user.get('email')}")

# ===== TAB: Cambio Password + Elimina Account =====
tab1, tab2, tab3 = st.tabs(["🔑 Cambio Password", "📥 Scarica Dati", "🗑️ Elimina Account"])

# ----- TAB 1: CAMBIO PASSWORD -----
with tab1:
    st.subheader("Modifica Password")
    
    stored_hash_check = user.get('password_hash', '').strip()
    if stored_hash_check and not stored_hash_check.startswith('$argon2'):
        st.warning(
            "⚠️ Il tuo account usa una protezione password obsoleta. "
            "Aggiorna la password per migliorare la sicurezza."
        )
    
    with st.form("form_cambio_password"):
        vecchia_password = st.text_input("Password Attuale", type="password")
        nuova_password = st.text_input("Nuova Password", type="password", help="Minimo 10 caratteri")
        conferma_password = st.text_input("Conferma Nuova Password", type="password")
        
        st.markdown("""
        **Requisiti password:**
        - Almeno 10 caratteri
        - Almeno 3 tra: maiuscola, minuscola, numero, simbolo
        - Non usare password comuni
        """)
        
        submit = st.form_submit_button("✅ Aggiorna Password", use_container_width=True, type="primary")
        
        if submit:
            if not vecchia_password or not nuova_password or not conferma_password:
                st.error("⚠️ Compila tutti i campi")
            elif nuova_password != conferma_password:
                st.error("❌ Le nuove password non coincidono")
            else:
                errori_compliance = valida_password_compliance(
                    nuova_password, 
                    user.get('email', ''), 
                    user.get('nome_ristorante', '')
                )
                if errori_compliance:
                    for err in errori_compliance:
                        st.error(err)
                elif vecchia_password == nuova_password:
                    st.warning("⚠️ La nuova password deve essere diversa da quella attuale")
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
                            import hmac as _hmac
                            sha_hash = hashlib.sha256(vecchia_password.encode()).hexdigest()
                            password_corretta = _hmac.compare_digest(sha_hash, stored_hash)
                        
                        if not password_corretta:
                            st.error("❌ Password attuale errata!")
                        else:
                            # Crea nuovo hash con Argon2 (formato moderno)
                            nuovo_hash = ph.hash(nuova_password)
                            
                            # Aggiorna nel database
                            response = supabase.table('users').update({
                                'password_hash': nuovo_hash
                            }).eq('id', user['id']).execute()
                            
                            if not response.data:
                                st.error("❌ Errore aggiornamento database")
                                logger.error(f"Update fallito per user_id={user['id']}")
                            else:
                                st.success("✅ Password aggiornata con successo!")
                                logger.info(f"Password modificata per {user.get('email')}")
                                st.info("🔄 Reindirizzamento al login tra 2 secondi...")
                                time.sleep(2)
                                
                                # Logout automatico + invalida session_token
                                try:
                                    supabase.table('users').update({'session_token': None}).eq('id', user['id']).execute()
                                except Exception as e:
                                    logger.warning(f"Errore invalidazione session token: {e}")
                                st.session_state.logged_in = False
                                st.session_state.user_data = None
                                st.switch_page("app.py")
                            
                    except Exception as e:
                        logger.exception(f"Errore cambio password per {user.get('email')}")
                        st.error(f"❌ Errore: {str(e)}")

# ----- TAB 2: EXPORT DATI -----
with tab2:
    st.subheader("📥 Esporta i Tuoi Dati")
    
    st.info("""
    **Diritto di Accesso (Art. 15 GDPR)**
    
    Puoi scaricare una copia di tutti i tuoi dati in formato JSON, inclusi:
    - Dati anagrafici account
    - Elenco fatture caricate (metadati)
    - Ristoranti/sedi configurati
    - Classificazioni personalizzate
    """)
    
    if st.button("📥 Genera e Scarica Dati", use_container_width=True, type="primary", key="btn_export_dati"):
        with st.spinner("Preparazione dati in corso..."):
            try:
                import json
                from datetime import datetime, timezone
                
                user_id = user.get('id')
                user_email = user.get('email')
                
                # Prepara dizionario dati
                export_data = {
                    "data_export": datetime.now(timezone.utc).isoformat(),
                    "account": {
                        "email": user.get('email'),
                        "nome_ristorante": user.get('nome_ristorante'),
                        "partita_iva": user.get('partita_iva'),
                        "ragione_sociale": user.get('ragione_sociale'),
                        "created_at": user.get('created_at')
                    },
                    "ristoranti": [],
                    "fatture": [],
                    "classificazioni_manuali": []
                }
                
                # Query ristoranti
                try:
                    ristoranti_query = supabase.table('ristoranti').select('nome_ristorante, partita_iva, ragione_sociale, attivo').eq('user_id', user_id).execute()
                    if ristoranti_query.data:
                        export_data["ristoranti"] = [
                            {
                                "nome": r.get('nome_ristorante'),
                                "piva": r.get('partita_iva'),
                                "ragione_sociale": r.get('ragione_sociale'),
                                "attivo": r.get('attivo')
                            }
                            for r in ristoranti_query.data
                        ]
                except Exception as e:
                    logger.warning(f"Errore query ristoranti export: {e}")
                
                # Query fatture con paginazione e ristorante_id (per GDPR completo)
                try:
                    fatture_export = []
                    offset = 0
                    page_size = 1000
                    while True:
                        fatture_query = supabase.table('fatture').select(
                            'file_origine, fornitore, data_documento, totale_riga, categoria, ristorante_id'
                        ).eq('user_id', user_id)\
                         .order('id', desc=False)\
                         .range(offset, offset + page_size - 1)\
                         .execute()
                        
                        rows = fatture_query.data or []
                        if not rows:
                            break
                        
                        for f in rows:
                            rid = f.get('ristorante_id')
                            fatture_export.append({
                                "file": f.get('file_origine'),
                                "fornitore": f.get('fornitore'),
                                "data": f.get('data_documento'),
                                "totale": f.get('totale_riga'),
                                "categoria": f.get('categoria'),
                                "ristorante_id": rid
                            })
                        
                        if len(rows) < page_size:
                            break
                        offset += page_size
                    
                    export_data["fatture"] = fatture_export
                except Exception as e:
                    logger.warning(f"Errore query fatture export: {e}")
                
                # Query classificazioni manuali con paginazione
                try:
                    class_export = []
                    offset = 0
                    page_size = 1000
                    while True:
                        class_query = supabase.table('classificazioni_manuali').select('*')\
                            .eq('user_id', user_id)\
                            .order('id', desc=False)\
                            .range(offset, offset + page_size - 1)\
                            .execute()
                        rows = class_query.data or []
                        if not rows:
                            break
                        class_export.extend(rows)
                        if len(rows) < page_size:
                            break
                        offset += page_size
                    if class_export:
                        export_data["classificazioni_manuali"] = class_export
                except Exception as e:
                    logger.warning(f"Errore query classificazioni export: {e}")
                
                # Converti in JSON
                json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
                
                # Calcola dimensione file
                file_size_bytes = len(json_data.encode('utf-8'))
                file_size_kb = file_size_bytes / 1024
                
                # Genera nome file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"dati_account_{timestamp}.json"
                
                # Bottone download
                st.success(f"✅ Dati pronti! ({len(export_data['fatture'])} fatture, {len(export_data['ristoranti'])} ristoranti) - {file_size_kb:.1f} KB")
                
                st.download_button(
                    label="💾 Scarica File JSON",
                    data=json_data,
                    file_name=filename,
                    mime="application/json",
                    use_container_width=True,
                    type="primary"
                )
                
                logger.info(f"EXPORT DATI - Generato per {user_email} ({file_size_kb:.1f} KB)")
                
            except Exception as e:
                logger.exception(f"Errore export dati: {e}")
                st.error(f"❌ Errore durante la generazione: {str(e)}")
    
    st.markdown("---")
    st.caption("🔒 I dati esportati sono in formato JSON leggibile. Non contengono informazioni sensibili come password (che sono sempre cifrate).")

# ----- TAB 3: ELIMINA ACCOUNT -----
with tab3:
    st.subheader("Eliminazione Account")
    
    # Gli admin NON possono auto-eliminarsi
    if is_admin:
        st.warning("⚠️ Gli account amministratori non possono essere eliminati da questa interfaccia per motivi di sicurezza.")
    else:
        st.error("""
        ⚠️ **ATTENZIONE: Azione irreversibile**
        
        L'eliminazione dell'account comporta:
        - Cancellazione immediata e permanente di tutti i dati personali
        - Eliminazione di tutte le fatture caricate e delle analisi associate
        - Impossibilità di recuperare i dati dopo l'eliminazione
        
        **Nota:** Questo servizio NON effettua conservazione fiscale. Assicurati di aver salvato le fatture originali presso i canali ufficiali prima di procedere.
        """)
        
        # Checkbox conferma
        conferma_elimina = st.checkbox(
            "Confermo di aver compreso che l'eliminazione è irreversibile e desidero eliminare definitivamente il mio account",
            key="check_elimina_account"
        )
        
        # Bottone eliminazione
        if st.button(
            "🗑️ ELIMINA DEFINITIVAMENTE IL MIO ACCOUNT",
            type="primary" if conferma_elimina else "secondary",
            disabled=not conferma_elimina,
            use_container_width=True,
            key="btn_elimina_account_finale"
        ):
            with st.spinner("⏳ Eliminazione in corso..."):
                try:
                    user_id = user.get('id')
                    user_email = user.get('email')
                    
                    if not user_id:
                        st.error("Errore: ID utente non trovato")
                        st.stop()
                    
                    # STEP 1: Elimina tutte le fatture (di TUTTI i ristoranti)
                    # Temporaneamente rimuovi ristorante_id per eliminare TUTTE le fatture dell'utente
                    saved_ristorante_id = st.session_state.pop('ristorante_id', None)
                    logger.info(f"ELIMINAZIONE ACCOUNT - Inizio per user_id={user_id}, email={user_email}")
                    result_fatture = elimina_tutte_fatture(user_id)
                    
                    if not result_fatture.get('success'):
                        # Ripristina ristorante_id in caso di errore
                        if saved_ristorante_id:
                            st.session_state['ristorante_id'] = saved_ristorante_id
                        st.error(f"Errore eliminazione fatture: {result_fatture.get('error')}")
                        st.stop()
                    
                    logger.info(f"ELIMINAZIONE ACCOUNT - Fatture eliminate: {result_fatture.get('fatture_eliminate', 0)}")
                    
                    # STEP 2: Elimina dati correlati (GDPR Art.17 - diritto alla cancellazione)
                    tables_to_clean = [
                        ('prodotti_utente', 'user_id'),
                        ('classificazioni_manuali', 'user_id'),
                        ('upload_events', 'user_id'),
                        ('margini_mensili', 'user_id'),
                        ('review_confirmed', 'user_id'),
                        ('review_ignored', 'user_id'),
                        ('ricette', 'userid'),
                        ('ingredienti_workspace', 'userid'),
                        ('note_diario', 'userid'),
                        ('ristoranti', 'user_id'),
                    ]
                    for table_name, id_col in tables_to_clean:
                        try:
                            supabase.table(table_name).delete().eq(id_col, user_id).execute()
                            logger.info(f"ELIMINAZIONE ACCOUNT - Pulita tabella {table_name}")
                        except Exception as table_err:
                            logger.warning(f"Errore pulizia tabella {table_name}: {table_err}")
                    
                    try:
                        from services.ai_service import invalida_cache_memoria
                        invalida_cache_memoria()
                    except Exception as e:
                        logger.warning(f"Cache non invalidata post-cambio-password: {e}")
                    
                    # STEP 3: Elimina l'utente dalla tabella users
                    delete_result = supabase.table('users').delete().eq('id', user_id).execute()
                    
                    logger.info(f"ELIMINAZIONE ACCOUNT - Utente {user_email} eliminato dal database")
                    
                    # STEP 4: Pulizia cache e sessione, poi logout
                    st.cache_data.clear()
                    st.session_state.clear()
                    st.session_state.logged_in = False
                    
                    # Messaggio finale
                    st.success("✅ Account eliminato con successo.")
                    st.info("I tuoi dati sono stati rimossi definitivamente dai nostri server. Arrivederci!")
                    
                    time.sleep(3)
                    st.rerun()
                    
                except Exception as e:
                    logger.exception(f"Errore eliminazione account: {e}")
                    st.error(f"❌ Errore durante l'eliminazione: {str(e)}")
                    st.warning("Se il problema persiste, contatta il supporto.")


