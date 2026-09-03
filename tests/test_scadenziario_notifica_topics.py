"""Audit router 3/9 (voce §3 #6, scadenziario): le scadenze tornano a parlare.

L'endpoint /api/scadenziario/notifica era MUTO da giugno per due difetti insieme:
l'upsert puntava a un vincolo unico che non esiste (`user_id,ristorante_id,
topic_key` — l'unico vero è su dedupe_key), quindi OGNI chiamata cadeva
nell'except; e il topic che provava a scrivere (`scadenze_aggregate`) era
comunque sconosciuto al briefing. Misurato: 0 notifiche di sempre, con 300
fatture scadute / 4,4 M€ nello scadenziario.

Qui si prova il comportamento nuovo: i DUE topic canonici via factory ufficiale
(dedupe settimanale, refresh_on_conflict), payload {count, totale} che il
briefing sa raccontare, spegnimento quando la condizione rientra, importi
italiani.
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import services.routers.scadenziario as scad


def _doc(scadenza, totale, pagata=False, nc=False):
    return {
        "pagata": pagata,
        "is_nota_credito": nc,
        "scadenza_effettiva": scadenza,
        "totale_documento": totale,
    }


def _chiama(docs, oggi=date(2026, 9, 3)):
    upsert = MagicMock(return_value=len(docs))
    dismiss = MagicMock()
    with patch.multiple(
        scad,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=MagicMock()),
        _resolve_ristorante_id=MagicMock(return_value="sede-1"),
        _oggi_rome=MagicMock(return_value=oggi),
    ), patch(
        "services.documenti_service.get_documenti_scadenziario",
        MagicMock(return_value=docs),
    ), patch(
        "services.notification_inbox_service.upsert_inbox_notifications", upsert,
    ), patch(
        "services.notification_inbox_service.dismiss_inbox_topics", dismiss,
    ):
        out = scad.genera_notifica_scadenze(authorization="Bearer x")
    records = upsert.call_args[0][0] if upsert.call_args else []
    return out, records, dismiss


def test_emette_i_due_topic_canonici_che_il_briefing_conosce():
    docs = [
        _doc("2026-08-01", 4400000.0),          # scaduta
        _doc("2026-09-05", 500.0),              # entro 7 giorni
    ]
    out, records, dismiss = _chiama(docs)

    assert out["ok"] is True and out["scadute"] == 1 and out["in_scadenza"] == 1
    topics = [r["topic_key"] for r in records]
    assert topics == ["scadenza_superata", "scadenza_imminente"], (
        "topic diversi dai canonici: il briefing non saprebbe raccontarli"
    )
    sup = records[0]
    assert sup["severity"] == "error"
    assert sup["payload"] == {"count": 1, "totale": 4400000.0}
    # Factory vera: dedupe settimanale + refresh, il contratto che rende
    # l'upsert idempotente SENZA il vincolo inesistente su topic_key.
    assert "::scadenza_superata::" in sup["dedupe_key"]
    assert sup["refresh_on_conflict"] is True
    dismiss.assert_not_called()


def test_gli_importi_sono_italiani_non_inglesi():
    out, records, _ = _chiama([_doc("2026-08-01", 4400000.0)])
    body = records[0]["body"]
    assert "4.400.000" in body
    assert "4,400,000" not in body


def test_a_condizione_rientrata_spegne_gli_avvisi():
    """Tutte pagate: un avviso acceso a problema risolto mente."""
    out, records, dismiss = _chiama([_doc("2026-08-01", 100.0, pagata=True)])
    assert records == []
    assert dismiss.call_args[0][2] == ["scadenza_superata", "scadenza_imminente"]


def test_solo_scadute_spegne_le_imminenti():
    out, records, dismiss = _chiama([_doc("2026-08-01", 250.0)])
    assert [r["topic_key"] for r in records] == ["scadenza_superata"]
    assert dismiss.call_args[0][2] == ["scadenza_imminente"]


def test_note_di_credito_e_pagate_fuori_dal_conteggio():
    docs = [
        _doc("2026-08-01", 100.0, nc=True),
        _doc("2026-08-01", 100.0, pagata=True),
        _doc("2026-08-01", 100.0),
    ]
    out, records, _ = _chiama(docs)
    assert records[0]["payload"]["count"] == 1
    assert records[0]["payload"]["totale"] == 100.0
