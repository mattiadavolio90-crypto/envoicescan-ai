# Piano di coerenza visiva ONEFLUX

**Data:** 18/09/2026 · **Commit di partenza:** `b7e9dc0`
**Perimetro:** solo pagine cliente principali (`apps/web/src/app/(app)/`). Esclusi
admin, demo e `/m` (frontend separato, va allineato a mano in un secondo tempo).

**Origine:** analisi di 26 screenshot light+dark (`SCREEN APP 18.09/`) più misure
sul codice. Prosegue `analisi_carico_visivo_cliente.md` (16/09) e i fix del 17/09.

---

## 0. L'obiettivo

**Lavoro di sola estetica.** Non funzionalità, non calcoli, non dati: grafica.
Richiesta di Mattia (18/09, testuale):

> *«SOLO L'ESTETICA DELL'APP. SOLO GRAFICA. DOBBIAMO RENDERE L'APP INTUITIVA PER
> IL CLIENTE ANDANDO DOVE POSSIBILE IN MANIERA INTELLIGENTE A SNELLIRE,
> RIETICHETTARE O RINOMINARE, ELIMINARE E MODIFICARE. DOBBIAMO DARE COERENZA
> VISIVA IN ENTRAMBE LE MODALITÀ E L'APP DEVE AVERE ASPETTO MODERNO, QUINDI SE
> CI SONO SEZIONI GRAFICI O TABELLE CHE GRAFICAMENTE SONO MIGLIORABILI DEVI
> DIRMELO.»*

**Le quattro leve, e nessun'altra:** snellire (togliere peso visivo) ·
rietichettare (parole da ristoratore, non da commercialista) · eliminare (ciò che
non guadagna lo spazio) · modificare (grafici e tabelle fatti male).

**I tre obiettivi:**
1. **Intuitiva per il cliente** — il metro non è «è corretto?» ma «si capisce a
   colpo d'occhio?». Chi la usa è un ristoratore, non un analista.
2. **Coerenza light/dark** — il cambio tema dev'essere *solo* un cambio tema.
   Oggi non lo è (§1.2).
3. **Aspetto moderno** — dove grafici e tabelle sembrano un foglio Excel, va
   detto e proposto diversamente.

**Il vincolo che limita tutto:** *«non deve essere una ristrutturazione totale
perché la base dell'app è già molto bella esteticamente, deve migliorare»*.
La struttura resta. Si interviene su **colore, parole e densità**.

**Perché serve:** l'audit del 16/09 ha dato **6,7/10** di complessità visiva su
sei pagine, e su tutte e sei la risposta a *«sembra uno strumento semplice o
complicato?»* è stata **complicato**. L'app fa cose giuste ma **sembra**
difficile.

**Come si misura che ha funzionato:** non da quante righe si cambiano, ma dal
fatto che il cliente apra una pagina e capisca subito dove guardare.

---

## 1. Le tre diagnosi, misurate

### 1.1 Il colore non ha una gerarchia

| Misura | Valore |
|---|---|
| Classi colore hardcoded (tutto `src/`) | **1.350** |
| di cui sulle sole pagine principali | **759** (39 file) |
| `sky-*` scritto a mano | **322** |
| `text-primary` + `bg-primary` (il token vero) | 417 |
| Colori decorativi senza significato (violet/purple/pink/orange/teal/indigo) | **233** |
| Hex crudi (`#0ea5e9`…) nel codice | 77 |

Famiglie per frequenza: `sky` 322 · `amber` 302 · `emerald` 243 · `rose` 109 ·
`violet` 83 · `orange` 83 · `red` 80 · `purple` 38 · `pink` 27 · resto < 25.

**Il token `--primary` È l'azzurro ONEFLUX** (`#0ea5e9`, definito in
`globals.css` con la sua versione dark più chiara: `oklch 0.751` vs `0.685`).
Esiste ed è corretto. Ma 322 volte è stato scritto `sky-500` a mano: un azzurro
fisso, che non si adatta al tema. **È questa la causa del "l'azzurro a volte c'è
e a volte no".**

### 1.2 Dark e light divergono — ma non nella struttura

Misura: **zero** classi `dark:` che cambiano layout, spaziatura, dimensione o
visibilità. La struttura è già identica fra i due temi.

La divergenza è **tutta nell'opacità**:

```
bg-sky-500/10  →  su bianco: velo appena percepibile
                  su nero:   fondo tinto pieno e saturo
```

| | Classi colorate |
|---|---|
| **senza** controparte `dark:` | **1.309** |
| con variante `dark:` | 329 |

**L'80% dei colori dell'app non è mai stato verificato sul dark.** Il design è
tarato sul light e guardato al buio: nel dark ogni tinta si stacca dal nero e
sembra "più curato", ma è solo più visibile.

> Correzione rispetto alla prima lettura in chat: avevo detto "sono due design
> diversi". Non è vero, ed è una buona notizia — la struttura non va rifatta.

### 1.3 Le parole sono da commercialista

`= 1° Margine`, `= 2° Margine (MOL)`, `Ricavi IVA 10%`, `Q.tà`,
`INCID. FATTURATO`, `Vs media`, `Righe`. Un ristoratore sa cosa incassa e cosa
spende; "2° Margine" non è italiano, è gergo contabile.

**Decisione di Mattia (18/09):** le rinomine si possono fare senza vincoli — i
clienti sono pochi e usano poco l'app. È il momento giusto.

---

## 2. La regola del colore

Tre livelli, e basta.

| Livello | Quando | Token |
|---|---|---|
| **Azzurro ONEFLUX** — il neutro dell'app | identità, navigazione, elementi interattivi, dato **senza** giudizio | `--primary` |
| **Grigio** — il dato che non giudica | numeri, tabelle, etichette, sparkline di contorno | `--foreground` / `--muted-foreground` |
| **Semantico** — solo giudizio, solo tre | verde = va bene · rosso = va male · **ambra = dato incompleto** | `--positivo` / `--negativo` / `--incerto` (nuovi) |

**Spariscono come decorazione:** violet, purple, pink, orange, teal, indigo —
oggi 233 occorrenze senza significato.

**Ambra confermata** come terzo colore semantico (decisione Mattia): è già usata
così in Catena e nel fix Home del 17/09, quindi è coerente col precedente.

Ogni token nuovo va tarato **a mano su entrambi i temi**. È questo che fa tornare
il cambio tema a essere solo un cambio tema: il colore giusto lo decide il token,
non la pagina.

---

## 3. Rilievi per pagina

Numerati per poterli spuntare. `[A]` = fase parole, `[B]` = fase colore,
`[C]` = fase densità.

### Home (`dashboard/`) — 54 occorrenze, 5 file

| # | Rilievo | Fase |
|---|---|---|
| H1 | **"Salute della gestione" non è la salute.** Misura *«hai inserito i dati?»*, non come va il locale. Nel dark: 100% "In salute" con MOL −5.712 €. → "Completezza dati"; "In salute"/"Dati incompleti" → "Completo"/"Incompleto" | A |
| H2 | **La stessa cosa detta tre volte:** assistente in prosa → card "Da fare oggi" identiche → "Vedi tutti gli avvisi (N)" con la stessa lista | C |
| H3 | **L'anello è mezzo vuoto:** cerchio da 100px in un riquadro alto 400px, poi la lista va a filo del bordo | C |
| H4 | **"Vai alla pagina →" ripetuto 4 volte** in 150px (light) | C |
| H5 | **Dark: "I tuoi conti" è rosso pieno.** Il MOL negativo tinge tutto il pannello. Nel light lo stesso pannello è bianco col solo numero rosso — ed è più leggibile | B |

### Ricavi e Margini (`margini/`) — 196 occorrenze, 8 file · **la pagina più pesante**

| # | Rilievo | Fase |
|---|---|---|
| M1 | **Tabella:** 8 colonne × 15 righe, ogni cella con valore **+ percentuale sotto**, font minimo. Nel dark le righe colorate su fondo nero fanno vibrare il testo | C |
| M2 | **"= 1° Margine" / "= 2° Margine (MOL)"** → "Margine sul cibo" / "Guadagno finale (MOL)". Via i segni `=` e `–` da foglio di calcolo | A |
| M3 | **"Analisi visiva" è l'arcobaleno:** 5 barre di 5 colori + 4 donut che ripetono numeri già in tabella. I donut mostrano **0% con pallino colorato** quando il dato non c'è | B |
| M4 | **Sparkline dei 6 riquadri senza scala né tooltip:** una linea grigia illeggibile. O si rendono leggibili, o si tolgono | C |
| M5 | **Analisi Avanzate: donut a due fette** (97,2% / 2,8%), una invisibile → due barre orizzontali | C |

### Osservatorio (`prezzi/`) — 92 occorrenze, 5 file · **la meglio riuscita**

I fix del 17/09 si vedono: intestazione una volta sola, percentuali neutre,
colore solo sull'impatto in euro.

| # | Rilievo | Fase |
|---|---|---|
| O1 | **Il pallino contraddice ancora l'impatto:** DERBY BLUE ANANAS −95% (risparmio, impatto verde) ha il pallino **arancione "Alto"**. Il pallino segue l'entità, non la direzione | B |
| O2 | **Tab "Sconti e Omaggi" / "Note di Credito" sono tabelle grezze:** 8 colonne fino al bordo, inclusa la **colonna "File" con `IT03237470236_foaGP.xml`** — un nome di file di sistema in faccia al cliente | C |
| O3 | **"Da Classificare" appare ~20 volte** in grigio nelle stesse tabelle: corretto, ma sembra un errore ripetuto | C |
| O4 | **Score Fornitori: 8 card su 10 con la frase identica** («Relazione complessivamente solida…») e lo stesso pallino giallo. Se il giudizio è uguale per quasi tutti, non sta discriminando | C |

### Gestione Fatture (`scadenziario/`) — 88 occorrenze, 1 file

I fix del 17/09 si vedono: "Scadute" chiusa, niente muro di barrette rosse.

| # | Rilievo | Fase |
|---|---|---|
| F1 | **"Esposizione futura" non guadagna lo spazio:** 120px per un blocco rosso e 5 colonne a 0 € → mostrarlo solo con ≥2 fasce popolate | C |
| F2 | **Tre livelli di controlli prima del contenuto:** 5 tab + 4 filtri + 2 filtri fornitore | C |
| F3 | **"Fuori dai conti" e "Note di credito"**: stessa cosa, due nomi in due schermate | A |
| F4 | **Gruppo: "723 fatture senza scadenza (810.335 €)"** in un avviso giallo sottile largo quanto la pagina. Un numero così merita più di una riga | C |

### Analisi Fatture (`analisi-fatture/`) — 70 occorrenze, 5 file

| # | Rilievo | Fase |
|---|---|---|
| AF1 | **4 riquadri, 4 colori, nessuna gerarchia:** "SPESA TOTALE" (business) e "RIGHE" (dettaglio tecnico) hanno lo stesso peso | B |
| AF2 | **"Righe" → "Voci in fattura"** | A |
| AF3 | **Tab Categorie: barre azzurre dentro le celle** — si leggono come selezione, non come proporzione. Nel light: azzurro acceso su bianco, molto pesante | B |
| AF4 | **Colonna "Trend": segmenti di due punti** senza scala. Non dice niente → ▲▼ + percentuale, o via | C |

### Analisi e Tag (`tag/`) — 0 occorrenze dirette (i colori arrivano dai componenti)

| # | Rilievo | Fase |
|---|---|---|
| T1 | **5 riquadri, 5 colori** (azzurro, verde, ciano, arancio, rosa) | B |
| T2 | **"Trend prezzi" con 80+ punti illeggibile:** date sovrapposte sull'asse X, marker che diventano una collana continua | C |
| T3 | **La scritta "Media" rossa si sovrappone al bordo** della linea tratteggiata — in entrambi i temi | C |
| T4 | **"Prodotti associati (39)":** 39 righe con ✕ a destra, nomi lunghi tutti maiuscoli | C |

### Agenda e Personale (`workspace/`) — 188 occorrenze, 9 file · **il dark più saturo**

| # | Rilievo | Fase |
|---|---|---|
| W1 | **Spese: 3 riquadri colorati per 3 zeri** (arancio, viola, azzurro, tutti 0,00 €), poi pagina vuota → empty state unico | B |
| W2 | **Personale: 3 card a fondo tinto pieno** (verde, arancio, blu). È il punto dove il dark è più saturo di tutta l'app | B |
| W3 | **"COSTO TOTALE" mostra "~16h 52m/g":** l'etichetta dice costo, il valore sono ore | A |
| W4 | **"COSTO ORDINARIE" mostra un trattino** dentro un riquadro enorme | C |
| W5 | **Calendario: pallini viola identici su quasi tutti i giorni** — se ci sono sempre, non segnalano niente | C |

### Catena (`catena/`) — 71 occorrenze, 6 file

| # | Rilievo | Fase |
|---|---|---|
| C1 | **"MOL DEL GRUPPO 9.335.987 €"** in arancione gigante e **subito sotto** «questo margine non è reale». Il numero più grande della pagina è dichiarato falso dalla riga sotto → se non è reale non va a 60px | B |
| C2 | **"Salute e margini per sede": 5× "dati incompleti"** e 5 valori (0, 25, 25, 49, 50) **senza unità** — non si capisce se sono %, punteggi o euro | A |
| C3 | **"Da vedere nella catena": 11 righe di cui 5 identiche** → raggruppare in «5 punti vendita: mancano fatture costo e personale» | C |

---

## 4. La tabella di Ricavi e Margini — proposta di design

**Il problema non è la griglia.** È l'unica pagina dove il cliente *modifica* i
dati, e il confronto mese-su-mese è il motivo per cui esiste: sostituirla con
delle card lo distruggerebbe. Il problema è che **ogni cella porta due numeri in
competizione**.

**a) Toggle € / % / entrambi.** Le percentuali sono incidenze e servono
(indicazione di Mattia). Invece di due stati, tre: default **€** (il numero che
si legge), **%** per chi ragiona per incidenze, **entrambi** per l'attuale. La
preferenza si ricorda.

**b) Gerarchia tipografica al posto del colore.** Oggi le righe si distinguono
per *tinta* (arancio, verde, rosa, viola). Invece: righe di dettaglio in grigio
regolare, righe di totale in **grassetto con un filo di separazione sopra**, MOL
in fondo **più grande**. La struttura si legge dalla forma, non da cinque colori.

**c) Colonna del mese corrente staccata.** Oggi ha un asterisco e un bordo
azzurro; renderla leggermente evidenziata per intero — è quella che si guarda.

---

## 5. Il piano in quattro fasi

| Fase | Cosa | Perché in quest'ordine | Rischio |
|---|---|---|---|
| **0 — Fondamenta** ✅ **CHIUSA** (commit `7cb145c`, 18/09) | Token `--positivo`/`--negativo`/`--incerto` definiti su entrambi i temi. Nessun cambio visibile, provato per mutazione. | Tutto il resto ci si appoggia. Farlo dopo = rifarlo due volte. | nullo |
| **1 — Parole** ✅ **CHIUSA** (commit `5f7a6f7`, 18/09) | H1, M2, AF2, F3, W3, C2 + Q.tà, Incid. Fatturato, Vs media | Indipendente dalla grafica, si può fare in parallelo | nullo |
| **2 — Colore** ✅ **CHIUSA** (12 commit da `7bffae6` a `1a81d92`, 18/09) | Sostituire le 759 classi hardcoded coi token, pagina per pagina. Eliminare i 233 decorativi. H5, M3, O1, AF1, AF3, W1, W2, C1 | **È il cuore:** risolve insieme l'incoerenza dell'azzurro, l'arcobaleno e il disallineamento dark/light — tre sintomi della stessa causa | medio — va guardato a schermo in entrambi i temi |
| **3 — Densità** ⏸️ **DA RIVEDERE PRIMA DI COMINCIARE** | L'elenco del 18/09 era: Tabella Margini (§4), H2-H4, M1, M4-M5, O2-O4, F1-F2-F4, AF4, T2-T4, W4-W5, C3. Dopo la verifica sul codice e sui 70 screenshot (§13) **ne restano 14 su 22**: vedi §14. | Tocca i layout: serve l'occhio di Mattia prima di committare | alto — **una pagina per volta** |

**Modo di lavoro sulla fase 3** (decisione delegata a me): propongo **una pagina
per volta**, la mostro, e passo alla successiva solo quando quella è chiusa.
È la regola di `WORKFLOW.md` §5 — sui layout è l'unico modo per non accumulare
quattro pagine da rifare insieme.

**Ordine deciso da Mattia il 21/09**, dopo il giro sugli screenshot: **prima R5
(i 93 troncamenti senza tooltip), O2 e O4** — che sono dati *nascosti o
sbagliati*, non densità, e si chiudono senza il suo occhio — **e la fase 3
dopo**, con l'elenco rivisto del §14.

---

## 6. Limiti di questa analisi — cosa NON è stato verificato

Va scritto, o alla prossima sessione sembrerà completa.

1. **L'app non è mai stata vista in movimento.** Uno screenshot non mostra
   caricamenti (scheletri? spinner? salto del layout?), transizioni, hover,
   dialog e form. L'audit del 16/09 misurava **25s di attesa sull'Osservatorio**:
   non è colore, ma è *esattamente* ciò che rende un'app "pesante".
2. **Le pagine sono tagliate.** Quasi tutti gli screen si fermano a metà:
   `/prezzi` 11 righe su 19, Analisi Fatture 12 su 696, la Home a metà
   "I tuoi conti". **Non si sa come finiscono le pagine.**
3. **Nessuna verifica responsive.** Tutti gli screen a ~1900px. L'audit del 16/09
   misurava a **1140px** — la larghezza di un portatile vero, dove le cose si
   rompono (fu il caso del nome sede che spariva).
4. **Percorsi mai visti:** upload fatture, configura assistente, impostazioni,
   login. Sono i momenti in cui il cliente si forma l'opinione sull'app.
5. **`/m` escluso dal perimetro** per scelta: è un frontend separato, non
   responsive, e va allineato a mano.

**Chiusura dei punti 1-4:** giro con l'estensione Chrome di Claude su
`app.oneflux.it` (materiale già pronto in `prompt_audit_visivo_chrome.md`).
Le fasi 0-2 **non** dipendono da quel giro — poggiano su misure del codice.
La fase 3 **sì**: va rivista dopo.

---

## 6-bis. Fase 0 in dettaglio — cosa fare esattamente

Stato misurato il 18/09 su `apps/web/src/app/globals.css` (296 righe):

| Token | Esiste? | Dove |
|---|---|---|
| `--primary` (azzurro ONEFLUX `#0ea5e9`) | ✅ | `:56` light `oklch(0.685 0.169 237.3)` · `:93` dark `oklch(0.751 0.148 237.3)` |
| `--destructive` | ✅ | `:69` light · `:101` dark |
| `--positivo` / `--negativo` / `--incerto` | ❌ **da creare** | — |

**Il pattern da seguire è già nel file:** ogni token è definito due volte, sotto
`:root` (light) e sotto `.dark`, con **valori diversi** — non lo stesso colore
riusato. La dark ha luminosità più alta perché deve staccarsi dal nero. Esempio
già presente: `--primary` passa da `0.685` a `0.751`, `--destructive` da `0.577`
a `0.704`.

**Cosa aggiungere:**

1. Tre coppie di token in `globals.css`, ciascuna con la sua taratura light+dark:
   - `--positivo` (verde: va bene)
   - `--negativo` (rosso: va male) — valutare se `--destructive` basta già, o se
     serve distinguere "errore di sistema" da "dato negativo"
   - `--incerto` (ambra: dato incompleto)
2. La loro esposizione in `@theme inline` (righe 9-43), sul modello delle altre:
   `--color-positivo: var(--positivo);` ecc.
3. **Nessun consumo.** La fase 0 non tocca una sola pagina: se un pixel cambia,
   è un errore.

**Come si verifica che sia giusta:** `npx tsc --noEmit` pulito e
`git diff --stat` che mostra **un solo file toccato** (`globals.css`).
Screenshot prima/dopo di una pagina qualsiasi: identici.

**Trappola già nota** (memoria `fix-tarato-su-un-solo-tema`): un colore scelto
guardando solo il light è sbagliato nel dark. I valori vanno decisi **guardando
entrambi i temi**, non calcolati.

### Esito della fase 0 (18/09, commit `7cb145c`)

**Valori scritti**, scelti da Mattia fra tre tarature:

| Token | Light | Dark |
|---|---|---|
| `--positivo` | `oklch(0.548 0.132 163.2)` | `oklch(0.773 0.153 163.2)` |
| `--negativo` | `oklch(0.560 0.215 17.6)` | `oklch(0.719 0.169 13.4)` |
| `--incerto` | `oklch(0.575 0.148 58.3)` | `oklch(0.837 0.164 84.4)` |

Non sono inventati: sono i colori che le pagine **già usano** (light 600, dark
400 — pattern misurato: `dark:text-emerald-400` 44 volte, `dark:text-amber-400`
35, `dark:text-rose-400` 18). Nel light però erano **sotto soglia di
leggibilità** su bianco e sono stati scuriti:

| | in uso oggi | contrasto | dopo |
|---|---|---|---|
| verde light | `emerald-600` | **3,77:1** ❌ | 4,50:1 ✅ |
| ambra light | `amber-600` | **3,19:1** ❌ | 4,57:1 ✅ |
| rosso light | `rose-600` | 4,70:1 ✅ | 5,22:1 ✅ |

I dark erano già tutti sopra soglia (4,90 – 7,92:1) e restano.

**`--negativo` distinto da `--destructive`: deciso e motivato sulla misura.**
`destructive` oggi marca l'azione pericolosa e l'errore di sistema (elimina
account, cestino, upload fallito, badge errore) — **mai** il dato in perdita.
Unirli legherebbe il rosso del MOL a quello del pulsante Elimina.

**Prova per mutazione** (non basta che il file compili): con un consumatore
temporaneo Tailwind genera `text-positivo` / `bg-incerto/10` / `border-negativo`
risolte nei due temi; rimosso il consumatore le classi **non esistono** (0)
mentre i token restano definiti (6). `git diff --stat`: un solo file.

### ⚠️ Vincolo misurato — **superato dalla fase 2.0** (18/09, sera)

Testo di un token **sul fondo tinto dello stesso token** (`bg-*/10`, il pattern
di H5, W2, C1) con la prima taratura restava sotto 4,5:1 in light. La colonna
dark di questa tabella era **mis-misurata**: lo script della fase 0 usava come
card `#303030` (sRGB 0,188) invece della vera `--card` dark, `oklch(0.205)` =
`#171717`. Rimisurato con la conversione verificata sui valori pubblicati da
Tailwind (`tests/test_globals_css_contrasto.py`):

| testo sul proprio fondo /10 | light, taratura fase 0 | **light, fase 2.0** | dark (fase 0, sbagliata) | **dark, vera** |
|---|---|---|---|---|
| positivo | 3,95:1 | **4,71:1** (L 0,548→0,51) | 5,66:1 | 7,8:1 |
| negativo | 4,43:1 | **4,76:1** (L 0,560→0,54) | 4,23:1 | 5,8:1 |
| incerto | 4,02:1 | **4,60:1** (L 0,575→0,54) | 6,35:1 | 8,8:1 |

I tre token light sono stati **ritarati** (avevano zero consumatori: nessun
pixel cambia) e il vincolo **sparisce**: `bg-positivo/10 text-positivo` si legge
in entrambi i temi. Resta una regola sola, più semplice: **le tinte semantiche
si scrivono `/10`, non `/15`** (al /15 il light torna sotto: 4,28 / 4,34 / 4,29).
La raccomandazione di H5 (fondo neutro, solo il numero colorato) resta valida
come scelta di design per i pannelli grandi, non più come obbligo di contrasto.

---

## 7. Decisioni prese (18/09, in chat con Mattia)

- Perimetro: **solo pagine app principali**, niente admin/demo/`/m`
- **Ambra** confermata come terzo colore semantico ("dato incompleto")
- Rinomine: **mano libera** — pochi clienti, usano poco, è il momento
- Azzurro ONEFLUX = **il neutro dell'app**, via `--primary`, mai `sky-*` a mano
- Tabella Margini: **toggle €/%**, non sostituzione con card
- Fase 3: **una pagina per volta**, mostrata prima di passare oltre
- Nessuna ristrutturazione: *«la base è già molto bella, deve migliorare»*

---

## 8. Esito della fase 1 — parole (18/09, commit `5f7a6f7`)

Dieci rinomine approvate da Mattia una per una. Due varianti rispetto alla
proposta: `= 1° Margine` → **«Margine su food&beverage»** (non "sul cibo"), e
**«Ricavi IVA 10/22%» NON si tocca** (serviva conferma su cosa contengano: non
data, quindi lasciate).

### Dove il piano sbagliava, corretto sul codice

- **F3 non era un doppione.** Il piano dava «Fuori dai conti» e «Note di credito»
  come «stessa cosa, due nomi». Sono cose diverse: `oscurata` = il **cliente** ha
  escluso la fattura, `is_nota_credito` = **rimborso del fornitore**. Vanno
  distinte meglio, non unite → «Escluse da te». La stringa è anche lo stato nel
  **CSV scaricato** (`statoDocumento`), quindi cambiata anche nell'union type e
  nel test che la presidia, o CSV e video divergerebbero.
- **W3 non era una rinomina.** «Costo totale» non aveva l'etichetta sbagliata:
  senza paghe inserite **ripiegava sulla media di ore al giorno**, mostrando ore
  sotto un'etichetta di costo. Ora dice «Paghe non inserite», come le altre due
  card che già mostravano «—». Rimossi `mediaGiornaliera` e `giorniConTurni`,
  che esistevano solo per quel ripiego.
- **Un rilievo mancava:** «Righe» era anche in **Catena**
  (`gruppo-tag-section.tsx`), non solo in Analisi Fatture. Allineato.

### Trappola evitata

`"1° Margine"` **non è solo un'etichetta**: è la chiave con cui il frontend
aggancia i commenti che manda il worker (`margine_service.py:1031`
→ `commentoPerKpi`). Rinominarla avrebbe **spento commenti ed emoji dei gauge** —
un cambio funzionale dentro un lavoro di sola grafica. Rinominata solo la `label`
a video; `kpiNome` invariato. Il codice lo diceva già in un commento del 16/09:
*«il match resta sul nome del worker: è quello il contratto»*.

### Fuori perimetro — con una correzione

Demo (`components/demo/`) e `/m` conservano le vecchie parole **solo dove hanno
una copia propria del markup**: `demo-margini.tsx` (`= 1° Margine`,
`= 2° Margine (MOL)`) e `demo-analisi.tsx` (`Q.tà`).

**Correzione al primo verbale** (rilievo della review, verificato sugli import):
per la card Salute **non è vero** che conservano le vecchie parole — sia
`(mobile)/m/briefing/page.tsx` sia `demo-home.tsx` importano il **componente
vero** `SaluteCard`, quindi hanno già ereditato «Completezza dati» e la scala
Completo / Quasi completo / Incompleto. Va a favore della coerenza, ma la frase
scritta la prima volta era falsa e avrebbe mandato una sessione futura a cercare
un allineamento già fatto.

### Seconda passata, dopo la review (verdetto 🔴 → fix)

Il primo giro aveva cercato le stringhe **con la grafia esatta** (`"Q.tà"` fra
virgolette, `>Fuori dai conti<` maiuscolo) e aveva mancato tre punti a video:

- **badge «fuori dai conti»** in minuscolo su ogni riga esclusa
  (`scadenziario-client.tsx:197`), **contiguo** alla sezione già rinominata
  «Escluse da te»: due nomi per la stessa cosa nella stessa schermata — il
  difetto F3 che la fase doveva chiudere
- **`Q.tà`** nell'intestazione del dettaglio riga (`articoli-tab.tsx:827`),
  **nello stesso file** dove era già stato rinominato: espandendo un articolo la
  colonna cambiava nome sotto gli occhi
- **`dati incompleti`** in minuscolo in 5 punti (Catena ×2, Home, finestra
  Margini e Coperti, **cella dell'export Excel**) mentre la scala nuova dice
  «Incompleto»

**La lezione è metodologica, non puntuale:** una rinomina si cerca
**case-insensitive e senza delimitatori**, o le occorrenze in minuscolo e quelle
in JSX nudo restano indietro. Rifatto così, il perimetro cliente è pulito.

**Decisione di Mattia sulle tre card del Personale:** tutte e tre dicono «Paghe
non inserite». Il primo giro lo aveva messo solo sulla terza motivandolo con
«le altre due già mostrano —», che era **falso**: mostravano `—` e quindi le tre
card divergevano, dentro un lavoro sulla coerenza visiva.

**Verifica:** `tsc --noEmit` pulito · test frontend verdi · review passata al secondo giro.

---

## 9. Il costo della review — cosa ha insegnato (18/09)

Le fasi 0 e 1 hanno richiesto **cinque giri di review** e 8 commit. Vale la pena
scriverlo, perché il costo non è stato nei cambi ma nel **modo di cercarli**.

### I difetti trovati, per classe

| Classe | Esempi | Come si evitava |
|---|---|---|
| **Ricerca con la grafia esatta** | badge `fuori dai conti` minuscolo · `Q.tà` nel dettaglio riga · `dati incompleti` in 5 punti · `vs media` nell'Osservatorio | cercare **case-insensitive e senza delimitatori**, sempre |
| **Perimetro dedotto invece che misurato** | `/m` e demo dati per «rimasti indietro»: importavano già il componente vero · `/m` aveva una copia della lista Catena | guardare gli **import**, non il nome della cartella |
| **Due fonti per la stessa parola** | schermo `incompleto` / export `Incompleto` nella **stessa tabella** | una **costante condivisa**: lo garantisce il compilatore, non un test |
| **Rimedio peggiore del male** | `truncate` per dare spazio → `12.450,00 €` diventa `12.45…`, plausibile e falso | su un **numero** non si tronca mai: meglio che sbordi, almeno si vede |
| **Presidio che cerca sé stesso** | il primo test ancorava il letterale `[Ii]ncompleto`: sopravviveva a una rinomina in `Parziale` | ancorare il **ramo di codice**, non la parola; e calcolare il perimetro invece di elencarlo |

### La lezione che vale oltre questa fase

**Un presidio va provato con il mutante che somiglia al lavoro in corso.** Il
primo test era verde su tutti i mutanti che gli avevo lanciato io — perché li
avevo scelti dentro la stessa idea sbagliata (grafia della parola). È bastato il
mutante giusto (*rinomina* verso un'altra parola) per smontarlo, ed era proprio
lo scenario della fase in corso.

### Cosa resta aperto, dichiarato

**Nessuno ha visto l'app a schermo** — né io né il reviewer. Tutte le cifre di
layout vengono dalle metriche del font e dalle classi CSS.

Da guardare su un portatile vero a **1140 e 1280px**: le tre card di Agenda →
Personale. Con le paghe inserite, `fmtEuro` a `text-4xl` produce un importo che
**da solo** eccede lo spazio della card (~221-259px su ~223 utili, a seconda del
fattore di peso usato). **È un difetto preesistente**, presente ogni volta che i
dati ci sono, non introdotto da questa fase: va risolto in **fase 3** riducendo
la taglia del testo, non redistribuendo lo spazio — nessuna valvola può
risolverlo, perché il contenuto eccede il contenitore a prescindere.

---

## 10. L'audit dell'estensione Chrome — cosa regge e cosa no (18/09)

Il materiale annunciato al §6 è arrivato (`rilievi_oneflux_18-09-2026`). **Prima di
riscrivere il piano su quei dati, l'ho verificato.** Una parte non regge, e proprio
la più grave.

### ❌ SMENTITO: «nel tema chiaro alcuni testi sono invisibili (CR 1,04)»

L'audit dichiarava, misurando dal DOM, testo `rgb(250,250,250)` su bianco su
`/catena` (fatturato di gruppo, food cost, nomi sede), `/agenda` e `/m`.

**Misurato sui pixel dei 12 screenshot in tema chiaro** (`SCREEN APP 18.09/`,
individuati per luminosità media; 12, non 11 — cifra corretta dal reviewer):

| Testo dato per invisibile | Misura reale |
|---|---|
| Fatturato gruppo 15.339.520 € | nero su bianco, **19,62:1** |
| Food cost 18,7% | **19,67:1** |
| Nome sede PADERNO | **18,91:1** |

Poi due prove che distinguono le ipotesi invece di confermarne una:
1. **gamma stirata** (246-255 → 0-255) sulla card sospetta: emergono solo il
   gradiente di fondo e il testo già visibile, **nessun glifo nascosto**;
2. **forma dei run** di pixel quasi-bianchi, a passo 1: dei run corti
   (forma-glifo) **5.067 confinano con pixel chiari** — bordi e antialiasing fra
   card e fondo — e solo **14 con pixel scuri**, e quei 14 sono gli spazi *dentro*
   glifi già visibili.

**Causa probabile dell'errore:** il metodo dell'audit risale l'albero DOM «fino al
primo fondo opaco». Dove il fondo è un **gradiente** (le card di `/catena` lo sono)
prende un colore che sotto quel testo non è mai dipinto.

### ✅ CONFERMATO: i contrasti bassi sui colori pieni

| Elemento | Audit | Mia misura sui pixel |
|---|---|---|
| Chip azzurro attivo dei filtri ("Anno in corso") | 2,18-2,71 | **2,10** (scuro) |
| Badge «dati incompleti» | — | **2,43** |

Il chip è l'elemento **più in vista** della barra comandi ed è il meno leggibile
della pagina. **È esattamente ciò che la fase 2 risolve**: è `sky-*` scritto a
mano, uno dei 322.

### La regola che ne esce

**Le misure dell'audit sui colori pieni sono attendibili; quelle sui fondi sfumati
no.** Vale per tutto il documento: i suoi rilievi di contrasto vanno ri-verificati
prima di agire, gli altri (troncamenti, tempi, struttura) non dipendono dal colore
e restano validi.

### Limiti di questa mia verifica — dichiarati

- Gli screenshot sono di **un altro account e di un'altra sessione**: «nessun testo
  invisibile in questi 12 screenshot» **non è** «nessun testo invisibile nel
  prodotto». Uno stato non renderizzato lì potrebbe comportarsi diversamente.
- Non è dimostrato che «il tema chiaro è sano», solo che **quel** rilievo è falso.
- Quello che è dimostrato: i contrasti bassi **reali** stanno sui colori pieni, e
  quelli sono già nel perimetro della fase 2.

### Cosa NON cambia nel piano

La fase 2 resta quella pianificata: sostituire i 322 `sky-*` a mano col token, e
togliere i 233 decorativi. **Non** va riscritta sulla premessa «il tema chiaro è il
malato»: metà di quella premessa non regge.

### Cosa il piano deve recepire (non verificato da me, non dipende dal colore)

1. **I troncamenti sono il vero danno a 1140px**, non lo sbordamento: 109 nomi
   fornitore tagliati, nomi sede al 24%, **e nessun tooltip** — il dato non è
   recuperabile dall'interfaccia. Va in fase 3.
2. **`/m` è una seconda interfaccia** con tipografia propria fino a 9px, oggi fuori
   perimetro, e **il redirect è a senso unico**.
3. **La performance non è densità**: il collo di bottiglia è il payload della rotta
   (3,2-9,2s), non il layout. Intervento separato, backend.
4. **Formati di numero e data incoerenti** nella stessa schermata — è fase 1
   (parole), immediatamente azionabile.
5. ❌ **SMENTITO — il dialog «Carica ricavi» funziona.** L'audit lo dava come «il
   difetto più grave del rilievo»: i pulsanti di salvataggio renderizzati 95px
   sotto il bordo del dialog, «a 631px di altezza il fatturato non è salvabile».
   **Mattia ha controllato (18/09): i pulsanti ci sono e il dialog scorre**,
   coerente con quello che dice il codice (`max-h-[90vh] flex flex-col` + area
   `overflow-y-auto`, e `twMerge` risolve `grid`→`flex` a favore del secondo).
   Nessun intervento.

### Il bilancio dell'audit: due smentite sulla stessa causa

I **due rilievi che l'audit dichiarava più gravi** — testi invisibili nel tema
chiaro e salvataggio ricavi bloccato — sono **entrambi falsi**, e per la stessa
ragione: misurati **interrogando la pagina** (colori risaliti nell'albero DOM,
posizioni calcolate) invece che **guardandola**. Dove il fondo è un gradiente o
dove un contenitore scorre, quel metodo legge numeri che non corrispondono a ciò
che il cliente vede.

Non lo rende inutile — **i rilievi su colori pieni, troncamenti, tempi di rete e
struttura HTML restano**, e il chip azzurro a 2,10:1 è vero e già nel perimetro
della fase 2. Ma stabilisce la regola per usarlo: **da quel documento non si agisce
senza aver prima verificato il singolo rilievo**, e la verifica che conta è
guardare, non ricalcolare.

È la stessa lezione dei sei giri di review sulle fasi 0-1, arrivata da un terzo
strumento: *a separare da un verdetto sbagliato è sempre stato guardare la cosa
vera, mai un ragionamento più accurato.*

---

## 11. CODA — da affrontare a FINE implementazione (decisione Mattia, 18/09)

**Non si aprono adesso.** Restano qui, uno per riga, e si chiudono quando tutte
le fasi della coerenza visiva (2 e 3) sono finite. Nessuno di questi blocca il
lavoro in corso; nessuno di questi è chiuso.

| # | Cosa | Natura | Perché non ora |
|---|---|---|---|
| R1 | **4 funzioni SQL con `search_path` mutabile** — `_riparto_categoria_is_fb`, `costi_automatici_mensili`, `costi_automatici_mensili_gruppo`, `articoli_da_fatture` | Sicurezza DB, non grafica | È lavoro di sicurezza: ha bisogno di una sua sessione e della sua review, non di un commit dentro un lavoro estetico. Misurato il 18/09 con `get_advisors`: 0 ERROR, questi 4 sono WARN |
| R2 | **Card Agenda → Personale a 1140/1280px con le paghe inserite** | Layout, **preesistente** | Nessuno ha ancora guardato l'app a schermo. A 1140px restano ~223px per card e un importo vero a `text-4xl` ne vale ~206: le due colonne non ci stanno insieme. **Non introdotto dalle fasi 0-1**, sede naturale in fase 3 (densità) |
| R3 | **Tetto di 250 file upload non applicato nel percorso vivo** | Funzionale | `MAX_FILES_PER_UPLOAD` ha un solo punto d'uso, in `upload_handler.py:1028`, raggiungibile solo da `legacy_streamlit/`. Oggi **documentato** in `README.md` (i limiti che reggono sono 50 MB/file e 200 MB/richiesta), **non risolto** |
| R4 | **Due certificati storici con «101 Deno» mai vero** — `DOCUMENTAZIONE/AUDIT_COPERTURA.md:30`, `DOCUMENTAZIONE/AUDIT_BILANCIO_LUGLIO_SETTEMBRE.md:109` | Documentazione | Erano 117 **già al commit `1011d10`** che certificano (verificato ricostruendo l'albero): la cifra era falsa quando fu scritta, e sei giri di review di L9 non la videro. Si **annota** accanto, non si riscrive: correggere un certificato storico è peggio del difetto |

**Dall'audit Chrome, non verificati da me** (§10: da quel documento non si agisce
senza prima guardare — due dei suoi rilievi «più gravi» erano falsi):

| # | Cosa | Dove va |
|---|---|---|
| R5 | **Troncamenti senza tooltip**: 109 nomi fornitore tagliati, nomi sede al 24%, colonna File. Nessun `title`, nessun `aria-label`: **il dato non è recuperabile dall'interfaccia** | Fase 3 — è il rilievo più sostanzioso dell'audit |
| R6 | **`/m` è una seconda interfaccia** con tipografia propria fino a 9px, e il redirect sarebbe **a senso unico** | Perimetro: oggi escluso per decisione (§7) |
| R7 | **Payload della rotta 3,2-9,2 s**: il collo di bottiglia non è il layout ma il rendering server-side | **Non è estetica**: backend, lavoro separato |
| R8 | **Formati di numero e data incoerenti** nella stessa schermata (`38.246 €` / `3954 €` / `€8.30`; `01/01/26` / `01 set 2026`). **Causa misurata:** `lib/format.ts` si dichiara «FONTE UNICA» ed espone `formatEuro(v, decimali = 0)`, ma alcuni punti lo **scavalcano** con formattatori propri — `anteprima-fattura-dialog.tsx:123` usa `€${…toFixed(4)}` (4 decimali, **senza spazio**), `variazioni-tab.tsx:173,182,199` usa `€${…toFixed(2)}`. Non è «qualche formato storto»: è un formattatore condiviso aggirato | **Fase 1 (parole)** — la sola voce dell'audit che appartiene a una fase già chiusa: si riapre qui o si fa in coda |

> **R8 merita due note.**
>
> **È l'unico residuo di competenza della fase 1**, chiusa il 18/09. Non è una
> dimenticanza di quella fase — l'audit è arrivato dopo — ma se si vuole la fase 1
> «completa» va fatto, non rimandato per sempre.
>
> **⚠️ Trappola già pagata** (memoria `sostituire-un-formattatore-locale-cambia-i-decimali`):
> sostituire un `fmtEuro` locale a 2 decimali con `formatEuro` (default **0**)
> **cambia i numeri che il cliente legge**. R8 va fatto provando l'equivalenza
> **caso per caso**, mai con un replace globale: altrimenti un lavoro «di sole
> parole» cambia gli importi a video.

---

## 12. Fase 2 — colore: regole, inventario e stato (18/09, sera)

### L'inventario di oggi, col metodo dichiarato

Occorrenze (non righe) di classi `prop-famiglia-tonalità[/opacità]` su
`.ts/.tsx`, con `prop` ∈ text/bg/border/ring/from/to/via/fill/stroke/shadow/…
Script: `scratchpad` di sessione, rieseguibile. Cifre diverse dal §1 (322/233/759)
perché il metodo conta più proprietà (ring, from/to, fill) e non solo le righe:

| Zona | file | classi | `sky` | decorativi | semantici | hex |
|---|---|---|---|---|---|---|
| tutto `src/` | 93 | 1.561 | 376 | 272 | 881 | 77 |
| `(app)/workspace` + `agenda` | 11 | 250 | 92 | 62 | 88 | 0 |
| `(app)/margini` | 8 | 201 | 65 | 41 | 92 | **44** |
| `(app)/prezzi` | 5 | 101 | 25 | 3 | 73 | 5 |
| `(app)/scadenziario` | 1 | 92 | 12 | 46 | 34 | 0 |
| `(app)/catena` | 6 | 75 | 10 | 2 | 63 | 0 |
| `(app)/analisi-fatture` | 5 | 70 | 18 | 15 | 37 | 5 |
| `(app)/dashboard` | 5 | 63 | 5 | 2 | 56 | 0 |
| `(app)/analisi-e-tag` | 1 | 41 | 4 | 6 | 31 | 5 |
| `(app)/assistenza`, `notifiche`, `impostazioni`, `style-guide` | 5 | 70 | 13 | 0 | 57 | 0 |
| `components/nav` (sidebar, su ogni pagina) | 1 | 25 | 25 | 0 | 0 | 0 |
| `lib/` condivisi dalle pagine (`salute-tint`, `foodcost`, `catena-*`, `scadenziario`) | 5 | 77 | 1 | 2 | 74 | 0 |
| `(app)/admin`, `components/demo`, `/m`, landing, auth — **fuori perimetro** | ~40 | ~560 | | | | |

### Perimetro (deviazione dichiarata dal §7)

§7 dice «solo pagine principali». Il presidio però non può avere una lista
scritta a mano di cartelle *incluse* (marcisce): è più onesto **tutta l'app del
cliente** meno le esclusioni decise (`admin`, `demo`, `/m`, landing, auth,
legal). Questo porta dentro anche `assistenza`, `notifiche`, `impostazioni` e
`style-guide` — 70 classi, stesse voci di menu delle pagine principali, e una
*style guide* che contraddice lo stile è il documento peggiore che ci sia.

### Le tre scoperte che cambiano il disegno

1. **`--primary` come testo fa 2,71:1 su bianco.** Sotto ogni soglia. È il motivo
   per cui le pagine scrivono `text-sky-700` a mano. Nuovo token
   **`--primary-text`**: light `oklch(0.50 0.11 237.3)` (≈ sky-700, 5,9:1 su
   bianco, ≥4,8 su card/accent/muted), dark = `--primary` (9,1:1). Regola:
   **testo blu → `text-primary-text`; superfici/bordi/anelli/icone → `primary`;
   fondo tinto blu → `bg-accent`** (già tarato per tema, opaco).
2. **La tabella dark del vincolo era sbagliata** (sopra, §6-bis). Ritarati i
   semantici light; il vincolo sparisce; resta «tinte semantiche a `/10`».
3. **I grafici hanno bisogno di una scala, non di un arcobaleno.** Cinque serie
   in cinque tinte (M3, `CENTRO_COLOR`, `COLORI_LINEE`) diventano una rampa del
   brand: `--grafico-1` (= primary) · `-2` (più scuro) · `-3` (più chiaro) ·
   `-4` (= muted-foreground) · `-5` (= foreground). Le serie **con un giudizio**
   (netto/lordo, sopra/sotto media) usano i semantici; le linee di riferimento
   («Media») vanno in grigio. Nei TSX si scrive `var(--grafico-2)`, mai un hex:
   `var()` dentro le prop di recharts è già in uso nel repo (`stroke: "var(--card)"`).

### Il mapping, famiglia per famiglia

| Era | Diventa | Nota |
|---|---|---|
| `text-sky-600/700/800/900` + `dark:text-sky-400/300` | `text-primary-text` | la coppia light/dark collassa: il token porta i due temi |
| `text-sky-400/500` (icone) | `text-primary` | se è testo leggibile → `primary-text` (verifica a mano) |
| `bg-sky-500/8…15`, `bg-sky-50/100`, `dark:bg-sky-900/950…` | `bg-accent` | fondo tinto blu, opaco, tarato per tema |
| `bg-sky-400/500` pieno | `bg-primary` | `hover:bg-sky-600` → `hover:bg-primary/90` |
| `border/ring/from/shadow-sky-*[/N]` | stesso prop su `primary` | opacità conservata |
| `focus:ring-sky-500`, `focus:border-sky-500` | `focus:ring-ring`, `focus:border-ring` | il token del focus esiste già |
| `emerald`/`green` | `positivo` | tinte `/15` → `/10` |
| `rose`/`red` | `negativo` | **`destructive`** se è azione pericolosa o errore di sistema (elimina, error-boundary) |
| `amber`/`yellow` | `incerto` | anche gli avvisi: è lo stesso ruolo visivo |
| `orange` | `incerto` se avvisa, altrimenti `primary`/grigio | decorativo nel piano, ma spesso usato come ambra |
| `violet`/`purple`/`pink`/`blue`/`indigo`/`teal` | `primary`/`accent` o grigio, **a mano** | il colore era la sola cosa che li distingueva: dove serviva distinguere, resta la forma (grassetto, bordo) |
| `slate`/`gray` | `muted-foreground` / `muted` / `border` | |
| hex nei grafici | `var(--grafico-N)` / `var(--positivo)` … | `app/layout.tsx` `themeColor` resta hex: è metadata, non CSS |

### Come si prova

- `tests/test_globals_css_contrasto.py` — **41 test**: converte l'oklch di
  `globals.css` in sRGB (matematica verificata su due valori pubblicati da
  Tailwind) e misura il contrasto dei token sui fondi reali, nei due temi.
  Provato con 6 mutanti (token schiarito, scurito, cancellato, dark che diverge).
- Presidio di convenzione (a fine fase): nel perimetro nessuna classe di
  palette cruda, nessun hex fra virgolette, ogni token usato è dichiarato in
  `@theme`, nessun `text-T` insieme a `bg-T/15`. Provato per mutazione.
- `tsc --noEmit` dopo ogni sotto-fase.
- **A schermo, nei due temi: lo può fare solo Mattia.** Da questa sessione non si
  può renderizzare l'app (niente Playwright, e l'unico modo di vedere le pagine
  vere sarebbe una sessione su dati di un cliente). Ogni sotto-fase dichiara
  cosa è stato misurato e cosa resta da guardare.

### Sotto-fasi (un commit ciascuna)

| # | Cosa | Stato |
|---|---|---|
| 2.0 | token `--primary-text`, rampa `--grafico-*`, ritaratura semantici light, test di contrasto | ✅ |
| 2.1 | condivisi: sidebar, page-header, trigger-hint, error-boundary, `components/fatture`, `lib/*` | ✅ `ab8f91b` |
| 2.2 | Home (`dashboard/`) | ✅ `e20f3c0` |
| 2.3 | Ricavi e Margini (`margini/`, 44 hex) | ✅ `a8f13d8` |
| 2.4 | Osservatorio (`prezzi/`) | ✅ `6be024d` |
| 2.5 | Gestione Fatture (`scadenziario/`, 34 violet) | ✅ `5c1db48` |
| 2.6 | Analisi Fatture (`analisi-fatture/`) | ✅ `e4b484d` |
| 2.7 | Analisi e Tag | ✅ `8646e60` |
| 2.8 | Agenda e Personale (`workspace/` + `agenda/`) | ✅ `06bd099` |
| 2.9 | Catena | ✅ `1587375` |
| 2.10 | assistenza, notifiche, impostazioni, style-guide | ✅ `f19db1e` |
| 2.11 | presidio di convenzione + verbale + contatore | ✅ `1a81d92` + verbale |

### Esito della fase 2 (18/09, sera — 12 commit da `7bffae6` a `1a81d92`)

**Misurato dopo, con lo stesso script dell'inventario:** nel perimetro del
cliente (tutta `src/` meno admin, demo, `/m`, landing, auth, legal) **0 classi
di palette, 0 esadecimali fra virgolette, 0 `var(--color-<palette>)`**. In
tutto `src/` le classi di palette passano da **1.561 a 458**, tutte nelle aree
escluse (admin 164, demo 126, `/m`+auth+legal 120, landing 26, `lib/admin`).
`sky-*` da 376 a 94, nessuno nel perimetro. 63 file toccati, +1.043/−710 righe.
`tsc --noEmit`: 0 errori nel sorgente (l'unico errore è un `validator.ts` stale
in `.next/dev/types`, che cita una pagina `probe` inesistente).

**Come è stato fatto.** Un riscrittore (nello scratchpad di sessione) ha
applicato il mapping alle classi dentro le stringhe, collassando ogni coppia
`x-600 dark:x-400` in un token; **ogni file è stato poi riletto nel diff**, e
lì sono uscite le decisioni che nessuna regola meccanica poteva prendere —
elencate nei commit. Le più importanti:

- **Il verde usato come decorazione** (icone di sezione, «Scontrino medio», la
  colonna Totale dei coperti) era stato promosso a `positivo` dal mapping
  emerald→positivo: riportato a blu, perché non è un giudizio. È il difetto
  tipico di questa fase: il riscrittore vede la famiglia, non il significato.
- **Tabella dei margini**: righe di input neutre, righe «= Totale» in blu
  leggibile, margine e MOL dal segno; `SECTION_CONFIG` e la legenda a chip
  **rimossi** (spiegavano colori che non ci sono più). È un pezzo del §4b
  anticipato: senza il colore, la gerarchia la fanno grassetto e separatori
  già presenti.
- **O1 chiuso**: la gravità delle variazioni (critico/alto/medio) è una scala
  di grigi, il giudizio sta solo sull'impatto in euro.
- **H5/W1/W2**: le card tinte (Personale, Spese) sono neutre col totale in
  blu; il numero porta il colore, non il pannello.
- **AF1/T1**: i riquadri KPI sono neutri con «Spesa totale» in blu.
- **Il viola aveva due significati** (Note di credito, sede tecnica «Gruppo»)
  e la palette per dipendente ne aveva otto: categorie, ora blu e rampa.
- **Diario**: il colore che il cliente sceglie per un appunto passa sui token,
  e **«Viola» esce dal selettore** (nessun token): gli appunti già salvati con
  quella chiave cadono sul primo colore. Decisione presa qui, **da confermare
  con Mattia** (si rimette con una riga).
- **Bug preesistente trovato dal presidio**: `text-destructive-foreground` nel
  dialog di conferma non era mai stato dichiarato — il bottone rosso aveva il
  testo del colore sbagliato nel tema chiaro.
- **Style guide**: era tarata sul solo dark (`-400` senza `dark:`); ora sui
  token, con una sezione che mostra i tre livelli, i chip e la rampa — l'unica
  pagina dove verificare tutti i token nei due temi da un posto solo.

**Deviazioni dal piano, dichiarate:** perimetro allargato ad assistenza,
notifiche, impostazioni, style-guide (§7 diceva «solo pagine principali»; il
presidio vuole esclusioni, non inclusioni); legenda dei margini rimossa
(densità, ma conseguenza diretta del colore); `focus:ring-sky-500` → token
`ring` (19 input).

**Come è provato:** `tests/test_globals_css_contrasto.py` (41, 6 mutanti
uccisi) e `tests/test_colori_solo_token_frontend.py` (674 casi su **168** file — il
messaggio del commit `1a81d92` dice 134, cifra scritta senza misurarla; 8
mutanti, 6 rossi e 2 verdi come atteso: un commento e admin non devono
scattare). **Suite intera a repo fermo, al commit `47657a2`: 15.485 verdi +
45 skip = 15.530 raccolti** (`python -m pytest -q -p no:randomly` dalla root);
il primo run completo aveva UN rosso, un test che chiedeva la variante `dark:`
alle classi prezzo della catena — la premessa vecchia — corretto in `47657a2`. La rete frontend (40 file **contando il presidio nuovo**: erano 39 quando
l'ho eseguita) e i 10 test che leggono i sorgenti delle pagine: verdi. **Non provato: l'occhio.** Da questa sessione non si renderizza
(niente Playwright, e le pagine vere vogliono i dati di un cliente): la verifica
a schermo nei due temi la fa Mattia — la style guide è il posto da cui partire.

### Residui nuovi, misurati (vanno in coda al §11)

**R9 — il bianco sui bottoni `bg-primary` fa 2,71:1 in light e 2,17:1 in dark.**
È il kit shadcn così com'è (`--primary-foreground: oklch(1 0 0)`), su tutti i
bottoni dell'app da sempre. Sistemarlo vuol dire scurire il blu del brand sui
bottoni o mettere testo scuro sul blu nel dark: **è una decisione di Mattia**,
non un fix. Lo stesso vale per il bottone rosso del dialog di conferma
(`bg-destructive text-white`).

**R10 — «Viola» tolto dal selettore del diario**: gli appunti salvati con la
chiave `purple` si vedono blu. Da confermare o da rimettere (una riga).

**R11 — verifica a schermo nei due temi** di tutte le pagine: non fatta da
questa sessione, per impossibilità. La fase 3 (densità) va comunque una pagina
per volta *mostrata*, quindi la verifica può avvenire lì. Da guardare per
primo: il food cost «rosso» che passa da `destructive` a `negativo`
(`lib/foodcost.ts`), l'unico punto dove cambia *quale* token, non solo
palette→token.

**R12 — `/m` a metà** (rilievo della review, 18/09 sera): il briefing mobile
(`app/(mobile)/m/briefing/mobile-catena.tsx`) importa `SALUTE_TINT`, che ora è
sui token, e nelle righe accanto tiene ancora `emerald-500`, `amber-700`,
`rose-500` scritti a mano — due verdi diversi nella stessa schermata. `/m` è
fuori perimetro per decisione (§7); chi lo allineerà parte da lì.

**Da tenere d'occhio, non residui:** il presidio ha una lista di utility
non-colore; `text-shadow-*` (Tailwind 4.1) e `outline-offset` senza numero
oggi non sono usati e farebbero un falso rosso — si aggiungono quando servono.
`color-mix(in oklch, …)` nella cascata e nel gauge contro `in oklab` altrove:
stesso effetto, due grafie.

---

## 13. L'app vista a schermo — 70 screenshot, 21/09/2026

Il giro visivo che il §6 dichiarava mancante («l'app non è mai stata vista in
movimento») e che il §11 aveva messo in R11. Mattia ha caricato **70
screenshot** in `SCREEN APP 18.09/` (nome della cartella vecchio, contenuto
rifatto la mattina del 21/09, dopo i 12 commit della fase 2): **entrambi i
temi**, tre account diversi — CASATI 14 (singola sede), Gruppo SUSHILAND (5 PV)
e Gruppo OFFSIDE (finestre di ripartizione).

**Esito generale: il colore della fase 2 regge.** Nessun token non dichiarato,
nessun riquadro trasparente, nessuna coppia testo/fondo illeggibile in nessuno
dei due temi. La tabella Margini con la colonna del mese corrente evidenziata
in blu tenue funziona meglio dell'asterisco che sostituisce (§4c, chiuso).

### 13.1 Due bug veri, trovati guardando

**«Paghe non inserite» in verde** (Agenda → Personale, screen 27 e 29, in
entrambi i temi) — `fix(agenda)` `61f6a30`. Un dato *mancante* colorato come un
esito positivo. Le tre tessere affiancate dicevano la stessa cosa con tre
colori: `text-positivo` la prima, `text-incerto` le altre due, mentre il
commento sopra la terza dichiarava già che «lo dicono tutte e tre allo stesso
modo» — il codice non faceva quello che il suo stesso commento diceva. Il verde
l'ha introdotto `06bd099`, **un commit della fase 2**: è esattamente la trappola
`il-riscrittore-vede-la-famiglia`, la riscrittura ha letto la famiglia del
colore invece del significato. Presidio nuovo dentro
`test_colori_solo_token_frontend.py`: *la stessa etichetta a video non porta due
token semantici diversi nello stesso file* — regola generale, non toppa sulla
riga. Provato per mutazione (rimesso `text-positivo` → 1 failed sul file
giusto, 168 file verdi intorno), **e nella forma che la prima stesura
lasciava passare**: `Paghe{" "}non inserite` finiva in una chiave diversa
da `Paghe non inserite`, cioè lo stesso bug riscritto con uno spazio JSX
sarebbe sfuggito. La prima regex catturava 33 etichette su 215 (15%);
quella riscritta ne prende 75 (34%) — il resto non sono etichette fisse
(icone senza testo, numeri calcolati, testo di sola espressione) e in una
regola sul testo a video non possono entrare. Il presidio passa da 674 a
**849** test, misurati con `--collect-only`, non sommati.

**Lo stesso avviso ripetuto per 5 PV** (Catena → «Da vedere», screen 42 e 46) —
`fix(catena)` `5942dfc`. 13 righe di cui 5 identiche parola per parola. C3 del
§3, confermato a video. La trappola del raggruppamento è il bottone «Vedi PV»,
che è una **destinazione**: comprimere a una riga con un solo id avrebbe
commutato la sede attiva su un PV arbitrario (cookie + preferenza, effetto
persistente) — lo stesso incidente che il commento del file già documentava per
i segnali senza `ristorante_id`. Il gruppo tiene **tutti** i PV, il bottone
compare solo quando la destinazione è una, i nomi vanno nel `title`. La logica
sta in `lib/catena-segnali.ts` — usata **sia** dal desktop **sia** da `/m`
(`m/briefing/mobile-catena.tsx`, allineato nello stesso giro: consumava lo
stesso endpoint e mostrava le stesse 5 righe identiche) — e **non** in
`lib/gruppo.ts` perché quello
importa `react` e `./worker` e sotto node non si carica: la rete frontend non
avrebbe potuto eseguirlo. 4 mutanti su 4 uccisi — ma **uno dei quattro
muta un percorso che in produzione non si raggiunge**: `severity: "error"`
non è prodotto da nessuno dei 5 emettitori in `gruppo.py`, che
scrivono tutti `"warning"`. Il test resta (il campo è nel tipo e nel
payload: il giorno che il backend lo usa, un gruppo che declassa a warning
un PV in errore sarebbe un bug silenzioso), ma la cifra «4 su 4» diceva
più di quanto provasse: i mutanti su codice vivo sono **3**.

### 13.2 Rilievi del §3 confermati a video

- **O2** — la colonna «File» mostra al cliente i nomi XML grezzi
  (`IT02621200126_037BG.xml`), in Sconti e in Note di Credito (screen 10, 11,
  23, 24). Aperto.
- **O4** — la frase di sintesi si ripete identica: «Relazione complessivamente
  solida…» due fornitori di fila, «Fornitore stabile e coerente nel periodo
  osservato» tre di fila (screen 31, 36). 4 frasi in tutto per tutti i
  fornitori, e si nota. Aperto.
- **R5** — troncamenti senza tooltip, visibili in quattro schermate diverse:
  `AVICOVO S.N.C. DI SEVESO…`, `BRICOMAN ITALIA S.R.L. S…`, `SUSHILAND
  MARIAN…` (il nome sede nella barra laterale). Aperto, 93 punti su 125.

### 13.3 Rilievi che a video NON si riproducono

- **F1** (fasce vuote nello Scadenziario, screen 12 e 25): con una sola fascia
  piena la lettura è immediata — «tutto scaduto» si capisce a colpo d'occhio.
  **Chiuso, non era un difetto.**
- **T2** (date ammassate sull'asse di Analisi e Tag, screen 6, 7, 19, 20): le
  date sono otto e leggibili. Il rischio nel codice resta reale (nessun
  `interval`, backend non limitato), ma **su nessun dato reale di oggi si
  manifesta**: non è lavoro della fase 3.

### 13.4 Cosa resta da guardare

Tutti gli screenshot sono a schermo pieno (~1900px). **R2 resta aperto e non
verificato**: nessuna immagine a 1140/1280px, che è la larghezza dove il §11
sospettava il problema delle card Agenda→Personale, e dove il commento nel
codice di `personale-tab.tsx:1540` calcola 365px di contenuto su 223 di spazio.
Serve una finestra stretta, non un altro screenshot a tutto schermo.

---

## 14. Fase 3 riveduta — cosa resta davvero, dopo codice e screenshot

L'elenco del §5 è del 18/09 e precede sia i 12 commit della fase 2 sia il giro
visivo del §13. **Dei 22 rilievi ne restano 14.** Questa è la lista da cui si
parte quando la fase 3 si apre; l'elenco vecchio non va più usato.

**Prima della fase 3 si fanno R5, O2 e O4** (decisione di Mattia, 21/09): non
sono densità — sono dati che l'interfaccia nasconde o dice male — e non
richiedono il suo occhio. La fase 3 viene dopo.

### 14.1 Gli 8 che cadono

| Rilievo | Perché cade | Verificato |
|---|---|---|
| **H3** anello perso nel pannello | ring 128px in pannello con padding e senza altezza fissa: la geometria descritta non esiste | codice, `salute-card.tsx:18-19,51` |
| **H4** «Vai alla pagina» ×4 | un solo punto nel codice, non quattro | codice, `salute-card.tsx:98-101` |
| **M5** ciambella a due fette | è a N fette, con tooltip e legenda | codice + screen 33, 38 |
| **W4** «COSTO ORDINARIE» col trattino | oggi scrive «Paghe non inserite» | codice + screen 27, 29 |
| **F1** fasce vuote nello Scadenziario | con una sola fascia piena la lettura è immediata: «tutto scaduto» si capisce a colpo d'occhio | **screen 12, 25** |
| **T2** date ammassate sull'asse Tag | le date sono otto e leggibili | **screen 6, 7, 19, 20** |
| **W4b** «Paghe non inserite» in verde | chiuso oggi, `61f6a30` | screen 27, 29 |
| **C3** segnali duplicati | chiuso oggi, `5942dfc` + `541b961` (`/m`) | screen 42, 46 |

M5 e W4 dipendevano dai dati: lo screenshot originale era probabilmente vero
allora e semplicemente non si riproduce più. **T2 merita una riga a parte:** il
rischio nel codice è reale (nessun `interval` su `XAxis`, backend non limitato
in `tag_analytics_service.py:238-272`), ma su nessun dato reale di oggi si
manifesta. Non è lavoro della fase 3; se un cliente accumulerà abbastanza punti
tornerà da solo, e allora sarà un bug con una causa nota.

### 14.2 I 14 che restano

**Il pezzo grosso — la tabella Margini (§4).** Tre decisioni, tutte di Mattia:

- **(a) l'interruttore € / % / entrambi**, default €, preferenza ricordata.
  Oggi ogni cella porta il valore *e* la percentuale sotto (`calcolo-tab.tsx:604-611`);
  l'unico interruttore esistente è Totale/Media (`:244-263`). **Domanda aperta:
  la percentuale sotto ogni numero serve sempre, o quasi mai?**
- **(b) la gerarchia tipografica** al posto del colore: dettaglio grigio
  regolare, totali in grassetto con un filo di separazione sopra, MOL in fondo
  più grande.
- **(c) la colonna del mese corrente** — **già fatta e già buona**: negli
  screenshot 4, 17 la colonna evidenziata in blu tenue funziona meglio
  dell'asterisco che sostituisce. Resta solo da confermare che piaccia.

**I grafici senza scala** (2):

- **M4** — le sei tessere di Margini: `<svg>` + `<polyline>` nudi
  (`kpi-bar.tsx:45-62`), nessun asse, nessun `<title>`, nessun hover. Si capisce
  se sale o scende, non di quanto. Visibile negli screen 4, 17.
- **AF4** — mezzo chiuso: la tendenza di Analisi Fatture è una spezzata vera a
  più punti (`pivot-tab.tsx:206-225`), manca solo la scala. Screen 57, 58.

**Dati nascosti o detti male** (3 — **si fanno PRIMA della fase 3**):

- **R5** — 93 troncamenti su 125 senza `title`. Il modello da copiare è già nel
  codice: `pivot-tab.tsx:379` (`truncate max-w-44` **con** `title={row.dimensione}`). Peggiori: `scadenziario-client.tsx` 9 su 10,
  `workspace/personale-tab.tsx` 6 su 6, `catena/gruppo-tag-section.tsx` 5 su 5.
  Visibile negli screen 13, 26, 44, 47 e nel nome sede della barra laterale.
- **O2** — la colonna «File» mostra al cliente i nomi XML grezzi
  (`IT02621200126_037BG.xml`), in Sconti e in Note di Credito. Screen 10, 11,
  23, 24. `sconti-tab.tsx:286,318`, `nc-tab.tsx:180,201`.
- **O4** — la frase di sintesi dei fornitori si ripete identica: 4 frasi in
  tutto per tutti (`prezzi.py:1317-1322`). Screen 31, 36.

**Il resto** (6): H2, M1, F2, F4, T3 (resta solo la sovrapposizione
dell'etichetta «Media», il colore è già a posto), T4 (nessun limite sui
prodotti, `analisi-e-tag-client.tsx:1366-1415`), W5.

### 14.3 Il vincolo che non cambia

La fase 3 è **layout**, e il §6 dice che va rivista dopo aver visto l'app: ora
l'abbiamo vista, ma **solo a ~1900px**. Resta aperto **R2**: nessuno screenshot
a 1140/1280px, che è la larghezza dove il commento in `personale-tab.tsx:1540`
calcola 365px di contenuto su 223 di spazio. **Una pagina per volta, mostrata
prima di passare oltre** (§7) vale ancora: gli screenshot dicono com'è adesso,
non come sarà dopo una modifica al layout.
