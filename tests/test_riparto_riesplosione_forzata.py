"""Test di esplodi_quote_per_categoria ESEGUITA davvero (non mockata).

Contesto: la correzione di categoria su una riga di gruppo (PATCH
/api/riparto/riga-categoria) cambia i pesi delle categorie sotto un riparto le cui
quote sono GIÀ per-categoria. Senza `forza=True` la funzione usciva subito
("evita di esplodere un'esplosione") e le quote restavano sulla categoria vecchia:
il MOL avrebbe instradato l'importo nel secchio sbagliato (F&B vs spese).

Copre inoltre la regressione latente che il modello per-categoria aveva introdotto:
aggregando per sede, `quota_perc` NON va sommata (è la % della sede, replicata
identica su ogni porzione). Sommandola, un riparto con 9 categorie produceva 450% e
sfondava il CHECK (quota_perc <= 100) della migration 20260714130000.

Negli altri file (test_riparto_da_fattura, test_riparto_modifica) questa funzione è
sempre patchata via MagicMock: qui è l'unico punto in cui gira sul serio.
"""
from types import SimpleNamespace

import pytest

from services.riparto_service import esplodi_quote_per_categoria


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._filters = {}

    def select(self, *a, **k): return self
    def eq(self, col, val):
        self._filters[col] = val
        return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def delete(self, *a, **k):
        self._c.deletes.setdefault(self._t, 0)
        self._c.deletes[self._t] += 1
        return self

    def insert(self, payload):
        self._c.inserts.setdefault(self._t, []).append(payload)
        return self

    def execute(self):
        if self._t == "fatture":
            return SimpleNamespace(data=self._c.righe)
        if self._t == "riparto_costi_catena_quote":
            return SimpleNamespace(data=self._c.quote)
        if self._t == "riparto_costi_catena":
            return SimpleNamespace(data=[self._c.padre] if self._c.padre else [])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, righe, quote, padre):
        self.righe = righe
        self.quote = quote
        self.padre = padre
        self.inserts = {}
        self.deletes = {}
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=params.get("p_riparto_id")))


_PADRE = {"tipo": "generale", "regola": "equa", "importo_totale": 380.50}

# Fattura mista: una riga da classificare + due categorie F&B (caso MONOPOLI reale).
_RIGHE = [
    {"categoria": "Da Classificare", "totale_riga": 149.00},
    {"categoria": "BIRRE", "totale_riga": 66.02},
    {"categoria": "CARNE", "totale_riga": 165.48},
]

# Quote GIÀ esplose: 2 sedi × 3 categorie, ognuna con la % della propria sede.
_QUOTE_ESPLOSE = [
    {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 74.50, "categoria": "Da Classificare"},
    {"id": "q2", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 33.01, "categoria": "BIRRE"},
    {"id": "q3", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 82.74, "categoria": "CARNE"},
    {"id": "q4", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 74.50, "categoria": "Da Classificare"},
    {"id": "q5", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 33.01, "categoria": "BIRRE"},
    {"id": "q6", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 82.75, "categoria": "CARNE"},
]

_QUOTE_LEGACY = [
    {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 190.25, "categoria": None},
    {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 190.25, "categoria": None},
]


def _quote_scritte(sb):
    assert sb.rpc_calls, "nessuna RPC chiamata"
    nome, params = sb.rpc_calls[-1]
    assert nome == "sostituisci_quote_riparto"
    return params["p_quote"]


def test_senza_forza_quote_gia_esplose_restano_intatte():
    """Comportamento storico preservato: default forza=False → early-return."""
    sb = _FakeSB(_RIGHE, _QUOTE_ESPLOSE, _PADRE)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml") is True
    assert sb.rpc_calls == []


def test_forza_riesplode_quote_gia_per_categoria():
    """Con forza=True le quote vengono ricalcolate sui pesi correnti."""
    sb = _FakeSB(_RIGHE, _QUOTE_ESPLOSE, _PADRE)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True) is True
    quote = _quote_scritte(sb)
    assert {q["categoria"] for q in quote} == {"Da Classificare", "BIRRE", "CARNE"}
    assert len(quote) == 6  # 2 sedi × 3 categorie


def test_forza_non_somma_le_percentuali_di_sede():
    """La regressione che sfonderebbe il CHECK (quota_perc <= 100)."""
    sb = _FakeSB(_RIGHE, _QUOTE_ESPLOSE, _PADRE)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    for q in _quote_scritte(sb):
        assert q["quota_perc"] == pytest.approx(50.0), (
            f"quota_perc {q['quota_perc']} — le porzioni non vanno sommate"
        )


def test_forza_conserva_il_totale_al_centesimo():
    """Ri-esplodere non deve creare né perdere centesimi: il costo resta quello."""
    sb = _FakeSB(_RIGHE, _QUOTE_ESPLOSE, _PADRE)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    tot = sum(q["quota_importo"] for q in _quote_scritte(sb))
    assert tot == pytest.approx(380.50, abs=0.01)


def test_riesplosione_dopo_correzione_categoria_sposta_la_quota():
    """Il caso d'uso reale: "Da Classificare" corretta in CARNE sulle righe →
    le quote non devono più contenere Da Classificare."""
    righe_corrette = [
        {"categoria": "CARNE", "totale_riga": 149.00},   # era Da Classificare
        {"categoria": "BIRRE", "totale_riga": 66.02},
        {"categoria": "CARNE", "totale_riga": 165.48},
    ]
    sb = _FakeSB(righe_corrette, _QUOTE_ESPLOSE, _PADRE)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote = _quote_scritte(sb)
    assert {q["categoria"] for q in quote} == {"CARNE", "BIRRE"}
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(380.50, abs=0.01)


def test_quote_legacy_esplodono_anche_senza_forza():
    """Le quote monolitiche (categoria NULL) restano il caso storico: nessuna
    regressione sul percorso già in produzione."""
    sb = _FakeSB(_RIGHE, _QUOTE_LEGACY, _PADRE)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml") is True
    quote = _quote_scritte(sb)
    assert len(quote) == 6
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(380.50, abs=0.01)


def test_scrittura_passa_dalla_rpc_transazionale_non_da_delete_insert():
    """Niente delete+insert separati: un fallimento a metà lascerebbe un riparto
    senza quote (orfano invisibile al motore MOL)."""
    sb = _FakeSB(_RIGHE, _QUOTE_LEGACY, _PADRE)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml")
    assert sb.deletes.get("riparto_costi_catena_quote") is None
    assert sb.inserts.get("riparto_costi_catena_quote") is None
    assert [n for n, _ in sb.rpc_calls] == ["sostituisci_quote_riparto"]


def test_padre_mancante_non_scrive_nulla():
    """Riparto inesistente per quell'utente: si esce senza toccare le quote."""
    sb = _FakeSB(_RIGHE, _QUOTE_LEGACY, None)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml") is False
    assert sb.rpc_calls == []


def test_senza_righe_vive_resta_legacy():
    """Storico purgato (GDPR): nessuna base per esplodere, nulla viene riscritto."""
    sb = _FakeSB([], _QUOTE_LEGACY, _PADRE)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True) is False
    assert sb.rpc_calls == []
