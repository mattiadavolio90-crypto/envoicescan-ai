# PROPOSTA ARCHITETTURALE SPRINT 2

Data: 2026-05-14
Stato: VALIDATA

## Obiettivo
Implementare Food Cost + MOL notifications e Radar Anomalie con integrazione inbox idempotente.

## Modello dati e fonte
- Fonte Food Cost/MOL: margini_mensili via carica_margini_anno.
- Fonte Radar: fatture_documenti (tenant-scoped, deleted_at IS NULL).
- Inbox persistence: notification_inbox via build_notification_record + upsert_notification_inbox RPC.

## Topic nuovi
- food_cost_soglia_superata (operativa, recurring monthly)
- mol_negativo (operativa, recurring monthly)
- food_cost_trend_peggioramento (operativa, recurring monthly)
- fattura_duplicata (upload, one-shot per upload)
- piva_duplicata_fornitore (radar, weekly)
- fattura_anomala_importo (upload, one-shot per upload)
- fornitore_critico_consecutivo (radar, recurring weekly)

## Bucket strategy
- monthly: food_cost_soglia_superata, mol_negativo, food_cost_trend_peggioramento
- upload hash file_ids: fattura_duplicata, fattura_anomala_importo
- weekly ISO: piva_duplicata_fornitore, fornitore_critico_consecutivo

## Refresh on conflict (DO UPDATE)
- food_cost_soglia_superata
- mol_negativo
- food_cost_trend_peggioramento
- fornitore_critico_consecutivo

## File coinvolti
- Modifica: services/notification_service.py
- Modifica: app.py
- Nuovo: services/anomaly_radar_service.py
- Modifica: services/upload_handler.py
- Modifica: services/notification_inbox_service.py
- Nuovo: migrations/071_add_radar_indexes.sql
- Modifica: tests/test_notification_service.py
- Nuovo: tests/test_anomaly_radar_service.py

## Step plan operativo
1. TASK 2A: builder food_cost in notification_service.
2. TASK 2B: integrazione app.py import/call/topic map.
3. TASK 2C: nuovo anomaly_radar_service.
4. TASK 2D: integrazione upload_handler post-upload.
5. TASK 2E: bucket/refresh topic in notification_inbox_service.
6. TASK 2F: migration indici radar.
7. TASK 2G: verifica topic map app.py (solo operativa).
8. TEST: unit test notification_service + anomaly_radar_service.
