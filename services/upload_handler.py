"""Gestione elaborazione file caricati - deduplicazione, validazione, salvataggio."""

import streamlit as st
import pandas as pd
import time
import logging
import html as _html
from collections import defaultdict

from config.constants import (
    TRUNCATE_DESC_LOG,
    TRUNCATE_ERROR_DISPLAY,
    MAX_FILES_PER_UPLOAD,
    MAX_UPLOAD_TOTAL_MB,
    BATCH_FILE_SIZE,
    BATCH_RATE_LIMIT_DELAY,
)

from utils.piva_validator import normalizza_piva
from utils.formatters import log_upload_event, get_nome_base_file
from utils.ristorante_helper import add_ristorante_filter

from services.ai_service import invalida_cache_memoria, mostra_loading_ai
from services.invoice_service import estrai_dati_da_xml, estrai_xml_da_p7m, estrai_dati_da_scontrino_vision, salva_fattura_processata


logger = logging.getLogger("fci_app")


def handle_uploaded_files(uploaded_files, supabase, user_id):
    """Gestisce l'elaborazione completa dei file caricati: deduplicazione, validazione, salvataggio."""
    # Pulisci messaggi precedenti all'inizio di un nuovo caricamento
    st.session_state.upload_messages = []
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
        # Verifica user_id disponibile
        user_data = st.session_state.get('user_data', {})
        user_id = user_data.get('id')
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
        logger.exception(f"Errore caricamento file da DB per user_id={st.session_state.user_data.get('id')}")
        logger.error(f"Errore caricamento file da DB: {e}")
        st.error("❌ Errore nel caricamento dei dati. Riprova.")
        file_su_supabase = set()
        file_su_supabase_full = set()


    # Calcola nomi caricati e duplicati in modo robusto
    uploaded_names = [f.name for f in uploaded_files]
    uploaded_unique = set(uploaded_names)
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
    
    just_uploaded = st.session_state.get('just_uploaded_files', set())
    
    for file in file_unici:
        filename = file.name
        filename_lower = filename.strip().lower()
        nome_base = get_nome_base_file(filename)
        
        # ── Confronto a 2 livelli ──────────────────────────────────
        # 1° LIVELLO: match ESATTO sul nome file completo (affidabile)
        # 2° LIVELLO: match sul nome base senza estensione (cattura XML/PDF stesso doc)
        is_exact_match = filename_lower in file_su_supabase_full
        is_base_match = nome_base in file_su_supabase
        is_just_uploaded = nome_base in just_uploaded
        
        if is_exact_match or is_base_match or is_just_uploaded:
            file_gia_processati.append(filename)
            # Log dettagliato per diagnosi
            reason = []
            if is_exact_match: reason.append('nome esatto in DB')
            if is_base_match and not is_exact_match: reason.append(f'nome base "{nome_base}" in DB')
            if is_just_uploaded: reason.append('appena caricato')
            logger.info(f"📋 SKIP '{filename}' → {', '.join(reason)}")
        # Protezione: Salta file che hanno già dato errore in questa sessione
        elif filename in st.session_state.get('files_con_errori', set()):
            continue
        else:
            file_nuovi.append(file)
    
    logger.info(f"📊 Dedup risultato: {len(file_nuovi)} nuovi, {len(file_gia_processati)} già presenti, {duplicate_count} duplicati upload")
    
    # Log file scartati come DUPLICATE_SKIPPED (solo quelli già nel DB, non appena caricati in sessione)
    if file_gia_processati:
        try:
            _uid = st.session_state.user_data.get('id', '')
            _email = st.session_state.user_data.get('email', 'unknown')
            for _fname in file_gia_processati:
                if get_nome_base_file(_fname) not in just_uploaded:
                    log_upload_event(
                        user_id=_uid,
                        user_email=_email,
                        file_name=_fname,
                        status='DUPLICATE_SKIPPED',
                        supabase_client=supabase
                    )
        except Exception as _log_ex:
            logger.warning(f"Errore logging duplicate skip: {_log_ex}")
    
    # Messaggio SOLO per ADMIN (interfaccia pulita per clienti)
    is_admin = st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False)
    
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
        file_errore = {}
        
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
                            # XML: deve iniziare con <?xml o <  (BOM UTF-8 opzionale)
                            _head = file_content[:100].lstrip(b'\xef\xbb\xbf')  # strip BOM
                            _magic_ok = _head.lstrip().startswith((b'<?xml', b'<'))
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
                        
                        if nome_file.endswith('.xml'):
                            items = estrai_dati_da_xml(file)
                        elif nome_file.endswith('.p7m'):
                            xml_stream = estrai_xml_da_p7m(file)
                            items = estrai_dati_da_xml(xml_stream)
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
                        
                        if not is_admin and not is_image:
                            # Estrai P.IVA dal cessionario (dalla prima riga - items è lista di dict)
                            piva_cessionario = None
                            if isinstance(items, list) and len(items) > 0:
                                piva_cessionario = items[0].get('piva_cessionario')
                            elif isinstance(items, dict):
                                piva_cessionario = items.get('piva_cessionario')
                            
                            # P.IVA ristorante ATTUALMENTE SELEZIONATO (multi-ristorante aware)
                            piva_attiva = st.session_state.get('partita_iva')
                            nome_ristorante_attivo = st.session_state.get('nome_ristorante', 'N/A')
                            
                            logger.info(f"🔍 Validazione P.IVA {file.name} - rist_id={st.session_state.get('ristorante_id')}")
                            
                            # ✅ CASO 2: P.IVA presente → VALIDAZIONE STRICT MULTI-RISTORANTE
                            if piva_attiva and piva_cessionario:
                                piva_cessionario_norm = normalizza_piva(piva_cessionario)
                                piva_attiva_norm = normalizza_piva(piva_attiva)
                                
                                if piva_cessionario_norm != piva_attiva_norm:
                                    # 🚫 BLOCCO: P.IVA non corrisponde al ristorante selezionato
                                    
                                    logger.warning(
                                        f"⚠️ UPLOAD BLOCCATO {file.name} - user_id={st.session_state.get('user_data', {}).get('id')} "
                                        f"P.IVA mismatch (rist_id={st.session_state.get('ristorante_id')})"
                                    )
                                    raise ValueError("🚫 FATTURA NON VALIDA - P.IVA FATTURA DIVERSA DA P.IVA AZIENDA")
                                else:
                                    # ✅ P.IVA match: log successo
                                    logger.info(f"✅ Validazione OK: P.IVA match per rist_id={st.session_state.get('ristorante_id')}")
                        
                        else:
                            # Admin/Impersonazione: log per debug (bypass validazione)
                            piva_cessionario = None
                            if isinstance(items, list) and len(items) > 0:
                                piva_cessionario = items[0].get('piva_cessionario')
                            logger.debug(f"👨‍💼 Admin upload {file.name} - P.IVA fattura: {piva_cessionario} (validazione bypassata)")
                        
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
                            st.session_state.files_processati_sessione.add(file.name)
                            # Aggiungi anche nome base per prevenire duplicati con estensione diversa
                            st.session_state.files_processati_sessione.add(get_nome_base_file(file.name))
                            
                            # 🔥 FIX BUG #1: Rimuovi da files_con_errori se presente (file ora ha successo)
                            st.session_state.files_con_errori.discard(file.name)
                        else:
                            raise ValueError(f"Errore salvataggio: {result.get('error', 'Sconosciuto')}")
                    
                    except Exception as e:
                        # TRACCIA ERRORE DETTAGLIATO (silenzioso - solo log)
                        full_error = str(e)
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
                                details={"exception_type": type(e).__name__},
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
            tutti_problematici[fname] = "Già presente nel database"
        
        # === SALVA MESSAGGI IN SESSION_STATE (persistono fino al prossimo upload) ===
        _messages = []
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
                elif "P.IVA FATTURA DIVERSA" in motivo:
                    motivo_label = "P.IVA della fattura diversa da quella dell'azienda"
                elif "ANNO PRECEDENTE" in motivo:
                    motivo_label = "Data fattura dell'anno precedente"
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
            if 'righe_ai_appena_categorizzate' in st.session_state:
                st.session_state.righe_ai_appena_categorizzate = []
            if 'uploader_key' not in st.session_state:
                st.session_state.uploader_key = 0
            st.session_state.uploader_key += 1
            st.session_state.just_uploaded_files = set()
            st.session_state.files_processati_sessione = set()
            st.session_state.ultimo_upload_ids = []
            upload_summary['caricate_successo'] = file_processati
            upload_summary['errori'] = len(tutti_problematici)
            st.session_state.last_upload_summary = upload_summary
            st.rerun()
        else:
            upload_summary['caricate_successo'] = 0
            upload_summary['errori'] = len(tutti_problematici)
            st.session_state.last_upload_summary = upload_summary

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
        
        # Salva messaggio persistente per duplicati
        if file_gia_processati:
            nomi = ", ".join(_html.escape(f) for f in file_gia_processati)
            n = len(file_gia_processati)
            lbl = "fattura scartata perché già caricata in precedenza (duplicata)" if n == 1 else "fatture scartate perché già caricate in precedenza (duplicate)"
            st.session_state.upload_messages = [
                f'<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #ffc107;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#856404;">⚠️ {n} {lbl}:</span><br/><span style="font-size:0.78rem;color:#856404;">{nomi}</span></div>'
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
        st.rerun()

