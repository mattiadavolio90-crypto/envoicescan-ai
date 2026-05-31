# ONEFLUX MASTER — Visione, Piano e Stato

**Ultima revisione:** 31 maggio 2026 (rev. 19 — Personale: costo lavoro + ore extra + copia settimana implementati; audit + bugfix rev.18)
**Chi lavora:** Mattia D'Avolio (+ Claude come assistente)
**Clienti attivi:** 2 in fase di test + 1 operativo — Streamlit deve restare acceso in parallelo
**Stack:** Next.js 16.2.6 + Tailwind v4 + shadcn/ui v4 + FastAPI (Railway) + Supabase

> Questo è l'unico documento di riferimento. Ogni decisione futura va presa in coerenza con quanto scritto qui. Se qualcosa cambia in modo significativo, si aggiorna questo file.

---

## 1. COS'È ONEFLUX 2.0

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
- **RECOMA SYSTEM SRL**: rivende ONEFLUX ai suoi clienti (Mattia fattura RECOMA, RECOMA fattura cliente, assistenza la fa Mattia pagato da RECOMA)
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

---

## 4. ARCHITETTURA TECNICA

### Stack
- **Frontend**: Next.js 16.2.6 + Tailwind v4 + shadcn/ui v4
- **Backend API**: FastAPI Python (`services/fastapi_worker.py`) su Railway
- **Worker async**: Python (`worker/run.py`) su GitHub Actions
- **Database**: Supabase PostgreSQL
- **Storage**: Supabase Storage (PDF/XML fatture)
- **Edge Functions**: Deno (`invoicetronic-webhook`)
- **AI**: GPT-4o-mini (valutiamo Claude Haiku 4.5 in Fase 7)

### Infrastruttura
| Servizio | Piano | Note |
|---|---|---|
| Railway `ingenious-fascination` | €5/mese | Streamlit + worker + queue-worker, manteniamo per FastAPI post-migrazione |
| Railway `exemplary-creation` | vuoto | Da eliminare |
| Vercel `oneflux-web` | gratis ora, Pro €20 quando serve | nuovo.oneflux.it |
| Supabase | gratis ora, Pro €25 SOLO quando free dà problemi reali | NON upgrade anticipato |
| Brevo, GitHub Actions, OpenAI, Aruba | invariati | |

### URL e dominio
- **Streamlit attuale**: app.oneflux.it (resta acceso fino Fase 10)
- **Next.js nuovo**: nuovo.oneflux.it (online da 26 maggio 2026)
- **Database condiviso**: entrambi puntano allo stesso Supabase → nessuna sincronizzazione necessaria

### Monitoring strategy (NO Sentry)
Script on-demand, da implementare gradualmente uno per uno:
- `/oneflux-health` · `/oneflux-costs` · `/oneflux-usage` · `/oneflux-anomalies` · `/oneflux-tests` · `/oneflux-backup`

### Scalabilità
Next.js è usato da Notion, TikTok, Nike, GitHub. Supabase è PostgreSQL. FastAPI è Python già esistente. Non ci sono limitazioni rilevanti per ONEFLUX nel medio-lungo termine.

---

## 5. STRUTTURA APPLICATIVA (UX)

### Layout
- **SOLO sidebar a sinistra** (no topbar, schermo pulito)
- Dropdown ristorante prominente in alto sidebar (per multi-ristorante)
- Nessun branding pesante, esperienza pulita

### Sidebar
```
🏠 Home
📄 Analisi Fatture
🏷️ Prezzi
📊 Ricavi e Margini
🧰 Strumenti          ← ex Foodcost; pagina-contenitore con tab (Foodcost/Diario/Personale/Inventario)
🏷️ Analisi e Tag
📅 Gestione Fatture   ← ex Scadenziario; cestino integrato come widget
─────────
🔔 Notifiche
⚙️ Impostazioni
🛡️ Admin              ← solo admin
─────────
👤 [nome utente]      ← footer: dropdown con solo "Esci" (logout)
```
> La sidebar reale (rev. 15) differisce dal layout concettuale originale: "Scadenziario" è ora "Gestione Fatture", il "Cestino" non è più una voce ma un widget interno, "Report" è stato **rimosso dalla sidebar** (placeholder non necessario), "Account" non è più voce nel dropdown footer (ridondante con Impostazioni — il footer ora apre solo il logout), "Assistenza" non è ancora presente.

> "Ricavi e Margini" è una voce unica in sidebar (scelta pragmatica confermata, 29/5).

### Modello adattivo multi-ristorante
- **1 ristorante**: modalità ristorante-centrica (catena invisibile)
- **2+ ristoranti**: modalità catena-centrica all'avvio — vista predefinita "Tutti i punti vendita", dropdown sempre prominente, notifiche raggruppate con drill-down, briefing AI a 2 livelli (catena + ristorante)

### Home (cuore dell'app)
```
┌─ Briefing AI personalizzato ──────────────┐
│ "Buongiorno Mario! Margine settimana 28%, │
│  3 fatture in scadenza, 1 alert prezzo."  │
└───────────────────────────────────────────┘
┌─ KPI cards ───────────────────────────────┐
│ Margine | Da pagare | Fatture nuove       │
└───────────────────────────────────────────┘
┌─ Notifiche (filtri per categoria) ────────┐
│ 🔴 Urgenti | 🟡 Importanti | 🔵 Info       │
│ • Notifica actionable con bottoni inline  │
│ • Raggruppate intelligentemente           │
└───────────────────────────────────────────┘
```

### Popup / pannelli di dettaglio
- **Solo peek laterale singolo** (50% schermo, a destra)
- Niente fluttuanti, niente multi-pannello, niente persistenza
- Apri → guardi → chiudi.

### Mobile (PWA)
- Solo 3 sezioni: Assistenza + Notifiche + Chat AI
- Niente popup, niente complessità, niente push notifications inizialmente
- PWA installabile da browser

---

## 6. AI ASSISTANT

### Cosa fa nell'MVP
- ✅ **Briefing giornaliero** (già in `daily_briefing_service`, da esporre meglio in Next.js)
- ✅ **Notifiche intelligenti** (categorizzate, prioritizzate, actionable)
- ❌ Q&A complessi → rimandati post-MVP
- ❌ Azioni autonome → rimandate

### Regole di affidabilità
- **L'AI NON calcola mai numeri** — il backend Python calcola, l'AI racconta
- Garanzia: zero numeri inventati

### GDPR / Privacy
- Anonimizzazione lato backend: AI riceve "Fornitore_123", non "Macelleria Rossi srl"
- DPA standard firmati con OpenAI
- In futuro (Q&A): Anthropic via AWS Bedrock EU per data residency UE

### Costi / contatore
- Limite quotidiano configurabile per cliente
- Counter visibile nel pannello account
- Soft block quando superato

### Personalità
- Tono amichevole (non formale, non eccessivamente colloquiale)
- No memoria conversazioni tra sessioni
- Suggerimenti upselling max 1 al giorno

### AI adapter
Layer di astrazione per cambiare provider AI con 1 riga di config. Non legati a OpenAI per sempre.

---

## 7. INTEGRAZIONE GESTIONALI (Passepartout / altri)

### Sistema import ricavi a 2 livelli

**LIVELLO 1 — AUTOMATICO via email** (per chi ha gestionale completo come PassBI)
- Email schedulata a `agent@oneflux.it`
- Oggetto template: `ONEFLUX_RICAVI_<account_id>_<periodo>`
- Allegato CSV/XLS strutturato → parsing automatico → conferma email

**LIVELLO 2 — MANUALE** (per chi non ha gestionale o ha solo registratore di cassa)
- Dialog "Carica ricavi": calendario mensile visuale + XLS Passbi v1 + modalità giornaliero/mensile

### Formato CSV standard
```
Data;Categoria;Totale_Venduto
01/03/2026;BEVANDE FREDDE;65,00
01/03/2026;CAFFETTERIA;31,50
```

### Blocchi temporali
- Mese corrente e precedente → modificabili
- Storico più vecchio → bloccato (upgrade opzionale)

### Import XLS (Passbi v1) — stato tecnico (29/5)
- Auto-detection versione gestionale
- Regole proforma/IVA, scorporo lordo→netto, aggregazione per giorno
- Righe di altri ristoranti ignorate con avviso esplicito (multi-ristorante non supportato in import)
- Limite file: 10 MB · timeout: 30s
- **Decisione architetturale**: SHOP è solo centro di costo (nessun fatturato proprio). Ripartizione centri: solo 4 centri (FOOD/BEVERAGE/ALCOLICI/DOLCI), solo mensile (%), derivata in giornaliera al momento della visualizzazione — zero tabelle DB extra.

---

## 8. SEZIONI DETTAGLIATE

### 🏠 Home
Briefing AI + KPI cards + notifiche actionable con filtri per categoria. Oggi: KPI cards e grafico spesa mensile funzionanti. **Manca**: briefing AI e notifiche actionable inline.

### 📄 Fatture
Lista con filtri, ricerca, dettaglio peek a destra, azioni rapide (pagata, sposta, elimina). Categorizzazione automatica con review solo per bassa/media confidenza (routing a livelli sull'ingest — vedi §9). **Elimina fattura** disponibile direttamente nel peek anteprima (soft-delete → cestino). **Stato**: ✅ funzionale.

### 📅 Gestione Fatture (ex Scadenziario)
Vista agenda (bucket urgenza) + calendario cash-flow. KPI bar 4 card reattive ai filtri. Filtri periodo (chip) + multi-fornitore (popover). Scadenza override manuale. Bulk segna pagata + select-all per sezione. Regole fornitore (Dialog centrato, selezione multi-fornitore). Anteprima righe fattura lazy-load nel peek (con bottone Elimina). Pre-notifica aggregata nella inbox. **Cestino integrato**: widget collassabile aperto dal bottone "Cestino" accanto ad "Aggiorna" (ripristina / elimina definitivo / svuota tutto) — non più pagina separata in sidebar. **Stato**: ✅ completato + hardening debug (30/5) + rename/cestino-widget/elimina-da-peek (30/5).

### 🔔 Notifiche
Cronologia con filtri per categoria, auto-purge 30 giorni, priorità visiva (🔴🟡🔵).
4 miglioramenti da fare: actionable inline · raggruppamento intelligente · filtri con count · priorità colori.
**Stato**: ✅ funzionale (mancano i 4 miglioramenti).

### 📊 Ricavi e Margini
Tab **Marginalità**: KPI bar, pivot mensile editabile, MOL, dialog "Carica ricavi" (calendario + XLS Passbi v1 + giornaliero/mensile), dettaglio giornaliero con selettore mese.
Tab **Analisi Avanzate**: donut centri, line chart, performance card, commenti AI, ripartizione centri mensile (€/%), dettaglio giornaliero per centro.
**Stato**: ✅ chiusa e consolidata (vedi changelog §14).

### 🏷️ Prezzi
Alert aumenti, storico prezzi per prodotto, sconti/omaggi, note credito, soglia alert configurabile. **Stato**: ✅ funzionale (UX dei 3 tab allineata al design system, 29/5). **Audit aperto**: vedi changelog §14 "Prezzi — Redesign + audit" per i 3 bug di correttezza da chiudere.

### 🧰 Strumenti (ex Foodcost) — Fase 6
Pagina-contenitore "layer a parte" con strumenti operativi che il ristoratore farebbe altrimenti su Excel/altre app. Route `/workspace`, etichetta sidebar **"Strumenti"** (icona cassetta attrezzi), flag `workspace` (ri-allineato con Streamlit, che già usava `workspace`). **4 tab:**
- **Foodcost** ✅ — riscrittura completa del foodcost Streamlit: ricette con ingredienti dalle **fatture reali** o da altre ricette (semilavorati), conversione UM, estrazione grammatura, foodcost/margine/incidenza per piatto. **Upgrade chiave implementato:** matrice **menu engineering** (Stelle/Cavalli/Enigmi/Cani — popolarità × marginalità). Riusa le tabelle esistenti (`ricette`, ecc.) senza perdere dati clienti.
- **Inventario** ✅ — **conta-giacenze** semplice (articolo + quantità + valore), non movimentazione live (filosofia #4). Articoli pescabili dai prodotti delle fatture (autocomplete con UM bloccata da fattura). Date picker custom con pallini evidenziatori sui giorni con inventario esistente. KPI cards (valore magazzino, prodotti, categorie), analisi per categoria collassabile, Copia da snapshot (articoli con qty=0 da data precedente), export CSV per Excel. DB: tabella `inventario_voci` con colonna `valore_totale` calcolata (GENERATED ALWAYS AS).
- **Diario** ✅ — calendario condiviso per ristorante: vista mensile a griglia con pallini colorati sui giorni con eventi, pannello laterale lista eventi del giorno selezionato, dialog aggiungi/modifica (titolo, data, orario opzionale, note, 6 colori). Migrazione automatica `note_diario` → `diario_eventi` nella migration SQL.
- **Personale** ✅ — turni a nomi liberi con autocomplete dai nomi già usati; vista settimana (griglia 7 colonne, click su cella per aggiungere) + vista mese (lista per data); KPI cards monte ore per persona; export CSV per ufficio paghe. Solo ore, NON gestionale HR.

**Stato**: ✅ **4/4 tab completati (31/5)** — Fase 6 chiusa.

### 💼 Assistenza
Chat AI opzionale + marketplace servizi: consulenza F&B, studio menù, comparatori utenze/POS, lead gen verso partner. Pagamenti **esterni all'app** (no Stripe integrato). **Stato**: ⏳ zero codice.

### ⚙️ Account
Dati ristorante, contatori utilizzo (fatture/mese, query AI/giorno), preferenze, logout. **Stato**: ⏳ placeholder.

---

## 9. ADMIN PANEL (redesign in Fase 7)

### Funzioni esistenti da mantenere
- Gestione clienti (crea, modifica, disabilita)
- Impersonazione cliente (per troubleshooting)
- Review righe €0 con classificazione speciale
- Memoria AI (globale, clienti, conflitti, audit)
- Verifica integrità DB · Costi AI per cliente

### Onboarding nuovo cliente (flusso esistente OK)
1. Admin inserisce: email + nome ristorante + P.IVA + ragione sociale
2. Sistema crea account `attivo=False`, `password_hash=NULL`
3. Email automatica con token 24h
4. Cliente imposta password sua (admin non vede)
5. Account diventa attivo

### Categorizzazione AI automatica — ✅ implementata (routing a livelli sull'ingest, 30/5)
Realizzata in `upload_handler.py` + `worker/queue_processor.py` via `classifica_via_worker_con_confidenza` (buckets di confidenza, non percentuali):
- **altissima / alta** → `needs_review=False` — bypassa coda (diciture sicure €0, sconti/omaggi verificati, hit memoria/regole forti)
- **media** → `needs_review=True` — pre-classificato MA messo in coda admin per review (dizionario fallback, GPT incerto)
- **bassa** → `needs_review=True` — fallback canonico + coda
- Guardrail BUG1: nessuna dicitura con prezzo > 0 entra in memoria globale
- **MAI** inserire `categoria = 'Da Clasificare'` (constraint DB) — vedi CLAUDE.md. Fallback: `"SERVIZI E CONSULENZE"`

### Agent notturno AI — ✅ nuovo (30/5)
Processo di manutenzione AI schedulabile, gestito da `/admin/sistema` con **toggle on/off** + "Esegui ora". Endpoint worker `/api/admin/sistema/agent-notturno/{toggle,esegui-ora}`. Automatizza la pulizia della coda review (auto-review delle diciture/sconti sicuri) senza intervento manuale dell'admin.

### Audit log azioni AI — ✅ nuovo (30/5)
Tabella `ai_review_log` (migration `20260530120000_create_ai_review_log.sql`). Ogni azione AI dell'admin (classificazione coda, auto-review, promozione conflitti) è loggata e **annullabile (undo)** dalla pagina Qualità AI.

### Da aggiungere in Fase 7
- UI admin per mapping ragione sociale → ristorante (tabella `ricavi_ragione_sociale_map`, già in DB)
- Dropdown switch ristorante in sidebar (oggi single-tenant)

---

## 10. NOTIFICHE DI SISTEMA

| Tipo | Esempio | Dove |
|---|---|---|
| **Manutenzione** | "Sab 28/05 ore 03:00, 30 min" | Banner sticky in cima home (chiudibile) |
| **Novità feature** | "Nuovo grafico ricavi disponibile" | Notifica normale categoria "Sistema" |
| **Aggiornamento maggiore** | "Da oggi gestione ricavi automatica" | Modal al primo accesso (1 volta sola) |

Implementiamo tabella DB `system_announcements` gestita da Admin Panel.

---

## 11. SICUREZZA E GDPR

### Invariato
- Password Argon2 (m=65536, t=3) — non toccare mai
- Token sessione 30 giorni · Rate limiting login (5 tentativi → 15 min block)
- Validazione file upload (magic bytes PDF/XML/P7M)
- Soft-delete via `filter_active()` per tutte le entità

### Migliorato con Next.js (già attivo)
- Cookie HttpOnly per sessioni (vs token in localStorage)
- Header sicurezza standard (CSP, HSTS, X-Frame-Options)
- Anonimizzazione dati prima di chiamate AI

### Post-MVP
- Migrazione a Supabase Auth completo (RLS reale)
- DPA con Anthropic se passiamo a Claude

---

## 12. SVILUPPO FUTURO (post-MVP)

1. Q&A AI complessi (domanda libera sui propri dati)
2. Push notifications mobile (service worker + push server)
3. Real-time updates (Supabase Realtime)
4. Voice/video AI
5. App nativa iOS (se PWA insufficiente)
6. Migrazione a Supabase Auth completo
7. Multi-distributore B2B2C (rivenditori oltre RECOMA)
8. White-label / multi-brand
9. Integrazioni delivery (Deliveroo, JustEat → ricalcolo margini)
10. Integrazione CRM prenotazioni (TheFork, 7rooms → analisi coperti)

### Tab Personale — stato evoluzioni (rev. 19)

1. ~~**Costo del lavoro** (costo orario per dipendente → costo periodo)~~ ✅ **Implementato (rev.19):** colonna `costo_orario`, card "Costo lavoro", costo per persona. **Manca il tie-in finale ⬇️.**
2. ~~**Copia settimana precedente**~~ ✅ **Implementato (rev.19):** endpoint `copia-settimana` + pulsante in vista Settimana.
3. ~~**Ore extra ("di cui")**~~ ✅ **Implementato (rev.19):** colonna `ore_extra`, card "Totale extra" (ambra), badge per turno/persona, colonna CSV.

**🔜 Da fare — interfaccia Personale ↔ Margini (incidenza % costo lavoro):** il dato "Costo lavoro del periodo" esiste già lato Personale; va portato nella pagina **Ricavi e Margini** incrociandolo con `ricavi_giornalieri` per mostrare il **costo personale %** accanto a foodcost e margine — la metrica che ogni ristoratore guarda. *Stima:* nel servizio margini, sommare `Σ(ore × costo_orario)` dei turni nel periodo selezionato e dividere per i ricavi del periodo; 1 KPI card "Costo personale %" + eventuale riga nel conto economico semplificato. Nessuna nuova tabella.

---

## 13. CONTATTI E ACCESSI

- **Email admin**: md@oneflux.it
- **Email sistema**: agent@oneflux.it
- **Email backup**: mattiadavolio90@gmail.com
- **GitHub**: mattiadavolio90-crypto
- **Vercel / Railway / Supabase**: account Mattia
- **Supabase project**: vthikmfpywilukizputn.supabase.co

---

## 14. PIANO DI MIGRAZIONE DETTAGLIATO

### Cosa sta succedendo — spiegazione semplice

L'app ONEFLUX oggi funziona con un'unica grande applicazione Python (Streamlit) che fa tutto. La nuova architettura divide il lavoro:
- **Next.js**: si occupa di quello che l'utente vede (pagine, bottoni, tabelle)
- **FastAPI + Supabase + Worker**: continuano a fare tutto il lavoro pesante — **non si toccano**

I due sistemi usano lo stesso database Supabase. Un cliente che carica una fattura su Streamlit la vede subito anche in Next.js. Streamlit resta acceso per tutti i 6-9 mesi di sviluppo, su `app.oneflux.it`. Next.js è disponibile su `nuovo.oneflux.it`.

### Modifiche strutturali rispetto al piano originale

**M1 — Fase 0.5 completata:** rimosso `@st.cache_data` da service Python. Nessun cambiamento visibile per clienti.

**M2 — Coesistenza Streamlit + Next.js:** durante sviluppo `app.oneflux.it` → Streamlit, `nuovo.oneflux.it` → Next.js. Switch finale solo quando Next.js supera checklist + 1 settimana uso personale + avviso clienti.

**M3 — Test con clienti reali:** i 2 clienti di test provano `nuovo.oneflux.it` mentre continuano su Streamlit. Nessun impegno formale.

**M4 — Upload file: limite 4.5 MB:** le fatture elettroniche italiane (XML 10-200 KB, P7M fino a 500 KB, PDF fino a 4 MB) rientrano tutte. Niente pre-signed URL, niente complessità extra.

**M5 — Auth: cookie HttpOnly ora, multi-dispositivo post-MVP** con Supabase Auth completo.

**M6 — Tab Ricavi eliminato:** inserimento ricavi spostato nel tab Marginalità via dialog "Carica ricavi". La voce sidebar "Ricavi e Margini" accorpa entrambe le funzioni.

**M7 — Foodcost: riscrittura completa, nessuna parità numerica richiesta.**

**M8 — Admin: redesign + AI categorization automatica in Fase 7.** Prima della fase, sessione di analisi per mappare esattamente cosa serve.

**M9 — Design system obbligatorio prima di Fase 2:** palette `#0ea5e9`, Inter, shadcn completo, pagina `style-guide`. ✅ Completato.

**M10 — Comunicazione clienti:** messaggio + video breve da preparare durante Fase 9, non ora.

### Roadmap completa — stato attuale

| Fase | Durata | Stato | Output |
|---|---|---|---|
| Fase 0 | — | ✅ | Cleanup, OpenAPI schema |
| Fase 0.5 | — | ✅ | `_make_cache()` pattern, no Streamlit deps nei service |
| Fase 1 | — | ✅ (26/5) | Next.js scaffold + Vercel + nuovo.oneflux.it |
| Fase 1b | — | ✅ | Design system: palette sky `#0ea5e9`, shadcn completo, sidebar collapsible, style-guide |
| Fase 1.5 | — | ⏸️ rimandata | Studio competitor — non bloccante |
| Fase 2 | 2-3 sett. | ✅ **chiusa (30/5)** | Auth login/logout/me ✅ · reset password ✅ · onboarding primo accesso ✅ |
| Fase 3 | 2-3 sett. | 🟡 parziale | Dashboard ✅ · Notifiche ✅ · Upload ✅ — **manca**: Home con briefing AI + notifiche actionable |
| Fase 4 | 1-2 sett. | ✅ **chiusa (30/5)** | Analisi Fatture ✅ · Analisi e Tag ✅ · Gestione Fatture (ex Scadenziario) ✅ · Cestino ✅ (ora widget integrato) · elimina da peek ✅ |
| Fase 5 | 2-3 sett. | ✅ **chiusa (28/5) + hardening (29/5)** | Margini ✅ · Ricavi ✅ · Analisi Avanzate ✅ · Prezzi ✅ · DB migrated · contratto FE↔worker allineato |
| Fase 6 | 2-3 sett. | ✅ **chiusa (31/5)** | **Strumenti** (ex Foodcost): pagina `/workspace` a 4 tab. Foodcost ✅ · Inventario ✅ · Diario ✅ · Personale ✅ |
| Fase 7 | 3-4 sett. | ✅ **chiusa + over-delivery (30/5)** | Admin Core ✅ · Qualità AI ✅ (coda review, auto-review, memoria globale, conflitti, **audit log + undo**) · Sistema/Salute ✅ (costi AI, retention, **agent notturno on/off**; tab Integrità DB rimosso) · **routing confidenza automatica sull'ingest ✅** |
| Fase 8 | 2-3 sett. | 🟡 parziale | Assistenza marketplace ⏳ · Report ⏳ · Account ✅ (dati ristorante, piano, contatori, cambio password) |
| Fase 9 | 1-2 sett. | ⏳ | Test, performance, sicurezza + comunicazione clienti |
| Fase 10 | 2-3 sett. | ⏳ | Switch dominio + 30gg coesistenza |
| Fase 11 | 3-5 giorni | ⏳ | Pulizia Streamlit |
| **TOTALE** | **~7-9 mesi** | | App completamente migrata |

### Fotografia codice reale (30 maggio 2026)

**Infrastruttura ✅**
- `apps/web` su Next.js 16.2.6 + Tailwind v4 + shadcn/ui v4, deploy Vercel, `nuovo.oneflux.it` online
- Auth con cookie HttpOnly: route `/api/auth/{login,logout,me}` + `lib/auth.ts`
- Tutte le pagine consumano FastAPI worker su Railway via route proxy `/api/*`

**Pagine**
| Sezione | Stato | Note |
|---|---|---|
| Login | ✅ | Link "Hai dimenticato la password?" → `/forgot-password` (Next.js nativo) |
| Forgot password | ✅ | Form email → link Brevo → `/reset-password?token=XXX` |
| Reset password | ✅ | Token pre-compilato da URL + nuova password + redirect login |
| Onboarding primo accesso | ✅ | Stesso `/reset-password?token=XXX&onboarding=1` — testi personalizzati, admin Streamlit invia link Next.js |
| Account / Impostazioni | ✅ | Dati ristorante, piano + contatore fatture/mese, cambio password |
| Dashboard (Home) | 🟡 | KPI cards, grafico spesa, top fornitori/categorie. **Manca** briefing AI |
| Analisi Fatture | ✅ | KPI bar, filtri periodo, tab Articoli + Categorie + Fornitori, edit categoria batch, upload modal |
| Ricavi e Margini | ✅ | Tab Marginalità + Analisi Avanzate (vedi changelog §14) |
| Prezzi | ✅ | Variazioni, Sconti/Omaggi, Note Credito, soglia alert |
| Notifiche | ✅ | Lista, severity, dismiss, badge. **Manca** raggruppamento + azioni inline |
| Analisi e Tag | ✅ | Chip tag, periodo, KPI bar, trend prezzi, analisi fornitori, prodotti inline, suggerimenti, export XLS |
| Gestione Fatture (ex Scadenziario) | ✅ | Agenda + calendario + KPI bar + regole fornitore + elimina da peek + cestino widget integrato |
| Strumenti (ex Foodcost) | ✅ | Route `/workspace`, 4 tab. Foodcost ✅ · Inventario ✅ · Diario ✅ · Personale ✅ |
| Report | ⏳ | Placeholder — **rimosso dalla sidebar (31/5)**; route `(app)/report/page.tsx` ancora presente ma scollegata. Valutare se eliminarla o ripensare la feature |
| Impostazioni/Account | ✅ | Dati ristorante, piano + contatore, cambio password |
| Admin Panel | ✅ | Core (clienti con piano inline + inizio piano, onboarding, impersonazione, sedi, flags, mapping) · Qualità AI (coda review con suggerimento categoria + 1-click, auto-review, memoria globale, conflitti, audit log + undo) · Sistema/Salute (costi AI, retention, **agent notturno on/off**) · routing confidenza sull'ingest |

**Non ancora iniziato (zero codice):** Assistenza/Marketplace · Multi-ristorante (dropdown switch) · PWA/mobile · fattore_kg UI (Analisi e Tag v2)

**Rimosso/deprecato:** tab "Integrità DB" in `/admin/sistema` (troppi falsi positivi, 30/5) · sidebar voce "Cestino" (ora widget in Gestione Fatture) · route orfana `/cestino/page.tsx` ancora presente ma scollegata dalla sidebar — **da rimuovere** (raggiungibile solo via URL diretto) · sidebar voce "Report" (31/5, placeholder non necessario; route `(app)/report/page.tsx` ancora presente ma scollegata) · voce "Account" nel dropdown footer della sidebar (31/5, ridondante con Impostazioni — il footer ora apre solo "Esci").

**Prerequisito Railway:** aggiungere env var `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME` per attivare reset password in produzione.

### Changelog sessioni

**Fase 1b ✅ — Design system**
Palette sky `#0ea5e9`, Inter, shadcn (Button, Input, Card, Dialog, Sheet, Table, Sidebar, DropdownMenu, Select, Tooltip, Badge, Avatar, Skeleton, Sonner, Popover), pagina `style-guide`, layout sidebar collapsible.

**Fase 5 ✅ — Ricavi e Margini (28 maggio 2026)**
- Tab Ricavi eliminato → inserimento ricavi nel tab Marginalità via dialog "Carica ricavi"
- Dialog: calendario mensile visuale (click giorno → popover IVA10/IVA22/Altri), XLS Passbi v1, modalità giornaliero/mensile
- Analisi Avanzate: donut, line chart, performance card, commenti AI
- DB: `ricavi_modalita_mensile` + `ricavi_ragione_sociale_map` migrated

**Fase 5 — Hardening (29 maggio 2026)**
Bug strutturali scoperti durante audit approfondito (il frontend era stato sviluppato oltre il backend):

- **Ripartizione centri ora salva davvero.** Prima il dialog inviava `pct_*` (5 centri incl. SHOP) ma il worker accetta `fatturato_*` euro (4 centri): dati persi silenziosamente. Ora: dialog solo mensile, toggle €/%, 4 centri, converti in euro prima del POST.
- **Nessun split giornaliero per centro** (decisione di semplicità): la ripartizione è mensile. Il dettaglio giornaliero per centro si deriva distribuendo la % mensile sul netto reale di ogni giorno — nuovo endpoint `GET /api/margini/fatturato-centri-giorni`, **zero nuove tabelle DB**.
- **Modalità mensile ricavi ora rispettata.** `ricavi_modalita_mensile` veniva scritta ma mai letta nel calcolo. Aggiunto `_load_mensile_overrides` applicato a pivot Marginalità, KPI bar (totali + sparkline), Analisi Avanzate.
- **Import Passbi multi-ristorante.** Righe di altri ristoranti ignorate con avviso esplicito (prima sommate erroneamente sul ristorante corrente).
- **Robustezza import XLS.** Limite 10 MB + timeout 30s sulla route proxy.
- **Pulizia.** Rimosso `ricavi-tab.tsx` (codice morto ~1070 righe). Estratto `scorporoNetto()` + costanti aliquote IVA in `periodi.ts` (prima duplicati in ~6 punti).

**Aperto dopo hardening:** UI admin per mapping ragione sociale catene (tabella già in DB, manca solo l'interfaccia). Eventuale split giornaliero per centro solo se un cliente lo richiede esplicitamente.

**Prezzi — Redesign tab + audit (29 maggio 2026)**
Tutti e 3 i tab di Controllo Prezzi allineati allo stesso design system di Variazioni (auto-load on mount, filtro periodo a pill mese + "Tutto l'anno", filtri secondari ricerca/categoria/fornitore, banner KPI reattivo ai filtri). Sconti/Omaggi e Note di Credito separati in 2 tab distinti (scelta confermata). Aggiunta colonna **N. Documento** (numero reale fattura/NC) come penultima colonna in Sconti e NC: `numero_documento` deriva da `fatture_documenti` via map `{file_origine → numero_documento}` (`_load_num_documento_map`), nessun JOIN SQL (non supportato dall'SDK Supabase Python).

Audit di correttezza dei 3 tab — **✅ tutti e 3 chiusi (29/5):**
1. **Doppio conteggio Sconti ↔ NC** — `mask_totale_neg` ora limitata ai `file_origine` con `segno_compensazione=-1` in `fatture_documenti`; nuovo helper `_load_nc_file_origini`.
2. **`storico-prodotto` full-scan** — push `.ilike("descrizione")` + `.eq("fornitore")` a livello DB prima del loop pagine.
3. **Join `numero_documento` fragile** — rimosso filtro date da `_load_num_documento_map`; `file_origine` è univoco per ristorante.

Migliorie minori individuate (non bloccanti): estrarre `isoDateRange/fmtEuro/fmtData/MESI` condivisi tra i 3 tab; helper `lib/worker.ts` per de-duplicare le 5 route proxy; reset filtri secondari al cambio periodo anche in Sconti/NC (oggi solo in Variazioni); valutare falsi positivi dell'heuristica omaggi (riga a valore zero).

**Analisi e Tag — implementazione completa (sessione 29 maggio 2026)**

Pagina fuori roadmap originale, aggiunta su richiesta. Non segue la numerazione fasi ma è parte di Fase 4 (analisi fatture).

*Backend (Fase A):*
- `services/tag_analytics_service.py` — nuovo service analytics puro (KPI, trend prezzi, analisi fornitori, orfani); porta la logica da pagina Streamlit `4_analisi_personalizzata.py`
- `services/tag_suggestion_service.py` — algoritmo suggerimenti **riscritto da zero**: `_get_product_root` (primo token significativo, len≥4, no cifre, no stopword); `new_tag` per cluster radice comune (min 3 prodotti, min 5 occorrenze); `extend_tag` per radice già presente in tag esistente (min 2 occorrenze); rimosso fuzzy matching e aggregazione per unità di misura
- `services/fastapi_worker.py` — 14 nuovi endpoint `/api/tag/*` (CRUD tag, associazioni, analisi, orfani, suggerimenti)
- `services/db_service.py` — fix soft-delete mancante in `get_descrizioni_distinte` (violava regola #5)
- 22 test nuovi per analytics e suggestion; suite totale: 780 passati

*Frontend (Fase B):*
- `apps/web/src/app/(app)/analisi-e-tag/` — pagina lineare senza tab: chip tag selezionabili, pill periodo (anno + mesi), KPI bar (5 card tonate), trend prezzi collassabile (recharts + linea media), tabella fornitori con barre incidenza, sezione prodotti inline (ricerca + aggiungi + rimuovi), banner suggerimenti (widget ambra + card espandibile con lista checkbox + nome modificabile), export XLS client-side (SheetJS, 3 fogli)
- `apps/web/src/app/api/tag/` — 14 proxy routes + `_worker.ts` helper condiviso
- `apps/web/src/lib/tag.ts` — tipi TypeScript
- Sidebar: voce "Analisi e Tag" con icona `Tags`

*Bug fix post-deploy:*
- Soft-delete `get_descrizioni_distinte` (prodotti cestinati comparivano nella ricerca)
- `TagDialog.onSaved` ora usa l'oggetto restituito dal backend (no più doppia fetch + match fragile per nome)
- KPI card label con `min-height` uniforme (no più "ballerino" su label lunghe)
- Bottone Suggerimenti sempre visibile (prima nascosto nel banner vuoto — paradosso)
- Suggerimenti: card espandibile con lista prodotti flaggabile e nome tag modificabile

*Decisioni architetturali:*
- Suggerimenti solo per nome prodotto simile (radice), niente fuzzy/unità misura
- `extend_tag` reimplementato con stessa logica radice (non rimosso)
- Pagina standalone in sidebar (non tab dentro Prezzi o Analisi Fatture)
- `fattore_kg` supportato nel backend ma UI rimandata a v2
- Confronto multi-tag rimandato a v2

**Onboarding + Account (30 maggio 2026)**

*Onboarding primo accesso:*
- `/reset-password` accetta ora `?onboarding=1` — testi personalizzati (titolo "Benvenuto", banner info, bottone "Attiva il mio account", messaggio successo "Account attivato")
- Admin Streamlit (`pages/admin.py`) aggiornato: il link di attivazione inviato via Brevo punta ora a `https://nuovo.oneflux.it/reset-password?token=...&onboarding=1` (prima puntava a Streamlit)
- Zero modifiche backend necessarie — `reset-confirm` esistente gestisce già `attivo=False → True`

*Pagina Account (Fase 8 light):*
- `services/fastapi_worker.py` — 2 nuovi endpoint:
  - `GET /api/account/me` — profilo completo (email, nome ristorante, ragione sociale, P.IVA, piano, limite fatture/mese, fatture usate mese corrente, data iscrizione, ultimo accesso)
  - `POST /api/account/cambia-password` — verifica password attuale + aggiorna hash Argon2
- `apps/web/src/app/api/account/` — proxy routes Next.js (`_worker.ts`, `me/route.ts`, `cambia-password/route.ts`)
- `apps/web/src/app/(app)/impostazioni/page.tsx` — server component che carica dati account
- `apps/web/src/app/(app)/impostazioni/account-client.tsx` — 3 card: dati ristorante, piano + barra contatore fatture (colore reattivo: verde/amber/rosso), form cambio password
- Sidebar footer dropdown: aggiunto link "Account" sopra "Esci"

**Admin Panel Core — Fase 7 blocco 1 (30 maggio 2026)**

Audit completo del pannello Streamlit (`pages/admin.py`, 3779 righe) + redesign completo in Next.js come Super Pannello.

*Filosofia adottata:* automation-first — l'admin vede solo le eccezioni, non naviga tutto manualmente. Creazione clienti e sedi tramite **Dialog centrati** (no expander/popover cramped). Routing reale (`/admin/*`) invece dell'hack radio nascosto di Streamlit.

*Backend (`services/fastapi_worker.py` — nuova sezione admin):*
- **`_verify_admin`**: nuovo guard doppio (worker key + bearer token → utente → `is_admin`). Prima il `_verify_worker_key` non verificava affatto l'identità admin — questo è il prerequisito di sicurezza fondamentale.
- `GET /api/admin/overview` — KPI flotta (clienti, attivi, fatture mese, costi AI 30gg)
- `GET /api/admin/clienti` — lista clienti con stats aggregate, sedi, trial
- `GET /api/admin/clienti/{id}` — dettaglio cliente completo
- `POST /api/admin/clienti` — crea cliente + ristorante + invia email onboarding Brevo (email HTML centralizzata nel backend, non più duplicata inline in Streamlit)
- `PATCH /api/admin/clienti/{id}/account` — attiva/disattiva
- `POST /api/admin/clienti/{id}/reset-password` — token + email Brevo
- `PATCH /api/admin/clienti/{id}/email` — cambia email + invalida sessione
- `DELETE /api/admin/clienti/{id}` — elimina cascade (opz: memoria globale)
- `POST /api/admin/impersona/{id}` — genera session token per cliente target
- `GET/POST /api/admin/clienti/{id}/sedi` · `DELETE /api/admin/clienti/{id}/sedi/{sid}`
- `GET/POST /api/admin/ragione-sociale-map` · `DELETE /api/admin/ragione-sociale-map/{mid}`
- `PATCH /api/admin/clienti/{id}/flags` — feature flags (nuova tassonomia sidebar Next.js) + blocchi temporali
- `POST /api/admin/clienti/{id}/trial` — attiva trial 7 giorni

*Frontend (`apps/web`):*
- Layout `/admin` gated: `(app)/admin/layout.tsx` — redirect se non admin
- Sidebar: prop `isAdmin` + voce "Admin" con icona `ShieldCheck` visibile solo agli admin
- `(app)/admin/page.tsx` — overview 4 KPI card + link rapidi a sezioni
- `(app)/admin/clienti/page.tsx` + `clienti-client.tsx` — tabella ricercabile (nome/email/P.IVA), filtro stato, colonne piano/attività/fatture; bottone "+ Nuovo cliente" → Dialog centrato con form completo (email, nome, P.IVA, piano, ragione sociale)
- `(app)/admin/clienti/[id]/page.tsx` + `cliente-dettaglio-client.tsx` — scheda cliente: dati + 5 azioni rapide + feature flags (8 toggle switch) + gestione sedi (add/delete Dialog) + zona pericolosa (elimina con Dialog conferma)
- `(app)/admin/ragione-sociale/page.tsx` + `ragione-sociale-client.tsx` — tabella mapping con Dialog centrato per aggiungere nuove associazioni
- 14 route proxy Next.js under `app/api/admin/`
- `lib/admin.ts` — tipi condivisi (`Cliente`, `ClienteDettaglio`, `Sede`, `TrialInfo`) + helpers
- `components/admin/impersona-banner.tsx` — banner sticky ambra con "Esci" (cookie `oneflux_impersonate` + `oneflux_session_backup`)

*Meccanismo impersonazione:* `POST /api/admin/clienti/{id}/impersona` genera nuovo `session_token` per il cliente e ritorna `target_token`. Il frontend salva il token admin in `oneflux_session_backup` (HttpOnly), imposta `oneflux_session` = token cliente, e `oneflux_impersonate` = email cliente (leggibile da JS per il banner). Exit ripristina la sessione admin. Tutto loggato come `IMPERSONATION_START` nel worker.

*Feature flags — nuova tassonomia:* abbandonati i nomi vecchi Streamlit (`workspace/foodcost`, `calcolo_margine`, `controllo_prezzi`, `analisi_personalizzata`). Nuove chiavi: `analisi_fatture`, `prezzi`, `margini`, `foodcost`, `analisi_e_tag`, `scadenziario`, `blocco_anno_precedente`, `blocco_mesi_precedenti`.

*Rimandato al blocco 2 (Fase 7):* Qualità AI (coda classificazione, memoria conflitti) · Sistema/Salute (costi AI, integrità DB, retention monitor) · Audit log admin (`admin_audit` table).

**Admin Panel Blocco 2 — Fase 7 completa (30 maggio 2026)**

*Qualità AI (`/admin/qualita-ai` — 3 tab):*
- **Coda review**: carica righe speciali di tutti i clienti, le classifica con `classify_special_row_vectorized` (buckets: dicitura/sconto_omaggio/storno/da_verificare), le raggruppa per descrizione. Per ogni gruppo: 1 click per classificare + salvare in `prodotti_master`. Bottone "Auto-review" classifica in automatico tutte le diciture sicure (€=0, nessun hint economico) e sconti/omaggi (conferma categoria attuale) — con guardrail BUG1 (nessuna dicitura con prezzo>0 entra in memoria).
- **Memoria globale**: browse paginato di `prodotti_master` con ricerca full-text, filtri (tutti/verified/non_verified/sospetti). Per "sospetti": applica `applica_correzioni_dizionario` + `applica_regole_categoria_forti` per trovare divergenze AI→categoria attuale. Edit inline + delete per ogni voce.
- **Conflitti**: trova descrizioni presenti in `prodotti_utente` con categoria diversa da `prodotti_master`. Per ogni conflitto: "Promuovi" (locale→globale) o "Ignora" (marca come eccezione locale accettata).

*Sistema/Salute (`/admin/sistema` — 3 tab):*
- **Costi AI**: KPI cards (costo tot, vision, categorizzazioni, token) + quota Vision oggi per ristorante + tabella dettaglio per cliente. Periodi: 7/30/90 giorni. Alimentato da RPC `get_ai_costs_summary`, `get_ai_costs_timeseries`, `ai_usage_events`.
- **Integrità DB**: scan on-demand (filtro periodo: 30/90/180gg o tutto). 5 check: date invalide, importi estremi (>€50k), quantità negative, descrizioni vuote, totali non corrispondenti. Risultati espandibili per categoria.
- **Retention**: stato dell'ultimo ciclo automatico (data, righe eliminate, di cui dal cestino, stato ok/errore). Alimentato da `get_retention_last_status`.

*Backend (17 nuovi endpoint sotto `/api/admin/`):*
`GET /api/admin/qualita-ai/coda` · `POST /coda/classifica` · `POST /coda/auto-review` · `GET /qualita-ai/memoria` · `PATCH /qualita-ai/memoria/{id}` · `DELETE /qualita-ai/memoria/{id}` · `GET /qualita-ai/conflitti` · `POST /qualita-ai/conflitti/risolvi` · `GET /sistema/costi-ai` · `POST /sistema/integrita` · `GET /sistema/retention`

*Route proxy Next.js:* 11 nuovi file sotto `apps/web/src/app/api/admin/qualita-ai/` e `apps/web/src/app/api/admin/sistema/`.
Pagine overview aggiornata con 4 card di navigazione.

**Scadenziario — hardening debug (30 maggio 2026)**
Analisi di correttezza della pagina Scadenziario dopo il completamento funzionale. Fix applicati:

1. **Bug timezone date-only.** `new Date("YYYY-MM-DD")` veniva interpretata come mezzanotte UTC: in Italia (UTC+1/+2) spostava i confronti di un giorno. Effetto concreto: una fattura **in scadenza oggi** appariva **scaduta** (bordo + testo rossi in `DocumentoRow`), incoerente con `bucketizeDocumenti`. Nuovo helper `parseLocalDate()` in `lib/scadenziario.ts` (parsing come data locale) usato in `computeKpi`, `bucketizeDocumenti`, `DocumentoRow.isOverdue` e `CalendarView` (agg + dettaglio giorno).
2. **Calendario incoerente coi filtri.** La vista calendario riceveva i documenti grezzi ignorando il filtro fornitore. Ora riceve `documentiCalendario` (filtrato per fornitore; i chip periodo restano specifici dell'agenda perché il calendario ha la propria navigazione mensile).
3. **Pulizia import morti** in `scadenziario-client.tsx`: rimossi `Sheet*`, `Select/SelectContent/SelectItem/SelectTrigger/SelectValue` (in uso solo `NativeSelect`), tipo `CalendarGiorno`. Rimossi i tipi `CalendarGiorno`/`CalendarResponse` da `lib/scadenziario.ts`.

**Aperto (non bloccante, da valutare):**
- **Endpoint `/api/scadenziario/calendario` morto**: il `CalendarView` aggrega client-side e non chiama mai quella route. Lasciato in piedi come base per un'eventuale aggregazione server-side (utile se i documenti crescono molto); da rimuovere se si decide di non usarlo.
- **Reload completo dopo ogni "Paga" singolo**: `handlePaga` rifà `loadData()` (riscansione paginata di tutte le `fatture` sul worker). Per il singolo si potrebbe fare update ottimistico; il bulk già fa una sola chiamata.
- **N+1 POST nelle Regole multi-fornitore**: `handleSave` cicla una POST per fornitore. Valutare endpoint batch se le selezioni diventano grandi.
- **Selezione persistente al cambio filtro**: le fatture selezionate restano in `selectedFileOrigini` anche se escono dal filtro (la bulk bar le conta pur non essendo visibili).

**Routing confidenza + agent notturno + audit AI + Gestione Fatture (30 maggio 2026, sera — rev. 14)**

Sessioni successive alla chiusura della Fase 7, non ancora riflesse nelle revisioni precedenti:

- **Routing a livelli di confidenza sull'ingest** (`upload_handler.py`, `worker/queue_processor.py`): `classifica_via_worker_con_confidenza` ritorna i bucket; altissima/alta → no coda, media/bassa → coda con `needs_review=True`. Chiude la "Categorizzazione AI automatica" pianificata in §9.
- **Agent notturno AI** (`/admin/sistema`): toggle on/off + "Esegui ora", ~300 righe worker, 3 route proxy. Pulizia automatica della coda review.
- **Audit log + undo azioni AI**: tabella `ai_review_log`, ogni azione AI admin annullabile da `/admin/qualita-ai`.
- **Coda review**: suggerimento categoria automatico + "Accetta" 1-click; filtro per cliente.
- **Admin clienti**: piano modificabile inline + colonna "inizio piano"; N. Fatture = totale storico (non solo mese corrente); freccia naviga al dettaglio.
- **Integrità DB**: tab rimosso da `/admin/sistema` (troppi falsi positivi).
- **Gestione Fatture** (ex Scadenziario): rename pagina + sidebar; bottone "Elimina fattura" nel peek anteprima (soft-delete via nuovo `POST /api/fatture/elimina` sul worker); cestino come widget collassabile accanto ad "Aggiorna"; anteprima allargata (`sm:max-w-3xl`). Root cause "not found" risolta: era un gap di deploy (route worker non ancora su Railway), non un bug.
- Fix vari admin: `get_supabase_client`/`datetime` import a livello modulo (risolveva 500 su tutti gli endpoint admin), overview difensivo, fix build TypeScript Vercel.

**Cleanup sidebar + fix Notifiche (31 maggio 2026 — rev. 15)**

Sessione di rifinitura UX/correttezza, nessuna nuova feature:
- **Footer sidebar = solo logout.** Il dropdown sul nome utente in basso causava crash al click per incompatibilità Base UI (NON Radix): `MenuPrimitive.GroupLabel` richiede un `<Menu.Group>` padre, e `nativeButton` non è prop valida su `Menu.Trigger`/`Item`. Fix: `DropdownMenuLabel` riscritto come `<div>` semplice in `dropdown-menu.tsx`; rimossa `nativeButton` dal trigger; `DropdownMenuContent` con `side="top" align="start" className="w-56"` (la var Radix `--radix-dropdown-menu-trigger-width` dava larghezza 0 in Base UI). Voce "Account" rimossa dal dropdown (ridondante con Impostazioni → stessa destinazione): ora resta solo "Esci".
- **Report rimosso dalla sidebar.** Voce e import `Receipt` tolti da `app-sidebar.tsx`. `navSecondary` ora = `[Notifiche, Impostazioni]`. Il file route `(app)/report/page.tsx` (placeholder) resta presente ma scollegato.
- **Fix Notifiche — RSC violation.** "Functions cannot be passed directly to Client Components": `SeverityIcon` veniva passata come prop da `page.tsx` (server) a `notifiche-list.tsx` (client). Spostata dentro il client component con i propri import lucide; `page.tsx` ora renderizza `<NotificheList notifiche={notifiche} />` senza prop funzione.

**Cleanup route orfane + Brevo verificato (31/5, seguito):**
- **Brevo in produzione ✅ FUNZIONANTE.** Le 3 env var (`BREVO_API_KEY`/`BREVO_SENDER_EMAIL`/`BREVO_SENDER_NAME`) sono ora sul worker Railway (service `worker`, Online). Test reale `POST /api/auth/reset-request` → `{"ok":true,"message":"Email inviata con successo"}` (HTTP 200). **Blocco #1 pre-switch chiuso.**
- **Route orfane rimosse:** `(app)/report/page.tsx`, `(app)/cestino/page.tsx`, `(app)/cestino/cestino-client.tsx`. Tolto `/report` da `PROTECTED_PREFIXES` in `proxy.ts`. **Le API proxy `app/api/cestino/*` restano** — servono il widget cestino in Gestione Fatture e l'elimina-da-peek (`api/fatture/elimina` importa `api/cestino/_worker`).

**Strumenti / Workspace — shell (31 maggio 2026, rev. 15)**

Avvio Fase 6 ridefinita: il "Foodcost" diventa **"Strumenti"**, una pagina-contenitore (layer a parte) con 4 tab. Decisioni di design prese con Mattia:
- **Nome/route:** etichetta sidebar "Strumenti" (icona `Wrench`), route `/workspace`, flag `workspace` (rinominato da `foodcost` → ri-allinea con Streamlit che già usava `workspace`; il Next.js **non fa gating per-pagina**, quindi nessuna migrazione DB distruttiva: i vecchi valori `foodcost` in `users.pagine_abilitate` restano orfani innocui, cleanup opzionale).
- **4 tab:** Foodcost (rework + menu engineering) · Diario (calendario condiviso per ristorante) · Personale (turni a nomi liberi → monte ore → export Excel, solo ore) · Inventario (conta-giacenze semplice, no movimentazione live).
- **Ordine:** shell-first, poi un tab alla volta.

*Implementato (shell, frontend reversibile):* `(app)/workspace/page.tsx` + `tabs-switcher.tsx` (pattern URL `?tab=` identico a Prezzi), 4 placeholder. Sidebar: voce "Strumenti"/`/workspace`. Rimossa vecchia route `(app)/foodcost/page.tsx`. `proxy.ts`: `/foodcost`→`/workspace`. Admin flag editor: `foodcost`→`workspace` label "Strumenti" (+ fix label "Scadenziario"→"Gestione Fatture"). `tsc --noEmit` pulito.

**Personale — costo lavoro + ore extra + copia settimana (31 maggio 2026, rev. 19)**

Implementate le 2 proposte di rev.18 + la richiesta "ore extra" di Mattia (commit `34982d0`).

*DB (migration `20260531140000_turni_costo_e_extra.sql`):* su `turni_personale` aggiunte `costo_orario NUMERIC(6,2)` (EUR/h, opzionale) e `ore_extra NUMERIC(5,2) DEFAULT 0` (quota straordinario, **sottoinsieme** delle ore totali — "di cui").

*Backend:*
- `GET /api/workspace/personale` ora ritorna anche `extra_per_persona`, `costo_per_persona`, `extra_totale`, `costo_totale` e `costi_noti` (mappa nome→ultimo costo orario, per prefill nel dialog).
- `POST`/`PATCH` accettano `ore_extra` e `costo_orario` (azzerabili via null nel PATCH).
- **Nuovo endpoint** `POST /api/workspace/personale/copia-settimana` — copia i turni di `[da−7, a−7]` su `[da, a]` con offset +7 giorni, **saltando i giorni destinazione già pieni** (no duplicati). OpenAPI 111 → 112.

*Frontend (`personale-tab.tsx` + proxy `copia-settimana/route.ts`):*
- Dialog turno: campi "di cui extra (h)" e "Costo orario (€/h)". Il costo orario si **autocompila** quando selezioni un nome già usato (da `costi_noti`). Validazioni: extra ≤ ore totali, valori ≥ 0. Durata live mostra anche il costo turno.
- Card totali: **Totale ore** (verde, prima) → **Totale extra** (ambra, seconda, sempre presente) → **Costo lavoro** (sky, solo se ≥1 costo impostato) → card per persona con badge "di cui Xh extra" + costo. Card = grid items → pari altezza per riga (allineate).
- Pulsante **"Copia settimana prec."** (icona `CopyPlus`, solo vista Settimana).
- Vista Settimana: indicatore "+Xh extra" (ambra) nelle celle. Vista Mese: extra + costo turno in riga. CSV: colonne "Di cui extra", "Costo orario", "Costo turno" + totali.

*⚠️ DA IMPLEMENTARE (richiesto da Mattia):* **interfaccia Personale ↔ Margini** — il costo del lavoro del periodo NON è ancora incrociato con i ricavi (`ricavi_giornalieri`) per mostrare l'**incidenza % del costo personale sui ricavi** accanto al foodcost. Vedi §12 e prossimi passi.

**Strumenti — audit completo + bugfix fuso orario (31 maggio 2026, rev. 18)**

Audit approfondito dei 4 tab di `/workspace` e delle relative inerenze (frontend, route proxy, endpoint worker, migration). Esito:

*Bug trovati e fixati (commit `d99b702`):*
- 🔴 **Fuso orario in `toISO` (personale-tab)** — usava `toISOString()` (UTC). In Italia (UTC+1/+2) la mezzanotte locale di un giorno diventava il giorno precedente in UTC. Effetti: nella **vista Settimana** i numeri dei giorni erano sfasati di −1 e i turni aggiunti dalle celle venivano **persistiti con data un giorno prima** dell'etichetta → dati errati visibili in CSV e vista Mese. Fix: `toISO` ora compone la data da `getFullYear/Month/Date` locali.
- 🟠 **`todayISO` (diario-tab)** — stesso `toISOString()`: tra mezzanotte e le 02:00 evidenziava/selezionava il giorno sbagliato. Fix analogo.
- 🟡 **Diario PATCH non azzerabile** — il worker filtrava i `None`, quindi rimuovere orario/descrizione da un evento esistente non salvava. Fix: `ora_inizio`/`ora_fine`/`descrizione` ora azzerabili (null = reset), mentre `titolo`/`data_evento`/`colore` restano aggiornati solo se valorizzati. Richiede deploy worker.
- ✨ **UX "Aggiungi turno"** — il pulsante in toolbar defaultava sempre a *oggi* anche navigando settimane/mesi diversi; ora default alla data nel periodo visualizzato (oggi se dentro il range, altrimenti inizio periodo).

*Verificato OK (nessun fix necessario):* calcolo ore overnight (sia frontend `calcolaSlotOre` con `+1440` sia worker `_ore_turno` via `.seconds` di timedelta normalizzato gestiscono correttamente turni a cavallo di mezzanotte); coerenza monte ore server/client; isolamento per `ristorante_id` su tutti gli 8 endpoint (pattern `_get_ristorante_id_for_user`); export CSV con BOM.

*Proposta di evoluzione (NON implementata — da validare con Mattia, vedi §12):* **Costo del lavoro %** e **Copia settimana precedente** sul tab Personale.

**Strumenti — tab Diario + Personale (31 maggio 2026, rev. 17 — Fase 6 chiusa)**

*Migration SQL (`20260531130000_create_diario_e_personale.sql`):*
- Tabella `diario_eventi` (ristorante_id CASCADE, user_id, data_evento DATE, ora_inizio/fine TIME opzionali, titolo, descrizione, colore). Migrazione automatica `note_diario → diario_eventi` nella stessa migration (data = created_at::DATE, colore gray, testo come titolo).
- Tabella `turni_personale` (ristorante_id CASCADE, user_id, nome, data_turno, ora_inizio, ora_fine, note). Entrambe con RLS service_role.

*Backend — 8 nuovi endpoint su `fastapi_worker.py`:*
- `GET /api/workspace/diario?mese=YYYY-MM` · `POST` · `PATCH /{id}` · `DELETE /{id}` — CRUD eventi
- `GET /api/workspace/personale?da=&a=` — turni + monte ore calcolato server-side + nomi distinti per autocomplete · `POST` · `PATCH /{id}` · `DELETE /{id}`

*Frontend:*
- `diario-tab.tsx` — layout 2 colonne: mini-calendario mensile custom (griglia 7×N, pallini colorati per evento, nessuna dipendenza esterna) + pannello giorno selezionato con lista eventi (titolo, orario, descrizione, colori, hover-actions edit/delete). Dialog evento: titolo, data, ora inizio/fine, note, 6 colori (sky/green/amber/red/purple/gray). Navigazione mese con frecce.
- `personale-tab.tsx` — toggle periodo Settimana/Mese; vista settimana = griglia 7 colonne cliccabili (+ click su cella per aggiungere turno sul giorno); vista mese = lista per data; KPI cards monte ore per persona; export CSV con BOM per Excel. Dialog turno: nome con autocomplete dropdown (dai nomi già usati), data, ora inizio/fine, durata calcolata live, note. Calcolo ore server-side (endpoint GET) + client-side (durata live nel dialog).
- 4 route proxy Next.js: `api/workspace/diario/route.ts` · `api/workspace/diario/[id]/route.ts` · `api/workspace/personale/route.ts` · `api/workspace/personale/[id]/route.ts`
- `page.tsx` aggiornato: rimossi i Placeholder, importati e usati i veri tab. `tsc --noEmit` pulito.
- OpenAPI aggiornato: 107 → 111 endpoint.

**Strumenti — tab Inventario (31 maggio 2026, rev. 16)**

Tab conta-giacenze completo. Modello dati: tabella `inventario_voci` (migration `20260531120000_create_inventario_voci.sql`) con `valore_totale` come colonna calcolata `GENERATED ALWAYS AS (ROUND(quantita * prezzo_unitario, 2)) STORED`. `user_id UUID` senza FK (pattern `ricavi_giornalieri`), `ristorante_id` con CASCADE.

*Backend — 7 nuovi endpoint su `fastapi_worker.py`:*
- `GET /api/workspace/inventario/articoli` — articoli da fatture con categoria, paginati e deduplicati
- `GET /api/workspace/inventario/snapshot-dates` — date distinte con n_articoli e valore_totale
- `POST /api/workspace/inventario/copia-snapshot` — copia articoli da data precedente con qty=0
- `GET /api/workspace/inventario` — lista voci per `?data=` + KPI + stats per categoria
- `POST /api/workspace/inventario` — crea voce
- `PATCH /api/workspace/inventario/{voce_id}` — modifica
- `DELETE /api/workspace/inventario/{voce_id}` — elimina
Nota routing: `articoli`, `snapshot-dates`, `copia-snapshot` definiti **prima** di `{voce_id}` per evitare conflitti FastAPI.

*Frontend — nuovi file:*
- `apps/web/src/app/api/workspace/_worker.ts` — helper condiviso workspace (al livello `workspace/`, non `foodcost/`)
- 5 route proxy Next.js (`inventario/route.ts`, `articoli/`, `snapshot-dates/`, `copia-snapshot/`, `[id]/`)
- `apps/web/src/lib/inventario.ts` — tipi + `UM_INVENTARIO` + `fmtData`
- `inventario-tab.tsx` — tab completo: date picker, KPI cards (ring-sky-400/60), analisi categoria collapsibile, tabella con colgroup proporzionale, tfoot totale, Copia da snapshot Popover, export CSV con BOM per Excel
- `inventario-aggiungi-dialog.tsx` — dialog aggiungi/modifica: campo Nome = autocomplete ricerca fatture (suggerimenti dal 2° carattere, UM bloccata da fattura via stato `daFattura`, selezionabile solo in modalità manuale/edit), grid 3 colonne (Quantità + UM + Prezzo/UM), valore live calcolato
- `inventario-date-picker.tsx` — calendario custom senza dipendenze: pallino sky sui giorni con inventario, navigazione mese per mese, giorno selezionato in blu pieno, oggi con bordo sky, legenda

*Decisioni chiave:*
- `daFattura` boolean: quando selezionato da autocomplete, UM si blocca come badge read-only (preserva UM originale fattura); in edit mode sempre selezionabile
- `openapi.json` aggiornato: 102 → 107 endpoint

### Prossimi passi concreti (aggiornato 31/5 — rev.16)

**⚠️ Prerequisiti / dimenticanze da chiudere (NON codice o cleanup):**
- ~~**Env var Brevo su Railway**~~ ✅ **CHIUSO (31/5).** Le 3 var sono sul worker, test reset-request reale → email inviata con successo. Reset password + onboarding ora funzionano in produzione.
- **Drift schema OpenAPI** — ricontrollare con `python scripts/export_openapi.py --check-drift` dopo ogni futura modifica a `fastapi_worker.py`. Ultimo aggiornamento: 107 endpoint (31/5, post-inventario).
- ~~**Route orfana `/cestino`**~~ ✅ **CHIUSO (31/5).** Rimossi `page.tsx` + `cestino-client.tsx`. Anche `/report` rimosso. Le API proxy `/api/cestino/*` mantenute (in uso dal widget Gestione Fatture).

**Roadmap funzionale (ordine di priorità concordato):**
1. ~~**Scadenziario / Gestione Fatture** (Fase 4)~~ ✅ **Completato** (30/5)
2. ~~**Cestino fatture** (Fase 4)~~ ✅ **Completato** (30/5, ora widget)
3. ~~**Onboarding primo accesso** lato Next.js~~ ✅ **Completato** (30/5)
4. ~~**Impostazioni/Account**~~ ✅ **Completato** (30/5)
5. ~~**Admin Panel** (Core + blocco 2 + routing confidenza + agent notturno + audit)~~ ✅ **Completato/over-delivered** (30/5)
6. ~~**Inventario** (Fase 6)~~ ✅ **Completato** (31/5)
7. ~~**Diario** (Fase 6)~~ ✅ **Completato** (31/5)
8. ~~**Personale** (Fase 6)~~ ✅ **Completato** (31/5)
9. ~~**Personale: costo lavoro + ore extra + copia settimana**~~ ✅ **Completato** (31/5, rev.19)
10. **Personale ↔ Margini (costo personale %)** — incrociare il costo lavoro del periodo con `ricavi_giornalieri` nella pagina Margini. Dato già calcolato lato Personale, manca solo l'esposizione in Margini. (richiesto da Mattia, rev.19)
11. **➡️ Home AI** — briefing giornaliero + notifiche actionable inline (Fase 3). Backend `daily_briefing_service` esiste già, va esposto in Next.js. La dashboard oggi ha solo KPI + grafici, zero briefing.
12. **Assistenza/Marketplace** (Fase 8) — zero codice.
13. **Notifiche v2** — raggruppamento + azioni inline + filtri con count (4 miglioramenti, Fase 3).
14. **Test, performance, switch dominio** (Fasi 9-11).

> Stato sintetico rev. 19: Fase 6 chiusa e **hardened+potenziata** (Foodcost ✅ + Inventario ✅ + Diario ✅ + Personale ✅). Audit + bugfix fuso orario (rev.18). Personale ora con **costo lavoro + ore extra + copia settimana** (rev.19). OpenAPI 112 endpoint. **Aperto:** tie-in Personale↔Margini (costo personale %) — vedi §12. **Prossimo grande step: Home AI** (briefing giornaliero + notifiche actionable).

---

## 15. STRATEGIA BRANCH GIT

```
main                  → produzione Streamlit (clienti attivi)
                       solo bugfix testati, mai lavorare direttamente

migration/nextjs      → branch di lavoro principale per Next.js
                       da qui partono i branch di feature

feature/streamlit-*   → bugfix Streamlit (es. feature/streamlit-fix-margini-aprile)
                       PR → main → deploy immediato

feature/migration-*   → feature Next.js (es. feature/migration-login)
                       PR → migration/nextjs
```

**Workflow:**
- Bug Streamlit → `feature/streamlit-fix-X` da `main` → fix → test → PR su `main` → deploy
- Sviluppo Next.js → `feature/migration-X` da `migration/nextjs` → PR su `migration/nextjs`
- Fine fase → merge `migration/nextjs` su `main` (solo dopo che la fase è completa e stabile)

**Codice condiviso (service Python usati da entrambi i frontend):** mai modificare senza eseguire `python -m pytest tests/` prima del merge.

---

## 16. PASSAGGIO DEFINITIVO (Fase 10 — dettaglio)

**Settimana 1 — Coesistenza monitorata**
- `app.oneflux.it` resta su Streamlit (default per tutti)
- `nuovo.oneflux.it` su Next.js (già funzionante)
- Uso personale quotidiano per almeno 5 giorni come "cliente reale"
- Invito i 2 clienti di test a provarlo per le loro attività normali

**Settimana 2 — Switch graduale**
- Backup completo database Supabase (snapshot pre-switch)
- Switch DNS: `app.oneflux.it` punta a Next.js
- `old.oneflux.it` punta a Streamlit (backup 30 giorni)
- Avviso ai clienti con spiegazione semplice + video breve

**Settimana 3 — Stabilizzazione**
- Monitoraggio attivo
- Fix bug critici se emergono
- Dopo 30 giorni senza problemi → Streamlit spento (Fase 11)

**Checklist pre-switch (da completare prima di toccare i DNS):**
- [ ] Tutte le sezioni funzionanti e testate
- [ ] Reset password funzionante lato Next.js
- [ ] Backup DB confermato
- [ ] Clienti avvisati con almeno 1 settimana di anticipo
- [ ] Rollback plan documentato e testato
