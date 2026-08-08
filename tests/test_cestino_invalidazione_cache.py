"""Test: le operazioni cestino invalidano la cache fatture.

Contesto (audit §3 su db_service.py, 8/8/2026). `get_fatture_cestino` e'
cachata 60s (`db_service.py:1536`) e `clear_fatture_cache` la invalida
esplicitamente (`:1516-1517`), ma nessuno dei 4 endpoint di `routers/cestino.py`
la chiamava: prima di questo fix `clear_fatture_cache` aveva UN SOLO chiamante
non-legacy in tutto il progetto (`upload_handler.py:2130`).

Percorso confermato vivo end-to-end: UI -> route Next (`apps/web/src/app/api/
cestino/*/route.ts`) -> endpoint worker -> funzione di db_service. Il cliente
spostava una fattura nel cestino e la lista restava ferma fino al TTL.

Stesso meccanismo dei casi gia' chiusi in questo ciclo su `ricavi.py` (7/8) e
`admin.py` (8/8). I test verificano il COMPORTAMENTO (la cache viene invalidata),
piu' una guardia sulla simmetria dei percorsi di scrittura.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.db_service as db


def _sb_mock(data=None, count=1):
    """Client Supabase con chain permissiva: qui interessa la cache, non i filtri."""
    q = MagicMock()
    for m in ("select", "eq", "update", "delete", "is_", "order", "limit", "range", "in_"):
        getattr(q, m).return_value = q
    q.not_.is_.return_value = q
    q.execute.return_value = SimpleNamespace(
        data=data if data is not None else [{"id": "1", "file_origine": "f.xml"}],
        count=count,
    )
    client = MagicMock()
    client.table.return_value = q
    return client


class TestCestinoInvalidaCache:

    def test_ripristina_fattura_invalida_la_cache(self):
        spia = MagicMock()
        with patch.object(db, "clear_fatture_cache", spia):
            out = db.ripristina_fattura(
                "f.xml", user_id="u1", ristorante_id="r1", supabase_client=_sb_mock()
            )
        assert out["success"] is True
        spia.assert_called_once()

    def test_svuota_cestino_invalida_la_cache(self):
        spia = MagicMock()
        with patch.object(db, "clear_fatture_cache", spia):
            out = db.svuota_cestino(
                "u1", ristorante_id="r1", supabase_client=_sb_mock()
            )
        assert out["success"] is True
        spia.assert_called_once()

    def test_elimina_fattura_completa_invalida_la_cache(self):
        """Hard delete: la riga sparisce, il cestino deve smettere di mostrarla."""
        spia = MagicMock()
        client = _sb_mock()
        # verify post-delete: 0 righe residue -> successo pieno
        client.table.return_value.execute.side_effect = [
            SimpleNamespace(data=[{"id": "1"}], count=1),   # count iniziale
            SimpleNamespace(data=[], count=0),               # delete
            SimpleNamespace(data=[], count=0),               # verify
            SimpleNamespace(data=[], count=0),               # eventuali extra
            SimpleNamespace(data=[], count=0),
            SimpleNamespace(data=[], count=0),
        ]
        with patch.object(db, "clear_fatture_cache", spia), patch.object(
            db, "_pulisci_riparto_orfano", MagicMock()
        ):
            out = db.elimina_fattura_completa(
                "f.xml", user_id="u1", ristoranteid="r1",
                soft_delete=False, supabase_client=client,
            )
        assert out["success"] is True
        spia.assert_called_once()

    def test_soft_delete_dal_router_invalida_la_cache(self):
        """`elimina_fattura_soft` scrive su fatture senza passare da db_service."""
        import services.routers.cestino as cestino
        spia = MagicMock()
        client = _sb_mock(data=[{"id": "1", "deleted_at": None}])
        body = cestino.FatturaEliminaRequest(file_origine="f.xml")
        with patch.multiple(
            cestino,
            _resolve_user_from_token=MagicMock(return_value={"id": "u1"}),
            _get_supabase_client=MagicMock(return_value=client),
            _resolve_ristorante_id=MagicMock(return_value="r1"),
        ), patch.object(db, "clear_fatture_cache", spia), patch.object(
            db, "_pulisci_riparto_orfano", MagicMock()
        ):
            out = cestino.elimina_fattura_soft(body, authorization="Bearer t")
        assert out["success"] is True
        spia.assert_called_once()

    def test_clear_fatture_cache_invalida_anche_il_cestino(self):
        """Se questa lista si accorcia, i test sopra difendono meno di quanto sembra."""
        import inspect
        src = inspect.getsource(db.clear_fatture_cache)
        assert "get_fatture_cestino" in src
        assert "_carica_fatture_da_supabase" in src

    def test_tutti_i_percorsi_cestino_sono_simmetrici(self):
        """Guardia: nessuna funzione cestino di db_service scrive senza invalidare."""
        import inspect
        for fn in (db.ripristina_fattura, db.svuota_cestino, db.elimina_fattura_completa):
            src = inspect.getsource(fn)
            assert "clear_fatture_cache()" in src, (
                f"{fn.__name__} scrive su fatture senza invalidare la cache"
            )
