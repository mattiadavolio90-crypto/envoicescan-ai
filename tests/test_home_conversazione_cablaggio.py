"""La conversazione nel riquadro del briefing — step 4, 28/9/2026.

Mattia: via il pulsante flottante «Chiedi a ONEFLUX», l'assistente vive solo in
Home, dentro il riquadro del briefing. Dal 29/9 una conversazione per vista:
sotto il briefing di un locale si vedono solo i suoi messaggi. La logica (quali
messaggi, cosa va al backend) e' eseguita in `test_home_chat_frontend.py`; qui
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
    # key: l'admin che entra in un cliente e ne esce con router.push non
    # ricarica il layout; senza, conversazione e conteggio passavano da un
    # cliente all'altro (revisore, 28/9).
    assert "<AssistenteProviderkey={user.id}utenteId={user.id}>" in n
    assert n.index("<AssistenteProvider") < n.index("<mainclassName") < n.index("</AssistenteProvider>")


def test_il_provider_manda_solo_la_vista_corrente_e_col_suo_contesto():
    n = _n(_PROVIDER)
    assert "messages:codaPerVista(vociRef.current,vista),contesto:vista.contesto" in n
    assert "conRisposta(v,vista.chiave,messaggioRisposta(res.status,data))" in n
    assert "constchiave=chiaveConversazione(utenteId);" in n
    assert "sessionStorage.removeItem(CHIAVE_VECCHIA)" in n


def test_a_schermo_la_conversazione_della_sola_vista_aperta():
    """Mattia, 29/9: la conversazione che continuava sotto il briefing di un
    altro locale confondeva. Il pannello riceve i soli messaggi della vista, e
    «Nuova conversazione» e l'attesa riguardano solo lei."""
    c = _n(_CONV)
    assert "constvoci=vociDellaVista(tutte,vista.chiave);" in c
    assert "<PannelloConversazionevoci={voci}" in c
    assert "onNuova={()=>nuova(vista.chiave)}" in c
    assert "attesa={inCorso===vista.chiave?testoAttesa(attesa):null}" in c
    assert "entraIn" not in c and "entraIn" not in _n(_PROVIDER)
    assert "nuova=useCallback((vistaChiave:string)=>aggiorna((v)=>senzaVista(v,vistaChiave))" in _n(_PROVIDER)


def test_la_home_pv_passa_la_sede_aperta_e_la_regola_della_chat():
    n = _n(_PV)
    assert "chatVisibile(config)&&(<ConversazioneAssistentevista={vistaSede(utente?.sede_attiva_id)}" in n
    assert "limiteGiorno={config?.chat_limite_giorno??0}domandeOggiIniziali={config?.chat_domande_oggi??0}" in n


def test_la_home_di_catena_passa_il_pool_solo_se_attivo():
    n = _n(_CATENA_PAGE)
    assert "chatCatenaAttiva(chatConfig)?{limiteGiorno:chatConfig.limite_giorno,domandeOggi:chatConfig.domande_oggi,lettoAlle:Date.now(),settore:utente?.tipo_attivita??null,}:null" in n
    c = _n(_CATENA)
    assert "{chat&&(<ConversazioneAssistentevista={vistaCatena()}" in c
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


def test_il_contatore_e_uno_per_account_e_segue_la_lettura_piu_recente():
    p = _n(_PROVIDER)
    assert "useState<Conteggio|null>(null)" in p
    assert "finita:quotaEsaurita(res.status,data)" in p
    c = _n(_CONV)
    assert "statoDomande(limiteGiorno,server,domande)" in c
    assert "},[domandeOggiIniziali,lettoAlle]);" in c


@pytest.mark.parametrize("p", [_PV, _CATENA_PAGE], ids=lambda p: p.name)
def test_ogni_render_della_home_porta_l_ora_della_lettura(p):
    assert "lettoAlle" in _n(p) and "Date.now()" in _n(p)


def test_le_domande_proposte_seguono_il_settore():
    assert "suggerimentiPer(vista.contesto,settore)" in _n(_CONV)
    assert "settore={utente?.tipo_attivita}" in _n(_PV)
    assert "settore={chat.settore}" in _n(_CATENA)


def test_la_casella_ferma_per_una_domanda_altrove_dice_perche():
    """Revisore, 29/9: domanda nella sede A, passaggio alla B prima della
    risposta. In B la casella e' ferma (una domanda alla volta) e senza attesa
    visibile sembrava rotta."""
    c = _n(_CONV)
    assert "constbloccato=inCorso!==null||esaurite;" in c
    assert ":inCorso!==null&&inCorso!==vista.chiave?\"Storispondendoalladomandachehaifattoinun'altravista…\"" in c
