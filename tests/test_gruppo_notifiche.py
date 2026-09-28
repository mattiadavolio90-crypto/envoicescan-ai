"""Gli avvisi della Home di catena (`/api/gruppo/notifiche`, 28/9/2026).

Mattia (26/9, confermato il 28/9): nella Home della catena gli avvisi restano
«come oggi, un pulsante che apre l'elenco», e ogni avviso porta il nome della
sua sede. L'endpoint riusa per ogni sede le regole della campanella del punto
vendita (`_righe_notifiche_sede`, estratta da get_notifiche).

L'isolamento fra clienti si prova su un Postgres vero in
`test_isolamento_per_risorsa.py` (GET_SESSIONE). Qui il comportamento: quali
sedi si leggono, con quale utente, come si etichetta, e che una sede non letta
lo dica invece di sparire.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.routers import gruppo

SEDI = [{"id": "r1", "nome_ristorante": "Centro"}, {"id": "r2", "nome_ristorante": "Porto"}]
RID_TO_NOME = {"r1": "Centro", "r2": "Porto"}


def _riga(id_, topic="tag", created="2026-09-27T10:00:00+00:00", dismissed=None):
    return {
        "id": id_, "topic_key": topic, "source_type": "radar", "severity": "warning",
        "title": f"Avviso {id_}", "body": None, "action_page": "/margini",
        "dismissed_at": dismissed, "expires_at": None, "created_at": created,
    }


def _chiama(per_sede, errori=()):
    chiamate = []

    def finto(user_id, rid, sb, *a, **k):
        chiamate.append((user_id, rid))
        if rid in errori:
            raise RuntimeError("giu'")
        return [dict(r) for r in per_sede.get(rid, [])]

    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=("sb", "u-1", SEDI, "Gruppo", RID_TO_NOME, ["r1", "r2"])), \
         patch.object(gruppo, "_righe_notifiche_sede", side_effect=finto):
        out = gruppo.gruppo_notifiche(authorization="Bearer t")
    return out, chiamate


def test_legge_ogni_sede_del_gruppo_con_l_utente_della_sessione():
    _, chiamate = _chiama({})
    assert chiamate == [("u-1", "r1"), ("u-1", "r2")]


def test_ogni_avviso_porta_la_sua_sede():
    out, _ = _chiama({"r1": [_riga("a")], "r2": [_riga("b")]})
    sedi = {n.id: (n.ristorante_id, n.sede_nome) for n in out.notifiche}
    assert sedi == {"a": ("r1", "Centro"), "b": ("r2", "Porto")}


def test_piu_recenti_prima_fra_sedi_diverse():
    out, _ = _chiama({
        "r1": [_riga("vecchia", created="2026-09-20T08:00:00+00:00")],
        "r2": [_riga("nuova", created="2026-09-27T08:00:00+00:00")],
    })
    assert [n.id for n in out.notifiche] == ["nuova", "vecchia"]


def test_lo_stesso_segnale_live_in_due_sedi_resta_due_voci():
    """«live-personale» ha lo stesso id in ogni sede: sono due avvisi diversi."""
    out, _ = _chiama({"r1": [_riga("live-personale", topic="personale")],
                      "r2": [_riga("live-personale", topic="personale")]})
    assert [(n.id, n.sede_nome) for n in out.notifiche] == [
        ("live-personale", "Centro"), ("live-personale", "Porto")]


def test_conteggi():
    out, _ = _chiama({"r1": [_riga("a"), _riga("b", dismissed="2026-09-26T00:00:00+00:00")],
                      "r2": [_riga("c")]})
    assert (out.total, out.unread) == (3, 2)


def test_una_sede_non_letta_lo_dice():
    """Dato assente ≠ niente da segnalare: l'elenco non deve sembrare completo."""
    out, _ = _chiama({"r1": [_riga("a")]}, errori={"r2"})
    assert [n.id for n in out.notifiche] == ["a"]
    assert out.sedi_non_lette == ["Porto"]


def test_tutte_lette_nessuna_segnalazione_di_errore():
    out, _ = _chiama({"r1": [], "r2": []})
    assert out.sedi_non_lette == []
    assert out.notifiche == []


def test_account_mono_sede_non_ha_gruppo():
    with patch.object(gruppo, "_resolve_gruppo",
                      side_effect=HTTPException(status_code=400, detail="x")):
        with pytest.raises(HTTPException) as e:
            gruppo.gruppo_notifiche(authorization="Bearer t")
    assert e.value.status_code == 400
