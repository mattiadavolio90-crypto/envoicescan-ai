"""
Elenca i branch locali del repo, categorizzati, senza mai eliminarne nessuno
in autonomia.

Categorie:
- MERGIATI IN MAIN: sicuri da eliminare (`git branch -d`).
- ATTIVI ORA: hanno una entry viva in .claude/.sessioni_attive.json (un'altra
  sessione Claude Code ci sta lavorando) — non toccare.
- DA VERIFICARE: non mergiati, non attivi — probabilmente abbandonati, ma
  vanno controllati a mano prima di eliminarli (potrebbero avere lavoro non
  ancora spedito).

Uso: python scripts/pulisci_branch.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRO = REPO_ROOT / ".claude" / ".sessioni_attive.json"


def _git(*args: str) -> str:
    risultato = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return risultato.stdout


def _pid_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True  # esiste ma di un altro utente: comunque vivo
    except OSError:
        return False
    return True


def _branch_attivi() -> set[str]:
    if not REGISTRO.exists():
        return set()
    try:
        entries = json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return set()
    if not isinstance(entries, list):
        return set()
    return {
        e.get("branch_atteso")
        for e in entries
        if isinstance(e, dict) and _pid_vivo(e.get("pid", -1)) and e.get("branch_atteso")
    }


def main() -> int:
    branch_corrente = _git("rev-parse", "--abbrev-ref", "HEAD").strip()

    tutti = {
        riga.strip().lstrip("* ").strip()
        for riga in _git("branch").splitlines()
        if riga.strip()
    }
    tutti.discard("main")

    attivi = _branch_attivi() & tutti

    mergiati_raw = {
        riga.strip().lstrip("* ").strip()
        for riga in _git("branch", "--merged", "main").splitlines()
        if riga.strip()
    }
    mergiati_raw.discard("main")
    mergiati_raw.discard(branch_corrente)
    # Un branch attivo (un'altra sessione ci lavora ora) non va MAI proposto
    # come sicuro da eliminare, anche se tecnicamente già mergiato in main.
    mergiati = mergiati_raw - attivi

    da_verificare = tutti - mergiati - attivi

    def _stampa_gruppo(titolo: str, branch: set[str]) -> None:
        print(f"\n{titolo} ({len(branch)})")
        if not branch:
            print("  (nessuno)")
            return
        for nome in sorted(branch):
            print(f"  {nome}")

    print(f"Branch corrente: {branch_corrente}")
    _stampa_gruppo("MERGIATI IN MAIN — sicuri da eliminare (git branch -d <nome>)", mergiati)
    _stampa_gruppo("ATTIVI ORA — un'altra sessione ci sta lavorando, NON toccare", attivi)
    _stampa_gruppo("DA VERIFICARE — non mergiati, non attivi: controllare a mano prima di eliminare", da_verificare)

    print(
        "\nQuesto comando non elimina nulla. Per eliminare un branch mergiato:\n"
        "  git branch -d <nome>\n"
        "Per un branch 'da verificare' che risulta davvero abbandonato, controllare prima\n"
        "il contenuto (git log <nome> -5) e poi eventualmente:\n"
        "  git branch -D <nome>"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
