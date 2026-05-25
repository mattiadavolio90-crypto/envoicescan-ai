"""
controllers/auth_controller.py

Gestione autenticazione, sessione cookie, impersonazione admin e trial.
Estratto da app.py — nessuna modifica alla logica, solo separazione di responsabilità.

Funzioni esposte (chiamate in sequenza da app.py):
    init_cookie_manager()
    handle_impersonation_cookie_set(cookie_manager, supabase)
    check_impersonation_timeout(cookie_manager)
    handle_force_logout(supabase)
    restore_session_from_cookie(cookie_manager, supabase, inactivity_hours, clear_fatture_cache_fn)
    update_last_seen_throttled(supabase, throttle_seconds)
    handle_reset_token_page(supabase)
    show_login_page(cookie_manager, supabase)
    check_login_gate(supabase, cookie_manager)
    restore_admin_flags()
    restore_impersonation_from_cookie(cookie_manager, supabase)
    check_trial_or_expire(supabase)
    render_impersonation_banner(supabase, cookie_manager)
"""

import logging
import secrets as _secrets
import time
from datetime import datetime, timedelta, timezone

import streamlit as st

logger = logging.getLogger("fci_app")


# ============================================================
# COOKIE MANAGER
# ============================================================

def init_cookie_manager():
    """Inizializza e restituisce il CookieManager. Restituisce None se non disponibile."""
    try:
        import extra_streamlit_components as stx
        return stx.CookieManager(key="cookie_manager_app")
    except Exception as e:
        logger.warning(f"CookieManager non disponibile: {e}")
        return None


# ============================================================
# IMPERSONAZIONE: SET COOKIE DA ADMIN.PY
# ============================================================

def handle_impersonation_cookie_set(cookie_manager, supabase) -> None:
    """
    admin.py imposta _set_impersonation_cookie prima di switch_page.
    Qui scriviamo il cookie browser, così sopravvive al F5.
    """
    if not st.session_state.get("_set_impersonation_cookie") or cookie_manager is None:
        return
    try:
        cookie_manager.set(
            "impersonation_user_id",
            str(st.session_state.get("_set_impersonation_cookie", "")),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            secure=True,
            same_site="strict",
        )
    except Exception as e:
        logger.warning(f"Errore impostazione cookie impersonazione: {e}")
    st.session_state.pop("_set_impersonation_cookie", None)


# ============================================================
# IMPERSONAZIONE: TIMEOUT 30 MIN
# ============================================================

def check_impersonation_timeout(cookie_manager) -> None:
    """Verifica timeout 30 min impersonazione. Ripristina admin e rerun se scaduta."""
    if not st.session_state.get("impersonating", False):
        return
    _imp_started_raw = st.session_state.get("impersonation_started_at")
    if not _imp_started_raw:
        return
    try:
        _imp_started_dt = datetime.fromisoformat(
            str(_imp_started_raw).replace("Z", "+00:00")
        )
        if _imp_started_dt.tzinfo is None:
            _imp_started_dt = _imp_started_dt.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - _imp_started_dt) <= timedelta(minutes=30):
            return
        # Timeout scaduto
        _imp_client_email = st.session_state.get("user_data", {}).get("email", "?")
        _imp_admin_email = st.session_state.get("admin_original_user", {}).get("email", "?")
        logger.warning(
            f"🔒 IMPERSONATION TIMEOUT: admin={_imp_admin_email} → client={_imp_client_email}"
        )
        if "admin_original_user" in st.session_state:
            st.session_state.user_data = st.session_state.admin_original_user.copy()
            del st.session_state.admin_original_user
        st.session_state.impersonating = False
        st.session_state.user_is_admin = True
        st.session_state.pop("impersonation_started_at", None)
        if cookie_manager is not None:
            try:
                cookie_manager.set(
                    "impersonation_user_id",
                    "",
                    expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
                )
            except Exception:
                pass
        st.warning("⏰ Sessione impersonazione scaduta (30 min). Sei tornato admin.")
        st.rerun()
    except (ValueError, TypeError) as _parse_err:
        logger.error(
            f"🔒 impersonation_started_at non parsabile ({_parse_err!r}) — forzo fine impersonazione per sicurezza"
        )
        if "admin_original_user" in st.session_state:
            st.session_state.user_data = st.session_state.admin_original_user.copy()
            del st.session_state.admin_original_user
        st.session_state.impersonating = False
        st.session_state.user_is_admin = True
        st.session_state.pop("impersonation_started_at", None)
        st.warning("⚠️ Sessione impersonazione ripristinata per anomalia tecnica.")
        st.rerun()


# ============================================================
# LOGOUT FORZATO VIA QUERY PARAMS
# ============================================================

def handle_force_logout(supabase) -> None:
    """Gestisce il logout forzato via query param ?logout=1."""
    if st.query_params.get("logout") != "1":
        return
    logger.warning("🚨 LOGOUT FORZATO via query params - pulizia sessione")
    try:
        _email_for_logout = st.session_state.get("user_data", {}).get("email")
        if _email_for_logout:
            supabase.table("users").update(
                {
                    "session_token": None,
                    "session_token_created_at": None,
                    "last_seen_at": None,
                }
            ).eq("email", _email_for_logout).execute()
    except Exception as e:
        logger.warning(
            f"⚠️ Impossibile invalidare session_token in DB durante logout: {e}"
        )
    st.session_state.clear()
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.query_params.clear()
    st.rerun()


# ============================================================
# RIPRISTINO SESSIONE DA COOKIE
# ============================================================

def restore_session_from_cookie(
    cookie_manager, supabase, inactivity_hours: int, clear_fatture_cache_fn
) -> None:
    """
    Tenta di ripristinare la sessione dal cookie session_token.

    Supporta due formati (backward-compatible):
      - refresh_token JWT Supabase Auth → rinnova via refresh_session(), aggiorna cookie
      - session_token opaco legacy → lookup su public.users (path pre-migrazione)
    """
    from config.constants import ADMIN_EMAILS
    from services.auth_service import verifica_sessione_da_cookie

    _force_logout_active = st.session_state.get("force_logout", False)
    if st.session_state.get("logged_in") or _force_logout_active or cookie_manager is None:
        return
    try:
        _token_cookie = cookie_manager.get("session_token")
        if _token_cookie:
            _u = verifica_sessione_da_cookie(
                _token_cookie, inactivity_hours=inactivity_hours
            )
            if _u:
                # Se verifica_sessione_da_cookie ha restituito un nuovo refresh_token (JWT ruotato),
                # aggiorna il cookie per ridurre la finestra di esposizione del token precedente.
                _new_refresh_token = _u.pop("_jwt_refresh_token", None)
                _u.pop("_jwt_access_token", None)  # access_token non va in session_state

                if _new_refresh_token and _new_refresh_token != _token_cookie and cookie_manager is not None:
                    try:
                        cookie_manager.set(
                            "session_token",
                            _new_refresh_token,
                            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                            secure=True,
                            same_site="strict",
                        )
                    except Exception as _cookie_err:
                        logger.warning(f"Errore aggiornamento cookie JWT ruotato: {_cookie_err}")

                st.session_state.logged_in = True
                st.session_state.user_data = _u
                st.session_state.partita_iva = _u.get("partita_iva")
                st.session_state.created_at = _u.get("created_at")
                if (_u.get("email") or "").strip().lower() in ADMIN_EMAILS:
                    st.session_state.user_is_admin = True
                clear_fatture_cache_fn()
                st.session_state.force_reload = True
                logger.info(
                    f"✅ Sessione ripristinata da token per user_id={_u.get('id')} "
                    f"— fatture cache cleared"
                )
            else:
                try:
                    cookie_manager.set(
                        "session_token",
                        "",
                        expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
                    )
                except Exception:
                    pass
                logger.info("🔒 Session token non valido o scaduto - richiesto login")
                st.session_state._cookie_checked = True
        elif not st.session_state.get("_cookie_checked", False):
            # Primo render: CookieManager non ha ancora letto i cookie, aspetta un ciclo
            st.session_state._cookie_checked = True
            st.markdown(
                """
                <div style='display:flex;align-items:center;justify-content:center;
                            height:80vh;flex-direction:column;gap:12px;'>
                    <div style='font-size:2rem;'>⏳</div>
                    <div style='color:#94a3b8;font-size:0.95rem;'>Caricamento sessione...</div>
                </div>
            """,
                unsafe_allow_html=True,
            )
            st.stop()
    except Exception as e:
        logger.warning(f"Errore ripristino sessione da cookie: {e}")


# ============================================================
# LAST SEEN THROTTLE
# ============================================================

def update_last_seen_throttled(supabase, throttle_seconds: int) -> None:
    """Aggiorna last_seen_at con throttling (max 1 scrittura ogni N secondi)."""
    from services.auth_service import aggiorna_last_seen

    if not st.session_state.get("logged_in", False):
        return
    _active_user_id = st.session_state.get("user_data", {}).get("id")
    if not _active_user_id:
        return
    _now_utc = datetime.now(timezone.utc)
    _last_seen_write_raw = st.session_state.get("_last_seen_write_at")
    _should_write = False
    if not _last_seen_write_raw:
        _should_write = True
    else:
        try:
            _last_write_dt = datetime.fromisoformat(
                str(_last_seen_write_raw).replace("Z", "+00:00")
            )
            if _last_write_dt.tzinfo is None:
                _last_write_dt = _last_write_dt.replace(tzinfo=timezone.utc)
            _should_write = (
                _now_utc - _last_write_dt
            ).total_seconds() >= throttle_seconds
        except (ValueError, TypeError):
            _should_write = True
    if _should_write:
        if aggiorna_last_seen(_active_user_id, supabase):
            st.session_state._last_seen_write_at = _now_utc.isoformat()


# ============================================================
# PAGINA RESET TOKEN (link email attivazione / recupero password)
# ============================================================

def handle_reset_token_page(supabase) -> None:
    """
    Se presente ?reset_token=..., mostra la pagina di impostazione password
    e chiama st.stop() al termine (pagina autonoma, non mostra il resto dell'app).
    """
    reset_token = st.query_params.get("reset_token")
    if not reset_token:
        return

    from config.constants import UI_DELAY_LONG
    from services.auth_service import imposta_password_da_token, valida_password_compliance
    from utils.ui_helpers import hide_sidebar_css

    hide_sidebar_css()

    st.markdown(
        """
    <h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
        🔐 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;">Imposta la tua Password</span>
    </h2>
    """,
        unsafe_allow_html=True,
    )

    try:
        check_result = (
            supabase.table("users")
            .select("id, email, nome_ristorante, reset_expires, password_hash")
            .eq("reset_code", reset_token)
            .execute()
        )

        if not check_result.data:
            st.error("❌ Link non valido o già utilizzato")
            st.info(
                "💡 Se hai già impostato la password, vai al login. "
                "Altrimenti contatta il supporto per un nuovo link."
            )
            if st.button("🔑 Vai al Login"):
                st.query_params.clear()
                st.rerun()
            st.stop()

        user_data = check_result.data[0]

        # Check scadenza token
        expires_str = user_data.get("reset_expires")
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)
                if now_utc > expires:
                    st.error("⏰ Link scaduto (validità: 24 ore)")
                    st.info(
                        "💡 Contatta il supporto per ricevere un nuovo link di attivazione."
                    )
                    st.stop()
            except Exception as e:
                logger.warning(f"Errore parsing data scadenza token: {e}")

        is_nuovo_cliente = user_data.get("password_hash") is None

        if is_nuovo_cliente:
            st.success(f"✅ Benvenuto, **{user_data.get('nome_ristorante')}**!")
            st.info(f"📧 Il tuo account: **{user_data.get('email')}**")
            st.markdown("Imposta una password sicura per accedere all'app.")
        else:
            st.info(f"📧 Reset password per: **{user_data.get('email')}**")

        with st.form("form_imposta_password"):
            nuova_password = st.text_input(
                "🔑 Nuova Password",
                type="password",
                help="Minimo 10 caratteri, con maiuscola, minuscola e numero",
            )
            conferma_password = st.text_input(
                "🔑 Conferma Password", type="password"
            )
            st.markdown(
                """
            **Requisiti password:**
            - ✅ Almeno 10 caratteri
            - ✅ Almeno 3 tra: maiuscola, minuscola, numero, simbolo
            - ❌ Non usare email o nome ristorante
            - ❌ Non usare password comuni
            """
            )
            # GDPR Art.6 — consenso esplicito al trattamento dati (solo primo accesso)
            gdpr_accepted = True
            if is_nuovo_cliente:
                gdpr_accepted = st.checkbox(
                    "✅ Ho letto e accetto l'[Informativa Privacy](/?page=privacy) "
                    "(D.lgs. 196/2003 e GDPR UE 2016/679). "
                    "Acconsento al trattamento dei miei dati per l'erogazione del servizio.",
                    key="gdpr_consent_activation",
                )
            submitted = st.form_submit_button(
                "✅ Conferma Password", type="primary", use_container_width=True
            )
            if submitted:
                if is_nuovo_cliente and not gdpr_accepted:
                    st.error("⚠️ Devi accettare l'Informativa Privacy per continuare.")
                elif not nuova_password or not conferma_password:
                    st.error("⚠️ Compila entrambi i campi password")
                elif nuova_password != conferma_password:
                    st.error("❌ Le password non coincidono")
                else:
                    errori = valida_password_compliance(
                        nuova_password,
                        user_data.get("email", ""),
                        user_data.get("nome_ristorante", ""),
                    )
                    if errori:
                        for err in errori:
                            st.error(err)
                    else:
                        successo, messaggio, _ = imposta_password_da_token(
                            reset_token, nuova_password, supabase
                        )
                        if successo:
                            st.success(
                                "🎉 **Password impostata con successo!**\n\n"
                                "Ora puoi effettuare il login con la tua email e password."
                            )
                            st.balloons()
                            time.sleep(UI_DELAY_LONG)
                            st.query_params.clear()
                            st.rerun()
                        else:
                            st.error(messaggio)
    except Exception:
        st.error(
            "❌ Errore durante la verifica del link. Riprova o contatta il supporto."
        )
        logger.exception("Errore verifica reset_token")

    st.stop()


# ============================================================
# PAGINA LOGIN
# ============================================================

def show_login_page(cookie_manager, supabase) -> None:
    """Mostra la pagina di login/recupero password (non chiama st.stop())."""
    from config.constants import (
        ADMIN_EMAILS,
        UI_DELAY_LONG,
        UI_DELAY_MEDIUM,
        UI_DELAY_SHORT,
    )
    from services.auth_service import (
        imposta_password_da_token,
        invia_codice_reset,
        verifica_credenziali,
        valida_password_compliance,
    )
    from services.db_service import clear_fatture_cache
    from utils.sidebar_helper import render_oh_yeah_header

    try:
        from services.auth_service import riepilogo_fatture_auto_da_ultimo_login
    except ImportError:
        def riepilogo_fatture_auto_da_ultimo_login(*args, **kwargs):
            return {
                "has_new": False,
                "file_count": 0,
                "row_count": 0,
                "event_count": 0,
                "recent_files": [],
                "files_detail": [],
                "window_start": None,
                "window_end": None,
            }

    st.markdown(
        """
        <style>
        /* ✂️ RIDUCI SPAZIO SUPERIORE LOGIN */
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 3rem !important;
        }
        </style>
    """,
        unsafe_allow_html=True,
    )

    # Messaggio scadenza trial (mostrato dopo logout automatico)
    if st.session_state.pop("_trial_expired_msg", False):
        st.error(
            "⏰ **Prova gratuita scaduta.** Il tuo account è stato disattivato. "
            "Contatta il supporto per attivare un abbonamento."
        )

    render_oh_yeah_header()

    st.markdown(
        """
<h2 style="font-size: clamp(2.2rem, 5.5vw, 3.2rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🔐 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Accedi al Sistema</span>
</h2>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<p style="font-size: clamp(0.7rem, 1.6vw, 0.82rem); color: #1e3a8a; margin: 0.75rem 0 1.25rem 0; line-height: 1.6;">
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</p>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div style="background:#f0f7ff;border:1px solid #bdd7f5;border-radius:6px;padding:8px 12px;
            font-size:0.75rem;color:#1e3a8a;margin-bottom:0.8rem;line-height:1.5;">
    🍪 <strong>Cookie tecnici:</strong> Questo sito utilizza esclusivamente cookie tecnici di sessione,
    necessari al funzionamento del servizio. Non vengono usati cookie di profilazione o tracciamento.
    Per maggiori informazioni consulta la pagina dedicata dopo il login.
</div>
""",
        unsafe_allow_html=True,
    )

    if "login_tab_attivo" not in st.session_state:
        st.session_state.login_tab_attivo = "login"

    st.markdown(
        """
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
    """,
        unsafe_allow_html=True,
    )

    col_lt1, col_lt2, _ = st.columns([1.2, 1.8, 5])
    with col_lt1:
        if st.button(
            "🔑 LOGIN",
            key="lt_btn_login",
            use_container_width=True,
            type="primary" if st.session_state.login_tab_attivo == "login" else "secondary",
        ):
            if st.session_state.login_tab_attivo != "login":
                st.session_state.login_tab_attivo = "login"
                st.rerun()
    with col_lt2:
        if st.button(
            "🔄 RECUPERA PASSWORD",
            key="lt_btn_reset",
            use_container_width=True,
            type="primary"
            if st.session_state.login_tab_attivo == "reset"
            else "secondary",
        ):
            if st.session_state.login_tab_attivo != "reset":
                st.session_state.login_tab_attivo = "reset"
                st.rerun()

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    if st.session_state.login_tab_attivo == "login":
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input(
                "🔑 Password", type="password", placeholder="La tua password"
            )
            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Accedi")

            if submit:
                if not email or not password:
                    st.error("⚠️ Compila tutti i campi!")
                else:
                    with st.spinner("Verifica credenziali..."):
                        user, errore = verifica_credenziali(email, password)

                        if user:
                            user.pop("password_hash", None)
                            st.session_state.force_logout = False
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False
                            st.session_state.pop("_session_token_set_this_run", None)
                            st.session_state.partita_iva = user.get("partita_iva")
                            st.session_state.created_at = user.get("created_at")
                            st.session_state.pop("login_tab_attivo", None)

                            # Notifica fatture automatiche ricevute tra login precedente e corrente
                            try:
                                summary_auto = riepilogo_fatture_auto_da_ultimo_login(
                                    user_id=user.get("id"),
                                    last_login_precedente=user.get(
                                        "last_login_precedente"
                                    ),
                                    login_at=user.get("login_at"),
                                    supabase_client=supabase,
                                )
                                if summary_auto.get("has_new") and (
                                    user.get("email") or ""
                                ).strip().lower() not in ADMIN_EMAILS:
                                    st.session_state.auto_invoice_notice = summary_auto
                                    st.session_state.auto_invoice_notice_toast_shown = (
                                        False
                                    )
                                    st.session_state.auto_invoice_notice_dismissed = (
                                        False
                                    )
                                    st.session_state.auto_received_file_origini = {
                                        f["file_name"]
                                        for f in summary_auto.get("files_detail", [])
                                    }
                                else:
                                    st.session_state.pop("auto_invoice_notice", None)
                                    st.session_state.pop(
                                        "auto_invoice_notice_toast_shown", None
                                    )
                                    st.session_state.pop(
                                        "auto_invoice_notice_dismissed", None
                                    )
                                    st.session_state.pop(
                                        "auto_received_file_origini", None
                                    )
                            except Exception as _notice_err:
                                logger.warning(
                                    f"Errore preparazione notifica fatture automatiche: {_notice_err}"
                                )

                            # 🍪 Salva token nel cookie persistente
                            # Path JWT: se verifica_credenziali() ha restituito refresh_token Supabase Auth,
                            # usalo come cookie (backward-compat: stessa chiave "session_token").
                            # Path legacy: genera UUID opaco e salvalo su public.users.session_token.
                            if cookie_manager is not None and not st.session_state.get(
                                "_session_token_set_this_run"
                            ):
                                st.session_state["_session_token_set_this_run"] = True
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _jwt_refresh_token = user.get("_jwt_refresh_token")

                                    if _jwt_refresh_token:
                                        # PATH JWT: salva refresh_token Supabase Auth nel cookie.
                                        # Aggiorna last_seen_at nel DB (non genera session_token legacy).
                                        supabase.table("users").update(
                                            {
                                                "last_seen_at": _now_utc.isoformat(),
                                            }
                                        ).eq("id", user.get("id")).execute()
                                        cookie_manager.set(
                                            "session_token",
                                            _jwt_refresh_token,
                                            expires_at=datetime.now(timezone.utc)
                                            + timedelta(days=30),
                                            secure=True,
                                            same_site="strict",
                                        )
                                        logger.debug(f"🔑 Cookie JWT impostato per user_id={user.get('id')}")
                                    else:
                                        # PATH LEGACY: genera UUID opaco, salvalo su public.users.
                                        _s_token = _secrets.token_urlsafe(32)
                                        supabase.table("users").update(
                                            {
                                                "session_token": _s_token,
                                                "session_token_created_at": _now_utc.isoformat(),
                                                "last_seen_at": _now_utc.isoformat(),
                                            }
                                        ).eq("id", user.get("id")).execute()
                                        cookie_manager.set(
                                            "session_token",
                                            _s_token,
                                            expires_at=datetime.now(timezone.utc)
                                            + timedelta(days=30),
                                            secure=True,
                                            same_site="strict",
                                        )
                                        logger.debug(f"🔑 Cookie legacy impostato per user_id={user.get('id')}")

                                    # Rimuovi token JWT da session_state (non devono essere esposti)
                                    user.pop("_jwt_access_token", None)
                                    user.pop("_jwt_refresh_token", None)
                                    st.session_state.user_data = user
                                    st.session_state._last_seen_write_at = _now_utc.isoformat()
                                except Exception as _ce:
                                    logger.warning(
                                        f"Errore salvataggio session token: {_ce}"
                                    )
                            else:
                                st.warning(
                                    "⚠️ Sessione non persistente: "
                                    "verifica che i cookie siano abilitati nel browser. "
                                    "Verrai disconnesso ad ogni aggiornamento pagina."
                                )

                            if (user.get("email") or "").strip().lower() in ADMIN_EMAILS:
                                st.session_state.user_is_admin = True
                                logger.info(
                                    f"✅ Login ADMIN: user_id={user.get('id')}"
                                )
                                st.success("✅ Accesso effettuato come ADMIN!")
                                time.sleep(UI_DELAY_SHORT)
                                st.switch_page("pages/admin.py")
                                st.stop()
                            else:
                                st.session_state.user_is_admin = False
                                logger.info(
                                    f"✅ Login cliente: user_id={user.get('id')}"
                                )
                                clear_fatture_cache()
                                st.session_state.force_reload = True
                                st.session_state.show_welcome = True
                                logger.info(
                                    f"[LOGIN] Fatture cache cleared + force_reload "
                                    f"per user_id={user.get('id')}"
                                )
                                st.success("✅ Accesso effettuato!")
                                time.sleep(UI_DELAY_MEDIUM)
                                st.rerun()
                        else:
                            st.error(f"❌ {errore}")

    elif st.session_state.login_tab_attivo == "reset":
        st.markdown("#### Reset Password via Email")
        st.markdown(
            """
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
        """,
            unsafe_allow_html=True,
        )

        reset_email = st.text_input(
            "📧 Email per reset",
            placeholder="tua@email.com",
            key="reset_email",
        )

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

        code_input = st.text_input(
            "🔢 Codice ricevuto",
            placeholder="Inserisci il codice",
            key="code_input",
        )
        new_pwd = st.text_input(
            "🔑 Nuova password (min 10 caratteri)",
            type="password",
            key="new_pwd",
        )
        confirm_pwd = st.text_input(
            "🔑 Conferma password", type="password", key="confirm_pwd"
        )

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
                        successo, messaggio, user = imposta_password_da_token(
                            code_input, new_pwd
                        )
                        if successo and user:
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False
                            st.session_state.pop("login_tab_attivo", None)
                            if cookie_manager is not None:
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _s_token = _secrets.token_urlsafe(32)
                                    supabase.table("users").update(
                                        {
                                            "session_token": _s_token,
                                            "session_token_created_at": _now_utc.isoformat(),
                                            "last_seen_at": _now_utc.isoformat(),
                                        }
                                    ).eq("id", user.get("id")).execute()
                                    cookie_manager.set(
                                        "session_token",
                                        _s_token,
                                        expires_at=datetime.now(timezone.utc)
                                        + timedelta(days=7),
                                        secure=True,
                                        same_site="strict",
                                    )
                                    st.session_state._last_seen_write_at = (
                                        _now_utc.isoformat()
                                    )
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
# GATE LOGIN
# ============================================================

def check_login_gate(supabase, cookie_manager) -> None:
    """
    Se force_logout attivo → forza logged_in=False.
    Se non loggato → mostra login e st.stop().
    Se user_data invalido → forza logout e st.rerun().
    """
    if st.session_state.get("force_logout", False):
        logger.critical("⛔ force_logout attivo - forzando logged_in=False")
        st.session_state.logged_in = False
        st.session_state.user_data = None

    if not st.session_state.get("logged_in", False):
        logger.info("👤 Utente non loggato - mostrando pagina login")
        st.session_state._rerun_guard = 0
        show_login_page(cookie_manager, supabase)
        st.stop()

    user = st.session_state.get("user_data") or {}
    if not user or not user.get("email"):
        logger.critical("❌ user_data è None o mancante email - FORZA LOGOUT")
        if cookie_manager is not None:
            try:
                _email_emergency = (
                    st.session_state.get("user_data", {}).get("email")
                    if st.session_state.get("user_data")
                    else None
                )
                if _email_emergency:
                    supabase.table("users").update(
                        {
                            "session_token": None,
                            "session_token_created_at": None,
                            "last_seen_at": None,
                        }
                    ).eq("email", _email_emergency).execute()
            except Exception:
                pass
        st.session_state.clear()
        st.session_state.logged_in = False
        st.session_state.force_logout = True
        st.session_state._cookie_checked = True
        st.rerun()


# ============================================================
# RIPRISTINO FLAG ADMIN
# ============================================================

def restore_admin_flags() -> None:
    """Ripristina o rimuove il flag user_is_admin basandosi su ADMIN_EMAILS."""
    from config.constants import ADMIN_EMAILS

    user = st.session_state.get("user_data", {}) or {}
    if (user.get("email") or "").strip().lower() in ADMIN_EMAILS:
        if not st.session_state.get("user_is_admin", False):
            st.session_state.user_is_admin = True
            logger.info(f"✅ Flag admin ripristinato per user_id={user.get('id')}")
    else:
        if st.session_state.get("user_is_admin", False):
            st.session_state.user_is_admin = False
            logger.warning(
                f"⚠️ Flag admin rimosso per utente non-admin: user_id={user.get('id')}"
            )


# ============================================================
# RIPRISTINO IMPERSONAZIONE DA COOKIE (dopo F5/refresh)
# ============================================================

def restore_impersonation_from_cookie(cookie_manager, supabase) -> None:
    """
    Se l'admin è loggato ma non sta impersonando, controlla se c'era
    un'impersonazione attiva prima del refresh e ripristinala.
    Aggiorna st.session_state.user_data direttamente.
    """
    if not (
        st.session_state.get("user_is_admin", False)
        and not st.session_state.get("impersonating", False)
        and cookie_manager is not None
    ):
        return
    try:
        _imp_uid_cookie = cookie_manager.get("impersonation_user_id")
        if not _imp_uid_cookie:
            return
        _imp_resp = (
            supabase.table("users")
            .select("id, email, nome_ristorante, attivo, pagine_abilitate")
            .eq("id", _imp_uid_cookie)
            .eq("attivo", True)
            .execute()
        )
        if _imp_resp and _imp_resp.data:
            _imp_customer = _imp_resp.data[0]
            st.session_state.admin_original_user = st.session_state.user_data.copy()
            st.session_state.user_data = {
                "id": _imp_customer["id"],
                "email": _imp_customer["email"],
                "nome_ristorante": _imp_customer.get("nome_ristorante"),
                "attivo": _imp_customer.get("attivo", True),
                "pagine_abilitate": _imp_customer.get("pagine_abilitate"),
            }
            st.session_state.user_is_admin = False
            st.session_state.impersonating = True
            if not st.session_state.get("impersonation_started_at"):
                st.session_state.impersonation_started_at = datetime.now(
                    timezone.utc
                ).isoformat()
            logger.info(
                f"✅ Impersonazione ripristinata da cookie dopo refresh: "
                f"user_id={_imp_customer.get('id')}"
            )
        else:
            cookie_manager.set(
                "impersonation_user_id",
                "",
                expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
            )
            logger.warning(
                f"⚠️ Cliente impersonato non trovato (id={_imp_uid_cookie}) - cookie rimosso"
            )
    except Exception as e:
        logger.warning(f"Errore ripristino impersonazione da cookie: {e}")


# ============================================================
# TRIAL: VERIFICA SCADENZA + LOGOUT SE SCADUTA
# ============================================================

def check_trial_or_expire(supabase) -> None:
    """
    Verifica scadenza trial per utenti normali.
    Admin e sessioni impersonazione ricevono trial_info fittizio (nessuna restrizione).
    """
    user = st.session_state.get("user_data", {}) or {}

    if (
        st.session_state.get("user_is_admin", False)
        or st.session_state.get("impersonating", False)
        or not user.get("id")
    ):
        # Admin o sessione impersonazione: sovrascriviamo SEMPRE per evitare
        # trial_info residuo da sessione precedente.
        st.session_state.trial_info = {
            "is_trial": False,
            "days_left": 0,
            "trial_month": None,
            "trial_year": None,
            "expired": False,
        }
        return

    _t_uid = user["id"]
    _t_now = datetime.now(timezone.utc)
    _t_last_raw = st.session_state.get("_trial_check_at")
    _cached_ti = st.session_state.get("trial_info", {})
    _cached_month = _cached_ti.get("trial_month")
    _month_mismatch = (
        _cached_ti.get("is_trial")
        and _cached_month is not None
        and _cached_month != _t_now.month
    )

    _needs_refresh = (
        "trial_info" not in st.session_state
        or not _t_last_raw
        or _month_mismatch
        or (
            _t_now
            - datetime.fromisoformat(str(_t_last_raw).replace("Z", "+00:00"))
        ).total_seconds()
        > 300
    )
    if not _needs_refresh:
        return

    from services.auth_service import (
        disattiva_trial_scaduta as _dis_ti,
        get_trial_info as _get_ti,
    )

    _fresh_ti = _get_ti(_t_uid, supabase)
    st.session_state.trial_info = _fresh_ti
    st.session_state._trial_check_at = _t_now.isoformat()

    if not _fresh_ti.get("expired"):
        return

    _ok_dis = _dis_ti(_t_uid, supabase)
    if not _ok_dis:
        logger.error(
            f"⚠️ disattiva_trial_scaduta FALLITA per user_id={_t_uid} "
            f"— logout forzato comunque"
        )
    try:
        supabase.table("users").update(
            {
                "session_token": None,
                "session_token_created_at": None,
            }
        ).eq("id", _t_uid).execute()
    except Exception as e:
        logger.error(
            f"Errore invalidazione session_token per trial scaduta: {e}"
        )
    st.session_state.clear()
    st.session_state.logged_in = False
    st.session_state._trial_expired_msg = True
    logger.warning(
        f"⏰ Trial scaduta → logout forzato: user_id={_t_uid} "
        f"(disattivazione_ok={_ok_dis})"
    )
    st.rerun()


# ============================================================
# BANNER IMPERSONAZIONE + BOTTONE "TORNA ADMIN"
# ============================================================

def render_impersonation_banner(supabase, cookie_manager) -> None:
    """
    Mostra il banner arancione/rosso di impersonazione e il bottone 'Torna Admin'.
    Se l'admin clicca, ripristina la sessione admin e reindirizza a admin.py.
    """
    import html as _html

    if not st.session_state.get("impersonating", False):
        return

    user = st.session_state.get("user_data", {}) or {}

    st.markdown(
        f"""
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
    """,
        unsafe_allow_html=True,
    )

    col_back_admin, col_spacer = st.columns([2, 8])
    with col_back_admin:
        if st.button(
            "🔙 Torna Admin",
            type="primary",
            use_container_width=True,
            key="back_to_admin_btn",
        ):
            if "admin_original_user" in st.session_state:
                _imp_client_email_end = user.get("email", "?")
                st.session_state.user_data = st.session_state.admin_original_user.copy()
                del st.session_state.admin_original_user
                st.session_state.impersonating = False
                st.session_state.user_is_admin = True

                # 🏢 Ripristina ristoranti admin (tutti i ristoranti del sistema)
                try:
                    ristoranti_admin = (
                        supabase.table("ristoranti")
                        .select(
                            "id, nome_ristorante, partita_iva, ragione_sociale, user_id"
                        )
                        .eq("attivo", True)
                        .order("nome_ristorante")
                        .execute()
                    )
                    st.session_state.ristoranti = (
                        ristoranti_admin.data if ristoranti_admin.data else []
                    )
                    for _k in ("ristorante_id", "partita_iva", "nome_ristorante"):
                        st.session_state.pop(_k, None)
                    logger.info(
                        f"🔙 ADMIN: Ripristinati "
                        f"{len(st.session_state.ristoranti)} ristoranti del sistema"
                    )
                except Exception as e:
                    logger.error(f"Errore ripristino ristoranti admin: {e}")

                # Log durata impersonazione
                _imp_duration_min = "?"
                _imp_started_end = st.session_state.pop("impersonation_started_at", None)
                if _imp_started_end:
                    try:
                        _s_dt = datetime.fromisoformat(
                            str(_imp_started_end).replace("Z", "+00:00")
                        )
                        if _s_dt.tzinfo is None:
                            _s_dt = _s_dt.replace(tzinfo=timezone.utc)
                        _imp_duration_min = int(
                            (datetime.now(timezone.utc) - _s_dt).total_seconds() / 60
                        )
                    except (ValueError, TypeError):
                        pass
                logger.info(
                    f"🔒 IMPERSONATION END: "
                    f"admin={st.session_state.user_data.get('email')} "
                    f"→ client={_imp_client_email_end} "
                    f"duration={_imp_duration_min}min"
                )

                if cookie_manager is not None:
                    try:
                        cookie_manager.set(
                            "impersonation_user_id",
                            "",
                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
                        )
                    except Exception:
                        pass

                st.switch_page("pages/admin.py")
                st.stop()
            else:
                st.error("⚠️ Errore: dati admin originali non trovati")
                st.session_state.impersonating = False
                if cookie_manager is not None:
                    try:
                        cookie_manager.set(
                            "impersonation_user_id",
                            "",
                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
                        )
                    except Exception:
                        pass
                st.rerun()

    st.markdown("---")
