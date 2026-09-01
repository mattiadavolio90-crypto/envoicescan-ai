"""
Hook PreToolUse per Claude Code: avvisa su collisioni fra sessioni parallele
sullo stesso branch.

Il problema che risolve: piu' sessioni Claude Code sulla stessa working
directory (niente worktree per sessione, per scelta) condividono lo stesso
`HEAD`. Due casi concreti gia' osservati su questo repo:
1. Una sessione fa `git checkout`/`switch` su un branch su cui un'altra
   sessione sta gia' lavorando, senza saperlo.
2. Una sessione fa `git commit` dopo che un'altra sessione ha spostato
   l'HEAD nel frattempo: il commit finisce sul branch sbagliato.

Legge il registro scritto da claude_hook_registra_sessione.py
(.claude/.sessioni_attive.json) per sapere quali altre sessioni sono vive e
su quale branch credono di essere.

Su collisione: esce con permissionDecision "ask" (conferma esplicita, non
blocco secco — stesso pattern di claude_hook_db_guard.py). Su nessuna
collisione: exit 0 senza output, nessun attrito.

Configurato in .claude/settings.json come hook PreToolUse su Bash.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRO = REPO_ROOT / ".claude" / ".sessioni_attive.json"

PATTERN_CHECKOUT = re.compile(r"\bgit\s+(checkout|switch)\b")
PATTERN_COMMIT = re.compile(r"\bgit\s+commit\b")


def _pid_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True  # esiste ma di un altro utente: comunque vivo
    except OSError:
        return False
    return True


def _carica_altre_sessioni(pid_corrente: int) -> list[dict]:
    if not REGISTRO.exists():
        return []
    try:
        entries = json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return []
    if not isinstance(entries, list):
        return []
    return [
        e
        for e in entries
        if isinstance(e, dict)
        and e.get("pid") != pid_corrente
        and _pid_vivo(e.get("pid", -1))
    ]


def _branch_destinazione_checkout(comando: str) -> str | None:
    # git checkout [-b] <branch> oppure git switch [-c] <branch>
    match = re.search(r"\bgit\s+(?:checkout|switch)\s+(?:-[bc]\s+)?([^\s-][\w./-]*)", comando)
    return match.group(1) if match else None


def _branch_corrente() -> str:
    try:
        risultato = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return risultato.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _ask(motivo: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": motivo,
        }
    }
    try:
        sys.stdout.write(json.dumps(output) + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(json.dumps(output, ensure_ascii=True) + "\n")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    comando = str((payload.get("tool_input") or {}).get("command") or "")
    if not comando:
        return 0

    pid_corrente = os.getppid()
    altre = _carica_altre_sessioni(pid_corrente)
    if not altre:
        return 0

    if PATTERN_CHECKOUT.search(comando):
        destinazione = _branch_destinazione_checkout(comando)
        if destinazione:
            collisioni = [e for e in altre if e.get("branch_atteso") == destinazione]
            if collisioni:
                dettagli = ", ".join(f"PID {e.get('pid')}" for e in collisioni)
                _ask(
                    f"[ONEFLUX branch guard] Un'altra sessione ({dettagli}) risulta gia' "
                    f"sul branch '{destinazione}'. Passarci sopra ora puo' causare commit "
                    "incrociati fra sessioni. Confermare solo se e' l'intenzione."
                )
        return 0

    if PATTERN_COMMIT.search(comando):
        branch_reale = _branch_corrente()
        mia_entry = next(
            (
                e
                for e in json.loads(REGISTRO.read_text(encoding="utf-8"))
                if e.get("pid") == pid_corrente
            ),
            None,
        ) if REGISTRO.exists() else None
        branch_atteso = mia_entry.get("branch_atteso") if mia_entry else None

        if branch_atteso and branch_reale and branch_atteso != branch_reale:
            _ask(
                f"[ONEFLUX branch guard] Questa sessione si aspettava di essere su "
                f"'{branch_atteso}' ma il branch corrente e' '{branch_reale}' (probabilmente "
                "un'altra sessione ha cambiato branch nel frattempo). Il commit finirebbe su "
                "un branch diverso da quello con cui hai iniziato: confermare solo se e' "
                "l'intenzione."
            )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
