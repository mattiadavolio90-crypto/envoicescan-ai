"""Test dell'endpoint POST /api/riparto/manuale (services/routers/riparto.py).

Un costo di gruppo manuale (senza fattura, es. "Utenze sede centrale") nasce già
per-categoria: il campo `categoria` (ex `tipo` binario generale/fb) è obbligatorio
e validato con lo stesso guardrail delle righe da fattura
(`normalizza_categoria_richiesta`), così un costo manuale non può finire in "Da
Classificare" né aggirare la regola di dominio #2 su NOTE E DICITURE. `tipo`
(generale/fb, colonna storica usata per badge e filtri) si deriva dalla categoria,
non è più scelto separatamente dall'utente.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self):
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if name == "crea_riparto_con_quote":
            return SimpleNamespace(execute=lambda: SimpleNamespace(data="riparto-1"))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


_SEDI = [
    {"id": "sede-a", "nome_ristorante": "OFFSIDE SPORTS PUB"},
    {"id": "sede-b", "nome_ristorante": "OVERTIME"},
]


def _patch(sedi=_SEDI):
    sb = _FakeSB()
    p = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
        _post_scrittura_riparto=MagicMock(return_value=None),
    )
    return sb, p


def _body(categoria="MANUTENZIONE E ATTREZZATURE", importo=100.0, regola="equa", percentuali=None):
    return riparto.RipartoManualeBody(
        descrizione="Costo di prova",
        importo_totale=importo,
        categoria=categoria,
        anno=2026,
        mese=8,
        regola=regola,
        percentuali=percentuali,
    )


def _quote_scritte(sb):
    for nome, params in sb.rpc_calls:
        if nome == "crea_riparto_con_quote":
            return params["p_quote"]
    raise AssertionError("crea_riparto_con_quote non chiamata")


def _tipo_scritto(sb):
    for nome, params in sb.rpc_calls:
        if nome == "crea_riparto_con_quote":
            return params["p_tipo"]
    raise AssertionError("crea_riparto_con_quote non chiamata")


def test_categoria_spese_generali_deriva_tipo_generale():
    sb, p = _patch()
    with p:
        out = riparto.riparto_manuale(_body(categoria="MANUTENZIONE E ATTREZZATURE"), authorization="Bearer x")
    assert out["ok"] is True
    assert _tipo_scritto(sb) == "generale"
    for q in _quote_scritte(sb):
        assert q["categoria"] == "MANUTENZIONE E ATTREZZATURE"


def test_categoria_food_beverage_deriva_tipo_fb():
    sb, p = _patch()
    with p:
        riparto.riparto_manuale(_body(categoria="BIRRE"), authorization="Bearer x")
    assert _tipo_scritto(sb) == "fb"
    for q in _quote_scritte(sb):
        assert q["categoria"] == "BIRRE"


def test_quote_equa_sommano_importo_totale():
    sb, p = _patch()
    with p:
        riparto.riparto_manuale(_body(importo=100.0), authorization="Bearer x")
    quote = _quote_scritte(sb)
    assert len(quote) == 2
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(100.0)


@pytest.mark.parametrize("cat", ["Da Classificare", "Da Clasificare", "", "INVENTATA"])
def test_categorie_non_valide_rifiutate(cat):
    """Regola di dominio #1: un costo manuale non può nascere già "Da Classificare"
    né con una categoria inventata — sporcherebbe margini e report."""
    sb, p = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_manuale(_body(categoria=cat), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_note_e_diciture_rifiutata():
    """Regola di dominio #2: NOTE E DICITURE solo per importo zero. Un costo di
    gruppo è per definizione un importo positivo → mai ammessa qui."""
    sb, p = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_manuale(_body(categoria="NOTE E DICITURE"), authorization="Bearer x")
    assert exc.value.status_code == 422


def test_categoria_mancante_rifiutata_a_livello_pydantic():
    with pytest.raises(Exception):
        riparto.RipartoManualeBody(
            descrizione="x", importo_totale=10.0, anno=2026, mese=8,
        )


def test_importo_non_positivo_rifiutato():
    sb, p = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_manuale(_body(importo=0), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_account_con_una_sola_sede_rifiutato():
    sb, p = _patch(sedi=[_SEDI[0]])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_manuale(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_regola_percentuali_scrive_categoria_su_ogni_quota():
    sb, p = _patch()
    with p:
        riparto.riparto_manuale(
            _body(categoria="CARNE", regola="percentuali", percentuali={"sede-a": 70, "sede-b": 30}),
            authorization="Bearer x",
        )
    quote = _quote_scritte(sb)
    assert {q["categoria"] for q in quote} == {"CARNE"}
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(100.0)
