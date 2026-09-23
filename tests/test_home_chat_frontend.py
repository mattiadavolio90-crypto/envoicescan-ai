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
