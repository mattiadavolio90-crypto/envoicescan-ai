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

        st.markdown("""
        <style>
        div.st-key-main_documents_upload_section .documents-header-row {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.5rem 1rem;
            padding: 0 0 12px 0;
        }
        div.st-key-main_documents_upload_section .documents-title {
            font-size: 2.25rem;
            font-weight: 700;
            color: #1f4e8c;
            line-height: 1.2;
        }
        div.st-key-main_documents_upload_section .documents-warning {
            font-size: 0.88rem;
            color: #166534;
            font-weight: 500;
            line-height: 1.4;
        }
        /* upload_hint_row: forza tutti i wrapper Streamlit a restringersi al contenuto */
        div.st-key-upload_hint_row {
            display: inline-flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 0.55rem !important;
            flex-wrap: nowrap !important;
            width: auto !important;
            max-width: 100% !important;
        }
        div.st-key-upload_hint_row > div,
        div.st-key-upload_hint_row > div > div {
            width: fit-content !important;
            max-width: fit-content !important;
            flex: 0 0 auto !important;
            min-width: 0 !important;
        }
        div.st-key-upload_hint_row > div:last-child,
        div.st-key-upload_hint_row > div:last-child > div {
            width: auto !important;
            max-width: none !important;
        }
        div.st-key-main_documents_upload_section .upload-format-hint {
            color: #2d6a4f;
            font-size: clamp(0.8rem, 0.3vw + 0.74rem, 0.9rem);
            font-weight: 600;
            line-height: 1.3;
            white-space: nowrap;
            margin: 0 !important;
        }
        div.st-key-main_documents_upload_section .upload-ai-spacer {
            height: 34px;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] {
            margin: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] > div,
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] > div > div,
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] section,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"],
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] > div {
            width: fit-content !important;
            max-width: fit-content !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] section {
            display: inline-flex !important;
            align-items: center !important;
            padding: 0 !important;
            min-height: 0 !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] {
            display: inline-flex !important;
            align-items: center !important;
            padding: 0 !important;
            min-height: 0 !important;
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzoneInstructions"] {
            visibility: hidden !important;
            position: absolute !important;
            width: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] > div {
            width: auto !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button {
            min-width: 12.5rem !important;
            height: 2.9rem !important;
            min-height: 2.9rem !important;
            padding: 0.72rem 1.05rem !important;
            border-radius: 10px !important;
            border: 1px solid #2d6a4f !important;
            background-color: #2d6a4f !important;
            color: transparent !important;
            box-shadow: none !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            position: relative !important;
            overflow: hidden !important;
            transform: none !important;
            line-height: 1 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button > * {
            opacity: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button p,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button span,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button div {
            font-size: 0 !important;
            line-height: 0 !important;
            margin: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button::after {
            content: "📄 Carica Documenti" !important;
            position: absolute !important;
            left: 50% !important;
            top: 50% !important;
            transform: translate(-50%, -50%) !important;
            width: max-content !important;
            text-align: center !important;
            font-size: clamp(0.85rem, 0.4vw + 0.75rem, 1rem) !important;
            line-height: 1.1 !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            pointer-events: none !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button:hover,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button:focus,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button:active {
            border-color: #1f513b !important;
            background-color: #1f513b !important;
            color: transparent !important;
            transform: none !important;
        }
        @media (max-width: 767px) {
            div.st-key-main_documents_upload_section .upload-format-hint {
                min-height: auto;
                padding-top: 0.15rem;
            }
            div.st-key-main_documents_upload_section .upload-ai-spacer {
                height: 12px;
            }
        }
        </style>
        """, unsafe_allow_html=True)

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
