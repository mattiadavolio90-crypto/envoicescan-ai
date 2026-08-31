# WORKFLOW — Come si lavora a una feature su ONEFLUX

Una pagina. Serve a non perdere decisioni tra sessioni e a non far esplodere i
token nelle sessioni lunghe, **senza** aggiungere cerimonia da ricordare. La
regola guida resta quella di sempre: semplicità prioritaria. Se un passo qui ti
costa più di quanto ti fa risparmiare, salta il passo.

Questo documento **non è un vincolo di dominio** (quelli stanno in `CLAUDE.md`).
È disciplina di processo: descrive il come, non il cosa-non-rompere.

---

## 0. Si accumula, si spedisce una volta sola

**Regola di base, decisa il 30/8/2026.** Il lavoro si accumula su **un solo
branch** (`lavoro`), e si spedisce in **un unico merge** dentro la finestra
oraria. Non un branch per modifica, non una PR per fix.

**Perché**: nessuna regola ha mai imposto branch-e-PR per ogni intervento —
`grep -i "branch\|PR\|merge"` su questo file e su `CLAUDE.md` non trovava
nulla di normativo. Era una consuetudine auto-alimentata, e costava caro: al 30/8/2026 il repo
aveva accumulato **19 branch remoti** (15 dei quali già dentro `main`, cioè
detriti puri) e **~35 locali** risalenti fino a maggio — tutti potati quel
giorno, oggi restano `main` e `lavoro`. E, dato che merge = deploy, **una
richiesta di autorizzazione a Mattia per ogni singolo intervento** (5 merge il
28/8 tra le 12:44 e le 16:49, in piena fascia di servizio).

### Come si lavora

1. **Durante il lavoro**: commit atomici su `lavoro` (uno per intervento
   concluso, così resta reversibile da solo). Nessuna PR, nessun merge.
   Per un intervento isolato va bene anche commit in locale su `main` **senza
   push** — il push è ciò che spedisce.
2. **Un branch dedicato si apre SOLO se** quel lavoro **potrebbe non essere
   spedito** insieme al resto (refactor lungo, esperimento, lavoro davvero
   parallelo). Altrimenti si resta su `lavoro`.
3. **Prima di spedire**, nella finestra oraria: `touch .claude/.pre_merge`
   (fa girare la suite completa allo Stop), `/code-reviewer` sul lavoro
   cumulativo, poi **una PR, un merge, un deploy**.

### Il lavoro attraversa le sessioni: 4 sessioni ≠ 4 deploy

**Il deploy non è legato alla sessione, è legato al push.** Un commit locale
non spedisce niente e non lo vede nessuno; è `git push` su `main` a far partire
Railway (e Vercel, se il commit tocca `apps/web/**`).

Quindi il lavoro di più sessioni si accumula da solo: 4 sessioni → 4+ commit su
`main` locale → **un push, un deploy**. Non c'è niente da fare per "tenerlo
insieme": succede se non si pusha.

**Divieto operativo**: mai `git push`, `gh pr create` o `gh pr merge` di
iniziativa. Si spedisce **solo** quando Mattia lo dice, e prima si guarda cosa
si sta spedendo — il push manda **tutti** i commit accumulati, non solo quelli
dell'ultima sessione:

```bash
git log --oneline origin/main..main    # cosa partirebbe adesso
git diff --stat origin/main..main      # quanto, e su quali file
```

A inizio sessione, se quel primo comando non è vuoto, **dirlo subito**: c'è
lavoro fatto e non ancora spedito, e Mattia deve saperlo prima di aggiungerne
altro.

### Cosa NON è cambiato

Il gate resta, cambia solo *quando* scatta. La suite completa e il
`code-reviewer` girano **prima di spedire** — che è il momento in cui contano.
Il `code-reviewer` continua inoltre a scattare **sempre** sui path sensibili
(auth, AI, margini, worker), a prescindere dalla dimensione: è lì che ha
trovato i difetti che i test verdi non vedevano.

### Igiene dei branch

Dopo ogni merge, il branch va cancellato (locale e remoto). Controllo
periodico:

```bash
git fetch --prune origin
git branch -r --merged origin/main | grep -v main   # detriti: vanno via
git branch -r --no-merged origin/main               # lavoro vero: da decidere
```

---

## 1. Pianificare ed eseguire sono due momenti, non due sessioni obbligatorie

Lo strumento nativo per separarli è il **plan mode di Claude Code**
(`EnterPlanMode` → si progetta in sola lettura, tu approvi, poi si esegue). È il
**default** per qualsiasi lavoro non banale: zero file da gestire, il piano lo
approvi tu prima che parta una sola Edit.

Chiudere e riaprire una sessione pulita per fase è un'ottimizzazione, **non la
regola**. Conviene solo quando:

- il lavoro dura **più di una sessione** (giorni, o troppe fasi per una sola),
  **oppure**
- la cronologia accumulata è così lunga che il costo/token o la qualità stanno
  degradando visibilmente.

Su una feature piccola — la maggioranza — una sessione sola con plan mode costa
**meno** di due sessioni, perché ogni sessione nuova ri-legge `CLAUDE.md`, le
memorie e ri-esplora il codice (cold start). Non spezzare per abitudine.

**Come decidere, in pratica** (criterio per chi apre la sessione, non per chi
esegue): appena il piano è scritto, guarda quante fasi ha.
- **1-2 fasi piccole, finibili in un pomeriggio** → una sessione sola, plan
  mode, si va dritti fino in fondo. Aprire una seconda sessione qui non fa
  risparmiare token, ne fa spendere di più (ogni sessione nuova riparte da
  zero).
- **3+ fasi, o lavoro che dura più giorni** → il ciclo a più sessioni ha
  senso: `docs/piani/PIANO_<feature>.md` (§2) come documento che porta lo
  stato da una sessione all'altra, e a fine sessione il prompt di ripresa +
  suggerimento del modello per la fase successiva (§3).

Il ciclo a più sessioni **non è il default per ogni richiesta** — è lo
strumento giusto solo quando la dimensione del lavoro lo giustifica davvero.

---

## 1bis. "A che punto siamo?" si risponde in cinque righe

Quando Mattia chiede **lo stato** — «a che punto siamo», «abbiamo finito»,
«cosa manca», «facciamo un recap», «è tutto a posto» — la risposta è:

1. **Una riga secca**: finito / manca X / bloccato su Y.
2. **Al massimo 3 punti**, uno per cosa aperta, una riga ciascuno.
3. **Se serve una sua decisione**, la domanda in fondo, una sola.
4. **Chiudi con «Vuoi il dettaglio?»** — e fermati lì.

**Massimo ~10 righe. Niente tabelle, niente blocchi di codice, niente nomi di
file o funzioni**, salvo che il nome *sia* la risposta. Il dettaglio tecnico si
dà **solo se lo chiede dopo**: allora sì, per esteso.

Il criterio non è «quanto so», è **cosa gli serve per decidere il prossimo
passo**. Se una frase non cambia cosa farà nei prossimi cinque minuti, va
tagliata — anche se è vera, anche se è interessante, anche se l'ho appena
misurata.

**Non fare** (visto il 31/8, su una domanda da tre righe di risposta):
ricostruire il ragionamento che ha portato alla conclusione; citare percorsi
con numero di riga; spiegare *perché* una cosa non è un problema invece di dire
che non lo è; elencare cosa non hai fatto e perché; premettere l'autocritica
alla risposta. Sono tutte cose corrette e tutte fuori posto: la correzione di un
mio errore si dice in mezza riga, non in un paragrafo.

Vale **in ogni sessione**, non solo quando lo ricorda.

---

## 1ter. Fine planning: riepilogo non tecnico + modello per fase

**Sempre**, ad ogni chiusura del plan mode (`ExitPlanMode`), prima o insieme
alla richiesta di approvazione: un riepilogo breve, in linguaggio non
tecnico, di cosa verrà fatto — comprensibile senza aver letto il piano
completo. Se il lavoro ha più fasi, dividilo per fase; per ciascuna fase
indica il **modello consigliato** (Opus/Sonnet) secondo il criterio di §3.

Non è un documento a parte: è l'ultima cosa che accompagna l'uscita dal plan
mode, ogni volta — non solo su richiesta.

---

## 2. Il file di piano: solo per lavori lunghi, uno per feature

Quando (e solo quando) un lavoro supera la singola sessione, si scrive:

```
docs/piani/PIANO_<feature>.md
```

**Uno per feature**, non un `PIANO_ATTUALE.md` unico: su ONEFLUX i lavori vanno
in parallelo (OFFSIDE + SUSHILAND + catena insieme), un file singolo forzerebbe
una serialità che non esiste. Questi file sono **git-ignorati** (`.gitignore`:
`docs/piani/*.md`): sono effimeri, non entrano nel repo, non triggerano
`tests/test_documentazione_onesta.py`.

Struttura minima:

```markdown
# PIANO — <feature>
Sessione di apertura: <data>. Obiettivo in una frase.

## Decisioni concordate (non ridiscutere senza motivo)
- <la cosa decisa e il perché, così una sessione futura non la re-litiga>

## Fasi
- [ ] Fase 1 — <cosa> · modello: <vedi §3>
- [ ] Fase 2 — <cosa> · modello: <vedi §3>
- [x] Fase 0 — <fatta il ...>

## Stato / note aperte
- <cosa manca, cosa è in dubbio, link a commit>
```

**Confine con la memoria persistente:** i file `memory/project_*.md` restano la
fonte di verità sullo *stato tra sessioni diverse* (sopravvivono da soli, senza
che nessuno debba ricordarsi di leggerli). Il `PIANO_<feature>.md` è la *mappa
operativa del lavoro in corso*. Quando la feature è deployata: si aggiorna la
memoria `project_*` con l'esito e **si elimina** il file di piano (vedi
`docs/storico/README.md`). Non tenere due fonti di verità sullo stesso stato.

---

## 3. Modello consigliato per tipo di fase

Il criterio "modello giusto per il compito" è già in uso nei sub-agenti
(`golive-certificatore` su Opus, `categorization-reviewer` su Sonnet). Si
estende alle fasi di sviluppo ordinario:

**Il default è Opus. Sonnet è l'eccezione**, non il regime normale
dell'implementazione. Non esiste la regola "si pianifica con Opus e si esegue con
Sonnet": va deciso fase per fase guardando cosa quella fase contiene davvero.

| Tipo di fase | Modello | Perché |
|---|---|---|
| Pianificazione, design, decisioni architetturali | Opus | Ragionamento, trade-off, si sbaglia meno dove costa di più |
| Debug non ovvio, audit, categorizzazione dubbia | Opus | Serve giudizio, non solo esecuzione |
| UI nuova da zero, modifiche al worker, scelte di interazione | Opus | È progettazione anche se il piano la chiama "implementazione" |
| Trascrizione: il piano dice file, riga e cosa sostituire | Sonnet | Più economico, il ragionamento è già stato fatto |
| Ricerca/scan ampia read-only nel codice | sub-agente `Explore` | Non consuma il contesto della sessione principale |

Test secco: se la fase richiede **decisioni** (cosa togliere, dove collocare una
funzione, come si comporta un'interazione) è Opus, anche se il piano è dettagliato.
Se richiede **trascrizione** di decisioni già prese, Sonnet basta. Nel dubbio, Opus.

> **Perché questa sezione è stata riscritta (31/7/2026).** La versione precedente
> presentava "esecuzione meccanica → Sonnet" come binario, con la caveat in nota.
> Applicata alla lettera su "Ristrutturazione Personale" (fasi 0-5) ha prodotto
> fasi ciascuna corretta in sé e incoerenti fra loro: una fase ha reintrodotto un
> toggle che un commento nel codice dichiarava già ridondante, un'altra ha
> consegnato 5 endpoint funzionanti senza la UI per raggiungerli. Il risultato —
> "tutte le funzioni ci sono ma la pagina è incasinata" — è costato una sessione
> intera di audit e ripianificazione. Il code-reviewer di fine fase non intercetta
> questa classe di problemi: verifica la correttezza *dentro* la fase, mai la
> coerenza *fra* le fasi.

---

## 4. Fine fase ≠ deploy

**Il completamento di una fase non autorizza mai un merge.** E poiché
**merge = deploy** (§0, `CLAUDE.md`), il vincolo di finestra oraria si applica
lì: sera/notte/mattina presto, dichiarata esplicitamente da Mattia *in
sessione*. Vedi `feedback_deploy_solo_fuori_orario` in memoria.

Una checklist tutta `[x]` significa "pronto e committato **su `lavoro`**", non
"spingi in produzione". Col ciclo ad accumulo la domanda va posta **una volta
per ciclo**, non a ogni fase: le fasi si chiudono in silenzio, si spedisce
insieme.

Commit **atomico a fine fase**: una fase conclusa = un commit che compila e
passa i test, così il piano e la git history raccontano la stessa storia e una
sessione futura può riprendere da un punto pulito.

---

## 5. Questo workflow affianca l'hook, non lo sostituisce

`scripts/claude_hook_promemoria.py` (PostToolUse su Edit|Write) risolve un
problema **diverso**: ricorda le *trappole di dominio* nell'istante in cui
tocchi un file critico (bumpa `_BRIEFING_CODE_VERSION`, `/m` non è responsive,
niente `__getattr__` nei router…). Continua a fare quello, sempre.

Questo documento risolve l'oblio delle *decisioni concordate* e il costo/token
delle sessioni lunghe. Sono leve complementari: l'hook parla nel momento
dell'azione, il piano/memoria conservano l'intento tra sessioni. Nessuno dei due
va rimosso in favore dell'altro.

**I due hook `Stop`, come sono tarati oggi** (rivisti il 30/8/2026 — prima
giravano a pieno regime a *ogni* chiusura di sessione, anche per un solo `.md`):

| Hook | Quando agisce | Costo misurato |
|---|---|---|
| `claude_hook_test_gate.py` | solo `.md` → **niente**; lavoro in corso → **solo i test collegati ai file toccati**; `.pre_merge`, `main`, un file globale (`conftest.py`, `requirements.txt`, `pytest.ini`…) o un file non mappabile (es. una migration `.sql`) → **suite completa** | ~20 s invece di ~140-260 s (30/8, modifica a `auth_service.py`: 13 file di test, 153 test). I tempi assoluti dipendono dalla macchina; l'ordine di grandezza no |
| `claude_hook_reviewer_gate.py` | > **8** file non-test **o** > **400** righe nette **o** path sensibile — misurati sul **merge-base con `main`**, cioè su tutto il lavoro accumulato | scatta una volta per ciclo, non una per sessione |

Se il gate **non riesce a misurare** (base di confronto irrisolvibile, git in
errore) blocca dicendolo, invece di lasciar passare in silenzio: "non lo so" e
"niente da rivedere" non sono la stessa cosa.

Le soglie precedenti (3 file / 150 righe, misurate sull'ultimo commit)
scattavano su quasi ogni sessione: un gate che scatta sempre viene saltato per
riflesso invece che letto. I **path sensibili restano senza soglia** — un fix
di tre righe su `auth_service.py` o `ai_service.py` merita la review quanto un
refactor da 400.

---

## 6. Manutenzione della documentazione: automatica, non su richiesta

**Regola vincolante, non un consiglio**: quando una fase/feature/piano si
chiude (checklist tutta `[x]`, `docs/piani/PIANO_<feature>.md` eliminato
secondo §2), prima di considerare il lavoro finito esegui:

```powershell
python scripts/check_documentazione.py
```

Poi agisci **subito, senza chiedere conferma**, sui casi ovvi che riguardano
il lavoro appena chiuso:
- un documento marcato chiuso/deployato il cui contenuto è già confluito in
  memoria (`memory/project_*.md`) o in un commit → **elimina**
- un documento chiuso ma con valore predittivo futuro (pattern di debug,
  causa radice non ovvia) → **sposta in `docs/storico/`** seguendo il
  criterio di `docs/storico/README.md`
- un link rotto generato dal tuo stesso lavoro (es. hai rinominato/spostato
  un file citato altrove) → **ripara** il riferimento
- un documento nuovo che hai creato e che rientra nelle categorie di
  `DOCUMENTAZIONE/MAPPA_TECNICA.md` §6 → **aggiungi la riga all'indice**
  nello stesso momento, non "poi"

Segnala invece (non decidere da solo) solo quando è dubbio se un documento
abbia ancora valore — es. un piano chiuso che non hai scritto tu in questa
sessione e di cui non conosci il contesto completo.

**Perché non è un hook automatico**: nessun evento del sistema (Edit, Stop,
fine sessione) può distinguere da solo "una feature si è appena chiusa" da
"ho appena risposto a una domanda" — quel giudizio richiede leggere il
contesto della conversazione, cosa che solo la sessione stessa può fare. Per
questo la regola è comportamentale (in questo file, sempre in contesto),
rinforzata da uno script che rende il controllo meccanico e verificabile
invece che "a sensazione". Puoi anche lanciarlo tu in qualunque momento per
un controllo generale, indipendente da un lavoro specifico.

---

## 7. Come si conduce un ciclo di audit

Il **metodo** vive qui (persiste anche quando un ciclo si chiude e il suo
documento va in `docs/storico/`). Lo **stato di un ciclo specifico** (quali
dimensioni sono verdi, con che esito, cosa resta aperto) vive nel documento
del ciclo — oggi `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md` (il 2026-07 e il 2026-08 sono
chiuso, in `docs/storico/`). Non
duplicare: se una regola di processo finisce scritta solo dentro il documento
di stato, sparisce col documento quando viene archiviato.

Il documento di stato è in **due file**, e vanno tenuti distinti: quello
principale dice *cosa manca* e deve restare leggibile in un minuto; il
`..._STORICO.md` a fianco raccoglie il dettaglio verificato di ogni passata e
le lezioni operative. Il dettaglio di una passata va **sempre** nello storico:
se torna nel file di stato, quello ridiventa illeggibile (è già successo — a
fine ciclo 2026-07 una singola cella era arrivata a 16.000 caratteri).

**Profondità minima per dimensione**: una passata read-only (agente
`oneflux-audit` o manuale) + una sessione di remediation. **Se la remediation
scrive codice, `code-reviewer` sul diff cumulativo prima di considerare la
dimensione chiusa** — non opzionale. Nel ciclo 2026-07, ogni volta che è
girato ha trovato un difetto reale che i test verdi non vedevano (cache non
invalidata, un'invalidazione che rompeva se stessa, uno streak azzerato da un
fallback finto): non è stato un caso, il pattern si è ripetuto su ogni singola
passata in cui è stato usato.

**Riverifica i numeri con un metodo diverso da quello che li ha prodotti**
prima di fidartene — sia il perimetro dichiarato ("~5000 righe" può essere
1/3 del vero), sia il conteggio di un finding ("39 route" può mancarne 9), sia
la gravità (un HIGH può essere un MEDIUM se il dato che lo aggraverebbe non è
mai raggiungibile in produzione, e viceversa). Un numero preso per buono
dall'agente che l'ha prodotto non è verificato, è solo scritto.

**Una dimensione non è chiusa solo perché non ha errori nei findings
elencati**: se il perimetro dichiarato non copre tutto il codice della
dimensione (es. metà di un file grande mai letta), la dimensione resta 🟡 o
va segnalato il gap esplicitamente — non arrotondare a 🟢 un perimetro
parziale.

---

## 8. Fine implementazione: riepilogo scostamenti dal piano

Al termine dell'esecuzione (tutte le fasi di un piano completate, o una fase
singola chiusa), confronto esplicito contro quanto approvato in planning:

- se sono state necessarie deviazioni (fase saltata, approccio cambiato in
  corsa, scope ridotto o ampliato) → elencarle col motivo, non lasciarle
  implicite nel diff.
- se nessuna deviazione → dichiararlo esplicitamente ("eseguito come
  pianificato, nessuno scostamento"), non dare per scontato che sia ovvio.

Questo è distinto dal verdetto di `code-reviewer` (§7, quello guarda
correttezza/chiusura reale): qui si confronta *cosa è stato fatto* con *cosa
era stato deciso*, non la qualità del codice in sé.

---

## 9. Problema segnalato da un cliente: prima cerca, poi analizzi

Prima di avviare un'analisi da zero su un problema riportato da un cliente,
cerca se è già stato riscontrato: `memory/project_*.md` (fonte di verità
sullo stato tra sessioni, §2) e `DOCUMENTAZIONE/` (inclusi
`docs/storico/*.md` per pattern di debug già chiusi). Un problema già
diagnosticato in passato — anche su un cliente diverso — spesso ha la stessa
causa radice (vedi `docs/storico/README.md` per esempi già capitati su
Invoicetronic/SDI). Solo se la ricerca non trova nulla di pertinente, parti
da un'analisi nuova.

**Il documento di stato si aggiorna una sessione alla volta**, mai in
parallelo (due sessioni sullo stesso file si sovrascrivono senza avviso), e
ogni sessione scrive **solo** la propria riga/dimensione con l'esito reale
verificato in quella sessione — non ricostruire a memoria l'esito di una
sessione altrui.

**Buchi di copertura test scoperti durante un audit non si chiudono in coda
alla stessa sessione**: si dichiarano nel documento come lavoro a sé (sono
scrittura, non audit) e si pianificano come sessione propria.

**Un ciclo si dichiara chiuso solo a copertura completa del perimetro**, non
alla prima passata verde su ogni dimensione: se anche solo alcune dimensioni
hanno avuto una sola passata senza `code-reviewer`, il ciclo resta aperto
finché non ricevono lo stesso scrutinio delle altre. Vedi
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md` per l'obiettivo di copertura
corrente.
