"""Fase 3, step 2: cosa dice il prompt sulle cifre dettate.

Il prompt intero del ristorante e' confrontato byte per byte in
`test_chat_settore_retail.py`; qui le deviazioni: senza la pagina Margini le
regole non ci sono (gli strumenti non ci sono), il negozio chiede anche il 22%,
la catena rimanda al locale.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from tests.test_chat_settore_retail import USER, _Settembre, _kpi_mock, _sb

REGOLA = "usa proponi_incasso, proponi_personale o proponi_fatturato_mese"


def _prompt(monkeypatch, user=USER, settore=SETTORE_RISTORAZIONE, cifre=True):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    return fw._build_chat_system_prompt(user, _sb(), None, "r-1", settore, cifre_dettate=cifre)


def test_con_margini_le_regole_delle_cifre_dettate_ci_sono(monkeypatch):
    p = _prompt(monkeypatch)
    assert REGOLA in p
    assert "Non dire mai che la cifra e' registrata" in p
    assert "CHIEDIGLI quanto e' al 10% e quanto senza IVA" in p
    assert "Il 22% indicalo solo se lo nomina il cliente." in p


REGOLA_SPESA = "usa proponi_spesa: va nelle Spese dell'Agenda, mai nel personale"


def test_senza_margini_niente_regole_ne_offerta_di_dettare(monkeypatch):
    senza = dict(USER, pagine_abilitate={"analisi_fatture": True})
    p = _prompt(monkeypatch, user=senza)
    assert "proponi_" not in p
    assert "prepari tu la registrazione" not in p


def test_con_la_sola_agenda_c_e_solo_la_regola_della_spesa(monkeypatch):
    solo_agenda = dict(USER, pagine_abilitate={"analisi_fatture": True, "agenda": True})
    p = _prompt(monkeypatch, user=solo_agenda)
    assert REGOLA_SPESA in p
    assert REGOLA not in p
    assert "prepari tu la registrazione" not in p


def test_con_margini_ma_senza_agenda_niente_regola_della_spesa(monkeypatch):
    p = _prompt(monkeypatch, user=dict(USER, pagine_abilitate={"margini": True}))
    assert REGOLA in p
    assert "proponi_spesa" not in p


def test_con_tutte_le_pagine_c_e_anche_la_spesa(monkeypatch):
    assert REGOLA_SPESA in _prompt(monkeypatch)


def test_senza_card_nel_client_il_prompt_e_quello_di_prima(monkeypatch):
    """Il default (`/m`, ogni chiamante che non lo dichiara): niente regole e gli
    avvisi di ieri. Il confronto byte per byte col testo di ieri e' in
    test_chat_settore_retail.test_ramo_ristorazione_e_identico_a_prima."""
    p = _prompt(monkeypatch, cifre=False)
    assert "proponi_" not in p
    assert "prepari tu la registrazione" not in p
    assert "Suggerisci di registrare i ricavi in Movimenti → Ricavi." in p
    assert REGOLA_SPESA not in p


def test_con_card_gli_avvisi_offrono_di_dettare(monkeypatch):
    # Dopo il 15: prima l'avviso del personale non c'e' (il sollecito parte da li').
    monkeypatch.setattr(fw, "datetime", _Settembre)
    p = _prompt(monkeypatch)
    assert "Movimenti → Ricavi, oppure di dettarti qui il fatturato del mese" in p
    assert "(sezione Personale), oppure di dirti qui la cifra" in p


def test_il_negozio_chiede_anche_il_22(monkeypatch):
    p = _prompt(monkeypatch, settore=SETTORE_RETAIL)
    assert REGOLA in p
    assert "CHIEDIGLI quanto e' al 22%, quanto al 10% e quanto senza IVA" in p
    assert "Il 22% indicalo solo se lo nomina il cliente." not in p


def _prompt_catena(monkeypatch, settore, cifre=True):
    monkeypatch.setattr(
        fw, "_gruppo_router_mod",
        lambda: MagicMock(gruppo_overview=MagicMock(side_effect=RuntimeError("no"))),
    )
    return fw._build_chat_system_prompt_catena(USER, _sb(), None, settore, cifre_dettate=cifre)


def test_la_catena_rimanda_alla_home_del_locale(monkeypatch):
    p = _prompt_catena(monkeypatch, SETTORE_RISTORAZIONE)
    assert "dillo.\n- Se il cliente ti detta una cifra da registrare" in p
    assert "qui non si registra: spiega che basta aprire la Home di quel locale" in p
    assert "proponi_" not in p
    assert "aprire la Home di quel punto vendita" in _prompt_catena(monkeypatch, SETTORE_RETAIL)


def test_senza_card_la_catena_non_rimanda_alla_home(monkeypatch):
    """Senza card nella Home del locale il rinvio sarebbe una promessa falsa."""
    p = _prompt_catena(monkeypatch, SETTORE_RISTORAZIONE, cifre=False)
    assert "qui non si registra" not in p
    assert "Non inventare numeri: se uno strumento torna vuoto, dillo." in p


class _Notte(datetime):
    """00:30 del 1/10 a Roma = 22:30 del 30/9 in UTC, l'ora dei server."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 30, 22, 30, tzinfo=timezone.utc).astimezone(tz)


def test_dopo_mezzanotte_oggi_e_il_giorno_di_roma(monkeypatch):
    """«Ieri» si calcola da qui: dopo la chiusura un giorno sbagliato finirebbe sulla card."""
    monkeypatch.setattr(fw, "datetime", _Notte)
    assert "Oggi e' 1 ottobre 2026." in _prompt(monkeypatch)
    assert "Oggi è 1/10/2026." in _prompt_catena(monkeypatch, SETTORE_RISTORAZIONE)


def test_le_regole_nominano_solo_strumenti_che_esistono():
    nomi = {t["function"]["name"] for t in fw._CHAT_TOOLS_SEDE}
    assert set(fw._assistente.STRUMENTI_PROPOSTA) <= nomi
    pagina_per_strumento = {
        "proponi_incasso": "incasso_giorno", "proponi_personale": "personale_mese",
        "proponi_fatturato_mese": "fatturato_mese", "proponi_spesa": "spesa_extra",
    }
    assert set(pagina_per_strumento) == set(fw._assistente.STRUMENTI_PROPOSTA)
    for nome, tipo in pagina_per_strumento.items():
        # Lo strumento c'e' con la stessa pagina che la Conferma pretende.
        assert fw._CHAT_TOOL_FLAG[nome] == fw._assistente.PAGINA_PER_TIPO[tipo]
        assert nome not in fw._CHAT_TOOLS_SEDE_IN_CATENA
    assert fw._CHAT_TOOL_FLAG["proponi_spesa"] == "agenda"


def _parametri(nome):
    [t] = [t for t in fw._CHAT_TOOLS_SEDE if t["function"]["name"] == nome]
    return t["function"]["parameters"]


def test_lo_strumento_del_personale_offre_le_tre_voci_e_nessuna_e_obbligatoria():
    """Fase D2: il modello deve poter dettare le sole ore extra. Una voce obbligatoria
    lo costringerebbe a inventarla (o a passare 0)."""
    par = _parametri("proponi_personale")
    assert set(fw._assistente.VOCI_PERSONALE) <= set(par["properties"])
    assert set(par["required"]) == {"anno", "mese"}


@pytest.mark.parametrize("nome", ["proponi_incasso", "proponi_fatturato_mese"])
def test_gli_incassi_hanno_solo_10_22_e_senza_iva(nome):
    """Mattia, 5/10/2026: niente 4/5% sugli incassi."""
    par = _parametri(nome)
    assert set(par["properties"]) - {"data", "anno", "mese"} == {"iva10", "senza_iva", "iva22"}
