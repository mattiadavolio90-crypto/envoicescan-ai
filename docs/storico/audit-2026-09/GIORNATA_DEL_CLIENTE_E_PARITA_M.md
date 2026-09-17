# L9 — La giornata del cliente e la parita' `/m` · 17/09/2026

**Nona e ultima lente.** Le otto precedenti hanno guardato l'app per proprieta'
tecniche (isolamento, tempo, ingresso ostile, cache). Questa la guarda **con gli
occhi di chi la usa**: i percorsi che un cliente fa in una giornata, e la
domanda se il telefono gli dice le stesse cose del desktop.

| | |
|---|---|
| Perimetro | **22 pagine desktop + 7 mobile**, 171 route API, 10 componenti client mobile che caricano dati |
| Difetti corretti | **4** (stati vuoti mobile che affermavano il falso) |
| Presidi | +12 casi in `tests/test_esito_caricamento_frontend.py` (45 → 53 nel file) |
| Mutanti | **6 provati, 6 uccisi** — di cui **1 sopravvissuto al primo giro** e poi chiuso |
| Suite | 14.184 → **14.196 verdi**, 0 rossi |

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

### Blocco KPI che sparisce — verificato, non e' una disparita'

Su `/m` il blocco dei conti fa `if (!kpi) return null`. Sembrava un silenzio
mobile, ma il desktop fa `{kpi && !kpiVuoto && ...}`: **stesso comportamento**.
E' una scelta coerente fra i due frontend, non un difetto. Scartato.

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
| `m/turni/mobile-turni.tsx` | «Nessun turno per questo mese.» |

Tutti e quattro hanno la stessa forma: `loading ? skeleton : lista.length === 0 ?
"Nessun…"`. **Manca il terzo ramo.**

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
