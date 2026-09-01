"""
Hook SessionStart per Claude Code: registra la sessione nel registro condiviso
e avvisa se il branch corrente e' vecchio/lontano da main.

Il problema che risolve: piu' sessioni Claude Code lavorano spesso in
parallelo sulla STESSA working directory (niente worktree per sessione, per
scelta). `HEAD` e' uno stato globale al filesystem, non per-sessione: quando
una sessione cambia branch, lo cambia sotto i piedi di tutte le altre, e
nessuna sessione sa che ne esistono altre attive. Un incidente di questa
natura e' gia' documentato in
docs/storico/AUDIT_ONEFLUX_STATO_2026-07_STORICO.md.

Questo hook scrive in .claude/.sessioni_attive.json (git-ignorato, effimero)
una entry {pid, branch_atteso, timestamp_avvio} per la sessione che parte.
Le entry con PID non piu' vivo vengono scartate ad ogni lettura: niente
cleanup esplicito necessario.

Letto poi da claude_hook_branch_guard.py (PreToolUse su git checkout/switch/
commit) per rilevare collisioni fra sessioni sullo stesso branch.

Avvisa (solo stampa, non blocca: vedi WORKFLOW.md §10) se il branch corrente
e' piu' vecchio di 3 giorni o piu' lontano di 20 commit da main — soglia
decisa in sessione, aggressiva di proposito ("short-lived + merge quasi
immediato").

Configurato in .claude/settings.json come hook SessionStart.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRO = REPO_ROOT / ".claude" / ".sessioni_attive.json"

SOGLIA_GIORNI = 3
SOGLIA_COMMIT = 20


def _pid_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True  # esiste ma di un altro utente: comunque vivo
    except OSError:
        return False
    return True


def _carica_registro() -> list[dict]:
    if not REGISTRO.exists():
        return []
    try:
        entries = json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return []
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict) and _pid_vivo(e.get("pid", -1))]


def _salva_registro(entries: list[dict]) -> None:
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _git(*args: str) -> str:
    try:
        risultato = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return risultato.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _branch_corrente() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD")


def _avviso_eta_branch(branch: str) -> str | None:
    if branch in ("main", "HEAD", ""):
        return None

    merge_base = _git("merge-base", "main", branch)
    if not merge_base:
        return None

    n_commit = _git("rev-list", "--count", f"main..{branch}")
    timestamp_divergenza = _git("log", "-1", "--format=%ct", merge_base)

    motivi = []
    try:
        if int(n_commit) > SOGLIA_COMMIT:
            motivi.append(f"{n_commit} commit avanti a main (soglia {SOGLIA_COMMIT})")
    except ValueError:
        pass

    try:
        eta_giorni = (time.time() - int(timestamp_divergenza)) / 86400
        if eta_giorni > SOGLIA_GIORNI:
            motivi.append(f"aperto da {eta_giorni:.1f} giorni (soglia {SOGLIA_GIORNI})")
    except ValueError:
        pass

    if not motivi:
        return None

    return (
        f"[ONEFLUX] Branch '{branch}' vecchio: {', '.join(motivi)}.\n"
        "  -> Valuta un merge a breve o `/pulisci-branch` per vedere lo stato "
        "di tutti i branch (WORKFLOW.md §10)."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    session_id = payload.get("session_id") or ""
    pid = os.getppid()
    branch = _branch_corrente()

    entries = _carica_registro()
    entries = [e for e in entries if e.get("pid") != pid]
    entries.append(
        {
            "pid": pid,
            "session_id": session_id,
            "branch_atteso": branch,
            "timestamp_avvio": time.time(),
        }
    )
    _salva_registro(entries)

    avviso = _avviso_eta_branch(branch)
    if avviso:
        sys.stdout.write(avviso + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
