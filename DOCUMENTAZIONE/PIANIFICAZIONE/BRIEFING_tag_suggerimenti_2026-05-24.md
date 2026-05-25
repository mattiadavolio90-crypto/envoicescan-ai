# BRIEFING - Suggerimenti e Automazioni Tag (Analisi e Tag)
Data: 2026-05-24
Stato: APPROVATO (passaggio a Fase 2)
Owner: Pianificazione Implementazioni ONEFLUX

## 1) Descrizione funzionale richiesta
Obiettivo business: ridurre la creazione manuale dei tag nella pagina Analisi e Tag, introducendo suggerimenti e automazioni guidate.

Richieste utente esplicite:
1. Proposta creazione tag quando l'app rileva molte righe/prodotti con stessa tipologia (es. "salmone").
2. Proposta di aggiunta automatica a tag esistenti quando arrivano nuovi prodotti coerenti con il tag.
3. Notifiche dedicate per entrambi i casi (nuovo tag suggerito, prodotto suggerito su tag esistente).
4. Definizione UX grafica chiara nella pagina Analisi e Tag + integrazione con tab Notifiche.

## 2) Perimetro impatto (prima mappatura reale codebase)
Pagina target:
- pages/4_analisi_personalizzata.py (UI gestione tag + analisi)

Servizi dati tag:
- services/db_service.py (get_custom_tags, get_custom_tag_prodotti, get_descrizioni_distinte, crea_tag, aggiungi_associazioni, ecc.)

Schema DB:
- migrations/055_create_custom_tags.sql (custom_tags, custom_tag_prodotti, RLS owner-based)

Notifiche:
- services/notification_inbox_service.py (topic, dedupe, bucket, query)
- components/notifications_panel.py (ingest operativa)
- pages/5_notifiche_e_gestione.py (render inbox e navigazione)

## 3) Vincoli espliciti (cosa NON deve cambiare)
1. Isolamento multi-tenant obbligatorio: user_id + ristorante_id.
2. Nessuna auto-modifica silenziosa delle associazioni: serve conferma utente esplicita (bulk one-click ammesso).
3. Nessuna regressione su limiti esistenti:
   - MAX_CUSTOM_TAGS / MAX_CUSTOM_TAGS_TRIAL
   - MAX_PRODOTTI_PER_TAG
4. Nessuna rottura dei flussi attuali di gestione manuale tag.
5. Performance UI stabile: evitare query pesanti ad ogni rerun Streamlit.

## 4) Decisioni business già note
1. Approccio desiderato: suggerimenti/automazioni assistite, non solo gestione manuale.
2. Alert desiderati per entrambe le casistiche (nuovo tag, estensione tag esistente).

## 5) Priorità di rischio
1. Alto: falsi positivi nei suggerimenti (raggruppamenti errati).
2. Alto: spam notifiche (troppi alert ripetitivi).
3. Medio: incremento latenza pagina Analisi e Tag.
4. Medio: collisioni/duplicazioni tra suggerimenti e tag già esistenti.
5. Medio: incoerenza tra UI suggerimenti e inbox notifiche.

## 6) Baseline tecnica osservata (fatti verificati)
1. Esiste già normalizzazione descrizione_key e matching stabile lato tag.
2. Esiste già get_descrizioni_distinte() con aggregazione occorrenze/fornitori/date utile per scoring suggerimenti.
3. Esiste infrastruttura notifiche inbox con dedupe per topic_key e bucket temporali.
4. Esistono costanti custom tag (inclusi limiti suggerimenti) non ancora sfruttate in UI.

## 7) Domande bloccanti (Gate Fase 1)
### DECISIONE RICHIESTA [1.1]
Problema: Modalità di rilevazione suggerimenti (accuratezza vs semplicità).
Opzione A: Regole deterministiche (tokenizzazione, normalizzazione, soglie frequenza, match prefisso/sottostringa).
Pro: veloce, explainable, costo basso, zero dipendenze AI runtime.
Con: meno robusta su sinonimi/descrizioni sporche.
Opzione B: Ibrida (regole + similarità lessicale/fuzzy + alias semantici configurabili).
Pro: migliore recall/precisione sui casi reali.
Con: complessità e tuning maggiore.
Raccomandazione tecnica: Opzione B con fallback ad A, ma attivazione progressiva.

### DECISIONE RICHIESTA [1.2]
Problema: Soglie minime per creare un suggerimento "nuovo tag".
Opzione A: soglia fissa (es. almeno 8 descrizioni_key e almeno 20 occorrenze aggregate negli ultimi 90 giorni).
Pro: prevedibile, facile da spiegare.
Con: non adatta a ristoranti piccoli/grandi allo stesso modo.
Opzione B: soglia adattiva (percentile su distribuzione occorrenze tenant).
Pro: più equa tra tenant con volumi diversi.
Con: più complessa da comunicare.
Raccomandazione tecnica: Opzione A in v1 con parametri configurabili.

### DECISIONE RICHIESTA [1.3]
Problema: Cosa succede quando arriva prodotto nuovo suggerito per tag esistente.
Opzione A: suggerimento passivo (lista con checkbox + bottone "Aggiungi selezionati").
Pro: controllo totale utente, zero sorprese.
Con: un click in più.
Opzione B: auto-aggancio con undo.
Pro: massima automazione.
Con: rischio errori business elevato.
Raccomandazione tecnica: Opzione A (assistita, non automatica) per v1.

### DECISIONE RICHIESTA [1.4]
Problema: Canale notifiche per suggerimenti tag.
Opzione A: solo inbox (tab Notifiche), con badge.
Pro: coerente con architettura esistente.
Con: visibilità ritardata se utente non apre tab.
Opzione B: inbox + callout in pagina Analisi e Tag.
Pro: alta visibilità contestuale, migliore adozione.
Con: maggiore lavoro UX.
Raccomandazione tecnica: Opzione B.

### DECISIONE RICHIESTA [1.5]
Problema: Frequenza notifiche suggerimenti.
Opzione A: real-time a ogni upload.
Pro: tempestivo.
Con: rischio spam alto.
Opzione B: digest giornaliero + refresh quando cambia fingerprint suggerimenti.
Pro: riduce rumore.
Con: lieve ritardo.
Raccomandazione tecnica: Opzione B con eccezione "first-time" immediata.

### DECISIONE RICHIESTA [1.6]
Problema: Scope temporale per analisi suggerimenti.
Opzione A: solo ultimi 90 giorni.
Pro: rilevanza alta, performance migliore.
Con: può perdere pattern stagionali lunghi.
Opzione B: 365 giorni con peso temporale decrescente.
Pro: copre stagionalità.
Con: più complesso.
Raccomandazione tecnica: Opzione A in v1, predisposizione a B.

## 8) Proposta UX preliminare (non vincolante, in attesa decisioni)
1. Nuovo blocco in Gestione Tag: "Suggerimenti intelligenti" in cima alla sezione ricerca prodotti.
2. Due pannelli separati:
   - "Nuovi Tag suggeriti" (card cluster con nome proposto, evidenze, top prodotti, count).
   - "Prodotti da aggiungere ai tag esistenti" (tabella azionabile per tag).
3. CTA chiare:
   - "Crea tag + associa tutto"
   - "Aggiungi N prodotti al tag"
   - "Ignora suggerimento" (con snooze).
4. Notifiche in inbox con deep-link a pages/4_analisi_personalizzata.py.

## 9) Uscita attesa da Fase 1
- Briefing consolidato + decisioni [1.1..1.6] approvate.
- Solo dopo approvazione: avvio Fase 2 con proposta architetturale completa (schema dati, migration plan, firme funzioni, step plan test/rollback).

## 10) Decisioni confermate (2026-05-25)
[PUNTO 1.1] Decisione: Opzione B (ibrida regole + similarita lessicale/fuzzy con fallback deterministico).

[PUNTO 1.2] Decisione: Opzione A (soglie fisse configurabili in v1).

[PUNTO 1.3] Decisione: Opzione A (suggerimento passivo con conferma utente, no auto-aggancio silenzioso).

[PUNTO 1.4] Decisione: Opzione B (notifiche inbox + callout contestuale in pagina Analisi e Tag).

[PUNTO 1.5] Decisione: Opzione B (digest controllato + first-time immediato).

[PUNTO 1.6] Decisione: Variante Opzione A con finestra temporale ridotta a 30 giorni + criterio obbligatorio aggiuntivo su numero prodotti (non solo tempo).
