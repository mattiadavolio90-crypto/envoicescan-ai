"""Il lock della coda e' del lotto, il lavoro e' dell'item (lente L6, 15/09/2026).

`claim_batch_for_processing` scrive `locked_at` una volta per fino a 10 item; `run_cycle`
li elabora in serie, ognuno fino a `JOB_TIMEOUT` (300 s). Dopo due timeout il terzo item
parte con un lock piu' vecchio di `STALE_LOCK_MIN` (10 min): un secondo processo lo
rilascia e se lo prende, mentre il primo lo elabora e poi lo marca done sotto i suoi
piedi (`mark_queue_item_done` non chiede chi chiama). Il ciclo rinnova il lock all'inizio
di ogni item, e salta l'item se il lock non e' piu' suo. Trovato dalla verifica
avversaria della lente, non dalla lettura.
"""
from __future__ import annotations

import pytest

from worker import queue_processor as qp


class _Risposta:
    def __init__(self, data):
        self.data = data


class _Catena:
    def __init__(self, data, esplode=False):
        self._data = data
        self._esplode = esplode
        self.filtri = []

    def table(self, nome):
        self.tabella = nome
        return self

    def update(self, valori):
        self.valori = valori
        return self

    def eq(self, colonna, valore):
        self.filtri.append((colonna, valore))
        return self

    def execute(self):
        if self._esplode:
            raise ConnectionError("rete assente")
        return _Risposta(self._data)


def test_rinnova_lock_dice_false_se_il_lock_non_e_piu_nostro():
    assert qp._rinnova_lock(_Catena([]), 7, "worker-a") is False


def test_rinnova_lock_scrive_solo_sull_item_ancora_nostro_e_in_lavorazione():
    catena = _Catena([{"id": 7}])

    assert qp._rinnova_lock(catena, 7, "worker-a") is True
    assert catena.tabella == "fatture_queue"
    assert set(catena.valori) == {"locked_at"}
    assert catena.filtri == [("id", 7), ("locked_by", "worker-a"), ("status", "processing")]


def test_rinnova_lock_su_errore_di_rete_procede_come_claim_ancora_valido():
    assert qp._rinnova_lock(_Catena([], esplode=True), 7, "worker-a") is True


@pytest.fixture
def ciclo(monkeypatch):
    """run_cycle con le sole dipendenze esterne finte; registra l'ordine delle chiamate."""
    eventi = []
    lotto = [{"id": 1, "event_id": "e1"}, {"id": 2, "event_id": "e2"}, {"id": 3, "event_id": "e3"}]
    monkeypatch.setattr(qp, "get_supabase_client", lambda: object())
    monkeypatch.setattr(qp, "_release_stale_locks", lambda *a, **k: 0)
    monkeypatch.setattr(qp, "_claim_batch", lambda *a, **k: list(lotto))
    monkeypatch.setattr(qp, "_mark_done", lambda sb, qid, purge_xml=True: eventi.append(("done", qid)))
    monkeypatch.setattr(qp, "_schedule_retry", lambda sb, qid, msg: eventi.append(("retry", qid)))

    def _elabora(sb, item, worker_id=None):
        eventi.append(("elabora", item["id"]))
        return qp.ItemResult(queue_id=item["id"], event_id=item["event_id"], status="done", righe=1)

    monkeypatch.setattr(qp, "_process_item", _elabora)
    return eventi


def test_il_ciclo_rinnova_il_lock_di_ogni_item_prima_di_iniziarlo(ciclo, monkeypatch):
    monkeypatch.setattr(qp, "_rinnova_lock", lambda sb, qid, w: ciclo.append(("rinnova", qid)) or True)

    stats = qp.run_cycle()

    assert stats.done == 3 and stats.skipped == 0
    assert ciclo == [
        ("rinnova", 1), ("elabora", 1), ("done", 1),
        ("rinnova", 2), ("elabora", 2), ("done", 2),
        ("rinnova", 3), ("elabora", 3), ("done", 3),
    ]


def test_il_ciclo_salta_l_item_il_cui_lock_e_di_un_altro(ciclo, monkeypatch):
    monkeypatch.setattr(qp, "_rinnova_lock", lambda sb, qid, w: qid != 2)

    stats = qp.run_cycle()

    assert stats.done == 2 and stats.skipped == 1
    assert ("elabora", 2) not in ciclo, "elaborato un item che un altro worker detiene"
    assert ("done", 2) not in ciclo and ("retry", 2) not in ciclo, "chiuso l'item di un altro"


def test_il_timeout_del_job_sta_sotto_la_soglia_del_lock_stantio():
    """Il rinnovo all'inizio dell'item basta solo se l'item finisce prima che il lock
    invecchi: se qualcuno alza JOB_TIMEOUT sopra STALE_LOCK_MIN, torna la finestra."""
    assert qp.JOB_TIMEOUT < qp.STALE_LOCK_MIN * 60
