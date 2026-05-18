# BRIEFING - Grafici Spesa nel Tempo (Punto 2 IMPLEMENTAZIONI)

Data: 2026-05-14
Stato: COMPLETATO

## Descrizione funzionale
- Aggiungere nella pagina Controllo Prezzi una sezione con grafici temporali della spesa mensile:
  - per fornitore (selectbox + line chart mensile + media storica 12 mesi)
  - per categoria (selectbox + line chart mensile + media storica 12 mesi)
- I grafici devono usare i dati gia caricati nel flusso pagina, senza query Supabase aggiuntive lato UI.

## Perimetro impatto
- pages/3_controllo_prezzi.py
- services/db_service.py
- tests/test_db_service.py

## Vincoli espliciti
- Nessuna regressione sulle tab esistenti: Variazioni Prezzo, Sconti/Omaggi, Note di Credito.
- Nessuna modifica schema DB o migration.
- Rispetto multi-tenant: usare dati gia filtrati per user_id + ristorante_id.
- Coerenza UX con filtro periodo gia presente in pagina.

## Decisioni business gia prese
- La visualizzazione e nel tab Variazioni Prezzo.
- Asse X per mesi, asse Y spesa aggregata in euro.
- Media storica mostrata come linea tratteggiata.

## Priorita rischio
1. Coerenza numerica della spesa (normalizzazione valori e date).
2. Prestazioni UI (no query extra, solo aggregazione in-memory).
3. Stato sessione non invasivo (nuove key namespace cp_*).

## Domande bloccanti
- Nessuna: il punto 2 e sufficientemente definito per implementazione.
