"""Audit worker/ 3/9 (voce §3 #5): il retry della coda email deve poter scrivere.

`_schedule_retry` passava a PostgREST la STRINGA "now() + interval '...'" come
valore di `next_retry_at`: Postgres la rifiuta come letterale timestamptz
("invalid input syntax", misurato a DB il 3/9), quindi l'UPDATE intero falliva —
niente status='failed', niente backoff, lock non rilasciato: il record sarebbe
tornato in coda solo col recupero dei lock stantii. Mai esercitato in produzione
(88 righe, tutte done al primo tentativo): latente, non vivo.

Ora il timestamp è calcolato in Python e deve essere un ISO 8601 vero, parsabile
e nel futuro della giusta quantità.
"""
from datetime import datetime, timedelta, timezone

import pytest

from worker.email_queue_processor import _BACKOFF_BASE_SEC, _schedule_retry


class _Q:
    def __init__(self, sb):
        self._sb = sb

    def update(self, payload):
        self._sb.updates.append(payload)
        return self

    def eq(self, *_a):
        return self

    def execute(self):
        return None


class _SB:
    def __init__(self):
        self.updates = []

    def table(self, name):
        assert name == "ricavi_email_queue"
        return _Q(self)


def test_next_retry_at_e_un_timestamp_vero_nel_futuro():
    sb = _SB()
    prima = datetime.now(timezone.utc)
    _schedule_retry(sb, "rec-1", "boom", attempts=1, max_attempts=5)

    assert len(sb.updates) == 1
    payload = sb.updates[0]
    assert payload["status"] == "failed"

    raw = payload["next_retry_at"]
    # Il letterale-espressione era esattamente questo modo di rompersi.
    assert "now()" not in raw and "interval" not in raw

    quando = datetime.fromisoformat(raw)  # esplode se non è ISO vero
    assert quando.tzinfo is not None, "timestamp senza fuso: ambiguo a DB"
    delta = (quando - prima).total_seconds()
    # attempts=1 -> base 60s con jitter ±25%, mai sotto i 30s.
    assert 30 <= delta <= _BACKOFF_BASE_SEC * 1.25 + 5


def test_oltre_i_tentativi_va_dead_senza_retry():
    sb = _SB()
    _schedule_retry(sb, "rec-1", "boom", attempts=5, max_attempts=5)
    assert len(sb.updates) == 1
    assert sb.updates[0]["status"] == "dead"
    assert "next_retry_at" not in sb.updates[0]


def test_il_backoff_cresce_con_i_tentativi():
    sb = _SB()
    prima = datetime.now(timezone.utc)
    _schedule_retry(sb, "rec-1", "boom", attempts=4, max_attempts=9)
    quando = datetime.fromisoformat(sb.updates[0]["next_retry_at"])
    delta = (quando - prima).total_seconds()
    # attempts=4 -> 60 * 2^3 = 480s, jitter ±25%.
    assert 480 * 0.75 - 5 <= delta <= 480 * 1.25 + 5
