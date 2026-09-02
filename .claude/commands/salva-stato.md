---
description: Salva lo stato corrente del lavoro in docs/piani/PIANO_<feature>.md prima di sospendere/chiudere la sessione, così una sessione futura riprende senza perdita di contesto
---

Genera o aggiorna `docs/piani/PIANO_<feature>.md` (formato: WORKFLOW.md §2 «Il file di piano»)
con lo stato reale della sessione corrente:

- **Decisioni concordate**: le scelte prese in questa sessione che non vanno
  ridiscusse senza motivo (e il perché).
- **Fasi**: checklist con quelle chiuse spuntate `[x]` e quelle aperte `[ ]`,
  ciascuna con il **modello consigliato** per eseguirla (WORKFLOW.md §4:
  default Opus, Sonnet solo per trascrizione di decisioni già prese).
- **Stato / note aperte**: cosa manca, cosa è in dubbio, link a commit
  rilevanti.

Usa questo comando quando sai già che la sessione sta per chiudersi o
sospendersi (es. l'utente dice "continuiamo domani/dopo"), prima che serva
l'hook automatico di compattazione (`PreCompact`). Se un file
`PIANO_<feature>.md` per questo lavoro esiste già, aggiornalo — non crearne
un secondo per la stessa feature (WORKFLOW.md §2 «Il file di piano»: uno per feature).

Se il lavoro sta in una sessione sola o poche fasi già completate, dillo
esplicitamente invece di forzare un file: WORKFLOW.md §2 sconsiglia di
spezzare per abitudine quando non serve.
