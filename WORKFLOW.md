# WORKFLOW — Come si lavora a una feature su ONEFLUX

Una pagina. Serve a non perdere decisioni tra sessioni e a non far esplodere i
token nelle sessioni lunghe, **senza** aggiungere cerimonia da ricordare. La
regola guida resta quella di sempre: semplicità prioritaria. Se un passo qui ti
costa più di quanto ti fa risparmiare, salta il passo.

Questo documento **non è un vincolo di dominio** (quelli stanno in `CLAUDE.md`).
È disciplina di processo: descrive il come, non il cosa-non-rompere.

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

**Il completamento di una fase non autorizza mai un deploy.** Il deploy resta
gated a una finestra oraria (sera/notte/mattina presto) dichiarata
esplicitamente da Matt *in sessione*. Vedi `feedback_deploy_solo_fuori_orario`
in memoria e `CLAUDE.md`. Una checklist tutta `[x]` significa "pronto e
committato", non "spingi in produzione".

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
