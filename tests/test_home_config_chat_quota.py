"""Test quota chat esposta da /api/home/config (services.fastapi_worker).

Miglioria E: il widget chat mostra "ti restano N domande oggi" gia' all'apertura.
Il valore iniziale arriva da home_config_get come chat_domande_oggi. Per non
fare query inutili, il conteggio viene letto SOLO se la chat e' disponibile
(piano con limite > 0 E chat attiva); altrimenti resta 0.
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


_USER = {"id": "u-1", "piano": "base", "nome_referente": "Marco"}
_RID = "rist-abc"


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


def test_config_include_domande_oggi_se_chat_disponibile():
    sb = _make_sb()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_limite_per_piano", return_value=15), \
         patch.object(fw, "_chat_domande_oggi", return_value=4) as m_count:
        resp = fw.home_config_get(authorization="Bearer tok")

    assert resp.chat_limite_giorno == 15
    assert resp.chat_domande_oggi == 4
    m_count.assert_called_once()


def test_config_non_conta_se_piano_free():
    sb = _make_sb()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_limite_per_piano", return_value=0), \
         patch.object(fw, "_chat_domande_oggi", return_value=4) as m_count:
        resp = fw.home_config_get(authorization="Bearer tok")

    # Piano free: chat non disponibile -> niente query, contatore a 0
    assert resp.chat_limite_giorno == 0
    assert resp.chat_domande_oggi == 0
    m_count.assert_not_called()


def test_config_non_conta_se_chat_spenta():
    sb = _make_sb({"nome_referente": "Marco", "topics_disabled": [], "chat_ai_enabled": False})
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_chat_limite_per_piano", return_value=15), \
         patch.object(fw, "_chat_domande_oggi", return_value=4) as m_count:
        resp = fw.home_config_get(authorization="Bearer tok")

    assert resp.chat_ai_enabled is False
    assert resp.chat_domande_oggi == 0
    m_count.assert_not_called()
