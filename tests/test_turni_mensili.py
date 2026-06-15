"""
Test per l'inserimento mensile dei turni personale (totali da busta paga).

Copre la logica lato worker introdotta con la modalità Mensile:
- _ore_turno: per le righe mensili ritorna ore_dichiarate, non calcola dagli orari
- ws_personale_list: aggrega il costo delle righe mensili dal lordo reale (non da tariffa)
- guardia di esclusività giornaliero/mensile per dipendente/mese (HTTP 409)
- validazioni del POST mensile
- get_costo_personale_da_turni (margini): le righe mensili usano il lordo reale

Supabase e auth sono mockati, coerentemente con gli altri test del modulo.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.fastapi_worker as worker
import services.routers.margini as margini
import services.routers.workspace as workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query_mock(execute_data=None):
    """Mock chain del client Supabase (select/eq/gte/lte/order/limit/insert/update/execute)."""
    q = MagicMock()
    for m in ("select", "eq", "gte", "lte", "order", "limit", "insert", "update", "delete"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=execute_data or [])
    return q


def _patch_workspace(table_side_effect):
    """Patcha auth + supabase + ristorante sul router workspace.

    table_side_effect: callable(table_name) -> query mock, così endpoint che
    interrogano più tabelle/condizioni possono restituire dati diversi."""
    client = MagicMock()
    client.table.side_effect = table_side_effect
    return patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _get_ristorante_id_for_user=MagicMock(return_value="rist-1"),
    ), client


# ---------------------------------------------------------------------------
# _ore_turno — righe mensili vs giornaliere
# ---------------------------------------------------------------------------

class TestOreTurno:

    def test_riga_mensile_usa_ore_dichiarate(self):
        t = {"mensile": True, "ore_dichiarate": 168, "ora_inizio": "00:00", "ora_fine": "00:00"}
        assert worker._ore_turno(t) == 168.0

    def test_riga_mensile_ore_dichiarate_none(self):
        t = {"mensile": True, "ore_dichiarate": None}
        assert worker._ore_turno(t) == 0.0

    def test_riga_giornaliera_calcola_da_orari(self):
        t = {"mensile": False, "ora_inizio": "09:00", "ora_fine": "17:00"}
        assert worker._ore_turno(t) == 8.0

    def test_riga_giornaliera_default_senza_flag(self):
        t = {"ora_inizio": "09:00", "ora_fine": "13:30"}
        assert worker._ore_turno(t) == 4.5

    def test_giornaliero_extra_aggiuntive_al_totale(self):
        # Nuova semantica: ore extra in PIU' rispetto all'orario.
        # 9-17 (8h) + 2h extra = 10h totali.
        t = {"mensile": False, "ora_inizio": "09:00", "ora_fine": "17:00", "ore_extra": 2}
        assert worker._ore_turno(t) == 10.0

    def test_giornaliero_extra_con_slot_spezzato(self):
        # 9-13 (4h) + 18-22 (4h) = 8h orari, + 1.5h extra = 9.5h.
        t = {
            "mensile": False, "ora_inizio": "09:00", "ora_fine": "13:00",
            "ora_inizio2": "18:00", "ora_fine2": "22:00", "ore_extra": 1.5,
        }
        assert worker._ore_turno(t) == 9.5


# ---------------------------------------------------------------------------
# ws_personale_list — aggregazione costi righe mensili
# ---------------------------------------------------------------------------

class TestPersonaleListMensile:

    def test_costo_mensile_da_lordo(self):
        # Una riga mensile: lordo 1850, di cui 120 extra → ordinario 1730, extra 120.
        riga = {
            "id": "m1", "nome": "Mario", "data_turno": "2026-06-01",
            "mensile": True, "ore_dichiarate": 168, "ore_extra": 8,
            "lordo_mensile": 1850.0, "importo_extra": 120.0,
            "costo_orario": None, "costo_orario_extra": None,
        }
        turni_q = _query_mock([riga])
        storico_q = _query_mock([{"nome": "Mario", "costo_orario": None, "costo_orario_extra": None, "data_turno": "2026-06-01"}])
        calls = {"n": 0}
        def side_effect(_name):
            calls["n"] += 1
            return turni_q if calls["n"] == 1 else storico_q
        ctx, _ = _patch_workspace(side_effect)
        with ctx:
            res = workspace.ws_personale_list(da="2026-06-01", a="2026-06-30", mensile=True, authorization="Bearer x")
        assert res["monte_ore"]["Mario"] == 168.0
        assert res["ore_extra_per_persona"]["Mario"] == 8.0
        assert res["costo_standard_per_persona"]["Mario"] == 1730.0
        assert res["costo_extra_per_persona"]["Mario"] == 120.0
        assert res["costo_totale"] == 1850.0

    def test_costo_mensile_senza_extra(self):
        riga = {
            "id": "m2", "nome": "Anna", "data_turno": "2026-06-01",
            "mensile": True, "ore_dichiarate": 160, "ore_extra": None,
            "lordo_mensile": 1600.0, "importo_extra": None,
            "costo_orario": None, "costo_orario_extra": None,
        }
        turni_q = _query_mock([riga])
        storico_q = _query_mock([{"nome": "Anna", "costo_orario": None, "costo_orario_extra": None, "data_turno": "2026-06-01"}])
        calls = {"n": 0}
        def side_effect(_name):
            calls["n"] += 1
            return turni_q if calls["n"] == 1 else storico_q
        ctx, _ = _patch_workspace(side_effect)
        with ctx:
            res = workspace.ws_personale_list(da="2026-06-01", a="2026-06-30", mensile=True, authorization="Bearer x")
        assert res["costo_standard_per_persona"]["Anna"] == 1600.0
        assert res["costo_extra_per_persona"].get("Anna", 0) == 0
        assert res["costo_totale"] == 1600.0


# ---------------------------------------------------------------------------
# Guardia esclusività — POST giornaliero
# ---------------------------------------------------------------------------

class TestEsclusivitaGiornaliero:

    def test_blocca_se_esiste_riga_mensile(self):
        # _esiste_riga_mese(mensile=True) trova una riga → POST giornaliero respinto.
        esiste_q = _query_mock([{"id": "m1"}])
        ctx, _ = _patch_workspace(lambda _n: esiste_q)
        body = workspace.NuovoTurnoBody(
            nome="Mario", data_turno="2026-06-10", ora_inizio="09:00", ora_fine="17:00"
        )
        with ctx:
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_personale_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 409
        assert "mensile" in exc.value.detail.lower()

    def test_ok_se_nessuna_riga_mensile(self):
        esiste_q = _query_mock([])           # nessuna riga mensile
        insert_q = _query_mock([{"id": "new", "nome": "Mario"}])
        calls = {"n": 0}
        def side_effect(_n):
            calls["n"] += 1
            return esiste_q if calls["n"] == 1 else insert_q
        ctx, _ = _patch_workspace(side_effect)
        body = workspace.NuovoTurnoBody(
            nome="Mario", data_turno="2026-06-10", ora_inizio="09:00", ora_fine="17:00"
        )
        with ctx:
            res = workspace.ws_personale_crea(body=body, authorization="Bearer x")
        assert res == {"id": "new", "nome": "Mario"}


# ---------------------------------------------------------------------------
# Guardia esclusività + validazioni — POST mensile
# ---------------------------------------------------------------------------

class TestPostMensile:

    def _body(self, **kw):
        base = dict(nome="Mario", mese="2026-06", ore_totali=168, lordo=1850.0)
        base.update(kw)
        return workspace.TurnoMensileBody(**base)

    def test_blocca_se_esistono_turni_giornalieri(self):
        # Prima query (_esiste_riga_mese mensile=False) trova turni → 409.
        giorn_q = _query_mock([{"id": "g1"}])
        ctx, _ = _patch_workspace(lambda _n: giorn_q)
        with ctx:
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_personale_crea_mensile(body=self._body(), authorization="Bearer x")
        assert exc.value.status_code == 409
        assert "giornalieri" in exc.value.detail.lower()

    def test_blocca_se_esiste_gia_mensile(self):
        # 1ª query (giornalieri) vuota, 2ª query (mensile) trova → 409.
        vuota = _query_mock([])
        mensile_q = _query_mock([{"id": "m1"}])
        calls = {"n": 0}
        def side_effect(_n):
            calls["n"] += 1
            return vuota if calls["n"] == 1 else mensile_q
        ctx, _ = _patch_workspace(side_effect)
        with ctx:
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_personale_crea_mensile(body=self._body(), authorization="Bearer x")
        assert exc.value.status_code == 409
        assert "già un inserimento mensile" in exc.value.detail.lower()

    def test_ore_extra_oltre_totali(self):
        ctx, _ = _patch_workspace(lambda _n: _query_mock([]))
        with ctx:
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_personale_crea_mensile(body=self._body(ore_extra=200), authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_importo_extra_oltre_lordo(self):
        ctx, _ = _patch_workspace(lambda _n: _query_mock([]))
        with ctx:
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_personale_crea_mensile(body=self._body(importo_extra=9999), authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_tutto_zero_respinto(self):
        ctx, _ = _patch_workspace(lambda _n: _query_mock([]))
        with ctx:
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_personale_crea_mensile(body=self._body(ore_totali=0, lordo=0), authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_creazione_valida_payload(self):
        # Due _esiste_riga_mese vuote, poi insert.
        vuota1 = _query_mock([])
        vuota2 = _query_mock([])
        insert_q = _query_mock([{"id": "new"}])
        calls = {"n": 0}
        def side_effect(_n):
            calls["n"] += 1
            return {1: vuota1, 2: vuota2}.get(calls["n"], insert_q)
        ctx, _ = _patch_workspace(side_effect)
        with ctx:
            res = workspace.ws_personale_crea_mensile(
                body=self._body(ore_totali=168, lordo=1850.0, ore_extra=8, importo_extra=120.0, note="  giugno  "),
                authorization="Bearer x",
            )
        assert res == {"id": "new"}
        payload = insert_q.insert.call_args[0][0]
        assert payload["mensile"] is True
        assert payload["data_turno"] == "2026-06-01"       # 1° del mese
        assert payload["ora_inizio"] == "00:00"
        assert payload["ore_dichiarate"] == 168.0
        assert payload["lordo_mensile"] == 1850.0
        assert payload["ore_extra"] == 8.0
        assert payload["importo_extra"] == 120.0
        assert payload["nome"] == "Mario"


# ---------------------------------------------------------------------------
# Margini — costo personale da turni con righe mensili
# ---------------------------------------------------------------------------

class TestMarginiCostoPersonale:

    def _patch_margini(self, turni):
        client = MagicMock()
        client.table.return_value = _query_mock(turni)
        return patch.multiple(
            margini,
            _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
            _get_supabase_client=MagicMock(return_value=client),
            _resolve_ristorante_id=MagicMock(return_value="rist-1"),
        )

    def test_riga_mensile_usa_lordo_reale(self):
        turni = [{
            "id": "m1", "nome": "Mario", "data_turno": "2026-06-01",
            "mensile": True, "ore_dichiarate": 168, "ore_extra": 8,
            "lordo_mensile": 1850.0, "importo_extra": 120.0, "costo_orario": None,
        }]
        with self._patch_margini(turni):
            res = margini.get_costo_personale_da_turni(anno=2026, mese=6, authorization="Bearer x")
        assert res["ore_totali"] == 168.0
        assert res["ore_extra"] == 8.0
        assert res["costo_personale_extra"] == 120.0
        assert res["costo_dipendenti"] == 1730.0
        assert res["n_senza_costo"] == 0   # la riga mensile NON conta come senza costo

    def test_riga_giornaliera_senza_extra(self):
        turni = [{
            "id": "g1", "nome": "Anna", "data_turno": "2026-06-10",
            "mensile": False, "ora_inizio": "09:00", "ora_fine": "17:00",
            "ore_extra": 0, "costo_orario": 12.0,
        }]
        with self._patch_margini(turni):
            res = margini.get_costo_personale_da_turni(anno=2026, mese=6, authorization="Bearer x")
        assert res["ore_totali"] == 8.0
        assert res["costo_dipendenti"] == 96.0
        assert res["costo_personale_extra"] == 0.0

    def test_giornaliero_extra_aggiuntive_split_corretto(self):
        # 9-17 (8h ordinarie) + 2h extra = 10h totali. costo std 12, extra 18.
        # ordinario = 8×12 = 96; extra = 2×18 = 36.
        turni = [{
            "id": "g1", "nome": "Anna", "data_turno": "2026-06-10",
            "mensile": False, "ora_inizio": "09:00", "ora_fine": "17:00",
            "ore_extra": 2, "costo_orario": 12.0, "costo_orario_extra": 18.0,
        }]
        with self._patch_margini(turni):
            res = margini.get_costo_personale_da_turni(anno=2026, mese=6, authorization="Bearer x")
        assert res["ore_totali"] == 10.0
        assert res["ore_extra"] == 2.0
        assert res["costo_dipendenti"] == 96.0
        assert res["costo_personale_extra"] == 36.0
