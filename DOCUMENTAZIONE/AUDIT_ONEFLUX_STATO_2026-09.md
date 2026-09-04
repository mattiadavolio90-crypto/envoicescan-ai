# Stato audit ONEFLUX — ciclo 2026-09

> **A cosa serve questo file.** Dice **cosa è fatto e cosa manca**, e nient'altro.
> Si legge in un minuto. Il dettaglio di ogni sessione sta nei verbali
> (`AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`); il conto delle righe coperte sta in
> `AUDIT_COPERTURA.md`. Se una di queste tre cose finisce nelle altre due, tutte
> e tre diventano illeggibili — è già successo.

**Ciclo aperto il 29/08/2026, tuttora in corso. Stato aggiornato al 04/09/2026.**
I cicli 2026-07 e 2026-08 sono chiusi e archiviati in `docs/storico/`.

> ⚠️ **Rinominato il 02/09/2026.** Si chiamava `..._2026-08-29.md` e faceva
> credere di essere «il lavoro di agosto», mentre agosto era chiuso da giorni.
> Il ciclo vivo è di settembre.

---

## 1. Cosa è chiuso

Una riga per sessione. Il dettaglio è nel verbale, in coda per data.

| Data | Dimensione | Verdetto |
|---|---|---|
| 30/08 | **Route API** (170 route Next) | ✅ chiusa — le 3 ipotesi di partenza erano tutte false; il layer è un proxy trasparente, l'autorizzazione vive nel worker |
| 31/08 | **Voci ereditate** (3) | ✅ chiusa — 2 su 3 erano false alla ri-misura |
| 31/08 | **Scadenziario** | ✅ chiusa — filtri, ordinamento e stato estratti in `lib/`, 15/15 mutanti |
| 31/08 | **`(app)/margini/`** — il MOL | ✅ chiusa — 183 test, 65/65 mutanti |
| 01→03/09 | **`(app)/catena/`** (3 passate + R3 + pct) | ✅ **100%** — 326 test; `card-segnali.tsx` è esclusione motivata. Le 77 righe di `fatture/` lette il 3/9: nessun difetto proprio, ma ci è stato trovato R10 (pattern condiviso, non di catena) |
| 01/09 | **Bug importi italiani** | ✅ corretti — erano in **60 punti**, non ~25; fonte unica in `lib/format.ts` |
| 01/09 | **`(app)/dashboard/`** — logica in `lib/` | ✅ 1ª passata — 92 test, 39 mutanti / 38 uccisi |
| 02/09 | **`(app)/impostazioni/`** — logica in `lib/` | ✅ 1ª passata — 22 test, 12/12 mutanti |
| 02/09 | **`(app)/notifiche/`** | ✅ chiusa — 23 test; corretto un difetto **visibile al cliente** (notifica senza pulsante) |
| 03/09 | **R5 — un endpoint nuovo non può nascere aperto** | ✅ chiuso — `dependencies` su tutti e 12 i router. Non chiudeva una falla (**216 endpoint su 216 già protetti**, ri-verificato): è la rete perché il 217° non nasca scoperto. **95 rotte confrontate prima/dopo: 0 differenze** |
| 03/09 | **R6 + R11 — il filtro «Da Classificare», Python e SQL** | ✅ chiuso — la regola «le righe non classificate restano fuori dal MOL» viene da un posto solo in Python (7 punti) e le **7 RPC vive** (misurate su `pg_proc`, non sui file) sono **legate a quella costante da un test**: se le due sponde divergono, la suite diventa rossa. **Nessuna migration** e nessuna migration riscritta |
| 03/09 | **R10 — il guasto non è più un «niente da fare»** | ✅ chiuso — **7 pagine cliente** (scadenziario PV + catena, avvisi desktop + mobile, tag, analisi-fatture). `workerGet` torna `null` su ogni fallimento e i `?? []` lo trasformavano in lista vuota: **4,4 M€ di scadenze** potevano diventare «Nessun documento trovato». Fonte unica in `lib/esito-caricamento.ts`, 41 test, **10/10 mutanti** (2 li ha trovati il code-reviewer) |
| 03/09 | **Residui R8, R2, R3, R1, R7, R4** | ✅ **6 su 6 chiusi** — corretto il netto mobile (euro sbagliati). Su R4 Mattia ha scelto: separatore delle migliaia e decimali arrotondati. Le 3 `pct` chiuse il 3/9: `formatPct` non aveva più chiamanti, correggerla non ha toccato nessuna schermata |
| 01→03/09 | **Categorizzazione** — fasi 0, 7, 1, 2, 3 + **4, 4bis, 5, 6, 8 (3/9 sera)** | ✅ **le 10 fasi del piano sono chiuse** (voce §3 #3) — Fase 4 dietro flag SPENTO (7 RPC vive, non 19; migration `20260903210000` **da applicare col via di Mattia**; delta oggi 0 su 11 sedi); 4bis card in Home (non vista nel browser); 5 apprendimento unificato (+319 correzioni `User` ora protette); 6 bypass solo con conferma (378 voci→hint; **153 conflitti a Mattia**); 8 refusi corti + ground truth (D7 ridimensionato dalla misura: 0,4 €/mese). Ogni fase: mutanti provati. Restano nel piano: NUOVO 1-2 (fuori dall'ordine deciso da Mattia) e le sue decisioni. Dettaglio: `docs/piani/PIANO_CATEGORIZZAZIONE.md` |
| 03/09 | **Quadratura dei numeri fra le pagine** (voce §3 #1) | ✅ **eseguita** (read-only) — la prima verifica sui dati veri: riparto in partita doppia **18/18 al centesimo**, Analisi Fatture↔Margini al centesimo, sincronia ricavi SUSHILAND perfetta. Trovati: 1 bug (segnale «margine in calo» mai scattato per le catene), 1 decisione di prodotto (food cost ÷lordo vs ÷netto, colore ribaltato in 3 mesi su 7), 1 rischio strutturale (snapshot `margini_mensili`). 3 finding del ciclo 07 risultati già superati. Esiti aperti: **Q1–Q4 in §2**; report in `scratchpad/coerenza_numeri_report.md` |
| 03-04/09 | **Sessione «tutte le voci del piano»** — riassunto | ✅ verbalizzata nello storico e in `DOCUMENTAZIONE/AUDIT_CON_FABLE.md` (lo storico delle sessioni Fable): 6 voci percorse in una sessione, 14 commit, suite piena 12.908 verdi, review sul cumulativo verde. Restano a Mattia: push, migration+flag Fase 4, 153 conflitti memoria, Q1–Q4, passate router |
| 03/09 | **Router — 1ª passata: scadenziario** (voce §3 #6) | 🟠 voce a programma (per router, come da roadmap) — **prima passata chiusa: le scadenze tornano a parlare.** `/api/scadenziario/notifica` era MUTO da giugno (upsert su un vincolo unico che non esiste + topic sconosciuto al briefing): **300 fatture scadute / 4,4 M€ senza mai un avviso**. Riscritto sulla factory ufficiale coi 2 topic canonici, payload che il briefing sa raccontare, spegnimento a condizione rientrata, formato italiano. 5 test, 3/3 mutanti. Report: `scratchpad/audit_router_scadenziario_report.md` |
| 03/09 | **Il worker asincrono** (`worker/`, voce §3 #5) | ✅ chiusa — 2.403 righe lette integralmente. «Gira non presidiato» era falso: è tra i moduli più difesi (claim atomico, watchdog, SSRF whitelist, purge GDPR, degradi dichiarati a ERROR). Code in salute: 647 fatture done con retry funzionanti, 0 arretrati. Chiuso 1 latente: il retry della coda email non poteva scrivere (`now() + interval` come stringa → cast rifiutato, misurato). **Trovato per strada e girato alla voce #6: le notifiche scadenze sono mute da giugno** (upsert su vincolo inesistente + topic sconosciuto al briefing), con 300 scadute / 4,4 M€ mai avvisate. Report: `scratchpad/audit_worker_report.md` |
| 03/09 | **Il briefing giornaliero** (`daily_briefing_service.py`, voce §3 #4) | ✅ chiusa — 1.637 righe lette integralmente. L'impianto regge: pipeline deterministica, AI solo per il tono, **validazione della narrativa che in produzione tiene** (0 violazioni su 24 snapshot — due rilievi in memoria risultati invecchiati, incluse le «6 soglie sbagliate» di LOGICA_BRIEFING: le 11 leve ri-misurate combaciano tutte). Chiusi in sessione (bump v21): importi delle scadenze in **formato inglese** nei bullet (latente: 0 bullet scadenze in cache) e validatore esteso all'**entusiasmo vietato** dal prompt. 3 mutanti / 3 uccisi. ⚠️ Trovato per strada: **le notifiche scadenza non vengono generate dall'1/6** — è del generatore (voce #5/#6), annotato nel report. Report: `scratchpad/audit_briefing_report.md` |
| 03/09 | **I prompt AI** (`config/`, voce §3 #2) | ✅ chiusa — coerenza prompt↔costanti↔DB piena (29 categorie, 1.268 chiavi validate, **zero categorie estranee in produzione**); la contraddizione interna del prompt («rispondi Da Classificare» vs «classifica sempre») è **neutralizzata dal gate nel codice su entrambi i percorsi**, verificato a DB. Chiuso un difetto: **12 chiavi del dizionario erano mojibake** e non potevano matchare nulla — riparate + 5 gemelli senza accento, presidio comportamentale, **3 mutanti / 3 uccisi**. Impatto vivo misurato ~1 riga (le fatture XML non hanno accenti); l'innesco vero era il futuro percorso PDF/Vision. Report: `scratchpad/audit_prompt_ai_report.md` |

**Il metodo che ha retto:** ogni sessione ha ri-misurato le ipotesi del proprio
prompt prima di crederci, e **in 5 casi su 10 il prompt aveva torto**. La misura
prima del lavoro è la pratica che ha prodotto più valore di tutto il ciclo.

---

## 2. Cosa è aperto

### Lavoro in corso

| Cosa | Stato |
|---|---|
| **Note di credito col segno sbagliato** | Codice fatto e committato. Restano **10 righe da correggere a DB**. ⚠️ **In esecuzione in un'altra sessione (02/09)** — non toccare |
| **Categorizzazione** — code di piano | Le 10 fasi sono chiuse (3/9 sera, vedi §1). In coda: **2 voci NUOVO** (guardrail IVA, RPC per la GUC del log) fuori dall'ordine deciso da Mattia, e **3 cose sue**: applicare la migration Fase 4 + attivazione flag; i **153 conflitti** memoria utente↔globale; le righe storiche da ricategorizzare. Piano in `docs/piani/PIANO_CATEGORIZZAZIONE.md` |

### Residui — la roadmap, chiusa il 03/09

> **Regola di Mattia (03/09/2026): i residui si chiudono TUTTI prima di aprire
> una zona nuova.** Niente parziali che si accumulano. Questa tabella è l'ordine
> di lavoro, non un elenco: si scende dall'alto e si depenna.
>
> **Perché questa sezione esiste.** Ogni verbale dichiara cosa *non* ha fatto, in
> una sezione «Non fatto, e dichiarato» — ce ne sono 6. Ma quei residui non
> risalivano da nessuna parte: restavano dentro verbali che nessuno riapre,
> mentre qui sopra si leggeva «chiusa ✅».
>
> **Ri-verificati sul codice il 03/09/2026, e due cose sono cambiate rispetto a
> come i verbali le raccontavano** — le misure, non le citazioni:
> - **R5 non è la falla che sembrava**: tutti i **216 endpoint** hanno già una
>   protezione esplicita (`Depends` in firma o `dependencies` nel decoratore),
>   **zero scoperti**. È un rischio *strutturale* (un endpoint nuovo nascerebbe
>   aperto), non un buco attivo. Declassato di priorità.
> - **R4 è più grande del dichiarato**: i formattatori duplicati sono **12, non
>   7**, e su **5 file** (non 4). I verbali cercavano `const`, ma sono `function`.
>
> **Sessione del 03/09 — 5 residui chiusi su 6 affrontati.** Altre tre cifre non
> hanno retto alla ri-misura, e vale la pena saperlo prima di fidarsi delle
> altre:
> - **R8 era già in produzione** dal commit `71ac3ab`, cioè dalla stessa passata
>   che lo dichiarava aperto: copiato dal «non fatto» di un verbale senza
>   riguardare il codice;
> - **R7 non erano 4 letterali ma 29** (`grep -c` conta le righe, non le
>   occorrenze: molte righe ne portano due);
> - **R1 non era teorico**: gli incassi a DB ci sono già (1.049 righe, 6 sedi).

**La tabella dei residui è vuota: R1-R11 sono tutti chiusi** (03/09), incluse
le 3 `pct` e le 77 righe di `catena/fatture/`. Vedi i verbali nello storico.

### Aperti dalla verifica di quadratura — 03/09 (Q1–Q4)

> Esito della voce §3 #1, eseguita il 03/09 (verbale nello storico; report completo
> in `scratchpad/coerenza_numeri_report.md`). Remediation e decisioni in sessioni
> separate, nell'ordine qui sotto.

| # | Cosa | Natura |
|---|---|---|
| **Q1** | Il segnale «margine in calo» della catena non è mai potuto scattare: legge lo snapshot `mol_perc` + gate `fatturato_netto > 0` di `margini_mensili`, mai valorizzati per le sedi delle due catene reali (OFFSIDE: netto 0 su tutti i mesi; OVERTIME e 3 SUSHILAND: `mol_perc` 0,00 ovunque). Blocco «Segnale 1» in `services/routers/gruppo.py`. La stessa classe di bug è già corretta in 3 percorsi fratelli (`_aggrega_sedi_mensili`, `_applica_override_netto`, segnale «ricavi mancanti») | **Bug** — fix |
| **Q2** | Food cost con due definizioni convivono: ÷lordo (Home, catena, briefing) vs ÷netto (pagina Margini) — 2,2–3,6 punti di scarto misurati su 14 mesi, colore ribaltato in 3 mesi su 7 per OFFSIDE alla soglia 38%. Il codice stesso la dichiara «decisione di prodotto» da prendere sui tre punti insieme | **Decisione di Mattia** |
| **Q3** | Snapshot economico di `margini_mensili` incoerente per costruzione: 3 scrittori (pagina Margini scrive tutto; trigger ricavi solo il fatturato; RPC `riparto_quote_mensili` ricalcola il MOL cieca all'override e non scrive mai le pct). Misurato: OVERTIME febbraio MOL fotografato +50.834 € vs +28.398 € vero. Oggi letto solo da Q1 e dall'endpoint senza consumatori `/api/margini/analisi-centri`: serve un presidio perché nessun lettore nuovo lo erediti | **Strutturale** |
| **Q4** | Tab Calcolo vs tab Analisi (pagina Margini): le quote riparto includono le righe «Da Classificare» della sede tecnica (deliberato — `supabase/migrations/20260724220000_riparto_quote_per_categoria.sql`), la proiezione per centro le esclude (deliberato — regola di dominio 1). Scarto misurato 13–592 €/mese. Due regole giuste in conflitto: scegliere una rappresentazione | **Decisione di Mattia** |

**R9 — chiuso il 03/09.** Il registro sessioni non usa più il PID:
`os.getppid()` in un hook è il wrapper che muore subito, e ri-misurando si
vedeva **il PID già morto con la sessione ancora attiva**. La doc ufficiale
degli hook conferma che nel payload **non esiste** nessun identificativo di
processo, quindi la vivacità è passata a `session_id` + scadenza rinfrescata
(nuovo `scripts/_registro_sessioni.py`, che unifica **3 copie** di `_pid_vivo`
— `pulisci_branch.py` era il terzo consumatore, fuori dal prompt originale).
Effetto: il fix del 03/09 al gate di review ora funziona invece di degradare
al merge-base. 19 test, 12/12 mutanti. Il fix stesso stava per introdurne due
peggiori, corretti prima di chiudere: il refresh concorrente azzerava il
registro (0 entry su 5), e la ri-registrazione disarmava la guardia sul commit.
Trovato per strada anche un difetto **pre-esistente**: quella guardia non
girava mai se nessun'altra sessione era viva.

> **Due ipotesi della roadmap non hanno retto alla misura**, ed è il motivo per
> cui R5 e R6 erano rimasti in fondo alla lista:
> - **R5 non richiedeva una sessione propria.** Il timore era «tocca tutto il
>   traffico»: misurato, `dependencies` a livello di router è **additivo**, non
>   sostitutivo (FastAPI esegue prima quella del router, poi quella
>   dell'endpoint), quindi `_verify_admin` resta più stretto dov'era. 95 rotte
>   confrontate prima/dopo: **0 differenze**.
> - **R6 non richiedeva nessuna migration.** Era dato per «migration su 7 account
>   veri»: la sostituzione è `'Da Classificare'` → `CATEGORIA_NON_CLASSIFICATA`,
>   cioè **la stessa stringa**. Nessun dato cambia. Ed erano **7 copie, non 9**.

**Fotografato di proposito, NON è un residuo.** Le **8 anomalie di `catena/`**
(`ordinaRighe` coi null, `tintConti` che sceglie l'ipotesi ottimista,
`incidenzaPct` che mostra «0,0%» dove il dato non esiste, le due heatmap
divergenti, le `euro2` omonime…) sono **decisioni di Mattia**: ognuna ha già un
test che la asserisce *sbagliata*, col perché nel corpo. Elenco nel verbale
dell'1/9, §«Otto comportamenti fotografati». Si riaprono se Mattia lo decide, non
si chiudono in coda a una sessione. Stessa natura: `daysToCestino` e
`DocumentoRow.isOverdue` (label e decorazione, non decidono inclusioni né
importi) e il mutante sul locale `"it"`.

**Chiuso e depennato:** `parseImportoIt` con `replace` non globale — risolto da
un'altra sessione senza che nessuno lo registrasse. **R8** (guardia sulle liste
vuote di `config-assistente-catena`) — era **già implementata** dal commit
`71ac3ab`, cioè dalla stessa 3ª passata che la dichiarava aperta: il residuo era
stato copiato dal «non fatto» del verbale senza ri-guardare il codice. Il 03/09
la guardia è stata provata per mutazione (3 mutanti, 3 uccisi) e legata da
`tests/test_catena_config_guardia_salva.py`. *La lista invecchia in
entrambe le direzioni: si ri-verifica, non si eredita.*

**Chiuso prima ancora di entrare in lista — il MEDIUM catena-tag.** Il prompt di
quadratura di agosto (`docs/storico/..._COERENZA_NUMERI.md` §E) lo dichiarava
aperto a **236,23 €** di note di credito non scalate sul percorso catena, e da lì
è stato ricopiato due volte come lavoro da fare. **Era già chiuso dal 27/8**:
la migration `20260827230000_gruppo_tag_note_credito.sql` è stata applicata poche
ore dopo la scrittura di quel prompt, che nessuno ha aggiornato. Verificato a DB
il **03/09** chiamando la RPC vera `gruppo_tag_analisi`: LAND DEI SAPORI mostra
245.518,38 € (il valore non corretto sarebbe 245.764,83 €), Villa Guardia
103.821,61 € contro 103.860,66 €. Due dettagli che la citazione aveva perso: le
RPC erano **4, non 6**, e al momento del fix la divergenza era **285,50 € su 7
righe**, non 236,23 € su 3 — nel frattempo erano arrivate altre note di credito.
*Un prompt archiviato invecchia come un verbale: se una sessione lo usa come
fonte, va ri-misurato prima, non citato.* Distinto dal fix sul **segno** delle
note di credito (`089b671`, 2/9), anch'esso chiuso e verificato: 140 TD04 a DB,
zero col netto positivo.

**Esclusioni motivate — non sono residui.** Il **rendering React** (~4.300 righe
in margini, e ovunque) non è coperto e non lo sarà: servirebbe un runner di
componenti in `apps/web/`, e `deploy-vercel.yml` scatta su `apps/web/**` — ogni
merge di un test farebbe partire un deploy di produzione. Scelta strutturale
dichiarata, non una svista. Vale lo stesso per le aree 🟠 del contatore: il
perimetro escluso è stato **misurato e motivato**.

---

## 3. Cosa manca — l'ordine di lavoro dopo i residui

> **Vincolo (Mattia, 03/09/2026): non si apre nulla di questa sezione finché la
> §2 non è vuota.** Una zona nuova aperta con residui in sospeso è come sono nate
> le sei sessioni disallineate di settembre.

Il conto delle righe sta in `AUDIT_COPERTURA.md`. Qui c'è l'ordine, deciso per
**importanza per il cliente**, non per dimensione del file.

| # | Cosa | Perché in questa posizione |
|---|---|---|
| **1** | **Quadratura dei numeri fra le pagine** — prendere 3 clienti veri e verificare che lo stesso dato torni in ogni schermata dove compare | ✅ **Eseguita il 03/09** (catena OFFSIDE completa, SUSHILAND ×3, LAND, TIME CAFE — read-only, tutto ri-misurato a DB). Le quadrature fondamentali tornano al centesimo; gli esiti aperti sono **Q1–Q4 in §2**. Report: `scratchpad/coerenza_numeri_report.md` |
| **2** | **I prompt AI** — `config/` (2.389 righe misurate all'apertura) | ✅ **Chiusa il 03/09** — coerenza piena, la contraddizione interna del prompt è neutralizzata dal gate nel codice (verificato a DB); chiuso il difetto delle 12 chiavi mojibake del dizionario con presidio (3/3 mutanti). Report: `scratchpad/audit_prompt_ai_report.md` |
| **3** | **Categorizzazione, fasi 4→8** | ✅ **Chiuse il 03/09 sera** (4, 4bis, 5, 6, 8 — dettaglio in §1). La Fase 4 è dietro flag spento: migration da applicare e attivazione = decisione di Mattia, delta ri-misurato al flip |
| **4** | **Il briefing giornaliero** — `daily_briefing_service.py` | ✅ **Chiusa il 03/09 sera** — letto integrale, 2 fix (formato scadenze, validatore tono), 2 rilievi di memoria invecchiati. Report: `scratchpad/audit_briefing_report.md` |
| **5** | **Il worker asincrono** — `worker/` | ✅ **Chiusa il 03/09 sera** — letto integrale: la premessa «non presidiato» era falsa, 1 latente chiuso (retry coda email). Report: `scratchpad/audit_worker_report.md` |
| **6** | **I router del worker** — 16.617 righe misurate, ~4.000 lette | 🟠 **A programma, per router** (mai in blocco). 1ª passata chiusa il 03/09: scadenziario (le notifiche scadenze erano mute da giugno — fix + presidio). Ordine delle prossime, per rischio cliente: margini/gruppo (lettura integrale), fatture, ricavi, riparto, poi gli altri. Report: `scratchpad/audit_router_scadenziario_report.md` |

Restano fuori, per misura e non per dimenticanza: `agenda/` (**0 turni a DB**),
`assistenza/` (`marketplace_leads` 0 righe), `style-guide/` (pagina interna).
**Il criterio per scegliere un'area resta: conta le righe a DB delle tabelle che
serve, poi decidi.** È così che l'agenda è stata scartata e `notifiche/` scelta —
dove è stato poi trovato un difetto che il cliente vedeva.

---

## 4. Come si lavora a questo ciclo

Il metodo sta in `WORKFLOW.md` e non si duplica qui — se una regola di processo
vive solo dentro questo file, sparisce quando il ciclo viene archiviato. I quattro
punti che hanno morso più spesso:

1. **Ogni cifra si ri-misura al momento di scriverla.** Violato 8 volte in 5
   giorni. Una cifra ripresa da un documento non è una cifra misurata.
2. **Accettare una correzione non è verificarla.** Due persone che non hanno
   misurato rendono definitiva una cifra sbagliata.
3. **Un mock generoso è un test che mente.** 6 test verdi per mesi su una query
   che filtrava una colonna inesistente.
4. **`tsc` non esegue niente.** Passa anche su un pulsante che punta alla pagina
   sbagliata.
