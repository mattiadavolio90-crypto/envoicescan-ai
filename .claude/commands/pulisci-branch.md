---
description: Elenca i branch locali categorizzati (mergiati/attivi in un'altra sessione/da verificare) per decidere quali eliminare — non elimina mai da solo
---

Esegui `python scripts/pulisci_branch.py` e mostra il risultato all'utente
così com'è (l'output è già la tabella di lettura, non serve riassumerla).

Lo script categorizza i branch locali in tre gruppi:
- **MERGIATI IN MAIN**: sicuri da eliminare con `git branch -d <nome>`.
- **ATTIVI ORA**: un'altra sessione Claude Code risulta averli aperti (legge
  `.claude/.sessioni_attive.json`, scritto da `claude_hook_registra_sessione.py`)
  — non toccarli.
- **DA VERIFICARE**: non mergiati, non attivi — probabilmente abbandonati ma
  potrebbero avere lavoro non ancora spedito. Prima di eliminarli, guarda
  `git log <nome> -5` per capire cosa contengono.

Non eliminare branch autonomamente: proponi quali sembrano sicuri e lascia
che sia l'utente a confermare, o esegui `git branch -d`/`-D` solo dopo
conferma esplicita per ciascun branch "da verificare".
