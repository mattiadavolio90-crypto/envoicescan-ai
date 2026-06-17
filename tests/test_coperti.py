"""Test feature COPERTI.

Copre i punti critici:
  - parser Passbi v1 (UI): coperti frazionari sommati per giorno e arrotondati
    solo sull'aggregato; file senza colonna → coperti None (retro-compatibilità);
  - parser email (worker): smistamento multi-ristorante con coperti;
  - notifica anomalia coperti (_briefing_anomalia_coperti): scatta solo oltre
    soglia e con baseline sufficiente.
"""
import os
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from services.routers.ricavi import (
    _parse_passbi_v1, _parse_passbi_v1_multisede, _parse_generico,
)


# ── Mock supabase per il mapping ragione sociale ──────────────────────────────
def _sb_ragione(mapping_rows):
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.execute.return_value = MagicMock(data=mapping_rows)
    return q


def _passbi_df(rows, with_coperti=True):
    """Costruisce un DataFrame Passbi v1 (header a riga 3) con/senza colonna coperti.
    rows: list di tuple (data, ragione, tipo, iva, importo[, coperti])."""
    header = ["Data (Data)", "Ragione sociale", "Tipo documento", "Codice (IVA)", "Importo"]
    if with_coperti:
        header.append("Coperti ristorante")
    grid = [
        ["ONEFLUX EXPORT-2", None, None, None, None] + ([None] if with_coperti else []),
        ["Periodo di riferimento:", "x", None, None, None] + ([None] if with_coperti else []),
        [None, None, None, None, None] + ([None] if with_coperti else []),
        header,
    ]
    for r in rows:
        grid.append(list(r))
    return pd.DataFrame(grid)


def test_passbi_coperti_sommati_e_arrotondati():
    # LAND 10/6: 28 (Fattura) + 297.0202 (Scontrino) + 109.9797 (proforma) = 435
    df = _passbi_df([
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "Fattura", 10, 912.2, 28),
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "Scontrino", 10, 8451.8783, 297.0202),
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "proforma", 10, 2622.0224, 109.9797),
    ])
    sb = _sb_ragione([{"ragione_sociale_norm": "land dei sapori", "ristorante_id": "RID"}])
    items, errors, parsed = _parse_passbi_v1(df, "RID", sb)
    assert len(items) == 1
    assert items[0].data == "2026-06-10"
    assert items[0].coperti == 435


def test_passbi_senza_colonna_coperti_none():
    df = _passbi_df([
        ("11/06/2026 00:00:00", "LAND DEI SAPORI", "Scontrino", 10, 1000.0),
    ], with_coperti=False)
    sb = _sb_ragione([{"ragione_sociale_norm": "land dei sapori", "ristorante_id": "RID"}])
    items, errors, parsed = _parse_passbi_v1(df, "RID", sb)
    assert len(items) == 1
    assert items[0].coperti is None  # nessuna colonna → non pervenuto, non 0


def test_passbi_coperti_zero_reale_resta_zero():
    df = _passbi_df([
        ("12/06/2026 00:00:00", "LAND DEI SAPORI", "Scontrino", 10, 500.0, 0),
    ])
    sb = _sb_ragione([{"ragione_sociale_norm": "land dei sapori", "ristorante_id": "RID"}])
    items, errors, parsed = _parse_passbi_v1(df, "RID", sb)
    assert len(items) == 1
    # colonna presente con valore 0 → coperti visto = 0 (non None)
    assert items[0].coperti == 0


def test_parse_generico_coperti_opzionale():
    df = pd.DataFrame([
        ["data", "iva10", "iva22", "altri", "coperti"],
        ["2026-06-10", 1100, 0, 0, 50],
        ["2026-06-11", 1100, 0, 0, None],
    ])
    items, errors, parsed = _parse_generico(df)
    by_date = {it.data: it for it in items}
    assert by_date["2026-06-10"].coperti == 50
    assert by_date["2026-06-11"].coperti is None


# ── Notifica anomalia coperti ─────────────────────────────────────────────────
def _sb_coperti(ieri_coperti, baseline_vals):
    """Mock supabase: prima query = ieri (eq data), seconda = baseline (gte/lte)."""
    calls = {"n": 0}

    def _execute():
        calls["n"] += 1
        if calls["n"] == 1:
            data = [] if ieri_coperti is None else [{"coperti": ieri_coperti}]
            return MagicMock(data=data)
        return MagicMock(data=[{"coperti": v} for v in baseline_vals])

    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.gte.return_value = q
    q.lte.return_value = q
    q.limit.return_value = q
    q.execute.side_effect = _execute
    return q


def test_anomalia_coperti_scatta_su_crollo():
    from services.fastapi_worker import _briefing_anomalia_coperti
    # ieri 40 coperti, baseline ~100 → -60% ben oltre soglia 30%
    sb = _sb_coperti(40, [100, 110, 95, 105, 100])
    notif = _briefing_anomalia_coperti("RID", sb, date(2026, 6, 16))
    assert notif is not None
    assert notif["topic_key"] == "coperti_anomalia"
    assert notif["severity"] == "warning"  # crollo


def test_anomalia_coperti_silenzio_se_nella_norma():
    from services.fastapi_worker import _briefing_anomalia_coperti
    # ieri 102, baseline ~100 → +2% sotto soglia → niente notifica
    sb = _sb_coperti(102, [100, 110, 95, 105, 100])
    assert _briefing_anomalia_coperti("RID", sb, date(2026, 6, 16)) is None


def test_anomalia_coperti_silenzio_se_baseline_magra():
    from services.fastapi_worker import _briefing_anomalia_coperti
    # solo 2 giorni di baseline (< min_giorni_baseline=4) → niente notifica
    sb = _sb_coperti(40, [100, 110])
    assert _briefing_anomalia_coperti("RID", sb, date(2026, 6, 16)) is None


def test_anomalia_coperti_silenzio_se_ieri_senza_dato():
    from services.fastapi_worker import _briefing_anomalia_coperti
    sb = _sb_coperti(None, [100, 110, 95, 105])
    assert _briefing_anomalia_coperti("RID", sb, date(2026, 6, 16)) is None


# ── Parser email multi-ristorante (worker) ────────────────────────────────────
def _sb_email(owned_ids, mapping):
    """Mock supabase per il worker: ristoranti owned + ricavi_ragione_sociale_map."""
    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        if state["table"] == "ristoranti":
            return MagicMock(data=[{"id": i} for i in owned_ids])
        if state["table"] == "ricavi_ragione_sociale_map":
            return MagicMock(data=mapping)
        return MagicMock(data=[])

    q = MagicMock()
    q.table.side_effect = _table
    q.select.return_value = q
    q.eq.return_value = q
    q.execute.side_effect = _execute
    return q


def test_parse_passbi_email_coperti_per_ristorante():
    from worker.email_queue_processor import _parse_passbi_email
    df = _passbi_df([
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "Fattura", 10, 912.2, 28),
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "Scontrino", 10, 8451.8783, 297.0202),
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "proforma", 10, 2622.0224, 109.9797),
        ("10/06/2026 00:00:00", "SUSHILAND MARIANO", "Scontrino", 10, 5695.9057, 192.9999),
    ])
    sb = _sb_email(
        owned_ids=["RID-LAND", "RID-SUSHI"],
        mapping=[
            {"ragione_sociale_norm": "land dei sapori", "ristorante_id": "RID-LAND"},
            {"ragione_sociale_norm": "sushiland mariano", "ristorante_id": "RID-SUSHI"},
        ],
    )
    per_rist, errors, parsed = _parse_passbi_email(df, "RID-LAND", "user-1", sb)
    land = next(r for r in per_rist["RID-LAND"] if r.data == "2026-06-10")
    sushi = next(r for r in per_rist["RID-SUSHI"] if r.data == "2026-06-10")
    assert land.coperti == 435
    assert sushi.coperti == 193  # 192.9999 → 193


# ── Parser Passbi multi-sede (import manuale UI) ──────────────────────────────
def test_passbi_multisede_smista_per_ragione_sociale():
    df = _passbi_df([
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "Fattura", 10, 912.2, 28),
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "Scontrino", 10, 8451.8783, 297.0202),
        ("10/06/2026 00:00:00", "LAND DEI SAPORI", "proforma", 10, 2622.0224, 109.9797),
        ("10/06/2026 00:00:00", "SUSHILAND MARIANO", "Scontrino", 10, 5695.9057, 192.9999),
    ])
    sb = _sb_email(
        owned_ids=["RID-LAND", "RID-SUSHI"],
        mapping=[
            {"ragione_sociale_norm": "land dei sapori", "ristorante_id": "RID-LAND"},
            {"ragione_sociale_norm": "sushiland mariano", "ristorante_id": "RID-SUSHI"},
        ],
    )
    per_rist, errors, parsed = _parse_passbi_v1_multisede(df, "RID-LAND", "user-1", sb)
    assert set(per_rist.keys()) == {"RID-LAND", "RID-SUSHI"}
    land = next(r for r in per_rist["RID-LAND"] if r.data == "2026-06-10")
    sushi = next(r for r in per_rist["RID-SUSHI"] if r.data == "2026-06-10")
    assert land.coperti == 435
    assert sushi.coperti == 193


def test_passbi_multisede_ragione_non_mappata_va_sul_token():
    df = _passbi_df([
        ("10/06/2026 00:00:00", "SCONOSCIUTO SRL", "Scontrino", 10, 1100.0, 40),
    ])
    sb = _sb_email(owned_ids=["RID-LAND"], mapping=[])
    per_rist, errors, parsed = _parse_passbi_v1_multisede(df, "RID-LAND", "user-1", sb)
    # ricade sul ristorante del token, con un avviso
    assert list(per_rist.keys()) == ["RID-LAND"]
    assert any("non mappate" in e.lower() for e in errors)


def test_passbi_multisede_ristorante_di_altro_utente_scartato():
    df = _passbi_df([
        ("10/06/2026 00:00:00", "ALTRUI SPA", "Scontrino", 10, 5000.0, 100),
    ])
    # la mappa punta a un ristorante NON posseduto da user-1 → ignorato in sicurezza
    sb = _sb_email(
        owned_ids=["RID-LAND"],
        mapping=[{"ragione_sociale_norm": "altrui spa", "ristorante_id": "RID-ESTRANEO"}],
    )
    per_rist, errors, parsed = _parse_passbi_v1_multisede(df, "RID-LAND", "user-1", sb)
    # mappa filtrata su owned → "altrui spa" non entra → fallback sul token (owned)
    assert "RID-ESTRANEO" not in per_rist


# ── Endpoint coperti-categorie (audit debug) ──────────────────────────────────
def _patch_categorie(monkeypatch, margini_rows, fb_map, overrides=None):
    """Prepara R.get_coperti_categorie con DB e helper worker mockati."""
    import services.routers.ricavi as R
    import services.fastapi_worker as fw

    monkeypatch.setattr(R, "_resolve_user_from_token", lambda a: {"id": "u1"})
    monkeypatch.setattr(R, "_resolve_ristorante_id", lambda u, s: "RID")

    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.in_.return_value = q
    q.execute.return_value = MagicMock(data=margini_rows)
    monkeypatch.setattr(R, "_get_supabase_client", lambda: q)

    monkeypatch.setattr(fw, "_load_mensile_overrides", lambda sb, rid, annos: (overrides or {}))
    monkeypatch.setattr(fw, "_load_fatture_fb_per_categoria_e_mese", lambda sb, rid, da, a: fb_map)
    return R


def test_coperti_categorie_esclude_shop_e_ordina(monkeypatch):
    # 2 mesi, coperti noti; PESCE pesa più di CARNE; SHOP presente ma va escluso
    margini = [
        {"anno": 2026, "mese": 1, "coperti": 1000},
        {"anno": 2026, "mese": 2, "coperti": 2000},
    ]
    fb = {
        (2026, 1, "PESCE"): 5000.0, (2026, 2, "PESCE"): 12000.0,
        (2026, 1, "CARNE"): 1000.0, (2026, 2, "CARNE"): 2000.0,
        (2026, 1, "SHOP"): 9999.0,  # deve sparire
    }
    R = _patch_categorie(monkeypatch, margini, fb)
    resp = R.get_coperti_categorie(data_da="2026-01-01", data_a="2026-02-28", authorization="x")

    cats = [r.categoria for r in resp.righe]
    assert "SHOP" not in cats
    assert cats[0] == "PESCE"  # media più alta in cima
    # media pesata PESCE = (5000+12000)/(1000+2000) = 5.67
    pesce = resp.righe[0]
    assert pesce.media == round(17000 / 3000, 2)
    assert resp.mesi_label == ["Gen 2026", "Feb 2026"]


def test_coperti_categorie_mese_senza_costo_e_dash(monkeypatch):
    # Feb ha coperti ma nessuna fattura PESCE -> valore None (dash in UI)
    margini = [
        {"anno": 2026, "mese": 1, "coperti": 1000},
        {"anno": 2026, "mese": 2, "coperti": 2000},
    ]
    fb = {(2026, 1, "PESCE"): 5000.0}
    R = _patch_categorie(monkeypatch, margini, fb)
    resp = R.get_coperti_categorie(data_da="2026-01-01", data_a="2026-02-28", authorization="x")
    pesce = next(r for r in resp.righe if r.categoria == "PESCE")
    per = {pm.mese: pm.valore for pm in pesce.per_mese}
    assert per[1] == 5.0       # 5000/1000
    assert per[2] is None      # nessuna fattura -> dash
    # media pesata solo sui mesi con costo: 5000/1000 = 5.0
    assert pesce.media == 5.0


def test_coperti_categorie_nessun_coperto_vuoto(monkeypatch):
    margini = [{"anno": 2026, "mese": 1, "coperti": None}]
    R = _patch_categorie(monkeypatch, margini, {(2026, 1, "PESCE"): 5000.0})
    resp = R.get_coperti_categorie(data_da="2026-01-01", data_a="2026-01-31", authorization="x")
    assert resp.mesi_label == []
    assert resp.righe == []
