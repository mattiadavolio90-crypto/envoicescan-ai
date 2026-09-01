# Prompt prossima sessione — il resto di `(app)/catena/`

> Scritto l'1/9/2026 a chiusura della prima passata su `catena/`.
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha già violato quattro volte in tre giorni.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git status --short                      # dev'essere pulito
git log --oneline origin/main..main     # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, con il numero — **quello che
leggi tu adesso**, non quello scritto qui. A fine giornata dell'1/9 erano **2**.
Il push manda **tutti** i commit accumulati, non solo quelli di oggi — e **il
push È il deploy**. Non pushare mai di iniziativa: la finestra è la sera/notte,
e la decide Mattia.

Si lavora su **`main` locale**. Niente branch, niente PR (`WORKFLOW.md` §0).

⚠️ **All'1/9 il working tree aveva lavoro di un'altra sessione non committato**
(`services/consumi_service.py`, la migration `20260901120000_rpc_admin_consumi_mensili.sql`,
modifiche a `routers/admin.py`, `config/constants.py`, `routers/account.py`).
Facevano fallire 2 test (`test_flusso_dati_admin.py::test_badges_*`) nel tree,
**non** su checkout pulito. Se lo trovi ancora lì: non è tuo, non committarlo,
ma **dillo a Mattia** — una migration non tracciata è schema che non esiste in
nessun file.

---

## 1. La dimensione: il resto di `catena/` — 1.767 righe

La prima passata (1/9) ha chiuso 3 file su 6. **Non è più un'area vergine**, ma
è la sola dove resta un blocco grosso e omogeneo.

Misurato l'1/9 (`wc -l`):

| File | Righe | Note |
|---|---:|---|
| `gruppo-tag-section.tsx` | 721 | **il candidato naturale** |
| `finestra-costi-gruppo.tsx` | 553 | |
| `config-assistente-catena.tsx` | 202 | |
| `card-segnali.tsx` | 110 | quasi tutto stato + fetch |
| `page.tsx` · `fatture/page.tsx` · `loading.tsx` | 76 · 77 · 28 | zero logica pura |

### Cosa ho già verificato per te (1/9)

- **`gruppo-tag-section.tsx` delega già** a `lib/tag-candidati.ts`
  (`calcolaCandidati`, `MIN_LETTERE_RICERCA`): il precedente di estrazione esiste
  dentro il file stesso, è il modello da seguire.
- Logica pura già mappata lì dentro: `maxPv`/`maxForn`/`maxTrend`, la soglia
  «servono ≥2 prezzi per confrontare» (`:551`), `percentualeBarra` replicata 3
  volte con regole diverse (`:644`, `:690`, `:707` — solo l'ultima ha il floor a
  4%), `vuoto` con `every(p => p.spesa === 0)` (uguaglianza float su denaro),
  e il confronto colore a `:653` che usa `===` su float **senza** la guardia
  `best !== worst` che invece esiste in `cellTone`.
- **`finestra-costi-gruppo.tsx` ha un bug vero**: `parseImportoIt` (`:354`) fa
  `replace(",", ".")` **non globale** → `"1.234,56"` diventa `NaN`.
- **`config-assistente-catena.tsx:82-83`**: con `segnali=[]` (load fallito) il
  payload è `[]`, che il backend legge come «niente escluso» → **riattiva tutto
  in silenzio**. Oggi è protetto da una guardia di UI (`disabled` a `:194`), cioè
  una guardia di *interfaccia* su una regola di *dati*.

---

## 2. Il metodo, battuto 6 volte — non inventarne uno nuovo

1. **Ricognizione**: leggi, misura, e **verifica le ipotesi del prompt sul DB
   di produzione prima di crederci**. L'1/9 **due su tre erano sbagliate**: la
   sparkline rossa non era raggiungibile (il worker spegne il grafico prima) e
   di letterali IVA nell'area non ce n'era **nemmeno uno**.
2. **Estrai la logica pura** in un modulo `lib/` nuovo, **byte per byte, senza
   correzioni**. Poi verifica che il diff dei componenti contenga **solo import
   e chiamate**: `git diff -U0 | grep '^+'`. Se compare logica, il taglia-incolla
   non era fedele — e un test verde su un'estrazione infedele certifica il codice
   sbagliato. È il rischio numero uno, più del test stesso.
3. **`import type { X }`, non `import { type X }`.** La seconda forma lascia in
   piedi la import statement, node carica `lib/gruppo.ts` → `./worker` (import
   relativo che il resolve hook non riscrive) e l'harness muore con
   `ERR_MODULE_NOT_FOUND`. Costata 10 minuti l'1/9, la ritroverai identica.
4. **Test con `esegui_ts`** (`tests/helpers_ts.py`), non un runner frontend.
   Niente runner in `apps/web/`: `deploy-vercel.yml` scatta su `apps/web/**`, un
   runner lì farebbe partire un **deploy di produzione a ogni merge di un test**.
5. **Prova per mutazione, sempre.** Copia di `apps/web/src` in scratchpad,
   `helpers_ts.WEB_SRC` ridiretto alla copia via `-p conftest_mut` (plugin, non
   un conftest raccolto) — **mai sul file del repo**. Lo script deve asserire
   **esattamente 1 sostituzione** e fermarsi altrimenti.
6. **Controprove obbligatorie**: almeno un mutante *equivalente* che deve
   **sopravvivere**. Se muore tutto, il test non discrimina, è rigido.
7. **Un mutante sopravvissuto va capito, non zittito.** L'1/9 ne sono usciti due
   opposti: uno (`-Infinity` → `+Infinity`) era **fixture povera** — con un solo
   null il segno non è osservabile, serve il secondo; l'altro (`v == null` in
   `cellTone`) era **equivalenza vera**, documentata nel sorgente invece di
   forzare un test che la zittisse. Distinguere i due casi è il lavoro.

### L'harness di mutazione

Sta in `/tmp/claude-*/scratchpad/muta.py` (si perde a fine sessione, riscrivilo).

**Validalo sui DUE lati prima di fidartene**: un mutante palese (`return 999999`)
deve **morire**, e una controprova (un commento cambiato) deve **sopravvivere**.
Il 31/8 il `code-reviewer` ha misurato 40/40 uccisi con un harness rotto: passava
`--timeout=300` senza `pytest-timeout`, pytest usciva con **rc=4** (usage error)
e lui leggeva `rc != 0` come «ucciso». **Distingui `rc=1` (test rosso) da `rc≥2`
(errore d'uso)**, con un assert esplicito. `pytest-timeout` **non è installato**:
verificato l'1/9, il flag fa ancora uscire pytest con rc=4.

### Due lacune che il reviewer ha trovato, e che rifarai se non stai attento

- **Fixture con soli valori positivi.** `0` e `-Infinity` sono indistinguibili
  se tutto è positivo: entrambi perdono contro tutto. Se la funzione ordina o
  confronta, **metti un valore negativo nella fixture** — in `catena/` i margini
  negativi esistono (Offside, 8 mesi su 8).
- **Coerenza interna scambiata per correttezza.** Asserire che due output
  combacino fra loro non prova che siano giusti: un path SVG sbagliato in modo
  coerente passa. Su una geometria, **asserisci le coordinate in assoluto**.

### La tecnica dello stub `fetch` (riusabile)

`helpers_ts.py` stubba `globalThis.fetch` a `throw`. Per testare una funzione che
fa rete, **riassegnalo dentro l'espressione node**, dopo il prologo — nessuna
modifica a `helpers_ts.py`, nessun effetto sugli altri test. Esempio completo in
`tests/test_margini_netto_mese_frontend.py`.

**Lo stub deve servire `json` anche quando `ok` è `false`**: una 500 di FastAPI
ha un body JSON valido (`{"detail": ...}`). Uno stub che su `ok:false` non
espone `json` è irrealistico e lascia vivere il mutante che toglie il controllo
su `r.ok` — è successo, 12 test su 12 non lo vedevano.

---

## 3. Come si risponde a Mattia

Owner, non lettore di codice: decide **cosa**, non come.

**Domande di stato** («a che punto siamo», «cosa manca»): **una riga di
verdetto**, **max 3 punti**, **una domanda** se serve una decisione, e **«Vuoi
il dettaglio?»**. Tetto ~10 righe. Niente tabelle, niente percorsi con numero di
riga. Un mio errore si corregge in **mezza riga**.

**A fine planning** (`ExitPlanMode`), sempre e **nel messaggio in chat**, non
solo nel file del piano: riepilogo non tecnico **+ tabella fase / modello /
sforzo / `ultrathink`**. Il 31/8 l'ho scritta solo nel file e Mattia me l'ha
contestata: «molto male». Il modello **lo sceglie lui**: l'1/9 ha chiesto Opus su
tutte le fasi, non il misto che avevo proposto — proponi, non decidere.

---

## 4. Chiusura — tutti i punti, non tre (`WORKFLOW.md` §5bis)

1. Prova per mutazione, con **bilancio dichiarato**: N mutanti, M uccisi, K
   sopravvissuti **elencati col motivo**. I sopravvissuti si dichiarano.
2. `python -m pytest tests/` verde + `cd apps/web && npx tsc --noEmit`.
   **`tsc` controlla i tipi e non esegue niente**: non è una rete sul
   comportamento.
3. **`/code-reviewer`** sul diff cumulativo, chiedendogli di **rifare la
   mutazione con i suoi mutanti**. Negli ultimi 5 giri ha trovato ogni volta
   qualcosa. Il gate `.claude/.reviewer_gate_ok` **si consuma**.
   Nota: **il reviewer sbaglia anche.** L'1/9 la conclusione su `R04` era giusta
   ma la prova allegata era **falsa** (sulla sua fixture mutante e originale
   danno lo stesso risultato). **Riproduci il rilievo prima di accettarlo**, e
   digli quando ha torto.
4. **Verbale** in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md`: perimetro
   misurato **e cosa non copre e perché**, ipotesi smentite, esposizione in euro,
   tecniche riusabili, e la coda di quel che resta **con la sua misura**.
5. **Roadmap** `AUDIT_ONEFLUX_STATO_2026-08-29.md` aggiornata.
6. **`AUDIT_COPERTURA.md` ri-misurato contro HEAD**, **risommando la colonna**.
   ⚠️ **Un'estrazione NON è a somma zero**: l'1/9 `lib/` ha fatto +284 e
   `catena/` −83, delta **+201** — il modulo aggiunge firme, tipi e i commenti
   che spiegano le anomalie. Chi si aspetta il pareggio crede di aver sbagliato
   la misura: è il contrario. Confronta sempre con
   `find apps/web/src -type f ! -name '*.woff' | xargs wc -l`.
   ⚠️ `git archive HEAD apps/web/src | tar -xO | wc -l` include **481 righe di
   due font `.woff` binari**: il totale è quella cifra **meno 481**.
7. `python scripts/check_documentazione.py` pulito. **Verifica i simboli, non
   l'aritmetica**: le somme dei `.md` non hanno nessuna rete automatica.
8. Commit su `main` locale, `git status --short` pulito (doc **insieme** al
   codice).
9. Riscrivere questo file per la dimensione successiva.
10. **Dire a Mattia quanti commit sono in coda. Non pushare.**

---

## 5. La coda — cose trovate e NON fatte, con la loro misura

Non sono dimenticanze: sono esclusioni motivate. Vanno riprese come dimensione
propria, non infilate in una sessione altrui (§5bis vieta gli strascichi).

- **Le 8 anomalie fotografate in `catena/`** (elenco completo nel verbale 1/9).
  Le due che pesano di più: `tintConti` con `livello_dati ?? "completo"` — sul
  campo assente sceglie l'ipotesi **più ottimista** e certifica in verde un MOL
  che nessuno ha verificato; e la sparkline rossa su MOL in risalita, oggi
  **disinnescata** da `gruppo.py:873` (filtra i mesi a `netto > 0`) ma che si
  arma se quel filtro cambia. **Sono un fix, cioè una dimensione a sé**: hanno
  bisogno della loro finestra di deploy, non di essere infilate in un audit.
- **7 copie locali di `euro`/`pct`/`num` e 3 di `MESI`** in `catena/`, mentre
  `lib/format.ts` è «FONTE UNICA» e `lib/mesi.ts` **cita catena** fra i file da
  centralizzare. Non deduplicate: sostituirle **è un cambio di comportamento** se
  l'output diverge, e diverge davvero — esistono **due `euro2` omonime con
  output diverso** (`finestra-margini-coperti.tsx:376` usa `toFixed`, niente
  separatore migliaia; `gruppo-tag-section.tsx:29` usa `Intl`). Serve prima un
  test di equivalenza byte per byte.
- **Il mobile riscrive a mano il gate mensile.**
  `(mobile)/m/diario/mobile-incassi.tsx:215-235` importa da `margini/periodi.ts`
  solo `scorporoNetto` e il tipo, poi **riscrive** la scelta
  override-vs-giornalieri **senza la distinzione null/0**. Un errore di lettura
  diventa «mese a zero». **Candidato forte** se si apre `(mobile)/`.
- **`MolAndamento` in `dashboard/kpi-block.tsx`** è il gemello di
  `MolSparkline`, **intatto**: ha la stessa logica, oggi non estratta né testata.
  Da unificare con `calcolaSparkline` quando si aprirà `dashboard/` (1.749
  righe, mai toccata).
- **L'asimmetria della Media Ricavi netti** (`lib/margini-aggregati.ts`):
  fotografata da un test, **non corretta** (decisione di Mattia). 0 sedi su 8 nel
  caso misto oggi, ma le 66 righe `source='manuale'` hanno tutte `coperti` NULL:
  si arma da sola.
- **I 4 letterali IVA** in `carica-ricavi-dialog.tsx:451,452,477,478` (`/1.10`,
  `/1.22`) invece di `scorporoNetto`. Delta oggi **zero**.
- **Le 9 copie backend del filtro `Da Classificare`** (8 letterali, 1 sola con la
  costante e `.strip()`, `fastapi_worker.py:8004`) + 2 RPC SQL. Sui dati veri:
  **0 righe attive**. Il fix richiede una **migration su 7 account**: dimensione
  a sé, con la sua finestra di deploy.
- **`lib/` importa da `app/`** — inversione di dipendenza, 2 occorrenze
  (`margini-aggregati.ts` e `demo-data.ts`). Da girare **quando toccherai
  `periodi.ts` per altro**. Non ora: è importato anche da un Server Component.
- **`dependencies=[...]` a livello di `APIRouter`**: tocca 238 endpoint.
- **Il rendering frontend resta non testato ovunque.** Serve un runner di
  componenti, escluso per ragione strutturale (vedi §2.4). Ogni area «chiusa»
  significa *logica pura coperta*, non *ogni riga testata* — ed è così che va
  detto a Mattia.

---

## 6. Trappole che sono già costate ore

- **Next.js in locale punta al DB cloud reale**: scrivi sui dati veri dei clienti.
- **Vercel deploya solo se il commit tocca `apps/web/**`; Railway non ha filtro
  di path** — anche soli `.md` gli fanno ridispiegare il worker.
- **Zero test frontend**: `npx tsc --noEmit` è l'unica rete, e non esegue niente.
- **Un test che mocka il client non prova che la query funzioni.** 6 test del
  radar anomalie sono verdi da mesi su una colonna che non esiste.
- **Mai `__getattr__`** per gli helper dei router: ha già rotto 9 router in
  produzione.
- **Worker locale senza `--reload`** tiene in memoria il codice vecchio.
