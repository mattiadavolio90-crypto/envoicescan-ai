"""Test guardia: lo switch sede invalida la cache di sessione del token.

Difetto osservato (selettore sede): dopo aver selezionato un punto vendita si
doveva ricaricare la pagina piu' volte e aspettare ~30s prima che la nuova sede
diventasse attiva. Causa: verifica_sessione_da_cookie ha una cache in-memory con
TTL 30s keyed sul token; /api/auth/me (e tutti gli endpoint che risolvono la
sede attiva) continuavano a leggere l'user CACHED col vecchio
ultimo_ristorante_id finche' la cache non scadeva.

Fix: account_cambia_sede invalida la cache per il token corrente subito dopo
aver scritto users.ultimo_ristorante_id, cosi' la richiesta successiva rilegge
dal DB la sede appena selezionata.
"""
from unittest.mock import MagicMock, patch

import services.routers.account as account


_USER = {"id": "u-1", "email": "x@y.it"}
_RID = "rist-nuova-sede"
_TOKEN = "sess-token-abc"


def _make_sb(sede_valida=True):
    """Mock supabase: il check ristorante torna una riga (sede valida) e l'update
    su users e' un no-op registrabile.
    """
    sb = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.update.return_value = q
    q.eq.return_value = q
    q.execute.return_value = MagicMock(data=([{"id": _RID}] if sede_valida else []))
    sb.table.return_value = q
    return sb


def test_cambia_sede_invalida_cache_del_token():
    sb = _make_sb(sede_valida=True)
    body = account.CambiaSedeBody(ristorante_id=_RID)

    with patch.object(account, "_resolve_user_from_token", return_value=_USER), \
         patch.object(account, "_get_supabase_client", return_value=sb), \
         patch("services.auth_service._clear_sessione_cache") as m_clear:
        out = account.account_cambia_sede(body, authorization=f"Bearer {_TOKEN}")

    assert out["ok"] is True
    assert out["ristorante_attivo_id"] == _RID
    # La cache di sessione del token corrente DEVE essere invalidata, altrimenti
    # la nuova sede non si vede prima dello scadere del TTL.
    m_clear.assert_called_once_with(_TOKEN)


def test_cambia_sede_sede_non_valida_non_tocca_cache():
    # Sede di un altro account / inesistente: 404, nessun update, nessuna
    # invalidazione (non e' cambiato nulla).
    sb = _make_sb(sede_valida=False)
    body = account.CambiaSedeBody(ristorante_id=_RID)

    with patch.object(account, "_resolve_user_from_token", return_value=_USER), \
         patch.object(account, "_get_supabase_client", return_value=sb), \
         patch("services.auth_service._clear_sessione_cache") as m_clear:
        try:
            account.account_cambia_sede(body, authorization=f"Bearer {_TOKEN}")
            raised = False
        except Exception:
            raised = True

    assert raised, "sede non valida deve sollevare HTTPException 404"
    m_clear.assert_not_called()
