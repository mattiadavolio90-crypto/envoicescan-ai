"""
controllers/upload_controller.py
Logica di orchestrazione upload estratta da app.py (Step 1.3).

Espone:
    show_upload_messages()                            Messaggi persistenti post-upload (30s TTL) + errore limite.
    process_uploaded_files(uploaded_files, supabase,  Chiama handle_uploaded_files dal servizio upload.
                           user_id)
    render_competenza_review(user_id)                 UI review date di competenza post-upload.
"""

import streamlit as st
import logging
import time

logger = logging.getLogger("fci_app")


def show_upload_messages() -> None:
    """
    Mostra messaggi persistenti dall'ultimo upload (TTL 30 secondi).
    Include avvisi TD24 MISSING e l'eventuale errore di limite upload.
    """
    if 'upload_messages' in st.session_state and st.session_state.upload_messages:
        _msg_age = time.time() - st.session_state.get('upload_messages_time', 0)
        if _msg_age < 30:
            for _msg in st.session_state.upload_messages:
                st.markdown(_msg, unsafe_allow_html=True)
            # Inline st.error per TD24 MISSING (pct < 50%)
            _td24_ctx = (st.session_state.get('last_upload_notification_context') or {}).get('td24_date_alerts') or []
            _td24_missing = [a for a in _td24_ctx if a.get('status') == 'missing']
            if _td24_missing:
                _td24_lines = []
                for _a in _td24_missing:
                    _td24_lines.append(
                        f"• **{_a.get('fornitore', '?')}** ({_a.get('file_name', '?')}) — "
                        f"{_a.get('lines_with_date', 0)}/{_a.get('lines_total', 0)} righe con data consegna"
                    )
                st.error(
                    "📅 **Fatture differite (TD24) senza data consegna:**\n\n"
                    + "\n".join(_td24_lines)
                    + "\n\nLa data consegna è importante per l'analisi dei margini mensili."
                )
        else:
            st.session_state.upload_messages = []

    # 🔥 MOSTRA ERRORE LIMITE UPLOAD (dopo reset widget)
    if '_upload_limit_error' in st.session_state:
        st.error(st.session_state.pop('_upload_limit_error'))


def process_uploaded_files(uploaded_files: list, supabase, user_id: str) -> None:
    """
    Chiama ``handle_uploaded_files`` dal servizio upload se ci sono file.
    Il chiamante è responsabile di invocare eventuali debug snap dopo il ritorno.
    """
    if uploaded_files:
        from services.upload_handler import handle_uploaded_files
        handle_uploaded_files(uploaded_files, supabase, user_id)


def render_competenza_review(user_id: str) -> None:
    """
    Mostra l'expander di review delle date di competenza per fatture
    emesse a inizio mese (se presenti in ``pending_competenza_review``).
    """
    _pending_competenza = st.session_state.get('pending_competenza_review')
    if not _pending_competenza:
        return

    from config.constants import COMPETENZA_AUTO_SOGLIA_GIORNI
    from services.db_service import aggiorna_data_competenza_fattura, clear_fatture_cache
    from services.ai_service import invalida_cache_memoria

    st.markdown("""
    <style>
    div.st-key-competenza_review_box [data-testid="stExpander"] details summary {
        background: linear-gradient(135deg, rgba(255, 243, 205, 0.97) 0%, rgba(255, 230, 155, 0.97) 100%) !important;
        border-radius: 8px !important; padding: 10px 14px !important;
        color: #856404 !important; font-weight: 700 !important;
        border: 1px solid #ffc107 !important;
    }
    div.st-key-competenza_review_box [data-testid="stExpander"] details {
        background: rgba(255, 249, 230, 0.97) !important;
        border: 1px solid #ffc107 !important; border-radius: 8px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.container(key="competenza_review_box"):
        with st.expander(
            f"⚠️ {len(_pending_competenza)} fattura/e emessa/e nei primi {COMPETENZA_AUTO_SOGLIA_GIORNI} giorni del mese — Verifica data di competenza",
            expanded=True
        ):
            st.markdown(
                "Le fatture sotto sono state emesse a inizio mese e potrebbero riferirsi al **mese precedente**. "
                "Spunta quelle da assegnare al mese indicato e clicca **Applica**. Lascia deselezionate le altre."
            )
            _selections = {}
            import pandas as _pd_comp
            for _item in _pending_competenza:
                _col_check, _col_info = st.columns([0.05, 0.95])
                with _col_check:
                    _selections[_item['file']] = st.checkbox(
                        "", value=True,
                        key=f"comp_chk_{_item['file']}",
                    )
                with _col_info:
                    _badge = "🔴 DATA MODIFICATA" if False else ""
                    st.markdown(
                        f"**{_item['fornitore']}** — `{_item['file']}`  \n"
                        f"Data documento: **{_item['data_documento']}** &nbsp;→&nbsp; "
                        f"Competenza suggerita: **{_item['mese_suggerito']}**"
                    )
            st.markdown("---")
            _col_apply, _col_skip, _col_spacer = st.columns([1, 1, 4])
            with _col_apply:
                if st.button("✅ Applica competenze selezionate", type="primary", use_container_width=True, key="btn_applica_competenza"):
                    _files_selezionati = [_item for _item in _pending_competenza if _selections.get(_item['file'], False)]
                    if _files_selezionati:
                        _errori_comp = []
                        for _item in _files_selezionati:
                            _esito = aggiorna_data_competenza_fattura(
                                file_origine=_item['file'],
                                user_id=user_id,
                                data_competenza=_item['data_competenza_suggerita'],
                                ristoranteid=st.session_state.get('ristorante_id'),
                            )
                            if not _esito.get('success'):
                                _errori_comp.append(_item['file'])
                        clear_fatture_cache()
                        invalida_cache_memoria()
                        del st.session_state['pending_competenza_review']
                        if _errori_comp:
                            st.warning(f"⚠️ Errore su: {', '.join(_errori_comp)}")
                        else:
                            _n_ok = len(_files_selezionati)
                            st.success(f"✅ {_n_ok} fattura/e assegnata/e al mese precedente")
                        st.rerun()
                    else:
                        st.info("Nessuna fattura selezionata.")
            with _col_skip:
                if st.button("✖️ Ignora", use_container_width=True, key="btn_skip_competenza"):
                    del st.session_state['pending_competenza_review']
                    st.rerun()
