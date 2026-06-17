"""Test guardia: il briefing segnala le righe da classificare come la card Salute.

Difetto osservato (LAND DEI SAPORI): la card "Salute della gestione" mostrava
"2 righe da controllare" (conteggio LIVE di needs_review sulle fatture degli
ultimi 30 giorni), ma campanella e briefing non le segnalavano — perche'
leggevano solo la notifica 'uncategorized_rows' scritta all'UPLOAD, assente se
le righe finivano in needs_review per una rilavorazione su fatture gia' caricate.

_briefing_righe_da_classificare ricalcola il segnale LIVE dalla stessa fonte
della Salute, cosi' le due sezioni Home restano coerenti.
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


# ── Fatture mancanti: stesso pattern (voce 1 della Salute) ──

def _sb_fatture(count, partita_iva=None):
    """Mock a due tabelle: 'fatture' (conteggio) e 'ristoranti' (.single -> P.IVA)."""
    sb = MagicMock()
    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        if state["table"] == "ristoranti":
            return MagicMock(data={"partita_iva": partita_iva})
        return MagicMock(count=count, data=[{"id": i} for i in range(count or 0)])

    q = MagicMock()
    q.table = None
    sb.table.side_effect = _table
    q.select.return_value = q
    q.eq.return_value = q
    q.is_.return_value = q
    q.gte.return_value = q
    q.limit.return_value = q
    q.single.return_value = q
    q.execute.side_effect = _execute
    return sb


def test_con_fatture_recenti_nessuna_notifica():
    # Almeno una fattura negli ultimi 30 gg -> niente avviso.
    assert _briefing_fatture_mancanti(RID, _sb_fatture(3)) is None


def test_senza_fatture_recenti_canale_manuale():
    # Nessuna P.IVA -> caricamento manuale -> "carica le fatture".
    out = _briefing_fatture_mancanti(RID, _sb_fatture(0, partita_iva=None))
    assert out is not None
    assert out["topic_key"] == "fatture_mancanti"
    assert out["payload"]["canale"] == "manuale"
    assert "caricata" in out["title"].lower()


def test_senza_fatture_recenti_canale_sdi():
    # Con P.IVA -> ricezione automatica SDI -> messaggio sul flusso, non "carica".
    out = _briefing_fatture_mancanti(RID, _sb_fatture(0, partita_iva="12345678901"))
    assert out is not None
    assert out["payload"]["canale"] == "sdi"
    assert "automatico" in out["title"].lower()
