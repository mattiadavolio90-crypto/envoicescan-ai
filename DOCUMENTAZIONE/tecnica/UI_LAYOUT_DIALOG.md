# UI — layout, dialog e trappole CSS

> Storico delle passate grafiche su ONEFLUX. Serve a **non rifare da capo**
> l'audit: qui c'è cosa è già stato controllato, cosa è stato corretto, e
> soprattutto **le classi di difetto** che si ripresentano.
>
> Ultima passata: **9 settembre 2026** — tema chiaro (§7).
> Passata precedente: **28 agosto 2026** — audit completo sui dialog.

---

## 1. La regola che spiega quasi tutti i bug trovati

`DialogContent` (in `apps/web/src/components/ui/dialog.tsx`) è una **grid** con
`p-4` e `gap-4` di default. Da questo discendono due trappole distinte.

### Trappola A — il footer che sparisce (asse verticale)

Con `p-0` + `max-h-[…vh]` + `overflow-hidden`, se i figli sono impilati **senza
`flex flex-col`**, il footer finisce oltre il bordo clippato e diventa
invisibile. Il bottone c'è nel DOM, l'utente non lo vede.

Peggiora se l'area scrollabile ha un'altezza calcolata a mano tipo
`max-h-[calc(90vh-5rem)]`: quel `-5rem` presume un header di 80px, ma se
l'header è `flex-wrap` con select e bottoni, su viewport stretti va a capo,
supera i 5rem, e il fondo della lista viene tagliato **senza scrollbar**.

**Pattern corretto** (riferimento: `AggiungiProdottiDialog` in
`apps/web/src/app/(app)/analisi-e-tag/analisi-e-tag-client.tsx`):

```
DialogContent  →  flex flex-col gap-0 p-0 max-h-[…vh]
  header       →  shrink-0
  body         →  min-h-0 flex-1 overflow-y-auto
  footer       →  shrink-0
```

Le altezze si **derivano**, non si calcolano a mano: `min-h-0 flex-1` si adatta
all'header reale, `max-h-[calc(…-5rem)]` no.

### Trappola B — il contenuto che sfonda (asse orizzontale)

`min-width: auto` è il default dei flex/grid item: un item **si rifiuta di
scendere sotto la larghezza intrinseca del contenuto**, e quindi ignora il
`max-width` del genitore.

Conseguenza controintuitiva: **`truncate` da solo non basta mai**. Se un
antenato può allargarsi, il `truncate` sulla foglia non ha nessun vincolo da
rispettare e non scatta.

> **Un `truncate` senza catena di `min-w-0` sopra è decorativo.**

`min-w-0` va messo su **ogni** contenitore intermedio fino a quello che ha una
larghezza vera — non solo sulla foglia. Questo errore è stato commesso due
volte nella stessa sessione: prima nel dialog "Ripartisci sul gruppo", poi
nelle card di `/catena`. In quest'ultimo caso l'ellissi veniva persino
renderizzata, ma **fuori schermo**: l'utente vedeva il nome tagliato netto
contro il bordo.

---

## 2. Le tre classi di difetto — grep da rifare a ogni passata

Sono controlli meccanici. Coprono la classe di bug, non i singoli esemplari.

### 2.1 Catena `min-w-0` sopra ogni `truncate`

```bash
grep -rn "truncate" --include=*.tsx apps/web/src
```

Per ogni risultato: risali i parent fino al contenitore con larghezza vera.
**Ogni** antenato `flex-1` deve avere `min-w-0`. Chi ha `overflow-*` è già a
posto (contiene o scrolla), non serve toccarlo.

### 2.2 `truncate` su valori numerici — è sempre sbagliato

```bash
grep -rn "truncate" --include=*.tsx apps/web/src | grep -E "tabular-nums|Euro|toFixed"
```

Su un importo l'ellissi **non informa**: `3.01…` non dice nulla. Soluzione: far
scalare il font col contenitore (`@container` + `clamp(...,cqw,...)`), come in
`apps/web/src/app/(app)/margini/kpi-bar.tsx`. Mai troncare un numero.

### 2.3 Elementi `sticky` con sfondo trasparente

```bash
grep -rn "sticky" --include=*.tsx apps/web/src | grep -E "bg-[a-z]+-[0-9]+/[0-9]+"
```

Una cella sticky deve coprire ciò che le scorre sotto: lo sfondo va **opaco**,
mai `/8` o `/40`. Per conservare una tinta colorata senza perdere l'opacità:
`bg-[color-mix(in_oklab,var(--color-sky-500)8%,var(--color-card))]`.

### 2.4 Bonus — `z-index` e stacking context

Un `z-index` su un figlio **non scavalca mai** il contesto creato dal padre. Se
`thead` ha `z-10`, lo `z-20` di un `th` ordina solo *dentro* il thead: le celle
sticky del corpo (stesso `z-10`, ma dopo nel DOM) vincono e coprono l'angolo
dell'header. Serve alzare il **padre**, non il figlio.

---

## 3. Cosa è già stato fatto — passata del 28/08/2026

Audit su **tutti i 65 `DialogContent`** dell'app. Corretti:

| Area | Difetto |
|---|---|
| `analisi-e-tag-client.tsx` | wizard nuovo tag senza vincolo di altezza: bottoni fuori schermo |
| `gruppo-tag-section.tsx` | footer invisibile (il bug segnalato dal cliente) + colonne che scorrevano insieme |
| 7 dialog Catena e `coda-da-assegnare.tsx` | `max-h-[calc(…-5rem)]` hardcoded: fondo lista tagliato |
| 3 dialog `m/diario/` | nessun `max-h`: con la tastiera aperta i bottoni uscivano |
| `ricetta-editor.tsx` | `overflow-y-auto` sul `DialogContent`: footer che scorreva via |
| `finestra-spesa-pv.tsx`, `finestra-margini-coperti.tsx` | header tabella coperto (stacking context) |
| `calcolo-tab.tsx`, `coperti-tab.tsx` | colonna sticky trasparente: numeri sovrapposti |
| `kpi-bar.tsx` | `truncate` su importi: sei KPI illeggibili |
| `sintesi-catena.tsx`, `app-sidebar.tsx` | `min-w-0` mancante sui contenitori intermedi |
| ~15 file | `flex-1 truncate` senza `min-w-0` |

### Verificato e scartato — non rifare

- **`DialogFooter`** (`dialog.tsx`) ha `-mx-4 -mb-4`, che presume un genitore
  con esattamente `p-4`. Difetto teorico: **0 file su 13** lo usano con un
  genitore diverso. Toccare il primitivo condiviso da 65 dialog per questo è
  rischio senza guadagno.
- **Dialog di Margini** con `showCloseButton={false}` e senza `max-h`: hanno
  una **X custom nell'header**, restano chiudibili. Sforano solo sotto i ~700px
  di viewport.

### Non ancora esplorato

Pagine, tabelle e form **fuori** dai dialog. Il mobile `/m` oltre ai dialog del
diario. Nessun audit sistematico è stato fatto lì.

---

## 4. Come verificare — il punto che conta di più

**Typecheck e lint non vedono i bug di layout.** In questa sessione un margine
sbagliato, una colonna trasparente e sei KPI tagliati passavano `tsc --noEmit`
ed `eslint` puliti. Sono difetti che **solo il rendering rivela**.

### Il metodo che ha funzionato: Claude nella sidebar di Chrome

Apri l'app in Chrome e usa l'estensione Claude nel pannello laterale, dandogli
una checklist di controlli. **Vede la pagina renderizzata e può misurare il
DOM** — cosa che Claude Code da terminale non può fare (in questo container
manca un browser: Playwright si installa ma il binario non parte, 11 librerie
di sistema mancanti e `apt` non disponibile).

Ha trovato bug reali che l'analisi statica non avrebbe mai visto, e ha prodotto
diagnosi corrette misurando le catene di parent. Ha anche suggerito i tre grep
della §2, che sono il lascito più utile di tutta la passata.

**Come impostarlo:**
- Dagli una checklist per aree, con percorsi espliciti nella UI
- Digli di **iniettare via DOM nomi lunghi** dove i dati reali sono corti: è
  così che sono emersi i bug di overflow
- **Regola tassativa**: su dati di clienti veri può aprire e guardare, mai
  salvare o confermare
- Chiedi che riporti misure (`clientWidth` vs `scrollWidth`, `boundingBox`),
  non impressioni

**Limiti noti:** non può ridimensionare una finestra massimizzata
(`resize_window` risponde "success" e non fa nulla) — vanno de-massimizzate a
mano. E non può simulare la tastiera mobile.

### Cosa resta solo umano

I dialog di `m/diario/` hanno un bug che si manifesta **solo con la tastiera del
telefono aperta**, che dimezza il viewport. Non riproducibile né da terminale né
in Chrome desktop: va guardato su un telefono vero.

### Verificare le classi Tailwind non standard

Con classi arbitrarie (`color-mix`, `clamp`, `@container`) il sorgente non
basta: `npm run build` con `.next` cancellata, poi cerca la classe nel CSS
generato sotto `.next/static/chunks/`. Senza `rm -rf .next` il build usa la
cache e non ricompila il CSS.

---

## 5. Nota di metodo

Prima di attribuire un bug a una modifica recente, **controlla `git log` sul
file**. Nell'ultima passata tre difetti erano stati segnalati come regressioni
dei fix appena deployati: la storia del repo ha mostrato che erano tutti
preesistenti, in file mai toccati da quella sessione. Erano semplicemente bug
che nessuno aveva mai guardato.

---

## 6. Errore di rete travestito da stato vuoto — passata del 28/08/2026

Non è un difetto di layout, ma è emerso dall'audit grafico ed è la stessa
famiglia: **la UI dice una cosa falsa e l'utente ci crede**.

### Il difetto

Il dialog "Spreco per categoria" (Catena → Margini e coperti → Categorie)
mostrava insieme il toast d'errore e il messaggio *"Nessun dato: servono coperti
e fatture F&B classificate nel periodo"* — cioè dava la colpa ai dati del
cliente per un errore del server, mandandolo a cercare coperti che non gli
servono.

La causa è strutturale, non locale: **tre stati logici (loading / errore /
vuoto) compressi in due stati React** (`loading`, `data | null`). Con
`data === null` usato insieme come valore iniziale, esito d'errore e caso "zero
righe", il render non può distinguerli e sceglie sempre il messaggio di dominio.

### La grep da rifare

```
.catch(() => setX(null))     → errore diventa "nessun dato"
.catch(() => setX([]))       → errore diventa lista vuota (e KPI a zero)
.catch(() => {})             → errore invisibile
r.ok ? r.json() : null       → i 5xx entrano nel ramo di successo, il catch non scatta
```

L'ultima è la più insidiosa: `: null` invece di `Promise.reject()` fa arrivare
un HTTP 500 nel `.then` come `data = null`, **bypassando il `.catch`**. Un
`.catch` scritto bene non serve a niente se il `.then` a monte inghiotte l'errore.

### I casi peggiori trovati (tutti corretti)

- `card-segnali.tsx` + gemello `m/briefing/mobile-catena.tsx`: su errore la card
  diceva *"Tutto sotto controllo, nessuna segnalazione"* — rassicurazione falsa
  proprio sulla card che esiste per avvisare
- `margini/analisi-tab.tsx`, `margini/calcolo-tab.tsx`: `giorni = []` alimenta
  `media`, `giorno migliore/peggiore` → un errore di rete produceva **KPI a
  zero** indistinguibili da un mese senza ricavi caricati
- `gruppo-tag-section.tsx`: una ricerca fallita diceva *"Nessun prodotto
  trovato"*, cioè "il prodotto non esiste"

### Il pattern corretto (già nel repo, non inventarne un altro)

Riferimenti: `catena/config-assistente-catena.tsx` (stessa cartella) e
`prezzi/score-tab.tsx` (stile del blocco d'errore).

1. Stato `loadError` **separato** da `data`
2. Fetch estratta in `carica()` riusabile dal bottone "Riprova"
3. **Non azzerare `data` nel catch** — un refetch fallito non deve cancellare
   dati validi già a schermo
4. `Promise.reject()`, mai `: null`
5. Tre rami di render: caricamento → errore + Riprova → vuoto

---

## 7. I 503 sulle prefetch RSC — verificato, non riproducibile

Segnalati come 503 "ripetuti e sistematici" sulle prefetch RSC di `/catena` e
`/catena/fatture` (richieste con `?_rsc=`). **Verificato il 28/08/2026: non
esistono lato server.** Nessun intervento fatto, e la ragione è questa.

Cosa dicono i log Vercel (progetto `oneflux-web`, 7 giorni, tutti i deployment):

- **Zero 503**, su qualunque rotta. Il breakdown status del deployment corrente
  è 200/304/307/401; quello con più errori è 200/304/307/502/401/500
- `/catena` e `/catena/fatture` rispondono **200 o 307**
- I soli 5× 502 in 7 giorni erano su `/analisi-fatture`, concentrati in ~1 minuto
  il 27/08 (14:52–14:53), con causa esplicita nei log:
  `[auth.me] worker fetch error: TimeoutError` → poi `502`. Un episodio di worker
  lento, non un bug di rotta

Cosa dice il codice:

- Nel codice applicativo esiste **un solo** 503: `apps/web/src/lib/auth.ts:74`,
  dentro `loginWithCredentials` — raggiungibile **solo dal flusso di login**
- **Non esiste `middleware.ts`** in `apps/web` (verificato): nessun percorso può
  emettere 503 su una richiesta di pagina o prefetch
- `verifySession` su timeout **non emette status**: ritorna
  `{ status: "unavailable" }` dopo 2 tentativi (fino a 2 × 12s), e
  `(app)/layout.tsx` renderizza "Servizio momentaneamente non raggiungibile"
  **con HTTP 200**

**Spiegazione più probabile di ciò che si è visto nel DevTools:** 503 del browser
durante un **redeploy**, quando il deployment precedente non è più servito.
Non lasciano traccia nei runtime log del nuovo deployment.

**Se si ripresentano:** catturare timestamp preciso + header `x-vercel-id` dalla
response, e rileggere i log su quella finestra. Senza quei due dati non sono
ricostruibili a posteriori.

> **Perché un 502 non catturato al momento è perso:** `services/worker_metrics.py`
> tiene la latenza **in-memory per processo** e si azzera a ogni redeploy. Non
> esiste storico p95 da consultare dopo. È anche il motivo per cui il 502 di
> `spreco-categorie` non è mai comparso nei log: quando è stato osservato,
> nessuno stava guardando.

---

## 7. Il tema chiaro — passata del 09/09/2026

Fino a qui ogni controllo grafico era stato fatto in **tema scuro**, che è il
default (`layout.tsx`, e `DEFAULT 'dark'` sulla colonna `users.tema`). Ma il
tema è una preferenza per account: al 9/9/2026 **2 clienti su 7 usano il
chiaro**, e uno dei due è fra i più grossi del parco (29.911 righe fattura).

Nove difetti trovati, **nessuno visibile in dark**. Il layout non c'entrava:
sono tutti contrasto, opacità e stacking.

### Perché il chiaro rompe cose che lo scuro non rompe

1. **`bg-*/opacità` su celle sticky.** Su fondo scuro un velo semitrasparente
   sembra opaco; su bianco lascia passare tutto. `bg-muted/40` su una cella
   sticky faceva trasparire le intestazioni dei mesi che le scorrevano sotto —
   mentre le `<td>` accanto, già opache, stavano bene. **Una cella sticky vuole
   un fondo pieno**, e su token si scrive `bg-[color-mix(in_oklab,var(--color-muted)40%,var(--color-card))]`.

2. **Le tinte `-500`/`-600` sono tarate sul fondo scuro.** In chiaro finiscono
   sotto AA: i KPI di Margini sono **16px/700**, che per WCAG **non è "large
   text"** (serve ≥18.66px bold), quindi la soglia è **4.5:1** e non 3:1.
   `orange-600` dava 3,58 e `emerald-600` 3,65 — proprio "Costi F&B" e "Margine
   Lordo". Regola: in light usare **`-700`**, lasciando `dark:` sulle `-400`.

3. **`text-primary` su fondo tinto.** `--primary` è azzurro a luminosità 0,685:
   su una cella di heatmap dava **1,79:1**, cioè invisibile — ed era il numero
   che la tabella esiste per far notare.

4. **Le scale di alpha si schiacciano.** La heatmap andava 5%→35% di `--primary`
   su trasparente: in chiaro **1,51:1 fra i due estremi**, con **8 salti su 11
   sotto 1,02:1**. Si distingueva "bianco" da "azzurrino", non l'intensità.
   Portata a 10%→70%. Stessa cosa per la colonna "Totale" all'8% (1,07:1 → 16%)
   e per l'overlay dei dialog (`bg-black/10` = 1,25:1 → `/25`).

5. **Bianco su bianco.** Gli header sticky di Catena erano `bg-popover` senza
   bordo: corretti in dark, invisibili in chiaro quando ci scorre sotto una riga
   chiara. Aggiunta una linea con `shadow-[0_1px_0_0_var(--color-border)]`
   (una `border-bottom` su `<thead>` non è affidabile con `border-collapse`).

### Il difetto peggiore non era un colore

Il contenitore del FAB "Chiedi a ONEFLUX" (`dashboard/chat-widget.tsx`) è
`fixed bottom-6 right-6` ma **senza larghezza**: da flex container si estendeva
per tutto il viewport, e la sua metà **invisibile a sinistra** intercettava i
click. In `/catena` il bottone "Vedi PV" non era premibile. Risolto con `w-fit`.

> **Lezione di metodo:** l'audit di agosto aveva già visto il FAB "che copre gli
> angoli delle card" e l'aveva classificato come difetto **estetico**. Era un
> bottone morto. Un elemento `fixed` senza larghezza esplicita va sempre
> verificato con `elementsFromPoint`, non a occhio.

### Come è stato verificato

Stesso metodo della §4 (Claude nella sidebar di Chrome), con **due differenze
che hanno fatto la qualità del risultato**:

- gli è stato chiesto di riportare **misure** (`getComputedStyle`, contrasti
  calcolati, `elementsFromPoint`), non impressioni. Tutti i numeri di questa
  sezione vengono da lì
- ha dichiarato **cosa non poteva misurare**: con un account a 1 sede `/catena`
  resta in caricamento, con 2 PV le tabelle non vanno mai in overflow
  orizzontale. Un audit che dice "questo non l'ho potuto vedere" vale più di uno
  che riporta tutto verde

### Cosa resta scoperto

- **Overflow orizzontale delle tabelle di catena**: servirebbe un account con
  ≥4 punti vendita. Con 2 PV `scrollWidth == clientWidth`, il caso non si dà.
- **Il dialog "Prodotti di «…»" in tema chiaro**: per aprirlo serve un tag di
  catena esistente, e crearlo significa scrivere sui dati del cliente. Misurato
  sull'equivalente mono-PV in `/analisi-e-tag`, stesso componente.
- **Viewport fisse** (1280, 1440): l'audit è stato fatto a finestra libera.
- **Il tema chiaro su `/m`** (mobile): mai guardato, né in questa passata né prima.

### Grep utili per questa classe di difetti

```bash
# celle sticky con fondo semitrasparente (devono essere opache)
grep -rn "sticky" --include=*.tsx apps/web/src | grep -E "bg-[a-z-]+/[0-9]+"

# tinte -500/-600 come colore di testo senza variante dark:
grep -rn "text-[a-z]+-[56]00" --include=*.tsx apps/web/src | grep -v "dark:"

# text-primary come colore di testo su fondi colorati
grep -rn "text-primary\b" --include=*.tsx apps/web/src
```

> **Nota sui test:** `tests/test_catena_confronti_frontend.py` fotografava i
> coefficienti esatti delle due heatmap. Cambiandoli si è colta l'occasione per
> aggiungere un test sull'**ampiezza** della scala (≥50 punti di alpha fra
> minimo e massimo) invece dei soli letterali: verifica la proprietà che serve —
> "la scala si legge" — e regge a una ritaratura futura. Provato per mutazione.
