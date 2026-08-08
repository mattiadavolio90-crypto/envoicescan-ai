"""Test per il router workspace: invalidazione briefing sul diario e allineamento
di ws_inventario_articoli agli helper di progetto (filter_active + fetch_all).

Contesto (audit §3, 8/8/2026). Due difetti distinti:

1. `ws_diario_crea` non invalidava lo snapshot briefing, mentre `ws_diario_aggiorna`
   e `ws_diario_elimina` lo facevano. Non e' cosmetica: il briefing ha il topic
   `appuntamento_imminente`, alimentato da `_briefing_appuntamenti` che legge
   `diario_eventi` per la data ODIERNA, e lo snapshot e' servito cache-first da
   `daily_briefing_state`. Creare un appuntamento per oggi non lo faceva comparire.
   I test difendono la SIMMETRIA dei tre percorsi: se un domani qualcuno aggiunge
   un quarto endpoint di scrittura sul diario senza invalidare, il test sulla
   simmetria non lo copre — ma quelli sui tre esistenti non permettono regressioni.

2. `ws_inventario_articoli` filtrava il soft-delete con `.is_("deleted_at","null")`
   inline invece di `filter_active()`, e reimplementava a mano il loop di
   paginazione invece di usare `fetch_all`. Il fake Supabase qui APPLICA davvero i
   filtri (eq/in_/deleted_at) invece di registrarli: un fake che li registra senza
   applicarli lascerebbe passare verde una perdita di isolamento multi-tenant, ed
   e' esattamente l'errore trovato dal code-reviewer su upload_handler (PR #17).
   Per lo stesso motivo le righe di prova includono un secondo utente, un'altra
   sede e una riga soft-deleted: senza quelle il filtro non ha nulla da escludere e
   il test resta vacuo comunque.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.routers.workspace as workspace


# ---------------------------------------------------------------------------
# Fake Supabase che FILTRA davvero
# ---------------------------------------------------------------------------

class _FakeQuery:
    """Builder che applica i predicati alle righe, invece di solo registrarli."""

    def __init__(self, rows, recorder):
        self._rows = list(rows)
        self._rec = recorder
        self._negate_next_in = False

    # --- predicati che filtrano davvero ---
    def eq(self, campo, valore):
        self._rec.setdefault("eq", []).append((campo, valore))
        self._rows = [r for r in self._rows if str(r.get(campo)) == str(valore)]
        return self

    def is_(self, campo, valore):
        # `not_` e' consumato SOLO da in_(): se arrivasse qui, questo fake
        # restituirebbe l'opposto di PostgREST (che con .not_.is_(x,"null")
        # ESCLUDE i NULL) e lascerebbe il flag armato per il filtro successivo.
        # Meglio fallire subito che dare verde a un test che asserisce il
        # contrario del vero — le query cestino usano proprio `.not_.is_`.
        if self._negate_next_in:
            raise NotImplementedError(
                "_FakeQuery non supporta .not_.is_(): implementa la negazione "
                "prima di usarlo per una query cestino/retention."
            )
        self._rec.setdefault("is_", []).append((campo, valore))
        if valore == "null":
            self._rows = [r for r in self._rows if r.get(campo) is None]
        return self

    @property
    def not_(self):
        self._negate_next_in = True
        return self

    def in_(self, campo, valori):
        negato = self._negate_next_in
        self._negate_next_in = False
        self._rec.setdefault("not_in_" if negato else "in_", []).append((campo, list(valori)))
        if negato:
            self._rows = [r for r in self._rows if r.get(campo) not in valori]
        else:
            self._rows = [r for r in self._rows if r.get(campo) in valori]
        return self

    # --- passanti ---
    def select(self, *a, **k):
        return self

    def order(self, campo, desc=False, **k):
        self._rec.setdefault("order", []).append(campo)
        self._rows.sort(key=lambda r: (r.get(campo) is None, r.get(campo)), reverse=desc)
        return self

    def range(self, start, end):
        self._rec.setdefault("range", []).append((start, end))
        self._sl = (start, end)
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def insert(self, payload):
        self._rec.setdefault("ops", []).append("insert")
        self._payload = payload
        return self

    def update(self, payload):
        self._rec.setdefault("ops", []).append("update")
        self._payload = payload
        return self

    def delete(self):
        self._rec.setdefault("ops", []).append("delete")
        return self

    def execute(self):
        sl = getattr(self, "_sl", None)
        rows = self._rows[sl[0]: sl[1] + 1] if sl else self._rows
        return SimpleNamespace(data=rows, count=len(self._rows))


class _FakeClient:
    def __init__(self, tabelle):
        self._tabelle = tabelle
        self.rec = {}

    def table(self, nome):
        self.rec.setdefault("tables", []).append(nome)
        return _FakeQuery(self._tabelle.get(nome, []), self.rec.setdefault(nome, {}))


def _patch_ws(client, user_id="user-1", rid="rist-1"):
    return patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": user_id}),
        _get_supabase_client=MagicMock(return_value=client),
        _get_ristorante_id_for_user=MagicMock(return_value=rid),
    )


# ---------------------------------------------------------------------------
# 1. Diario -> invalidazione briefing
# ---------------------------------------------------------------------------

class TestDiarioInvalidaBriefing:
    """I tre percorsi di scrittura sul diario invalidano lo snapshot di oggi."""

    def _body_crea(self):
        return workspace.NuovoEventoDiarioBody(
            data_evento="2026-08-08", titolo="Consegna fornitore", colore="blue"
        )

    def test_crea_invalida_il_briefing(self):
        client = _FakeClient({"diario_eventi": []})
        spia = MagicMock()
        with _patch_ws(client), patch(
            "services.daily_briefing_service.invalidate_today_briefing", spia
        ):
            workspace.ws_diario_crea(self._body_crea(), authorization="Bearer t")
        spia.assert_called_once()
        # Deve invalidare per l'utente E la sede giusti, non a caso.
        args = spia.call_args.args
        assert args[0] == "user-1"
        assert args[1] == "rist-1"

    def test_aggiorna_invalida_il_briefing(self):
        client = _FakeClient({"diario_eventi": [{"id": "e1", "ristorante_id": "rist-1"}]})
        spia = MagicMock()
        body = workspace.AggiornaEventoDiarioBody(titolo="Nuovo titolo")
        with _patch_ws(client), patch(
            "services.daily_briefing_service.invalidate_today_briefing", spia
        ):
            workspace.ws_diario_aggiorna("e1", body, authorization="Bearer t")
        spia.assert_called_once()

    def test_elimina_invalida_il_briefing(self):
        client = _FakeClient({"diario_eventi": [{"id": "e1", "ristorante_id": "rist-1"}]})
        spia = MagicMock()
        with _patch_ws(client), patch(
            "services.daily_briefing_service.invalidate_today_briefing", spia
        ):
            workspace.ws_diario_elimina("e1", authorization="Bearer t")
        spia.assert_called_once()

    def test_invalidazione_fallita_non_blocca_la_scrittura(self):
        """Best-effort: l'evento si crea anche se l'invalidazione esplode."""
        client = _FakeClient({"diario_eventi": []})
        with _patch_ws(client), patch(
            "services.daily_briefing_service.invalidate_today_briefing",
            MagicMock(side_effect=RuntimeError("boom")),
        ):
            out = workspace.ws_diario_crea(self._body_crea(), authorization="Bearer t")
        assert out == {}  # nessuna riga tornata dal fake, ma nessuna eccezione
        assert "insert" in client.rec["diario_eventi"]["ops"]

    def test_tutti_i_percorsi_di_scrittura_diario_sono_simmetrici(self):
        """Guardia sulla simmetria: nessuno dei tre scrive senza invalidare."""
        import inspect
        for fn in (
            workspace.ws_diario_crea,
            workspace.ws_diario_aggiorna,
            workspace.ws_diario_elimina,
        ):
            src = inspect.getsource(fn)
            assert "invalidate_today_briefing" in src, (
                f"{fn.__name__} scrive sul diario senza invalidare il briefing"
            )


# ---------------------------------------------------------------------------
# 2. ws_inventario_articoli -> filter_active + fetch_all
# ---------------------------------------------------------------------------

def _riga(desc, user="user-1", rid="rist-1", cat="CARNE", deleted=None, data="2026-08-01"):
    return {
        "descrizione": desc,
        "prezzo_unitario": 1.0,
        "unita_misura": "KG",
        "categoria": cat,
        "data_documento": data,
        "user_id": user,
        "ristorante_id": rid,
        "deleted_at": deleted,
    }


class TestInventarioArticoliIsolamento:
    """Il soft-delete e l'isolamento multi-tenant sono applicati davvero."""

    def test_esclude_soft_deleted_altro_utente_e_altra_sede(self):
        client = _FakeClient({"fatture": [
            _riga("MIA"),
            _riga("CESTINATA", deleted="2026-08-02T10:00:00Z"),
            _riga("ALTRO UTENTE", user="user-2"),
            _riga("ALTRA SEDE", rid="rist-2"),
        ]})
        with _patch_ws(client):
            out = workspace.ws_inventario_articoli(authorization="Bearer t")
        nomi = {a["nome"] for a in out["articoli"]}
        assert nomi == {"MIA"}

    def test_esclude_le_categorie_di_spesa_generale(self):
        from config.constants import CATEGORIE_SPESE_GENERALI
        generale = next(iter(CATEGORIE_SPESE_GENERALI))
        client = _FakeClient({"fatture": [
            _riga("ARTICOLO FOOD"),
            _riga("BOLLETTA", cat=generale),
        ]})
        with _patch_ws(client):
            out = workspace.ws_inventario_articoli(authorization="Bearer t")
        assert {a["nome"] for a in out["articoli"]} == {"ARTICOLO FOOD"}

    def test_usa_filter_active_non_il_predicato_inline(self):
        """La guardia di dominio cerca filter_active: l'inline le sfuggiva."""
        import inspect
        src = inspect.getsource(workspace.ws_inventario_articoli)
        assert "filter_active" in src
        assert '.is_("deleted_at"' not in src

    def test_pagina_oltre_le_1000_righe(self):
        """Con >1 pagina il risultato non si ferma alla prima (cap PostgREST)."""
        righe = [_riga(f"ART{i:05d}") for i in range(1500)]
        client = _FakeClient({"fatture": righe})
        with _patch_ws(client):
            out = workspace.ws_inventario_articoli(authorization="Bearer t")
        assert len(out["articoli"]) == 1500
        # Deve aver chiesto piu' di una pagina, non una sola select gigante.
        assert len(client.rec["fatture"]["range"]) >= 2

    def test_usa_fetch_all_non_un_loop_a_mano(self):
        import inspect
        src = inspect.getsource(workspace.ws_inventario_articoli)
        assert "fetch_all" in src
        assert "while True" not in src

    def test_deduplica_per_descrizione_tenendo_la_piu_recente(self):
        client = _FakeClient({"fatture": [
            _riga("POMODORO", data="2026-08-05"),
            _riga("POMODORO", data="2026-01-01"),
        ]})
        with _patch_ws(client):
            out = workspace.ws_inventario_articoli(authorization="Bearer t")
        assert len(out["articoli"]) == 1
