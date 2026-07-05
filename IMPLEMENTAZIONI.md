# 🚀 ONEFLUX — Roadmap Nuove Implementazioni
*Sessione brainstorming 13 maggio 2026 — Mattia D'Avolio, Recoma System srl*

## 1. Home Intelligente — Score "Pulse" + Briefing Contestuale

### Il problema che risolve
Oggi il ristoratore apre l'app e vede una lista di notifiche. Non ha però una risposta immediata alla domanda più importante: "Come sto andando? C'è qualcosa di urgente da fare oggi?" Per capirlo deve leggere tutte le notifiche, aprire le varie pagine, fare da solo il collegamento tra i dati. Un ristoratore impegnato in cucina non ha questo tempo.

### Come funziona

**Score "Pulse"** — un cerchio visivo grande con un numero da 0 a 100 e colore dinamico:
- 90-100 → verde → "Tutto sotto controllo 🟢"
- 70-89 → giallo → "Buono, qualcosa da sistemare 🟡"
- 50-69 → arancio → "Attenzione richiesta 🟠"
- < 50 → rosso → "Situazione critica — agisci oggi 🔴"

Il punteggio parte da 100 e scala in base a questi fattori (tutti da dati già disponibili, zero query aggiuntive):
- Fatturato mese precedente non inserito → -15 pt
- Costo personale mese precedente non inserito → -10 pt
- Scadenze già scadute → fino a -20 pt (3 pt per scadenza)
- Scadenze imminenti entro 7 giorni → fino a -10 pt
- Fatture non categorizzate > 20% → -15 pt
- Nessun upload negli ultimi 30 giorni → -10 pt
- Più di 3 alert prezzi attivi → -10 pt
- 1-3 alert prezzi attivi → -5 pt

**Briefing Contestuale** — massimo 4 righe sotto lo score che spiegano perché il punteggio è quello. Struttura a 6 slot con gerarchia fissa — si mostrano i primi 4 attivi:
- Slot 1: "Hai X scadenze scadute per totale €YYY"
- Slot 2: "Fornitore [Nome] ha aumentato i prezzi del X% questo mese"
- Slot 3: "Il fatturato di [mese] non è ancora stato inserito"
- Slot 4: "Questa settimana hai caricato X fatture per €YYY totali"
- Slot 5: "Hai X fatture SDI da confermare"
- Slot 6 (solo se score > 90): "Ottimo lavoro — tutto in ordine! 🎉"

Se uno slot non ha la condizione vera viene saltato — nessuna riga banale appare mai.

### Flusso utente completo
Apre l'app → vede score "78/100 — Buono" → legge briefing "Hai 2 scadenze per €1.400" → scende alle notifiche che mostrano il dettaglio con link diretto per agire. Trenta secondi dall'apertura all'azione.

### File da toccare
- `pages/5_notifiche_e_gestione.py` — aggiungere il blocco sopra le notifiche esistenti
- Nessun nuovo service necessario — tutti i dati già calcolati durante l'ingestion in app.py

---


## 3. Progress Bar KPI con Target Automatico

### Il problema che risolve
La pagina Calcolo Marginalità mostra i KPI come numeri statici. Il ristoratore vede "food cost 34%" ma non sa se è tanto o poco, se sta sforando rispetto alla sua storia. Deve ricordare a mente il valore del mese scorso per fare il confronto. La pagina è informativa ma non azionabile.

### Come funziona
Ogni KPI riceve una barra di avanzamento. Il target viene calcolato automaticamente come media rolling degli ultimi 3 mesi dello stesso ristorante — non impostato manualmente dall'utente (troppo attrito, nessuno lo farebbe).

Esempio visivo:
- Food Cost: `████████░░` €4.200 / €5.800 target → 72% ✅ In linea
- Bevande: `████████████` €1.900 / €1.600 target → 119% ⚠️ Stai sforando
- Personale: `██████░░░░` €3.100 / €4.200 target → 74% ✅ In linea

Colori dinamici: Verde < 90% target / Giallo 90-100% / Rosso > 100%.

### Perché cambia l'esperienza
- Prima: apri la pagina a fine mese, constati cosa è già successo → esperienza **retrospettiva**
- Dopo: apri a metà mese, vedi le barre, sai se stai sforando e puoi ancora agire → esperienza **predittiva**

Ogni upload aggiorna le barre in tempo reale — il caricamento diventa un gesto con significato immediato.

### File da toccare
- `pages/calcolo_marginalita.py` — modificare render KPI
- Aggiungere query per calcolo media rolling 3 mesi per ogni KPI


## 5. Digest Email Lunedì Mattina

### Il problema che risolve
L'app è uno strumento passivo: dà valore solo quando il ristoratore la apre. Se passa una settimana senza accedere, scadenze si accumulano e dati restano mancanti. Il ristoratore deve essere raggiunto proattivamente, non aspettare che lui venga dall'app.

### Come funziona
Ogni lunedì alle 7:00 una email automatica personalizzata con il briefing basato sui dati reali del ristorante. Stessa logica del Briefing Contestuale (punto 1) — si riusa lo stesso codice Python, si adatta solo il formato di output da widget Streamlit a testo email.

Struttura email proposta:
- Oggetto: "📊 Il tuo lunedì — [Nome Ristorante], [data]"
- Score Pulse testuale: "Il tuo punteggio questa settimana: 78/100"
- I 3-4 punti del briefing contestuale
- Bottone CTA: "→ Apri ONEFLUX"
- Footer con link opt-out (obbligatorio GDPR)

**Attenzione importante:** il contenuto preciso degli slot va definito e validato PRIMA di implementare. Il rischio è inviare email con informazioni banali che il ristoratore inizia a ignorare e poi disattiva.

### Infrastruttura
- Supabase Edge Function schedulata (cron ogni lunedì ore 7:00)
- Resend come provider email (piano free: 3.000 email/mese)
- Costo effettivo: zero fino a centinaia di clienti attivi
- Opt-out nelle impostazioni account (obbligatorio GDPR)

### File da toccare
- `supabase/functions/weekly_digest/` (nuova Edge Function)
- `pages/gestione_account.py` (toggle opt-in/opt-out email)
- Tabella `users`: aggiungere campo `email_digest_enabled` (boolean, default true)

---

## 6. Benchmark Anonimo tra Ristoranti

### Il problema che risolve
Il ristoratore sa che il suo food cost è 34% ma non sa se è tanto o poco rispetto ai competitor. Senza un riferimento esterno i numeri sono solo numeri — non diventano mai una leva per migliorare. Questa informazione oggi non è accessibile per le PMI della ristorazione italiana.

### Come funziona
Aggregazione anonima dei KPI di tutti i clienti ONEFLUX con profilo simile. Il singolo ristoratore vede i propri KPI confrontati con la media — senza che nessun dato individuale venga esposto. Minimo 10 ristoranti nel pool prima di mostrare la media (privacy).

Esempio di output per ogni KPI:
- Food Cost: Tu 34% — Media ONEFLUX 28% → ⚠️ Superiore alla media del 6%
- Bevande: Tu 12% — Media ONEFLUX 13% → ✅ In linea
- Personale: Tu 31% — Media ONEFLUX 29% → 🟡 Leggermente sopra

### Dove si integra — da decidere prima di implementare
- **Opzione A:** accanto a ogni KPI in Calcolo Marginalità, sotto la progress bar del punto 3
- **Opzione B:** come slot nel Briefing Contestuale (punto 1) quando il delta supera il 10%

### Prerequisiti
Richiede base clienti minima per essere statisticamente significativo. I dati sono già tutti in DB — zero raccolta aggiuntiva. Da attivare quando il numero di clienti attivi è adeguato.

### File da toccare
- `services/benchmark_service.py` (nuovo — query aggregate anonime cross-tenant)
- `pages/calcolo_marginalita.py` (visualizzazione benchmark)
- Supabase RLS: aggiornare per query aggregate cross-tenant sicure


## 8. DNA Ristorante — Profilo Narrativo Annuale

### Il problema che risolve
Dopo mesi di utilizzo il ristoratore ha accumulato un patrimonio di dati prezioso ma non lo percepisce come tale. Vede fatture e numeri ma non ha mai una visione di insieme della "storia" del suo ristorante. Non sa rispondere a "come è cambiata la mia spesa in 12 mesi?" senza cercare manualmente mese per mese.

### Come funziona
Una pagina dedicata che costruisce nel tempo un profilo narrativo unico del ristorante, con frasi generate da template Python — nessuna AI. Ispirazione: Spotify Wrapped. Aggiornamento mensile automatico.

Esempi di frasi generate automaticamente:
- "Il tuo ristorante spende di più a dicembre e agosto — la tua stagionalità principale."
- "Il tuo fornitore più fedele è Birra & Co: presente da 18 mesi senza interruzioni."
- "La tua categoria più volatile è Pesce: varia in media del ±34% mese su mese."
- "Il tuo mese migliore per il margine è stato ottobre 2025 (MOL: 24%)."
- "Hai gestito 847 fatture per €124.000 di spese da quando usi ONEFLUX"
- "Il tuo fornitore più costoso in assoluto è [Nome]: €XX.XXX negli ultimi 12 mesi."

### Perché è differenziante strategicamente
Genera lock-in naturale: dopo 12-18 mesi l'utente non può "portare via" questa storia cambiando app. L'account ONEFLUX diventa un asset unico e personale. Nessun competitor nel segmento PMI italiano lo offre.

### Prerequisiti temporali
- 3 mesi di dati → sezione base (top fornitore, categoria più costosa, totale gestito)
- 6 mesi di dati → stagionalità, trend semestrale
- 12 mesi di dati → versione completa con confronto anno su anno

### File da toccare
- `pages/dna_ristorante.py` (nuova pagina)
- `services/dna_service.py` (nuovo — aggregazione e template narrativi)
- `utils/sidebar_helper.py` (aggiunta voce menu)

---

## 9. Chef AI — Assistente Contestuale sui Propri Dati

### Il problema che risolve
Il ristoratore ha domande sui suoi dati che oggi richiedono di navigare in più pagine, filtrare, ricordare numeri e fare calcoli a mente. Domande come "quanto ho speso in carne questo mese rispetto al mese scorso?" richiedono 4-5 passaggi manuali. Con decine di categorie e fornitori, le domande comparative sono sempre un percorso multi-step tedioso.

### Come funziona
Un box chat in linguaggio naturale dove il ristoratore fa domande sui PROPRI dati reali e riceve risposte immediate. Non è un chatbot generico — conosce le fatture, i fornitori, i margini di quel ristorante specifico. GPT-4.1-mini è già attivo nell'app per la classificazione fatture — zero infrastruttura aggiuntiva.

Esempi di domande reali:
- "Quanto ho speso in carne questo mese rispetto al mese scorso?"
- "Quali fornitori mi stanno aumentando i prezzi più rapidamente?"
- "Sto guadagnando o perdendo sul reparto bevande?"
- "Quante fatture ho caricato ad aprile e per che importo totale?"

### Come controllare qualità e costi

**Qualità:** modalità default con 6-8 domande predefinite cliccabili (le più frequenti). L'AI risponde con contesto ottimizzato per quella domanda specifica — risposta controllata e precisa. Chat libera disponibile come opzione secondaria avanzata.

**Costi:** rate limiting (max 10 domande/giorno/cliente) + contesto ridotto (solo aggregati, non fatture singole). Costo stimato: ~2-3€/mese per cliente attivo.

### Posizione nell'app — da decidere prima di implementare
- **Opzione A:** box collassabile in fondo al tab Notifiche
- **Opzione B:** pagina dedicata "🤖 Chef AI" nel menu laterale

### Perché è il differenziante a lungo termine
Trasforma ONEFLUX da "software gestionale" a "consulente digitale del ristoratore". Nessun competitor nel segmento PMI italiano della ristorazione lo offre oggi.

### File da toccare
- `services/chef_ai_service.py` (nuovo)
- `pages/chef_ai.py` (nuova pagina) oppure inserimento in `pages/5_notifiche_e_gestione.py`
- Tabella `ai_usage_log` su Supabase per rate limiting (user_id, date, count)
- `pages/gestione_account.py` (toggle on/off Chef AI)