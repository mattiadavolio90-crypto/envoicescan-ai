# Prompt prossima sessione — `(app)/catena/`

> Scritto il 31/8/2026 a chiusura della dimensione `margini/`.
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha già violato quattro volte in tre giorni.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git status --short                      # dev'essere pulito
git log --oneline origin/main..main     # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, con il numero — **quello che
leggi tu adesso**, non quello scritto qui. A fine giornata del 31/8 erano **27**,
ma se nel frattempo è avvenuto un push sono zero: è una cifra che invecchia in
poche ore, riportala dal comando. Il push manda **tutti** i commit accumulati,
non solo quelli di oggi — e **il push È il deploy**. Non pushare mai di
iniziativa: la finestra è la sera/notte, e la decide Mattia.

Si lavora su **`main` locale**. Niente branch, niente PR (`WORKFLOW.md` §0).

---

## 1. La dimensione: `(app)/catena/` — 3.127 righe

**È l'unica area frontend grande che nessuna passata ha mai aperto.** Non «poco
coperta»: **zero**. Multi-sede — è la vista del gruppo, quella che aggrega più
punti vendita in un numero solo.

Misurato il 31/8 (`find ... -exec wc -l`):

| File | Righe |
|---|---:|
| `gruppo-tag-section.tsx` | 721 |
| `sintesi-catena.tsx` | 559 |
| `finestra-costi-gruppo.tsx` | 553 |
| `finestra-margini-coperti.tsx` | 522 |
| `finestra-spesa-pv.tsx` | 279 |
| `config-assistente-catena.tsx` | 202 |
| `card-segnali.tsx` | 110 |
| `fatture/page.tsx` · `page.tsx` · `loading.tsx` | 77 · 76 · 28 |

### Perché è esposta

Aggrega **più sedi**. Un errore qui non sbaglia il numero di un cliente: sbaglia
il **confronto fra i suoi locali**, che è la ragione per cui un cliente
multi-sede paga il prodotto. E gli errori di aggregazione sono quelli che non si
vedono a occhio — un totale plausibile resta plausibile anche quando è sbagliato.

### Cosa ho già verificato per te (31/8)

- **`lib/gruppo.ts` (230 righe) NON è il posto dove estrarre.** È un client del
  worker: `fetchGruppoOverview`/`fetchGruppoChatConfig` sono `cache()` + `fetch`.
  Stesso caso di `lib/margini.ts`. `helpers_ts.py` vieta i moduli con
  side-effect all'import — serve un modulo nuovo, come è stato
  `lib/margini-aggregati.ts`.
- Import da `catena/`: `@/lib/gruppo` (5), `@/lib/utils` (4), `@/lib/worker`,
  `@/lib/tag-candidati`, `@/lib/scadenziario`.

---

## 2. Il metodo, battuto 5 volte — non inventarne uno nuovo

1. **Ricognizione**: leggi, misura, e **verifica le ipotesi del prompt sul DB
   di produzione prima di crederci**. Nella sessione `margini/` due piste su tre
   indicate dal prompt precedente si sono sgonfiate alla prima query, e
   l'esposizione vera (70.095 €) era altrove.
2. **Estrai la logica pura** in un modulo `lib/` nuovo, **byte per byte, senza
   correzioni**. Poi verifica che il diff dei componenti contenga **solo import
   e rimozioni**: `git diff -U0 | grep '^+'`. Se compare logica, il taglia-incolla
   non era fedele — e un test verde su un'estrazione infedele certifica il codice
   sbagliato. È il rischio numero uno di questa fase, più del test stesso.
3. **Test con `esegui_ts`** (`tests/helpers_ts.py`), non un runner frontend.
   Niente runner in `apps/web/`: `deploy-vercel.yml` scatta su `apps/web/**`, un
   runner lì farebbe partire un **deploy di produzione a ogni merge di un test**.
4. **Prova per mutazione, sempre.** Copia di `apps/web/src` in scratchpad,
   `helpers_ts.WEB_SRC` ridiretto alla copia via `-p conftest_mut` (plugin, non
   un conftest raccolto) — **mai sul file del repo**. Lo script deve asserire
   **esattamente 1 sostituzione** e fermarsi altrimenti: un mutante che non
   matcha «sopravvive» senza aver misurato niente.
5. **Controprove obbligatorie**: almeno un mutante *equivalente* che deve
   **sopravvivere**. Se muore tutto, il test non discrimina, è rigido.
6. **Un mutante sopravvissuto va capito, non zittito.** Il 31/8 il `?? 0`
   sopravviveva perché in JS `32 + null === 32`: il mutante era davvero
   equivalente **su quella fixture**, e il caso reale (`undefined` → `NaN`) non
   era coperto. La risposta non era un assert in più, era la fixture sbagliata.

### L'harness di mutazione

Sta in `/tmp/claude-*/scratchpad/muta.py` (si perde a fine sessione, riscrivilo).

**Validalo sui DUE lati prima di fidartene**: un mutante palese (`return 999999`)
deve **morire**, e una controprova (un commento cambiato) deve **sopravvivere**.
La sola prova di sanità non basta — può «morire» per il motivo sbagliato. Il 31/8
il `code-reviewer` ha misurato 40/40 uccisi con un harness rotto: passava
`--timeout=300` senza `pytest-timeout`, pytest usciva con **rc=4** (usage error)
e lui leggeva `rc != 0` come «ucciso». **Distingui `rc=1` (test rosso) da `rc≥2`
(errore d'uso)**, con un assert esplicito.

### La tecnica dello stub `fetch` (riusabile)

`helpers_ts.py` stubba `globalThis.fetch` a `throw`. Per testare una funzione che
fa rete, **riassegnalo dentro l'espressione node**, dopo il prologo — nessuna
modifica a `helpers_ts.py`, nessun effetto sugli altri test (ogni `esegui_ts` è
un processo node separato). Esempio completo in
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
contestata: «molto male». `ultrathink` su apertura, audit e fix a una regola di
dominio; normale sull'esecuzione (`WORKFLOW.md` §1ter e §3).

---

## 4. Chiusura — tutti i punti, non tre (`WORKFLOW.md` §5bis)

1. Prova per mutazione, con **bilancio dichiarato**: N mutanti, M uccisi, K
   sopravvissuti **elencati col motivo**. I sopravvissuti si dichiarano.
2. `python -m pytest tests/` verde + `cd apps/web && npx tsc --noEmit`.
   **`tsc` controlla i tipi e non esegue niente**: non è una rete sul
   comportamento.
3. **`/code-reviewer`** sul diff cumulativo, chiedendogli di **rifare la
   mutazione con i suoi mutanti**. Negli ultimi 4 giri ha trovato ogni volta
   qualcosa. Il gate `.claude/.reviewer_gate_ok` **si consuma**.
   Nota: il reviewer sbaglia anche — il 31/8 ha dichiarato rotto un harness che
   funzionava. **Verifica prima di accettare**, e digli quando ha torto.
4. **Verbale** in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md`: perimetro
   misurato **e cosa non copre e perché**, ipotesi smentite, esposizione in euro,
   tecniche riusabili, e la coda di quel che resta **con la sua misura**.
5. **Roadmap** `AUDIT_ONEFLUX_STATO_2026-08-29.md` aggiornata.
6. **`AUDIT_COPERTURA.md` ri-misurato contro HEAD**, **risommando la colonna**.
   Le estrazioni spostano righe fra l'area e `lib/`: cambiano **due** voci.
   ⚠️ `git archive HEAD apps/web/src | tar -xO | wc -l` include **481 righe di
   due font `.woff` binari** in `app/fonts/`: il totale del contatore è quella
   cifra **meno 481**. Il 31/8 questo, più una voce ferma da due cicli, faceva
   sbagliare il totale di 350 righe.
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

- **Il mobile riscrive a mano il gate mensile.**
  `(mobile)/m/diario/mobile-incassi.tsx:215-235` importa da `margini/periodi.ts`
  solo `scorporoNetto` e il tipo, poi **riscrive** la scelta
  override-vs-giornalieri **senza la distinzione null/0**
  (`nettoAutorevole?.netto ?? risposta?.totale_netto ?? 0`). È esattamente il
  difetto che `fetchNettoMese` protegge, in un file che non la chiama. Un errore
  di lettura diventa «mese a zero». **Candidato forte** se si apre `(mobile)/`.
- **L'asimmetria della Media Ricavi netti** (`lib/margini-aggregati.ts`):
  fotografata da un test, **non corretta** (decisione di Mattia). 0 sedi su 8 nel
  caso misto oggi, ma le 66 righe `source='manuale'` hanno tutte `coperti` NULL:
  si arma da sola.
- **I 4 letterali IVA** in `carica-ricavi-dialog.tsx:451,452,477,478` (`/1.10`,
  `/1.22`) invece di `scorporoNetto`. Delta oggi **zero**; il test intercetta la
  divergenza futura.
- **Le 9 copie backend del filtro `Da Classificare`** (8 letterali, 1 sola con la
  costante e `.strip()`, `fastapi_worker.py:8004`) + 2 RPC SQL, e le NOTE senza
  emoji in `margine_service.py`. Sui dati veri: **0 righe attive** (172 con
  grafia esatta, 0 con spazi, 0 col refuso). Il fix richiede una **migration su
  7 account**: dimensione a sé, con la sua finestra di deploy.
- **`lib/` importa da `app/`** — inversione di dipendenza, 2 occorrenze:
  `lib/margini-aggregati.ts` prende `MESI_NOMI_SHORT` da
  `app/(app)/margini/periodi`, e `lib/demo-data.ts` fa già lo stesso con
  `analisi-fatture/periodi`. Da girare **quando toccherai `periodi.ts` per
  altro**, spostando in `lib/` le costanti pure (`MESI_NOMI_*`,
  `IVA_DIVISORE_*`) e lasciando in `app/` solo ciò che sa di route. Non ora:
  `periodi.ts` è importato anche da `page.tsx` (Server Component).
- **`dependencies=[...]` a livello di `APIRouter`**: tocca 238 endpoint.
- **Il rendering frontend resta non testato ovunque.** Servirebbe un runner di
  componenti, escluso per ragione strutturale (vedi §2.3). Ogni area «chiusa»
  significa *logica pura coperta*, non *ogni riga testata* — ed è così che va
  detto a Mattia.

---

## 6. Trappole che sono già costate ore

- **Next.js in locale punta al DB cloud reale**: scrivi sui dati veri dei clienti.
- **Vercel deploya solo se il commit tocca `apps/web/**`; Railway non ha filtro
  di path** — anche soli `.md` gli fanno ridispiegare il worker.
- **Zero test frontend**: `npx tsc --noEmit` è l'unica rete, e non esegue niente.
  Una condizione su una soglia va **provata per mutazione sui valori veri**.
- **Un test che mocka il client non prova che la query funzioni.** 6 test del
  radar anomalie sono verdi da mesi su una colonna che non esiste.
- **Mai `__getattr__`** per gli helper dei router: ha già rotto 9 router in
  produzione.
- **Worker locale senza `--reload`** tiene in memoria il codice vecchio.
