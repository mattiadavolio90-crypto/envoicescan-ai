"""
Hook Stop: test automatici a fine sessione, tarati sul costo reale.

Il problema che risolve (rivisto il 30/8/2026): la versione precedente lanciava
l'INTERA suite (11.424 test, minuti) a ogni Stop, anche quando il diff era un
solo .md. Con il modo di lavorare ad accumulo — tante sessioni brevi su un unico
branch, un solo merge a fine ciclo — quel costo si pagava decine di volte al
giorno per un'informazione che serve una volta sola: prima di spedire.

Regime attuale, tre livelli:

1. Diff di soli .md / documenti  -> NESSUN test. Non c'e' codice da rompere.
2. Lavoro in corso               -> solo i test COLLEGATI ai file toccati
                                    (secondi invece di minuti).
3. Prima di spedire              -> suite COMPLETA. Attivata da
                                    PRE_MERGE (marker .claude/.pre_merge) oppure
                                    quando si e' su main.

Il livello 2 e' una rete, non una garanzia: e' il livello 3 che certifica.
Per questo la suite completa NON e' opzionale prima del merge — vedi
WORKFLOW.md, sezione sul ciclo ad accumulo.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_PRE_MERGE = REPO_ROOT / ".claude" / ".pre_merge"

# Estensioni che non possono rompere la suite Python da sole.
ESTENSIONI_INERTI = {".md", ".txt", ".rst", ".json", ".yml", ".yaml", ".toml", ".lock"}
# Frontend: ha la sua rete (tsc), non la suite pytest.
PREFISSI_NON_PYTEST = ("apps/web/", "supabase/functions/")


def _run_git(*args: str) -> str:
    try:
        esito = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=15
        )
        return esito.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def _branch_corrente() -> str:
    return _run_git("rev-parse", "--abbrev-ref", "HEAD").strip()


def _file_toccati() -> list[str]:
    """File modificati rispetto a HEAD (working tree + staged)."""
    grezzo = _run_git("diff", "--name-only", "HEAD")
    return [riga.strip() for riga in grezzo.splitlines() if riga.strip()]


def _solo_documenti(percorsi: list[str]) -> bool:
    return all(Path(p).suffix.lower() in ESTENSIONI_INERTI for p in percorsi)


def _test_collegati(percorsi: list[str]) -> list[str]:
    """Mappa i file toccati sui file di test che li riguardano.

    Due strade, unite:
      - il file toccato E' un test  -> se stesso
      - il file toccato e' un modulo -> tests/test_<nome>*.py, piu' i test che
        ne citano il nome (grep sul nome del modulo, non sul path: i test
        importano `services.x`, non `services/x.py`)
    """
    cartella_test = REPO_ROOT / "tests"
    if not cartella_test.is_dir():
        return []

    selezionati: set[str] = set()
    moduli: list[str] = []

    for percorso in percorsi:
        p = Path(percorso)
        if p.suffix != ".py":
            continue
        if percorso.startswith("tests/"):
            if (REPO_ROOT / percorso).exists():
                selezionati.add(percorso)
            continue
        if percorso.startswith(PREFISSI_NON_PYTEST):
            continue
        moduli.append(p.stem)

    for modulo in moduli:
        for candidato in cartella_test.glob(f"test_{modulo}*.py"):
            selezionati.add(str(candidato.relative_to(REPO_ROOT)))
        pattern = re.compile(rf"\b{re.escape(modulo)}\b")
        for file_test in cartella_test.glob("test_*.py"):
            try:
                if pattern.search(file_test.read_text(encoding="utf-8", errors="ignore")):
                    selezionati.add(str(file_test.relative_to(REPO_ROOT)))
            except OSError:
                continue

    return sorted(selezionati)


def _serve_suite_completa(percorsi: list[str]) -> bool:
    if MARKER_PRE_MERGE.exists():
        return True
    if _branch_corrente() == "main":
        return True
    # conftest.py cambia il comportamento di tutta la suite: non e' mirabile.
    return any(Path(p).name == "conftest.py" for p in percorsi)


def _esegui_pytest(argomenti: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("WORKER_DEV_MODE", "1")
    env.setdefault("SUPABASE_URL", "http://x")
    env.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
    return subprocess.run(
        [sys.executable, "-m", "pytest", *argomenti, "-q"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _blocca(esito: subprocess.CompletedProcess, ambito: str) -> None:
    righe = [
        riga
        for riga in esito.stdout.splitlines()
        if "PydanticDeprecatedSince" not in riga and "@model_validator" not in riga
    ]
    coda = "\n".join(righe[-40:])
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": f"Test non verdi ({ambito}, exit {esito.returncode}). Ultime righe:\n{coda}",
            }
        )
    )
    sys.exit(2)


def main() -> int:
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass

    percorsi = _file_toccati()

    if not percorsi:
        return 0

    if _serve_suite_completa(percorsi):
        esito = _esegui_pytest(["tests/"])
        if esito.returncode != 0:
            _blocca(esito, "suite completa")
        MARKER_PRE_MERGE.unlink(missing_ok=True)
        return 0

    if _solo_documenti(percorsi):
        return 0

    mirati = _test_collegati(percorsi)
    if not mirati:
        return 0

    esito = _esegui_pytest(mirati)
    if esito.returncode != 0:
        _blocca(esito, f"{len(mirati)} file di test collegati ai file toccati")
    return 0


if __name__ == "__main__":
    sys.exit(main())
