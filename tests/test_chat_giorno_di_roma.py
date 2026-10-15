"""Gli «oggi» della chat sono il giorno di Roma, non quello del server.

Perche' esiste
==============
Audit di ottobre 2026 (K18): il prompt scriveva «Oggi e'» dal giorno di Roma ma
cercava gli appuntamenti di oggi con `date.today()`, che sul server (UTC) fra
mezzanotte e l'una (le due d'estate) e' ancora ieri; `query_costi` decideva il
«mese non ancora caricato» allo stesso modo. Il giorno di Roma qui e' fissato
lontano dal calendario vero: se il codice torna all'orologio del server, i due
giorni non coincidono mai e il test cade a qualunque ora giri.
"""
from datetime import date
from unittest.mock import MagicMock

import services.fastapi_worker as fw

ROMA = date(2031, 3, 1)


def _sb():
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq", "is_", "gte", "lte", "lt", "in_", "single", "limit", "order", "not_", "or_", "ilike"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[], count=0)
    return sb, q


def test_gli_appuntamenti_di_oggi_sono_del_giorno_di_roma(monkeypatch):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: ROMA)
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: None)
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    sb, q = _sb()
    user = {"id": "u", "nome_ristorante": "T", "email": "t@x.it",
            "pagine_abilitate": {"agenda": True}}
    fw._build_chat_system_prompt(user, sb, None, "r-1", "ristorazione")
    giorni = [c.args[1] for c in q.eq.call_args_list if c.args and c.args[0] == "data_evento"]
    assert giorni == ["2031-03-01"]


def test_il_mese_prima_di_quello_di_roma_non_e_il_mese_in_corso(monkeypatch):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: ROMA)
    sb, _ = _sb()
    out = fw._chat_query_costi(user_id="u", supabase_client=sb, mese=2, anno=2031, ristorante_id="r-1")
    assert "mese_non_ancora_caricato" not in out
    out = fw._chat_query_costi(user_id="u", supabase_client=sb, mese=3, anno=2031, ristorante_id="r-1")
    assert out["mese_non_ancora_caricato"] is True
