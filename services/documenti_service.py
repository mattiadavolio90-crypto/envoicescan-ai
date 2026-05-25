"""Servizi per gestione header documento in fatture_documenti."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.logger_setup import get_logger

logger = get_logger("documenti")


def _to_date_iso(value: Any) -> Optional[str]:
    """Converte una data in formato YYYY-MM-DD, altrimenti None."""
    if value in (None, "", "N/A", "None"):
        return None
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def _to_int_safe(value: Any) -> Optional[int]:
    if value in (None, "", "N/A", "None"):
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _to_float_safe(value: Any) -> Optional[float]:
    if value in (None, "", "N/A", "None"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _tipo_documento_safe(value: Any) -> str:
    td = str(value or "TD01").upper().strip()
    return td if td else "TD01"


def _calcola_scadenza_base(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Calcola scadenza_effettiva e source per Step 2.

    Priorita:
    1) scadenza_override
    2) scadenza_xml
    3) data_documento + giorni_termini_xml
    4) None
    """
    scadenza_override = _to_date_iso(payload.get("scadenza_override"))
    if scadenza_override:
        return scadenza_override, "override"

    scadenza_xml = _to_date_iso(payload.get("scadenza_xml"))
    if scadenza_xml:
        return scadenza_xml, "xml"

    data_documento = _to_date_iso(payload.get("data_documento"))
    giorni_termini = _to_int_safe(payload.get("giorni_termini_xml"))
    if data_documento and giorni_termini is not None:
        base_dt = pd.to_datetime(data_documento, errors="coerce")
        if pd.notna(base_dt):
            return (base_dt + timedelta(days=giorni_termini)).strftime("%Y-%m-%d"), "xml"

    return None, None


try:
    import streamlit as _st_cv

    @_st_cv.cache_data(ttl=20, show_spinner=False)
    def _get_cache_version_internal(key: str) -> int:
        """Versione cached di get_cache_version (TTL 20s per ridurre round-trip)."""
        from services import get_supabase_client as _gcv_sb
        sb = _gcv_sb()
        resp = sb.table("cache_version").select("version").eq("key", key).limit(1).execute()
        row = (resp.data or [None])[0]
        if not row:
            return 0
        return int(row.get("version") or 0)
except Exception:
    def _get_cache_version_internal(key: str) -> int:  # type: ignore[misc]
        from services import get_supabase_client as _gcv_sb
        sb = _gcv_sb()
        resp = sb.table("cache_version").select("version").eq("key", key).limit(1).execute()
        row = (resp.data or [None])[0]
        if not row:
            return 0
        return int(row.get("version") or 0)


def get_cache_version(key: str, supabase_client=None) -> int:
    """Legge la versione cache da public.cache_version (0 se assente). Cached 20s."""
    return _get_cache_version_internal(key)


def upsert_fattura_documento(
    user_id: str,
    ristorante_id: str,
    file_origine: str,
    payload: Dict[str, Any],
    supabase_client=None,
) -> Dict[str, Any]:
    """
    Upsert idempotente su fatture_documenti (chiave: user_id, ristorante_id, file_origine).

    Aggiorna metadati header senza sovrascrivere campi pagamento/override se non forniti.
    """
    from services import get_supabase_client

    if not user_id or not ristorante_id or not file_origine:
        raise ValueError("user_id, ristorante_id e file_origine sono obbligatori")

    sb = supabase_client or get_supabase_client()

    tipo_documento = _tipo_documento_safe(payload.get("tipo_documento"))
    segno_compensazione = -1 if tipo_documento == "TD04" else 1

    record: Dict[str, Any] = {
        "user_id": str(user_id),
        "ristorante_id": str(ristorante_id),
        "file_origine": str(file_origine),
        "fornitore": payload.get("fornitore"),
        "piva_fornitore": payload.get("piva_fornitore"),
        "numero_documento": payload.get("numero_documento"),
        "data_documento": _to_date_iso(payload.get("data_documento")),
        "data_competenza": _to_date_iso(payload.get("data_competenza")),
        "tipo_documento": tipo_documento,
        "totale_documento": _to_float_safe(payload.get("totale_documento")),
        "totale_imponibile": _to_float_safe(payload.get("totale_imponibile")),
        "totale_iva": _to_float_safe(payload.get("totale_iva")),
        "segno_compensazione": segno_compensazione,
        "source_origin": "invoicetronic" if str(payload.get("source_origin", "manual")).lower() == "invoicetronic" else "manual",
    }

    has_scadenza_input = any(
        payload.get(k) not in (None, "", "N/A", "None")
        for k in ("scadenza_xml", "giorni_termini_xml", "scadenza_override")
    )
    if has_scadenza_input:
        record["scadenza_xml"] = _to_date_iso(payload.get("scadenza_xml"))
        record["giorni_termini_xml"] = _to_int_safe(payload.get("giorni_termini_xml"))
        if payload.get("scadenza_override") not in (None, "", "N/A", "None"):
            record["scadenza_override"] = _to_date_iso(payload.get("scadenza_override"))

        scadenza_effettiva, scadenza_source = _calcola_scadenza_base(payload)
        if scadenza_effettiva:
            record["scadenza_effettiva"] = scadenza_effettiva
            record["scadenza_source"] = scadenza_source

    # Evita upsert con campi sporchi/None ridondanti.
    cleaned_record = {k: v for k, v in record.items() if v is not None}

    resp = (
        sb.table("fatture_documenti")
        .upsert(cleaned_record, on_conflict="user_id,ristorante_id,file_origine")
        .execute()
    )

    return {
        "ok": True,
        "row_count": len(resp.data or []),
        "data": resp.data or [],
    }


def _compute_stato_scadenza(scadenza_iso: Optional[str], pagata: bool, today: date) -> str:
    """Calcola stato leggibile per dashboard scadenziario."""
    if pagata:
        return "✅ Pagata"
    if not scadenza_iso:
        return "⚪ Nessuna scadenza"
    try:
        scad = pd.to_datetime(scadenza_iso, errors="coerce")
        if pd.isna(scad):
            return "⚪ Nessuna scadenza"
        delta = (scad.date() - today).days
        if delta < 0:
            return "🔴 Scaduta"
        if delta <= 7:
            return "🟡 In scadenza"
        return "🟢 Pianificata"
    except Exception:
        return "⚪ Nessuna scadenza"


def _filter_documenti_rows(rows: List[Dict[str, Any]], filtro: str, today: date, giorni_imminenti: int) -> List[Dict[str, Any]]:
    """Applica filtro scadenziario lato applicazione per mantenere logica uniforme."""
    filtro_norm = str(filtro or "tutte").strip().lower()
    if filtro_norm == "tutte":
        return rows

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        pagata = bool(row.get("pagata"))
        if pagata:
            continue

        scad_raw = row.get("scadenza_effettiva")
        if not scad_raw:
            continue

        scad_dt = pd.to_datetime(scad_raw, errors="coerce")
        if pd.isna(scad_dt):
            continue

        delta = (scad_dt.date() - today).days
        if filtro_norm == "scadute" and delta < 0:
            filtered.append(row)
        elif filtro_norm == "imminenti" and 0 <= delta <= int(giorni_imminenti):
            filtered.append(row)

    return filtered


# Cache locale a processo: viene invalidata quando cambia cache_version su DB.
try:
    import streamlit as st

    @st.cache_data(ttl=60, show_spinner=False)
    def _fetch_documenti_cached(user_id: str, ristorante_id: str, cache_version: int) -> List[Dict[str, Any]]:
        from services import get_supabase_client

        sb = get_supabase_client()
        query = (
            sb.table("fatture_documenti")
            .select(
                "id,file_origine,fornitore,piva_fornitore,tipo_documento,totale_documento,"
                "data_documento,numero_documento,"
                "scadenza_xml,giorni_termini_xml,scadenza_effettiva,scadenza_source,"
                "pagata,pagata_at,created_at"
            )
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .order("scadenza_effettiva", desc=False)
            .order("created_at", desc=True)
        )
        resp = query.execute()
        return resp.data or []
except Exception:
    def _fetch_documenti_cached(user_id: str, ristorante_id: str, cache_version: int) -> List[Dict[str, Any]]:  # type: ignore[misc]
        from services import get_supabase_client

        sb = get_supabase_client()
        query = (
            sb.table("fatture_documenti")
            .select(
                "id,file_origine,fornitore,piva_fornitore,tipo_documento,totale_documento,"
                "data_documento,numero_documento,"
                "scadenza_xml,giorni_termini_xml,scadenza_effettiva,scadenza_source,"
                "pagata,pagata_at,created_at"
            )
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .order("scadenza_effettiva", desc=False)
            .order("created_at", desc=True)
        )
        resp = query.execute()
        return resp.data or []


def _applica_regole_fornitore(
    fornitore: Optional[str],
    piva_fornitore: Optional[str],
    data_documento: Optional[str],
    scadenza_xml: Optional[str],
    giorni_termini_xml: Optional[int],
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
    regole_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Optional[str], str]:
    """
    Applica gerarchia scadenza con lookup a fornitori_pagamenti_config.
    
    Priorita:
    1) Lookup fornitore in fornitori_pagamenti_config by piva_fornitore
    2) scadenza_xml (se presente)
    3) data_documento + giorni_termini_xml
    4) None
    
    Ritorna: (scadenza_effettiva, source)

    Se `regole_map` è fornito (dict {piva: {giorni_pagamento, data_riferimento}}),
    viene usato al posto di una query DB per evitare N+1 in loop su molte righe.
    """
    # Priorita 1: Lookup fornitore in fornitori_pagamenti_config
    if piva_fornitore or fornitore:
        try:
            regola: Optional[Dict[str, Any]] = None
            _piva_key = str(piva_fornitore).strip() if piva_fornitore else ""

            if regole_map is not None:
                # Path "batch": usa mappa pre-caricata
                if _piva_key:
                    regola = regole_map.get(_piva_key)
            else:
                # Path legacy single-shot: query DB on-demand
                from services import get_supabase_client
                sb = supabase_client or get_supabase_client()
                if _piva_key:
                    query = (
                        sb.table("fornitori_pagamenti_config")
                        .select("giorni_pagamento,data_riferimento,modalita")
                        .eq("user_id", user_id)
                        .eq("ristorante_id", ristorante_id)
                        .eq("piva_fornitore", _piva_key)
                        .eq("attiva", True)
                        .is_("deleted_at", "null")
                        .limit(1)
                        .execute()
                    )
                    if query.data and len(query.data) > 0:
                        regola = query.data[0]

            if regola:
                modalita_reg = str(regola.get("modalita") or "").strip().lower()

                if modalita_reg:
                    # Nuova logica: modalita discreta
                    if data_documento:
                        base_dt = pd.to_datetime(data_documento, errors="coerce")
                        if pd.notna(base_dt):
                            if modalita_reg == "rid":
                                return base_dt.strftime("%Y-%m-%d"), "fornitore_rid"
                            elif modalita_reg in ("30gg", "60gg", "90gg"):
                                _days = {"30gg": 30, "60gg": 60, "90gg": 90}[modalita_reg]
                                return (base_dt + pd.Timedelta(days=_days)).strftime("%Y-%m-%d"), "fornitore"
                            elif modalita_reg in ("30gg_fm", "60gg_fm", "90gg_fm"):
                                _months = {"30gg_fm": 1, "60gg_fm": 2, "90gg_fm": 3}[modalita_reg]
                                _last_day = (base_dt + pd.DateOffset(months=_months)) + pd.offsets.MonthEnd(0)
                                return _last_day.strftime("%Y-%m-%d"), "fornitore"
                else:
                    # Logica legacy: giorni_pagamento + data_riferimento
                    giorni_pag = _to_int_safe(regola.get("giorni_pagamento"))
                    data_rif = str(regola.get("data_riferimento") or "data_documento").strip().lower()

                    if giorni_pag is not None and data_documento:
                        base_dt = pd.to_datetime(data_documento, errors="coerce")
                        if pd.notna(base_dt):
                            if data_rif == "fine_mese":
                                last_day = (base_dt + pd.offsets.MonthEnd(0))
                                scad_dt = last_day + pd.Timedelta(days=giorni_pag)
                            elif data_rif == "fine_mese_successivo":
                                first_of_next = base_dt + pd.offsets.MonthEnd(0) + pd.Timedelta(days=1)
                                last_of_next = first_of_next + pd.offsets.MonthEnd(0)
                                scad_dt = last_of_next + pd.Timedelta(days=giorni_pag)
                            else:  # data_documento
                                scad_dt = base_dt + pd.Timedelta(days=giorni_pag)
                            return scad_dt.strftime("%Y-%m-%d"), "fornitore"
        except Exception as e:
            logger.warning(f"Errore lookup fornitore regole: {e}")

    # Priorita 2: scadenza_xml
    scad_xml = _to_date_iso(scadenza_xml)
    if scad_xml:
        return scad_xml, "xml"
    
    # Priorita 3: data_documento + giorni_termini_xml
    data_doc = _to_date_iso(data_documento)
    giorni_termini = _to_int_safe(giorni_termini_xml)
    if data_doc and giorni_termini is not None:
        base_dt = pd.to_datetime(data_doc, errors="coerce")
        if pd.notna(base_dt):
            return (base_dt + timedelta(days=giorni_termini)).strftime("%Y-%m-%d"), "xml"
    
    # Priorita 4: None
    return None, "none"


try:
    import streamlit as _st_fpc

    @_st_fpc.cache_data(ttl=120, show_spinner=False)
    def _get_fornitori_pagamenti_config_cached(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:
        """Versione cached di get_fornitori_pagamenti_config (TTL 120s)."""
        from services import get_supabase_client as _fpc_sb
        sb = _fpc_sb()
        try:
            query = (
                sb.table("fornitori_pagamenti_config")
                .select("*")
                .eq("user_id", user_id)
                .eq("ristorante_id", ristorante_id)
                .order("attiva", desc=True)
                .order("created_at", desc=True)
                .execute()
            )
            return query.data or []
        except Exception as e:
            logger.warning(f"Errore caricamento fornitori config: {e}")
            return []
except Exception:
    def _get_fornitori_pagamenti_config_cached(user_id: str, ristorante_id: str) -> List[Dict[str, Any]]:  # type: ignore[misc]
        from services import get_supabase_client as _fpc_sb
        sb = _fpc_sb()
        try:
            query = (
                sb.table("fornitori_pagamenti_config")
                .select("*")
                .eq("user_id", user_id)
                .eq("ristorante_id", ristorante_id)
                .order("attiva", desc=True)
                .order("created_at", desc=True)
                .execute()
            )
            return query.data or []
        except Exception as e:
            logger.warning(f"Errore caricamento fornitori config: {e}")
            return []


def get_fornitori_pagamenti_config(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Carica lista regole pagamento fornitore configurate. Cached 120s."""
    if not user_id or not ristorante_id:
        return []
    return _get_fornitori_pagamenti_config_cached(str(user_id), str(ristorante_id))


# Mapping modalita → (giorni_pagamento legacy, data_riferimento legacy)
_MODALITA_LEGACY_MAP: Dict[str, tuple] = {
    "rid":     (0,  "data_documento"),
    "30gg":    (30, "data_documento"),
    "60gg":    (60, "data_documento"),
    "90gg":    (90, "data_documento"),
    "30gg_fm": (30, "data_documento"),
    "60gg_fm": (60, "data_documento"),
    "90gg_fm": (90, "data_documento"),
}


def upsert_fornitori_pagamenti_config(
    user_id: str,
    ristorante_id: str,
    piva_fornitore: Optional[str],
    modalita: str,
    giorni_pagamento: Optional[int] = None,
    data_riferimento: str = "data_documento",
    attiva: bool = True,
    note: Optional[str] = None,
    supabase_client=None,
) -> Dict[str, Any]:
    """Upsert regola pagamento fornitore."""
    if not user_id or not ristorante_id or not modalita:
        raise ValueError("user_id, ristorante_id, modalita obbligatori")
    
    if not piva_fornitore or not str(piva_fornitore).strip():
        raise ValueError("P.IVA/codice fornitore obbligatorio")

    # 🔒 Sanitizzazione P.IVA: evita injection/path traversal via codice fornitore
    import re as _re
    _piva_clean = str(piva_fornitore).strip()
    if not _re.match(r'^[\w\-\.]{1,64}$', _piva_clean):
        raise ValueError(f"P.IVA/codice fornitore non valido: {_piva_clean!r}")

    try:
        from services import get_supabase_client
        from datetime import datetime, timezone
        sb = supabase_client or get_supabase_client()

        _piva = _piva_clean
        _now = datetime.now(timezone.utc).isoformat()

        # Deriva giorni_pagamento e data_riferimento dalla modalita
        _modalita_clean = str(modalita).strip().lower()
        _gg_legacy, _dr_legacy = _MODALITA_LEGACY_MAP.get(_modalita_clean, (giorni_pagamento or 30, data_riferimento))

        # Check esistenza (l'indice è parziale, ON CONFLICT non funziona → check manuale)
        _existing = (
            sb.table("fornitori_pagamenti_config")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("ristorante_id", str(ristorante_id))
            .eq("piva_fornitore", _piva)
            .limit(1)
            .execute()
        )

        if _existing.data:
            # UPDATE
            resp = (
                sb.table("fornitori_pagamenti_config")
                .update({
                    "modalita": _modalita_clean,
                    "giorni_pagamento": int(_gg_legacy),
                    "data_riferimento": str(_dr_legacy).strip().lower(),
                    "attiva": bool(attiva),
                    "note": str(note or "").strip() or None,
                    "updated_at": _now,
                })
                .eq("id", _existing.data[0]["id"])
                .execute()
            )
        else:
            # INSERT
            resp = (
                sb.table("fornitori_pagamenti_config")
                .insert({
                    "user_id": str(user_id),
                    "ristorante_id": str(ristorante_id),
                    "piva_fornitore": _piva,
                    "modalita": _modalita_clean,
                    "giorni_pagamento": int(_gg_legacy),
                    "data_riferimento": str(_dr_legacy).strip().lower(),
                    "attiva": bool(attiva),
                    "note": str(note or "").strip() or None,
                })
                .execute()
            )
        
        # Invalida cache versione
        try:
            current_version = get_cache_version("fornitori_pagamenti_config", sb)
            sb.table("cache_version").upsert({
                "key": "fornitori_pagamenti_config",
                "version": current_version + 1
            }, on_conflict="key").execute()
        except Exception:
            pass
        
        return {"ok": True, "row_count": len(resp.data or [])}
    except Exception as e:
        logger.error(f"Errore upsert fornitori config: {e}")
        return {"ok": False, "error": str(e)}


def delete_fornitori_pagamenti_config(
    user_id: str,
    ristorante_id: str,
    regola_id: str,
    supabase_client=None,
) -> Dict[str, Any]:
    """Elimina regola pagamento fornitore."""
    if not user_id or not ristorante_id or not regola_id:
        raise ValueError("user_id, ristorante_id, regola_id obbligatori")
    
    try:
        from services import get_supabase_client
        from datetime import datetime, timezone
        sb = supabase_client or get_supabase_client()
        
        # Hard delete (la tabella non ha deleted_at)
        resp = (
            sb.table("fornitori_pagamenti_config")
            .delete()
            .eq("id", regola_id)
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .execute()
        )
        
        # Invalida cache
        try:
            current_version = get_cache_version("fornitori_pagamenti_config", sb)
            sb.table("cache_version").upsert({
                "key": "fornitori_pagamenti_config",
                "version": current_version + 1
            }, on_conflict="key").execute()
        except Exception:
            pass
        
        return {"ok": True, "row_count": len(resp.data or [])}
    except Exception as e:
        logger.error(f"Errore delete fornitori config: {e}")
        return {"ok": False, "error": str(e)}


def clear_fornitori_cache() -> None:
    """Invalida cache locale fornitori config."""
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass


# ============================================================
# CACHE DOCUMENTI NORMALIZZATI
# Centralizza la normalizzazione (scadenza_effettiva + regole fornitore)
# in un'unica funzione cached. get_documenti_list diventa un thin wrapper
# che chiama questa cache e poi filtra in memoria — 0 query DB per cache hit.
# ============================================================

try:
    import streamlit as _st_dnorm

    @_st_dnorm.cache_data(ttl=60, show_spinner=False)
    def _get_documenti_normalized_cached(
        user_id: str, ristorante_id: str, cache_version: int
    ) -> List[Dict[str, Any]]:
        """
        Normalizza TUTTI i documenti applicando regole scadenza fornitore.
        Cached 60s per cache_version → si invalida automaticamente con clear_documenti_cache().
        Usa _fetch_documenti_cached e _get_fornitori_pagamenti_config_cached (entrambi cached)
        → 0 query DB per cache hit.
        """
        rows = _fetch_documenti_cached(user_id, ristorante_id, cache_version)
        regole_list = _get_fornitori_pagamenti_config_cached(user_id, ristorante_id)
        regole_map: Dict[str, Dict[str, Any]] = {
            str(r.get("piva_fornitore", "")).strip(): r
            for r in regole_list
            if r.get("piva_fornitore")
        }
        today = date.today()
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            scadenza_eff, source_eff = _applica_regole_fornitore(
                fornitore=row.get("fornitore"),
                piva_fornitore=row.get("piva_fornitore"),
                data_documento=row.get("data_documento"),
                scadenza_xml=row.get("scadenza_xml"),
                giorni_termini_xml=row.get("giorni_termini_xml"),
                user_id=user_id,
                ristorante_id=ristorante_id,
                regole_map=regole_map,
            )
            if not scadenza_eff:
                _stored = row.get("scadenza_effettiva")
                if _stored:
                    scadenza_eff = _to_date_iso(_stored)
                    source_eff = row.get("scadenza_source") or "stored"
            pagata = bool(row.get("pagata"))
            # Auto-pagato: fatture di fornitori con regola RID risultano già pagate
            if source_eff == "fornitore_rid" and not pagata:
                pagata = True
            normalized.append({
                "id": row.get("id"),
                "file_origine": row.get("file_origine"),
                "fornitore": row.get("fornitore") or "Sconosciuto",
                "tipo_documento": row.get("tipo_documento") or "TD01",
                "totale_documento": _to_float_safe(row.get("totale_documento")) or 0.0,
                "data_documento": row.get("data_documento"),
                "numero_documento": row.get("numero_documento"),
                "scadenza_xml": row.get("scadenza_xml"),
                "giorni_termini_xml": row.get("giorni_termini_xml"),
                "scadenza_effettiva": scadenza_eff,
                "scadenza_source": source_eff,
                "pagata": pagata,
                "data_pagamento": _to_date_iso(row.get("pagata_at")),
                "pagata_at": _to_date_iso(row.get("pagata_at")),
                "stato_scadenza": _compute_stato_scadenza(scadenza_eff, pagata=pagata, today=today),
                "created_at": row.get("created_at"),
            })
        return normalized
except Exception:
    def _get_documenti_normalized_cached(  # type: ignore[misc]
        user_id: str, ristorante_id: str, cache_version: int
    ) -> List[Dict[str, Any]]:
        rows = _fetch_documenti_cached(user_id, ristorante_id, cache_version)
        regole_list = _get_fornitori_pagamenti_config_cached(user_id, ristorante_id)
        regole_map: Dict[str, Dict[str, Any]] = {
            str(r.get("piva_fornitore", "")).strip(): r
            for r in regole_list
            if r.get("piva_fornitore")
        }
        today = date.today()
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            scadenza_eff, source_eff = _applica_regole_fornitore(
                fornitore=row.get("fornitore"),
                piva_fornitore=row.get("piva_fornitore"),
                data_documento=row.get("data_documento"),
                scadenza_xml=row.get("scadenza_xml"),
                giorni_termini_xml=row.get("giorni_termini_xml"),
                user_id=user_id,
                ristorante_id=ristorante_id,
                regole_map=regole_map,
            )
            if not scadenza_eff:
                _stored = row.get("scadenza_effettiva")
                if _stored:
                    scadenza_eff = _to_date_iso(_stored)
                    source_eff = row.get("scadenza_source") or "stored"
            pagata = bool(row.get("pagata"))
            # Auto-pagato: fatture di fornitori con regola RID risultano già pagate
            if source_eff == "fornitore_rid" and not pagata:
                pagata = True
            normalized.append({
                "id": row.get("id"),
                "file_origine": row.get("file_origine"),
                "fornitore": row.get("fornitore") or "Sconosciuto",
                "tipo_documento": row.get("tipo_documento") or "TD01",
                "totale_documento": _to_float_safe(row.get("totale_documento")) or 0.0,
                "data_documento": row.get("data_documento"),
                "numero_documento": row.get("numero_documento"),
                "scadenza_xml": row.get("scadenza_xml"),
                "giorni_termini_xml": row.get("giorni_termini_xml"),
                "scadenza_effettiva": scadenza_eff,
                "scadenza_source": source_eff,
                "pagata": pagata,
                "data_pagamento": _to_date_iso(row.get("pagata_at")),
                "pagata_at": _to_date_iso(row.get("pagata_at")),
                "stato_scadenza": _compute_stato_scadenza(scadenza_eff, pagata=pagata, today=today),
                "created_at": row.get("created_at"),
            })
        return normalized


def get_documenti_list(
    user_id: str,
    ristorante_id: str,
    filtro: str = "tutte",
    giorni_imminenti: int = 7,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """
    Restituisce lista documenti da fatture_documenti con stato scadenza calcolato.

    filtro supportati:
    - "tutte"
    - "scadute"
    - "imminenti"

    ⚡ Performance: usa _get_documenti_normalized_cached (cached 60s) per
    normalizzazione e regole fornitore → 0 query DB per cache hit.
    """
    if not user_id or not ristorante_id:
        return []

    current_version = get_cache_version("fatture_documenti", supabase_client=supabase_client)
    # Ottieni tutti i documenti normalizzati dalla cache → O(1) per cache hit
    all_normalized = _get_documenti_normalized_cached(str(user_id), str(ristorante_id), int(current_version))

    # Applica filtro in memoria — puro Python, senza I/O
    today = date.today()
    return _filter_documenti_rows(all_normalized, filtro=filtro, today=today, giorni_imminenti=giorni_imminenti)


def clear_documenti_cache() -> None:
    """Invalida cache Streamlit lato processo per la sezione documenti."""
    try:
        import streamlit as st

        st.cache_data.clear()
    except Exception as exc:
        logger.debug("clear_documenti_cache non disponibile: %s", exc)


def segna_fattura_pagata(
    file_origine: str,
    user_id: str,
    ristorante_id: str,
    pagata: bool = True,
    supabase_client=None,
) -> Dict[str, Any]:
    """Segna una fattura come pagata (o non pagata) su fatture_documenti."""
    from services import get_supabase_client

    if not file_origine or not user_id or not ristorante_id:
        return {"success": False, "error": "Parametri obbligatori mancanti"}

    sb = supabase_client or get_supabase_client()
    try:
        from datetime import datetime
        _file_target = str(file_origine).strip()
        _file_target_norm = _file_target.lower()

        payload: Dict[str, Any] = {"pagata": pagata}
        if pagata:
            payload["pagata_at"] = datetime.utcnow().date().isoformat()
        else:
            payload["pagata_at"] = None

        resp = (
            sb.table("fatture_documenti")
            .update(payload)
            .eq("user_id", str(user_id))
            .eq("ristorante_id", str(ristorante_id))
            .is_("deleted_at", "null")
            .eq("file_origine", _file_target)
            .execute()
        )
        updated_rows = resp.data or []

        # Fallback robusto: intercetta mismatch su maiuscole/spazi nel file_origine.
        if not updated_rows:
            lookup = (
                sb.table("fatture_documenti")
                .select("id,file_origine")
                .eq("user_id", str(user_id))
                .eq("ristorante_id", str(ristorante_id))
                .is_("deleted_at", "null")
                .execute()
            )
            matched_id = None
            for row in (lookup.data or []):
                _row_file = str(row.get("file_origine") or "").strip().lower()
                if _row_file == _file_target_norm:
                    matched_id = row.get("id")
                    break

            if matched_id is not None:
                resp = (
                    sb.table("fatture_documenti")
                    .update(payload)
                    .eq("id", matched_id)
                    .execute()
                )
                updated_rows = resp.data or []

        if not updated_rows:
            return {
                "success": False,
                "error": f"Fattura non trovata per aggiornamento pagamento: {_file_target}",
            }

        try:
            current_version = get_cache_version("fatture_documenti", sb)
            sb.table("cache_version").upsert({
                "key": "fatture_documenti",
                "version": current_version + 1,
            }, on_conflict="key").execute()
        except Exception:
            pass

        return {"success": True, "data": updated_rows}
    except Exception as exc:
        logger.error("segna_fattura_pagata error: %s", exc)
        return {"success": False, "error": str(exc)}


__all__ = [
    "get_cache_version",
    "upsert_fattura_documento",
    "get_documenti_list",
    "clear_documenti_cache",
]
