"""Test guardia: il briefing segnala le righe da controllare come la pagina.

_briefing_righe_da_classificare ricalcola il segnale LIVE contando i PRODOTTI
DISTINTI (per descrizione) con needs_review non cancellati.

Affinamento 28/06: la pagina aggrega per descrizione, quindi qui si contano i
prodotti distinti e NON le righe (3 righe stessa descrizione = 1 voce in pagina).

NOVITA' vs ARRETRATO (decisione Mattia 2/9/2026). Fino ad allora si contava TUTTO
lo storico: sui dati veri usciva "112 prodotti da controllare" (SUSHILAND San
Giuliano, fermo da luglio) in cima alle 4 card — un arretrato travestito da
compito, che nessuno azzera in un giorno. Ora la CARD conta solo le novita' degli
ultimi DA_CONTROLLARE_NOVITA_GIORNI giorni e il totale resta nel payload come
'arretrato', per la riga di contesto nella narrativa.

I conteggi qui sono quelli VERI misurati il 2/9/2026 (totale/novita 7gg):
San Giuliano 112/0, Villa Guardia 100/46, LAND 29/26, Mariano 18/0, TIME CAFE 5/0.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from services.fastapi_worker import (
    DA_CONTROLLARE_ARRETRATO_SOGLIA,
    _briefing_righe_da_classificare,
    _briefing_fatture_mancanti,
)

RID = "rist-xyz"


def _sb(descrizioni, giorni_fa=0):
    """descrizioni: lista di descrizioni (duplicati = piu' righe della stessa voce).

    giorni_fa: quanti giorni fa sono state CARICATE (created_at). 0 = oggi, quindi
    novita'. Il mock porta created_at come la colonna reale: senza, ogni riga
    risulterebbe vecchia e il test misurerebbe un caso che in produzione non esiste.
    """
    ts = (datetime.now(timezone.utc) - timedelta(days=giorni_fa)).isoformat()
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.is_.return_value = q
    q.gte.return_value = q
    q.range.return_value = q
    q.limit.return_value = q
    q.execute.return_value = MagicMock(
        count=len(descrizioni),
        data=[{"descrizione": d, "created_at": ts} for d in descrizioni],
    )
    sb.table.return_value = q
    return sb


def _sb_misto(recenti, vecchie):
    """Sede con novita' E arretrato: `recenti` caricate oggi, `vecchie` 60 giorni fa."""
    oggi = datetime.now(timezone.utc).isoformat()
    vecchio = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    righe = ([{"descrizione": d, "created_at": oggi} for d in recenti]
             + [{"descrizione": d, "created_at": vecchio} for d in vecchie])
    sb = MagicMock()
    q = MagicMock()
    for attr in ("select", "eq", "is_", "gte", "range", "limit"):
        getattr(q, attr).return_value = q
    q.execute.return_value = MagicMock(count=len(righe), data=righe)
    sb.table.return_value = q
    return sb


def test_nessuna_riga_da_classificare_nessuna_notifica():
    assert _briefing_righe_da_classificare(RID, _sb([])) is None


def test_righe_da_classificare_genera_notifica_live():
    out = _briefing_righe_da_classificare(RID, _sb(["A", "B"]))
    assert out is not None
    assert out["topic_key"] == "uncategorized_rows"
    assert out["source_type"] == "live"
    assert out["payload"]["uncategorized_rows"] == 2
    assert out["payload"]["count"] == 2
    assert "2 prodotti" in out["title"]
    # Deep-link al tab Articoli filtrato sulle righe da controllare.
    assert "verifica=1" in out["action_page"]


def test_singolare_un_prodotto():
    out = _briefing_righe_da_classificare(RID, _sb(["UNICO"]))
    assert out is not None
    assert "1 prodotto" in out["title"]


def test_righe_duplicate_contano_come_un_prodotto():
    # IL FIX del 28/06: 6 righe ma 4 descrizioni distinte (la pagina ne mostra 4).
    # "COMPENSAZIONE" x3 + altre 3 voci uniche -> 4 prodotti, non 6 righe.
    sei_righe = [
        "COMPENSAZIONE RIGA OMAGGIO",
        "COMPENSAZIONE RIGA OMAGGIO",
        "COMPENSAZIONE RIGA OMAGGIO",
        "COUPON LIDL PLUS 5",
        "FATTURA DI ACCONTO",
        "RIGA FATTURA",
    ]
    out = _briefing_righe_da_classificare(RID, _sb(sei_righe))
    assert out["payload"]["count"] == 4, "deve contare i prodotti distinti, non le righe"
    assert "4 prodotti" in out["title"]


class TestNovitaVsArretrato:
    def test_san_giuliano_112_arretrati_zero_novita_nessuna_card(self):
        """Caso reale peggiore: 112 totali, 0 caricati di recente."""
        out = _briefing_righe_da_classificare(
            RID, _sb([f"prod-{i}" for i in range(112)], giorni_fa=45)
        )
        assert out is not None, "l'arretrato va comunque segnalato alla narrativa"
        assert out["payload"]["count"] == 0, "nessuna novita' -> nessuna card da fare"
        assert out["payload"]["arretrato"] == 112
        assert out["severity"] == "info", "un arretrato non e' un warning quotidiano"
        assert "arretrato" in out["title"]

    def test_villa_guardia_100_totali_46_novita(self):
        """Caso reale misto: la card scende da 100 a 46, l'arretrato resta 54."""
        out = _briefing_righe_da_classificare(
            RID,
            _sb_misto([f"nuovo-{i}" for i in range(46)],
                      [f"vecchio-{i}" for i in range(54)]),
        )
        assert out["payload"]["count"] == 46, "la card conta solo le novita'"
        assert out["payload"]["arretrato"] == 54
        assert out["payload"]["totale"] == 100
        assert "46 prodotti" in out["title"]
        assert "100" not in out["title"], "il totale non deve finire nella card"

    def test_land_quasi_tutto_fresco(self):
        """29 totali / 26 novita': la card resta praticamente invariata."""
        out = _briefing_righe_da_classificare(
            RID,
            _sb_misto([f"n-{i}" for i in range(26)], [f"v-{i}" for i in range(3)]),
        )
        assert out["payload"]["count"] == 26
        assert out["payload"]["arretrato"] == 3

    def test_arretrato_sotto_soglia_e_silenzio(self):
        """TIME CAFE (5) e Mariano (18): sotto soglia, nessun record."""
        for n in (5, 18):
            assert n < DA_CONTROLLARE_ARRETRATO_SOGLIA
            out = _briefing_righe_da_classificare(
                RID, _sb([f"p-{i}" for i in range(n)], giorni_fa=45)
            )
            assert out is None, f"{n} arretrati sotto soglia: zero rumore"

    def test_le_novita_restano_novita_al_limite_della_finestra(self):
        """Una riga caricata 6 giorni fa e' ancora novita' (finestra 7)."""
        out = _briefing_righe_da_classificare(RID, _sb(["A"], giorni_fa=6))
        assert out is not None and out["payload"]["count"] == 1


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
