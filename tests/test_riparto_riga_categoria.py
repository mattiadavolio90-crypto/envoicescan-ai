"""Test di PATCH /api/riparto/riga-categoria (services/routers/riparto.py).

Contesto: le righe di una fattura di struttura vivono sulla SEDE TECNICA
("Costi comuni di gruppo"), non sul punto vendita. /api/fatture/categoria-batch
filtra per ristorante_id del PV → match su 0 righe, e la sede tecnica non è
selezionabile (account.py). Risultato: la categoria di una riga ripartita non era
correggibile da nessuna UI — 124 righe per 18.093 € bloccate in "Da Classificare"
sull'account OFFSIDE al 24/8/2026.

Questo endpoint scrive sulle righe reali per (user_id, file_origine, descrizione) e
ri-esplode le quote con forza=True, così il MOL non resta sulla categoria vecchia.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


_SEDI = [
    {"id": "sede-a", "nome_ristorante": "OFFSIDE SPORTS PUB"},
    {"id": "sede-b", "nome_ristorante": "OVERTIME"},
]

_RIPARTO = {"id": "riparto-1", "anno": 2026, "mese": 7}


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._slice = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, col, vals):
        self._c.in_filters.append((self._t, col, vals))
        return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def range(self, start, end):
        # fetch_all pagina con .range(): affettare davvero, altrimenti restituire
        # sempre la pagina piena farebbe ciclare il paginatore all'infinito.
        self._slice = (start, end + 1)
        return self

    def update(self, payload):
        self._c.updates.append((self._t, payload))
        return self

    def execute(self):
        if self._t == "riparto_costi_catena":
            data = self._c.riparti
        elif self._t == "fatture":
            data = self._c.righe
        else:
            data = []
        if self._slice is not None:
            data = data[self._slice[0]:self._slice[1]]
        return SimpleNamespace(data=data)


class _FakeSB:
    def __init__(self, riparti, righe):
        self.riparti = riparti
        self.righe = righe
        self.updates = []
        self.in_filters = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


def _patch(riparti=None, righe=None, sedi=_SEDI):
    sb = _FakeSB(
        riparti if riparti is not None else [_RIPARTO],
        righe if righe is not None else [{"id": 11, "totale_riga": 149.0, "prezzo_unitario": 149.0}],
    )
    esplodi = MagicMock(return_value=True)
    p = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
        _post_scrittura_riparto=MagicMock(return_value=None),
    )
    return sb, p, esplodi


def _body(cat="CARNE", file_origine="IT123_x.xml", descrizione="1 ACCONTO"):
    return riparto.RipartoRigaCategoriaBody(
        file_origine=file_origine, descrizione=descrizione, nuova_categoria=cat
    )


def test_corregge_la_riga_reale_e_riesplode_le_quote():
    sb, p, esplodi = _patch()
    with p, patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")

    assert out["ok"] is True and out["categoria"] == "CARNE"
    assert ("fatture", {"categoria": "CARNE", "needs_review": False}) in sb.updates
    # forza=True: senza, le quote resterebbero sulla categoria vecchia.
    assert esplodi.call_args.kwargs.get("forza") is True


def test_risposta_nomina_tutte_le_sedi_impattate():
    """Il cliente deve sapere che la correzione vale anche per l'altra sede."""
    sb, p, esplodi = _patch()
    with p, patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert out["sedi_impattate"] == ["OFFSIDE SPORTS PUB", "OVERTIME"]


def test_ricalcolo_mol_invocato_sul_periodo_del_riparto():
    sb, p, esplodi = _patch()
    post = MagicMock(return_value=None)
    with patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI),
        _post_scrittura_riparto=post,
    ), patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert post.call_args[0][2:] == (2026, 7)


@pytest.mark.parametrize("cat", ["Da Classificare", "Da Clasificare", "", "INVENTATA"])
def test_categorie_non_valide_rifiutate(cat):
    """Regola di dominio #1: "Da Classificare" è uno stato dell'AI, non una scelta
    dell'utente; una categoria inventata sporcherebbe margini e report."""
    sb, p, esplodi = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(cat=cat), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_note_e_diciture_rifiutate_su_riga_con_importo():
    """Regola di dominio #2: NOTE E DICITURE solo su totale_riga == 0."""
    sb, p, esplodi = _patch(righe=[{"id": 11, "totale_riga": 149.0, "prezzo_unitario": 149.0}])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(cat="NOTE E DICITURE"), authorization="Bearer x")
    assert exc.value.status_code == 422


def test_note_e_diciture_ammesse_su_riga_a_importo_zero():
    sb, p, esplodi = _patch(righe=[{"id": 11, "totale_riga": 0, "prezzo_unitario": 0}])
    with p, patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        out = riparto.riparto_riga_categoria(
            _body(cat="NOTE E DICITURE"), authorization="Bearer x"
        )
    assert out["categoria"] == "📝 NOTE E DICITURE"


def test_documento_senza_riparto_404():
    sb, p, esplodi = _patch(riparti=[])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert exc.value.status_code == 404


def test_riga_inesistente_404():
    sb, p, esplodi = _patch(righe=[])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert exc.value.status_code == 404


def test_account_con_una_sola_sede_rifiutato():
    """Gating catena: senza 2+ sedi non esistono costi di gruppo."""
    sb, p, esplodi = _patch(sedi=[_SEDI[0]])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_parametri_vuoti_rifiutati():
    sb, p, esplodi = _patch()
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(_body(descrizione="  "), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_esplosione_fallita_non_fa_fallire_la_correzione():
    """La riga è già scritta: un errore nella ri-esplosione non deve rollbackare la
    correzione né saltare il ricalcolo del MOL (best-effort, come altrove nel router)."""
    sb, p, _ = _patch()
    boom = MagicMock(side_effect=RuntimeError("giù"))
    with p, patch("services.riparto_service.esplodi_quote_per_categoria", boom):
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")
    assert out["ok"] is True


# ─── Regressione: "Worker unreachable" sulle righe ripartite (25/8/2026) ─────────
# Il cliente non riusciva a cambiare categoria a NESSUNA riga ripartita: toast
# "Worker unreachable" in 1-3 secondi (quindi non un timeout, che scatta a 12s).
# Sotto c'erano due difetti distinti, entrambi coperti qui.


def test_ricalcolo_quote_fallito_non_fa_fallire_la_scrittura():
    """_post_scrittura_riparto girava DOPO l'UPDATE ma rilanciava HTTPException(500)
    se la RPC falliva: la categoria era già salvata e il cliente leggeva un errore.
    Peggio, il worker non ha exception handler globale → quel 500 tornava con corpo
    non-JSON, che lato Next diventava il fuorviante "Worker unreachable"."""
    sb, p, esplodi = _patch()
    with patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI),
        _invalidate_fatture_rows_cache=MagicMock(),
    ), patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        sb.rpc = MagicMock(side_effect=RuntimeError("RPC giù"))
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")

    assert out["ok"] is True, "la categoria è già scritta: non si dichiara fallito tutto"
    assert out["ricalcolo_quote_ok"] is False, "ma il client deve poterlo dire all'utente"
    assert ("fatture", {"categoria": "CARNE", "needs_review": False}) in sb.updates


def test_ricalcolo_quote_ok_true_quando_la_rpc_riesce():
    """Contro-prova del test precedente: con la RPC sana il flag è True, così un
    False significa davvero "ricalcolo fallito" e non "flag sempre spento"."""
    sb, p, esplodi = _patch()
    with patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI),
        _invalidate_fatture_rows_cache=MagicMock(),
    ), patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        out = riparto.riparto_riga_categoria(_body(), authorization="Bearer x")

    assert out["ricalcolo_quote_ok"] is True


def test_riga_sintetica_di_quota_corretta_sulle_quote_non_404():
    """Le righe sintetiche (_proietta_riparto, ramo senza righe reali) hanno una
    descrizione GENERATA che non esiste in `fatture`: il lookup per descrizione non
    poteva trovarla e l'endpoint rispondeva 404 su una riga legittima. La loro
    categoria vive solo sulle quote, come per un costo manuale."""
    from services.riparto_service import DESCR_QUOTA_SINTETICA_PREFIX

    sb, p, esplodi = _patch(righe=[])  # nessuna riga reale: è il caso sintetico
    with p, patch("services.riparto_service.esplodi_quote_per_categoria", esplodi):
        out = riparto.riparto_riga_categoria(
            _body(descrizione=f"{DESCR_QUOTA_SINTETICA_PREFIX}UTENZE E LOCALI"),
            authorization="Bearer x",
        )

    assert out["ok"] is True
    # La categoria finisce sulle QUOTE (non su `fatture`), riscritte in transazione:
    # l'UPDATE in blocco di prima violava uq_riparto_quota_sede_categoria.
    assert out["categoria"] == "CARNE"
    assert not any(t == "fatture" for t, _ in sb.updates)


def test_descrizione_inesistente_resta_404():
    """Il fallback sintetico non deve trasformare ogni 404 in un falso successo."""
    sb, p, esplodi = _patch(righe=[])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_riga_categoria(
            _body(descrizione="PRODOTTO CHE NON ESISTE"), authorization="Bearer x"
        )
    assert exc.value.status_code == 404


# ─── Regressione: APIError sul vincolo UNIQUE delle quote (25/8/2026) ────────────
# uq_riparto_quota_sede_categoria e' UNIQUE (riparto_id, ristorante_id, categoria).
# Dall'esplosione per-categoria (24/7) una sede puo' avere N quote, una per categoria
# (nei dati reali fino a 10). _correggi_categoria_costo_manuale le riscriveva TUTTE a
# `nuova_cat` con un solo UPDATE: le N righe collassavano sulla stessa terna e il
# vincolo saltava. L'APIError non era gestito e il worker rispondeva 500 con corpo
# non-JSON — che lato Next diventava il fuorviante "Worker unreachable".


class _QueryQuote(_Query):
    """_Query + supporto alle quote e alla RPC di sostituzione."""

    def execute(self):
        if self._t == "riparto_costi_catena_quote":
            data = self._c.quote
            if self._slice is not None:
                data = data[self._slice[0]:self._slice[1]]
            return SimpleNamespace(data=data)
        return super().execute()


class _FakeSBQuote(_FakeSB):
    def __init__(self, riparti, righe, quote):
        super().__init__(riparti, righe)
        self.quote = quote
        self.rpc_calls = []

    def table(self, name):
        return _QueryQuote(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data="riparto-1"))


_RIPARTO_MANUALE = {
    "id": "riparto-1", "anno": 2026, "mese": 7,
    "origine": "manuale", "regola": "equa", "importo_totale": 300.0,
}

# Due sedi x tre categorie: la forma reale dopo l'esplosione per-categoria.
_QUOTE_MULTI = [
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 30.0, "categoria": "CARNE"},
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 70.0, "categoria": "PESCE"},
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 50.0, "categoria": "SALUMI"},
    {"ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 40.0, "categoria": "CARNE"},
    {"ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 60.0, "categoria": "PESCE"},
    {"ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 50.0, "categoria": "SALUMI"},
]


def _patch_quote(quote=None):
    sb = _FakeSBQuote([_RIPARTO_MANUALE], [], _QUOTE_MULTI if quote is None else quote)
    p = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI),
        _invalidate_fatture_rows_cache=MagicMock(),
    )
    return sb, p


def test_quote_multi_categoria_consolidate_una_per_sede():
    """Il fix: N quote per sede diventano UNA, cosi' la terna del vincolo e' unica."""
    sb, p = _patch_quote()
    with p:
        out = riparto.riparto_riga_categoria(
            _body(file_origine="riparto:riparto-1", descrizione="Quota"),
            authorization="Bearer x",
        )

    assert out["ok"] is True
    rpc = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"]
    assert rpc, "le quote vanno riscritte in transazione, non con un UPDATE in blocco"
    quote_nuove = rpc[0][1]["p_quote"]

    terne = [(q["ristorante_id"], q["categoria"]) for q in quote_nuove]
    assert len(terne) == len(set(terne)), f"duplicati sulla terna del vincolo: {terne}"
    assert len(quote_nuove) == 2, "una quota per sede"


def test_consolidamento_conserva_importo_totale_per_sede():
    """Il consolidamento somma: se perdesse importi, il MOL della sede cambierebbe
    da solo per una semplice correzione di categoria."""
    sb, p = _patch_quote()
    with p:
        riparto.riparto_riga_categoria(
            _body(file_origine="riparto:riparto-1", descrizione="Quota"),
            authorization="Bearer x",
        )
    quote_nuove = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"][0][1]["p_quote"]
    per_sede = {q["ristorante_id"]: q["quota_importo"] for q in quote_nuove}

    assert per_sede["sede-a"] == 150.0, "30+70+50"
    assert per_sede["sede-b"] == 150.0, "40+60+50"
    assert sum(per_sede.values()) == sum(q["quota_importo"] for q in _QUOTE_MULTI)


def test_consolidamento_preserva_la_percentuale_di_sede():
    """quota_perc e' la % della SEDE, non della categoria: sommarla darebbe 150%."""
    sb, p = _patch_quote()
    with p:
        riparto.riparto_riga_categoria(
            _body(file_origine="riparto:riparto-1", descrizione="Quota"),
            authorization="Bearer x",
        )
    quote_nuove = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"][0][1]["p_quote"]
    assert all(q["quota_perc"] == 50.0 for q in quote_nuove)


def test_tutte_le_quote_portano_la_nuova_categoria():
    sb, p = _patch_quote()
    with p:
        riparto.riparto_riga_categoria(
            _body(cat="PESCE", file_origine="riparto:riparto-1", descrizione="Quota"),
            authorization="Bearer x",
        )
    quote_nuove = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"][0][1]["p_quote"]
    assert {q["categoria"] for q in quote_nuove} == {"PESCE"}


def test_riparto_senza_quote_non_chiama_la_rpc():
    """Caso degenere: niente quote da riscrivere, ma il padre va comunque riallineato
    (la RPC rifiuta p_quote vuoto, quindi chiamarla sarebbe un errore garantito)."""
    sb, p = _patch_quote(quote=[])
    with p:
        out = riparto.riparto_riga_categoria(
            _body(file_origine="riparto:riparto-1", descrizione="Quota"),
            authorization="Bearer x",
        )
    assert out["ok"] is True
    assert not [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"]
    assert any(t == "riparto_costi_catena" and "tipo" in payload for t, payload in sb.updates)
