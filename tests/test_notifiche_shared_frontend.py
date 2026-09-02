"""Notifiche condivise (`lib/notifiche-shared.ts`) — ordinamento, CTA, testo.

Perche' esiste, e perche' solo ora: queste funzioni erano gia' pure, ma vivevano
in `app/(app)/notifiche/`, fuori dalla portata dell'harness (che risolve solo
l'alias @/ dentro lib/). Spostarle non e' bastato: importavano il tipo da
`lib/notifiche.ts`, che a sua volta importa `./worker-config` con path relativo
— e un import di SOLO TIPO basta a rendere un modulo non eseguibile sotto node.
La dipendenza e' stata invertita (il tipo vive nel modulo puro, il modulo con le
fetch lo ri-esporta).

Le usano due pagine: il widget della Home e la pagina /notifiche.
"""

from tests.helpers_ts import esegui_ts

MODULO = "lib/notifiche-shared"


def _chiama(fn, args, richiede=None):
    return esegui_ts(MODULO, f"emit(m.{fn}(...input));", argomento=args, richiede=richiede or [fn])


def _n(id_, severity="info", source="upload", created="2026-09-01T10:00:00Z", page=None):
    return {
        "id": id_, "topic_key": None, "source_type": source, "severity": severity,
        "title": f"t{id_}", "body": None, "action_page": page,
        "dismissed_at": None, "expires_at": None, "created_at": created,
    }


# ─── raggruppa: severity prima, poi la data ───────────────────────────────

def test_gruppi_ordinati_come_GRUPPO_ORDINE_non_come_arrivano():
    """Le scadenze vengono prima degli upload anche se arrivano dopo."""
    out = _chiama("raggruppa", [[_n("a", source="upload"), _n("b", source="scadenza")]])
    assert [g["key"] for g in out] == ["scadenza", "upload"]


def test_dentro_un_gruppo_vince_la_severity():
    out = _chiama("raggruppa", [[
        _n("info", severity="info"),
        _n("err", severity="error"),
        _n("warn", severity="warning"),
        _n("ok", severity="success"),
    ]])
    assert [n["id"] for n in out[0]["notifiche"]] == ["err", "warn", "info", "ok"]


def test_a_parita_di_severity_la_piu_recente_e_prima():
    out = _chiama("raggruppa", [[
        _n("vecchia", created="2026-08-01T10:00:00Z"),
        _n("nuova", created="2026-09-01T10:00:00Z"),
    ]])
    assert [n["id"] for n in out[0]["notifiche"]] == ["nuova", "vecchia"]


def test_created_at_nullo_non_rompe_l_ordinamento():
    """`?? ""` sui due lati: una data mancante finisce in fondo, non lancia."""
    out = _chiama("raggruppa", [[_n("senza", created=None), _n("con")]])
    assert [n["id"] for n in out[0]["notifiche"]] == ["con", "senza"]


def test_source_sconosciuto_finisce_in_Altro():
    out = _chiama("raggruppa", [[_n("x", source="qualcosa_di_nuovo")]])
    assert out[0]["key"] == "altro"


def test_source_case_insensitive():
    out = _chiama("raggruppa", [[_n("x", source="UPLOAD")]])
    assert out[0]["key"] == "upload"


def test_scadenziario_e_scadenza_finiscono_nello_stesso_gruppo():
    """Due source_type diversi dal backend, una sola voce per l'utente."""
    out = _chiama("raggruppa", [[_n("a", source="scadenza"), _n("b", source="scadenziario")]])
    assert len(out) == 1 and len(out[0]["notifiche"]) == 2


def test_lista_vuota():
    assert _chiama("raggruppa", [[]]) == []


# ─── ctaDi: le rotte legacy di Streamlit sopravvivono nei dati ────────────

def test_cta_assente_quando_non_c_e_pagina():
    assert _chiama("ctaDi", [_n("x", page=None)]) is None
    assert _chiama("ctaDi", [_n("x", page="   ")]) is None


def test_cta_rotta_next_passa_intera():
    assert _chiama("ctaDi", [_n("x", page="/margini")])["href"] == "/margini"


def test_cta_traduce_una_rotta_streamlit_legacy():
    """Streamlit e' stato rimosso dal repo, ma i suoi path sono ancora nelle
    notifiche vecchie a DB: senza la mappa il pulsante non porterebbe da
    nessuna parte."""
    assert _chiama("ctaDi", [_n("x", page="pages/3_controllo_prezzi.py")])["href"] == "/prezzi"


def test_cta_legacy_case_insensitive():
    assert _chiama("ctaDi", [_n("x", page="Dashboard")])["href"] == "/dashboard"


def test_cta_rotta_sconosciuta_non_produce_un_link_rotto():
    """Meglio nessun pulsante che un pulsante che porta a un 404."""
    assert _chiama("ctaDi", [_n("x", page="pages/99_inesistente.py")]) is None


# ─── il difetto del 2/9: action_page non e' solo un path Streamlit ───────────

def test_cta_Agenda_porta_dove_si_inserisce_l_incasso():
    """LA REGRESSIONE, e la sua correzione dopo la review.

    Misurato a DB il 2/9/2026: 33 righe con `action_page='Agenda'` (topic
    `incasso_mancante`), di cui **3 ancora visibili su 2 utenti** una volta
    applicato `expires_at` come fa il frontend (le altre sono scadute). La mappa
    conosceva solo path Streamlit (`pages/*.py`), non i NOMI di pagina: `ctaDi`
    tornava None e la notifica "Manca l'incasso di ieri" non aveva il pulsante.

    **La destinazione NON e' /agenda**, ed e' l'errore che la prima stesura di
    questo fix aveva commesso: gli incassi sono stati spostati fuori dall'Agenda
    (desktop Margini -> Calcolo, mobile "Movimenti"). `/agenda` non contiene la
    stringa "incass": il pulsante ci sarebbe stato, ma non avrebbe fatto fare la
    cosa chiesta. `/margini` e' anche cio' che il briefing usa gia' per questo
    topic e cio' che scrive la versione live della notifica nel worker.

    I test c'erano gia' (`pages/99_inesistente.py`) ma erano scritti guardando
    la mappa, non i dati: nessuno usava un valore presente nel DB.
    """
    assert _chiama("ctaDi", [_n("x", page="Agenda")])["href"] == "/margini"


def test_cta_nomi_di_pagina_storici():
    """Restano nelle notifiche vecchie a DB.

    Censimento completo (`grep action_page` su services/, config/, worker/,
    scripts/): i NOMI di pagina non sono due, sono sette, tutti in
    `upload_handler.py:2051-2145` (percorso Streamlit) piu' quello di
    `scadenziario.py`. Questi due hanno una destinazione univoca; 'Carica
    Fatture' e 'Gestione e Pagamenti' no, e restano senza pulsante."""
    assert _chiama("ctaDi", [_n("x", page="Analisi Margine")])["href"] == "/margini"
    assert _chiama("ctaDi", [_n("x", page="Analisi Fatture")])["href"] == "/analisi-fatture"


def test_cta_senza_destinazione_univoca_resta_senza_pulsante():
    """Meglio nessun pulsante di un 404. `/documenti` non esiste fra le rotte di
    `app/(app)/`; 'Carica Fatture' e 'Gestione e Pagamenti' (`upload_handler.py`)
    non hanno una pagina Next corrispondente."""
    assert _chiama("ctaDi", [_n("x", page="Vai ai Documenti")]) is None
    assert _chiama("ctaDi", [_n("x", page="Carica Fatture")]) is None
    assert _chiama("ctaDi", [_n("x", page="Gestione e Pagamenti")]) is None


# ─── pulisci: markdown grezzo -> testo ────────────────────────────────────

def test_pulisci_grassetto_e_corsivo():
    assert _chiama("pulisci", ["**Attenzione**: prezzo *alto*"]) == "Attenzione: prezzo alto"


def test_pulisci_br_diventa_a_capo():
    assert _chiama("pulisci", ["riga1<br>riga2<br />riga3"]) == "riga1\nriga2\nriga3"


def test_pulisci_backtick_spariscono():
    assert _chiama("pulisci", ["il campo `totale`"]) == "il campo totale"


def test_pulisci_trimma():
    assert _chiama("pulisci", ["  testo  "]) == "testo"


def test_pulisci_testo_gia_pulito_non_cambia():
    assert _chiama("pulisci", ["Prezzo aumentato del 12%"]) == "Prezzo aumentato del 12%"


def test_pulisci_DUE_grassetti_nella_stessa_riga():
    """Il quantificatore e' lazy (`.+?`) e deve restarlo.

    Con `.+` greedy il match parte dal primo `**` e arriva all'ULTIMO: due
    coppie diventano una sola, e gli asterischi centrali restano a schermo
    ("**a** e **b**" -> "a** e **b"). Trovato da un mutante sopravvissuto:
    tutti i casi che avevo scritto avevano una coppia sola, dove greedy e lazy
    coincidono.
    """
    assert _chiama("pulisci", ["**a** e **b**"]) == "a e b"


def test_pulisci_asterisco_singolo_non_accoppiato_resta():
    """Il regex vuole una coppia: un asterisco solo non e' markup."""
    assert _chiama("pulisci", ["2 * 3 = 6"]) == "2 * 3 = 6"


# ─── filtri per severity (estratti da notifiche-list.tsx il 2/9) ─────────────
# Erano dentro tre `useMemo` del componente: pure, ma irraggiungibili
# dall'harness. Il comportamento e' stato congelato per oracolo (2.340 casi,
# 0 divergenze) PRIMA di spostarle, e l'oracolo validato sui due lati
# (success->warning: 740 divergenze; info senza success: 185).

def _conta(notifiche):
    return esegui_ts(
        MODULO, "emit(m.contaPerFiltro(input));",
        argomento=notifiche, richiede=["contaPerFiltro"],
    )


def _filtra(notifiche, filtro):
    return esegui_ts(
        MODULO, "emit(m.filtraPerSeverity(input[0], input[1]).map(n => n.id));",
        argomento=[notifiche, filtro], richiede=["filtraPerSeverity"],
    )


def _visibili(notifiche, dismessi):
    return esegui_ts(
        MODULO, "emit(m.visibili(input[0], new Set(input[1])).map(n => n.id));",
        argomento=[notifiche, dismessi], richiede=["visibili"],
    )


def test_conta_insieme_vuoto():
    assert _conta([]) == {"tutte": 0, "error": 0, "warning": 0, "info": 0}


def test_conta_una_per_severity():
    n = [_n("a", "error"), _n("b", "warning"), _n("c", "info")]
    assert _conta(n) == {"tutte": 3, "error": 1, "warning": 1, "info": 1}


def test_success_e_contato_insieme_a_info():
    """"Informazioni" e' UNA voce di menu per DUE severity: un avviso positivo
    non merita una categoria propria. Non e' una svista.

    Congelato apposta: `success` non esiste nei dati veri (misurato il 2/9 su
    `notification_inbox`: solo warning/info/error), quindi questo ramo non e'
    mai stato esercitato dalla produzione e nessun dato lo proteggerebbe."""
    assert _conta([_n("a", "success"), _n("b", "info")])["info"] == 2


def test_conta_tutte_e_il_totale_non_la_somma_dei_filtri():
    n = [_n("a", "error"), _n("b", "success")]
    c = _conta(n)
    assert c["tutte"] == 2
    assert c["error"] + c["warning"] + c["info"] == 2


def test_filtro_tutte_non_toglie_niente():
    n = [_n("a", "error"), _n("b", "info")]
    assert _filtra(n, "tutte") == ["a", "b"]


def test_filtro_info_include_anche_success():
    """Deve restare allineato a contaPerFiltro: se divergessero, il contatore
    direbbe un numero e la lista ne mostrerebbe un altro."""
    n = [_n("a", "info"), _n("b", "success"), _n("c", "warning")]
    assert _filtra(n, "info") == ["a", "b"]


def test_filtro_secco_su_error_e_warning():
    n = [_n("a", "error"), _n("b", "warning"), _n("c", "info")]
    assert _filtra(n, "error") == ["a"]
    assert _filtra(n, "warning") == ["b"]


def test_filtro_conserva_l_ordine_in_ingresso():
    """L'ordinamento e' compito di `raggruppa`, che gira DOPO: se il filtro
    riordinasse, il raggruppamento partirebbe da una lista diversa."""
    n = [_n("c", "info"), _n("a", "info"), _n("b", "info")]
    assert _filtra(n, "info") == ["c", "a", "b"]


def test_visibili_toglie_gli_archiviati_in_sessione():
    n = [_n("a"), _n("b"), _n("c")]
    assert _visibili(n, ["b"]) == ["a", "c"]


def test_visibili_senza_archiviati_non_tocca_niente():
    n = [_n("a"), _n("b")]
    assert _visibili(n, []) == ["a", "b"]


def test_visibili_puo_svuotare_tutto():
    """Il componente mostra lo stato "Tutto archiviato" quando resta zero."""
    assert _visibili([_n("a")], ["a"]) == []


# ─── CTA sul mobile: la PWA non ha le stesse pagine del desktop ──────────────
# `hideCta` spegneva TUTTE le CTA sul mobile, perche' portavano a viste
# desktop. Ma `incasso_mancante` NASCE sul mobile (`m/incasso-reminder.tsx`):
# l'avviso arrivava sul telefono senza modo di agire. Ora la CTA compare quando
# — e solo quando — la destinazione esiste anche nella PWA.

def _cta_mobile(page, topic="incasso_mancante"):
    n = _n("x", page=page)
    n["topic_key"] = topic
    return esegui_ts(
        MODULO, "emit(m.ctaMobile(input));", argomento=n, richiede=["ctaMobile"],
    )


def test_incasso_porta_ai_movimenti_del_mobile():
    """LA CTA che mancava sul telefono. /m/turni e' la sezione "Movimenti"
    (ex Turni) e il suo tab di default e' proprio "Incassi"
    (`mobile-turni.tsx`): l'utente atterra dove deve inserire il dato."""
    assert _cta_mobile("/margini")["href"] == "/m/turni"


def test_incasso_dal_valore_storico_a_DB_arriva_comunque():
    """Le righe gia' scritte hanno action_page='Agenda': devono passare per la
    mappa legacy PRIMA di quella mobile, o sul telefono resterebbero mute."""
    assert _cta_mobile("Agenda")["href"] == "/m/turni"


def test_si_mappa_il_topic_non_il_path():
    """LA CORREZIONE dopo la seconda review. Su `/margini` desktop confluiscono
    almeno 6 topic: mappare il PATH li avrebbe mandati tutti su /m/turni, e per
    due sarebbe stato un pulsante che non fa fare la cosa chiesta —

    - `fatturato_mancante` e' il totale MENSILE, read-only su mobile
      ("Totale mensile inserito da desktop", `mobile-incassi.tsx`);
    - `coperti_anomalia` punta al tab `coperti`, che sul mobile non esiste
      (zero occorrenze di "coperti" in `(mobile)/m/`).

    Stessa classe dell'errore `/agenda`: destinazione dedotta invece che
    cercata. Qui i due casi restano senza pulsante, com'e' giusto."""
    assert _cta_mobile("/margini", topic="fatturato_mancante") is None
    assert _cta_mobile("/margini?tab=coperti", topic="coperti_anomalia") is None
    assert _cta_mobile("/margini", topic="costo_personale_mancante") is None
    assert _cta_mobile("/margini", topic="upload_ricavi_failed") is None
    assert _cta_mobile("/margini", topic="buona_notizia") is None


def test_destinazioni_senza_equivalente_mobile_non_hanno_pulsante():
    """La PWA ha 6 sezioni, il desktop molte di piu'. Per prezzi, fatture e
    scadenzario non esiste una pagina mobile: meglio nessun pulsante di uno che
    butta l'utente fuori dall'app (e' il motivo per cui `hideCta` esiste)."""
    assert _cta_mobile("/prezzi", topic="price_alert") is None
    assert _cta_mobile("/analisi-fatture", topic="fatture_mancanti") is None
    assert _cta_mobile("/scadenziario", topic="scadenza_imminente") is None


def test_topic_giusto_ma_senza_cta_desktop_resta_muto():
    """Passa da `ctaDi`: se la CTA desktop non esiste, non deve esistere
    nemmeno quella mobile (niente pulsante inventato dal nulla)."""
    assert _cta_mobile(None) is None
    assert _cta_mobile("Vai ai Documenti") is None


def test_senza_topic_niente_cta_mobile():
    """`topic_key` e' nullable nel tipo: non deve far esplodere il lookup."""
    assert _cta_mobile("/margini", topic=None) is None
