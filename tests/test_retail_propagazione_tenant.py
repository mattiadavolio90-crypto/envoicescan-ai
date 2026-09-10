"""La propagazione storica di una correzione globale non tocca i clienti retail (RETAIL_FASI.md 1.6).

`_propaga_global_override_a_fatture_storiche` riscrive le fatture storiche di
TUTTI i clienti senza personalizzazione locale: e' il comportamento documentato
nel suo docstring e asserito da `tests/test_propagazione_globale_guardrail_note.py`
(due utenti, entrambi raggiunti). La memoria globale pero' e' dei ristoranti:
una correzione admin su "SCAFFALE METALLICO" non deve riscrivere le righe di un
negozio, che quella descrizione la classifica a modo suo. Il filtro e' per
SETTORE del tenant, dentro la funzione (tre chiamanti), cosi' vale per tutti.
"""
from __future__ import annotations

from unittest.mock import patch

import services.ai_service as ai
import services.settore_service as ss
from tests.test_propagazione_globale_guardrail_note import FakeSB

DESC = "SCAFFALE METALLICO 4 RIPIANI"


def _righe():
    return [
        {"id": "f-rist", "user_id": "u-rist", "descrizione": DESC, "categoria": "Da Classificare",
         "totale_riga": 90.0, "prezzo_unitario": 90.0},
        {"id": "f-retail", "user_id": "u-retail", "descrizione": DESC, "categoria": "Da Classificare",
         "totale_riga": 90.0, "prezzo_unitario": 90.0},
    ]


def _propaga(sb, settori):
    desc_norm, _ = ai.get_descrizione_normalizzata_e_originale(DESC)
    with patch.object(ss, "settore_utente", side_effect=lambda uid, supabase_client=None: settori[uid]):
        return ai._propaga_global_override_a_fatture_storiche(desc_norm, "MANUTENZIONE E ATTREZZATURE", sb)


def test_le_fatture_di_un_cliente_retail_non_vengono_riscritte():
    sb = FakeSB(_righe())
    aggiornate = _propaga(sb, {"u-rist": "ristorazione", "u-retail": "retail"})
    assert aggiornate == 1
    assert sb._rows[0]["categoria"] == "MANUTENZIONE E ATTREZZATURE"
    assert sb._rows[1]["categoria"] == "Da Classificare"


def test_fra_ristoranti_la_propagazione_raggiunge_tutti_come_prima():
    sb = FakeSB(_righe())
    aggiornate = _propaga(sb, {"u-rist": "ristorazione", "u-retail": "ristorazione"})
    assert aggiornate == 2
    assert [r["categoria"] for r in sb._rows] == ["MANUTENZIONE E ATTREZZATURE"] * 2


def test_solo_clienti_retail_nessun_update():
    sb = FakeSB(_righe())
    aggiornate = _propaga(sb, {"u-rist": "retail", "u-retail": "retail"})
    assert aggiornate == 0
    assert sb.updates == []
