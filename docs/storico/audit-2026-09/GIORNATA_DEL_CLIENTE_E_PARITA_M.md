# L9 — La giornata del cliente e la parita' `/m` · 17/09/2026

**Nona e ultima lente.** Le otto precedenti hanno guardato l'app per proprieta'
tecniche (isolamento, tempo, ingresso ostile, cache). Questa la guarda **con gli
occhi di chi la usa**: i percorsi che un cliente fa in una giornata, e la
domanda se il telefono gli dice le stesse cose del desktop.

| | |
|---|---|
| Perimetro | **22 pagine desktop + 7 mobile**, 171 route API, 10 componenti client mobile che caricano dati |
| Difetti corretti | **4** (stati vuoti mobile che affermavano il falso) |
| Presidi | **+32 casi** in `tests/test_esito_caricamento_frontend.py` (**41 → 73** nel file) + `statoLista()` in `lib/esito-caricamento.ts` |
| Mutanti | **20 provati, 20 uccisi** in quattro giri — di cui **6 sopravvissuti** al primo tentativo del rispettivo presidio |
| Suite | 14.184 → **14.216 verdi**, 0 rossi |

---

## Come e' stata tagliata la lente

L9 e' l'unica delle nove **senza un piano scritto**: la riga di coda diceva
«account nuovo percorso in ordine cliente; stati vuoti, CTA morte, coppie
desktop/mobile». Il perimetro e' stato quindi misurato prima di guardare.

**La prima misura ha corretto la premessa.** «Parita' `/m`» suggerisce uno
specchio: 22 pagine desktop, 7 mobile. Ma il mobile **non e' una riduzione del
desktop** — e' un prodotto diverso, con una sua navigazione a 5 tab (Home,
Agenda, Movimenti, Assistente, Profilo) e nomi che sul desktop non esistono.
Cercare «le 15 pagine mancanti su `/m`» avrebbe prodotto un elenco di non-difetti.

La domanda utile e' diventata: **dove il mobile promette qualcosa che non
mantiene**, cioe' dove dice al cliente una cosa diversa — e piu' sbagliata — di
quella che gli direbbe il desktop davanti agli stessi dati.

---

## Cosa e' stato guardato, e con quale esito

### CTA morte — cercate, non trovate

Rilevatore su tutti gli `href` / `router.push` / `redirect` **letterali** di
`apps/web/src`, confrontati con le **36 rotte pagina reali** (segmenti dinamici
inclusi, route group `(app)`/`(mobile)` normalizzati): **0 destinazioni
inesistenti**.

Le destinazioni **costruite** sono state lette a mano, perche' il rilevatore non
le vede: sono tutte `${pathname}?${params}` (la pagina corrente con filtri
diversi) o `mailto:`. Nessuna inventa un percorso.

Un caso meritava una verifica vera, perche' e' il tipo di CTA che marcisce in
silenzio: `trigger-hint.tsx` manda a `/assistenza?servizio=<key>`. Verificato
**nella cartella d'arrivo** e non dedotto dal nome: `marketplace.tsx` legge
davvero quel parametro, ci scrolla e apre il dialog. E le chiavi emesse sono
legate a quelle accettate **dal tipo** (`servizioKey: Servizio["key"]`), quindi
una chiave inventata non compila.

### Blocco KPI che sparisce — scelta diversa dal desktop, accettata

Su `/m` il blocco dei conti fa `if (!kpi) return null`: **un** ramo. Il desktop
ne ha **tre**, via `statoBlocchi(kpi, salute)` in `lib/home-kpi.ts`:

| Situazione | Desktop | Mobile |
|---|---|---|
| worker giu' (`!kpi && !salute`) | `BlockRetry` + skeleton — **riprova** | blocco assente |
| cliente senza dati (`has_data === false`) | card «Nessun dato di margine per questo mese» | `KpiBlock` |
| dati ok | `KpiBlock` | `KpiBlock` |

**Il primo giro di questa lente lo aveva dichiarato «stesso comportamento»,
guardando solo l'ultima riga della catena** (`{kpi && !kpiVuoto && ...}`), che
presa da sola somiglia a `if (!kpi) return null`. Sopra c'e' un early return che
il mobile non ha: rilievo del code-reviewer, corretto qui.

Resta **scartato come difetto**, ma per una ragione diversa da quella scritta
prima: un blocco **assente** non afferma nulla di falso, mentre «Nessun incasso
inserito» si'. E' una degradazione piu' povera, non una bugia — e sulla PWA puo'
essere deliberata. Se un giorno si volesse allineare, l'helper ha gia'
`kpiNonDisponibile` per questo. **Scelta diversa, accettata; non «identica».**

### Briefing mobile — gia' corretto

`Nessuna azione da fare oggi.` era nella lista dei sospetti. Leggendo la pagina:
`if (!briefing)` mostra gia' «Impossibile caricare il briefing. Riprova piu'
tardi.» Falso positivo del censimento, scartato.

---

## I 4 difetti — lo stesso difetto, quattro volte

**Il fix del 3/9 (R10) era arrivato al desktop e non a `/m`.**

L'helper `lib/esito-caricamento.ts` esiste dal 3 settembre e distingue «non c'e'
niente» da «non sono riuscito a chiedere». Lo usano **11 file**: dieci sul
desktop, **uno solo** sul mobile (`m/notifiche`).

Censiti i 6 file mobile con uno stato vuoto, **4 non distinguevano i due casi**:

| File | Cosa diceva col worker giu' |
|---|---|
| `m/diario/mobile-incassi.tsx` | «Nessun incasso inserito in questo mese.» |
| `m/diario/mobile-spese.tsx` | «Nessuna spesa extra in questo mese.» |
| `m/diario/mobile-diario.tsx` | «Nessun evento per questo giorno.» |
| `m/turni/mobile-turni.tsx` | «Nessun turno per questo mese.» + altri **2 rami** (vedi sotto) |

Tutti hanno la stessa forma: `loading ? skeleton : lista.length === 0 ?
"Nessun…"`. **Manca il terzo ramo.**

> ⚠️ **Il primo giro contava i FILE, non gli stati vuoti** — e su
> `mobile-turni.tsx` ne ha visto uno dei tre. Vedi «Il secondo giro» piu' sotto:
> gli stati vuoti da correggere erano **6**, non 4.

**Perche' e' un difetto vero e non teorico.** Tre cose misurate:

1. Lo stato iniziale e' `null` / `[]` in tutti e quattro. Al **primo**
   caricamento fallito — cioe' all'apertura della pagina, il caso piu' comune —
   la lista e' vuota e la frase falsa compare.
2. Il fallimento non e' raro: il repo stesso lo documenta in
   `esito-caricamento.ts` — «Railway spegne il worker quando non e' usato, e il
   risveglio sfora gli 8s di timeout».
3. Il toast d'errore c'e', ma **sparisce dopo pochi secondi** e lascia in pagina
   l'affermazione falsa. Chi guarda un attimo dopo legge solo quella.

Il contrasto col desktop e' diretto: su `/scadenziario` la stessa situazione dice
«Non e' stato possibile caricare le scadenze. Riprova fra un momento.»

**Il fix** riusa l'helper esistente invece di inventare un pattern nuovo: un flag
`fallito` che si alza nel `catch` e si abbassa sul successo, e un terzo ramo
`mostraGuasto(fallito, lista.length)` **prima** di quello del vuoto.

---

## Il mutante sopravvissuto — e perche' e' il punto di questa lente

Il primo presidio estendeva la guardia strutturale esistente: «questi file
chiamano `mostraGuasto`». Verde. Poi il mutante:

```
} catch {
  setFallito(false);   // invece di true
```

**Sopravvissuto.** Il file continua a importare e chiamare `mostraGuasto`, la
guardia di delega resta verde — e il cliente rilegge «Nessun incasso inserito»
col worker giu'. Il presidio provava che il codice *nomina* la funzione, non che
la decisione *funzioni*.

Chiuso con due presidi nuovi, che leggono la **riga normalizzata** e non una
sottostringa (`test_esito_caricamento_frontend.py` documenta gia' perche': un
`? false : false` contiene il testo cercato):

- **le due transizioni del flag** — `setFallito(true)` nel catch *e*
  `setFallito(false)` sul successo. Senza il secondo, dopo un retry riuscito il
  messaggio d'errore resta appiccicato a una lista che ora ha dati.
- **l'ordine dei rami** — `mostraGuasto` valutato **prima** di `length === 0`.
  Invertendoli il ramo del guasto diventa **irraggiungibile**: una lista fallita
  e' sempre anche vuota, quindi il primo ternario la cattura per sempre.

### I sei mutanti

| # | File | Mutazione | Esito |
|---|---|---|---|
| 1 | incassi | tolto `mostraGuasto` (ritorno al pre-fix) | ucciso |
| 2 | incassi | `setFallito(true)` → `(false)` | **sopravvissuto**, poi ucciso |
| 3 | incassi | tolto `setFallito(false)` dal successo | ucciso |
| 4 | incassi | invertito l'ordine dei due rami | ucciso |
| 5 | spese | `setFallito(true)` → `(false)` | ucciso |
| 6 | diario / turni | `setFallito(true)` → `(false)` | ucciso (×2) |

Ogni mutante e' stato verificato come **realmente applicato** (hash del file
cambiato) e ogni ripristino confrontato per hash col file pre-mutazione.

---

---

## Il secondo giro — cosa ha trovato il code-reviewer

La prima stesura di questa lente e' stata dichiarata chiusa e **bocciata dalla
review**. Tre rilievi veri, tutti corretti prima del commit definitivo.

### 1. Il censimento contava i file, non gli stati vuoti

`mobile-turni.tsx` ha **tre viste** mutuamente esclusive, ognuna con la sua
lista e il suo stato vuoto. Il flag era stato collegato **alla prima soltanto**:

| Riga | Vista | Lista | Primo giro |
|---|---|---|---|
| ~1054 | mese | `riepilogoMese` | ✅ corretta |
| ~1128 | mensile | `righeMensili` | ❌ scoperta |
| ~1193 | **giornaliera — il DEFAULT** | `turniGiorno` | ❌ scoperta |

`modalita` parte da `"giornaliero"`: **il primo giro aveva corretto il ramo che
si raggiunge dopo aver toccato il selettore, e lasciato scoperto quello che si
apre da solo.** Un `grep -c "length === 0"` sul file ne restituiva tre; il
censimento ne aveva contato uno per file.

Gli stati vuoti corretti sono quindi **6**, non 4 — su 4 file.

### 2. I presidi erano neutralizzabili: i mutanti evasivi

I sei mutanti del primo giro erano tutti della stessa famiglia — **cancellare o
invertire un token che il test cerca esplicitamente**. Nessuno costruito
*sapendo* cosa il test legge. Il reviewer ne ha scritti due che sopravvivevano:

```
) : (false && mostraGuasto(fallito, voci.length)) ? (   // il ramo non si accende
} finally { setFallito(false); setLoading(false); }     // il flag muore a ogni giro
```

Entrambi **ripristinano il difetto intero con la suite verde**. Il secondo e' il
peggiore: soddisfa alla lettera un test che chiede «esiste `setFallito(true)` ed
esiste `setFallito(false)`», mentre il reset a ogni giro cancella il primo.

**La correzione non e' stata un test in piu', ma spostare la decisione.** La
scelta fra caricamento / guasto / vuoto / dati e' ora `statoLista()` in
`lib/esito-caricamento.ts`, che i test **eseguono** (8 casi + l'invariante «con
un guasto non si dice mai vuoto»). Nei `.tsx` resta una riga che la chiama e tre
rami che ne confrontano il risultato.

Restano tre guardie di **forma** sul sorgente, per ciò che l'harness non può
eseguire — e una di esse e' nata da un mutante sopravvissuto **alla guardia
stessa**:

| Guardia | Mutante che uccide |
|---|---|
| nessun `length === 0` vivo, e `#vuoto == #guasto` | un ramo dimenticato in una delle tre viste |
| nessun `false &&` su un ramo `=== "guasto"` | il ramo spento da una costante |
| nessun `setFallito` dentro un `finally` | il flag riazzerato a ogni giro |
| ogni `statoLista({...})` passa `caricamentoFallito: fallito` | **`caricamentoFallito: false` letterale**, che spegne il guasto di **una vista sola** |

### 3. «Identico al desktop» era piu' forte del vero

Vedi la sezione sul blocco KPI, riscritta.

### I sette mutanti del secondo giro

| # | Dove | Mutazione | Esito |
|---|---|---|---|
| A | spese `.tsx` | `(false && stato === "guasto")` | ucciso |
| B | spese `.tsx` | `setFallito(false)` nel `finally` | ucciso |
| C | `lib/` | `statoLista` ritorna sempre `"vuoto"` | ucciso |
| D | `lib/` | tolto `if (caricamento)` — lo skeleton non vince | ucciso |
| E | turni `.tsx` | tolto il ramo guasto della **vista di default** | ucciso |
| F | turni `.tsx` | `caricamentoFallito: false` sulla vista di default | **sopravvissuto**, poi ucciso |
| G | `lib/` | `righeCaricate > 0` → `>= 0` | ucciso |

**7 su 7**, ognuno verificato come applicato davvero (hash) e ogni ripristino
confrontato per hash.

---

## Il terzo giro — quando la correzione toglie una copertura

La seconda stesura e' stata **bocciata di nuovo**, e il rilievo principale e' il
piu' istruttivo dei tre giri.

### La regressione: sostituire invece di affiancare

Spostando la decisione in `statoLista` avevo **sostituito** il vecchio presidio
sulle transizioni del flag, invece di affiancarlo. Risultato: il mutante
storico di questa lente — `setFallito(true)` → `(false)` nel `catch`, quello che
il verbale chiamava «il mutante che conta» — **e' tornato a sopravvivere**, con
69 test verdi. Dopo la correzione era **rosso**; dopo il "miglioramento", verde.

La ragione e' netta: `statoLista` decide bene **dato** `caricamentoFallito`, ma
quel booleano **nasce nel `catch` di un `.tsx`**, che l'harness non esegue.
L'estrazione ha chiuso i mutanti che agiscono *sulla decisione* e ha scoperto
quello che agisce *sul suo input*. **Le due coperture sono ortogonali, non
alternative.**

### I mutanti scritti da fuori

Il reviewer ne ha costruiti quattro **conoscendo** le quattro guardie. Due
uccisi, due sopravvissuti — piu' il ritorno del mutante storico:

| # | Mutante | Primo esito | Ora |
|---|---|---|---|
| I | `setFallito(true)` → `(false)` nel catch | **sopravvissuto** | ucciso |
| J | `caricamentoFallito: falsoFlag` (costante via variabile) | ucciso da (d) | ucciso |
| K | state rinominato + `const fallito = false;` (**shadowing**) | **sopravvissuto** | ucciso |
| H | i due **messaggi scambiati** fra ramo guasto e ramo vuoto | **sopravvissuto** | ucciso |

**K** soddisfaceva la guardia (d) alla lettera — `caricamentoFallito: fallito` e'
testualmente presente su tutte e tre le chiamate — mentre spegneva il guasto in
**tutte** le viste insieme: (d) verificava il *nome* dell'argomento, non la sua
*provenienza*. Chiuso dal ripristino di I, che ancora l'identita'
`fallito` ↔ `setFallito`.

**H** e' il piu' sottile: nessuna guardia guardava **dentro** il ramo. Scambiando
i due testi il cliente col worker giu' rilegge «Nessuna spesa extra in questo
mese.» e tutte le guardie restano verdi. Chiuso con un presidio
sull'**accoppiamento ramo/messaggio** (le parole «Non e' stato possibile» e
«Riprova» devono stare nel ramo del guasto e **non** in quello del vuoto).

### Le cifre, di nuovo

Due errori nello stesso file: la riga «Suite» della *riga che conta* era rimasta
a 14.768/14.184 mentre il commit accanto aggiornava l'hash certificato; e la
frase «il blocco KPI si comporta **identico al desktop**» era **sopravvissuta
accanto alla sua stessa correzione** — accodata, non sostituita. Chi leggeva la
riga trovava entrambe le versioni. E' [[cifra-vive-in-piu-punti]] applicata a una
frase invece che a un numero.

---

## Il quarto giro — l'invariante globale e la finestra fissa

Terza review, altri due difetti nei **presidi** (il codice di produzione era
ormai corretto).

### Il conteggio dei rami si pareggia duplicando

La guardia chiedeva `#vuoto == #guasto` **su tutto il file**. Il reviewer l'ha
aggirata togliendo il ramo guasto della **vista di default** dei turni e
duplicando quello di un'altra vista: conteggio 3/3, **69 test verdi**, e il
cliente che apre `/m/turni` rilegge «Nessun turno per questo giorno.» col worker
giu'. Riprodotto: sopravviveva davvero.

E' [[assert-su-aggregato-nasconde-errori-che-si-compensano]] — la somma torna
perche' due errori opposti si annullano. **L'invariante era globale mentre il
difetto e' per-vista**: la stessa classe di errore del primo giro (censire
l'unita' sbagliata), spostata dal file al conteggio aggregato.

Sostituita da una guardia che **lega ogni variabile ai suoi rami**: per ogni
`statoX` assegnato da `statoLista`, devono esistere sia `statoX === "guasto"`
sia `statoX === "vuoto"`. Duplicare non aiuta piu': manca il nome giusto.

### La finestra di tre righe era porosa in due direzioni

Il presidio sull'accoppiamento ramo/messaggio leggeva `righe[i:i+3]`. Bastava
riformattare il JSX su piu' righe — come farebbe Prettier, o un messaggio piu'
lungo — per bucarlo **in entrambi i sensi**:

- **falso positivo**: un ramo corretto col testo alla quarta riga faceva
  fallire il test. Un presidio che grida su una riformattazione innocua e'
  un presidio che viene disattivato al primo allarme.
- **falso negativo**: il testo di guasto nascosto nel ramo del vuoto, spinto
  oltre la finestra, passava. Un mese davvero vuoto annunciato come errore.

Ora il blocco si chiude sul **delimitatore strutturale** (`) : `, che apre il
ramo seguente) invece che su un conteggio di righe. Entrambe le direzioni
verificate: il mutante muore, la riformattazione resta verde.

### Le cifre, ancora

La baseline del file di test era dichiarata **45** ed era **41** (misurata
eseguendo `pytest --collect-only` su `3a040e7~1`). Il «+24 presidi» derivava da
`69 − 45`, cioe' da una **sottrazione su una base mai misurata**: i presidi di
L9 sono **32** (41 → 73). E `INDICE_LENTI` conservava la frase «identico al
desktop» — corretta due giri prima nel registro, **non qui**: la correzione era
stata applicata a un file su due.

### I mutanti dei quattro giri

| Giro | Provati | Sopravvissuti al primo tentativo |
|---|---|---|
| 1 | 6 | 1 (`setFallito(true)` → `(false)`) |
| 2 | 7 | 1 (`caricamentoFallito: false` letterale) |
| 3 | 4 (scritti **da fuori**) | 3 (ritorno del mutante storico, shadowing, messaggi scambiati) |
| 4 | 3 (scritti **da fuori**) | 2 (ramo duplicato, finestra porosa) |

**20 provati, 20 uccisi.** Sette sono sopravvissuti al primo tentativo del
presidio che avrebbe dovuto ucciderli — e **cinque dei sette** li ha scritti il
reviewer, non io.

### La lezione

Quattro errori di metodo, non di logica.

1. **Il perimetro si conta sull'unita' che ha il difetto** — qui lo stato vuoto,
   non il file che lo contiene.
2. **Una batteria di mutanti scritta da chi ha scritto il presidio misura solo
   cio' che il presidio gia' guarda.** Su 4 mutanti scritti da fuori, 2 sono
   passati al primo colpo. Vanno chiesti a qualcun altro, o costruiti partendo
   dal **test** e non dal codice.
3. **Migliorare un presidio non autorizza a rimuoverne un altro.** Estrarre la
   decisione in `lib/` era giusto, ma ha coperto un insieme *diverso*, non piu'
   grande: togliendo il vecchio assert ho riaperto il difetto che quella lente
   era nata per chiudere. Quando si sposta una logica, il presidio vecchio si
   **affianca** finche' non si e' dimostrato che il nuovo lo include.

4. **Un invariante aggregato non prova una proprieta' per-elemento.**
   `#vuoto == #guasto` si pareggia duplicando; la forma robusta lega ogni
   elemento alla sua proprieta'. E un blocco di testo si delimita su un
   **delimitatore**, mai su un numero fisso di righe: la finestra sbaglia in
   entrambe le direzioni, e il falso positivo e' il piu' dannoso dei due perche'
   fa disattivare il presidio.

Il confine resta dichiarato: `statoLista` e' eseguita, il resto e' lettura di
forma. Una riscrittura completa dei testi, o un refactoring che rinomina tutto in
modo coerente, passerebbe ancora — per chiuderla servirebbe un runner che renda i
componenti.

## Cosa NON e' stato guardato — e resta una scelta

- **Rendering, hook, stato, effetti.** L'harness esegue `lib/`, non i `.tsx`
  (`tests/helpers_ts.py` lo dichiara). I presidi sui quattro client leggono la
  **forma** del codice: uccidono i mutanti realistici elencati sopra, ma non
  sostituiscono un test che renda il componente. Per chiuderlo davvero servirebbe
  un runner frontend — che e' una **decisione esplicita di Mattia** (punto 9 del
  ciclo 2026-08: un runner in `apps/web/package.json` farebbe partire il deploy
  Vercel a ogni test).
- **La giornata del cliente end-to-end su un account nuovo.** Non e' stata
  eseguita: richiede di creare un account vero in produzione (il locale punta al
  DB cloud reale). I percorsi sono stati letti, non percorsi.
- **Accessibilita', gesture mobile, PWA offline.** Fuori perimetro.
- **Le altre 3 schermate mobile** (`m/chat`, `m/impostazioni`, `m/page`) non
  hanno liste con stati vuoti: nulla da distinguere.

---

## Quando si riapre

- Quando nasce un **componente mobile che carica dati e mostra una lista**: va
  aggiunto a `_CLIENT_MOBILE` nel test, o il difetto rientra dalla finestra.
  Oggi i client mobile che fanno fetch sono **10**; i 4 con una lista sono
  presidiati, gli altri 6 non hanno stati vuoti da distinguere.
- Quando si aggiunge una pagina a `/m`: la domanda non e' «esiste anche sul
  desktop?» ma «dice al cliente qualcosa di diverso davanti agli stessi dati?».
- Se un giorno `apps/web/` avesse un runner di test, i quattro presidi di forma
  andrebbero sostituiti da test che eseguono il rendering.
