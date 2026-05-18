# VERIFICA CRITICA SPRINT 2 - Multi-livello

Data: 2026-05-14

## Sezione A - Aderenza proposta vs codice
[PUNTO A.1] - ✅ OK
Riga: services/notification_service.py#L364
Motivazione: esiste builder monthly e helper get_previous_month_period.
Azione: estendere con nuovo builder food_cost.

[PUNTO A.2] - ✅ OK
Riga: services/notification_inbox_service.py#L73
Motivazione: resolve_bucket centralizzato, facilmente estendibile.
Azione: aggiungere mapping topic nuovi.

[PUNTO A.3] - ✅ OK
Riga: services/upload_handler.py#L1740
Motivazione: blocco ingestion post-upload gia presente con try/except.
Azione: innestare Radar non critico subito dopo upsert corrente.

## Sezione B - Rischi non coperti
[PUNTO B.1] - ⚠️ ATTENZIONE
Riga: services/notification_service.py#L546
Motivazione: evitare notifiche operative in impersonazione.
Azione: mantenere gate impersonating per trial e food_cost.

[PUNTO B.2] - ⚠️ ATTENZIONE
Riga: services/anomaly_radar_service.py#L1
Motivazione: query radar devono includere filtri user_id + ristorante_id + deleted_at.
Azione: applicare filtro tenant in ogni query.

[PUNTO B.3] - ⚠️ ATTENZIONE
Riga: migrations/071_add_radar_indexes.sql#L1
Motivazione: performance query radar su piva/data/importo.
Azione: creare due indici parziali IF NOT EXISTS.

## Sezione C - Decisioni aperte
[PUNTO C.1] - ✅ OK
Riga: richiesta utente
Motivazione: bucket strategy e fonte dati gia decise esplicitamente.
Azione: nessuna.

## Sezione D - Proposta finale integrata
[PUNTO D.1] - ✅ OK
Riga: multipli file
Motivazione: piano completo con firme funzioni, integrazione, migration, test.
Azione: procedere a implementazione step-by-step.

## Sezione E - Domande pre-step
- Nessuna domanda bloccante residua.

## Sezione F - Revisione critica pre-step
[PUNTO F.1] - ✅ OK
Riga: app.py + upload_handler.py
Motivazione: integrazione non invasiva, fallback safe su errori radar.
Azione: implementare.

## Esito gate
✅ PIANO APPROVATO
Data: 2026-05-14
Versione spec: dev-notes/PROPOSTA_ARCHITETTURALE_SPRINT2_NOTIFICHE_RADAR_2026-05-14.md
Step plan: 8 step
Tech-debt tracciato: ottimizzazione query inbox expires_at lato SQL (fuori Sprint 2)
Pronto per implementazione Step 1.
