# Prompt per la sessione — Fase 6: tempo, concorrenza, dipendenze che cadono

> **Come si usa.** Imposta **Fable** e scrivi **`ultrathink`** nel messaggio di
> apertura (vedi §«Modello e sforzo»: qui il rischio è scegliere male i casi,
> non contare male). Apri una sessione nuova e incolla la sezione «PROMPT». Il
> resto del file è contesto che la sessione leggerà da sola.

> **Archiviato il 15/09/2026 a lente chiusa.** Due misure di questo prompt erano
> sbagliate e la sessione le ha corrette prima di usarle: le «8 letture dell'ora
> senza fuso» erano **6** nel codice (due erano commenti che nominavano
> `date.today()`), e le «8 chiamate HTTP su 11 senza timeout» erano **0** — il grep
> guardava la riga della chiamata e il `timeout=` stava tre righe sotto. Il difetto
> di timeout vero stava nei **client OpenAI** (3 su 4 col default del SDK, 600 s).
> Esito in `AUDIT_ONEFLUX_STATO_2026-09_STORICO.md` §15/09 L6.

---

## PROMPT (copia da qui)

Apri la **Fase 6 della sessione trasversale di audit: L6 — tempo, concorrenza,
dipendenze che cadono**. È la sesta delle nove lenti trasversali; L1, L3, L2, L4
sono chiuse il 14/09/2026 e L5 il 15/09/2026. `ultrathink`.

Leggi prima, in quest'ordine:
1. `DOCUMENTAZIONE/AUDIT_COPERTURA.md` → sezione «Lenti trasversali»
2. `WORKFLOW.md` §6 → come si conduce un audit **e la regola sul costo**
3. `docs/piani/PROMPT_FASE6_TEMPO_CONCORRENZA_DIPENDENZE.md` → perimetro **già
   misurato**, i presidi che esistono già, e le trappole già pagate

**Il problema in una riga:** ogni lente finora ha guardato l'app **da ferma**.
Questa la guarda **mentre succede qualcosa che il codice non ha scelto**: è
mezzanotte a Roma ma le 22 sul server, due copie del worker prendono lo stesso
lotto durante un deploy, OpenAI risponde 429 alla terza chiamata su dieci, una
`requests.post` senza timeout aspetta per sempre dentro il ciclo del worker.
Nessun test verde di oggi prova questi momenti: i presidi sul tempo sono **3
file** su 14.000 test, e il retry vero di `tenacity` è provato su una funzione
sintetica, non sul call site che parla con OpenAI.

**Il lavoro di scoperta è già fatto: parti da qui, non da zero.** Misurato il
15/09/2026 (ri-misura, non ereditare): ~~8~~ **6 letture dell'ora senza fuso** in 6
file su un server che vive in UTC, ~~8 chiamate HTTP su 11 senza timeout~~ (erano 0: ma 3 client OpenAI su 4 col timeout di default, 600 s), **3
`FOR UPDATE` senza `SKIP LOCKED`**, **4 call site OpenAI** di cui uno solo sotto
`@retry`. Sono candidati, non verdetti.

**Il metro è l'esecuzione, non la lettura.** Ogni caso si prova **facendolo
succedere**: l'ora si congela (fusi estremi, non «ora locale»), i due worker si
lanciano davvero su un Postgres vero (`-m sql`, `claim_batch_for_processing`
esiste già con 10 presidi), il 429 si solleva a metà lotto con la classe vera di
`openai` **sul call site vero**, non su una funzione di prova. Un caso ragionato
e non eseguito non chiude niente.

**Vincolo di costo, non negoziabile.** Rilevatori e misure si fanno **in
sessione**: niente workflow multi-agente. L'unico sub-agente è il
`code-reviewer` a fine fase (`WORKFLOW.md` §6).

**Non riscrivere i retry.** Un timeout aggiunto o un retry rimontato è un fix con
mutante sul call site; una nuova politica di retry è una feature e va pianificata
a parte (`WORKFLOW.md` §6: i buchi trovati in audit non si chiudono in coda).

**Non pushare.** Si lavora su `main` locale; misura tu la coda all'apertura e
dichiarala (il 15/09 sera erano 16 commit).

Apri con `/apertura-sessione`, dichiara il perimetro che hai **misurato tu**, e
parti.

## (fine prompt)

---

## Modello e sforzo

`AUDIT_COPERTURA.md` raccomanda **Fable `ultrathink` sui casi**, e la
raccomandazione regge. A differenza di L5 (dove il metro era ovvio e il rischio
era credere al grep), qui **il lavoro è scegliere i casi**: quali momenti far
succedere, in quale ordine, con quale osservabile. Sbagliare un caso non dà un
test rosso che lo dice — dà un test verde su un momento che non capita mai.

| Parte della fase | Modello | Sforzo |
|---|---|---|
| Scelta dei casi per le tre famiglie (tempo / concorrenza / dipendenze) | **Fable** | `ultrathink` — apre una dimensione nuova, e un caso sbagliato è invisibile |
| Esecuzione: congelare l'ora, lanciare i due worker, sollevare il 429 | **Fable** | normale (stessa sessione: non si cambia a metà) |
| Fix di un difetto trovato (timeout mancante, retry inerte, ora senza fuso) | **Fable** | `ultrathink` se tocca coda fatture, margini o auth |

---

## Perimetro — misurato il 15/09/2026 (RI-MISURARE, non ereditare)

### Tempo

| Cosa | Misura |
|---|---|
| `datetime.now(` in `services utils config worker` | 102 occorrenze, 21 file |
| di cui **senza fuso** (`datetime.now()`, `utcnow()`, `date.today()`) | ~~8~~ **6 nel codice** (le 2 di `fastapi_worker.py` erano commenti): `upload_policy.py` ×2, `routers/admin.py`, `price_impact_service.py`, `db_service.py`, `daily_briefing_service.py` |
| `Europe/Rome` esplicito | 30 occorrenze in 6 file (13 in `fastapi_worker.py`, 10 in `routers/gruppo.py`) |
| `new Date(` nel frontend | 171 (34 file in `app/(app)`, 5 in `app/(mobile)`, 4 in `lib/`); **0** `timeZone`/`Europe/Rome` in TypeScript |
| `now()` nelle funzioni SQL dello snapshot | 142 (`claim_*`, `release_stale_locks`, `schedule_retry`, `riparto_quote_mensili`…); 1 `CURRENT_DATE` (finestra `p_giorni`) |
| Cron GitHub | 8 workflow, tutti in UTC (`db_backup` 03:11, i check del mattino 06:30–06:45) |
| Test che congelano l'ora | **3** file (`test_pagata_at_fuso_italiano`, `test_notification_inbox_service`, `test_trial`) |
| Test sui fusi estremi | 4 file, tutti frontend (`catena_confronti`, `margini_aggregati`, `margini_periodi`, `scadenziario_kpi`) |

Il server Railway e Vercel vivono in **UTC**; il cliente a Roma. Fra le 22:00 e
mezzanotte (ora legale) «oggi» differisce fra il server e il cliente: ogni
`date.today()` senza fuso è un candidato, e ogni `new Date()` del browser
confrontato con una data del server è l'altro lato dello stesso caso.

### Concorrenza

| Cosa | Misura |
|---|---|
| Processi in produzione | `worker` (FastAPI, `WORKER_WEB_CONCURRENCY=4`: **4 processi**, ognuno con le proprie cache in memoria) + `queue-worker` (**1** processo, `python worker/run.py`, poll 15 s) |
| RPC con `FOR UPDATE SKIP LOCKED` | 2: `claim_batch_for_processing`, `claim_ricavi_email_batch` |
| `FOR UPDATE` **senza** `SKIP LOCKED` | 3: `assegna_fattura_a_sede`, `assegna_fattura_a_sede_tecnica`, `schedule_retry` |
| Lock scaduti | `release_stale_locks(p_timeout_minutes DEFAULT 10)`, indice parziale su `processing` |
| Presidi esistenti su `claim_batch_for_processing` | **10** in `tests/test_sql_funzioni_soldi.py` (fra cui «non ruba il lavoro di un altro worker», «recupera i lock scaduti») — **tutti con un worker alla volta**: nessuno lancia due `claim` concorrenti |
| Stati di `fatture_queue` | `pending / processing / done / failed / dead / unknown_tenant / da_assegnare / scartata` |

Il «secondo worker» non è teoria: **a ogni deploy Railway** il container vecchio e
quello nuovo convivono per una finestra, e ogni riavvio dopo crash lascia i
`processing` del morto fino al timeout dei 10 minuti. Il caso da eseguire è
**due `claim` nella stessa transazione-finestra** su un Postgres vero, e un
`processing` orfano con `locked_at` a 9 e a 11 minuti.

### Dipendenze che cadono

| Cosa | Misura |
|---|---|
| Call site OpenAI (`chat.completions.create`) | **4**: `ai_service.py:5481` (sotto `@retry` tenacity, stop a 3 tentativi o deadline), `fastapi_worker.py:4121`, `invoice_service.py:1568`, `daily_briefing_service.py:1353` |
| `@retry` di tenacity | **1** (`ai_service.py:5393`); retry fatti in casa: 43 righe in 11 file (`queue_processor.py` con budget AI e backoff troncato) |
| Righe che nominano `RateLimitError` / 429 | 18 in 3 file (`ai_service`, `fastapi_worker`, `worker_client`) |
| Chiamate HTTP `requests`/`httpx` | **11**, ~~8 senza timeout~~ **tutte col timeout** (chiamate multi-riga: il kwarg non era sulla riga del grep). Senza timeout erano i **client OpenAI**: 3 su 4 |
| Host esterni chiamati | OpenAI, Invoicetronic (4 siti), Telegram (5), Brevo (3), Supabase (sempre) |
| Client Supabase | `create_client(` in 5 file; `ConnectionTerminated` già visto in produzione (chi crea client nel loop caldo) |
| Test esistenti su retry/429 | `test_ai_deadline_retry.py` (livello 1: stop/wait **veri** di tenacity, ma su una funzione sintetica che solleva `ValueError`), `test_aiservice.py`, `test_ai_service_troncamento.py`. Dal 28/8/2026 il conftest mocka **solo streamlit**: `tenacity` e `openai` sono veri (`test_conftest_mocka_solo_streamlit` lo presidia) |

## Le tre famiglie di casi da far succedere

1. **Tempo.** Congelare l'ora a `23:30 Europe/Rome` (= 21:30 UTC) e a `00:30`
   il primo del mese, sui percorsi che decidono «oggi»: briefing giornaliero,
   scadenziario, trial, `pagata_at`, finestra `p_giorni` in SQL, cron delle
   06:30 che leggono «ieri». Osservabile: la data che il cliente vede, non il
   valore interno.
2. **Concorrenza.** Due `claim_batch_for_processing` concorrenti su Postgres
   vero (due connessioni, `BEGIN` aperto sulla prima) → nessuna riga in entrambi
   i lotti. Un `processing` con `locked_at` a 11 minuti e il worker vivo → chi
   vince. Le 3 RPC `FOR UPDATE` senza `SKIP LOCKED`: il secondo chiamante
   **aspetta** o **fallisce**? E l'API con 4 processi: una cache invalidata in
   uno resta viva negli altri 3 (questo è materia di L8, ma va **misurato** qui
   una volta per dire quanto vale).
3. **Dipendenze.** `openai.RateLimitError` vera alla chiamata 3 di 10, sollevata
   dal client mockato **sotto** `_chiama_gpt_classificazione` (così il `@retry`
   vero la vede): il lotto finisce `Da Classificare` o `dead`? Timeout che scade in
   `worker_client` dentro il ciclo del worker: il ciclo prosegue o si blocca
   fino al `release_stale_locks`? Telegram giù: l'alert che non parte fa
   fallire l'operazione che lo mandava?

## Trappole già pagate — non ripagarle

1. **«tenacity è mockato nel conftest» è una premessa scaduta.** Lo era fino al
   28/8/2026; la riga L6 scritta il 14/09 («con tenacity smontato») e una memoria
   la ripetevano ancora il 15/09. Oggi il conftest mocka **solo streamlit**: il
   `@retry` che decora `_chiama_gpt_classificazione` è quello vero, e un 429 si
   prova sollevando `openai.RateLimitError` dal client mockato sotto di lui —
   senza rimontare niente. Verifica la premessa nel docstring di
   `tests/conftest.py` prima di costruirci sopra.
2. **Un test sul fuso passa o fallisce secondo l'ora in cui lo lanci**: si
   usano fusi estremi (`Pacific/Kiritimati`, `Etc/GMT+12`), non «Roma vs UTC» a
   mezzogiorno. E «stesso risultato in due fusi» vale solo per grandezze
   indipendenti da oggi. Memorie: `test-sul-fuso-dipende-dall-ora`,
   `confronto-fra-fusi-solo-su-dati-assoluti`.
3. **Un `def` inserito fra decoratore e funzione lascia la chiamata senza
   retry**: è già successo alla chiamata GPT, e lo ha visto solo un test su
   `__wrapped__`. Prima di dire «è sotto retry» verifica che il decoratore
   decori **quella** funzione.
4. **`ConnectionTerminated` non accusa il pool ma chi crea client nel loop
   caldo**: `last_stream_id` fisso. Non «aggiungere un retry» senza aver contato
   i `create_client`.
5. **Il rate limit del login è fail-open**: su errore ritorna `(False, 0)`. Il
   caso «Supabase lento durante un brute force» va eseguito, non dedotto.
6. **`pgrep -f` matcha se stesso** dentro il tool Bash: per sapere se il secondo
   worker è vivo si guarda il DB (`locked_by`), non la lista processi.
7. **`-k` con spazi seleziona zero test**: un giro di mutazione vale solo se
   N test > 0. Un mutante va applicato **nella funzione giusta** (lo stesso
   pattern sta in più funzioni) e verificato con un diff.
8. **`FOR UPDATE` senza `SKIP LOCKED` in una RPC chiamata dall'API** fa aspettare
   il secondo chiamante fino al commit del primo: con PostgREST il timeout è del
   client, e il cliente vede un 5xx senza log. Non è un bug **finché non lo
   misuri** con due connessioni.

## La classe che il conteggio NON trova, ed è la più grave

Contare `now()` e `timeout=` trova ciò che il codice **nomina**. Non trova
l'ordine sbagliato di due operazioni corrette: il `mark_queue_item_done` che
arriva **prima** del salvataggio delle righe se il salvataggio va in retry; il
`purge` GDPR che gira alle 03:11 UTC mentre il worker sta ancora processando il
lotto delle 03:10; la cache del briefing (`_BRIEFING_CODE_VERSION`, TTL 30')
scaldata dal processo 1 e servita stantia dal processo 3. Questi si trovano
**scrivendo la sequenza** e eseguendola, non leggendo i file.

## Criteri di chiusura (WORKFLOW §5)

- [ ] Per ogni famiglia (tempo / concorrenza / dipendenze) almeno un caso
      **eseguito**, con l'osservabile che il cliente vedrebbe
- [ ] Le 8 letture dell'ora senza fuso classificate una per una: innocua
      (log, durata) / difetto (decide una data che il cliente vede)
- [ ] Le 8 chiamate HTTP senza timeout classificate: in un ciclo del worker o
      in una richiesta API → difetto; in uno script a mano → dichiarato
- [ ] Due `claim` concorrenti provati su Postgres vero (`-m sql`); le 3 RPC
      `FOR UPDATE` senza `SKIP LOCKED` provate con due connessioni
- [ ] Un `RateLimitError` vero a metà lotto attraverso il `@retry` vero del
      call site, esito registrato
- [ ] Ogni difetto vero corretto con mutante sul **call site**; ogni presidio
      nuovo ucciso dal suo mutante
- [ ] I presidi nuovi sono **eseguibili in CI** (freeze dell'ora, non
      `sleep`; Postgres embedded per la concorrenza)
- [ ] `python -m pytest tests/ -q` e `python -m pytest -q -m sql` verdi
- [ ] `python scripts/check_documentazione.py` pulito
- [ ] Verbale (≤ 40 righe) in
      `docs/storico/audit-2026-09/AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`
- [ ] Riga **L6** in «Lenti trasversali» di `DOCUMENTAZIONE/AUDIT_COPERTURA.md`,
      con metro e «si riapre se…», L6 tolta da «ancora da fare» e **L7 promossa**
- [ ] Questo prompt archiviato in `docs/storico/audit-2026-09/`
- [ ] `code-reviewer` sul cumulativo `origin/main..main` — **un solo agente**
- [ ] Commit su `main` locale. **Nessun push.**

## Residui che questa fase eredita

- **Da L5**: `category_change_log.actor_*` si rimisura al primo cambio di
  categoria su `fatture` dopo il deploy dell'8/9 — non è materia di L6, ma se
  nel frattempo è arrivato un evento va annotato nel verbale.
- **Da L3**: i monitor girano in UTC alle 06:30–06:45 e leggono «ieri»: L6 è
  il posto dove si prova cosa vedono il giorno del cambio d'ora (25–26/10/2026,
  fra sei settimane).
- **Da L1 / memoria**: `ConnectionTerminated` e il rate limit fail-open sono
  stati corretti ma mai **eseguiti sotto carico**; L6 li esegue.

## Dopo la Fase 6

Restano L7-L9, in ordine, col modello consigliato nella tabella «Le lenti ancora
da fare» di `DOCUMENTAZIONE/AUDIT_COPERTURA.md`.
