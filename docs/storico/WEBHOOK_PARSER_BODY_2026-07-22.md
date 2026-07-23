# Bug: webhook nativo arriva ma il parser non legge il payload — 22-23/07/2026

> ✅ **Fix scritto, testato (52 test Deno verdi), type-check pulito. IN ATTESA DI
> DEPLOY** (fuori orario) e della **conferma sul campo** al primo evento nativo
> reale. Edge Function `invoicetronic-webhook`. Terzo episodio della serie:
> vedi `INVOICETRONIC_DIAGNOSI_2026-07-02.md`, `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md`,
> `WEBHOOK_SCARTO_SILENZIOSO_2026-07-21.md`.

## Problema segnalato
Mattia: dopo il fix del 21/7, il contatore Invoicetronic continuava a salire ("da
26 a 37 a 43") ma restava il dubbio se le fatture entrassero DAVVERO nell'app.
"Due le ha scalate da solo e le altre solo dopo l'estrazione." In totale da
Invoicetronic dovevano esserci **43 fatture OFFSIDE**: il numero doveva tornare.

## Verifica del numero — TORNA: 43 = 43
Nel DB, le fatture SDI OFFSIDE (identificate da `payload_meta.resource_id`, che le
distingue dai caricamenti manuali) sono **esattamente 43**: 38 `da_assegnare` (tutte
con XML) + 5 `done`. Corrisponde al contatore Invoicetronic.

⚠️ Le altre **333** righe `da_assegnare` OFFSIDE **senza** resource_id NON sono SDI:
sono il blocco del 1° semestre caricato a mano il 20/7 per il riparto costi catena
(la card "365 da collocare · 380.455 €" nel briefing catena). Non falsano il conteggio
delle 43, ma spiegano perché la coda mostra un numero grande. Il briefing "ieri 11
fatture" era corretto ma parziale (contava solo la finestra del 21/7).

## Causa radice — il parser leggeva il livello sbagliato del JSON
I log Edge Function mostrano **POST reali 200** alla `invoicetronic-webhook` v33
negli orari 22/7 05:55 / 08:28 / 09:29 (IT) — coincidenti coi `created_at` di 3
fatture. Quindi **il webhook nativo ARRIVA e l'HMAC è VALIDO** (altrimenti la rete
di sicurezza non scatterebbe). Ma le righe salvate avevano `raw_endpoint=null`,
`raw_event=null`, `resource_id=null`: il parser leggeva **tutti null**.

Il fix del 21/7 aveva reso robusto il *riconoscimento* dell'endpoint, ma assumeva
l'oggetto `Event` al **root** del body (come nei payload di test/replay costruiti da
noi). La doc ufficiale Invoicetronic
(https://invoicetronic.com/en/docs/webhooks/) descrive l'Event con i campi al root
(`id, user_id, company_id, resource_id, endpoint, method, status_code, success,
date_time, api_version`), ma il body **live reale** arriva in forma diversa —
quasi certamente un **ARRAY** `[{...}]` o annidato in un **wrapper**
(`{"data":{...}}` o simile). `JSON.parse(rawBody)` leggeva `ev.resource_id` sul
contenitore invece che sull'Event → tutto undefined → a cascata:
`isReceiveWebhook=false` → rete di sicurezza → `failed`/`dead` senza resource_id →
il worker non può scaricare l'XML → morte dopo 8 tentativi.

**Perché il fix del 21/7 non poteva coprirlo**: era testato solo su payload piatti
costruiti da noi, mai sul body nativo reale. Stessa lezione del 21/7
(`[[verifica_prima_di_fidarti_dei_piani]]`): un flusso che "sembra funzionare" solo
grazie a recuperi manuali ripetuti non è mai stato davvero testato end-to-end.

### Sul contatore Invoicetronic (chiarimento definitivo)
Il contatore sale quando **qualcuno LEGGE la fattura via API** (`GET /receive/{id}`),
non quando SDI la consegna. "Le due scalate da sole" = i 3 webhook nativi che sono
arrivati davvero (la Edge Function ha fatto la sua GET → +1), ma hanno fallito il
parsing. "Le altre dopo l'estrazione" = le GET dei miei script di recovery.
**Contatore che sale ≠ fattura entrata pulita nell'app.**

### Realtà cruda: il flusso automatico non è MAI partito da solo
Le 43 fatture in DB: 26 recuperate a mano il 15/7, 11 (replay) il 21/7, 6 (via API)
il 22/7. **Nessuna** con origine webhook nativo andato a buon fine. Ogni fattura è
entrata perché l'abbiamo tirata giù noi.

## Fix (Interventi A–E)

**A — Parser robusto a array e wrapper** (`extractEventObject`, esportata):
scava il body fino all'oggetto Event reale, gestendo: oggetto piatto, array (anche
multi-evento: processa il primo, `extraCount` conta+logga gli altri, mai persi),
wrapper annidati (`data`/`event`/`payload`/`events`/`items`/`result`/`body`, fino a
3 livelli). `event` è ambiguo (nome-evento stringa vs wrapper-oggetto): trattato come
campo-Event solo se il valore è stringa. Il resto della pipeline invariato (HMAC già
verificato sul rawBody intero).

**B — Cattura del body grezzo** (`payload_meta.raw_body_sample`, troncato 2KB):
ogni evento non riconosciuto salva un campione del body. L'Event NON contiene PII
(solo id numerici/endpoint/timestamp). Così il **primo evento nativo post-deploy
rivela la struttura esatta** senza aspettare un secondo giro.

**C — Auto-recupero nella rete di sicurezza**: se dal body si estrae un
`resource_id` valido (anche con endpoint/event non riconosciuti), NON ci si ferma
più a `failed`: si prosegue col download XML. Flag `passedSafetyNet` +
`ignoreDuplicates: !passedSafetyNet` così l'upsert finale **promuove** (ON CONFLICT
DO UPDATE) la riga `failed` a `da_assegnare`/`done` invece di lasciarla doppia
(DO NOTHING). Chiave idempotente coerente: `event_id` se c'è, altrimenti
`res:{resourceId}` (mai la stringa letterale `"null"`, che avrebbe fatto collidere
tutte le fatture senza event_id sulla stessa riga — bug evitato).

**D — Test**: nuovo `event_unwrap_test.ts` (15 test: piatto/array/wrapper/annidato/
degeneri/alias camelCase/non-regressione sul campo `data` secondario). Suite Edge
Function completa **52/52 verde**, `deno check` pulito, zero regressioni su
hmac/p7m/routing/event_recognition.

**E — Pulizia righe morte**: le 3 righe `dead` del 21/7 (`piva UNKNOWN`, rid/raw
null — tentativi webhook nativi falliti PRIMA della cattura del body) erano residui
diagnostici, non fatture perse (le corrispondenti sono tra le 43 già recuperate).
Marcate `done` con `dead_resolved_reason`, così non generano falsi allarmi. Coda ora
senza righe `dead`.

## Cosa NON è stato toccato (e perché)
- **Secret** (`INVOICETRONIC_API_KEY`/`WEBHOOK_SECRET`): corretti, l'HMAC valida. Il
  problema era solo il parsing, non l'auth.
- Nessun deploy di giorno (regola: clienti in uso). Fix committato, deploy serale.

## STATO — FIX PRONTO, DA DEPLOYARE + VERIFICARE SUL CAMPO
Il codice è corretto, testato e type-safe. **Prova definitiva ancora mancante**
(come il 21/7): la prima fattura SDI reale post-deploy che comparirà in coda **da
sola** — con resource_id, XML, `da_assegnare`, senza `correlation_id` di recovery e
senza intervento manuale — chiude il caso. Stavolta, se una forma di payload
sfuggisse ancora, `raw_body_sample` dice esattamente com'è fatta al primo colpo.

## Prossimi passi
1. **Deploy** Edge Function fuori orario (`supabase functions deploy invoicetronic-webhook`).
2. **Verifica sul campo**: al primo evento nativo, controllare la nuova riga (deve
   avere resource_id + XML + `da_assegnare`; se `recovered_from_safety_net=true`,
   leggere `raw_body_sample` per confermare la forma reale e, se serve, affinare
   l'unwrap — ma la fattura è comunque entrata).
3. **Mattia (manuale)**: smistare le 38+ `da_assegnare` OFFSIDE tra le 2 sedi
   (si riconosce dal fornitore, non dall'indirizzo — nessuno dei due indirizzi in
   fattura è la sede operativa).
4. **🔴 SICUREZZA**: rigenerare la Live API key Invoicetronic (`ik_live_fLg…`,
   incollata in chat il 22/7 → compromessa) e aggiornare il secret su Supabase +
   Railway.
5. **Opzionale**: scrivere a Nicola/Stefano (assistenza Invoicetronic) per farsi
   confermare la struttura esatta del payload webhook (array vs wrapper) — non
   bloccante, il fix funziona a prescindere, ma chiude il cerchio.
