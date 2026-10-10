"""Chat della Home (`lib/home-chat.ts`).

Perche' esiste: due di queste funzioni proteggono da guasti che l'utente non
puo' aggirare da solo.

`parseStorico` legge sessionStorage, cioe' contenuto fuori dal nostro controllo:
se lancia, la chat non si apre piu' e non c'e' modo di ripulirla dall'interfaccia.
`codaDaInviare` tronca la conversazione a 16 messaggi perche' il backend ne
accetta 20 (ChatRequest.max_length): senza, dopo ~20 scambi ogni invio falliva
con 422 e un errore generico.
"""

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/home-chat"


def _chiama(fn, args, richiede=None):
    return esegui_ts(MODULO, f"emit(m.{fn}(...input));", argomento=args, richiede=richiede or [fn])


def _msg(i):
    return {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}


# ─── parseStorico: quattro modi di avere spazzatura, zero eccezioni ───────

def test_storico_assente():
    assert _chiama("parseStorico", [None]) == []
    assert _chiama("parseStorico", [""]) == []


def test_storico_non_e_json():
    """Non deve lanciare: un throw qui blocca la chat per sempre."""
    assert _chiama("parseStorico", ["{non json"]) == []


def test_storico_json_ma_non_array():
    assert _chiama("parseStorico", ['{"role":"user"}']) == []
    assert _chiama("parseStorico", ["42"]) == []
    assert _chiama("parseStorico", ["null"]) == []


def test_storico_scarta_le_voci_malformate_e_tiene_le_buone():
    grezzo = (
        '[{"role":"user","content":"ok"},'
        '{"role":"hacker","content":"x"},'      # ruolo non previsto
        '{"role":"assistant","content":123},'   # contenuto non stringa
        '{"role":"assistant"},'                 # senza contenuto
        'null,'                                 # voce nulla
        '{"role":"assistant","content":"ok2"}]'
    )
    out = _chiama("parseStorico", [grezzo])
    assert [m["content"] for m in out] == ["ok", "ok2"]


def test_storico_una_voce_null_non_fa_esplodere_il_filtro():
    """`m &&` prima dei confronti: senza, `null.role` lancerebbe."""
    assert _chiama("parseStorico", ["[null,null]"]) == []


# ─── codaDaInviare: il tetto che evita il 422 ─────────────────────────────

def test_coda_corta_passa_intera():
    msgs = [_msg(i) for i in range(5)]
    assert len(_chiama("codaDaInviare", [msgs])) == 5


def test_coda_lunga_e_troncata_a_16_TENENDO_LA_FINE():
    """Il taglio prende la coda, non la testa: il contesto utile e' l'ultimo."""
    msgs = [_msg(i) for i in range(40)]
    out = _chiama("codaDaInviare", [msgs])
    assert len(out) == 16
    assert out[-1]["content"] == "m39"
    assert out[0]["content"] == "m24"


def test_coda_esattamente_al_limite():
    assert len(_chiama("codaDaInviare", [[_msg(i) for i in range(16)]])) == 16


def test_coda_vuota():
    assert _chiama("codaDaInviare", [[]]) == []


# ─── quota rimanente ──────────────────────────────────────────────────────

def test_rimanenti_normale():
    assert _chiama("domandeRimanenti", [20, 3]) == 17


def test_rimanenti_non_va_MAI_sotto_zero():
    """Un contatore backend piu' alto del limite (piano cambiato in giornata)
    non deve mostrare "-3 domande rimaste"."""
    assert _chiama("domandeRimanenti", [20, 25]) == 0


# ─── messaggioRisposta: cosa legge l'utente quando qualcosa va storto ─────

def test_risposta_normale_vince_su_tutto():
    assert _chiama("messaggioRisposta", [200, {"reply": "ecco"}]) == "ecco"


def test_reply_vince_anche_con_status_di_errore():
    """Se il backend manda comunque una risposta, quella si mostra."""
    assert _chiama("messaggioRisposta", [429, {"reply": "ecco"}]) == "ecco"


def test_429_spiega_il_limite_giornaliero():
    """Il 429 deve dire DUE cose: che il limite e' finito e QUANDO riparte.

    Diceva «Riprova domani», che col contatore sul giorno UTC era falso nelle
    due direzioni (chi finiva la quota alle 23:00 ripartiva dopo un'ora; chi la
    finiva alle 00:30 aveva gia' «domani» sul calendario ma aspettava fino
    all'01:00). Dal 23/09/2026 la finestra e' il giorno di Roma, quindi
    l'azzeramento e' davvero a mezzanotte — e il messaggio lo dice invece di
    lasciarlo indovinare.
    """
    out = _chiama("messaggioRisposta", [429, {}])
    assert "limite di domande" in out
    assert "mezzanotte" in out, (
        "il messaggio non dice quando riparte: «per oggi» da solo non basta, "
        f"il cliente non sa se aspettare un'ora o un giorno. Testo: {out!r}"
    )
    assert "domani" not in out, (
        "«domani» e' l'indicazione che era falsa: il contatore si azzera a "
        f"mezzanotte, non a un generico domani. Testo: {out!r}"
    )


def test_403_parla_del_piano():
    assert "piano" in _chiama("messaggioRisposta", [403, {}])


def test_504_NON_usa_il_messaggio_del_backend():
    """Il testo di un gateway non e' scritto per un ristoratore: qui il nostro
    vince anche se `error` c'e'."""
    out = _chiama("messaggioRisposta", [504, {"error": "upstream request timeout"}])
    assert out == "L'assistente ha impiegato troppo tempo. Riprova."


def test_errore_4xx_usa_error_se_c_e():
    assert _chiama("messaggioRisposta", [400, {"error": "boom"}]) == "boom"
    assert "errore" in _chiama("messaggioRisposta", [400, {}]).lower()


@pytest.mark.parametrize("status,error", [
    (500, "OPENAI_API_KEY non configurata"),
    (500, "Internal Server Error"),
    (502, "Errore worker"),
    (503, "Servizio temporaneamente non disponibile. Riprova."),
])
def test_5xx_NON_mostra_il_testo_tecnico(status, error):
    """29/9: in chat e' comparso «OPENAI_API_KEY non configurata». Sui 5xx il
    testo viene dal server o dal gateway, non e' scritto per un ristoratore."""
    out = _chiama("messaggioRisposta", [status, {"error": error}])
    assert out == "L'assistente non è disponibile in questo momento. Riprova tra poco."


# ─── contatore: segue il backend, tranne quando tace su un 429 ────────────

def test_contatore_segue_il_backend():
    assert _chiama("contatoreAggiornato", [200, {"domande_oggi": 7}, 20, 3]) == 7


def test_contatore_su_429_senza_dato_va_a_esaurite():
    assert _chiama("contatoreAggiornato", [429, {}, 20, 3]) == 20


def test_contatore_su_429_CON_dato_usa_il_dato():
    """Il backend ha l'ultima parola anche sul 429."""
    assert _chiama("contatoreAggiornato", [429, {"domande_oggi": 18}, 20, 3]) == 18


def test_contatore_su_altri_errori_non_si_muove():
    """Un 500 non consuma una domanda: il contatore resta dov'era."""
    assert _chiama("contatoreAggiornato", [500, {}, 20, 3]) == 3


def test_contatore_zero_dal_backend_non_e_confuso_con_assente():
    """`typeof === "number"` e non `||`: lo zero e' un valore, non un'assenza."""
    assert _chiama("contatoreAggiornato", [200, {"domande_oggi": 0}, 20, 9]) == 0


# ─── il mobile usa questa libreria, non una sua copia ─────────────────────

def test_la_chat_mobile_non_ricopia_la_decisione_sui_messaggi():
    """`/m/chat` non deve avere una sua copia di come si parla con l'assistente.

    Fino al 23/09/2026 `mobile-chat.tsx` aveva la stessa catena di `if` di
    `messaggioRisposta` ricopiata a mano, identica riga per riga. Due copie della
    stessa decisione di cui l'harness ne esegue **una sola**: quando il messaggio
    del 429 e' stato corretto perche' diceva il falso, la copia mobile e' rimasta
    indietro e nessun test se ne e' accorto.

    Dalla fase I (10/10/2026) il telefono non chiama piu' /api/chat da solo:
    passa dal provider della Home (`useConversazione` -> `AssistenteProvider`),
    che usa `messaggioRisposta`. Il presidio guarda la FORMA dei .tsx perche'
    l'harness non esegue i componenti: e' un limite dichiarato, non una svista.
    Uccide il mutante realistico — reintrodurre una chiamata o una copia nel
    telefono — e la logica vera resta provata dai test qui sopra, che la eseguono.
    """
    from pathlib import Path

    web = Path("apps/web/src")
    sorgente = (web / "app/(mobile)/m/chat/mobile-chat.tsx").read_text(encoding="utf-8")
    provider = (web / "components/home/assistente-provider.tsx").read_text(encoding="utf-8")

    assert "useConversazione" in sorgente, "la chat mobile non usa la conversazione condivisa"
    assert "fetch(" not in sorgente, (
        "la chat mobile chiama /api/chat da sola: la decisione sui messaggi e' di nuovo duplicata"
    )
    assert "messaggioRisposta" in provider and 'from "@/lib/home-chat"' in provider, (
        "il provider deve prendere messaggioRisposta da lib/home-chat, l'unica copia eseguita dai test"
    )
    for testo in ("Hai raggiunto il limite di domande",
                  "La chat non è disponibile nel tuo piano"):
        for nome, src in (("mobile-chat", sorgente), ("assistente-provider", provider)):
            assert testo not in src, (
                f"{nome}.tsx contiene il testo {testo!r}: e' una seconda copia "
                "del messaggio, e vivrebbe fuori dalla portata dei test"
            )


def test_il_telefono_mostra_le_card_con_conferma():
    """Senza la card il cliente leggerebbe «premi Conferma» e non troverebbe niente
    da premere. Forma del .tsx: il render non si esegue, la logica delle card si'
    (`cardDaProposte`, `esitoConferma` qui sopra)."""
    from pathlib import Path

    m = Path("apps/web/src/app/(mobile)/m/chat/mobile-chat.tsx").read_text(encoding="utf-8")
    assert "<CardCifraDettata" in m and "onConferma={c.conferma}" in m and "onAnnulla={c.annulla}" in m


def test_il_telefono_dice_al_worker_di_essere_il_telefono():
    """Il layout di /m monta il provider con `mobile`: senza, il corpo non porta il
    flag e il worker rimanda a una scheda (Score Fornitori) che sul telefono non c'e'.
    Forma del .tsx, come sopra: il corpo vero e' provato da `corpoRichiestaChat`."""
    from pathlib import Path

    web = Path("apps/web/src")
    layout = (web / "app/(mobile)/m/layout.tsx").read_text(encoding="utf-8")
    provider = (web / "components/home/assistente-provider.tsx").read_text(encoding="utf-8")
    assert "<AssistenteProvider" in layout and " mobile>" in layout
    assert "corpoRichiestaChat(vociRef.current, vista, mobile)" in provider
    # La Home non lo dice: il suo corpo resta quello di prima.
    app_layout = (web / "app/(app)/layout.tsx").read_text(encoding="utf-8")
    assert "<AssistenteProvider" in app_layout and "mobile" not in app_layout.split("<AssistenteProvider")[1].split(">")[0]


def test_429_mensile_riconosciuto_come_mese():
    """Col budget mensile esaurito il cliente NON deve sentirsi dire «domani».

    Il contatore del giorno su un 429 mensile va al massimo — vero ma
    incompleto: chi legge la barra conclude «riprovo domani» e domani e' fermo
    di nuovo. `quotaEsaurita` distingue i due casi dal messaggio del backend,
    che e' l'unico segnale che arriva al client.
    """
    msg = "Hai usato tutte le 300 domande di questo mese. Il budget riparte il 1° del mese prossimo."
    assert _chiama("quotaEsaurita", [429, {"error": msg}]) == "mese"


def test_429_giornaliero_riconosciuto_come_giorno():
    msg = "Hai raggiunto il limite di 30 domande per oggi. Il contatore si azzera a mezzanotte."
    assert _chiama("quotaEsaurita", [429, {"error": msg}]) == "giorno"


def test_429_senza_messaggio_ripiega_sul_giorno():
    """Senza testo si assume il caso piu' frequente e meno grave: il giorno."""
    assert _chiama("quotaEsaurita", [429, {}]) == "giorno"


def test_fuori_dal_429_nessuna_quota_e_esaurita():
    for status in (200, 403, 500, 504):
        assert _chiama("quotaEsaurita", [status, {"error": "questo mese"}]) is None, (
            f"status {status}: non e' un limite di quota, non deve dire che e' esaurita"
        )


# ─── Una conversazione sola, con la vista di ogni messaggio (28/9/2026) ──────
#
# Il pulsante flottante teneva lo storico in una chiave di sessionStorage
# condivisa fra catena e punto vendita: al backend arrivavano, come contesto,
# domande fatte su un altro locale. Ora ogni voce porta la vista in cui e' stata
# scritta, e al backend va solo la vista corrente.


def _vs(id_="r1"):
    return _chiama("vistaSede", [id_])


def _vc():
    return _chiama("vistaCatena", [])


def _u(testo, vista):
    return {"role": "user", "content": testo, "vista": vista}


def _a(testo, vista):
    return {"role": "assistant", "content": testo, "vista": vista}


def test_la_vista_di_una_sede_e_diversa_da_quella_di_un_altra():
    a, b = _vs("r1"), _vs("r2")
    assert a["chiave"] != b["chiave"]
    assert a["contesto"] == b["contesto"] == "sede"


def test_la_vista_catena():
    assert _vc() == {"chiave": "catena", "contesto": "catena"}


def test_la_conversazione_salvata_scarta_le_voci_senza_vista():
    """Il formato del vecchio pulsante non diceva a quale locale apparteneva; le
    righe «Ora sei in…» salvate prima del 29/9 non si mostrano piu'."""
    grezzo = (
        '[{"role":"user","content":"vecchia"},'
        '{"role":"user","content":"ok","vista":"catena"},'
        '{"role":"vista","content":"Ora sei in A","vista":"sede:r1"},'
        '{"role":"assistant","content":"x","vista":""},'
        '{"role":"hacker","content":"x","vista":"catena"},'
        'null]'
    )
    out = _chiama("parseConversazione", [grezzo])
    assert [v["content"] for v in out] == ["ok"]


def test_la_conversazione_salvata_non_lancia_mai():
    for raw in [None, "", "{rotto", "42", "null", '{"a":1}']:
        assert _chiama("parseConversazione", [raw]) == []


def test_si_salvano_solo_le_ultime_voci():
    voci = [_u(f"m{i}", "catena") for i in range(250)]
    out = _chiama("daSalvare", [voci])
    assert len(out) == 200
    assert out[0]["content"] == "m50" and out[-1]["content"] == "m249"


# ─── Una conversazione per vista (Mattia, 29/9) ─────────────────────────

_TRE_VISTE = [
    _u("catena?", "catena"), _a("gruppo", "catena"),
    _u("sede?", "sede:r1"), _a("locale", "sede:r1"),
    _u("altra?", "sede:r2"),
]


def test_a_schermo_solo_la_conversazione_della_vista_aperta():
    """Sotto il briefing di un locale non compaiono domande fatte su un altro:
    era la confusione della foto del 29/9."""
    assert _chiama("vociDellaVista", [_TRE_VISTE, "sede:r1"]) == [_u("sede?", "sede:r1"), _a("locale", "sede:r1")]
    assert _chiama("vociDellaVista", [_TRE_VISTE, "catena"]) == [_u("catena?", "catena"), _a("gruppo", "catena")]
    assert _chiama("vociDellaVista", [_TRE_VISTE, "sede:r9"]) == []


def test_tornando_nel_locale_la_conversazione_c_e_ancora():
    """Cambiare locale non cancella niente: e' la stessa lista, filtrata."""
    dopo = _TRE_VISTE + [_u("ancora?", "sede:r2")]
    assert [v["content"] for v in _chiama("vociDellaVista", [dopo, "sede:r1"])] == ["sede?", "locale"]


def test_nuova_conversazione_ricomincia_solo_quella_della_vista():
    out = _chiama("senzaVista", [_TRE_VISTE, "sede:r1"])
    assert [v["content"] for v in out] == ["catena?", "gruppo", "altra?"]


def test_al_backend_solo_i_messaggi_della_vista_corrente():
    """LA regressione: prima tutto lo storico, di tutte le viste."""
    out = _chiama("codaPerVista", [_TRE_VISTE, _vs("r1")])
    assert out == [{"role": "user", "content": "sede?"}, {"role": "assistant", "content": "locale"}]


def test_al_backend_al_massimo_16_e_solo_role_e_content():
    voci = [_u(f"m{i}", "catena") for i in range(20)]
    out = _chiama("codaPerVista", [voci, _vc()])
    assert len(out) == 16
    assert out[-1]["content"] == "m19"
    assert all(set(m) == {"role", "content"} for m in out)


def test_le_domande_proposte_finche_in_questa_vista_non_si_e_scritto():
    voci = [_u("q", "catena"), _a("r", "catena")]
    assert _chiama("mostraSuggerimenti", [voci, _vc()]) is False
    assert _chiama("mostraSuggerimenti", [voci, _vs()]) is True
    assert _chiama("mostraSuggerimenti", [[], _vc()]) is True


def test_la_risposta_resta_nella_vista_della_sua_domanda():
    """Domanda in catena, poi il cliente scende in un locale e ci scrive prima
    che arrivi la risposta: la risposta resta nella conversazione della catena."""
    voci = [_u("q", "catena"), _u("altro", "sede:r1")]
    out = _chiama("conRisposta", [voci, "catena", "risposta"])
    assert out[1] == _a("risposta", "catena")
    assert _chiama("vociDellaVista", [out, "catena"]) == [_u("q", "catena"), _a("risposta", "catena")]


def test_la_risposta_senza_domanda_va_in_fondo():
    out = _chiama("conRisposta", [[], "catena", "r"])
    assert out == [_a("r", "catena")]


def test_la_chiave_di_sessionstorage_e_per_utente():
    """sessionStorage sopravvive al logout nella stessa scheda."""
    a = _chiama("chiaveConversazione", ["u1"])
    b = _chiama("chiaveConversazione", ["u2"])
    assert a != b and a != "oneflux:chat-messages"


def test_contatore_e_attesa():
    assert _chiama("testoContatore", [1]) == "Ti restano 1 domanda oggi"
    assert _chiama("testoContatore", [5]) == "Ti restano 5 domande oggi"
    assert _chiama("testoContatore", [0]).startswith("Limite di oggi raggiunto")
    assert [_chiama("testoAttesa", [i]) for i in (0, 1, 2, 7)] == [
        "Sto cercando...", "Sto leggendo le tue fatture...", "Ci sono quasi, un attimo...", "Ci sono quasi, un attimo...",
    ]


# ─── Il contatore: una quota per account, vince la lettura piu' recente ─────
#
# Revisore, 28/9: il conteggio era tenuto per vista e il provider non si
# rimonta mai. Tornando in catena dopo domande nel PV il numero vecchio vinceva
# sul server (il backend conta UN pool per account); il mattino dopo, con la
# scheda aperta, la casella restava bloccata finche' non si ricaricava.


def _stato(limite, server, risposta):
    return _chiama("statoDomande", [limite, server, risposta])


def test_senza_risposte_conta_il_server():
    out = _stato(20, {"valore": 3, "alle": 100}, None)
    assert out == {"usate": 3, "rimanenti": 17, "esaurite": False, "testo": "Ti restano 17 domande oggi"}


def test_la_risposta_piu_recente_vince_sul_server():
    out = _stato(20, {"valore": 3, "alle": 100}, {"valore": 4, "alle": 200})
    assert out["usate"] == 4


def test_tornando_in_catena_vince_il_server_riletto():
    """3 domande in catena, 2 nel PV: la Home di catena rilegge 5 dal server."""
    out = _stato(20, {"valore": 5, "alle": 300}, {"valore": 3, "alle": 200})
    assert out["usate"] == 5


def test_il_mattino_dopo_la_casella_si_sblocca():
    out = _stato(20, {"valore": 0, "alle": 900}, {"valore": 20, "alle": 500})
    assert out["esaurite"] is False and out["rimanenti"] == 20


def test_limite_mensile_detto_come_mensile():
    """Un 429 mensile che dice «si azzera a mezzanotte» fa riprovare domani."""
    out = _stato(20, {"valore": 2, "alle": 100}, {"valore": 20, "alle": 200, "finita": "mese"})
    assert out["esaurite"] is True and out["rimanenti"] == 0
    assert "mese" in out["testo"] and "mezzanotte" not in out["testo"]


def test_limite_giornaliero_detto_come_giornaliero():
    out = _stato(20, {"valore": 2, "alle": 100}, {"valore": 20, "alle": 200, "finita": "giorno"})
    assert out["testo"] == "Limite di oggi raggiunto — si azzera a mezzanotte"


def test_una_lettura_nuova_del_server_toglie_il_limite_mensile_vecchio():
    out = _stato(20, {"valore": 0, "alle": 300}, {"valore": 20, "alle": 200, "finita": "mese"})
    assert out["esaurite"] is False


def test_sede_senza_id_manda_solo_l_ultima_domanda():
    """Senza id tutte le sedi avrebbero la chiave «sede:»: niente storico."""
    v = _vs(None)
    assert v["chiave"] == "sede:"
    voci = [_u("vecchia", "sede:"), _a("r", "sede:"), _u("nuova", "sede:")]
    assert _chiama("codaPerVista", [voci, v]) == [{"role": "user", "content": "nuova"}]


def test_limite_mensile_blocca_anche_con_domande_di_oggi_rimaste():
    """Il 429 mensile puo' portare `domande_oggi` (5 su 20): il giorno ne avrebbe
    ancora 15, ma il mese e' finito. La casella va bloccata."""
    out = _stato(20, {"valore": 2, "alle": 100}, {"valore": 5, "alle": 200, "finita": "mese"})
    assert out["rimanenti"] == 0 and out["esaurite"] is True


# ─── Domande proposte per settore (regola 7) ───────────────────────────────


def test_i_ristoranti_hanno_le_domande_di_sempre():
    assert _chiama("suggerimentiPer", ["sede", "ristorazione"]) == [
        "Qual è il mio food cost?", "Cosa devo pagare?", "Com'è andato il MOL?", "Chi è il mio fornitore più caro?",
    ]
    assert _chiama("suggerimentiPer", ["sede", None]) == _chiama("suggerimentiPer", ["sede", "ristorazione"])
    assert _chiama("suggerimentiPer", ["catena", None]) == [
        "Quale punto vendita ha il margine peggiore?", "Dove si spende di più in pesce?",
        "Cosa c'è da vedere nella catena?", "Chi ha lo scontrino medio più alto?",
    ]


@pytest.mark.parametrize("contesto", ["sede", "catena"])
def test_i_negozi_non_leggono_food_cost_pesce_ne_scontrino(contesto):
    testo = " ".join(_chiama("suggerimentiPer", [contesto, "retail"])).lower()
    for parola in ("food cost", "pesce", "scontrino", "coperti"):
        assert parola not in testo


# ─── Fase 3: la card delle cifre dettate ──────────────────────────────────────
# La proposta arriva dal worker (`ChatResponse.proposte`) ed e' gia' il corpo di
# POST /api/assistente/registra; resta in sessionStorage con la sua voce. Qui:
# cosa si accetta, cosa dice la card, cosa si rimanda, com'e' andata.

PROPOSTA = {
    "tipo": "incasso_giorno", "ristorante_id": "r-1", "sede_nome": "NAVIGLI", "data": "2026-09-29",
    "fatturato_iva10": 1800, "altri_ricavi_noiva": 540, "fatturato_iva22": 0, "precedente": None,
    "anno": None, "mese": None, "costo_dipendenti": None, "costo_personale_extra": None,
    "costo_personale_chiamata": None,
}
# Fase D: le voci del personale sulla proposta sono le DETTATE; `restano` quelle
# gia' registrate che non si toccano.
PERSONALE = {**PROPOSTA, "tipo": "personale_mese", "data": None, "anno": 2026, "mese": 8,
             "fatturato_iva10": 0, "altri_ricavi_noiva": 0, "costo_dipendenti": 12000,
             "restano": {"costo_personale_extra": 450, "costo_personale_chiamata": 37}}
FATTURATO = {**PROPOSTA, "tipo": "fatturato_mese", "data": None, "anno": 2026, "mese": 8,
             "fatturato_iva10": 30000, "altri_ricavi_noiva": 2000, "fatturato_iva22": 500}


def _card(proposta=PROPOSTA, stato="attesa", **kw):
    return {"id": "1-0", "proposta": proposta, "stato": stato, **kw}


@pytest.mark.parametrize("p", [PROPOSTA, PERSONALE, FATTURATO], ids=["incasso", "personale", "fatturato"])
def test_proposta_del_worker_valida(p):
    assert _chiama("propostaValida", [p]) is True


@pytest.mark.parametrize("modifica", [
    {"tipo": "costo_affitto"}, {"ristorante_id": ""}, {"ristorante_id": 7},
    {"fatturato_iva10": -1}, {"fatturato_iva10": "1800"}, {"altri_ricavi_noiva": None},
    {"data": "29/09/2026"}, {"data": None},
    {"fatturato_iva10": 0, "altri_ricavi_noiva": 0},
    {"precedente": {"fatturato_iva10": "700"}}, {"precedente": [1]},
    {"sede_nome": 3}, {"costo_personale_extra": -5},
    {"costo_personale_chiamata": -5}, {"costo_personale_chiamata": "37"},
    {"restano": {"costo_dipendenti": -1}}, {"restano": [450]},
], ids=lambda m: ",".join(f"{k}={v!r}" for k, v in m.items()))
def test_proposta_incasso_malformata_scartata(modifica):
    assert _chiama("propostaValida", [{**PROPOSTA, **modifica}]) is False


@pytest.mark.parametrize("p", [
    {**PERSONALE, "costo_dipendenti": 0}, {**PERSONALE, "costo_dipendenti": None},
    {**PERSONALE, "mese": 13}, {**PERSONALE, "mese": 0}, {**PERSONALE, "anno": 2026.5},
    {**FATTURATO, "fatturato_iva10": 0, "altri_ricavi_noiva": 0, "fatturato_iva22": 0},
    {**FATTURATO, "anno": None},
], ids=["pers-zero", "pers-null", "mese-13", "mese-0", "anno-decimale", "fatt-zero", "fatt-senza-anno"])
def test_proposta_mensile_malformata_scartata(p):
    assert _chiama("propostaValida", [p]) is False


def test_card_dalle_proposte_con_id_unici_e_solo_le_valide():
    out = _chiama("cardDaProposte", [[PROPOSTA, {"tipo": "x"}, PERSONALE], 99])
    assert [(c["id"], c["stato"], c["proposta"]["tipo"]) for c in out] == [
        ("99-0", "attesa", "incasso_giorno"), ("99-1", "attesa", "personale_mese")]
    assert _chiama("cardDaProposte", [None, 1]) == []
    assert _chiama("cardDaProposte", [{"tipo": "x"}, 1]) == []


def test_la_risposta_porta_le_sue_card():
    voci = [{"role": "user", "content": "ieri 2.340", "vista": "sede:r-1"}]
    out = _chiama("conRisposta", [voci, "sede:r-1", "Ecco", [_card()]])
    assert out[1]["card"] == [_card()]
    senza = _chiama("conRisposta", [voci, "sede:r-1", "Ecco"])
    assert "card" not in senza[1]


def test_al_worker_si_manda_solo_il_testo_non_le_card():
    voci = [{"role": "user", "content": "ieri 2.340", "vista": "sede:r-1"},
            {"role": "assistant", "content": "Ecco", "vista": "sede:r-1", "card": [_card()]}]
    out = _chiama("codaPerVista", [voci, {"chiave": "sede:r-1", "contesto": "sede"}])
    assert out == [{"role": "user", "content": "ieri 2.340"}, {"role": "assistant", "content": "Ecco"}]


def test_le_card_salvate_tornano_e_quelle_rotte_si_scartano():
    import json
    voci = [{"role": "assistant", "content": "Ecco", "vista": "sede:r-1",
             "card": [_card(), _card(stato="boh"), _card(proposta={"tipo": "x"}), None,
                      _card(stato="registrata", messaggio="Registrato.")]}]
    [voce] = _chiama("parseConversazione", [json.dumps(voci)])
    assert [c["stato"] for c in voce["card"]] == ["attesa", "registrata"]


def test_card_salvata_in_invio_torna_confermabile():
    """Pagina ricaricata mentre la Conferma viaggiava: ripeterla e' innocuo (vedi
    test_conferma_ripetuta_e_registrata); restare «invio» la bloccherebbe per sempre."""
    import json
    voci = [{"role": "assistant", "content": "Ecco", "vista": "sede:r-1", "card": [_card(stato="invio")]}]
    [voce] = _chiama("parseConversazione", [json.dumps(voci)])
    assert voce["card"][0]["stato"] == "attesa"


def test_card_non_array_o_su_voce_del_cliente_si_toglie_la_voce_resta():
    import json
    voci = [{"role": "assistant", "content": "A", "vista": "v", "card": "rotto"},
            {"role": "user", "content": "U", "vista": "v", "card": [_card()]},
            {"role": "assistant", "content": "B", "vista": "v", "extra": 1}]
    out = _chiama("parseConversazione", [json.dumps(voci)])
    assert out == [{"role": "assistant", "content": "A", "vista": "v"},
                   {"role": "user", "content": "U", "vista": "v"},
                   {"role": "assistant", "content": "B", "vista": "v"}]


def test_la_conferma_rimanda_la_proposta_senza_i_campi_della_card():
    out = _chiama("corpoConferma", [{**PERSONALE, "user_id": "altro", "extra": 1}])
    assert out == {k: v for k, v in PERSONALE.items() if k not in ("sede_nome", "restano")}
    assert "restano" not in out


@pytest.mark.parametrize("voci", [
    {"costo_dipendenti": None, "costo_personale_extra": None, "costo_personale_chiamata": 37},
    {"costo_dipendenti": 7320, "costo_personale_extra": 688, "costo_personale_chiamata": 150},
], ids=["sola-chiamata", "tre-voci"])
def test_le_voci_dettate_entrano_nella_conferma(voci):
    p = {**PERSONALE, **voci, "restano": None}
    assert _chiama("propostaValida", [p]) is True
    out = _chiama("corpoConferma", [p])
    assert {k: out[k] for k in voci} == voci


# ─── Cosa dice la card ────────────────────────────────────────────────────────
def test_testo_card_incasso_con_divisione_e_totale():
    t = _chiama("testoCard", [PROPOSTA, 2026])
    assert t["titolo"] == "Incasso di martedì 29 settembre"
    assert t["sede"] == "NAVIGLI"
    assert t["righe"] == [["Al 10%", "1.800,00\u00a0€"], ["Senza IVA", "540,00\u00a0€"]]
    assert t["totale"] == "2.340,00\u00a0€"
    assert t["nota"] is None


def test_testo_card_il_22_solo_se_c_e_e_l_anno_se_non_e_quest_anno():
    t = _chiama("testoCard", [{**PROPOSTA, "data": "2025-12-31", "fatturato_iva22": 100}, 2026])
    assert t["titolo"] == "Incasso di mercoledì 31 dicembre 2025"
    assert t["righe"][-1] == ["Al 22%", "100,00\u00a0€"]
    assert t["totale"] == "2.440,00\u00a0€"


def test_testo_card_valore_gia_presente():
    prima = {"fatturato_iva10": 700, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}
    t = _chiama("testoCard", [{**PROPOSTA, "precedente": prima}, 2026])
    assert t["nota"] == "Risulta già 700,00\u00a0€: lo sostituisco."


def test_testo_card_fatturato_del_mese():
    t = _chiama("testoCard", [FATTURATO, 2026])
    assert t["titolo"] == "Fatturato di agosto 2026"
    assert t["totale"] == "32.500,00\u00a0€"


def test_testo_card_personale_col_lordo_precedente_e_le_voci_che_restano():
    t = _chiama("testoCard", [{**PERSONALE, "precedente": {"costo_dipendenti": 8000}}, 2026])
    assert t["titolo"] == "Costo del personale di agosto 2026"
    assert t["righe"] == [["Lordo", "12.000,00\u00a0€"]]
    assert t["totale"] is None
    assert t["nota"] == ("Risulta già 8.000,00\u00a0€: lo sostituisco. Più 450,00\u00a0€ di ore extra "
                         "e 37,00\u00a0€ di chiamata già registrati, che restano.")
    assert _chiama("testoCard", [{**PERSONALE, "restano": None}, 2026])["nota"] is None


def test_testo_card_personale_con_la_sola_chiamata_che_resta():
    t = _chiama("testoCard", [{**PERSONALE, "costo_dipendenti": 1000,
                               "restano": {"costo_personale_chiamata": 37}}, 2026])
    assert t["righe"] == [["Lordo", "1.000,00\u00a0€"]]
    assert t["nota"] == "Più 37,00\u00a0€ di chiamata già registrati, che restano."


def test_testo_card_personale_con_le_tre_voci_dettate():
    p = {**PERSONALE, "costo_dipendenti": 7320, "costo_personale_extra": 688.5, "costo_personale_chiamata": 150,
         "restano": None, "precedente": {"costo_dipendenti": 7000, "costo_personale_extra": 200,
                                         "costo_personale_chiamata": 0}}
    t = _chiama("testoCard", [p, 2026])
    assert t["righe"] == [["Lordo", "7.320,00\u00a0€"], ["Ore extra", "688,50\u00a0€"], ["Chiamata", "150,00\u00a0€"]]
    assert t["totale"] == "8.158,50\u00a0€"
    assert t["nota"] == "Risulta già lordo 7.000,00\u00a0€ e ore extra 200,00\u00a0€: li sostituisco."


def test_testo_card_delle_sole_ore_extra_col_lordo_che_resta():
    p = {**PERSONALE, "costo_dipendenti": None, "costo_personale_extra": 688,
         "restano": {"costo_dipendenti": 7320}}
    t = _chiama("testoCard", [p, 2026])
    assert t["righe"] == [["Ore extra", "688,00\u00a0€"]]
    assert t["totale"] is None
    assert t["nota"] == "Più 7.320,00\u00a0€ di lordo già registrati, che restano."


def test_testo_card_due_voci_una_sola_gia_presente():
    p = {**PERSONALE, "costo_personale_extra": 500, "restano": None,
         "precedente": {"costo_dipendenti": 0, "costo_personale_extra": 300}}
    assert _chiama("testoCard", [p, 2026])["nota"] == "Risulta già ore extra 300,00\u00a0€: lo sostituisco."


def test_senza_nome_della_sede_niente_riga_vuota():
    assert _chiama("testoCard", [{**PROPOSTA, "sede_nome": "  "}, 2026])["sede"] is None


# ─── Com'e' andata la Conferma ────────────────────────────────────────────────
def _esito(status, data, card=None):
    return _chiama("esitoConferma", [status, data, card or _card()])


def test_conferma_riuscita():
    out = _esito(200, {"ok": True})
    assert (out["stato"], out["messaggio"]) == ("registrata", "Registrato.")


def test_valore_cambiato_mostra_il_nuovo_e_chiede_una_conferma_nuova():
    attuale = {"fatturato_iva10": 900, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}
    out = _esito(409, {"detail": {"motivo": "valore_cambiato", "attuale": attuale}})
    assert out["stato"] == "cambiata"
    assert out["proposta"]["precedente"] == attuale
    assert "premi di nuovo Conferma" in out["messaggio"]
    assert _chiama("confermabile", [out]) is True


@pytest.mark.parametrize("proposta,attuale", [
    (PROPOSTA, {"fatturato_iva10": 1800, "altri_ricavi_noiva": 540, "fatturato_iva22": 0}),
    (PROPOSTA, {"fatturato_iva10": 1800.004, "altri_ricavi_noiva": 540, "fatturato_iva22": 0}),
    (PERSONALE, {"costo_dipendenti": 12000}),
    ({**PERSONALE, "costo_personale_extra": 500}, {"costo_dipendenti": 12000, "costo_personale_extra": 500}),
], ids=["incasso", "al-centesimo", "personale", "personale-due-voci"])
def test_conferma_ripetuta_e_registrata(proposta, attuale):
    """La seconda Conferma della stessa cifra (pagina ricaricata, risposta persa,
    scheda duplicata): il server dice 409 col valore uguale al dettato. Non e'
    «cambiato»: e' gia' registrato."""
    out = _esito(409, {"detail": {"motivo": "valore_cambiato", "attuale": attuale}}, _card(proposta))
    assert (out["stato"], out["messaggio"]) == ("registrata", "Registrato.")


@pytest.mark.parametrize("proposta,attuale", [
    (PROPOSTA, {"fatturato_iva10": 1800, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}),
    (PROPOSTA, {"fatturato_iva10": 1800, "altri_ricavi_noiva": 540, "fatturato_iva22": 10}),
    (PERSONALE, {"costo_dipendenti": 8000}),
    ({**PERSONALE, "costo_personale_extra": 500}, {"costo_dipendenti": 12000, "costo_personale_extra": 0}),
], ids=["senza-iva-diverso", "22-diverso", "personale-diverso", "personale-seconda-voce-diversa"])
def test_uguale_solo_in_parte_resta_cambiato(proposta, attuale):
    out = _esito(409, {"detail": {"motivo": "valore_cambiato", "attuale": attuale}}, _card(proposta))
    assert out["stato"] == "cambiata"


def test_valore_tolto_nel_frattempo():
    card = _card(proposta={**PROPOSTA, "precedente": {"fatturato_iva10": 700}})
    out = _esito(409, {"detail": {"motivo": "valore_cambiato", "attuale": None}}, card)
    assert out["stato"] == "cambiata" and out["proposta"]["precedente"] is None
    assert "è stato tolto" in out["messaggio"]


@pytest.mark.parametrize("motivo,testo", [
    ("mese_a_totale", "tenuto come totale del mese"),
    ("mese_con_giorni", "già gli incassi giorno per giorno"),
])
def test_mese_tenuto_in_altro_modo_errore_leggibile(motivo, testo):
    """Due card sullo stesso mese (giorno + mese intero): la seconda Conferma e'
    per forza 409 — il cliente deve capire perche'."""
    out = _esito(409, {"detail": {"motivo": motivo, "attuale": None}})
    assert out["stato"] == "errore" and testo in out["messaggio"]
    assert _chiama("confermabile", [out]) is False


def test_400_mostra_il_motivo_del_server():
    """La card preparata al limite dei 60 giorni e confermata dopo mezzanotte."""
    out = _esito(400, {"detail": "Data troppo lontana: usa Movimenti"})
    assert (out["stato"], out["messaggio"]) == ("errore", "Non registrato. Data troppo lontana: usa Movimenti.")


@pytest.mark.parametrize("status,stato,testo", [
    (404, "errore", "non è più disponibile"),
    (403, "errore", "non hai il permesso"),
    (401, "attesa", "sessione è scaduta"),
    (502, "attesa", "Riprova tra poco"),
    (0, "attesa", "Riprova tra poco"),
    (409, "attesa", "Riprova tra poco"),
])
def test_altri_esiti(status, stato, testo):
    out = _esito(status, {"detail": "x"} if status != 409 else {"detail": {"motivo": "boh"}})
    assert out["stato"] == stato and testo in out["messaggio"]


def test_409_con_attuale_malformato_non_diventa_la_nuova_card():
    out = _esito(409, {"detail": {"motivo": "valore_cambiato", "attuale": {"fatturato_iva10": "x"}}})
    assert out["stato"] == "attesa" and out["proposta"]["precedente"] is None


def test_esito_con_corpo_non_json():
    assert _esito(500, None)["stato"] == "attesa"


@pytest.mark.parametrize("stato,atteso", [
    ("attesa", True), ("cambiata", True), ("invio", False),
    ("registrata", False), ("annullata", False), ("errore", False),
])
def test_confermabile(stato, atteso):
    assert _chiama("confermabile", [_card(stato=stato)]) is atteso


def test_con_card_tocca_solo_quella_card():
    voci = [{"role": "assistant", "content": "A", "vista": "v", "card": [_card(), {**_card(), "id": "1-1"}]},
            {"role": "user", "content": "U", "vista": "v"}]
    out = esegui_ts(MODULO, 'emit(m.conCard(input, "1-1", (c) => ({...c, stato: "annullata"})));',
                    argomento=voci, richiede=["conCard"])
    assert [c["stato"] for c in out[0]["card"]] == ["attesa", "annullata"]
    assert out[1] == voci[1]
    assert _chiama("trovaCard", [voci, "1-1"])["id"] == "1-1"
    assert _chiama("trovaCard", [voci, "9-9"]) is None


# ─── Bozze al fornitore spente (Mattia, 3/10/2026) ───────────────────────────
# Il worker non le manda piu'. Una conversazione salvata prima puo' ancora
# portarle in sessionStorage: si scartano, non arrivano a schermo ne' al worker.

BOZZA = {"fornitore": "ITTICA MARINA SRL", "sede_nome": "NAVIGLI", "periodo": "feb–ago 2026",
         "testo": "Gentile Ittica Marina Srl,\n\nanalizzando i miei acquisti..."}


def test_una_bozza_salvata_prima_si_scarta():
    import json
    voci = [{"role": "assistant", "content": "Ecco", "vista": "sede:r-1", "bozze": [BOZZA]}]
    assert _chiama("parseConversazione", [json.dumps(voci)]) == \
        [{"role": "assistant", "content": "Ecco", "vista": "sede:r-1"}]


def test_al_worker_non_va_la_bozza():
    voci = [{"role": "assistant", "content": "Ecco", "vista": "sede:r-1", "bozze": [BOZZA]}]
    assert _chiama("codaPerVista", [voci, {"chiave": "sede:r-1", "contesto": "sede"}]) == \
        [{"role": "assistant", "content": "Ecco"}]


# ─── Fase D2: parita' worker → client → worker ────────────────────────────────
def test_personale_a_tre_voci_dal_worker_al_client_e_ritorno():
    """La proposta vera del worker (voci dettate + `restano`) passa dal client e la
    Conferma che ne esce rivalida alle stesse voci: `restano` non diventa dettato."""
    from datetime import date

    from services.routers import assistente as A

    class _Sb:
        def table(self, _):
            return self

        def select(self, _):
            return self

        def eq(self, *_):
            return self

        def limit(self, _):
            return self

        def execute(self):
            return type("R", (), {"data": [{"id": 1, "costo_dipendenti": 7320, "costo_personale_extra": 0,
                                            "costo_personale_chiamata": 37}]})()

    proposta, _ = A._proponi_personale({"anno": 2026, "mese": 9, "ore_extra": 688}, _Sb(), "r-1", "X",
                                       date(2026, 10, 4))
    p = proposta.model_dump()
    assert _chiama("propostaValida", [p]) is True
    corpo = _chiama("corpoConferma", [p])
    assert A.valida_personale(A.RegistraRequest(**corpo)) == {"costo_personale_extra": 688.0}
    t = _chiama("testoCard", [p, 2026])
    assert t["righe"] == [["Ore extra", "688,00 €"]]
    assert "7.320,00 € di lordo e 37,00 € di chiamata" in t["nota"]


def test_la_conferma_del_personale_dichiara_sempre_le_tre_voci():
    """Anche se la proposta arriva senza le chiavi (sessionStorage, serializzazione
    diversa): il server rifiuta il corpo che non le ha."""
    p = {k: v for k, v in PERSONALE.items() if k not in ("costo_personale_extra", "costo_personale_chiamata")}
    out = _chiama("corpoConferma", [p])
    assert (out["costo_dipendenti"], out["costo_personale_extra"], out["costo_personale_chiamata"]) == (12000, None, None)
    incasso = _chiama("corpoConferma", [{k: v for k, v in PROPOSTA.items() if not k.startswith("costo_")}])
    assert not any(k.startswith("costo_") for k in incasso)


# ─── Fase F (8/10/2026): domande proposte dal briefing ───────────────────────
# Mattia, screen 8: «le domande sotto proposte non sono coerenti con il contesto
# del briefing». Il worker dice di quali temi ha parlato (`BriefingResponse.temi`)
# e la Home ne fa le domande; i posti liberi restano alle domande fisse.

FISSE_PV = ["Qual è il mio food cost?", "Cosa devo pagare?", "Com'è andato il MOL?",
            "Chi è il mio fornitore più caro?"]


def _domande(temi, settore="ristorazione", registra=True):
    return _chiama("domandeDalBriefing", [temi, settore, {"registra": registra}])


def test_senza_temi_le_domande_di_sempre():
    assert _domande([]) == FISSE_PV
    assert _domande(None) == FISSE_PV


def test_le_domande_seguono_l_ordine_del_briefing():
    out = _domande(["buona_notizia:incasso_ieri", "mese_chiuso", "appuntamento_imminente"])
    assert out == ["Com'è andato l'incasso del mese finora?",
                   "Quali categorie hanno pesato di più il mese scorso?",
                   "Che appuntamenti ho oggi?",
                   "Qual è il mio food cost?"]


def test_una_domanda_gia_fra_le_fisse_non_si_ripete():
    out = _domande(["scadenza_superata", "scadenza_imminente"])
    assert out == ["Cosa devo pagare?", "Qual è il mio food cost?", "Com'è andato il MOL?",
                   "Chi è il mio fornitore più caro?"]


def test_al_massimo_quattro():
    temi = ["buona_notizia:mol_mese", "mese_chiuso", "coperti_anomalia",
            "appuntamento_imminente", "scadenza_superata"]
    assert _domande(temi) == ["Come si è chiuso il mese scorso?",
                              "Quali categorie hanno pesato di più il mese scorso?",
                              "Come vanno i coperti questo mese?",
                              "Che appuntamenti ho oggi?"]


def test_i_temi_senza_domanda_si_saltano():
    """Senza uno strumento che risponda, niente domanda."""
    assert _domande(["uncategorized_rows", "fatture_mancanti", "upload_failed"]) == FISSE_PV


def test_rincari_e_ribassi_con_lo_strumento_degli_avvisi():
    """Tolte il 8/10 finche' nessuno strumento elencava gli avvisi prezzi
    (revisore); tornate con `avvisi_prezzi`."""
    assert _domande(["prezzo_sceso", "price_alert"])[:2] == [
        "Quali prezzi sono scesi di recente?", "Quali prodotti sono rincarati di più?"]


def test_registrare_solo_dove_c_e_la_conferma():
    """Una vista che non mostra le card «Conferma» non propone «Voglio
    inserire…»: l'assistente non saprebbe registrarlo."""
    temi = ["costo_personale_mancante", "fatturato_mancante", "incasso_mancante"]
    assert _domande(temi, registra=True)[:3] == [
        "Voglio inserire il costo del personale",
        "Voglio inserire il fatturato del mese scorso",
        "Voglio inserire l'incasso di ieri"]
    assert _domande(temi, registra=False) == FISSE_PV


def test_i_negozi_riempiono_con_le_loro_fisse():
    out = _domande(["scadenza_superata"], settore="retail")
    assert out == ["Cosa devo pagare?", "Qual è il mio costo merce?", "Com'è andato il MOL?",
                   "Chi è il mio fornitore più caro?"]


def test_ogni_tema_della_tabella_esiste_nel_worker():
    """Un refuso nella chiave e la domanda non compare mai, in silenzio."""
    import services.daily_briefing_service as dbs
    chiavi = esegui_ts(MODULO, "emit([...Object.keys(m.DOMANDE_PER_TEMA), ...Object.keys(m.DOMANDE_PER_REGISTRARE)]);")
    assert len(chiavi) >= 16
    tipi_buona = {"mol_mese", "perdita_in_calo", "incasso_ieri", "fatture_arrivate"}
    for k in chiavi:
        if k.startswith("buona_notizia:"):
            assert k.split(":", 1)[1] in tipi_buona, k
        else:
            assert k in dbs._TOPIC_PRIORITY, k


# ─── Il corpo di POST /api/chat (fase I: la chat del telefono) ───────────────

def _corpo(voci, vista, mobile=None):
    args = [voci, vista] if mobile is None else [voci, vista, mobile]
    return _chiama("corpoRichiestaChat", args)


_VOCI_SEDE = [
    {"role": "user", "content": "ciao", "vista": "sede:r-1"},
    {"role": "assistant", "content": "salve", "vista": "sede:r-1"},
    {"role": "user", "content": "altro locale", "vista": "sede:r-2"},
]
_SEDE = {"chiave": "sede:r-1", "contesto": "sede"}


def test_corpo_desktop_resta_quello_di_prima():
    """Dalla Home il corpo e' esattamente { messages, contesto, card_conferma }:
    niente chiave `mobile`, nemmeno a false."""
    assert _corpo(_VOCI_SEDE, _SEDE) == {
        "messages": [{"role": "user", "content": "ciao"}, {"role": "assistant", "content": "salve"}],
        "contesto": "sede",
        "card_conferma": True,
    }
    assert "mobile" not in _corpo(_VOCI_SEDE, _SEDE, False)


def test_corpo_telefono_dice_di_essere_il_telefono():
    out = _corpo(_VOCI_SEDE, _SEDE, True)
    assert out["mobile"] is True and out["card_conferma"] is True


def test_corpo_porta_solo_i_messaggi_della_vista():
    out = _corpo(_VOCI_SEDE, {"chiave": "sede:r-2", "contesto": "sede"}, True)
    assert out["messages"] == [{"role": "user", "content": "altro locale"}]


def test_corpo_catena_ha_il_contesto_catena():
    voci = [{"role": "user", "content": "margini?", "vista": "catena"}]
    out = _corpo(voci, {"chiave": "catena", "contesto": "catena"}, True)
    assert out["contesto"] == "catena" and out["messages"] == [{"role": "user", "content": "margini?"}]
