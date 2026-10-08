"""Fase F del piano consulente (08/10/2026): le domande proposte dal briefing.

Mattia, screen 8: «le domande sotto proposte non sono coerenti con il contesto
del briefing». Il worker dichiara di quali temi ha parlato, nell'ordine
(`BriefingResponse.temi`); la Home e il telefono ne fanno le domande
(`domandeDalBriefing` in lib/home-chat.ts, provata in test_home_chat_frontend).
"""
import re
from pathlib import Path

import services.daily_briefing_service as dbs
import services.fastapi_worker as fw

_WEB = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"


def _n(p: Path) -> str:
    return re.sub(r"\s+", "", p.read_text(encoding="utf-8"))


def _rec(topic, severity="warning", **payload):
    return {"topic_key": topic, "severity": severity, "title": topic, "payload": payload}


INCASSO = _rec("buona_notizia", "success", tipo="incasso_ieri", incasso=497,
               giorno_settimana="mercoledì")
MESE = _rec("mese_chiuso", "success", mese="settembre", food_cost_pct=28.8)
SCAD = _rec("scadenza_superata", count=11, totale=11278.43)
PERS = _rec("costo_personale_mancante", mese="settembre", anno=2026)


# ── Il worker: quali temi, in che ordine ──────────────────────────────────

def test_temi_nell_ordine_del_briefing():
    snap = dbs._build_snapshot([SCAD, MESE, INCASSO])
    assert snap["temi"] == ["buona_notizia:incasso_ieri", "mese_chiuso", "scadenza_superata"]


def test_le_fatture_accodate_sono_un_tema():
    con = {**INCASSO, "payload": {**INCASSO["payload"],
                                  "fatture_ieri": {"n_fatture": 3, "importo": 2400.0}}}
    assert dbs._build_snapshot([con])["temi"] == [
        "buona_notizia:incasso_ieri", "buona_notizia:fatture_arrivate"]


def test_un_tema_spento_non_c_e():
    snap = dbs._build_snapshot([MESE, SCAD], topics_disabled=["mese_chiuso"])
    assert snap["temi"] == ["scadenza_superata"]


def test_solo_le_card_mostrate_non_quelle_tagliate():
    """Oltre le 4 card il resto va nella campanella: non se ne parla, quindi
    nemmeno le domande."""
    recs = [_rec("fatturato_mancante", mese="settembre", anno=2026),
             _rec("incasso_mancante"), PERS, SCAD,
             _rec("scadenza_imminente", count=2, totale=300.0),
             _rec("appuntamento_imminente", "info", count=1)]
    snap = dbs._build_snapshot(recs)
    assert len(snap["azioni"]) == dbs._MAX_CARD
    assert snap["temi"] == [a["topic_key"] for a in snap["azioni"]]
    assert "appuntamento_imminente" not in snap["temi"]


def test_il_rientro_e_un_tema():
    rientro = _rec("rientro_assenza", "info", giorni=9)
    assert dbs._build_snapshot([rientro, SCAD])["temi"][0] == "rientro_assenza"


def test_cliente_nuovo_solo_il_benvenuto_e_i_primi_passi():
    onb = _rec("onboarding", "info")
    snap = dbs._build_snapshot([onb, INCASSO, PERS])
    assert snap["temi"][0] == "onboarding"
    assert "buona_notizia:incasso_ieri" not in snap["temi"]


def test_la_risposta_porta_i_temi():
    snap = dbs._build_snapshot([INCASSO, SCAD])
    out = fw._briefing_response_from_snapshot(snap, "Mattia")
    assert out.temi == ["buona_notizia:incasso_ieri", "scadenza_superata"]


def test_snapshot_vecchio_senza_temi():
    snap = dbs._build_snapshot([SCAD])
    snap.pop("temi")
    assert fw._briefing_response_from_snapshot(snap, None).temi == []


def test_versione_del_briefing_alzata():
    """Senza bump gli snapshot di oggi resterebbero senza temi fino al TTL."""
    assert dbs._BRIEFING_CODE_VERSION >= 34


# ── Il cablaggio delle pagine ──────────────────────────────────────────────

_CONV = _WEB / "components/home/conversazione-assistente.tsx"
_PV = _WEB / "app/(app)/dashboard/page.tsx"
_M_PAGE = _WEB / "app/(mobile)/m/chat/page.tsx"
_M_CHAT = _WEB / "app/(mobile)/m/chat/mobile-chat.tsx"


def test_la_home_del_locale_passa_i_temi():
    assert "temi={briefing.temi}" in _n(_PV)


def test_la_conversazione_usa_i_temi_solo_nella_sede_e_con_la_conferma():
    c = _n(_CONV)
    assert ('vista.contesto==="sede"&&temi?.length?domandeDalBriefing(temi,settore,{registra:true})'
            ':suggerimentiPer(vista.contesto,settore)') in c


def test_il_telefono_usa_i_temi_senza_registrare():
    p = _n(_M_PAGE)
    assert "domandeDalBriefing(briefing?.temi,utente?.tipo_attivita,{registra:false})" in p
    assert "<MobileChatsuggerimenti={suggerimenti}/>" in p


def test_il_telefono_non_ha_piu_le_domande_scritte_nel_componente():
    m = _n(_M_CHAT)
    assert "constSUGGERIMENTI" not in m
    assert "suggerimenti.map(" in m


def test_buona_notizia_senza_tipo_non_e_un_tema():
    snap = dbs._build_snapshot([_rec("buona_notizia", "success"), SCAD])
    assert snap["temi"] == ["scadenza_superata"]
