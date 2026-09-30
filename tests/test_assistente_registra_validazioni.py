"""Fase 3: le validazioni pure della «Conferma» delle cifre dettate.

Il comportamento sul DB (sede, 409, campi conservati) sta in
`test_sql_assistente_registra.py`; qui i confini che li' costerebbero un
Postgres per caso: il cambio d'anno dei mesi, i valori non finiti, la corsa
sull'insert.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from services.routers import assistente as A


def _body(**kw):
    base = {"tipo": "incasso_giorno", "ristorante_id": "x"}
    return A.RegistraRequest(**{**base, **kw})


def _codice(fn, *args):
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    return exc.value.status_code


# ─── Giorno ───────────────────────────────────────────────────────────────────
OGGI = date(2026, 1, 5)


@pytest.mark.parametrize("testo", ["2026-01-05", "2025-11-06"])
def test_giorno_ai_confini_e_ammesso(testo):
    assert A.valida_giorno(testo, OGGI) == date.fromisoformat(testo)


@pytest.mark.parametrize("testo", ["2026-01-06", "2025-11-05", "05/01/2026", "", None, "2026-02-30"])
def test_giorno_fuori_finestra_o_malformato_e_400(testo):
    assert _codice(A.valida_giorno, testo, OGGI) == 400


# ─── Mese ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("anno,mese", [(2026, 1), (2025, 1), (2025, 12)])
def test_mese_nella_finestra_attraversa_il_cambio_d_anno(anno, mese):
    assert A.valida_mese(anno, mese, OGGI) == (anno, mese)


@pytest.mark.parametrize("anno,mese", [(2026, 2), (2024, 12), (2026, 0), (2026, 13), (None, 1), (2026, None)])
def test_mese_fuori_finestra_o_malformato_e_400(anno, mese):
    assert _codice(A.valida_mese, anno, mese, OGGI) == 400


# ─── Importi ──────────────────────────────────────────────────────────────────
def test_importi_arrotondati_al_centesimo():
    v = A.valida_importi_incasso(_body(fatturato_iva10=100.004, altri_ricavi_noiva=0.006), 1000)
    assert v == {"fatturato_iva10": 100.0, "altri_ricavi_noiva": 0.01, "fatturato_iva22": 0.0}


@pytest.mark.parametrize("campo,valore", [
    ("fatturato_iva10", float("nan")), ("fatturato_iva10", float("inf")),
    ("altri_ricavi_noiva", -0.01), ("fatturato_iva22", -5),
])
def test_importo_non_finito_o_negativo_e_400(campo, valore):
    corpo = _body(fatturato_iva10=100, **{campo: valore}) if campo != "fatturato_iva10" else _body(**{campo: valore})
    assert _codice(A.valida_importi_incasso, corpo, 1000) == 400


def test_il_tetto_vale_sul_totale_non_sul_singolo_importo():
    assert A.valida_importi_incasso(_body(fatturato_iva10=600, altri_ricavi_noiva=400), 1000)
    assert _codice(A.valida_importi_incasso, _body(fatturato_iva10=600, altri_ricavi_noiva=400.01), 1000) == 400


def test_personale_mancante_zero_o_oltre_il_tetto_e_400():
    for valore in (None, 0, A.TETTO_PERSONALE_MESE + 0.01, float("nan")):
        assert _codice(A.valida_personale, _body(tipo="personale_mese", costo_dipendenti=valore)) == 400
    assert A.valida_personale(_body(tipo="personale_mese", costo_dipendenti=A.TETTO_PERSONALE_MESE)) == A.TETTO_PERSONALE_MESE


# ─── Gli argomenti del modello ────────────────────────────────────────────────
@pytest.mark.parametrize("valore,atteso", [
    (2026, 2026), ("9", 9), (9.0, 9), (9.5, None), (True, None), ("nove", None),
    (float("inf"), None), (float("nan"), None), ("Infinity", None),
])
def test_intero_dal_modello(valore, atteso):
    assert A._intero({"x": valore}, "x") == atteso


# ─── Il confronto con la card ─────────────────────────────────────────────────
@pytest.mark.parametrize("precedente,attuale,uguali", [
    (None, None, True),
    (None, {"costo_dipendenti": 1.0}, False),
    ({"costo_dipendenti": 1.0}, None, False),
    ({"costo_dipendenti": 1.004}, {"costo_dipendenti": 1.0}, True),
    ({"costo_dipendenti": 1.01}, {"costo_dipendenti": 1.0}, False),
    ({"fatturato_iva10": 1.0}, {"fatturato_iva10": 1.0, "altri_ricavi_noiva": 0.0}, False),
])
def test_uguali(precedente, attuale, uguali):
    assert A._uguali(precedente, attuale) is uguali


# ─── Le corse sulla scrittura ─────────────────────────────────────────────────
class _SbFinto:
    """Un insert che solleva (vincolo unico) o un update che non trova la riga."""

    def __init__(self, insert_solleva=False):
        self.insert_solleva = insert_solleva

    def table(self, _nome):
        return self

    def insert(self, _riga):
        return self

    def update(self, _payload):
        return self

    def eq(self, *_a):
        return self

    def is_(self, *_a):
        return self

    def execute(self):
        if self.insert_solleva:
            raise RuntimeError("duplicate key value violates unique constraint")
        return type("R", (), {"data": []})()


DETTATO = {"costo_dipendenti": 12000.0}
LETTO = A.Letto("id-riga", {"costo_dipendenti": 8000.0}, {"costo_dipendenti": 8000})


def test_riga_nata_durante_la_conferma_e_409_col_valore_nuovo():
    with pytest.raises(HTTPException) as exc:
        A._inserisci(_SbFinto(insert_solleva=True), "t", {}, DETTATO,
                     lambda: A.Letto("id", {"costo_dipendenti": 5.0}, {}))
    assert exc.value.status_code == 409
    assert exc.value.detail == {"motivo": "valore_cambiato", "attuale": {"costo_dipendenti": 5.0}}


def test_insert_fallito_senza_riga_nuova_e_500_non_un_successo():
    with pytest.raises(HTTPException) as exc:
        A._inserisci(_SbFinto(insert_solleva=True), "t", {}, DETTATO, lambda: A.Letto(None, None, {}))
    assert exc.value.status_code == 500


def test_insert_riuscito_con_risposta_persa_non_e_un_conflitto():
    A._inserisci(_SbFinto(insert_solleva=True), "t", {}, DETTATO,
                 lambda: A.Letto("id", {"costo_dipendenti": 12000.0}, {}))


def test_update_che_non_trova_i_valori_letti_e_409():
    with pytest.raises(HTTPException) as exc:
        A._aggiorna(_SbFinto(), "t", LETTO, "rid", {}, DETTATO,
                    lambda: A.Letto("id-riga", {"costo_dipendenti": 9000.0}, {}))
    assert exc.value.status_code == 409
    assert exc.value.detail["attuale"] == {"costo_dipendenti": 9000.0}


def test_update_che_trova_gia_il_dettato_e_un_successo():
    A._aggiorna(_SbFinto(), "t", LETTO, "rid", {}, DETTATO,
                lambda: A.Letto("id-riga", {"costo_dipendenti": 12000.0}, {}))
