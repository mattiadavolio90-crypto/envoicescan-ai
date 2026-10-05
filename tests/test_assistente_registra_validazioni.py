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
    assert A.valida_personale(_body(tipo="personale_mese", costo_dipendenti=A.TETTO_PERSONALE_MESE)) == \
        {"costo_dipendenti": A.TETTO_PERSONALE_MESE}


# ─── Gli argomenti del modello ────────────────────────────────────────────────
@pytest.mark.parametrize("valore,atteso", [
    (2026, 2026), ("9", 9), (9.0, 9), (9.5, None), (True, None), ("nove", None),
    (float("inf"), None), (float("nan"), None), ("Infinity", None),
])
def test_intero_dal_modello(valore, atteso):
    assert A._intero({"x": valore}, "x") == atteso


def test_la_divisione_da_chiedere_dipende_dal_settore():
    assert "(il 22% solo se lo dice lui)" in A._chiedi_divisione("ristorazione")["cosa_fare"]
    assert "(il 22% solo se lo dice lui)" in A._chiedi_divisione(None)["cosa_fare"]
    negozio = A._chiedi_divisione("retail")["cosa_fare"]
    assert "quanto e' al 22%, quanto al 10% e quanto senza IVA" in negozio


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


# ─── Il personale: lordo, ore extra e chiamata ────────────────────────────────
class _SbMese:
    """Una riga di margini_mensili; tiene la select chiesta, perche' una select a
    colonne esplicite che dimentica la chiamata la perde anche se il mock la da'."""

    def __init__(self, riga):
        self.riga = riga
        self.select_chiesta = None

    def table(self, _nome):
        return self

    def select(self, colonne):
        self.select_chiesta = colonne
        return self

    def eq(self, *_a):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return type("R", (), {"data": [self.riga] if self.riga else []})()


def test_leggi_personale_chiede_e_porta_anche_la_chiamata():
    sb = _SbMese({"id": 7, "costo_dipendenti": 1000, "costo_personale_extra": 200,
                  "costo_personale_chiamata": 37})
    letto = A.leggi_personale(sb, "rid", 2026, 9)
    assert "costo_personale_chiamata" in sb.select_chiesta
    assert letto.attuale == {"costo_dipendenti": 1000.0}
    assert letto.grezzo == {"costo_dipendenti": 1000}
    assert letto.info == {"costo_dipendenti": 1000.0, "costo_personale_extra": 200.0,
                          "costo_personale_chiamata": 37.0}


def test_leggi_personale_sulle_voci_dettate():
    sb = _SbMese({"id": 7, "costo_dipendenti": 1000, "costo_personale_extra": None,
                  "costo_personale_chiamata": 37})
    letto = A.leggi_personale(sb, "rid", 2026, 9, ("costo_personale_extra", "costo_personale_chiamata"))
    assert letto.attuale == {"costo_personale_extra": 0.0, "costo_personale_chiamata": 37.0}
    assert letto.grezzo == {"costo_personale_extra": None, "costo_personale_chiamata": 37}


def test_leggi_personale_voci_dettate_a_zero_e_nessun_valore():
    sb = _SbMese({"id": 7, "costo_dipendenti": 1000, "costo_personale_extra": 0,
                  "costo_personale_chiamata": None})
    letto = A.leggi_personale(sb, "rid", 2026, 9, ("costo_personale_extra", "costo_personale_chiamata"))
    assert letto.attuale is None and letto.id == "7"


def test_leggi_personale_chiamata_null_vale_zero():
    sb = _SbMese({"id": 7, "costo_dipendenti": 1000, "costo_personale_extra": None,
                  "costo_personale_chiamata": None})
    assert A.leggi_personale(sb, "rid", 2026, 9).info == {
        "costo_dipendenti": 1000.0, "costo_personale_extra": 0.0, "costo_personale_chiamata": 0.0}


OGGI_P = date(2026, 10, 4)


def test_proposta_personale_col_solo_lordo_e_la_chiamata_che_resta():
    sb = _SbMese({"id": 7, "costo_dipendenti": 0, "costo_personale_extra": 0,
                  "costo_personale_chiamata": 37})
    proposta, al_modello = A._proponi_personale({"anno": 2026, "mese": 9, "importo": 1000}, sb,
                                                "rid", "NAVIGLI", OGGI_P)
    assert (proposta.costo_dipendenti, proposta.costo_personale_extra, proposta.costo_personale_chiamata) == \
        (1000.0, None, None)
    assert proposta.restano == {"costo_personale_chiamata": 37.0}
    assert al_modello["si_registra"] == {"lordo": 1000.0}
    assert al_modello["restano_gia_registrate"] == {"chiamata": 37.0}


def test_proposta_personale_con_le_tre_voci_dettate():
    sb = _SbMese({"id": 7, "costo_dipendenti": 7000, "costo_personale_extra": 200,
                  "costo_personale_chiamata": 0})
    proposta, al_modello = A._proponi_personale(
        {"anno": 2026, "mese": 9, "importo": 7320, "ore_extra": 688, "chiamata": 150}, sb, "rid", None, OGGI_P)
    assert (proposta.costo_dipendenti, proposta.costo_personale_extra, proposta.costo_personale_chiamata) == \
        (7320.0, 688.0, 150.0)
    assert proposta.precedente == {"costo_dipendenti": 7000.0, "costo_personale_extra": 200.0,
                                   "costo_personale_chiamata": 0.0}
    assert proposta.restano is None and "restano_gia_registrate" not in al_modello
    assert al_modello["si_registra"] == {"lordo": 7320.0, "ore_extra": 688.0, "chiamata": 150.0}


def test_proposta_delle_sole_ore_extra_lascia_il_lordo():
    sb = _SbMese({"id": 7, "costo_dipendenti": 7320, "costo_personale_extra": 0,
                  "costo_personale_chiamata": 0})
    proposta, al_modello = A._proponi_personale({"anno": 2026, "mese": 9, "ore_extra": 688}, sb,
                                                "rid", None, OGGI_P)
    assert (proposta.costo_dipendenti, proposta.costo_personale_extra) == (None, 688.0)
    assert proposta.precedente is None and al_modello["valore_attuale"] == "nessun valore"
    assert proposta.restano == {"costo_dipendenti": 7320.0}


def test_una_voce_a_zero_dal_modello_non_si_scrive():
    """Il modello che passa 0 per la voce non detta non la cancella."""
    sb = _SbMese({"id": 7, "costo_dipendenti": 7320, "costo_personale_extra": 0,
                  "costo_personale_chiamata": 0})
    proposta, _ = A._proponi_personale({"anno": 2026, "mese": 9, "importo": 0, "ore_extra": 688, "chiamata": 0},
                                       sb, "rid", None, OGGI_P)
    assert (proposta.costo_dipendenti, proposta.costo_personale_extra, proposta.costo_personale_chiamata) == \
        (None, 688.0, None)


@pytest.mark.parametrize("args", [
    {"anno": 2026, "mese": 9},
    {"anno": 2026, "mese": 9, "importo": 0, "ore_extra": 0},
    {"anno": 2026, "mese": 9, "ore_extra": -5},
    {"anno": 2026, "mese": 9, "importo": 200_000, "ore_extra": 100_000.01},
])
def test_proposta_personale_senza_voci_valide_e_un_errore(args):
    sb = _SbMese({"id": 7, "costo_dipendenti": 0})
    proposta, al_modello = A.proponi("proponi_personale", args, user={"id": "u"}, sb=_SbSede(sb),
                                     ristorante_id=RID_P, sede_nome=None)
    assert proposta is None
    assert al_modello["errore"] in ("L'importo deve essere maggiore di zero", "Importo fuori scala: controlla la cifra",
                                    "Importo non valido: costo_personale_extra")


def test_la_stessa_strada_con_una_voce_valida_propone():
    """Controprova del test sopra: la sede finta non e' la ragione del rifiuto."""
    proposta, _ = A.proponi("proponi_personale", {"anno": 2026, "mese": 9, "chiamata": 37}, user={"id": "u"},
                            sb=_SbSede(_SbMese({"id": 7, "costo_dipendenti": 0})), ristorante_id=RID_P,
                            sede_nome=None)
    assert proposta is not None and proposta.costo_personale_chiamata == 37.0


@pytest.mark.parametrize("arg", ["importo", "ore_extra", "chiamata"])
def test_proposta_personale_con_importo_in_testo(arg):
    assert A._proponi_personale({"anno": 2026, "mese": 9, arg: "1.000"}, _SbMese(None), "rid", None, OGGI_P) == \
        (None, A._IMPORTO_IN_TESTO)


def test_proposta_personale_gia_cosi():
    sb = _SbMese({"id": 7, "costo_dipendenti": 7320, "costo_personale_extra": 688,
                  "costo_personale_chiamata": 0})
    proposta, al_modello = A._proponi_personale({"anno": 2026, "mese": 9, "ore_extra": 688}, sb,
                                                "rid", None, OGGI_P)
    assert proposta is None and al_modello == {"gia_registrato": True, "valore_attuale": {"ore_extra": 688.0}}


def test_proposta_personale_senza_extra_ne_chiamata():
    sb = _SbMese({"id": 7, "costo_dipendenti": 0, "costo_personale_extra": 0,
                  "costo_personale_chiamata": 0})
    proposta, al_modello = A._proponi_personale({"anno": 2026, "mese": 9, "importo": 1000}, sb,
                                                "rid", None, OGGI_P)
    assert (proposta.costo_personale_extra, proposta.costo_personale_chiamata, proposta.restano) == \
        (None, None, None)
    assert "restano_gia_registrate" not in al_modello


RID_P = "6f1c3a52-0000-4000-8000-0000000000aa"


class _SbSede:
    """La sede esiste (sede_scrivibile) e margini_mensili e' quella di `mese`."""

    def __init__(self, mese):
        self.mese = mese

    def table(self, nome):
        if nome == "ristoranti":
            return _SbMese({"id": RID_P})
        return self.mese


# ─── Il valore dettato vs le voci della Conferma ──────────────────────────────
@pytest.mark.parametrize("kw,atteso", [
    ({"costo_personale_extra": 500}, {"costo_personale_extra": 500.0}),
    ({"costo_dipendenti": 0, "costo_personale_chiamata": 37.004}, {"costo_personale_chiamata": 37.0}),
    ({"costo_dipendenti": 7320, "costo_personale_extra": 688, "costo_personale_chiamata": 150},
     {"costo_dipendenti": 7320.0, "costo_personale_extra": 688.0, "costo_personale_chiamata": 150.0}),
])
def test_valida_personale_tiene_le_sole_voci_dette(kw, atteso):
    assert A.valida_personale(_body(tipo="personale_mese", **kw)) == atteso


def test_il_tetto_del_personale_vale_sulla_somma_delle_voci():
    assert A.valida_personale(_body(tipo="personale_mese", costo_dipendenti=200_000, costo_personale_extra=100_000))
    assert _codice(A.valida_personale, _body(tipo="personale_mese", costo_dipendenti=200_000,
                                             costo_personale_extra=100_000.01)) == 400


@pytest.mark.parametrize("campo", ["costo_personale_extra", "costo_personale_chiamata"])
def test_una_voce_negativa_e_400_anche_accanto_a_una_valida(campo):
    assert _codice(A.valida_personale, _body(tipo="personale_mese", costo_dipendenti=1000, **{campo: -1})) == 400


# ─── Incassi al 4% e al 5%: scorporati nella parte senza IVA ──────────────────
@pytest.mark.parametrize("extra,altri", [
    ({"iva4": 208}, 300.0 + 200.0),
    ({"iva5": 105}, 300.0 + 100.0),
    ({"iva4": 104, "iva5": 210}, 300.0 + 100.0 + 200.0),
    ({"iva4": 20}, 300.0 + 19.23),
    ({"iva4": 0, "iva5": None}, 300.0),
])
def test_il_4_e_il_5_si_sommano_senza_iva(extra, altri):
    importi, errore, ridotte = A._importi_dettati({"iva10": 1000, "senza_iva": 300, **extra}, None)
    assert errore == {}
    assert importi == {"fatturato_iva10": 1000.0, "altri_ricavi_noiva": altri, "fatturato_iva22": 0.0}
    assert ridotte == {k: float(v) for k, v in extra.items() if v}


def test_senza_4_e_5_gli_importi_restano_quelli_detti():
    assert A._importi_dettati({"iva10": 1000, "senza_iva": 300.5, "iva22": 40}, "retail") == (
        {"fatturato_iva10": 1000.0, "altri_ricavi_noiva": 300.5, "fatturato_iva22": 40.0}, {}, {})


@pytest.mark.parametrize("arg", ["iva4", "iva5"])
def test_il_4_o_il_5_in_testo_si_rifiuta(arg):
    assert A._importi_dettati({"iva10": 1000, "senza_iva": 0, arg: "1.040"}, None) == (None, A._IMPORTO_IN_TESTO, {})


@pytest.mark.parametrize("args", [
    {"iva10": 1000, "senza_iva": 0, "iva4": -10},
    {"iva10": 1000, "senza_iva": 0, "iva5": float("nan")},
    {"iva10": 1000, "senza_iva": -100, "iva4": 208},
])
def test_il_4_o_il_5_non_validi_sono_400(args):
    assert _codice(A._importi_dettati, args, None) == 400


def test_senza_divisione_si_chiede_anche_col_4():
    importi, errore, _ = A._importi_dettati({"iva4": 208}, None)
    assert importi is None and errore["errore"] == "divisione IVA mancante"


def test_al_modello_il_4_dice_quanto_si_registra():
    assert A._ridotte_al_modello({"iva4": 20.0})["iva_ridotta"] == {"al_4%": {"detto": 20.0, "senza_iva": 19.23}}
    assert A._ridotte_al_modello({}) == {}
