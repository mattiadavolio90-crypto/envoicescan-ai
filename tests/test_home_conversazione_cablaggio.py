"""La conversazione nel riquadro del briefing — step 4, 28/9/2026.

Mattia: via il pulsante flottante «Chiedi a ONEFLUX», l'assistente vive solo in
Home, dentro il riquadro del briefing. La logica (vista dei messaggi, riga «Ora
sei in…», cosa va al backend) e' eseguita in `test_home_chat_frontend.py`; qui
si guarda che i componenti la usino, e che il vecchio pulsante non torni.
"""
import re
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parent.parent / "apps/web/src"
_PROVIDER = _WEB / "components/home/assistente-provider.tsx"
_CONV = _WEB / "components/home/conversazione-assistente.tsx"
_LAYOUT = _WEB / "app/(app)/layout.tsx"
_PV = _WEB / "app/(app)/dashboard/page.tsx"
_CATENA_PAGE = _WEB / "app/(app)/catena/page.tsx"
_CATENA = _WEB / "app/(app)/catena/sintesi-catena.tsx"
_BRIEFING_PV = _WEB / "app/(app)/dashboard/home-briefing.tsx"
_DEMO_HOME = _WEB / "components/demo/screens/demo-home.tsx"
_DEMO_CHAT = _WEB / "components/demo/demo-chat.tsx"
_DEMO_SHELL = _WEB / "app/(demo)/demo/demo-shell.tsx"


def _n(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    t = re.sub(r"\{/\*.*?\*/\}", "", t, flags=re.S)
    return re.sub(r"\s+", "", t)


def test_il_pulsante_flottante_non_c_e_piu():
    assert not (_WEB / "app/(app)/dashboard/chat-widget.tsx").exists()
    for p in list(_WEB.rglob("*.tsx")):
        t = _n(p)
        assert "ChatWidget" not in t, p
        assert "ChiediaONEFLUX" not in t, p


@pytest.mark.parametrize("p", [_PV, _CATENA], ids=lambda p: p.name)
def test_niente_spazio_riservato_al_pulsante(p):
    assert 'aria-hiddenclassName="h-20"' not in _n(p)


def test_la_conversazione_sta_nel_layout_dell_app_per_utente():
    n = _n(_LAYOUT)
    assert "<AssistenteProviderutenteId={user.id}>" in n
    assert n.index("<AssistenteProvider") < n.index("<mainclassName") < n.index("</AssistenteProvider>")


def test_il_provider_manda_solo_la_vista_corrente_e_col_suo_contesto():
    n = _n(_PROVIDER)
    assert "messages:codaPerVista(vociRef.current,vista),contesto:vista.contesto" in n
    assert "conRisposta(v,vista.chiave,messaggioRisposta(res.status,data))" in n
    assert "constchiave=chiaveConversazione(utenteId);" in n
    assert "sessionStorage.removeItem(CHIAVE_VECCHIA)" in n


def test_la_riga_ora_sei_in_aspetta_la_conversazione_salvata():
    """Aggiunta prima della lettura, finiva su una conversazione vuota e si perdeva."""
    assert "if(pronta)entraIn(vista);" in _n(_CONV)


def test_la_home_pv_passa_la_sede_aperta_e_la_regola_della_chat():
    n = _n(_PV)
    assert "chatVisibile(config)&&(<ConversazioneAssistentevista={vistaSede(utente?.sede_attiva_id,utente?.sede_attiva_nome??utente?.nome_ristorante)}" in n
    assert "limiteGiorno={config?.chat_limite_giorno??0}domandeOggiIniziali={config?.chat_domande_oggi??0}" in n


def test_la_home_di_catena_passa_il_pool_solo_se_attivo():
    n = _n(_CATENA_PAGE)
    assert "chatCatenaAttiva(chatConfig)?{limiteGiorno:chatConfig.limite_giorno,domandeOggi:chatConfig.domande_oggi}:null" in n
    c = _n(_CATENA)
    assert "{chat&&(<ConversazioneAssistentevista={vistaCatena(nomeGruppo)}" in c
    assert "chat={chat}" in c


def test_la_conversazione_e_dentro_il_riquadro_del_briefing():
    assert "chiaveGiorno={briefing.data}>{conversazione}</RiquadroAssistente>" in _n(_BRIEFING_PV)
    c = _n(_CATENA)
    i = c.index("<RiquadroAssistente")
    assert c.index("<ConversazioneAssistente", i) < c.index("</RiquadroAssistente>", i)


def test_la_demo_usa_lo_stesso_pannello_dentro_il_riquadro():
    assert "<PannelloConversazione" in _n(_DEMO_CHAT)
    assert "fixed" not in _n(_DEMO_CHAT)
    assert "conversazione={<DemoConversazioneattiva={chatAttiva}/>}" in _n(_DEMO_HOME)
    assert "chatAttiva={openChat}" in _n(_DEMO_SHELL)
    assert "<DemoChat" not in _n(_DEMO_SHELL)
