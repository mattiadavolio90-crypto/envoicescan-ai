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
from datetime import datetime
import pandas as pd
import streamlit as st
import xmltodict
from defusedxml import ElementTree as _DefusedET
from typing import List, Dict, Any, Optional


def _ui_msg(level: str, msg: str) -> None:
    """
    Invia un messaggio all'UI Streamlit se disponibile,
    altrimenti lo logga (contesto worker/CLI).
    """
    try:
        fn = getattr(st, level, None)
        if fn:
            fn(msg)
            return
    except Exception:
        pass
    logger.info("[UI %s] %s", level, msg)


# Import utilities
from utils.formatters import (
    safe_get,
    converti_in_base64,
    calcola_prezzo_standard_intelligente,
    calcola_alert_data_consegna_td24,
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
from config.constants import MAX_FILE_SIZE_P7M, VISION_DAILY_LIMIT
logger = get_logger('invoice')


class VisionDailyLimitExceededError(RuntimeError):
    """Eccezione custom quando la quota Vision giornaliera del ristorante è esaurita."""

    def __init__(self, used: int, limit: int, ristorante_id: str | None = None):
        self.used = int(used or 0)
        self.limit = int(limit or 0)
        self.ristorante_id = ristorante_id
        super().__init__(
            f"QUOTA VISION RAGGIUNTA — Limite giornaliero esaurito ({self.used}/{self.limit}) per PDF/JPG/PNG. "
            f"Questo file è stato scartato. Riprova domani oppure carica XML/P7M."
        )


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
        return "PZ"
    
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


def _estrai_xml_con_asn1crypto(contenuto_bytes: bytes) -> bytes | None:
    """Metodo 1: Parsing ASN.1/CMS con asn1crypto (gestisce strutture nidificate)."""
    try:
        from asn1crypto import cms, core
        content_info = cms.ContentInfo.load(contenuto_bytes)
        signed_data = content_info['content']
        encap_content = signed_data['encap_content_info']['content']
        if encap_content is not None:
            raw = encap_content.native
            if isinstance(raw, bytes) and b'<' in raw:
                logger.info("✅ XML estratto da .p7m tramite parsing ASN.1/CMS")
                return raw
            # Potrebbe essere un OCTET STRING annidato
            if isinstance(raw, bytes):
                try:
                    inner = core.OctetString.load(raw)
                    inner_bytes = inner.native
                    if isinstance(inner_bytes, bytes) and b'<' in inner_bytes:
                        logger.info("✅ XML estratto da .p7m tramite ASN.1 (OCTET STRING annidato)")
                        return inner_bytes
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"⚠️ Parsing ASN.1 .p7m fallito: {e}")
    return None


def _estrai_xml_con_openssl(contenuto_bytes: bytes) -> bytes | None:
    """Metodo 2: OpenSSL via subprocess (gestisce anche firme multiple/nidificate)."""
    import subprocess
    import tempfile
    import os
    try:
        # Verifica che openssl sia disponibile
        subprocess.run(["openssl", "version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    tmp_in = None
    tmp_out = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.p7m') as f:
            f.write(contenuto_bytes)
            tmp_in = f.name
        tmp_out = tmp_in + '.xml'

        result = subprocess.run(
            ["openssl", "cms", "-verify", "-noverify", "-inform", "DER",
             "-in", tmp_in, "-out", tmp_out],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            # Prova con smime invece di cms
            result = subprocess.run(
                ["openssl", "smime", "-verify", "-noverify", "-inform", "DER",
                 "-in", tmp_in, "-out", tmp_out],
                capture_output=True, timeout=30
            )

        if result.returncode == 0 and os.path.exists(tmp_out):
            with open(tmp_out, 'rb') as f:
                xml_bytes = f.read()
            if xml_bytes and b'<' in xml_bytes:
                logger.info("✅ XML estratto da .p7m tramite OpenSSL")
                return xml_bytes
    except Exception as e:
        logger.warning(f"⚠️ Estrazione OpenSSL .p7m fallita: {e}")
    finally:
        for path in [tmp_in, tmp_out]:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    return None


def _estrai_xml_con_pattern(contenuto_bytes: bytes) -> bytes | None:
    """Metodo 3: Fallback - ricerca pattern XML nel binario."""
    try:
        # Cerca l'inizio dell'XML (inclusi namespace vari usati da SDI)
        patterns_inizio = [b'<?xml', b'<p:FatturaElettronica', b'<FatturaElettronica',
                           b'<ns2:FatturaElettronica', b'<ns3:FatturaElettronica',
                           b'<n:FatturaElettronica', b'<a:FatturaElettronica']
        start_idx = -1
        for pat in patterns_inizio:
            idx = contenuto_bytes.find(pat)
            if idx >= 0 and (start_idx < 0 or idx < start_idx):
                start_idx = idx

        if start_idx >= 0:
            # Cerca la fine dell'XML (tutti i possibili namespace)
            end_markers = [b'</p:FatturaElettronica>', b'</FatturaElettronica>',
                           b'</ns2:FatturaElettronica>', b'</ns3:FatturaElettronica>',
                           b'</n:FatturaElettronica>', b'</a:FatturaElettronica>']
            end_idx = -1
            for marker in end_markers:
                pos = contenuto_bytes.find(marker, start_idx)
                if pos >= 0:
                    end_idx = pos + len(marker)
                    break

            if end_idx != -1 and end_idx > start_idx and start_idx >= 0:
                xml_bytes = contenuto_bytes[start_idx:end_idx]
                # Verifica qualità: se contiene control chars invalidi per XML
                # (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F), l'XML è corrotto
                # (succede con OCTET STRING chunked dove i DER header sono inclusi)
                bad_bytes = sum(1 for b in xml_bytes if b < 32 and b not in (9, 10, 13))
                if bad_bytes > 0:
                    logger.warning(f"⚠️ Pattern search: XML contiene {bad_bytes} control chars invalidi - rifiutato, provo metodo successivo")
                    return None
                logger.info("✅ XML estratto da .p7m tramite ricerca pattern (fallback)")
                return xml_bytes
    except Exception as e:
        logger.warning(f"⚠️ Ricerca pattern XML in .p7m fallita: {e}")
    return None


def _estrai_xml_con_der_scan(contenuto_bytes: bytes) -> bytes | None:
    """Metodo 4: Riassemblaggio chunk DER OCTET STRING.
    
    Nei p7m italiani con firma CAdES, l'XML è spesso dentro un
    Constructed OCTET STRING (tag 0x24, indefinite length 0x80)
    suddiviso in chunk primitivi (tag 0x04 + lunghezza DER).
    Questo metodo riassembla i chunk rimuovendo gli header DER intermedi.
    """
    try:
        # Cerca il primo <?xml o BOM+<?xml
        xml_pos = contenuto_bytes.find(b'<?xml')
        if xml_pos < 0:
            bom_pos = contenuto_bytes.find(b'\xef\xbb\xbf')
            if bom_pos >= 0:
                xml_pos = bom_pos
            else:
                return None

        # Cerca il Constructed OCTET STRING (0x24 0x80) prima di <?xml
        found_outer = False
        for i in range(xml_pos - 1, max(0, xml_pos - 20), -1):
            if contenuto_bytes[i] == 0x80 and i > 0 and contenuto_bytes[i - 1] == 0x24:
                pos = i + 1
                found_outer = True
                break

        if not found_outer:
            return None

        # Leggi chunk per chunk fino a 0x00 0x00 (end-of-contents)
        total_data = bytearray()
        chunks = 0
        while pos < len(contenuto_bytes) - 2:
            if contenuto_bytes[pos] == 0x00 and contenuto_bytes[pos + 1] == 0x00:
                break
            if contenuto_bytes[pos] != 0x04:
                break

            lb = contenuto_bytes[pos + 1]
            if lb < 0x80:
                chunk_len = lb
                header_len = 2
            elif lb == 0x81:
                chunk_len = contenuto_bytes[pos + 2]
                header_len = 3
            elif lb == 0x82:
                chunk_len = (contenuto_bytes[pos + 2] << 8) | contenuto_bytes[pos + 3]
                header_len = 4
            elif lb == 0x83:
                chunk_len = (contenuto_bytes[pos + 2] << 16) | (contenuto_bytes[pos + 3] << 8) | contenuto_bytes[pos + 4]
                header_len = 5
            else:
                break

            if pos + header_len + chunk_len > len(contenuto_bytes):
                break

            total_data.extend(contenuto_bytes[pos + header_len : pos + header_len + chunk_len])
            pos += header_len + chunk_len
            chunks += 1

        if chunks > 1 and b'FatturaElettronica' in total_data:
            logger.info(f"✅ XML estratto da .p7m tramite riassemblaggio DER ({chunks} chunks, {len(total_data)} bytes)")
            return bytes(total_data)
    except Exception as e:
        logger.warning(f"⚠️ Riassemblaggio DER .p7m fallito: {e}")
    return None


def _estrai_xml_con_pulizia_byte(contenuto_bytes: bytes) -> bytes | None:
    """Metodo 5: Rimuovi byte binari DER e riassembla XML.
    
    Nei p7m con OCTET STRING chunked, il contenuto XML è spezzato da
    header DER (tag + length). Rimuovendo tutti i byte non-ASCII si ottiene
    il testo XML riassemblato.
    """
    try:
        if b'FatturaElettronica' not in contenuto_bytes:
            return None
        
        # Rimuovi byte non-ASCII (mantieni solo printable + whitespace XML-valido)
        cleaned = bytearray()
        for b in contenuto_bytes:
            if 32 <= b <= 126 or b in (9, 10, 13):
                cleaned.append(b)
        text = bytes(cleaned)
        
        # Cerca inizio XML
        patterns_inizio = [b'<?xml', b'<p:FatturaElettronica', b'<FatturaElettronica',
                           b'<ns2:FatturaElettronica', b'<ns3:FatturaElettronica',
                           b'<n:FatturaElettronica', b'<a:FatturaElettronica']
        start_idx = -1
        for pat in patterns_inizio:
            idx = text.find(pat)
            if idx >= 0 and (start_idx < 0 or idx < start_idx):
                start_idx = idx
        
        if start_idx < 0:
            return None
        
        # Cerca fine XML
        end_markers = [b'</p:FatturaElettronica>', b'</FatturaElettronica>',
                       b'</ns2:FatturaElettronica>', b'</ns3:FatturaElettronica>',
                       b'</n:FatturaElettronica>', b'</a:FatturaElettronica>']
        end_idx = -1
        for marker in end_markers:
            pos = text.find(marker, start_idx)
            if pos >= 0:
                end_idx = pos + len(marker)
                break
        
        if end_idx > start_idx:
            xml_bytes = text[start_idx:end_idx]
            logger.info(f"✅ XML estratto da .p7m tramite pulizia byte ({len(xml_bytes)} bytes)")
            return xml_bytes
    except Exception as e:
        logger.warning(f"⚠️ Pulizia byte .p7m fallita: {e}")
    return None


def _prova_decodifica_base64(contenuto_bytes: bytes) -> bytes | None:
    """Se il p7m è base64-encoded (PEM), decodifica e restituisce il DER."""
    import base64
    try:
        # Rimuovi header/footer PEM se presenti
        testo = contenuto_bytes
        if b'-----BEGIN' in testo:
            linee = testo.split(b'\n')
            linee = [l for l in linee if not l.startswith(b'-----')]
            testo = b''.join(linee)
        # Rimuovi whitespace (base64 multi-linea)
        testo = testo.replace(b'\r', b'').replace(b'\n', b'').replace(b' ', b'')
        decoded = base64.b64decode(testo, validate=True)
        # Verifica che sia DER valido (inizia con 0x30 = SEQUENCE)
        if decoded and decoded[0:1] == b'\x30':
            return decoded
    except Exception as b64_err:
        logger.debug("_prova_decodifica_base64: tentativo fallito (%s)", b64_err)
    return None


def _pulisci_xml_bytes(xml_bytes: bytes) -> bytes:
    """Pulisce XML estratto da caratteri problematici comuni nelle fatture italiane."""
    import re as _re
    
    # Rimuovi BOM e byte nulli iniziali
    xml_bytes = xml_bytes.lstrip(b'\xef\xbb\xbf\x00')
    
    # Rimuovi byte nulli sparsi (common in some p7m extractions)
    xml_bytes = xml_bytes.replace(b'\x00', b'')
    
    # Rimuovi caratteri di controllo (tranne \t, \n, \r che sono validi in XML)
    xml_bytes = _re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f]', b'', xml_bytes)
    
    # Gestisci problemi di encoding: prova a decodificare e ri-encodare
    # Molte fatture dichiarano UTF-8 ma usano Latin-1/CP1252
    try:
        xml_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            # Prova Latin-1 → UTF-8
            text = xml_bytes.decode('latin-1')
            xml_bytes = text.encode('utf-8')
            # Aggiorna la dichiarazione encoding se presente
            xml_bytes = xml_bytes.replace(b'encoding="ISO-8859-1"', b'encoding="UTF-8"')
            xml_bytes = xml_bytes.replace(b"encoding='ISO-8859-1'", b"encoding='UTF-8'")
            xml_bytes = xml_bytes.replace(b'encoding="iso-8859-1"', b'encoding="UTF-8"')
            logger.info("✅ P7M: corretto encoding Latin-1 → UTF-8")
        except Exception as enc_err:
            logger.warning(f"Conversione Latin-1/UTF-8 fallita: {enc_err}")
    
    return xml_bytes


def estrai_xml_da_p7m(file_caricato):
    """
    Estrae il contenuto XML da un file .p7m (firma digitale CAdES/PKCS#7).
    
    Args:
        file_caricato: File .p7m caricato (UploadedFile di Streamlit)
        
    Returns:
        io.BytesIO: Stream contenente l'XML estratto, pronto per estrai_dati_da_xml()
        
    Raises:
        ValueError: Se non è possibile estrarre XML dal file .p7m
    """
    import io
    
    contenuto_bytes = file_caricato.read()
    
    # Limite dimensione file P7M
    if len(contenuto_bytes) > MAX_FILE_SIZE_P7M:
        raise ValueError(f"File P7M troppo grande ({len(contenuto_bytes) / 1_000_000:.1f} MB). Limite: {MAX_FILE_SIZE_P7M // 1_000_000} MB")
    
    # Se il file è base64 encoded (PEM), decodifica prima
    raw_bytes = contenuto_bytes
    if raw_bytes[0:1] != b'\x30':
        decoded = _prova_decodifica_base64(raw_bytes)
        if decoded:
            logger.info("✅ P7M base64 decodificato in DER")
            raw_bytes = decoded
    
    xml_bytes = None
    
    # Metodo 1: ASN.1/CMS parsing (più affidabile)
    xml_bytes = _estrai_xml_con_asn1crypto(raw_bytes)
    
    # Metodo 2: OpenSSL (gestisce firme complesse/nidificate)
    if xml_bytes is None:
        xml_bytes = _estrai_xml_con_openssl(raw_bytes)
    
    # Metodo 3: ricerca pattern nel binario
    if xml_bytes is None:
        xml_bytes = _estrai_xml_con_pattern(raw_bytes)
    
    # Metodo 4: scansione manuale strutture DER per OCTET STRING con XML
    if xml_bytes is None:
        xml_bytes = _estrai_xml_con_der_scan(raw_bytes)
    
    # Metodo 5: rimuovi byte binari DER e riassembla XML dal testo pulito
    # (essenziale per p7m con OCTET STRING chunked dove asn1crypto non è disponibile)
    if xml_bytes is None:
        xml_bytes = _estrai_xml_con_pulizia_byte(raw_bytes)
    
    # Se ancora nulla, riprova pattern sul contenuto originale (pre-base64 decode)
    if xml_bytes is None and raw_bytes is not contenuto_bytes:
        xml_bytes = _estrai_xml_con_pattern(contenuto_bytes)
    
    # Riprova pulizia byte sul contenuto originale
    if xml_bytes is None and raw_bytes is not contenuto_bytes:
        xml_bytes = _estrai_xml_con_pulizia_byte(contenuto_bytes)
    
    if xml_bytes is None or len(xml_bytes) == 0:
        raise ValueError("Impossibile estrarre XML dal file .p7m - firma digitale non riconosciuta")
    
    # Pulizia XML: rimuovi caratteri problematici, fix encoding
    xml_bytes = _pulisci_xml_bytes(xml_bytes)
    
    # Validazione soft: verifica che contenga il tag radice FatturaElettronica
    # NON usiamo ET.fromstring() perché è troppo rigido e fallisce su XML
    # con encoding misti che però estrai_dati_da_xml gestisce correttamente
    if b'FatturaElettronica' not in xml_bytes:
        raise ValueError("File .p7m: contenuto estratto non contiene una FatturaElettronica")
    
    # Restituisci come BytesIO con attributo name per compatibilità con estrai_dati_da_xml
    xml_stream = io.BytesIO(xml_bytes)
    xml_stream.name = getattr(file_caricato, 'name', 'fattura.xml').replace('.p7m', '.xml')
    return xml_stream


def estrai_dati_da_xml(file_caricato, user_id: str = None):
    """
    Estrae dati da fatture XML elettroniche italiane.
    
    Args:
        file_caricato: File XML caricato (st.UploadedFile, BytesIO, o file-like con .name)
        user_id:       ID utente per precarico memoria classificazioni.
                       Se None, tenta di leggerlo da st.session_state (retrocompatibilità
                       con path Streamlit). Passare esplicitamente dal worker FastAPI.
        
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
        
        # Risolvi user_id: parametro esplicito ha priorità su session_state
        # Il fallback su session_state garantisce retrocompatibilità con Streamlit.
        current_user_id = user_id
        if current_user_id is None:
            try:
                current_user_id = st.session_state.get('user_data', {}).get('id')
            except Exception:
                pass  # Fuori contesto Streamlit (worker, test) — nessun session_state
        
        # Carica cache memoria globale SUBITO
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
                except (ImportError, ValueError) as enc_err:
                    # Fallback finale: sostituisci caratteri non decodificabili
                    contenuto = contenuto_bytes.decode('utf-8', errors='replace')
                    logger.warning(f"⚠️ Encoding fallback UTF-8 con sostituzione: {enc_err}")
        else:
            contenuto = contenuto_bytes
        
        # 🔒 Validazione XXE: verifica assenza entità esterne prima del parsing
        try:
            _DefusedET.fromstring(contenuto if isinstance(contenuto, str) else contenuto.decode('utf-8', errors='replace'))
        except Exception as xxe_err:
            logger.warning(f"⚠️ Validazione XML sicurezza fallita: {xxe_err}")
            raise ValueError(f"XML non valido o potenzialmente pericoloso: {xxe_err}")
        
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
        _TIPI_DOCUMENTO_VALIDI = {'TD01', 'TD02', 'TD04', 'TD05', 'TD06', 'TD07', 'TD16', 'TD17', 'TD18', 'TD19', 'TD20', 'TD24', 'TD25', 'TD26', 'TD27'}
        tipo_documento_raw = safe_get(
            fattura,
            ['FatturaElettronicaBody', 'DatiGenerali', 'DatiGeneraliDocumento', 'TipoDocumento'],
            default='TD01',
            keep_list=False
        )
        tipo_documento = str(tipo_documento_raw).upper().strip()
        if tipo_documento not in _TIPI_DOCUMENTO_VALIDI:
            logger.warning(f"⚠️ TipoDocumento sconosciuto: '{tipo_documento_raw}', fallback a TD01")
            tipo_documento = 'TD01'
        is_nota_credito = tipo_documento == 'TD04'
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

        # ============================================================
        # ESTRAZIONE DATA CONSEGNA DA DatiDDT (fatture differite TD24)
        # ============================================================
        # Mappa numero_riga → data consegna (YYYY-MM-DD) dal blocco DatiDDT.
        # Schema A/C: DatiDDT con RiferimentoNumeroLinea + DataDDT
        # Schema B: idem, date anche ripetute in Descrizione
        # Schema D: nessun DatiDDT → fallback regex GG/MM/AAAA in Descrizione
        _ddt_date_map: Dict[int, str] = {}  # linea → "YYYY-MM-DD"
        _ddt_global_date: Optional[str] = None  # data DDT senza RiferimentoNumeroLinea
        is_td24 = (tipo_documento == 'TD24')

        if is_td24:
            dati_generali = safe_get(body, ['DatiGenerali'], default={}, keep_list=False)
            dati_ddt_raw = dati_generali.get('DatiDDT') if isinstance(dati_generali, dict) else None
            if dati_ddt_raw is not None:
                if isinstance(dati_ddt_raw, dict):
                    dati_ddt_raw = [dati_ddt_raw]
                if isinstance(dati_ddt_raw, list):
                    for ddt_block in dati_ddt_raw:
                        if not isinstance(ddt_block, dict):
                            continue
                        data_ddt = str(ddt_block.get('DataDDT') or '').strip()
                        if not data_ddt:
                            continue
                        rif_linee = ddt_block.get('RiferimentoNumeroLinea')
                        if rif_linee is None:
                            # Nessun riferimento riga → vale per tutte le righe
                            _ddt_global_date = data_ddt
                        else:
                            if not isinstance(rif_linee, list):
                                rif_linee = [rif_linee]
                            for num in rif_linee:
                                try:
                                    _ddt_date_map[int(num)] = data_ddt
                                except (ValueError, TypeError):
                                    pass
            if _ddt_date_map or _ddt_global_date:
                logger.info(
                    f"📅 TD24 DatiDDT: {len(_ddt_date_map)} righe mappate"
                    + (f", data globale={_ddt_global_date}" if _ddt_global_date else "")
                )

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
                        logger.warning(
                            f"⚠️ {file_caricato.name} - Riga {idx} scartata: "
                            f"prezzo=0, totale=0, descrizione assente/corta. "
                            f"Desc='{(descrizione_raw or '')[:80]}', Fornitore='{fornitore}'"
                        )
                        continue
                    needs_review_flag = True
                
                # QUANTITÀ: Default = 1 per servizi (se manca ma c'è PrezzoTotale)
                if quantita_raw is None or float(quantita_raw or 0) == 0:
                    if totale_riga and totale_riga != 0:  # Accetta anche negativi (note di credito)
                        quantita = 1.0
                    else:
                        logger.warning(
                            f"⚠️ {file_caricato.name} - Riga {idx} scartata: "
                            f"quantità=0 e totale_riga=0. "
                            f"Desc='{(descrizione_raw or '')[:80]}', Fornitore='{fornitore}'"
                        )
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
                
                # TRIM: Descrizioni lunghe (max 150 caratteri)
                if len(descrizione) > 150:
                    descrizione = descrizione[:150] + "..."
                
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

                # ============================================================
                # DATA CONSEGNA (solo TD24): DatiDDT → regex fallback
                # ============================================================
                _riga_data_consegna = None
                if is_td24:
                    # 1) Mappa DatiDDT per numero riga
                    # Usa NumeroLinea reale dall'XML (non idx enumerate) perché
                    # alcuni fornitori (es. PARTESA) numerano le righe come 10, 20, 30...
                    # e RiferimentoNumeroLinea nel DatiDDT fa riferimento a quei valori.
                    _num_linea_xml = int(riga.get('NumeroLinea') or 0)
                    _riga_data_consegna = _ddt_date_map.get(_num_linea_xml) or _ddt_date_map.get(idx)
                    # 2) Fallback: data globale DDT (senza RiferimentoNumeroLinea)
                    if not _riga_data_consegna and _ddt_global_date:
                        _riga_data_consegna = _ddt_global_date
                    # 3) Fallback: regex GG/MM/AAAA nella descrizione (Schema D)
                    if not _riga_data_consegna and descrizione_raw:
                        _date_match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', descrizione_raw)
                        if _date_match:
                            _dd, _mm, _yyyy = _date_match.groups()
                            try:
                                _parsed = datetime.strptime(f"{_yyyy}-{_mm}-{_dd}", "%Y-%m-%d")
                                if 2020 <= _parsed.year <= 2030:
                                    _riga_data_consegna = _parsed.strftime("%Y-%m-%d")
                            except ValueError:
                                pass

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
                    'File_Origine': file_caricato.name.replace('..', '').replace('/', '').replace('\\', '').replace('%2F', '').replace('%2f', '').replace('\x00', ''),
                    'Prezzo_Standard': prezzo_std,
                    'needs_review': needs_review,
                    'piva_cessionario': piva_cessionario,  # P.IVA destinatario fattura
                    'tipo_documento': tipo_documento,  # TD01=Fattura, TD04=Nota Credito
                    'sconto_percentuale': round(sconto_percentuale, 2),  # % sconto applicato
                    'data_consegna': _riga_data_consegna,  # Data consegna DDT (solo TD24)
                })
            except Exception as e:
                logger.warning(f"{file_caricato.name} - Riga {idx} skippata: {str(e)[:100]}")
                continue
        
        logger.info(f"✅ {file_caricato.name}: {len(righe_prodotti)} righe estratte")
        
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore lettura XML: {getattr(file_caricato, 'name', 'sconosciuto')}")
        # Mostra warning solo se Streamlit è attivo (non dal worker)
        try:
            st.warning(f"⚠️ File {getattr(file_caricato, 'name', '?')}: impossibile leggere")
        except Exception:
            pass
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

        # � Admin e impersonazione bypassano i limiti Vision per test operativi
        ristorante_id = st.session_state.get('ristorante_id')
        _is_unrestricted_admin = bool(st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False))
        if ristorante_id and not _is_unrestricted_admin:
            try:
                from services.ai_cost_service import get_daily_quota_status
                quota = get_daily_quota_status(
                    ristorante_id=ristorante_id,
                    operation_types=['pdf', 'vision'],
                    daily_limit=VISION_DAILY_LIMIT,
                )
                if quota['is_exceeded']:
                    logger.warning(
                        "🔒 Quota Vision superata per ristorante %s: %s/%s oggi",
                        ristorante_id,
                        quota['used'],
                        quota['limit'],
                    )
                    raise VisionDailyLimitExceededError(
                        used=int(quota['used']),
                        limit=int(quota['limit']),
                        ristorante_id=ristorante_id,
                    )
            except VisionDailyLimitExceededError:
                raise
            except Exception as quota_err:
                logger.warning(f"⚠️ Errore check quota Vision: {quota_err} — proseguo senza blocco")

        # I-1: Limite dimensione immagini Vision — file >20 MB supera il massimo OpenAI (~20 MB inline)
        _MAX_VISION_BYTES = 20 * 1024 * 1024  # 20 MB
        _file_size = getattr(file_caricato, 'size', None)
        if _file_size is None:
            try:
                file_caricato.seek(0, 2)
                _file_size = file_caricato.tell()
                file_caricato.seek(0)
            except Exception:
                _file_size = 0
        if _file_size > _MAX_VISION_BYTES:
            logger.warning(
                "⚠️ File Vision troppo grande: %s (%d MB) — limite 20 MB",
                file_caricato.name, _file_size // (1024 * 1024)
            )
            _ui_msg("error", f"❌ {file_caricato.name} supera il limite di 20 MB per l'analisi Vision.")
            return []

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
                'File_Origine': file_caricato.name.replace('..', '').replace('/', '').replace('\\', '').replace('%2F', '').replace('%2f', '').replace('\x00', ''),
                'Prezzo_Standard': prezzo_std,
                'needs_review': needs_review,
                'piva_cessionario': piva_cessionario  # P.IVA destinatario per validazione
            })

        # ============================================================
        # TRACKING COSTI AI
        # ============================================================
        try:
            from services.ai_cost_service import track_ai_usage

            usage = response.usage
            if usage:
                track_ai_usage(
                    operation_type='pdf',
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    ristorante_id=st.session_state.get('ristorante_id'),
                    source_file=getattr(file_caricato, 'name', None),
                    item_count=len(righe_prodotti),
                    metadata={
                        'source': 'vision-upload',
                        'file_name': getattr(file_caricato, 'name', None),
                        'righe_estratte': len(righe_prodotti),
                    },
                )
        except Exception as track_error:
            logger.warning(f"⚠️ Errore tracking costo AI: {track_error}")
        # ============================================================
        return righe_prodotti
        
    except Exception as e:
        logger.exception(f"Errore Vision: {getattr(file_caricato, 'name', 'sconosciuto')}")
        st.error(f"❌ Errore nell'elaborazione di {file_caricato.name}. Riprova.")
        return []


def salva_fattura_processata(nome_file: str, dati_prodotti: List[Dict],
                             supabase_client=None, silent: bool = False,
                             ristoranteid: str = None,
                             user_id: str = None,
                             ingestion_source: str = "manual_upload") -> Dict[str, Any]:
    """
    Salva fatture su Supabase con logging eventi.

    Args:
        nome_file: Nome file fattura
        dati_prodotti: Lista dizionari con dati prodotti
        supabase_client: Client Supabase (opzionale, auto-fetch se None)
        silent: Se True, nasconde messaggi UI Streamlit (obbligatorio fuori Streamlit)
        ristoranteid: UUID ristorante (obbligatorio)
        user_id: UUID utente — se None, tenta st.session_state (solo in UI Streamlit)
        ingestion_source: Origine ingestione (es. manual_upload, invoicetronic)

    Returns:
        Dict con: success, error, righe, location

    Note:
        - Priorità: Supabase SEMPRE (no fallback JSON)
        - Forza categoria valida (mai NULL/vuoto → "Da Classificare")
        - Verifica integrità post-salvataggio
        - Logging automatico su tabella upload_events
    """
    from services import get_supabase_client

    # Sanitizza nome file: previene path traversal nel campo file_origine del DB
    nome_file = nome_file.replace('..', '').replace('/', '').replace('\\', '').replace('%2F', '').replace('%2f', '').replace('\x00', '')
    event_source = (ingestion_source or "manual_upload").strip().lower()

    # ── Risoluzione user_id ────────────────────────────────────────────────────
    # Accetta user_id esplicito (worker) o lo legge da session_state (UI Streamlit)
    if user_id is None:
        try:
            user_id = st.session_state.user_data["id"]
        except Exception:
            if not silent:
                _ui_msg("error", "❌ Errore: Utente non autenticato. Effettua il login.")
            return {"success": False, "error": "not_authenticated", "righe": 0, "location": None}

    ristorante_id = ristoranteid  # Passato esplicitamente dal caller
    
    # ⚠️ VALIDAZIONE: Utenti senza ristorante_id non possono salvare fatture
    if not ristorante_id:
        logger.error(f"❌ ERRORE CRITICO: ristorante_id mancante per user_id={user_id}")
        logger.error(f"   File: {nome_file}, Righe: {len(dati_prodotti)}")
        if not silent:
            _ui_msg("error", "⚠️ Configurazione account incompleta. Impossibile salvare fatture.")
            _ui_msg("info", "💡 Contatta l'assistenza per completare la configurazione del tuo account.")
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
                    "sconto_percentuale": prod.get("sconto_percentuale", 0.0),
                    "data_consegna": prod.get("data_consegna"),
                })
            

            # Idempotenza: rimuovi eventuali righe già esistenti per lo stesso file/user/ristorante
            cleanup_response = (
                supabase_client.table("fatture")
                .delete()
                .eq("user_id", user_id)
                .eq("file_origine", nome_file)
                .eq("ristorante_id", ristorante_id)
                .execute()
            )
            righe_preesistenti = len(cleanup_response.data) if cleanup_response.data else 0
            if righe_preesistenti:
                logger.warning(
                    f"♻️ Idempotenza salvataggio: eliminate {righe_preesistenti} righe preesistenti "
                    f"per {nome_file} (user={user_id}, ristorante={ristorante_id})"
                )

            # Inserimento
            response = supabase_client.table("fatture").insert(records).execute()
            
            righe_confermate = len(response.data) if response.data else len(records)

            
            # Verifica integrità
            verifica = verifica_integrita_fattura(
                nome_file,
                dati_prodotti,
                user_id,
                supabase_client,
                righe_db_override=righe_confermate,
            )
            
            # Log upload event
            try:
                try:
                    user_email = st.session_state.user_data.get("email", "unknown")
                except Exception:
                    user_email = "worker"

                _is_invoicetronic = event_source == 'invoicetronic'
                _td24_alert = calcola_alert_data_consegna_td24(dati_prodotti)
                _base_details = {"source": event_source, "ristorante_id": ristorante_id}
                if _td24_alert:
                    _base_details.update({
                        "alert_data_consegna": _td24_alert["status"],
                        "td24_lines_total": _td24_alert["lines_total"],
                        "td24_lines_with_date": _td24_alert["lines_with_date"],
                        "td24_pct": _td24_alert["pct"],
                    })

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
                        details=_base_details,
                        supabase_client=supabase_client,
                        needs_ack=_is_invoicetronic,
                        alert_data_consegna=_td24_alert["status"] if _td24_alert else None,
                    )
                elif verifica:
                    _partial_details = {
                        **_base_details,
                        "righe_parsed": verifica["righe_parsed"],
                        "righe_db": verifica["righe_db"],
                        "perdite": verifica["perdite"],
                    }
                    log_upload_event(
                        user_id=user_id,
                        user_email=user_email,
                        file_name=nome_file,
                        status="SAVED_PARTIAL",
                        rows_parsed=verifica["righe_parsed"],
                        rows_saved=verifica["righe_db"],
                        error_stage="POSTCHECK",
                        error_message=f"Perdita dati: {verifica['perdite']} righe mancanti",
                        details=_partial_details,
                        supabase_client=supabase_client,
                        needs_ack=_is_invoicetronic,
                        alert_data_consegna=_td24_alert["status"] if _td24_alert else None,
                    )
            except Exception as log_error:
                logger.error(f"Errore logging upload event: {log_error}")
            
            # Gestisci discrepanza
            if verifica and not verifica["integrita_ok"]:
                logger.error(f"🚨 DISCREPANZA {nome_file}: parsed={verifica['righe_parsed']} vs db={verifica['righe_db']}")
                if not silent:
                    try:
                        if 'verifica_integrita' not in st.session_state:
                            st.session_state.verifica_integrita = []
                        st.session_state.verifica_integrita.append(verifica)
                    except Exception:
                        pass  # fuori Streamlit: ignorato

            if not silent:
                _ui_msg("success", f"✅ {nome_file}: {num_righe} righe salvate su Supabase")
            
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
                try:
                    user_email = st.session_state.user_data.get("email", "unknown")
                except Exception:
                    user_email = "worker"
                log_upload_event(
                    user_id=user_id,
                    user_email=user_email,
                    file_name=nome_file,
                    status="FAILED",
                    rows_parsed=num_righe,
                    rows_saved=0,
                    error_stage="SUPABASE_INSERT",
                    error_message=str(e)[:500],
                    details={"source": event_source, "ristorante_id": ristorante_id, "exception_type": type(e).__name__},
                    supabase_client=supabase_client
                )
            except Exception as log_error:
                logger.error(f"Errore logging failed event: {log_error}")
            
            if not silent:
                _ui_msg("error", f"❌ Errore salvataggio {nome_file}. Riprova.")

            return {
                "success": False,
                "error": str(e),
                "righe": 0,
                "location": None
            }
    else:
        if not silent:
            _ui_msg("error", "❌ Supabase non disponibile")
        return {"success": False, "error": "no_supabase", "righe": 0, "location": None}


__all__ = [
    'VisionDailyLimitExceededError',
    'estrai_dati_da_xml',
    'estrai_dati_da_scontrino_vision',
    'salva_fattura_processata',
]

