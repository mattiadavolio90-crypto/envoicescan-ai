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

_RIPARTO_MANUALE = {
    "id": "rip-man-1", "anno": 2026, "mese": 8, "origine": "manuale",
    "regola": "equa", "importo_totale": 200.0,
}

# Due categorie sulla STESSA sede: la configurazione che faceva collassare l'UPDATE
# in blocco su un duplicato di uq_riparto_quota_sede_categoria.
_QUOTE = [
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 60.0, "categoria": "UTENZE E LOCALI"},
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 40.0, "categoria": "SERVIZI E CONSULENZE"},
    {"ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 100.0, "categoria": "UTENZE E LOCALI"},
]


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
        if self._t == "riparto_costi_catena_quote":
            return SimpleNamespace(data=self._c.quote)
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, riparti, quote=None):
        self.riparti = riparti
        # Forma reale dopo l'esplosione per-categoria: una sede puo' avere piu'
        # quote, una per categoria. E' il caso che rompeva il vincolo UNIQUE.
        self.quote = _QUOTE if quote is None else quote
        self.updates = []
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
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


def _tipo_scritto(sb):
    """`tipo` passa dalla RPC quando ci sono quote, dall'UPDATE sul padre quando no."""
    rpc = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"]
    if rpc:
        return rpc[0][1]["p_tipo"]
    hdr = _update_su(sb, "riparto_costi_catena")
    return hdr[0][1]["tipo"] if hdr else None


def test_sentinella_riconosciuta_scrive_categoria_sulle_quote():
    """Il caso che prima dava 404: il sentinella va risolto per id."""
    sb, p = _patch()
    with p:
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")

    assert out["ok"] is True
    assert out["categoria"] == "MANUTENZIONE E ATTREZZATURE"
    # Le quote si riscrivono via RPC transazionale, non con un UPDATE in blocco:
    # quello violava uq_riparto_quota_sede_categoria quando una sede aveva piu'
    # categorie (APIError -> 500 opaco, 25/8/2026).
    rpc = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"]
    assert rpc, "le quote devono essere riscritte"
    assert rpc[0][1]["p_riparto_id"] == "rip-man-1"
    assert {q["categoria"] for q in rpc[0][1]["p_quote"]} == {"MANUTENZIONE E ATTREZZATURE"}


def test_tipo_header_riallineato_a_spese_generali():
    sb, p = _patch()
    with p:
        riparto.riparto_riga_categoria(_body(cat="UTENZE E LOCALI"), authorization="Bearer x")
    # `tipo` viaggia nella RPC transazionale insieme alle quote: header e quote
    # cambiano insieme o non cambiano affatto.
    assert _tipo_scritto(sb) == "generale"


def test_tipo_header_riallineato_a_fb():
    """Se resta 'generale' su una categoria F&B, badge e filtri mentono."""
    sb, p = _patch()
    with p:
        riparto.riparto_riga_categoria(_body(cat="BIRRE"), authorization="Bearer x")
    assert _tipo_scritto(sb) == "fb"


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


def test_quote_di_una_sede_su_piu_categorie_non_violano_il_vincolo():
    """Regressione 25/8/2026. `sede-a` ha due quote (UTENZE + SERVIZI): l'UPDATE in
    blocco le portava entrambe a `nuova_cat`, duplicando la terna di
    uq_riparto_quota_sede_categoria (riparto_id, ristorante_id, categoria).
    Postgres rifiutava, il worker non gestiva l'APIError e rispondeva 500 con corpo
    non-JSON — che l'utente leggeva come "Worker unreachable"."""
    sb, p = _patch()
    with p:
        out = riparto.riparto_riga_categoria(
            _body(cat="MANUTENZIONE E ATTREZZATURE"), authorization="Bearer x"
        )

    assert out["ok"] is True
    quote = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"][0][1]["p_quote"]
    terne = [(q["ristorante_id"], q["categoria"]) for q in quote]
    assert len(terne) == len(set(terne)), f"duplicati sulla terna: {terne}"
    # sede-a: 60+40 consolidati in una sola quota; sede-b resta 100.
    per_sede = {q["ristorante_id"]: q["quota_importo"] for q in quote}
    assert per_sede == {"sede-a": 100.0, "sede-b": 100.0}
