# Stato audit ONEFLUX — ciclo 2026-09

> **A cosa serve questo file.** Dice **cosa è fatto e cosa manca**, e nient'altro.
> Si legge in un minuto. Il dettaglio di ogni sessione sta nei verbali
> (`AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`); il conto delle righe coperte sta in
> `AUDIT_COPERTURA.md`. Se una di queste tre cose finisce nelle altre due, tutte
> e tre diventano illeggibili — è già successo.

**Ciclo aperto il 29/08/2026, tuttora in corso. Stato aggiornato al 02/09/2026.**
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
| 01/09 | **`(app)/catena/`** (3 passate) | ✅ chiusa al 95% — 283 test; le 138 righe residue non hanno logica |
| 01/09 | **Bug importi italiani** | ✅ corretti — erano in **60 punti**, non ~25; fonte unica in `lib/format.ts` |
| 01/09 | **`(app)/dashboard/`** — logica in `lib/` | ✅ 1ª passata — 92 test, 39 mutanti / 38 uccisi |
| 02/09 | **`(app)/impostazioni/`** — logica in `lib/` | ✅ 1ª passata — 22 test, 12/12 mutanti |
| 02/09 | **`(app)/notifiche/`** | ✅ chiusa — 23 test; corretto un difetto **visibile al cliente** (notifica senza pulsante) |
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
> - **R3 è più grande del dichiarato**: i formattatori duplicati sono **12, non
>   7**. I verbali cercavano `const`, ma sono `function`.

| # | Residuo | Sforzo | Perché in questa posizione |
|---|---|---|---|
| **R1** | **Gate mensile mobile** — `(mobile)/m/diario/mobile-incassi.tsx:274` riscrive a mano la scelta override-vs-giornalieri senza distinguere «zero» da «nessun dato» | Basso | 🔴 **L'unico che produce euro sbagliati.** Quando arriveranno gli incassi il netto sarà errato e nessuno se ne accorgerà. È il difetto che `fetchNettoMese` protegge sul desktop, in un file che non lo chiama |
| **R2** | **`scripts/regen_notifiche_utente.py` è rotto** — importa `services/notification_service.py`, che non esiste più | Molto basso | Si rompe alla prima riga. Nessuno lo usa oggi, ma è una trappola fra sei mesi. O si ripara o si elimina |
| **R3** | **`card-segnali.tsx`** — 110 righe scoperte (fetch + JSX) | Basso | Chiude `catena/` al **100%**: è l'unica area a un passo dal completamento |
| **R4** | **12 formattatori duplicati** in `catena/` (`euro`, `euro2`, `num`, `pct` su 4 file) + 4 copie di `MESI` | Medio | ⚠️ Unificarli **cambia cosa il cliente vede a schermo** (le due `euro2` divergono davvero): serve prima un test di equivalenza byte-per-byte, non un refactor a mano |
| **R5** | **`dependencies=[...]` a livello di `APIRouter`** — 12 router, 216 endpoint | Medio-alto | Nessuna falla attiva (0 endpoint scoperti): è **prevenzione**. Tocca tutto il traffico, vuole la sua finestra e una sessione propria |
| **R6** | **9 copie backend del filtro `Da Classificare`** + NOTE senza emoji in `margine_service.py` e 2 RPC | Alto | **Non è un residuo da chiudere in coda**: 0 righe attive oggi, ma richiede una **migration su 7 account veri**. Si apre come dimensione a sé, quando Mattia decide |

| **R7** | **4 letterali IVA** in `margine_service.py` (`/1.10`, `/1.22` a righe 777, 799, 1101) | Basso | L'aliquota vive come numero magico in 3 punti del calcolo del **fatturato netto**. Se una cambia, cambia in un posto solo e nessuno se ne accorge. Dichiarato «remediation separata, da proporre» |
| **R8** | **Guardia sulle liste vuote** di `config-assistente-catena` | Basso | Fix a sé, dichiarato aperto nella 3ª passata su `catena/` |

**Come si esegue:** R1→R4 stanno in **una sessione** (piccoli e indipendenti).
R5 in una sessione propria. R6 è una dimensione, non un residuo.

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
un'altra sessione senza che nessuno lo registrasse. *La lista invecchia in
entrambe le direzioni: si ri-verifica, non si eredita.*

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
