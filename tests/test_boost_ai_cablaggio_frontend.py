"""Boost AI (fase J, 10/10/2026): dove compare l'offerta e cosa c'e' fra i Servizi.

La regola (75%, ricarica a zero, solo titolare) e' eseguita in
`tests/test_trigger_servizi_frontend.py`. Qui il cablaggio dei .tsx, che
l'harness non esegue: forma del sorgente, normalizzata dagli spazi.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

_WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"


def _n(rel: str) -> str:
    t = (_WEB / rel).read_text(encoding="utf-8")
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    return re.sub(r"\s+", "", t)


def test_il_boost_e_fra_i_servizi_a_10_euro():
    servizi = esegui_ts("lib/assistenza", "emit(m.SERVIZI)", None, richiede=["whatsappLink"])
    boost = [s for s in servizi if s["key"] == "boost_ai"]
    assert len(boost) == 1
    b = boost[0]
    assert b["priceValue"] == "10€ + IVA una tantum" and b["priceMode"] == "fixed"
    assert "300 crediti" in b["descrizione"] and "non scade" in b["descrizione"]
    assert b["soloClienti"] is True


def test_la_landing_non_elenca_il_boost_fra_i_servizi():
    assert "SERVIZI.filter((sv)=>!sv.soloClienti).map((sv)=>{" in _n("components/landing/servizi-modal.tsx")


def test_l_icona_del_boost_esiste_dove_si_disegnano_i_servizi():
    for rel in ("app/(app)/assistenza/marketplace.tsx", "components/landing/servizi-modal.tsx"):
        n = _n(rel)
        assert "Zap," in n and "Zap,};" in n, rel


def test_la_home_del_locale_propone_il_boost_coi_numeri_del_contatore():
    n = _n("app/(app)/dashboard/page.tsx")
    assert (
        "chatVisibile(config)&&triggerAbilitati(user?.pagine_abilitate)"
        "?valutaTrigger(\"home\",segnaliBoost(quotaDaConfig(config),!user?.sotto_utente)):null;"
    ) in n
    assert "<Suspensefallback={null}><BoostBlock/></Suspense>" in n


def test_la_home_di_catena_propone_il_boost_coi_numeri_del_gruppo():
    n = _n("app/(app)/catena/page.tsx")
    assert (
        "chatCatenaAttiva(chatConfig)&&triggerAbilitati(utente?.pagine_abilitate)"
        "?valutaTrigger(\"home\",segnaliBoost(quotaDaGruppo(chatConfig),!utente?.sotto_utente)):null;"
    ) in n
    assert "<TriggerHinttrigger={boost}className=\"mt-6\"/>" in n
