# Pagina Servizi (Marketing)

Stato e roadmap della pagina **Servizi / Assistenza** di ONEFLUX (route `/assistenza`).
Documento operativo: cosa è stato fatto, cosa resta, e le decisioni prese su cosa
NON fare. È la nostra versione rielaborata del brief iniziale, con priorità ribaltate
rispetto al prompt originale.

Ultimo aggiornamento: 2026-06-10

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

### 2. Trigger contestuali — SECONDO, con disciplina
Dentro l'app, dove il ristoratore *vede* un problema, offrirgli il servizio che lo
risolve (food cost alto → Check-up; margine basso → Consulenza Gestionale).
È il vero moltiplicatore di valore della pagina.
**Regola ferrea (filosofia ONEFLUX, non invadente):**
- massimo **1 trigger per pagina**;
- **dismissibile**, ricordato come chiuso;
- **mai popup, mai bloccante** — un banner discreto, non un'agenzia che insegue.
- Vive in altre pagine (non in `/assistenza`); rimanda alla card giusta.

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
