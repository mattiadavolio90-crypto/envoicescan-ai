---
name: chiusura-feature
description: Chiude davvero una fase, feature, dimensione di audit o piano su ONEFLUX — esegue i 5 punti di WORKFLOW.md §5 (mutazione, commit, verbale, contatore, check documentazione), non solo la pulizia dei documenti. Attivala su segnali come "ho finito questa fase", "la dimensione è chiusa", "possiamo chiudere questo piano", o via comando esplicito /chiusura-feature.
---

Esegue la chiusura prescritta da `WORKFLOW.md` §5. Quel documento resta la
fonte di verità sulla regola; questa skill è il modo di eseguirla senza doverlo
riaprire ogni volta.

> **Perché questa skill è stata riscritta (2/9/2026).** La versione precedente
> eseguiva **2 dei 5 punti**: lanciava `check_documentazione.py` e gestiva i
> piani, senza nominare mai il verbale, il contatore o la roadmap del ciclo. Chi
> la invocava credeva di aver chiuso e aveva saltato i tre punti che contano —
> ed è la causa diretta del disallineamento trovato quel giorno: 10 verbali nello
> storico, 4 riflessi nel file di stato. **Vale per le dimensioni di audit quanto
> per le feature**: il nome dice "feature", il perimetro è entrambe.

## I cinque punti, in ordine. Nessuno è saltabile.

### 1. Il codice fa quello che deve — provato per mutazione

Non basta «i test passano». Si rimuove il fix su **copia in scratchpad** (mai sul
file del branch) e si controlla che i test tornino rossi. Un test che non
fallisce quando il difetto torna non è una rete.

Riporta il bilancio: quanti mutanti, quanti uccisi, e **perché** i sopravvissuti
sopravvivono. Un sopravvissuto non motivato è un buco, non un dettaglio.

⚠️ Se il pattern della mutazione non esiste nel sorgente, non hai mutato niente:
«sopravvissuto» non misura nulla. Verifica che la sostituzione sia avvenuta.

### 2. Il lavoro è committato

Non `git add`-ato: **committato**. Il 30/8 il `code-reviewer` ha bloccato una
chiusura esattamente per questo.

```bash
git status --short          # deve essere pulito per i TUOI file
git log --oneline -1
```

Committa **solo i tuoi file**, elencandoli: `git add -A` prende anche il lavoro
delle altre sessioni, che qui è il regime normale.

### 3. Il verbale, nello STORICO del ciclo — **tetto 40 righe**

Va in `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_<ciclo>_STORICO.md`, in coda, con la
data. Formato fisso:

```markdown
## <data> — <dimensione>
**Verdetto:** chiusa / parziale / aperta.
**Fatto:** 3-5 bullet, uno per cosa concreta.
**Non fatto:** ogni voce → va anche nel registro residui (punto 4).
**Trovato:** i difetti reali, con l'impatto sul cliente se c'è.
**Prove:** test aggiunti, mutanti uccisi/sopravvissuti, comandi.
```

**Le lezioni di metodo NON stanno nel verbale**: vanno in memoria persistente o
nella sezione unica in fondo allo storico. Ripetute dentro ogni verbale sono la
causa per cui il verbale medio era arrivato a 178 righe e nessuno li riapriva —
ed è così che i residui sono diventati invisibili.

Aggiorna anche **l'indice in cima allo storico**: una riga, data e verdetto.

### 4. Lo stato del ciclo + il registro dei residui

Nel file di stato (`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_<ciclo>.md`):

- sposta la dimensione nella tabella **«Cosa è chiuso»**, con il verdetto vero
  (`chiusa` ≠ `parziale`: se il perimetro dichiarato non copre tutto, è parziale);
- **ogni voce del tuo «Non fatto» va nella tabella «Residui aperti»**, con dove è
  dichiarata e se è *esclusione motivata* o *lavoro rimandato*;
- aggiorna la data in «Stato aggiornato al …», o il controllo automatico
  segnalerà lo stato come indietro rispetto al suo storico;
- se chiudendo hai risolto un residuo già in lista, **depennalo**: la lista
  invecchia in entrambe le direzioni.

### 5. Il contatore, ri-misurato — e `check_documentazione.py` pulito

`DOCUMENTAZIONE/AUDIT_COPERTURA.md`: sposta la riga (🔴 → 🔍 → 📖) e **ri-misura**
coi comandi in cima al file. Poi **ri-somma la colonna** e verifica che chiuda col
totale: un delta aggiunto senza ri-sommare è come sono nati tre totali diversi
nello stesso documento.

```bash
python scripts/check_documentazione.py
```

Deve uscire pulito (i piani attivi in `docs/piani/` non sono un problema).

## Poi, la pulizia dei documenti

Agisci **subito, senza chiedere conferma**, sui casi ovvi del lavoro appena chiuso:

- documento chiuso il cui contenuto è già in `memory/project_*.md` o in un commit
  → **elimina**
- documento chiuso con valore predittivo futuro (pattern di debug, causa radice
  non ovvia) → **sposta in `docs/storico/`**, seguendo `docs/storico/README.md`
- link rotto generato dal tuo lavoro → **ripara**
- documento nuovo che rientra in `DOCUMENTAZIONE/MAPPA_TECNICA.md` §6 →
  **aggiungi la riga all'indice** ora, non "poi"
- `docs/piani/PIANO_<feature>.md` di una feature deployata → aggiorna la memoria
  `project_*` con l'esito, poi **elimina** il piano

**Segnala invece di decidere** quando è dubbio se un documento ha ancora valore —
es. un piano che non hai scritto tu e di cui non conosci il contesto.

## Cosa NON fa parte della chiusura

- **Il prompt della prossima sessione non si scrive.** Si scrive **solo se Mattia
  lo chiede** (allora: `/salva-stato`). Era in checklist e si auto-rigenerava a
  ogni sessione: un file globale sovrascritto da sessioni che non sapevano cosa
  facevano le altre.
- **Nessun `git push`.** Il push È il deploy, e si fa solo quando Mattia lo dice.
  Riporta la coda senza spedirla: `git log --oneline origin/main..main`.

## Come si chiude

Una riga di verdetto, i punti aperti, la coda commit. Se un punto dei cinque non
è stato fatto, **dillo**: una chiusura dichiarata e incompleta è peggio di una
non dichiarata, perché nessuno la ricontrolla.
