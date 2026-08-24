"""Test dello switch sede vs. proiezione righe ripartite.

Contesto: passando da vista catena a un punto vendita di catena, Analisi Fatture →
Articoli non mostrava né le righe ripartite né il chip "Solo ripartite" (derivato dal
dataset: nessuna riga ripartita → nessun chip). Nemmeno ricaricare la pagina sbloccava;
cambiare PV e tornare indietro invece sì.

Causa: il worker gira a più processi (WORKER_WEB_CONCURRENCY=4) con cache in-process non
condivise, e l'invalidazione al cambio sede tocca solo il processo che serve la POST.
Un processo che calcolava _ristorante_quote_meta durante lo switch — con la sede attiva
non ancora propagata — otteneva ha_quote=False e lo inchiodava per 300s
(_RISTORANTE_QUOTE_TTL). Senza ha_quote, _fetch_fatture_rows salta del tutto
righe_ripartite_proiettate.

Difese testate qui:
  1. TTL asimmetrico: il False (che NASCONDE righe) scade presto, il True resta a lungo.
  2. cambia-sede invalida la cache righe/meta del rid di destinazione.
"""
from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw
import services.routers.account as account


class _Query:
    """Client Supabase minimo: risponde a ristoranti (user_id) e alle quote riparto."""

    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self): return self

    def execute(self):
        self._c.calls.append(self._t)
        if self._t == "ristoranti":
            return MagicMock(data={"user_id": self._c.user_id})
        if self._t == "riparto_costi_catena_quote":
            return MagicMock(data=([{"id": "q1"}] if self._c.ha_quote else []))
        return MagicMock(data=[])


class _Client:
    def __init__(self, ha_quote=True, user_id="user-1"):
        self.ha_quote = ha_quote
        self.user_id = user_id
        self.calls = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def _cache_pulita():
    fw._RISTORANTE_QUOTE_META.clear()
    fw._FATTURE_ROWS_CACHE.clear()
    yield
    fw._RISTORANTE_QUOTE_META.clear()
    fw._FATTURE_ROWS_CACHE.clear()


def test_meta_negativa_scade_presto():
    """ha_quote=False non deve restare cachato 5 minuti: è lo stato che nasconde le
    righe ripartite, e se è sbagliato nemmeno il refresh sblocca l'utente."""
    sb = _Client(ha_quote=False)
    uid, ha_quote = fw._ristorante_quote_meta(sb, "pv-1")
    assert (uid, ha_quote) == ("user-1", False)

    scadenza = fw._RISTORANTE_QUOTE_META["pv-1"][0]
    import time
    residuo = scadenza - time.time()
    assert residuo <= fw._RISTORANTE_QUOTE_TTL_NEG
    assert residuo < fw._RISTORANTE_QUOTE_TTL


def test_meta_negativa_ricalcolata_dopo_ttl_breve():
    """Scaduto il TTL breve, un PV che nel frattempo ha quote viene visto come tale."""
    sb = _Client(ha_quote=False)
    assert fw._ristorante_quote_meta(sb, "pv-1") == ("user-1", False)

    # Simula il TTL breve trascorso, senza dormire davvero.
    exp, uid, hq = fw._RISTORANTE_QUOTE_META["pv-1"]
    fw._RISTORANTE_QUOTE_META["pv-1"] = (0.0, uid, hq)

    sb.ha_quote = True
    assert fw._ristorante_quote_meta(sb, "pv-1") == ("user-1", True)


def test_meta_positiva_resta_cachata_a_lungo():
    """Il caso che AGGIUNGE righe conserva il TTL lungo: nessuna regressione di costo."""
    sb = _Client(ha_quote=True)
    assert fw._ristorante_quote_meta(sb, "pv-1") == ("user-1", True)

    import time
    residuo = fw._RISTORANTE_QUOTE_META["pv-1"][0] - time.time()
    assert residuo > fw._RISTORANTE_QUOTE_TTL_NEG
    assert residuo <= fw._RISTORANTE_QUOTE_TTL

    # Seconda chiamata servita da cache: nessuna query in più.
    chiamate = len(sb.calls)
    assert fw._ristorante_quote_meta(sb, "pv-1") == ("user-1", True)
    assert len(sb.calls) == chiamate


def test_invalidazione_righe_pulisce_anche_la_meta():
    """_invalidate_fatture_rows_cache(rid) è ciò che cambia-sede riusa: deve togliere
    la entry meta di QUEL rid e lasciare intatte le altre."""
    fw._RISTORANTE_QUOTE_META["pv-1"] = (9e9, "user-1", False)
    fw._RISTORANTE_QUOTE_META["pv-2"] = (9e9, "user-1", True)

    with patch.object(fw, "get_supabase_client", MagicMock()):
        fw._invalidate_fatture_rows_cache("pv-1")

    assert "pv-1" not in fw._RISTORANTE_QUOTE_META
    assert "pv-2" in fw._RISTORANTE_QUOTE_META


def test_cambia_sede_invalida_la_meta_del_rid_destinazione():
    """La POST di cambio sede deve invalidare la cache del PV in cui si sta entrando,
    altrimenti una meta avvelenata a False sopravvive allo switch."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "pv-1"}]
    )

    worker = MagicMock()
    with patch.object(account, "_resolve_user_from_token", return_value={"id": "user-1"}), \
         patch.object(account, "_get_supabase_client", return_value=sb), \
         patch.object(account, "_fw", return_value=worker), \
         patch("services.auth_service._clear_sessione_cache", MagicMock()):
        res = account.account_cambia_sede(
            account.CambiaSedeBody(ristorante_id="pv-1"),
            authorization="Bearer tok-123",
        )

    assert res["ok"] is True
    worker._invalidate_fatture_rows_cache.assert_called_once_with("pv-1")
    worker._invalidate_sede_attiva_cache.assert_called_once_with("tok-123")
