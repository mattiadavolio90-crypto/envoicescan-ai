# ONEFLUX — Visione, Filosofia e Modello Commerciale

**Chi lavora:** Mattia D'Avolio (+ Claude come assistente)
**Titolare:** RECOMASYSTEM S.r.l. (P.IVA 12993240154, Trezzano)

> Questo documento copre **visione, filosofia e modello commerciale** — le parti
> che non cambiano a ogni deploy. Per lo stato tecnico: `CLAUDE.md` (le regole) e
> `DOCUMENTAZIONE/MAPPA_TECNICA.md` (dove sta cosa). Questo file **non è più** il
> documento di stato/piano: quel ruolo è stato ritirato il 17/7/2026 perché
> duplicava e disallineava rispetto a documenti aggiornati più spesso. Traccia
> storica della migrazione: `docs/storico/MIGRAZIONE_APP.md`.

---

## 1. COS'È ONEFLUX

ONEFLUX **non è un gestionale per ristoranti**.
ONEFLUX è una **piattaforma di servizi per il ristoratore**, orchestrata da un'AI che lo accompagna ogni giorno.

In Italia non esiste nulla del genere oggi. La concorrenza si divide in:
- **Software gestionali** (Tilby, iPratico, Passepartout) — freddi, transazionali
- **Software analisi/controllo gestione** (TomatoAI, Foodcost in Cloud, Olivia, Ristoratore Top, Biplanfood)
- **Consulenti F&B** — costosi, sporadici, manuali
- **Servizi separati** (utenze, POS, CRM) — frammentati

ONEFLUX li integra tutti in **un'unica esperienza AI-first**.

### Modello a 3 strati

```
STRATO 1 — AUTOMAZIONE (il software base)
   Fatture, Scadenze, Margini, Foodcost, Prezzi, Ricavi
   → Pricing 39-69€/mese (3 tier per volume fatture)

STRATO 2 — INTELLIGENZA (l'AI come tessuto)
   Briefing giornalieri, notifiche smart, alert prezzi, suggerimenti
   → Incluso nel pricing base

STRATO 3 — SERVIZI (il marketplace)
   Consulenza, studi menù, comparatori utenze/POS, formazione, lead gen
   → Pay-per-use, upselling, commissioni
```

Strato 1+2 è il **biglietto d'ingresso** ricorrente. Strato 3 è dove ONEFLUX diventa profittevole.

---

## 2. FILOSOFIA PORTANTE (regole d'oro inviolabili)

1. **App di analisi, NON live critica** — niente strumenti operativi tipo cassa/comande. Se va giù un giorno, va bene.
2. **Ristoratori antitecnologici** — soluzioni smart MA semplici. MAI complicare.
3. **AI-first** — l'AI orchestra, non è un addon.
4. **Dati MACRO** — assistente di gestione, niente granularità "quanti spaghetti hai venduto" (per quello c'è il gestionale).
5. **Modulare per il futuro** — mai più riscrivere come Streamlit.
6. **Componenti riutilizzabili** — una "Tabella Fatture" si usa in 5 posti.
7. **App uguale per tutti** — admin (Mattia) decide visibilità feature per cliente.
8. **Semplicità prioritaria su robustezza enterprise** — no Sentry, no Supabase Pro anticipato, no disaster recovery complesso.

---

## 3. POSIZIONAMENTO COMMERCIALE

### Modello di business
- **Prodotto**: ONEFLUX — by **MATTIA & RECOMA**
- **Mattia**: P.IVA personale, fornitore di ONEFLUX
- **RECOMASYSTEM S.r.l.**: rivende ONEFLUX ai suoi clienti (Mattia fattura RECOMA, RECOMA fattura cliente, assistenza la fa Mattia pagato da RECOMA)
- **Mattia diretto**: vende ONEFLUX a clienti non-RECOMA
- **Costi infrastruttura**: intestati a Mattia personalmente

### Pricing (3 tier)
| Piano | Prezzo | Fatture | Margine atteso |
|---|---|---|---|
| **Base** | €39/mese | fino a 50 | 72% |
| **Plus** | €49/mese | fino a 100 | 67% |
| **Pro** | €69/mese | fino a 200 | 65% |

**Costo variabile principale:** Invoicetronic (€0,10-0,15 per fattura — più pacchetti grandi compri, meno costa per fattura).

**Multi-ristorante:**
- Stessa P.IVA → abbonamento moltiplicato per N ristoranti + vista catena INCLUSA
- P.IVA diverse → abbonamenti separati

Il counter "Hai usato 47/100 fatture del tuo piano" deve essere SEMPRE visibile nell'account.
