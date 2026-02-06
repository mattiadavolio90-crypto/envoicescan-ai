"""
Modulo formatters per FCI_PROJECT.

Funzioni per:
- Conversione file (PDF/IMG → base64)
- Navigazione dizionari annidati (safe_get)
- Calcolo prezzi standard intelligenti
- Gestione categorie
- Logging eventi upload
"""

import re
import base64
import fitz  # PyMuPDF
import logging
from typing import Optional, List, Dict, Any

from config.constants import (
    REGEX_KG_NUMERO,
    REGEX_GR_NUMERO,
    REGEX_ML_NUMERO,
    REGEX_CL_NUMERO,
    REGEX_LT_NUMERO,
    REGEX_PZ_NUMERO,
    REGEX_X_NUMERO,
    REGEX_PARENTESI_NUMERO,
    REGEX_NUMERO_KG,
    REGEX_NUMERO_LT,
    REGEX_NUMERO_GR
)

logger = logging.getLogger(__name__)


# ============================================================
# CONVERSIONE FILE
# ============================================================

def converti_in_base64(file_obj, nome_file: str) -> Optional[str]:
    """
    Converte PDF/IMG in base64 per OpenAI Vision usando PyMuPDF.
    
    Features:
    - Converte PDF in PNG (prima pagina, 300 DPI)
    - Gestisce immagini direttamente
    - Logging errori dettagliati
    - Traccia files con errori in session_state (se disponibile)
    
    Args:
        file_obj: oggetto file (BytesIO o UploadedFile)
        nome_file: nome file con estensione
    
    Returns:
        str: stringa base64 o None se errore
    
    Dipendenze:
        - fitz (PyMuPDF) per PDF
        - base64 standard library
    """
    try:
        content = file_obj.read()
        
        # Se è PDF, converti prima pagina in immagine con PyMuPDF
        if nome_file.lower().endswith('.pdf'):
            try:
                # Apri PDF con PyMuPDF
                pdf_document = fitz.open(stream=content, filetype="pdf")
                
                if pdf_document.page_count == 0:
                    errore = "PDF vuoto o senza pagine"
                    logger.error(f"Conversione PDF {nome_file}: {errore}")
                    
                    # Traccia errore in session_state se disponibile
                    try:
                        import streamlit as st
                        if 'files_con_errori' not in st.session_state:
                            st.session_state.files_con_errori = {}
                        st.session_state.files_con_errori[nome_file] = errore
                    except Exception:
                        pass  # Streamlit non disponibile o errore session_state
                    
                    pdf_document.close()
                    return None
                
                # Carica prima pagina
                page = pdf_document[0]
                
                # Converti in immagine ad alta risoluzione (300 DPI per OCR ottimale)
                # zoom = 300/72 = 4.166 (72 DPI è il default)
                zoom = 300 / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # Converti pixmap in bytes PNG
                img_bytes = pix.tobytes("png")
                pdf_document.close()
                
                # Usa i bytes PNG come content
                content = img_bytes
                
            except fitz.fitz.FileDataError as fitz_err:
                errore = f"PDF corrotto o non valido: {str(fitz_err)[:80]}"
                logger.error(f"Errore PyMuPDF per {nome_file}: {fitz_err}")
                
                try:
                    import streamlit as st
                    if 'files_con_errori' not in st.session_state:
                        st.session_state.files_con_errori = {}
                    st.session_state.files_con_errori[nome_file] = errore
                except:
                    pass
                
                return None
            
            except Exception as pdf_err:
                errore = f"Errore conversione PDF: {str(pdf_err)[:100]}"
                logger.exception(f"Errore conversione PDF {nome_file}: {pdf_err}")
                
                try:
                    import streamlit as st
                    if 'files_con_errori' not in st.session_state:
                        st.session_state.files_con_errori = {}
                    st.session_state.files_con_errori[nome_file] = errore
                except:
                    pass
                
                return None
        
        # Converti in base64
        return base64.b64encode(content).decode('utf-8')
    
    except Exception as e:
        errore = f"Errore lettura file: {str(e)[:100]}"
        logger.exception(f"Errore conversione file in immagine: {nome_file}")
        
        try:
            import streamlit as st
            if 'files_con_errori' not in st.session_state:
                st.session_state.files_con_errori = {}
            st.session_state.files_con_errori[nome_file] = errore
        except Exception:
            pass  # Streamlit non disponibile
        
        return None


# ============================================================
# NAVIGAZIONE DIZIONARI ANNIDATI
# ============================================================

def safe_get(
    dizionario: dict,
    percorso_chiavi: list,
    default=None,
    keep_list: bool = False
):
    """
    Naviga dizionario annidato in sicurezza (BUGFIX per parsing XML).
    
    Args:
        dizionario: dizionario da navigare
        percorso_chiavi: lista chiavi (es. ['Body', 'Lines', 'Item'])
        default: valore di default se chiave non trovata
        keep_list: Se True, mantiene liste (per DettaglioLinee)
                   Se False, estrae primo elemento (per Body)
    
    Returns:
        Valore trovato o default
    
    Esempi:
        >>> safe_get({"a": {"b": 1}}, ["a", "b"])
        1
        >>> safe_get({"a": [{"b": 1}]}, ["a", "b"], keep_list=False)
        1
        >>> safe_get({"a": [{"b": 1}, {"b": 2}]}, ["a"], keep_list=True)
        [{"b": 1}, {"b": 2}]
        >>> safe_get({}, ["x", "y"], default="not_found")
        'not_found'
    """
    valore_corrente = dizionario
    
    for chiave in percorso_chiavi:
        if isinstance(valore_corrente, dict):
            valore_corrente = valore_corrente.get(chiave)
            if valore_corrente is None:
                return default
            
            if isinstance(valore_corrente, list):
                if keep_list:
                    return valore_corrente if valore_corrente else default
                else:
                    if len(valore_corrente) > 0:
                        valore_corrente = valore_corrente[0]
                    else:
                        return default
        else:
            return default
    
    # Preserva valori falsy come 0 o ""; ritorna default solo se None
    return valore_corrente if valore_corrente is not None else default


# ============================================================
# CALCOLO PREZZO STANDARD
# ============================================================

def calcola_prezzo_standard_intelligente(
    descrizione: str,
    um: str,
    prezzo_unitario: float
) -> Optional[float]:
    """
    Calcola prezzo standardizzato usando SOLO pattern universali.
    NON dipende da prodotti specifici, applicabile a QUALSIASI ristorante.
    
    Pattern riconosciuti (in ordine di priorità):
    1. U.M. unitaria (PZ, CT, NR, FS, UN, SC)
    2. Quantità nella descrizione (KG<num>, GR<num>, ML<num>, PZ<num>)
    3. Confezioni (X<num>, (<num>))
    4. Default per KG/LT
    
    Args:
        descrizione: descrizione prodotto (es. "PASTA KG5")
        um: unità di misura (es. "KG", "PZ", "LT")
        prezzo_unitario: prezzo per unità di misura
    
    Returns:
        float: prezzo standard al kg/lt o None se non calcolabile
    
    Esempi:
        >>> calcola_prezzo_standard_intelligente("OLIO KG5", "KG", 25.0)
        5.0
        >>> calcola_prezzo_standard_intelligente("COCA 330ML", "PZ", 1.5)
        4.545454545454546
        >>> calcola_prezzo_standard_intelligente("PASTA", "KG", 2.5)
        2.5
        >>> calcola_prezzo_standard_intelligente("PANE", "PZ", 1.0)
        1.0
    """
    try:
        prezzo = float(prezzo_unitario)
        if prezzo <= 0:
            return None
    except (ValueError, TypeError):
        return None
    
    # Normalizza input
    um_norm = (um or '').strip().upper()
    desc = (descrizione or '').upper().strip()
    
    # =======================================================
    # PATTERN 1: U.M. UNITARIA (PZ, CT, NR, FS, UN, SC)
    # =======================================================
    # Se U.M. è unitaria, il prezzo unitario È il prezzo standard
    if um_norm in ['PZ', 'CT', 'NR', 'FS', 'UN', 'SC', 'NUMERO', 'PEZZI']:
        if 0.001 <= prezzo <= 10000:
            return prezzo
        return None
    
    # =======================================================
    # PATTERN 2: QUANTITÀ NELLA DESCRIZIONE
    # =======================================================
    
    # 2A. Pattern "KG<numero>" (es. KG5, KG12)
    match = REGEX_KG_NUMERO.search(desc)
    if match:
        try:
            kg = float(match.group(1).replace(',', '.'))
            if 0.01 <= kg <= 10000:
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # 2B. Pattern "GR<numero>" (es. GR500, GR800)
    match = REGEX_GR_NUMERO.search(desc)
    if match:
        try:
            gr = float(match.group(1))
            if 1 <= gr <= 100000:
                kg = gr / 1000.0
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # 2C. Pattern "ML<numero>" (es. ML750, ML500)
    match = REGEX_ML_NUMERO.search(desc)
    if match:
        try:
            ml = float(match.group(1))
            if 1 <= ml <= 100000:
                lt = ml / 1000.0
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 2D. Pattern "CL<numero>" (es. CL50)
    match = REGEX_CL_NUMERO.search(desc)
    if match:
        try:
            cl = float(match.group(1))
            if 1 <= cl <= 10000:
                lt = cl / 100.0
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 2E. Pattern "LT<numero>" o "L<numero>" (es. LT5, L30)
    match = REGEX_LT_NUMERO.search(desc)
    if match:
        try:
            lt = float(match.group(1).replace(',', '.'))
            if 0.01 <= lt <= 10000:
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 2F. Pattern "PZ<numero>" nella descrizione (es. PZ100, PZ50)
    match = REGEX_PZ_NUMERO.search(desc)
    if match:
        try:
            pz = float(match.group(1))
            if 2 <= pz <= 10000:
                return prezzo / pz
        except (ValueError, TypeError):
            pass
    
    # =======================================================
    # PATTERN 3: CONFEZIONI/MULTIPLI
    # =======================================================
    
    # 3A. Pattern "X<numero>" (es. X12, X24)
    match = REGEX_X_NUMERO.search(desc)
    if match:
        try:
            num = float(match.group(1))
            if 2 <= num <= 1000:
                return prezzo / num
        except (ValueError, TypeError):
            pass
    
    # 3B. Pattern "(<numero>)" (es. (12), (50))
    match = REGEX_PARENTESI_NUMERO.search(desc)
    if match:
        try:
            num = float(match.group(1))
            if 2 <= num <= 1000:
                return prezzo / num
        except (ValueError, TypeError):
            pass
    
    # =======================================================
    # PATTERN 4: PESO/VOLUME IN FORMATO TESTUALE
    # =======================================================
    
    # 4A. Pattern "<numero> KG" o "<numero>,<numero> KG"
    match = REGEX_NUMERO_KG.search(desc)
    if match:
        try:
            kg = float(match.group(1).replace(',', '.'))
            if 0.01 <= kg <= 10000:
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # 4B. Pattern "<numero> LT" o "<numero> LITRI"
    match = REGEX_NUMERO_LT.search(desc)
    if match:
        try:
            lt = float(match.group(1).replace(',', '.'))
            if 0.01 <= lt <= 10000:
                return prezzo / lt
        except (ValueError, TypeError):
            pass
    
    # 4C. Pattern "<numero> GR" o "<numero> GRAMMI"
    match = REGEX_NUMERO_GR.search(desc)
    if match:
        try:
            gr = float(match.group(1))
            if 1 <= gr <= 100000:
                kg = gr / 1000.0
                return prezzo / kg
        except (ValueError, TypeError):
            pass
    
    # =======================================================
    # PATTERN 5: DEFAULT PER U.M. STANDARD
    # =======================================================
    
    # Se U.M. è KG o LT e nessun pattern trovato, il prezzo è già standard
    if um_norm in ['KG', 'LT', 'KILOGRAMMI', 'LITRI']:
        return prezzo
    
    # =======================================================
    # NESSUN PATTERN RICONOSCIUTO
    # =======================================================
    return None


# ============================================================
# GESTIONE CATEGORIE
# ============================================================

def carica_categorie_da_db(supabase_client=None) -> list:
    """
    Restituisce SOLO le categorie definite in constants.py.
    NON carica più dal database per evitare categorie inconsistenti.
    
    Args:
        supabase_client: istanza Supabase (ignorato, mantenuto per compatibilità)
    
    Returns:
        list: Lista categorie formato "CARNE" (SENZA EMOJI), ordinate
              F&B alfabetico + Spese Generali alfabetico
    
    Note:
        - USA SOLO categorie da constants.py
        - ESCLUSO "NOTE E DICITURE" (solo per Review Righe €0)
        - Ordine: F&B alfabetico, poi Spese Generali alfabetico
    """
    # Import delle categorie da constants.py per garantire coerenza
    from config.constants import (
        CATEGORIE_FOOD_BEVERAGE, 
        CATEGORIE_MATERIALI, 
        CATEGORIE_SPESE_OPERATIVE
    )
    
    # Combina tutte le categorie F&B (Food+Beverage + MATERIALE DI CONSUMO)
    categorie_fb = CATEGORIE_FOOD_BEVERAGE + CATEGORIE_MATERIALI  # Include MATERIALE DI CONSUMO
    
    # Ordina alfabeticamente entrambe le liste
    categorie_fb_sorted = sorted(categorie_fb)
    categorie_spese_sorted = sorted(CATEGORIE_SPESE_OPERATIVE)
    
    # Combina: prima F&B, poi spese generali
    categorie_finali = categorie_fb_sorted + categorie_spese_sorted
    
    logger.info(f"✅ Categorie standardizzate: {len(categorie_finali)} ({len(categorie_fb_sorted)} F&B + {len(categorie_spese_sorted)} spese)")
    return categorie_finali


# ============================================================
# LOGGING EVENTI
# ============================================================

def log_upload_event(
    user_id: str,
    user_email: str,
    file_name: str,
    status: str,
    rows_parsed: int = 0,
    rows_saved: int = 0,
    rows_excluded: int = 0,
    error_stage: Optional[str] = None,
    error_message: Optional[str] = None,
    details: Optional[dict] = None,
    supabase_client = None
) -> None:
    """
    Logga evento di upload su Supabase per supporto tecnico.
    Non solleva mai eccezioni per non bloccare l'upload principale.
    
    IMPORTANTE: Non logga duplicati (comportamento corretto).
    
    Args:
        user_id: UUID utente
        user_email: Email utente
        file_name: Nome file caricato
        status: SAVED_OK | SAVED_PARTIAL | FAILED (NO DUPLICATE)
        rows_parsed: Numero righe estratte dal parsing
        rows_saved: Numero righe effettivamente salvate
        rows_excluded: Numero righe escluse per "diciture" (comportamento normale)
        error_stage: Stage dove è avvenuto errore (PARSING | VISION | SUPABASE_INSERT | POSTCHECK)
        error_message: Messaggio errore (max 500 char)
        details: Dict con dettagli aggiuntivi (salvato come JSONB)
        supabase_client: istanza Supabase client
    
    Returns:
        None (non solleva eccezioni)
    """
    if supabase_client is None:
        logger.warning("log_upload_event: supabase_client non fornito, skip logging")
        return
    
    try:
        # Determina file_type
        file_type = "xml" if file_name.lower().endswith(".xml") else \
                   "pdf" if file_name.lower().endswith(".pdf") else \
                   "image" if file_name.lower().endswith((".jpg", ".jpeg", ".png")) else "unknown"
        
        # Tronca error_message se troppo lungo
        if error_message and len(error_message) > 500:
            error_message = error_message[:497] + "..."
        
        event_data = {
            'user_id': user_id,
            'user_email': user_email,
            'file_name': file_name,
            'file_type': file_type,
            'status': status,
            'rows_parsed': rows_parsed,
            'rows_saved': rows_saved,
            'rows_excluded': rows_excluded,
            'error_stage': error_stage,
            'error_message': error_message,
            'details': details
        }
        
        supabase_client.table('upload_events').insert(event_data).execute()
        logger.info(f"✅ LOG EVENT: {status} - {file_name} - user {user_email}")
        
    except Exception as e:
        # Non solleva eccezione per non bloccare l'upload
        logger.error(f"❌ Errore logging upload event: {e}")


def formatta_euro(valore: float) -> str:
    """
    Formatta un valore numerico come stringa euro con formato italiano.
    
    Args:
        valore: Numero da formattare
    
    Returns:
        str: "€ 1.234,56" (formato italiano con migliaia separate da punti)
    """
    try:
        return f"€ {valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "€ 0,00"


def crea_pivot_mensile(df, index_col: str):
    """
    Crea tabella pivot mensile per analisi temporale.
    
    Args:
        df: DataFrame con colonne Mese, index_col, Totale
        index_col: Nome colonna da usare come indice (es. 'Categoria', 'Fornitore')
    
    Returns:
        DataFrame pivot con mesi come colonne e index_col come righe
    """
    import pandas as pd
    
    if df.empty or index_col not in df.columns:
        return pd.DataFrame()
    
    try:
        # Crea pivot con mesi ordinati cronologicamente
        pivot = df.pivot_table(
            index=index_col,
            columns='Mese',
            values='Totale',
            aggfunc='sum',
            fill_value=0
        )
        
        # Ordina colonne cronologicamente (YYYY-MM)
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)
        
        # Aggiungi colonna Totale
        pivot['Totale'] = pivot.sum(axis=1)
        
        # Ordina per Totale decrescente
        pivot = pivot.sort_values('Totale', ascending=False)
        
        # Formatta valori in euro
        for col in pivot.columns:
            if col != 'Totale':
                pivot[col] = pivot[col].apply(lambda x: formatta_euro(x) if x > 0 else "")
        pivot['Totale'] = pivot['Totale'].apply(formatta_euro)
        
        return pivot
    except Exception as e:
        logger.error(f"Errore creazione pivot mensile: {e}")
        return pd.DataFrame()


def genera_box_recap(num_righe: int, totale: float) -> str:
    """
    Genera HTML per box riepilogativo con stile Material Design.
    
    Args:
        num_righe: Numero righe/prodotti
        totale: Importo totale in euro
    
    Returns:
        str: HTML con box colorato e formattato
    """
    html = f"""
    <div style='
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        color: white;
        text-align: center;
    '>
        <div style='font-size: 48px; font-weight: bold; margin-bottom: 10px;'>
            {formatta_euro(totale)}
        </div>
        <div style='font-size: 18px; opacity: 0.9;'>
            {num_righe:,} prodotti analizzati
        </div>
    </div>
    """
    return html
