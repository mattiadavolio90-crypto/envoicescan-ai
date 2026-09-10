"""L'agente notturno non lavora sugli account retail (RETAIL_FASI.md 1.5, trovato dal reviewer).

`_run_agent_notturno` legge le righe in coda di TUTTI gli utenti non-admin, le
decide col dizionario e le regole dei ristoranti, le scrive su `fatture` e
promuove la descrizione in `prodotti_master` (memoria globale, verified=True).
Per un negozio non deve girare: le sue righe restano in coda per l'AI col prompt
del settore. Il presidio e' sul filtro degli utenti PRIMA della query sulle
fatture: cio' che non viene letto non puo' essere scritto.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import services.fastapi_worker as fw
import services.settore_service as ss

UTENTI = [{"id": "u-rist", "email": "rist@x.it"}, {"id": "u-retail", "email": "shop@x.it"}]


class _Query:
    def __init__(self, fake, tabella):
        self._fake, self._tabella = fake, tabella

    def select(self, *_a, **_k):
        return self

    def is_(self, *_a):
        return self

    def in_(self, colonna, valori):
        if self._tabella == "fatture" and colonna == "user_id":
            self._fake.utenti_interrogati.append(list(valori))
        return self

    def range(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def upsert(self, *_a, **_k):
        return self

    def update(self, *_a, **_k):
        return self

    def execute(self):
        if self._tabella == "users":
            return SimpleNamespace(data=list(UTENTI))
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self):
        self.utenti_interrogati: list = []

    def table(self, nome):
        return _Query(self, nome)


def _esegui(settori):
    fake = _FakeSB()
    with patch.object(fw, "get_supabase_client", return_value=fake), \
         patch.object(fw, "_admin_emails_set", return_value=set()), \
         patch.object(ss, "settore_utente", side_effect=lambda uid, supabase_client=None: settori[uid]):
        esito = fw._run_agent_notturno()
    return fake, esito


def test_le_righe_di_un_negozio_non_vengono_nemmeno_lette():
    fake, _ = _esegui({"u-rist": "ristorazione", "u-retail": "retail"})
    assert fake.utenti_interrogati == [["u-rist"]]


def test_con_soli_negozi_l_agente_non_fa_nulla():
    fake, esito = _esegui({"u-rist": "retail", "u-retail": "retail"})
    assert fake.utenti_interrogati == []
    assert esito["classificate"] == 0


def test_per_i_ristoranti_legge_tutti_come_prima():
    fake, _ = _esegui({"u-rist": "ristorazione", "u-retail": "ristorazione"})
    assert fake.utenti_interrogati == [["u-rist", "u-retail"]]
