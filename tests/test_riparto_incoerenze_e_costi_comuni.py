"""Test di GET /api/admin/riparto/incoerenze e GET /api/gruppo/costi-comuni
(services/routers/riparto.py). Entrambi sola lettura, 0 test prima di questo
file (audit ONEFLUX §2, 8/8/2026, residuo dopo la copertura di riparto_da_fattura).

riparto_incoerenze: diagnostica per il workflow riparto_coerenza_check.yml,
aggrega v_riparto_incoerenze per account distinguendo 'orfano' (costo sparito
dal MOL) da 'riparto_senza_documento' (costo fantasma ancora contato) — le due
classi non sono mai sommabili in un unico numero, solo il totale conta le righe.

gruppo_costi_comuni: lista costi di gruppo del mese con quote per sede, gatato
da _require_catena (>=2 sedi attive, altrimenti 400).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


# ─── riparto_incoerenze ────────────────────────────────────────────────────

class _QueryIncoerenze:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self

    def execute(self):
        if self._t == "v_riparto_incoerenze":
            return SimpleNamespace(data=self._c.righe)
        return SimpleNamespace(data=[])


class _FakeSBIncoerenze:
    def __init__(self, righe):
        self.righe = righe

    def table(self, name):
        return _QueryIncoerenze(self, name)


def _patch_incoerenze(righe):
    sb = _FakeSBIncoerenze(righe)
    return sb, patch.object(riparto, "_get_supabase_client", MagicMock(return_value=sb))


def test_incoerenze_vuoto():
    sb, p = _patch_incoerenze([])
    with p:
        out = riparto.riparto_incoerenze()
    assert out == {"totale": 0, "account": []}


def test_incoerenze_bucket_orfano_e_senza_documento():
    righe = [
        {
            "user_id": "user-1", "tipo_incoerenza": "orfano",
            "file_origine": "IT123_a.xml", "riparto_id": None,
            "fornitore": "Fornitore A", "importo": 100.0, "data_documento": "2026-06-01",
        },
        {
            "user_id": "user-1", "tipo_incoerenza": "riparto_senza_documento",
            "file_origine": None, "riparto_id": "riparto-9",
            "fornitore": "Fornitore B", "importo": 250.5, "data_documento": "2026-06-10",
        },
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()

    assert out["totale"] == 2
    assert len(out["account"]) == 1
    acc = out["account"][0]
    assert acc["user_id"] == "user-1"
    assert len(acc["orfani"]) == 1
    assert acc["orfani"][0]["fornitore"] == "Fornitore A"
    assert acc["orfani"][0]["importo"] == 100.0
    assert len(acc["riparti_senza_documento"]) == 1
    assert acc["riparti_senza_documento"][0]["riparto_id"] == "riparto-9"


def test_incoerenze_multi_account_non_mischiati():
    righe = [
        {"user_id": "user-1", "tipo_incoerenza": "orfano", "file_origine": "a.xml",
         "riparto_id": None, "fornitore": "F1", "importo": 10.0, "data_documento": "2026-06-01"},
        {"user_id": "user-2", "tipo_incoerenza": "orfano", "file_origine": "b.xml",
         "riparto_id": None, "fornitore": "F2", "importo": 20.0, "data_documento": "2026-06-02"},
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()

    assert out["totale"] == 2
    uids = {acc["user_id"] for acc in out["account"]}
    assert uids == {"user-1", "user-2"}
    for acc in out["account"]:
        assert len(acc["orfani"]) == 1
        assert len(acc["riparti_senza_documento"]) == 0


def test_incoerenze_nuovi_tipi_nel_secchio_giusto():
    """riparto_senza_quote e riparto_segno_incoerente (view 20260827214500) hanno un
    secchio proprio. Regressione: con l'`else` catch-all di prima finivano entrambi in
    riparti_senza_documento e l'alert diceva una cosa per un'altra."""
    righe = [
        {"user_id": "user-1", "tipo_incoerenza": "riparto_senza_quote",
         "file_origine": "IT0526289001426211_FCNYM.xml", "riparto_id": "a8143a95",
         "fornitore": "07516911000", "importo": 118.10, "data_documento": "2026-07-01"},
        {"user_id": "user-1", "tipo_incoerenza": "riparto_segno_incoerente",
         "file_origine": "IT02355260981_eCsBh.xml", "riparto_id": "395b6758",
         "fornitore": "15162191009", "importo": -307.30, "data_documento": "2026-02-01"},
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()

    acc = out["account"][0]
    assert out["totale"] == 2
    assert len(acc["riparti_senza_quote"]) == 1
    assert acc["riparti_senza_quote"][0]["riparto_id"] == "a8143a95"
    assert len(acc["riparti_segno_incoerente"]) == 1
    assert acc["riparti_segno_incoerente"][0]["importo"] == -307.30
    # I secchi storici restano vuoti: nessuna contaminazione.
    assert acc["orfani"] == []
    assert acc["riparti_senza_documento"] == []


def test_incoerenze_tipo_sconosciuto_non_inquina_i_secchi():
    """Un tipo non previsto finisce in 'altro' con la sua etichetta, non in un secchio
    esistente: meglio visibile e non classificato che silenziosamente sbagliato."""
    righe = [
        {"user_id": "user-1", "tipo_incoerenza": "tipo_futuro_ignoto", "file_origine": "x.xml",
         "riparto_id": None, "fornitore": "F", "importo": 1.0, "data_documento": "2026-01-01"},
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()
    acc = out["account"][0]
    assert acc["riparti_senza_documento"] == []
    assert len(acc["altro"]) == 1
    assert acc["altro"][0]["tipo_incoerenza"] == "tipo_futuro_ignoto"


def test_incoerenze_importo_none_non_solleva():
    righe = [
        {"user_id": "user-1", "tipo_incoerenza": "orfano", "file_origine": "a.xml",
         "riparto_id": None, "fornitore": "F1", "importo": None, "data_documento": None},
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()
    assert out["account"][0]["orfani"][0]["importo"] is None


# ─── gruppo_costi_comuni ────────────────────────────────────────────────────

_SEDI_2 = [
    {"id": "sede-a", "nome_ristorante": "Locale A"},
    {"id": "sede-b", "nome_ristorante": "Locale B"},
]

_SEDE_1 = [{"id": "sede-a", "nome_ristorante": "Locale A"}]


class _QueryCostiComuni:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._slice = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self

    def range(self, start, end):
        # fetch_all pagina con .range(): affettare davvero, altrimenti restituire
        # sempre la pagina piena farebbe ciclare il paginatore all'infinito.
        self._slice = (start, end + 1)
        return self

    def execute(self):
        if self._t == "riparto_costi_catena":
            data = self._c.costi
        elif self._t == "riparto_costi_catena_quote":
            data = self._c.quote
        elif self._t == "fatture":
            data = self._c.righe
        else:
            data = []
        if self._slice is not None:
            data = data[self._slice[0]:self._slice[1]]
        return SimpleNamespace(data=data)


class _FakeSBCostiComuni:
    def __init__(self, costi, quote, righe=None):
        self.costi = costi
        self.quote = quote
        self.righe = righe or []

    def table(self, name):
        return _QueryCostiComuni(self, name)


def _patch_costi_comuni(costi, quote, sedi=_SEDI_2, righe=None):
    sb = _FakeSBCostiComuni(costi, quote, righe)
    p = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
    )
    return sb, p


def test_costi_comuni_richiede_almeno_2_sedi():
    sb, p = _patch_costi_comuni([], [], sedi=_SEDE_1)
    with p, pytest.raises(HTTPException) as exc:
        riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert exc.value.status_code == 400


def test_costi_comuni_nessun_costo_ritorna_vuoto_senza_interrogare_quote():
    sb, p = _patch_costi_comuni([], [])
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out == {
        "anno": 2026, "mese": 6, "costi": [], "totale": 0.0,
        "da_classificare_importo": 0.0, "da_classificare_costi": 0,
        "da_classificare_non_correggibili": 0,
    }


def test_costi_comuni_happy_path_mappa_sede_e_totale():
    costi = [
        {"id": "c1", "origine": "manuale", "file_origine": None, "fornitore": "FASTWEB",
         "descrizione": "Internet", "importo_totale": 100.0, "tipo": "generale", "regola": "equa"},
        {"id": "c2", "origine": "manuale", "file_origine": None, "fornitore": "ENEL",
         "descrizione": "Energia", "importo_totale": 200.5, "tipo": "generale", "regola": "equa"},
    ]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 50.0},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 50.0},
        {"riparto_id": "c2", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 100.25},
        {"riparto_id": "c2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 100.25},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")

    assert out["anno"] == 2026 and out["mese"] == 6
    assert out["totale"] == 300.5
    assert len(out["costi"]) == 2
    c1 = next(c for c in out["costi"] if c["id"] == "c1")
    assert len(c1["quote"]) == 2
    sedi_nomi = {q["sede"] for q in c1["quote"]}
    assert sedi_nomi == {"Locale A", "Locale B"}


def test_costi_comuni_costo_senza_quote_ritorna_lista_vuota():
    costi = [
        {"id": "c1", "origine": "manuale", "file_origine": None, "fornitore": "FASTWEB",
         "descrizione": "Internet", "importo_totale": 100.0, "tipo": "generale", "regola": "equa"},
    ]
    sb, p = _patch_costi_comuni(costi, [])
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")

    assert out["costi"][0]["quote"] == []
    assert out["totale"] == 100.0


# ─── quote per-categoria: aggregazione per sede (fix 24/8) ──────────────────
# Dal 24/7/2026 le quote sono per (sede × categoria). L'endpoint le elencava piatte:
# una fattura mista mostrava la stessa sede ripetuta una volta per categoria, con la
# sua percentuale replicata (nove "50%" che sommano 450%). Caso reale: MONOPOLI,
# 380,50 € su 2 sedi × 9 categorie = 18 righe a schermo.

_COSTO_MISTO = [
    {"id": "c1", "origine": "fattura", "file_origine": "IT123_x.xml", "fornitore": "MONOPOLI",
     "descrizione": "Costo comune MONOPOLI", "importo_totale": 380.50,
     "tipo": "generale", "regola": "equa"},
]

_QUOTE_PER_CATEGORIA = [
    {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 74.50, "categoria": "Da Classificare"},
    {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 33.01, "categoria": "BIRRE"},
    {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 82.74, "categoria": "CARNE"},
    {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 74.50, "categoria": "Da Classificare"},
    {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 33.01, "categoria": "BIRRE"},
    {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 82.74, "categoria": "CARNE"},
]


def _costo_misto():
    sb, p = _patch_costi_comuni(_COSTO_MISTO, _QUOTE_PER_CATEGORIA)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=7, authorization="Bearer x")
    return out["costi"][0]


def test_quote_per_categoria_aggregate_una_riga_per_sede():
    c1 = _costo_misto()
    assert len(c1["quote"]) == 2, "una entry per sede, non una per (sede × categoria)"
    assert {q["sede"] for q in c1["quote"]} == {"Locale A", "Locale B"}


def test_quote_per_categoria_percentuale_non_sommata():
    """Il difetto visibile a schermo: 50% replicato su ogni porzione, mai sommato."""
    for q in _costo_misto()["quote"]:
        assert q["quota_perc"] == pytest.approx(50.0)


def test_quote_per_categoria_importi_sommati_per_sede():
    c1 = _costo_misto()
    for q in c1["quote"]:
        assert q["quota_importo"] == pytest.approx(190.25, abs=0.01)
    tot = sum(q["quota_importo"] for q in c1["quote"])
    assert tot == pytest.approx(380.50, abs=0.01)


def test_dettaglio_categorie_esposto_e_ordinato_per_importo():
    dett = _costo_misto()["dettaglio_categorie"]
    assert [d["categoria"] for d in dett] == ["CARNE", "Da Classificare", "BIRRE"]
    assert sum(d["importo"] for d in dett) == pytest.approx(380.50, abs=0.01)


def test_righe_documento_esposte_per_la_correzione_categoria():
    righe = [
        {"file_origine": "IT123_x.xml", "id": 11, "descrizione": "1 ACCONTO",
         "categoria": "Da Classificare", "totale_riga": 149.0, "needs_review": True},
    ]
    sb, p = _patch_costi_comuni(_COSTO_MISTO, _QUOTE_PER_CATEGORIA, righe=righe)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=7, authorization="Bearer x")
    r = out["costi"][0]["righe"]
    assert len(r) == 1 and r[0]["descrizione"] == "1 ACCONTO"
    assert r[0]["categoria"] == "Da Classificare" and r[0]["needs_review"] is True


def test_quote_legacy_senza_categoria_restano_una_per_sede():
    """Nessuna regressione sui riparti pre-24/7 (categoria NULL)."""
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 190.25, "categoria": None},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 190.25, "categoria": None},
    ]
    sb, p = _patch_costi_comuni(_COSTO_MISTO, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=7, authorization="Bearer x")
    c1 = out["costi"][0]
    assert len(c1["quote"]) == 2
    assert c1["dettaglio_categorie"] == []


# ─── quote "Da Classificare": visibili, non nascoste ────────────────────────
#
# Asimmetria deliberata (vedi 20260724220000_riparto_quote_per_categoria.sql): una
# riga fattura "Da Classificare" è ESCLUSA dal MOL, una quota di riparto invece
# entra nel secchio spese — la riga d'origine è già esclusa come
# ripartita_su_gruppo, quindi la quota è l'unico posto in cui quel costo esiste.
# Escluderla lo farebbe sparire e il MOL sembrerebbe migliore del reale.
# Il prezzo di quella scelta è che il costo pesa sul secchio sbagliato finché
# nessuno lo classifica: l'endpoint lo dichiara, così la UI può avvisare.


def _costo(cid, importo, tipo="generale"):
    return {"id": cid, "origine": "fattura", "file_origine": None, "fornitore": "F",
            "descrizione": f"Costo {cid}", "importo_totale": importo,
            "tipo": tipo, "regola": "equa"}


def test_costi_comuni_espone_totale_quote_da_classificare():
    costi = [_costo("c1", 1000.0), _costo("c2", 500.0)]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 400.0, "categoria": "Da Classificare"},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0,
         "quota_importo": 400.0, "categoria": "Da Classificare"},
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 100.0, "categoria": "CARNE"},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0,
         "quota_importo": 100.0, "categoria": "CARNE"},
        {"riparto_id": "c2", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 250.0, "categoria": "UTENZE E LOCALI"},
        {"riparto_id": "c2", "ristorante_id": "sede-b", "quota_perc": 50.0,
         "quota_importo": 250.0, "categoria": "UTENZE E LOCALI"},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")

    assert out["da_classificare_importo"] == 800.0, "somma delle sole quote non classificate"
    assert out["da_classificare_costi"] == 1, "un solo costo ne contiene, non due"
    assert out["totale"] == 1500.0, "il totale non cambia: nessuna quota viene esclusa"


def test_costi_comuni_nessuna_quota_da_classificare_non_allarma():
    """Zero falsi positivi: senza quote non classificate l'avviso non deve comparire."""
    costi = [_costo("c1", 100.0)]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 50.0, "categoria": "CARNE"},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0,
         "quota_importo": 50.0, "categoria": "CARNE"},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out["da_classificare_importo"] == 0
    assert out["da_classificare_costi"] == 0


def test_costi_comuni_quote_senza_categoria_sono_contate():
    """Una quota con categoria NULL NON è innocua e va segnalata come le altre.

    Verifica sul DB reale (24/8/2026): 4 quote NULL per 531,76 €, su due riparti
    TOYOTA creati il 21/8 le cui righe fattura non esistono più. Con categoria NULL
    la quota non passa da _riparto_categoria_is_fb: finisce nel secchio del `tipo`
    dell'header senza che nulla lo dichiari. Il test precedente asseriva il contrario
    ("non sono da classificare, non vanno segnalate") ed è stato riscritto: era la
    stessa cecità che l'avviso doveva eliminare.
    """
    costi = [_costo("c1", 100.0)]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 50.0, "categoria": None},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0,
         "quota_importo": 50.0, "categoria": None},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out["da_classificare_importo"] == 100.0
    assert out["da_classificare_costi"] == 1
    assert out["totale"] == 100.0, "il totale non cambia: nessuna quota viene esclusa"


def test_costi_comuni_categoria_vuota_equiparata_a_null():
    """Stringa vuota e NULL sono lo stesso stato: entrambe niente categoria."""
    costi = [_costo("c1", 60.0)]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 30.0, "categoria": ""},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0,
         "quota_importo": 30.0, "categoria": "   "},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out["da_classificare_importo"] == 60.0
    assert out["da_classificare_costi"] == 1


def test_costi_comuni_sentinella_fuori_da_dettaglio_categorie():
    """dettaglio_categorie elenca categorie REALI: mostrare la chiave interna delle
    quote senza categoria la farebbe sembrare una classificazione avvenuta."""
    costi = [_costo("c1", 100.0)]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 30.0, "categoria": None},
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0,
         "quota_importo": 20.0, "categoria": "CARNE"},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    cats = [d["categoria"] for d in out["costi"][0]["dettaglio_categorie"]]
    assert cats == ["CARNE"], f"solo categorie reali, trovato {cats}"
    assert riparto._SENZA_CATEGORIA not in cats


def test_costi_comuni_segnala_costi_non_correggibili_dalla_ui():
    """Senza righe il dropdown non ha nulla da offrire: dirgli "correggi dalle righe"
    sarebbe un'istruzione ineseguibile, quindi il conteggio va esposto a parte."""
    costi = [_costo("c1", 100.0)]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 100.0,
         "quota_importo": 100.0, "categoria": None},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out["costi"][0]["righe"] == [], "il costo non ha righe da cui correggere"
    assert out["da_classificare_non_correggibili"] == 1


def test_costi_comuni_costo_con_righe_non_e_non_correggibile():
    """Il contatore deve restare zero quando l'utente PUÒ agire, altrimenti l'avviso
    manda a rifare un costo che bastava correggere dal dropdown."""
    costi = [dict(_costo("c1", 100.0), file_origine="IT123_doc.xml")]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 100.0,
         "quota_importo": 100.0, "categoria": "Da Classificare"},
    ]
    righe = [
        {"id": 1, "file_origine": "IT123_doc.xml", "descrizione": "Voce",
         "categoria": "Da Classificare", "totale_riga": 100.0, "needs_review": True},
    ]
    sb, p = _patch_costi_comuni(costi, quote, righe=righe)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out["da_classificare_costi"] == 1
    assert out["da_classificare_non_correggibili"] == 0


# ─── riparto_auto_pulisci ──────────────────────────────────────────────────
# La manutenzione automatica scrive e cancella: qui si verifica soprattutto
# COSA NON tocca. Vedi la docstring dell'endpoint per il perché.

class _QueryPulisci:
    def __init__(self, client, table):
        self._c, self._t, self._filtri = client, table, {}

    def select(self, *a, **k): return self

    def eq(self, col, val):
        self._filtri[col] = val
        return self

    def limit(self, *a, **k): return self

    def execute(self):
        if self._t == "v_riparto_incoerenze":
            righe = self._c.righe
            uid = self._filtri.get("user_id")
            if uid:
                righe = [r for r in righe if str(r.get("user_id")) == str(uid)]
            return SimpleNamespace(data=righe)
        if self._t == "riparto_costi_catena":
            rid = self._filtri.get("id")
            return SimpleNamespace(data=[p for p in self._c.padri if p["id"] == rid])
        if self._t == "ristoranti":
            return SimpleNamespace(data=self._c.sedi)
        return SimpleNamespace(data=[])


class _FakeSBPulisci:
    def __init__(self, righe, padri, sedi=None):
        self.righe, self.padri = righe, padri
        self.sedi = sedi if sedi is not None else [
            {"id": "sede-A"}, {"id": "sede-B"},
        ]
        self.rpc_calls = []

    def table(self, name):
        return _QueryPulisci(self, name)

    def rpc(self, nome, params):
        self.rpc_calls.append((nome, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


UID = "2f3f93a1-c1f4-4804-858e-a161e6f36f3f"


def _riga(tipo, rid, fo="F.xml"):
    return {"user_id": UID, "tipo_incoerenza": tipo, "riparto_id": rid,
            "file_origine": fo, "fornitore": "TOYOTA", "importo": 374.91,
            "data_documento": "2026-02-01"}


def _padre(rid, importo=374.91, fo="F.xml"):
    return {"id": rid, "anno": 2026, "mese": 2, "fornitore": "TOYOTA",
            "importo_totale": importo, "file_origine": fo, "origine": "fattura"}


def _patch_pulisci(sb, netto=-307.30):
    """Patcha il client e le due funzioni di riparto_service usate dall'endpoint."""
    import services.riparto_service as rs
    return (
        patch.object(riparto, "_get_supabase_client", MagicMock(return_value=sb)),
        patch.object(rs, "_pesi_e_netto_categoria_fattura",
                     MagicMock(return_value=({"CARBURANTI": 1.0}, netto))),
        patch.object(rs, "esplodi_quote_per_categoria", MagicMock(return_value=True)),
    )


def test_auto_pulisci_dry_run_non_scrive():
    sb = _FakeSBPulisci([_riga("riparto_segno_incoerente", "r1")], [_padre("r1")])
    p1, p2, p3 = _patch_pulisci(sb)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=False)

    assert out["applicato"] is False
    assert len(out["riparati"]) == 1
    assert out["riparati"][0]["netto_reale"] == -307.30
    assert sb.rpc_calls == [], "il dry-run non deve scrivere nulla"


def test_auto_pulisci_segno_incoerente_ricalcola_il_mese():
    sb = _FakeSBPulisci([_riga("riparto_segno_incoerente", "r1")], [_padre("r1")])
    p1, p2, p3 = _patch_pulisci(sb)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=True)

    assert out["mesi_ricalcolati"] == 1
    assert ("riparto_quote_mensili", {"p_user_id": UID, "p_anno": 2026, "p_mese": 2}) in sb.rpc_calls


def test_auto_pulisci_senza_quote_le_ricrea():
    sb = _FakeSBPulisci([_riga("riparto_senza_quote", "r2")], [_padre("r2", 118.10)])
    p1, p2, p3 = _patch_pulisci(sb, netto=96.80)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=True)

    sostituisci = [c for c in sb.rpc_calls if c[0] == "sostituisci_quote_riparto"]
    assert len(sostituisci) == 1
    assert sostituisci[0][1]["p_importo_totale"] == 96.80
    assert len(sostituisci[0][1]["p_quote"]) == 2, "una quota per sede operativa"
    assert out["riparati"][0]["tipo_incoerenza"] == "riparto_senza_quote"


def test_auto_pulisci_non_elimina_riparti_senza_documento():
    """I 2 TOYOTA di agosto: il riparto orfano è l'unica traccia della fattura persa.

    Eliminarlo farebbe sparire il sintomo insieme alla prova. Deve finire in
    `non_toccati`, senza alcuna scrittura.
    """
    sb = _FakeSBPulisci(
        [_riga("riparto_senza_documento", "r3"), _riga("orfano", None)],
        [_padre("r3")],
    )
    p1, p2, p3 = _patch_pulisci(sb)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=True)

    assert out["riparati"] == []
    assert len(out["non_toccati"]) == 2
    assert {v["tipo_incoerenza"] for v in out["non_toccati"]} == {
        "riparto_senza_documento", "orfano"}
    assert sb.rpc_calls == [], "nessuna scrittura per le classi non riparabili"


def test_auto_pulisci_salta_netto_zero():
    """Una NC che azzera esattamente il costo: non c'è più nulla da distribuire."""
    import services.riparto_service as rs
    sb = _FakeSBPulisci([_riga("riparto_segno_incoerente", "r1")], [_padre("r1")])
    with patch.object(riparto, "_get_supabase_client", MagicMock(return_value=sb)), \
         patch.object(rs, "_pesi_e_netto_categoria_fattura", MagicMock(return_value=None)), \
         patch.object(rs, "esplodi_quote_per_categoria", MagicMock()) as esplodi:
        out = riparto.riparto_auto_pulisci(apply=True)

    assert out["riparati"] == []
    assert len(out["saltati"]) == 1
    assert "da valutare a mano" in out["saltati"][0]["motivo"]
    assert not esplodi.called


def test_auto_pulisci_salta_costo_manuale_senza_file():
    sb = _FakeSBPulisci(
        [_riga("riparto_segno_incoerente", "r1", fo=None)],
        [_padre("r1", fo=None)],
    )
    p1, p2, p3 = _patch_pulisci(sb)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=True)

    assert len(out["saltati"]) == 1
    assert "costo manuale" in out["saltati"][0]["motivo"]


def test_auto_pulisci_filtra_per_account():
    righe = [
        _riga("riparto_segno_incoerente", "r1"),
        {**_riga("riparto_segno_incoerente", "r9"), "user_id": "altro-account"},
    ]
    sb = _FakeSBPulisci(righe, [_padre("r1"), _padre("r9")])
    p1, p2, p3 = _patch_pulisci(sb)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=False, user_id=UID)

    assert len(out["riparati"]) == 1
    assert out["riparati"][0]["riparto_id"] == "r1"


def test_auto_pulisci_niente_da_fare_e_idempotente():
    sb = _FakeSBPulisci([], [])
    p1, p2, p3 = _patch_pulisci(sb)
    with p1, p2, p3:
        out = riparto.riparto_auto_pulisci(apply=True)

    assert out == {"applicato": True, "riparati": [], "saltati": [],
                   "non_toccati": [], "mesi_ricalcolati": 0}
    assert sb.rpc_calls == []
