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


# ─── Riparto registrato LORDO (flusso da-coda): rientro al netto ──────────────
# /api/riparto/da-coda registra importo_totale = ImportoTotaleDocumento (IVA inclusa)
# perché le righe non sono ancora atterrate. All'atterraggio esplodi_quote_per_categoria
# deve riportare importo_totale e quote al netto reale (sum(totale_riga)).

# C.E.D.A.G. reale: netto 3425.00, lordo 4178.50 (IVA 22%), 50/50 su 2 sedi.
_RIGHE_NETTE = [
    {"categoria": "SERVIZI E CONSULENZE", "totale_riga": 2000.00},
    {"categoria": "Da Classificare", "totale_riga": 1425.00},
]
_PADRE_LORDO_FATTURA = {
    "origine": "fattura", "tipo": "generale", "regola": "equa", "importo_totale": 4178.50,
}
# Quote monolitiche in scala al LORDO: 4178.50 / 2 = 2089.25 per sede.
_QUOTE_LORDE = [
    {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 2089.25, "categoria": None},
    {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 2089.25, "categoria": None},
]


def test_da_coda_lordo_rientra_al_netto():
    sb = _FakeSB(_RIGHE_NETTE, _QUOTE_LORDE, _PADRE_LORDO_FATTURA)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml") is True
    nome, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(3425.00, abs=0.01)
    quote = params["p_quote"]
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(3425.00, abs=0.01)
    # 50/50: ogni sede pareggia la metà del netto.
    per_sede = {}
    for q in quote:
        per_sede.setdefault(q["ristorante_id"], 0.0)
        per_sede[q["ristorante_id"]] += q["quota_importo"]
    for tot in per_sede.values():
        assert tot == pytest.approx(1712.50, abs=0.02)


def test_da_fattura_netto_non_si_muove():
    """origine='fattura' ma importo già netto (da-fattura): nessuna rettifica."""
    padre_netto = {**_PADRE_LORDO_FATTURA, "importo_totale": 3425.00}
    quote_nette = [
        {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 1712.50, "categoria": None},
        {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 1712.50, "categoria": None},
    ]
    sb = _FakeSB(_RIGHE_NETTE, quote_nette, padre_netto)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml")
    _, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(3425.00, abs=0.01)


def test_costo_manuale_lordo_non_viene_toccato():
    """origine='manuale': l'importo è quello inserito dall'utente, niente netto da righe."""
    padre_manuale = {"origine": "manuale", "tipo": "generale", "regola": "equa", "importo_totale": 4178.50}
    sb = _FakeSB(_RIGHE_NETTE, _QUOTE_LORDE, padre_manuale)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml")
    _, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(4178.50, abs=0.01)


def test_da_coda_lordo_idempotente():
    """Rieseguire sul riparto già rientrato al netto non lo muove più."""
    padre_gia_netto = {**_PADRE_LORDO_FATTURA, "importo_totale": 3425.00}
    quote_gia_nette = [
        {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 1000.00, "categoria": "SERVIZI E CONSULENZE"},
        {"id": "q2", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 712.50, "categoria": "Da Classificare"},
        {"id": "q3", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 1000.00, "categoria": "SERVIZI E CONSULENZE"},
        {"id": "q4", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 712.50, "categoria": "Da Classificare"},
    ]
    sb = _FakeSB(_RIGHE_NETTE, quote_gia_nette, padre_gia_netto)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    _, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(3425.00, abs=0.01)
    assert sum(q["quota_importo"] for q in params["p_quote"]) == pytest.approx(3425.00, abs=0.01)


# ─── Note di credito (TD04): il riparto deve diventare NEGATIVO ───────────────
# In un conto mono-sede la NC si netta da sola (parser inverte le righe, il costo è
# una SUM pura). Il path di gruppo deve comportarsi uguale: netto reale negativo →
# importo_totale e quote negative, che riparto_quote_mensili sottrae dal mese.
# Prima di 20260827214500 i CHECK (>= 0) lo impedivano e il backfill crashava.

# Caso OFFSIDE reale: IT02355260981_eCsBh, NC TOYOTA di -307,30 € netti, ripartita
# dalla coda col LORDO POSITIVO provvisorio (+374,91) perché ImportoTotaleDocumento
# non porta il segno. 50/50 su 2 sedi.
_RIGHE_NC = [
    {"categoria": "MANUTENZIONI", "totale_riga": -250.00},
    {"categoria": "MATERIALE DI CONSUMO", "totale_riga": -57.30},
]
_PADRE_NC_LORDO = {
    "origine": "fattura", "tipo": "generale", "regola": "equa", "importo_totale": 374.91,
}
_QUOTE_NC_POSITIVE = [
    {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 187.46, "categoria": None},
    {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 187.45, "categoria": None},
]


def test_nota_credito_header_positivo_diventa_negativo():
    """Il bug OFFSIDE: header +374,91 su righe che valgono -307,30 → il gruppo
    pagava la NC invece di riceverla. Deve rientrare al netto NEGATIVO."""
    sb = _FakeSB(_RIGHE_NC, _QUOTE_NC_POSITIVE, _PADRE_NC_LORDO)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-nc", "nc.xml") is True
    _, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(-307.30, abs=0.01)
    quote = params["p_quote"]
    # Ogni quota è negativa: nessuna sede riceve un costo da una nota di credito.
    assert all(q["quota_importo"] < 0 for q in quote)
    # E le quote pareggiano l'header al centesimo (nessun centesimo perso).
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(-307.30, abs=0.01)


def test_nota_credito_quote_pareggiano_per_sede():
    """50/50 su un netto dispari: le due sedi si dividono -107,33 senza derive."""
    righe = [{"categoria": "SERVIZI E CONSULENZE", "totale_riga": -107.33}]
    padre = {"origine": "fattura", "tipo": "generale", "regola": "equa", "importo_totale": 130.94}
    quote = [
        {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 65.47, "categoria": None},
        {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 65.47, "categoria": None},
    ]
    sb = _FakeSB(righe, quote, padre)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-nc2", "nc2.xml")
    _, params = sb.rpc_calls[-1]
    per_sede = {}
    for q in params["p_quote"]:
        per_sede[q["ristorante_id"]] = per_sede.get(q["ristorante_id"], 0.0) + q["quota_importo"]
    assert sum(per_sede.values()) == pytest.approx(-107.33, abs=0.01)
    # -53,66 / -53,67: l'ultima sede assorbe il centesimo dispari.
    assert all(-53.68 <= v <= -53.65 for v in per_sede.values())


def test_nota_credito_percentuali_asimmetriche():
    """Con quote 70/30 il segno non altera le proporzioni."""
    righe = [{"categoria": "UTENZE", "totale_riga": -150.00}]
    padre = {"origine": "fattura", "tipo": "generale", "regola": "percentuali", "importo_totale": 156.00}
    quote = [
        {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 70.0, "quota_importo": 109.20, "categoria": None},
        {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 30.0, "quota_importo": 46.80, "categoria": None},
    ]
    sb = _FakeSB(righe, quote, padre)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-nc3", "nc3.xml")
    _, params = sb.rpc_calls[-1]
    per_sede = {}
    for q in params["p_quote"]:
        per_sede[q["ristorante_id"]] = per_sede.get(q["ristorante_id"], 0.0) + q["quota_importo"]
    assert per_sede["sede-a"] == pytest.approx(-105.00, abs=0.01)
    assert per_sede["sede-b"] == pytest.approx(-45.00, abs=0.01)


def test_nota_credito_gia_negativa_e_idempotente():
    """Un riparto già al netto negativo non si muove più (niente doppia inversione)."""
    padre = {"origine": "fattura", "tipo": "generale", "regola": "equa", "importo_totale": -307.30}
    quote = [
        {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": -125.00, "categoria": "MANUTENZIONI"},
        {"id": "q2", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": -28.65, "categoria": "MATERIALE DI CONSUMO"},
        {"id": "q3", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": -125.00, "categoria": "MANUTENZIONI"},
        {"id": "q4", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": -28.65, "categoria": "MATERIALE DI CONSUMO"},
    ]
    sb = _FakeSB(_RIGHE_NC, quote, padre)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-nc", "nc.xml", forza=True)
    _, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(-307.30, abs=0.01)
    assert sum(q["quota_importo"] for q in params["p_quote"]) == pytest.approx(-307.30, abs=0.01)


def test_header_negativo_con_quote_positive_stantie():
    """Scrittura interrotta a metà: header già al netto NEGATIVO ma quote ancora in
    scala lorda POSITIVA. È il caso che la vecchia riscalatura per netto/lordo non
    sapeva chiudere (il fattore restava 1.0 con header <= 0.01, lasciando +374,91 di
    quote sotto un header di -307,30 — e riparto_quote_mensili legge le QUOTE, quindi
    la sede pagava comunque). Ricostruendo dalle percentuali il segno rientra sempre."""
    padre = {"origine": "fattura", "tipo": "generale", "regola": "equa", "importo_totale": -300.00}
    quote_stantie = [
        {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 187.46, "categoria": None},
        {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 187.45, "categoria": None},
    ]
    sb = _FakeSB(_RIGHE_NC, quote_stantie, padre)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-nc", "nc.xml", forza=True)
    _, params = sb.rpc_calls[-1]
    assert params["p_importo_totale"] == pytest.approx(-307.30, abs=0.01)
    quote = params["p_quote"]
    assert all(q["quota_importo"] < 0 for q in quote), "nessuna quota può restare positiva"
    assert sum(q["quota_importo"] for q in quote) == pytest.approx(-307.30, abs=0.01)


def test_netto_zero_non_esplode_e_non_scrive():
    """NC che azzera esattamente il costo (netto ~0): niente crash, niente scrittura.
    Lo segnala v_riparto_incoerenze, lo chiude la manutenzione."""
    righe = [
        {"categoria": "UTENZE", "totale_riga": 150.00},
        {"categoria": "UTENZE", "totale_riga": -150.00},
    ]
    sb = _FakeSB(righe, _QUOTE_NC_POSITIVE, _PADRE_NC_LORDO)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-zero", "zero.xml") is False
    assert sb.rpc_calls == []


def test_riparto_senza_quote_non_scrive():
    """Header senza quote (caso AUTOSTRADE): esce senza toccare nulla."""
    sb = _FakeSB(_RIGHE_NETTE, [], _PADRE_LORDO_FATTURA)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-vuoto", "f.xml") is False
    assert sb.rpc_calls == []
