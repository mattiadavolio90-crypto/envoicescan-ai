# Stato audit ONEFLUX — ciclo 2026-09

> **A cosa serve questo file.** Dice **cosa è fatto e cosa manca**, e nient'altro.
> Si legge in un minuto. Il dettaglio di ogni sessione sta nei verbali
> (`AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`); il conto delle righe coperte sta in
> `AUDIT_COPERTURA.md`. Se una di queste tre cose finisce nelle altre due, tutte
> e tre diventano illeggibili — è già successo.

**Ciclo aperto il 29/08/2026, tuttora in corso. Stato aggiornato al 03/09/2026.**
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
| 01→02/09 | **Categorizzazione** — fasi 0, 7, 1, 2, 3 | 🟠 **parziale: 5 fasi su 10** — vedi §2 |

**Il metodo che ha retto:** ogni sessione ha ri-misurato le ipotesi del proprio
prompt prima di crederci, e **in 5 casi su 10 il prompt aveva torto**. La misura
prima del lavoro è la pratica che ha prodotto più valore di tutto il ciclo.

---

## 2. Cosa è aperto

### Lavoro in corso

| Cosa | Stato |
|---|---|
| **Note di credito col segno sbagliato** | Codice fatto e committato. Restano **10 righe da correggere a DB**. ⚠️ **In esecuzione in un'altra sessione (02/09)** — non toccare |
| **Categorizzazione** — fasi 4, 4bis, 5, 6, 8 | 5 fasi aperte su 10, più 2 voci emerse strada facendo. Piano in `docs/piani/PIANO_CATEGORIZZAZIONE.md` |

La fase 4 (esclusione dai margini, 19 RPC) è la più pesante e la più delicata:
tocca il MOL su tutto lo storico, dietro un flag disattivato, e il delta per sede
va misurato e portato a Mattia **prima** di attivarlo.

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
| **1** | **Quadratura dei numeri fra le pagine** — prendere 3 clienti veri e verificare che lo stesso dato torni in ogni schermata dove compare | 🔴 **Non è un audit di codice, è la verifica che nessuno ha mai fatto.** Il prompt esiste da agosto (`docs/storico/..._COERENZA_NUMERI.md`) e non è mai stato eseguito. Nasce dall'unico difetto trovato **dal cliente prima che dall'audit** (F&B e Spese Generali che non tornavano). È ciò che difende la reputazione, non la qualità del codice |
| **2** | **I prompt AI** — `config/`, 2.379 righe, mai guardate | È il cuore del prodotto e la **regola di dominio n.1**. Un difetto qui non colpisce un cliente: li colpisce tutti insieme, in silenzio. Ha già dato un problema (il prompt contraddiceva la regola, ciclo 08) |
| **3** | **Categorizzazione, fasi 4→8** — 5 fasi su 10 aperte | Lavoro già iniziato e fermo a metà: rientra nel principio «niente parziali». La fase 4 tocca il MOL su tutto lo storico, dietro flag: il delta per sede si misura e si porta a Mattia **prima** di attivarlo |
| **4** | **Il briefing giornaliero** — `daily_briefing_service.py`, 1.637 righe | È **la prima cosa che il cliente legge ogni mattina**. Quattro sessioni di lavoro a settembre, mai auditato come oggetto proprio |
| **5** | **Il worker notturno** — `worker/`, 2.400 righe | **Gira non presidiato** e non è in nessuna lista. Se sbaglia di notte, se ne accorge il cliente al mattino |
| **6** | **I router del worker** — 16.514 righe, ~4.000 lette | Il blocco più grande a copertura parziale. Da affrontare per router, non in blocco |

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
