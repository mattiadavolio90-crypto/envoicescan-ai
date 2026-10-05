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


# ─── Fase D3: come si chiede (la conversazione del latte, screen 1-2) ───────
#
# «inseriamo una spesa di stamattina» → la chat chiedeva la divisione fra 10%,
# 22% e senza IVA (quella degli incassi); «latte 20€» → chiedeva l'IVA; poi
# «e' food? generica o di un fornitore?», poi «Confermi?» a parole, e solo dopo
# «ok» la card. Le regole sotto sono quelle che quella conversazione ha violato.

UNA_DOMANDA = "UNA domanda alla volta, e mai cio' che il cliente ha gia' detto in questa conversazione"
NIENTE_CONFERMI = "senza chiedere \"confermi?\" a parole: la conferma e' il pulsante Conferma"
DATE = "Le date relative (\"ieri\", \"stamattina\", \"sabato scorso\") calcolale da oggi"
SPESA_SENZA_DOMANDE = (
    "Per una spesa bastano cosa e quanto (il giorno, se non lo dice, e' oggi): se manca "
    "qualcosa chiedi solo quello, senza nominare l'IVA o la categoria, e non chiedere di "
    "dividerla fra 10%, 22% e senza IVA, che vale solo per gli incassi."
)
SPESA_LORDA = (
    "L'importo e' quello pagato, IVA compresa: una spesa senza fattura non scarica l'IVA, "
    "quindi non scorporarla."
)
PIU_IVA = "Se invece dice \"piu' IVA\" fai una sola domanda, questa: \"Quanto hai pagato in tutto, IVA compresa?\""
TRE_VOCI = "Il personale ha tre voci: lordo (gli stipendi), ore extra e chiamata."
NON_CENTRA = "non usarne mai uno che non c'entra"


def test_le_regole_del_latte_ci_sono(monkeypatch):
    p = _prompt(monkeypatch)
    for regola in (UNA_DOMANDA, NIENTE_CONFERMI, DATE, SPESA_SENZA_DOMANDE, SPESA_LORDA, PIU_IVA, TRE_VOCI, NON_CENTRA):
        assert regola in p, regola
    assert "passala allo strumento" not in p


def test_le_regole_comuni_stanno_dopo_quelle_degli_strumenti(monkeypatch):
    """Una volta sola, fra gli strumenti e la regola delle bozze."""
    p = _prompt(monkeypatch)
    assert p.count(UNA_DOMANDA) == 1 and p.count(DATE) == 1
    assert p.index(REGOLA_SPESA) < p.index(UNA_DOMANDA) < p.index("Non scrivere messaggi o bozze")


def test_con_la_sola_agenda_le_date_relative_ci_sono(monkeypatch):
    """Rilievo (a) del revisore sulla D1: il sotto-utente con l'Agenda e senza
    Margini ha la spesa, e la regola su «ieri» stava solo fra quelle di Margini."""
    solo_agenda = dict(USER, pagine_abilitate={"analisi_fatture": True, "agenda": True})
    p = _prompt(monkeypatch, user=solo_agenda)
    assert DATE in p and UNA_DOMANDA in p and SPESA_SENZA_DOMANDE in p
    assert TRE_VOCI not in p


def test_con_i_soli_margini_niente_regola_della_spesa_ma_le_comuni_si(monkeypatch):
    p = _prompt(monkeypatch, user=dict(USER, pagine_abilitate={"margini": True}))
    assert UNA_DOMANDA in p and DATE in p and TRE_VOCI in p
    assert SPESA_SENZA_DOMANDE not in p


def test_senza_strumenti_nessuna_regola_su_come_chiedere(monkeypatch):
    for p in (
        _prompt(monkeypatch, cifre=False),
        _prompt(monkeypatch, user=dict(USER, pagine_abilitate={"analisi_fatture": True})),
    ):
        for regola in (UNA_DOMANDA, NIENTE_CONFERMI, DATE, SPESA_SENZA_DOMANDE, TRE_VOCI):
            assert regola not in p, regola


def test_lo_strumento_della_spesa_non_ha_l_iva():
    """Mattia, 5/10: la spesa si registra com'e' stata pagata, IVA compresa. Un
    campo `iva` nello schema inviterebbe il modello a scorporarla."""
    spesa = next(t for t in fw._CHAT_TOOLS_SEDE if t["function"]["name"] == "proponi_spesa")
    assert set(spesa["function"]["parameters"]["properties"]) == {"data", "descrizione", "categoria", "importo"}
    assert "IVA compresa" in spesa["function"]["description"]


def test_la_catena_nomina_anche_la_spesa(monkeypatch):
    """Rilievo (b) del revisore sulla D1."""
    p = _prompt_catena(monkeypatch, SETTORE_RISTORAZIONE)
    assert "una cifra da registrare (incasso, spesa, personale, fatturato)" in p
