"""
Servizio di gestione fatture - Parsing, estrazione e salvataggio.

Questo modulo fornisce:
- Parsing XML (Fatture Elettroniche)
- Estrazione Vision API (PDF/immagini con OpenAI)
- Salvataggio su Supabase con logging
- Categorizzazione automatica integrata

Dipendenze:
- xmltodict: Parsing XML
- openai: Vision API per PDF/immagini
- supabase: Database
- streamlit: UI e secrets
- pandas: Data processing
"""

import json
import logging
import pandas as pd
import streamlit as st
import xmltodict
from typing import List, Dict, Any, Optional
from datetime import datetime

# Import utilities
from utils.formatters import (
    safe_get,
    converti_in_base64,
    calcola_prezzo_standard_intelligente,
    log_upload_event
)
from utils.text_utils import (
    normalizza_stringa,
    estrai_fornitore_xml
)
from utils.validation import (
    verifica_integrita_fattura
)

# Logger
logger = logging.getLogger('fci_app.invoice')


def estrai_dati_da_xml(file_caricato):
    """
    Estrae dati da fatture XML elettroniche italiane.
    
    Args:
        file_caricato: File XML caricato
        
    Returns:
        List[Dict]: Lista di righe prodotto estratte
        
    Note:
        - Carica cache memoria globale all'inizio (1 volta per tutte le righe)
        - Categorizza automaticamente con sistema ibrido (memoria + keyword)
        - Esclude diciture automaticamente
        - Gestisce sconti (usa totale_riga / quantita per prezzo effettivo)
    """
    try:
        # Import services solo quando necessario per evitare circular imports
        from services.ai_service import (
            carica_memoria_completa,
            carica_memoria_ai,
            categorizza_con_memoria
        )
        
        # Carica cache memoria globale SUBITO
        current_user_id = st.session_state.get('user_data', {}).get('id')
        if current_user_id:
            carica_memoria_completa(current_user_id)
            logger.info("âœ… Cache memoria precaricata per elaborazione XML")
        
        contenuto = file_caricato.read()
        doc = xmltodict.parse(contenuto)
        
        root_key = list(doc.keys())[0]
        fattura = doc[root_key]
        
        data_documento = safe_get(
            fattura,
            ['FatturaElettronicaBody', 'DatiGenerali', 'DatiGeneraliDocumento', 'Data'],
            default='N/A',
            keep_list=False
        )
        
        fornitore = estrai_fornitore_xml(fattura)
        
        body = safe_get(fattura, ['FatturaElettronicaBody'], default={}, keep_list=False)
        
        linee = safe_get(
            body, 
            ['DatiBeniServizi', 'DettaglioLinee'], 
            default=[],
            keep_list=True
        )
        
        if not linee:
            linee = safe_get(body, ['DettaglioLinee'], default=[], keep_list=True)
        
        if isinstance(linee, dict):
            linee = [linee]
        
        memoria_ai = carica_memoria_ai()
        
        righe_prodotti = []
        for idx, riga in enumerate(linee, start=1):
            if not isinstance(riga, dict):
                continue
            
            try:
                # Codice articolo
                codice_articolo = ""
                codice_articolo_raw = riga.get('CodiceArticolo', [])
                if isinstance(codice_articolo_raw, list) and len(codice_articolo_raw) > 0:
                    codice_articolo = codice_articolo_raw[0].get('CodiceValore', '')
                elif isinstance(codice_articolo_raw, dict):
                    codice_articolo = codice_articolo_raw.get('CodiceValore', '')
                
                descrizione_raw = riga.get('Descrizione', 'Articolo senza nome')
                descrizione = normalizza_stringa(descrizione_raw)
                
                quantita = float(riga.get('Quantita', 0) or 1)
                unita_misura = riga.get('UnitaMisura', '')
                prezzo_base = float(riga.get('PrezzoUnitario', 0))
                aliquota_iva = float(riga.get('AliquotaIVA', 0))
                totale_riga = float(riga.get('PrezzoTotale', 0))
                
                # Calcola prezzo effettivo (include sconti)
                if quantita > 0 and totale_riga > 0:
                    prezzo_unitario = totale_riga / quantita
                else:
                    prezzo_unitario = prezzo_base
                    if totale_riga == 0:
                        totale_riga = quantita * prezzo_unitario
                
                prezzo_unitario = round(prezzo_unitario, 4)
                
                # Log sconti
                if abs(prezzo_unitario - prezzo_base) > 0.01:
                    sconto_percentuale = ((prezzo_base - prezzo_unitario) / prezzo_base) * 100
                    logger.info(f"ðŸŽ SCONTO: {descrizione[:40]} | Base: â‚¬{prezzo_base:.2f} â†’ Effettivo: â‚¬{prezzo_unitario:.2f} ({sconto_percentuale:.1f}%)")
                
                # Auto-categorizzazione
                categoria_finale = categorizza_con_memoria(
                    descrizione=descrizione,
                    prezzo=prezzo_unitario,
                    quantita=quantita,
                    user_id=current_user_id
                )
                
                # Escludi diciture
                if categoria_finale == "ðŸ“ NOTE E DICITURE":
                    logger.info(f"âŠ— Riga ESCLUSA (dicitura): {descrizione}")
                    continue
                
                # Calcolo prezzo standard
                prezzo_std = calcola_prezzo_standard_intelligente(
                    descrizione=descrizione,
                    um=unita_misura,
                    prezzo_unitario=prezzo_unitario
                )
                
                righe_prodotti.append({
                    'Numero_Riga': idx,
                    'Codice_Articolo': codice_articolo,
                    'Descrizione': descrizione,
                    'Quantita': quantita,
                    'Unita_Misura': unita_misura,
                    'Prezzo_Unitario': round(prezzo_unitario, 2),
                    'IVA_Percentuale': aliquota_iva,
                    'Totale_Riga': round(totale_riga, 2),
                    'Fornitore': fornitore,
                    'Categoria': categoria_finale,
                    'Data_Documento': data_documento,
                    'File_Origine': file_caricato.name,
                    'Prezzo_Standard': prezzo_std
                })
            except Exception as e:
                logger.exception(f"Errore parsing riga {idx}")
                continue
        
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore lettura XML: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.warning(f"âš ï¸ File {file_caricato.name}: impossibile leggere")
        return []


def estrai_dati_da_scontrino_vision(file_caricato, openai_client=None):
    """
    Estrae dati da scontrini/PDF usando OpenAI Vision API.
    
    Args:
        file_caricato: File PDF/immagine caricato
        openai_client: OpenAI client (opzionale, usa st.secrets se None)
        
    Returns:
        List[Dict]: Lista di righe prodotto estratte
        
    Note:
        - Usa GPT-4o-mini Vision API
        - Formato JSON strutturato
        - Categorizzazione con sistema ibrido (locale + globale)
        - Gestisce markdown code fences nella risposta
    """
    try:
        # Import services
        from services.ai_service import (
            carica_memoria_ai,
            ottieni_categoria_prodotto
        )
        from openai import OpenAI
        
        # Ottieni client se non fornito
        if openai_client is None:
            api_key = st.secrets.get("OPENAI_API_KEY", "")
            if not api_key:
                st.error("âŒ OPENAI_API_KEY mancante")
                return []
            openai_client = OpenAI(api_key=api_key)
        
        file_caricato.seek(0)
        base64_image = converti_in_base64(file_caricato, file_caricato.name)
        if not base64_image:
            return []
        
        prompt = """Sei un esperto contabile per ristoranti italiani. Analizza questo documento (scontrino/fattura) ed estrai i dati.

INFORMAZIONI DA ESTRARRE:
1. **Fornitore**: Nome completo del fornitore. PuÃ² essere:
   - SocietÃ /Azienda (es. "METRO SRL", "CRAI", "EKAF")
   - Persona fisica/Professionista (es. "MARIO ROSSI", "Studio BIANCHI")
   Cerca in: Ragione Sociale, Denominazione, Cedente/Prestatore, Nome e Cognome
2. **Data**: Data del documento in formato YYYY-MM-DD
3. **Righe articoli**: Lista completa di TUTTI i prodotti acquistati

PER OGNI ARTICOLO:
- Descrizione (normalizzata in MAIUSCOLO)
- QuantitÃ  (numero, se non specificato usa 1.0)
- Prezzo unitario in â‚¬ (numero decimale)
- Totale riga in â‚¬ (numero decimale)

REGOLE IMPORTANTI:
- Estrai SOLO le righe articolo vere (ignora intestazioni, note, pubblicitÃ )
- Se manca la quantitÃ , usa 1.0
- Se manca prezzo unitario ma c'Ã¨ il totale, calcola: prezzo_unitario = totale / quantitÃ 
- Normalizza descrizioni: "parmigiano reggiano" â†’ "PARMIGIANO REGGIANO"
- Date italiane (es. 08/12/2024) converti in 2024-12-08

FORMATO RISPOSTA (SOLO JSON):
{
  "fornitore": "NOME FORNITORE",
  "data": "YYYY-MM-DD",
  "righe": [
    {
      "descrizione": "DESCRIZIONE ARTICOLO",
      "quantita": 2.5,
      "prezzo_unitario": 12.50,
      "totale": 31.25
    }
  ]
}

IMPORTANTE: Rispondi SOLO con il JSON, niente altro testo."""

        with st.spinner(f"ðŸ” Analizzo {file_caricato.name} con AI..."):
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}}
                    ]
                }],
                max_tokens=1500,
                temperature=0
            )
        
        testo = response.choices[0].message.content.strip()

        # Rimuovi markdown code fences
        try:
            if testo.startswith('```'):
                lines = testo.split('\n')
                if lines[0].strip().lower() in ['```', '```json']:
                    lines = lines[1:]
                testo = '\n'.join(lines)
            
            if testo.endswith('```'):
                lines = testo.split('\n')
                if lines[-1].strip() == '```':
                    lines = lines[:-1]
                testo = '\n'.join(lines)
        except Exception:
            pass

        testo = testo.strip()
        
        try:
            dati = json.loads(testo)
        except json.JSONDecodeError:
            st.error(f"âŒ Risposta Vision non valida per {file_caricato.name}")
            st.code(testo[:500])
            return []
        
        fornitore = normalizza_stringa(dati.get('fornitore', 'Fornitore Sconosciuto'))
        data_documento = dati.get('data', 'N/A')
        
        try:
            pd.to_datetime(data_documento)
        except Exception as e:
            data_documento = pd.Timestamp.now().strftime('%Y-%m-%d')
            st.warning(f"âš ï¸ Data non valida, uso data odierna: {e}")
        
        righe_prodotti = []
        memoria_ai = carica_memoria_ai()
        current_user_id = st.session_state.get('user_data', {}).get('id')
        
        for idx, riga in enumerate(dati.get('righe', []), start=1):
            descrizione = normalizza_stringa(riga.get('descrizione', 'Articolo senza nome'))
            
            try:
                quantita = float(riga.get('quantita', 1.0))
            except (ValueError, TypeError):
                quantita = 1.0
            
            try:
                prezzo_unitario = float(riga.get('prezzo_unitario', 0))
            except (ValueError, TypeError):
                prezzo_unitario = 0
            
            unita_misura = riga.get('unita_misura', 'PZ')
            
            try:
                totale_riga = float(riga.get('totale', 0))
            except (ValueError, TypeError):
                totale_riga = 0
            
            # Calcola mancanti
            if totale_riga == 0 and prezzo_unitario > 0:
                totale_riga = quantita * prezzo_unitario
            if prezzo_unitario == 0 and totale_riga > 0 and quantita > 0:
                prezzo_unitario = totale_riga / quantita
            
            # Categorizzazione
            if current_user_id:
                categoria_iniziale = ottieni_categoria_prodotto(descrizione, current_user_id)
            else:
                categoria_iniziale = memoria_ai.get(descrizione, "Da Classificare")
            
            # Prezzo standard
            prezzo_std = calcola_prezzo_standard_intelligente(
                descrizione=descrizione,
                um=unita_misura,
                prezzo_unitario=prezzo_unitario
            )
            
            righe_prodotti.append({
                'Numero_Riga': idx,
                'Codice_Articolo': '',
                'Descrizione': descrizione,
                'Quantita': quantita,
                'Unita_Misura': unita_misura,
                'Prezzo_Unitario': round(prezzo_unitario, 2),
                'IVA_Percentuale': 0,
                'Totale_Riga': round(totale_riga, 2),
                'Fornitore': fornitore,
                'Categoria': categoria_iniziale,
                'Data_Documento': data_documento,
                'File_Origine': file_caricato.name,
                'Prezzo_Standard': prezzo_std
            })
        
        if righe_prodotti:
            st.success(f"âœ… Estratte {len(righe_prodotti)} righe da {file_caricato.name}")
        else:
            st.warning(f"âš ï¸ Nessuna riga trovata in {file_caricato.name}")
        
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore Vision: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.error(f"âŒ Errore Vision su {file_caricato.name}: {str(e)}")
        return []


def salva_fattura_processata(nome_file: str, dati_prodotti: List[Dict], 
                             supabase_client=None, silent: bool = False) -> Dict[str, Any]:
    """
    Salva fatture su Supabase con logging eventi.
    
    Args:
        nome_file: Nome file fattura
        dati_prodotti: Lista dizionari con dati prodotti
        supabase_client: Client Supabase (opzionale, usa st.secrets se None)
        silent: Se True, nasconde messaggi UI (per batch)
        
    Returns:
        Dict con: success, error, righe, location
        
    Note:
        - PrioritÃ : Supabase SEMPRE (no fallback JSON)
        - Forza categoria valida (mai NULL/vuoto â†’ "Da Classificare")
        - Verifica integritÃ  post-salvataggio
        - Logging automatico su tabella upload_events
    """
    from supabase import create_client
    
    # Verifica autenticazione
    if "user_data" not in st.session_state or "id" not in st.session_state.user_data:
        if not silent:
            st.error("âŒ Errore: Utente non autenticato. Effettua il login.")
        return {"success": False, "error": "not_authenticated", "righe": 0, "location": None}
    
    user_id = st.session_state.user_data["id"]
    num_righe = len(dati_prodotti)
    
    # Ottieni client se non fornito
    if supabase_client is None:
        supabase_url = st.secrets["supabase"]["url"]
        supabase_key = st.secrets["supabase"]["key"]
        supabase_client = create_client(supabase_url, supabase_key)
    
    # Salvataggio Supabase
    if supabase_client is not None:
        try:
            if not dati_prodotti:
                return {"success": False, "error": "no_data", "righe": 0, "location": None}
            
            logger.info(f"ðŸ”¥ Inizio elaborazione: {nome_file}")
            logger.info(f"ðŸ“„ {nome_file}: {len(dati_prodotti)} righe estratte")
            
            # Prepara records
            records = []
            for prod in dati_prodotti:
                prezzo_std = prod.get("PrezzoStandard", prod.get("Prezzo_Standard"))
                
                # Forza categoria valida
                categoria_raw = prod.get("Categoria", "Da Classificare")
                if not categoria_raw or pd.isna(categoria_raw) or str(categoria_raw).strip() == '':
                    categoria_raw = "Da Classificare"
                
                records.append({
                    "user_id": user_id,
                    "file_origine": nome_file,
                    "numero_riga": prod.get("NumeroRiga", prod.get("Numero_Riga", 0)),
                    "data_documento": prod.get("DataDocumento", prod.get("Data_Documento", None)),
                    "fornitore": prod.get("Fornitore", "Sconosciuto"),
                    "descrizione": prod.get("Descrizione", ""),
                    "quantita": prod.get("Quantita", 1),
                    "unita_misura": prod.get("UnitaMisura", prod.get("Unita_Misura", "")),
                    "prezzo_unitario": prod.get("PrezzoUnitario", prod.get("Prezzo_Unitario", 0)),
                    "iva_percentuale": prod.get("IVAPercentuale", prod.get("IVA_Percentuale", 0)),
                    "totale_riga": prod.get("TotaleRiga", prod.get("Totale_Riga", 0)),
                    "categoria": categoria_raw,
                    "codice_articolo": prod.get("CodiceArticolo", prod.get("Codice_Articolo", "")),
                    "prezzo_standard": float(prezzo_std) if prezzo_std and pd.notna(prezzo_std) else None
                })
            
            logger.info(f"ðŸ’¾ {nome_file}: invio {len(records)} record a Supabase")
            
            # Inserimento
            response = supabase_client.table("fatture").insert(records).execute()
            
            righe_confermate = len(response.data) if response.data else len(records)
            logger.info(f"âœ… {nome_file}: {righe_confermate} righe confermate su DB")
            
            # Verifica integritÃ 
            verifica = verifica_integrita_fattura(nome_file, dati_prodotti, user_id, supabase_client)
            
            # Log upload event
            try:
                user_email = st.session_state.user_data.get("email", "unknown")
                
                if verifica and verifica["integrita_ok"]:
                    log_upload_event(
                        user_id=user_id,
                        user_email=user_email,
                        file_name=nome_file,
                        status="SAVED_OK",
                        rows_parsed=verifica["righe_parsed"],
                        rows_saved=verifica["righe_db"],
                        error_stage=None,
                        error_message=None,
                        details=None
                    )
                elif verifica:
                    log_upload_event(
                        user_id=user_id,
                        user_email=user_email,
                        file_name=nome_file,
                        status="SAVED_PARTIAL",
                        rows_parsed=verifica["righe_parsed"],
                        rows_saved=verifica["righe_db"],
                        error_stage="POSTCHECK",
                        error_message=f"Perdita dati: {verifica['perdite']} righe mancanti",
                        details={
                            "righe_parsed": verifica["righe_parsed"],
                            "righe_db": verifica["righe_db"],
                            "perdite": verifica["perdite"]
                        }
                    )
            except Exception as log_error:
                logger.error(f"Errore logging upload event: {log_error}")
            
            # Gestisci discrepanza
            if verifica and not verifica["integrita_ok"]:
                logger.error(f"ðŸš¨ DISCREPANZA {nome_file}: parsed={verifica['righe_parsed']} vs db={verifica['righe_db']}")
                if not silent:
                    if 'verifica_integrita' not in st.session_state:
                        st.session_state.verifica_integrita = []
                    st.session_state.verifica_integrita.append(verifica)
            
            if not silent:
                st.success(f"âœ… {nome_file}: {num_righe} righe salvate su Supabase")
            
            return {
                "success": True,
                "error": None,
                "righe": righe_confermate,
                "location": "supabase"
            }
            
        except Exception as e:
            logger.exception(f"Errore salvataggio Supabase per {nome_file}")
            
            # Log failed event
            try:
                user_email = st.session_state.user_data.get("email", "unknown")
                log_upload_event(
                    user_id=user_id,
                    user_email=user_email,
                    file_name=nome_file,
                    status="FAILED",
                    rows_parsed=num_righe,
                    rows_saved=0,
                    error_stage="SUPABASE_INSERT",
                    error_message=str(e)[:500],
                    details={"exception_type": type(e).__name__}
                )
            except Exception as log_error:
                logger.error(f"Errore logging failed event: {log_error}")
            
            if not silent:
                st.error(f"âŒ Errore salvataggio {nome_file}: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "righe": 0,
                "location": None
            }
    else:
        if not silent:
            st.error("âŒ Supabase non disponibile")
        return {"success": False, "error": "no_supabase", "righe": 0, "location": None}


__all__ = [
    'estrai_dati_da_xml',
    'estrai_dati_da_scontrino_vision',
    'salva_fattura_processata',
]

