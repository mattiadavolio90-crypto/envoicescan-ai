"""Presidio: i solleciti arrivano quando il cliente puo' davvero rispondere.

Due difetti misurati sui dati di produzione (7/9/2026, 43 briefing letti):

1. COSTO PERSONALE reclamato dal 1° del mese successivo. La busta paga del
   consulente del lavoro arriva a meta' mese: 5 sedi su 5 risultavano "in
   ritardo" ad agosto e settembre — cioe' la norma, non un'anomalia.

2. INCASSO DI IERI ripetuto ogni giorno: la `dedupe_key` conteneva la data di
   ieri, quindi era nuova ogni mattina. Misurato: ignorato 25 volte su 35 (71%),
   e un cliente ha spento 4 avvisi dal configuratore.

Un assistente che sollecita cose impossibili insegna a essere ignorato. Qui si
presidia il calendario: personale dal 15, incasso una volta a settimana.

I test PINNANO la data: senza, l'esito dipenderebbe dal giorno in cui gira la
suite (verdi dal 15 in poi, rossi prima) — un presidio che si sposta da solo.
"""
import os

# Il worker rifiuta l'import senza chiave: in suite passava solo perche' un file
# lanciato prima la impostava. Da solo il file dava errore di raccolta.
os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

from datetime import date
from unittest.mock import MagicMock, patch

from services.fastapi_worker import (
    _briefing_dati_mensili_mancanti,
    _GIORNO_SOLLECITO_PERSONALE,
)

RID = "rist-xyz"


def _sb(margini_rows, incasso_ieri=True, ha_storia=True, anno=2026, mese=8):
    """Mock delle tre tabelle lette dalla funzione, con mese esplicito."""
    incasso_rows = [{"data": "2026-09-22"}] if incasso_ieri else []
    storia_rows = [{"data": "2026-05-01"}] if ha_storia else []
    margini_rows = [{**r, "mese": r.get("mese", mese)} for r in (margini_rows or [])]
    state = {"table": None, "rg": None}

    def _table(name):
        state["table"] = name
        state["rg"] = None
        return q

    def _eq(*a, **k):
        if a and a[0] == "data":
            state["rg"] = "ieri"
        return q

    def _lt(*a, **k):
        state["rg"] = "storia"
        return q

    def _execute():
        if state["table"] == "ricavi_giornalieri":
            return MagicMock(data=storia_rows if state["rg"] == "storia" else incasso_rows)
        if state["table"] == "ricavi_modalita_mensile":
            return MagicMock(data=[])
        return MagicMock(data=margini_rows)

    q = MagicMock()
    q.table.side_effect = _table
    q.select.return_value = q
    q.eq.side_effect = _eq
    q.lt.side_effect = _lt
    # Dal 25/09 la domanda «incasso di ieri» e' una finestra (gte/lte su
    # "data", larga quanto i giorni di chiusura + 1): la riconosce il lte.
    def _lte(*a, **k):
        if a and a[0] == "data":
            state["rg"] = "ieri"
        return q

    q.gte.return_value = q
    q.lte.side_effect = _lte
    q.in_.return_value = q
    q.limit.return_value = q
    q.execute.side_effect = _execute
    return q


def _oggi(giorno, mese=9, anno=2026):
    """Pinna la data vista dalla funzione.

    `_dt2` e' un'importazione LOCALE dentro _briefing_dati_mensili_mancanti
    (`from datetime import datetime as _dt2`), quindi non esiste come attributo
    del modulo: si patcha alla fonte, `datetime.datetime`.
    """
    import datetime as _dtmod

    class _FakeDateTime(_dtmod.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dtmod.datetime(anno, mese, giorno, 12, 0, tzinfo=tz)

    return patch.object(_dtmod, "datetime", _FakeDateTime)


def _righe_fatturato_senza_personale(mese=8):
    return [{
        "mese": mese,
        "fatturato_iva10": 10000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 0, "costo_personale_extra": 0,
    }]



def _sb_salute(margini_rows):
    """Mock per `_salute_indice_rosso`: legge `fatture` e `margini_mensili`.

    `_costi_automatici_mese` va patchato a parte dal test: fa una RPC che un
    MagicMock non intercetta (un uuid finto arriva fino al DB vero).
    """
    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        if state["table"] == "margini_mensili":
            return MagicMock(data=margini_rows, count=len(margini_rows))
        return MagicMock(data=[], count=0)

    q = MagicMock()
    q.table.side_effect = _table
    for m in ("select", "eq", "lt", "gte", "lte", "limit", "in_", "not_",
              "is_", "order", "neq", "range"):
        getattr(q, m).return_value = q
    q.execute.side_effect = _execute
    return q


def _topics(notifs):
    return {n["topic_key"] for n in notifs}


def test_personale_non_sollecitato_prima_del_quindici():
    """Il 3 settembre il personale di agosto non e' ancora arrivato."""
    with _oggi(3):
        out = _briefing_dati_mensili_mancanti(RID, _sb(_righe_fatturato_senza_personale()))
    assert "costo_personale_mancante" not in _topics(out), (
        "personale reclamato prima che la busta paga esista"
    )


def test_personale_sollecitato_dal_quindici():
    """Dal 15 il dato c'e': se manca, e' giusto dirlo."""
    with _oggi(_GIORNO_SOLLECITO_PERSONALE):
        out = _briefing_dati_mensili_mancanti(RID, _sb(_righe_fatturato_senza_personale()))
    assert "costo_personale_mancante" in _topics(out), (
        "il sollecito non arriva nemmeno quando il dato e' disponibile"
    )


def test_mesi_piu_vecchi_sollecitati_subito():
    """Un mese vecchio e' in ritardo davvero: non aspetta il 15.

    Senza questo, la soglia diventerebbe un modo per tacere sui buchi veri.
    """
    righe = _righe_fatturato_senza_personale(mese=6)
    with _oggi(3):
        out = _briefing_dati_mensili_mancanti(RID, _sb(righe, mese=6))
    assert "costo_personale_mancante" in _topics(out), (
        "un buco di giugno non va taciuto a settembre"
    )


def test_incasso_segnalato_una_volta_a_settimana():
    """L'avviso ESISTE un giorno e NON esiste negli altri sei.

    Si misura la presenza del topic, non la forma della `dedupe_key`: una prima
    stesura ancorava la chiave alla settimana ISO, ma `_build_snapshot`
    raggruppa per `topic_key` e la chiave finisce solo in
    `notifications_fingerprint`, che per suo stesso docstring nessuno rilegge —
    l'avviso sarebbe tornato ogni giorno esattamente come prima. Un test sulla
    chiave sarebbe stato verde su quel difetto.

    `incasso_mancante` e' in TOPIC_LIVE_NON_IGNORABILI: il cliente non puo'
    nemmeno spegnerlo, quindi l'unica misura possibile e' non emetterlo.
    """
    giorni_con_avviso = []
    # 21-27 settembre 2026: una settimana intera, lunedi -> domenica.
    for giorno in range(21, 28):
        with _oggi(giorno):
            out = _briefing_dati_mensili_mancanti(
                RID, _sb(_righe_fatturato_senza_personale(), incasso_ieri=False)
            )
        if "incasso_mancante" in _topics(out):
            giorni_con_avviso.append(giorno)
    assert len(giorni_con_avviso) == 1, (
        f"l'avviso compare {len(giorni_con_avviso)} volte a settimana: {giorni_con_avviso}"
    )


def test_incasso_torna_la_settimana_dopo():
    """Una volta a settimana, non una volta e basta: deve tornare.

    NOTA: questi test derivano il giorno da `_GIORNO_SOLLECITO_INCASSO`, quindi
    cambiarne il VALORE non li fa cadere — di proposito. La cadenza (una volta a
    settimana, e che torni) e' una regola e si presidia; QUALE giorno e' una
    scelta di prodotto, misurata sui buchi veri e motivata accanto alla
    costante. Un test che cablasse il giovedi' presidierebbe il numero, non la
    regola, e andrebbe riscritto a ogni ritaratura.
    """
    from services.fastapi_worker import _GIORNO_SOLLECITO_INCASSO

    # 14/09/2026 e' un lunedi: +offset = il giorno di emissione, +7 = quello
    # dopo. Si parte dal 14 e non dal 21 perche' con offset alti il "+7"
    # sconfinerebbe oltre il 30 settembre (un 31 settembre non esiste).
    from datetime import timedelta

    primo = date(2026, 9, 14) + timedelta(days=_GIORNO_SOLLECITO_INCASSO)
    visti = []
    for d in (primo, primo + timedelta(days=7)):
        with _oggi(d.day, d.month, d.year):
            out = _briefing_dati_mensili_mancanti(
                RID, _sb(_righe_fatturato_senza_personale(), incasso_ieri=False)
            )
        visti.append("incasso_mancante" in _topics(out))
    assert visti == [True, True], f"l'avviso non torna la settimana dopo: {visti}"


def test_incasso_presente_non_genera_avviso():
    """Il gate settimanale non deve inventare avvisi quando il dato c'e'."""
    with _oggi(21):
        out = _briefing_dati_mensili_mancanti(
            RID, _sb(_righe_fatturato_senza_personale(), incasso_ieri=True)
        )
    assert "incasso_mancante" not in _topics(out)



# ── Coerenza fra briefing, card «Completezza dati» e indice di salute ────────
# Le tre voci misurano lo stesso dato. Se solo il briefing tacesse prima del 15,
# la card direbbe «manca» mentre il briefing non ne parla — l'incoerenza che
# `home_salute` dichiara nel docstring di voler evitare. E `_salute_indice_rosso`
# e' il GATE della «buona notizia»: un rosso per un dato non ancora dovuto la
# sopprimerebbe senza motivo.

def test_regola_del_dovuto_sul_mese_appena_chiuso():
    from services.fastapi_worker import _personale_gia_dovuto as dovuto

    assert dovuto(date(2026, 9, 3), (2026, 8)) is False
    assert dovuto(date(2026, 9, _GIORNO_SOLLECITO_PERSONALE), (2026, 8)) is True
    # Mesi piu' vecchi: sempre dovuti, anche il 3 del mese.
    assert dovuto(date(2026, 9, 3), (2026, 6)) is True


def test_regola_del_dovuto_attraversa_il_capodanno():
    """A gennaio il mese appena chiuso e' dicembre dell'anno PRIMA.

    Senza il caso esplicito, un confronto su `oggi.month - 1` darebbe 0 e la
    regola si applicherebbe al mese sbagliato per tutto gennaio.
    """
    from services.fastapi_worker import _personale_gia_dovuto as dovuto

    assert dovuto(date(2026, 1, 3), (2025, 12)) is False
    assert dovuto(date(2026, 1, 20), (2025, 12)) is True
    assert dovuto(date(2026, 1, 3), (2025, 11)) is True


def test_indice_rosso_non_conta_il_personale_non_ancora_dovuto():
    """ESEGUE `_salute_indice_rosso` prima e dopo il 15, stessi dati.

    Prima versione di questo presidio: asseriva che il simbolo
    `_personale_gia_dovuto` esistesse (`inspect.getsource` + `callable`).
    Verificava il NameError, non la regola: rimuovendo la guardia da questo ramo
    il test restava verde, perche' il nome sopravviveva nell'altro chiamante. Un
    test sul sorgente non prova il comportamento — qui si esegue la funzione.

    Conta perche' `_salute_indice_rosso` e' il GATE della buona notizia: un
    rosso per un dato non ancora dovuto la sopprimerebbe senza motivo.
    """
    from services.fastapi_worker import _salute_indice_rosso

    # L'indice e' la media di 4 voci da 25 punti; rosso sotto 50. Perche' il
    # personale sia il voto DECISIVO servono due altre voci gia' mancanti: qui
    # niente fatturato (riga a zero) e nessuna fattura di costo. Restano
    # "classificate" (nessuna riga da classificare -> a posto) e il personale.
    # Con personale contato mancante: 1 voce su 4 -> 25, rosso.
    # Con personale non ancora dovuto: 2 su 4 -> 50, non rosso.
    righe = [{
        "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 0, "costo_personale_extra": 0,
    }]
    # Fatture di costo PRESENTI: cosi' mancano esattamente due voci
    # (fatturato + personale) e il personale e' il voto che decide.
    costi = patch(
        "services.fastapi_worker._costi_automatici_mese", return_value=5000.0
    )
    with _oggi(3), costi:
        prima = _salute_indice_rosso(RID, _sb_salute(righe))
    with _oggi(20), costi:
        dopo = _salute_indice_rosso(RID, _sb_salute(righe))
    assert (prima, dopo) == (False, True), (
        f"la guardia sul personale non dovuto non e' applicata: {prima=} {dopo=}"
    )


def test_card_completezza_non_conta_il_personale_non_ancora_dovuto():
    """ESEGUE `home_salute` e guarda la voce «personale» nella risposta vera.

    Prima versione: verificava la regola in isolamento e poi contava gli usi di
    `_personale_gia_dovuto` dentro `home_salute` con `inspect.getsource`. Meta'
    di quel test era un assert sul sorgente — lo stesso difetto che avevo appena
    corretto altrove: sopravvive a una modifica che rompe il comportamento
    lasciando il testo, e grida su una rinomina innocua. Qui si chiama la
    funzione: la dependency di auth vale solo via HTTP, quindi si patchano i
    cinque punti esterni e si legge la voce.

    E' l'altro consumatore della regola: senza, la card direbbe «manca» mentre
    il briefing tace.
    """
    from services.fastapi_worker import home_salute

    righe = [{
        "fatturato_iva10": 10000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 0, "costo_personale_extra": 0,
    }]

    def _voce_personale(giorno):
        patches = [
            patch("services.fastapi_worker._resolve_user_from_token",
                  return_value={"id": "user-1"}),
            patch("services.fastapi_worker._get_supabase_client",
                  return_value=_sb_salute(righe)),
            patch("services.fastapi_worker._resolve_ristorante_id", return_value=RID),
            patch("services.fastapi_worker._costi_automatici_mese", return_value=5000.0),
            _oggi(giorno),
        ]
        for pa in patches:
            pa.start()
        try:
            resp = home_salute(authorization="Bearer x")
        finally:
            for pa in reversed(patches):
                pa.stop()
        return next(v for v in resp.voci if v.key == "personale")

    prima = _voce_personale(3)
    dopo = _voce_personale(20)
    assert prima.ok is True, "la card dice «manca» su un dato non ancora dovuto"
    assert dopo.ok is False, "dal 15 il dato e' dovuto: se manca, va detto"


def test_la_campanella_passa_dallo_stesso_gate_del_briefing():
    """Il gate settimanale non deve essere aggirabile dalla campanella.

    Esisteva un SECONDO percorso che generava `incasso_mancante`: un endpoint
    chiamato dal mobile a ogni apertura, che scriveva in `notification_inbox`
    con bucket GIORNALIERO (tolto il 25/09/2026). Righe vecchie di quel tipo
    possono restare nella tabella, e sarebbero un bypass: sul telefono l'avviso
    tornerebbe ogni giorno.

    Non lo e' perche' `get_notifiche` rimuove SEMPRE le righe persistite dei
    topic in `TOPIC_LIVE_NON_IGNORABILI` e le sostituisce con i live, che
    passano da `_segnali_live_dati_mancanti` -> `_briefing_dati_mensili_mancanti`,
    cioe' dalla funzione col gate. Questo test lega i due anelli: se un domani
    la sostituzione saltasse, o il topic uscisse da quella lista, il bypass si
    riaprirebbe in silenzio.
    """
    import inspect
    import services.fastapi_worker as fw
    from services.daily_briefing_service import TOPIC_LIVE_NON_IGNORABILI

    assert "incasso_mancante" in TOPIC_LIVE_NON_IGNORABILI, (
        "uscendo da questa lista, le righe persistite del mobile tornerebbero "
        "visibili ogni giorno, aggirando il gate settimanale"
    )
    src = inspect.getsource(fw._segnali_live_dati_mancanti)
    assert "_briefing_dati_mensili_mancanti(" in src, (
        "la campanella non passa piu' dalla funzione col gate settimanale"
    )


def test_il_prompt_chat_non_contraddice_briefing_e_card():
    """Quarto consumatore: l'assistente non deve smentirsi da solo.

    `_build_chat_system_prompt` calcola un suo `personale_ok` per iniettare
    l'avviso «Costo del personale non registrato» nel prompt. Senza la guardia,
    prima del 15 la chat lo direbbe mentre briefing e card «Completezza dati»
    tacciono: il cliente non vede tre fonti, vede l'assistente.

    Si guarda il TESTO del prompt generato, non il sorgente: e' quello che
    finisce al modello.
    """
    import services.fastapi_worker as fw

    per_riga = {"costo_dipendenti": 0, "costo_personale_extra": 0}

    def _prompt(giorno):
        sb = _sb_salute([per_riga])
        # Qui la data NON passa da `datetime.datetime` ma da `_oggi_rome()`:
        # `_oggi` da solo non basta, va patchato anche quello o la guardia
        # vedrebbe la data vera e il test misurerebbe il giorno in cui gira.
        with _oggi(giorno), patch(
            "services.fastapi_worker._oggi_rome",
            return_value=date(2026, 9, giorno),
        ), patch(
            "services.fastapi_worker._costi_automatici_mese", return_value=5000.0
        ):
            return fw._build_chat_system_prompt(
                {"id": "user-1", "pagine_abilitate": ["margini"]},
                sb,
                None,
                ristorante_id=RID,
            )

    # Niente try/except: uno skip silenzioso e' un presidio che non misura.
    prima, dopo = _prompt(3), _prompt(20)

    assert "Costo del personale non registrato" not in prima, (
        "la chat reclama il personale prima che sia dovuto, mentre il briefing tace"
    )
    assert "Costo del personale non registrato" in dopo, (
        "dal 15 il dato e' dovuto: se manca, la chat deve poterlo dire"
    )
