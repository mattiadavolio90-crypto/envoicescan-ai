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
(.claude/.sessioni_attive.json, schema in scripts/_registro_sessioni.py) per
sapere quali altre sessioni sono vive e su quale branch credono di essere.
Girando su ogni Bash, e' anche l'hook che rinfresca la vivacita' della propria
sessione: senza, una sessione lunga scadrebbe mentre e' ancora al lavoro.

Su collisione: esce con permissionDecision "ask" (conferma esplicita, non
blocco secco — stesso pattern di claude_hook_db_guard.py). Su nessuna
collisione: exit 0 senza output, nessun attrito.

Configurato in .claude/settings.json come hook PreToolUse su Bash.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _registro_sessioni import carica, mia_entry, tocca  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

PATTERN_CHECKOUT = re.compile(r"\bgit\s+(checkout|switch)\b")
PATTERN_COMMIT = re.compile(r"\bgit\s+commit\b")


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

    session_id = payload.get("session_id") or ""
    if not session_id:
        # Senza sapere chi sono non posso distinguermi dalle altre entry:
        # segnalerei me stesso come collisione a ogni comando.
        return 0

    # Girando su ogni Bash, questo e' il punto che tiene viva la sessione nel
    # registro: senza, la scadenza ucciderebbe anche chi sta lavorando.
    tocca(session_id)

    altre = carica(escludi_session_id=session_id)
    if not altre:
        return 0

    if PATTERN_CHECKOUT.search(comando):
        destinazione = _branch_destinazione_checkout(comando)
        if destinazione:
            collisioni = [e for e in altre if e.get("branch_atteso") == destinazione]
            if collisioni:
                dettagli = ", ".join(
                    f"sessione {str(e.get('session_id') or '?')[:8]}" for e in collisioni
                )
                _ask(
                    f"[ONEFLUX branch guard] Un'altra sessione ({dettagli}) risulta gia' "
                    f"sul branch '{destinazione}'. Passarci sopra ora puo' causare commit "
                    "incrociati fra sessioni. Confermare solo se e' l'intenzione."
                )
        return 0

    if PATTERN_COMMIT.search(comando):
        branch_reale = _branch_corrente()
        mia = mia_entry(session_id)
        branch_atteso = mia.get("branch_atteso") if mia else None

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
