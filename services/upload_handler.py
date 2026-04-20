"""Gestione elaborazione file caricati - deduplicazione, validazione, salvataggio."""

import streamlit as st
import pandas as pd
import time
import logging
import html as _html
from collections import Counter, defaultdict
from datetime import datetime, timezone

from config.constants import (
    TRUNCATE_DESC_LOG,
    TRUNCATE_ERROR_DISPLAY,
    MAX_FILES_PER_UPLOAD,
    MAX_UPLOAD_TOTAL_MB,
    BATCH_FILE_SIZE,
    BATCH_RATE_LIMIT_DELAY,
)

from utils.piva_validator import normalizza_piva
from utils.formatters import log_upload_event, get_nome_base_file, calcola_alert_data_consegna_td24
from utils.ristorante_helper import add_ristorante_filter

from services.ai_service import invalida_cache_memoria, mostra_loading_ai
from services.invoice_service import (
    estrai_dati_da_scontrino_vision,
    salva_fattura_processata,
    VisionDailyLimitExceededError,
)
from services.worker_client import parse_file_via_worker
from services.db_service import calcola_alert, carica_e_prepara_dataframe, clear_fatture_cache


logger = logging.getLogger("fci_app")


def _is_trial_invoice_date_allowed(data_documento: str, reference_date=None) -> bool:
    """Consente in trial fatture del mese corrente o del mese precedente."""
    if not data_documento or data_documento == 'N/A':
        return True

    try:
        _ref = pd.Timestamp(reference_date) if reference_date is not None else pd.Timestamp.now()
        _current_period = (_ref.year, _ref.month)
        _previous_ref = _ref.replace(day=1) - pd.Timedelta(days=1)
        _previous_period = (_previous_ref.year, _previous_ref.month)
        _dt = pd.to_datetime(data_documento)
        return (_dt.year, _dt.month) in {_current_period, _previous_period}
    except Exception:
        return True


def _make_problematic_upload_entry(file_name: str, reason: str, category: str) -> dict:
    return {
        'file_name': file_name,
        'reason': reason,
        'category': category,
    }


def _get_policy_block_kind(error_text: str) -> str | None:
    """Classifica i blocchi upload intenzionali per mostrare un messaggio corretto."""
    _err = str(error_text or '')
    if _err.startswith('ANNO PRECEDENTE'):
        return 'year'
    if _err.startswith('MESE PRECEDENTE'):
        return 'month'
    if _err.startswith('BLOCCO TRIAL'):
        return 'trial'
    return None


def _build_policy_block_messages(policy_blocks: dict) -> list[str]:
    """Costruisce i banner UI per i blocchi data intenzionali senza messaggi fuorvianti."""
    messages = []
    _now = pd.Timestamp.now()
    _current_year = _now.year

    if policy_blocks.get('year'):
        _n = len(policy_blocks['year'])
        _lbl = 'file ignorato' if _n == 1 else 'file ignorati'
        messages.append(
            f'<div style="padding:10px 16px;background:#fef9c3;border-left:5px solid #d97706;'
            f'border-radius:6px;margin-bottom:8px;">'
            f'<span style="font-size:0.88rem;font-weight:600;color:#92400e;">'
            f'📅 {_n} {_lbl} perché con data dell\'anno precedente — '
            f'è possibile caricare solo fatture dal 1 Gennaio {_current_year} in poi.'
            f'</span></div>'
        )

    if policy_blocks.get('month'):
        from config.constants import MESI_ITA as _MESI_MESI
        _n = len(policy_blocks['month'])
        _lbl = 'file ignorato' if _n == 1 else 'file ignorati'
        _mese_nome = _MESI_MESI[_now.month - 1]
        messages.append(
            f'<div style="padding:10px 16px;background:#fef9c3;border-left:5px solid #d97706;'
            f'border-radius:6px;margin-bottom:8px;">'
            f'<span style="font-size:0.88rem;font-weight:600;color:#92400e;">'
            f'📆 {_n} {_lbl} perché per questo account è attivo il blocco dei mesi precedenti — '
            f'sono consentite solo fatture di {_mese_nome} {_current_year}.'
            f'</span></div>'
        )

    if policy_blocks.get('trial'):
        from config.constants import MESI_ITA as _MESI_TRIAL
        _prev_month_ref = _now.replace(day=1) - pd.Timedelta(days=1)
        _allowed_labels = (
            f"{_MESI_TRIAL[_now.month - 1]} {_now.year} "
            f"oppure {_MESI_TRIAL[_prev_month_ref.month - 1]} {_prev_month_ref.year}"
        )
        _n = len(policy_blocks['trial'])
        _lbl = 'file ignorato' if _n == 1 else 'file ignorati'
        messages.append(
            f'<div style="padding:10px 16px;background:#fef9c3;border-left:5px solid #d97706;'
            f'border-radius:6px;margin-bottom:8px;">'
            f'<span style="font-size:0.88rem;font-weight:600;color:#92400e;">'
            f'🎟️ {_n} {_lbl} per data non consentita in prova gratuita — '
            f'puoi caricare fatture del mese corrente o del mese precedente ({_allowed_labels}).'
            f'</span></div>'
        )

    return messages


def _find_existing_saved_ok_events(supabase_client, user_id: str, ristorante_id: str, file_names: list[str]) -> dict:
    """Recupera upload già completati con successo per gli stessi file."""
    if supabase_client is None or not user_id or not file_names:
        return {}

    normalized_targets = {str(name).strip().lower() for name in file_names if name}
    raw_targets = [str(name).strip() for name in file_names if name]
    matches = {}

    try:
        query = (
            supabase_client.table("upload_events")
            .select("file_name, created_at, details")
            .eq("user_id", user_id)
            .eq("status", "SAVED_OK")
        )
        if raw_targets:
            query = query.in_("file_name", list(set(raw_targets)))

        response = query.execute()
        for row in response.data or []:
            file_name = str(row.get("file_name") or "").strip()
            if not file_name:
                continue

            key = file_name.lower()
            if key not in normalized_targets:
                continue

            details = row.get("details") or {}
            event_ristorante_id = details.get("ristorante_id") if isinstance(details, dict) else None
            same_ristorante = (
                not ristorante_id
                or not event_ristorante_id  # compatibilità con eventi legacy
                or str(event_ristorante_id) == str(ristorante_id)
            )
            if not same_ristorante:
                continue

            current = matches.get(key)
            if not current or str(row.get("created_at") or "") > str(current.get("created_at") or ""):
                matches[key] = row
    except Exception as e:
        logger.warning(f"Errore controllo upload_events SAVED_OK: {e}")

    return matches


def _format_saved_ok_date(created_at_value) -> str:
    try:
        return pd.to_datetime(created_at_value).strftime("%d/%m/%Y")
    except Exception:
        return "data sconosciuta"


def _duplicate_reason_for_ui(file_name: str, reasons_map: dict) -> str:
    reasons = reasons_map.get(file_name) or ["Già presente nel database"]
    if isinstance(reasons, list):
        reason_text = " — ".join(str(r) for r in reasons if r)
        return reason_text or "Già presente nel database"
    return str(reasons)


def _collect_post_upload_quality_checks(supabase_client, user_id: str, file_names: list[str], ristorante_id=None) -> dict:
    """Verifica post-upload: righe salvate, €0, needs_review e non categorizzate."""
    checks = {
        'checked_files': len(file_names or []),
        'rows_saved': 0,
        'zero_price_rows': 0,
        'needs_review_rows': 0,
        'uncategorized_rows': 0,
        'note_rows': 0,
        'verification_ok': False,
    }

    if supabase_client is None or not user_id or not file_names:
        return checks

    try:
        query = (
            supabase_client.table('fatture')
            .select('file_origine, prezzo_unitario, categoria, needs_review')
            .eq('user_id', user_id)
            .in_('file_origine', list({str(name).strip() for name in file_names if str(name).strip()}))
        )
        query = add_ristorante_filter(query, ristorante_id)
        response = query.execute()
        rows = response.data or []

        checks['rows_saved'] = len(rows)
        for row in rows:
            try:
                prezzo = float(row.get('prezzo_unitario') or 0)
            except (TypeError, ValueError):
                prezzo = 0.0
            categoria = str(row.get('categoria') or '').strip()

            if abs(prezzo) < 1e-9:
                checks['zero_price_rows'] += 1
            if bool(row.get('needs_review')):
                checks['needs_review_rows'] += 1
            if categoria == 'Da Classificare':
                checks['uncategorized_rows'] += 1
            if categoria == '📝 NOTE E DICITURE':
                checks['note_rows'] += 1

        checks['verification_ok'] = True
    except Exception as exc:
        checks['verification_error'] = str(exc)[:180]
        logger.warning(f"[UPLOAD VERIFY] Audit qualità post-upload fallito: {exc}")

    return checks


def handle_uploaded_files(uploaded_files, supabase, user_id):
    """Gestisce l'elaborazione completa dei file caricati: deduplicazione, validazione, salvataggio."""
    # [DEBUG]
    t0_upload = time.perf_counter()
    # Pulisci messaggi precedenti all'inizio di un nuovo caricamento
    st.session_state.upload_messages = []
    st.session_state.pop('last_upload_notification_context', None)
    # 🚫 BLOCCO POST-DELETE: Se c'è flag force_empty, ignora file caricati
    if st.session_state.get('force_empty_until_upload', False):
        st.warning("⚠️ **Hai appena eliminato tutte le fatture.** Clicca su 'Ripristina upload' prima di caricare nuovi file.")
        st.info("💡 Usa il pulsante '🔄 Ripristina upload' sopra per sbloccare il caricamento.")
        st.stop()  # Blocca esecuzione per evitare ricaricamento automatico
    
    # 🔒 RATE LIMIT UPLOAD: max file e dimensione totale
    if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
        # Reset file uploader per evitare accumulo file tra tentativi
        st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
        st.session_state['_upload_limit_error'] = f"⚠️ Puoi caricare al massimo **{MAX_FILES_PER_UPLOAD} file** per volta. Hai selezionato {len(uploaded_files)} file."
        st.rerun()
    
    _total_upload_bytes = sum(f.size for f in uploaded_files)
    _max_upload_bytes = MAX_UPLOAD_TOTAL_MB * 1024 * 1024
    if _total_upload_bytes > _max_upload_bytes:
        _total_mb = _total_upload_bytes / (1024 * 1024)
        # Reset file uploader per evitare accumulo file tra tentativi
        st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
        st.session_state['_upload_limit_error'] = f"⚠️ Dimensione totale troppo grande: **{_total_mb:.0f} MB** (max {MAX_UPLOAD_TOTAL_MB} MB). Riduci il numero di file."
        st.rerun()
    
    # 🚀 PROGRESS BAR IMMEDIATA: Mostra subito che stiamo lavorando
    upload_placeholder = st.empty()
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text(f"🔍 Analisi di {len(uploaded_files)} file in corso...")
    
    # QUERY FILE GIÀ CARICATI SU SUPABASE (con filtro userid obbligatorio)
    file_su_supabase = set()
    file_su_supabase_full = set()
    try:
        # Verifica user_id disponibile (usa il parametro passato, non rileggere da session)
        user_data = st.session_state.get('user_data', {})
        if not user_id:
            logger.error("❌ user_id mancante in session_state durante query file")
            file_su_supabase = set()
        else:
            ristorante_id = st.session_state.get('ristorante_id')
            
            # ⚠️ Controllo: ristorante_id DEVE essere presente
            if not ristorante_id:
                logger.warning(f"⚠️ ristorante_id mancante per user {user_id} - rischio falsi positivi cross-ristorante")
            
            # Tentativo 1: Usa RPC function se disponibile (query aggregata SQL lato server)
            try:
                # 🔧 RPC con filtro multi-ristorante
                rpc_params = {'p_user_id': user_id}
                if ristorante_id:
                    rpc_params['p_ristorante_id'] = ristorante_id
                response_rpc = supabase.rpc('get_distinct_files', rpc_params).execute()
                # Tieni i nomi COMPLETI (con estensione) dal DB per confronto primario
                file_su_supabase_full = {row["file_origine"].strip().lower()
                                        for row in response_rpc.data 
                                        if row.get("file_origine") and row["file_origine"].strip()}
                # Nomi base (senza estensione) per confronto secondario XML/PDF
                file_su_supabase = {get_nome_base_file(row["file_origine"]) 
                                   for row in response_rpc.data 
                                   if row.get("file_origine") and row["file_origine"].strip()}
                logger.info(f"🔍 Query file DB: ristorante_id={ristorante_id}, trovati {len(file_su_supabase_full)} file distinti")
                    
            except Exception as rpc_error:
                # Fallback: Query normale ma ottimizzata CON PAGINAZIONE
                logger.warning(f"RPC function non disponibile, uso query normale con paginazione: {rpc_error}")
                
                file_su_supabase = set()
                file_su_supabase_full = set()
                page = 0
                page_size = 1000
                max_pages = 100  # Safety guard: max 100k righe
                
                while page < max_pages:
                    try:
                        offset = page * page_size
                        query_files = (
                            supabase.table("fatture")
                            .select("file_origine", count="exact")
                            .eq("user_id", user_id)
                        )
                        if ristorante_id:
                            query_files = query_files.eq("ristorante_id", ristorante_id)
                        response = query_files.range(offset, offset + page_size - 1).execute()
                        
                        if not response.data:
                            break
                            
                        for row in response.data:
                            if row.get("file_origine") and row["file_origine"].strip():
                                file_su_supabase_full.add(row["file_origine"].strip().lower())
                                file_su_supabase.add(get_nome_base_file(row["file_origine"]))
                        
                        if len(response.data) < page_size:
                            break
                            
                        page += 1
                        
                    except Exception as page_error:
                        logger.error(f"Errore paginazione pagina {page}: {page_error}")
                        break
                
                logger.info(f"🔍 Query file DB (fallback): ristorante_id={ristorante_id}, trovati {len(file_su_supabase_full)} file distinti")
        
        # 🔍 VERIFICA COERENZA: Se DB è vuoto ma session ha file, è un errore -> reset
        if len(file_su_supabase) == 0 and len(st.session_state.files_processati_sessione) > 0:
            logger.warning(f"⚠️ INCOERENZA RILEVATA: DB vuoto ma session ha {len(st.session_state.files_processati_sessione)} file -> RESET")
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
        
    except Exception as e:
        logger.exception(f"Errore caricamento file da DB per user_id={user_id}")
        logger.error(f"Errore caricamento file da DB: {e}")
        st.error("❌ Errore nel caricamento dei dati. Riprova.")
        file_su_supabase = set()
        file_su_supabase_full = set()


    # Calcola nomi caricati e duplicati in modo robusto
    uploaded_names = [f.name for f in uploaded_files]
    uploaded_unique = set(uploaded_names)
    uploaded_name_counts = Counter(uploaded_names)
    duplicate_in_selection = sorted([
        fname for fname, count in uploaded_name_counts.items()
        if count > 1
    ])
    duplicate_count = max(0, len(uploaded_names) - len(uploaded_unique))

    # Ricostruisci liste coerenti con i nomi unici
    visti = set()
    file_unici = []
    for file in uploaded_files:
        if file.name not in visti:
            file_unici.append(file)
            visti.add(file.name)
    
    # ============================================================
    # FIX: DEDUPLICAZIONE CORRETTA (solo contro DB reale)
    # ============================================================
    # Assicura che file_su_supabase_full esista (già inizializzato prima del try)
    
    file_nuovi = []
    file_gia_processati = []
    file_gia_processati_reason = {}
    
    just_uploaded = st.session_state.get('just_uploaded_files', set())
    force_reimport_all = bool(st.session_state.get('force_reimport_upload', False))
    force_reimport_files = {
        str(name).strip().lower()
        for name in st.session_state.get('force_reimport_files', set())
        if name
    }
    existing_saved_ok_events = _find_existing_saved_ok_events(
        supabase,
        user_id,
        st.session_state.get('ristorante_id'),
        [f.name for f in file_unici],
    )
    
    for file in file_unici:
        filename = file.name
        filename_lower = filename.strip().lower()
        nome_base = get_nome_base_file(filename)
        is_force_reimport = (
            force_reimport_all
            or filename_lower in force_reimport_files
            or nome_base in force_reimport_files
        )
        existing_saved_ok = existing_saved_ok_events.get(filename_lower)
        
        # ── Confronto a 2 livelli ──────────────────────────────────
        # 1° LIVELLO: upload già confermato via upload_events
        # 2° LIVELLO: match ESATTO sul nome file completo nel DB
        # 3° LIVELLO: match sul nome base senza estensione
        is_exact_match = filename_lower in file_su_supabase_full
        is_base_match = nome_base in file_su_supabase
        is_just_uploaded = nome_base in just_uploaded
        
        if existing_saved_ok and not is_force_reimport:
            file_gia_processati.append(filename)
            imported_at_label = _format_saved_ok_date(existing_saved_ok.get('created_at'))
            reason = [
                f"File già importato il {imported_at_label}",
                "usare 'Reimporta' per forzare l'aggiornamento",
            ]
            file_gia_processati_reason[filename] = reason.copy()
            logger.info(f"📋 SKIP '{filename}' → upload_events SAVED_OK del {imported_at_label}")
        elif is_exact_match or is_base_match or is_just_uploaded:
            file_gia_processati.append(filename)
            # Log dettagliato per diagnosi
            reason = []
            if is_exact_match:
                reason.append('nome esatto in DB')
            if is_base_match and not is_exact_match:
                reason.append(f'nome base "{nome_base}" in DB')
            if is_just_uploaded:
                reason.append('appena caricato')
            file_gia_processati_reason[filename] = reason.copy()
            logger.info(f"📋 SKIP '{filename}' → {', '.join(reason)}")
        # Protezione: Salta file che hanno già dato errore in questa sessione
        elif filename in st.session_state.get('files_con_errori', set()):
            continue
        else:
            if is_force_reimport:
                logger.info(f"🔄 Reimport forzato consentito per '{filename}'")
            file_nuovi.append(file)    
    logger.info(
        f"📊 Dedup risultato: {len(file_nuovi)} nuovi, {len(file_gia_processati)} già presenti, "
        f"{duplicate_count} duplicati upload ({len(duplicate_in_selection)} nomi duplicati nella selezione)"
    )

    # Log duplicati intra-selezione (stesso nome file selezionato più volte nello stesso upload)
    if duplicate_in_selection:
        try:
            _uid = st.session_state.user_data.get('id', '')
            _email = st.session_state.user_data.get('email', 'unknown')
            for _fname in duplicate_in_selection:
                _extra_count = max(1, uploaded_name_counts.get(_fname, 1) - 1)
                log_upload_event(
                    user_id=_uid,
                    user_email=_email,
                    file_name=_fname,
                    status='DUPLICATE_IN_SELECTION',
                    details={
                        'source': 'manual_upload',
                        'reason': 'in_selection',
                        'duplicates_extra_count': _extra_count,
                    },
                    supabase_client=supabase,
                )
        except Exception as _log_ex:
            logger.warning(f"Errore logging duplicate in selection: {_log_ex}")
    
    # Log file scartati come DUPLICATE_SKIPPED (solo quelli già nel DB, non appena caricati in sessione)
    if file_gia_processati:
        try:
            _uid = st.session_state.user_data.get('id', '')
            _email = st.session_state.user_data.get('email', 'unknown')
            for _fname in file_gia_processati:
                _is_session_duplicate = get_nome_base_file(_fname) in just_uploaded
                if not _is_session_duplicate:
                    log_upload_event(
                        user_id=_uid,
                        user_email=_email,
                        file_name=_fname,
                        status='DUPLICATE_SKIPPED',
                        details={
                            'source': 'manual_upload',
                            'ristorante_id': st.session_state.get('ristorante_id'),
                            'reason': 'already_in_db',
                            'dedup_reason': file_gia_processati_reason.get(_fname, []),
                        },
                        supabase_client=supabase
                    )
                else:
                    log_upload_event(
                        user_id=_uid,
                        user_email=_email,
                        file_name=_fname,
                        status='DUPLICATE_SKIPPED',
                        details={
                            'source': 'manual_upload',
                            'ristorante_id': st.session_state.get('ristorante_id'),
                            'reason': 'already_in_session',
                            'dedup_reason': file_gia_processati_reason.get(_fname, []),
                        },
                        supabase_client=supabase
                    )
        except Exception as _log_ex:
            logger.warning(f"Errore logging duplicate skip: {_log_ex}")
    
    # Messaggio SOLO per ADMIN (interfaccia pulita per clienti)
    is_admin = st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False)
    file_blocchi_formato_trial = []

    # ============================================================
    # LIMITI TRIAL: max 50 file, solo XML/P7M
    # ============================================================
    if not is_admin:
        _trial_limits = st.session_state.get('trial_info', {})
        if _trial_limits.get('is_trial'):
            _TRIAL_MAX_FILES = 50
            _TRIAL_ALLOWED_EXT = ('.xml', '.p7m')

            # 1) Filtra e rimuovi PDF / immagini dalla lista dei file nuovi
            _file_nuovi_bloccati = [
                f for f in file_nuovi
                if not f.name.lower().endswith(_TRIAL_ALLOWED_EXT)
            ]
            if _file_nuovi_bloccati:
                file_blocchi_formato_trial = [f.name for f in _file_nuovi_bloccati]
                _uid_tl = st.session_state.get('user_data', {}).get('id', '')
                _email_tl = st.session_state.get('user_data', {}).get('email', 'unknown')
                for _bf in _file_nuovi_bloccati:
                    logger.warning(
                        f"🎟️ TRIAL BLOCCO FORMATO {_bf.name} — "
                        f"user={_email_tl} (solo XML/P7M consentiti)"
                    )
                    log_upload_event(
                        user_id=_uid_tl, user_email=_email_tl,
                        file_name=_bf.name, status='TRIAL_FORMAT_BLOCKED',
                        details={'source': 'manual_upload'},
                        supabase_client=supabase
                    )
                file_nuovi = [
                    f for f in file_nuovi
                    if f.name.lower().endswith(_TRIAL_ALLOWED_EXT)
                ]
                _bloccati_nomi = ', '.join(f.name for f in _file_nuovi_bloccati)
                st.warning(
                    f"🎟️ **Prova gratuita — Solo XML/P7M consentiti.** "
                    f"File ignorati: {_bloccati_nomi}"
                )

            # 2) Blocca se superano il limite di 50 file
            if len(file_nuovi) > _TRIAL_MAX_FILES:
                _uid_tl = st.session_state.get('user_data', {}).get('id', '')
                _email_tl = st.session_state.get('user_data', {}).get('email', 'unknown')
                logger.warning(
                    f"🎟️ TRIAL BLOCCO LIMITE {len(file_nuovi)} file — user={_email_tl}"
                )
                st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
                st.session_state['_upload_limit_error'] = (
                    f"⏳ **Prova gratuita: massimo {_TRIAL_MAX_FILES} file per volta.** "
                    f"Hai selezionato {len(file_nuovi)} file XML/P7M validi."
                )
                st.rerun()

    # Salva riferimento a just_uploaded PRIMA di pulirlo
    erano_just_uploaded = just_uploaded.copy() if just_uploaded else set()
    
    # Sopprimi messaggi se arriviamo da AVVIA AI (flag one-shot)
    if st.session_state.get('suppress_upload_messages_once', False):
        st.session_state.suppress_upload_messages_once = False
    
    # ✅ Pulizia flag just_uploaded
    if erano_just_uploaded:
        st.session_state.just_uploaded_files = set()
    
    # ============================================================
    # ELABORAZIONE FILE NUOVI (solo se ci sono)
    # ============================================================
    
    # Riepilogo base per questa selezione (aggiornato dopo l'elaborazione)
    upload_summary = {
        'totale_selezionati': len(uploaded_names),
        'gia_presenti': len({n for n in uploaded_unique if (get_nome_base_file(n) in file_su_supabase or get_nome_base_file(n) in erano_just_uploaded)}),
        'duplicati_upload': duplicate_count,
        'nuovi_da_elaborare': len(file_nuovi),
        'caricate_successo': 0,
        'errori': 0
    }
    
    if file_nuovi:
        # Aggiorna progress bar: inizio elaborazione
        status_text.text(f"📄 Elaborazione {len(file_nuovi)} fatture...")
        
        # Contatori per statistiche DETTAGLIATE
        file_processati = 0
        righe_batch = 0
        salvati_supabase = 0
        salvati_json = 0
        errori = []
        file_ok = []
        file_note_credito = []
        td24_date_alerts = []  # TD24: tracking copertura data_consegna
        file_errore = {}
        file_blocchi_policy = {'year': [], 'month': [], 'trial': []}  # blocchi data intenzionali
        
        try:
            # Mostra animazione AI
            mostra_loading_ai(upload_placeholder, f"Analisi AI di {len(file_nuovi)} Fatture")
            
            total_files = len(file_nuovi)
            
            # ============================================================
            # BATCH PROCESSING - 20 file alla volta (evita memoria piena)
            # ============================================================
            BATCH_SIZE = BATCH_FILE_SIZE  # Usa costante definita sopra (20)
            
            # Loop batch invisibile
            for batch_start in range(0, total_files, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_files)
                batch_corrente = file_nuovi[batch_start:batch_end]
                
                # Elabora file nel batch corrente
                for idx_in_batch, file in enumerate(batch_corrente):
                    idx_globale = batch_start + idx_in_batch + 1
                    nome_file = file.name.lower()
                    
                    # Protezione loop: salta file già elaborati o con errori
                    if file.name in st.session_state.files_processati_sessione:
                        continue
                    
                    # 🔥 FIX BUG #3: Se file è in errori, skippa senza aggiungere a file_errore
                    # (errore già presente in files_errori_report, evita duplicati)
                    if file.name in st.session_state.get('files_con_errori', set()):
                        continue
                    
                    # Aggiorna progress GLOBALE
                    progress = idx_globale / total_files
                    progress_bar.progress(progress)
                    status_text.text(f"📄 Elaborazione {idx_globale}/{total_files}: {file.name[:TRUNCATE_DESC_LOG]}...")
                    
                    # Routing automatico per tipo file con TRY/EXCEPT ROBUSTO
                    try:
                        # ⚡ Validazione dimensione file (0-byte / file vuoti)
                        file_content = file.getvalue()
                        if not file_content or len(file_content) == 0:
                            raise ValueError(f"File vuoto (0 byte): {file.name}")
                        file.seek(0)  # Reset posizione dopo getvalue()
                        
                        # 🔒 Validazione magic bytes (verifica contenuto reale vs estensione)
                        _ext = nome_file.rsplit('.', 1)[-1].lower() if '.' in nome_file else ''
                        _magic_ok = False
                        if _ext == 'xml':
                            # XML: deve iniziare con <?xml o tag FatturaElettronica (BOM UTF-8 opzionale)
                            _head = file_content[:200].lstrip(b'\xef\xbb\xbf')  # strip BOM
                            _head_stripped = _head.lstrip()
                            _magic_ok = _head_stripped.startswith(b'<?xml') or b'<' in _head_stripped[:10] and b'FatturaElettronica' in _head[:500]
                        elif _ext == 'p7m':
                            # P7M: DER binary (0x30) oppure PEM/base64 (testo ASCII)
                            _raw_start = file_content[:20].decode('ascii', errors='ignore').strip()
                            _magic_ok = (
                                len(file_content) > 2 and file_content[0:1] == b'\x30'
                            ) or (
                                len(file_content) > 10 and
                                any(_raw_start.startswith(p) for p in ('MIIF', 'MIIE', 'MIIG', 'MIIB', 'MIIA', '-----'))
                            )
                        elif _ext == 'pdf':
                            _magic_ok = file_content[:5] == b'%PDF-'
                        elif _ext in ('jpg', 'jpeg'):
                            _magic_ok = file_content[:2] == b'\xff\xd8'
                        elif _ext == 'png':
                            _magic_ok = file_content[:4] == b'\x89PNG'
                        
                        if not _magic_ok:
                            raise ValueError(f"Il contenuto del file non corrisponde all'estensione .{_ext}")
                        
                        if nome_file.endswith(('.xml', '.p7m')):
                            items = parse_file_via_worker(file, nome_file, user_id=user_id)
                        elif nome_file.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                            items = estrai_dati_da_scontrino_vision(file)
                        else:
                            raise ValueError("Formato non supportato")
                        
                        # Validazione risultato parsing
                        if items is None:
                            raise ValueError("Parsing ritornato None")
                        if len(items) == 0:
                            raise ValueError("Nessuna riga estratta - DataFrame vuoto")
                        
                        # ============================================================
                        # VALIDAZIONE P.IVA CESSIONARIO (Anti-abuso)
                        # ═══════════════════════════════════════════════════════════════
                        # VALIDAZIONE P.IVA MULTI-RISTORANTE
                        # Applicata solo a XML e PDF (NON a immagini)
                        # ═══════════════════════════════════════════════════════════════
                        # ⚠️ SKIP anche per immagini JPG/PNG (solo XML e PDF)
                        is_image = nome_file.endswith(('.jpg', '.jpeg', '.png'))
                        # Admin PURO (non in impersonificazione) salta il check P.IVA
                        # perché opera sul proprio pannello e non su un profilo cliente.
                        # Admin in IMPERSONIFICAZIONE deve rispettare la P.IVA del cliente
                        # (carica sul suo profilo → stesse regole del cliente).
                        is_admin_puro = st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False)
                        
                        if not is_admin_puro and not is_image:
                            # Estrai P.IVA dal cessionario (dalla prima riga - items è lista di dict)
                            piva_cessionario = None
                            if isinstance(items, list) and len(items) > 0:
                                piva_cessionario = items[0].get('piva_cessionario')
                            elif isinstance(items, dict):
                                piva_cessionario = items.get('piva_cessionario')
                            
                            # P.IVA ristorante ATTUALMENTE SELEZIONATO (multi-ristorante aware)
                            piva_attiva = st.session_state.get('partita_iva')
                            
                            logger.info(f"🔍 Validazione P.IVA {file.name} - rist_id={st.session_state.get('ristorante_id')}{' [impersonating]' if st.session_state.get('impersonating') else ''}")
                            
                            # ✅ CASO 2: P.IVA presente → VALIDAZIONE STRICT MULTI-RISTORANTE
                            if piva_attiva and piva_cessionario:
                                piva_cessionario_norm = normalizza_piva(piva_cessionario)
                                piva_attiva_norm = normalizza_piva(piva_attiva)
                                
                                if piva_cessionario_norm != piva_attiva_norm:
                                    # 🚫 BLOCCO: P.IVA non corrisponde al ristorante selezionato
                                    logger.warning(
                                        f"⚠️ UPLOAD BLOCCATO {file.name} - user_id={st.session_state.get('user_data', {}).get('id')} "
                                        f"P.IVA mismatch (rist_id={st.session_state.get('ristorante_id')})"
                                        f"{' [impersonating]' if st.session_state.get('impersonating') else ''}"
                                    )
                                    raise ValueError("🚫 FATTURA NON VALIDA - P.IVA FATTURA DIVERSA DA P.IVA AZIENDA")
                                else:
                                    # ✅ P.IVA match: log successo
                                    logger.info(f"✅ Validazione OK: P.IVA match per rist_id={st.session_state.get('ristorante_id')}")
                        
                        else:
                            # Admin PURO (non in impersonificazione): log per debug, bypass validazione
                            piva_cessionario = None
                            if isinstance(items, list) and len(items) > 0:
                                piva_cessionario = items[0].get('piva_cessionario')
                            logger.debug(f"👨‍💼 Admin puro upload {file.name} - P.IVA fattura: {piva_cessionario} (validazione bypassata)")
                        
                        # ============================================================
                        # BLOCCO FATTURE ANNO PRECEDENTE (per clienti non-admin)
                        # ============================================================
                        # Se il flag blocco_anno_precedente è attivo in pagine_abilitate,
                        # impedisci caricamento fatture con data_documento < 1 Gennaio anno corrente.
                        # Admin e impersonificati bypassano sempre.
                        if not is_admin:
                            _pagine_cfg = st.session_state.get('user_data', {}).get('pagine_abilitate') or {}
                            if _pagine_cfg.get('blocco_anno_precedente', True):
                                _data_doc = None
                                if isinstance(items, list) and len(items) > 0:
                                    _data_doc = items[0].get('Data_Documento') or items[0].get('data_documento')
                                if _data_doc and _data_doc != 'N/A':
                                    try:
                                        _dt_doc = pd.to_datetime(_data_doc)
                                        _anno_corrente = pd.Timestamp.now().year
                                        if _dt_doc.year < _anno_corrente:
                                            logger.warning(
                                                f"📅 UPLOAD BLOCCATO {file.name} - Data {_data_doc} precedente al {_anno_corrente} "
                                                f"(user: {st.session_state.get('user_data', {}).get('email')})"
                                            )
                                            raise ValueError(
                                                f"ANNO PRECEDENTE - La data documento ({_data_doc}) è precedente al "
                                                f"1 Gennaio {_anno_corrente}. È possibile caricare solo fatture dell'anno corrente."
                                            )
                                    except ValueError:
                                        raise
                                    except Exception:
                                        pass  # Se la data non è parsabile, lascia passare

                        # ============================================================
                        # BLOCCO MESI PRECEDENTI ANNO CORRENTE (per clienti non-admin)
                        # ============================================================
                        # Se il flag blocco_mesi_precedenti è attivo in pagine_abilitate,
                        # impedisci caricamento fatture con mese < mese corrente (stesso anno).
                        # Admin e impersonificati bypassano sempre. I trial seguono una
                        # policy dedicata e possono caricare anche il mese precedente.
                        _trial_upload = st.session_state.get('trial_info', {})
                        if not is_admin and not _trial_upload.get('is_trial'):
                            _pagine_cfg_mesi = st.session_state.get('user_data', {}).get('pagine_abilitate') or {}
                            if _pagine_cfg_mesi.get('blocco_mesi_precedenti', False):
                                _data_doc_mesi = None
                                if isinstance(items, list) and len(items) > 0:
                                    _data_doc_mesi = items[0].get('Data_Documento') or items[0].get('data_documento')
                                if _data_doc_mesi and _data_doc_mesi != 'N/A':
                                    try:
                                        _dt_doc_mesi = pd.to_datetime(_data_doc_mesi)
                                        _now_mesi = pd.Timestamp.now()
                                        if _dt_doc_mesi.year == _now_mesi.year and _dt_doc_mesi.month < _now_mesi.month:
                                            from config.constants import MESI_ITA as _MESI_BLK
                                            _mese_nome = _MESI_BLK[_now_mesi.month - 1]
                                            logger.warning(
                                                f"📅 UPLOAD BLOCCATO MESE PRECEDENTE {file.name} - Data {_data_doc_mesi} "
                                                f"precedente a {_mese_nome} {_now_mesi.year} "
                                                f"(user: {st.session_state.get('user_data', {}).get('email')})"
                                            )
                                            raise ValueError(
                                                f"MESE PRECEDENTE \u2014 La data documento ({_data_doc_mesi}) è precedente al "
                                                f"mese corrente ({_mese_nome} {_now_mesi.year}). "
                                                f"È possibile caricare solo fatture del mese in corso."
                                            )
                                    except ValueError:
                                        raise
                                    except Exception:
                                        pass  # Se la data non è parsabile, lascia passare

                        # ============================================================
                        # BLOCCO TRIAL: consenti mese corrente e mese precedente
                        # ============================================================
                        if not is_admin and _trial_upload.get('is_trial'):
                            _t_now_trial = pd.Timestamp.now()
                            _prev_month_ref = _t_now_trial.replace(day=1) - pd.Timedelta(days=1)
                            from config.constants import MESI_ITA as _MESI
                            _allowed_labels = (
                                f"{_MESI[_t_now_trial.month - 1]} {_t_now_trial.year} "
                                f"oppure {_MESI[_prev_month_ref.month - 1]} {_prev_month_ref.year}"
                            )
                            _data_trial = None
                            if isinstance(items, list) and len(items) > 0:
                                _data_trial = (
                                    items[0].get('Data_Documento')
                                    or items[0].get('data_documento')
                                )
                            if _data_trial and _data_trial != 'N/A':
                                try:
                                    if not _is_trial_invoice_date_allowed(_data_trial, reference_date=_t_now_trial):
                                        logger.warning(
                                            f"🎟️ UPLOAD BLOCCATO TRIAL {file.name} - "
                                            f"Data {_data_trial} fuori finestra consentita ({_allowed_labels}) "
                                            f"(user: {st.session_state.get('user_data', {}).get('email')})"
                                        )
                                        raise ValueError(
                                            f"BLOCCO TRIAL \u2014 Durante la prova gratuita puoi caricare "
                                            f"fatture del mese corrente o del mese precedente "
                                            f"({_allowed_labels}). La fattura ha data {_data_trial}."
                                        )
                                except ValueError:
                                    raise
                                except Exception:
                                    pass  # Data non parsabile: lascia passare
                        
                        # Salva in memoria se trovati dati (SILENZIOSO)
                        result = salva_fattura_processata(
                            file.name, items, silent=True,
                            ristoranteid=st.session_state.get('ristorante_id')
                        )
                        
                        if result["success"]:
                            file_processati += 1
                            righe_batch += result["righe"]
                            if result["location"] == "supabase":
                                salvati_supabase += 1
                            elif result["location"] == "json":
                                salvati_json += 1
                            
                            # Rimuovi flag force empty: ci sono nuovi dati
                            if 'force_empty_until_upload' in st.session_state:
                                del st.session_state.force_empty_until_upload
                            
                            # Traccia successo (aggiungi sia nome completo che base normalizzato)
                            file_ok.append(file.name)
                            # Rileva nota di credito (TD04)
                            if isinstance(items, list) and len(items) > 0:
                                if str(items[0].get('tipo_documento', '')).upper().strip() == 'TD04':
                                    file_note_credito.append(file.name)
                                # Rileva TD24 e calcola copertura data_consegna
                                _td24_alert = calcola_alert_data_consegna_td24(items)
                                if _td24_alert and _td24_alert['status'] != 'ok':
                                    td24_date_alerts.append({
                                        'file_name': file.name,
                                        'fornitore': str(items[0].get('Fornitore', 'Sconosciuto')),
                                        'status': _td24_alert['status'],
                                        'lines_total': _td24_alert['lines_total'],
                                        'lines_with_date': _td24_alert['lines_with_date'],
                                        'pct': _td24_alert['pct'],
                                    })
                            st.session_state.files_processati_sessione.add(file.name)
                            # Aggiungi anche nome base per prevenire duplicati con estensione diversa
                            st.session_state.files_processati_sessione.add(get_nome_base_file(file.name))
                            
                            # 🔥 FIX BUG #1: Rimuovi da files_con_errori se presente (file ora ha successo)
                            st.session_state.files_con_errori.discard(file.name)
                        else:
                            raise ValueError(f"Errore salvataggio: {result.get('error', 'Sconosciuto')}")
                    
                    except VisionDailyLimitExceededError as e:
                        quota_msg = str(e)
                        logger.warning(f"🚫 File scartato per quota Vision esaurita: {file.name} — {quota_msg}")
                        file_errore[file.name] = quota_msg
                        st.session_state.files_errori_report[file.name] = quota_msg
                        try:
                            log_upload_event(
                                user_id=st.session_state.user_data.get("id"),
                                user_email=st.session_state.user_data.get("email", "unknown"),
                                file_name=file.name,
                                status="VISION_LIMIT_REACHED",
                                rows_parsed=0,
                                rows_saved=0,
                                error_stage="VISION",
                                error_message=quota_msg[:150],
                                details={"source": "manual_upload", "exception_type": type(e).__name__},
                                supabase_client=supabase,
                            )
                        except Exception as log_error:
                            logger.warning(f"Errore logging vision limit event: {log_error}")
                        continue

                    except Exception as e:
                        # TRACCIA ERRORE DETTAGLIATO (silenzioso - solo log)
                        full_error = str(e)

                        # ============================================================
                        # Blocchi policy su data upload NON sono errori tecnici.
                        # Li separiamo per tipo, con messaggi coerenti e logging audit.
                        # ============================================================
                        _policy_block_kind = _get_policy_block_kind(full_error)
                        if _policy_block_kind:
                            file_blocchi_policy[_policy_block_kind].append(file.name)
                            try:
                                _status_map = {
                                    'year': 'YEAR_BLOCKED',
                                    'month': 'MONTH_BLOCKED',
                                    'trial': 'TRIAL_DATE_BLOCKED',
                                }
                                log_upload_event(
                                    user_id=st.session_state.user_data.get("id"),
                                    user_email=st.session_state.user_data.get("email", "unknown"),
                                    file_name=file.name,
                                    status=_status_map[_policy_block_kind],
                                    rows_parsed=0,
                                    rows_saved=0,
                                    details={
                                        "source": "manual_upload",
                                        "policy_block": _policy_block_kind,
                                        "policy_error": full_error[:250],
                                    },
                                    supabase_client=supabase,
                                )
                            except Exception as _policy_log_error:
                                logger.warning(f"Errore logging policy block {file.name}: {_policy_log_error}")
                            continue  # Non aggiungere a file_errore né a files_con_errori

                        error_msg = full_error[:TRUNCATE_ERROR_DISPLAY] + ("..." if len(full_error) > TRUNCATE_ERROR_DISPLAY else "")
                        logger.exception(f"❌ Errore elaborazione {file.name}: {full_error}")
                        file_errore[file.name] = error_msg
                        errori.append(f"{file.name}: {error_msg}")
                        
                        # NON mostrare errore qui (evita duplicati) - verrà mostrato nel report finale
                        
                        # ============================================================
                        # 🔥 FIX BUG #2: NON aggiungere a files_processati_sessione
                        # altrimenti il file viene skippato per sempre e non può riprovare
                        # ============================================================
                        # st.session_state.files_processati_sessione.add(file.name)  # ❌ RIMOSSO
                        
                        st.session_state.files_con_errori.add(file.name)
                        
                        # Salva anche in report persistente (per mostrarlo dopo download)
                        st.session_state.files_errori_report[file.name] = error_msg
                        
                        # Log upload event FAILED
                        try:
                            user_id = st.session_state.user_data.get("id")
                            user_email = st.session_state.user_data.get("email", "unknown")
                            error_stage = "PARSING" if file.name.endswith(('.xml', '.p7m')) else "VISION"
                            
                            log_upload_event(
                                user_id=user_id,
                                user_email=user_email,
                                file_name=file.name,
                                status="FAILED",
                                rows_parsed=0,
                                rows_saved=0,
                                error_stage=error_stage,
                                error_message=error_msg,
                                details={"source": "manual_upload", "exception_type": type(e).__name__},
                                supabase_client=supabase
                            )
                        except Exception as log_error:
                            logger.error(f"Errore logging failed event: {log_error}")
                        
                        # CONTINUA con il prossimo file invece di crashare
                        continue
                
                # ============================================================
                # PAUSA TRA BATCH (rate limit OpenAI + liberazione memoria)
                # ============================================================
                if batch_end < total_files:
                    time.sleep(BATCH_RATE_LIMIT_DELAY)  # Pausa tra batch per evitare rate limit
        
        except Exception as critical_error:
            # ERRORE CRITICO: logga e aggiunge agli errori invece di fermare tutto
            logger.exception(f"❌ ERRORE CRITICO durante elaborazione batch")
            errori.append(f"Errore critico durante elaborazione: {str(critical_error)[:200]}")
        
        finally:
            # ============================================================
            # PULIZIA GARANTITA: rimuove loading anche in caso di crash
            # ============================================================
            upload_placeholder.empty()
            progress_bar.empty()
            status_text.empty()
        
        # ============================================
        # REPORT FINALE UNIFICATO
        # ============================================
        
        # Raccogli TUTTI i file problematici (errori elaborazione + duplicati)
        tutti_problematici = {}
        if file_errore:
            tutti_problematici.update(file_errore)
        for fname in file_gia_processati:
            tutti_problematici[fname] = _duplicate_reason_for_ui(fname, file_gia_processati_reason)

        problematic_entries = []
        for fname, motivo in file_errore.items():
            problematic_entries.append(_make_problematic_upload_entry(fname, motivo, 'failed'))
        for fname in file_gia_processati:
            problematic_entries.append(
                _make_problematic_upload_entry(fname, _duplicate_reason_for_ui(fname, file_gia_processati_reason), 'duplicate')
            )
        for fname in file_blocchi_policy.get('year', []):
            problematic_entries.append(_make_problematic_upload_entry(fname, 'Data fattura dell\'anno precedente', 'blocked'))
        for fname in file_blocchi_policy.get('month', []):
            problematic_entries.append(_make_problematic_upload_entry(fname, 'Data del mese precedente non consentita per questo account', 'blocked'))
        for fname in file_blocchi_policy.get('trial', []):
            problematic_entries.append(_make_problematic_upload_entry(fname, 'Fuori finestra consentita per la prova gratuita', 'blocked'))
        for fname in file_blocchi_formato_trial:
            problematic_entries.append(_make_problematic_upload_entry(fname, 'Formato non consentito durante la prova gratuita', 'blocked'))

        upload_notification_context = {
            'upload_id': datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'successful_files': list(file_ok),
            'successful_count': file_processati,
            'credit_note_files': list(file_note_credito),
            'problematic_files': problematic_entries,
            'problematic_count': len(problematic_entries),
            'price_alerts': [],
            'td24_date_alerts': td24_date_alerts,
            'stats': dict(upload_summary),
        }
        
        # === SALVA MESSAGGI IN SESSION_STATE (persistono fino al prossimo upload) ===
        _messages = []
        _messages.extend(_build_policy_block_messages(file_blocchi_policy))
        if file_processati > 0:
            msg_ok = f"1 fattura caricata" if file_processati == 1 else f"{file_processati} fatture caricate"
            _messages.append(f'<div style="padding:10px 16px;background:#d4edda;border-left:5px solid #28a745;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#155724;">✅ {msg_ok} con successo!</span></div>')
            # Messaggio aggiuntivo per note di credito
            if file_note_credito:
                nc_nomi = ", ".join(_html.escape(f) for f in file_note_credito)
                nc_n = len(file_note_credito)
                nc_lbl = "nota di credito caricata" if nc_n == 1 else "note di credito caricate"
                _messages.append(f'<div style="padding:10px 16px;background:#cce5ff;border-left:5px solid #004085;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#004085;">ℹ️ Attenzione: {nc_n} {nc_lbl}: </span><span style="font-size:0.82rem;color:#004085;">{nc_nomi}</span></div>')
        
        if tutti_problematici:
            n = len(tutti_problematici)
            # ── Raggruppa file per motivo di scarto ──
            motivi_raggruppati = defaultdict(list)
            for fname, motivo in tutti_problematici.items():
                # Normalizza motivi per raggruppamento leggibile
                if motivo == "Già presente nel database":
                    motivo_label = "Già caricata in precedenza (duplicata)"
                elif "già importato il" in motivo.lower():
                    motivo_label = motivo
                elif "P.IVA FATTURA DIVERSA" in motivo:
                    motivo_label = "P.IVA della fattura diversa da quella dell'azienda"
                elif "ANNO PRECEDENTE" in motivo:
                    motivo_label = "Data fattura dell'anno precedente"
                elif "QUOTA VISION RAGGIUNTA" in motivo:
                    motivo_label = "Quota Vision giornaliera raggiunta — file scartato, riprova domani"
                else:
                    motivo_label = motivo
                motivi_raggruppati[motivo_label].append(fname)
            
            # Costruisci HTML con dettaglio per motivo
            lbl = "fattura scartata" if n == 1 else "fatture scartate"
            dettaglio_html = ""
            for motivo, files_list in motivi_raggruppati.items():
                nomi_files = ", ".join(_html.escape(f) for f in files_list)
                dettaglio_html += f'<div style="margin-top:6px;"><span style="font-size:0.82rem;font-weight:600;color:#856404;">📌 {_html.escape(motivo)} ({len(files_list)}):</span><br/><span style="font-size:0.78rem;color:#856404;">{nomi_files}</span></div>'
            
            _messages.append(f'<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #ffc107;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#856404;">⚠️ {n} {lbl}:</span>{dettaglio_html}</div>')
            # Segna come processati per evitare ri-elaborazione
            for nome_file in tutti_problematici:
                st.session_state.files_processati_sessione.add(nome_file)
                st.session_state.files_processati_sessione.add(get_nome_base_file(nome_file))
        
        st.session_state.upload_messages = _messages
        st.session_state.upload_messages_time = time.time()
        st.session_state.files_errori_report = {}
        st.session_state.files_con_errori = set()
        
        if file_processati > 0 or tutti_problematici:
            invalida_cache_memoria()
            # [DEBUG]
            try:
                verify = supabase.table("fatture") \
                    .select("id", count="exact") \
                    .eq("user_id", user_id) \
                    .execute()
                righe_db = verify.count or 0
                logger.debug(f"[UPLOAD VERIFY] Righe presenti in DB post-upload: {righe_db}")
            except Exception as ve:
                logger.warning(f"[UPLOAD VERIFY] Verifica post-upload fallita: {ve}")
            # Invalida la cache fatture prima del rerun per mostrare subito i nuovi dati.
            if file_ok:
                try:
                    df_post_upload = carica_e_prepara_dataframe(
                        user_id,
                        force_refresh=True,
                        ristorante_id=st.session_state.get('ristorante_id'),
                    )
                    df_alert = calcola_alert(df_post_upload, soglia_minima=5.0)
                    if not df_alert.empty:
                        filtered_alerts = df_alert[
                            (df_alert['Aumento_Perc'] >= 5.0) &
                            (df_alert['N_Fattura'].isin(file_ok))
                        ]
                        upload_notification_context['price_alerts'] = [
                            {
                                'product': row['Prodotto'],
                                'supplier': row['Fornitore'],
                                'increase_pct': round(float(row['Aumento_Perc']), 1),
                                'file_name': row['N_Fattura'],
                            }
                            for _, row in filtered_alerts.head(5).iterrows()
                        ]
                except Exception as price_alert_error:
                    logger.warning(f"Errore calcolo alert prezzi post-upload: {price_alert_error}")

                quality_checks = _collect_post_upload_quality_checks(
                    supabase,
                    user_id,
                    file_ok,
                    st.session_state.get('ristorante_id'),
                )
                upload_notification_context['quality_checks'] = quality_checks
                upload_summary['righe_salvate'] = quality_checks.get('rows_saved', 0)
                upload_summary['righe_da_rivedere'] = quality_checks.get('needs_review_rows', 0)
                upload_summary['righe_prezzo_zero'] = quality_checks.get('zero_price_rows', 0)
                upload_summary['righe_non_classificate'] = quality_checks.get('uncategorized_rows', 0)

                if quality_checks.get('verification_ok'):
                    _rows_saved = int(quality_checks.get('rows_saved') or 0)
                    _review = int(quality_checks.get('needs_review_rows') or 0)
                    _zero = int(quality_checks.get('zero_price_rows') or 0)
                    _unc = int(quality_checks.get('uncategorized_rows') or 0)
                    if _review > 0 or _zero > 0 or _unc > 0:
                        _details = []
                        if _review > 0:
                            _details.append(f"{_review} da rivedere")
                        if _zero > 0:
                            _details.append(f"{_zero} a prezzo zero")
                        if _unc > 0:
                            _details.append(f"{_unc} non classificate")
                        _messages.append(
                            f'<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #f59e0b;border-radius:6px;margin-bottom:8px;">'
                            f'<span style="font-size:0.88rem;font-weight:600;color:#92400e;">'
                            f'🧪 Verifica qualità completata: {_rows_saved} righe salvate — ' + ', '.join(_details) + '.'
                            f'</span></div>'
                        )
                    else:
                        _messages.append(
                            f'<div style="padding:10px 16px;background:#d1fae5;border-left:5px solid #10b981;border-radius:6px;margin-bottom:8px;">'
                            f'<span style="font-size:0.88rem;font-weight:600;color:#065f46;">'
                            f'✅ Verifica qualità completata: {_rows_saved} righe salvate, nessuna anomalia su categorizzazione o righe a prezzo zero.'
                            f'</span></div>'
                        )
                else:
                    _messages.append(
                        '<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #d97706;border-radius:6px;margin-bottom:8px;">'
                        '<span style="font-size:0.88rem;font-weight:600;color:#92400e;">'
                        '⚠️ Upload salvato, ma la verifica qualità automatica non è riuscita a completarsi.'
                        '</span></div>'
                    )
            if 'righe_ai_appena_categorizzate' in st.session_state:
                st.session_state.righe_ai_appena_categorizzate = []
            if 'uploader_key' not in st.session_state:
                st.session_state.uploader_key = 0
            st.session_state.uploader_key += 1
            st.session_state.just_uploaded_files = {
                str(name).strip()
                for name in list(file_ok) + [get_nome_base_file(name) for name in file_ok]
                if str(name).strip()
            }
            st.session_state.files_processati_sessione = set()
            st.session_state.ultimo_upload_ids = []
            upload_summary['caricate_successo'] = file_processati
            upload_summary['errori'] = len(tutti_problematici)
            st.session_state.last_upload_summary = upload_summary
            upload_notification_context['stats'] = dict(upload_summary)
            st.session_state.last_upload_notification_context = upload_notification_context
            # 🧠 AUTO-TRIGGER AI: avvia categorizzazione automatica dopo upload riuscito
            if file_processati > 0:
                st.session_state.ai_categorization_in_progress = True
                st.session_state.trigger_ai_categorize = True
                st.session_state.pop('_fonte_pm_cache', None)  # Invalida cache Fonte
                logger.info(f"🧠 Auto-trigger AI: {file_processati} file caricati → categorizzazione automatica")
            # [DEBUG]
            logger.debug(f"[TIMING] handle_uploaded_files completato in {time.perf_counter()-t0_upload:.2f}s")
            st.rerun()
        else:
            upload_summary['caricate_successo'] = 0
            upload_summary['errori'] = len(tutti_problematici)
            st.session_state.last_upload_summary = upload_summary
            upload_notification_context['stats'] = dict(upload_summary)
            st.session_state.last_upload_notification_context = upload_notification_context

    else:
        # Nessun file nuovo — TUTTI duplicati/già presenti
        # Mostra progress bar rapida anche per duplicati
        total_check = len(uploaded_files)
        for i in range(total_check):
            progress_bar.progress((i + 1) / total_check)
            status_text.text(f"🔍 Verifica {i + 1}/{total_check}: {uploaded_files[i].name[:TRUNCATE_DESC_LOG]}...")
            time.sleep(0.05)
        
        upload_placeholder.empty()
        progress_bar.empty()
        status_text.empty()
        
        st.session_state.last_upload_summary = upload_summary
        problematic_entries = [
            _make_problematic_upload_entry(fname, _duplicate_reason_for_ui(fname, file_gia_processati_reason), 'duplicate')
            for fname in file_gia_processati
        ]
        st.session_state.last_upload_notification_context = {
            'upload_id': datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'successful_files': [],
            'successful_count': 0,
            'credit_note_files': [],
            'problematic_files': problematic_entries,
            'problematic_count': len(problematic_entries),
            'price_alerts': [],
            'td24_date_alerts': [],
            'stats': dict(upload_summary),
        }
        
        # Salva messaggio persistente per duplicati
        if file_gia_processati:
            nomi = ", ".join(
                _html.escape(f"{f} ({_duplicate_reason_for_ui(f, file_gia_processati_reason)})")
                for f in file_gia_processati
            )
            n = len(file_gia_processati)
            lbl = "file già importato in precedenza" if n == 1 else "file già importati in precedenza"
            st.session_state.upload_messages = [
                f'<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #ffc107;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#856404;">⚠️ {n} {lbl} — usare "Reimporta" per forzare l\'aggiornamento.</span><br/><span style="font-size:0.78rem;color:#856404;">{nomi}</span></div>'
            ]
            st.session_state.upload_messages_time = time.time()
            # Segna come processati
            for nome_file in file_gia_processati:
                st.session_state.files_processati_sessione.add(nome_file)
                st.session_state.files_processati_sessione.add(get_nome_base_file(nome_file))
        
        # Pulizia stato e reset uploader
        st.session_state.files_errori_report = {}
        st.session_state.files_con_errori = set()
        if 'uploader_key' not in st.session_state:
            st.session_state.uploader_key = 0
        st.session_state.uploader_key += 1
        logger.info(f"⚠️ {len(file_gia_processati)} fatture duplicate - stato pulito automaticamente")
        # [DEBUG]
        logger.debug(f"[TIMING] handle_uploaded_files completato in {time.perf_counter()-t0_upload:.2f}s")
        st.rerun()

