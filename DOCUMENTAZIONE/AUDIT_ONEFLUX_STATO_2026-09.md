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

### Residui aperti — le dimenticanze che nessuno vedeva

> **Perché questa sezione esiste.** Ogni verbale dichiara onestamente cosa *non*
> ha fatto, in una sezione «Non fatto, e dichiarato». Ce ne sono **6**. Ma quei
> residui non risalivano da nessuna parte: restavano dentro verbali che nessuno
> riapre, mentre qui sopra si leggeva «chiusa ✅». Ri-verificati sul codice il
> 02/09/2026 — uno risultava già chiuso da un'altra sessione, e nessuno l'aveva
> depennato. **La lista invecchia in entrambe le direzioni: va ri-verificata,
> non ereditata.**

| Residuo | Dichiarato in | Stato (verificato 02/09) |
|---|---|---|
| `dependencies=[...]` a livello di `APIRouter` — 238 endpoint, default aperto | 3 verbali | 🔴 **aperto** — 12 router, 0 con `dependencies` |
| Il mobile riscrive a mano il gate mensile (`mobile-incassi.tsx`), senza distinzione null/0 | verbale margini | 🔴 **aperto** — sono euro sbagliati quando arriveranno i dati |
| 7 copie locali di `euro`/`pct`/`num` + 4 di `MESI` in `catena/` | 2 verbali | 🔴 **aperto** — unificarle cambia output a schermo: serve prima un test di equivalenza |
| `card-segnali.tsx` — 110 righe scoperte | verbale catena | 🔴 **aperto** — fetch + JSX, nessuna logica |
| `scripts/regen_notifiche_utente.py` importa un modulo che non esiste più | prompt sessione | 🔴 **rotto** — preesistente, mai toccato |
| Le 9 copie backend del filtro `Da Classificare` | verbale margini | 🔴 aperto — **0 righe attive** oggi; il fix richiede una migration su 7 account |
| `parseImportoIt` con `replace` non globale | verbale catena | ✅ **chiuso** da un'altra sessione — nessuno l'aveva registrato |

**Esclusioni motivate — non sono residui.** Il **rendering React** (~4.300 righe
in margini, e ovunque) non è coperto e non lo sarà: servirebbe un runner di
componenti in `apps/web/`, e `deploy-vercel.yml` scatta su `apps/web/**` — ogni
merge di un test farebbe partire un deploy di produzione. È una scelta
strutturale dichiarata, non una svista. Vale lo stesso per le aree 🟠 del
contatore: il perimetro escluso è stato **misurato e motivato**, riaprirlo senza
leggere il verbale è lavoro fantasma.

---

## 3. Cosa non è mai stato guardato

Non si duplica qui: il conto sta in **`AUDIT_COPERTURA.md`**, l'unico posto dove
le somme devono tornare. In sintesi, e da ri-misurare lì: le aree mai aperte sono
soprattutto nel **backend** — il worker non presidiato, i prompt AI in `config/`,
le utility — più tre aree frontend minori.

**Il criterio per scegliere la prossima**, che ha funzionato due sere di fila:
**conta le righe a DB delle tabelle che l'area serve**, poi decidi. Non ereditare
una priorità da un prompt: l'agenda è stata scartata così (0 turni a DB) e
`notifiche/` scelta al suo posto (67 righe, 5 utenti attivi).

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
