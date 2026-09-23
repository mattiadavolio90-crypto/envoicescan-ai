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
    """Una volta a settimana, non una volta e basta: deve tornare."""
    visti = []
    for giorno in (21, 28):  # due lunedi consecutivi
        with _oggi(giorno):
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


def test_i_consumatori_della_regola_esistono_e_sono_chiamabili():
    """Il nome chiamato deve esistere: un helper mai definito e' un NameError.

    Difetto reale occorso scrivendo questa fase: la chiamata a
    `_personale_gia_dovuto` era stata inserita in `home_salute` e in
    `_salute_indice_rosso` mentre la sua `def` era andata persa. Sintassi
    valida, suite verde, e in produzione due NameError — perche' nessun test
    eseguiva quei rami.

    Qui si presidia il legame: ogni punto che CHIAMA la regola deve poterla
    risolvere. Si legge il sorgente solo per trovare i chiamanti; la prova e'
    che il simbolo esista davvero nel modulo ed sia invocabile.
    """
    import inspect
    import services.fastapi_worker as fw

    src = inspect.getsource(fw)
    assert "_personale_gia_dovuto(" in src, "la regola non e' piu' usata da nessuno"
    # Deve esistere come attributo vero del modulo, non solo come testo.
    assert callable(getattr(fw, "_personale_gia_dovuto", None)), (
        "la regola e' chiamata ma non definita: NameError a runtime"
    )
    # E deve essere definita, non solo importata per caso.
    assert "def _personale_gia_dovuto(" in src
