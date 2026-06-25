"""Test guardia: il briefing segnala le righe da controllare come la pagina.

_briefing_righe_da_classificare ricalcola il segnale LIVE contando TUTTE le
righe needs_review non cancellate (decisione Mattia 19/06: niente finestra 30gg,
il numero deve combaciare con cio' che il cliente trova in Analisi Fatture; caso
LAND: 2 recenti ma 9 totali -> il briefing deve dire 9).
"""
from unittest.mock import MagicMock

from services.fastapi_worker import (
    _briefing_righe_da_classificare,
    _briefing_fatture_mancanti,
)

RID = "rist-xyz"


def _sb(count):
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.is_.return_value = q
    q.gte.return_value = q
    q.limit.return_value = q
    q.execute.return_value = MagicMock(count=count, data=[{"id": i} for i in range(count or 0)])
    sb.table.return_value = q
    return sb


def test_nessuna_riga_da_classificare_nessuna_notifica():
    assert _briefing_righe_da_classificare(RID, _sb(0)) is None


def test_righe_da_classificare_genera_notifica_live():
    out = _briefing_righe_da_classificare(RID, _sb(2))
    assert out is not None
    assert out["topic_key"] == "uncategorized_rows"
    assert out["source_type"] == "live"
    assert out["payload"]["uncategorized_rows"] == 2
    assert out["payload"]["count"] == 2
    assert "2 righe" in out["title"]
    # Deep-link al tab Articoli filtrato sulle righe da controllare.
    assert "verifica=1" in out["action_page"]


def test_singolare_una_riga():
    out = _briefing_righe_da_classificare(RID, _sb(1))
    assert out is not None
    assert "1 riga" in out["title"]


def test_conta_tutte_senza_finestra_temporale():
    # Decisione 19/06: NESSUN filtro su created_at (.gte). Se qualcuno reintroduce
    # la finestra 30gg, questo test si rompe.
    sb = _sb(9)
    out = _briefing_righe_da_classificare(RID, sb)
    assert out["payload"]["count"] == 9
    assert "9 righe" in out["title"]
    q = sb.table.return_value
    assert not q.gte.called, "Il conteggio non deve filtrare per created_at (niente finestra 30gg)"


# ── Fatture mancanti: stesso pattern (voce 1 della Salute) ──

def _sb_fatture(count, sdi_attivo=False, ultima_created_at=None):
    """Mock a tre tabelle del caso A:
      - 'ristoranti' (.single -> user_id + sdi_attivo, decide il canale)
      - 'margini_mensili' (caso B: vuoto -> fatturato 0 -> caso B saltato)
      - 'fatture' (caso A: ultima fattura via order/limit created_at).
    count=0 -> nessuna fattura recente -> avviso; count>0 -> fattura di OGGI -> ok.
    sdi_attivo=True -> canale sdi; False -> manuale.
    """
    from datetime import datetime, timezone
    sb = MagicMock()
    state = {"table": None}

    if ultima_created_at is None and count:
        ultima_created_at = datetime.now(timezone.utc).isoformat()

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        if state["table"] == "ristoranti":
            return MagicMock(data={"user_id": "u1", "sdi_attivo": sdi_attivo})
        if state["table"] == "margini_mensili":
            return MagicMock(data=[])  # nessun fatturato -> caso B non scatta
        # fatture: ultima fattura (order created_at desc, limit 1)
        rows = [{"created_at": ultima_created_at}] if ultima_created_at else []
        return MagicMock(count=count, data=rows)

    q = MagicMock()
    sb.table.side_effect = _table
    q.select.return_value = q
    q.eq.return_value = q
    q.is_.return_value = q
    q.gte.return_value = q
    q.lte.return_value = q
    q.order.return_value = q
    q.limit.return_value = q
    q.single.return_value = q
    q.execute.side_effect = _execute
    return sb


def test_con_fatture_recenti_nessuna_notifica():
    # Una fattura caricata oggi (entro 7 gg) -> niente avviso.
    assert _briefing_fatture_mancanti(RID, _sb_fatture(3)) is None


def test_senza_fatture_recenti_canale_manuale():
    # sdi_attivo=False -> caricamento manuale -> "carica le fatture".
    out = _briefing_fatture_mancanti(RID, _sb_fatture(0, sdi_attivo=False))
    assert out is not None
    assert out["topic_key"] == "fatture_mancanti"
    assert out["payload"]["canale"] == "manuale"
    assert "caricata" in out["title"].lower()


def test_senza_fatture_recenti_canale_sdi():
    # sdi_attivo=True -> ricezione automatica -> messaggio sul flusso, non "carica".
    out = _briefing_fatture_mancanti(RID, _sb_fatture(0, sdi_attivo=True))
    assert out is not None
    assert out["payload"]["canale"] == "sdi"
    assert "automatico" in out["title"].lower()


def test_default_senza_flag_e_manuale():
    # Default prudente: senza sdi_attivo (False) il canale e' manuale, mai mandare
    # a verificare un flusso automatico non attivo (stato attuale di tutti i clienti).
    out = _briefing_fatture_mancanti(RID, _sb_fatture(0))
    assert out is not None
    assert out["payload"]["canale"] == "manuale"


def test_ultima_fattura_oltre_7_giorni_scatta():
    # Decisione 19/06: ultima fattura piu' vecchia di 7 gg -> avviso (era 30 gg).
    from datetime import datetime, timezone, timedelta
    otto_gg_fa = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    out = _briefing_fatture_mancanti(
        RID, _sb_fatture(1, sdi_attivo=False, ultima_created_at=otto_gg_fa)
    )
    assert out is not None
    assert out["topic_key"] == "fatture_mancanti"


def test_ultima_fattura_entro_7_giorni_silenzio():
    from datetime import datetime, timezone, timedelta
    tre_gg_fa = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    out = _briefing_fatture_mancanti(
        RID, _sb_fatture(1, sdi_attivo=False, ultima_created_at=tre_gg_fa)
    )
    assert out is None
