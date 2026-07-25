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

| Tipo di fase | Modello | Perché |
|---|---|---|
| Pianificazione, design, decisioni architetturali | Opus | Ragionamento, trade-off, si sbaglia meno dove costa di più |
| Debug non ovvio, audit, categorizzazione dubbia | Opus / Sonnet | Serve giudizio, non solo esecuzione |
| Esecuzione meccanica di una fase già decisa | Sonnet | Più economico, il piano ha già fatto il ragionamento |
| Ricerca/scan ampia read-only nel codice | sub-agente `Explore` | Non consuma il contesto della sessione principale |

Indicazione, non legge. Se una fase "meccanica" nasconde una decisione, torna su
Opus.

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
