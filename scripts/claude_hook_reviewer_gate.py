"""
Hook Stop per Claude Code: forza code-reviewer sulle implementazioni
"complesse" prima di chiudere la sessione.

Il problema che risolve: code-reviewer esiste (.claude/agents/code-reviewer.md,
comando /code-reviewer) ma finora scattava solo se qualcuno se ne ricordava a
fine lavoro. Questo hook lo rende sistematico per due criteri (soglia
ibrida, decisa in sessione):

1. Dimensione del diff CUMULATIVO rispetto a main (file non-test/non-md
   toccati o righe nette cambiate sopra soglia — i .md sono esclusi da
   ENTRAMBI i conteggi, non solo dal numero di file: un verbale d'audit
   lungo centinaia di righe non deve far scattare il gate da solo).
   Soglie alzate il 30/8/2026 (3 file/150 righe -> 8 file/400 righe): le
   precedenti scattavano su quasi ogni sessione, e un gate che scatta sempre
   viene ignorato invece che letto.
2. OPPURE il diff tocca un path "sensibile" — riusa la STESSA lista di
   claude_hook_promemoria.py (nessuna duplicazione): un cambio piccolo su
   ai_service.py o auth_service.py e' complesso quanto un refactor grande
   (vedi WORKFLOW.md §3, nota sulla "Ristrutturazione Personale").

Il controllo "inerenze/effetti collaterali" NON e' un hook separato: e'
dentro al perimetro di code-reviewer stesso (vedi .claude/agents/code-reviewer.md).

Rilevamento "code-reviewer gia' girato in questa sessione": tramite un marker
file temporaneo (.claude/.reviewer_gate_ok) che l'agente/comando code-reviewer
deve scrivere a fine corsa. Se il marker non c'e' e la soglia e' superata,
blocca lo Stop UNA SOLA VOLTA con un messaggio esplicito; se lo Stop si
ripresenta con lo stesso HEAD e senza nuove modifiche non forza un loop
infinito (vedi _gia_segnalato_per_questo_head).

Configurato in .claude/settings.json come hook Stop (in aggiunta, non al
posto di, claude_hook_test_gate.py).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_OK = REPO_ROOT / ".claude" / ".reviewer_gate_ok"
MARKER_SEGNALATO = REPO_ROOT / ".claude" / ".reviewer_gate_segnalato"

SOGLIA_FILE_NON_TEST = 8
SOGLIA_RIGHE_NETTE = 400
BRANCH_BASE = "main"


def _carica_path_sensibili() -> list:
    spec = importlib.util.spec_from_file_location(
        "claude_hook_promemoria", REPO_ROOT / "scripts" / "claude_hook_promemoria.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.PATH_SENSIBILI


def _e_file_di_test(percorso: str) -> bool:
    """Un test vero, non un file di produzione che ha "test" nel nome.

    Il filtro precedente (`"test" in percorso.lower()`) scartava
    scripts/ab_test_modello_categorizzazione.py, le Edge Function *_test.ts e
    persino claude_hook_test_gate.py — 177 righe di logica esclusa dal conteggio
    che decide se serve una review.
    """
    normalizzato = percorso.replace("\\", "/")
    nome = normalizzato.rsplit("/", 1)[-1]
    return (
        normalizzato.startswith("tests/")
        or "/tests/" in normalizzato
        or nome.startswith("test_")
        or nome.endswith(("_test.py", "_test.ts"))
    )


def _base_confronto() -> str:
    """Punto di paragone del diff: il branch base, non l'ultimo commit.

    Cambiato il 30/8/2026 col passaggio al ciclo ad accumulo. Misurando su HEAD
    il gate ripartiva da zero a ogni commit, quindi scattava una volta per
    sessione su lavoro gia' rivisto. Misurando sul merge-base con main misura
    l'INTERO lavoro non ancora spedito: scatta una volta sola, su tutto insieme,
    che e' il momento in cui la review serve davvero.
    """
    for riferimento in (f"origin/{BRANCH_BASE}", BRANCH_BASE):
        try:
            esito = subprocess.run(
                ["git", "merge-base", "HEAD", riferimento],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if esito.returncode == 0 and esito.stdout.strip():
                return esito.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            continue
    return ""  # nessuna base: il chiamante deve accorgersene, non misurare zero


def _diff_stat() -> tuple[list[str], int] | None:
    """File non-test toccati e righe nette rispetto al branch base.

    Ritorna None quando la misura NON e' stata possibile (base irrisolvibile o
    git in errore). None e ([], 0) non sono la stessa cosa: il primo significa
    "non lo so", il secondo "misurato, niente da rivedere". Confonderli spegne
    il gate in silenzio — che e' esattamente il difetto che questo gate esiste
    per impedire altrove.
    """
    base = _base_confronto()
    if not base:
        return None
    try:
        risultato = subprocess.run(
            ["git", "diff", "--numstat", base],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return None

    if risultato.returncode != 0:
        return None

    file_non_test: list[str] = []
    righe_nette = 0
    for riga in risultato.stdout.splitlines():
        parti = riga.split("\t")
        if len(parti) != 3:
            continue
        aggiunte, rimosse, percorso = parti
        if _e_file_di_test(percorso) or percorso.endswith(".md"):
            continue
        try:
            righe_nette += int(aggiunte) + int(rimosse)
        except ValueError:
            continue  # file binario
        file_non_test.append(percorso)

    return file_non_test, righe_nette


def _tocca_path_sensibile(file_toccati: list[str], path_sensibili: list) -> str | None:
    for percorso in file_toccati:
        for pattern in path_sensibili:
            if pattern.search(percorso):
                return percorso
    return None


def _head_corrente() -> str:
    try:
        risultato = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return risultato.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def main() -> int:
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass

    if MARKER_OK.exists():
        MARKER_OK.unlink(missing_ok=True)
        MARKER_SEGNALATO.unlink(missing_ok=True)
        return 0

    misura = _diff_stat()
    if misura is None:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        "[ONEFLUX] Il gate non e' riuscito a misurare il diff "
                        f"(base di confronto '{BRANCH_BASE}' irrisolvibile o git in errore).\n"
                        "Non posso dire se serve una review: verifica lo stato del repo, "
                        "oppure lancia /code-reviewer se il lavoro e' sostanziale."
                    ),
                }
            )
        )
        sys.exit(2)

    file_toccati, righe_nette = misura
    if not file_toccati:
        return 0

    path_sensibili = _carica_path_sensibili()
    match_sensibile = _tocca_path_sensibile(file_toccati, path_sensibili)

    complessa = (
        len(file_toccati) > SOGLIA_FILE_NON_TEST
        or righe_nette > SOGLIA_RIGHE_NETTE
        or match_sensibile is not None
    )
    if not complessa:
        return 0

    head = _head_corrente()
    if MARKER_SEGNALATO.exists() and MARKER_SEGNALATO.read_text(encoding="utf-8").strip() == head:
        return 0  # già segnalato per questo stato: non ripetere il blocco all'infinito

    MARKER_SEGNALATO.parent.mkdir(parents=True, exist_ok=True)
    MARKER_SEGNALATO.write_text(head, encoding="utf-8")

    motivo = (
        f"path sensibile toccato ({match_sensibile})"
        if match_sensibile
        else f"{len(file_toccati)} file / {righe_nette} righe nette"
    )
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    f"[ONEFLUX] Implementazione complessa rilevata ({motivo}).\n"
                    "Lancia /code-reviewer prima di chiudere: verifica anche le inerenze "
                    "(chi altro chiama le funzioni/contratti toccati) come da "
                    ".claude/agents/code-reviewer.md."
                ),
            }
        )
    )
    sys.exit(2)


if __name__ == "__main__":
    sys.exit(main())
