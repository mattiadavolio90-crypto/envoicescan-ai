"""
Gestione Fatture e Notifiche - Scadenziario e Avvisi
Step 6/7: gestione documenti caricati + regole fornitore + notifiche scadenze.
"""

import logging
import os
import time
import html
from datetime import date

import pandas as pd
import streamlit as st

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

from config.constants import MESI_ITA, COMPETENZA_AUTO_SOGLIA_GIORNI
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ristorante_helper import get_current_ristorante_id, add_ristorante_filter
from utils.page_setup import check_page_enabled
from utils.text_utils import format_fattura_label
from services.documenti_service import (
    clear_documenti_cache,
    get_cache_version,
    get_documenti_list,
    segna_fattura_pagata,
)
from services.ai_service import invalida_cache_memoria
from services.db_service import (
    aggiorna_data_competenza_fattura,
    carica_e_prepara_dataframe,
    clear_fatture_cache,
    elimina_fattura_completa,
    elimina_tutte_fatture,
    filter_active,
    get_fatture_cestino,
    get_fatture_stats,
    ripristina_fattura,
    svuota_cestino,
)
from services.notification_service import build_scoped_notification_id
from services.notification_inbox_service import (
    dismiss_inbox_topics,
    dismiss_all_inbox_notifications,
    dismiss_inbox_notification,
    get_inbox_badge_count,
    get_inbox_notifications,
)
from services.daily_briefing_service import (
    generate_and_save_briefing,
    get_today_briefing,
    notifications_fingerprint,
)
from services import get_supabase_client


st.set_page_config(
    page_title="Notifiche e Gestione - ONEFLUX",
    page_icon="🔔",
    layout="wide",
    initial_sidebar_state="expanded",
)

logger = logging.getLogger('gestione_fatture_notifiche')

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    from utils.ui_helpers import hide_sidebar_css

    hide_sidebar_css()


if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")
    st.stop()


user = st.session_state.user_data
user_id = user["id"]
current_ristorante = get_current_ristorante_id()

if not current_ristorante:
    st.error("⚠️ Nessun ristorante selezionato. Torna alla Dashboard per selezionarne uno.")
    st.stop()


check_page_enabled("gestione_documenti", user_id)

render_sidebar(user)
render_oh_yeah_header()

st.markdown("<div style='margin-top: 3rem;'></div>", unsafe_allow_html=True)
st.markdown(
    """
    <h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
        📋 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;">Notifiche e Gestione</span>
    </h2>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div style='margin-bottom: 0.5rem;'></div>", unsafe_allow_html=True)

# Sync cache locale con cache_version DB (invalidazione cross-processo).
current_doc_version = get_cache_version("fatture_documenti")
local_doc_version = st.session_state.get("gfn_documenti_cache_version", 0)
if current_doc_version != local_doc_version:
    clear_documenti_cache()
    st.session_state["gfn_documenti_cache_version"] = current_doc_version


# ============================================
# FUNZIONE RENDER AUTO INVOICE NOTICE (spostata da app.py Step 3)
# ============================================

def _render_auto_invoice_notice(auto_notice, user_id, dismissed_ids, supabase_client, ristorante_id):
    """Render della notifica fatture automatiche sotto il contesto ristorante."""
    if not auto_notice or st.session_state.get('auto_invoice_notice_dismissed', False):
        return

    files_detail = auto_notice.get('files_detail', []) or []
    pending_files = []
    for finfo in files_detail:
        notification_id = build_scoped_notification_id(
            f"auto-file:{finfo.get('file_name', '')}",
            ristorante_id,
        )
        if finfo.get('file_name') in st.session_state.auto_invoice_handled:
            continue
        if notification_id in dismissed_ids:
            continue
        pending_files.append(finfo)

    if not pending_files:
        return

    # Mantieni ordinamento cronologico di ricezione (piu recente prima).
    pending_files = sorted(
        pending_files,
        key=lambda x: str(x.get('created_at') or ''),
        reverse=True,
    )

    # Split chiaro per il cliente:
    # - nuove: ricevute dopo l'ultimo login
    # - in sospeso: backlog non ancora confermato
    nuove_count = int(auto_notice.get('new_count') or 0)
    totale_da_conferma = int(auto_notice.get('total_pending_count') or len(pending_files))
    in_sospeso_count = int(auto_notice.get('pending_count') or max(0, totale_da_conferma - nuove_count))

    if not st.session_state.get('auto_invoice_notice_toast_shown', False):
        fatture_label = 'fattura' if len(pending_files) == 1 else 'fatture'
        toast_message = f"Hai ricevuto {len(pending_files)} {fatture_label} automatiche"
        st.toast(f"📬 {toast_message}", icon="📥")
        st.session_state.auto_invoice_notice_toast_shown = True

    # expander_auto_invoices CSS ora in common.css

    with st.container(key="expander_auto_invoices"):
        fatture_label = 'fattura' if len(pending_files) == 1 else 'fatture'
        _hdr_col, _save_all_col = st.columns([5, 1])
        with _hdr_col:
            st.markdown(
                f"<span style='font-size:1.05rem; font-weight:700; color:#1e3a8a;'>"
                f"🔔 Sono arrivate {len(pending_files)} nuove {fatture_label} dall'ultimo tuo accesso"
                f"</span>",
                unsafe_allow_html=True,
            )
        with _save_all_col:
            if st.button("✅ Salva tutte", key="auto_notice_save_all", use_container_width=True, type="primary"):
                _ack_uid = st.session_state.user_data.get('id')
                _ack_event_ids = []
                for _f in pending_files:
                    _ack_event_ids.extend(_f.get('event_ids') or [])
                _ack_event_ids = list({eid for eid in _ack_event_ids if eid is not None})
                if _ack_uid and _ack_event_ids:
                    try:
                        supabase_client.table('upload_events') \
                            .update({'needs_ack': False}) \
                            .eq('user_id', _ack_uid) \
                            .in_('id', _ack_event_ids) \
                            .execute()
                    except Exception as _ack_err:
                        logger.error(f"Errore ack needs_ack Salva tutte: {_ack_err}")
                for f in pending_files:
                    st.session_state.auto_invoice_handled.add(f['file_name'])
                clear_fatture_cache()
                st.session_state.auto_invoice_notice_dismissed = True
                st.rerun()
        expander_title = (
            f"📄 Fatture | Nuove: {nuove_count} | "
            f"In sospeso da confermare: {in_sospeso_count} | "
            f"Totale da confermare: {totale_da_conferma}"
        )
        with st.expander(expander_title, expanded=False):
            for idx, finfo in enumerate(pending_files):
                fname = finfo.get('file_name', 'file sconosciuto')
                fornitore = finfo.get('fornitore', 'Sconosciuto')
                data_doc = finfo.get('data_documento', '')
                num_righe = finfo.get('num_righe', 0)
                totale = finfo.get('totale', 0)

                col_detail, col_btns = st.columns([6, 2])
                with col_detail:
                    _row_label = format_fattura_label(
                        file_name=fname,
                        fornitore=fornitore,
                        totale=totale,
                        num_righe=num_righe,
                        data=data_doc,
                        max_file_chars=28,
                    )
                    st.markdown(
                        f"{_row_label}",
                    )
                with col_btns:
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("💾 Salva", key=f"auto_save_{idx}", use_container_width=True):
                            _ack_uid = st.session_state.user_data.get('id')
                            _ack_event_ids = [eid for eid in (finfo.get('event_ids') or []) if eid is not None]
                            if _ack_uid:
                                try:
                                    if _ack_event_ids:
                                        supabase_client.table('upload_events') \
                                            .update({'needs_ack': False}) \
                                            .eq('user_id', _ack_uid) \
                                            .in_('id', _ack_event_ids) \
                                            .execute()
                                except Exception as _ack_err:
                                    logger.error(f"Errore ack needs_ack Salva {fname}: {_ack_err}")
                            st.session_state.auto_invoice_handled.add(fname)
                            clear_fatture_cache()
                            st.rerun()
                    with bc2:
                        if st.button("❌ Rifiuta", key=f"auto_reject_{idx}", use_container_width=True):
                            _ack_uid = st.session_state.user_data.get('id')
                            _ack_event_ids = [eid for eid in (finfo.get('event_ids') or []) if eid is not None]
                            if _ack_uid:
                                try:
                                    if _ack_event_ids:
                                        supabase_client.table('upload_events') \
                                            .update({'needs_ack': False}) \
                                            .eq('user_id', _ack_uid) \
                                            .in_('id', _ack_event_ids) \
                                            .execute()
                                except Exception as _ack_err:
                                    logger.error(f"Errore ack needs_ack Rifiuta {fname}: {_ack_err}")
                            try:
                                _reject_uid = st.session_state.user_data.get('id')
                                _reject_rid = st.session_state.get('ristorante_id')
                                elimina_fattura_completa(fname, _reject_uid, ristoranteid=_reject_rid, soft_delete=False)
                                invalida_cache_memoria()
                                clear_fatture_cache()
                            except Exception as _rej_err:
                                logger.error(f"Errore rifiuto fattura auto {fname}: {_rej_err}")
                            st.session_state.auto_invoice_handled.add(fname)
                            st.rerun()

# ============================================
# HELPER RENDERING ANTEPRIMA FATTURA
# ============================================

def render_anteprima_fattura(file_origine, docs_map, df_cache, fattura_sel, panel_key="gfn_preview_panel"):
    """
    Renderizza pannello preview di una fattura con header e tabella righe.
    
    Args:
        file_origine: chiave join (FileOrigine)
        docs_map: dict con metadati documento (fornitore, P.IVA, numero_documento, data, tipo, scadenza, pagata)
        df_cache: DataFrame con righe (Descrizione, Quantità, UM, PrezzoUnitario, IVA%, TotaleRiga, Categoria)
        fattura_sel: dict riga selezione (fallback campi base)
        panel_key: key Streamlit per container stabile
    """
    # Estrai metadati documento
    doc_info = docs_map.get(file_origine, {})

    # Filtra righe per file_origine per usare la prima riga come fallback
    try:
        righe_fattura = df_cache[df_cache['FileOrigine'] == file_origine].copy() if 'FileOrigine' in df_cache.columns else pd.DataFrame()
    except Exception:
        righe_fattura = pd.DataFrame()

    def _is_value_present(val):
        if val is None:
            return False
        if pd.isna(val):
            return False
        text = str(val).strip()
        return text not in {'', 'None', 'none', 'NaT', 'nan'}

    def get_field_with_fallback(doc_key, sel_key, df_col, default='—'):
        val = doc_info.get(doc_key)
        if _is_value_present(val):
            return html.escape(str(val).strip())

        val = fattura_sel.get(sel_key)
        if _is_value_present(val):
            return html.escape(str(val).strip())

        val = fattura_sel.get(doc_key)
        if _is_value_present(val):
            return html.escape(str(val).strip())

        if not righe_fattura.empty and df_col in righe_fattura.columns:
            val = righe_fattura.iloc[0].get(df_col)
            if _is_value_present(val):
                return html.escape(str(val).strip())

        return default

    fornitore = get_field_with_fallback('fornitore', 'Fornitore', 'Fornitore', 'Sconosciuto')
    piva = get_field_with_fallback('piva_fornitore', 'PIVAFornitore', 'PIVAFornitore', '—')
    # Fallback PIVA: estrai dal nome file (es. IT08605510968_xxx.xml → 08605510968)
    if piva == '—' and file_origine:
        import re as _re
        _m = _re.match(r'^IT(\d{11})_', str(file_origine))
        if _m:
            piva = _m.group(1)
    numero_doc = get_field_with_fallback('numero_documento', 'NumeroFattura', 'NumeroDocumento', '—')
    data_doc = get_field_with_fallback('data_documento', 'Data', 'DataDocumentoOriginale', '—')
    tipo_doc = get_field_with_fallback('tipo_documento', 'TipoDocumento', 'TipoDocumento', '—')
    scadenza = get_field_with_fallback('scadenza_effettiva', 'Scadenza', 'Scadenza', '—')
    pagata_bool = bool(doc_info.get('pagata', fattura_sel.get('Pagata', False)))
    pagata_badge = '✅ Pagata' if pagata_bool else '⚪ Non pagata'

    # Mapping colonne con fallback (nomi reali da db_service.py)
    col_desc = next((c for c in righe_fattura.columns if c.lower() in ['descrizione', 'description']), 'Descrizione')
    col_qta = next((c for c in righe_fattura.columns if c.lower() in ['quantita', 'quantità', 'qty', 'qta']), 'Quantita')
    col_um = next((c for c in righe_fattura.columns if c.lower() in ['unitamisura', 'um', 'unit']), 'UnitaMisura')
    col_prezzo = next((c for c in righe_fattura.columns if c.lower() in ['prezzounitario', 'prezzo_unitario', 'unitprice']), 'PrezzoUnitario')
    col_iva = next((c for c in righe_fattura.columns if c.lower() in ['ivapercentuale', 'iva_percentuale', 'iva', 'iva%', 'aliquotaiva']), 'IVAPercentuale')
    col_totale = next((c for c in righe_fattura.columns if c.lower() in ['totaleriga', 'totale_riga', 'total', 'importo']), 'TotaleRiga')
    
    # Normalizza numeri e handle null
    def safe_float(val):
        try:
            f = float(val) if pd.notna(val) else 0.0
            return f
        except (ValueError, TypeError):
            return 0.0
    
    def fmt_eur(val):
        f = safe_float(val)
        return f"€ {f:,.2f}"
    
    def fmt_pct(val):
        f = safe_float(val)
        return f"{f:.1f}%"
    
    num_righe = len(righe_fattura)
    totale_righe = righe_fattura[col_totale].apply(safe_float).sum() if not righe_fattura.empty and col_totale in righe_fattura.columns else 0.0
    
    # Costruisci tabella righe HTML
    righe_html = ""
    if not righe_fattura.empty:
        for idx, row in righe_fattura.iterrows():
            desc = html.escape(str(row.get(col_desc, '—')).strip()[:100] or '—')
            qta = safe_float(row.get(col_qta))
            um = html.escape(str(row.get(col_um, '—')).strip()[:10] or '—')
            prezzo = safe_float(row.get(col_prezzo))
            iva = safe_float(row.get(col_iva))
            tot = safe_float(row.get(col_totale))
            
            righe_html += f"""
            <tr>
                <td>{desc}</td>
                <td style="text-align: center;">{qta:.2f}</td>
                <td style="text-align: center;">{um}</td>
                <td style="text-align: right;">€ {prezzo:.2f}</td>
                <td style="text-align: center;">{iva:.1f}%</td>
                <td style="text-align: right; font-weight: 600;">€ {tot:.2f}</td>
            </tr>
            """
    else:
        righe_html = """
        <tr>
            <td colspan="6" style="text-align: center; color: #9ca3af; font-style: italic;">
                Nessuna riga strutturata disponibile
            </td>
        </tr>
        """
    
    # CSS e HTML completo (CSS inline: st.components.v1.html usa iframe isolato, common.css non vi entra)
    html_content = f"""
    <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
    .gfn-preview-wrap {{ margin-top: 14px; margin-bottom: 16px; }}
    .gfn-preview-doc-card {{
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        border: 1px solid #bfdbfe;
        border-left: 5px solid #1e40af;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(30,64,175,0.10);
        padding: 16px;
    }}
    .gfn-preview-doc-header {{
        display: grid;
        grid-template-columns: 1.3fr 1fr;
        gap: 12px;
        background: #eff6ff;
        border: 1px solid #dbeafe;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 12px;
    }}
    .gfn-preview-doc-header .label {{ color: #1e3a8a; font-weight: 600; font-size: 0.85rem; }}
    .gfn-preview-doc-header .value {{ color: #111827; font-weight: 700; font-size: 1.02rem; }}
    .gfn-preview-doc-header .sub {{ color: #475569; font-size: 0.88rem; }}
    .gfn-preview-doc-header-row {{ line-height: 1.6; }}
    .gfn-preview-table-wrap {{
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #dbeafe;
        border-radius: 10px;
        margin-bottom: 10px;
    }}
    .gfn-preview-table {{ width: 100%; border-collapse: collapse; font-size: 0.90rem; }}
    .gfn-preview-table thead th {{
        position: sticky; top: 0;
        background: #dbeafe; color: #1e3a8a; font-weight: 700;
        border-bottom: 1px solid #93c5fd;
        padding: 8px 10px; text-align: left;
    }}
    .gfn-preview-table tbody td {{
        border-bottom: 1px solid #eef2ff;
        padding: 7px 10px; color: #111827; vertical-align: top;
    }}
    .gfn-preview-footer {{
        display: flex; justify-content: space-between;
        padding-top: 8px; border-top: 1px dashed #93c5fd;
        color: #1e3a8a; font-weight: 700; font-size: 0.95rem;
    }}
    @media (max-width: 900px) {{
        .gfn-preview-doc-header {{ grid-template-columns: 1fr; }}
        .gfn-preview-table {{ font-size: 0.82rem; }}
    }}
    </style>
    <div class="gfn-preview-wrap">
        <div class="gfn-preview-doc-card">
            <div class="gfn-preview-doc-header">
                <div>
                    <div class="label">📦 Fornitore</div>
                    <div class="value">{fornitore}</div>
                    <div class="sub">P.IVA: {piva}</div>
                </div>
                <div class="gfn-preview-doc-header-row">
                    <div><span class="label">N° Documento:</span> <strong>{numero_doc}</strong></div>
                    <div><span class="label">Data:</span> <strong>{data_doc}</strong></div>
                    <div><span class="label">Tipo:</span> <strong>{tipo_doc}</strong></div>
                    <div><span class="label">Scadenza:</span> <strong>{scadenza}</strong></div>
                    <div><span class="label">Stato:</span> <strong style="color: {'#166534' if pagata_bool else '#dc2626'};">{pagata_badge}</strong></div>
                </div>
            </div>
            
            <div class="gfn-preview-table-wrap">
                <table class="gfn-preview-table">
                    <thead>
                        <tr>
                            <th>Descrizione</th>
                            <th>Qta</th>
                            <th>UM</th>
                            <th style="text-align: right;">Prezzo Unit.</th>
                            <th>IVA%</th>
                            <th style="text-align: right;">Totale Riga</th>
                        </tr>
                    </thead>
                    <tbody>
                        {righe_html}
                    </tbody>
                </table>
            </div>
            
            <div class="gfn-preview-footer">
                <div>📋 Righe: {num_righe}</div>
                <div>Totale: {fmt_eur(totale_righe)}</div>
            </div>
        </div>
    </div>
    """
    
    return html_content

# ============================================

# ============================================
# NAVIGAZIONE TAB
# ============================================
# Fallback: normalizza valori non riconosciuti
if st.session_state.get('gfn_tab_attivo') not in ('gestione', 'scadenziario', 'notifiche'):
    st.session_state.gfn_tab_attivo = 'notifiche'

# Reset gfn_notif_* e gfn_briefing_snapshot::* quando cambia ristorante
_gfn_last_rist = st.session_state.get('_gfn_last_ristorante_id')
if _gfn_last_rist != current_ristorante:
    st.session_state['_gfn_last_ristorante_id'] = current_ristorante
    for _k in list(st.session_state.keys()):
        if str(_k).startswith('gfn_notif_') or str(_k).startswith('gfn_briefing_snapshot::'):
            st.session_state.pop(_k, None)

# Badge count notifiche (calcolato prima del render tab per aggiornamento immediato)
# Se il tab notifiche e' attivo, prefetch della lista completa per evitare doppio fetch badge+lista.
_supabase_badge = get_supabase_client()
_legacy_cleanup_key = f"gfn_inbox_cleanup_done::{user_id}::{current_ristorante}"
if not st.session_state.get(_legacy_cleanup_key):
    dismiss_inbox_topics(
        user_id=user_id,
        ristorante_id=current_ristorante,
        topic_keys=['fornitore_unico_categoria'],
        supabase_client=_supabase_badge,
    )
    st.session_state[_legacy_cleanup_key] = True
_prefetched_notifs = None
gfn_col1, gfn_col2, gfn_col3 = st.columns(3)
st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

if st.session_state.get('gfn_tab_attivo') == 'notifiche':
    _prefetched_notifs = get_inbox_notifications(
        user_id=user_id,
        ristorante_id=current_ristorante,
        supabase_client=_supabase_badge,
        source_type=None,
    )
    _notif_badge_count = len(_prefetched_notifs)
else:
    _notif_badge_count = get_inbox_badge_count(user_id, current_ristorante, _supabase_badge)
_notif_badge_label = "🔔 NOTIFICHE" + (f" ({_notif_badge_count})" if _notif_badge_count > 0 else "")

gfn_col1, gfn_col2, gfn_col3 = st.columns(3)

with gfn_col1:
    if st.button(_notif_badge_label, key="gfn_btn_notifiche", use_container_width=True,
                 type="primary" if st.session_state.gfn_tab_attivo == "notifiche" else "secondary"):
        if st.session_state.gfn_tab_attivo != "notifiche":
            st.session_state.gfn_tab_attivo = "notifiche"
            st.rerun()

with gfn_col2:
    if st.button("🗂️ GESTIONE\nFATTURE", key="gfn_btn_gestione", use_container_width=True,
                 type="primary" if st.session_state.gfn_tab_attivo == "gestione" else "secondary"):
        if st.session_state.gfn_tab_attivo != "gestione":
            st.session_state.gfn_tab_attivo = "gestione"
            st.rerun()

with gfn_col3:
    if st.button("📅 SCADENZIARIO", key="gfn_btn_scadenziario", use_container_width=True,
                 type="primary" if st.session_state.gfn_tab_attivo == "scadenziario" else "secondary"):
        if st.session_state.gfn_tab_attivo != "scadenziario":
            st.session_state.gfn_tab_attivo = "scadenziario"
            st.rerun()

# CSS bottoni tab (caricati da file statico condiviso)
from utils.ui_helpers import load_all_css
load_all_css()

st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

@st.fragment
def _render_scadenziario_tab(user_id, current_ristorante):
        # Carica TUTTI i documenti (nessun filtro stato) per il report mensile completo
        with st.spinner("⏳ Caricamento scadenziario..."):
            tutti_documenti = get_documenti_list(
                user_id=user_id,
                ristorante_id=current_ristorante,
                filtro="tutte",
                giorni_imminenti=365,
        )

        if not tutti_documenti:
            st.info("Nessun documento disponibile.")
        else:
            df_all = pd.DataFrame(tutti_documenti)
            df_all["scadenza_ts"] = pd.to_datetime(df_all["scadenza_effettiva"], errors="coerce")
            df_all["totale_documento"] = pd.to_numeric(df_all["totale_documento"], errors="coerce").fillna(0.0)
            df_all["pagata"] = df_all["pagata"].fillna(False).astype(bool)
            today = pd.Timestamp(date.today())

            # ── Filtro periodo ─────────────────────────────────────────────────
            from utils.period_helper import get_mesi_disponibili_fatture as _get_mesi_scad
            from services import get_supabase_client as _get_sb_scad
            _sb_scad = _get_sb_scad()
            _mesi_scad = _get_mesi_scad(user_id, current_ristorante, _sb_scad)
            _anni_scad = sorted(list({a for a, _, _ in _mesi_scad}), reverse=True) or [today.year]
            _opzioni_tutto_anno = [f"🗓️ Tutto il {a}" for a in _anni_scad]
            _opzioni_mesi_scad = [lbl for _, _, lbl in reversed(_mesi_scad)]
            _opzioni_periodo_scad = _opzioni_tutto_anno + _opzioni_mesi_scad
            if not _opzioni_periodo_scad:
                _opzioni_periodo_scad = [f"🗓️ Tutto il {today.year}"]
            _default_scad_key = f"🗓️ Tutto il {today.year}"
            _default_scad_idx = _opzioni_periodo_scad.index(_default_scad_key) if _default_scad_key in _opzioni_periodo_scad else 0

            _sc_col1, _sc_col2 = st.columns([1.5, 1.5])
            with _sc_col1:
                _periodo_scad = st.selectbox(
                    "📅 Periodo Scadenziario",
                    options=_opzioni_periodo_scad,
                    index=_default_scad_idx,
                    key="scad_periodo_sel",
                )
            with _sc_col2:
                _fornitori_opzioni = ["🏢 Tutti i fornitori"] + sorted(
                    df_all["fornitore"].dropna().astype(str).unique().tolist()
                )
                _filtro_fornitore = st.selectbox(
                    "🏢 Fornitore",
                    options=_fornitori_opzioni,
                    key="scad_filtro_fornitore",
                )

            # Risolvi periodo selezionato
            if _periodo_scad.startswith("🗓️ Tutto il "):
                _anno_sel = int(_periodo_scad.replace("🗓️ Tutto il ", ""))
                _df_filtrato = df_all[df_all["scadenza_ts"].dt.year == _anno_sel].copy()
            else:
                _match_mese_scad = next(((a, m) for a, m, lbl in _mesi_scad if lbl == _periodo_scad), None)
                if _match_mese_scad:
                    _anno_sel, _mese_num_sel = _match_mese_scad
                    _df_filtrato = df_all[
                        (df_all["scadenza_ts"].dt.year == _anno_sel) &
                        (df_all["scadenza_ts"].dt.month == _mese_num_sel)
                    ].copy()
                else:
                    _anno_sel = today.year
                    _df_filtrato = df_all[df_all["scadenza_ts"].dt.year == _anno_sel].copy()

            # ── KPI globali ────────────────────────────────────────────────────
            _df_anno_no_scad = df_all[df_all["scadenza_ts"].isna()].copy()

            # Applica filtro fornitore
            if _filtro_fornitore != "🏢 Tutti i fornitori":
                _df_filtrato = _df_filtrato[_df_filtrato["fornitore"] == _filtro_fornitore]
                _df_anno_no_scad = _df_anno_no_scad[_df_anno_no_scad["fornitore"] == _filtro_fornitore]

            _tot_anno = _df_filtrato["totale_documento"].sum()
            _tot_pagato = _df_filtrato[_df_filtrato["pagata"]]["totale_documento"].sum()
            _tot_residuo = _df_filtrato[~_df_filtrato["pagata"]]["totale_documento"].sum()
            _tot_scaduto = _df_filtrato[
                (~_df_filtrato["pagata"]) & (_df_filtrato["scadenza_ts"].dt.normalize() < today)
            ]["totale_documento"].sum()

            st.markdown("<div style='margin-top:1.8rem;'></div>", unsafe_allow_html=True)
            _kc1, _kc2, _kc3, _kc4 = st.columns(4)

            def _scad_kpi_html(label, value, color="#1e40af"):
                return f"""<div style="
                    background: linear-gradient(135deg, rgba(248,249,250,0.95), rgba(233,236,239,0.95));
                    padding: 1.1rem 1rem;
                    border-radius: 12px;
                    border: 1px solid rgba(206,212,218,0.5);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.05);
                    text-align: center;
                    min-height: 100px;
                    display: flex; flex-direction: column;
                    justify-content: center; align-items: center;
                ">
                    <div style="color:#2563eb; font-weight:700; font-size:0.92rem; margin-bottom:6px; line-height:1.3;">{label}</div>
                    <div style="color:{color}; font-size:1.78rem; font-weight:800;">{value}</div>
                </div>"""

            with _kc1:
                st.markdown(_scad_kpi_html("📋 Totale periodo", f"€ {_tot_anno:,.0f}"), unsafe_allow_html=True)
            with _kc2:
                st.markdown(_scad_kpi_html("✅ Pagato", f"€ {_tot_pagato:,.0f}", color="#166534"), unsafe_allow_html=True)
            with _kc3:
                st.markdown(_scad_kpi_html("💸 Da pagare", f"€ {_tot_residuo:,.0f}", color="#b45309"), unsafe_allow_html=True)
            with _kc4:
                st.markdown(_scad_kpi_html("🔴 Scaduto", f"€ {_tot_scaduto:,.0f}", color="#dc2626"), unsafe_allow_html=True)

            st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)

            # ── Report mensile ─────────────────────────────────────────────────
            _det_col_h, _det_col_lbl, _det_col_f = st.columns([3, 0.7, 1.3])
            with _det_col_h:
                st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📊 Dettaglio Mensile</h3>", unsafe_allow_html=True)
            with _det_col_lbl:
                st.markdown("<div style='text-align:right; padding-top:0.65rem; color:#374151; font-size:0.88rem; font-weight:600;'>Filtra per stato:</div>", unsafe_allow_html=True)
            with _det_col_f:
                _filtro_stato = st.selectbox(
                    "💳 Stato Fatture",
                    options=["⏳ Da pagare", "🔴 Scadute", "✅ Pagate", "📋 Tutte"],
                    index=0,
                    key="scad_filtro_stato",
                    label_visibility="collapsed",
                )

            if _filtro_stato == "⏳ Da pagare":
                _df_report = _df_filtrato[~_df_filtrato["pagata"]]
            elif _filtro_stato == "🔴 Scadute":
                _df_report = _df_filtrato[
                    (~_df_filtrato["pagata"]) &
                    (_df_filtrato["scadenza_ts"].notna()) &
                    (_df_filtrato["scadenza_ts"] < pd.Timestamp(today))
                ]
            elif _filtro_stato == "✅ Pagate":
                _df_report = _df_filtrato[_df_filtrato["pagata"]]
            else:
                _df_report = _df_filtrato
            _df_report = _df_report[_df_report["scadenza_ts"].notna()].copy()
            _df_report["_mese"] = _df_report["scadenza_ts"].dt.month

            for _mese_num in range(1, 13):
                _df_m = _df_report[_df_report["_mese"] == _mese_num]
                if _df_m.empty:
                    continue
                _mese_label = MESI_ITA.get(_mese_num, str(_mese_num))
                _tot_m = _df_m["totale_documento"].sum()
                _pag_m = _df_m[_df_m["pagata"]]["totale_documento"].sum()
                _res_m = _df_m[~_df_m["pagata"]]["totale_documento"].sum()
                _n_m = len(_df_m)

                # Colore intestazione mese: rosso se scaduto, arancio se mese corrente, azzurro altrimenti
                _mese_ts = pd.Timestamp(year=int(_anno_sel), month=_mese_num, day=1)
                _fine_mese = (_mese_ts + pd.offsets.MonthEnd(0)).normalize()
                if _fine_mese < today:
                    _hdr_color = "#fef2f2"; _border_color = "#fca5a5"; _txt_color = "#991b1b"
                elif _mese_ts.month == today.month and _mese_ts.year == today.year:
                    _hdr_color = "#fefce8"; _border_color = "#fde047"; _txt_color = "#854d0e"
                else:
                    _hdr_color = "#eff6ff"; _border_color = "#93c5fd"; _txt_color = "#1e3a8a"

                with st.expander(
                    f"📅 **{_mese_label} {_anno_sel}** — 📋 {_n_m} fatture  |  "
                    f"⏳ Da pagare: **€ {_res_m:,.0f}**  |  ✅ Pagato: **€ {_pag_m:,.0f}**",
                    expanded=(today.month == _mese_num and today.year == int(_anno_sel)),
                ):
                    # Tabella dettaglio fatture del mese
                    _cols_show = ["fornitore", "data_documento", "scadenza_effettiva", "totale_documento", "pagata", "numero_documento"]
                    _cols_avail = [c for c in _cols_show if c in _df_m.columns]
                    _df_det = _df_m[_cols_avail].copy()

                    _rename_map = {
                        "fornitore": "Fornitore",
                        "data_documento": "Data Fattura",
                        "scadenza_effettiva": "Scadenza",
                        "totale_documento": "Totale (€)",
                        "pagata": "Pagata",
                        "numero_documento": "N° Fattura",
                    }
                    _df_det = _df_det.rename(columns={k: v for k, v in _rename_map.items() if k in _df_det.columns})
                    _df_det = _df_det.sort_values("Scadenza", ascending=True, na_position="last")
                    if "Pagata" in _df_det.columns:
                        _pagata_series = _df_m["pagata"].fillna(False).astype(bool)
                        _icons = pd.Series("⚪", index=_df_m.index)
                        _icons[_pagata_series] = "🟢"
                        if "scadenza_ts" in _df_m.columns:
                            _scadute_mask = (
                                (~_pagata_series)
                                & _df_m["scadenza_ts"].notna()
                                & (_df_m["scadenza_ts"] < pd.Timestamp(today))
                            )
                            _icons[_scadute_mask] = "🔴"
                        _df_det["Pagata"] = _icons.reindex(_df_det.index).fillna("⚪")
                    if "Totale (€)" in _df_det.columns:
                        _df_det["Totale (€)"] = _df_det["Totale (€)"].apply(lambda x: f"€ {x:,.2f}")

                    _cc_det = {c: st.column_config.TextColumn(c) for c in _df_det.select_dtypes(include="object").columns}
                    st.dataframe(_df_det, use_container_width=True, hide_index=True, column_config=_cc_det)

            # ── Senza scadenza ─────────────────────────────────────────────────
            if _filtro_stato == "⏳ Da pagare":
                _df_no_scad_report = _df_anno_no_scad[~_df_anno_no_scad["pagata"]]
            elif _filtro_stato == "🔴 Scadute":
                _df_no_scad_report = pd.DataFrame()  # senza scadenza non possono essere scadute
            elif _filtro_stato == "✅ Pagate":
                _df_no_scad_report = _df_anno_no_scad[_df_anno_no_scad["pagata"]]
            else:
                _df_no_scad_report = _df_anno_no_scad
            if not _df_no_scad_report.empty:
                _tot_no_scad = _df_no_scad_report["totale_documento"].sum()
                with st.expander(
                    f"⚪ **Senza scadenza** — {len(_df_no_scad_report)} fatture | Totale: **€ {_tot_no_scad:,.0f}**",
                    expanded=False,
                ):
                    _cols_ns = ["fornitore", "data_documento", "totale_documento", "pagata", "numero_documento"]
                    _cols_ns_avail = [c for c in _cols_ns if c in _df_no_scad_report.columns]
                    _df_ns = _df_no_scad_report[_cols_ns_avail].rename(columns={
                        "fornitore": "Fornitore",
                        "data_documento": "Data Documento",
                        "totale_documento": "Totale (€)",
                        "pagata": "Pagata",
                        "numero_documento": "N° Fattura",
                    }).copy()
                    if "Pagata" in _df_ns.columns:
                        _df_ns["Pagata"] = _df_ns["Pagata"].apply(lambda x: "🟢" if x else "⚪")
                    if "Totale (€)" in _df_ns.columns:
                        _df_ns["Totale (€)"] = _df_ns["Totale (€)"].apply(lambda x: f"€ {x:,.2f}")
                    _cc_ns = {c: st.column_config.TextColumn(c) for c in _df_ns.select_dtypes(include="object").columns}
                    st.dataframe(_df_ns, use_container_width=True, hide_index=True, column_config=_cc_ns)
                    st.caption("💡 Queste fatture non hanno una scadenza assegnata. Configurala dal tab Avvisi → Regole Pagamento oppure modifica la singola fattura.")

            # ── Scadenze imminenti (prossimi 30 giorni) ────────────────────────
            st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
            st.markdown("<h3 style='color:#1e40af; font-weight:700;'>⏰ Documenti in Scadenza (Prossimi 30 giorni)</h3>", unsafe_allow_html=True)

            _scad_imminenti = get_documenti_list(
                user_id=user_id,
                ristorante_id=current_ristorante,
                filtro="imminenti",
                giorni_imminenti=30,
            )
            _scad_non_pagate = [d for d in _scad_imminenti if not d.get("pagata")]
            if _filtro_fornitore != "🏢 Tutti i fornitori":
                _scad_non_pagate = [d for d in _scad_non_pagate if d.get("fornitore") == _filtro_fornitore]

            if not _scad_non_pagate:
                st.info("✅ Nessun documento in scadenza nei prossimi 30 giorni.")
            else:
                _cards_html = ""
                for _doc in sorted(_scad_non_pagate, key=lambda x: x.get("scadenza_effettiva") or ""):
                    # XSS-safe: escape valori derivati dai dati fattura prima di interpolarli nell'HTML
                    _scad_str = html.escape(str(_doc.get("scadenza_effettiva") or "N/A"))
                    _forn = html.escape(str(_doc.get("fornitore") or "Sconosciuto"))
                    _tot = _doc.get("totale_documento") or 0
                    _src = html.escape(str(_doc.get("scadenza_source") or "none"))
                    try:
                        _scad_dt = pd.to_datetime(_scad_str, errors="coerce")
                        if pd.notna(_scad_dt):
                            _gg_rim = (_scad_dt.date() - today.date()).days
                            if _gg_rim <= 0:
                                _badge_bg = "#fee2e2"; _badge_color = "#991b1b"; _border = "#fca5a5"; _urgenza = "🔴 Scaduto"
                            elif _gg_rim <= 7:
                                _badge_bg = "#fef3c7"; _badge_color = "#92400e"; _border = "#fcd34d"; _urgenza = f"🔴 {_gg_rim}gg"
                            else:
                                _badge_bg = "#fefce8"; _badge_color = "#854d0e"; _border = "#fde047"; _urgenza = f"🟡 {_gg_rim}gg"
                        else:
                            _badge_bg = "#f3f4f6"; _badge_color = "#6b7280"; _border = "#d1d5db"; _urgenza = "⚪ N/D"
                    except Exception:
                        _badge_bg = "#f3f4f6"; _badge_color = "#6b7280"; _border = "#d1d5db"; _urgenza = "⚪"
                    _cards_html += f"""
                    <div style="display:flex; align-items:center; gap:1rem;
                        background:white; border:1px solid {_border};
                        border-left:4px solid {_badge_color};
                        border-radius:10px; padding:0.75rem 1.1rem;
                        margin-bottom:0.55rem;
                        box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="background:{_badge_bg}; color:{_badge_color}; font-weight:700;
                            font-size:0.90rem; border-radius:6px; padding:0.25rem 0.6rem; white-space:nowrap;">{_urgenza}</div>
                        <div style="flex:1; font-weight:700; color:#111827; font-size:1.05rem;">{_forn}</div>
                        <div style="font-size:1.12rem; font-weight:800; color:#1e40af; white-space:nowrap;">€ {_tot:,.2f}</div>
                        <div style="color:#6b7280; font-size:0.90rem; white-space:nowrap;">📅 {_scad_str} <span style='color:#9ca3af;'>({_src})</span></div>
                    </div>"""
                st.markdown(
                    f'<div style="max-height:400px; overflow-y:auto; padding-right:6px;">{_cards_html}</div>',
                    unsafe_allow_html=True,
                )

            # ── Regole scadenza fornitori ───────────────────────────────────────────
            from services.documenti_service import (
                get_fornitori_pagamenti_config,
                upsert_fornitori_pagamenti_config,
                delete_fornitori_pagamenti_config,
                clear_fornitori_cache,
            )
            import time

            # Opzioni modalità pagamento
            _OPZIONI_SCADENZA_LABELS = [
                "⚡ Automatico/RID — già pagato",
                "30 giorni dalla data fattura",
                "60 giorni dalla data fattura",
                "90 giorni dalla data fattura",
                "Fine mese successivo",
                "Fine del 2° mese successivo",
                "Fine del 3° mese successivo",
            ]
            _OPZIONI_SCADENZA_VALORI = ["rid", "30gg", "60gg", "90gg", "30gg_fm", "60gg_fm", "90gg_fm"]
            _LABEL_DA_MODALITA = dict(zip(_OPZIONI_SCADENZA_VALORI, _OPZIONI_SCADENZA_LABELS))

            st.markdown("<div style='margin-top:2.5rem;'></div>", unsafe_allow_html=True)
            st.markdown("<h3 style='color:#1e40af; font-weight:700;'>⚙️ Regole Scadenza Fornitori</h3>", unsafe_allow_html=True)
            st.markdown(
                "<div style='background:#fefce8; border:1px solid #fde047; border-radius:8px; "
                "padding:0.55rem 0.9rem; font-size:0.87rem; color:#78350f; margin-bottom:1rem;'>"
                "💡 Seleziona un fornitore e scegli la modalità di pagamento. "
                "La scadenza verrà calcolata automaticamente in base alla regola impostata.</div>",
                unsafe_allow_html=True,
            )

            _regole = get_fornitori_pagamenti_config(user_id, current_ristorante)

            # Carica fornitori distinti dal DB
            @st.cache_data(ttl=120, show_spinner=False)
            def _get_fornitori_distinti(uid, rid):
                try:
                    _sb = get_supabase_client()
                    _res = (
                        filter_active(
                            _sb.table("fatture_documenti")
                            .select("fornitore,piva_fornitore")
                            .eq("user_id", uid)
                            .eq("ristorante_id", rid)
                        )
                        .execute()
                    )
                    _seen = {}
                    for _r in (_res.data or []):
                        _piva = (_r.get("piva_fornitore") or "").strip()
                        _nome = (_r.get("fornitore") or "").strip()
                        if _piva and _piva not in _seen:
                            _seen[_piva] = _nome or _piva
                    return sorted(_seen.items(), key=lambda x: x[1])
                except Exception:
                    return []

            _fornitori_lista = _get_fornitori_distinti(user_id, current_ristorante)
            # Rimuovi fornitori già con regola
            _pive_con_regola = {_rg.get("piva_fornitore", "") for _rg in _regole}

            # Tabella regole esistenti
            if _regole:
                _rh1, _rh2, _rh3, _rh4 = st.columns([4, 1.5, 0.6, 0.6])
                _rh1.markdown("**Fornitore**")
                _rh2.markdown("**Modalità pagamento**")
                _rh3.markdown("")
                _rh4.markdown("")
                for _rg in _regole:
                    _rg_id = _rg.get("id")
                    _edit_key = f"scad_editing_{_rg_id}"
                    _rc1, _rc2, _rc3, _rc4 = st.columns([4, 1.5, 0.6, 0.6])
                    _piva_rg = _rg.get("piva_fornitore") or "?"
                    _nome_rg = next((n for p, n in _fornitori_lista if p == _piva_rg), _piva_rg)
                    if _nome_rg != _piva_rg:
                        _rc1.markdown(f"**{_nome_rg}**<br><span style='color:#9ca3af;font-size:0.78rem;'>{_piva_rg}</span>", unsafe_allow_html=True)
                    else:
                        _rc1.markdown(_piva_rg)

                    if st.session_state.get(_edit_key):
                        # Modalità modifica
                        with _rc2:
                            _modalita_corrente = str(_rg.get("modalita") or "30gg").strip().lower()
                            _idx_default = _OPZIONI_SCADENZA_VALORI.index(_modalita_corrente) if _modalita_corrente in _OPZIONI_SCADENZA_VALORI else 1
                            _sel_edit = st.selectbox(
                                "Modalità",
                                options=_OPZIONI_SCADENZA_VALORI,
                                format_func=lambda v: _LABEL_DA_MODALITA.get(v, v),
                                index=_idx_default,
                                key=f"scad_modalita_edit_{_rg_id}",
                                label_visibility="collapsed",
                            )
                        with _rc3:
                            if st.button("✅", key=f"scad_save_edit_{_rg_id}", use_container_width=True, help="Salva"):
                                try:
                                    upsert_fornitori_pagamenti_config(
                                        user_id=user_id,
                                        ristorante_id=current_ristorante,
                                        piva_fornitore=_piva_rg,
                                        modalita=_sel_edit,
                                        attiva=True,
                                    )
                                    clear_fornitori_cache()
                                    clear_documenti_cache()
                                    st.session_state.pop(_edit_key, None)
                                    st.rerun()
                                except Exception as _e:
                                    st.error(str(_e))
                        with _rc4:
                            if st.button("❌", key=f"scad_cancel_edit_{_rg_id}", use_container_width=True, help="Annulla"):
                                st.session_state.pop(_edit_key, None)
                                st.rerun()
                    else:
                        # Visualizzazione normale
                        _modalita_disp = str(_rg.get("modalita") or "").strip().lower()
                        _rc2.write(_LABEL_DA_MODALITA.get(_modalita_disp, f"{_rg.get('giorni_pagamento', '?')} gg"))
                        with _rc3:
                            if st.button("✏️", key=f"scad_edit_reg_{_rg_id}", use_container_width=True, help="Modifica"):
                                st.session_state[_edit_key] = True
                                st.rerun()
                        with _rc4:
                            if st.button("🗑️", key=f"scad_del_reg_{_rg_id}", use_container_width=True, help="Elimina"):
                                try:
                                    delete_fornitori_pagamenti_config(user_id, current_ristorante, _rg_id)
                                    clear_fornitori_cache()
                                    clear_documenti_cache()
                                    st.rerun()
                                except Exception as _e:
                                    st.error(str(_e))
            else:
                st.info("Nessuna regola configurata.")

            # Form aggiunta
            _fornitori_disponibili = [(p, n) for p, n in _fornitori_lista if p not in _pive_con_regola]
            st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
            with st.expander("➕ Aggiungi regola", expanded=False):
                if not _fornitori_disponibili:
                    st.info("Tutti i fornitori presenti hanno già una regola configurata.")
                else:
                    _fa, _fb, _fc = st.columns([3, 1.5, 1.2])
                    with _fa:
                        _fornitore_sel = st.selectbox(
                            "Fornitore",
                            options=[p for p, n in _fornitori_disponibili],
                            format_func=lambda p: next((f"{n} ({p})" for pp, n in _fornitori_disponibili if pp == p), p),
                            key="scad_reg_fornitore",
                        )
                    with _fb:
                        _new_modalita = st.selectbox(
                            "Modalità pagamento",
                            options=_OPZIONI_SCADENZA_VALORI,
                            format_func=lambda v: _LABEL_DA_MODALITA.get(v, v),
                            index=1,
                            key="scad_reg_modalita",
                        )
                    with _fc:
                        st.markdown("<div style='margin-top:1.6rem;'></div>", unsafe_allow_html=True)
                        if st.button("✅ Salva", type="primary", use_container_width=True, key="scad_reg_save"):
                            try:
                                _result = upsert_fornitori_pagamenti_config(
                                    user_id=user_id,
                                    ristorante_id=current_ristorante,
                                    piva_fornitore=_fornitore_sel,
                                    modalita=_new_modalita,
                                    attiva=True,
                                )
                                if _result.get("ok"):
                                    clear_fornitori_cache()
                                    clear_documenti_cache()
                                    st.toast("✅ Regola salvata", icon="✅")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Errore salvataggio: {_result.get('error', 'errore sconosciuto')}")
                            except Exception as _e:
                                st.error(str(_e))



if st.session_state.gfn_tab_attivo == "scadenziario":
    _render_scadenziario_tab(user_id, current_ristorante)

elif st.session_state.gfn_tab_attivo == "gestione":
    # ============================================================
    # 🗂️ GESTIONE FATTURE (clone identica dell'expander originale di app.py)
    # ============================================================
    supabase = get_supabase_client()

    with st.spinner("⏳ Caricamento fatture..."):
        df_cache = carica_e_prepara_dataframe(
            user_id,
            force_refresh=False,
            ristorante_id=current_ristorante,
        )

    def _norm_file_key(value):
        return str(value or "").strip().lower()

    # Mappa file → metadati documento/pagata per mostrare stato pagamento sui bottoni
    try:
        _docs_pagata = get_documenti_list(
            user_id=user_id,
            ristorante_id=current_ristorante,
            filtro="tutte",
            giorni_imminenti=0,
        )
        _docs_map = {
            str(d.get('file_origine', '')).strip(): d
            for d in (_docs_pagata or [])
            if str(d.get('file_origine', '')).strip()
        }
        _docs_map_norm = {
            _norm_file_key(d.get('file_origine')): d
            for d in (_docs_pagata or [])
            if _norm_file_key(d.get('file_origine'))
        }
        _pagata_map = {k: bool(v.get('pagata', False)) for k, v in _docs_map_norm.items()}
    except Exception:
        _docs_pagata = []
        _docs_map = {}
        _docs_map_norm = {}
        _pagata_map = {}

    fatture_cestino_cache = []
    try:
        fatture_cestino_cache = get_fatture_cestino(
            user_id,
            ristorante_id=current_ristorante,
        )
    except Exception as e:
        logger.error(f"Errore caricamento cestino fatture: {e}")
        fatture_cestino_cache = []

    if df_cache.empty and not fatture_cestino_cache:
        st.info("🔭 Nessuna fattura caricata. Carica documenti dalla pagina principale per iniziare.")
    else:
        with st.container():

            # ========================================
            # BOX STATISTICHE
            # ========================================
            try:
                stats_db = get_fatture_stats(user_id, current_ristorante)
            except Exception as e:
                logger.error(f"Errore get_fatture_stats: {e}")
                st.error("❌ Errore caricamento statistiche")
                stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}

            num_fatture_xml_p7m = 0
            num_altri_documenti = 0
            num_righe_attive = len(df_cache)
            estensioni_fatture = {'.xml', '.p7m'}
            if 'FileOrigine' in df_cache.columns:
                file_unici = {
                    str(file_name).strip()
                    for file_name in df_cache['FileOrigine'].dropna().unique().tolist()
                    if str(file_name).strip()
                }
                num_fatture_xml_p7m = sum(
                    1 for file_name in file_unici
                    if os.path.splitext(file_name)[1].lower() in estensioni_fatture
                )
                num_altri_documenti = len(file_unici) - num_fatture_xml_p7m

            # Conta note di credito (TD04) dai file unici in df_cache
            num_note_credito = 0
            if 'TipoDocumento' in df_cache.columns and 'FileOrigine' in df_cache.columns:
                num_note_credito = df_cache[df_cache['TipoDocumento'].str.upper().str.strip() == 'TD04']['FileOrigine'].nunique()
            note_credito_html = f' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #1e40af;">{num_note_credito:,}</strong>' if num_note_credito > 0 else ' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #1e40af;">0</strong>'
            altri_documenti_html = f' | 📎 Altri Documenti: <strong style="font-size: 1.2em; color: #1e40af;">{num_altri_documenti:,}</strong>'
            st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, rgba(219,234,254,0.55) 0%, rgba(191,219,254,0.70) 100%);
        padding: clamp(0.75rem, 1.8vw, 0.9rem) clamp(0.9rem, 2.5vw, 1.4rem);
        border-radius: 10px;
        border-left: 5px solid rgba(59,130,246,0.55);
        box-shadow: 0 3px 6px rgba(30,64,175,0.10);
        margin: 0 0 8px 0;
        display: block;
        width: min(100%, 44rem);
        min-width: 0;
        box-sizing: border-box;
        backdrop-filter: blur(10px);
    ">
        <span style="color: #1e3a8a; font-size: clamp(0.95rem, 1.3vw, 1.05rem); font-weight: 700; line-height: 1.45; overflow-wrap: anywhere;">
            📊 Fatture: <strong style="font-size: 1.2em; color: #1e40af;">{num_fatture_xml_p7m:,}</strong>{note_credito_html}{altri_documenti_html} | 
            📋 Righe Attive: <strong style="font-size: 1.2em; color: #1e40af;">{num_righe_attive:,}</strong>
        </span>
    </div>
    """, unsafe_allow_html=True)

            # Contatore fatture mensili (per file univoco XML/P7M)
            if 'FileOrigine' in df_cache.columns and 'DataDocumento' in df_cache.columns:
                df_month_counter = df_cache[['FileOrigine', 'DataDocumento']].copy()
                df_month_counter['DataDocumento'] = pd.to_datetime(df_month_counter['DataDocumento'], errors='coerce')
                df_month_counter = df_month_counter.dropna(subset=['FileOrigine', 'DataDocumento'])

                if not df_month_counter.empty:
                    df_month_counter['ext'] = df_month_counter['FileOrigine'].astype(str).apply(
                        lambda x: os.path.splitext(x.strip())[1].lower()
                    )
                    df_month_counter = df_month_counter[df_month_counter['ext'].isin(estensioni_fatture)]

                if not df_month_counter.empty:
                    # Un solo mese per file: usiamo la data massima del file
                    df_file_month = df_month_counter.groupby('FileOrigine', as_index=False)['DataDocumento'].max()
                    df_file_month['Anno'] = df_file_month['DataDocumento'].dt.year
                    df_file_month['MeseNum'] = df_file_month['DataDocumento'].dt.month

                    monthly_counts = (
                        df_file_month.groupby(['Anno', 'MeseNum'])
                        .size()
                        .reset_index(name='NumFatture')
                        .sort_values(['Anno', 'MeseNum'])
                    )

                    parti_mensili = []
                    for _, row in monthly_counts.iterrows():
                        mese_label = MESI_ITA.get(int(row['MeseNum']), str(int(row['MeseNum'])))
                        parti_mensili.append(
                            f"{mese_label}: <strong style='font-size:1.2em; color:#1e40af;'>{int(row['NumFatture'])}</strong>"
                        )

                    if parti_mensili:
                        st.markdown(
                            f"""
<div style="
    background: linear-gradient(135deg, rgba(219,234,254,0.55) 0%, rgba(191,219,254,0.70) 100%);
    padding: clamp(0.75rem, 1.8vw, 0.9rem) clamp(0.9rem, 2.5vw, 1.4rem);
    border-radius: 10px;
    border-left: 5px solid rgba(59,130,246,0.55);
    box-shadow: 0 3px 6px rgba(30,64,175,0.10);
    margin: 0 0 16px 0;
    display: block;
    width: min(100%, 44rem);
    min-width: 0;
    box-sizing: border-box;
    backdrop-filter: blur(10px);
">
    <span style="color: #1e3a8a; font-size: clamp(0.95rem, 1.3vw, 1.05rem); font-weight: 700; line-height: 1.45; overflow-wrap: anywhere;">
        📅 Fatture Mensili: {' | '.join(parti_mensili)}
    </span>
</div>
                            """,
                            unsafe_allow_html=True,
                        )

            st.markdown("---")

            # Raggruppa per file origine per creare summary
            if not df_cache.empty:
                _agg_dict = {
                    'Fornitore': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],
                    'TotaleRiga': 'sum',
                    'NumeroRiga': 'count',
                    'DataDocumento': 'first'
                }
                if 'DataDocumentoOriginale' in df_cache.columns:
                    _agg_dict['DataDocumentoOriginale'] = 'first'
                if 'DataCompetenza' in df_cache.columns:
                    _agg_dict['DataCompetenza'] = 'first'
                if 'CreatedAt' in df_cache.columns:
                    _agg_dict['CreatedAt'] = 'max'
                fatture_summary = df_cache.groupby('FileOrigine').agg(_agg_dict).reset_index()

                # 🔧 FIX: Reset index prima di rinominare (già fatto ma assicuriamo drop=True)
                fatture_summary = fatture_summary.reset_index(drop=True)

                _columns_rename = {
                    'FileOrigine': 'File',
                    'TotaleRiga': 'Totale',
                    'NumeroRiga': 'NumProdotti',
                    'DataDocumento': 'Data',
                }
                fatture_summary = fatture_summary.rename(columns=_columns_rename)

                _sort_dates = pd.to_datetime(fatture_summary.get('Data'), errors='coerce')
                fatture_summary = fatture_summary.assign(_sort_data=_sort_dates)
                if 'CreatedAt' in fatture_summary.columns:
                    _created_sort = pd.to_datetime(fatture_summary['CreatedAt'], errors='coerce')
                    fatture_summary = fatture_summary.assign(_sort_created=_created_sort).sort_values(
                        by=['_sort_data', '_sort_created'],
                        ascending=[False, False],
                        na_position='last',
                    )
                    fatture_summary = fatture_summary.drop(columns=['_sort_created'])
                else:
                    fatture_summary = fatture_summary.sort_values('_sort_data', ascending=False, na_position='last')
                fatture_summary = fatture_summary.drop(columns=['_sort_data'])
            else:
                fatture_summary = pd.DataFrame(columns=['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data'])

            # Allinea Gestione Fatture con fatture_documenti: mostra anche documenti
            # presenti nello Scadenziario ma senza righe in tabella fatture.
            if _docs_pagata:
                _present_files = set()
                if not fatture_summary.empty and 'File' in fatture_summary.columns:
                    _present_files = {
                        _norm_file_key(_f) for _f in fatture_summary['File'].dropna().tolist()
                    }

                _missing_rows = []
                for _doc in _docs_pagata:
                    _file_doc = str(_doc.get('file_origine') or '').strip()
                    _file_key_doc = _norm_file_key(_file_doc)
                    if not _file_doc or _file_key_doc in _present_files:
                        continue

                    _tot_doc = pd.to_numeric(_doc.get('totale_documento'), errors='coerce')
                    _tot_doc = float(_tot_doc) if pd.notna(_tot_doc) else 0.0
                    _data_doc = _doc.get('data_documento')

                    _missing_rows.append({
                        'File': _file_doc,
                        'Fornitore': str(_doc.get('fornitore') or 'Sconosciuto').strip() or 'Sconosciuto',
                        'Totale': _tot_doc,
                        'NumProdotti': 0,
                        'Data': _data_doc,
                        'DataDocumentoOriginale': _data_doc,
                        'DataCompetenza': None,
                        'CreatedAt': _doc.get('created_at'),
                    })
                    _present_files.add(_file_key_doc)

                if _missing_rows:
                    fatture_summary = pd.concat([
                        fatture_summary,
                        pd.DataFrame(_missing_rows),
                    ], ignore_index=True)

                    _sort_dates = pd.to_datetime(fatture_summary.get('Data'), errors='coerce')
                    fatture_summary = fatture_summary.assign(_sort_data=_sort_dates)
                    if 'CreatedAt' in fatture_summary.columns:
                        _created_sort = pd.to_datetime(fatture_summary['CreatedAt'], errors='coerce')
                        fatture_summary = fatture_summary.assign(_sort_created=_created_sort).sort_values(
                            by=['_sort_data', '_sort_created'],
                            ascending=[False, False],
                            na_position='last',
                        )
                        fatture_summary = fatture_summary.drop(columns=['_sort_created'])
                    else:
                        fatture_summary = fatture_summary.sort_values('_sort_data', ascending=False, na_position='last')
                    fatture_summary = fatture_summary.drop(columns=['_sort_data'])

            # 🗑️ PULSANTE SVUOTA TUTTO (solo admin/impersonificati - nessuna conferma richiesta)
            if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
                st.markdown("### 🗑️ Eliminazione Massiva")

                if st.button(
                    "🗑️ ELIMINA TUTTO",
                    type="primary",
                    use_container_width=True,
                    key="gfn_btn_svuota_definitivo"
                ):
                        with st.spinner("🗑️ Eliminazione in corso..."):
                            is_impersonating = st.session_state.get('impersonating', False)
                            use_soft_delete = not is_impersonating

                            # Progress bar per UX
                            progress = st.progress(0)
                            progress.progress(20, text="Eliminazione da Supabase...")

                            result = elimina_tutte_fatture(
                                user_id,
                                ristoranteid=current_ristorante,
                                soft_delete=use_soft_delete,
                            )

                            # 🔥 INVALIDAZIONE CACHE: Forza reload dati dopo eliminazione
                            invalida_cache_memoria()  # Reset memoria AI

                            # 🔥 RESET SESSION: Reinizializza set vuoti (non solo clear)
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
                                logger.warning(f"⚠️ Errore clear cache_resource durante hard reset: {e}")

                            progress.progress(80, text="Ripristino sessione...")

                            # HARD RESET: Rimuovi session state specifici
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
                                if use_soft_delete:
                                    st.success(f"✅ **{result['fatture_eliminate']} fatture** spostate nel cestino! ({result['righe_eliminate']} prodotti)")
                                    st.info("🗑️ Le fatture resteranno nel cestino per 30 giorni, poi verranno eliminate definitivamente.")
                                else:
                                    st.success(f"✅ **{result['fatture_eliminate']} fatture** eliminate definitivamente! ({result['righe_eliminate']} prodotti)")
                                    st.warning("⚠️ Operazione definitiva: fatture rimosse anche dall'archivio/cestino.")

                                # LOG AUDIT: Verifica immediata post-delete
                                try:
                                    verify_query = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id)
                                    if use_soft_delete:
                                        verify_query = filter_active(verify_query)
                                    verify_query = add_ristorante_filter(verify_query)
                                    verify = verify_query.execute()
                                    num_residue = verify.count or 0
                                    if num_residue == 0:
                                        logger.info(f"✅ DELETE VERIFIED: 0 righe rimaste per user_id={user_id}")
                                        if use_soft_delete:
                                            st.success("✅ Verifica: nessuna riga attiva rimasta")
                                        else:
                                            st.success("✅ Verifica: database pulito (0 righe)")
                                    else:
                                        logger.error(f"⚠️ DELETE INCOMPLETE: {num_residue} righe ancora presenti per user_id={user_id}")
                                        if use_soft_delete:
                                            st.error(f"⚠️ Attenzione: {num_residue} righe attive ancora presenti (possibile problema RLS)")
                                        else:
                                            st.error(f"⚠️ Attenzione: {num_residue} righe ancora presenti (possibile problema RLS)")
                                except Exception as e:
                                    logger.exception("Errore verifica post-delete")

                                if 'check_conferma_svuota' in st.session_state:
                                    del st.session_state.check_conferma_svuota

                                st.session_state.hide_uploader = True
                                st.session_state.files_processati_sessione = set()
                                st.cache_data.clear()
                                invalida_cache_memoria()
                                st.success("✅ Eliminato tutto!")
                                st.rerun()
                            else:
                                st.error(f"❌ Errore: {result['error']}")

                st.markdown("---")

            # ========== GESTIONE SINGOLA FATTURA ==========

            if len(fatture_summary) > 0:
                # ⚡ PERFORMANCE: filtri e tabella dentro @st.fragment
                # → cambiare un filtro rerun SOLO il fragment, non tutta la pagina
                @st.fragment
                def _render_gfn_fatture_fragment(fatture_summary_local):
                    # 🔍 FILTRI — Fornitore + Mese su due colonne affiancate
                    col_filtro_fornitore, col_filtro_mese = st.columns([1.2, 1.2])

                    fornitori_disponibili = sorted(fatture_summary_local['Fornitore'].dropna().unique().tolist())
                    opzioni_fornitore = ["— Tutti i fornitori —"] + fornitori_disponibili

                    with col_filtro_fornitore:
                        filtro_fornitore_sel = st.selectbox(
                            "🔍 Filtra per Fornitore:",
                            options=opzioni_fornitore,
                            key="gfn_filtro_fornitore_gestione"
                        )

                    if filtro_fornitore_sel == "— Tutti i fornitori —":
                        fatture_filtrate_temp = fatture_summary_local
                    else:
                        fatture_filtrate_temp = fatture_summary_local[fatture_summary_local['Fornitore'] == filtro_fornitore_sel]

                    # Estrai mesi unici dalle fatture filtrate per fornitore
                    mesi_disponibili = []
                    if len(fatture_filtrate_temp) > 0:
                        try:
                            date_vals = pd.to_datetime(fatture_filtrate_temp['Data'], errors='coerce')
                            mesi_disponibili = sorted(
                                [(f"{MESI_ITA.get(d.month, d.strftime('%B'))} {d.year}", d.year, d.month) for d in date_vals.dropna()],
                                key=lambda x: (x[1], x[2]),
                                reverse=True
                            )
                            mesi_visti = set()
                            mesi_disponibili = [
                                m for m in mesi_disponibili
                                if not (m in mesi_visti or mesi_visti.add(m))
                            ]
                        except Exception as _e_mesi:
                            logger.debug(f"Errore estrazione mesi: {_e_mesi}")
                            mesi_disponibili = []

                    opzioni_mese = ["— Tutti i mesi —"]
                    if mesi_disponibili:
                        _anni_disp = sorted(list({m[1] for m in mesi_disponibili}), reverse=True)
                        for _a in _anni_disp:
                            opzioni_mese.append(f"Tutto il {_a}")
                        opzioni_mese += [m[0] for m in mesi_disponibili]

                    with col_filtro_mese:
                        filtro_mese_sel = st.selectbox(
                            "📅 Filtra per Mese:",
                            options=opzioni_mese,
                            key="gfn_filtro_mese_gestione"
                        )

                    if filtro_mese_sel == "— Tutti i mesi —":
                        fatture_filtrate = fatture_filtrate_temp
                    elif filtro_mese_sel.startswith("Tutto il "):
                        _anno_target_int = int(filtro_mese_sel.replace("Tutto il ", ""))
                        fatture_filtrate = fatture_filtrate_temp[
                            pd.to_datetime(fatture_filtrate_temp['Data'], errors='coerce').dt.year == _anno_target_int
                        ]
                    else:
                        mese_target = next((m for m in mesi_disponibili if m[0] == filtro_mese_sel), None)
                        if mese_target:
                            _, anno_target, mese_num = mese_target
                            fatture_filtrate = fatture_filtrate_temp[
                                (pd.to_datetime(fatture_filtrate_temp['Data'], errors='coerce').dt.month == mese_num) &
                                (pd.to_datetime(fatture_filtrate_temp['Data'], errors='coerce').dt.year == anno_target)
                            ]
                        else:
                            fatture_filtrate = fatture_filtrate_temp

                    # File ricevuti da Invoicetronic non ancora confermati
                    _nuovi_invoicetronic = set()
                    if (st.session_state.get('auto_invoice_notice')
                            and not st.session_state.get('auto_invoice_notice_dismissed', False)):
                        _auto_ricevuti = st.session_state.get('auto_received_file_origini', set()) or set()
                        _auto_gestiti = st.session_state.get('auto_invoice_handled', set()) or set()
                        _nuovi_invoicetronic = _auto_ricevuti - _auto_gestiti

                    fatture_options = []
                    for idx, row in fatture_filtrate.iterrows():
                        _doc_row = _docs_map_norm.get(_norm_file_key(row.get('File')), {})
                        _data_competenza_val = row['DataCompetenza'] if 'DataCompetenza' in row.index else None
                        _data_originale_val = row['DataDocumentoOriginale'] if 'DataDocumentoOriginale' in row.index else row.get('Data')
                        _has_data_competenza = bool(pd.notna(_data_competenza_val) and str(_data_competenza_val).strip() not in {'', 'NaT', 'None'})
                        fatture_options.append({
                            'File': row['File'],
                            'Fornitore': row['Fornitore'],
                            'NumProdotti': int(row['NumProdotti']),
                            'Totale': row['Totale'],
                            'Data': row['Data'],
                            'DataOriginale': _data_originale_val,
                            'DataCompetenza': _data_competenza_val,
                            'HasDataCompetenza': _has_data_competenza,
                            'Pagata': bool(_doc_row.get('pagata', _pagata_map.get(_norm_file_key(row.get('File')), False))),
                            'Scadenza': _doc_row.get('scadenza_effettiva'),
                            'NumeroFattura': _doc_row.get('numero_documento'),
                            'TipoDocumento': _doc_row.get('tipo_documento'),
                            'PIVAFornitore': _doc_row.get('piva_fornitore'),
                            'IsNuova': row['File'] in _nuovi_invoicetronic,
                        })

                    fatture_options_local = fatture_options
                    if not fatture_options_local:
                        st.info("🔭 Nessuna fattura trovata per il fornitore cercato.")
                        return

                    # ---- Seleziona / Deseleziona tutto ----
                    if 'gfn_tbl_key_ver' not in st.session_state:
                        st.session_state.gfn_tbl_key_ver = 0
                    if 'gfn_selected_files' not in st.session_state:
                        st.session_state.gfn_selected_files = set()

                    _visible_files = {str(f['File']) for f in fatture_options}
                    st.session_state.gfn_selected_files = {
                        str(_f) for _f in (st.session_state.gfn_selected_files or set()) if str(_f) in _visible_files
                    }

                    # ---- Stato preview anteprima ----
                    if 'gfn_preview_open' not in st.session_state:
                        st.session_state.gfn_preview_open = False
                    if 'gfn_preview_file' not in st.session_state:
                        st.session_state.gfn_preview_file = None
                    if 'gfn_preview_nonce' not in st.session_state:
                        st.session_state.gfn_preview_nonce = 0
                    if 'gfn_preview_closed_for_n_sel' not in st.session_state:
                        st.session_state.gfn_preview_closed_for_n_sel = -1

                    # gfn-sel-col + stBaseButton-secondary CSS ora in common.css
                    _scol1, _scol2, _scol_info = st.columns([1.6, 1.8, 6.6])
                    with _scol1:
                        if st.button("☑️ Seleziona tutto", key="gfn_btn_sel_tutto", use_container_width=True):
                            st.session_state.gfn_selected_files = set(_visible_files)
                            st.session_state.gfn_tbl_key_ver += 1
                    with _scol2:
                        if st.button("⬜ Deseleziona tutto", key="gfn_btn_desel_tutto", use_container_width=True):
                            st.session_state.gfn_selected_files = set()
                            st.session_state.gfn_tbl_key_ver += 1

                    # ---- Tabella fatture ----
                    _df_tbl = pd.DataFrame([{
                        '✓': str(f['File']) in st.session_state.gfn_selected_files,
                        '🆕': '🆕' if f.get('IsNuova') else '',
                        'Fornitore': f['Fornitore'],
                        'Totale (€)': float(f['Totale']) if f['Totale'] is not None else 0.0,
                        'Righe': f['NumProdotti'],
                        'Data': str(f['DataOriginale'])[:10] if f.get('DataOriginale') else (str(f['Data'])[:10] if f.get('Data') else ''),
                        'Pagata': '✅' if f['Pagata'] else '⚪',
                        'Data Modificata': ('🔴 ' + str(f['DataCompetenza'])[:10]) if f['HasDataCompetenza'] else '',
                        'Scadenza': str(f['Scadenza'])[:10] if f['Scadenza'] else '',
                        'N° Fattura': str(f['NumeroFattura']) if f['NumeroFattura'] else '',
                        'File': f['File'],
                    } for f in fatture_options])

                    # stDataFrameResizable header azzurro CSS ora in common.css

                    _edited_tbl = st.data_editor(
                        _df_tbl,
                        column_config={
                            '✓': st.column_config.CheckboxColumn('✓', width='small', required=True),
                            '🆕': st.column_config.TextColumn('🆕', width='small', disabled=True, help='Fattura ricevuta automaticamente da Invoicetronic, in attesa di conferma'),
                            'Fornitore': st.column_config.TextColumn('Fornitore', disabled=True),
                            'N° Fattura': st.column_config.TextColumn('N° Fattura', disabled=True),
                            'Totale (€)': st.column_config.NumberColumn('Totale (€)', format='€ %.2f', disabled=True),
                            'Righe': st.column_config.NumberColumn('Righe', width='small', disabled=True),
                            'Data': st.column_config.TextColumn('Data', width='small', disabled=True),
                            'Scadenza': st.column_config.TextColumn('Scadenza', width='small', disabled=True),
                            'Pagata': st.column_config.TextColumn('Pagata', width='small', disabled=True),
                            'Data Modificata': st.column_config.TextColumn('Data Modificata', width='medium', disabled=True),
                            'File': st.column_config.TextColumn('File', disabled=True),
                        },
                        use_container_width=True,
                        hide_index=True,
                        height=420,
                        key=f'gfn_fatture_table_{st.session_state.gfn_tbl_key_ver}',
                    )

                    _selected_files_after_edit = set(
                        _edited_tbl.loc[_edited_tbl['✓'], 'File'].astype(str).tolist()
                    )
                    st.session_state.gfn_selected_files = _selected_files_after_edit

                    fatture_selezionate = [
                        f for f in fatture_options if str(f['File']) in st.session_state.gfn_selected_files
                    ]
                    n_sel = len(fatture_selezionate)

                    if n_sel > 0:
                        st.caption(f"**{n_sel}** fattura/e selezionata/e")

                    _fatture_pagate_sel = [f for f in fatture_selezionate if f.get('Pagata')]
                    _fatture_non_pagate_sel = [f for f in fatture_selezionate if not f.get('Pagata')]
                    _ha_comp = any(f.get('HasDataCompetenza') for f in fatture_selezionate)

                    # ---- Bottoni azioni ----
                    col_btn_delete, col_btn_date, col_btn_preview, col_btn_pagamento, col_btn_reset, col_spacer = st.columns([1, 1, 1, 1, 1, 1])
                    with col_btn_delete:
                        if st.button("🗑️ Elimina Fattura", type="secondary", use_container_width=True,
                                     key="gfn_btn_elimina_fattura", disabled=n_sel == 0):
                            with st.spinner("🗑️ Eliminazione in corso..."):
                                _errori_el = []
                                for _fat in fatture_selezionate:
                                    result = elimina_fattura_completa(_fat['File'], user_id, ristoranteid=current_ristorante)
                                    invalida_cache_memoria()
                                    clear_fatture_cache()
                                    if 'files_processati_sessione' in st.session_state:
                                        st.session_state.files_processati_sessione.discard(_fat['File'])
                                        st.session_state.files_processati_sessione.discard(os.path.splitext(_fat['File'])[0].lower())
                                    if not result.get("success"):
                                        _errori_el.append(f"{_fat['File']}: {result.get('error', '?')}")
                                if _errori_el:
                                    st.error("❌ Errori: " + "; ".join(_errori_el))
                                else:
                                    st.toast(f"✅ {n_sel} fattura/e spostate nel cestino", icon="🗑️")
                                    st.rerun()

                    with col_btn_date:
                        if st.button("📅 Cambia Data", type="secondary", use_container_width=True,
                                     key="gfn_btn_modifica_data", disabled=n_sel != 1):
                            if n_sel == 1:
                                st.session_state['gfn_fattura_data_editor_file'] = fatture_selezionate[0]['File']

                    with col_btn_preview:
                        if st.button("👁️ Anteprima", type="secondary", use_container_width=True,
                                     key="gfn_btn_anteprima", disabled=n_sel != 1):
                            if n_sel == 1:
                                st.session_state['gfn_preview_open'] = True
                                st.session_state['gfn_preview_file'] = fatture_selezionate[0]['File']

                    with col_btn_pagamento:
                        if _fatture_non_pagate_sel and st.button("💳 Conferma Pagamento", type="secondary", use_container_width=True,
                                     key="gfn_btn_conferma_pagamento"):
                            with st.spinner("Aggiornamento pagamento..."):
                                _errori_pag = []
                                for _fat in _fatture_non_pagate_sel:
                                    _esito_pag = segna_fattura_pagata(
                                        file_origine=_fat['File'],
                                        user_id=user_id,
                                        ristorante_id=current_ristorante,
                                        pagata=True,
                                    )
                                    if not _esito_pag.get("success"):
                                        _errori_pag.append(_fat['File'])
                                clear_documenti_cache()
                                clear_fatture_cache()
                                if _errori_pag:
                                    st.error(f"❌ Errore su: {', '.join(_errori_pag)}")
                                else:
                                    _msg_pag = f"✅ {len(_fatture_non_pagate_sel)} fattura/e pagate"
                                    st.toast(_msg_pag, icon="💳")
                                    st.rerun()

                        if _fatture_pagate_sel and st.button("↩️ Annulla Pagamento", type="secondary", use_container_width=True,
                                     key="gfn_btn_annulla_pagamento"):
                            with st.spinner("Aggiornamento pagamento..."):
                                _errori_pag = []
                                for _fat in _fatture_pagate_sel:
                                    _esito_pag = segna_fattura_pagata(
                                        file_origine=_fat['File'],
                                        user_id=user_id,
                                        ristorante_id=current_ristorante,
                                        pagata=False,
                                    )
                                    if not _esito_pag.get("success"):
                                        _errori_pag.append(_fat['File'])
                                clear_documenti_cache()
                                clear_fatture_cache()
                                if _errori_pag:
                                    st.error(f"❌ Errore su: {', '.join(_errori_pag)}")
                                else:
                                    st.toast(f"✅ {len(_fatture_pagate_sel)} fattura/e impostate come non pagate", icon="↩️")
                                    st.rerun()

                    with col_btn_reset:
                        if _ha_comp:
                            if st.button("↩️ Ripristina Data", use_container_width=True, key="gfn_btn_ripristina_data"):
                                with st.spinner("Ripristino in corso..."):
                                    for _fat in [f for f in fatture_selezionate if f.get('HasDataCompetenza')]:
                                        esito = aggiorna_data_competenza_fattura(
                                            file_origine=_fat['File'],
                                            user_id=user_id,
                                            data_competenza=None,
                                            ristoranteid=current_ristorante,
                                        )
                                        if not esito.get("success"):
                                            st.error(f"❌ {_fat['File']}: {esito.get('error', '?')}")
                                    clear_fatture_cache()
                                    invalida_cache_memoria()
                                    st.toast("✅ Date ripristinate", icon="↩️")
                                    st.session_state.pop('gfn_fattura_data_editor_file', None)
                                    st.rerun()

                    # ---- Pannello anteprima fattura (inline, indipendente dall'editor competenza) ----
                    if st.session_state.gfn_preview_open and st.session_state.gfn_preview_file:
                        _preview_file = st.session_state.gfn_preview_file
                        # Cerca in fatture_options (non in fatture_selezionate) per non dipendere dalla selezione attiva
                        _preview_fat = next((f for f in fatture_options if f['File'] == _preview_file), None)
                        if _preview_fat is None:
                            # Fattura non più visibile (filtrata o eliminata) → reset silenzioso
                            st.session_state.gfn_preview_open = False
                            st.session_state.gfn_preview_file = None

                        if _preview_fat:
                            with st.container():
                                _preview_col1, _preview_col_close = st.columns([11, 1])
                                with _preview_col_close:
                                    st.markdown("<div style='height: 0.4rem;'></div>", unsafe_allow_html=True)
                                    if st.button("✕", type="secondary", use_container_width=True,
                                                 key="gfn_btn_close_preview", help="Chiudi anteprima"):
                                        st.session_state.gfn_preview_open = False
                                        st.rerun(scope="fragment")

                                # Renderizza anteprima
                                _html_preview = render_anteprima_fattura(
                                    file_origine=_preview_file,
                                    docs_map=_docs_map,
                                    df_cache=df_cache,
                                    fattura_sel=_preview_fat
                                )
                                st.components.v1.html(_html_preview, height=700, scrolling=True)

                    # ---- Editor data competenza (solo per 1 fattura selezionata) ----
                    _file_date_editor = st.session_state.get('gfn_fattura_data_editor_file')
                    _fat_date = next((f for f in fatture_selezionate if f['File'] == _file_date_editor), None)
                    if _fat_date is None and _file_date_editor:
                        st.session_state.pop('gfn_fattura_data_editor_file', None)

                    if _fat_date:
                        st.markdown("#### 📅 Mese di competenza")
                        st.caption("La data documento originale resta invariata. Questa modifica impatta solo i riepiloghi gestionali.")

                        _data_raw = _fat_date.get('DataCompetenza') or _fat_date.get('Data')
                        _default_date = pd.Timestamp.now().date()
                        if _data_raw is not None and str(_data_raw).strip() not in {'', 'NaT', 'None'}:
                            try:
                                _parsed = pd.to_datetime(_data_raw, errors='coerce')
                                if pd.notna(_parsed):
                                    _default_date = _parsed.date()
                            except Exception:
                                pass

                        _mesi_it = {
                            1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
                            5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
                            9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre',
                        }
                        _anno_corrente = pd.Timestamp.now().year

                        col_mese, col_save_date, col_cancel_date, col_empty = st.columns([2.2, 1, 1, 4])

                        with col_mese:
                            mese_selezionato = st.selectbox(
                                "Mese-Anno",
                                options=list(_mesi_it.keys()),
                                index=max(0, min(11, _default_date.month - 1)),
                                format_func=lambda m: f"{_mesi_it.get(m, str(m))} {_anno_corrente}",
                                key="gfn_input_mese_competenza_fattura",
                            )

                        data_competenza = pd.Timestamp(year=int(_anno_corrente), month=int(mese_selezionato), day=1).date()

                        with col_save_date:
                            st.markdown("<div style='height: 1.9rem;'></div>", unsafe_allow_html=True)
                            if st.button("💾 Salva", type="primary", use_container_width=True, key="gfn_btn_salva_competenza"):
                                with st.spinner("Aggiornamento data in corso..."):
                                    esito = aggiorna_data_competenza_fattura(
                                        file_origine=_fat_date['File'],
                                        user_id=user_id,
                                        data_competenza=data_competenza.isoformat(),
                                        ristoranteid=current_ristorante,
                                    )
                                    if esito.get("success"):
                                        clear_fatture_cache()
                                        invalida_cache_memoria()
                                        st.toast(f"✅ Competenza impostata su {_mesi_it[mese_selezionato]} {_anno_corrente}", icon="📅")
                                        st.session_state.pop('gfn_fattura_data_editor_file', None)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Errore: {esito.get('error', 'errore sconosciuto')}")

                        with col_cancel_date:
                            st.markdown("<div style='height: 1.9rem;'></div>", unsafe_allow_html=True)
                            if st.button("✖️ Annulla", use_container_width=True, key="gfn_btn_annulla_competenza"):
                                st.session_state.pop('gfn_fattura_data_editor_file', None)
                                st.rerun(scope="fragment")

                _render_gfn_fatture_fragment(fatture_summary)
            else:
                st.info("🔭 Nessuna fattura da eliminare.")

            st.markdown("---")
            st.markdown("<h3 style='color:#1e40af; font-weight:700;'>♻️ Cestino Fatture</h3>", unsafe_allow_html=True)

            fatture_cestino = fatture_cestino_cache

            if fatture_cestino:
                file_cestino = st.selectbox(
                    "Seleziona fattura dal cestino:",
                    options=fatture_cestino,
                    format_func=lambda x: format_fattura_label(
                        file_name=x.get('file_origine', ''),
                        fornitore=x.get('fornitore', ''),
                        totale=x.get('totale', 0.0),
                        num_righe=int(x.get('num_righe', 0) or 0),
                        data=x.get('data_documento', ''),
                    ),
                    key="gfn_select_fattura_cestino"
                )

                col_restore, col_empty_trash, col_trash_spacer = st.columns([1, 1, 3])

                with col_restore:
                    if st.button("♻️ Ripristina Fattura", use_container_width=True, key="gfn_btn_ripristina_fattura"):
                        with st.spinner("♻️ Ripristino in corso..."):
                            result_restore = ripristina_fattura(
                                file_cestino.get('file_origine', ''),
                                user_id,
                                ristorante_id=current_ristorante
                            )
                            invalida_cache_memoria()
                            clear_fatture_cache()
                            if result_restore.get("success"):
                                st.toast(
                                    f"✅ Fattura ripristinata ({result_restore.get('righe_ripristinate', 0)} prodotti)",
                                    icon="♻️",
                                )
                                st.rerun()
                            else:
                                st.error(f"❌ Errore ripristino: {result_restore.get('error')}")

                with col_empty_trash:
                    if st.button("🗑️ Svuota Cestino", use_container_width=True, key="gfn_btn_svuota_cestino"):
                        with st.spinner("🗑️ Svuotamento cestino in corso..."):
                            result_empty = svuota_cestino(
                                user_id,
                                ristorante_id=current_ristorante
                            )
                            invalida_cache_memoria()
                            clear_fatture_cache()
                            if result_empty.get("success"):
                                st.toast(
                                    f"✅ Cestino svuotato: {result_empty.get('righe_eliminate', 0)} righe eliminate definitivamente",
                                    icon="🗑️",
                                )
                                st.rerun()
                            else:
                                st.error(f"❌ Errore svuotamento: {result_empty.get('error')}")
            else:
                st.info("🗑️ Cestino vuoto")

            if st.session_state.get('impersonating', False):
                st.caption("🗑️ In modalità impersona: 'ELIMINA TUTTO' è definitivo, mentre l'eliminazione singola passa dal cestino (30 giorni).")
            else:
                st.caption("🗑️ Le fatture eliminate vengono spostate nel cestino per 30 giorni")

            # ============================================================
            # 📅 RIVEDI COMPETENZE PREGRESSE
            # ============================================================
            st.markdown("---")
            st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📅 Rivedi Competenze Pregresse</h3>", unsafe_allow_html=True)
            st.caption(
                "Cerca tra le fatture già importate quelle emesse nei primi giorni del mese "
                "che potrebbero riferirsi al mese precedente e non hanno ancora una data di competenza impostata."
            )
            if st.button("🔍 Analizza fatture senza competenza", key="gfn_btn_analizza_competenze_pregresse"):
                st.session_state['gfn_show_rivedi_competenze'] = True

            if st.session_state.get('gfn_show_rivedi_competenze'):
                _SOGLIA_PREG = COMPETENZA_AUTO_SOGLIA_GIORNI
                _MESI_PREG = MESI_ITA
                _candidati_preg = []
                if not df_cache.empty and 'DataDocumentoOriginale' in df_cache.columns:
                    _df_preg = df_cache.copy()
                    _df_preg['_dt_orig'] = pd.to_datetime(_df_preg['DataDocumentoOriginale'], errors='coerce')
                    _df_preg['_comp_null'] = _df_preg['DataCompetenza'].apply(
                        lambda v: pd.isna(v) or str(v).strip() in ('', 'NaT', 'None', 'nan')
                    )
                    _df_preg = _df_preg[
                        _df_preg['_dt_orig'].notna() &
                        (_df_preg['_dt_orig'].dt.day <= _SOGLIA_PREG) &
                        _df_preg['_comp_null']
                    ]
                    if not _df_preg.empty:
                        _grp = _df_preg.groupby('FileOrigine').first().reset_index()
                        for _, _row in _grp.iterrows():
                            _dt_val = _row['_dt_orig']
                            _prev = _dt_val.replace(day=1) - pd.Timedelta(days=1)
                            _mese_l = f"{_MESI_PREG.get(_prev.month, '?').capitalize()} {_prev.year}"
                            _importo = float(_row.get('TotaleRiga', 0.0)) if pd.notna(_row.get('TotaleRiga')) else 0.0
                            _candidati_preg.append({
                                'file': str(_row['FileOrigine']),
                                'fornitore': str(_row.get('Fornitore', '')).strip() or 'Sconosciuto',
                                'data_documento': _dt_val.strftime('%d/%m/%Y'),
                                'mese_suggerito': _mese_l,
                                'data_competenza_suggerita': _prev.replace(day=1).date().isoformat(),
                                'importo': _importo,
                            })

                if not _candidati_preg:
                    st.success("✅ Nessuna fattura pregressa da rivedere — tutte le date di competenza risultano già corrette.")
                else:
                    st.warning(
                        f"Trovate **{len(_candidati_preg)} fatture** emesse nei primi {_SOGLIA_PREG} giorni del mese "
                        f"senza data di competenza impostata."
                    )
                    _sel_preg = {}
                    for _item_p in _candidati_preg:
                        _col_c, _col_i = st.columns([0.05, 0.95])
                        with _col_c:
                            _sel_preg[_item_p['file']] = st.checkbox(
                                "", value=True, key=f"gfn_preg_chk_{_item_p['file']}"
                            )
                        with _col_i:
                            st.markdown(
                                f"**{_item_p['fornitore']}** — `{_item_p['file']}`  \n"
                                f"Data documento: **{_item_p['data_documento']}** | 💰 **€ {_item_p['importo']:,.2f}** &nbsp;→&nbsp; "
                                f"Competenza suggerita: **{_item_p['mese_suggerito']}**"
                            )
                    st.markdown("---")
                    _col_ap, _col_ch, _col_sp = st.columns([1, 1, 4])
                    with _col_ap:
                        if st.button("✅ Applica selezione", type="primary", use_container_width=True, key="gfn_btn_applica_preg"):
                            _sel_items = [_i for _i in _candidati_preg if _sel_preg.get(_i['file'], False)]
                            if _sel_items:
                                _err_preg = []
                                for _i in _sel_items:
                                    _r = aggiorna_data_competenza_fattura(
                                        file_origine=_i['file'],
                                        user_id=user_id,
                                        data_competenza=_i['data_competenza_suggerita'],
                                        ristoranteid=current_ristorante,
                                    )
                                    if not _r.get('success'):
                                        _err_preg.append(_i['file'])
                                clear_fatture_cache()
                                invalida_cache_memoria()
                                st.session_state.pop('gfn_show_rivedi_competenze', None)
                                if _err_preg:
                                    st.toast(f"⚠️ Errore su: {', '.join(_err_preg)}", icon="⚠️")
                                else:
                                    st.toast(f"✅ {len(_sel_items)} fattura/e aggiornata/e", icon="✅")
                                st.rerun()
                            else:
                                st.info("Nessuna fattura selezionata.")
                    with _col_ch:
                        if st.button("✖️ Chiudi", use_container_width=True, key="gfn_btn_chiudi_preg"):
                            st.session_state.pop('gfn_show_rivedi_competenze', None)
                            st.rerun()

elif st.session_state.gfn_tab_attivo == "notifiche":
    # ============================================================
    # 🔔 INBOX NOTIFICHE
    # ============================================================
    from datetime import datetime as _dt_notif
    supabase_notif = get_supabase_client()

    # ============================================================
    # STEP 8 — Migrazione one-shot legacy dismissed_notification_ids
    # Mappa gli ID legacy (users.dismissed_notification_ids) verso
    # topic_key inbox e dismissa silenziosamente le notifiche
    # corrispondenti. Eseguito una sola volta per utente (flag
    # users.metadata->>'inbox_migration_done' = 'true').
    # ============================================================
    try:
        _sess_mig_key = f"gfn_notif_legacy_migration_done::{current_ristorante}"
        if not st.session_state.get(_sess_mig_key):
            # Verifica flag DB
            _mig_resp = (
                supabase_notif.table('users')
                .select('dismissed_notification_ids, metadata')
                .eq('id', user_id)
                .limit(1)
                .execute()
            )
            _mig_row = (_mig_resp.data or [{}])[0] or {}
            _mig_meta = _mig_row.get('metadata') or {}
            if not isinstance(_mig_meta, dict):
                _mig_meta = {}

            _done_by_rist = _mig_meta.get('inbox_migration_done_by_ristorante') or []
            if not isinstance(_done_by_rist, list):
                _done_by_rist = []
            _done_set = {str(_rid) for _rid in _done_by_rist}

            if str(current_ristorante) not in _done_set:
                _legacy_ids = _mig_row.get('dismissed_notification_ids') or {}
                if isinstance(_legacy_ids, dict) and _legacy_ids:
                    # Mappa pattern ID legacy → topic_key inbox
                    _LEGACY_MAP = [
                        ('missing-revenue',  ['fatturato_mancante']),
                        ('missing-labor',     ['costo_personale_mancante']),
                        ('scaduti',           ['scadenza_superata']),
                        ('imminenti',         ['scadenza_imminente']),
                        ('price-alert',       ['price_alert']),
                        ('credit-note',       ['credit_note']),
                        ('uncategorized',     ['uncategorized_rows']),
                    ]
                    # Pattern multipli (richiedono 2 condizioni)
                    _LEGACY_MAP_MULTI = [
                        (('td24', 'noddt'),    'td24_noddt'),
                        (('td24', 'missing'),  'td24_partial'),
                        (('failed',),          'upload_failed'),
                        (('other',),           'upload_failed'),
                    ]

                    _topics_to_dismiss: set = set()
                    for _lid in _legacy_ids.keys():
                        _lid_lower = str(_lid).lower()
                        for _pattern, _topics in _LEGACY_MAP:
                            if _pattern in _lid_lower:
                                _topics_to_dismiss.update(_topics)
                        for _patterns, _topic in _LEGACY_MAP_MULTI:
                            if all(p in _lid_lower for p in _patterns):
                                _topics_to_dismiss.add(_topic)

                    if _topics_to_dismiss:
                        from datetime import timezone as _tz_mig
                        _now_mig = _dt_notif.now(_tz_mig.utc).isoformat()
                        (
                            supabase_notif.table('notification_inbox')
                            .update({'dismissed_at': _now_mig})
                            .eq('user_id', user_id)
                            .eq('ristorante_id', current_ristorante)
                            .in_('topic_key', list(_topics_to_dismiss))
                            .is_('dismissed_at', 'null')
                            .execute()
                        )

                # Segna migrazione completata nel DB per questo ristorante
                _done_by_rist.append(str(current_ristorante))
                _new_meta = {
                    **_mig_meta,
                    'inbox_migration_done': True,
                    'inbox_migration_done_by_ristorante': sorted(set(_done_by_rist)),
                }
                supabase_notif.table('users').update(
                    {'metadata': _new_meta}
                ).eq('id', user_id).execute()

            # Flag sessione: evita query DB ai rerun successivi
            st.session_state[_sess_mig_key] = True
    except Exception as _mig_exc:
        logger.warning(f"[INBOX] Migrazione legacy dismissed IDs fallita (non critico): {_mig_exc}")
        st.session_state[f"gfn_notif_legacy_migration_done::{current_ristorante}"] = True  # Non riprovare

    # ── Toolbar ─────────────────────────────────────────────────
    _SOURCE_TYPE_LABELS = {
        "operativa":     "⚙️ Gestione",
        "upload":        "🧾 Fatture e Dati",
        "invoicetronic": "📥 Ricezione SDI",
    }
    _filter_options_labels = ['🔔 Tutte', '⚙️ Gestione', '🧾 Fatture e Dati', '📥 Ricezione SDI']
    _filter_label_to_db = {
        '🔔 Tutte':          None,
        '⚙️ Gestione':      'operativa',
        '🧾 Fatture e Dati': 'upload',
        '📥 Ricezione SDI': 'invoicetronic',
    }
    _filter_label = st.session_state.get('gfn_notif_filter', '🔔 Tutte')
    if _filter_label not in _filter_label_to_db:
        _filter_label = '🔔 Tutte'

    # ── Daily Briefing ──────────────────────────────────────────
    _briefing_key = f'gfn_briefing_snapshot::{current_ristorante}'
    _briefing_snap = st.session_state.get(_briefing_key)
    if _briefing_snap is None:
        _briefing_snap = get_today_briefing(
            user_id=user_id,
            ristorante_id=current_ristorante,
            supabase_client=supabase_notif,
        )
        if _briefing_snap is not None:
            st.session_state[_briefing_key] = _briefing_snap

    # Auto-refresh briefing: evita snapshot stantio quando cambiano le notifiche
    # (es. card "tutto in ordine" salvata prima che arrivino nuovi avvisi).
    _briefing_notif_count_saved = int((_briefing_snap or {}).get('notif_count') or 0)
    if _briefing_snap is not None and _briefing_notif_count_saved != int(_notif_badge_count):
        _notifs_for_brief = _prefetched_notifs
        if _notifs_for_brief is None:
            _notifs_for_brief = get_inbox_notifications(
                user_id=user_id,
                ristorante_id=current_ristorante,
                supabase_client=supabase_notif,
                source_type=None,
            )
        _new_snap = generate_and_save_briefing(
            user_id=user_id,
            ristorante_id=current_ristorante,
            notifications=_notifs_for_brief or [],
            supabase_client=supabase_notif,
        )
        if _new_snap is not None:
            _briefing_snap = _new_snap
            st.session_state[_briefing_key] = _new_snap

    _briefing_sev = (_briefing_snap or {}).get('severity_max', 'info')
    _briefing_color = {'error': '#ef4444', 'warning': '#f59e0b', 'info': '#3b82f6'}.get(_briefing_sev, '#3b82f6')

    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    if _briefing_snap and (_briefing_snap.get('narrative') or _briefing_snap.get('bullets')):
        _briefing_date_str = (_briefing_snap or {}).get('generated_for_date', '')
        _briefing_notif_count = (_briefing_snap or {}).get('notif_count', 0)
        _briefing_saved_fp = str((_briefing_snap or {}).get('notif_fingerprint') or '')
        _live_notifs_for_brief = _prefetched_notifs
        if _live_notifs_for_brief is None:
            _live_notifs_for_brief = get_inbox_notifications(
                user_id=user_id,
                ristorante_id=current_ristorante,
                supabase_client=supabase_notif,
                source_type=None,
            )
        _live_fp = notifications_fingerprint(_live_notifs_for_brief or [])
        _briefing_is_fresh = bool(_briefing_saved_fp) and (_briefing_saved_fp == _live_fp)
        _narrative = (_briefing_snap.get('narrative') or '').strip()
        if not _narrative:
            _narrative = ' '.join(str(b) for b in (_briefing_snap.get('bullets') or []))
        _nparts = [l for l in _narrative.split('\n') if l.strip()]
        if len(_nparts) >= 3:
            _n_open  = html.escape(_nparts[0])
            _n_body  = ''.join(
                f'<p style="margin:0.55rem 0 0 0;font-size:1.18rem;font-weight:600;color:#1e293b;line-height:1.75;">'
                f'{html.escape(l)}</p>'
                for l in _nparts[1:-1]
            )
            _n_close = html.escape(_nparts[-1])
        else:
            _n_open  = ''
            _n_body  = ''.join(
                f'<p style="margin:0.4rem 0 0 0;font-size:1.18rem;font-weight:600;color:#1e293b;line-height:1.75;">'
                f'{html.escape(l)}</p>'
                for l in _nparts
            )
            _n_close = ''
        _narrative_html = (
            (f'<p style="margin:0;font-size:1.1rem;font-weight:700;color:#1e40af;">{_n_open}</p>' if _n_open else '')
            + _n_body
            + (f'<p style="margin:0.6rem 0 0 0;font-size:1.05rem;font-weight:600;color:#64748b;font-style:italic;">{_n_close}</p>' if _n_close else '')
        )
        st.markdown(
            f'<div style="background:#f0f7ff;border:3px solid #3b82f6;'
            f'border-radius:10px;'
            f'padding:1rem 1.4rem;margin-bottom:1.2rem;">'
            f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">'
            f'<span style="font-size:0.8rem;font-weight:700;color:#2563eb;letter-spacing:0.05em;text-transform:uppercase;">'
            f'\U0001F4CB Briefing di oggi</span>'
            f'<span style="font-size:0.75rem;color:#94a3b8;margin-left:auto;">'
            f'{_briefing_notif_count} notifiche \u00b7 {html.escape(str(_briefing_date_str))}'
            f'</span></div>'
            f'{_narrative_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        _brief_col, _ = st.columns([1, 3])
        with _brief_col:
            _refresh_label = '✅ Briefing aggiornato' if _briefing_is_fresh else '🔄 Aggiorna briefing ora'
            if st.button(_refresh_label, key='gfn_rigenera_briefing',
                         use_container_width=True, type='secondary',
                         disabled=_briefing_is_fresh,
                         help='Si attiva quando arrivano nuove notifiche'):
                _notifs_for_brief = _live_notifs_for_brief
                _new_snap = generate_and_save_briefing(
                    user_id=user_id,
                    ristorante_id=current_ristorante,
                    notifications=_notifs_for_brief or [],
                    supabase_client=supabase_notif,
                )
                if _new_snap:
                    st.session_state[_briefing_key] = _new_snap
                    st.toast('Briefing aggiornato', icon='✅')
                    st.rerun()
                else:
                    st.warning('Impossibile aggiornare il briefing. Riprova.')
    else:
        _col_brief, _ = st.columns([1, 3])
        with _col_brief:
            # gfn_genera_briefing_wrap button CSS ora in common.css
            st.markdown('<span id="gfn_genera_briefing_wrap"></span>', unsafe_allow_html=True)
            if st.button('\U0001F4CB Genera briefing di oggi', key='gfn_genera_briefing',
                         use_container_width=True, type='primary'):
                _notifs_for_brief = get_inbox_notifications(
                    user_id=user_id,
                    ristorante_id=current_ristorante,
                    supabase_client=supabase_notif,
                )
                _new_snap = generate_and_save_briefing(
                    user_id=user_id,
                    ristorante_id=current_ristorante,
                    notifications=_notifs_for_brief,
                    supabase_client=supabase_notif,
                )
                if _new_snap:
                    st.session_state[_briefing_key] = _new_snap
                    st.toast('Briefing generato', icon='\u2705')
                    st.rerun()
                else:
                    st.warning('Impossibile generare il briefing. Riprova.')

    # ── Toolbar azione (sotto il briefing, allineata alle card) ─
    st.markdown("<div style='margin-top:2.4rem;'></div>", unsafe_allow_html=True)
    _tc1, _ = st.columns([1.3, 3.5])
    with _tc1:
        _filter_label = st.selectbox(
            "Filtra per tipologia:",
            options=_filter_options_labels,
            index=_filter_options_labels.index(_filter_label),
            key="gfn_notif_filter",
        )
    _ta1, _ta2 = st.columns([0.87, 0.13], vertical_alignment='center')
    with _ta1:
        st.markdown(
            "<span style='font-size:0.85rem;color:#64748b;'>"
            "\u2139\ufe0f Le notifiche vengono eliminate dopo 30 giorni"
            "</span>",
            unsafe_allow_html=True,
        )
    with _ta2:
        if st.button("\U0001F5D1\ufe0f Rimuovi tutte", key="gfn_notif_dismiss_all", use_container_width=True):
            dismiss_all_inbox_notifications(
                user_id=user_id,
                ristorante_id=current_ristorante,
                supabase_client=supabase_notif,
                source_type=_filter_label_to_db[_filter_label],
            )
            st.rerun()

    # ── Carica notifiche ─────────────────────────────────────────
    _selected_source = _filter_label_to_db[_filter_label]
    if _selected_source is None and _prefetched_notifs is not None:
        _all_notifs = _prefetched_notifs
    else:
        _all_notifs = get_inbox_notifications(
            user_id=user_id,
            ristorante_id=current_ristorante,
            supabase_client=supabase_notif,
            source_type=_selected_source,
        )

    if not _all_notifs:
        st.markdown("""
<div style="text-align:center;padding:3rem 1rem;color:#64748b;">
    <div style="font-size:2.5rem;margin-bottom:0.5rem;">🎉</div>
    <div style="font-size:1.1rem;font-weight:600;color:#1e293b;">Nessuna notifica attiva — tutto in ordine!</div>
    <div style="font-size:0.85rem;margin-top:0.4rem;">Le nuove notifiche appariranno qui automaticamente.</div>
</div>
""", unsafe_allow_html=True)
    else:
        # ── Helpers ──────────────────────────────────────────────
        def _sev_icon(sev):
            return {'error': '🔴', 'warning': '🟡', 'info': '🔵'}.get(sev, '🔵')

        def _chip_css(source_type):
            return {
                'operativa':     'background:#dbeafe;color:#1e40af;border:1px solid #bfdbfe;',
                'upload':        'background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;',
                'invoicetronic': 'background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;',
            }.get(source_type, 'background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;')

        def _chip_label(source_type):
            return _SOURCE_TYPE_LABELS.get(source_type, source_type or '—')

        def _fmt_date(iso_str):
            try:
                _d = _dt_notif.fromisoformat(str(iso_str).replace('Z', '+00:00'))
                return _d.strftime('%d/%m/%Y %H:%M')
            except Exception:
                return str(iso_str or '')[:10]

        def _render_notif_card(notif, card_key_suffix):
            _nid   = str(notif.get('id') or '')
            _sev   = notif.get('severity', 'info')
            _stype = notif.get('source_type', '')
            _title = notif.get('title', '')
            _body  = notif.get('body', '')
            _action = notif.get('action_page') or ''
            _date_str = _fmt_date(notif.get('source_event_at', ''))
            _title_safe = html.escape(str(_title or ''))
            _body_safe = html.escape(str(_body or '')).replace('\n', '<br/>')
            _body_safe = (
                _body_safe
                .replace('&lt;br/&gt;', '<br/>')
                .replace('&lt;br&gt;', '<br/>')
                .replace('&lt;br /&gt;', '<br/>')
            )
            # Colori stile scadenziario: bordo sinistro forte + bordo esterno tono chiaro
            _sev_colors = {
                "error":   ("#e05252", "#fca5a5"),
                "warning": ("#d97706", "#fcd34d"),
                "info":    ("#3a82e0", "#93c5fd"),
                "success": ("#3aad5e", "#86efac"),
            }
            _border_strong, _border_light = _sev_colors.get(_sev, ("#94a3b8", "#cbd5e1"))
            # Mappa nomi testuali → tab interni della pagina
            _TAB_MAP = {
                'Gestione e Pagamenti': 'scadenziario',
                'Scadenziario':         'scadenziario',
                'Gestione Fatture':     'gestione',
                'Vai ai Documenti':     'scadenziario',
            }
            # Fallback per action_page obsoleti: usa topic_key per determinare destinazione
            _TOPIC_PAGE_FALLBACK = {
                'fatturato_mancante':              'pages/1_calcolo_margine.py',
                'costo_personale_mancante':        'pages/1_calcolo_margine.py',
                'food_cost_soglia_superata':        'pages/2_foodcost.py',
                'mol_negativo':                    'pages/1_calcolo_margine.py',
                'food_cost_trend_peggioramento':   'pages/2_foodcost.py',
                'price_alert':                     'pages/3_controllo_prezzi.py',
                'prezzo_prodotto_record_storico':  'pages/3_controllo_prezzi.py',
                'uncategorized_rows':              'pages/4_analisi_personalizzata.py',
                'piva_duplicata_fornitore':        'pages/4_analisi_personalizzata.py',
                'tag_suggestion_new_tag':          'pages/4_analisi_personalizzata.py',
                'tag_suggestion_extend_tag':       'pages/4_analisi_personalizzata.py',
            }
            _TOPIC_TAB_FALLBACK = {
                'scadenza_superata':  'scadenziario',
                'scadenza_imminente': 'scadenziario',
                'invoicetronic_auto': 'gestione',
            }
            # Determina destinazione navigazione in modo robusto
            _nav_tab  = None
            _nav_page = None
            if _action:
                # Vecchio valore sbagliato: correggi on-the-fly
                if _action == 'pages/4_analisi_fatture.py':
                    _action = 'pages/4_analisi_personalizzata.py'
                if _action == 'pages/5_notifiche_e_gestione.py':
                    _nav_tab = 'scadenziario'
                elif _action.startswith('pages/') or _action == 'app.py':
                    _nav_page = _action
                elif _action in _TAB_MAP:
                    _nav_tab = _TAB_MAP[_action]
                else:
                    # Valore legacy non riconosciuto → fallback per topic_key
                    _topic_k = str(notif.get('topic_key') or '')
                    if _topic_k in _TOPIC_TAB_FALLBACK:
                        _nav_tab = _TOPIC_TAB_FALLBACK[_topic_k]
                    elif _topic_k in _TOPIC_PAGE_FALLBACK:
                        _nav_page = _TOPIC_PAGE_FALLBACK[_topic_k]
                    else:
                        _nav_page = 'app.py'
            elif notif.get('topic_key'):
                # Nessun action_page → usa fallback topic
                _topic_k = str(notif.get('topic_key') or '')
                if _topic_k in _TOPIC_TAB_FALLBACK:
                    _nav_tab = _TOPIC_TAB_FALLBACK[_topic_k]
                elif _topic_k in _TOPIC_PAGE_FALLBACK:
                    _nav_page = _TOPIC_PAGE_FALLBACK[_topic_k]
            _has_action = bool(_nav_tab or _nav_page)
            # Layout: card | cestino | freccia (freccia occupa spazio anche se vuota per allineamento)
            _col_card, _col_del, _col_nav = st.columns([0.87, 0.065, 0.065], vertical_alignment="center")
            with _col_card:
                st.markdown(
                    f"""<div style="border:2px solid {_border_light};border-left:6px solid {_border_strong};
                        border-radius:10px;padding:0.75rem 1.1rem;margin-bottom:2px;
                        background:#ffffff;box-shadow:0 2px 6px rgba(0,0,0,0.09);">
  <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px;">
    <span style="font-size:1.2rem;flex-shrink:0;line-height:1.5;">{_sev_icon(_sev)}</span>
        <strong style="font-size:1.15rem;color:#1e293b;line-height:1.4;flex:1;">{_title_safe}</strong>
    <span style="padding:4px 12px;border-radius:12px;font-size:1rem;font-weight:700;
                 white-space:nowrap;{_chip_css(_stype)}">{_chip_label(_stype)}</span>
  </div>
    <p style="margin:0 0 8px 28px;font-size:1rem;color:#475569;line-height:1.55;">{_body_safe}</p>
  <div style="display:flex;align-items:center;gap:16px;margin-left:28px;font-size:0.85rem;color:#94a3b8;">
    <span>🕐 {_date_str}</span>
  </div></div>""",
                    unsafe_allow_html=True,
                )
            with _col_del:
                if st.button("🗑️", key=f"gfn_notif_dismiss_{card_key_suffix}",
                             use_container_width=True, help="Rimuovi notifica"):
                    dismiss_inbox_notification(_nid, supabase_notif)
                    st.rerun()
            with _col_nav:
                if _has_action:
                    if st.button("➡️", key=f"gfn_notif_nav_{card_key_suffix}",
                                 use_container_width=True, help="Vai alla pagina"):
                        if _nav_tab:
                            st.session_state.gfn_tab_attivo = _nav_tab
                            st.rerun()
                        elif _nav_page:
                            st.switch_page(_nav_page)
            st.markdown("<div style='margin-bottom:6px;'></div>", unsafe_allow_html=True)

        # ── Sezione Nuove (<24h) ─────────────────────────────────
        _nuove      = [n for n in _all_notifs if n.get('is_new')]
        _precedenti = [n for n in _all_notifs if not n.get('is_new')]

        if _nuove:
            st.markdown("""
<div style="display:flex;align-items:center;gap:8px;margin:0.5rem 0 0.8rem;">
  <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
               background:#ef4444;flex-shrink:0;"></span>
  <span style="font-weight:700;font-size:0.95rem;color:#1e293b;">Nuove</span>
  <span style="font-size:0.8rem;color:#64748b;">Ultime 24 ore</span>
</div>""", unsafe_allow_html=True)
            for _i, _n in enumerate(_nuove):
                _render_notif_card(_n, f"new_{_i}")

        # ── Sezione Precedenti ───────────────────────────────────
        if _precedenti:
            st.markdown("""
<div style="display:flex;align-items:center;gap:8px;margin:1rem 0 0.8rem;">
  <span style="font-weight:700;font-size:0.95rem;color:#1e293b;">Precedenti</span>
</div>""", unsafe_allow_html=True)
            for _i, _n in enumerate(_precedenti):
                _render_notif_card(_n, f"prev_{_i}")

    # ── Info cleanup rimossa (testo spostato nella toolbar) ────

elif st.session_state.gfn_tab_attivo == "avvisi":
    # Tab avvisi rimosso - redirect a scadenziario
    st.session_state.gfn_tab_attivo = "scadenziario"
    st.rerun()



