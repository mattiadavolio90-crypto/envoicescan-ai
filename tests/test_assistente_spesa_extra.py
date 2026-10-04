"""Fase D1 del piano consulente: la spesa extra dettata all'assistente.

Le regole pure (giorno, categoria, IVA, importo, id della proposta) e la Conferma
ripetuta. Il percorso intero su Postgres vero sta in
`test_sql_assistente_registra.py` e `test_sql_chat_proposte.py`.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from services.routers import assistente as A

OGGI = date(2026, 1, 5)
ID = str(uuid.uuid4())


def _spesa(**kw):
    base = {"tipo": "spesa_extra", "ristorante_id": "x", "data": "2026-01-05", "categoria": "LATTICINI",
            "descrizione": "Latte", "importo": 20, "id_proposta": ID}
    return A.RegistraRequest(**{**base, **kw})


def _codice(fn, *args):
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    return exc.value.status_code


# ─── Giorno: oggi e i 12 mesi interi prima ────────────────────────────────────
@pytest.mark.parametrize("testo", ["2026-01-05", "2025-01-01"])
def test_giorno_della_spesa_ai_confini_e_ammesso(testo):
    assert A.valida_giorno_spesa(testo, OGGI) == date.fromisoformat(testo)


@pytest.mark.parametrize("testo", ["2026-01-06", "2024-12-31", "05/01/2026", "", None])
def test_giorno_della_spesa_fuori_finestra_o_malformato_e_400(testo):
    assert _codice(A.valida_giorno_spesa, testo, OGGI) == 400


# ─── La riga che si scrive ────────────────────────────────────────────────────
def test_senza_iva_dichiarata_si_registra_l_importo_com_e():
    riga = A.valida_spesa(_spesa(), OGGI)
    assert riga == {"id": ID, "data_spesa": "2026-01-05", "tipo": "fb", "categoria": "LATTICINI",
                    "descrizione": "Latte", "importo": 20.0}


@pytest.mark.parametrize("aliquota,netto", [(4, 19.23), (5, 19.05), (10, 18.18), (22, 16.39)])
def test_con_iva_dichiarata_si_registra_il_netto(aliquota, netto):
    assert A.valida_spesa(_spesa(iva_inclusa=aliquota), OGGI)["importo"] == netto


def test_la_categoria_decide_il_tipo():
    assert A.valida_spesa(_spesa(categoria="UTENZE E LOCALI"), OGGI)["tipo"] == "generale"
    assert A.valida_spesa(_spesa(categoria="MATERIALE DI CONSUMO"), OGGI)["tipo"] == "generale"
    assert A.valida_spesa(_spesa(categoria="VINI"), OGGI)["tipo"] == "fb"


def test_la_descrizione_si_ripulisce_dagli_spazi():
    assert A.valida_spesa(_spesa(descrizione="  Latte  "), OGGI)["descrizione"] == "Latte"


def test_il_tetto_e_ammesso():
    assert A.valida_spesa(_spesa(importo=A.TETTO_SPESA), OGGI)["importo"] == A.TETTO_SPESA


@pytest.mark.parametrize("campo,valore", [
    ("categoria", "Da Classificare"),
    ("categoria", "📝 NOTE E DICITURE"),
    ("categoria", "PERSONALE"),
    ("categoria", None),
    ("descrizione", "   "),
    ("descrizione", None),
    ("descrizione", "x" * (A.DESCRIZIONE_MAX + 1)),
    ("importo", 0),
    ("importo", -5),
    ("importo", None),
    ("importo", float("nan")),
    ("importo", A.TETTO_SPESA + 0.01),
    ("iva_inclusa", 7),
    ("iva_inclusa", 0),
    ("id_proposta", None),
    ("id_proposta", "non-un-uuid"),
    ("data", "2026-01-06"),
])
def test_spesa_non_valida_e_400(campo, valore):
    assert _codice(A.valida_spesa, _spesa(**{campo: valore}), OGGI) == 400


def test_le_categorie_offerte_al_modello_sono_quelle_che_la_conferma_accetta():
    for categoria in A.CATEGORIE_SPESA:
        assert A.valida_spesa(_spesa(categoria=categoria), OGGI)["categoria"] == categoria
    assert len(A.CATEGORIE_SPESA) == len(set(A.CATEGORIE_SPESA)) == 29


# ─── L'aliquota detta al modello ──────────────────────────────────────────────
@pytest.mark.parametrize("args,attesa", [
    ({}, None), ({"iva": None}, None), ({"iva": 0}, None), ({"iva": 4}, 4), ({"iva": 22.0}, 22),
])
def test_aliquota_detta(args, attesa):
    assert A._aliquota_detta(args) == (attesa, None)


@pytest.mark.parametrize("iva", [7, 4.5, True, "dieci"])
def test_aliquota_detta_non_valida_e_un_errore_per_il_modello(iva):
    aliquota, errore = A._aliquota_detta({"iva": iva})
    assert aliquota is None and errore["errore"] == "aliquota IVA non valida"


# ─── Due spese diverse sono due card ──────────────────────────────────────────
def _proposta(**kw):
    base = {"tipo": "spesa_extra", "ristorante_id": "x", "data": "2026-01-05", "categoria": "LATTICINI",
            "descrizione": "Latte", "importo": 20.0, "id_proposta": str(uuid.uuid4())}
    return A.PropostaCifra(**{**base, **kw})


def test_la_stessa_spesa_due_volte_e_una_card_sola():
    assert A.chiave_proposta(_proposta()) == A.chiave_proposta(_proposta(descrizione="LATTE"))


@pytest.mark.parametrize("campo,valore", [
    ("descrizione", "Panna"), ("importo", 21.0), ("categoria", "SALUMI"), ("data", "2026-01-04"),
    ("iva_inclusa", 4),
])
def test_spese_diverse_sono_card_diverse(campo, valore):
    assert A.chiave_proposta(_proposta()) != A.chiave_proposta(_proposta(**{campo: valore}))


# ─── La Conferma ripetuta non scrive una seconda spesa ────────────────────────
class _Tabella:
    def __init__(self, righe, fallisce):
        self.righe, self.fallisce, self.filtri, self.inserite = righe, fallisce, {}, []

    def insert(self, riga):
        self.inserite.append(riga)
        return self

    def select(self, *_):
        return self

    def eq(self, col, val):
        self.filtri[col] = val
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if self.inserite and not self.filtri:
            if self.fallisce:
                raise RuntimeError("duplicate key value violates unique constraint")
            return type("R", (), {"data": self.inserite})()
        trovate = [r for r in self.righe if all(r.get(k) == v for k, v in self.filtri.items())]
        return type("R", (), {"data": trovate})()


class _Sb:
    def __init__(self, righe=(), fallisce=False):
        self.tabella = _Tabella(list(righe), fallisce)

    def table(self, nome):
        assert nome == "spese_extra"
        return self.tabella


@pytest.fixture
def oggi(monkeypatch):
    monkeypatch.setattr(A, "_oggi", lambda: OGGI)


def test_la_spesa_si_inserisce_con_l_id_della_proposta(oggi):
    sb = _Sb()
    valori = A._registra_spesa(sb, {"id": "u-1"}, "r-1", _spesa(iva_inclusa=4))
    [riga] = sb.tabella.inserite
    assert riga["id"] == ID and riga["ristorante_id"] == "r-1" and riga["user_id"] == "u-1"
    assert valori == {"data_spesa": "2026-01-05", "tipo": "fb", "categoria": "LATTICINI",
                      "descrizione": "Latte", "importo": 19.23}


def test_conferma_ripetuta_sulla_stessa_spesa_e_un_successo(oggi):
    sb = _Sb([{"id": ID, "ristorante_id": "r-1", "importo": "20.00"}], fallisce=True)
    assert A._registra_spesa(sb, {"id": "u-1"}, "r-1", _spesa())["importo"] == 20.0


@pytest.mark.parametrize("righe", [
    [],
    [{"id": ID, "ristorante_id": "r-altra", "importo": 20}],
    [{"id": ID, "ristorante_id": "r-1", "importo": 25}],
])
def test_insert_fallito_senza_la_stessa_spesa_e_500(oggi, righe):
    assert _codice(A._registra_spesa, _Sb(righe, fallisce=True), {"id": "u-1"}, "r-1", _spesa()) == 500
