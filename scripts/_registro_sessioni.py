"""
Registro delle sessioni Claude Code attive sulla stessa working directory.

Perche' esiste: piu' sessioni lavorano in parallelo sullo stesso filesystem
(niente worktree per sessione, per scelta). `HEAD` e' globale: serve sapere
chi altro e' vivo e su quale branch crede di essere.

**Perche' NON si usa il PID** (R9, corretto il 3/9/2026). Il registro salvava
`os.getppid()`: il genitore di un hook Claude Code e' il wrapper che lo invoca
e muore subito dopo. Misurato: il PID scritto a SessionStart era gia' morto
mentre la sessione era pienamente attiva, quindi ogni lettura scartava tutte
le entry. Il payload JSON degli hook non porta nessun identificativo di
processo: `session_id` e' l'unico campo stabile.

Vivacita' = `ultimo_visto` recente, non "PID vivo". Il timestamp viene
rinfrescato da ogni hook che passa di qui (vedi `tocca`), non solo a
SessionStart: una sessione che lavora resta viva a prescindere da quanto dura,
una abbandonata scade entro SCADENZA_SECONDI.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRO = REPO_ROOT / ".claude" / ".sessioni_attive.json"

# Rinfrescata a ogni hook: una sessione attiva non la raggiunge mai. Regola
# solo da quanto sopravvive una sessione chiusa senza che nessuno la rimuova.
SCADENZA_SECONDI = 2 * 60 * 60


def _branch_corrente() -> str:
    try:
        esito = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return esito.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def sessione_viva(entry: dict) -> bool:
    """Vive se l'ultimo segno di vita e' entro la soglia.

    Le entry in formato vecchio (col campo `pid`, senza `ultimo_visto`) non
    hanno segno di vita: scadute per definizione, mai un crash.
    """
    ultimo = entry.get("ultimo_visto")
    if not isinstance(ultimo, (int, float)):
        return False
    return time.time() - float(ultimo) < SCADENZA_SECONDI


def carica(escludi_session_id: str = "") -> list[dict]:
    """Entry vive, opzionalmente escludendo la sessione corrente."""
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
        and sessione_viva(e)
        and not (escludi_session_id and e.get("session_id") == escludi_session_id)
    ]


def salva(entries: list[dict]) -> None:
    """Scrittura atomica: `write_text` tronca il file, e con le sessioni in
    parallelo (il regime normale) un lettore concorrente ne leggeva meta' —
    JSON invalido, quindi "registro vuoto". Misurato prima di introdurlo:
    5 sessioni che si rinfrescano insieme azzeravano il registro (0 entry su 5).
    `os.replace` e' atomico: chi legge vede il file vecchio o quello nuovo.
    """
    try:
        REGISTRO.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(REGISTRO.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
            os.replace(tmp, REGISTRO)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass  # un hook non deve mai far fallire il comando dell'utente


def registra(session_id: str, branch_atteso: str) -> None:
    """Scrive (o rimpiazza) l'entry della sessione. Chiamata a SessionStart."""
    ora = time.time()
    entries = carica(escludi_session_id=session_id)
    entries.append(
        {
            "session_id": session_id,
            "branch_atteso": branch_atteso,
            "timestamp_avvio": ora,
            "ultimo_visto": ora,
        }
    )
    salva(entries)


def tocca(session_id: str) -> None:
    """Rinfresca `ultimo_visto` della sessione corrente.

    Chiamata dagli hook che girano spesso: e' cio' che tiene viva una sessione
    lunga senza allungare la scadenza per quelle abbandonate.

    Se la sessione non c'e' piu' (scaduta durante una pausa lunga, e cancellata
    dalla prima scrittura di un'altra sessione) la RI-REGISTRA. Senza, una
    sessione che riprende a lavorare resterebbe invisibile per sempre: nessuna
    collisione rilevata e il gate di review di nuovo cieco — cioe' R9 daccapo,
    solo piu' raro. `timestamp_avvio` riparte da adesso e non e' un dato
    inventato: e' il momento da cui questa sessione e' tornata al lavoro, e per
    l'attribuzione dei commit sbaglia dal lato prudente (misura di meno, mai
    lavoro altrui).
    """
    if not session_id:
        return
    ora = time.time()
    entries = carica()
    trovata = False
    for entry in entries:
        if entry.get("session_id") == session_id:
            entry["ultimo_visto"] = ora
            trovata = True
    if not trovata:
        entries.append(
            {
                "session_id": session_id,
                "branch_atteso": _branch_corrente(),
                "timestamp_avvio": ora,
                "ultimo_visto": ora,
            }
        )
    salva(entries)


def mia_entry(session_id: str) -> dict | None:
    if not session_id:
        return None
    for entry in carica():
        if entry.get("session_id") == session_id:
            return entry
    return None
