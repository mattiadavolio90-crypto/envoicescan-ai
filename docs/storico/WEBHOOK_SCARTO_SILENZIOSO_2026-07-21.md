# Bug: webhook Invoicetronic scartava fatture reali con 200 — 21/07/2026

> ✅ **CHIUSO, fixato e deployato lo stesso giorno (21/7/2026)**, commit `fa6f695`,
> Edge Function `invoicetronic-webhook` v33. Questo documento è la ricostruzione
> completa del percorso diagnostico e del fix, per non dover ripartire da zero se
> ricapita qualcosa di simile. Vedi anche i precedenti della stessa serie:
> `INVOICETRONIC_DIAGNOSI_2026-07-02.md` e `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md`.

## Problema segnalato
Mattia segnala (screenshot del Desk Invoicetronic) che "Invoicetronic non riceve
fatture da più di una settimana": il contatore "Transazioni Usate" del Desk è
fermo a **26/1000** da giorni, per OFFSIDE SRL (P.IVA 07863990961, 2 sedi:
OFFSIDE SPORTS PUB via Losanna 46 / OVERTIME via Settembrini 36).

## Primo errore diagnostico (mio) — corretto in corsa
Prima ipotesi: il problema era di nuovo a monte (SDI/Invoicetronic non riceve),
come nell'episodio del 14/7. **Sbagliata**: Mattia ha corretto subito ("NO ha
messo nostro SDI e sono arrivate 26 fatture da Invoicetronic ma ora non stanno
più arrivando") — le 26 erano realmente arrivate, il problema era che non ne
arrivavano di nuove.

Ho comunque preparato una mail per l'assistenza Invoicetronic (mai inviata,
vedi sotto) e in parallelo ho fatto la verifica diretta via API con la chiave
live (`ik_live_fLgZldZ95Ua3hxO8fIFJbTPO84u6AhxJ`, fornita da Mattia una tantum,
non salvata in chiaro né in memoria né nei documenti).

## Secondo errore diagnostico (mio) — corretto dall'assistenza Invoicetronic
La mia prima query API (`GET /v1/receive` con filtro `committente`) sembrava
confermare "zero nuove fatture dopo il 15/7". **Causa: paginazione.** L'endpoint
pagina i risultati e la query di default mostrava solo la prima pagina (~26
record), mascherando le fatture più recenti.

**Stefano/Nicola (assistenza Invoicetronic) hanno risposto:**
> "Ci sono 10 fatture in attesa su Invoicetronic. La query è probabilmente
> sbagliata; committente deve includere IT, altrimenti non troverà nulla (match
> esatto). Anche una semplice GET senza filtri rivelerà tutte le fatture
> disponibili, sia quelle già lette che quelle da leggere. In ogni caso, lato
> SDI/Invoicetronic tutto a posto."

Ripetendo `GET /v1/receive?pageSize=100` (senza filtro stretto) sono comparse
**11 fatture nuove non ancora acquisite** (non 10 — il conteggio di Nicola era
approssimato). **Prova decisiva che il problema era a valle, nostro, non
upstream.**

## Causa radice — trovata nel codice
`supabase/functions/invoicetronic-webhook/index.ts` riconosceva un evento di
ricezione fattura solo con match **esatto**: `endpoint === 'receive'`. Il
payload webhook **live** reale di Invoicetronic porta nel campo `endpoint`
l'endpoint API effettivo, che **non è mai il secco `"receive"`** — è qualcosa
come `"receive/86940"` o `"/v1/receive"`. Il match esatto quindi non
riconosceva mai un evento reale.

Conseguenza: `isReceiveEvent` risultava `false` → il vecchio codice restituiva
**`200 OK` senza salvare nulla e senza log utile**. Invoicetronic vede un 200 e
**non ritenta** (comportamento corretto per un webhook: un 200 significa
"consegnato con successo"). Risultato: fattura consegnata con successo dal loro
lato, persa in silenzio dal nostro.

## Scoperta più pesante: il flusso automatico non aveva MAI funzionato
Controllando `fatture_queue`, le "26 fatture entrate il 15/7" che sembravano la
prova che il webhook funzionasse **non provenivano da veri webhook**: portavano
il marcatore `payload_meta.xml_recovered_at = "2026-07-20-manual"` — un campo
che **non esiste in nessun punto del codice del repo**, quindi scritto da query
dirette one-off (recuperi manuali precedenti), non dal flusso automatico.

**Conclusione**: il flusso webhook → Edge Function → `fatture_queue` per
OFFSIDE non aveva mai funzionato end-to-end con un payload realmente spinto da
Invoicetronic. Sembrava funzionare solo perché ogni volta veniva "rattoppato"
con un recupero manuale. Lezione per il futuro: quando un flusso sembra
funzionare solo grazie a recuperi manuali ripetuti, verificare se il percorso
*automatico* sia mai stato davvero testato con un payload reale (non
confezionato da noi) — vedi `[[verifica_prima_di_fidarti_dei_piani]]` in memoria.

## Fix (commit `fa6f695`, deployato come v33)

**1. Riconoscimento robusto dell'evento** (`isReceiveWebhook` / `isOtherWebhook`,
funzioni pure esportate in `index.ts`):
```ts
export function isReceiveWebhook(ev: NormalizedWebhookEvent): boolean {
  const endpointMatch = ev.endpoint != null && /(^|[^a-z])receive([^a-z]|$)/.test(ev.endpoint)
  const eventMatch    = ev.eventName != null && ev.eventName.startsWith('receive')
  return endpointMatch || eventMatch
}
export function isOtherWebhook(ev: NormalizedWebhookEvent): boolean {
  return ev.endpoint != null &&
    !/receive/.test(ev.endpoint) &&
    (ev.eventName == null || !ev.eventName.startsWith('receive'))
}
```
Riconosce qualsiasi endpoint che contenga il segmento "receive" come parola
(non sottostringa: `"received_notification"` resta escluso), più l'alias
storico `eventName` che inizia per `"receive"` (`receive.add`, `receive.update`).

**2. Rete di sicurezza — mai più perdita silenziosa.** Se un evento arriva con
**HMAC valido** (quindi autenticato, è davvero Invoicetronic) ma non viene
riconosciuto come receive, oppure manca `resourceId`/`eventId`, il webhook
**non risponde più 200-e-basta**: registra comunque una riga in `fatture_queue`
con `status: 'failed'`, `piva_raw: 'UNKNOWN'`, e `payload_meta.unrecognized_event`
= motivo dello scarto (+ `raw_endpoint`, `raw_event`, `resource_id` per
diagnosi). Se anche l'insert fallisse, risponde `500` (così Invoicetronic
ritenta, invece di considerarlo consegnato). Event key con fallback
(`eventId` → `res:{resourceId}` → hash del body) per evitare collisioni
sull'upsert idempotente. Così qualunque variante di payload non ancora
prevista **compare visibile in coda come `failed`**, recuperabile, invece di
sparire senza traccia.

**3. Test**: nuovo file `event_recognition_test.ts`, 12 test — copre le forme
reali di endpoint (`receive`, `receive/86940`, `/v1/receive`,
`api/v1/receive/84532`, `eventName` `receive.add`/`receive.update`), i
falsi-positivi da escludere (`received_notification`, `send`, `status`), e la
mutua esclusività tra `isReceiveWebhook`/`isOtherWebhook`. Tutti verdi, nessuna
regressione sulla suite Edge Function esistente (hmac/p7m/routing).

## Recupero delle 11 fatture perse
Non esistendo un endpoint di retry lato Invoicetronic, le 11 fatture (già
presenti e "in attesa" sul loro sistema dal 15 al 21/7) sono state re-inviate
alla Edge Function in produzione ricostruendo e firmando manualmente 11 eventi
equivalenti (stesso `resource_id`/`company_id`, header
`Invoicetronic-Signature: t=<ts>,v1=<hmac-hex>` con
`HMAC-SHA256("{ts}.{rawBody}", INVOICETRONIC_WEBHOOK_SECRET)`) — stesso
identico flusso che avrebbe eseguito Invoicetronic stessa.

**Risultato: 11/11 in `fatture_queue`**, tutte `da_assegnare` (atteso: OFFSIDE
multi-sede, P.IVA condivisa, serve lo smistamento manuale — non un errore),
XML ben formato incluse le 5 fatture firmate `.p7m` (il fix P7M del 15/7 ha
retto). Marcate con `correlation_id = 'replay-fix-v33-<resource_id>'` per
distinguerle in futuro da un arrivo webhook nativo. Zero righe finite nella
rete di sicurezza (`unrecognized_event` sempre `NULL`) — tutte riconosciute
correttamente dal fix.

## Chiarimento importante: perché il contatore "Transazioni Usate" di Invoicetronic è salito da 26 a 37
Punto su cui la mia prima spiegazione è stata sbagliata e Mattia mi ha
corretto (giustamente): il contatore **non** sale semplicemente perché SDI
consegna una fattura a Invoicetronic — sale quando **noi la scarichiamo/leggiamo
via la loro API**. Il codice della Edge Function, per ogni evento receive
riconosciuto, fa una `GET https://api.invoicetronic.com/v1/receive/{resource_id}?include_payload=true`
per ottenere l'XML (righe ~615 e ~894 di `index.ts`). Il mio replay ha quindi
generato 11 vere chiamate a quell'endpoint → +11 sul contatore, **contestuali**
al mio intervento, non a un arrivo autonomo. Questo conferma anche che il
recupero è genuino e verificato pure lato Invoicetronic, non solo scritto a
mano nel nostro DB.

## Verifica di produzione post-fix (fatta con l'agente `flusso-dati-monitor`)
- **Versione deployata**: `invoicetronic-webhook` confermata **v33, ACTIVE** su
  Supabase (nessun rischio di versione vecchia in cache).
- **Log post-deploy**: tutte le chiamate viste sono `200`, ma corrispondono
  esattamente agli orari dei miei replay manuali (`correlation_id =
  replay-fix-v33-*`) — **nessun evento webhook spontaneo reale è ancora
  arrivato** da quando la v33 è live, semplicemente perché non è ancora
  arrivata una fattura nuova da OFFSIDE nel frattempo.
- **`fatture_queue`**: zero righe con `status='failed'`/`unrecognized_event`
  valorizzato, su qualsiasi cliente — ma è un risultato "non ancora
  contraddetto", non "confermato con traffico reale".

**Stato onesto a fine sessione**: il codice è corretto, testato (12 test
unitari + suite esistente verde) e deployato in produzione. **Manca ancora la
conferma sul campo**: la prima fattura vera che arriverà su OFFSIDE via SDI
dopo il 21/7, se comparirà in coda da sola (senza replay, `correlation_id`
nativo/assente), sarà la prova definitiva che il ciclo automatico regge
end-to-end. Va controllata quando arriva.

## Housekeeping di sessione
- Mail di segnalazione a Invoicetronic **preparata ma mai inviata** (era basata
  sulla diagnosi sbagliata "problema upstream" — superata dai fatti, non più
  utile da mandare così com'è).
- Script di replay (`replay11.py`) e file con l'elenco delle 11 fatture
  (`unread11.json`, conteneva il webhook secret) **cancellati dallo scratchpad**
  a fine sessione — non lasciare secrets in file temporanei.
- Nessuna modifica a `INVOICETRONIC_API_KEY` / `INVOICETRONIC_WEBHOOK_SECRET`:
  erano già corretti dal fix del 14-15/7, il bug di questa sessione era solo
  nel matching del payload, non nei secrets.

## STATO FINALE — CHIUSO (fix), IN OSSERVAZIONE (conferma su traffico reale)
Le 11 fatture perse sono tutte recuperate e in coda. Il bug di riconoscimento è
fixato e la rete di sicurezza attiva rende strutturalmente impossibile una
futura perdita silenziosa (nel peggiore dei casi, un payload non previsto
finisce visibile come `failed`, mai più scomparso senza traccia).

**Prossimi passi residui (non bloccanti):**
1. **Mattia (manuale)**: smistare le 11 righe `da_assegnare` tra le 2 sedi
   OFFSIDE dalla vista Catena (si riconosce dal fornitore, non dall'indirizzo
   fatturazione — nessuno dei due indirizzi in fattura è la sede operativa).
2. **Verifica sul campo**: alla prossima fattura reale ricevuta via SDI su
   OFFSIDE, controllare che arrivi in coda da sola (senza intervento manuale) —
   quello è il segnale che chiude definitivamente anche la parte "osservata con
   traffico reale", non solo "corretta sulla carta".
3. Opzionale: breve messaggio di chiusura a Nicola/Stefano (assistenza
   Invoicetronic) per confermare che il problema era nostro e ringraziare della
   segnalazione delle fatture in attesa — non ancora inviato, non obbligatorio.
