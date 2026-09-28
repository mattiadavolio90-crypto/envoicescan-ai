"""Chat della Home (`lib/home-chat.ts`).

Perche' esiste: due di queste funzioni proteggono da guasti che l'utente non
puo' aggirare da solo.

`parseStorico` legge sessionStorage, cioe' contenuto fuori dal nostro controllo:
se lancia, la chat non si apre piu' e non c'e' modo di ripulirla dall'interfaccia.
`codaDaInviare` tronca la conversazione a 16 messaggi perche' il backend ne
accetta 20 (ChatRequest.max_length): senza, dopo ~20 scambi ogni invio falliva
con 422 e un errore generico.
"""

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


def test_errore_generico_usa_error_se_c_e():
    assert _chiama("messaggioRisposta", [500, {"error": "boom"}]) == "boom"
    assert "errore" in _chiama("messaggioRisposta", [500, {}]).lower()


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
    """`/m/chat` deve CHIAMARE `messaggioRisposta`, non duplicarla.

    Fino al 23/09/2026 `mobile-chat.tsx` aveva la stessa catena di `if`
    ricopiata a mano, identica riga per riga. Due copie della stessa decisione
    di cui l'harness ne esegue **una sola**: quando il messaggio del 429 e'
    stato corretto perche' diceva il falso, la copia mobile e' rimasta indietro
    e nessun test se ne e' accorto (il reviewer l'ha ucciso con un mutante che
    sopravviveva).

    Il presidio guarda la FORMA del .tsx perche' l'harness non esegue i
    componenti: e' un limite dichiarato, non una svista. Uccide il mutante
    realistico — reintrodurre la copia — e la logica vera resta provata dai
    test di `messaggioRisposta` qui sopra, che la eseguono.
    """
    from pathlib import Path

    sorgente = Path("apps/web/src/app/(mobile)/m/chat/mobile-chat.tsx").read_text(
        encoding="utf-8"
    )

    assert "messaggioRisposta" in sorgente, (
        "la chat mobile non chiama messaggioRisposta: se ha ricopiato la "
        "decisione, il prossimo messaggio corretto restera' sbagliato qui"
    )
    assert 'from "@/lib/home-chat"' in sorgente, (
        "messaggioRisposta deve arrivare da lib/home-chat, l'unica copia "
        "eseguita dai test"
    )
    for testo in ("Hai raggiunto il limite di domande",
                  "La chat non è disponibile nel tuo piano"):
        assert testo not in sorgente, (
            f"il .tsx contiene ancora il testo {testo!r}: e' una seconda copia "
            "del messaggio, e vivrebbe fuori dalla portata dei test"
        )


# ─── quotaEsaurita: giorno o mese, non «un 429 generico» ──────────────────

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


def _vs(id_="r1", nome="CASATI 14"):
    return _chiama("vistaSede", [id_, nome])


def _vc(nome="SUSHILAND"):
    return _chiama("vistaCatena", [nome])


def _u(testo, vista):
    return {"role": "user", "content": testo, "vista": vista}


def _a(testo, vista):
    return {"role": "assistant", "content": testo, "vista": vista}


def test_la_vista_di_una_sede_e_diversa_da_quella_di_un_altra():
    a, b = _vs("r1", "A"), _vs("r2", "B")
    assert a["chiave"] != b["chiave"]
    assert a["contesto"] == b["contesto"] == "sede"
    assert a["frase"] == "Ora sei in A"


def test_la_vista_catena():
    v = _vc("SUSHILAND")
    assert v == {"chiave": "catena", "contesto": "catena", "frase": "Ora sei nella vista catena del gruppo SUSHILAND"}


def test_nomi_assenti_non_lasciano_frasi_rotte():
    assert _vs("r1", None)["frase"] == "Ora sei nel tuo locale"
    assert _vs("r1", "   ")["frase"] == "Ora sei nel tuo locale"
    assert _vc(None)["frase"] == "Ora sei nella vista catena"


def test_la_conversazione_salvata_scarta_le_voci_senza_vista():
    """Il formato del vecchio pulsante non diceva a quale locale apparteneva."""
    grezzo = (
        '[{"role":"user","content":"vecchia"},'
        '{"role":"user","content":"ok","vista":"catena"},'
        '{"role":"vista","content":"Ora sei in A","vista":"sede:r1"},'
        '{"role":"assistant","content":"x","vista":""},'
        '{"role":"hacker","content":"x","vista":"catena"},'
        'null]'
    )
    out = _chiama("parseConversazione", [grezzo])
    assert [v["content"] for v in out] == ["ok", "Ora sei in A"]


def test_la_conversazione_salvata_non_lancia_mai():
    for raw in [None, "", "{rotto", "42", "null", '{"a":1}']:
        assert _chiama("parseConversazione", [raw]) == []


def test_si_salvano_solo_le_ultime_voci():
    voci = [_u(f"m{i}", "catena") for i in range(250)]
    out = _chiama("daSalvare", [voci])
    assert len(out) == 200
    assert out[0]["content"] == "m50" and out[-1]["content"] == "m249"


def test_in_una_conversazione_vuota_niente_riga_ora_sei_in():
    assert _chiama("entraInVista", [[], _vc()]) == []


def test_nella_stessa_vista_niente_riga():
    voci = [_u("q", "catena"), _a("r", "catena")]
    assert _chiama("entraInVista", [voci, _vc()]) == voci


def test_cambiando_vista_compare_la_riga():
    voci = [_u("q", "catena"), _a("r", "catena")]
    out = _chiama("entraInVista", [voci, _vs("r1", "CASATI 14")])
    assert out[-1] == {"role": "vista", "content": "Ora sei in CASATI 14", "vista": "sede:r1"}
    assert out[:-1] == voci


def test_due_cambi_di_fila_lasciano_una_riga_sola():
    voci = [_u("q", "catena"), {"role": "vista", "content": "Ora sei in A", "vista": "sede:r1"}]
    out = _chiama("entraInVista", [voci, _vs("r2", "B")])
    assert [v["content"] for v in out] == ["q", "Ora sei in B"]


def test_tornare_dove_si_era_senza_scrivere_toglie_la_riga():
    voci = [_u("q", "catena"), {"role": "vista", "content": "Ora sei in A", "vista": "sede:r1"}]
    assert _chiama("entraInVista", [voci, _vc()]) == [_u("q", "catena")]


def test_al_backend_solo_i_messaggi_della_vista_corrente():
    """LA regressione: prima tutto lo storico, di tutte le viste."""
    voci = [
        _u("catena?", "catena"), _a("gruppo", "catena"),
        {"role": "vista", "content": "Ora sei in A", "vista": "sede:r1"},
        _u("sede?", "sede:r1"), _a("locale", "sede:r1"),
        {"role": "vista", "content": "Ora sei in B", "vista": "sede:r2"},
        _u("altra?", "sede:r2"),
    ]
    out = _chiama("codaPerVista", [voci, _vs("r1", "A")])
    assert out == [{"role": "user", "content": "sede?"}, {"role": "assistant", "content": "locale"}]


def test_al_backend_mai_le_righe_ora_sei_in_e_al_massimo_16():
    voci = [{"role": "vista", "content": "Ora sei nella vista catena", "vista": "catena"}]
    voci += [_u(f"m{i}", "catena") for i in range(20)]
    out = _chiama("codaPerVista", [voci, _vc()])
    assert len(out) == 16
    assert out[-1]["content"] == "m19"
    assert all(set(m) == {"role", "content"} for m in out)


def test_le_domande_proposte_finche_in_questa_vista_non_si_e_scritto():
    voci = [_u("q", "catena"), _a("r", "catena")]
    assert _chiama("mostraSuggerimenti", [voci, _vc()]) is False
    assert _chiama("mostraSuggerimenti", [voci, _vs()]) is True
    assert _chiama("mostraSuggerimenti", [[], _vc()]) is True


def test_la_risposta_va_sotto_la_sua_domanda_non_sotto_la_riga_del_cambio():
    """Domanda in catena, poi il cliente scende in un locale prima della risposta."""
    voci = [
        _u("q", "catena"),
        {"role": "vista", "content": "Ora sei in A", "vista": "sede:r1"},
    ]
    out = _chiama("conRisposta", [voci, "catena", "risposta"])
    assert [v["content"] for v in out] == ["q", "risposta", "Ora sei in A"]
    assert out[1] == _a("risposta", "catena")


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
