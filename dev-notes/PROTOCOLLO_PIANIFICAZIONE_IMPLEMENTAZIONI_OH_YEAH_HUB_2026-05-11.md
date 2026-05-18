# Agente AI - Pianificazione Implementazioni OH YEAH! Hub

> **Versione:** 1.0 - Maggio 2026  
> **Scopo:** Definire il protocollo completo che l'agente AI deve seguire ogni volta che viene richiesta una nuova implementazione nel progetto OH YEAH! Hub. L'obiettivo e arrivare all'implementazione con un piano d'azione completo, verificato, privo di ambiguita e a rischio-zero di rottura del codice esistente.  
> **Modelli assegnati:**  
> - Fase di analisi e costruzione piano -> **Claude Opus (livello massimo)**  
> - Esecuzione roadmap e verifiche intermedie -> **Modelli automatici (Copilot Agent/GPT-4o)**  
> - Check finale pre-implementazione -> **Claude Opus (livello massimo)**  
> - Interventi correttivi post-check -> **Modelli automatici**

***

## PARTE 1 - FILOSOFIA E PRINCIPI

### 1.1 Principio fondamentale

Nessuna riga di codice viene scritta finche il piano non e **completo, verificato e approvato**. L'implementazione e l'ultimo atto, non il primo.

### 1.2 Perche questo protocollo esiste

Le applicazioni in produzione hanno uno stato complesso: dipendenze tra moduli, cache, session state, pipeline di ingestione dati, worker asincroni, RLS sul database, logica di autenticazione e flussi multi-tenant. Aggiungere una funzionalita senza analizzare prima come si integra con tutto questo produce:

- bug difficili da tracciare
- regressioni su funzionalita esistenti
- incoerenze tra database e UI
- race condition tra worker e modifica manuale
- perdita di dati silenziosa

L'obiettivo di questo protocollo e **eliminare le sorprese** rendendo ogni step dell'implementazione prevedibile, verificabile e reversibile.

### 1.3 Regola d'oro

> **Se durante qualsiasi fase emergono domande senza risposta certa, ci si ferma. Non si procede. Si risolvono prima.**

***

## PARTE 2 - STRUTTURA DELLE FASI

Il processo si divide in **5 fasi sequenziali**. Nessuna fase puo iniziare finche la precedente non e completata e firmata.

```text
FASE 1 -> Briefing e raccolta requisiti         [OPUS]
FASE 2 -> Analisi codebase e proposta iniziale  [OPUS]
FASE 3 -> Verifica critica e confronto          [OPUS + modelli automatici]
FASE 4 -> Risoluzione blocchi e patch spec      [modelli automatici + OPUS check finale]
FASE 5 -> Piano approvato -> implementazione     [modelli automatici per step]
```

***

## PARTE 3 - FASE 1: BRIEFING E RACCOLTA REQUISITI

**Eseguita da: Claude Opus**

### Obiettivo

Capire esattamente cosa si vuole costruire, con quali vincoli, e identificare subito le domande bloccanti prima di toccare il codice.

### Input richiesti dall'utente

Prima di iniziare qualsiasi analisi, Opus deve raccogliere queste informazioni:

1. **Descrizione funzionale** - cosa deve fare la nuova funzionalita dal punto di vista dell'utente finale
2. **Perimetro** - quali pagine, moduli o flussi esistenti sono coinvolti o limitrofi
3. **Vincoli espliciti** - cosa NON deve cambiare (es. "la pagina analisi deve rimanere identica")
4. **Decisioni gia prese** - scelte di business gia definite (es. "il pagamento e solo flag si/no, non importi parziali")
5. **Priorita di rischio** - quali aree dell'app sono piu critiche da proteggere

### Output atteso

Un documento `BRIEFING_[feature]_[data].md` con:

- Descrizione funzionale pulita e verificata
- Lista decisioni di business gia prese
- Lista domande bloccanti aperte (da risolvere prima di passare alla Fase 2)
- Perimetro d'impatto preliminare

### Regola

**Opus non passa alla Fase 2 finche tutte le domande bloccanti della Fase 1 non sono state risposta dall'utente.**

***

## PARTE 4 - FASE 2: ANALISI CODEBASE E PROPOSTA INIZIALE

**Eseguita da: Claude Opus**

### Obiettivo

Leggere il codice reale, costruire la proposta architetturale completa e identificare ogni punto di contatto con il sistema esistente.

### Attivita obbligatorie

Opus deve eseguire **tutte** le seguenti ricerche nel codebase prima di scrivere qualsiasi proposta:

#### 4.1 Mappatura moduli coinvolti

- Identificare ogni file che verra modificato (non solo creato)
- Per ogni file: capire il suo ruolo attuale, chi lo chiama, chi lo usa
- Cercare dead code correlato da eliminare

#### 4.2 Analisi modello dati esistente

- Struttura reale delle tabelle coinvolte (non quella documentata, quella reale)
- Indici, constraint, RLS, trigger esistenti
- Pattern migration gia utilizzati (per replicarli)
- Numero ultima migration (per continuare la sequenza)

#### 4.3 Analisi pipeline di ingestione

- Come arriva un dato nel sistema (upload manuale, API esterna, worker, etc.)
- Dove avviene il parsing e il salvataggio
- Dove potrebbe rompersi se si aggiunge un nuovo step

#### 4.4 Analisi cache e state management

- Quali cache TTL esistono e cosa invalidano
- Quali chiavi `st.session_state` sono gia usate (per evitare collisioni)
- Come funziona il reset al cambio di contesto (es. cambio ristorante)
- Pattern `cache_version` se presente

#### 4.5 Analisi notifiche e feedback UI

- Quali sistemi di notifica esistono (in-app, alert, toast, expander)
- Come vengono gestiti i dismiss persistenti
- Cosa deve essere spostato vs cosa puo restare

#### 4.6 Analisi autenticazione e multi-tenant

- Come viene verificato l'accesso alle pagine
- Come sono protetti i dati per utente e per ristorante
- Pattern RLS da replicare

#### 4.7 Analisi test esistenti

- Infrastruttura test disponibile (pytest, Supabase locale)
- Copertura attuale
- Lacune di test nelle aree impattate

### Output atteso

Un documento `PROPOSTA_ARCHITETTURALE_[feature]_[data].md` con:

- Schema tabelle nuovo/modificato (con colonne, chiavi, indici, RLS, trigger)
- Lista migrations con ordine e numero
- Firme canoniche di tutti i nuovi servizi/funzioni
- Mappa file coinvolti (modificati vs creati)
- Regole di business formalizzate
- Strategia cache e session state
- Step plan preliminare

***

## PARTE 5 - FASE 3: VERIFICA CRITICA A PIU LIVELLI

**Eseguita da: Claude Opus (struttura verifica) + modelli automatici (esecuzione ricerche)**

Questa e la fase piu importante. La proposta viene **smontata e verificata punto per punto** contro il codice reale. Non ci si fida della proposta: si verifica tutto.

### 5.1 Struttura della verifica

La verifica e organizzata in **Sezioni tematiche** (da A a N, a seconda della complessita). Ogni sezione contiene punti numerati nel formato:

```text
[PUNTO X.Y] - ✅ OK / ⚠️ ATTENZIONE / ❌ BLOCCO
Riga: nome_file.py (con numero riga dove possibile)
Motivazione: spiegazione sintetica
Azione: (solo per ⚠️ e ❌) cosa fare prima di procedere
```

### 5.2 Sezioni obbligatorie della verifica

#### Sezione A - Aderenza proposta al codice reale
Verifica se quello che la proposta dice esiste, funziona come descritto o e diverso dalla realta.

Punti da verificare:
- Ogni modulo citato nella proposta esiste davvero nel percorso indicato
- Le funzioni menzionate hanno le firme reali attese
- I dati che si vogliono leggere esistono gia nelle strutture attuali
- I pattern che si vogliono replicare sono effettivamente nel codice
- Non ci sono versioni duplicate o dead code che creano confusione

#### Sezione B - Rischi non coperti dalla proposta
Ricerca attiva di problemi che la proposta NON ha considerato.

Punti da verificare obbligatoriamente:
- **Trial/piano SaaS**: la nuova funzionalita e accessibile in trial? Serve gating?
- **Multi-tenant/multi-ristorante**: tutti i dati nuovi sono isolati per `user_id` e `ristorante_id`?
- **GDPR export e delete account**: le nuove tabelle sono incluse nell'export dati e nella cancellazione account?
- **Cestino/soft delete**: se esiste soft delete, il nuovo dato lo eredita correttamente?
- **Concorrenza**: cosa succede se worker asincrono e modifica manuale agiscono sullo stesso dato contemporaneamente?
- **Tipi documento edge case**: il nuovo flusso gestisce tutti i `tipo_documento` possibili (non solo il caso principale)?
- **Session state collisions**: le nuove chiavi `st.session_state` usano un namespace dedicato e non collidono con quelle esistenti?
- **Cache scope per utente**: le cache nuove sono keyed per utente/ristorante e non condivise tra sessioni diverse?

#### Sezione C - Decisioni aperte che bloccano l'implementazione
Lista di scelte tecniche ancora non prese che renderebbero l'implementazione ambigua.

Per ogni decisione aperta:
- Descrizione del problema
- Opzioni disponibili (A, B, C...)
- Pro e contro di ciascuna
- Raccomandazione tecnica

#### Sezione D - Proposta finale integrata
Dopo aver raccolto i risultati delle Sezioni A, B, C, la proposta viene riscritta nelle parti che erano sbagliate o incomplete.

Questa sezione produce:
- Schema tabelle corretto e definitivo
- Firme funzioni aggiornate
- Migration plan numerato
- Step plan operativo aggiornato con file precisi
- Discrepanze risolte con severita (Bloccante / Importante / Minore)

#### Sezione E - Domande pre-Step specifiche
Per ogni step del piano che richiede implementazione immediata e senza ambiguita, vengono poste domande mirate al codice:

Formato domanda:
```text
DOMANDA: [cosa serve sapere]
RICERCA: [ricerca nel codebase da eseguire]
RISPOSTA: [trovata dal modello automatico]
IMPATTO: [cosa cambia nella spec dopo questa risposta]
```

#### Sezione F - Revisione critica pre-Step (per ogni step complesso)
Prima che un modello automatico inizi lo Step N, Opus fa una revisione critica:

Punti obbligatori:
- Lacune nella specifica che causerebbero bug in produzione
- Ordine delle operazioni corretto (es. trigger definiti prima del loro utilizzo)
- Servizi mancanti da creare prima di poter implementare
- Edge case non coperti
- Miglioramenti suggeriti alla specifica

### 5.3 Regola di progressione

- ✅ OK -> nessuna azione richiesta
- ⚠️ ATTENZIONE -> l'utente decide, la spec viene aggiornata, si prosegue
- ❌ BLOCCO -> implementazione sospesa finche non risolto

**Non si puo passare alla Fase 4 se esistono ❌ BLOCCO aperti.**

***

## PARTE 6 - FASE 4: RISOLUZIONE BLOCCHI E PATCH SPEC

**Eseguita da: modelli automatici per patch + Claude Opus per check finale**

### 6.1 Gestione decisioni bloccanti

Per ogni ⚠️ e ❌ aperto, l'utente prende una decisione esplicita nel formato:

```text
[PUNTO X.Y] Decisione: [testo decisione]
```

Esempio reale:
```text
[1.1] Naming: usare piva_fornitore ovunque, non piva_cedente
[1.2] scadenza_source: normalizzare sempre a 'xml' lato parser
[1.3] Rimuovere CHECK scadenza_xml >= data_documento dalla migration
```

### 6.2 Patch della specifica

I modelli automatici applicano patch **solo al documento di specifica**, senza toccare alcun file di codice applicativo.

Per ogni patch:
- Identificare le righe esatte da modificare (con ricerca regex sul documento)
- Applicare modifica minimale e puntuale
- Non toccare sezioni non coinvolte dalla decisione

### 6.3 Check coerenza post-patch

Dopo ogni batch di patch, il modello automatico esegue una verifica di coerenza:
- Nessun riferimento obsoleto rimasto nel documento
- Nessuna contraddizione interna
- Tutti i punti ⚠️/❌ risolti sono aggiornati nel documento

### 6.4 Check finale Opus

Claude Opus legge la specifica patchata e verifica:
- Coerenza interna complessiva
- Nessun punto bloccante residuo
- Piano implementativo internamente consistente
- Nessuna ambiguita che possa causare implementazione errata

Se il check passa -> emette `✅ PIANO APPROVATO`.  
Se fallisce -> torna alla risoluzione blocchi.

### 6.5 Documento di specifica finale

Al termine della Fase 4 esiste un documento `REVIEW_CRITICA_[feature]_[data].md` che contiene:

- Analisi completa (Sezioni A->N)
- Tutte le decisioni prese dall'utente
- Schema dati definitivo
- Firme funzioni canoniche
- Migration plan con numeri reali
- Step plan operativo completo
- Strategia test
- Tech-debt tracciato (⚠️ risolti ma da tenere d'occhio)

***

## PARTE 7 - FASE 5: IMPLEMENTAZIONE PER STEP

**Eseguita da: modelli automatici (uno step alla volta)**

### 7.1 Regola fondamentale

Un solo step alla volta. Nessuno step successivo inizia senza:
1. Conferma esplicita che lo step precedente e completato
2. Nessuna regressione introdotta (test passano)
3. Criterio di done verificato

### 7.2 Formato di ogni step

Ogni step del piano ha questa struttura obbligatoria:

```markdown
### STEP N - [Nome Step]

**Obiettivo:** [cosa produce questo step, in una frase]

**File coinvolti:**
- percorso/file.py -> [modifica / creazione / eliminazione] - [perche]

**Operazioni in ordine:**
1. [prima operazione]
2. [seconda operazione]
...

**Regole:**
- [vincoli specifici di questo step]
- [cosa NON fare]

**Edge case da gestire:**
- [caso limite 1 con soluzione]
- [caso limite 2 con soluzione]

**Test da eseguire:**
- [ ] [test 1]
- [ ] [test 2]

**Criterio di done:**
[condizione verificabile che conferma il completamento]

**Rischio:** Basso / Medio / Alto
**Rollback:** [come annullare questo step se va storto]
```

### 7.3 Gestione errori durante l'implementazione

Se durante uno step il modello automatico incontra qualcosa di diverso da quanto previsto nella spec:

1. **Si ferma**
2. Descrive la discrepanza trovata
3. Chiede conferma all'utente prima di procedere
4. NON inventa soluzioni alternative non previste dal piano

### 7.4 Check intermedi

Ogni 2-3 step, Opus puo essere coinvolto per un check intermedio se:
- Lo step era classificato come rischio Alto
- Sono emerse discrepanze durante l'implementazione
- Si sospetta una regressione

### 7.5 Check finale Opus post-implementazione

Dopo l'ultimo step, Claude Opus esegue un audit finale:

- Verifica che tutti i file previsti siano stati toccati
- Verifica che i file NON previsti non siano stati toccati
- Verifica coerenza tra schema DB atteso e schema reale
- Verifica che i test chiave passino
- Produce `AUDIT_POST_IMPLEMENTAZIONE_[feature]_[data].md`

***

## PARTE 8 - SEZIONI DI VERIFICA STANDARD (TEMPLATE RIUSABILE)

Questo e il template delle sezioni di verifica da usare per ogni nuovo progetto. Le sezioni vanno adattate alla feature specifica ma la struttura e sempre questa.

### Sezione A - Aderenza proposta vs codice reale
Verificare che ogni claim della proposta corrisponda alla realta del codebase.

### Sezione B - Rischi non coperti
Ricerca attiva di problemi non considerati: trial, multi-tenant, GDPR, soft delete, concorrenza, edge case tipi documento, session state collisions, cache scope.

### Sezione C - Decisioni aperte
Scelte tecniche ancora non prese. Con opzioni, pro/contro, raccomandazione.

### Sezione D - Proposta finale integrata
Schema dati corretto, firme funzioni, migration plan, step plan, discrepanze risolte.

### Sezione E - Domande pre-Step
Ricerche mirate nel codice per eliminare ogni ambiguita prima dell'implementazione.

### Sezione F - Revisione critica pre-Step
Lacune spec, ordine operazioni, servizi mancanti, edge case, miglioramenti.

### Sezione G - Specifica operativa step-by-step
Dettaglio tecnico completo di ogni step: pseudocodice, flusso dati, punti di inserimento nel codice, chiavi session state, pattern da replicare.

### Sezione H - Verifica finale pre-approvazione
Controllo che spec sia internamente coerente, senza contraddizioni, senza ambiguita residue.

***

## PARTE 9 - REGOLE COMPORTAMENTALI DELL'AGENTE

### 9.1 Cosa l'agente DEVE sempre fare

- Leggere il codice reale prima di fare qualsiasi affermazione su di esso
- Usare numeri di riga precisi nelle citazioni al codice
- Distinguere chiaramente tra "la proposta dice" e "il codice dice"
- Segnalare esplicitamente ⚠️ e ❌ senza minimizzare
- Fermarsi e chiedere quando incontra ambiguita
- Aggiornare solo la spec, mai il codice applicativo durante le fasi 1-4
- Usare nomi variabili/funzioni esatti dal codice reale, non inventarne

### 9.2 Cosa l'agente NON deve mai fare

- Implementare codice durante la fase di analisi/progettazione
- Supporre che una funzione esista senza verificarla
- Procedere con ❌ BLOCCO aperti
- Patchare piu sezioni della spec in un colpo solo senza conferma utente
- Rinominare funzioni o tabelle senza approvazione esplicita
- Saltare step del piano per "efficienza"
- Considerare approvato un piano che non ha ricevuto `✅ PIANO APPROVATO` esplicito

### 9.3 Formato comunicazione con l'utente

Durante la fase di analisi, l'agente comunica con l'utente usando questo formato standard:

**Per decisioni richieste:**
```text
DECISIONE RICHIESTA [X.Y]
Problema: [descrizione]
Opzione A: [descrizione] -> Pro: ... Con: ...
Opzione B: [descrizione] -> Pro: ... Con: ...
Raccomandazione tecnica: [A/B/altro]
```

**Per conferme avanzamento:**
```text
✅ Sezione [N] completata - [N_OK] OK, [N_WARN] ⚠️, [N_BLOCK] ❌
Proseguo con Sezione [N+1]? / Attendo decisioni su: [lista punti aperti]
```

**Per emissione piano approvato:**
```text
✅ PIANO APPROVATO
Data: [data]
Versione spec: [nome file]
Step plan: [N] step
Tech-debt tracciato: [lista ⚠️ residui]
Pronto per implementazione Step 1.
```

***

## PARTE 10 - DOCUMENTO DI CONTESTO PROGETTO

Ogni volta che si inizia una nuova sessione di pianificazione, l'agente riceve in input il **documento di contesto progetto** aggiornato. Questo documento contiene:

### Stack tecnologico
- Frontend: Streamlit
- Backend: Python 3.11+
- Database: Supabase (PostgreSQL con RLS)
- AI: OpenAI GPT-4o-mini per classificazione
- Deploy: Railway
- Worker asincrono: queue processor per Invoicetronic (SDI automatico)
- Auth: Argon2id, sessioni Streamlit

### Architettura file
```text
app.py                          <- dashboard principale / analisi fatture
pages/                          <- pagine secondarie Streamlit
  └── [N_nome_pagina].py
services/
  ├── invoice_service.py        <- parsing XML/P7M/PDF/Vision
  ├── upload_handler.py         <- orchestrazione upload
  ├── db_service.py             <- query, cache, invalidazione
  ├── notification_service.py   <- notifiche in-app
  └── ai_service.py             <- classificazione AI
utils/
  ├── app_controllers.py        <- controller UI
  ├── sidebar_helper.py         <- sidebar condivisa
  └── ui_helpers.py             <- helper CSS/UI
worker/
  └── queue_processor.py        <- elaborazione asincrona SDI
migrations/
  └── [NNN_nome].sql            <- sequenziali, numerate
tests/
  └── test_*.py                 <- pytest, Supabase locale
config/
  └── logger_setup.py
static/
  └── layout.css
```

### Regole architetturali invarianti
1. La tabella `fatture` contiene righe articolo, non testate documento
2. RLS attiva su tutte le tabelle user-facing, accesso via `service_role`
3. Ogni dato e isolato per `user_id` + `ristorante_id`
4. `st.session_state` e condiviso tra pagine: usare prefissi namespace dedicati per ogni feature
5. `st.cache_data` e keyed per parametri: includere sempre `user_id` e `ristorante_id`
6. Pattern `cache_version` (migration 068) per invalidazione cross-process
7. Upload manuale e worker Invoicetronic convergono sulla stessa pipeline parser
8. Soft delete via campo `deleted_at` (non DELETE fisico)
9. Migrations numerate sequenzialmente, mai saltare numeri
10. Test con Supabase locale reale (localhost:54321), nessun mock

### Vincoli UX invarianti
1. La pagina Analisi Fatture (app.py) e puramente analitica, non gestionale
2. Il pattern navigazione dashboard usa bottoni + `st.session_state.sezione_attiva`, non `st.tabs`
3. `patch_streamlit_width_api()` sempre come prima istruzione in ogni pagina
4. `st.set_page_config()` sempre prima di qualsiasi `st.` call
5. Autenticazione verificata all'inizio di ogni pagina con redirect a `app.py` se non loggato
6. Reset completo stato e cache al cambio ristorante

***

## PARTE 11 - CHECKLIST FINALE PRE-IMPLEMENTAZIONE

Prima di emettere `✅ PIANO APPROVATO`, Opus verifica questa checklist:

### Database
- [ ] Tutte le tabelle nuove hanno RLS abilitata
- [ ] Tutte le tabelle nuove hanno indici per `user_id`, `ristorante_id`, `deleted_at`
- [ ] I trigger sono definiti nell'ordine corretto (funzione prima, trigger dopo)
- [ ] Le migrations sono numerate in sequenza senza salti
- [ ] Il backfill per dati storici e previsto e non inventa dati inesistenti
- [ ] GDPR: nuove tabelle incluse in export e delete cascade

### Codice applicativo
- [ ] Nessun file esistente viene modificato senza motivo documentato
- [ ] Dead code identificato e pianificato per eliminazione
- [ ] Nuovi servizi seguono il pattern `db_service.py` (cache + try/except + logger)
- [ ] Nuove chiavi session_state usano prefisso namespace dedicato
- [ ] Reset nuove chiavi session_state incluso nel callback cambio ristorante
- [ ] Nessuna firma di funzione esistente modificata senza necessita

### Regole di business
- [ ] Gerarchia priorita scadenza documentata e non ambigua
- [ ] Tutti i tipi documento edge case coperti
- [ ] Comportamento in caso di errore documentato (blocca vs warn vs silenzio)
- [ ] Multi-tenant verificato su ogni nuova query

### Test
- [ ] Suite test per ogni nuovo servizio pianificata
- [ ] Test per regole di business critiche (priorita, gerarchia, calcoli)
- [ ] Test di non-regressione su funzionalita esistenti
- [ ] Infrastruttura test esistente riutilizzabile senza modifiche strutturali

### Sincronizzazione
- [ ] Strategia `cache_version` definita per ogni nuova entita
- [ ] Ciclo di polling version definito nel render delle nuove sezioni
- [ ] `clear_*_cache()` chiamato nei punti corretti (dopo write, al cambio ristorante)
- [ ] Nessuna race condition tra worker e modifica manuale

***

*Fine documento - versione 1.0*
