"""Test guardia: le notifiche sono filtrate per SEDE attiva (multi-sede).

Difetto osservato (cliente con LAND DEI SAPORI + 3 SUSHILAND, stesso user_id):
entrando come SUSHILAND SAN GIULIANO — sede a 0 fatture — la campanella mostrava
"Suggeriti 1 nuovo tag", che era una notifica di LAND DEI SAPORI. Causa: gli
endpoint che leggono notification_inbox filtravano solo per user_id, non per
ristorante_id, cosi' un cliente multi-sede vedeva le notifiche di tutte le sedi
su ogni sede.

Verifichiamo che get_notifiche applichi .eq("ristorante_id", <sede attiva>).
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw

_USER = {"id": "u-1"}
_RID = "rist-sushiland"


def _make_sb(rows=None):
    """Mock supabase che REGISTRA le coppie (colonna, valore) passate a .eq().

    Cosi' possiamo asserire che la query filtra per ristorante_id oltre che per
    user_id. Tutte le query restituiscono `rows` (default []).
    """
    sb = MagicMock()
    q = MagicMock()
    q.eq_calls = []

    def _eq(col, val):
        q.eq_calls.append((col, val))
        return q

    q.select.return_value = q
    q.eq.side_effect = _eq
    q.or_.return_value = q
    q.order.return_value = q
    q.limit.return_value = q
    q.execute.return_value = MagicMock(data=rows or [])
    sb.table.return_value = q
    sb._q = q
    return sb


def test_get_notifiche_filtra_per_ristorante():
    sb = _make_sb(rows=[])
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID):
        fw.get_notifiche(authorization="Bearer tok")

    cols = dict(sb._q.eq_calls)
    assert cols.get("user_id") == "u-1"
    assert cols.get("ristorante_id") == _RID, (
        "get_notifiche deve filtrare le notifiche per sede attiva, non solo per utente"
    )


def test_get_notifiche_senza_sede_non_filtra_ristorante():
    # Cliente senza alcuna sede risolvibile: non si applica il filtro sede
    # (altrimenti la query non avrebbe senso). Resta il solo filtro user_id.
    sb = _make_sb(rows=[])
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=None):
        fw.get_notifiche(authorization="Bearer tok")

    cols = [c for (c, _v) in sb._q.eq_calls]
    assert "ristorante_id" not in cols


# ── Fusione live + persistite: la campanella e' la SOMMA (card + minori) ──

def _live(topic, title="x"):
    return {"id": f"live-{topic}", "topic_key": topic, "source_type": "live",
            "severity": "warning", "title": title, "body": "", "action_page": "/x"}


def test_campanella_include_segnali_live():
    # Persistita: una notifica minore (tag). Live: costo personale mancante (card).
    # La campanella deve contenere ENTRAMBE.
    persistite = [{"id": "p1", "topic_key": "tag_suggestion_new_tag", "source_type": "operativa",
                   "severity": "info", "title": "Tag", "body": None, "action_page": None,
                   "dismissed_at": None, "expires_at": None, "created_at": "2026-06-17T10:00:00Z"}]
    sb = _make_sb(rows=persistite)
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_segnali_live_dati_mancanti",
                      return_value=[_live("costo_personale_mancante")]):
        res = fw.get_notifiche(authorization="Bearer tok")

    topics = {n.topic_key for n in res.notifiche}
    assert "tag_suggestion_new_tag" in topics  # minore persistita
    assert "costo_personale_mancante" in topics  # card live


def test_campanella_scarta_persistita_stantia_se_live_assente():
    # Persistita stantia "fatturato_mancante" ma il LIVE non lo segnala piu'
    # (dato ormai inserito): non deve restare in campanella.
    persistite = [{"id": "p1", "topic_key": "fatturato_mancante", "source_type": "operativa",
                   "severity": "warning", "title": "Manca fatturato", "body": None,
                   "action_page": None, "dismissed_at": None, "expires_at": None,
                   "created_at": "2026-06-01T10:00:00Z"}]
    sb = _make_sb(rows=persistite)
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_segnali_live_dati_mancanti", return_value=[]):
        res = fw.get_notifiche(authorization="Bearer tok")

    topics = {n.topic_key for n in res.notifiche}
    assert "fatturato_mancante" not in topics, (
        "una persistita stantia deve sparire se il segnale live non la conferma piu'"
    )
