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

    fisso = date(anno, mese, giorno)

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


def test_incasso_stessa_chiave_dentro_la_settimana():
    """Due giorni della stessa settimana ISO -> stessa dedupe_key.

    E' la chiave che decide se l'avviso ricompare: uguale = gia' visto.
    """
    chiavi = set()
    for giorno in (22, 23, 24):  # lun/mar/mer della stessa settimana
        with _oggi(giorno):
            out = _briefing_dati_mensili_mancanti(
                RID, _sb(_righe_fatturato_senza_personale(), incasso_ieri=False)
            )
        for n in out:
            if n["topic_key"] == "incasso_mancante":
                chiavi.add(n["dedupe_key"])
    assert len(chiavi) == 1, f"l'avviso ricompare piu' volte a settimana: {chiavi}"


def test_incasso_chiave_diversa_la_settimana_dopo():
    """Settimana nuova -> chiave nuova: l'avviso torna, una volta."""
    chiavi = set()
    for giorno in (23, 30):  # due settimane ISO diverse
        with _oggi(giorno):
            out = _briefing_dati_mensili_mancanti(
                RID, _sb(_righe_fatturato_senza_personale(), incasso_ieri=False)
            )
        for n in out:
            if n["topic_key"] == "incasso_mancante":
                chiavi.add(n["dedupe_key"])
    assert len(chiavi) == 2, f"l'avviso non torna la settimana dopo: {chiavi}"
