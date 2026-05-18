# VERIFICA CRITICA - Grafici Spesa nel Tempo

Data: 2026-05-14

## Sezione A - Aderenza proposta vs codice
[PUNTO A.1] - ✅ OK
Riga: pages/3_controllo_prezzi.py#L301
Motivazione: esiste tab Variazioni Prezzo con blocco grafico gia consolidato dove innestare la nuova sezione.
Azione: integrare sotto grafico storico prodotto senza alterare tab navigation.

[PUNTO A.2] - ✅ OK
Riga: services/db_service.py#L260
Motivazione: esistono gia funzioni pure DataFrame (es. calcola_alert) coerenti con nuovo helper aggregazione.
Azione: aggiungere funzione nello stesso modulo per mantenere pattern di riuso.

[PUNTO A.3] - ✅ OK
Riga: tests/test_db_service.py#L93
Motivazione: suite test gia organizzata per funzioni db_service data-centriche.
Azione: aggiungere gruppo test dedicato per aggregazione mensile.

## Sezione B - Rischi non coperti
[PUNTO B.1] - ⚠️ ATTENZIONE
Riga: pages/3_controllo_prezzi.py#L245
Motivazione: il filtro periodo pagina puo ridurre a 1 mese il dataset, rendendo la media 12m poco informativa.
Azione: fallback automatico a media sui mesi disponibili con label esplicita.

[PUNTO B.2] - ✅ OK
Riga: services/db_service.py#L99
Motivazione: dataset origine e gia filtrato per user_id/ristorante_id/deleted_at.
Azione: nessuna query aggiuntiva lato UI.

[PUNTO B.3] - ✅ OK
Riga: pages/3_controllo_prezzi.py#L578
Motivazione: naming session key cp_* gia usato estensivamente nella pagina.
Azione: mantenere namespace cp_* per i nuovi widget.

## Sezione C - Decisioni aperte
[PUNTO C.1] - ✅ OK
Riga: IMPLEMENTAZIONI.md
Motivazione: perimetro funzionale chiaro (fornitore/categoria + media 12m).
Azione: nessuna decisione bloccante residua.

## Sezione D - Proposta finale integrata
[PUNTO D.1] - ✅ OK
Riga: pages/3_controllo_prezzi.py + services/db_service.py
Motivazione: integrazione locale, senza migrazioni, con test unitari dedicati.
Azione: procedere implementazione step-by-step.

## Sezione E - Domande pre-step
- Nessuna domanda bloccante residua.

## Sezione F - Revisione critica pre-step
[PUNTO F.1] - ✅ OK
Riga: tests/test_db_service.py
Motivazione: testabilita alta grazie a funzione pura di aggregazione.
Azione: introdurre test su normalizzazione, bucket mensile e gestione input invalidi.

## Esito gate
✅ PIANO APPROVATO
Data: 2026-05-14
Versione spec: dev-notes/PROPOSTA_ARCHITETTURALE_GRAFICI_SPESA_TEMPO_2026-05-14.md
Step plan: 4 step
Tech-debt tracciato: valutare in futuro confronto media 12m fisso su storico completo vs periodo filtrato utente.
Pronto per implementazione Step 1.
