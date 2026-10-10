"""Crediti della chat esposti da /api/home/config (services.fastapi_worker).

Il widget chat mostra i crediti che restano gia' all'apertura. Dal 10/10/2026
(fase J) tutto e' in CREDITI: spesi oggi, spesi nel mese, ricarica residua,
letti da `_chat_crediti_stato` (la RPC `chat_crediti_stato`). Per non fare
letture inutili si leggono SOLO se la chat e' disponibile (piano con limite > 0
E chat attiva); altrimenti restano 0.
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


_USER = {"id": "u-1", "piano": "base", "nome_referente": "Marco"}
_RID = "rist-abc"
_STATO = {"oggi": 12, "mese": 180, "ricarica": 300}


def _make_sb(pref_row=None):
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.single.return_value = q
    q.execute.return_value = MagicMock(data=([pref_row] if pref_row else []))
    sb.table.return_value = q
    return sb


def test_config_include_i_crediti_se_chat_disponibile():
    sb = _make_sb()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_limite_per_piano", return_value=20), \
         patch.object(fw, "_chat_crediti_stato", return_value=_STATO) as m_count:
        resp = fw.home_config_get(authorization="Bearer tok")

    assert resp.chat_limite_giorno == 20
    assert resp.chat_crediti_oggi == 12
    assert resp.chat_crediti_mese == 180
    assert resp.chat_crediti_ricarica == 300
    m_count.assert_called_once()


def test_config_non_conta_se_piano_free():
    sb = _make_sb()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_limite_per_piano", return_value=0), \
         patch.object(fw, "_chat_crediti_stato", return_value=_STATO) as m_count:
        resp = fw.home_config_get(authorization="Bearer tok")

    # Piano free: chat non disponibile -> niente query, contatore a 0
    assert resp.chat_limite_giorno == 0
    assert resp.chat_crediti_oggi == 0
    assert resp.chat_crediti_ricarica == 0
    m_count.assert_not_called()


def test_config_non_conta_se_chat_spenta():
    sb = _make_sb({"nome_referente": "Marco", "topics_disabled": [], "chat_ai_enabled": False})
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_limite_per_piano", return_value=20), \
         patch.object(fw, "_chat_crediti_stato", return_value=_STATO) as m_count:
        resp = fw.home_config_get(authorization="Bearer tok")

    assert resp.chat_ai_enabled is False
    assert resp.chat_crediti_oggi == 0
    assert resp.chat_crediti_ricarica == 0
    m_count.assert_not_called()


# ─── il budget MENSILE arriva al frontend, e si spegne come il giorno ──────
#
# Scritti dopo un rilievo del code-reviewer: i due campi erano stati aggiunti a
# `ConfigResponse` e popolati nei due endpoint, ma NESSUN test li nominava — si
# poteva cancellare la loro valorizzazione e 15.870 test restavano verdi. E' lo
# stesso difetto del payload RPC, un livello piu' in la': codice nuovo non
# presidiato.


def test_config_include_il_budget_mensile():
    """Senza questi campi il contatore mente per due terzi del mese.

    Col giorno al 10% del budget, chi va a pieno regime esaurisce il mese al
    giorno 10: dall'11 al 30 il widget direbbe «ti restano N domande oggi»
    mentre ogni invio prende 429.
    """
    sb = _make_sb()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_quota_pool", return_value=(30, False)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=1000), \
         patch.object(fw, "_chat_crediti_stato", return_value=_STATO) as m_mese:
        resp = fw.home_config_get(authorization="Bearer tok")

    assert resp.chat_limite_mese == 1000, (
        f"il budget mensile non arriva al frontend: {resp.chat_limite_mese}"
    )
    assert resp.chat_crediti_mese == 180, (
        f"il consumo mensile non arriva al frontend: {resp.chat_crediti_mese}"
    )
    m_mese.assert_called_once()


def test_il_budget_mensile_non_si_conta_a_chat_spenta():
    """Stessa regola del giorno: niente query inutili se la chat non c'e'."""
    sb = _make_sb({"nome_referente": "Marco", "topics_disabled": [], "chat_ai_enabled": False})
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_quota_pool", return_value=(30, False)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=1000), \
         patch.object(fw, "_chat_crediti_stato", return_value=_STATO) as m_mese:
        resp = fw.home_config_get(authorization="Bearer tok")

    assert resp.chat_limite_mese == 0
    assert resp.chat_crediti_mese == 0
    m_mese.assert_not_called()


def test_il_budget_mensile_arriva_anche_dal_salvataggio():
    """I due endpoint (GET e POST) devono dire la stessa cosa.

    Il POST rispondeva con lo stesso `ConfigResponse` ma i campi nuovi erano
    popolati in un punto separato: un mutante che ne svuotava uno solo
    sopravviveva, e il contatore sarebbe tornato a mentire dopo un salvataggio.
    """
    sb = _make_sb({"nome_referente": "Marco", "topics_disabled": [], "chat_ai_enabled": True})
    body = fw.ConfigUpdateRequest(nome_referente="Marco", topics_disabled=[])
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_quota_pool", return_value=(60, False)), \
         patch.object(fw, "_chat_budget_mensile_pool", return_value=1500), \
         patch.object(fw, "_chat_crediti_stato", return_value={"oggi": 6, "mese": 55, "ricarica": 9}):
        resp = fw.home_config_post(body, authorization="Bearer tok")

    assert resp.chat_limite_mese == 1500, (
        "dopo un salvataggio il budget mensile sparisce: il contatore torna a "
        f"mostrare solo il giorno. Valore: {resp.chat_limite_mese}"
    )
    assert resp.chat_crediti_mese == 55
    assert resp.chat_crediti_oggi == 6
    assert resp.chat_crediti_ricarica == 9, "dopo un salvataggio la ricarica sparisce dal contatore"
