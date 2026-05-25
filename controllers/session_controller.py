"""
controllers/session_controller.py
Logica di sessione estratta da app.py — Step 1.2 refactor.

Funzioni:
  init_ristoranti_session(supabase, user) — carica/inizializza ristoranti in session_state
"""
import logging

import streamlit as st

logger = logging.getLogger("fci_app")


def init_ristoranti_session(supabase, user) -> None:
    """
    Carica i ristoranti dell'utente in st.session_state e imposta il ristorante corrente.

    Casistiche gestite:
    - Admin puro → usa ensure_admin_test_workspace (workspace di test)
    - Utente normale o admin-in-impersonazione → carica da tabella ristoranti
      - Imposta default (ultimo usato o primo)
      - Utente legacy senza ristoranti → tenta auto-creazione da P.IVA
      - Fallback su dati tabella users se tutto il resto fallisce

    Effetti collaterali:
    - Scrive su st.session_state: ristoranti, ristorante_id, partita_iva, nome_ristorante
    - Può chiamare st.rerun() in caso di errore critico o creazione ristorante
    - Può chiamare st.success() / st.warning() per messaggi UI inline
    """
    from utils.ristorante_helper import ensure_admin_test_workspace

    # ------------------------------------------------------------------
    # SAFETY CHECK: user deve essere valido (già garantito da check_login_gate,
    # ma difesa in profondità)
    # ------------------------------------------------------------------
    if not user or not user.get('id'):
        logger.error("❌ ERRORE CRITICO: user non definito in init_ristoranti_session")
        st.session_state.logged_in = False
        st.session_state.force_logout = True
        st.session_state._cookie_checked = True
        st.rerun()

    _is_pure_admin = (
        st.session_state.get('user_is_admin', False)
        and not st.session_state.get('impersonating', False)
    )

    # ------------------------------------------------------------------
    # RAMO ADMIN PURO → workspace test
    # ------------------------------------------------------------------
    if _is_pure_admin:
        try:
            admin_workspace = ensure_admin_test_workspace(supabase, user)
            st.session_state.ristoranti = [admin_workspace] if admin_workspace else []

            if admin_workspace:
                st.session_state.ristorante_id = admin_workspace['id']
                st.session_state.partita_iva = admin_workspace.get('partita_iva')
                st.session_state.nome_ristorante = (
                    admin_workspace.get('nome_ristorante') or 'Ambiente Test Admin'
                )
                logger.info(f"🧪 Admin workspace test attivo: rist_id={admin_workspace['id']}")
            else:
                logger.warning("⚠️ Nessun workspace test admin disponibile")
                st.session_state.pop('ristorante_id', None)
                st.session_state.partita_iva = None
                st.session_state.nome_ristorante = 'Ambiente Test Admin'
        except Exception as e:
            logger.exception(f"Errore setup workspace test admin: {e}")
            st.session_state.ristoranti = []
            st.session_state.pop('ristorante_id', None)
            st.session_state.partita_iva = None
            st.session_state.nome_ristorante = 'Ambiente Test Admin'

    # ------------------------------------------------------------------
    # RAMO UTENTE NORMALE (o admin in impersonazione)
    # Carica solo se ristoranti non ancora in sessione o nessun ristorante_id
    # ------------------------------------------------------------------
    elif 'ristoranti' not in st.session_state or not st.session_state.get('ristorante_id'):
        try:
            ristoranti = supabase.table('ristoranti') \
                .select('id, nome_ristorante, partita_iva, ragione_sociale') \
                .eq('user_id', user.get('id')) \
                .eq('attivo', True) \
                .execute()

            logger.info(
                f"🔍 DEBUG: Caricati "
                f"{len(ristoranti.data) if ristoranti.data else 0} "
                f"ristoranti per user_id={user.get('id')}"
            )
            st.session_state.ristoranti = ristoranti.data if ristoranti.data else []

            if st.session_state.ristoranti:
                # Imposta ristorante di default (ultimo usato o primo in lista)
                if 'ristorante_id' not in st.session_state:
                    ultimo_id = user.get('ultimo_ristorante_id')
                    ristorante_default = None
                    if ultimo_id:
                        ristorante_default = next(
                            (r for r in st.session_state.ristoranti if r['id'] == ultimo_id),
                            None,
                        )
                    if ristorante_default is None:
                        ristorante_default = st.session_state.ristoranti[0]
                    st.session_state.ristorante_id = ristorante_default['id']
                    st.session_state.partita_iva = ristorante_default['partita_iva']
                    st.session_state.nome_ristorante = ristorante_default['nome_ristorante']
                    logger.info(
                        f"🏢 Ristorante caricato: rist_id={ristorante_default['id']}"
                        f"{' [ultimo usato]' if ultimo_id and ristorante_default['id'] == ultimo_id else ' [primo in lista]'}"
                    )
            else:
                # ⚠️ UTENTE LEGACY: nessun ristorante trovato in tabella
                _handle_legacy_user(supabase, user)

        except Exception as e:
            logger.exception(f"Errore caricamento ristoranti: {e}")
            # Fallback: usa dati dalla tabella users (solo utenti non-admin)
            if not st.session_state.get('user_is_admin', False):
                st.session_state.ristoranti = []
                st.session_state.partita_iva = user.get('partita_iva')
                st.session_state.nome_ristorante = user.get('nome_ristorante')


def _handle_legacy_user(supabase, user) -> None:
    """
    Gestisce utente senza ristoranti nella tabella ristoranti.
    Tenta auto-creazione da P.IVA; in caso di fallimento usa dati dalla tabella users.
    Chiamata solo da init_ristoranti_session quando ristoranti è vuoto.
    """
    if st.session_state.get('user_is_admin', False):
        logger.warning("⚠️ Admin senza ristoranti nel sistema")
        return

    piva = user.get('partita_iva')
    nome = user.get('nome_ristorante')
    user_id = user.get('id')

    if piva and user_id:
        logger.warning(
            f"⚠️ Utente legacy {user_id} senza ristoranti - tentativo creazione automatica\n"
            f"   Dati: nome='{nome}', piva=***{piva[-4:] if piva and len(piva) >= 4 else '????'}"
        )
        try:
            # Cerca ristorante con questa P.IVA dello stesso utente
            check_existing = supabase.table('ristoranti') \
                .select('id, user_id, nome_ristorante') \
                .eq('partita_iva', piva) \
                .eq('user_id', user_id) \
                .execute()

            if check_existing.data and len(check_existing.data) > 0:
                existing = check_existing.data[0]
                st.session_state.ristoranti = [existing]
                st.session_state.ristorante_id = existing['id']
                st.session_state.partita_iva = piva
                st.session_state.nome_ristorante = existing['nome_ristorante']
                logger.info(f"✅ Ristorante esistente trovato e collegato: {existing['id']}")
            else:
                nome_rist = nome or f"Ristorante {piva}"
                new_rist = supabase.table('ristoranti').insert({
                    'user_id': user_id,
                    'nome_ristorante': nome_rist,
                    'partita_iva': piva,
                    'ragione_sociale': user.get('ragione_sociale', ''),
                    'attivo': True,
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
                    logger.error(
                        f"❌ Creazione ristorante fallita per utente {user_id} - response vuota"
                    )
                    st.warning(
                        "⚠️ Configurazione account incompleta. "
                        "Alcune funzionalità potrebbero non essere disponibili."
                    )
        except Exception as create_err:
            logger.error(f"❌ ERRORE DETTAGLIATO creazione ristorante: {str(create_err)}")
            logger.error(f"   Tipo errore: {type(create_err).__name__}")
            st.warning(f"⚠️ Problemi di configurazione rilevati: {str(create_err)[:100]}")
    elif user_id:
        # P.IVA assente ma user_id presente: crea ristorante con placeholder
        logger.warning(
            f"⚠️ Utente {user_id} senza ristoranti e senza P.IVA — creazione ristorante con placeholder"
        )
        try:
            _piva_placeholder = f"TEMP{user_id.replace('-', '')[:11].upper()}"
            _nome_rist = nome or f"Account {user_id[:8]}"
            new_rist = supabase.table('ristoranti').insert({
                'user_id': user_id,
                'nome_ristorante': _nome_rist,
                'partita_iva': _piva_placeholder,
                'ragione_sociale': user.get('ragione_sociale', ''),
                'attivo': True,
            }).execute()
            if new_rist.data:
                st.session_state.ristoranti = new_rist.data
                st.session_state.ristorante_id = new_rist.data[0]['id']
                st.session_state.partita_iva = _piva_placeholder
                st.session_state.nome_ristorante = _nome_rist
                logger.info(f"✅ Ristorante placeholder creato: {new_rist.data[0]['id']}")
                st.warning("⚠️ P.IVA mancante — completa i dati nelle impostazioni del profilo.")
                st.rerun()
            else:
                logger.error(f"❌ Creazione ristorante placeholder fallita per utente {user_id}")
                st.error("⚠️ Configurazione account incompleta. Contatta l'assistenza.")
        except Exception as _placeholder_err:
            logger.error(f"❌ Errore creazione ristorante senza P.IVA: {_placeholder_err}")
            st.error(f"⚠️ Problemi di configurazione: {str(_placeholder_err)[:100]}")
    else:
        logger.warning(f"⚠️ Utente {user_id} senza ristoranti e dati incompleti - accesso limitato")
        st.warning(
            "⚠️ Configurazione account incompleta. "
            "Contatta l'assistenza per configurare il tuo ristorante."
        )

    # FALLBACK finale: se ristoranti è ancora vuoto, usa dati tabella users
    if not st.session_state.get('ristoranti'):
        piva = user.get('partita_iva')
        nome = user.get('nome_ristorante')
        logger.warning(
            f"⚠️ Utente {user.get('email')} senza ristoranti in tabella - fallback su dati users"
        )
        st.session_state.partita_iva = piva
        st.session_state.nome_ristorante = nome
