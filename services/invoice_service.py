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
import re
import pandas as pd
import streamlit as st
import xmltodict
from typing import List, Dict, Any, Optional

# Import utilities
from utils.formatters import (
    safe_get,
    converti_in_base64,
    calcola_prezzo_standard_intelligente,
    log_upload_event
)
from utils.text_utils import (
    normalizza_stringa,
    estrai_fornitore_xml,
    pulisci_caratteri_corrotti
)
from utils.validation import (
    verifica_integrita_fattura
)

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('invoice')


def normalizza_unita_misura(um: str) -> str:
    """
    Normalizza unità di misura in forma abbreviata standard.
    
    Args:
        um: Unità di misura da normalizzare
    
    Returns:
        str: Unità normalizzata (es: "KG", "PZ", "LT")
    
    Examples:
        "kilogrammi" → "KG"
        "pezzi" → "PZ"
        "litri" → "LT"
        "grammi" → "GR"
    """
    if not um or not isinstance(um, str):
        return ""
    
    um_upper = um.upper().strip()
    
    # Mappa normalizzazione completa
    mappa_normalizzazione = {
        # Peso
        "KILOGRAMMI": "KG",
        "CHILOGRAMMI": "KG",
        "KILOGRAMMO": "KG",
        "CHILOGRAMMO": "KG",
        "KILO": "KG",
        "CHILO": "KG",
        "GRAMMI": "GR",
        "GRAMMO": "GR",
        "GRM": "GR",
        
        # Volume
        "LITRI": "LT",
        "LITRO": "LT",
        "MILLILITRI": "ML",
        "MILLILITRO": "ML",
        "CENTILITRI": "CL",
        "CENTILITRO": "CL",
        
        # Quantità
        "PEZZI": "PZ",
        "PEZZO": "PZ",
        "NUMERO": "NR",
        "UNITA": "PZ",
        "UNITÀ": "PZ",
        
        # Confezioni
        "CONFEZIONE": "CF",
        "CONFEZIONI": "CF",
        "CONF": "CF",
        "SCATOLA": "SC",
        "SCATOLE": "SC",
        "CARTONE": "CT",
        "CARTONI": "CT",
        "BUSTA": "BS",
        "BUSTE": "BS",
        "VASETTO": "VS",
        "VASETTI": "VS",
        "BARATTOLO": "BR",
        "BARATTOLI": "BR",
        "BOTTIGLIA": "BT",
        "BOTTIGLIE": "BT"
    }
    
    # Verifica se già abbreviato correttamente
    abbreviazioni_valide = ["KG", "GR", "LT", "ML", "CL", "PZ", "NR", "CF", "SC", "CT", "BS", "VS", "BR", "BT"]
    if um_upper in abbreviazioni_valide:
        return um_upper
    
    # Normalizza usando mappa
    return mappa_normalizzazione.get(um_upper, um_upper)


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
            categorizza_con_memoria
        )
        
        # Carica cache memoria globale SUBITO
        current_user_id = st.session_state.get('user_data', {}).get('id')
        if current_user_id:
            carica_memoria_completa(current_user_id)
            logger.info("✅ Cache memoria precaricata per elaborazione XML")
        
        contenuto_bytes = file_caricato.read()
        
        # Gestione encoding robusta per caratteri speciali (cinesi, ecc.)
        if isinstance(contenuto_bytes, bytes):
            # ── Step 1: Leggi encoding dichiarato nel prolog XML ─────────────
            # Es: <?xml version='1.0' encoding='GB2312'?>
            xml_prolog = contenuto_bytes[:300].decode('ascii', errors='ignore')
            _enc_match = re.search(r'encoding=["\']([^"\']+)["\']', xml_prolog, re.IGNORECASE)
            declared_enc = _enc_match.group(1).strip().lower() if _enc_match else None
            if declared_enc:
                logger.info(f"📄 Encoding dichiarato nel prolog XML: {declared_enc}")

            # ── Step 2: Costruisci lista priorità encoding ────────────────────
            # Prima il dichiarato (se non è UTF-8, già incluso sotto), poi UTF-8,
            # poi Windows-1252 (comune fatture italiane su Windows), poi CJK, poi latin-1
            encodings_to_try = []
            if declared_enc and declared_enc not in ('utf-8', 'utf8', 'utf_8'):
                encodings_to_try.append(declared_enc)
            encodings_to_try.extend(['utf-8-sig', 'utf-8', 'cp1252', 'gb2312', 'gbk', 'big5', 'latin-1'])

            contenuto = None
            for encoding in encodings_to_try:
                try:
                    contenuto = contenuto_bytes.decode(encoding)
                    logger.info(f"✅ File XML decodificato con encoding: {encoding}")
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if contenuto is None:
                # ── Step 3: Usa charset-normalizer per rilevamento automatico ─
                try:
                    from charset_normalizer import from_bytes as _from_bytes
                    _result = _from_bytes(contenuto_bytes).best()
                    if _result:
                        contenuto = str(_result)
                        logger.info(f"✅ Encoding rilevato da charset-normalizer: {_result.encoding}")
                    else:
                        raise ValueError("charset-normalizer non ha riconosciuto l'encoding")
                except Exception:
                    # Fallback finale: sostituisci caratteri non decodificabili
                    contenuto = contenuto_bytes.decode('utf-8', errors='replace')
                    logger.warning("⚠️ Utilizzato encoding UTF-8 con sostituzione errori (fallback finale)")
        else:
            contenuto = contenuto_bytes
        
        doc = xmltodict.parse(contenuto)
        
        root_key = list(doc.keys())[0]
        fattura = doc[root_key]
        
        data_documento = safe_get(
            fattura,
            ['FatturaElettronicaBody', 'DatiGenerali', 'DatiGeneraliDocumento', 'Data'],
            default='N/A',
            keep_list=False
        )
        
        # ============================================================
        # ESTRAZIONE TIPO DOCUMENTO (fattura vs nota di credito)
        # ============================================================
        # TD01 = Fattura, TD02 = Acconto, TD04 = Nota di Credito,
        # TD05 = Nota di Debito, TD06 = Parcella, TD07 = Autofattura
        tipo_documento = safe_get(
            fattura,
            ['FatturaElettronicaBody', 'DatiGenerali', 'DatiGeneraliDocumento', 'TipoDocumento'],
            default='TD01',
            keep_list=False
        )
        is_nota_credito = str(tipo_documento).upper().strip() == 'TD04'
        if is_nota_credito:
            logger.info(f"📋 NOTA DI CREDITO rilevata (TipoDocumento={tipo_documento})")
        
        fornitore = estrai_fornitore_xml(fattura)
        
        # ============================================================
        # ESTRAZIONE P.IVA CESSIONARIO (destinatario fattura)
        # ============================================================
        # Legge <CessionarioCommittente><IdFiscaleIVA><IdCodice>
        # Usato per validazione: fattura appartiene a questo cliente?
        piva_cessionario = estrai_piva_cessionario_xml(fattura)
        if piva_cessionario:
            logger.info(f"📋 P.IVA Cessionario estratta: {piva_cessionario}")
        
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
        
        # Limite sicurezza: 200 righe max per fattura XML (parsing locale, no API)
        # Se superato, processa le prime 200 e logga warning
        MAX_RIGHE_XML = 200
        righe_originali_count = len(linee)
        if righe_originali_count > MAX_RIGHE_XML:
            logger.warning(f"{file_caricato.name}: {righe_originali_count} righe totali, limitate a {MAX_RIGHE_XML}")
            linee = linee[:MAX_RIGHE_XML]
            st.warning(f"⚠️ Fattura con {righe_originali_count} righe: elaborate le prime {MAX_RIGHE_XML}. Contatta l'assistenza se necessiti di processarle tutte.")
        
        righe_prodotti = []
        for idx, riga in enumerate(linee, start=1):
            if not isinstance(riga, dict):
                continue
            
            try:
                # ============================================================
                # STEP 2: VALIDAZIONE E SKIP RIGHE INVALIDE
                # ============================================================
                # Estrai valori base per validazione
                descrizione_raw = riga.get('Descrizione', '')
                
                # Pulisci caratteri corrotti (encoding errato, caratteri cinesi mal encodati)
                if descrizione_raw:
                    descrizione_raw = pulisci_caratteri_corrotti(descrizione_raw)
                
                quantita_raw = riga.get('Quantita')
                prezzo_base = float(riga.get('PrezzoUnitario', 0) or 0)
                totale_riga = float(riga.get('PrezzoTotale', 0) or 0)
                
                # ============================================================
                # NOTA DI CREDITO: Inverti segno importi se positivi
                # ============================================================
                # Le note di credito (TD04) rappresentano rimborsi/resi.
                # Se il gestionale emette importi positivi, li neghiamo
                # perché nel nostro sistema devono RIDURRE i costi.
                if is_nota_credito:
                    if totale_riga > 0:
                        totale_riga = -totale_riga
                    if prezzo_base > 0:
                        prezzo_base = -prezzo_base
                
                # ============================================================
                # ESTRAZIONE SCONTO MAGGIORAZIONE XML
                # ============================================================
                sconto_percentuale = 0.0
                sconto_maggiorazione = riga.get('ScontoMaggiorazione')
                if sconto_maggiorazione:
                    # Può essere dict singolo o lista
                    if isinstance(sconto_maggiorazione, dict):
                        sconto_maggiorazione = [sconto_maggiorazione]
                    if isinstance(sconto_maggiorazione, list):
                        for sm in sconto_maggiorazione:
                            tipo_sm = sm.get('Tipo', 'SC')  # SC=Sconto, MG=Maggiorazione
                            perc = float(sm.get('Percentuale', 0) or 0)
                            if tipo_sm == 'SC':
                                sconto_percentuale += perc
                            elif tipo_sm == 'MG':
                                sconto_percentuale -= perc  # Maggiorazione riduce lo sconto
                
                # MARK FOR REVIEW: Prezzo zero o mancante (potrebbe essere omaggio, dicitura, o servizio gratuito)
                needs_review_flag = False
                if not prezzo_base or prezzo_base == 0:
                    # Se ha anche totale_riga == 0 e non sembra un prodotto, skip
                    has_totale = totale_riga and totale_riga != 0
                    has_desc = descrizione_raw and len(descrizione_raw.strip()) > 3
                    if not has_totale and not has_desc:
                        continue
                    needs_review_flag = True
                
                # QUANTITÀ: Default = 1 per servizi (se manca ma c'è PrezzoTotale)
                if quantita_raw is None or float(quantita_raw or 0) == 0:
                    if totale_riga and totale_riga != 0:  # Accetta anche negativi (note di credito)
                        quantita = 1.0
                    else:
                        continue
                else:
                    quantita = float(quantita_raw)
                
                # SKIP: Descrizione vuota o invalida (DDT, numeri)
                # ============================================================
                # FIX FATTURE SERVIZI: Controlla descrizione PRIMA di normalizzare
                # ============================================================
                descrizione_raw_stripped = descrizione_raw.strip() if descrizione_raw else ""
                
                # Se descrizione è solo "." o molto corta MA c'è prezzo > 0 → usa fornitore
                if len(descrizione_raw_stripped) <= 3 and len(descrizione_raw_stripped) > 0 and abs(prezzo_base) > 0:
                    descrizione = f"Servizio {fornitore}"
                    logger.info(f"{file_caricato.name} - Riga {idx}: descrizione '{descrizione_raw_stripped}' sostituita con '{descrizione}'")
                else:
                    # Normalizza normalmente
                    descrizione = normalizza_stringa(descrizione_raw)
                
                # SKIP solo se completamente vuota
                if not descrizione or len(descrizione.strip()) == 0:
                    continue
                
                if descrizione.strip().upper() in ['DDT', 'DT', 'N/A']:
                    continue
                
                # TRIM: Descrizioni lunghe (max 100 caratteri)
                if len(descrizione) > 100:
                    descrizione = descrizione[:100] + "..."
                
                # Codice articolo
                codice_articolo = ""
                codice_articolo_raw = riga.get('CodiceArticolo', [])
                if isinstance(codice_articolo_raw, list) and len(codice_articolo_raw) > 0:
                    codice_articolo = codice_articolo_raw[0].get('CodiceValore', '')
                elif isinstance(codice_articolo_raw, dict):
                    codice_articolo = codice_articolo_raw.get('CodiceValore', '')
                
                # Estrai e normalizza unità di misura
                unita_misura_raw = riga.get('UnitaMisura', '')
                unita_misura = normalizza_unita_misura(unita_misura_raw)
                
                aliquota_iva = float(riga.get('AliquotaIVA', 0))
                
                # Calcola prezzo effettivo (include sconti)
                # Usa abs() per gestire correttamente quantità negative (resi)
                # e note di credito (totale negativo)
                if abs(quantita) > 0 and totale_riga != 0:
                    prezzo_unitario = totale_riga / quantita
                else:
                    prezzo_unitario = prezzo_base
                    if totale_riga == 0:
                        totale_riga = quantita * prezzo_unitario
                
                prezzo_unitario = round(prezzo_unitario, 4)
                
                # Se sconto non rilevato da XML tag ma c'è differenza prezzo base vs effettivo,
                # calcola sconto_percentuale dal confronto prezzi
                if sconto_percentuale == 0.0 and prezzo_base != 0 and abs(prezzo_unitario) < abs(prezzo_base):
                    sconto_percentuale = round(((abs(prezzo_base) - abs(prezzo_unitario)) / abs(prezzo_base)) * 100, 2)
                

                # Auto-categorizzazione
                categoria_finale = categorizza_con_memoria(
                    descrizione=descrizione,
                    prezzo=prezzo_unitario,
                    quantita=quantita,
                    user_id=current_user_id,
                    fornitore=fornitore,
                    unita_misura=unita_misura
                )
                
                # Strategia ibrida: salva tutto, marca per review se necessario
                needs_review = needs_review_flag  # Inherit from prezzo==0 check above
                
                if prezzo_unitario == 0 or totale_riga == 0:
                    if categoria_finale == "📝 NOTE E DICITURE":
                        needs_review = True
                    elif categoria_finale == "Da Classificare":
                        needs_review = True
                elif categoria_finale == "📝 NOTE E DICITURE" and prezzo_unitario > 0:
                    needs_review = True
                    logger.warning(f"⚠️ NOTE con €{prezzo_unitario:.2f} → review: {descrizione[:50]}")
                
                # Calcolo prezzo standard (skip per omaggi/prezzo zero - non significativo)
                if prezzo_unitario != 0:
                    prezzo_std = calcola_prezzo_standard_intelligente(
                        descrizione=descrizione,
                        um=unita_misura,
                        prezzo_unitario=abs(prezzo_unitario)
                    )
                else:
                    prezzo_std = None
                
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
                    'Prezzo_Standard': prezzo_std,
                    'needs_review': needs_review,
                    'piva_cessionario': piva_cessionario,  # P.IVA destinatario fattura
                    'tipo_documento': tipo_documento,  # TD01=Fattura, TD04=Nota Credito
                    'sconto_percentuale': round(sconto_percentuale, 2)  # % sconto applicato
                })
            except Exception as e:
                logger.warning(f"{file_caricato.name} - Riga {idx} skippata: {str(e)[:100]}")
                continue
        
        logger.info(f"✅ {file_caricato.name}: {len(righe_prodotti)} righe estratte")
        
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore lettura XML: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.warning(f"⚠️ File {file_caricato.name}: impossibile leggere")
        return []


def estrai_piva_cessionario_xml(fattura: dict) -> str:
    """
    Estrae P.IVA del cessionario (destinatario fattura) da XML.
    
    IMPORTANTE: Legge <CessionarioCommittente> (chi RICEVE la fattura),
    NON <CedentePrestatore> (chi EMETTE la fattura).
    
    Args:
        fattura: Dizionario parsed da xmltodict
    
    Returns:
        str: P.IVA cessionario (11 cifre) o None se non trovata
    """
    try:
        # Percorso primario: FatturaElettronicaHeader > CessionarioCommittente
        cessionario = safe_get(
            fattura,
            ['FatturaElettronicaHeader', 'CessionarioCommittente', 'DatiAnagrafici', 'IdFiscaleIVA'],
            default=None,
            keep_list=False
        )
        
        if cessionario:
            id_paese = cessionario.get('IdPaese', '')
            id_codice = cessionario.get('IdCodice', '')
            
            # Valida formato P.IVA italiana
            if id_paese == 'IT' and id_codice and len(str(id_codice)) == 11:
                return str(id_codice)
            elif id_codice:
                # P.IVA estera o formato non standard
                logger.warning(f"P.IVA cessionario non italiana: {id_paese}{id_codice}")
                return str(id_codice)
        
        # Fallback: cerca in altri percorsi possibili
        cessionario_alt = safe_get(
            fattura,
            ['CessionarioCommittente', 'DatiAnagrafici', 'IdFiscaleIVA'],
            default=None,
            keep_list=False
        )
        
        if cessionario_alt:
            id_codice = cessionario_alt.get('IdCodice', '')
            if id_codice and len(str(id_codice)) == 11:
                return str(id_codice)
        
        return None
        
    except Exception as e:
        logger.warning(f"Errore estrazione P.IVA cessionario: {e}")
        return None


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
            ottieni_categoria_prodotto,
            carica_memoria_completa
        )
        from openai import OpenAI
        
        # Ottieni client se non fornito
        if openai_client is None:
            api_key = st.secrets.get("OPENAI_API_KEY", "")
            if not api_key:
                st.error("❌ OPENAI_API_KEY mancante")
                return []
            openai_client = OpenAI(api_key=api_key)
        
        file_caricato.seek(0)
        base64_image = converti_in_base64(file_caricato, file_caricato.name)
        if not base64_image:
            return []
        
        prompt = """Sei un esperto contabile per ristoranti italiani. Analizza questo documento (scontrino/fattura) ed estrai i dati.

INFORMAZIONI DA ESTRARRE:
1. **Fornitore**: Nome completo del fornitore. Può essere:
   - Società/Azienda (es. "METRO SRL", "CRAI", "EKAF")
   - Persona fisica/Professionista (es. "MARIO ROSSI", "Studio BIANCHI")
   Cerca in: Ragione Sociale, Denominazione, Cedente/Prestatore, Nome e Cognome
2. **P.IVA Cessionario/Destinatario**: Partita IVA del destinatario/cliente (CHI RICEVE la fattura)
   - Cerca in: Cessionario, Destinatario, Cliente, P.IVA destinazione
   - Formato: numero (es. "12345678901" o "IT12345678901")
   - Se non trovi la P.IVA destinatario, restituisci stringa vuota ""
3. **Data**: Data del documento in formato YYYY-MM-DD
4. **Righe articoli**: Lista completa di TUTTI i prodotti acquistati

PER OGNI ARTICOLO:
- Descrizione (normalizzata in MAIUSCOLO)
- Quantità (numero, se non specificato usa 1.0)
- Prezzo unitario in € (numero decimale)
- Totale riga in € (numero decimale)

REGOLE IMPORTANTI:
- Estrai SOLO le righe articolo vere (ignora intestazioni, note, pubblicità)
- Se manca la quantità, usa 1.0
- Se manca prezzo unitario ma c'è il totale, calcola: prezzo_unitario = totale / quantità
- Normalizza descrizioni: "parmigiano reggiano" → "PARMIGIANO REGGIANO"
- Date italiane (es. 08/12/2024) converti in 2024-12-08

FORMATO RISPOSTA (SOLO JSON):
{
  "fornitore": "NOME FORNITORE",
  "piva_cessionario": "12345678901",
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
        with st.spinner(f"🔍 Analizzo {file_caricato.name} con AI..."):
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}
                    ]
                }],
                max_tokens=4000,  # Aumentato da 1500 per supportare fatture con molti prodotti
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
        except Exception as e:
            logger.debug(f"Strip markdown code fences fallito: {e}")

        testo = testo.strip()
        
        try:
            dati = json.loads(testo)
        except json.JSONDecodeError:
            st.error(f"❌ Risposta Vision non valida per {file_caricato.name}")

            return []
        
        fornitore = normalizza_stringa(dati.get('fornitore', 'Fornitore Sconosciuto'))
        data_documento = dati.get('data', 'N/A')
        piva_cessionario = dati.get('piva_cessionario', '')  # Estrai P.IVA cessionario
        
        try:
            pd.to_datetime(data_documento)
        except Exception as e:
            data_documento = pd.Timestamp.now().strftime('%Y-%m-%d')
            st.warning(f"⚠️ Data non valida, uso data odierna: {e}")
        
        righe_prodotti = []
        current_user_id = st.session_state.get('user_data', {}).get('id')
        
        # Precarica memoria per categorizzazione (come in XML path)
        if current_user_id:
            carica_memoria_completa(current_user_id)
        
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
            
            # Estrai e normalizza unità di misura
            unita_misura_raw = riga.get('unita_misura', 'PZ')
            unita_misura = normalizza_unita_misura(unita_misura_raw)
            
            try:
                totale_riga = float(riga.get('totale', 0))
            except (ValueError, TypeError):
                totale_riga = 0
            
            # Calcola mancanti
            if totale_riga == 0 and prezzo_unitario > 0:
                totale_riga = quantita * prezzo_unitario
            if prezzo_unitario == 0 and totale_riga > 0 and quantita > 0:
                prezzo_unitario = totale_riga / quantita
            
            # Categorizzazione (usa stesso sistema moderno del path XML)
            categoria_iniziale = ottieni_categoria_prodotto(descrizione, current_user_id) if current_user_id else "Da Classificare"
            
            # needs_review: True se non classificato (allineato con path XML)
            needs_review = (categoria_iniziale == "Da Classificare")
            
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
                'Prezzo_Standard': prezzo_std,
                'needs_review': needs_review,
                'piva_cessionario': piva_cessionario  # P.IVA destinatario per validazione
            })
                # ============================================================
        # TRACKING COSTI AI
        # ============================================================
        # Traccia utilizzo e costo AI per il ristorante
        try:
            from services import get_supabase_client
            
            # Calcola costo basato su token usage
            tokens_usati = response.usage.total_tokens
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            
            # Pricing GPT-4o-mini (Gen 2026):
            # Input: $0.15 per 1M token
            # Output: $0.60 per 1M token
            # Vision detail=high: ~$0.01-0.03 per immagine
            costo_input = (prompt_tokens / 1_000_000) * 0.15
            costo_output = (completion_tokens / 1_000_000) * 0.60
            costo_totale = round(costo_input + costo_output, 4)
            
            # Incrementa contatore per il ristorante
            ristorante_id = st.session_state.get('ristorante_id')
            if ristorante_id:
                try:
                    supabase_client = get_supabase_client()
                    result = supabase_client.rpc('increment_ai_cost', {
                        'p_ristorante_id': ristorante_id,
                        'p_cost': costo_totale,
                        'p_tokens': tokens_usati
                    }).execute()
                    
                    logger.info(f"💰 AI Cost tracked: ${costo_totale:.4f} ({tokens_usati} tokens) - Ristorante: {ristorante_id}")
                except Exception as rpc_err:
                    # RPC potrebbe non esistere, avere firma diversa o permessi insufficienti
                    logger.error(f"❌ Errore RPC increment_ai_cost: {rpc_err}")
                    logger.warning(f"⚠️ Costo AI NON salvato su DB: ${costo_totale:.4f} ({tokens_usati} tokens)")
                    # Non bloccare l'elaborazione anche se tracking fallisce
            else:
                # ⚠️ Utente senza ristorante_id (legacy o errore configurazione)
                logger.warning(f"⚠️ AI Cost NON tracked: ristorante_id mancante. Costo: ${costo_totale:.4f} ({tokens_usati} tokens)")
        except Exception as track_error:
            # Non bloccare l'elaborazione se il tracking fallisce
            logger.warning(f"⚠️ Errore tracking costo AI: {track_error}")
        # ============================================================
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore Vision: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.error(f"❌ Errore Vision su {file_caricato.name}: {str(e)}")
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
        - Priorità: Supabase SEMPRE (no fallback JSON)
        - Forza categoria valida (mai NULL/vuoto → "Da Classificare")
        - Verifica integrità post-salvataggio
        - Logging automatico su tabella upload_events
    """
    from services import get_supabase_client
    
    # Verifica autenticazione
    if "user_data" not in st.session_state or "id" not in st.session_state.user_data:
        if not silent:
            st.error("❌ Errore: Utente non autenticato. Effettua il login.")
        return {"success": False, "error": "not_authenticated", "righe": 0, "location": None}
    
    user_id = st.session_state.user_data["id"]
    ristorante_id = st.session_state.get('ristorante_id')  # Può essere None per utenti legacy
    
    # ⚠️ VALIDAZIONE: Utenti senza ristorante_id non possono salvare fatture
    if not ristorante_id:
        logger.error(f"❌ ERRORE CRITICO: ristorante_id mancante per user_id={user_id}")
        logger.error(f"   File: {nome_file}, Righe: {len(dati_prodotti)}")
        if not silent:
            st.error("⚠️ Configurazione account incompleta. Impossibile salvare fatture.")
            st.info("💡 Contatta l'assistenza per completare la configurazione del tuo account.")
        return {"success": False, "error": "missing_ristorante_id", "righe": 0, "location": None}
    
    num_righe = len(dati_prodotti)
    
    # Ottieni client singleton se non fornito
    if supabase_client is None:
        supabase_client = get_supabase_client()
    
    # Salvataggio Supabase
    if supabase_client is not None:
        try:
            if not dati_prodotti:
                return {"success": False, "error": "no_data", "righe": 0, "location": None}
            

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
                    "ristorante_id": ristorante_id,  # 🏢 MULTI-RISTORANTE
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
                    "prezzo_standard": float(prezzo_std) if prezzo_std and pd.notna(prezzo_std) else None,
                    "needs_review": prod.get("needs_review", False),
                    "tipo_documento": prod.get("tipo_documento", "TD01"),
                    "sconto_percentuale": prod.get("sconto_percentuale", 0.0)
                })
            

            # Inserimento
            response = supabase_client.table("fatture").insert(records).execute()
            
            righe_confermate = len(response.data) if response.data else len(records)

            
            # Verifica integrità
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
                logger.error(f"🚨 DISCREPANZA {nome_file}: parsed={verifica['righe_parsed']} vs db={verifica['righe_db']}")
                if not silent:
                    if 'verifica_integrita' not in st.session_state:
                        st.session_state.verifica_integrita = []
                    st.session_state.verifica_integrita.append(verifica)
            
            if not silent:
                st.success(f"✅ {nome_file}: {num_righe} righe salvate su Supabase")
            
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
                st.error(f"❌ Errore salvataggio {nome_file}: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "righe": 0,
                "location": None
            }
    else:
        if not silent:
            st.error("❌ Supabase non disponibile")
        return {"success": False, "error": "no_supabase", "righe": 0, "location": None}


__all__ = [
    'estrai_dati_da_xml',
    'estrai_dati_da_scontrino_vision',
    'salva_fattura_processata',
]

