# PIANO DI MIGRAZIONE DEFINITIVO — ONEFLUX verso Next.js

**Data:** 25 maggio 2026 (aggiornato)
**Chi lavora:** 1 sviluppatore (+ Claude come assistente)
**Clienti attivi:** 2 in fase di test + 1 operativo — rischio MEDIO, Streamlit deve restare acceso
**Basato su:** ROADMAP + AUDIT del 25 maggio, aggiornato con nuove decisioni di progetto

---

## COSA STA SUCCEDENDO — SPIEGAZIONE SEMPLICE

L'app ONEFLUX oggi funziona così: c'è un'unica grande applicazione Python (Streamlit) che fa tutto — mostra le pagine, gestisce i dati, calcola i numeri. È come una cucina dove il cuoco cucina, serve ai tavoli e fa i conti, tutto da solo.

La nuova architettura divide il lavoro:
- **Next.js** (nuovo): si occupa solo di quello che l'utente vede (le pagine, i bottoni, le tabelle)
- **FastAPI + Supabase + Worker** (esistenti): continuano a fare tutto il lavoro "pesante" con i dati e le fatture — non si toccano

In pratica stai tenendo tutta la cucina e cambi solo la sala e il menu. Questo è il motivo per cui è fattibile senza rischiare di perdere dati o rompere la logica esistente.

**Differenza rispetto alla versione precedente del piano:** hai 3 clienti attivi. Questo significa che Streamlit deve continuare a funzionare normalmente per tutta la durata dello sviluppo. I due sistemi girano in parallelo su URL diversi finché Next.js non è completamente pronto.

---

## QUANTO CI VUOLE — SENZA ILLUSIONI

La migrazione completa richiede **circa 6-9 mesi** lavorando da solo, anche con Claude. Non è "qualche giorno" — è un progetto serio.

| Fase | Durata stimata | Cosa si vede alla fine |
|---|---|---|
| Fase 0 (già fatta) | ✅ Completata | Codice pulito, schema API disponibile |
| Fase 0.5 | 3-5 giorni | Codice Python pronto per essere esposto come API |
| Fase 1 | 1-2 settimane | Scheletro Next.js su URL separato, visibile nel browser |
| Fase 2 | 2-3 settimane | Login funzionante nella nuova interfaccia |
| Fase 3 | 2-3 settimane | Dashboard + Upload fatture funzionanti |
| Fase 4 | 1-2 settimane | Notifiche, scadenzario, cestino |
| Fase 5 | 2-3 settimane | Controllo prezzi + calcolo margini |
| Fase 6 | 2-3 settimane | Foodcost (riscrittura completa, no parità) |
| Fase 7 | 3-4 settimane | Pannello admin (redesign completo) |
| Fase 8 | 1-2 settimane | Test, performance, sicurezza |
| Fase 9 | 1 settimana | Passaggio definitivo — switch dominio principale |
| Fase 10 | 3-5 giorni | Pulizia codice Streamlit |
| **TOTALE** | **~6-9 mesi** | **App completamente migrata** |

> **Nota sul worker fatture:** Hai clienti attivi — il worker che elabora le fatture ogni 5 minuti è ora operativo. Funziona su GitHub Actions. Questo va bene per i volumi attuali, ma quando il numero di clienti cresce o se iniziano ad arrivare molte fatture automatiche contemporaneamente, lo spostiamo su un processo sempre acceso (Railway o simile). Per ora non è urgente, ma tienilo d'occhio.

---

## TECNOLOGIA — RISPOSTA ALLA DOMANDA SULLA SCALABILITÀ

Domanda: *"Siamo certi che questa implementazione porti a un'app scalabile senza limitazioni nel lungo termine?"*

**Risposta breve: sì.** Questa è la ragione tecnica:

- **Next.js** è usato da aziende come Notion, TikTok, Nike, GitHub. Vercel (l'azienda dietro Next.js) investe centinaia di milioni l'anno nel progetto. Non diventerà obsoleto — e se anche tu volessi cambiare host un giorno, Next.js gira su qualsiasi server (Railway, AWS, self-hosted). Non sei bloccato su Vercel.

- **Supabase** è PostgreSQL (il database più affidabile al mondo, usato da tutti dal 1989) con un'interfaccia moderna sopra. Se Supabase come azienda sparisse domani, i tuoi dati resterebbero intatti in PostgreSQL e potresti spostarli. I dati sono sempre tuoi.

- **FastAPI** è Python — il tuo codice esistente con la logica business rimane, non lo riscrivi.

**Per le funzionalità che vuoi:**

| Cosa vuoi | Come si fa | Stato |
|---|---|---|
| Popup/modal che si aprono | shadcn Dialog — libreria standard | Built-in nel design system |
| Grafici interattivi con drill-down | Recharts o Tremor | Librerie mature, React |
| Tabelle pivot con filtri e aggregazioni | TanStack Table v8 | La più potente disponibile in React |
| Tema scuro/chiaro | shadcn/ui — già supportato nativamente | Built-in, nessun lavoro extra |
| Italiano/Inglese | next-intl — libreria standard | 1 settimana di lavoro |
| App mobile (PWA, installa su telefono) | next-pwa — plugin semplice | ~3 giorni di lavoro |
| Notifiche push mobile | Web Push API | Aggiuntivo post-MVP |
| Aggiornamenti in tempo reale | Supabase Realtime | Post-MVP |

**Limitazione da sapere:** Vercel ha un costo mensile che cresce con il traffico. Per decine di ristoranti è quasi zero. Per centinaia di ristoranti è gestibile. Se arrivassimo a migliaia, avresti anche abbastanza fatturato da giustificare infrastruttura dedicata. Non è un problema ora.

**Conclusione:** la tecnologia scelta non ha limitazioni rilevanti per ONEFLUX nel medio-lungo termine. È la scelta giusta.

---

## L'INTERFACCIA NUOVA — COSA SI COSTRUISCE

Questa sezione descrive come deve sembrare e comportarsi la nuova interfaccia. Il design grafico (colori esatti, tipografia, layout dettagliato) lo decidiamo insieme durante la Fase 1 — non devi saperlo adesso.

### Principi fondamentali

- **Veloce**: le pagine principali devono caricare in meno di 1 secondo. Nessun "attendere prego" per dati già visti.
- **Moderna**: no tabelle piatte e statiche. I dati si possono esplorare, filtrare, ordinare, cliccare per approfondire.
- **Popup e hyperlink**: invece di navigare su pagine diverse, molti dettagli si aprono in finestre overlay (modal) sopra la pagina corrente. Cliccando su un fornitore si apre il pannello fornitore, cliccando su una fattura si apre la fattura, ecc.

### Grafici e analisi

- **Dashboard e pagine KPI** → grafici interattivi: clicca su una barra e vedi il dettaglio del mese, filtra per categoria, confronta periodi.
- **Pagine di analisi** (margini, prezzi, foodcost) → tabelle con filtri e aggregazioni dinamiche. Puoi raggruppare per fornitore, categoria, mese — i totali si aggiornano live.

### Mobile (versione telefono)

La versione mobile è una vista semplificata pensata per guardare i dati velocemente, non per fare lavoro complesso. Le funzioni mobile previste:

- **Dashboard mobile**: KPI principali (margine settimana, alert attivi, ultime fatture ricevute)
- **Notifiche e alert**: ricevi notifiche push quando arriva una fattura, quando scatta un alert prezzo, quando si avvicina una scadenza
- **Consultazione rapida**: puoi vedere margini mensili, lista fatture, scadenzario

Non previsto su mobile (richiede schermo grande): analisi pivot, gestione ricette foodcost, pannello admin.

### Temi

- Tema **chiaro** e tema **scuro** — l'utente sceglie nelle impostazioni
- Lingua **italiano** e **inglese** — l'utente sceglie nelle impostazioni
- Il design grafico preciso (palette colori, stile componenti) lo scegliamo insieme durante la Fase 1, prima di costruire qualsiasi pagina

---

## MODIFICHE RISPETTO AL PIANO ORIGINALE

### MODIFICA 1 — Aggiunta Fase 0.5 (già pianificata, invariata)

**Cosa si fa:** rimuovere `@st.cache_data` da `db_service.py`, `margine_service.py`, `documenti_service.py` — libera il codice Python dalle dipendenze Streamlit in modo che possa funzionare come API.

**Impatto:** nessun cambiamento visibile per i clienti. L'app Streamlit continua a funzionare normalmente.

---

### MODIFICA 2 — Coesistenza Streamlit e Next.js durante lo sviluppo

**Situazione attuale:** hai 3 clienti attivi. Non puoi spegnere Streamlit per sviluppare Next.js.

**Come funziona lo sviluppo in parallelo:**

```
Durante sviluppo (6-9 mesi):
  app.oneflux.it      → Streamlit (clienti attuali, mai toccare)
  nuovo.oneflux.it    → Next.js (sviluppo, test, preview)

Quando Next.js è pronto:
  app.oneflux.it      → Next.js (switch dominio)
  old.oneflux.it      → Streamlit (backup 30 giorni, poi spento)
```

I due sistemi usano lo stesso database Supabase — non ci sono due basi dati da sincronizzare. Un cliente che carica una fattura su Streamlit la vede subito anche in Next.js (e viceversa) perché i dati sono sempre nello stesso posto.

**Il passaggio finale** avviene solo quando:
1. Next.js supera tutti i controlli della checklist finale
2. Lo hai testato personalmente per almeno una settimana
3. Hai avvisato i clienti con anticipo

---

### MODIFICA 3 — Test con clienti reali invece di test A/B formale

La roadmap originale prevedeva test A/B con clienti pilota formali. Ora puoi fare meglio: chiedi ai tuoi 2 clienti di test di provare la nuova interfaccia su `nuovo.oneflux.it` mentre continuano ad usare Streamlit normalmente. Nessun impegno formale — solo feedback reale.

---

### MODIFICA 4 — Upload file: limite a 4.5 MB, nessun meccanismo speciale

**Il problema originale:** Vercel ha un limite di 4.5 MB per i file ricevuti. Il piano precedente prevedeva pre-signed URL per file fino a 200 MB.

**Nuova decisione:** il limite di 200 MB non era un requisito reale — è stato scelto senza una logica precisa. Le fatture elettroniche italiane (XML/P7M) hanno dimensioni tipiche:
- XML: 10–200 KB
- P7M: 20–500 KB
- PDF: fino a 3-4 MB in casi estremi

4.5 MB copre il 100% dei casi reali. I file vanno direttamente a Vercel (semplice), nessuna infrastruttura aggiuntiva.

**Cosa si risparmia:** eliminazione di un livello di complessità (pre-signed URL, configurazione Supabase Storage, gestione token temporanei). Questa semplificazione riduce il lavoro della Fase 3 di circa 3-4 giorni.

---

### MODIFICA 5 — Autenticazione: cookie sicuri ora, multi-dispositivo dopo

Il sistema di login attuale usa un token singolo per utente. Con Next.js implementiamo subito i cookie HttpOnly (il miglioramento principale di sicurezza). La gestione sessioni multi-dispositivo (logout da tutti i dispositivi, ecc.) viene nella fase post-MVP con Supabase Auth completo.

---

### MODIFICA 6 — Ordine di costruzione delle API (invariato)

**Fase 2:** login, logout, reset password, sessione, impersonazione admin
**Fase 3:** statistiche dashboard, lista fatture, upload, versione cache
**Fase 4:** scadenziario, cestino, ripristino, segna pagata, config pagamento fornitori
**Fase 5:** alert prezzi, sconti, omaggi, margini, fatturato centri
**Fase 6:** foodcost (riscrittura), note diario, tag custom
**Fase 7:** gestione clienti (admin redesign), AI categorization automatica
**Fase 8+:** cambio password, export GDPR, delete account, notifiche inbox

---

### MODIFICA 7 — Comunicazione clienti: ora necessaria

La roadmap originale prevedeva documentazione per i clienti che ho rimosso perché "nessun cliente reale". Ora che hai clienti, prima del passaggio finale bisogna preparare:
- Un messaggio semplice ai clienti che spiega la novità (lo facciamo insieme durante la Fase 9)
- Una landing page o video breve che mostra le differenze principali

Non si fa adesso — si fa quando Next.js è quasi pronto.

---

### MODIFICA 8 — Foodcost: riscrittura completa, nessuna parità richiesta

La pagina Foodcost è la meno usata. Non è necessario che la nuova versione si comporti esattamente come quella Streamlit — anzi, è l'occasione per migliorarla.

**Cosa cambia:**
- Nessun test di parità numerica (risparmiamo 1 settimana di lavoro)
- Si progetta da zero con grafici moderni, tabelle pivot per le analisi di costo
- La logica Python nel backend (calcolo food cost %) resta — solo l'interfaccia cambia radicalmente

**Quando:** Fase 6, dopo margini e prezzi.

---

### MODIFICA 9 — Admin: redesign completo + automazione categorizzazione AI

Il pannello admin attuale ha due problemi principali:
1. La struttura dei tab non è chiara
2. La gestione della categorizzazione AI richiede troppo lavoro manuale

**Cosa si costruisce nella nuova versione:**

**Categorizzazione AI più autonoma:**
- L'AI classifica automaticamente senza richiedere review per ogni voce
- Intervento manuale solo quando la confidenza è bassa (sotto una soglia configurabile)
- Dashboard di monitoraggio: quante classificazioni automatiche, quante revisionate, accuracy nel tempo

**Struttura admin semplificata:**
- Una pagina per ogni funzione principale (non tutto in tab sovrapposti)
- Popup di dettaglio per le operazioni sui clienti

**Quando:** Fase 7. Prima dell'inizio di questa fase facciamo una sessione di analisi insieme per mappare esattamente cosa vuoi che faccia il nuovo admin.

---

## IL RISCHIO PIÙ GRANDE — DA NON SOTTOVALUTARE

L'audit lo dice chiaramente: **questo non è "solo riscrivere l'interfaccia grafica"**.

Il problema vero è che in Streamlit, la grafica e la logica sono mescolate insieme. Per ogni pagina il lavoro è:
1. Spostare la logica dati nel FastAPI (Python — già conosci)
2. Costruire la nuova pagina in Next.js (TypeScript — linguaggio nuovo)
3. Verificare che i risultati siano corretti

**Foodcost e Admin** non richiedono più test di parità (le stiamo riscrivendo da zero). Per le altre pagine (Dashboard, Margini, Prezzi) i numeri devono tornare esattamente — Claude aiuta a scrivere i test di confronto.

**Il rischio con i clienti attivi:** ogni modifica ai servizi Python (Fase 0.5 in poi) deve essere testata prima di andare in produzione su Streamlit. Si usa sempre il branch `main` protetto — nessuna modifica diretta in produzione.

---

## SICUREZZA — COSA NON CAMBIA E COSA MIGLIORA

**Resta invariato:**
- Password con Argon2 (sistema molto sicuro)
- Rate limiting login (blocco dopo 5 tentativi)
- Validazione file caricati (magic bytes PDF/XML/P7M)
- Protezione prompt injection per l'AI
- Log senza dati personali (GDPR)

**Migliora con Next.js:**
- Cookie HttpOnly: il token di sessione non è più visibile al browser — protegge contro XSS
- Intestazioni di sicurezza standard (CSP, HSTS, X-Frame-Options): Next.js le gestisce nativamente

**Non si tocca per ora:**
- La chiave `service_role` di Supabase resta nel backend FastAPI. Si risolve nella fase post-MVP con Supabase Auth completo.

---

## COME INIZIARE — PROSSIMI PASSI CONCRETI

### Questa settimana (Fase 0.5):

1. **Rimuovere `@st.cache_data` dai service Python** — 3 file: `db_service.py`, `margine_service.py`, `documenti_service.py`. Claude lo fa direttamente.
2. **Eseguire i test** — `python -m pytest tests/`. Devono passare tutti.
3. **Nessuna modifica visibile per i clienti** — Streamlit funziona come prima.

### Settimana prossima (Fase 1):

4. **Creare `apps/web`** con Next.js 14 — Claude fa lo scaffold completo.
5. **Scegliere il design** — palette colori, stile componenti, layout. Lo facciamo insieme prima di costruire qualsiasi pagina.
6. **Deploy su Vercel** — URL `nuovo.oneflux.it` o simile, separato da Streamlit.

---

## CHECKLIST FINALE — QUANDO L'APP È PRONTA PER IL PASSAGGIO

Prima di spostare `app.oneflux.it` su Next.js:

- [ ] Login, logout, reset password funzionano
- [ ] Upload fatture XML/P7M/PDF funziona (file fino a 4.5 MB)
- [ ] Dashboard mostra gli stessi numeri di Streamlit
- [ ] Calcolo margini: stesso risultato su 5 mesi di dati reali
- [ ] Alert prezzi: stessi alert su dati reali
- [ ] Foodcost: funziona correttamente (no parità richiesta — nuova versione)
- [ ] Pannello admin: impersonazione funzionante, categorizzazione AI automatica operativa
- [ ] Cookie di sessione sono HttpOnly (verificabile con DevTools del browser)
- [ ] Nessuna chiave segreta (`SUPABASE_KEY`, `OPENAI_API_KEY`) visibile lato browser
- [ ] Dashboard carica in meno di 1 secondo
- [ ] App funziona su mobile (layout responsive, dashboard e notifiche)
- [ ] Tema scuro/chiaro funzionante
- [ ] Backup Streamlit disponibile su `old.oneflux.it` per 30 giorni
- [ ] Clienti avvisati con anticipo

---

## COSA RIMANE FUORI DA QUESTO PIANO (POST-MVP)

1. **Notifiche push mobile** — ricezione notifiche anche quando l'app è chiusa (richiede service worker + push server)
2. **Aggiornamenti in tempo reale** — dashboard che si aggiorna istantaneamente all'arrivo di una fattura, senza ricaricare la pagina (Supabase Realtime)
3. **Chat AI integrata** — "Chiedi a ONEFLUX" con domande sui propri dati
4. **Migrazione a Supabase Auth** — sistema di login nativo con sicurezza RLS reale
5. **White-label / multi-brand** — se mai vorrai permettere a partner di rivendere ONEFLUX con il loro logo

---

**Fine documento.**

*Aggiornato il 25 maggio 2026 — incorpora le decisioni su clienti attivi, upload limit 4.5MB, Foodcost e Admin come riscritture complete, UI moderna con grafici/pivot/mobile, risposta sulla scalabilità tecnologica.*
