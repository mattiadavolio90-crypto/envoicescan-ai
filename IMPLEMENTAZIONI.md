# 🗺 ONEFLUX — Roadmap Nuove Implementazioni
*Sessione pianificazione 8 luglio 2026 — Mattia D'Avolio, Recoma System srl*

> Questa versione SOSTITUISCE la roadmap del 13 maggio 2026. I punti superati
> (Score Pulse/Briefing → assorbito da Home AI; Chef AI → è la Chat AI attuale)
> e i punti non più di interesse sono stati rimossi. I punti relativi a
> benchmark prezzi prodotto, bacheca offerte fornitori e clausola ToS per dati
> aggregati sono confluiti nel documento separato GRUPPO_ACQUISTO.md, di cui
> sono componenti.

---

## 1. Notifiche Push Proattive (PWA)

### Il problema che risolve
L'app oggi è uno strumento "pull": dà valore solo se il ristoratore la apre.
Più l'app è automatizzata (fatture via SDI, classificazione AI), meno motivi
naturali ci sono per entrare. Il briefing giornaliero esiste ma aspetta che il
cliente arrivi a leggerlo.

### Come funziona
Notifica push nativa della PWA (`/m`), inviata quando c'è un evento rilevante:
scadenza imminente/scaduta, alert prezzo sopra soglia, promemoria dato mensile
mancante. Riusa la stessa logica di priorità/gerarchia già presente nel
briefing (`daily_briefing_service.py`) — non è un nuovo motore decisionale,
solo un nuovo canale di consegna dello stesso contenuto.

Vincolo tecnico: funziona solo per chi ha installato la PWA e accettato le
notifiche browser. Non è un canale universale (a differenza di un domani
WhatsApp), va comunicato come "attivalo nelle impostazioni" — non dato per
scontato attivo su tutta la base clienti.

### Perché ora
Costo di infrastruttura pressoché zero (Web Push API, nessun provider a
pagamento), riuso quasi totale della logica briefing esistente. Il rapporto
sforzo/beneficio è il più favorevole dell'intera lista.

### File probabilmente coinvolti
- `apps/web/public/sw.js` — service worker, gestione evento push
- Nuovo endpoint worker per invio push (subscription storage + trigger)
- `services/daily_briefing_service.py` — riuso della selezione/priorità topic esistente
- Tabella nuova per le push subscription per utente (endpoint, chiavi)
- UI opt-in nelle Impostazioni

### Criteri di completamento
- Il cliente può attivare/disattivare le notifiche push da Impostazioni
- Almeno 1 topic (es. scadenza imminente) genera una push reale e testata
- Nessuna push per topic già disattivati dal configuratore Home (stessa
  regola di coerenza toggle già esistente per il briefing)

### Stato
Da approfondire tecnicamente con Claude Code (fattibilità Web Push su
Vercel/service worker attuale) prima di stimare i tempi.

---

## 2. Data Entry via Assistente AI (ricavi, coperti, personale, spese)

### Il problema che risolve
La filosofia dell'app è "zero data entry obbligatorio", e resta tale. Ma
alcuni dati (fatturato del mese, costo personale, coperti, spese extra) non
arrivano da nessuna fonte automatica — richiedono che il cliente li inserisca
a mano nel form di Margini/Agenda. Molti non lo fanno, e questo è oggi la
causa principale della "Salute della gestione" bassa: senza quei dati,
food cost % e MOL restano falsi o incompleti.

### Come funziona
Il cliente scrive in chat, in linguaggio naturale: *"ieri ho incassato 2.340€
con 87 coperti"* oppure *"il costo del personale di giugno è stato 8.400€"*.
L'assistente AI riconosce il tipo di dato, lo struttura e lo salva nella
tabella corretta (`margini_mensili`, `ricavi_giornalieri`, costo personale),
con conferma esplicita prima del salvataggio (mai scrittura silenziosa).

Non sostituisce i form esistenti — resta un canale alternativo, più veloce,
per chi preferisce "raccontarlo" piuttosto che compilare un campo. Il cliente
che preferisce il form continua a usarlo.

### Perché è la priorità più alta
Attacca direttamente il collo di bottiglia reale (dati mensili mancanti →
Salute rossa/gialla → briefing meno utile → MOL falso). Riusa l'infrastruttura
Chat AI già esistente (function calling, rate limiting per piano) — non serve
nuova infrastruttura AI, solo nuovi "tool" lato chat che scrivono invece di
solo leggere.

### Vincoli da rispettare (regole del progetto)
- Ogni scrittura via chat filtrata per `user_id` + `ristorante_id` come tutte
  le altre operazioni (regola multi-tenant)
- Conferma esplicita dell'utente prima di ogni salvataggio — la chat oggi è
  sola lettura, questo è un cambio di categoria (da "risponde" a "agisce") e
  richiede più cautela sugli errori di interpretazione
- Nessun nome di prodotto/fornitore reale verso OpenAI in questo flusso,
  come da regola GDPR esistente — ma qui il rischio è più basso: si parla di
  aggregati (fatturato, coperti), non di righe fattura con nomi prodotto

### File probabilmente coinvolti
- `services/fastapi_worker.py` — nuovi tool di scrittura per la chat
  (function calling), accanto a quelli di lettura esistenti
- Chat AI service (il modulo che gestisce i tool della chat)
- Possibile nuova UI di conferma inline in chat prima del salvataggio

### Criteri di completamento
- L'assistente riconosce almeno: fatturato giorno/mese, coperti, costo
  personale, spesa extra
- Ogni inserimento richiede conferma esplicita dell'utente, mai automatico
- I dati inseriti via chat appaiono correttamente in Margini/Agenda,
  indistinguibili da quelli inseriti via form
- Test su ambiguità: cosa succede se il cliente scrive qualcosa di
  interpretabile in due modi (da definire con Claude Code)

### Stato
Pronto per essere trasformato in brief tecnico quando vuoi procedere.

---

## 3. Benchmark KPI Aggregati (food cost %, incidenza personale %, ecc.)

### Il problema che risolve
Il ristoratore vede il proprio food cost (es. 34%) ma non ha un riferimento
esterno per sapere se è tanto o poco. Il numero resta isolato, senza diventare
una leva per agire.

### Come funziona
Media aggregata e anonima dei KPI di tutti i clienti OneFlux con profilo
simile (es. stessa fascia di fatturato o tipologia cucina, se disponibile).
Il cliente vede solo: "Tu 34% — Media OneFlux 28% — sopra la media del 6%".
Nessun dato individuale di altri clienti è mai esposto.

**Importante — a differenza del benchmark sui prezzi prodotto (che vive nel
documento Gruppo d'Acquisto):** questo benchmark lavora su percentuali già
calcolate (food cost %, incidenza personale %), non su righe fattura da
normalizzare prodotto per prodotto. Zero rischio di match sbagliati tra
descrizioni fornitore diverse — è puro calcolo aggregato su dati che l'app
già possiede. Per questo può partire prima e con meno rischio del benchmark
prezzi.

### Prerequisiti
- Soglia minima di clienti nel pool prima di mostrare una media (proposta:
  almeno 10, per solidità statistica e per evitare che il dato sia
  riconducibile a pochi ristoranti) — verificare la soglia esatta anche sotto
  il profilo privacy con la clausola ToS del punto F del documento Gruppo
  d'Acquisto, che copre anche questo utilizzo
- Nessuna raccolta dati aggiuntiva: tutto già in DB

### File probabilmente coinvolti
- Nuovo service di aggregazione cross-tenant (query aggregate, mai per singolo
  cliente)
- Verifica RLS Supabase per garantire che l'aggregazione non esponga righe
  individuali nemmeno per errore di query
- Punto di visualizzazione: dentro Margini, accanto ai KPI esistenti

### Criteri di completamento
- La media si mostra solo sopra la soglia minima di pool
- Nessuna query espone dati a livello di singolo cliente
- Clausola ToS aggiornata prima del lancio (vedi GRUPPO_ACQUISTO.md, sezione
  ToS — condivisa tra i due usi)

### Stato
Da attivare quando il numero di clienti attivi è adeguato. Fondazione tecnica
(query aggregate) può essere preparata prima, senza attendere la soglia.

---

## Riepilogo priorità

| # | Punto | Priorità | Blocco principale |
|---|-------|----------|--------------------|
| 1 | Push proattive PWA | Alta — quick win | Verifica fattibilità tecnica Web Push |
| 2 | Data entry via assistente | Alta — impatto diretto su Salute | Nessuno, pronta per brief |
| 3 | Benchmark KPI aggregati | Media | Soglia minima clienti nel pool |
