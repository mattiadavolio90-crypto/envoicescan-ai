# Prompt prossima sessione — `(app)/dashboard/`, e cosa insegna catena

> Scritto l'1/9/2026 dopo la **terza** passata su `catena/`, che ha chiuso
> l'area a 2.800/2.938 righe (**95%**), 282 test.
>
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha violato **sei** volte in tre giorni. La
> sesta è la più istruttiva e sta al §2: la 2ª passata ha scritto «catena chiusa
> al 90%» su un criterio che non misurava quello che credeva.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git status --short                      # dev'essere pulito
git log --oneline origin/main..main     # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, col numero **che leggi tu
adesso**. A fine giornata dell'1/9 erano **16** — e nel corso di quella
sola sessione sono passati da 12 a 16, perché altre sessioni committavano in
parallelo. Il numero si legge adesso, non si eredita da questa riga: qui è già
vecchio nel momento in cui lo leggi.

Il push manda **tutti** i commit accumulati — e **il push È il deploy**. Non
pushare mai di iniziativa: la finestra è sera/notte e la decide Mattia.

Si lavora su **`main` locale**. Niente branch, niente PR (`WORKFLOW.md` §0).

⚠️ **Nel tree c'è lavoro di un'altra sessione** (consumi admin: `4bce085` più
`services/consumi_service.py`, `routers/admin.py`, `tests/test_consumi_service.py`
non committati). Porta una **migration mai confrontata col DB live**
(`20260901120000_rpc_admin_consumi_mensili.sql`). **Non è tua: non committarla,
non "sistemarla".** `git add -A` è il modo tipico di rubarla per sbaglio — usa
`git add` sui file tuoi, uno per uno. Se la segnali a Mattia, di' **di chi è**.

---

## 1. `catena/` è chiusa — non riaprirla

**138 righe residue su 2.938**, e nessuna ha logica:

| File | Righe | Cosa c'è |
|---|---|---|
| `card-segnali.tsx` | 110 | fetch + JSX. `ICONA` mappa a componenti `lucide-react`: non entra in `lib/` senza cambiare forma |
| `loading.tsx` | 28 | skeleton |

`page.tsx` è stato chiuso il 1/9 estraendo le sue due decisioni vere — chi
**vede** la modalità catena (`num_pv < 2`) e chi vede la chat AI (pool `> 0`) —
come predicati puri in `catena-confronti.ts`.

**Se torni su quest'area, il lavoro è un fix, non un audit.** Le anomalie
fotografate (arrotondamento, `%` costante, importo italiano) aspettano una
finestra di deploy, non un'altra passata di copertura.

---

## 2. La lezione della 3ª passata — leggila prima di dichiarare chiuso qualcosa

La 2ª passata ha scritto «`catena/` chiusa, 90%». Non lo era. Contava come
coperti `finestra-margini-coperti.tsx` e `finestra-spesa-pv.tsx` **perché
importavano da `lib/`** — mentre dentro `exportXls()` restavano ~55 righe di
costruzione del file Excel che nessun test poteva raggiungere.

> **«Il file importa da `lib/`» non è «la logica del file è in `lib/`».**
> Un file può essere coperto a metà e il criterio non se ne accorge.

Quando dichiari un'area chiusa, il controllo non è *quali file importano*: è
**aprire i file e cercare cosa non è uscito**. Un `grep 'Math\.\|\.map(\|\.filter(\|replace('`
sui `.tsx` dell'area costa 30 secondi e avrebbe trovato questo.

---

## 3. Il buco nell'harness — riguarda ogni test futuro

`helpers_ts.py` era **cieco a ogni argomento negativo scalare**. `esegui_ts`
passa `json.dumps(argomento)` in coda a `node -e <script>`, e `json.dumps(-2.675)`
dà `-2.675`: node lo legge come **flag** e muore con `rc=9` e **stderr vuoto** —
un fallimento che si legge come «il modulo sotto test è rotto».

Corretto l'1/9 aggiungendo `"--"` prima dell'argomento. **546 test frontend
verificati verdi dopo il fix.**

Nessuno se n'era accorto in 12 file di test perché passavano tutti oggetti o
liste (che iniziano con `{` o `[`). Le passate precedenti avevano scritto la
regola «fixture con valori negativi obbligatorie» — ma l'avevano applicata solo
*dentro* gli oggetti, dove il bug non si manifesta.

> **Un harness che non ha mai ricevuto un certo input non è provato su
> quell'input, anche se ha 546 test verdi.**

Se un test fallisce con `rc=9` e stderr vuoto, **non è il modulo**: è l'harness
che rifiuta l'argomento. Guarda cosa passi prima di riscrivere il codice.

Da oggi l'harness ha i **suoi** test (`tests/test_helpers_ts_harness.py`, 18):
round-trip dei tipi in uso, i negativi che prima uccidevano node, e le stringhe
che *sembrano* flag (`"--help"`, `"-v"`) che devono restare dati. Provati per
mutazione: togliendo il `"--"` falliscono esattamente 3 test. Se li vedi rossi,
il bug è in `subprocess.run` dentro `esegui_ts`, non nel modulo che stai
testando.

---

## 4. La prossima dimensione: `(app)/dashboard/` — 1.749 righe

L'aggancio pronto: **`MolAndamento`** in `dashboard/kpi-block.tsx`, il gemello
mai estratto di `calcolaSparkline` (che invece è già in `catena-confronti.ts`,
testato). Due implementazioni della stessa curva, una coperta e una no: se
divergono, nessuno lo sa.

Prima di pianificare, verifica **con un grep, non a memoria**:
- quali file di `dashboard/` importano già da `lib/` — e poi **apri quelli**, per
  non ripetere l'errore del §2;
- se `MolAndamento` è davvero l'unica logica non estratta.

---

## 5. Regole di lavoro che non cambiano

**Si fotografano i bug, non si correggono** (`// ANOMALIA FOTOGRAFATA` +
`test_fotografa_*`). Un fix ha bisogno della sua finestra di deploy. Ma la
fotografia dev'essere **misurata**: l'1/9 il primo commento su `arrotonda2`
dava una causa sbagliata («`Math.round` verso +∞») presa per ragionamento invece
che per misura — quella vera è la rappresentazione binaria (`1.005*100` vale
`100.49999…`). **Un commento sbagliato su un'anomalia fotografata è peggio di
nessun commento**, perché chi farà il fix lo leggerà come specifica.

**Il gate del diff non basta.** `git diff | grep '^+'` prova che la logica è
*uscita* dal `.tsx`, non che sia *arrivata intatta*. La prova vera è l'oracolo:
prendere l'espressione originale da `git show HEAD:<file>`, ricostruirla come
`.mjs` in scratchpad e confrontarla col modulo nuovo su input avversari. L'1/9:
734 esiti sui margini e ~2.593 celle sulla pivot, 0 divergenze.

⚠️ **Un oracolo è forte quanto il parametro più trascurato.** Il mio generava
valori avversari sugli *importi* (`-0`, `NaN`, `1e9`) ma sul *conteggio* passava
solo interi plausibili — e lì si nascondeva una divergenza vera
(`!(n > 0)` ≠ `n <= 0` per NaN), trovata dal reviewer. Se pensi «questo
parametro è un intero, cosa vuoi che succeda», è **esattamente** quello da
generare avversario.

**Mutazione**: harness in scratchpad, **validato sui due lati ogni volta**
(un mutante palese deve morire, un commento cambiato deve sopravvivere).
`rc=1` = ucciso, `rc>=2` = errore d'uso che ferma il giro. `pytest-timeout` **non
è installato** — `--timeout` fa uscire pytest con `rc=4`, che un harness ingenuo
legge come successo.

⚠️ **Il `code-reviewer` può mutare il file VERO del repo.** L'1/9 ha montato due
mutanti su `catena-export.ts` nel working tree (`find` → `findLast`,
`"margine_perc"` → `"margine_eur"`). Conseguenze: un mutante quasi committato, e
una suite in parallelo che misurava un albero mutato (risultato scartato).
**Guarda `git diff` prima di ogni commit** durante una review, e non lanciare la
suite mentre il reviewer lavora. Non ripristinare a metà del suo giro — falsi il
suo esito: avvisalo, aspetta che finisca, poi `git checkout --`.

**Ogni cifra nei .md deve dire cosa conta.** L'1/9 il reviewer ha bloccato su
«282 test non corrisponde a nessuna misura» contandone 269: aveva omesso un file
dell'area. Il 282 era giusto, ma **due lettori indipendenti hanno ottenuto due
numeri** perché la cifra non elencava gli addendi. Un numero giusto che nessuno
può ricostruire è fragile quanto uno sbagliato: scrivi `95+61+50+63+13`, non
`282`.

**Chiusura §5bis**: bilancio mutanti coi sopravvissuti *elencati col motivo*,
suite verde, `npx tsc --noEmit`, `/code-reviewer` sul cumulativo (riproduci ogni
rilievo prima di accettarlo), verbale, `AUDIT_COPERTURA.md` **ri-misurato**,
`check_documentazione.py`, commit doc+codice insieme, prompt nuovo, **dire la
coda a Mattia senza pushare**.

---

## 6. Come si parla a Mattia

Non legge codice: decide **cosa** si fa. Alle domande di stato — **una riga di
verdetto, max 3 punti, una domanda, «Vuoi il dettaglio?»**. Tetto ~10 righe,
niente tabelle né percorsi con numero di riga. Un tuo errore si corregge in
**mezza riga**, non in un paragrafo.
