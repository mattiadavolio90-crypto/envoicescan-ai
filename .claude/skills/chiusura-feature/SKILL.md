---
name: chiusura-feature
description: Manutenzione documentazione a chiusura di una fase/feature/piano su ONEFLUX (checklist tutta [x], PIANO_<feature>.md da eliminare) — elimina/archivia/ripara/indicizza secondo WORKFLOW.md §6. Attivala su segnali come "ho finito questa fase", "la feature è chiusa/deployata", "possiamo chiudere questo piano", o via comando esplicito /chiusura-feature.
---

Replica la procedura vincolante di `WORKFLOW.md` §6 — quel documento resta la
fonte di verità sulla regola, questa skill è il modo di eseguirla senza
doverlo riaprire ogni volta.

## Passi

1. **Esegui sempre, prima di considerare il lavoro finito:**
   ```bash
   python scripts/check_documentazione.py
   ```

2. **Agisci subito, senza chiedere conferma, sui casi ovvi che riguardano il
   lavoro appena chiuso:**
   - documento marcato chiuso/deployato il cui contenuto è già confluito in
     `memory/project_*.md` o in un commit → **elimina**
   - documento chiuso ma con valore predittivo futuro (pattern di debug,
     causa radice non ovvia) → **sposta in `docs/storico/`**, seguendo il
     criterio di `docs/storico/README.md` (un documento sta lì solo se
     insegna qualcosa di riusabile su un problema che può ripresentarsi, non
     solo perché descrive un evento passato)
   - link rotto generato dal tuo stesso lavoro (file rinominato/spostato
     citato altrove) → **ripara** il riferimento
   - documento nuovo che rientra nelle categorie di
     `DOCUMENTAZIONE/MAPPA_TECNICA.md` §6 → **aggiungi la riga all'indice**
     nello stesso momento, non "poi"

3. **Segnala invece di decidere da solo** quando è dubbio se un documento ha
   ancora valore — es. un piano chiuso che non hai scritto tu in questa
   sessione e di cui non conosci il contesto completo.

4. Se un `docs/piani/PIANO_<feature>.md` esiste per questa feature ed è
   deployata: aggiorna la memoria `project_*` con l'esito, poi **elimina** il
   file di piano (è git-ignorato ed effimero per design — WORKFLOW.md §2).

## Perché questi passi e non altri

Il giudizio "una feature si è appena chiusa" richiede il contesto della
conversazione — nessun evento tecnico lo sostituisce. Questa skill non
decide *quando* attivarsi al posto tuo con certezza assoluta: se il segnale
è ambiguo, chiedi prima di agire sui documenti.
