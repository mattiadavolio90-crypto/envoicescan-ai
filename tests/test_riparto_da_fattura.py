"""Test dell'endpoint POST /api/riparto/da-fattura (services/routers/riparto.py).

Ripartisce una fattura di struttura (già caricata su una sede reale, es. commercialista
intestato alla sede legale) sul gruppo: legge importo/periodo dalle righe fattura, crea
il riparto + quote (RPC transazionale), esplode le quote per categoria, marca le righe
come ripartite (anti-doppio-conteggio). Se questo endpoint sbaglia il costo finisce sul
punto vendita sbagliato o sparisce dal MOL in silenzio — stessa classe dell'incidente
FASTWEB del 22/7 citato nei commenti di _crea_riparto_con_quote.

Prima di questo file l'endpoint aveva 0 test (audit ONEFLUX §2, 8/8/2026).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


# ─── Fake Supabase stateful ───────────────────────────────────────────────────

class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._is_insert = False

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self, *a, **k): return self

    def insert(self, payload):
        self._is_insert = True
        self._c.inserts.setdefault(self._t, []).append(payload)
        return self

    def update(self, payload):
        self._c.updates.setdefault(self._t, []).append(payload)
        return self

    def upsert(self, payload, **k):
        self._c.upserts.setdefault(self._t, []).append(payload)
        return self

    def delete(self, *a, **k):
        return self

    def execute(self):
        if self._t == "fatture" and not self._is_insert:
            return SimpleNamespace(data=self._c.righe_fattura)
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, righe_fattura):
        self.righe_fattura = righe_fattura
        self.inserts = {}
        self.updates = {}
        self.upserts = {}
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if name == "crea_riparto_con_quote":
            # Simula la RPC transazionale: registra padre+quote come farebbe il DB.
            self.inserts.setdefault("riparto_costi_catena", []).append({
                "user_id": params["p_user_id"], "origine": params["p_origine"],
                "file_origine": params["p_file_origine"], "fornitore": params["p_fornitore"],
                "descrizione": params["p_descrizione"], "importo_totale": params["p_importo_totale"],
                "tipo": params["p_tipo"], "anno": params["p_anno"], "mese": params["p_mese"],
                "regola": params["p_regola"],
            })
            self.inserts.setdefault("riparto_costi_catena_quote", []).append(params["p_quote"])
            return SimpleNamespace(execute=lambda: SimpleNamespace(data="riparto-1"))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


_SEDI_REALI = [
    {"id": "sede-a", "nome_ristorante": "Locale A"},
    {"id": "sede-b", "nome_ristorante": "Locale B"},
]

_RIGHE_OK = [
    {
        "id": "riga-1", "totale_riga": 600.0,
        "data_documento": "2026-06-05", "data_competenza": None,
        "fornitore": "Studio Rossi", "piva_cedente": "09408560960",
        "ripartita_su_gruppo": False,
    },
    {
        "id": "riga-2", "totale_riga": 400.0,
        "data_documento": "2026-06-05", "data_competenza": None,
        "fornitore": "Studio Rossi", "piva_cedente": "09408560960",
        "ripartita_su_gruppo": False,
    },
]


def _patch(righe, sedi=_SEDI_REALI, esplodi_side_effect=None):
    sb = _FakeSB(righe)
    esplodi_mock = MagicMock(side_effect=esplodi_side_effect)
    patches = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
        _post_scrittura_riparto=MagicMock(return_value=None),
    )
    esplodi_patch = patch(
        "services.riparto_service.esplodi_quote_per_categoria", esplodi_mock
    )
    return sb, esplodi_mock, patches, esplodi_patch


def _body(**over):
    base = dict(file_origine="IT123_commercialista.xml", descrizione="Commercialista giugno",
                tipo="generale", regola="equa")
    base.update(over)
    return riparto.RipartoDaFatturaBody(**base)


# ─── Happy path ───────────────────────────────────────────────────────────────

def test_da_fattura_regola_equa_crea_riparto_e_marca_righe():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)
    with p, ep:
        out = riparto.riparto_da_fattura(_body(), authorization="Bearer x")

    assert out["ok"] is True
    assert out["importo"] == 1000.0
    assert out["anno"] == 2026 and out["mese"] == 6

    rip = sb.inserts["riparto_costi_catena"][0]
    assert rip["origine"] == "fattura"
    assert rip["file_origine"] == "IT123_commercialista.xml"
    assert rip["fornitore"] == "09408560960"  # piva_cedente preferita a fornitore

    quote = sb.inserts["riparto_costi_catena_quote"][0]
    assert len(quote) == 2
    assert sum(q["quota_importo"] for q in quote) == 1000.0
    assert {q["ristorante_id"] for q in quote} == {"sede-a", "sede-b"}

    # marcatura ripartita_su_gruppo sulla fattura sorgente (anti-doppio-conteggio)
    upd = sb.updates["fatture"][0]
    assert upd == {"ripartita_su_gruppo": True}

    # esplosione per categoria tentata col riparto appena creato
    esplodi.assert_called_once()
    assert esplodi.call_args[0][2] == "riparto-1"


def test_da_fattura_regola_percentuali():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)
    with p, ep:
        out = riparto.riparto_da_fattura(
            _body(regola="percentuali", percentuali={"sede-a": 70.0, "sede-b": 30.0}),
            authorization="Bearer x",
        )
    assert out["ok"] is True
    quote = {q["ristorante_id"]: q["quota_importo"] for q in sb.inserts["riparto_costi_catena_quote"][0]}
    assert quote["sede-a"] == 700.0
    assert quote["sede-b"] == 300.0


# ─── Periodo di competenza ──────────────────────────────────────────────────────

def test_da_fattura_usa_data_competenza_se_presente():
    righe = [dict(_RIGHE_OK[0], data_competenza="2026-08-01"), _RIGHE_OK[1]]
    sb, esplodi, p, ep = _patch(righe)
    with p, ep:
        out = riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    assert out["anno"] == 2026 and out["mese"] == 8


def test_da_fattura_fallback_data_documento_se_competenza_assente():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)  # tutte con data_competenza=None
    with p, ep:
        out = riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    assert out["anno"] == 2026 and out["mese"] == 6  # da data_documento


def test_da_fattura_data_assente_400():
    righe = [dict(r, data_documento=None, data_competenza=None) for r in _RIGHE_OK]
    sb, esplodi, p, ep = _patch(righe)
    with p, ep, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400


# ─── Errori di validazione ──────────────────────────────────────────────────────

def test_da_fattura_file_origine_mancante_400():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)
    with p, ep, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_fattura(_body(file_origine="  "), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_da_fattura_tipo_non_valido_400():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)
    with p, ep, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_fattura(_body(tipo="altro"), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_da_fattura_non_trovata_404():
    sb, esplodi, p, ep = _patch([])  # nessuna riga con questo file_origine
    with p, ep, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    assert exc.value.status_code == 404


def test_da_fattura_gia_ripartita_409_non_duplica():
    righe = [dict(_RIGHE_OK[0], ripartita_su_gruppo=True), _RIGHE_OK[1]]
    sb, esplodi, p, ep = _patch(righe)
    with p, ep, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    assert exc.value.status_code == 409
    assert sb.inserts.get("riparto_costi_catena", []) == []


def test_da_fattura_gating_una_sola_sede_reale_400():
    sb, esplodi, p, ep = _patch(_RIGHE_OK, sedi=[{"id": "sede-a", "nome_ristorante": "Unico"}])
    with p, ep, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400


# ─── Regola fornitore opzionale ─────────────────────────────────────────────────

def test_da_fattura_salva_regola_fornitore():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)
    with p, ep:
        riparto.riparto_da_fattura(
            _body(salva_regola_fornitore=True, regola="percentuali",
                  percentuali={"sede-a": 60.0, "sede-b": 40.0}),
            authorization="Bearer x",
        )
    upsert = sb.upserts["riparto_regole_fornitore"][0]
    assert upsert["fornitore"] == "09408560960"
    assert upsert["regola"] == "percentuali"
    assert upsert["tipo"] == "generale"
    assert upsert["attiva"] is True


def test_da_fattura_senza_salva_regola_fornitore_non_scrive():
    sb, esplodi, p, ep = _patch(_RIGHE_OK)
    with p, ep:
        riparto.riparto_da_fattura(_body(salva_regola_fornitore=False), authorization="Bearer x")
    assert sb.upserts.get("riparto_regole_fornitore", []) == []


# ─── Esplosione per categoria: fallback legacy, non deve propagare ──────────────

def test_da_fattura_esplosione_categoria_fallisce_non_rompe_endpoint():
    sb, esplodi, p, ep = _patch(_RIGHE_OK, esplodi_side_effect=RuntimeError("boom"))
    with p, ep:
        out = riparto.riparto_da_fattura(_body(), authorization="Bearer x")
    # il riparto resta comunque creato e le righe marcate (fallback legacy silenzioso)
    assert out["ok"] is True
    assert sb.inserts["riparto_costi_catena"]
    assert sb.updates["fatture"][0]["ripartita_su_gruppo"] is True


# Le mutazioni vere e proprie (rimuovere temporaneamente il guard 236-237 o la
# marcatura 273-274 dal sorgente e rilanciare la suite) sono verificate a mano
# durante la sessione, non incluse come test permanenti: i due test sopra
# (`test_da_fattura_gia_ripartita_409_non_duplica` e
# `test_da_fattura_regola_equa_crea_riparto_e_marca_righe`) sono quelli che
# devono diventare rossi quando quelle righe vengono tolte.
