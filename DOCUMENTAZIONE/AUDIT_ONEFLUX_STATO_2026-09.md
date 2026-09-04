# Stato audit ONEFLUX — ciclo 2026-09

> **A cosa serve questo file.** Dice **cosa è fatto e cosa manca**, e nient'altro.
> Si legge in un minuto. Il dettaglio di ogni sessione sta nei verbali
> (`AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`); il conto delle righe coperte sta in
> `AUDIT_COPERTURA.md`. Se una di queste tre cose finisce nelle altre due, tutte
> e tre diventano illeggibili — è già successo.

**Ciclo aperto il 29/08/2026, tuttora in corso. Stato aggiornato al 04/09/2026 (sera).**
I cicli 2026-07 e 2026-08 sono chiusi e archiviati in `docs/storico/`.

> ⚠️ **Rinominato il 02/09/2026.** Si chiamava `..._2026-08-29.md` e faceva
> credere di essere «il lavoro di agosto», mentre agosto era chiuso da giorni.
> Il ciclo vivo è di settembre.

---

## 0. I prossimi passi — in ordine

> Ri-misurato il **04/09/2026 sera**, dopo il deploy di `a5e77f1`. Copertura app:
> **69%** (backend 84%, frontend 51%, edge 100%) — dettaglio in
> [`AUDIT_COPERTURA.md`](AUDIT_COPERTURA.md).

| # | Cosa | Di chi è | Perché adesso |
|---|---|---|---|
| ~~1~~ | ~~**Q2** — food cost ÷lordo vs ÷netto~~ | ✅ **CHIUSO il 04/09** | Decisione di Mattia: **il food cost è SEMPRE sul netto**. Home e Catena allineate (erano gli unici due punti sul lordo: il briefing non lo calcola, riceve il numero già fatto) |
| **2** | **Q4** — quote riparto vs proiezione per centro | **Decisione di Mattia** | Due regole giuste in conflitto: serve scegliere quale rappresentazione mostrare |
| **3** | **Flag Fase 4** (migration `20260903210000` **già applicata**, verificata su `pg_proc` il 04/09: 7 RPC su 7 hanno `p_escludi_da_verificare`) | **Mattia** (lasciato da Fable) | ⚠️ **Il «delta zero su 11 sedi» NON vale più.** Ri-misurato il 04/09 sera: **340 righe classificate-ma-dubbie su 10 sedi**, per **26.453 €** che uscirebbero dai margini — quasi tutti su due sedi (SUSHILAND VILLA GUARDIA 13.704 €, SAN GIULIANO 12.612 €). Accendere il flag oggi **cambierebbe il MOL di clienti veri**: la misura va rifatta al momento di decidere, non ereditata |
| **4** | **`utils/` + altri moduli `services/`** — 9.345 righe | Lavoro tecnico | **Le uniche due zone MAI guardate del backend** (riparto, foodcost, price_impact, radar). È la prossima dimensione naturale |
| **5** | **Q3** — snapshot `margini_mensili`, 3 scrittori | Lavoro tecnico | Meno urgente di prima: chiuso Q1, `mol_perc` **non ha più alcun lettore runtime**. Da «serve un presidio» a «colonna morta da valutare» |
| **6** | **Ripasso #3 categorizzazione e #6 router** | Lavoro tecnico | Coperte da Fable, ma #3 tocca la regola di dominio #1 e #6 ha visto **1 router su molti** |

**Non da rifare:** prompt AI (#2), briefing (#4), worker (#5) — chiusi dalla
sessione Fable con presidio provato per mutazione. Dettaglio e criterio in
[`AUDIT_COPERTURA.md`](AUDIT_COPERTURA.md) §«Cosa ha coperto la sessione Fable».

**Rilievo di prodotto aperto** (non tecnico): il testo del segnale «margine in
calo» non dice **di quale mese** parla, e col gate di completezza può riferirsi a
2-3 mesi fa. Rimedio minimo: «Margine di giugno al 39%…».

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
| 04/09 | **Q1 — il segnale «margine in calo»** (esito quadratura) | ✅ **chiuso** — non era mai potuto scattare per nessun cliente: leggeva lo snapshot `mol_perc`, che per le sedi di catena non è valorizzato. Ora calcola il MOL con la formula viva e un **gate di completezza per mese** (senza, i mesi con fatture non ancora arrivate uscivano al 100% e facevano scattare crolli inventati). Da **0 sedi servite** a **4 accensioni su 6**. Tolta l'eccezione nella guardia di dominio. **9 mutanti / 9 uccisi**. Ri-misurata la roadmap §3: **5 voci su 6 erano già coperte dalla sessione Fable** ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md)) e il ciclo le dava ancora per aperte — colonna «Copertura reale» e contatore allineati |
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
| **Categorizzazione** — fasi 4, 4bis, 5, 6, 8 | ✅ **Chiuse fuori ciclo** il 03-04/09 (**sessione Fable**, [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §3, `e36dfcd`→`8dd7a2e`), ognuna con test dedicati: 10 fasi su 10. Piano in `docs/piani/PIANO_CATEGORIZZAZIONE.md` (registra fino alla 4bis: le fasi 5, 6, 8 stanno nei commit). ⚠️ **Resta a carico di Mattia**: decidere se accendere il flag (la migration `20260903210000` **risulta già applicata al DB** — verificata su `pg_proc` il 04/09, 7 RPC su 7) `ESCLUDI_DA_VERIFICARE_DAI_MARGINI` (oggi `False`; il «delta zero» del 03/09 **non vale più**: 04/09 sera = 340 righe su 10 sedi, 26.453 €) |

La fase 4 (esclusione dai margini) è la più pesante e la più delicata: tocca il
MOL su tutto lo storico, dietro un flag disattivato, e il delta per sede va
misurato e portato a Mattia **prima** di attivarlo. **Le RPC vive erano 7, non
19** (ri-misurate su `pg_proc`, non contate sui file migration): la cifra vecchia
era un conteggio sui file, non sul DB.

### Residui aperti — la roadmap di chiusura

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

| # | Residuo | Sforzo | Perché in questa posizione |
|---|---|---|---|
| **R9** | ✅ **CHIUSO** — `claude_hook_registra_sessione.py` non usa più `os.getppid()`. Verificato il 04/09: commit `c8ec158`, già su `origin/main`; nel sorgente non c'è più alcuna occorrenza di `getppid`. La riga restava aperta per inerzia | — | Chiuso il 03/09 |

### Aperti dalla verifica di quadratura — 03/09 (Q1–Q4)

> Esito della voce §3 #1, eseguita il 03/09 sui dati veri (report completo in
> `scratchpad/coerenza_numeri_report.md`). Le quadrature fondamentali tornano al
> centesimo; questi sono i quattro esiti che restano. Remediation e decisioni in
> sessioni separate.

| # | Cosa | Natura |
|---|---|---|
| **Q1** | ✅ **CHIUSO il 04/09.** Il segnale «margine in calo» non è mai potuto scattare per nessun cliente: leggeva due colonne **snapshot** di `margini_mensili` (gate `fatturato_netto > 0` e valore `mol_perc`), non valorizzate per le sedi di catena. **Fix**: il MOL si calcola con la formula viva (`_aggrega_sedi_mensili`), la stessa di overview e margini-coperti, con costi F&B **live** dalle fatture e override dei ricavi mensili. Un mese entra nel confronto **solo se completo** (ricavi + costi + personale): senza quel gate i mesi con fatture non ancora arrivate uscivano al **100%** e il segnale confrontava margini inventati. Ri-misurato sui dati veri: da **0 sedi servite** a **4 accensioni su 6 sedi** di catena, testi sensati, le 2 sedi in salute restano mute. Rimossa l'eccezione `_calcola_segnali` da `test_regole_dominio_guardia.py` (il debito che la giustificava non esiste più). Aggiunta anche la guardia `segnali_off` sul blocco (gli altri segnali ce l'hanno): **non era un bug visibile** — un filtro finale rimuoveva già dall'output i segnali disattivati — ma evita di calcolarli per poi buttarli. Presidio: `tests/test_gruppo_segnale_margine_calo.py` (12 test), **9 mutanti / 9 uccisi**, misurati **uno alla volta**. La cifra e' stata corretta **quattro volte** prima di reggere, sempre dal `code-reviewer`: (1) un mutante era inefficace (`elif True:` non cambiava il ramo); (2) «ordine anni» sopravviveva — era **codice ridondante**, rimosso; (3) sopravvivevano `per_pv_mesi` e `segnali_off`; (4) `per_pv_mesi` sopravviveva **ancora**, e la diagnosi precedente era sbagliata: il colpevole non era il `try` esterno ma un test i cui dati dell'anno precedente erano **decorativi**. Riscritto come finestra a cavallo del capodanno — il caso in cui i 3 mesi di confronto stanno nell'anno vecchio e il segnale, col bug, si spegneva del tutto. Lungo la strada: rimosso un `try` diventato codice morto e **due test che non provavano nulla**. ⚠️ **Al deploy**: i segnali hanno una cache giornaliera (`gruppo_segnali_state`, 1×/giorno per account) che si invalida solo al salvataggio della config — i clienti vedranno il segnale nuovo **dal giorno dopo**, o subito su `/api/gruppo/segnali?force=true`. Comportamento pre-esistente, non introdotto dal fix. ⚠️ **Rilievo aperto** (dal `code-reviewer`, non risolto qui perché è una scelta di prodotto): il testo del segnale non dice **di quale mese** parla, e col gate di completezza l'ultimo mese confrontabile può essere 2-3 mesi indietro (oggi: luglio per LAND/OFFSIDE/OVERTIME, giugno per le 3 SUSHILAND). Il cliente legge un margine giusto attribuito al momento sbagliato. Rimedio minimo suggerito: «Margine di giugno al 39%…». **Causa ri-misurata a DB il 04/09**: non sono le fatture a mancare ma il **costo del personale** — le 3 SUSHILAND hanno `costo_dipendenti = 0` da luglio, e **tutte e 6 le sedi** ce l'hanno a 0 ad agosto. È un dato che i clienti non hanno ancora inserito, non un difetto del gate | ✅ **Chiuso** |
| **Q2** | ✅ **CHIUSO il 04/09.** Food cost con due definizioni: ÷lordo vs ÷netto. **Decisione di Mattia: sempre sul netto.** ⚠️ **Il perimetro del rilievo era sbagliato**: i punti sul lordo erano **2, non 3** — `_kpi_periodo` (Home) e `gruppo_overview` (Catena). Il **briefing non calcola il food cost**, riceve il numero già composto; `margine_service` (soglie e notifiche) e le 3 formule della pagina Margini erano **già sul netto**. **Perché contava**: le soglie di `KPI_SOGLIE` (38%) sono tarate sul netto, quindi il denominatore lordo giudicava con un metro più generoso e **l'allarme non scattava**. Misurato a DB sui costi veri da fatture (non sullo snapshot, stantìo): **5 mesi su 5 sedi diverse** stavano sotto il 38 col lordo e sopra col netto — OVERTIME 6/2026 (36,9→40,3), LAND 4/2026 (36,7→39,6) e 5/2026 (37,6→40,6), SUSHILAND SAN GIULIANO 5/2026 (35,8→38,6), SUSHILAND VILLA GUARDIA 5/2026 (36,4→39,0). Delta medio +2,7 punti. Presidio: `tests/test_food_cost_sempre_su_netto.py` (8 test), **2 mutanti / 2 uccisi**. Il primo test sulla Catena **ricalcolava la formula** invece di chiamare `gruppo_overview`: sopravviveva al mutante, riscritto. ⚠️ **Al deploy**: i clienti vedranno il food cost salire di 2-4 punti — non è un peggioramento, è il numero giusto | ✅ **Chiuso** |
| **Q3** | Snapshot economico di `margini_mensili` incoerente per costruzione: 3 scrittori che non si parlano. Misurato: OVERTIME febbraio MOL fotografato +50.834 € vs +28.398 € vero. ⚠️ **Chiuso Q1, la colonna `mol_perc` resta senza alcun lettore runtime** (verificato: il blocco Segnale 1 era l'unico): la natura della voce cambia da «serve un presidio» a «colonna morta da valutare» | **Strutturale** |
| **Q4** | Tab Calcolo vs tab Analisi (pagina Margini): le quote riparto includono le righe «Da Classificare» della sede tecnica (deliberato), la proiezione per centro le esclude (deliberato — regola di dominio 1). Scarto 13–592 €/mese. Due regole giuste in conflitto | **Decisione di Mattia** |

> **Perché questa sezione è stata riscritta il 04/09.** Il commit `4985f5f` aveva
> riportato indietro lo stato del ciclo per tenerne fuori il lavoro Fable, e con
> esso erano sparite anche Q1–Q4, che invece **appartengono a questo ciclo** (voce
> §3 #1, l'unica che Fable non ha toccato). Ricostruita dal report di quadratura,
> con le cifre ri-misurate a DB, non ricopiate.

**Come si esegue: la sezione dei residui è VUOTA.** R1-R8 e R10 chiusi il 03/09;
**R9 chiuso** dal commit `c8ec158` (verificato il 04/09: nessun `getppid` nel sorgente,
commit già in produzione) — restava in lista per inerzia, non perché aperto. Il vincolo
«niente zone nuove finché §2 non è vuota» non blocca più nulla: gli unici punti aperti
sono **Q3** (tecnico) e **Q4** (decisione di Mattia): Q2 è stato chiuso il 04/09.

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

> **Copertura fuori ciclo (04/09).** Cinque di queste sei voci sono già state
> percorse dalla **sessione Fable** — un lavoro autonomo, aperto e chiuso, il cui
> racconto vive **solo** in [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) per scelta
> di Mattia (commit `4985f5f`). **Chi ha eseguito quelle voci è quella sessione,
> non questo ciclo**: il dettaglio di cosa è stato trovato e chiuso si legge lì. Quel lavoro **non si riporta dentro questo ciclo**:
> la colonna «Copertura reale» serve solo a non far rifare da zero ciò che è già
> stato fatto e **deployato**. È stata misurata sul codice (`git log` sui
> percorsi di ogni voce), non ereditata dai documenti.
>
> Conseguenza pratica: il vincolo qui sotto **non obbliga a rifare** le voci già
> coperte. Restano da ripassare con Opus solo la **#3** (regola di dominio #1,
> flag spento, migration gia' applicata) e la **#6** (prima passata: 1 router su
> molti).

| # | Cosa | Perché in questa posizione | Copertura reale (misurata 04/09) |
|---|---|---|---|
| **1** | **Quadratura dei numeri fra le pagine** — prendere 3 clienti veri e verificare che lo stesso dato torni in ogni schermata dove compare | 🔴 **Non è un audit di codice, è la verifica che nessuno ha mai fatto.** Il prompt esiste da agosto (`docs/storico/..._COERENZA_NUMERI.md`) e non è mai stato eseguito. Nasce dall'unico difetto trovato **dal cliente prima che dall'audit** (F&B e Spese Generali che non tornavano). È ciò che difende la reputazione, non la qualità del codice | ✅ **Eseguita il 03/09.** Da qui nascono Q1-Q4 (§2) |
| **2** | **I prompt AI** — `config/`, 2.379 righe, mai guardate | È il cuore del prodotto e la **regola di dominio n.1**. Un difetto qui non colpisce un cliente: li colpisce tutti insieme, in silenzio. Ha già dato un problema (il prompt contraddiceva la regola, ciclo 08) | ✅ **Coperta fuori ciclo** (**sessione Fable**, [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §2, `0cfc8fa`): presidio anti-mojibake provato per mutazione. **Non da ripassare** |
| **3** | **Categorizzazione, fasi 4→8** — 5 fasi su 10 aperte | Lavoro già iniziato e fermo a metà: rientra nel principio «niente parziali». La fase 4 tocca il MOL su tutto lo storico, dietro flag: il delta per sede si misura e si porta a Mattia **prima** di attivarlo | ✅ **Coperta fuori ciclo** (**sessione Fable**, [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §3, `e36dfcd`→`8dd7a2e`): 10 fasi su 10, ognuna con test dedicati. ⚠️ **Da ripassare con Opus**: tocca la regola di dominio #1 e la Fase 4 ha un flag ancora **spento** (la migration `20260903210000` e' invece **gia' applicata al DB**, verificata il 04/09) |
| **4** | **Il briefing giornaliero** — `daily_briefing_service.py`, 1.637 righe | È **la prima cosa che il cliente legge ogni mattina**. Quattro sessioni di lavoro a settembre, mai auditato come oggetto proprio | ✅ **Coperta fuori ciclo** (**sessione Fable**, [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §4, `79679c3`). **Non da ripassare** |
| **5** | **Il worker notturno** — `worker/`, 2.400 righe | **Gira non presidiato** e non è in nessuna lista. Se sbaglia di notte, se ne accorge il cliente al mattino | ✅ **Coperta fuori ciclo** (**sessione Fable**, [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §5, `3fde2dd`). ⚠️ La colonna a sinistra **è smentita dalla misura**: 7 file di test worker, non «non presidiato». **Non da ripassare** |
| **6** | **I router del worker** — 16.514 righe, ~4.000 lette | Il blocco più grande a copertura parziale. Da affrontare per router, non in blocco | 🟠 **Prima passata fuori ciclo** (**sessione Fable**, [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §6, `8e6a19b`: scadenziario). **Da ripassare con Opus**: per costruzione copre 1 router su molti — è la voce più grande e resta la meno coperta |

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
