# Ciclo di vita delle colonne — lente L5 — 15/09/2026

Inventario **riproducibile** di chi scrive e chi legge ognuna delle colonne del DB:
`python scripts/audit_ciclo_vita_colonne.py --stat docs/storico/audit-2026-09/L5_stat_colonne_2026-09-15.csv`.
Le cifre di questo file vengono dal JSON prodotto dallo script quel giorno, non sono
trascritte a mano; i **verdetti** (la colonna a destra delle tabelle) sono letture del
codice al call site, una per una. Il CSV accanto e' la fotografia dei dati live
(righe, non-NULL, distinti per ogni colonna), prodotta con la query nel docstring dello script.

## Perimetro misurato

| Cosa | Misura |
|---|---|
| Tabelle `BASE TABLE` in `public` | 59 |
| Colonne | 667 (336 nomi distinti) |
| File letti | 540 di codice (py/ts/tsx) + 10 Edge Function + 149 SQL, in 16.5 s |
| Tabelle vuote | 10 (80 colonne che i dati non possono giudicare) |
| Colonne NULL al 100% in tabelle con righe | **47** (il bacino della classe grave) |
| Colonne costanti (1 valore distinto, mai NULL) | 82 |
| Scritture opache (`insert(variabile)`) non attribuibili a una tabella | 52 |
| Drift snapshot/dati al rilancio | nessuno — le 4 colonne che lo snapshot dell'08/09 non aveva (`fatture.oscurata`, `fatture.oscurata_at`, `ristoranti.tipo_attivita`, `users.vista_fatture`) sono state aggiunte a mano il 15/09/2026 |

Taratura (casi di esito noto, `--taratura`): le due colonne morte di L4 a 0, le quattro vive
a 4/12/16/37 file, `idempotency_key` viva solo in SQL, `ack` non gonfiata da «fallback»,
`bypass_guardia_piva` letta in `fastapi_worker.py`. Se non torna, e' rotto il rilevatore.

## Esito per classe

| Esito del rilevatore | Colonne | Cosa vuol dire |
|---|---|---|
| viva | 584 | letta e scritta (o scritta di fatto: ha valori a DB) |
| mai nominata | 15 | 0 riferimenti nel codice, nelle Edge Function e negli usi SQL |
| letta, scrittura incerta | 44 | letta; nessuna scrittura attribuita, ma la tabella ha scritture opache o e' vuota/NULL: esaminate a mano sotto |
| letta e mai scritta | 6 | letta; nessuna scrittura da nessuna parte e i dati non smentiscono |
| scritta e mai letta | 18 | ha uno scrittore e nessun lettore: lavoro sprecato a ogni riga |

## La classe grave, cercata esplicitamente: letta e mai scritta

Metodo: per ogni colonna le occorrenze in **lettura** (select, filtri, `row["col"]`,
`obj.col`) sono separate da quelle in **scrittura** (chiavi di insert/update/upsert,
`INSERT INTO`, `UPDATE SET`, `NEW.col` nei trigger, default); poi ogni colonna letta senza
scrittore e' incrociata coi dati. Le **47** colonne NULL al 100% su tabelle con righe
sono state lette una per una al call site. Le 6 «lette e mai scritte» del rilevatore sono 5
colonne di tabelle vuote (i dati non possono giudicarle) piu' `fornitore_norm` (morta): le
quattro vere stavano fra le 44 «incerte», dove la tabella ha scritture opache. Verdetto:

- **4 colonne lette e mai scritte** per costruzione, nessuna delle quali produce un numero sbagliato in pagina:
  - `custom_tag_prodotti.fattore_kg`: letta da tag_analytics (conversione in kg) e dall'API; l'unico scrittore riceve dal frontend un `fattore_kg: null` cablato (analisi-e-tag-client.tsx): la conversione per unita' a pezzo non puo' mai attivarsi. NULL su 170/170
  - `gruppo_tag_prodotti.fattore_kg`: stesso caso sulla catena (gruppo.py, lib/gruppo.ts): NULL su 78/78
  - `users.session_token`: letta dal ramo legacy di auth_service (sessioni pre multi-token), 0 token residui: il ramo e' morto nei dati
  - `users.session_token_created_at`: con session_token
- Tutte le altre NULL al 100% hanno uno scrittore vero nel codice e sono NULL perche' **nessun cliente ha mai compilato il campo**, o perche' il dato non arriva dalla sorgente (XML senza termini, Invoicetronic senza `xml_url`), o sono lock transitori. Dettaglio nella tabella.
- `category_change_log.actor_*`: **non misurabile** oggi (0 eventi su `fatture` dal deploy dell'attribuzione), si rimisura al primo traffico.

### Le colonne NULL al 100% (tabelle con righe), una per una

| Colonna | Rilevatore | Dati | Verdetto |
|---|---|---|---|
| `ai_review_log.annullato_at` | viva | 0/51 non-NULL, 0 distinti | **mai usata** — l'endpoint admin di annullamento esiste, mai usato |
| `ai_review_log.annullato_da` | scritta mai letta | 0/51 non-NULL, 0 distinti | **mai usata** — idem |
| `ai_usage_events.source_file` | viva | 0/554 non-NULL, 0 distinti | **mai usata** — track_ai_usage riceve sempre None: il chiamante e' il percorso PDF dell'era Streamlit (invoice_service.py, st.session_state) |
| `category_change_log.actor_email` | viva | 0/4135 non-NULL, 0 distinti | **non misurabile** — il trigger li scrive dai GUC di sessione; 0 eventi su fatture dal deploy dell'8/9 (ultimo 03/09), e i 3 su prodotti_utente del 10/09 sono gli anonimi gia' corretti da L4. Si rimisura al primo traffico |
| `category_change_log.actor_user_id` | scritta mai letta | 0/4135 non-NULL, 0 distinti | **non misurabile** — con actor_email |
| `category_change_log.batch_id` | viva | 0/4135 non-NULL, 0 distinti | **non misurabile** — con actor_email |
| `classificazioni_manuali.user_id` | letta scrittura incerta | 0/4 non-NULL, 0 distinti | **decisione** — NULL su 4/4; l'unica lettura del codice e' un DELETE per user_id in svuota_cestino, che non matcha mai. Se la tabella torna scritta dall'app, serve: sta nella stessa decisione |
| `custom_tag_prodotti.fattore_kg` | letta scrittura incerta | 0/170 non-NULL, 0 distinti | **letta e mai scritta** — letta da tag_analytics (conversione in kg) e dall'API; l'unico scrittore riceve dal frontend un `fattore_kg: null` cablato (analisi-e-tag-client.tsx): la conversione per unita' a pezzo non puo' mai attivarsi. NULL su 170/170 |
| `custom_tag_suggestions.snooze_until` | viva | 0/62 non-NULL, 0 distinti | **mai usata** — snooze scritto da tag_suggestion_service, nessun cliente l'ha usato |
| `dipendenti.costo_orario_default` | letta scrittura incerta | 0/4 non-NULL, 0 distinti | **mai usata** — POST/PATCH dipendente lo scrivono; nessuno dei 4 dipendenti ha una tariffa |
| `fatture_documenti.giorni_termini_xml` | letta scrittura incerta | 0/3905 non-NULL, 0 distinti | **mai usata** — il parser lo valorizza solo se l'XML ha GiorniTerminiPagamento senza DataScadenzaPagamento: nei 1.348 documenti senza scadenza non c'era mai |
| `fatture_documenti.note_pagamento` | mai nominata | 0/3905 non-NULL, 0 distinti | **morta** — 0 riferimenti, 0 valori su 3.905 documenti |
| `fatture_documenti.scadenza_override` | letta scrittura incerta | 0/3905 non-NULL, 0 distinti | **mai usata** — set_scadenza_override lo scrive; nessun cliente ha mai forzato una scadenza |
| `fatture_queue.locked_at` | viva | 0/677 non-NULL, 0 distinti | **transitoria** — lock di claim_batch, azzerato a fine lavorazione: NULL a riposo e' lo stato atteso (4 righe pendenti mai prese) |
| `fatture_queue.locked_by` | viva | 0/677 non-NULL, 0 distinti | **transitoria** — con locked_at |
| `fatture_queue.xml_url` | letta scrittura incerta | 0/677 non-NULL, 0 distinti | **mai usata** — Invoicetronic manda sempre xml_file (base64), mai xml_url: il fallback di recupero del worker e dell'anteprima non e' mai esercitabile |
| `fornitori_pagamenti_config.fornitore_norm` | letta mai scritta | 0/11 non-NULL, 0 distinti | **morta** — 0 riferimenti nel codice; la nominano solo un indice UNIQUE inerte (i NULL sono distinti) e un CHECK. NULL su 11/11 |
| `fornitori_pagamenti_config.note` | viva | 0/11 non-NULL, 0 distinti | **mai usata** — campo libero mai compilato |
| `gruppo_tag_prodotti.fattore_kg` | letta scrittura incerta | 0/78 non-NULL, 0 distinti | **letta e mai scritta** — stesso caso sulla catena (gruppo.py, lib/gruppo.ts): NULL su 78/78 |
| `gruppo_tags.colore` | viva | 0/3 non-NULL, 0 distinti | **mai usata** — il frontend usa emoji |
| `inventario_voci.note` | viva | 0/6 non-NULL, 0 distinti | **mai usata** — campo libero mai compilato |
| `prodotti_master.categoria_suggerita` | viva | 0/2913 non-NULL, 0 distinti | **mai usata** — la preparazione dei suggerimenti AI (admin.py) non e' mai stata lanciata: NULL su 2.913 |
| `prodotti_master.descrizione_originale` | letta scrittura incerta | 0/2913 non-NULL, 0 distinti | **morta** — nominata solo nello snapshot, NULL su 2.913 righe |
| `prodotti_master.suggerimento_fonte` | viva | 0/2913 non-NULL, 0 distinti | **mai usata** — idem |
| `prodotti_master.suggerito_at` | viva | 0/2913 non-NULL, 0 distinti | **mai usata** — idem |
| `prodotti_master.ultimo_correttore` | mai nominata | 0/2913 non-NULL, 0 distinti | **morta** — confermata da L4 |
| `ricavi_email_queue.last_error` | viva | 0/100 non-NULL, 0 distinti | **transitoria** — coda email: 100 righe tutte processate senza errore |
| `ricavi_email_queue.locked_at` | viva | 0/100 non-NULL, 0 distinti | **transitoria** — idem |
| `ricavi_email_queue.locked_by` | viva | 0/100 non-NULL, 0 distinti | **transitoria** — idem |
| `ricavi_modalita_mensile.coperti` | letta scrittura incerta | 0/17 non-NULL, 0 distinti | **mai usata** — campo opzionale (migration 16/06); nessuna delle 17 righe mensili lo compila |
| `ricette.note` | letta scrittura incerta | 0/5 non-NULL, 0 distinti | **mai usata** — idem |
| `riparto_regole_fornitore.percentuali` | viva | 0/26 non-NULL, 0 distinti | **mai usata** — le 26 regole sono tutte dello stesso tipo e non usano percentuali |
| `system_maintenance_status.error_message` | letta scrittura incerta | 0/1 non-NULL, 0 distinti | **mai usata** — scritto solo se il job di purge fallisce: mai successo |
| `turni_personale.costo_orario` | letta scrittura incerta | 0/125 non-NULL, 0 distinti | **mai usata** — POST/PATCH turno lo scrivono; l'unica sede con turni (125, ago-set) non ha mai inserito tariffe: il costo del personale da turni e' 0 per lei |
| `turni_personale.costo_orario_extra` | letta scrittura incerta | 0/125 non-NULL, 0 distinti | **mai usata** — con costo_orario |
| `turni_personale.importo_a_carico` | viva | 0/125 non-NULL, 0 distinti | **mai usata** — assenze a carico mai registrate |
| `turni_personale.importo_extra` | letta scrittura incerta | 0/125 non-NULL, 0 distinti | **mai usata** — con costo_orario |
| `turni_personale.lordo_mensile` | letta scrittura incerta | 0/125 non-NULL, 0 distinti | **mai usata** — con costo_orario |
| `turni_personale.note` | letta scrittura incerta | 0/125 non-NULL, 0 distinti | **mai usata** — idem |
| `turni_personale.ore_dichiarate` | letta scrittura incerta | 0/125 non-NULL, 0 distinti | **mai usata** — con costo_orario |
| `upload_events.ack_at` | mai nominata | 0/6983 non-NULL, 0 distinti | **morta** — con ack |
| `upload_events.ack_by` | mai nominata | 0/6983 non-NULL, 0 distinti | **morta** — con ack |
| `users.note_admin` | mai nominata | 0/8 non-NULL, 0 distinti | **morta** — 0 riferimenti, 0 valori |
| `users.piano_inizio_at` | letta scrittura incerta | 0/8 non-NULL, 0 distinti | **mai usata** — PATCH admin cliente lo scrive, mai compilato: il piano vive sulla sede (ristoranti.piano_inizio_at, 4 valori) |
| `users.session_token` | viva | 0/8 non-NULL, 0 distinti | **letta e mai scritta** — letta dal ramo legacy di auth_service (sessioni pre multi-token), 0 token residui: il ramo e' morto nei dati |
| `users.session_token_created_at` | viva | 0/8 non-NULL, 0 distinti | **letta e mai scritta** — con session_token |
| `users.trial_activated_at` | viva | 0/8 non-NULL, 0 distinti | **mai usata** — trial mai attivato |

## Mai nominate: le candidate al drop

| Colonna | Rilevatore | Dati | Verdetto |
|---|---|---|---|
| `classificazioni_manuali.validato_da` | mai nominata | 4/4 non-NULL, 1 distinti | **decisione** — 0 riferimenti; ma la tabella (4 righe scritte a mano il 30/12/2025) e' letta da ai_service come memoria admin e dall'agente categorization-reviewer: si decide sulla tabella, non sulla colonna |
| `email_rate_log.oggetto_hash` | mai nominata | 0/0 non-NULL, 0 distinti | **decisione** — tabella senza nessuno scrittore nel codice (0 righe); ma il job GDPR purge_email_rate_log (worker/run.py) la presuppone: si toglie insieme al job e al suo test, o si collega chi doveva scriverla |
| `fatture.data_elaborazione` | mai nominata | 39646/39646 non-NULL, 3559 distinti | **morta** — default now() su 39.646 righe: doppione di created_at che nessuno legge |
| `fatture_documenti.note_pagamento` | mai nominata | 0/3905 non-NULL, 0 distinti | **morta** — 0 riferimenti, 0 valori su 3.905 documenti |
| `prodotti_master.correzioni_count` | mai nominata | 2913/2913 non-NULL, 1 distinti | **morta** — confermata da L4 |
| `prodotti_master.ultimo_correttore` | mai nominata | 0/2913 non-NULL, 0 distinti | **morta** — confermata da L4 |
| `review_confirmed.confirmed_at` | mai nominata | 131/131 non-NULL, 8 distinti | **agente** — tabella scritta solo dall'agente categorization-reviewer (131 righe, giu-lug) |
| `review_confirmed.confirmed_by` | mai nominata | 131/131 non-NULL, 1 distinti | **agente** — idem |
| `review_confirmed.is_correct` | mai nominata | 131/131 non-NULL, 1 distinti | **agente** — idem |
| `review_ignored.ignored_at` | mai nominata | 0/0 non-NULL, 0 distinti | **morta** — tabella vuota, 0 riferimenti |
| `review_ignored.ignored_by` | mai nominata | 0/0 non-NULL, 0 distinti | **morta** — idem |
| `upload_events.ack_at` | mai nominata | 0/6983 non-NULL, 0 distinti | **morta** — con ack |
| `upload_events.ack_by` | mai nominata | 0/6983 non-NULL, 0 distinti | **morta** — con ack |
| `users.dismissed_notification_ids` | mai nominata | 8/8 non-NULL, 3 distinti | **morta** — 8/8 valorizzata da un codice che non esiste piu' (Streamlit); oggi notification_inbox.dismissed_at |
| `users.note_admin` | mai nominata | 0/8 non-NULL, 0 distinti | **morta** — 0 riferimenti, 0 valori |
| `upload_events.ack` | viva | 6983/6983 non-NULL, 1 distinti | **morta** — sempre false su 6.983 righe; la nomina solo un indice. Vive needs_ack |
| `fornitori_pagamenti_config.fornitore_norm` | letta mai scritta | 0/11 non-NULL, 0 distinti | **morta** — 0 riferimenti nel codice; la nominano solo un indice UNIQUE inerte (i NULL sono distinti) e un CHECK. NULL su 11/11 |

## Scritte e mai lette

Nessuna e' un difetto: sono telemetria, provenienza e attribuzioni che il codice registra e
non rilegge. Costano una scrittura per riga; si tengono se servono a un'indagine, altrimenti no.

| Colonna | Rilevatore | Dati | Verdetto |
|---|---|---|---|
| `ai_review_log.annullato_da` | scritta mai letta | 0/51 non-NULL, 0 distinti | **mai usata** — idem |
| `app_settings.updated_by` | scritta mai letta | 1/1 non-NULL, 1 distinti | **scritta, mai riletta** — scritto dall'admin, mai mostrato |
| `brand_ambigui.prima_vista` | scritta mai letta | 0/0 non-NULL, 0 distinti | **mai usata** — con brand |
| `brand_ambigui.tasso_correzione` | scritta mai letta | 0/0 non-NULL, 0 distinti | **mai usata** — con brand |
| `category_change_log.actor_user_id` | scritta mai letta | 0/4135 non-NULL, 0 distinti | **non misurabile** — con actor_email |
| `custom_tag_suggestions.feedback_note` | scritta mai letta | 10/62 non-NULL, 2 distinti | **scritta, mai riletta** — feedback del cliente (10/62), mai riletto |
| `fatture.oscurata_at` | scritta mai letta | 1/39646 non-NULL, 1 distinti | **scritta, mai riletta** — 1 riga; si legge `oscurata`, non la data |
| `fatture.reviewed_by` | scritta mai letta | 821/39646 non-NULL, 11 distinti | **scritta, mai riletta** — attribuzione della revisione (821 righe), mai riletta |
| `fatture_queue.anteprima_at` | scritta mai letta | 383/677 non-NULL, 53 distinti | **scritta, mai riletta** — telemetria coda |
| `fatture_queue.indirizzo_raw` | scritta mai letta | 339/677 non-NULL, 39 distinti | **scritta, mai riletta** — telemetria coda |
| `review_confirmed.categoria_finale` | scritta mai letta | 131/131 non-NULL, 26 distinti | **agente** — idem |
| `ricavi_email_queue.imported_rows` | scritta mai letta | 100/100 non-NULL, 5 distinti | **scritta, mai riletta** — telemetria coda email |
| `ricavi_giornalieri.source_meta` | scritta mai letta | 1025/1108 non-NULL, 2 distinti | **scritta, mai riletta** — provenienza dell'import, mai riletta |
| `upload_events.error_stage` | scritta mai letta | 230/6983 non-NULL, 4 distinti | **scritta, mai riletta** — telemetria upload |
| `upload_events.file_type` | scritta mai letta | 6983/6983 non-NULL, 2 distinti | **scritta, mai riletta** — idem |
| `upload_events.rows_excluded` | scritta mai letta | 6983/6983 non-NULL, 1 distinti | **scritta, mai riletta** — costante 0 su 6.983: nessuno la valorizza davvero |
| `upload_events.rows_parsed` | scritta mai letta | 6983/6983 non-NULL, 91 distinti | **scritta, mai riletta** — idem |
| `users.password_changed_at` | scritta mai letta | 8/8 non-NULL, 8 distinti | **scritta, mai riletta** — scritta al cambio password, mai riletta |
| `fatture_queue.correlation_id` | viva | 81/677 non-NULL, 81 distinti | **scritta, mai riletta** — scritta dalla Edge Function (81/677), letta solo da un indice: tracciabilita' |

## Lette e mai scritte sulle tabelle vuote

| Colonna | Rilevatore | Dati | Verdetto |
|---|---|---|---|
| `email_rate_log.destinatario` | letta mai scritta | 0/0 non-NULL, 0 distinti | **decisione** — idem |
| `fornitori_pagamenti_config.fornitore_norm` | letta mai scritta | 0/11 non-NULL, 0 distinti | **morta** — 0 riferimenti nel codice; la nominano solo un indice UNIQUE inerte (i NULL sono distinti) e un CHECK. NULL su 11/11 |
| `memoria_ai_categorie.descrizione_normalizzata` | letta mai scritta | 0/0 non-NULL, 0 distinti | **morta** — tabella vuota, 0 riferimenti: la memoria vive in prodotti_utente/prodotti_master |
| `note_diario.testo` | letta mai scritta | 0/0 non-NULL, 0 distinti | **mai usata** — 0 note |
| `review_ignored.ignored_until` | letta mai scritta | 0/0 non-NULL, 0 distinti | **morta** — idem |
| `review_ignored.row_id` | letta mai scritta | 0/0 non-NULL, 0 distinti | **morta** — idem |

## Le tabelle

| Tabella | Righe | Stato | Perche' |
|---|---|---|---|
| `brand_ambigui` | 0 | **mai usata** | 0 righe, ma viva: ai_service.py la legge (cache memoria) e la scrive (upsert) alla correzione di un brand ambiguo — mai scattato |
| `memoria_ai_categorie` | 0 | **morta** | 0 righe, 0 riferimenti: la memoria vive in prodotti_utente/prodotti_master |
| `review_ignored` | 0 | **morta** | 0 righe, 0 riferimenti, nemmeno nell'agente |
| `email_rate_log` | 0 | **decisione** | 0 righe e nessuno scrittore nel codice; il job GDPR purge_email_rate_log del worker la presuppone |
| `classificazioni_manuali` | 4 | **dell'agente** | 4 righe scritte a mano il 30/12/2025; l'app non la scrive, l'agente categorization-reviewer la legge come priorita' globale |
| `review_confirmed` | 131 | **dell'agente** | 131 righe (giu-lug) scritte dall'agente categorization-reviewer |
| `ingredienti_utente` | 0 | **mai usata** | 0 righe, scrittori nel codice (ricette) |
| `ingredienti_workspace` | 0 | **mai usata** | idem |
| `marketplace_leads` | 0 | **mai usata** | 0 lead: nessun cliente ha mai chiesto un servizio |
| `note_diario` | 0 | **mai usata** | 0 note |
| `regole_turni_ricorrenti` | 0 | **mai usata** | 0 regole |
| `upload_locks` | 0 | **transitoria** | lock di upload: vuota a riposo |

## Servite dal worker, mai nominate dal frontend

67 colonne vive sono lette dal worker e non compaiono per nome in `apps/web/src`.
E' una lista **parziale per costruzione** (trappola 5: il frontend legge anche per nome dinamico
e riceve i payload in blocco) e in gran parte sono campi interni — hash, token, `xml_content`,
provenienze. Non e' una classe di difetto: e' l'elenco da cui partire se un giorno si vuole
snellire i payload. Lo stampa lo script, in coda.

## Limiti del perimetro

`tools/` (script manutentivi) non e' scandito: un grep a mano sulle colonne morte vi trova un solo
riferimento, `dismissed_notification_ids` in `tools/check_migrations.py`, che non cambia il verdetto.
Nell'SQL una colonna nominata in un `WHERE` conta come letta anche se e' un job di purge; e le
tabelle si attribuiscono solo dalle catene con il nome letterale (`.table("x")`): il resto e' opaco.
Il primo giro di questa lente ha dichiarato morte `brand_ambigui` ed `email_rate_log`: il
code-reviewer ha trovato lettori e scrittori con apici singoli e un job GDPR. Le tabelle che
sopra risultano «morte» sono state ricontrollate con entrambi gli apici e nelle funzioni SQL.

## Proposta per Mattia — niente e' stato cancellato

Far cadere una colonna e' irreversibile: qui c'e' la lista, la migration la decide lui.
`fornitore_norm` e' anche seminata da `tests/test_isolamento_per_risorsa.py`: il drop tocca quel seed.

**11 colonne morte** (0 lettori, 0 scrittori, nessun dato che serva):
- `fatture.data_elaborazione`
- `upload_events.ack`
- `upload_events.ack_at`
- `upload_events.ack_by`
- `users.note_admin`
- `users.dismissed_notification_ids`
- `fatture_documenti.note_pagamento`
- `prodotti_master.correzioni_count`
- `prodotti_master.ultimo_correttore`
- `prodotti_master.descrizione_originale`
- `fornitori_pagamenti_config.fornitore_norm`

**2 tabelle morte** (0 righe, 0 riferimenti nel codice e nelle funzioni SQL): `memoria_ai_categorie`, `review_ignored`.

**4 decisioni**, non drop:
- `email_rate_log`: nessuno la scrive, ma `purge_email_rate_log` (retention GDPR, `worker/run.py`) e il suo test la presuppongono. O si toglie tutto insieme, o si collega chi doveva scriverla.
- `fattore_kg` (due tabelle): o si aggiunge il campo nell'interfaccia dei tag, o si tolgono colonna e ramo di conversione. Oggi la conversione in kg per le unita' a pezzo e' promessa dal codice e impossibile per il cliente.
- `classificazioni_manuali` (con le sue colonne `validato_da` e `user_id`, morte nel codice) e `review_confirmed`: la prima e' letta da `ai_service.py` come memoria admin e scritta solo a mano, la seconda solo dall'agente `categorization-reviewer`. Restano tabelle dell'agente/admin o si portano nell'app?
- `users.session_token` + `session_token_created_at` e il ramo legacy in `auth_service.py`: 0 token residui, si puo' chiudere il ramo insieme alle colonne.

## Come si rilancia

```bash
python scripts/audit_ciclo_vita_colonne.py --taratura      # prima: i casi noti devono tornare
python scripts/audit_ciclo_vita_colonne.py --stat docs/storico/audit-2026-09/L5_stat_colonne_2026-09-15.csv
python scripts/audit_ciclo_vita_colonne.py --dove turni_personale.costo_orario   # i punti di lettura/scrittura
```

Il CSV va rigenerato sul DB live (query nel docstring dello script) quando si rilancia: e' la
fotografia di un giorno, non uno schema. Se `--taratura` fallisce, l'inventario non va creduto.
