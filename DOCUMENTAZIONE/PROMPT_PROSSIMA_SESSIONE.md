# Prompt prossima sessione — `(app)/dashboard/`, 1.749 righe

> Scritto l'1/9/2026 dopo la **seconda** passata su `catena/`, che ha portato
> l'area al 90%.
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha violato **cinque** volte in tre giorni —
> l'ultima l'1/9, quando ho scritto «191 test» e «225 righe» senza ricontare a
> fine lavoro: erano 194 e 229, e le ha trovate il reviewer.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git status --short                      # dev'essere pulito
git log --oneline origin/main..main     # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, con il numero — **quello che
leggi tu adesso**, non quello scritto qui. A fine giornata dell'1/9 erano **8**.
Il push manda **tutti** i commit accumulati — e **il push È il deploy**. Non
pushare mai di iniziativa: la finestra è la sera/notte, e la decide Mattia.

Si lavora su **`main` locale**. Niente branch, niente PR (`WORKFLOW.md` §0).

⚠️ **Nel tree c'è lavoro di un'altra sessione** (consumi admin: `4bce085` più
modifiche non committate). Porta una **migration mai confrontata col DB live**
(`20260901120000_rpc_admin_consumi_mensili.sql`). Non è tuo, non committarlo, ma
**dillo a Mattia**: è schema che nessuno ha ancora verificato esistere davvero.

---

## 1. La dimensione: `(app)/dashboard/` — 1.749 righe

`catena/` è **chiusa** (90%: restano solo `card-segnali.tsx` e le pages, entrambe
senza logica pura). `dashboard/` è ora l'area 🔴 più grande, e ha un aggancio già
pronto: **`MolAndamento` in `dashboard/kpi-block.tsx` è il gemello di
`MolSparkline`** — stessa logica, già estratta e testata in
`lib/catena-confronti.ts` come `calcolaSparkline`, ma la copia di dashboard è
**intatta**. È il punto di partenza naturale.

Misura tutto tu: `find "apps/web/src/app/(app)/dashboard" -type f | xargs wc -l`.

Alternative, se Mattia preferisce: `(app)/impostazioni/` (806),
`(app)/agenda/` (693), o la **coda** qui sotto al §5.

---

## 2. Il metodo, battuto 8 volte — non inventarne uno nuovo

1. **Ricognizione**: leggi, misura, e **verifica le ipotesi del prompt prima di
   crederci**. L'1/9 (2ª passata) **tre su cinque erano sbagliate**, e una
   avrebbe fatto sbagliare il fix: vedi §2bis.
2. **Estrai la logica pura** in un modulo `lib/` nuovo, **byte per byte, senza
   correzioni**. Poi `git diff -U0 | grep '^+'` sul componente: deve contenere
   **solo import e chiamate**.
   ⚠️ **Quel gate dimostra che la logica è USCITA dal `.tsx`, non che sia
   ARRIVATA INTATTA in `lib/`.** Se durante la copia scrivi un `Math.round` che
   prima non c'era, `tsc` passa, i test (scritti dopo, sul codice già estratto)
   passano, e il gate pure. Per le funzioni dove "migliorare" è tentante —
   regex, formule che finiscono in uno `style` — il controllo vero è un
   **oracolo**: valuta l'espressione originale presa da `git show HEAD:<file>`
   contro il modulo nuovo su ~200 input avversi. L'1/9 ne ho fatti 236 su due
   regex di slug: zero divergenze, ~20 minuti.
3. **`import type { X }`, non `import { type X }`.** La seconda lascia in piedi
   la import statement e l'harness muore con `ERR_MODULE_NOT_FOUND`.
4. **Test con `esegui_ts`** (`tests/helpers_ts.py`), mai un runner in
   `apps/web/`: `deploy-vercel.yml` scatta su `apps/web/**` e ogni test farebbe
   partire un **deploy di produzione**.
5. **Prova per mutazione, sempre.** Copia di `apps/web/src` in scratchpad,
   `helpers_ts.WEB_SRC` ridiretta via `-p conftest_mut` (plugin, non un conftest
   raccolto) — **mai sul file del repo**.
6. **Controprove obbligatorie**: almeno un mutante *equivalente* che deve
   **sopravvivere**. Se muore tutto, il test è rigido, non forte.
7. **Un mutante sopravvissuto va capito, non zittito.** Fixture povera ed
   equivalenza vera sono due esiti diversi: la prima si chiude con un dato, la
   seconda si documenta nel sorgente.

### L'harness di mutazione

Sta in `/tmp/claude-*/scratchpad/muta.py` (si perde a fine sessione, riscrivilo).
**Validalo sui TRE lati prima di fidartene** — l'1/9 ha funzionato:
- un mutante palese (`return "999999%"`) deve **morire**;
- una controprova innocua (un commento cambiato) deve **sopravvivere**;
- un pattern **inesistente** deve **fermare il giro**, non produrre un falso
  sopravvissuto. Una regex che matcha 0 volte lascia il file identico
  all'originale: il test resta verde e sembra un'equivalenza.

`pytest-timeout` **non è installato** (riverificato l'1/9): `--timeout` fa uscire
pytest con **rc=4**. Tratta `rc=1` come ucciso e **`rc>=2` come errore d'uso**
che interrompe il giro. Il 31/8 un harness ha misurato 40/40 così.

### 2bis. Le tre lezioni della 2ª passata

- **Non generalizzare una conclusione locale a tutto il file.** Avevo dichiarato
  equivalente un `??` (in una funzione dove il tipo escludeva lo `0`) e non ho
  riverificato l'**altro** `??` dello stesso file, dove `number | null` rende lo
  `0` raggiungibile. Il reviewer l'ha trovato con un mutante che sopravviveva a
  110 test.
- **Il fix "ovvio" può non essere il fix.** Il bug dell'importo italiano
  (`"1.234,56"` → NaN) sembra causato dal `replace` non globale. **Non lo è**:
  `replaceAll` lascia il difetto identico, perché a rompere è il **punto** delle
  migliaia. La ricetta vera —
  `Number(t.replace(/\./g, "").replace(",", "."))` — è verificata e sta nel
  commento di `parseImportoManuale`. Il mutante `replace→replaceAll` è
  un'equivalenza, non una lacuna.
- **Le fixture di soli valori positivi nascondono metà del comportamento.** In
  `catena/` la `spesa` è netta delle note di credito e può essere negativa
  davvero: tre anomalie (barra a `-30%`, pavimento che alza i negativi a 4%,
  `Math.max(0, …)` che restituisce un valore fuori lista) sono invisibili senza.

### La tecnica dello stub `fetch` (riusabile)

`helpers_ts.py` stubba `globalThis.fetch` a `throw`, ma il prologo è concatenato
**prima** dell'espressione: riassegnalo dentro l'espressione node. Esempio
completo in `tests/test_margini_netto_mese_frontend.py`. **Lo stub deve servire
`json` anche quando `ok` è `false`** — una 500 di FastAPI ha un body JSON valido.

---

## 3. Come si risponde a Mattia

Owner, non lettore di codice: decide **cosa**, non come.

**Domande di stato** («a che punto siamo», «cosa manca»): **una riga di
verdetto**, **max 3 punti**, **una domanda** se serve una decisione, e **«Vuoi il
dettaglio?»**. Tetto ~10 righe. Niente tabelle, niente percorsi con numero di
riga. Un mio errore si corregge in **mezza riga**.

**A fine planning** (`ExitPlanMode`), sempre e **nel messaggio in chat**, non solo
nel file del piano: riepilogo non tecnico **+ tabella fase / modello / sforzo /
`ultrathink`**. Il modello **lo sceglie lui**: l'1/9 ha chiesto Opus su tutte le
fasi in entrambe le sessioni — proponi, non decidere.

---

## 4. Chiusura — tutti i punti, non tre (`WORKFLOW.md` §5bis)

1. Mutazione con **bilancio dichiarato**: N mutanti, M uccisi, K sopravvissuti
   **elencati col motivo**.
2. `python -m pytest tests/` verde + `cd apps/web && npx tsc --noEmit`.
   **`tsc` controlla i tipi e non esegue niente.**
3. **`/code-reviewer`** sul diff cumulativo, chiedendogli di **rifare la
   mutazione con i suoi mutanti**. Negli ultimi 6 giri ha trovato ogni volta
   qualcosa — l'1/9 (2ª passata) una fixture mancante che nessuno dei miei 51
   mutanti copriva. Il gate `.claude/.reviewer_gate_ok` **si consuma**.
   Nota: **il reviewer sbaglia anche.** **Riproduci il rilievo prima di
   accettarlo**, e digli quando ha torto.
4. **Verbale** in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md`: perimetro misurato
   **e cosa non copre e perché**, ipotesi smentite, tecniche riusabili, coda con
   la sua misura.
5. **Roadmap** `AUDIT_ONEFLUX_STATO_2026-08-29.md` aggiornata.
6. **`AUDIT_COPERTURA.md` ri-misurato contro HEAD**, **risommando la colonna**.
   ⚠️ **Un'estrazione NON è a somma zero**: l'1/9 la 1ª passata ha fatto +201 e la
   2ª **+591** — i moduli aggiungono firme, tipi e i commenti che spiegano le
   anomalie. Chi si aspetta il pareggio crede di aver sbagliato la misura.
   ⚠️ `git archive HEAD apps/web/src | tar -xO | wc -l` include **481 righe di due
   font `.woff` binari**: il totale è quella cifra **meno 481**. All'1/9:
   **52.205**.
   ⚠️ **Ri-conta i test e le righe a fine lavoro**, non a metà: è l'errore già
   fatto cinque volte.
7. `python scripts/check_documentazione.py` pulito. **Verifica i simboli, non
   l'aritmetica**: le somme dei `.md` non hanno nessuna rete automatica.
8. Commit su `main` locale, `git status --short` pulito (doc **insieme** al
   codice).
9. Riscrivere questo file per la dimensione successiva.
10. **Dire a Mattia quanti commit sono in coda. Non pushare.**

---

## 5. La coda — cose trovate e NON fatte, con la loro misura

Esclusioni motivate, non dimenticanze. Vanno riprese come dimensione propria
(§5bis vieta gli strascichi).

**I fix, che hanno bisogno della loro finestra di deploy:**

- **`parseImportoManuale` in ~25 punti dell'app** — `"1.234,56"` → NaN.
  **La ricetta è verificata** (§2bis): non è `replaceAll`. Oggi il danno è
  contenuto da una guardia: l'utente vede un messaggio d'errore sbagliato, il NaN
  non arriva al backend.
- **La guardia sulle liste vuote di `config-assistente-catena`** — con un load
  fallito il POST manda `[]`, che il backend legge come «niente escluso» e
  riattiva tutto in silenzio. Difesa solo da un `disabled` di UI. Il fix cambia
  comportamento su uno stato oggi abilitato.
- **Le 8 anomalie della 1ª passata catena** (elenco nel verbale 1/9), fra cui
  `tintConti` con `livello_dati ?? "completo"`, che sul campo assente sceglie
  l'ipotesi **più ottimista** e certifica in verde un MOL non verificato.
- **Le 8 anomalie della 2ª passata** (verbale 1/9, 2ª sezione), fra cui
  `classePrezzo` che con prezzi uniformi colora **tutti** i PV di rosso.
- **Le 9 copie backend del filtro `Da Classificare`** + 2 RPC SQL. Sui dati veri:
  **0 righe attive**. Richiede una migration su 7 account.

**Le deduplicazioni, che sono cambi di comportamento:**

- **7 copie di `euro`/`pct`/`num` e 10 di `MESI`** — `lib/format.ts` è «FONTE
  UNICA» e `lib/mesi.ts` **cita catena**, ma nessuno dei file di catena le
  importa. Sostituirle **cambia l'output**: `num` diverge sui decimali (1 vs 3),
  `pct` sulla guardia null, e `lib/format.ts` usa `toFixed` dove le copie locali
  usano `toLocaleString("it-IT")` (separatori diversi). Serve prima un test di
  equivalenza byte per byte.
- **`ICONA` in `card-segnali.tsx`**, identica a
  `(mobile)/m/briefing/mobile-catena.tsx:7-12`. Mappa a componenti `lucide-react`:
  per estrarla va cambiata forma.
- **`lib/` importa da `app/`** — inversione di dipendenza, 2 occorrenze. Da
  girare **quando toccherai `periodi.ts` per altro**.

**Il resto:**

- **`MolAndamento` in `dashboard/kpi-block.tsx`** — gemello di `MolSparkline`,
  intatto. **È l'aggancio della prossima passata** (§1).
- **Il mobile riscrive a mano il gate mensile**
  (`(mobile)/m/diario/mobile-incassi.tsx:215-235`), senza la distinzione
  null/0: un errore di lettura diventa «mese a zero».
- **L'asimmetria della Media Ricavi netti** (`lib/margini-aggregati.ts`):
  fotografata, non corretta (decisione di Mattia). 0 sedi su 8 oggi, ma le 66
  righe `source='manuale'` hanno tutte `coperti` NULL: si arma da sola.
- **`dependencies=[...]` a livello di `APIRouter`**: tocca 238 endpoint.
- **Il rendering frontend resta non testato ovunque.** Ogni area «chiusa»
  significa *logica pura coperta*, non *ogni riga testata* — ed è così che va
  detto a Mattia.

---

## 6. Trappole che sono già costate ore

- **Next.js in locale punta al DB cloud reale**: scrivi sui dati veri dei clienti.
- **Vercel deploya solo se il commit tocca `apps/web/**`; Railway non ha filtro di
  path** — anche soli `.md` gli fanno ridispiegare il worker.
- **Zero test frontend**: `npx tsc --noEmit` è l'unica rete, e non esegue niente.
- **Un test che mocka il client non prova che la query funzioni.** 6 test del
  radar anomalie sono verdi da mesi su una colonna che non esiste.
- **Mai `__getattr__`** per gli helper dei router: ha già rotto 9 router in
  produzione.
- **Worker locale senza `--reload`** tiene in memoria il codice vecchio.
