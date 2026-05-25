# VERIFICA CRITICA MULTI-LIVELLO - Suggerimenti Tag
Data: 2026-05-25
Input: PROPOSTA_ARCHITETTURALE_tag_suggerimenti_2026-05-25.md
Esito complessivo: PASS con attenzione su rischi non bloccanti

## Sezione A - Aderenza proposta vs codice
[PUNTO A.1] - ✅ OK
Riga: pages/4_analisi_personalizzata.py:#L957
Motivazione: la pagina Gestione Tag e gia il punto naturale per integrare la nuova area "Suggerimenti intelligenti" senza cambiare routing.
Azione: inserire sezione suggerimenti sopra ricerca prodotti mantenendo flusso esistente.

[PUNTO A.2] - ✅ OK
Riga: services/db_service.py:#L1847
Motivazione: esiste gia aggregazione descrizioni con descrizione_key/occorrenze/ultima_data utile per il pool suggerimenti.
Azione: riuso in service dedicato con finestra 30 giorni e limiti anti-scan.

[PUNTO A.3] - ✅ OK
Riga: migrations/055_create_custom_tags.sql:#L84
Motivazione: schema custom_tags/custom_tag_prodotti gia normalizzato e con RLS owner-based; estensione con tabelle suggestion e coerente.
Azione: creare migration 080/081 mantenendo pattern policy/trigger.

[PUNTO A.4] - ✅ OK
Riga: services/notification_inbox_service.py:#L135
Motivazione: infrastruttura inbox supporta topic nuovi, dedupe_key e refresh_on_conflict.
Azione: aggiungere topic tag_suggestion_new_tag e tag_suggestion_extend_tag con bucket settimanale.

## Sezione B - Rischi non coperti
[PUNTO B.1] - ⚠️ ATTENZIONE
Riga: config/constants.py:#L1687
Motivazione: limiti trial/tag max possono rendere non accettabili alcuni suggerimenti (utente trial = max 1 tag).
Azione: nella UI mostrare CTA alternativa "estendi tag esistente" o "upgrade" quando create_tag non consentito.

[PUNTO B.2] - ⚠️ ATTENZIONE
Riga: services/db_service.py:#L1405
Motivazione: suggerimenti devono ignorare righe soft-delete, altrimenti si generano falsi cluster.
Azione: query suggerimenti con deleted_at is null come regola hard.

[PUNTO B.3] - ⚠️ ATTENZIONE
Riga: services/notification_inbox_service.py:#L29
Motivazione: topic nuovi senza regole dedupe/bucket rischiano spam alert.
Azione: inserire topic in _REFRESH_ON_CONFLICT_TOPICS e resolve_bucket su settimana ISO.

[PUNTO B.4] - ⚠️ ATTENZIONE
Riga: pages/4_analisi_personalizzata.py:#L324
Motivazione: collisioni session_state possibili se chiavi suggerimenti non namespaced.
Azione: obbligo namespace ap_sugg_* e reset al cambio ristorante.

[PUNTO B.5] - ⚠️ ATTENZIONE
Riga: services/upload_handler.py:#L1788
Motivazione: trigger post-upload concorrenti possono duplicare calcolo suggerimenti.
Azione: upsert su cluster_key + unique pending + refresh last_seen_at idempotente.

[PUNTO B.6] - ⚠️ ATTENZIONE
Riga: migrations/055_create_custom_tags.sql:#L184
Motivazione: compliance multi-tenant/GDPR richiede ownership rigorosa e cancellazione dati suggerimenti in export/delete account.
Azione: includere nuove tabelle nei flussi export/delete account e policy RLS owner.

## Sezione C - Decisioni aperte
[PUNTO C.1] - ✅ OK
Riga: DOCUMENTAZIONE/PIANIFICAZIONE/PROPOSTA_ARCHITETTURALE_tag_suggerimenti_2026-05-25.md:#L252
Motivazione: decisione confermata: window_days=30 e min_products_for_suggestion=6.
Azione: applicare questi default in constants + service v1.

[PUNTO C.2] - ✅ OK
Riga: DOCUMENTAZIONE/PIANIFICAZIONE/BRIEFING_tag_suggerimenti_2026-05-24.md:#L105
Motivazione: canale notifiche confermato inbox + callout in pagina.
Azione: implementare doppia visibilita con dedupe anti-rumore.

## Sezione D - Proposta finale integrata
[PUNTO D.1] - ✅ OK
Riga: services/tag_suggestion_service.py:#L1
Motivazione: separare motore suggerimenti in service dedicato evita logica pesante in pagina Streamlit.
Azione: introdurre service con API pure (detect/upsert/accept/dismiss/snooze/notifiche).

[PUNTO D.2] - ✅ OK
Riga: migrations/080_create_custom_tag_suggestions.sql:#L1
Motivazione: persistenza suggestion/items necessaria per stato utente e feedback storico.
Azione: creare tabelle + trigger + RLS con migration sequenziali 080/081.

[PUNTO D.3] - ✅ OK
Riga: pages/5_notifiche_e_gestione.py:#L2324
Motivazione: fallback di navigazione gia centralizzato, semplice estendere con nuovi topic tag.
Azione: mappare topic nuovi su pages/4_analisi_personalizzata.py.

## Sezione E - Domande pre-step mirate al codice
[PUNTO E.1] - ✅ OK
Riga: services/db_service.py:#L1946
Motivazione: serve invalidazione cache dedicata suggerimenti oltre clear_tags_cache.
Azione: aggiungere clear_tag_suggestions_cache e chiamarla in tutti i punti accept/dismiss/snooze.

[PUNTO E.2] - ✅ OK
Riga: services/notification_inbox_service.py:#L26
Motivazione: source_type nuovo non obbligatorio (fallback 7 giorni) ma meglio esplicitarlo.
Azione: aggiungere source_type='tag' in _EXPIRES_DELTA per controllo TTL.

[PUNTO E.3] - ✅ OK
Riga: tests/test_custom_tags.py:#L4
Motivazione: test pagina attuale coprono helper puri ma non il nuovo motore.
Azione: introdurre test_tag_suggestion_service.py + estensione test notifiche.

## Sezione F - Revisione critica pre-step
[PUNTO F.1] - ✅ OK
Riga: DOCUMENTAZIONE/PIANIFICAZIONE/PROPOSTA_ARCHITETTURALE_tag_suggerimenti_2026-05-25.md:#L200
Motivazione: il piano copre schema dati, pipeline, cache, UI, notifiche, test e rollback.
Azione: procedere con implementazione per step senza variazioni scope.

[PUNTO F.2] - ✅ OK
Riga: DOCUMENTAZIONE/PIANIFICAZIONE/PROPOSTA_ARCHITETTURALE_tag_suggerimenti_2026-05-25.md:#L219
Motivazione: step plan include gate e criteri di done chiari.
Azione: mantenere un solo step attivo per volta con validazione test prima dello step successivo.

## Esito gate Fase 3
- Blocchi residui: 0
- Warning aperti: 6 (gestibili nello step design/implementazione, non bloccanti)
- Condizione di passaggio a Fase 4: soddisfatta
