#!/usr/bin/env python3
"""
scripts/export_openapi.py — Esporta lo schema OpenAPI dal FastAPI worker.

Importa il modulo FastAPI direttamente (in-process) e chiama app.openapi()
per generare lo schema senza avviare un server temporaneo.

Uso:
    python scripts/export_openapi.py              # genera openapi/openapi.json
    python scripts/export_openapi.py --check-drift  # verifica drift (CI)
"""

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

DEFAULT_OUTPUT = _ROOT / "openapi" / "openapi.json"


def _load_app():
    """Importa l'app FastAPI dopo aver impostato le variabili d'ambiente minime."""
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    # Variabili minime per l'import senza crash (valori fake, non servono per lo schema)
    defaults = {
        "SUPABASE_URL": os.environ.get("SUPABASE_URL", "https://placeholder.supabase.co"),
        "SUPABASE_KEY": os.environ.get("SUPABASE_KEY", "placeholder"),
        "SUPABASE_SERVICE_ROLE_KEY": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "placeholder"),
        "WORKER_SECRET_KEY": os.environ.get("WORKER_SECRET_KEY", "placeholder"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "placeholder"),
    }
    for k, v in defaults.items():
        os.environ.setdefault(k, v)

    from services.fastapi_worker import app  # type: ignore
    return app


def export_schema(output: Path = DEFAULT_OUTPUT) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)

    print("[export_openapi] Importazione FastAPI worker in-process...")
    try:
        app = _load_app()
    except Exception as e:
        print(f"[export_openapi] ERRORE import worker: {e}")
        return 1

    print("[export_openapi] Generazione schema OpenAPI...")
    schema = app.openapi()

    with open(output, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")

    n_paths = len(schema.get("paths", {}))
    print(f"[export_openapi] Schema salvato in {output.relative_to(_ROOT)}")
    print(f"[export_openapi] Endpoint trovati: {n_paths}")
    return 0


def check_drift() -> int:
    """Modalità CI: verifica che openapi/openapi.json committato sia aggiornato."""
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
        committed_paths = set(committed.get("paths", {}).keys())
        generated_paths = set(generated.get("paths", {}).keys())
        added = generated_paths - committed_paths
        removed = committed_paths - generated_paths
        if added:
            print(f"[export_openapi] DRIFT: {len(added)} endpoint nuovi non committati:")
            for p in sorted(added):
                print(f"  + {p}")
        if removed:
            print(f"[export_openapi] DRIFT: {len(removed)} endpoint rimossi non committati:")
            for p in sorted(removed):
                print(f"  - {p}")
        if not added and not removed:
            print("[export_openapi] DRIFT: schema modificato (body/parametri cambiati)")
        print("[export_openapi] Esegui: python scripts/export_openapi.py e committa il risultato.")
        return 1

    print(f"[export_openapi] OK: nessun drift ({len(committed.get('paths', {}))} endpoint).")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "export"
    if mode == "--check-drift":
        sys.exit(check_drift())
    else:
        sys.exit(export_schema())
