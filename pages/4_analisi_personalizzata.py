"""
Analisi Personalizzata - Tag prodotto e aggregazioni personalizzate.
Skeleton iniziale con gating pagina e navigazione a bottoni.
"""

import io
import html as _html
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

from config.constants import (
    CATEGORIE_SPESE_GENERALI,
    CUSTOM_TAG_COLOR_DEFAULT,
    CUSTOM_TAG_SUGGESTION_MIN_PRODUCTS,
    CUSTOM_TAG_SUGGESTION_MIN_ROWS,
    CUSTOM_TAG_SUGGESTION_MIN_SCORE_EXTEND,
    MAX_CUSTOM_TAGS,
    MAX_CUSTOM_TAGS_TRIAL,
    MAX_PRODOTTI_PER_TAG,
    ORPHAN_CHECK_DAYS,
)
from config.logger_setup import get_logger
from services.db_service import (
    _normalize_custom_tag_key,
    aggiungi_associazioni,
    carica_e_prepara_dataframe,
    clear_tags_cache,
    crea_tag,
    elimina_tag,
    get_custom_tag_prodotti,
    get_custom_tags,
    get_descrizioni_distinte,
    rimuovi_associazione,
)
from services.tag_suggestion_service import (
    accept_suggestion_create_tag,
    accept_suggestion_extend_tag,
    dismiss_tag_suggestion,
    list_pending_tag_suggestions,
    run_tag_suggestion_pipeline,
    snooze_tag_suggestion,
)
from utils.period_helper import PERIODO_OPTIONS, calcola_date_periodo, risolvi_periodo
from utils.page_setup import check_page_enabled
from utils.ristorante_helper import get_current_ristorante_id
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header

logger = get_logger('analisi_personalizzata')


# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Analisi e Tag - ONEFLUX",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================
# NASCONDI SIDEBAR SE NON LOGGATO
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()


# ============================================
# AUTENTICAZIONE RICHIESTA
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")
    st.stop()

# Admin puro: accesso consentito anche fuori dal pannello admin

user = st.session_state.user_data
user_id = user["id"]
current_ristorante = get_current_ristorante_id()

if not current_ristorante:
    st.error("⚠️ Nessun ristorante selezionato. Torna alla Dashboard per selezionarne uno.")
    st.stop()


# ============================================
# CONTROLLO PAGINA ABILITATA
# ============================================
check_page_enabled('analisi_personalizzata', user_id)


# ============================================
# CARICAMENTO DATI BASE
# ============================================
custom_tags = get_custom_tags(user_id, current_ristorante)
descrizioni_distinte = get_descrizioni_distinte(user_id, current_ristorante)


def _tag_label(tag: dict) -> str:
    emoji = (tag.get("emoji") or "").strip()
    nome = (tag.get("nome") or "Tag senza nome").strip()
    return f"{emoji} {nome}".strip()


def _build_tag_associazioni_map(tags: list[dict], user_id: str) -> dict[int, list[dict]]:
    mapping = {}
    for tag in tags:
        tag_id = int(tag["id"])
        mapping[tag_id] = get_custom_tag_prodotti(tag_id, user_id)
    return mapping


def _build_descrizione_usage_map(tags: list[dict], tag_associazioni_map: dict[int, list[dict]]) -> dict[str, list[dict]]:
    usage_map = {}
    for tag in tags:
        tag_id = int(tag["id"])
        tag_label = _tag_label(tag)
        for assoc in tag_associazioni_map.get(tag_id, []):
            descrizione_key = assoc.get("descrizione_key")
            if not descrizione_key:
                continue
            usage_map.setdefault(descrizione_key, []).append(
                {
                    "tag_id": tag_id,
                    "tag_label": tag_label,
                }
            )
    return usage_map


def _build_usage_notice(other_tags: list[str], is_selected: bool) -> tuple[str, str] | None:
    labels = sorted({str(tag).strip() for tag in other_tags if str(tag).strip()})
    if not labels:
        return None

    joined = ", ".join(labels)
    if is_selected:
        return "warning", f"⚠️ Se salvi questo tag, questa descrizione resterà associata anche a: {joined}"
    return "info", f"ℹ️ Già presente in altri tag: {joined}"


def _apply_tipo_filtro(df_source: pd.DataFrame, tipo_filtro: str) -> pd.DataFrame:
    if df_source is None or df_source.empty or "Categoria" not in df_source.columns:
        return df_source.copy() if isinstance(df_source, pd.DataFrame) else pd.DataFrame()

    if tipo_filtro == "Food & Beverage":
        return df_source[~df_source["Categoria"].isin(CATEGORIE_SPESE_GENERALI)].copy()
    if tipo_filtro == "Spese Generali":
        return df_source[df_source["Categoria"].isin(CATEGORIE_SPESE_GENERALI)].copy()
    return df_source.copy()


def _conversione_quantita_normalizzata(row: pd.Series, fattore_kg: float | None) -> tuple[float | None, str | None]:
    quantita = row.get("Quantita")
    unita_misura = str(row.get("UnitaMisura") or "").strip().upper()

    if pd.isna(quantita):
        return None, None

    try:
        quantita = float(quantita)
    except (TypeError, ValueError):
        return None, None

    if fattore_kg:
        return quantita * float(fattore_kg), "normalizzata"

    if unita_misura == "KG":
        return quantita, "KG"
    if unita_misura == "GR":
        return quantita / 1000, "KG"
    if unita_misura == "LT":
        return quantita, "LT"
    if unita_misura == "ML":
        return quantita / 1000, "LT"
    if unita_misura == "CL":
        return quantita / 100, "LT"

    # Fallback per unità a pezzo/confezione (PZ, NR, CF, BT, SC, ecc.)
    # Usa la quantità grezza come unità intera
    if quantita > 0:
        return quantita, "PZ"

    return None, None


def _build_associazioni_map(associazioni_tag: list[dict]) -> dict[str, dict]:
    return {
        assoc["descrizione_key"]: {
            "descrizione": assoc.get("descrizione"),
            "fattore_kg": assoc.get("fattore_kg"),
        }
        for assoc in associazioni_tag
        if assoc.get("descrizione_key")
    }


def _prepare_tag_dataframe(df_source: pd.DataFrame, associazioni_map: dict[str, dict]) -> pd.DataFrame:
    if df_source.empty or not associazioni_map:
        return pd.DataFrame()

    df_tag = df_source.copy()
    df_tag["Data_DT"] = pd.to_datetime(df_tag["DataDocumento"], errors="coerce")
    df_tag["DescrizioneKey"] = df_tag["Descrizione"].apply(_normalize_custom_tag_key)
    df_tag = df_tag[df_tag["DescrizioneKey"].isin(set(associazioni_map.keys()))].copy()

    if df_tag.empty:
        return df_tag

    df_tag["FattoreKg"] = df_tag["DescrizioneKey"].map(
        lambda key: associazioni_map.get(key, {}).get("fattore_kg")
    )
    conversioni = df_tag.apply(
        lambda row: _conversione_quantita_normalizzata(row, row.get("FattoreKg")),
        axis=1,
        result_type="expand"
    )
    df_tag["QuantitaNorm"] = conversioni[0]
    df_tag["UnitaNorm"] = conversioni[1]
    df_tag["TotaleRigaNum"] = pd.to_numeric(df_tag["TotaleRiga"], errors="coerce").fillna(0.0)
    df_tag["PrezzoUnitarioNum"] = pd.to_numeric(df_tag["PrezzoUnitario"], errors="coerce")
    # Escludi righe con prezzo non positivo (sconti, rettifiche negative)
    df_tag = df_tag[df_tag["PrezzoUnitarioNum"] > 0].copy()
    return df_tag


def _filter_periodo(df_source: pd.DataFrame, data_inizio_filtro, data_fine_filtro) -> pd.DataFrame:
    if df_source.empty:
        return df_source
    mask_periodo = (
        (df_source["Data_DT"].dt.date >= data_inizio_filtro) &
        (df_source["Data_DT"].dt.date <= data_fine_filtro)
    )
    return df_source[mask_periodo].copy()


def _compute_kpi(df_tag_periodo: pd.DataFrame) -> dict:
    df_convertibili = df_tag_periodo[df_tag_periodo["QuantitaNorm"].notna()].copy()
    spesa_totale = float(df_tag_periodo["TotaleRigaNum"].sum())
    quantita_norm_totale = float(df_convertibili["QuantitaNorm"].sum()) if not df_convertibili.empty else 0.0
    prezzo_medio_ponderato = (
        float(df_convertibili["TotaleRigaNum"].sum()) / quantita_norm_totale
        if quantita_norm_totale > 0 else None
    )
    num_fornitori = int(df_tag_periodo["Fornitore"].nunique())
    num_fatture = int(df_tag_periodo["FileOrigine"].nunique())

    unita_norm_set = set(df_convertibili["UnitaNorm"].dropna().unique().tolist())
    if "KG" in unita_norm_set and "LT" not in unita_norm_set and "PZ" not in unita_norm_set:
        quantita_label = "⚖️ Quantità Totale KG"
        prezzo_label = "💶 Prezzo Medio €/KG"
    elif "LT" in unita_norm_set and "KG" not in unita_norm_set and "PZ" not in unita_norm_set:
        quantita_label = "🧴 Quantità Totale LT"
        prezzo_label = "💶 Prezzo Medio €/LT"
    elif unita_norm_set == {"PZ"} or ("PZ" in unita_norm_set and "KG" not in unita_norm_set and "LT" not in unita_norm_set):
        quantita_label = "📦 Quantità Totale (pz)"
        prezzo_label = "💶 Prezzo Medio €/pz"
    else:
        quantita_label = "⚖️ Quantità Normalizzata"
        prezzo_label = "💶 Prezzo Medio €/unità norm."

    return {
        "spesa_totale": spesa_totale,
        "quantita_norm_totale": quantita_norm_totale,
        "prezzo_medio_ponderato": prezzo_medio_ponderato,
        "num_fornitori": num_fornitori,
        "num_fatture": num_fatture,
        "quantita_label": quantita_label,
        "prezzo_label": prezzo_label,
    }


def _compute_orfani(df_all: pd.DataFrame, associazioni_tag: list[dict]) -> list[dict]:
    if df_all.empty or not associazioni_tag:
        return []

    soglia = pd.Timestamp.now().normalize() - pd.Timedelta(days=ORPHAN_CHECK_DAYS)
    df_recenti = df_all.copy()
    df_recenti["Data_DT"] = pd.to_datetime(df_recenti["DataDocumento"], errors="coerce")
    df_recenti = df_recenti[df_recenti["Data_DT"] >= soglia].copy()
    df_recenti["DescrizioneKey"] = df_recenti["Descrizione"].apply(_normalize_custom_tag_key)

    chiavi_recenti = set(df_recenti["DescrizioneKey"].dropna().unique().tolist())
    orfani = []
    for assoc in associazioni_tag:
        descrizione_key = assoc.get("descrizione_key")
        if descrizione_key and descrizione_key not in chiavi_recenti:
            orfani.append(assoc)
    return orfani


def _build_export_workbook(df_riepilogo: pd.DataFrame, df_dettaglio: pd.DataFrame) -> bytes:
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_riepilogo.to_excel(writer, sheet_name="Riepilogo Tag", index=False)
        df_dettaglio.to_excel(writer, sheet_name="Dettaglio Righe", index=False)
    excel_buffer.seek(0)
    return excel_buffer.getvalue()


tag_associazioni_map = _build_tag_associazioni_map(custom_tags, user_id)
descrizione_usage_map = _build_descrizione_usage_map(custom_tags, tag_associazioni_map)


# ============================================
# SESSION STATE PAGINA
# ============================================
if 'ap_show_create_form' not in st.session_state:
    st.session_state.ap_show_create_form = not bool(custom_tags)

if 'ap_form_nome' not in st.session_state:
    st.session_state.ap_form_nome = ""

if 'ap_form_emoji' not in st.session_state:
    st.session_state.ap_form_emoji = ""

if 'ap_form_colore' not in st.session_state:
    st.session_state.ap_form_colore = CUSTOM_TAG_COLOR_DEFAULT

if 'ap_search_descrizioni' not in st.session_state:
    st.session_state.ap_search_descrizioni = ""

if 'ap_tag_selezionato_id' not in st.session_state:
    st.session_state.ap_tag_selezionato_id = int(custom_tags[0]["id"]) if custom_tags else None

if 'ap_selected_descrizioni' not in st.session_state:
    st.session_state.ap_selected_descrizioni = {}

if 'ap_periodo_dropdown' not in st.session_state:
    st.session_state.ap_periodo_dropdown = "🗓️ Anno in Corso"

date_periodo = calcola_date_periodo()
oggi_date = date_periodo['oggi']
inizio_anno = date_periodo['inizio_anno']

if 'ap_data_inizio' not in st.session_state:
    st.session_state.ap_data_inizio = inizio_anno

if 'ap_data_fine' not in st.session_state:
    st.session_state.ap_data_fine = oggi_date

with st.spinner("Caricamento dati fatture..."):
    df_all_cached = carica_e_prepara_dataframe(
        user_id,
        ristorante_id=current_ristorante,
    )

valid_tag_ids = {int(tag["id"]) for tag in custom_tags}
if st.session_state.ap_tag_selezionato_id not in valid_tag_ids:
    st.session_state.ap_tag_selezionato_id = int(custom_tags[0]["id"]) if custom_tags else None


# ============================================
# SIDEBAR CONDIVISA
# ============================================
render_sidebar(user)


# ============================================
# HEADER PAGINA
# ============================================
render_oh_yeah_header()

st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
    🏷️ <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi e Tag</span>
</h2>
""", unsafe_allow_html=True)

st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)


# ============================================
# NAVIGAZIONE TAB
# ============================================
if 'ap_tab_attivo' not in st.session_state:
    st.session_state.ap_tab_attivo = "panoramica" if custom_tags else "gestione"
# Guard: il tab "export" è stato rimosso — reindirizza
if st.session_state.ap_tab_attivo == "export":
    st.session_state.ap_tab_attivo = "panoramica" if custom_tags else "gestione"

col_t1, col_t2 = st.columns(2)

with col_t1:
    if st.button("🏷️ GESTIONE\nTAG", key="ap_btn_gestione", use_container_width=True,
                 type="primary" if st.session_state.ap_tab_attivo == "gestione" else "secondary"):
        if st.session_state.ap_tab_attivo != "gestione":
            st.session_state.ap_tab_attivo = "gestione"
            for _k in [k for k in st.session_state if k.startswith("ap_confirm_delete_")]:
                st.session_state.pop(_k, None)
            st.rerun()

with col_t2:
    if st.button("📊 ANALISI\nTAG", key="ap_btn_panoramica", use_container_width=True,
                 type="primary" if st.session_state.ap_tab_attivo == "panoramica" else "secondary"):
        if st.session_state.ap_tab_attivo != "panoramica":
            st.session_state.ap_tab_attivo = "panoramica"
            for _k in [k for k in st.session_state if k.startswith("ap_confirm_delete_")]:
                st.session_state.pop(_k, None)
            st.rerun()

from utils.ui_helpers import load_all_css
load_all_css()

trial_info = st.session_state.get('trial_info', {})
is_trial = trial_info.get('is_trial', False) and not st.session_state.get('impersonating', False)
max_tags_allowed = MAX_CUSTOM_TAGS_TRIAL if is_trial else MAX_CUSTOM_TAGS
can_create_tag = len(custom_tags) < max_tags_allowed


# ============================================
# FILTRO PERIODO / AZIONE GESTIONE TAG
# ============================================
if st.session_state.ap_tab_attivo == "gestione":
    st.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)
else:
    st.markdown("<div style='margin-top: 1.1rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="color: #1e3a8a; font-size: 1.05rem; font-weight: 700; margin-bottom: 0.35rem;">
            Filtra per periodo
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_periodo, col_info_periodo = st.columns([1, 3])

    with col_periodo:
        periodo_selezionato = st.selectbox(
            "Periodo",
            options=PERIODO_OPTIONS,
            label_visibility="collapsed",
            index=PERIODO_OPTIONS.index(st.session_state.ap_periodo_dropdown)
            if st.session_state.ap_periodo_dropdown in PERIODO_OPTIONS else 3,
            key="ap_filtro_periodo"
        )

    st.session_state.ap_periodo_dropdown = periodo_selezionato
    data_inizio_filtro, data_fine_filtro, label_periodo = risolvi_periodo(periodo_selezionato, date_periodo)

    with col_info_periodo:
        if periodo_selezionato == "📆 Seleziona Mese":
            from utils.period_helper import get_mesi_disponibili_fatture, risolvi_mese_selezionato
            from services import get_supabase_client as _get_sb_ap
            _sb_ap = _get_sb_ap()
            _mesi_ap = get_mesi_disponibili_fatture(user_id, current_ristorante, _sb_ap)
            _mesi_labels_ap = [x[2] for x in _mesi_ap]
            if not _mesi_labels_ap:
                _mesi_labels_ap = [inizio_anno.strftime("%B %Y")]
            _col_mese_ap, _col_empty_ap = st.columns([1.2, 1.8])
            with _col_mese_ap:
                _mese_sel_ap = st.selectbox(
                    "Mese",
                    options=_mesi_labels_ap,
                    index=len(_mesi_labels_ap) - 1,
                    key="ap_mese_sel",
                    label_visibility="collapsed",
                )
            data_inizio_filtro, data_fine_filtro = risolvi_mese_selezionato(_mese_sel_ap, _mesi_ap)
            label_periodo = _mese_sel_ap
        elif data_inizio_filtro is None:
            # Periodo Personalizzato: range picker inline — larghezza contenuta con sotto-colonne
            _col_range, _col_empty = st.columns([1.2, 1.8])
            with _col_range:
                _range = st.date_input(
                    "Periodo",
                    value=(st.session_state.ap_data_inizio, st.session_state.ap_data_fine),
                    min_value=inizio_anno,
                    format="DD/MM/YYYY",
                    key="ap_data_range_custom",
                    label_visibility="collapsed",
                )
            if isinstance(_range, (list, tuple)) and len(_range) == 2:
                data_inizio_custom, data_fine_custom = _range[0], _range[1]
                if data_inizio_custom > data_fine_custom:
                    st.error("⚠️ La data iniziale deve essere precedente alla data finale.")
                    data_inizio_filtro = st.session_state.ap_data_inizio
                    data_fine_filtro = st.session_state.ap_data_fine
                else:
                    st.session_state.ap_data_inizio = data_inizio_custom
                    st.session_state.ap_data_fine = data_fine_custom
                    data_inizio_filtro = data_inizio_custom
                    data_fine_filtro = data_fine_custom
            else:
                # L'utente sta ancora selezionando la seconda data — mantieni il range precedente
                data_inizio_filtro = st.session_state.ap_data_inizio
                data_fine_filtro = st.session_state.ap_data_fine

            label_periodo = f"{data_inizio_filtro.strftime('%d/%m/%Y')} → {data_fine_filtro.strftime('%d/%m/%Y')}"
        else:
            # Periodo preimpostato: box azzurro come prima
            st.markdown(f"""
            <div style="display: inline-block; width: fit-content; background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
                        padding: 10px 16px;
                        border-radius: 8px;
                        border: 1px solid #93c5fd;
                        color: #1e3a8a;
                        font-size: clamp(0.78rem, 1.8vw, 0.88rem);
                        font-weight: 500;
                        line-height: 1.5;
                        margin-top: 0px;">
                📊 {label_periodo}
            </div>
            """, unsafe_allow_html=True)


# ============================================
# CONTENUTO TAB - SKELETON
# ============================================
if st.session_state.ap_tab_attivo == "panoramica":
    if not custom_tags:
        st.info("📭 Nessun tag disponibile. Vai al tab Gestione Tag per creare il primo.")
    else:
        tag_options = {_tag_label(tag): int(tag["id"]) for tag in custom_tags}
        selected_label = next(
            (label for label, tag_id in tag_options.items() if tag_id == st.session_state.ap_tag_selezionato_id),
            list(tag_options.keys())[0],
        )

        st.markdown("<div style='margin-top: 0.9rem;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="color: #1e3a8a; font-size: 1.12rem; font-weight: 700; margin-bottom: 0.35rem;">
                Seleziona Tag da Analizzare
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Calcola excel bytes PRIMA delle colonne per poter renderizzare inline
        _excel_bytes = None
        if not df_all_cached.empty:
            _exp_riepilogo, _exp_dettaglio = [], []
            for _exp_tag in custom_tags:
                _exp_tag_id = int(_exp_tag["id"])
                _exp_assoc = tag_associazioni_map.get(_exp_tag_id, [])
                if not _exp_assoc:
                    continue
                _exp_df = _prepare_tag_dataframe(df_all_cached, _build_associazioni_map(_exp_assoc))
                if _exp_df.empty:
                    continue
                _exp_df_p = _filter_periodo(_exp_df, data_inizio_filtro, data_fine_filtro)
                if _exp_df_p.empty:
                    continue
                _exp_kpi = _compute_kpi(_exp_df_p)
                _exp_riepilogo.append({
                    "Tag": _tag_label(_exp_tag),
                    "Spesa Totale (\u20ac)": round(_exp_kpi["spesa_totale"], 2),
                    "Quantit\u00e0 Normalizzata": round(_exp_kpi["quantita_norm_totale"], 3),
                    "Prezzo Medio Ponderato": round(_exp_kpi["prezzo_medio_ponderato"], 4) if _exp_kpi["prezzo_medio_ponderato"] is not None else None,
                    "Fornitori Distinti": _exp_kpi["num_fornitori"],
                    "Fatture Coinvolte": _exp_kpi["num_fatture"],
                })
                _exp_df_out = _exp_df_p.copy()
                _exp_df_out["Tag"] = _tag_label(_exp_tag)
                _exp_dettaglio.append(
                    _exp_df_out[[
                        "Tag", "DataDocumento", "Fornitore", "Descrizione",
                        "Quantita", "UnitaMisura", "QuantitaNorm",
                        "PrezzoUnitarioNum", "TotaleRigaNum", "FileOrigine",
                    ]].rename(columns={
                        "DataDocumento": "Data", "Quantita": "Quantit\u00e0", "UnitaMisura": "U.M.",
                        "QuantitaNorm": "Q.t\u00e0 Norm.", "PrezzoUnitarioNum": "Prezzo Unit.",
                        "TotaleRigaNum": "Totale Riga", "FileOrigine": "Fattura",
                    })
                )
            if _exp_riepilogo and _exp_dettaglio:
                _excel_bytes = _build_export_workbook(
                    pd.DataFrame(_exp_riepilogo),
                    pd.concat(_exp_dettaglio, ignore_index=True),
                )

        # Layout inline: selectbox tag | bottone Excel
        _col_tag, _col_export_btn, _col_tag_empty = st.columns([2.2, 0.45, 0.85])
        with _col_tag:
            selected_label = st.selectbox(
                "Seleziona Tag da Analizzare",
                options=list(tag_options.keys()),
                index=list(tag_options.keys()).index(selected_label),
                key="ap_select_tag_panoramica",
                label_visibility="collapsed",
            )
            st.session_state.ap_tag_selezionato_id = tag_options[selected_label]
            selected_tag_id = st.session_state.ap_tag_selezionato_id
        with _col_export_btn:
            if _excel_bytes:
                st.download_button(
                    label="XLS",
                    data=_excel_bytes,
                    file_name=f"analisi_tag_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ap_download_inline",
                    use_container_width=False,
                )

        associazioni_tag = tag_associazioni_map.get(selected_tag_id, [])
        if not associazioni_tag:
            st.info("📭 Il tag selezionato non ha ancora descrizioni associate.")
        else:
            associazioni_map = _build_associazioni_map(associazioni_tag)

            if df_all_cached.empty:
                st.info("📭 Nessuna fattura disponibile per costruire la panoramica del tag.")
            else:
                df_tag = _prepare_tag_dataframe(df_all_cached, associazioni_map)

                if df_tag.empty:
                    st.info("📭 Nessuna riga fattura collegata al tag selezionato.")
                else:
                    df_tag_periodo = _filter_periodo(df_tag, data_inizio_filtro, data_fine_filtro)

                    if df_tag_periodo.empty:
                        st.info("📭 Nessun dato disponibile nel periodo selezionato per questo tag.")
                    else:
                        kpi = _compute_kpi(df_tag_periodo)

                        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                        st.markdown("<h3 style='color:#1e40af; font-weight:700;'>💬 Analisi KPI Prodotti</h3>", unsafe_allow_html=True)

                        # stMetric CSS ora in common.css

                        col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
                        with col_kpi1:
                            st.metric("💰 Totale Spesa", f"€{kpi['spesa_totale']:,.0f}")
                        with col_kpi2:
                            st.metric(kpi["quantita_label"], f"{kpi['quantita_norm_totale']:,.0f}")
                        with col_kpi3:
                            st.metric(kpi["prezzo_label"], f"€{kpi['prezzo_medio_ponderato']:,.0f}" if kpi["prezzo_medio_ponderato"] is not None else "n.d.")
                        with col_kpi4:
                            st.metric("🏪 Fornitori Distinti", f"{kpi['num_fornitori']}")
                        with col_kpi5:
                            st.metric("🧾 Fatture Coinvolte", f"{kpi['num_fatture']}")

                        st.markdown("<div style='margin-top: 1.75rem;'></div>", unsafe_allow_html=True)
                        st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📈 Trend Acquisti nel Periodo</h3>", unsafe_allow_html=True)
                        df_trend = df_tag_periodo.copy()
                        df_trend["Data_DT"] = pd.to_datetime(df_trend["Data_DT"], errors="coerce")
                        df_trend["PrezzoUnitario"] = pd.to_numeric(df_trend["PrezzoUnitario"], errors="coerce")
                        df_trend["TotaleRigaNum"] = pd.to_numeric(df_trend.get("TotaleRigaNum"), errors="coerce")
                        df_trend["QuantitaNorm"] = pd.to_numeric(df_trend.get("QuantitaNorm"), errors="coerce")
                        df_trend["Quantita"] = pd.to_numeric(df_trend.get("Quantita"), errors="coerce")
                        df_trend = df_trend[df_trend["Data_DT"].notna() & df_trend["PrezzoUnitario"].notna()].copy()
                        df_trend = df_trend.sort_values(["Data_DT", "FileOrigine", "Descrizione"])

                        if not df_trend.empty:
                            usa_quantita_norm_trend = (
                                "QuantitaNorm" in df_trend.columns
                                and df_trend["QuantitaNorm"].notna().any()
                                and float(df_trend["QuantitaNorm"].fillna(0).sum()) > 0
                            )

                            if usa_quantita_norm_trend:
                                df_linea_tag = (
                                    df_trend.groupby("Data_DT", as_index=False)
                                    .agg(
                                        TotaleSpesa=("TotaleRigaNum", "sum"),
                                        QuantitaTotale=("QuantitaNorm", "sum"),
                                    )
                                )
                            else:
                                df_linea_tag = (
                                    df_trend.groupby("Data_DT", as_index=False)
                                    .agg(
                                        TotaleSpesa=("TotaleRigaNum", "sum"),
                                        QuantitaTotale=("Quantita", "sum"),
                                    )
                                )

                            df_linea_tag["PrezzoTag"] = df_linea_tag.apply(
                                lambda r: (r["TotaleSpesa"] / r["QuantitaTotale"])
                                if pd.notna(r["TotaleSpesa"]) and pd.notna(r["QuantitaTotale"]) and float(r["QuantitaTotale"]) > 0
                                else None,
                                axis=1,
                            )
                            df_linea_tag = df_linea_tag[df_linea_tag["PrezzoTag"].notna()].sort_values("Data_DT")

                            prezzo_medio_periodo = float(df_linea_tag["PrezzoTag"].mean()) if not df_linea_tag.empty else 0.0
                            if prezzo_medio_periodo > 0:
                                df_linea_tag["Var_Perc"] = ((df_linea_tag["PrezzoTag"] - prezzo_medio_periodo) / prezzo_medio_periodo) * 100
                            else:
                                df_linea_tag["Var_Perc"] = 0.0
                            df_linea_tag["VarPercLabel"] = df_linea_tag["Var_Perc"].apply(lambda x: f"{x:+.1f}%")

                            n_punti = len(df_linea_tag)

                            # Asse X: adattivo — se molti punti usa nticks, altrimenti array esplicito
                            if n_punti > 20:
                                x_axis_cfg = dict(
                                    tickformat="%d/%m/%y",
                                    nticks=10,
                                    tickangle=0,
                                    tickfont=dict(size=12, color="#6b7280", family="Arial"),
                                    showgrid=False,
                                    linecolor="#e5e7eb",
                                )
                            elif n_punti > 10:
                                x_tickvals = df_linea_tag["Data_DT"].dropna().drop_duplicates().tolist()
                                x_axis_cfg = dict(
                                    tickformat="%d/%m/%y",
                                    tickmode="array",
                                    tickvals=x_tickvals,
                                    tickangle=0,
                                    tickfont=dict(size=12, color="#6b7280", family="Arial"),
                                    showgrid=False,
                                    linecolor="#e5e7eb",
                                )
                            else:
                                x_tickvals = df_linea_tag["Data_DT"].dropna().drop_duplicates().tolist()
                                x_axis_cfg = dict(
                                    tickformat="%d/%m/%y",
                                    tickmode="array",
                                    tickvals=x_tickvals,
                                    tickangle=0,
                                    tickfont=dict(size=13, color="#6b7280", family="Arial"),
                                    showgrid=False,
                                    linecolor="#e5e7eb",
                                )

                            # Asse Y: massimo 7 tick equidistanti, mai uno per ogni valore
                            y_axis_cfg = dict(
                                nticks=7,
                                tickprefix="€",
                                tickformat=".2f",
                                tickfont=dict(size=14, color="#6b7280", family="Arial"),
                                gridcolor="rgba(229,231,235,0.7)",
                                gridwidth=1,
                                zeroline=False,
                            )

                            fig_prezzo = px.line(
                                df_linea_tag,
                                x="Data_DT",
                                y="PrezzoTag",
                                markers=True,
                                labels={"Data_DT": "", "PrezzoTag": ""},
                                custom_data=["VarPercLabel"],
                            )
                            fig_prezzo.update_traces(
                                line=dict(color="#2563eb", width=2.5, shape="spline"),
                                marker=dict(size=7, color="#2563eb", line=dict(color="#ffffff", width=1.5)),
                                fill="tozeroy",
                                fillcolor="rgba(37,99,235,0.07)",
                                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Prezzo: <b>€%{y:.2f}</b><br>Var. vs media: %{customdata[0]}<extra></extra>",
                            )
                            fig_prezzo.add_hline(
                                y=prezzo_medio_periodo,
                                line_dash="dash",
                                line_color="#dc2626",
                                line_width=1.5,
                                annotation_text=f"  Media €{prezzo_medio_periodo:.2f}",
                                annotation_position="right",
                                annotation_font=dict(color="#dc2626", size=13, family="Arial"),
                            )
                            fig_prezzo.update_layout(
                                height=380,
                                hovermode="x unified",
                                plot_bgcolor="#f9fafb",
                                paper_bgcolor="#ffffff",
                                margin=dict(t=20, b=10, l=10, r=80),
                                xaxis=x_axis_cfg,
                                yaxis=y_axis_cfg,
                                font=dict(size=12, color="#374151", family="Arial"),
                                showlegend=False,
                            )
                            st.plotly_chart(
                                fig_prezzo,
                                use_container_width=True,
                                config={"displayModeBar": False},
                            )
                        else:
                            st.info("📭 Nessun dato disponibile per disegnare il trend acquisti del tag nel periodo selezionato.")

                        st.markdown("<h3 style='color:#1e40af; font-weight:700;'>🏪 Analisi Fornitori del Tag</h3>", unsafe_allow_html=True)
                        df_forn = df_tag_periodo.copy()
                        df_forn["Fornitore"] = df_forn["Fornitore"].fillna("Fornitore sconosciuto").astype(str).str.strip()
                        df_forn["TotaleRigaNum"] = pd.to_numeric(df_forn["TotaleRigaNum"], errors="coerce")
                        df_forn["PrezzoUnitario"] = pd.to_numeric(df_forn["PrezzoUnitario"], errors="coerce")
                        df_forn["Quantita"] = pd.to_numeric(df_forn.get("Quantita"), errors="coerce")
                        df_forn["QuantitaNorm"] = pd.to_numeric(df_forn.get("QuantitaNorm"), errors="coerce")

                        usa_quantita_norm = (
                            "QuantitaNorm" in df_forn.columns
                            and df_forn["QuantitaNorm"].notna().any()
                            and float(df_forn["QuantitaNorm"].fillna(0).sum()) > 0
                        )

                        if usa_quantita_norm:
                            df_fornitori = (
                                df_forn.groupby("Fornitore", as_index=False)
                                .agg(
                                    SpesaTotale=("TotaleRigaNum", "sum"),
                                    QuantitaTotale=("QuantitaNorm", "sum"),
                                    NumAcquisti=("FileOrigine", "count"),
                                )
                            )
                            df_fornitori["PrezzoMedio"] = df_fornitori.apply(
                                lambda row: row["SpesaTotale"] / row["QuantitaTotale"] if row["QuantitaTotale"] and row["QuantitaTotale"] > 0 else None,
                                axis=1,
                            )
                            quantita_label = "Q.tà norm."
                        else:
                            df_fornitori = (
                                df_forn.groupby("Fornitore", as_index=False)
                                .agg(
                                    SpesaTotale=("TotaleRigaNum", "sum"),
                                    QuantitaTotale=("Quantita", "sum"),
                                    NumAcquisti=("FileOrigine", "count"),
                                    PrezzoMedio=("PrezzoUnitario", "mean"),
                                )
                            )
                            quantita_label = "Q.tà"

                        df_fornitori = df_fornitori[df_fornitori["SpesaTotale"].notna()].copy()

                        if not df_fornitori.empty:
                            df_fornitori["IncidenzaSpesa"] = (
                                df_fornitori["SpesaTotale"] / max(float(df_fornitori["SpesaTotale"].sum()), 0.0001) * 100
                            )
                            prezzo_medio_tag = float(df_fornitori["PrezzoMedio"].dropna().mean()) if not df_fornitori["PrezzoMedio"].dropna().empty else None
                            if prezzo_medio_tag:
                                df_fornitori["DeltaPct"] = ((df_fornitori["PrezzoMedio"] / prezzo_medio_tag) - 1) * 100
                            else:
                                df_fornitori["DeltaPct"] = 0.0

                            df_fornitori = df_fornitori.sort_values(["PrezzoMedio", "SpesaTotale"], ascending=[True, False]).reset_index(drop=True)
                            best_supplier = df_fornitori.iloc[0]
                            worst_supplier = df_fornitori.iloc[-1]
                            _best_pm = best_supplier["PrezzoMedio"]
                            _worst_pm = worst_supplier["PrezzoMedio"]
                            gap_pct = ((float(_worst_pm) / float(_best_pm)) - 1) * 100 if pd.notna(_best_pm) and pd.notna(_worst_pm) and float(_best_pm) > 0 else 0.0

                            def _forn_pct_html(value: float) -> str:
                                color = "#16a34a" if value <= 0 else "#dc2626"
                                sign = "+" if value > 0 else ""
                                return f'<span style="color:{color};font-weight:700;">{sign}{value:.1f}%</span>'

                            def _forn_bar_html(value: float) -> str:
                                width = max(4, min(100, value))
                                return (
                                    f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;">'
                                    f'<div style="width:72px;height:8px;background:#e2e8f0;border-radius:999px;overflow:hidden;">'
                                    f'<div style="width:{width:.0f}%;height:8px;background:#0ea5e9;"></div></div>'
                                    f'<span style="font-weight:600;">{value:.1f}%</span></div>'
                                )

                            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
                            # Stili tag-forn-* in static/common.css

                            h = []
                            h.append('<div class="tag-forn-grid">')
                            h.append(f'<div class="tag-forn-row tag-forn-header"><div>Fornitore</div><div>Spesa (€)</div><div>Acquisti</div><div>{quantita_label}</div><div>Prezzo medio</div><div>Vs media</div><div>% sul tag</div></div>')
                            for _, row_f in df_fornitori.iterrows():
                                fornitore_safe = _html.escape(str(row_f["Fornitore"]))
                                prezzo_medio = row_f["PrezzoMedio"] if pd.notna(row_f["PrezzoMedio"]) else 0.0
                                quantita_tot = row_f["QuantitaTotale"] if pd.notna(row_f["QuantitaTotale"]) else 0.0
                                h.append('<div class="tag-forn-row tag-forn-body">')
                                h.append(f'<div>{fornitore_safe}</div>')
                                h.append(f'<div>€ {row_f["SpesaTotale"]:,.2f}</div>')
                                h.append(f'<div>{int(row_f["NumAcquisti"])} </div>')
                                h.append(f'<div>{quantita_tot:,.2f}</div>')
                                h.append(f'<div>€ {prezzo_medio:,.2f}</div>')
                                h.append(f'<div>{_forn_pct_html(float(row_f["DeltaPct"]))}</div>')
                                h.append(f'<div>{_forn_bar_html(float(row_f["IncidenzaSpesa"]))}</div>')
                                h.append('</div>')
                            h.append('</div>')
                            st.markdown(''.join(h), unsafe_allow_html=True)

                            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

                            _colori_kpi = {'🟢': '#16a34a', '🟡': '#ca8a04', '🟠': '#ea580c', '🔴': '#dc2626', 'ℹ️': '#2563eb'}
                            _commenti_fornitori = []

                            migliore_delta = float(best_supplier["DeltaPct"]) if pd.notna(best_supplier["DeltaPct"]) else 0.0
                            peggiore_delta = float(worst_supplier["DeltaPct"]) if pd.notna(worst_supplier["DeltaPct"]) else 0.0
                            concentrazione_top = float(df_fornitori["IncidenzaSpesa"].max()) if not df_fornitori.empty else 0.0
                            num_fornitori_tag = len(df_fornitori)

                            if num_fornitori_tag > 1:
                                if concentrazione_top <= 35:
                                    conc_emoji, conc_text = "🟢", "Spesa ben distribuita tra i fornitori — buona diversificazione"
                                elif concentrazione_top <= 55:
                                    conc_emoji, conc_text = "🟡", "Un fornitore pesa più degli altri — monitorare la dipendenza"
                                else:
                                    conc_emoji, conc_text = "🔴", "Forte concentrazione su un solo fornitore — rischio di dipendenza elevato"
                                _commenti_fornitori.append({
                                    'kpi_nome': 'Concentrazione fornitore principale',
                                    'percentuale': f'{concentrazione_top:.1f}%',
                                    'commento': conc_text,
                                    'emoji': conc_emoji,
                                    'colore': _colori_kpi.get(conc_emoji, '#6b7280')
                                })

                                if gap_pct <= 10:
                                    gap_emoji, gap_text = "🟢", "Gap prezzi contenuto — mercato abbastanza allineato"
                                elif gap_pct <= 25:
                                    gap_emoji, gap_text = "🟡", "Gap prezzi moderato — ci sono margini di trattativa"
                                else:
                                    gap_emoji, gap_text = "🔴", "Gap prezzi elevato — conviene rivedere il mix fornitori"
                                _commenti_fornitori.append({
                                    'kpi_nome': 'Gap prezzi tra fornitori',
                                    'percentuale': f'{gap_pct:.1f}%',
                                    'commento': gap_text,
                                    'emoji': gap_emoji,
                                    'colore': _colori_kpi.get(gap_emoji, '#6b7280')
                                })

                                _commenti_fornitori.append({
                                    'kpi_nome': f'Fornitore più conveniente — {_html.escape(str(best_supplier["Fornitore"]))}',
                                    'percentuale': f'{migliore_delta:.1f}%',
                                    'commento': 'Prezzo sotto la media del tag — opportunità di ottimizzazione acquisti',
                                    'emoji': '🟢' if migliore_delta <= 0 else '🟡',
                                    'colore': _colori_kpi.get('🟢' if migliore_delta <= 0 else '🟡', '#6b7280')
                                })

                                _worst_emoji = '🔴' if peggiore_delta > 0 else '🟢'
                                _commenti_fornitori.append({
                                    'kpi_nome': f'Fornitore più caro — {_html.escape(str(worst_supplier["Fornitore"]))}',
                                    'percentuale': f'{peggiore_delta:.1f}%',
                                    'commento': 'Prezzo sopra la media del tag — valutare alternative o trattativa',
                                    'emoji': _worst_emoji,
                                    'colore': _colori_kpi.get(_worst_emoji, '#6b7280')
                                })

                            if num_fornitori_tag <= 1:
                                forn_emoji, forn_text = "🟡", "Un solo fornitore sul tag — confronto limitato"
                            elif num_fornitori_tag <= 3:
                                forn_emoji, forn_text = "🟢", "Confronto fornitori chiaro e gestibile"
                            else:
                                forn_emoji, forn_text = "🟢", "Buona base di confronto tra fornitori del tag"
                            _commenti_fornitori.append({
                                'kpi_nome': 'Copertura fornitori',
                                'percentuale': f'{num_fornitori_tag} forn.',
                                'commento': forn_text,
                                'emoji': forn_emoji,
                                'colore': _colori_kpi.get(forn_emoji, '#6b7280')
                            })

                            if _commenti_fornitori:
                                st.markdown("<div style='margin-top: 1.35rem;'></div>", unsafe_allow_html=True)
                                st.markdown('<h4 style="color:#1e40af;font-weight:700;">💬 Analisi KPI Fornitori</h4>', unsafe_allow_html=True)
                                for c in _commenti_fornitori:
                                    st.markdown(f"""
                                    <div style='display: flex; align-items: center; gap: 12px; padding: 10px 16px; margin: 5px 0;
                                                border-left: 4px solid {c['colore']};
                                                background: linear-gradient(135deg, rgba(248,249,250,0.95), rgba(240,242,245,0.95));
                                                border-radius: 6px;'>
                                        <span style='font-size: clamp(1.1rem, 3vw, 1.4rem); font-weight: 800; color: {c['colore']}; min-width: 90px;'>
                                            {c['emoji']} {c['percentuale']}
                                        </span>
                                        <span style='font-size: clamp(0.8rem, 1.8vw, 0.9rem); color: #374151;'>
                                            <strong>{c['kpi_nome']}</strong>: {c['commento']}
                                        </span>
                                    </div>
                                    """, unsafe_allow_html=True)
                        else:
                            st.info("📭 Nessun dato fornitore disponibile per il tag nel periodo selezionato.")
elif st.session_state.ap_tab_attivo == "gestione":

    if not can_create_tag:
        if is_trial:
            st.warning("🔒 In prova gratuita puoi creare un solo tag. Passa al piano completo per sbloccarne altri.")
        else:
            st.warning(f"🔒 Hai raggiunto il limite massimo di {MAX_CUSTOM_TAGS} tag per questo account.")

    st.markdown('<h3 style="color:#1e40af; font-weight:700;">💡 Suggerimenti intelligenti</h3>', unsafe_allow_html=True)
    _sugg_refresh_key = f"ap_sugg_last_run_ts::{user_id}::{current_ristorante}"
    _now_ts = time.time()
    if (_now_ts - float(st.session_state.get(_sugg_refresh_key, 0.0))) > 600:
        run_tag_suggestion_pipeline(
            user_id=user_id,
            ristorante_id=current_ristorante,
            min_products=CUSTOM_TAG_SUGGESTION_MIN_PRODUCTS,
            min_rows=CUSTOM_TAG_SUGGESTION_MIN_ROWS,
            min_score_extend=CUSTOM_TAG_SUGGESTION_MIN_SCORE_EXTEND,
        )
        st.session_state[_sugg_refresh_key] = _now_ts

    _pending_suggestions = list_pending_tag_suggestions(user_id=user_id, ristorante_id=current_ristorante)
    _pending_new = [s for s in _pending_suggestions if s.get('suggestion_type') == 'new_tag']
    _pending_extend = [s for s in _pending_suggestions if s.get('suggestion_type') == 'extend_tag']
    _tag_label_by_id = {int(t['id']): _tag_label(t) for t in custom_tags if t.get('id') is not None}

    _orfani_associazioni = []
    _sel_tag_id_for_orfani = st.session_state.get('ap_tag_selezionato_id')
    if _sel_tag_id_for_orfani and not df_all_cached.empty:
        _assoc_sel = tag_associazioni_map.get(int(_sel_tag_id_for_orfani), [])
        if _assoc_sel:
            _orfani_associazioni = _compute_orfani(df_all_cached, _assoc_sel)
    _orfani_count = len(_orfani_associazioni)

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric("Nuovi Tag Suggeriti", f"{len(_pending_new)}")
    with col_s2:
        st.metric("Estensioni Tag", f"{len(_pending_extend)}")
    with col_s3:
        st.metric("Totale Suggerimenti", f"{len(_pending_suggestions)}")
    with col_s4:
        st.metric("Associazioni Da Rivedere", f"{_orfani_count}")

    if _orfani_count > 0:
        with st.expander(
            f"⚠️ {_orfani_count} associazioni potenzialmente orfane (ultimi {ORPHAN_CHECK_DAYS} giorni)",
            expanded=False,
        ):
            _sel_tag_label = _tag_label_by_id.get(int(_sel_tag_id_for_orfani), "tag selezionato")
            st.caption(f"Tag corrente: {_sel_tag_label}")
            for _assoc in _orfani_associazioni[:20]:
                st.markdown(f"- {_assoc.get('descrizione', '-')}")
            if _orfani_count > 20:
                st.caption(f"... e altre {_orfani_count - 20} associazioni")

            _confirm_bulk_key = f"ap_confirm_remove_orfani_{int(_sel_tag_id_for_orfani)}"
            _valid_orfani_ids = [
                int(_assoc['id'])
                for _assoc in _orfani_associazioni
                if _assoc.get('id') is not None
            ]
            if _valid_orfani_ids:
                if st.session_state.get(_confirm_bulk_key, False):
                    _c1, _c2 = st.columns([1.1, 1])
                    with _c1:
                        if st.button(
                            "⚠️ Conferma rimozione orfani",
                            key=f"ap_bulk_remove_orfani_confirm_{int(_sel_tag_id_for_orfani)}",
                            use_container_width=True,
                        ):
                            for _assoc_id in _valid_orfani_ids:
                                rimuovi_associazione(_assoc_id, user_id)
                            st.session_state.pop(_confirm_bulk_key, None)
                            clear_tags_cache()
                            st.toast("Associazioni orfane rimosse", icon="🧹")
                            st.rerun()
                    with _c2:
                        if st.button(
                            "Annulla",
                            key=f"ap_bulk_remove_orfani_cancel_{int(_sel_tag_id_for_orfani)}",
                            use_container_width=True,
                        ):
                            st.session_state.pop(_confirm_bulk_key, None)
                            st.rerun()
                else:
                    if st.button(
                        "🧹 Rimuovi tutte le associazioni orfane",
                        key=f"ap_bulk_remove_orfani_start_{int(_sel_tag_id_for_orfani)}",
                        use_container_width=True,
                    ):
                        st.session_state[_confirm_bulk_key] = True
                        st.rerun()

    if _pending_suggestions:
        for _s in _pending_suggestions[:10]:
            _sid = int(_s.get('id'))
            _stype = str(_s.get('suggestion_type') or '')
            _items = _s.get('items') or []
            _products = int(_s.get('matched_products_count') or 0)
            _rows = int(_s.get('matched_rows_count') or 0)
            _conf = float(_s.get('confidence_score') or 0.0)
            _title = (
                f"Nuovo Tag: {_s.get('suggested_tag_name') or 'Senza nome'}"
                if _stype == 'new_tag'
                else f"Estendi Tag ID {_s.get('target_tag_id') or '-'}"
            )

            with st.container(border=True):
                st.markdown(f"**{_title}**")
                st.caption(
                    f"Prodotti: {_products} · Occorrenze: {_rows} · Confidenza: {_conf:.0f}% · Finestra: 30 giorni"
                )
                if _items:
                    _preview = ", ".join(str(i.get('descrizione') or '') for i in _items[:5] if i.get('descrizione'))
                    if _preview:
                        st.caption(f"Esempi: {_preview}")

                _c_accept, _c_snooze, _c_dismiss = st.columns([1.2, 1, 1])
                with _c_accept:
                    if st.button("✅ Accetta", key=f"ap_sugg_accept_{_sid}", use_container_width=True):
                        if _stype == 'new_tag':
                            _result = accept_suggestion_create_tag(
                                suggestion_id=_sid,
                                tag_name=str(_s.get('suggested_tag_name') or '').strip() or None,
                                user_id=user_id,
                                ristorante_id=current_ristorante,
                            )
                        else:
                            _result = accept_suggestion_extend_tag(
                                suggestion_id=_sid,
                                tag_id=int(_s.get('target_tag_id') or 0) or None,
                                user_id=user_id,
                                ristorante_id=current_ristorante,
                            )
                        if _result.get('success'):
                            st.toast("Suggerimento applicato", icon="✅")
                            clear_tags_cache()
                            st.rerun()
                        st.error(f"⚠️ Operazione non riuscita: {_result.get('error', 'errore sconosciuto')}")
                with _c_snooze:
                    if st.button("⏰ Snooze 30g", key=f"ap_sugg_snooze_{_sid}", use_container_width=True):
                        snooze_tag_suggestion(_sid, user_id=user_id, ristorante_id=current_ristorante, days=30)
                        st.toast("Suggerimento rinviato di 30 giorni", icon="⏰")
                        st.rerun()
                with _c_dismiss:
                    if st.button("❌ Ignora", key=f"ap_sugg_dismiss_{_sid}", use_container_width=True):
                        dismiss_tag_suggestion(_sid, user_id=user_id, ristorante_id=current_ristorante)
                        st.toast("Suggerimento ignorato", icon="🗑️")
                        st.rerun()
    else:
        st.info("📭 Nessun suggerimento attivo al momento. I nuovi suggerimenti vengono aggiornati automaticamente dopo i caricamenti.")

    st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)

    st.markdown('<h3 style="color:#1e40af; font-weight:700;">✨ Crea Nuovo o modifica Tag</h3>', unsafe_allow_html=True)
    st.markdown("""
    <div style="display: inline-block; background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%); padding: 10px 14px; border-radius: 10px; border: 1px solid #93c5fd; color: #1e3a8a; font-weight: 600; font-size: 0.88rem; margin-bottom: 0.5rem;">
        🔔 Inserisci il nome tag - filtra e seleziona i prodotti - salva tag
    </div>
    <br>
    <div style="display: inline-block; background: linear-gradient(135deg, #fef3c7 0%, #fffbeb 100%); padding: 10px 14px; border-radius: 10px; border: 1px solid #f59e0b; color: #92400e; font-weight: 600; font-size: 0.88rem; margin-bottom: 0.8rem;">
        🔔 Inserisci il nome tag da modificare - modifica tag - filtra e aggiungi i prodotti - salva tag
    </div>
    <!-- stTextInput label + ap_btn_modifica_tag CSS ora in common.css -->
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
    col_nome_tag, col_modifica_btn, col_salva_btn = st.columns([3.2, 1.2, 1.1])
    with col_nome_tag:
        st.text_input(
            "Inserisci il nome del tag nuovo o da modificare",
            key="ap_form_nome",
            placeholder="Es. Salmone, Olio EVO, Farina 00",
            max_chars=100,
        )
    with col_modifica_btn:
        st.markdown("<div style='margin-top: 1.75rem;'></div>", unsafe_allow_html=True)
        modifica_tag_clicked = st.button(
            "✏️ Modifica Tag",
            key="ap_btn_modifica_tag",
            use_container_width=True,
            disabled=not bool(st.session_state.ap_form_nome.strip()),
        )
    with col_salva_btn:
        st.markdown("<div style='margin-top: 1.75rem;'></div>", unsafe_allow_html=True)
        crea_tag_clicked = st.button(
            "💾 Salva Tag",
            key="ap_btn_crea_tag",
            type="primary",
            use_container_width=True,
            disabled=not bool(st.session_state.ap_form_nome.strip()),
        )

    if modifica_tag_clicked:
        nome_tag = st.session_state.ap_form_nome.strip()
        existing_tag = next(
            (
                tag for tag in custom_tags
                if str(tag.get("nome", "")).strip().lower() == nome_tag.lower()
            ),
            None,
        )
        if not existing_tag:
            st.error("⚠️ Nessun tag esistente trovato con questo nome.")
        else:
            tag_id = int(existing_tag["id"])
            st.session_state.ap_tag_selezionato_id = tag_id
            for _key in list(st.session_state.keys()):
                if str(_key).startswith("ap_chk_"):
                    st.session_state.pop(_key, None)
            st.session_state.ap_selected_descrizioni = {
                assoc["descrizione_key"]: {
                    "descrizione": assoc.get("descrizione", ""),
                    "descrizione_key": assoc.get("descrizione_key"),
                    "fattore_kg": assoc.get("fattore_kg"),
                }
                for assoc in tag_associazioni_map.get(tag_id, [])
                if assoc.get("descrizione_key")
            }
            for _desc_key in st.session_state.ap_selected_descrizioni:
                st.session_state[f"ap_chk_{_desc_key}"] = True
            st.rerun()

    if crea_tag_clicked:
        nome_tag = st.session_state.ap_form_nome.strip()
        selected_associazioni = list(st.session_state.ap_selected_descrizioni.values())
        existing_tag = next(
            (
                tag for tag in custom_tags
                if str(tag.get("nome", "")).strip().lower() == nome_tag.lower()
            ),
            None,
        )

        if not nome_tag:
            st.error("⚠️ Inserisci un nome tag prima di salvare.")
        elif existing_tag is None and not can_create_tag:
            st.error(f"⚠️ Hai raggiunto il limite massimo di {max_tags_allowed} tag.")
        elif len(selected_associazioni) > MAX_PRODOTTI_PER_TAG:
            st.error(f"⚠️ Hai selezionato più di {MAX_PRODOTTI_PER_TAG} descrizioni per questo tag.")
        elif existing_tag is not None:
            tag_id = int(existing_tag["id"])
            associazioni_correnti = tag_associazioni_map.get(tag_id, [])
            current_by_key = {
                assoc.get("descrizione_key"): assoc
                for assoc in associazioni_correnti
                if assoc.get("descrizione_key")
            }
            selected_by_key = {
                assoc.get("descrizione_key"): assoc
                for assoc in selected_associazioni
                if assoc.get("descrizione_key")
            }

            if len(selected_by_key) > MAX_PRODOTTI_PER_TAG:
                st.error(f"⚠️ Il tag supererebbe il limite di {MAX_PRODOTTI_PER_TAG} associazioni.")
            else:
                nuove_associazioni = [
                    assoc for key, assoc in selected_by_key.items()
                    if key not in current_by_key
                ]
                associazioni_da_rimuovere = [
                    assoc for key, assoc in current_by_key.items()
                    if key not in selected_by_key
                ]

                if nuove_associazioni:
                    aggiungi_associazioni(tag_id, nuove_associazioni, user_id=user_id)
                for assoc in associazioni_da_rimuovere:
                    rimuovi_associazione(int(assoc["id"]), user_id)

                st.session_state.ap_tag_selezionato_id = tag_id
                st.session_state.pop("ap_form_nome", None)
                st.session_state.ap_selected_descrizioni = {}
                for _key in list(st.session_state.keys()):
                    if str(_key).startswith("ap_chk_"):
                        st.session_state.pop(_key, None)
                clear_tags_cache()
                st.rerun()
        else:
            new_tag = crea_tag(
                user_id=user_id,
                ristorante_id=current_ristorante,
                nome=nome_tag,
                emoji=None,
                colore=CUSTOM_TAG_COLOR_DEFAULT,
            )
            if selected_associazioni:
                aggiungi_associazioni(int(new_tag["id"]), selected_associazioni, user_id=user_id)

            st.session_state.ap_tag_selezionato_id = int(new_tag["id"])
            st.session_state.pop("ap_form_nome", None)
            st.session_state.ap_selected_descrizioni = {}
            for _key in list(st.session_state.keys()):
                if str(_key).startswith("ap_chk_"):
                    st.session_state.pop(_key, None)
            clear_tags_cache()
            st.rerun()

    selected_tag_id = st.session_state.ap_tag_selezionato_id
    selected_tag = next((tag for tag in custom_tags if int(tag["id"]) == selected_tag_id), None)
    selected_tag_label = _tag_label(selected_tag) if selected_tag else ""
    selected_associazioni_correnti = tag_associazioni_map.get(selected_tag_id, []) if selected_tag_id else []


    st.markdown("<div style='margin-top: 1.2rem;'></div>", unsafe_allow_html=True)
    st.markdown('<h3 style="color:#1e40af; font-weight:700;">🔎 Cerca Prodotti da Fatture</h3>', unsafe_allow_html=True)

    df_descrizioni_source = df_all_cached
    if "Categoria" not in df_descrizioni_source.columns:
        df_descrizioni_source = df_descrizioni_source.assign(Categoria="")
    if "Fornitore" not in df_descrizioni_source.columns:
        df_descrizioni_source = df_descrizioni_source.assign(Fornitore="")
    if "Descrizione" in df_descrizioni_source.columns:
        df_descrizioni_source = df_descrizioni_source.assign(
            descrizione_key=df_descrizioni_source["Descrizione"].apply(_normalize_custom_tag_key)
        )
    else:
        df_descrizioni_source = df_descrizioni_source.assign(descrizione_key="")

    df_descrizioni_source = df_descrizioni_source.assign(
        Categoria=df_descrizioni_source["Categoria"].fillna("").astype(str).str.strip(),
        Fornitore=df_descrizioni_source["Fornitore"].fillna("").astype(str).str.strip(),
    )

    col_tipo, col_search_type, col_search = st.columns([2, 2, 3])

    with col_tipo:
        tipo_filtro = st.selectbox(
            "📦 Tipo Prodotti:",
            options=["Food & Beverage", "Spese Generali", "Tutti"],
            key="ap_tipo_filtro_prodotti",
            help="Filtra per tipologia di prodotto",
        )

    df_descrizioni_source = _apply_tipo_filtro(df_descrizioni_source, tipo_filtro)

    with col_search_type:
        search_type = st.selectbox(
            "🔍 Cerca per:",
            options=["Prodotto", "Categoria", "Fornitore"],
            key="ap_search_type",
        )

    with col_search:
        if search_type == "Prodotto":
            search_term = st.text_input(
                "🔍 Cerca nella descrizione:",
                placeholder="Es: pollo, salmone, caffè...",
                key="ap_search_prodotto_text",
            ).strip()
            if search_term:
                df_descrizioni_source = df_descrizioni_source[
                    df_descrizioni_source["Descrizione"].astype(str).str.contains(search_term, case=False, na=False)
                    | df_descrizioni_source["descrizione_key"].astype(str).str.contains(search_term, case=False, na=False)
                ].copy()
        elif search_type == "Categoria":
            categoria_options = ["— Tutte le categorie —"] + sorted(
                cat for cat in df_descrizioni_source["Categoria"].dropna().unique().tolist() if str(cat).strip()
            )
            categoria_sel = st.selectbox(
                "🔍 Cerca per categoria:",
                options=categoria_options,
                key="ap_search_prodotto_cat",
            )
            if categoria_sel != "— Tutte le categorie —":
                df_descrizioni_source = df_descrizioni_source[
                    df_descrizioni_source["Categoria"] == categoria_sel
                ].copy()
        else:
            fornitore_options = ["— Tutti i fornitori —"] + sorted(
                forn for forn in df_descrizioni_source["Fornitore"].dropna().unique().tolist() if str(forn).strip()
            )
            fornitore_sel = st.selectbox(
                "🔍 Cerca per fornitore:",
                options=fornitore_options,
                key="ap_search_prodotto_forn",
            )
            if fornitore_sel != "— Tutti i fornitori —":
                df_descrizioni_source = df_descrizioni_source[
                    df_descrizioni_source["Fornitore"] == fornitore_sel
                ].copy()

    filtered_keys = set(df_descrizioni_source["descrizione_key"].dropna().tolist())
    filtered_descrizioni = [
        row for row in descrizioni_distinte
        if row.get("descrizione_key") in filtered_keys
    ]

    col_sel_all, col_desel_all, col_info = st.columns([1.2, 1.2, 4])
    with col_sel_all:
        if st.button(
            "✅ Seleziona tutto",
            key="ap_btn_select_all_visible",
            use_container_width=True,
            disabled=not filtered_descrizioni,
        ):
            for row in filtered_descrizioni:
                descrizione_key = row["descrizione_key"]
                st.session_state.ap_selected_descrizioni[descrizione_key] = {
                    "descrizione": row["descrizione"],
                    "descrizione_key": descrizione_key,
                    "fattore_kg": None,
                }
                st.session_state[f"ap_chk_{descrizione_key}"] = True
            st.rerun()

    with col_desel_all:
        if st.button(
            "❌ Deseleziona tutto",
            key="ap_btn_deselect_all_visible",
            use_container_width=True,
            disabled=not filtered_descrizioni,
        ):
            for row in filtered_descrizioni:
                descrizione_key = row["descrizione_key"]
                st.session_state.ap_selected_descrizioni.pop(descrizione_key, None)
                st.session_state[f"ap_chk_{descrizione_key}"] = False
            st.rerun()

    with col_info:
        st.write("")

    if not filtered_descrizioni:
        st.info("📭 Nessun prodotto trovato con i filtri applicati.")
    else:
        with st.container(height=520, border=True):
            for idx, row in enumerate(filtered_descrizioni):
                descrizione_key = row["descrizione_key"]
                existing_selection = st.session_state.ap_selected_descrizioni
                is_selected = descrizione_key in existing_selection

                other_tags = [
                    entry["tag_label"]
                    for entry in descrizione_usage_map.get(descrizione_key, [])
                    if entry["tag_id"] != selected_tag_id
                ]

                checkbox_key = f"ap_chk_{descrizione_key}"
                if checkbox_key not in st.session_state:
                    st.session_state[checkbox_key] = is_selected

                col_check, col_main, col_meta = st.columns([0.6, 5, 2])
                with col_check:
                    checked = st.checkbox(
                        "Seleziona",
                        key=checkbox_key,
                        label_visibility="collapsed",
                    )
                with col_main:
                    st.markdown(f"**{row['descrizione']}**")
                    usage_notice = _build_usage_notice(other_tags, checked)
                    if usage_notice:
                        notice_level, notice_text = usage_notice
                        if notice_level == "warning":
                            st.warning(notice_text, icon="⚠️")
                        else:
                            st.caption(notice_text)
                with col_meta:
                    st.caption(
                        f"Occorrenze: {row['occorrenze']}  \n"
                        f"Fornitori: {row['num_fornitori']}  \n"
                        f"Ultima data: {row['ultima_data'] or '-'}"
                    )

                if checked:
                    st.session_state.ap_selected_descrizioni[descrizione_key] = {
                        "descrizione": row["descrizione"],
                        "descrizione_key": descrizione_key,
                        "fattore_kg": None,
                    }
                else:
                    st.session_state.ap_selected_descrizioni.pop(descrizione_key, None)

                if idx < len(filtered_descrizioni) - 1:
                    st.markdown("<hr style='margin: 0.35rem 0 0.75rem 0; border: none; border-top: 1px solid rgba(148, 163, 184, 0.35);'>", unsafe_allow_html=True)


    st.markdown("<div style='margin-top: 1.4rem;'></div>", unsafe_allow_html=True)
    st.markdown('<h3 style="color:#1e40af; font-weight:700;">🏷️ Gestione Tag</h3>', unsafe_allow_html=True)
    # stExpander Gestione Tag + ap_delete_box CSS ora in common.css
    if custom_tags:
        for tag in custom_tags:
            tag_id = int(tag["id"])
            tag_label = _tag_label(tag)
            associazioni_tag = tag_associazioni_map.get(tag_id, [])
            num_prodotti = len(associazioni_tag)

            col_expander, col_delete_tag = st.columns([6, 1])
            with col_expander:
                with st.expander(f"{tag_label} • {num_prodotti} prodotti associati", expanded=False):
                    if associazioni_tag:
                        for idx, assoc in enumerate(associazioni_tag):
                            col_assoc, col_remove = st.columns([6, 1])
                            with col_assoc:
                                st.markdown(f"- {assoc['descrizione']}")
                            with col_remove:
                                if st.button("Rimuovi", key=f"ap_remove_assoc_{assoc['id']}"):
                                    rimuovi_associazione(int(assoc["id"]), user_id)
                                    st.success("✅ Associazione rimossa.")
                                    st.rerun()

                            if idx < len(associazioni_tag) - 1:
                                st.markdown("<hr style='margin: 0.25rem 0 0.6rem 0; border: none; border-top: 1px solid rgba(148, 163, 184, 0.25);'>", unsafe_allow_html=True)
                    else:
                        st.info("📭 Nessun prodotto associato a questo tag.")

            with col_delete_tag:
                with st.container(key=f"ap_delete_box_{tag_id}"):
                    confirm_key = f"ap_confirm_delete_{tag_id}"
                    if st.session_state.get(confirm_key, False):
                        if st.button("⚠️ Conferma", key=f"ap_delete_tag_confirm_{tag_id}", use_container_width=True):
                            elimina_tag(tag_id, user_id)
                            if st.session_state.ap_tag_selezionato_id == tag_id:
                                st.session_state.ap_tag_selezionato_id = None
                            st.session_state.pop(confirm_key, None)
                            clear_tags_cache()
                            st.success("✅ Tag eliminato.")
                            st.rerun()
                    else:
                        if st.button("Elimina", key=f"ap_delete_tag_{tag_id}", use_container_width=True):
                            st.session_state[confirm_key] = True
                            st.rerun()
    else:
        st.info("📭 Nessun tag creato.")