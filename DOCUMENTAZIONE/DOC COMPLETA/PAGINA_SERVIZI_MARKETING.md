# Pagina Servizi (Marketing)

Stato e roadmap della pagina **Servizi / Assistenza** di ONEFLUX (route `/assistenza`).
Documento operativo: cosa è stato fatto, cosa resta, e le decisioni prese su cosa
NON fare. È la nostra versione rielaborata del brief iniziale, con priorità ribaltate
rispetto al prompt originale.

Ultimo aggiornamento: 2026-06-10 (aggiunti trigger contestuali soft)

---

## Cos'è
Pagina servizi nativa di ONEFLUX (non una landing da agenzia): un catalogo di 6
servizi con CTA `Richiedi info` (lead) + `WhatsApp`. Tono semplice, premium,
concreto, per ristoratori spesso poco tecnici.

**File coinvolti:**
- `apps/web/src/lib/assistenza.ts` — catalogo dati tipizzato + helper WhatsApp + tipi lead admin
- `apps/web/src/app/(app)/assistenza/page.tsx` — pagina (header + sottotitolo)
- `apps/web/src/app/(app)/assistenza/marketplace.tsx` — render card + dialog lead
- `apps/web/src/components/ui/page-header.tsx` — prop `subtitle` (riutilizzabile)
- `apps/web/src/app/api/assistenza/lead/route.ts` — proxy lead → worker (NON modificato)

---

## I 6 servizi

| # | Servizio | Gruppo visivo | Prezzo mostrato |
|---|----------|---------------|-----------------|
| 1 | **Check-up Operativo** | Civetta (giallo, in primo piano) | `49€ una tantum` |
| 2 | Consulenza Gestionale | OneFlux (azzurro) | `da 199€/mese` |
| 3 | Assistenza Continuativa | OneFlux (azzurro) | `99€/mese` |
| 4 | Analisi su Richiesta | OneFlux (azzurro) | `da 49€ una tantum` |
| 5 | Ottimizzazione Costi | Partner (rosso) | — (su preventivo) |
| 6 | Sito e Presenza Online | Partner (rosso) | — (su preventivo) |

La card 6 cita Recoma System solo come collaborazione (label + link informativo
secondario); il servizio NON si chiama Recoma.

---

## ✅ FATTO (Fase 1 + ritocchi)

### Contenuti e struttura
- 6 card con i nuovi contenuti (copy definitivo), nell'ordine voluto.
- Catalogo `assistenza.ts` riscritto con tipo forte:
  - `ServizioIconName` (union type: un refuso icona è errore a compile-time, non
    fallback silenzioso a runtime).
  - `variant`: `default | featured | partner`.
  - campi predisposti per il futuro ma usati con parsimonia: `priceMode`,
    `priceValue`, `isFutureAutomated`, `asyncReportTopics`, `notesInternal`,
    `partnerLabel`, `partnerUrl`.
- Header pagina con **sottotitolo visibile** (nuova prop `subtitle` su `PageHeader`,
  retro-compatibile con le altre pagine).

### Resa grafica — tre gruppi nettamente distinti
Ogni gruppo ha `border-2` spesso + ombra colorata coordinata sullo stesso accento:
- **Civetta (card 1)** — GIALLO/amber. Card "in primo piano": `scale-[1.04]`,
  `-translate-y-2`, `shadow-2xl`, `z-10`; hover che la avvicina ancora. Effetto 3D
  di vicinanza.
- **OneFlux (card 2-3-4)** — AZZURRO ONEFLUX (sky), tutte identiche tra loro.
- **Partner (card 5-6)** — ROSSO, stessa logica di contorno/ombra.
- Icone e micro-label intonate all'accento del proprio gruppo.

### Prezzi
- Badge prezzo visibile in alto a destra (card 1-4), in tinta col gruppo.
- Card partner (5-6) **senza badge**: prezzo su preventivo (`priceValue` vuoto a
  bivio, `priceMode: custom` resta nei dati).

### Layout / qualità
- Griglia 3×2 desktop, responsive (collassa su tablet/mobile).
- `auto-rows-fr` + `h-full`: card di altezza uniforme, CTA allineate in fondo.
- Padding sulla grid per non clippare ombra/scala della card sollevata.
- Accessibilità: `aria-label` contestuale sui link WhatsApp.
- Lead flow invariato: payload `servizio_key/servizio_label/messaggio` → worker →
  tabella `marketplaceleads` → coda admin. Nessuna regressione.

### Trigger contestuali soft (era roadmap punto 2 — ora fatto)
Suggerimenti discreti che, dentro l'app, propongono il servizio giusto quando
c'è un segnale reale. Canale **separato** da briefing/notifiche operative: quelle
restano pulite e fidate, qui non entrano proposte commerciali.

- **Architettura** (`apps/web/src/lib/trigger-servizi.ts`): unica fonte di verità.
  Mappa 4 trigger → card di `/assistenza` + `valutaTrigger()` puro che decide SE
  e QUALE mostrare, **al massimo uno per pagina**. Card 5-6 (partner) mai
  triggerabili.
- **UI** (`apps/web/src/components/trigger-hint.tsx`): banner leggero in fondo
  alla pagina, **mai popup, mai bloccante**, dismissibile con **cooldown 14gg**
  in `localStorage` (se ignorato non torna subito). Deep-link
  `/assistenza?servizio=<key>` che scrolla alla card, la evidenzia e apre il
  dialog lead.
- **Segnali — riuso di dati GIÀ calcolati, nessuna query pesante nuova:**
  - `/margini` → **Consulenza**: MOL negativo o food cost oltre soglia (dal KPI
    di pagina).
  - `/prezzi` → **Analisi su Richiesta**: prezzi in aumento (topic
    `price_alert`, letto da `contaTopicAttivo` su `fetchNotifiche` già cache-ata).
  - `/analisi-fatture` → **Check-up**: molte righe da classificare (topic
    `uncategorized_rows`).
- **Toggle per-cliente** (come i flag pagina): switch *"Suggerimenti servizi"*
  nel pannello admin del cliente. Salvato in `pagine_abilitate` con **convenzione
  inversa** (`trigger_servizi_off`): assente = **ON di default** (anche per i
  clienti esistenti), presente = spento. Nessuna migration, nessuna modifica al
  worker. Lettura centralizzata in `triggerAbilitati()`.

---

## 🔜 DA FARE (nostra roadmap, in ordine di priorità)

Priorità ribaltate rispetto al prompt originale: prima le cose piccole e utili,
dopo il resto.

### 1. Payload lead arricchito — PRIMO
Far arrivare lead più qualificati nella coda admin.
- Includere `partnerLabel` (così la coda distingue lead partner) e, per la card
  Analisi, il **topic selezionato** (food cost / margini / fornitori / prezzi /
  criticità / mercato — già in `asyncReportTopics`).
- Richiede: piccola modifica al `body` in `marketplace.tsx` + accettare i campi
  extra in `api/assistenza/lead/route.ts` e nel worker, senza rompere la coda
  esistente. Oggi c'è già un TODO commentato nel fetch.
- Rischio basso, ritorno alto.

### 2. Rifiniture dei trigger contestuali — quando servono
La base dei trigger è fatta (vedi sopra). Restano migliorie *opzionali*, da fare
solo se l'uso reale le richiede — non prima:
- **Trigger Assistenza Continuativa**: oggi non scatta da nessuna parte. Il suo
  segnale ("uso discontinuo / vuole delegare") richiederebbe un dato nuovo
  (giorni dall'ultimo accesso / inattività). Volutamente NON implementato per non
  inventare un calcolo: si aggancia quando avremo un segnale solido e raro.
- **Segnale "poche fatture" sul Check-up**: oggi il Check-up scatta solo sulle
  righe da classificare. Aggiungere "pochi dati caricati" serve un conteggio
  fatture lato server in pagina (ora non c'è pulito): da valutare.
- **Cooldown lato server invece di `localStorage`**: oggi il "non ripeterlo
  subito" è per-dispositivo (localStorage). Se serve renderlo per-utente
  (cross-device), si sposta su DB. Per ora basta così.

---

## ❌ NON FACCIAMO (decisioni prese — fuori scope)

Esplicitamente escluse dal piano, per non sovradimensionare un prodotto con pochi
clienti e per restare fedeli alla semplicità ONEFLUX.

- **Report asincroni automatici** (card Analisi). Il lead arriva col topic, si
  risponde **a mano** (PDF/messaggio). Niente pipeline di generazione/consegna
  in-app finché il volume non la giustifica. La struttura `asyncReportTopics`
  basta a questo scopo.
- **Automazione del Check-up in-app**. Generare il check-up automaticamente dai
  dati è un mini-prodotto, non un ritocco: prima va validato che il Check-up si
  venda a mano. `isFutureAutomated: true` resta solo come segnaposto/backlog.
- **Tracciamento click/lead per servizio**. Non ci interessa ora.
- **Pricing dinamico**. Per 6 servizi che cambiano di rado è complessità senza
  ritorno: i prezzi vivono nei dati (`priceValue`), si edita una riga. Declassato a
  "prezzi configurabili da dati", già fatto.
- **Deck commerciale Recoma / offerta lancio**. Materiale marketing/commerciale,
  non sviluppo della pagina: vivono altrove, non in questa roadmap tecnica.

---

## Note tecniche / vincoli
- `key` del servizio è mappato 1:1 a `servizio_key` nel payload lead e letto dalla
  coda admin: NON rinominare in id/slug senza toccare worker + tabella.
- Numero WhatsApp: `NEXT_PUBLIC_WHATSAPP_NUMERO` (fallback al numero noto).
- `priceValue` è testo già umano ("da 199€/mese"): nessuna formattazione runtime.

### Trigger — file e vincoli
- `lib/trigger-servizi.ts` — catalogo + `valutaTrigger()` (1 per pagina) +
  `triggerAbilitati()`. `TriggerDef.servizioKey` deve combaciare con un
  `Servizio.key` di `assistenza.ts`, altrimenti il deep-link non trova la card.
- `components/trigger-hint.tsx` — banner, cooldown `localStorage`
  (`oneflux_trigger_v1_*`). Alza `STORAGE_PREFIX` se cambia la semantica.
- Flag cliente `trigger_servizi_off` in **convenzione inversa** (presente =
  spento). NON usare `trigger_servizi` "dritto": la lista `pagine_abilitate` lato
  client porta solo le chiavi `true` (`_normalize_pagine` scarta i `false`),
  quindi un OFF deve essere una chiave PRESENTE.
- I segnali si leggono da dati GIÀ calcolati (KPI margini, topic notifiche via
  `contaTopicAttivo`). Regola: un trigger non deve mai introdurre query pesanti
  nuove — se il segnale non c'è pulito, il trigger NON scatta (meglio che inventare).
