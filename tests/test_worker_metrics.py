"""Test per services.worker_metrics (spia latenza worker per l'Admin)."""
from services import worker_metrics as wm


def _reset():
    wm.reset()


def test_registra_e_aggrega_p50_p95():
    _reset()
    for _ in range(95):
        wm.record("/api/auth/me", 200, 200)
    for _ in range(5):
        wm.record("/api/auth/me", 5000, 200)
    snap = wm.snapshot()
    row = next(r for r in snap["routes"] if r["route"] == "/api/auth/me")
    assert row["count"] == 100
    assert row["p50_ms"] == 200
    assert row["p95_ms"] >= 200          # i 5 lenti spingono su il p95
    assert row["slow"] == 5              # sopra soglia SLOW_MS
    assert row["max_ms"] == 5000


def test_conta_errori_5xx():
    _reset()
    wm.record("/api/home/kpi", 300, 200)
    wm.record("/api/home/kpi", 300, 500)
    wm.record("/api/home/kpi", 300, 503)
    snap = wm.snapshot()
    row = next(r for r in snap["routes"] if r["route"] == "/api/home/kpi")
    assert row["errors"] == 2
    assert snap["totale"]["errors"] == 2


def test_ordina_per_p95_discendente():
    _reset()
    wm.record("/lento", 8000, 200)
    wm.record("/veloce", 50, 200)
    snap = wm.snapshot()
    assert snap["routes"][0]["route"] == "/lento"


def test_finestra_scorrevole_non_esplode():
    _reset()
    for i in range(2000):
        wm.record("/api/x", float(i), 200)
    snap = wm.snapshot()
    row = next(r for r in snap["routes"] if r["route"] == "/api/x")
    # count totale conservato anche se la finestra campioni è limitata
    assert row["count"] == 2000


def test_snapshot_vuoto():
    _reset()
    snap = wm.snapshot()
    assert snap["routes"] == []
    assert snap["totale"]["count"] == 0


def test_middleware_registra_le_richieste_ed_esclude_health():
    """Il middleware di latenza registra ogni richiesta (anche in errore) e
    NON conta /health (rumore). Verifica end-to-end via l'app reale."""
    import os
    os.environ.setdefault("WORKER_DEV_MODE", "1")
    os.environ.setdefault("SUPABASE_URL", "http://x")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
    from fastapi.testclient import TestClient
    import services.fastapi_worker as fw

    _reset()
    client = TestClient(fw.app, raise_server_exceptions=False)
    for _ in range(3):
        client.get("/api/auth/me")   # 401 senza token, ma passa dal middleware
        client.get("/health")        # deve restare escluso
    snap = wm.snapshot()
    routes = {r["route"]: r["count"] for r in snap["routes"]}
    assert routes.get("/api/auth/me") == 3
    assert "/health" not in routes
