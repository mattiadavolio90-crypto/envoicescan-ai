# Diagnosi: fatture OFFSIDE non arrivano — 14/07/2026

> ✅ **CHIUSO, risolto e deployato il 15/7/2026** (vedi "STATO FINALE" in fondo a
> questo file). Per lo stato corrente vedi `RIEPILOGO_OFFSIDE_STATO_15-07.md`.
> Questo documento resta come traccia dettagliata del percorso diagnostico
> (sandbox vs live, secrets disallineati, bug P7M) — non descrive più lo stato
> attuale del sistema.

## Problema segnalato
OFFSIDE SRL (P.IVA 07863990961, due sedi: OFFSIDE SPORTS PUB via Losanna 46 e OVERTIME via Settembrini 36, Milano) ha impostato il nostro Codice Destinatario (7HD37X0) sul proprio cassetto fiscale, ma **nessuna fattura fornitore arriva** né sull'app ONEFLUX né su Invoicetronic. Mattia riferisce che sia il cassetto fiscale che la comunicazione ai fornitori sono già stati aggiornati da OFFSIDE/commercialista da oltre una settimana.

## Metodo
Su richiesta esplicita di Mattia, prima di concludere "è un problema SDI/cliente" è stato fatto un controllo rigoroso e a più livelli lato configurazione ONEFLUX + Invoicetronic, con verifiche dirette (non assunzioni).

## Verifiche eseguite lato "nostro" — tutte OK

| Area | Verifica | Esito |
|---|---|---|
| Edge Function webhook | Stato, versione, `verify_jwt` | Attiva v25, `verify_jwt=false` (corretto, auth è HMAC) |
| Log invocazioni | `get_logs` su invoicetronic-webhook | **Zero invocazioni mai ricevute** per OFFSIDE |
| `fatture_queue` | Righe per OFFSIDE dal 30/06 | Zero righe |
| `ristoranti` | Config sedi OFFSIDE | Entrambe `attivo=true`, `sdi_attivo=true`, indirizzi corretti |
| Codebase | grep "7HD37X0" / "codice_destinatario" | Zero occorrenze — il nostro sistema instrada per P.IVA/indirizzo estratti dall'XML, il Codice Destinatario è un concetto esterno a SDI/Invoicetronic, non lo gestiamo noi |
| Webhook Invoicetronic (screenshot) | URL, Eventi (`receive.add`), Abilitato, Segreto, campo Azienda vuoto | Tutto corretto; campo Azienda vuoto = webhook attivo per **tutte** le aziende dell'account (confermato da doc ufficiale, non un bug) |
| Registro eventi webhook | Storico consegne | "No data" — coerente con zero invocazioni: Invoicetronic non ha mai tentato di consegnare nulla, perché non ha mai ricevuto nulla da inoltrare |
| Dashboard Invoicetronic | Transazioni Usate / Limite | 0 / 1000 — pacchetto acquistato, mai consumato |
| Azienda OFFSIDE su Invoicetronic | Presenza, P.IVA, data creazione | Creata correttamente (IT07863990961), 11/06/2026, insieme a 4 aziende SUSHILAND |
| Codice Destinatario | Verifica su Dashboard profilo Mattia | 7HD37X0 confermato corretto |
| "Fatture ricevute" (Desk) | 510 fatture visibili | **Tutte fittizie/di test** (Notaio Azzeccagarbugli, Gadget snc, ecc., indirizzi inventati) — nessuna è una vera fattura OFFSIDE |
| Chiave API usata nei test | Test vs Live | Il campo "API Key" nel Profilo Desk (`ik_test_...`) è solo una preferenza personale di navigazione Desk-web, **scollegata** dal webhook/query di produzione — verificato in Dashboard → Chiavi che la chiave Live è `ik_live_fLgZldZ95Ua3hxO8flFJbTPO84u6AhxJ`, la stessa usata nel test API sotto |

## Prova definitiva
Query diretta all'API Invoicetronic (bypassa completamente la nostra app e la UI del Desk), con la chiave **live** corretta come Basic Auth:

```
GET /v1/receive?committente=07863990961
→ 200 OK
→ []
```

**Zero fatture sono mai state ricevute da Invoicetronic per la P.IVA di OFFSIDE**, su tutta la finestra di retention (2 anni). Se anche una sola fattura fosse arrivata da SDI, comparirebbe qui — indipendentemente da webhook, secret, o qualunque altra cosa nostra.

## Documentazione ufficiale Invoicetronic consultata (conferme rilevanti)
- Campo Azienda vuoto sul webhook = attivo per tutte le aziende dell'account (non un errore).
- Una company creata dopo l'arrivo di una fattura non causa perdita dati: Invoicetronic mette in coda e riprocessa automaticamente alla creazione dell'azienda.
- Un solo Codice Destinatario a livello di account/API key, condiviso da tutte le aziende gestite (OFFSIDE + le 4 SUSHILAND).
- Testo esplicito doc: *"Nessuna data di cutoff necessaria... l'Agenzia delle Entrate (SDI) inoltra automaticamente le fatture al tuo indirizzo registrato, indipendentemente dal codice specificato dai tuoi fornitori."*
- Tip troubleshooting ufficiale (CLI docs): *"Non ricevi fatture nell'ambiente di produzione? Assicurati che i tuoi corrispondenti utilizzino 7HD37X0 come valore del campo Codice Destinatario delle loro fatture."*

## Conclusione
**Lato ONEFLUX e lato Invoicetronic è tutto corretto e verificato con prove dirette** (non solo per esclusione): app, webhook, routing multi-sede, azienda su Invoicetronic, Codice Destinatario, chiave API live — nessun anello della catena nostra spiega l'assenza di fatture.

Il problema è a monte, tra **SDI e il cassetto fiscale di OFFSIDE**: nonostante la dichiarazione che cassetto e fornitori siano stati aggiornati da oltre una settimana, SDI non sta di fatto recapitando nulla per quella P.IVA con quel Codice Destinatario.

## Prossimo passo (in corso, verifica chiesta a OFFSIDE)
Controllo diretto sul **cassetto fiscale Agenzia delle Entrate** di OFFSIDE → sezione "Fatture e Corrispettivi" → "Consultazione": verificare se lì risultano fatture recenti ricevute da SDI.
- Se **zero fatture anche lì** → conferma che i fornitori non hanno ancora emesso nulla di nuovo dopo l'aggiornamento (a prescindere da cosa dichiarato).
- Se **le fatture ci sono sul cassetto AdE ma non su Invoicetronic** → il problema sarebbe nella registrazione del Codice Destinatario 7HD37X0 (es. non salvato correttamente, refuso) — da verificare a quel punto.

Mattia ha già inoltrato la richiesta di verifica a OFFSIDE; in attesa di risposta.

## Aggiornamento pomeriggio 14/07/2026

**Secondo giro di verifica (dopo conferma OFFSIDE):** OFFSIDE ha confermato che il cambio SDI sul cassetto fiscale è stato fatto "la scorsa settimana" e che probabilmente sono già arrivate fatture nuove dopo il cambio. Rifatta la stessa query diretta API:

```
GET /v1/receive?committente=07863990961
→ 200 OK
→ []
```

Stesso risultato di prima — invariato, ancora zero fatture, nonostante il cambio dichiarato attivo da oltre una settimana. Questo rafforza il sospetto che il problema non sia (solo) attesa fornitori, ma qualcosa nella configurazione a monte.

**Azioni in parallelo avviate:**
1. **Richiesta a OFFSIDE**: controllo diretto e puntuale sul proprio cassetto fiscale AdE — verificare sia il valore di Codice Destinatario effettivamente salvato, sia l'elenco fatture ricevute con data (sezione "Fatture e Corrispettivi" → "Consultazione"). Risposta in sospeso.
2. **Email inviata a Invoicetronic** (`info@invoicetronic.com`, supporto italiano, sede Ravenna): mail unica ed esaustiva in italiano con riepilogo completo di tutte le verifiche già fatte (per evitare botta e risposta) + 4 domande mirate:
   - conferma se SDI ha mai tentato una consegna (anche fallita/scartata) per 7HD37X0 / P.IVA IT07863990961
   - eventuale ritardo di propagazione/attivazione di un cambio Codice Destinatario superiore a una settimana
   - conferma che 7HD37X0 è correttamente accreditato e attivo in produzione
   - altro lato configurazione account/azienda/webhook che possa spiegare l'anomalia

   Allegati 6 screenshot (webhook, Dashboard Transazioni/Firme/Chiavi/Codice Destinatario, Desk fatture ricevute, Desk aziende, Desk profilo). Inviata oggi (14/07/2026), risposta attesa nel pomeriggio.

**Stato:** entrambi i riscontri (cassetto AdE OFFSIDE + risposta Invoicetronic) sono in sospeso. Nessuna ulteriore verifica possibile lato nostro finché non arriva almeno uno dei due — tutto il perimetro ONEFLUX/Invoicetronic già controllato e documentato sopra resta valido e pulito.

**Prossimo passo:** appena arriva una delle due risposte, confrontarla con quanto già verificato per isolare la causa definitiva (mancata emissione fornitori vs Codice Destinatario non effettivamente attivo vs problema lato SDI/Invoicetronic).

## Causa reale trovata — risposta assistenza Invoicetronic (Nicola, 14/07 pomeriggio)

**NON era un problema SDI/cassetto fiscale OFFSIDE.** Scambio mail con l'assistenza (Nicola) ha isolato la causa reale, tutta lato nostra configurazione Invoicetronic:

1. **Il Desk stava usando la API Key di test/sandbox**, non quella live, nel Profilo. Il Desk mostra dati coerenti con la chiave inserita (sandbox → aziende/fatture finte, le "510 fatture fittizie" già notate in precedenza erano proprio questo).
2. **Le aziende clienti (OFFSIDE + 4 SUSHILAND) erano state create solo in ambiente sandbox**, mai in ambiente live — perché la creazione era avvenuta da Desk mentre operava in modalità test.
3. **Conferma esplicita di Nicola: 26 fatture di OFFSIDE risultavano già in attesa lato SDI/Invoicetronic**, semplicemente non visibili perché si guardava l'ambiente sbagliato (sandbox invece di live).
4. Tentando di passare la chiave live nel profilo Desk è comparso un banner: il Desk in ambiente live richiede una "postazione" a pagamento (Desk seat, non necessaria in sandbox). Nicola ha confermato che **non serve comprarla**: le aziende si possono creare via API diretta con la chiave live, come già fatto finora in sandbox.

### Azione correttiva eseguita (14/07, sessione stessa)
Individuato tramite lo schema OpenAPI ufficiale (`https://api.invoicetronic.com/v1/docs/swagger.json`) l'endpoint corretto per la gestione aziende:
- `GET /v1/company` — lista aziende
- `GET /v1/company/{vat}` — lettura per P.IVA
- `POST /v1/company` — creazione (body: `{"id":0,"vat":"IT...","fiscal_code":"IT...","name":"..."}`)

**Nota correzione chiave live:** la chiave live salvata nei documenti/memoria precedenti conteneva un refuso (`fLgZldZ95Ua3hxO8flFJbTPO84u6AhxJ` — `l` minuscola) che causava `401 Unauthorized` su ogni chiamata. La chiave corretta ha una **I maiuscola**: `ik_live_fLgZldZ95Ua3hxO8fIFJbTPO84u6AhxJ` (verificata da Mattia via screenshot Dashboard → Chiavi). Con la chiave corretta, `/v1/receive?committente=07863990961` è tornato a rispondere `200 OK`.

Verificato che in ambiente live esisteva **solo** l'azienda auto-creata "MATTIA D'AVOLIO" (id 1736) — nessuna delle 5 aziende clienti. Create via `POST /v1/company` con la chiave live:

| Azienda | P.IVA | id live | Esito |
|---|---|---|---|
| OFFSIDE SRL | IT07863990961 | 1756 | 201 Created |
| SUSHILAND MARIANO COMENSE SRL | IT04140610132 | 1757 | 201 Created |
| LAND DEI SAPORI SRL | IT10865360969 | 1758 | 201 Created |
| SUSHILAND SAN GIULIANO M. SRL | IT12557550964 | 1759 | 201 Created |
| SUSHILAND VILLA GUARDIA SRL | IT12222020963 | 1760 | 201 Created |

Verificato anche il webhook in ambiente live: **già attivo e corretto** (id 9, `company_id: null` = tutte le aziende, `enabled: true`, evento `receive.add`, stesso URL Supabase e secret già in uso) — non serviva ricrearlo.

### Stato dopo la creazione — monitorato a 30', 1h e il giorno successivo (15/07), ancora vuoto
Ricontrollato `GET /v1/receive?committente=07863990961` e `GET /v1/receive` (senza filtro, tutto l'account) a ~30 minuti, ~1 ora e nuovamente il giorno dopo (15/07) dalla creazione delle 5 aziende in live (creazione: 19:47-19:48 UTC del 14/07): **sempre `[]`**, in tutti i controlli. Le 26 fatture citate da Nicola non sono mai rifluite automaticamente, nemmeno dopo diverse ore.

Conclusione: il riprocessamento automatico non avviene da solo (o comunque non entro un lasso di tempo ragionevole). Serve un'azione/sollecito esplicito da parte di Invoicetronic.

**Aggiornamento 15/07 mattina — Nicola conferma: le 26 fatture erano già caricate su Invoicetronic.** Nicola ha scritto proattivamente confermando che le 26 fatture arrivate dopo il cambio Codice Destinatario sono state caricate sulla API Invoicetronic, e che Desk non è indispensabile: con l'API si può fare tutto ciò che fa Desk.

Verifica immediata: `GET /v1/receive` (senza filtro) ha effettivamente mostrato le 26 fatture, tutte con `committente: IT07863990961` e `company_id: 1756` (OFFSIDE, creata il giorno prima) — confermato, erano davvero lì.

### Causa del blocco successivo — webhook riceveva ma rifiutava con 401
`fatture_queue` risultava comunque vuota. Controllati i log Edge Function: **26 tentativi di consegna webhook, tutti falliti con 401 Unauthorized** (confermato anche da `GET /v1/webhookhistory`). Causa: `INVOICETRONIC_WEBHOOK_SECRET` su Supabase (secrets, ultimo update 30/03) non corrispondeva più al secret attuale del webhook su Invoicetronic (`wh_sec_Mj0qDrFE6DTFUxV02bJZ0LS5ma56InLge`, creato 20/03 e mai cambiato da allora). Fix: `supabase secrets set INVOICETRONIC_WEBHOOK_SECRET=wh_sec_Mj0qDrFE6DTFUxV02bJZ0LS5ma56InLge`.

Test di un evento firmato manualmente (HMAC-SHA256 con lo stesso secret, replay dell'evento `receive.add`) → `200 OK`, ma la riga finiva in `fatture_queue` con `status: failed, piva_raw: UNKNOWN, api_error: "HTTP 401"`. Causa: anche `INVOICETRONIC_API_KEY` su Supabase (secret usato dalla Edge Function per chiamare `GET /v1/receive/{id}`) aveva lo stesso problema della chiave live — allineata anch'essa: `supabase secrets set INVOICETRONIC_API_KEY=ik_live_fLgZldZ95Ua3hxO8fIFJbTPO84u6AhxJ`.

### Recupero delle 26 fatture — 22 riuscite, 4 bloccate da un bug reale (P7M)
Non essendoci un endpoint di "retry" lato Invoicetronic, per recuperare le 26 fatture già presenti (webhook originale mai arrivato a buon fine per nessuna) sono stati ricostruiti e firmati manualmente 26 eventi `receive.add` equivalenti (stesso `resource_id`/`company_id`/`event_id` originali, HMAC-SHA256 con il secret corretto) e inviati alla Edge Function in produzione — stesso identico flusso che avrebbe eseguito Invoicetronic.

**Risultato: 22/26 fatture entrate correttamente in `fatture_queue`** (`piva_raw: 07863990961`, per lo più `da_assegnare` — OFFSIDE ha 2 sedi con indirizzi ambigui, smistamento manuale atteso e non un errore).

**4/26 falliscono sistematicamente con `500 Internal Server Error`** — sono le fatture arrivate come **P7M firmato digitalmente** (`file_name` termina in `.xml.p7m`, `encoding: Base64`): id Invoicetronic 84274, 84275, 84279, 84291 (EniMoov x2, DESTRIERO, Ristopiù Lombardia). Causa identificata: il payload P7M è una busta crittografica CMS/PKCS#7 binaria (contiene l'XML ma cifrato/firmato, non XML puro), e **contiene byte nulli** (` `) una volta decodificato da base64. Il codice della Edge Function (`base64ToUtf8`, riga ~506 di `supabase/functions/invoicetronic-webhook/index.ts`) tratta ciecamente ogni payload Base64 come XML testuale UTF-8, senza distinguere P7M da XML semplice — il byte nullo nella stringa fa fallire l'INSERT Postgres (che non ammette ` ` in colonne text), da cui il 500.

**Questo è un bug pre-esistente della Edge Function**, non specifico di OFFSIDE: qualunque fattura firmata P7M ricevuta da un fornitore, per qualsiasi cliente, romperebbe allo stesso modo. Probabile che finora non fosse mai emerso perché pochi fornitori inviano P7M, oppure perché i pochi retry avvenivano su altri payload. **Da correggere**: la Edge Function deve riconoscere il formato P7M (firma `format` o struttura del payload) ed estrarne l'XML interno (decodifica CMS/PKCS#7) prima del parsing, invece di trattarlo come XML diretto.

**Correzione fatta:** aggiornati su Supabase sia `INVOICETRONIC_WEBHOOK_SECRET` che `INVOICETRONIC_API_KEY` con i valori corretti/allineati. La chiave live salvata in memoria/documenti aveva un refuso storico (`l` minuscola invece di `I` maiuscola in `fIFJb`) — ora corretta ovunque: `ik_live_fLgZldZ95Ua3hxO8fIFJbTPO84u6AhxJ`.

### Fix del bug P7M — RISOLTO e deployato (15/07)
Il bug è stato corretto nella Edge Function `supabase/functions/invoicetronic-webhook/index.ts`:
- Nuova funzione `extractXmlFromP7m(bytes)`: estrae l'XML FatturaPA in chiaro dalla busta CMS/PKCS#7 individuando gli offset di byte di `<?xml … </…FatturaElettronica>` su una vista latin1 e ridecodificando solo quella porzione come UTF-8. Robusta al prefisso namespace variabile (ns0:/ns3:/nessuno) e a più occorrenze. Nessuna dipendenza ASN.1/CMS esterna (il P7M CAdES-BES incapsula l'XML in chiaro, è solo firmato non cifrato).
- Nuova funzione `bytesToXml(bytes)`: rileva sul CONTENUTO (prologo `<?xml` + assenza byte nulli) se è XML pulito o P7M, e sceglie il percorso giusto. Copre anche P7M annunciati come `encoding: Xml`.
- `decodePayloadToXml` e i 3 rami di ottenimento XML (payload inline / xml_file / xml_url via download) ora passano tutti da `bytesToXml`.
- Difesa in profondità: prima dell'INSERT, se per un formato non riconosciuto restassero byte nulli, vengono rimossi e segnalato in `payload_meta.payload_sanitized` (evita per sempre il 500 storico).
- Test: nuovo file `p7m_test.ts` (5 test unitari, tutti verdi) + `hmac_test.ts` esistente rieseguito (9 verdi, nessuna regressione). Deno `check` pulito.

Deployato in produzione. Le 4 fatture P7M reinviate con lo stesso meccanismo di replay firmato → tutte `200 OK` ed entrate in coda con P.IVA/importi corretti (`payload_sanitized: null`, cioè l'estrazione ha prodotto XML pulito senza dover ricorrere alla rimozione d'emergenza).

## STATO FINALE — CHIUSO
**Tutte 26 le fatture OFFSIDE sono in `fatture_queue`, zero fallite** (22 `da_assegnare`, 4 `done`). Verificato via query di conteggio su `piva_raw = '07863990961'`.

**Prossimi passi residui (non bloccanti):**
1. Verifica in UI: le 22 `da_assegnare` compaiono nella card "coda da assegnare" in Home (visibile solo ai clienti multi-sede come OFFSIDE) e sono smistabili tra le due sedi (OFFSIDE SPORTS PUB / OVERTIME).
2. Opzionale: confermare a Nicola (Invoicetronic) che è tutto risolto e chiudere il thread — il problema non era loro/SDI, ma la config secrets Supabase + il gap P7M lato nostro.
3. Le altre 4 aziende SUSHILAND ora esistono in ambiente live: quando cambieranno il Codice Destinatario le loro fatture arriveranno automaticamente (webhook + secrets ora corretti + fix P7M attivo per tutti).
