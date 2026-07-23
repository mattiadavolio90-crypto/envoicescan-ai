"""Test guardia: la coda "da assegnare" allega la regola-fornitore memorizzata.

Contesto (23/07/2026, richiesta OFFSIDE): il cliente ha molte fatture di gruppo
da smistare a mano. Se per un fornitore ha già detto "fai sempre così" (regola in
riparto_regole_fornitore), la coda deve arrivare con quella regola già allegata,
così l'UI evidenzia la fattura e offre la conferma rapida ("Dividi come al solito").

La regola PROPONE, non applica mai da sola: qui verifichiamo solo che il dato arrivi
attaccato alla voce giusta (match per P.IVA cedente), e che la coda resti pienamente
usabile se la lettura delle regole fallisce (la regola è un di più, non un requisito).

Copre:
  - voce con fornitore che ha una regola attiva → regola_fornitore valorizzata;
  - voce senza regola → regola_fornitore None;
  - match per P.IVA (non per nome fornitore);
  - una sola query regole per tutto il lotto (no N+1);
  - lettura regole in errore → coda comunque servita, regola_fornitore None ovunque.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.routers.fatture as fatture


class _RegoleQuery:
    """Query builder minimale per riparto_regole_fornitore: registra la lista di
    P.IVA passata a .in_() così il test può verificare il singolo colpo di lettura."""

    def __init__(self, client):
        self._c = client

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self

    def in_(self, col, values):
        self._c.in_calls.append(list(values))
        return self

    def execute(self):
        if self._c.regole_raise:
            raise RuntimeError("boom regole")
        return SimpleNamespace(data=self._c.regole_rows)


class _CodaQuery:
    def __init__(self, client):
        self._c = client

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self

    def execute(self):
        return SimpleNamespace(data=self._c.coda_rows)


class _FakeSB:
    def __init__(self, coda_rows, regole_rows, regole_raise=False):
        self.coda_rows = coda_rows
        self.regole_rows = regole_rows
        self.regole_raise = regole_raise
        self.in_calls = []

    def table(self, name):
        if name == "riparto_regole_fornitore":
            return _RegoleQuery(self)
        return _CodaQuery(self)


def _coda_row(qid, piva):
    return {
        "id": qid,
        "piva_raw": piva,
        "payload_meta": {"piva_cedente": piva, "numero_fattura": f"n{qid}",
                         "data_fattura": "2026-06-01", "importo_totale": 100.0,
                         "indirizzo_destinatario": "Via X"},
        "created_at": "2026-06-01T00:00:00Z",
        "xml_content": None,
    }


def _patch(sb):
    return patch.multiple(
        fatture,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _denominazione_cedente=MagicMock(return_value=None),
    )


def test_voce_con_regola_riceve_criterio():
    coda = [_coda_row(1, "111"), _coda_row(2, "222")]
    regole = [{"fornitore": "111", "regola": "equa", "tipo": "generale", "percentuali": None}]
    sb = _FakeSB(coda, regole)
    with _patch(sb):
        out = fatture.fatture_da_assegnare(authorization="Bearer x")
    by_id = {i["queue_id"]: i for i in out["items"]}
    assert by_id[1]["regola_fornitore"] == {"regola": "equa", "tipo": "generale", "percentuali": None}
    assert by_id[2]["regola_fornitore"] is None


def test_match_per_piva_non_per_nome():
    # La regola è chiave P.IVA: una P.IVA che non compare fra le regole → None.
    coda = [_coda_row(1, "999")]
    regole = [{"fornitore": "111", "regola": "equa", "tipo": "generale", "percentuali": None}]
    sb = _FakeSB(coda, regole)
    with _patch(sb):
        out = fatture.fatture_da_assegnare(authorization="Bearer x")
    assert out["items"][0]["regola_fornitore"] is None


def test_una_sola_query_regole_per_lotto():
    # Due fatture, tre voci (una P.IVA ripetuta): un solo colpo di lettura regole,
    # con le P.IVA distinte. Niente N+1.
    coda = [_coda_row(1, "111"), _coda_row(2, "222"), _coda_row(3, "111")]
    sb = _FakeSB(coda, [])
    with _patch(sb):
        fatture.fatture_da_assegnare(authorization="Bearer x")
    assert len(sb.in_calls) == 1
    assert sorted(sb.in_calls[0]) == ["111", "222"]


def test_percentuali_passano_intatte():
    coda = [_coda_row(1, "111")]
    regole = [{"fornitore": "111", "regola": "percentuali", "tipo": "fb",
               "percentuali": {"sede-a": 70, "sede-b": 30}}]
    sb = _FakeSB(coda, regole)
    with _patch(sb):
        out = fatture.fatture_da_assegnare(authorization="Bearer x")
    rf = out["items"][0]["regola_fornitore"]
    assert rf["regola"] == "percentuali"
    assert rf["tipo"] == "fb"
    assert rf["percentuali"] == {"sede-a": 70, "sede-b": 30}


def test_errore_lettura_regole_non_rompe_la_coda():
    # La regola è un di più: se la lettura fallisce la coda resta servita per intero,
    # con regola_fornitore None ovunque. Nessuna fattura si perde.
    coda = [_coda_row(1, "111"), _coda_row(2, "222")]
    sb = _FakeSB(coda, [], regole_raise=True)
    with _patch(sb):
        out = fatture.fatture_da_assegnare(authorization="Bearer x")
    assert out["count"] == 2
    assert all(i["regola_fornitore"] is None for i in out["items"])


def test_coda_vuota_non_interroga_le_regole():
    sb = _FakeSB([], [])
    with _patch(sb):
        out = fatture.fatture_da_assegnare(authorization="Bearer x")
    assert out == {"items": [], "count": 0}
    assert sb.in_calls == []
