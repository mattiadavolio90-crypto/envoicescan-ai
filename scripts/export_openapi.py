#!/usr/bin/env python3
"""
scripts/export_openapi.py — Esporta lo schema OpenAPI dal FastAPI worker.

Avvia temporaneamente l'app FastAPI, recupera /openapi.json via HTTP e salva
il file in openapi/openapi.json.

Uso:
    python scripts/export_openapi.py              # genera openapi/openapi.json
    python scripts/export_openapi.py --check-drift  # verifica drift in CI

Il file generato viene usato da openapi-typescript per generare i tipi TypeScript
condivisi tra Next.js e il backend (packages/shared/types.ts nel monorepo).

In CI: --check-drift fallisce con exit code 1 se lo schema committato non è aggiornato.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

DEFAULT_OUTPUT = _ROOT / "openapi" / "openapi.json"
WORKER_MODULE = "services.fastapi_worker:app"
WORKER_HOST = "127.0.0.1"
WORKER_PORT = 19873
STARTUP_TIMEOUT = 15


def _wait_for_server(url: str, timeout: int) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _fetch_schema(url: str) -> dict:
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def export_schema(output: Path = DEFAULT_OUTPUT) -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    output.parent.mkdir(parents=True, exist_ok=True)
    worker_url = f"http://{WORKER_HOST}:{WORKER_PORT}/openapi.json"

    print(f"[export_openapi] Avvio FastAPI worker su porta {WORKER_PORT}...")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT)

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            WORKER_MODULE,
            "--host", WORKER_HOST,
            "--port", str(WORKER_PORT),
            "--no-access-log",
        ],
        cwd=str(_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    try:
        print(f"[export_openapi] Attendo startup (max {STARTUP_TIMEOUT}s)...")
        if not _wait_for_server(worker_url, STARTUP_TIMEOUT):
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            print(f"[export_openapi] ERRORE: server non risponde dopo {STARTUP_TIMEOUT}s")
            if stderr:
                print(f"[export_openapi] stderr worker:\n{stderr[:2000]}")
            return 1

        print("[export_openapi] Server pronto. Recupero schema...")
        schema = _fetch_schema(worker_url)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"[export_openapi] Schema salvato in {output.relative_to(_ROOT)}")
        print(f"[export_openapi] Endpoint trovati: {len(schema.get('paths', {}))}")
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_drift() -> int:
    """
    Modalita CI: verifica che openapi.json committato sia aggiornato.
    Esce con codice 1 se c'e drift.
    """
    if not DEFAULT_OUTPUT.exists():
        print("[export_openapi] DRIFT: openapi/openapi.json non trovato nel repo.")
        print("[export_openapi] Esegui: python scripts/export_openapi.py")
        return 1

    committed = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    tmp = _ROOT / "openapi" / ".tmp_drift_check.json"
    try:
        rc = export_schema(output=tmp)
        if rc != 0:
            return rc
        generated = json.loads(tmp.read_text(encoding="utf-8"))
    finally:
        tmp.unlink(missing_ok=True)

    if committed != generated:
        print("[export_openapi] DRIFT: openapi/openapi.json non e aggiornato.")
        print("[export_openapi] Esegui: python scripts/export_openapi.py e committa il risultato.")
        return 1

    print("[export_openapi] OK: nessun drift rilevato.")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "export"
    if mode == "--check-drift":
        sys.exit(check_drift())
    else:
        sys.exit(export_schema())
