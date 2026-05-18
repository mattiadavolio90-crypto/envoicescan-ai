# BRIEFING SPRINT 2 - Food Cost + MOL + Anomaly Radar

Data: 2026-05-14
Stato: COMPLETATO

## Descrizione funzionale
- Estendere le notifiche operative con segnali su Food Cost e MOL.
- Introdurre Radar anomalie deterministico (senza AI) basato su fatture_documenti.
- Integrare il Radar sia post-upload sia con check settimanale dedicato.

## Perimetro impatto
- services/notification_service.py
- app.py
- services/anomaly_radar_service.py (nuovo)
- services/upload_handler.py
- services/notification_inbox_service.py
- migrations/071_add_radar_indexes.sql (nuova)
- tests/test_notification_service.py
- tests/test_anomaly_radar_service.py (nuovo)

## Vincoli espliciti confermati
- Fatturato netto (coerenza con margine_service).
- MOL letto da DB con fallback runtime.
- Base Radar: fatture_documenti.
- Bucket topic-specific.
- File blocked esclusi dalla inbox.

## Decisioni business gia prese
- Notifiche Food Cost e MOL in severity warning.
- Duplicati fattura in severity error.
- Radar non blocca pipeline upload (best effort, try/except non critico).

## Priorita rischio
1. Regressioni su pipeline upload e inbox.
2. Dedupe/bucket incoerenti per topic nuovi.
3. Falsi positivi radar su importi e duplicati.

## Domande bloccanti
- Nessuna: requisiti e scelte sono stati forniti in modo completo.
