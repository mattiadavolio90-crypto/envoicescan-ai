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
# Dalla fase I la logica della conversazione di una vista vive in un hook solo,
# usato dalla Home e da /m/chat: i presidi che guardavano _CONV guardano lui.
_HOOK = _WEB / "components/home/use-conversazione.ts"
_M_CHAT = _WEB / "app/(mobile)/m/chat/mobile-chat.tsx"
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


def test_home_e_telefono_usano_la_stessa_conversazione():
    """Una sola copia della logica di una vista: se una delle due superfici la
    riscrive, torna il difetto che la fase I ha chiuso (due copie che divergono)."""
    for p in (_CONV, _M_CHAT):
        assert "useConversazione({vista,quota,lettoAlle})" in _n(p), p
        assert "useAssistente" not in _n(p), p


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
    assert "<AssistenteProviderkey={idPersona(user)}utenteId={idPersona(user)}>" in n
    assert n.index("<AssistenteProvider") < n.index("<mainclassName") < n.index("</AssistenteProvider>")


def test_il_provider_manda_solo_la_vista_corrente_e_col_suo_contesto():
    n = _n(_PROVIDER)
    # Il corpo lo compone corpoRichiestaChat (lib/home-chat.ts, eseguita in
    # test_home_chat_frontend.py): messaggi della sola vista, il suo contesto,
    # card_conferma.
    assert "body:JSON.stringify(corpoRichiestaChat(vociRef.current,vista,mobile))" in n
    assert ("conRisposta(v,vista.chiave,messaggioRisposta(res.status,data),"
            "data.reply?cardDaProposte(data.proposte,Date.now()):[],)") in n
    assert "constchiave=chiaveConversazione(utenteId);" in n
    assert "sessionStorage.removeItem(CHIAVE_VECCHIA)" in n


def test_a_schermo_la_conversazione_della_sola_vista_aperta():
    """Mattia, 29/9: la conversazione che continuava sotto il briefing di un
    altro locale confondeva. Il pannello riceve i soli messaggi della vista, e
    «Nuova conversazione» e l'attesa riguardano solo lei."""
    h = _n(_HOOK)
    assert "constvoci=vociDellaVista(tutte,vista.chiave);" in h
    assert "nuova:()=>nuova(vista.chiave)," in h
    assert "attesa:inCorso===vista.chiave?testoAttesa(attesa):null," in h
    c = _n(_CONV)
    assert "<PannelloConversazionevoci={c.voci}" in c
    assert "attesa={c.attesa}" in c and "onNuova={c.nuova}" in c
    assert "entraIn" not in c and "entraIn" not in _n(_PROVIDER)
    assert "nuova=useCallback((vistaChiave:string)=>aggiorna((v)=>senzaVista(v,vistaChiave))" in _n(_PROVIDER)


def test_la_home_pv_passa_la_sede_aperta_e_la_regola_della_chat():
    n = _n(_PV)
    assert "chatVisibile(config)&&(<ConversazioneAssistentevista={vistaSede(utente?.sede_attiva_id)}" in n
    assert "quota={quotaDaConfig(config)}" in n


def test_la_home_di_catena_passa_il_pool_solo_se_attivo():
    n = _n(_CATENA_PAGE)
    assert "chatCatenaAttiva(chatConfig)?{quota:quotaDaGruppo(chatConfig),lettoAlle:Date.now(),settore:utente?.tipo_attivita??null,}:null" in n
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
    c = _n(_HOOK)
    assert "statoCrediti({limiteGiorno,limiteMese},server,risposta)" in c
    assert "},[oggi,mese,ricarica,lettoAlle]);" in c
    # la domanda parte coi crediti che la vista mostra ora
    assert "voidinvia(testoDomanda,vista,crediti);" in c
    assert "...contatoreAggiornato(data,attuale)," in p


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
    h = _n(_HOOK)
    assert "constbloccato=inCorso!==null||esaurite;" in h
    assert "inAltraVista:inCorso!==null&&inCorso!==vista.chiave," in h
    assert "c.inAltraVista" in _n(_CONV)
    assert "Storispondendoalladomandachehaifattoinun'altravista…" in _n(_CONV)
    assert "c.inAltraVista" in _n(_M_CHAT)


# ─── Fase 3: la card delle cifre dettate ──────────────────────────────────────
# La logica (validazione, testi, esiti) e' eseguita in test_home_chat_frontend.py;
# qui che la Conferma rimandi la proposta all'endpoint giusto, una volta sola, e
# che la card arrivi a schermo solo con chi sa gestirla.
_CARD = _WEB / "components/home/card-cifra.tsx"
_PANNELLO = _WEB / "components/home/pannello-conversazione.tsx"


def test_la_conferma_scrive_solo_dall_endpoint_dedicato_e_una_volta():
    n = _n(_PROVIDER)
    i = n.index("constconferma=useCallback(")
    corpo = n[i:n.index("constannulla=useCallback(", i)]
    assert "if(!card||!confermabile(card))return;" in corpo
    assert 'aggiorna((v)=>conCard(v,cardId,(c)=>({...c,stato:"invio",messaggio:undefined})));' in corpo
    assert corpo.index('stato:"invio"') < corpo.index("awaitfetch(")
    assert 'fetch("/api/assistente/registra",{method:"POST"' in corpo
    assert "body:JSON.stringify(corpoConferma(card.proposta))" in corpo
    assert "constesito=esitoConferma(res.status,data,trovaCard(vociRef.current,cardId)??card);" in corpo
    assert "aggiorna((v)=>conCard(v,cardId,()=>esito));" in corpo
    assert 'if(esito.stato==="registrata")router.refresh();' in corpo
    assert "/api/chat" not in corpo


def test_annulla_non_chiama_il_server():
    n = _n(_PROVIDER)
    i = n.index("constannulla=useCallback(")
    corpo = n[i:n.index("return(", i)]
    assert "fetch" not in corpo
    assert 'confermabile(c)?{...c,stato:"annullata"' in corpo


def test_la_card_arriva_a_schermo_con_i_suoi_pulsanti():
    assert "conferma:(id:string)=>voidconferma(id)," in _n(_HOOK)
    assert "onConferma={c.conferma}onAnnulla={c.annulla}" in _n(_CONV)
    p = _n(_PANNELLO)
    assert "v.card?.map((c)=>(<CardCifraDettatakey={c.id}card={c}onConferma={onConferma}onAnnulla={onAnnulla}/>))" in p
    k = _n(_CARD)
    assert '{onConferma&&(aperta||card.stato==="invio")&&(' in k
    assert "constaperta=confermabile(card);" in k
    assert 'disabled={card.stato==="invio"}onClick={()=>onConferma(card.id)}' in k


def test_niente_card_della_bozza():
    """Bozze al fornitore spente (Mattia, 3/10/2026): niente card sotto la risposta."""
    assert not (_WEB / "components/home/card-bozza.tsx").exists()
    for p in (_PANNELLO, _PROVIDER):
        assert "bozz" not in _n(p).lower(), p


def test_lo_score_usa_il_copia_condiviso():
    s = _n(_WEB / "app/(app)/prezzi/score-tab.tsx")
    assert 'import{CopyButton}from"@/components/ui/copy-button";' in s
    assert "functionCopyButton" not in s
    c = _n(_WEB / "components/ui/copy-button.tsx")
    assert "awaitnavigator.clipboard.writeText(testo);" in c


def test_la_demo_non_conferma_niente():
    assert "onConferma" not in _n(_DEMO_CHAT)
