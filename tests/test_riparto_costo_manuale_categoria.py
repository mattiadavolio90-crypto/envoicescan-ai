"""Correzione categoria su un costo di gruppo MANUALE (senza fattura).

Un costo manuale ha `file_origine` NULL in tabella: le righe sintetiche proiettate
nel tab Articoli ricevono il sentinella "riparto:<uuid>"
(`services.riparto_service.SENTINELLA_RIPARTO_MANUALE`). Cercarlo per file_origine
in `riparto_costi_catena` non lo troverebbe mai → 404, e non esistono righe reali in
`fatture` da aggiornare: la categoria di un costo manuale vive SOLO sulle quote.

Da quando il costo manuale nasce categorizzato (form "Aggiungi costo di gruppo"),
questo è il caso normale, non un residuo: senza il ramo dedicato la correzione era
irraggiungibile dalla UI.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto
from services.riparto_service import SENTINELLA_RIPARTO_MANUALE


_SEDI = [
    {"id": "sede-a", "nome_ristorante": "OFFSIDE SPORTS PUB"},
    {"id": "sede-b", "nome_ristorante": "OVERTIME"},
]

_RIPARTO_MANUALE = {"id": "rip-man-1", "anno": 2026, "mese": 8, "origine": "manuale"}


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._eq = {}
        self._pending_update = None

    def select(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def range(self, *a, **k): return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def update(self, payload):
        self._pending_update = payload
        return self

    def execute(self):
        # .eq() arriva DOPO .update() nel builder PostgREST: i filtri vanno letti qui,
        # non al momento della update, altrimenti risultano sempre vuoti.
        if self._pending_update is not None:
            self._c.updates.append((self._t, self._pending_update, dict(self._eq)))
            return SimpleNamespace(data=[])
        if self._t == "riparto_costi_catena":
            # Il lookup del ramo manuale è per id, non per file_origine.
            if "id" in self._eq:
                match = [r for r in self._c.riparti if r["id"] == self._eq["id"]]
                return SimpleNamespace(data=match)
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, riparti):
        self.riparti = riparti
        self.updates = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


def _patch(riparti=None, sedi=_SEDI):
    sb = _FakeSB(riparti if riparti is not None else [_RIPARTO_MANUALE])
    p = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
        _require_catena=MagicMock(return_value=sedi),
        _post_scrittura_riparto=MagicMock(return_value=None),
    )
    return sb, p


def _body(cat="MANUTENZIONE E ATTREZZATURE", riparto_id="rip-man-1"):
    return riparto.RipartoRigaCategoriaBody(
        file_origine=f"{SENTINELLA_RIPARTO_MANUALE}{riparto_id}",
        descrizione="Utenze sede centrale",
        nuova_categoria=cat,
    )


def _update_su(sb, tabella):
    return [u for u in sb.updates if u[0] == tabella]


def test_sentinella_riconosciuta_scrive_categoria_sulle_quote():
    """Il caso che prima dava 404: il sentinella va risolto per id."""
    sb, p = _patch()
    with p:
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")

    assert out["ok"] is True
    assert out["categoria"] == "MANUTENZIONE E ATTREZZATURE"
    quote_upd = _update_su(sb, "riparto_costi_catena_quote")
    assert quote_upd, "le quote devono essere aggiornate"
    assert quote_upd[0][1] == {"categoria": "MANUTENZIONE E ATTREZZATURE"}
    assert quote_upd[0][2]["riparto_id"] == "rip-man-1"


def test_tipo_header_riallineato_a_spese_generali():
    sb, p = _patch()
    with p:
        riparto.riparto_riga_categoria(_body(cat="UTENZE E LOCALI"), authorization="Bearer x")
    hdr = _update_su(sb, "riparto_costi_catena")
    assert hdr and hdr[0][1] == {"tipo": "generale"}


def test_tipo_header_riallineato_a_fb():
    """Se resta 'generale' su una categoria F&B, badge e filtri mentono."""
    sb, p = _patch()
    with p:
        riparto.riparto_riga_categoria(_body(cat="BIRRE"), authorization="Bearer x")
    hdr = _update_su(sb, "riparto_costi_catena")
    assert hdr and hdr[0][1] == {"tipo": "fb"}


def test_riparto_inesistente_404():
    sb, p = _patch(riparti=[])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert exc.value.status_code == 404


@pytest.mark.parametrize("cat", ["Da Classificare", "Da Clasificare", "INVENTATA", ""])
def test_categoria_non_valida_rifiutata(cat):
    """Regola #1: nemmeno per un costo manuale l'utente può imporre Da Classificare."""
    sb, p = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(cat=cat), authorization="Bearer x")
    assert exc.value.status_code == 400
    assert not sb.updates, "nessuna scrittura se la categoria è rifiutata"


def test_note_e_diciture_rifiutata_su_costo_manuale():
    """Regola #2: un costo di gruppo è per definizione un importo positivo."""
    sb, p = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(cat="📝 NOTE E DICITURE"), authorization="Bearer x")
    assert exc.value.status_code == 422
    assert not sb.updates


def test_sentinella_definita_una_volta_sola():
    """Il prefisso è condiviso fra chi lo produce (riparto_service) e chi lo consuma
    (router): se divergono, la correzione torna a dare 404 in silenzio."""
    assert riparto._SENTINELLA_RIPARTO_MANUALE is SENTINELLA_RIPARTO_MANUALE
