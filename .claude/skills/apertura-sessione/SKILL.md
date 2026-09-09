---
name: apertura-sessione
description: Apre una sessione di lavoro su ONEFLUX partendo dallo stato reale invece che dal prompt — controlli di sessione, cosa è aperto, residui in sospeso, e la misura a DB dell'area prima di sceglierla. Attivala all'inizio di una sessione, o su segnali come "da dove ripartiamo", "cosa c'è da fare", "apri una dimensione", o via comando esplicito /apertura-sessione.
---

Serve a non ripartire dal prompt. **Il prompt è la fonte meno affidabile che
esista in questo progetto**: nel ciclo 2026-09 le ipotesi del prompt di sessione
sono risultate false **in 5 casi su 10**, e un'area indicata da un prompt aveva
**0 righe a DB**. Lo stato vero sta nei documenti e nel database, non nel testo
che apre la sessione.

## 1. Controlli di sessione — prima di qualunque cosa

```bash
git branch --show-current              # NON basta git log: un'altra sessione può aver spostato HEAD
git status --short                     # file non tuoi = normale, è il regime di lavoro
git log --oneline origin/main..main    # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, col numero che leggi tu adesso
e **di chi sono** i commit: «in coda: 7 commit, 3 miei». Il push manda *tutti* i
commit accumulati, e **il push È il deploy**.

Commit e file non tuoi sono **lo stato atteso**, non un allarme: più sessioni in
parallelo sono la norma. Non chiedere a Mattia cosa farne.

## 2. Leggi lo stato, non il prompt

In quest'ordine, e fermati appena sai cosa fare:

1. `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_<ciclo>.md` — **cosa è chiuso, cosa è
   aperto, i residui**. Si legge in un minuto, ed è l'unico file che devi aprire
   per sapere cosa manca.
2. La sua sezione **«Residui aperti»** — lavoro dichiarato ma mai raccolto. Spesso
   la cosa più utile da fare è lì, non in un'area nuova.
3. `docs/piani/PIANO_*.md` — se esistono, c'è lavoro multi-sessione in corso.
   ⚠️ **Un piano può essere in esecuzione in un'altra sessione**: controlla prima
   di toccarlo.
4. `DOCUMENTAZIONE/AUDIT_COPERTURA.md` — solo se devi scegliere un'area nuova.

**Non aprire lo `_STORICO.md`** per sapere cosa manca: è l'archivio. Si apre solo
per il dettaglio di una dimensione che stai riaprendo (ha un indice in cima).

## 3. Misura a DB prima di scegliere l'area

**La regola che ha funzionato due sere di fila**, e che vale più di qualunque
priorità ereditata: *conta le righe a DB delle tabelle che l'area serve, poi
scegli.*

Così `agenda/` è stata scartata (**0 turni** a DB, 693 righe di codice che nessuno
usa) e `notifiche/` scelta al suo posto (67 righe, 5 utenti, 5 negli ultimi 7
giorni) — dove è stato poi trovato un difetto **che il cliente vedeva**.

```sql
-- esempio: quanto è viva l'area prima di aprirla
SELECT count(*), count(DISTINCT user_id), max(created_at)::date FROM <tabella>;
```

Un'area senza dati non ha difetti raggiungibili: qualunque cosa trovi lì è teoria.

## 4. Verifica le ipotesi del prompt prima di crederci

Se il prompt (o un documento) afferma qualcosa — «questa area non è mai stata
letta», «questo modulo è morto», «sono ~25 punti» — **misuralo prima di
lavorarci**. In questo progetto:

- «~25 punti da correggere» erano **60**;
- «il blocco è codice morto» era **irraggiungibile per costruzione**, cosa diversa;
- una cifra ereditata da un documento è stata sbagliata **8 volte in 5 giorni**.

**Una cifra ripresa da un documento non è una cifra misurata.** Ri-misurala nel
momento in cui la scrivi, anche se l'hai letta dieci minuti fa: le sessioni
parallele committano mentre lavori.

## 5. Dichiara cosa apri, e quanto è grande

Prima di scrivere codice, dichiara: **quale dimensione**, **il perimetro
misurato** (righe, file), **le ipotesi da verificare**, **il criterio di
chiusura**. Se il perimetro non copre tutto il codice della dimensione, dillo
adesso: una dimensione chiusa su un perimetro parziale è `parziale`, non `chiusa`.

**Una cosa alla volta** (`WORKFLOW.md` §5): non si apre una dimensione nuova
finché la precedente non è chiusa davvero — provata per mutazione, committata, col
verbale, il contatore aggiornato e `check_documentazione.py` pulito.

## Come si apre, parlando a Mattia

Una riga su cosa apri e perché quella (con la misura che l'ha decisa), la coda
commit, e una sola domanda se serve una sua decisione. Non elencare cosa hai
letto per arrivarci.
