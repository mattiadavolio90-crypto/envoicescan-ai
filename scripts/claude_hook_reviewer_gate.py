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


def _diff_stat(base_esplicita: str = "") -> tuple[list[str], int] | None:
    """File non-test toccati e righe nette rispetto al branch base.

    Ritorna None quando la misura NON e' stata possibile (base irrisolvibile o
    git in errore). None e ([], 0) non sono la stessa cosa: il primo significa
    "non lo so", il secondo "misurato, niente da rivedere". Confonderli spegne
    il gate in silenzio — che e' esattamente il difetto che questo gate esiste
    per impedire altrove.
    """
    base = base_esplicita or _base_confronto()
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


# --- Attribuzione dei commit alla sessione (aggiunto il 3/9/2026) ------------
# Il gate misurava `git diff <merge-base con main>`, cioe' TUTTO il lavoro non
# ancora pushato. Con una sessione per volta era giusto; con piu' sessioni in
# parallelo — che qui e' il regime normale — attribuisce a chiunque prema Stop
# anche il lavoro degli altri. Successo il 3/9: una sessione che aveva toccato
# due soli .md si e' vista contestare "11 file / 293 righe", cioe' il lavoro di
# un'altra sessione sui residui. Un avviso che parla di file non tuoi viene
# ignorato per riflesso, ed e' cosi' che un gate muore.
#
# Il registro .sessioni_attive.json porta `timestamp_avvio` per ogni sessione:
# i commit DELLA sessione sono quelli creati dopo quell'istante. Si prende il
# genitore del primo, che e' la base giusta da cui misurare.
#
# DEGRADA VERSO IL VECCHIO COMPORTAMENTO, mai verso "nessun avviso": se il
# registro manca, se la sessione non e' registrata (una ripresa da --continue
# non riscrive il record) o se git non risponde, si torna al merge-base. Un
# gate che tace quando non sa e' peggio di uno che esagera.

REGISTRO_SESSIONI = REPO_ROOT / ".claude" / ".sessioni_attive.json"


def _avvio_sessione(session_id: str) -> float | None:
    """Istante di avvio della sessione corrente, dal registro degli hook."""
    if not session_id or not REGISTRO_SESSIONI.exists():
        return None
    try:
        entries = json.loads(REGISTRO_SESSIONI.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    if not isinstance(entries, list):
        return None
    for voce in entries:
        if isinstance(voce, dict) and voce.get("session_id") == session_id:
            avvio = voce.get("timestamp_avvio")
            if isinstance(avvio, (int, float)):
                return float(avvio)
    return None


def _base_sessione(session_id: str) -> str:
    """Base di misura ristretta ai commit di QUESTA sessione.

    Ritorna "" quando l'attribuzione non e' possibile: il chiamante ricade sul
    merge-base con main, cioe' sul comportamento storico.
    """
    avvio = _avvio_sessione(session_id)
    if avvio is None:
        return ""
    base_main = _base_confronto()
    if not base_main:
        return ""
    try:
        esito = subprocess.run(
            ["git", "log", "--format=%H %ct", f"{base_main}..HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    if esito.returncode != 0:
        return ""

    # `git log` scende dal piu' recente: l'ultimo che supera l'avvio e' il primo
    # commit della sessione.
    #
    # NESSUNA TOLLERANZA all'indietro, ed e' una scelta misurata: una finestra di
    # grazia (provata a 120s) fa rientrare il commit che un'altra sessione ha
    # appena chiuso, che e' esattamente l'errore da eliminare. Sbagliare "in
    # avanti" costa un avviso in meno su lavoro proprio committato nel secondo
    # esatto dell'avvio; sbagliare "all'indietro" ti imputa il lavoro altrui —
    # e quello e' il difetto che fa ignorare il gate.
    primo_della_sessione = ""
    for riga in esito.stdout.splitlines():
        parti = riga.split()
        if len(parti) != 2:
            continue
        sha, timestamp = parti
        try:
            if float(timestamp) >= avvio:
                primo_della_sessione = sha
        except ValueError:
            continue

    if not primo_della_sessione:
        # Nessun commit attribuito. NON si misura da HEAD: git ha risoluzione al
        # secondo, quindi una sessione che committa nello stesso secondo in cui
        # e' partita non si riconoscerebbe nessun commit, misurerebbe zero e il
        # gate TACEREBBE su lavoro vero. Misurato il 3/9: due commit con lo
        # stesso %ct e il gate cieco su 9 file di codice.
        #
        # Si torna al merge-base ("" = comportamento storico): l'avviso puo'
        # comprendere lavoro altrui, ma il gate parla. Fra un avviso troppo
        # largo e un gate muto, il secondo e' il guasto peggiore — un gate muto
        # non lo nota nessuno.
        return ""

    try:
        esito = subprocess.run(
            ["git", "rev-parse", f"{primo_della_sessione}^"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    if esito.returncode != 0 or not esito.stdout.strip():
        return ""
    return esito.stdout.strip()


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


# --- Stato della documentazione (aggiunto il 2/9/2026) -----------------------
# I gate difendevano tutti il CODICE (test, DB, branch, review); nessuno guardava
# lo stato dei DOCUMENTI. Una sessione che chiudeva una dimensione senza
# aggiornare la roadmap non superava nessuna soglia e passava pulita: e' successo
# 6 volte di fila, e il file che deve dire "cosa manca" e' rimasto indietro di
# tre giorni. Questo e' un AVVISO, non un blocco: il giudizio "ho chiuso una
# dimensione" non e' deducibile da un diff, quindi si segnala e si lascia
# decidere. Un blocco su un'euristica verrebbe aggirato per riflesso.

_DOC_STATO = ("DOCUMENTAZIONE/AUDIT_COPERTURA.md", "DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_")
_PREFISSI_CODICE = ("services/", "apps/web/src/", "worker/", "utils/", "config/")
SOGLIA_FILE_CODICE_SENZA_STATO = 4


def _stato_non_aggiornato(file_toccati: list[str]) -> str | None:
    """Molto codice toccato e nessun documento di stato: probabile chiusura muta."""
    di_codice = [
        f
        for f in file_toccati
        if f.startswith(_PREFISSI_CODICE) and "/test" not in f
    ]
    if len(di_codice) <= SOGLIA_FILE_CODICE_SENZA_STATO:
        return None
    if any(f.startswith(_DOC_STATO) for f in file_toccati):
        return None
    return f"{len(di_codice)} file di codice, nessun aggiornamento a stato/contatore"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    if MARKER_OK.exists():
        MARKER_OK.unlink(missing_ok=True)
        MARKER_SEGNALATO.unlink(missing_ok=True)
        return 0

    base_sessione = _base_sessione(payload.get("session_id") or "")
    misura = _diff_stat(base_sessione)
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

    avviso_stato = _stato_non_aggiornato(file_toccati)

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
                    + (
                        f"\n\n[stato documentazione] {avviso_stato}.\n"
                        "Se hai chiuso una dimensione o una fase, /chiusura-feature "
                        "esegue i 5 punti di WORKFLOW.md §5bis (verbale, residui, "
                        "contatore ri-misurato). Se invece e' lavoro in corso, ignora."
                        if avviso_stato
                        else ""
                    )
                ),
            }
        )
    )
    sys.exit(2)


if __name__ == "__main__":
    sys.exit(main())
