"""Fase 5 (D5): la correzione manuale insegna su TUTTI i percorsi, e lo dice.

Prima: solo categoria-batch scriveva in `prodotti_utente` — inline, con la
descrizione grezza e `classificato_da: "User"`, che i check `startswith('Manuale')`
NON riconoscevano (319 voci reali a DB il 3/9): l'auto-save poteva sovrascrivere
una correzione fatta a mano. La PATCH singola riga e riparto/riga-categoria non
imparavano niente. E se la scrittura falliva, la risposta era comunque `ok: True`.

Adesso: una sola funzione canonica (`salva_correzione_in_memoria_locale`) su
tutti e tre i percorsi, protezione estesa alla grafia legacy `User`, e il campo
`memoria_aggiornata` nella risposta dice la verità.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.fatture as fatture
import services.routers.riparto as riparto
from services.ai_service import (
    _e_override_manuale,
    _esiste_override_manuale_locale,
    flush_pending_local_saves,
)


# ─── Il criterio di protezione, sulle grafie REALI misurate a DB (3/9) ───────

@pytest.mark.parametrize("grafia,atteso", [
    ("Manuale (ghyl.888@gmail.com)", True),
    ("Manuale (reviewer-agent)", True),
    ("User", True),                    # legacy di categoria-batch: 319 voci reali
    ("keyword-auto", False),
    ("AI (auto-upload)", False),
    ("AI (auto)", False),
    ("admin-audit", False),
    (None, False),
    ("", False),
])
def test_criterio_override_manuale(grafia, atteso):
    assert _e_override_manuale(grafia) is atteso


def test_una_voce_user_blocca_l_autosave_batch():
    """flush_pending_local_saves NON deve sovrascrivere una correzione `User`."""

    class _Q:
        def __init__(self, sb):
            self._sb = sb

        def select(self, *_a, **_k): return self
        def eq(self, *_a, **_k): return self

        def in_(self, _col, descs):
            self._descs = list(descs)
            return self

        def execute(self):
            return SimpleNamespace(data=[
                {"descrizione": "POLLO KG1", "classificato_da": "User"},
            ])

        def upsert(self, payload, **_k):
            self._sb.upserted.extend(payload)
            return self

    class _SB:
        def __init__(self):
            self.upserted = []

        def table(self, _):
            return _Q(self)

    sb = _SB()
    n = flush_pending_local_saves(
        [
            {"descrizione": "POLLO KG1", "categoria": "CARNE"},
            {"descrizione": "COCA COLA 33CL", "categoria": "BEVANDE"},
        ],
        user_id="u1",
        supabase_client=sb,
    )
    descs = [r["descrizione"] for r in sb.upserted]
    assert "POLLO KG1" not in descs, "la correzione manuale `User` è stata sovrascritta"
    assert descs == ["COCA COLA 33CL"]
    assert n == 1


def test_una_voce_user_e_un_override_manuale_locale():
    class _Q:
        def select(self, *_a, **_k): return self
        def eq(self, *_a, **_k): return self
        def in_(self, *_a, **_k): return self

        def execute(self):
            return SimpleNamespace(data=[{"descrizione": "X", "classificato_da": "User"}])

    class _SB:
        def table(self, _):
            return _Q()

    assert _esiste_override_manuale_locale("u1", "X", _SB()) is True


# ─── I tre percorsi usano la funzione canonica, e la risposta dice la verità ──

class _QueryFatture:
    def __init__(self, sb, table):
        self._sb = sb
        self._t = table
        self._update = None

    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def is_(self, *_a, **_k): return self
    def in_(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self

    def update(self, payload):
        self._update = payload
        return self

    def execute(self):
        if self._update is not None:
            return SimpleNamespace(data=[{"id": 1}])
        if self._t == "fatture":
            return SimpleNamespace(data=self._sb.rows)
        return SimpleNamespace(data=[])


class _SBFatture:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _QueryFatture(self, name)


def _patch_fatture(sb, salva):
    return patch.multiple(
        fatture,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1", "email": "cli@x.it"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _resolve_ristorante_id=MagicMock(return_value="sede-1"),
        _invalidate_fatture_rows_cache=MagicMock(),
        _salva_correzione_memoria=salva,
    )


@pytest.mark.parametrize("esito_memoria", [True, False])
def test_categoria_batch_dice_se_ha_imparato(esito_memoria):
    sb = _SBFatture([{"id": 1, "totale_riga": 10.0, "prezzo_unitario": 10.0}])
    salva = MagicMock(return_value=esito_memoria)
    with _patch_fatture(sb, salva):
        out = fatture.categoria_batch(
            fatture.CategoriaBatchRequest(descrizione="POLLO KG1", nuova_categoria="CARNE"),
            authorization="Bearer x",
        )
    assert out["ok"] is True
    assert out["memoria_aggiornata"] is esito_memoria
    assert salva.call_args.kwargs["descrizione"] == "POLLO KG1"
    assert salva.call_args.kwargs["nuova_categoria"] == "CARNE"
    assert salva.call_args.kwargs["user_email"] == "cli@x.it"


def test_categoria_batch_su_zero_righe_non_impara():
    """0 righe toccate (es. riga di gruppo): insegnare sarebbe un falso successo."""

    class _SBVuoto(_SBFatture):
        def table(self, name):
            q = _QueryFatture(self, name)
            _orig = q.execute

            def execute():
                if q._update is not None:
                    return SimpleNamespace(data=[])
                return _orig()
            q.execute = execute
            return q

    salva = MagicMock(return_value=True)
    with _patch_fatture(_SBVuoto([]), salva):
        out = fatture.categoria_batch(
            fatture.CategoriaBatchRequest(descrizione="POLLO KG1", nuova_categoria="CARNE"),
            authorization="Bearer x",
        )
    assert out["righe_aggiornate"] == 0
    assert out["memoria_aggiornata"] is False
    salva.assert_not_called()


def test_patch_riga_ora_impara_con_la_descrizione_della_riga():
    """Il percorso che non insegnava niente: la stessa descrizione sulla fattura
    successiva tornava sbagliata."""
    sb = _SBFatture([{"id": 7, "totale_riga": 5.0, "prezzo_unitario": 5.0,
                      "descrizione": "MOZZARELLA KG1"}])
    salva = MagicMock(return_value=True)
    with _patch_fatture(sb, salva):
        out = fatture.aggiorna_categoria_riga(
            7,
            fatture.AggiornaCategoriaRequest(categoria="LATTICINI"),
            authorization="Bearer x",
        )
    assert out["memoria_aggiornata"] is True
    assert salva.call_args.kwargs["descrizione"] == "MOZZARELLA KG1"
    assert salva.call_args.kwargs["nuova_categoria"] == "LATTICINI"


def test_riparto_riga_categoria_ora_impara():
    from tests.test_riparto_riga_categoria import _FakeSB, _RIPARTO, _SEDI

    sb = _FakeSB([_RIPARTO], [{"id": 11, "totale_riga": 149.0, "prezzo_unitario": 149.0}])
    salva = MagicMock(return_value=True)
    esplodi = MagicMock(return_value=True)
    with patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1", "email": "cli@x.it"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI),
        _post_scrittura_riparto=MagicMock(return_value=True),
        _salva_correzione_memoria=salva,
    ), patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        out = riparto.riparto_riga_categoria(
            riparto.RipartoRigaCategoriaBody(
                file_origine="IT123_x.xml", descrizione="1 ACCONTO", nuova_categoria="CARNE",
            ),
            authorization="Bearer x",
        )
    assert out["memoria_aggiornata"] is True
    assert salva.call_args.kwargs["descrizione"] == "1 ACCONTO"
