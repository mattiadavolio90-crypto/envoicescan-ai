"""
components/upload_panel.py
UI del pannello caricamento documenti — estratto da app.py (Step 1.3).

Espone:
    render_upload_panel() -> list   Renderizza il container file uploader e restituisce la lista
                                    dei file caricati (può essere vuota).
"""

import streamlit as st
import logging

logger = logging.getLogger("fci_app")


def render_upload_panel() -> list:
    """
    Renderizza il container ``main_documents_upload_section`` con CSS, header e
    widget ``st.file_uploader``.

    Returns:
        list: file caricati dall'utente (lista vuota se nessun file).
    """
    uploaded_files = []

    with st.container(key="main_documents_upload_section"):
        _is_pure_admin_upload = st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False)
        _documents_warning_html = (
            "🧪 <strong>AMBIENTE TEST ADMIN:</strong> puoi caricare documenti liberamente per prove, training AI e categorizzazione."
            if _is_pure_admin_upload
            else "⚠️ <strong>IMPORTANTE:</strong> Le fatture caricate devono corrispondere alla P.IVA del ristorante mostrato sopra! <strong>Altrimenti verranno scartate</strong>"
        )

        st.markdown(f"""
        <div class="documents-header-row">
            <div class="documents-title">📄 Documenti</div>
            <div class="documents-warning">
                {_documents_warning_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Upload panel CSS (documents-header-row, upload_hint_row, dropzone button) ora in common.css

        col_upload, col_ai_right = st.columns([3, 2])

        with col_upload:
            with st.container(key="upload_hint_row"):
                uploaded_files = st.file_uploader(
                    "Carica file",
                    accept_multiple_files=True,
                    type=['xml', 'p7m', 'pdf', 'jpg', 'jpeg', 'png'],
                    label_visibility="collapsed",
                    key=f"file_uploader_{st.session_state.get('uploader_key', 0)}"
                )
                st.markdown(
                    "<div class='upload-format-hint'>Formati accettati: XML, P7M, PDF, PNG, JPG, JPEG · Max 200MB</div>",
                    unsafe_allow_html=True,
                )

        if uploaded_files and len(uploaded_files) > 0:
            # Durante l'elaborazione nasconde il rettangolo drag&drop in trasparenza.
            st.markdown(
                """
                <style>
                div.st-key-main_documents_upload_section div.st-key-upload_hint_row {
                    display: none !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

        with col_ai_right:
            st.markdown("<div class='upload-ai-spacer'></div>", unsafe_allow_html=True)

    return uploaded_files or []
