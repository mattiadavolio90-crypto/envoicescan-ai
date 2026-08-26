"""
Hook PreCompact per Claude Code: forza uno scheletro di continuita' prima
che la cronologia venga compattata.

Il problema che risolve: WORKFLOW.md (SS1-2) descrive gia' il meccanismo per
non perdere stato tra sessioni (docs/piani/PIANO_<feature>.md), ma e' solo
comportamentale - dipende dal fatto che la sessione se ne ricordi PRIMA che
il contesto lungo venga tagliato. Nessun trigger tecnico lo richiamava.

Questo hook non decide il contenuto (richiede il contesto della
conversazione, che solo la sessione ha): genera/aggiorna solo lo SCHELETRO
del file con le sezioni gia' formattate secondo WORKFLOW.md SS2, e stampa un
promemoria forte che obbliga a fermarsi e riempirlo prima che la
compattazione avvenga.

Riceve su stdin il JSON dell'evento PreCompact. Non blocca mai la
compattazione (un hook che blocca per un promemoria e' un hook che verra'
disattivato): scrive lo scheletro se non esiste gia' un piano per la
feature indicata, poi stampa il promemoria ed esce sempre con 0.

Configurato in .claude/settings.json come hook PreCompact.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

PIANI_DIR = Path("docs/piani")

SCHELETRO = """# PIANO — {feature}
Sessione di apertura: {data}. Obiettivo in una frase.

## Decisioni concordate (non ridiscutere senza motivo)
- <la cosa decisa e il perché, così una sessione futura non la re-litiga>

## Fasi
- [ ] Fase 1 — <cosa> · modello: <Opus/Sonnet, vedi WORKFLOW.md §3>
- [ ] Fase 2 — <cosa> · modello: <Opus/Sonnet, vedi WORKFLOW.md §3>

## Stato / note aperte
- <cosa manca, cosa è in dubbio, link a commit>
"""


def _slug(nome: str) -> str:
    pulito = re.sub(r"[^\w\-]+", "_", nome.strip(), flags=re.UNICODE)
    return pulito.strip("_") or "SENZA_NOME"


def _stampa(testo: str) -> None:
    try:
        sys.stdout.write(testo + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(testo.encode("ascii", "replace").decode("ascii") + "\n")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    PIANI_DIR.mkdir(parents=True, exist_ok=True)

    esistenti = sorted(p.name for p in PIANI_DIR.glob("PIANO_*.md"))

    if esistenti:
        _stampa(
            "[ONEFLUX] Compattazione imminente — piano/i già aperto/i: "
            + ", ".join(esistenti)
            + "\n  -> Aggiorna QUI, ora, prima che il contesto venga tagliato: "
            "Decisioni concordate, checklist Fasi (spunta quelle chiuse), "
            "Stato/note aperte, e il modello consigliato per la fase successiva "
            "(WORKFLOW.md §3: default Opus, Sonnet solo per trascrizione)."
        )
        return 0

    nome_feature = str(payload.get("feature") or "").strip()
    slug = _slug(nome_feature) if nome_feature else "SESSIONE_CORRENTE"
    percorso = PIANI_DIR / f"PIANO_{slug}.md"

    percorso.write_text(
        SCHELETRO.format(feature=nome_feature or slug, data=date.today().isoformat()),
        encoding="utf-8",
    )

    _stampa(
        f"[ONEFLUX] Compattazione imminente — nessun piano aperto.\n"
        f"  -> Scheletro creato: {percorso.as_posix()}\n"
        "  -> FERMATI e riempilo ORA con lo stato reale (decisioni prese, fasi fatte/da fare, "
        "modello consigliato per la fase successiva) prima che il dettaglio si perda nel riassunto. "
        "Se il lavoro sta in una sola sessione/poche fasi, questo file è di cortesia: "
        "puoi anche cancellarlo a fine sessione (WORKFLOW.md §1)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
