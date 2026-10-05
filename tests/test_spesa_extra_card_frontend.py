"""Fase D1 del piano consulente: la card della spesa extra nella Home (`lib/home-chat.ts`).

La proposta arriva dal worker o da sessionStorage e la Conferma la rimanda al
server cosi' com'e': qui si prova che il client la riconosca, ne rimandi solo i
campi della Conferma, dica cosa registra (la cifra pagata, IVA compresa) e, dopo, dove la trova.
L'ultimo test fa girare la proposta vera del worker attraverso il client e di
nuovo nella validazione del worker.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from services.routers import assistente as A
from tests.helpers_ts import esegui_ts

MODULO = "lib/home-chat"


def _chiama(fn, args):
    return esegui_ts(MODULO, f"emit(m.{fn}(...input));", argomento=args, richiede=[fn])


def _proposta(**kw):
    base = {"tipo": "spesa_extra", "ristorante_id": "r-1", "sede_nome": "CASATI 14", "data": "2026-10-01",
            "fatturato_iva10": 0, "altri_ricavi_noiva": 0, "fatturato_iva22": 0,
            "categoria": "LATTICINI", "descrizione": "Latte", "importo": 20,
            "id_proposta": "6f1c3a52-0000-4000-8000-000000000001", "doppione": False}
    return {**base, **kw}


def test_la_spesa_valida_e_riconosciuta():
    assert _chiama("propostaValida", [_proposta()]) is True


def test_la_card_aperta_prima_del_deploy_resta_valida():
    """Una proposta in sessionStorage della versione con lo scorporo (5/10)."""
    assert _chiama("propostaValida", [_proposta(iva_inclusa=4, importo_netto=19.23)]) is True


@pytest.mark.parametrize("campo,valore", [
    ("categoria", ""), ("categoria", None), ("descrizione", "  "), ("descrizione", None),
    ("importo", 0), ("importo", -1), ("importo", None), ("id_proposta", None), ("id_proposta", ""),
    ("data", "1/10/2026"), ("data", None), ("doppione", "si"),
])
def test_la_spesa_malformata_e_scartata(campo, valore):
    assert _chiama("propostaValida", [_proposta(**{campo: valore})]) is False


def test_la_conferma_rimanda_solo_i_campi_della_registrazione():
    corpo = _chiama("corpoConferma", [_proposta(iva_inclusa=4, importo_netto=19.23)])
    assert corpo == {"tipo": "spesa_extra", "ristorante_id": "r-1", "data": "2026-10-01",
                     "fatturato_iva10": 0, "altri_ricavi_noiva": 0, "fatturato_iva22": 0,
                     "categoria": "LATTICINI", "descrizione": "Latte", "importo": 20,
                     "id_proposta": "6f1c3a52-0000-4000-8000-000000000001"}


def test_la_card_dice_la_cifra_pagata():
    t = _chiama("testoCard", [_proposta(), 2026])
    assert t["titolo"] == "Spesa extra di giovedì 1 ottobre"
    assert t["sede"] == "CASATI 14"
    assert t["righe"] == [["Voce", "Latte"], ["Categoria", "LATTICINI"], ["Importo", "20,00 €"]]
    assert t["totale"] is None and t["nota"] is None


def test_la_card_di_prima_del_deploy_mostra_la_cifra_che_si_registra():
    """Con lo scorporo la card diceva il netto; ora la Conferma salva l'importo pieno
    e la card deve dire quello, non il netto rimasto in sessionStorage."""
    t = _chiama("testoCard", [_proposta(iva_inclusa=4, importo_netto=19.23), 2026])
    assert t["righe"][2:] == [["Importo", "20,00 €"]]


def test_il_doppione_e_detto_sulla_card():
    t = _chiama("testoCard", [_proposta(doppione=True), 2026])
    assert "già una spesa uguale" in t["nota"]


def _card(**kw):
    return {"id": "1-0", "proposta": _proposta(**kw), "stato": "invio"}


def test_dopo_la_conferma_dice_dove_trovarla_e_come_entra_nel_mol():
    esito = _chiama("esitoConferma", [200, {"ok": True}, _card()])
    assert esito["stato"] == "registrata"
    assert "Spese dell'Agenda" in esito["messaggio"] and "Recupera dal tab Spese" in esito["messaggio"]


def test_le_altre_cifre_dopo_la_conferma_dicono_solo_registrato():
    incasso = {"id": "1-0", "stato": "invio", "proposta": {
        "tipo": "incasso_giorno", "ristorante_id": "r-1", "data": "2026-10-01",
        "fatturato_iva10": 100, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}}
    assert _chiama("esitoConferma", [200, {}, incasso])["messaggio"] == "Registrato."


def test_un_409_sulla_spesa_non_si_legge_come_gia_registrata():
    esito = _chiama("esitoConferma", [409, {"detail": {"motivo": "valore_cambiato", "attuale": {}}}, _card()])
    assert esito["stato"] != "registrata"


def test_la_proposta_del_worker_passa_dal_client_e_torna_valida_al_worker():
    """Parita' worker → client → worker: cio' che il worker propone il client lo
    mostra, e cio' che il client rimanda la Conferma lo accetta con la stessa cifra."""
    oggi = date(2026, 10, 4)
    proposta = A.PropostaCifra(
        tipo="spesa_extra", ristorante_id=str(uuid.uuid4()), sede_nome="X", data="2026-10-01",
        categoria="UTENZE E LOCALI", descrizione="Idraulico", importo=150.0,
        id_proposta=str(uuid.uuid4()),
    ).model_dump()
    assert _chiama("propostaValida", [proposta]) is True
    corpo = _chiama("corpoConferma", [proposta])
    riga = A.valida_spesa(A.RegistraRequest(**corpo), oggi)
    assert riga["importo"] == proposta["importo"] == 150.0
    assert riga["id"] == proposta["id_proposta"] and riga["tipo"] == "generale"
