# Mappa dei silenzi — cosa dice la produzione (14/09/2026)

> **A cosa serve.** Prima lente trasversale: invece di leggere il codice, si
> legge **cosa il sistema ha fatto davvero** — tabelle-telemetria, code, job,
> monitor, errori runtime, advisor — e per ogni cosa che gira si risponde a tre
> domande: *ultima evidenza?* *cosa produce quando fallisce?* *chi se ne
> accorgerebbe?* Ogni cifra è misurata il 14/09/2026 (07:50–08:40 UTC) in sola
> lettura dal DB live con lo script `scratchpad` della sessione; le fonti
> piattaforma (Vercel, log Supabase, advisor) sono del 13/09 via MCP.
> Ri-misurare, non ereditare.

## 1. Il battito: chi gira, chi tace

| Cosa | Ultima evidenza | Se fallisce | Chi se ne accorge | Verdetto |
|---|---|---|---|---|
| Backup DB (`db_backup.yml`) | 14/09 03:29, success | run rosso + Telegram/mail | Mattia | ✅ |
| Coda ricavi email (`ricavi_email_queue`) | 99/99 `done`, ultimo 14/09 03:03 | monitor orario | **il monitor taceva in ENTRAMBI i casi**: se la sua chiamata falliva (`STUCK=0` → «sana») e, trovato dal reviewer, anche a coda davvero bloccata (JSON dell'email rotto → Brevo 400 → run verde). Corretti tutti e due oggi | ⚠️⚠️→✅ |
| Incassi (`ricavi_giornalieri`) | 30 righe in 7 gg, ultimo giorno 13/09 | — | briefing «incasso mancante» (37 notifiche, 25 chiuse) | ✅ |
| Briefing giornaliero (`daily_briefing_state`) | generato 14/09; 6 in 7 gg | cache-first: testo vecchio | nessuno (vedi §3) | ✅ tecnico |
| Segnali di gruppo (`gruppo_segnali_state`) | 14/09 (OFFSIDE), 11/09 (SUSHILAND) | — | — | ✅ |
| Retention 2 anni (`system_maintenance_status`) | 13/09 15:47 `ok`, 0 righe | `status=error` in tabella | **nessun monitor la legge** | 🟡 |
| Cache versions (`cache_version`) | `fatture_documenti` 14/09 07:54 | — | — | ✅ |
| Sessioni / login | 18 attive, 7 login in 7 gg, 0 blocchi | rate limit fail-open (memoria) | — | ✅ |
| Worker `/health` (`keepalive`, `uptime`, `latency`) | ogni 5/15 min, success | Telegram/mail | Mattia | ✅ |
| Monitor Telegram (riparto, retail, eventi sconosciuti) | 14/09 06:57–07:05 | `totale=-1` → alert con -1 | Mattia (testo poco chiaro) | ✅ |
| Agente notturno (`app_settings.agent_notturno`) | **spento dal 30/05** | — | dichiarato nei verbali | ⏸ scelta |
| `ai_review_log` | ultima riga **15/06** (attore `auto-review`, scrittore non più nel codice) | — | nessuno | 💀 morta |
| Upload manuali (`upload_events`) | ultimo 12/09; **0 FAILED negli ultimi 30 gg** (gli 117 del campione erano feb–giu) | riga `FAILED` + `error_stage` | il cliente a schermo | ✅ |
| SDI Invoicetronic (`fatture_queue`) | vedi §2 | `da_assegnare` | **nessuno** | 🔴 |

## 2. I due silenzi veri

### 2a. Sei sedi «SDI attivo dal 23/06», eventi reali per una P.IVA sola

`ristoranti.sdi_attivo = true` (dal 23/06) su **6 sedi**: LAND DEI SAPORI,
OVERTIME, OFFSIDE, SUSHILAND ×3. In `fatture_queue` (674 righe dal 30/03,
nessuna cancellata: i mesi vuoti sono maggio e giugno) le P.IVA con eventi
`invoicetronic` sono **tre**: `07863990961` (OFFSIDE/OVERTIME, vivo fino al
13/09), `10865360969` (LAND, **ultimo 13/04**, cioè prima del flag) e
`13584150968` (CASATI, ultimo 03/04, flag `false`). Le tre P.IVA SUSHILAND
**non compaiono mai**. Quindi **4 sedi su 6 col flag acceso non hanno ricevuto
un solo evento SDI in 83 giorni**, e le loro fatture entrano solo a mano
(LAND e VILLA GUARDIA: ultimo caricamento 27/08; MARIANO e SAN GIULIANO:
21/07, ultima data documento 30/06). Nessun controllo confronta il flag con
gli eventi **in modo attivo**: il confronto esiste nel briefing di sede
(`fastapi_worker.py` ≈6211, topic `fatture_mancanti`, canale `sdi` dal flag),
ma per gli account di catena il briefing di sede non viene generato (vedi §3:
fermo al 28/08, 10/08, 07/08), quindi non ha mai potuto scattare per queste
4 sedi. Se è una configurazione Invoicetronic mai completata, il flag mente;
se è configurata, il canale è muto: in entrambi i casi oggi lo dice solo
questa misura. **Decisione di Mattia** (verifica sul pannello Invoicetronic,
`invoicetronic-readiness`); proposta tecnica in §4.

> **Risposta di Mattia (14/09/2026):** il flag mente perché **SDI non è ancora
> stato collegato** per quelle sedi; lo farà a breve. Quindi non è un difetto
> da correggere: `sdi_attivo = true` è stato acceso in anticipo sulla
> configurazione. Resta valida la proposta di §4 (un controllo che confronti
> flag ed eventi), che diventerà utile **quando** il collegamento sarà fatto —
> se dopo l'attivazione le sedi restassero mute, oggi nessuno se ne
> accorgerebbe.

### 2b. OFFSIDE: 20 fatture SDI in attesa da 11 giorni, e nessuno lo dice

Le tre sedi del gruppo OFFSIDE hanno **la stessa P.IVA e lo stesso
indirizzo** (Via Montalbino 4, Milano): l'indirizzo arriva (sta in
`payload_meta.indirizzo_destinatario`), ma non può discriminare. La Edge
Function usa lo storico fornitore→sede (`fallback_tried`) e mette la riga in
`da_assegnare` se `best_score < 0,40` **o** `gap < 0,20` — corretto: mai
assegnare a caso. Sulle 20 di oggi decide **solo il gap** (0,036 su 17, 0,015
su 3): 17 hanno `best_score` esattamente 0,40. Abbassare la soglia dello score
non cambierebbe nulla; conta il distacco fra le due sedi migliori. Da luglio il **75–90 % delle righe è `mode: manual`**
(W29: 22 su 26); fino a fine agosto venivano tutte chiuse (dal cliente nella
coda su `/catena`, o dall'admin) con **mediana 64 ore, p90 14 giorni, massimo
23 giorni** dalla ricezione. Dal 31/08 non le chiude più nessuno: **20 in
`da_assegnare`** (6 in W36, 14 in W37), la più vecchia del 03/09, mentre il
cliente ha aperto l'app il 09/09 e il 14/09. Il fornitore più frequente
(`08973230967`, 8 delle 20) ha uno storico 9 «Costi comuni» / 2 OFFSIDE:
ambiguo per costruzione. Per il cliente quelle fatture **non esistono in
nessun numero** finché non sceglie. Chi lo dice: la coda stessa su `/catena`
(badge ambra) e la pagina admin *Flusso dati* («N da smistare»,
`flusso-dati-client.tsx:363`). Chi NON lo dice: il briefing, le notifiche e i
monitor cron (grep `da_assegnare` in `daily_briefing_service.py`,
`notification_inbox_service.py`, `.github/workflows/`: 0 — file letti, non
vuoti). Manca un avviso **attivo**, non il dato. **Decisione di Mattia**:
briefing/notifica oltre N giorni, e/o alert admin.

> **Risposta di Mattia (14/09/2026):** lo smistamento **è del cliente** — la
> coda su `/catena` e il badge ambra sono il canale previsto, e va bene così.
> Nessun avviso attivo da costruire ora. La misura resta a verbale come
> baseline: fino al 31/08 le righe venivano chiuse (mediana 64 h, p90 14 gg),
> dal 31/08 no. Si riapre solo se l'arretrato cresce ancora senza che il
> cliente lo smaltisca.

## 3. Cosa dice sul prodotto (non sono bug)

- **Chi usa l'app** (`users.last_seen_at`): OFFSIDE 14/09, CASATI 13/09,
  SUSHILAND/LAND 12/09, TIME CAFE 01/09, **IL BARETTINO 16/07** (il giorno
  dell'onboarding, mai più). Il briefing per sede delle 4 sedi SUSHILAND/LAND
  è fermo al **28/08, 10/08, 07/08**: l'account di catena entra su `/catena` e
  il briefing del punto vendita non viene generato — l'avviso «costo personale
  mancante» che il verbale del 07/09 dava per «già in produzione» non viene
  letto da quelle sedi.
- **Ore di generazione del briefing**: distribuite dalle 05 alle 19 UTC (48
  righe): conferma che si genera all'apertura, non di notte.
- **Notifiche** (`notification_inbox`, 73 righe): vive solo `incasso_mancante`
  (37) e `scadenza_superata` (7, dal fix del 03/09); i topic `price_alert`,
  `credit_note`, `quality_check_failed`, `scadenza_imminente`,
  `fatturato_mancante`, `costo_personale_mancante` **fermi al 01–05/06**.

## 4. Errori reali e advisor (13/09, MCP)

- **Vercel, 7 gg**: `[gruppo.overview] worker error 400` e `[gruppo.chatConfig]
  400/500` su `/catena` (2 utenti, 8 volte dal 18/06): il 400 è «Account non
  multi-sede», raggiungibile da `upload-modal.tsx:364` (link fisso) e dal
  redirect di login. `[home.config] worker error 401` su `/m` (6 utenti, 6
  volte): sessione scaduta sulla PWA, il layout poi rimanda al login. Rumore,
  non perdita.
- **Supabase log, 24 h**: 16.274 POST 200, **4 POST 504**, 5 POST 404, 2
  `ERROR "array_agg" is an aggregate function` (SQL applicato via MCP da una
  sessione, non dall'app).
- **Advisor**: 4 funzioni-soldi con `search_path` mutabile
  (`costi_automatici_mensili`, `_gruppo`, `articoli_da_fatture`,
  `_riparto_categoria_is_fb`), 40 indici mai usati, 3 FK senza indice
  (`fatture_queue.ristorante_id`, `turni_personale.dipendente_id`,
  `regole_turni_ricorrenti.dipendente_id`).

## 5. Materiale per le lenti successive

- **L5 (colonne)**: `fatture.stato` sempre `''`; `upload_events.ack_at` e
  `prodotti_master.suggerito_at` mai valorizzate; `fatture_queue.indirizzo_raw`
  scritta solo dal percorso worker (vuota su tutte le `da_assegnare`);
  `upload_events.status='SAVED_PARTIAL'` prodotto ancora dal codice ma 0 righe
  da giugno; tabelle a 0 righe: `brand_ambigui`, `email_rate_log`,
  `upload_locks`, `memoria_ai_categorie`, `review_ignored`,
  `regole_turni_ricorrenti`, `ingredienti_utente`, `ingredienti_workspace`,
  `note_diario`, `marketplace_leads`.
- **L6 (tempo)**: 11 sessioni su 18 attive create fra giugno e agosto, non
  revocate: la scadenza a 30 giorni è calcolata alla lettura, mai provata.
- **Proposta tecnica (non fatta, Fase 1 è di sola lettura)**: un cron
  «silenzi» che confronti `sdi_attivo` con l'ultimo evento per P.IVA e conti le
  `da_assegnare` più vecchie di 3 giorni, con alert; e la lettura di
  `system_maintenance_status.status='error'`.
