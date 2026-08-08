"""Test worker/run.py — entry point del worker fatture_queue (audit §2, 8/8/2026).

worker.run esegue codice a livello di modulo (killswitch WORKER_ENABLED) e ha
un ciclo `while True` in main(): i test escono dal loop facendo sollevare
un'eccezione sentinella a time.sleep dopo N iterazioni, senza toccare il
codice di produzione.
"""
import logging
import sys
import time as time_module
from unittest.mock import MagicMock, patch

import pytest


class _StopLoop(BaseException):
    """Sentinella per uscire dal while True nei test.

    Eredita da BaseException (non Exception): main() intercetta
    `except Exception` per il retry/backoff, e una sentinella Exception
    verrebbe assorbita silenziosamente facendo continuare il loop invece
    di propagarsi fino al test.
    """


def _reload_worker_run():
    sys.modules.pop("worker.run", None)
    import worker.run as worker_run
    return worker_run


@pytest.fixture
def worker_run_module(monkeypatch):
    monkeypatch.delenv("WORKER_ENABLED", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    mod = _reload_worker_run()
    yield mod
    sys.modules.pop("worker.run", None)


class _FakeCycleStats:
    def __init__(self, batch_claimed=0):
        self.batch_claimed = batch_claimed
        self.done = 0
        self.retry_scheduled = 0
        self.dead = 0
        self.skipped = 0

    def log_summary(self):
        pass


class _FakeEmailStats:
    def log_summary(self):
        pass


# ─── _check_env ────────────────────────────────────────────────────────────

def test_check_env_ok(worker_run_module, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    assert worker_run_module._check_env() is True


def test_check_env_manca_url(worker_run_module, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    assert worker_run_module._check_env() is False


def test_check_env_manca_service_role_key(worker_run_module, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert worker_run_module._check_env() is False


def test_check_env_mancano_entrambe(worker_run_module, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert worker_run_module._check_env() is False


# ─── _ensure_streamlit_available ───────────────────────────────────────────

def test_ensure_streamlit_available_gia_importabile(worker_run_module):
    with patch.dict(sys.modules, {"streamlit": MagicMock()}):
        assert worker_run_module._ensure_streamlit_available() is True


def test_ensure_streamlit_available_fallback_stub(worker_run_module, monkeypatch):
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "streamlit":
            raise ImportError("no streamlit")
        return real_import(name, *args, **kwargs)

    stub_installed = MagicMock()
    with patch("builtins.__import__", side_effect=_fake_import):
        with patch("worker.streamlit_stub.install_streamlit_stub", stub_installed):
            assert worker_run_module._ensure_streamlit_available() is True
    stub_installed.assert_called_once()


def test_ensure_streamlit_available_doppio_fallimento(worker_run_module):
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name in ("streamlit", "worker.streamlit_stub"):
            raise ImportError(f"no {name}")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        assert worker_run_module._ensure_streamlit_available() is False


# ─── Killswitch WORKER_ENABLED=0 ───────────────────────────────────────────

def test_killswitch_pausa_non_chiama_nulla_prima_dello_sleep(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "0")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    sys.modules.pop("worker.run", None)
    with patch.object(time_module, "sleep", side_effect=_fake_sleep):
        with pytest.raises(_StopLoop):
            import worker.run  # noqa: F401
    sys.modules.pop("worker.run", None)

    assert sleep_calls == [3600]


@pytest.mark.parametrize("value", ["0", "false", "False", "no"])
def test_killswitch_attivo_per_ogni_valore_falsy(monkeypatch, value):
    monkeypatch.setenv("WORKER_ENABLED", value)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    sys.modules.pop("worker.run", None)
    with patch.object(time_module, "sleep", side_effect=_StopLoop()):
        with pytest.raises(_StopLoop):
            import worker.run  # noqa: F401
    sys.modules.pop("worker.run", None)


def test_killswitch_non_attivo_con_1(monkeypatch):
    # A differenza degli altri test killswitch, qui NON mockiamo time.sleep:
    # se il killswitch scattasse per errore, l'import si bloccherebbe nel
    # vero time.sleep(3600) e il test andrebbe in timeout invece che passare.
    monkeypatch.delenv("WORKER_ENABLED", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    mod = _reload_worker_run()
    try:
        assert hasattr(mod, "main")
    finally:
        sys.modules.pop("worker.run", None)


# ─── main() — ciclo felice e sleep adattivo ────────────────────────────────

def _patch_main_deps(worker_run_module, run_cycle_mock, email_cycle_mock=None,
                      purge_cestino=None, purge_retention=None):
    qp_mock = MagicMock()
    qp_mock.run_cycle = run_cycle_mock
    qp_mock._purge_xml = MagicMock()
    qp_mock._purge_raw_body_sample = MagicMock()
    qp_mock.XML_RETENTION_H = 24
    qp_mock.RAW_BODY_SAMPLE_RETENTION_D = 90
    fake_sb = MagicMock()
    fake_sb.rpc.return_value.execute.return_value = MagicMock(data=0)
    qp_mock.get_supabase_client = MagicMock(return_value=fake_sb)

    db_service_mock = MagicMock()
    db_service_mock.purge_cestino_scaduto = purge_cestino or MagicMock(return_value={"righe_eliminate": 0})
    db_service_mock.purge_fatture_retention = purge_retention or MagicMock(return_value={"righe_eliminate": 0})

    email_qp_mock = MagicMock()
    email_qp_mock.run_email_cycle = email_cycle_mock or MagicMock(return_value=_FakeEmailStats())
    email_qp_mock.purge_ricavi_xls_storage = MagicMock()

    modules_patch = {
        "worker.queue_processor": qp_mock,
        "services.db_service": db_service_mock,
        "worker.email_queue_processor": email_qp_mock,
    }
    return modules_patch, qp_mock, db_service_mock, email_qp_mock


def test_main_sleep_poll_interval_quando_coda_vuota(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "15")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert sleep_calls == [15]


def test_main_sleep_1s_quando_batch_claimed(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "15")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=3))
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert sleep_calls == [1]


# ─── main() — backoff esponenziale con jitter ──────────────────────────────

def test_main_backoff_esponenziale_cresce_e_si_cappa(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_ERROR_BACKOFF_SECONDS", "30")
    monkeypatch.setenv("WORKER_MAX_BACKOFF_SECONDS", "300")
    run_cycle_mock = MagicMock(side_effect=RuntimeError("boom"))
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 4:
            raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch("random.uniform", return_value=1.0):
            with patch.object(time_module, "sleep", side_effect=_fake_sleep):
                with pytest.raises(_StopLoop):
                    worker_run_module.main()

    # failure 1: 30*2^0=30, failure 2: 30*2^1=60, failure 3: 30*2^2=120,
    # failure 4: 30*2^3=240 (sotto il cap 300)
    assert sleep_calls == [30.0, 60.0, 120.0, 240.0]


def test_main_backoff_si_cappa_al_massimo(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_ERROR_BACKOFF_SECONDS", "30")
    monkeypatch.setenv("WORKER_MAX_BACKOFF_SECONDS", "300")
    run_cycle_mock = MagicMock(side_effect=RuntimeError("boom"))
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 10:
            raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch("random.uniform", return_value=1.0):
            with patch.object(time_module, "sleep", side_effect=_fake_sleep):
                with pytest.raises(_StopLoop):
                    worker_run_module.main()

    assert sleep_calls[-1] == 300.0
    assert max(sleep_calls) == 300.0


def test_main_backoff_jitter_applicato(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_ERROR_BACKOFF_SECONDS", "30")
    monkeypatch.setenv("WORKER_MAX_BACKOFF_SECONDS", "300")
    run_cycle_mock = MagicMock(side_effect=RuntimeError("boom"))
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch("random.uniform", return_value=0.5):
            with patch.object(time_module, "sleep", side_effect=_fake_sleep):
                with pytest.raises(_StopLoop):
                    worker_run_module.main()

    # failure 1: base 30 * jitter 0.5 = 15.0
    assert sleep_calls == [15.0]


def test_main_backoff_reset_dopo_successo(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_ERROR_BACKOFF_SECONDS", "30")
    monkeypatch.setenv("WORKER_MAX_BACKOFF_SECONDS", "300")
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "15")

    call_sequence = [RuntimeError("boom"), _FakeCycleStats(batch_claimed=0)]

    def _run_cycle_side_effect():
        result = call_sequence.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    run_cycle_mock = MagicMock(side_effect=_run_cycle_side_effect)
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch("random.uniform", return_value=1.0):
            with patch.object(time_module, "sleep", side_effect=_fake_sleep):
                with pytest.raises(_StopLoop):
                    worker_run_module.main()

    # primo sleep = backoff (30), secondo sleep = poll interval normale (15),
    # NON un backoff raddoppiato: consecutive_failures va azzerato dopo successo.
    assert sleep_calls == [30.0, 15]


# ─── main() — KeyboardInterrupt ────────────────────────────────────────────

def test_main_keyboard_interrupt_ritorna_0(worker_run_module):
    run_cycle_mock = MagicMock(side_effect=KeyboardInterrupt())
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        result = worker_run_module.main()

    assert result == 0


# ─── main() — env vars mancanti / import falliti ───────────────────────────

def test_main_ritorna_1_se_env_mancanti(worker_run_module, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert worker_run_module.main() == 1


def test_main_ritorna_1_se_import_queue_processor_fallisce(worker_run_module):
    with patch.dict(sys.modules, {"worker.queue_processor": None}):
        assert worker_run_module.main() == 1


def test_main_continua_se_import_email_queue_processor_fallisce(worker_run_module, monkeypatch):
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    modules_patch, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)
    modules_patch["worker.email_queue_processor"] = None

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    # il ciclo fatture prosegue comunque, il ciclo email semplicemente manca
    assert sleep_calls == [15]


# ─── main() — email-cycle disabilitato ─────────────────────────────────────

def test_main_email_cycle_disabilitato_non_chiama_run_email_cycle(worker_run_module, monkeypatch):
    monkeypatch.setenv("EMAIL_CYCLE_ENABLED", "0")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    email_cycle_mock = MagicMock(return_value=_FakeEmailStats())
    modules_patch, _qp, _db, email_qp_mock = _patch_main_deps(
        worker_run_module, run_cycle_mock, email_cycle_mock=email_cycle_mock,
    )

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    email_cycle_mock.assert_not_called()


# ─── main() — i tre gate temporali (purge cestino / coda / retention) ─────

def test_main_purge_cestino_scatta_al_primo_giro(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_PURGE_INTERVAL_SECONDS", str(6 * 3600))
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_cestino_mock = MagicMock(return_value={"righe_eliminate": 0})
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_cestino=purge_cestino_mock,
    )

    def _fake_sleep(seconds):
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    # last_purge_time e' inizializzato a boot - INTERVAL: il primo giro deve
    # far scattare subito il purge, non aspettare l'intervallo pieno
    # (bug reale gia' avvenuto: audit DevOps/Config 30/7/2026).
    purge_cestino_mock.assert_called_once()


def test_main_purge_cestino_non_riscatta_prima_dellintervallo(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_PURGE_INTERVAL_SECONDS", str(6 * 3600))
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "15")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_cestino_mock = MagicMock(return_value={"righe_eliminate": 0})
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_cestino=purge_cestino_mock,
    )

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    # secondo giro, pochi secondi dopo: l'intervallo di 6h non e' passato,
    # il purge non deve essere richiamato una seconda volta.
    assert purge_cestino_mock.call_count == 1


def test_main_retention_fatture_scatta_al_primo_giro(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_RETENTION_INTERVAL_SECONDS", str(24 * 3600))
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_retention_mock = MagicMock(return_value={"righe_eliminate": 0, "righe_da_cestino": 0})
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_retention=purge_retention_mock,
    )

    def _fake_sleep(seconds):
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    purge_retention_mock.assert_called_once_with(batch_size=500)


def test_main_purge_queue_scatta_al_primo_giro(worker_run_module, monkeypatch):
    monkeypatch.setenv("WORKER_QUEUE_PURGE_INTERVAL_SECONDS", str(6 * 3600))
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    modules_patch, qp_mock, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)

    def _fake_sleep(seconds):
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    qp_mock._purge_xml.assert_called_once()
    qp_mock._purge_raw_body_sample.assert_called_once()


# ─── main() — rami "successo con righe eliminate" e rami except interni ───

def test_main_purge_cestino_logga_righe_eliminate(worker_run_module, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="worker.run")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_cestino_mock = MagicMock(return_value={"righe_eliminate": 5})
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_cestino=purge_cestino_mock,
    )

    def _fake_sleep(seconds):
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert any("5 righe scadute eliminate" in r.getMessage() for r in caplog.records)


def test_main_purge_cestino_errore_non_fatale(worker_run_module):
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_cestino_mock = MagicMock(side_effect=RuntimeError("db down"))
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_cestino=purge_cestino_mock,
    )

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    # l'errore nel purge non fa fallire il ciclo: consecutive_failures resta 0,
    # lo sleep e' quello normale del ciclo felice (15s), non un backoff.
    assert sleep_calls == [15]


def test_main_purge_queue_errore_non_fatale(worker_run_module):
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    modules_patch, qp_mock, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)
    qp_mock._purge_xml.side_effect = RuntimeError("boom")

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert sleep_calls == [15]


def test_main_retention_fatture_logga_righe_eliminate(worker_run_module, caplog):
    caplog.set_level(logging.INFO, logger="worker.run")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_retention_mock = MagicMock(return_value={"righe_eliminate": 7, "righe_da_cestino": 2})
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_retention=purge_retention_mock,
    )

    def _fake_sleep(seconds):
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert any("7 righe eliminate" in r.getMessage() for r in caplog.records)


def test_main_retention_fatture_errore_non_fatale(worker_run_module):
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    purge_retention_mock = MagicMock(side_effect=RuntimeError("db down"))
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, purge_retention=purge_retention_mock,
    )

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert sleep_calls == [15]


def test_main_retention_upload_events_logga_righe_eliminate(worker_run_module, caplog):
    caplog.set_level(logging.INFO, logger="worker.run")
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    modules_patch, qp_mock, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)
    qp_mock.get_supabase_client.return_value.rpc.return_value.execute.return_value = MagicMock(data=3)

    def _fake_sleep(seconds):
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert any("Retention upload_events: 3 righe eliminate" in r.getMessage() for r in caplog.records)


def test_main_retention_upload_events_errore_non_fatale(worker_run_module):
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    modules_patch, qp_mock, *_ = _patch_main_deps(worker_run_module, run_cycle_mock)
    qp_mock.get_supabase_client.return_value.rpc.side_effect = RuntimeError("db down")

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert sleep_calls == [15]


def test_main_email_cycle_errore_non_fatale(worker_run_module):
    run_cycle_mock = MagicMock(return_value=_FakeCycleStats(batch_claimed=0))
    email_cycle_mock = MagicMock(side_effect=RuntimeError("smtp down"))
    modules_patch, *_ = _patch_main_deps(
        worker_run_module, run_cycle_mock, email_cycle_mock=email_cycle_mock,
    )

    sleep_calls = []

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    worker_run_module = _reload_worker_run()
    with patch.dict(sys.modules, modules_patch):
        with patch.object(time_module, "sleep", side_effect=_fake_sleep):
            with pytest.raises(_StopLoop):
                worker_run_module.main()

    assert sleep_calls == [15]
