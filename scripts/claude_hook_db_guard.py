"""
Hook PreToolUse per Claude Code: conferma esplicita su comandi distruttivi
verso il DB Supabase reale.

Il problema che risolve: non esiste distinzione locale/produzione su
ONEFLUX — ogni script in scripts/ e ogni chiamata a execute_sql/apply_migration
scrivono sullo stesso DB cloud con dati veri di clienti (vedi CLAUDE.md,
"Trappole": "Next.js in locale punta al DB cloud reale"). Questo era finora
solo documentale, senza alcun enforcement tecnico.

Interviene SOLO su pattern ad alto rischio (flag --commit sugli script di
scripts/, comandi railway che toccano servizi live, SQL grezzo distruttivo
senza WHERE) chiedendo conferma esplicita — non blocca letture o scritture
mirate innocue, per non introdurre attrito su un DB che è comunque l'unico
esistente.

Riceve su stdin il JSON dell'evento PreToolUse. Se rileva un pattern a
rischio, stampa su stdout un JSON con hookSpecificOutput.permissionDecision
"ask" e un motivo; altrimenti esce con 0 senza output (nessun attrito).

Configurato in .claude/settings.json come hook PreToolUse su Bash.
"""
from __future__ import annotations

import json
import re
import sys

PATTERN_RISCHIO: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\bscripts[/\\]\S+\.py\b.*--commit"),
        "Script in scripts/ con --commit: scrive sul DB cloud reale (dati veri di clienti).",
    ),
    (
        re.compile(r"\brailway\s+(redeploy|variables\s+--set|down)\b"),
        "Comando railway che modifica/riavvia un servizio in produzione.",
    ),
    (
        re.compile(
            r"\b(DELETE|UPDATE|DROP|TRUNCATE)\b(?!.*\bWHERE\b)",
            re.IGNORECASE,
        ),
        "Comando SQL distruttivo (DELETE/UPDATE/DROP/TRUNCATE) senza WHERE visibile.",
    ),
]


def _comando_dal_payload(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    return str(tool_input.get("command") or "")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    comando = _comando_dal_payload(payload)
    if not comando:
        return 0

    for pattern, motivo in PATTERN_RISCHIO:
        if pattern.search(comando):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        f"[ONEFLUX DB guard] {motivo}\n"
                        "Operi sul DB cloud reale (Supabase) o su un servizio live: "
                        "non esiste ambiente locale/staging separato su questo repo. "
                        "Conferma solo se e' l'intenzione."
                    ),
                }
            }
            try:
                sys.stdout.write(json.dumps(output) + "\n")
            except UnicodeEncodeError:
                sys.stdout.write(json.dumps(output, ensure_ascii=True) + "\n")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
