"""
utils/app_controllers.py

Controller estratti da app.py per ridurre la monoliticità del file principale.
Zero breaking changes: ogni funzione usa gli stessi st.session_state e produce
gli stessi side-effect dell'equivalente blocco originale.

Struttura:
  - is_admin_or_impersonating()           helper di sessione
  - mostra_pagina_login(supabase, cookie_manager)
  - load_and_setup_session(supabase, logger, cookie_manager)
  - render_sidebar_and_header(supabase, logger, cookie_manager)  → user
  - render_dashboard_ui(supabase, logger, user)                  → (df_cache, stats_db, uploaded_files)
  - handle_upload_and_ai(supabase, logger, user_id, uploaded_files, df_cache)

Come usarli in app.py (dopo l'inizializzazione di supabase/logger/_cookie_manager):

    from utils.app_controllers import (
        is_admin_or_impersonating, mostra_pagina_login,
        load_and_setup_session, render_sidebar_and_header,
        render_dashboard_ui, handle_upload_and_ai,
    )

    load_and_setup_session(supabase, logger, _cookie_manager)
    user = render_sidebar_and_header(supabase, logger, _cookie_manager)
    df_cache, stats_db, uploaded_files = render_dashboard_ui(supabase, logger, user)
    handle_upload_and_ai(supabase, logger, user['id'], uploaded_files, df_cache)
"""

import streamlit as st
import html as _html
import uuid as _uuid
import secrets as _secrets
import time
import os
from datetime import datetime, timedelta, timezone

from config.constants import (
    ADMIN_EMAILS,
    UI_DELAY_SHORT,
    UI_DELAY_MEDIUM,
    UI_DELAY_LONG,
    MAX_RIGHE_GLOBALE,
    SESSION_INACTIVITY_HOURS as _SESSION_INACTIVITY_HOURS,
    LAST_SEEN_WRITE_THROTTLE_SECONDS as _LAST_SEEN_WRITE_THROTTLE_SECONDS,
)
from utils.ui_helpers import hide_sidebar_css
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ristorante_helper import add_ristorante_filter
from utils.text_utils import format_fattura_label

from services.auth_service import (
    verifica_credenziali,
    invia_codice_reset,
    aggiorna_last_seen,
    imposta_password_da_token,
    verifica_sessione_da_cookie,
    valida_password_compliance,
    get_trial_info as _get_trial_info,
    disattiva_trial_scaduta as _disattiva_trial,
)
from services.db_service import (
    carica_e_prepara_dataframe,
    clear_fatture_cache,
    elimina_fattura_completa,
    elimina_tutte_fatture,
    get_fatture_stats,
)
from services.ai_service import invalida_cache_memoria, mostra_loading_ai


# ============================================================
# HELPER
# ============================================================

def is_admin_or_impersonating() -> bool:
    """
    Helper per verificare se l'utente corrente è admin o in impersonificazione.
    Riduce codice duplicato in tutta l'app.

    Returns:
        bool: True se admin o impersonating, False altrimenti
    """
    return st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False)


# ============================================================
# PAGINA LOGIN  (estratta da app.py righe ~502–754)
# ============================================================

def mostra_pagina_login(supabase, cookie_manager):
    """Form login con recupero password - ESTETICA STREAMLIT PULITA"""
    # Elimina completamente sidebar e pulsante (CSS già applicato globalmente prima del login)
    # Solo CSS aggiuntivo per padding login
    st.markdown("""
        <style>
        /* ✂️ RIDUCI SPAZIO SUPERIORE LOGIN */
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 3rem !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Messaggio scadenza trial (mostrato dopo logout automatico da app.py)
    if st.session_state.pop('_trial_expired_msg', False):
        st.error(
            "⏰ **Prova gratuita scaduta.** Il tuo account è stato disattivato. "
            "Contatta il supporto per attivare un abbonamento."
        )

    render_oh_yeah_header()

    st.markdown("""
<h2 style="font-size: clamp(2.2rem, 5.5vw, 3.2rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🔐 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Accedi al Sistema</span>
</h2>
""", unsafe_allow_html=True)

    # Nota legale senza sfondo
    st.markdown("""
<p style="font-size: clamp(0.7rem, 1.6vw, 0.82rem); color: #1e3a8a; margin: 0.75rem 0 1.25rem 0; line-height: 1.6;">
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</p>
""", unsafe_allow_html=True)

    # ── Informativa cookie (Garante Privacy IT — cookie tecnici strettamente necessari) ──
    st.markdown("""
<div style="background:#f0f7ff;border:1px solid #bdd7f5;border-radius:6px;padding:8px 12px;
            font-size:0.75rem;color:#1e3a8a;margin-bottom:0.8rem;line-height:1.5;">
    🍪 <strong>Cookie tecnici:</strong> Questo sito utilizza esclusivamente cookie tecnici di sessione,
    necessari al funzionamento del servizio. Non vengono usati cookie di profilazione o tracciamento.
    Per maggiori informazioni consulta la pagina dedicata dopo il login.
</div>
""", unsafe_allow_html=True)

    # Tab navigazione stile bottoni
    if 'login_tab_attivo' not in st.session_state:
        st.session_state.login_tab_attivo = "login"

    st.markdown("""
        <style>
        /* Bottone Accedi: azzurro, larghezza 200px */
        div[data-testid="stFormSubmitButton"] button {
            background-color: #0ea5e9 !important;
            color: white !important;
            width: 200px !important;
        }
        div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #0284c7 !important;
        }
        /* Fix altezza pagina */
        .main .block-container {
            max-height: none !important;
        }
        div[data-testid="stForm"] {
            max-height: none !important;
            height: auto !important;
        }
        section[data-testid="stSidebar"] ~ div {
            max-height: none !important;
            overflow-y: auto !important;
        }
        </style>
    """, unsafe_allow_html=True)

    col_lt1, col_lt2, _ = st.columns([1.2, 1.8, 5])
    with col_lt1:
        if st.button("🔑 LOGIN", key="lt_btn_login", use_container_width=True,
                     type="primary" if st.session_state.login_tab_attivo == "login" else "secondary"):
            if st.session_state.login_tab_attivo != "login":
                st.session_state.login_tab_attivo = "login"
                st.rerun()
    with col_lt2:
        if st.button("🔄 RECUPERA PASSWORD", key="lt_btn_reset", use_container_width=True,
                     type="primary" if st.session_state.login_tab_attivo == "reset" else "secondary"):
            if st.session_state.login_tab_attivo != "reset":
                st.session_state.login_tab_attivo = "reset"
                st.rerun()

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    if st.session_state.login_tab_attivo == "login":
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input("🔑 Password", type="password", placeholder="La tua password")

            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Accedi")

            if submit:
                if not email or not password:
                    st.error("⚠️ Compila tutti i campi!")
                else:
                    with st.spinner("Verifica credenziali..."):
                        user, errore = verifica_credenziali(email, password)

                        if user:
                            user.pop('password_hash', None)  # Non esporre hash in session
                            st.session_state.force_logout = False
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False  # ← Reset flag logout

                            # Salva P.IVA in session_state per validazione fatture
                            st.session_state.partita_iva = user.get('partita_iva')
                            st.session_state.created_at = user.get('created_at')

                            # Pulizia chiave login UI
                            st.session_state.pop('login_tab_attivo', None)

                            # 🍪 Genera e salva session_token nel DB + cookie persistente
                            if cookie_manager is not None:
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _s_token = _secrets.token_urlsafe(32)
                                    supabase.table('users').update({
                                        'session_token': _s_token,
                                        'session_token_created_at': _now_utc.isoformat(),
                                        'last_seen_at': _now_utc.isoformat(),
                                    }).eq('id', user.get('id')).execute()
                                    cookie_manager.set("session_token", _s_token,
                                                       expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                                                       secure=True, same_site="strict")
                                    st.session_state._last_seen_write_at = _now_utc.isoformat()
                                except Exception as _ce:
                                    import logging as _lg
                                    _lg.getLogger('fci_app').warning(f"Errore salvataggio session token: {_ce}")
                            else:
                                st.warning(
                                    "⚠️ Sessione non persistente: "
                                    "verifica che i cookie siano abilitati nel browser. "
                                    "Verrai disconnesso ad ogni aggiornamento pagina."
                                )

                            # Verifica se è admin e imposta flag
                            if user.get('email') in ADMIN_EMAILS:
                                st.session_state.user_is_admin = True
                                import logging as _lg
                                _lg.getLogger('fci_app').info(f"✅ Login ADMIN: user_id={user.get('id')}")
                                st.success("✅ Accesso effettuato come ADMIN!")
                                time.sleep(UI_DELAY_SHORT)
                                st.switch_page("pages/admin.py")
                                st.stop()
                            else:
                                st.session_state.user_is_admin = False
                                import logging as _lg
                                _lg.getLogger('fci_app').info(f"✅ Login cliente: user_id={user.get('id')}")
                                st.success("✅ Accesso effettuato!")
                                time.sleep(UI_DELAY_MEDIUM)
                                st.rerun()
                        else:
                            st.error(f"❌ {errore}")

    elif st.session_state.login_tab_attivo == "reset":
        st.markdown("#### Reset Password via Email")
        st.markdown("""
            <style>
            div.st-key-reset_btn_invia button {
                width: auto !important;
                min-width: unset !important;
                background-color: #0ea5e9 !important;
                color: white !important;
            }
            div.st-key-reset_btn_invia button:hover {
                background-color: #0284c7 !important;
            }
            div.st-key-reset_btn_conferma button {
                width: auto !important;
                min-width: unset !important;
            }
            </style>
        """, unsafe_allow_html=True)

        reset_email = st.text_input("📧 Email per reset", placeholder="tua@email.com", key="reset_email")

        with st.container(key="reset_btn_invia"):
            if st.button("📨 Invia Codice"):
                if not reset_email:
                    st.warning("⚠️ Inserisci un'email")
                else:
                    success, msg = invia_codice_reset(reset_email)
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                        st.info(f"ℹ️ {msg}")

        st.markdown("---")

        code_input = st.text_input("🔢 Codice ricevuto", placeholder="Inserisci il codice", key="code_input")
        new_pwd = st.text_input("🔑 Nuova password (min 10 caratteri)", type="password", key="new_pwd")
        confirm_pwd = st.text_input("🔑 Conferma password", type="password", key="confirm_pwd")

        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        with st.container(key="reset_btn_conferma"):
            if st.button("✅ Conferma Reset", type="primary"):
                if not reset_email or not code_input or not new_pwd or not confirm_pwd:
                    st.warning("⚠️ Compila tutti i campi")
                elif new_pwd != confirm_pwd:
                    st.error("❌ Le password non coincidono")
                else:
                    errori = valida_password_compliance(new_pwd, reset_email)
                    if errori:
                        for e in errori:
                            st.error(f"❌ {e}")
                    else:
                        successo, messaggio, user = imposta_password_da_token(code_input, new_pwd)

                        if successo and user:
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False
                            st.session_state.pop('login_tab_attivo', None)
                            if cookie_manager is not None:
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _s_token = _secrets.token_urlsafe(32)
                                    supabase.table('users').update({
                                        'session_token': _s_token,
                                        'session_token_created_at': _now_utc.isoformat(),
                                        'last_seen_at': _now_utc.isoformat(),
                                    }).eq('id', user.get('id')).execute()
                                    cookie_manager.set("session_token", _s_token,
                                                       expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                                                       secure=True, same_site="strict")
                                    st.session_state._last_seen_write_at = _now_utc.isoformat()
                                except Exception:
                                    pass
                            else:
                                st.warning(
                                    "⚠️ Sessione non persistente: "
                                    "verifica che i cookie siano abilitati nel browser. "
                                    "Verrai disconnesso ad ogni aggiornamento pagina."
                                )
                            st.success("✅ Password aggiornata! Accesso automatico...")
                            time.sleep(UI_DELAY_LONG)
                            st.rerun()
                        else:
                            st.error(f"❌ {messaggio}")


# ============================================================
# 1. LOAD AND SETUP SESSION  (estratto da app.py righe ~214–490)
# ============================================================

def load_and_setup_session(supabase, logger, cookie_manager):
    """
    Gestisce tutto il ciclo di sessione/cookie prima del login:
      - Imposta cookie impersonazione (richiesto da admin.py via session_state)
      - Timeout impersonazione (max 30 minuti)
      - Logout forzato via query params (?logout=1)
      - Ripristino sessione da cookie persistente
      - Aggiornamento last_seen con throttling (max 1 scrittura ogni 5 min)
      - Gestione token reset password (nuovo cliente + recupero password)

    Chiama st.stop() internamente sui path che arrestano il rendering
    (es. primo caricamento cookie, reset password).
    Non restituisce nulla — modifica st.session_state direttamente.
    """
    # ============================================
    # IMPOSTA COOKIE IMPERSONAZIONE (richiesto da admin.py via session_state)
    # ============================================
    # admin.py imposta _set_impersonation_cookie prima di switch_page("app.py").
    # Qui lo leggiamo e scriviamo il cookie browser, così sopravvive al F5.
    if st.session_state.get('_set_impersonation_cookie') and cookie_manager is not None:
        try:
            cookie_manager.set(
                "impersonation_user_id",
                str(st.session_state['_set_impersonation_cookie']),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                secure=True, same_site="strict"
            )
        except Exception as _ice:
            logger.warning(f"Errore impostazione cookie impersonazione: {_ice}")
        del st.session_state['_set_impersonation_cookie']

    # ============================================
    # TIMEOUT IMPERSONAZIONE (max 30 minuti)
    # ============================================
    if st.session_state.get('impersonating', False):
        _imp_started_raw = st.session_state.get('impersonation_started_at')
        if _imp_started_raw:
            try:
                _imp_started_dt = datetime.fromisoformat(str(_imp_started_raw).replace('Z', '+00:00'))
                if _imp_started_dt.tzinfo is None:
                    _imp_started_dt = _imp_started_dt.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - _imp_started_dt) > timedelta(minutes=30):
                    _imp_client_email = st.session_state.get('user_data', {}).get('email', '?')
                    _imp_admin_email = st.session_state.get('admin_original_user', {}).get('email', '?')
                    logger.warning(f"🔒 IMPERSONATION TIMEOUT: admin={_imp_admin_email} → client={_imp_client_email}")
                    # Ripristina admin
                    if 'admin_original_user' in st.session_state:
                        st.session_state.user_data = st.session_state.admin_original_user.copy()
                        del st.session_state.admin_original_user
                    st.session_state.impersonating = False
                    st.session_state.user_is_admin = True
                    st.session_state.pop('impersonation_started_at', None)
                    if cookie_manager is not None:
                        try:
                            cookie_manager.set("impersonation_user_id", "",
                                               expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                        except Exception:
                            pass
                    st.warning("⏰ Sessione impersonazione scaduta (30 min). Sei tornato admin.")
                    st.rerun()
            except (ValueError, TypeError):
                pass

    # ============================================
    # GESTIONE LOGOUT FORZATO VIA QUERY PARAMS
    # ============================================
    if st.query_params.get("logout") == "1":
        logger.warning("🚨 LOGOUT FORZATO via query params - pulizia sessione")
        # Token già invalidato da sidebar_helper, ma tenta anche qui come fallback
        try:
            _email_for_logout = st.session_state.get('user_data', {}).get('email')
            if _email_for_logout:
                supabase.table('users').update({
                    'session_token': None,
                    'session_token_created_at': None,
                    'last_seen_at': None,
                }).eq('email', _email_for_logout).execute()
        except Exception as _logout_err:
            logger.warning(f"⚠️ Impossibile invalidare session_token in DB durante logout: {_logout_err}")
        st.session_state.clear()
        st.session_state.logged_in = False
        st.session_state.force_logout = True
        st.session_state._cookie_checked = True
        st.query_params.clear()
        st.rerun()

    # Ripristina sessione da cookie solo se NON in stato di logout forzato
    _force_logout_active = st.session_state.get('force_logout', False)

    if not st.session_state.logged_in and not _force_logout_active and cookie_manager is not None:
        try:
            _token_cookie = cookie_manager.get("session_token")
            if _token_cookie:
                _u = verifica_sessione_da_cookie(_token_cookie, inactivity_hours=_SESSION_INACTIVITY_HOURS)
                if _u:
                    st.session_state.logged_in = True
                    st.session_state.user_data = _u
                    st.session_state.partita_iva = _u.get('partita_iva')
                    st.session_state.created_at = _u.get('created_at')
                    if _u.get('email') in ADMIN_EMAILS:
                        st.session_state.user_is_admin = True
                    logger.info(f"✅ Sessione ripristinata da token per user_id={_u.get('id')}")
                else:
                    # Token non valido, scaduto o inattivo → pulisci cookie e vai al login
                    try:
                        cookie_manager.set("session_token", "",
                                           expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    except Exception:
                        pass
                    logger.info("🔒 Session token non valido o scaduto - richiesto login")
                    st.session_state._cookie_checked = True
            elif not st.session_state.get('_cookie_checked', False):
                # Primo render: CookieManager non ha ancora letto i cookie, aspetta un ciclo
                st.session_state._cookie_checked = True
                st.markdown("""
                    <div style='display:flex;align-items:center;justify-content:center;
                                height:80vh;flex-direction:column;gap:12px;'>
                        <div style='font-size:2rem;'>⏳</div>
                        <div style='color:#94a3b8;font-size:0.95rem;'>Caricamento sessione...</div>
                    </div>
                """, unsafe_allow_html=True)
                st.stop()
            # else: nessun token e già controllato → login normale
        except Exception as cookie_err:
            logger.warning(f"Errore ripristino sessione da cookie: {cookie_err}")

    # ✅ Reset contatore anti-loop SOLO nella pagina login (non loggato)
    # Il reset nel flow autenticato avviene DOPO il render completo
    if not st.session_state.get('logged_in', False):
        st.session_state._rerun_guard = 0

    # Aggiorna last_seen_at con throttling: massimo 1 scrittura ogni 5 minuti per sessione Streamlit
    if st.session_state.get('logged_in', False):
        _active_user_id = st.session_state.get('user_data', {}).get('id')
        if _active_user_id:
            _now_utc = datetime.now(timezone.utc)
            _last_seen_write_raw = st.session_state.get('_last_seen_write_at')
            _should_write_last_seen = False

            if not _last_seen_write_raw:
                _should_write_last_seen = True
            else:
                try:
                    _last_write_dt = datetime.fromisoformat(str(_last_seen_write_raw).replace('Z', '+00:00'))
                    if _last_write_dt.tzinfo is None:
                        _last_write_dt = _last_write_dt.replace(tzinfo=timezone.utc)
                    _should_write_last_seen = (_now_utc - _last_write_dt).total_seconds() >= _LAST_SEEN_WRITE_THROTTLE_SECONDS
                except (ValueError, TypeError):
                    _should_write_last_seen = True

            if _should_write_last_seen:
                if aggiorna_last_seen(_active_user_id, supabase):
                    st.session_state._last_seen_write_at = _now_utc.isoformat()

    # ============================================================
    # GESTIONE TOKEN RESET PASSWORD (NUOVO CLIENTE + RECUPERO PASSWORD)
    # ============================================================
    # Se c'è il parametro reset_token, mostra form impostazione password
    if st.query_params.get("reset_token"):
        reset_token = st.query_params.get("reset_token")

        # Nascondi sidebar per pagina pulita
        hide_sidebar_css()

        st.title("🔐 Imposta la tua Password")

        # Verifica token valido
        try:
            check_result = supabase.table('users')\
                .select('id, email, nome_ristorante, reset_expires, password_hash')\
                .eq('reset_code', reset_token)\
                .execute()

            if not check_result.data:
                st.error("❌ Link non valido o già utilizzato")
                st.info("💡 Se hai già impostato la password, vai al login. Altrimenti contatta il supporto per un nuovo link.")
                if st.button("🔑 Vai al Login"):
                    st.query_params.clear()
                    st.rerun()
                st.stop()

            user_data = check_result.data[0]

            # Check scadenza token
            expires_str = user_data.get('reset_expires')
            if expires_str:
                try:
                    expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                    now_utc = datetime.now(timezone.utc)
                    if now_utc > expires:
                        st.error("⏰ Link scaduto (validità: 24 ore)")
                        st.info("💡 Contatta il supporto per ricevere un nuovo link di attivazione.")
                        st.stop()
                except Exception as e:
                    logger.warning(f"Errore parsing data scadenza token: {e}")

            # Mostra info utente
            is_nuovo_cliente = user_data.get('password_hash') is None

            if is_nuovo_cliente:
                st.success(f"✅ Benvenuto, **{user_data.get('nome_ristorante')}**!")
                st.info(f"📧 Il tuo account: **{user_data.get('email')}**")
                st.markdown("Imposta una password sicura per accedere all'app.")
            else:
                st.info(f"📧 Reset password per: **{user_data.get('email')}**")

            # Form impostazione password
            with st.form("form_imposta_password"):
                nuova_password = st.text_input(
                    "🔑 Nuova Password",
                    type="password",
                    help="Minimo 10 caratteri, con maiuscola, minuscola e numero"
                )
                conferma_password = st.text_input(
                    "🔑 Conferma Password",
                    type="password"
                )
                st.markdown("""
                **Requisiti password:**
                - ✅ Almeno 10 caratteri
                - ✅ Almeno 3 tra: maiuscola, minuscola, numero, simbolo
                - ❌ Non usare email o nome ristorante
                - ❌ Non usare password comuni
                """)

                # GDPR Art.6 — consenso esplicito al trattamento dati (solo primo accesso)
                gdpr_accepted = True  # default per reset password (utente già registrato)
                if is_nuovo_cliente:
                    gdpr_accepted = st.checkbox(
                        "✅ Ho letto e accetto l'[Informativa Privacy](/?page=privacy) "
                        "(D.lgs. 196/2003 e GDPR UE 2016/679). "
                        "Acconsento al trattamento dei miei dati per l'erogazione del servizio.",
                        key="gdpr_consent_activation"
                    )

                submitted = st.form_submit_button("✅ Conferma Password", type="primary", use_container_width=True)

                if submitted:
                    # Validazioni
                    if is_nuovo_cliente and not gdpr_accepted:
                        st.error("⚠️ Devi accettare l'Informativa Privacy per continuare.")
                    elif not nuova_password or not conferma_password:
                        st.error("⚠️ Compila entrambi i campi password")
                    elif nuova_password != conferma_password:
                        st.error("❌ Le password non coincidono")
                    else:
                        # Valida compliance GDPR
                        errori = valida_password_compliance(
                            nuova_password,
                            user_data.get('email', ''),
                            user_data.get('nome_ristorante', '')
                        )
                        if errori:
                            for err in errori:
                                st.error(err)
                        else:
                            # Imposta password
                            successo, messaggio, _ = imposta_password_da_token(
                                reset_token,
                                nuova_password,
                                supabase
                            )
                            if successo:
                                st.success("""
                                🎉 **Password impostata con successo!**

                                Ora puoi effettuare il login con la tua email e password.
                                """)
                                st.balloons()
                                # Pulisci token da URL
                                time.sleep(UI_DELAY_LONG)
                                st.query_params.clear()
                                st.rerun()
                            else:
                                st.error(messaggio)

        except Exception as e:
            st.error("❌ Errore durante la verifica del link. Riprova o contatta il supporto.")
            logger.exception("Errore verifica reset_token")

        st.stop()  # Non mostrare resto app


# ============================================================
# 2. RENDER SIDEBAR AND HEADER  (estratto da app.py righe ~754–1430)
# ============================================================

def render_sidebar_and_header(supabase, logger, cookie_manager):
    """
    Gestisce il ciclo post-sessione:
      - Verifica login (chiama mostra_pagina_login se non loggato, poi st.stop)
      - Ripristino flag admin e impersonazione da cookie (dopo F5/refresh)
      - Caricamento ristoranti (multi-ristorante), creazione automatica se legacy
      - Redirect admin puro → pannello admin
      - Verifica scadenza trial + logout automatico
      - Banner impersonazione con pulsante "Torna Admin"
      - Render sidebar e header OH YEAH!
      - Trial banner (giorni rimanenti)
      - Dropdown multi-ristorante (se cliente con più ristoranti)

    Returns:
        user (dict): dati utente aggiornati da st.session_state.user_data
    """
    # ============================================================
    # CHECK LOGIN ALL'AVVIO
    # ============================================================
    # (logged_in già inizializzato sopra — in load_and_setup_session)

    # VERIFICA FINALE: se force_logout è attivo, FORZA logged_in = False
    if st.session_state.get('force_logout', False):
        logger.critical("⛔ force_logout attivo - forzando logged_in=False")
        st.session_state.logged_in = False
        st.session_state.user_data = None

    # Se NON loggato, mostra login e STOP
    if not st.session_state.get('logged_in', False):
        logger.info("👤 Utente non loggato - mostrando pagina login")
        st.session_state._rerun_guard = 0
        mostra_pagina_login(supabase, cookie_manager)
        st.stop()

    # Se arrivi qui, sei loggato! Vai DIRETTO ALL'APP
    user = st.session_state.user_data

    # ULTIMA VERIFICA: se user_data è None o invalido, FORZA logout immediato
    if not user or not user.get('email'):
        logger.critical("❌ user_data è None o mancante email - FORZA LOGOUT")
        if cookie_manager is not None:
            try:
                # Invalida token nel DB prima di pulire la sessione
                _email_emergency = st.session_state.get('user_data', {}).get('email') if st.session_state.get('user_data') else None
                if _email_emergency:
                    supabase.table('users').update({
                        'session_token': None,
                        'session_token_created_at': None,
                        'last_seen_at': None,
                    }).eq('email', _email_emergency).execute()
            except Exception:
                pass
        st.session_state.clear()
        st.session_state.logged_in = False
        st.session_state.force_logout = True
        st.session_state._cookie_checked = True
        st.rerun()

    # ============================================
    # VERIFICA E RIPRISTINO FLAG ADMIN
    # ============================================
    # Ripristina flag admin se l'utente è in ADMIN_EMAILS
    # (necessario perché session_state viene perso al refresh della pagina)
    if user.get('email') in ADMIN_EMAILS:
        if not st.session_state.get('user_is_admin', False):
            st.session_state.user_is_admin = True
            logger.info(f"✅ Flag admin ripristinato per user_id={user.get('id')}")
    else:
        # Assicura che non-admin non abbiano il flag
        if st.session_state.get('user_is_admin', False):
            st.session_state.user_is_admin = False
            logger.warning(f"⚠️ Flag admin rimosso per utente non-admin: user_id={user.get('id')}")

    # ============================================
    # RIPRISTINO IMPERSONAZIONE DA COOKIE (dopo F5/refresh)
    # ============================================
    # Se l'admin è loggato ma non sta impersonando, controlla se c'era
    # un'impersonazione attiva prima del refresh e ripristinala.
    if (st.session_state.get('user_is_admin', False)
            and not st.session_state.get('impersonating', False)
            and cookie_manager is not None):
        try:
            _imp_uid_cookie = cookie_manager.get("impersonation_user_id")
            if _imp_uid_cookie:
                _imp_resp = supabase.table("users") \
                    .select("id, email, nome_ristorante, attivo, pagine_abilitate") \
                    .eq("id", _imp_uid_cookie).eq("attivo", True).execute()
                if _imp_resp and _imp_resp.data:
                    _imp_customer = _imp_resp.data[0]
                    # Salva dati admin originali e passa a quelli del cliente
                    st.session_state.admin_original_user = st.session_state.user_data.copy()
                    st.session_state.user_data = {
                        'id': _imp_customer['id'],
                        'email': _imp_customer['email'],
                        'nome_ristorante': _imp_customer.get('nome_ristorante'),
                        'attivo': _imp_customer.get('attivo', True),
                        'pagine_abilitate': _imp_customer.get('pagine_abilitate'),
                    }
                    st.session_state.user_is_admin = False
                    st.session_state.impersonating = True
                    # Preserva il timestamp originale se già presente (evita reset timer ad ogni F5)
                    if not st.session_state.get('impersonation_started_at'):
                        st.session_state.impersonation_started_at = datetime.now(timezone.utc).isoformat()
                    # Aggiorna variabile locale user per il resto della pagina
                    user = st.session_state.user_data
                    logger.info(f"✅ Impersonazione ripristinata da cookie dopo refresh: user_id={_imp_customer.get('id')}")
                else:
                    # Cliente non trovato (disattivato o cancellato) → pulisci il cookie
                    cookie_manager.set("impersonation_user_id", "",
                                       expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    logger.warning(f"⚠️ Cliente impersonato non trovato (id={_imp_uid_cookie}) - cookie rimosso")
        except Exception as _imp_e:
            logger.warning(f"Errore ripristino impersonazione da cookie: {_imp_e}")

    # ============================================
    # CARICAMENTO RISTORANTI (MULTI-RISTORANTE STEP 2)
    # ============================================
    # Carica ristoranti dell'utente (oppure TUTTI i ristoranti se admin)
    # ⚠️ SAFETY CHECK: Verifica che user sia definito
    if not user or not user.get('id'):
        logger.error("❌ ERRORE CRITICO: user non definito in caricamento ristoranti")
        st.session_state.logged_in = False
        st.session_state.force_logout = True
        st.session_state._cookie_checked = True
        st.rerun()

    if 'ristoranti' not in st.session_state or not st.session_state.get('ristorante_id'):
        try:
            # Admin: carica TUTTI i ristoranti dal sistema
            if st.session_state.get('user_is_admin', False):
                ristoranti = supabase.table('ristoranti')\
                    .select('id, nome_ristorante, partita_iva, ragione_sociale, user_id')\
                    .eq('attivo', True)\
                    .order('nome_ristorante')\
                    .execute()
                logger.info(f"👨‍💼 ADMIN: Caricati {len(ristoranti.data) if ristoranti.data else 0} ristoranti (tutti i clienti)")
            else:
                # Utente normale: carica solo i propri ristoranti
                ristoranti = supabase.table('ristoranti')\
                    .select('id, nome_ristorante, partita_iva, ragione_sociale')\
                    .eq('user_id', user.get('id'))\
                    .eq('attivo', True)\
                    .execute()
                logger.info(f"🔍 DEBUG: Caricati {len(ristoranti.data) if ristoranti.data else 0} ristoranti per user_id={user.get('id')}")

            st.session_state.ristoranti = ristoranti.data if ristoranti.data else []

            # Se ha ristoranti, imposta il default
            if st.session_state.ristoranti:
                # Se non c'è un ristorante selezionato, usa l'ultimo usato (se ancora disponibile)
                if 'ristorante_id' not in st.session_state:
                    ultimo_id = user.get('ultimo_ristorante_id')
                    ristorante_default = None
                    if ultimo_id:
                        ristorante_default = next(
                            (r for r in st.session_state.ristoranti if r['id'] == ultimo_id), None
                        )
                    if ristorante_default is None:
                        ristorante_default = st.session_state.ristoranti[0]
                    st.session_state.ristorante_id = ristorante_default['id']
                    st.session_state.partita_iva = ristorante_default['partita_iva']
                    st.session_state.nome_ristorante = ristorante_default['nome_ristorante']
                    logger.info(f"🏢 Ristorante caricato: rist_id={ristorante_default['id']}{' [ultimo usato]' if ultimo_id and ristorante_default['id'] == ultimo_id else ' [primo in lista]'}")
            else:
                # ⚠️ UTENTE LEGACY: Nessun ristorante trovato
                if not st.session_state.get('user_is_admin', False):
                    piva = user.get('partita_iva')
                    nome = user.get('nome_ristorante')
                    user_id_r = user.get('id')

                    # Tenta creazione automatica ristorante se ha P.IVA
                    if piva and user_id_r:
                        logger.warning(f"⚠️ Utente legacy {user_id_r} senza ristoranti - tentativo creazione automatica")
                        logger.warning(f"   Dati: nome='{nome}', piva='{piva}'")
                        try:
                            # Cerca ristorante con questa P.IVA DELLO STESSO UTENTE
                            check_existing = supabase.table('ristoranti')\
                                .select('id, user_id, nome_ristorante')\
                                .eq('partita_iva', piva)\
                                .eq('user_id', user_id_r)\
                                .execute()

                            if check_existing.data and len(check_existing.data) > 0:
                                # È il suo ristorante, usalo
                                existing = check_existing.data[0]
                                st.session_state.ristoranti = [existing]
                                st.session_state.ristorante_id = existing['id']
                                st.session_state.partita_iva = piva
                                st.session_state.nome_ristorante = existing['nome_ristorante']
                                logger.info(f"✅ Ristorante esistente trovato e collegato: {existing['id']}")
                            else:
                                # Non esiste, crea nuovo
                                nome_rist = nome or f"Ristorante {piva}"
                                new_rist = supabase.table('ristoranti').insert({
                                    'user_id': user_id_r,
                                    'nome_ristorante': nome_rist,
                                    'partita_iva': piva,
                                    'ragione_sociale': user.get('ragione_sociale', ''),
                                    'attivo': True
                                }).execute()

                                if new_rist.data:
                                    st.session_state.ristoranti = new_rist.data
                                    st.session_state.ristorante_id = new_rist.data[0]['id']
                                    st.session_state.partita_iva = piva
                                    st.session_state.nome_ristorante = nome
                                    logger.info(f"✅ Ristorante creato automaticamente: {new_rist.data[0]['id']}")
                                    st.success("✅ Account configurato correttamente!")
                                    st.rerun()
                                else:
                                    logger.error(f"❌ Creazione ristorante fallita per utente {user_id_r} - response vuota")
                                    st.warning("⚠️ Configurazione account incompleta. Alcune funzionalità potrebbero non essere disponibili.")
                        except Exception as create_err:
                            logger.error(f"❌ ERRORE DETTAGLIATO creazione ristorante: {str(create_err)}")
                            logger.error(f"   Tipo errore: {type(create_err).__name__}")
                            st.warning(f"⚠️ Problemi di configurazione rilevati: {str(create_err)[:100]}")
                    else:
                        # Nessuna P.IVA o dati mancanti - permetti comunque l'accesso
                        logger.warning(f"⚠️ Utente {user_id_r} senza ristoranti e dati incompleti - accesso limitato")
                        st.warning("⚠️ Configurazione account incompleta. Contatta l'assistenza per configurare il tuo ristorante.")

                # FALLBACK vecchio codice per compatibilità
                # ⚠️ Solo se ristoranti NON è stato popolato dalle operazioni sopra
                if not st.session_state.get('user_is_admin', False) and not st.session_state.get('ristoranti'):
                    piva = user.get('partita_iva')
                    nome = user.get('nome_ristorante')
                    logger.warning(f"⚠️ Utente {user.get('email')} senza ristoranti in tabella - fallback su dati users")
                    # Imposta dati di fallback dalla tabella users
                    st.session_state.partita_iva = piva
                    st.session_state.nome_ristorante = nome
                elif st.session_state.get('user_is_admin', False) and not st.session_state.get('ristoranti'):
                    # Admin senza ristoranti nel sistema
                    logger.warning("⚠️ Admin senza ristoranti nel sistema")
        except Exception as e:
            logger.exception(f"Errore caricamento ristoranti: {e}")
            # Fallback: usa dati utente (solo per non-admin)
            if not st.session_state.get('user_is_admin', False):
                st.session_state.ristoranti = []
                st.session_state.partita_iva = user.get('partita_iva')
                st.session_state.nome_ristorante = user.get('nome_ristorante')

    # ============================================
    # ADMIN PURO: REDIRECT A PANNELLO ADMIN
    # ============================================
    # L'admin (non impersonificato) non accede alle pagine app, solo al pannello admin.
    if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
        logger.info(f"👨‍💼 Admin user_id={user.get('id')} su app.py → redirect a pannello admin")
        st.switch_page("pages/admin.py")
        st.stop()

    # ============================================
    # TRIAL: VERIFICA SCADENZA + CARICA INFO
    # ============================================
    # Solo per utenti normali (non admin, non impersonazione da admin)
    if (
        not st.session_state.get('user_is_admin', False)
        and not st.session_state.get('impersonating', False)
        and user.get('id')
    ):
        _t_uid = user['id']
        _t_now = datetime.now(timezone.utc)
        _t_last_raw = st.session_state.get('_trial_check_at')

        # Forza refresh anche se il TTL non è scaduto ma il mese in cache
        # non corrisponde al mese corrente (es. cache rimasta da sessione precedente).
        _cached_ti = st.session_state.get('trial_info', {})
        _cached_month = _cached_ti.get('trial_month')
        _current_month = _t_now.month
        _month_mismatch = (
            _cached_ti.get('is_trial') and
            _cached_month is not None and
            _cached_month != _current_month
        )

        _t_needs_refresh = (
            'trial_info' not in st.session_state
            or not _t_last_raw
            or _month_mismatch
            or (_t_now - datetime.fromisoformat(
                str(_t_last_raw).replace('Z', '+00:00')
            )).total_seconds() > 300
        )
        if _t_needs_refresh:
            _fresh_ti = _get_trial_info(_t_uid, supabase)
            st.session_state.trial_info = _fresh_ti
            st.session_state._trial_check_at = _t_now.isoformat()
            if _fresh_ti.get('expired'):
                _ok_dis = _disattiva_trial(_t_uid, supabase)
                if not _ok_dis:
                    logger.error(
                        f"⚠️ disattiva_trial_scaduta FALLITA per user_id={_t_uid} "
                        f"— logout forzato comunque, il DB verrà aggiornato al prossimo tentativo"
                    )
                try:
                    supabase.table('users').update({
                        'session_token': None,
                        'session_token_created_at': None,
                    }).eq('id', _t_uid).execute()
                except Exception as _tok_err:
                    logger.error(f"Errore invalidazione session_token per trial scaduta: {_tok_err}")
                st.session_state.clear()
                st.session_state.logged_in = False
                st.session_state._trial_expired_msg = True
                logger.warning(f"⏰ Trial scaduta → logout forzato: user_id={_t_uid} (disattivazione_ok={_ok_dis})")
                st.rerun()
    else:
        # Admin o sessione impersonazione: nessuna restrizione trial.
        # Sovrascriviamo SEMPRE (non solo se assente) per evitare che un trial_info
        # residuo da una sessione precedente appaia su un nuovo giro di impersonazione.
        st.session_state.trial_info = {
            'is_trial': False, 'days_left': 0,
            'trial_month': None, 'trial_year': None, 'expired': False,
        }

    # ============================================
    # BANNER IMPERSONAZIONE (solo per admin che impersonano)
    # ============================================
    if st.session_state.get('impersonating', False):
        # Banner visibile quando l'admin sta impersonando un cliente
        st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f59e0b 0%, #dc2626 100%);
                padding: clamp(0.75rem, 2vw, 1rem);
                border-radius: 10px;
                margin-bottom: 1.25rem;
                text-align: center;
                border: 3px solid #dc2626;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
        <h3 style="color: white; margin: 0; font-size: clamp(1rem, 2.5vw, 1.25rem);">
            ⚠️ MODALITÀ IMPERSONAZIONE
        </h3>
        <p style="color: #fef3c7; margin: 0.625rem 0 0 0; font-size: clamp(0.875rem, 2vw, 1rem); word-wrap: break-word;">
            Stai visualizzando l'account di: <strong>{_html.escape(user.get('nome_ristorante', 'Cliente'))}</strong> ({_html.escape(user.get('email', ''))})
        </p>
    </div>
    """, unsafe_allow_html=True)

        # Bottone "Torna Admin" in colonna separata
        col_back_admin, col_spacer = st.columns([2, 8])
        with col_back_admin:
            if st.button("🔙 Torna Admin", type="primary", use_container_width=True, key="back_to_admin_btn"):
                # Ripristina dati admin originali
                if 'admin_original_user' in st.session_state:
                    _imp_client_email_end = st.session_state.get('user_data', {}).get('email', '?')
                    st.session_state.user_data = st.session_state.admin_original_user.copy()
                    del st.session_state.admin_original_user
                    st.session_state.impersonating = False

                    # Ripristina flag admin
                    st.session_state.user_is_admin = True

                    # 🏢 RIPRISTINA RISTORANTI ADMIN (tutti i ristoranti del sistema)
                    try:
                        ristoranti_admin = supabase.table('ristoranti')\
                            .select('id, nome_ristorante, partita_iva, ragione_sociale, user_id')\
                            .eq('attivo', True)\
                            .order('nome_ristorante')\
                            .execute()
                        st.session_state.ristoranti = ristoranti_admin.data if ristoranti_admin.data else []
                        # Rimuovi ristorante_id specifico (admin vede tutti i ristoranti)
                        if st.session_state.get('ristorante_id'):
                            del st.session_state.ristorante_id
                        if 'partita_iva' in st.session_state:
                            del st.session_state.partita_iva
                        if 'nome_ristorante' in st.session_state:
                            del st.session_state.nome_ristorante
                        logger.info(f"🔙 ADMIN: Ripristinati {len(st.session_state.ristoranti)} ristoranti del sistema")
                    except Exception as e:
                        logger.error(f"Errore ripristino ristoranti admin: {e}")

                    # Log uscita impersonazione con durata
                    _imp_duration_min = '?'
                    _imp_started_end = st.session_state.get('impersonation_started_at')
                    if _imp_started_end:
                        try:
                            _imp_s_dt = datetime.fromisoformat(str(_imp_started_end).replace('Z', '+00:00'))
                            if _imp_s_dt.tzinfo is None:
                                _imp_s_dt = _imp_s_dt.replace(tzinfo=timezone.utc)
                            _imp_duration_min = int((datetime.now(timezone.utc) - _imp_s_dt).total_seconds() / 60)
                        except (ValueError, TypeError):
                            pass
                    st.session_state.pop('impersonation_started_at', None)
                    logger.info(f"🔒 IMPERSONATION END: admin={st.session_state.user_data.get('email')} → client={_imp_client_email_end} duration={_imp_duration_min}min")

                    # Rimuovi cookie impersonazione (non deve più sopravvivere al refresh)
                    if cookie_manager is not None:
                        try:
                            cookie_manager.set("impersonation_user_id", "",
                                               expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                        except Exception:
                            pass

                    # Redirect al pannello admin
                    st.switch_page("pages/admin.py")
                    st.stop()
                else:
                    st.error("⚠️ Errore: dati admin originali non trovati")
                    st.session_state.impersonating = False
                    if cookie_manager is not None:
                        try:
                            cookie_manager.set("impersonation_user_id", "",
                                               expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                        except Exception:
                            pass
                    st.rerun()

        st.markdown("---")

    # ============================================
    # SIDEBAR CON NAVIGAZIONE E INFO
    # ============================================
    render_sidebar(user)

    # ============================================
    # HEADER
    # ============================================
    render_oh_yeah_header()

    st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🧠 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi Fatture AI</span>
</h2>
<div style='padding: 4px 14px 0; font-size: 0.88rem; color: #1e2a4a; font-weight: 500; margin-bottom: 1.5rem;'>
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</div>
""", unsafe_allow_html=True)

    # ============================================
    # TRIAL BANNER
    # ============================================
    _tb = st.session_state.get('trial_info', {})
    if _tb.get('is_trial') and not st.session_state.get('impersonating', False):
        _tb_days = _tb.get('days_left', 0)
        _tb_color = '#dc2626' if _tb_days <= 2 else '#d97706'
        st.markdown(f"""
<div style="background:linear-gradient(135deg,#fef9c3,#fef08a);border:2px solid {_tb_color};
            border-radius:10px;padding:12px 18px;margin-bottom:1rem;
            display:flex;align-items:center;gap:12px;">
    <span style="font-size:1.6rem;">⏳</span>
    <div>
        <strong style="color:{_tb_color};font-size:1rem;">
            Prova gratuita attiva &mdash; Rimangono {_tb_days} giorni
        </strong><br>
        <span style="color:#92400e;font-size:0.85rem;">
            Accesso limitato alle fatture del mese in corso.
            Upload: max 50 file, solo XML/P7M. Export Excel non disponibile durante la prova.
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

    # ============================================
    # DROPDOWN MULTI-RISTORANTE
    # ============================================
    # Mostra dropdown per clienti NON admin con più ristoranti
    if user.get('email') not in ADMIN_EMAILS:
        ristoranti = st.session_state.get('ristoranti', [])

        if len(ristoranti) > 1:
            st.markdown('<h3 style="color:#1e3a5f;font-weight:700;">🏢 Seleziona Ristorante da Gestire</h3>', unsafe_allow_html=True)

            # Trova indice ristorante corrente
            current_id = st.session_state.get('ristorante_id')
            current_idx = 0
            for idx, r in enumerate(ristoranti):
                if r['id'] == current_id:
                    current_idx = idx
                    break

            # Dropdown ristorante
            ristorante_idx = st.selectbox(
                "🏪 Scegli ristorante:",
                range(len(ristoranti)),
                index=current_idx,
                format_func=lambda i: f"{ristoranti[i]['nome_ristorante']}",
                key="dropdown_ristorante_main",
                help="Seleziona il ristorante per cui vuoi caricare e analizzare fatture"
            )

            # Info ristorante sotto il dropdown, su tutta la larghezza
            rag_soc = _html.escape(ristoranti[ristorante_idx].get('ragione_sociale') or 'N/A')
            nome_r = _html.escape(ristoranti[ristorante_idx]['nome_ristorante'])
            piva_r = _html.escape(ristoranti[ristorante_idx]['partita_iva'])
            st.markdown(f"""
            <div style='padding: 8px 14px; font-size: 0.88rem; color: #1e3a5f; font-weight: 500;'>
                ✅ <strong>Attivo</strong> &nbsp;·&nbsp; 📋 {nome_r} &nbsp;·&nbsp; 🏢 IT{piva_r} &nbsp;·&nbsp; 📄 {rag_soc}
            </div>
            """, unsafe_allow_html=True)

            # Aggiorna sessione se cambiato
            selected_ristorante = ristoranti[ristorante_idx]
            if st.session_state.get('ristorante_id') != selected_ristorante['id']:
                st.session_state.ristorante_id = selected_ristorante['id']
                st.session_state.partita_iva = selected_ristorante['partita_iva']
                st.session_state.nome_ristorante = selected_ristorante['nome_ristorante']

                # 🧹 Pulizia cache contesto ristorante precedente
                if 'files_processati_sessione' in st.session_state:
                    st.session_state.files_processati_sessione = set()
                if 'files_con_errori' in st.session_state:
                    st.session_state.files_con_errori = set()
                # 🧹 Pulizia chiavi stale da ristorante precedente
                for _stale_key in ['righe_ai_appena_categorizzate', 'righe_keyword_appena_categorizzate',
                                   'righe_memoria_appena_categorizzate', 'righe_modificate_manualmente',
                                   'force_reload', 'force_empty_until_upload',
                                   'files_errori_report', 'last_upload_summary', 'ultimo_upload_ids',
                                   'ingredienti_temp', 'ricetta_edit_mode', 'ricetta_edit_data',
                                   '_fonte_pm_cache']:
                    st.session_state.pop(_stale_key, None)
                clear_fatture_cache()

                # 💾 Salva l'ultimo ristorante usato nel DB per ripristinarlo alla prossima sessione
                try:
                    supabase.table('users').update(
                        {'ultimo_ristorante_id': selected_ristorante['id']}
                    ).eq('id', user.get('id')).execute()
                except Exception as _e:
                    logger.warning(f"Errore salvataggio ultimo_ristorante_id: {_e}")

                logger.info(f"🔄 Ristorante cambiato: rist_id={selected_ristorante['id']}")
                st.rerun()

            st.markdown("---")

        elif len(ristoranti) == 1:
            # Singolo ristorante: mostra solo info compatta
            st.success(f"🏪 **Ristorante:** {ristoranti[0]['nome_ristorante']} | 📋 **P.IVA:** `IT{ristoranti[0]['partita_iva']}`")
            st.markdown("---")

    return st.session_state.user_data


# ============================================================
# 3. RENDER DASHBOARD UI  (estratto da app.py righe ~1304–1810)
# ============================================================

def render_dashboard_ui(supabase, logger, user):
    """
    Carica i dati e renderizza tutti i componenti UI della dashboard principale:
      - Carica df_cache via carica_e_prepara_dataframe (con force_refresh)
      - Gestione Fatture (expander elimina singola/tutto)
      - Controllo visibilità uploader (hide_uploader flag)
      - Check limite righe globale (blocca se DB pieno)
      - Selettore ristorante per admin
      - Pre-compute conteggio righe da classificare
      - File uploader + bottone "Riprova AI"
      - Bottone reset upload (solo admin/impersonating)
      - Inizializzazione session state tracking upload

    Returns:
        tuple: (df_cache, stats_db, uploaded_files)
            - df_cache       : DataFrame Pandas con le fatture caricate
            - stats_db       : dict con num_uniche / num_righe / success
            - uploaded_files : lista file caricati da st.file_uploader (può essere [])
    """
    from utils.ui_helpers import load_css

    # API key OpenAI
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        logger.exception("API Key OpenAI non trovata o accesso a st.secrets fallito")
        st.error("⛔ Configurazione AI non disponibile. Contatta l'amministratore.")
        st.stop()

    if 'timestamp_ultimo_caricamento' not in st.session_state:
        st.session_state.timestamp_ultimo_caricamento = time.time()

    # ============================================================
    # 🔒 IMPORTANTE: user_id per cache isolata (multi-tenancy)
    # ============================================================
    try:
        user_id = st.session_state.user_data["id"]
    except (KeyError, TypeError, AttributeError):
        logger.critical("❌ user_data corrotto o mancante campo 'id' - FORZA LOGOUT")
        st.session_state.logged_in = False
        st.session_state.force_logout = True
        st.session_state._cookie_checked = True
        st.error("⚠️ Sessione invalida. Effettua nuovamente il login.")
        st.rerun()

    # ⚡ SINGLE DATA LOAD: Carica una sola volta, riusa per Gestione Fatture + Dashboard
    force_refresh = st.session_state.get('force_reload', False)
    if force_refresh:
        st.session_state.force_reload = False
        logger.info("🔄 FORCE RELOAD attivato dopo categorizzazione AI")

    with st.spinner("⏳ Caricamento dati..."):
        df_cache = carica_e_prepara_dataframe(user_id, force_refresh=force_refresh, ristorante_id=st.session_state.get('ristorante_id'))

    # Inizializzazione safe: stats_db potrebbe non essere raggiunto se df_cache è vuoto.
    stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}

    # ============================================================
    # 🗂️ GESTIONE FATTURE - Eliminazione (prima del file uploader)
    # ============================================================
    if not df_cache.empty:
        st.markdown("""
    <style>
    /* Expander Gestione Fatture - sfondo arancione chiaro */
    div.st-key-expander_gestione_fatture [data-testid="stExpander"] details summary {
        background: linear-gradient(135deg, rgba(255, 237, 213, 0.95) 0%, rgba(254, 215, 170, 0.95) 100%) !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        color: #9a3412 !important;
        font-weight: 600 !important;
        border: 1px solid #fdba74 !important;
    }
    div.st-key-expander_gestione_fatture [data-testid="stExpander"] details {
        background: rgba(255, 247, 237, 0.9) !important;
        border: 1px solid #fdba74 !important;
        border-radius: 8px !important;
    }
    div.st-key-expander_gestione_fatture [data-testid="stExpander"] details[open] summary {
        border-bottom: 1px solid #fdba74 !important;
        border-radius: 8px 8px 0 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
        with st.container(key="expander_gestione_fatture"):
            with st.expander("🗂️ Apri per gestire le Fatture Caricate (Elimina)", expanded=False):

                # ========================================
                # BOX STATISTICHE
                # ========================================
                try:
                    stats_db = get_fatture_stats(user_id, st.session_state.get('ristorante_id'))
                except Exception as e:
                    logger.error(f"Errore get_fatture_stats: {e}")
                    st.error("❌ Errore caricamento statistiche")
                    stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}

                # Conta note di credito (TD04) dai file unici in df_cache
                num_note_credito = 0
                if 'TipoDocumento' in df_cache.columns and 'FileOrigine' in df_cache.columns:
                    num_note_credito = df_cache[df_cache['TipoDocumento'].str.upper().str.strip() == 'TD04']['FileOrigine'].nunique()
                note_credito_html = f' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #FF5500;">{num_note_credito:,}</strong>' if num_note_credito > 0 else ' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #FF5500;">0</strong>'
                st.markdown(f"""
<div style="
    background: linear-gradient(135deg, rgba(255, 140, 0, 0.15) 0%, rgba(255, 165, 0, 0.20) 100%);
    padding: 14px 22px;
    border-radius: 10px;
    border-left: 5px solid rgba(255, 107, 0, 0.6);
    box-shadow: 0 3px 6px rgba(255, 140, 0, 0.15);
    margin: 0 0 20px 0;
    display: inline-block;
    min-width: 400px;
    backdrop-filter: blur(10px);
">
    <span style="color: #FF6B00; font-size: 1.05em; font-weight: 700;">
        📊 Fatture: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_uniche"]:,}</strong>{note_credito_html} |
        📋 Righe Totali: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_righe"]:,}</strong>
    </span>
</div>
""", unsafe_allow_html=True)

                st.markdown("---")

                # Raggruppa per file origine per creare summary
                _agg_dict = {
                    'Fornitore': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],
                    'TotaleRiga': 'sum',
                    'NumeroRiga': 'count',
                    'DataDocumento': 'first'
                }
                if 'CreatedAt' in df_cache.columns:
                    _agg_dict['CreatedAt'] = 'max'
                fatture_summary = df_cache.groupby('FileOrigine').agg(_agg_dict).reset_index()
                fatture_summary = fatture_summary.reset_index(drop=True)
                if 'CreatedAt' in fatture_summary.columns:
                    fatture_summary.columns = ['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data', 'CreatedAt']
                    fatture_summary = fatture_summary.sort_values('CreatedAt', ascending=False)
                else:
                    fatture_summary.columns = ['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data']
                    fatture_summary = fatture_summary.sort_values('Data', ascending=False)

                # 🗑️ PULSANTE SVUOTA TUTTO (solo admin/impersonificati)
                if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
                    st.markdown("### 🗑️ Eliminazione Massiva")

                    if st.button(
                        "🗑️ ELIMINA TUTTO",
                        type="primary",
                        use_container_width=True,
                        key="btn_svuota_definitivo"
                    ):
                        with st.spinner("🗑️ Eliminazione in corso..."):
                            progress = st.progress(0)
                            progress.progress(20, text="Eliminazione da Supabase...")

                            result = elimina_tutte_fatture(user_id, ristoranteid=st.session_state.get('ristorante_id'))

                            # 🔥 INVALIDAZIONE CACHE
                            invalida_cache_memoria()

                            # 🔥 RESET SESSION
                            st.session_state.files_processati_sessione = set()
                            st.session_state.files_con_errori = set()

                            progress.progress(40, text="Pulizia file JSON locali...")

                            # HARD RESET: Elimina file JSON obsoleti
                            json_files = ['fattureprocessate.json', 'fatture.json', 'data.json']
                            for json_file in json_files:
                                if os.path.exists(json_file):
                                    try:
                                        os.remove(json_file)
                                        logger.info(f"🗑️ Rimosso file JSON obsoleto: {json_file}")
                                    except Exception as e:
                                        logger.warning(f"⚠️ Impossibile rimuovere {json_file}: {e}")

                            progress.progress(60, text="Pulizia cache Streamlit...")

                            # HARD RESET: Pulisci TUTTE le cache
                            st.cache_data.clear()
                            try:
                                st.cache_resource.clear()
                            except Exception as e:
                                logger.warning(f"⚠️ Errore clear cache_resource: {e}")

                            progress.progress(80, text="Ripristino sessione...")

                            # 🔧 FIX: Preserva chiavi impersonazione e contesto ristorante
                            keys_to_preserve = {
                                'user_data', 'logged_in',
                                'impersonating', 'admin_original_user', 'user_is_admin',
                                'ristorante_id', 'ristoranti', 'partita_iva', 'nome_ristorante',
                            }
                            keys_to_remove = [k for k in st.session_state.keys()
                                              if k not in keys_to_preserve]
                            for key in keys_to_remove:
                                st.session_state.pop(key, None)

                            progress.progress(100, text="Completato!")
                            time.sleep(0.1)

                            if result["success"]:
                                st.success(f"✅ **{result['fatture_eliminate']} fatture** eliminate! ({result['righe_eliminate']} prodotti)")
                                st.info("🧹 **Ripristino completo**: Cache, JSON locali e stato sessione puliti")

                                # LOG AUDIT: Verifica immediata post-delete
                                try:
                                    verify_query = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id)
                                    verify_query = add_ristorante_filter(verify_query)
                                    verify = verify_query.execute()
                                    num_residue = verify.count or 0
                                    if num_residue == 0:
                                        logger.info(f"✅ DELETE VERIFIED: 0 righe rimaste per user_id={user_id}")
                                        st.success("✅ Verifica: Database pulito (0 righe)")
                                    else:
                                        logger.error(f"⚠️ DELETE INCOMPLETE: {num_residue} righe ancora presenti per user_id={user_id}")
                                        st.error(f"⚠️ Attenzione: {num_residue} righe ancora presenti (possibile problema RLS)")
                                except Exception as e:
                                    logger.exception("Errore verifica post-delete")

                                if 'check_conferma_svuota' in st.session_state:
                                    del st.session_state.check_conferma_svuota

                                # 🔥 FLAG HIDE UPLOADER dopo eliminazione totale
                                st.session_state.hide_uploader = True
                                st.session_state.files_processati_sessione = set()
                                st.cache_data.clear()
                                invalida_cache_memoria()
                                st.success("✅ Eliminato tutto!")
                                st.rerun()
                            else:
                                st.error(f"❌ Errore: {result['error']}")

                    st.markdown("---")

                # ========== ELIMINA SINGOLA FATTURA ==========
                st.markdown("### 🗑️ Elimina Fattura Singola")

                if len(fatture_summary) > 0:
                    # 🔍 FILTRO FORNITORE
                    fornitori_disponibili = sorted(fatture_summary['Fornitore'].dropna().unique().tolist())
                    opzioni_fornitore = ["— Tutti i fornitori —"] + fornitori_disponibili
                    filtro_fornitore_sel = st.selectbox(
                        "🔍 Filtra per Fornitore:",
                        options=opzioni_fornitore,
                        key="filtro_fornitore_gestione"
                    )
                    if filtro_fornitore_sel == "— Tutti i fornitori —":
                        fatture_filtrate = fatture_summary
                    else:
                        fatture_filtrate = fatture_summary[fatture_summary['Fornitore'] == filtro_fornitore_sel]

                    fatture_options = []
                    for idx, row in fatture_filtrate.iterrows():
                        fatture_options.append({
                            'File': row['File'],
                            'Fornitore': row['Fornitore'],
                            'NumProdotti': int(row['NumProdotti']),
                            'Totale': row['Totale'],
                            'Data': row['Data']
                        })

                    if not fatture_options:
                        st.info("🔭 Nessuna fattura trovata per il fornitore cercato.")
                    else:
                        fattura_selezionata = st.selectbox(
                            "Seleziona fattura da eliminare:",
                            options=fatture_options,
                            format_func=lambda x: format_fattura_label(
                                file_name=x['File'],
                                fornitore=x['Fornitore'],
                                totale=x['Totale'],
                                num_righe=x['NumProdotti'],
                                data=x['Data'],
                            ),
                            help="Il nome file viene mostrato completo e si adatta allo spazio disponibile",
                            key="select_fattura_elimina"
                        )

                        col_btn, col_spacer = st.columns([1, 3])
                        with col_btn:
                            if st.button("🗑️ Elimina Fattura", type="secondary", use_container_width=True):
                                with st.spinner("🗑️ Eliminazione in corso..."):
                                    result = elimina_fattura_completa(fattura_selezionata['File'], user_id, ristoranteid=st.session_state.get('ristorante_id'))

                                    # 🔥 INVALIDAZIONE CACHE
                                    invalida_cache_memoria()
                                    clear_fatture_cache()

                                    # 🔥 RESET SESSION
                                    if 'files_processati_sessione' in st.session_state:
                                        file_eliminato = fattura_selezionata['File']
                                        st.session_state.files_processati_sessione.discard(file_eliminato)
                                        st.session_state.files_processati_sessione.discard(os.path.splitext(file_eliminato)[0].lower())

                                    if result["success"]:
                                        st.success(f"✅ Fattura **{fattura_selezionata['File']}** eliminata! ({result['righe_eliminate']} prodotti)")
                                        time.sleep(0.3)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Errore: {result['error']}")
                else:
                    st.info("🔭 Nessuna fattura da eliminare.")

                st.caption("⚠️ L'eliminazione è immediata e irreversibile")

        st.markdown("""
    <div style='padding: 8px 14px; font-size: 0.88rem; color: #9a3412; font-weight: 500;'>
        ⚠️ <strong>IMPORTANTE:</strong> Le fatture caricate devono corrispondere alla P.IVA del ristorante mostrato sopra! <strong>Altrimenti verranno scartate</strong>
    </div>
    """, unsafe_allow_html=True)

    # === GESTIONE VISIBILITÀ UPLOADER ===
    if st.session_state.get("hide_uploader", False):
        st.warning("⚠️ Hai eliminato tutte le fatture.")
        if st.button("🔄 Ricarica Pagina", key="refresh_page_btn"):
            st.session_state.hide_uploader = False
            st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
            st.components.v1.html(
                """
                <script>
                window.parent.location.reload();
                </script>
                """,
                height=0
            )
        return df_cache, stats_db, []  # Nessun file da elaborare in questo stato

    # ============================================================
    # CHECK LIMITE RIGHE GLOBALE (STEP 1 - Performance)
    # ============================================================
    righe_totali = stats_db.get('num_righe', 0)

    if righe_totali >= MAX_RIGHE_GLOBALE:
        st.error(f"⚠️ Limite database raggiunto ({righe_totali:,} righe). Elimina vecchie fatture.")
        st.warning("Usa 'Gestione Fatture Caricate' sopra per eliminare")
        st.stop()

    elif righe_totali >= MAX_RIGHE_GLOBALE * 0.8:
        percentuale = (righe_totali / MAX_RIGHE_GLOBALE * 100)
        st.warning(f"⚠️ Database quasi pieno: {righe_totali:,}/{MAX_RIGHE_GLOBALE:,} righe ({percentuale:.0f}%)")

    # ============================================================
    # SELETTORE RISTORANTE PER ADMIN
    # ============================================================
    if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
        st.markdown("### 👨‍💼 Modalità Admin - Seleziona Ristorante")

        if st.session_state.get('ristoranti') and len(st.session_state.ristoranti) > 0:
            ristoranti_admin = st.session_state.ristoranti

            current_rist_id = st.session_state.get('ristorante_id')
            try:
                current_idx = next(i for i, r in enumerate(ristoranti_admin) if r['id'] == current_rist_id)
            except StopIteration:
                current_idx = 0

            selected_idx = st.selectbox(
                "Seleziona ristorante per caricare fatture:",
                range(len(ristoranti_admin)),
                format_func=lambda i: f"🏪 {ristoranti_admin[i]['nome_ristorante']} - P.IVA: IT{ristoranti_admin[i]['partita_iva']}",
                index=current_idx,
                key="admin_ristorante_selector"
            )

            selected_ristorante = ristoranti_admin[selected_idx]
            if selected_ristorante['id'] != st.session_state.get('ristorante_id'):
                st.session_state.ristorante_id = selected_ristorante['id']
                st.session_state.partita_iva = selected_ristorante['partita_iva']
                st.session_state.nome_ristorante = selected_ristorante['nome_ristorante']
                logger.info(f"👨‍💼 Admin: ristorante cambiato a rist_id={selected_ristorante['id']}")
                st.rerun()

            st.info(f"📌 Le fatture saranno caricate per: **{st.session_state.nome_ristorante}** (P.IVA: IT{st.session_state.partita_iva})")
            st.markdown("---")
        else:
            st.error("⚠️ Nessun ristorante disponibile nel sistema. Crea almeno un cliente prima di caricare fatture.")
            st.stop()

    # ============================================================
    # PRE-COMPUTE: Conta righe da categorizzare per UI
    # ⚡ ALLINEATO con mostra_statistiche: escludi NOTE E DICITURE + needs_review
    # ============================================================
    _righe_da_class_ui = 0
    try:
        if not df_cache.empty and 'Categoria' in df_cache.columns:
            _mask_note = df_cache['Categoria'].fillna('') == '📝 NOTE E DICITURE'
            if 'needs_review' in df_cache.columns:
                _mask_review = df_cache['needs_review'].fillna(False) == True
                _df_for_count = df_cache[~(_mask_note | _mask_review)]
            else:
                _df_for_count = df_cache[~_mask_note]

            _mask_da_class = (
                _df_for_count['Categoria'].isna()
                | (_df_for_count['Categoria'] == 'Da Classificare')
                | (_df_for_count['Categoria'].astype(str).str.strip() == '')
            )
            _righe_da_class_ui = _mask_da_class.sum()
    except Exception:
        pass

    # ============================================================
    # LAYOUT: FILE UPLOADER + AI INFO/BUTTON AFFIANCATI
    # ============================================================
    st.markdown("""
    <style>
    /* Compatta altezza drop zone */
    [data-testid="stFileUploaderDropzone"] {
        padding: 8px 15px !important;
        min-height: 0 !important;
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
    }
    /* Nascondi testo originale inglese "Drag and drop" + limit */
    [data-testid="stFileUploaderDropzoneInstructions"] {
        visibility: hidden !important;
        position: absolute !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    /* Traduci bottone Browse files → Sfoglia */
    [data-testid="stFileUploaderDropzone"] button {
        font-size: 0 !important;
        padding: 6px 16px !important;
        min-height: 0 !important;
        flex-shrink: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] button::after {
        content: "Sfoglia" !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stFileUploaderDropzone"]::after {
        content: "📂 Trascina file qui o clicca Sfoglia  ·  XML, P7M, PDF, JPG, JPEG, PNG · Max 200MB" !important;
        font-size: 0.78rem !important;
        color: #666 !important;
        white-space: nowrap !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col_upload, col_ai_right = st.columns([3, 2])

    with col_upload:
        uploaded_files = st.file_uploader(
            "Carica file",
            accept_multiple_files=True,
            type=['xml', 'p7m', 'pdf', 'jpg', 'jpeg', 'png'],
            label_visibility="collapsed",
            key=f"file_uploader_{st.session_state.get('uploader_key', 0)}"
        )

    with col_ai_right:
        st.markdown("<div style='margin-top: 34px;'></div>", unsafe_allow_html=True)
        if _righe_da_class_ui > 0:
            # 🧠 Recovery: bottone visibile SOLO se rimangono righe Da Classificare dopo l'AI
            if st.button(
                "🧠 Riprova AI per Categorizzare",
                use_container_width=True,
                type="primary",
                key="btn_ai_categorizza_upload"
            ):
                st.session_state.trigger_ai_categorize = True
                st.rerun()

    # 🧠 RESET ICONE AI al nuovo caricamento (solo session_state, niente DB)
    if uploaded_files and len(uploaded_files) > 0:
        current_upload_ids = [f.name for f in uploaded_files]
        ultimo_upload = st.session_state.get('ultimo_upload_ids', [])

        if current_upload_ids != ultimo_upload:
            if 'righe_ai_appena_categorizzate' in st.session_state:
                st.session_state.righe_ai_appena_categorizzate = []
            logger.info("🧹 Reset icone AI - nuovo caricamento rilevato")
            st.session_state.ultimo_upload_ids = current_upload_ids
            if 'last_upload_summary' in st.session_state:
                del st.session_state.last_upload_summary

    # ============================================================
    # INIZIALIZZAZIONE SET ERRORI (prevenzione loop)
    # ============================================================
    if 'files_con_errori' not in st.session_state:
        st.session_state.files_con_errori = set()

    # Bottone Reset Upload (solo admin)
    if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
        if st.button("🔄 Ripristina upload (pulisci cache sessione)", key="reset_upload_cache"):
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
            st.session_state.files_errori_report = {}
            if 'force_empty_until_upload' in st.session_state:
                del st.session_state.force_empty_until_upload
            st.success("✅ Cache pulita! Puoi ricaricare i file.")
            st.rerun()

    return df_cache, stats_db, uploaded_files


# ============================================================
# 4. HANDLE UPLOAD AND AI  (estratto da app.py righe ~1810–1890)
# ============================================================

def handle_upload_and_ai(supabase, logger, user_id, uploaded_files, df_cache):
    """
    Gestisce la logica di upload e visualizzazione dashboard:
      - Inizializzazione session state tracking file (processati, errori, report)
      - Auto-pulizia errori quando l'utente rimuove i file
      - Mostra messaggi persistenti dall'ultimo upload (30 secondi)
      - Mostra errore limite upload (da _upload_limit_error)
      - Processa i file caricati via handle_uploaded_files
      - Renderizza la dashboard statistiche (mostra_statistiche)
      - Reset contatore anti-loop a fine ciclo

    Args:
        supabase     : client Supabase
        logger       : logger applicazione
        user_id      : str/UUID — id utente corrente
        uploaded_files: lista file da st.file_uploader
        df_cache     : DataFrame già caricato da render_dashboard_ui
    """
    # Lazy import per evitare l'import circolare con dashboard_renderer
    from components.dashboard_renderer import mostra_statistiche  # noqa: PLC0415
    from services.upload_handler import handle_uploaded_files      # noqa: PLC0415

    # ============================================================
    # SESSION STATE: Tracking file elaborati/errori
    # ============================================================
    if 'files_processati_sessione' not in st.session_state:
        st.session_state.files_processati_sessione = set()

    if 'files_con_errori' not in st.session_state:
        st.session_state.files_con_errori = set()

    if 'files_errori_report' not in st.session_state:
        st.session_state.files_errori_report = {}  # Dizionario persistente per mostrare report anche dopo rerun

    # ============================================================
    # AUTO-PULIZIA: Se non ci sono file caricati ma ci sono errori nel report,
    # significa che l'utente ha rimosso i file → pulisci automaticamente
    # ============================================================
    if not uploaded_files and len(st.session_state.files_errori_report) > 0:
        logger.info("🧹 Auto-pulizia errori dopo rimozione file")
        st.session_state.files_con_errori = set()
        st.session_state.files_errori_report = {}
        # Non serve rerun: la pagina è già pulita senza file caricati

    # ============================================================
    # MOSTRA MESSAGGI PERSISTENTI DALL'ULTIMO UPLOAD
    # (rimangono visibili per 30 secondi, poi spariscono)
    # ============================================================
    if 'upload_messages' in st.session_state and st.session_state.upload_messages:
        _msg_age = time.time() - st.session_state.get('upload_messages_time', 0)
        if _msg_age < 30:
            for _msg in st.session_state.upload_messages:
                st.markdown(_msg, unsafe_allow_html=True)
        else:
            st.session_state.upload_messages = []

    # 🔥 MOSTRA ERRORE LIMITE UPLOAD (dopo reset widget)
    if '_upload_limit_error' in st.session_state:
        st.error(st.session_state.pop('_upload_limit_error'))

    # 🔥 GESTIONE FILE CARICATI
    if uploaded_files:
        handle_uploaded_files(uploaded_files, supabase, user_id)

    # 🔥 CARICA E MOSTRA STATISTICHE SEMPRE (da Supabase)
    # ⚡ RIUSA df_cache caricato sopra (evita doppia query DB)

    # Crea placeholder per loading
    loading_placeholder = st.empty()

    try:
        # Mostra animazione AI durante caricamento
        mostra_loading_ai(loading_placeholder, "Caricamento Dashboard AI")

        # Riusa dati già caricati (df_cache) - evita seconda chiamata a carica_e_prepara_dataframe
        df_completo = df_cache

        loading_placeholder.empty()

        # Mostra dashboard direttamente senza messaggi
        if not df_completo.empty:
            mostra_statistiche(df_completo, supabase, uploaded_files)
        else:
            st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")

    except Exception as e:
        loading_placeholder.empty()
        logger.error(f"Errore durante il caricamento: {e}")
        st.error("❌ Errore durante il caricamento del file. Riprova.")
        logger.exception("Errore caricamento dashboard")

    # ✅ Reset contatore anti-loop DOPO che il render è completato senza rerun
    # (se siamo arrivati qui, il ciclo corrente è terminato normalmente)
    if st.session_state.get('logged_in', False):
        st.session_state._rerun_guard = 0
