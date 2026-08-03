# Stato audit ONEFLUX — ciclo 2026-07

Ciclo di audit avviato luglio 2026 sulle 10 dimensioni che l'agente
`oneflux-audit` copre. Documento vivo: **ogni sessione che chiude una
dimensione aggiorna la propria riga qui, prima di chiudere la sessione.**

Obiettivo: rispondere in un colpo a "cosa abbiamo controllato e cosa manca"
senza ricostruire da memoria sparsa — e lasciare, a fine ciclo, uno storico
consultabile invece di farlo sparire in chat isolate.

Legenda stato: 🟢 fatta e chiusa · 🟡 fatta ma con residui aperti · ⚪ non fatta.

| # | Dimensione | Stato | Ultima passata | Esito | Note |
|---|---|---|---|---|---|
| 1 | Security | 🟢 | 29/7/2026 (notte) | 3 passate audit + 1 sessione di follow-up, tutto deployato (6025080+2acf303+96be8be+0b3d57e+e33535e+7cb296c+030a053+474df6e+cec67ff+e4ef48f, push e4ef48f). Findings audit: 1 CRITICAL, 2 HIGH, 4 MEDIUM, 7 LOW — tutti fixati. Follow-up: 1 test rotto fixato, 1 bug indipendente scoperto e fixato, 1 debito tecnico chiuso | Passata 1: auth/sessione/gate su 174 endpoint worker. Passata 2: 8 router di dominio riga-per-riga. Passata 3: `admin.py` (2959 righe) + 160 route Next `api/**/route.ts`. CRITICAL = scrittura cross-tenant in riparto.py (id sede dal body senza check ownership). HIGH #1 = cache sessione non invalidata su revoca (30s finestra). HIGH #2 = admin_elimina_cliente cancellava prodotti_master.user_id (colonna inesistente, GDPR delete falliva silenziosamente). **Follow-up stessa notte**: (a) fixato test pre-esistente `test_eventi_sconosciuti_filtra_solo_unrecognized_event` (data hardcoded scaduta, non era un residuo Security ma bloccava la suite verde); (b) **verificato che il residuo "~130 componenti .tsx da auditare per XSS" era una stima sbagliata** — nel repo c'è 1 solo uso di `dangerouslySetInnerHTML` (JSON-LD statico in structured-data.tsx, zero input utente, sicuro), chiuso senza scrivere codice; (c) chiuso il residuo "89 route Next senza timeout verso il worker" — aggiunto helper `workerFetch` in `worker-config.ts`, migrate 53 route reali (il numero 89 contava anche GET e file già a posto), e scoperto/fixato un bug indipendente non noto prima: tutte le 21 route dell'albero `workspace/` non avevano try/catch attorno al fetch (500 grezzo invece di 502 pulito su errore rete). Suite finale: pytest 10104 passed/0 failed, build Next pulita. Nessun residuo aperto su questa dimensione. Giri storici precedenti sugli stessi layer: 4/7 (Fable), 20/6 (anti-hacker), 19/6 |
| 2 | Edge Functions | 🟢 | 30/7/2026 | 11 findings, tutti fixati e deployati (v39/v12) | CRITICAL: canale reprocess rimosso. 2 HIGH integrità coda → hanno aperto il caso per Database |
| 3 | Bug | 🟡 | 3/8/2026 (passata 1 di 2: audit + remediation stessa sessione) | **Passata 1 chiusa** su upload → parsing (XML/P7M/PDF) → categorizzazione AI. Due giri read-only con `oneflux-audit` (Sonnet): 2 HIGH + 3 MEDIUM + 4 LOW + 1 INFO. Tutti rimediati (Opus), più 4 blocchi trovati da `code-reviewer` sul diff cumulativo. Suite 10172 passed/0 failed, OpenAPI drift OK (193 endpoint). **Resta aperta la passata 2** (margini/briefing/chat in `fastapi_worker.py`) | **Due giri, non uno**: il primo agente ha lasciato ~3900 righe di `ai_service.py` non lette e l'ha dichiarato solo a fine report; un secondo giro mirato ha trovato lì il finding più grave. **Tutti i findings riverificati a mano** leggendo il codice e cercando i chiamanti vivi, non presi per buoni dall'agente. **HIGH#1** — `salva_correzione_in_memoria_globale` (`ai_service.py`) aveva **zero chiamanti vivi**, quindi `_propaga_global_override_a_fatture_storiche` era irraggiungibile: le correzioni admin alla memoria globale **non si propagavano più alle fatture storiche**, valevano solo per le righe future. I due endpoint admin scrivevano `prodotti_master` in diretta (refactor lasciato a metà). Fix: `POST /conflitti/risolvi` azione "promuovi" ora passa da `salva_correzione_in_memoria_globale(is_admin=True)`; `PATCH /memoria/{prod_id}` fa una sola UPDATE ancorata a `prod_id` e poi chiama direttamente la propagazione — **non** passa dalla funzione, perché quella cerca il record per descrizione *normalizzata* e in `prodotti_master` convivono varianti non normalizzate (verificato sul DB live: 5 casi su 10 divergono; `id 4799` `'(I)100 COP EST. X DW 280CC'` normalizza esattamente su `id 17195` `'( )COP EST X DW 280CC'`, due record distinti già presenti — sarebbe finita su un record diverso o avrebbe creato un duplicato). **HIGH#2** — upsert a chunk di 500 senza transazione: su fallimento a metà le prime 500 righe restavano scritte ma l'evento loggato diceva `FAILED rows_saved=0`, cioè **il log sottostimava il danno**; `verifica_integrita_fattura` sta dentro lo stesso try e non veniva mai eseguita. Fix (scelta esplicita di Mattia, "cap + osservabilità", **niente rollback di compensazione**): `_MAX_RIGHE_PER_FATTURA = 2000` portata nel percorso vivo (esisteva solo nel ramo Streamlit morto, `upload_handler.py:1389`) + status `SAVED_PARTIAL` con conteggio reale e `partial_write: true` nei details (verificato sul DB live che il CHECK constraint ammette già quel valore). **MEDIUM#1** — al `JOB_TIMEOUT` (300s) il thread daemon resta vivo e un altro worker può riclamare lo stesso item: le righe non si duplicano (upsert idempotente) ma **le chiamate AI a pagamento sì**. Fix: `_claim_ancora_valido` (compare-and-swap su `locked_by`) prima di `salva_fattura_processata` e prima di `_auto_classify_saved_rows`, con status `skip` (che il ciclo già gestiva, era codice morto). **MEDIUM#2** — quota AI esaurita indistinguibile da errore di rete: entrambe finivano in `Da Classificare` senza dirlo al cliente. Fix: nuova `AIDailyLimitExceededError(RuntimeError)` (sottoclasse, così il mapping su 429 in `fastapi_worker` regge), `summary['ai_rate_limited']`, short-circuit sui chunk successivi, e `worker_client.py` ora traduce il 429 HTTP nell'eccezione invece di degradare a fallback locale mascherando la causa. **MEDIUM#3** — rimossa `svuota_memoria_globale`: dead code che cancellava `prodotti_master` di **tutti** i clienti senza conferma. **LOW#1** — `volte_visto` non cresceva mai (passato fisso a `1` negli upsert, che riscrivevano la colonna): campo omesso dal payload in 4 siti, il default DB copre l'insert e su conflitto il valore resta. Dati live coerenti con la diagnosi: 5011 record a 1, appena 172 sopra. **LOW#2** — rimossa `_extract_piva_from_xml` (dead code il cui fallback prendeva la P.IVA del **CedentePrestatore**, cioè il fornitore invece del destinatario, invertendo la semantica del routing multi-sede). **LOW#3** — `try/except` locale su `int(NumeroLinea)` nel ramo TD24 (l'eccezione faceva scartare l'intera riga, sballando la quadratura in silenzio). **LOW#4** — rimossa lettura morta in `_esiste_override_manuale_locale`. **INFO** — `ai_service.py:4507` usa `prezzo == 0` invece di `totale_riga == 0`, innocuo perché il guardrail a valle usa `totale_riga`: non toccato. **4 blocchi trovati da `code-reviewer`** sul diff cumulativo (di nuovo il passo che trova ciò che audit e remediation non vedono): (a) MEDIUM#2 inerte sul percorso HTTP di produzione — il 429 degradava a fallback locale; (b) LOW#1 incompleto, `upload_handler.py:762` (il sito **più caldo**, ogni upload) passava ancora `volte_visto: 1` — mancato perché il grep iniziale era limitato a `ai_service.py`; (c) PATCH admin con doppia scrittura che poteva riportare `verified=False` **dopo** che la propagazione di massa era già partita; (d) il mismatch id/descrizione normalizzata descritto sopra. Tutti chiusi. **Un secondo giro di `code-reviewer` sulle correzioni** ha poi trovato che il fix (a) aveva introdotto una regressione: il worker restituisce 429 per **due** motivi diversi — quota AI giornaliera e rate limiter per IP (30 req/60s, `_check_rate_limit`) — e trattarli uguali significava che un upload grosso (chunk da 30) faceva scattare il limite per IP, veniva letto come "quota esaurita" e **short-circuitava tutti i chunk rimanenti** con una diagnosi falsa, dove prima il fallback locale funzionava. Fix: il worker marca il 429 di quota con header `X-RateLimit-Scope: ai-daily-quota`, il client discrimina sull'header col testo come fallback per il rollout. **Nota sui test**: in questa suite `requests` è sostituito da un mock del conftest che non è un package e non espone eccezioni vere — un `import requests` dentro un mock di risposta dà `exceptions must derive from BaseException` e fa passare il test per il motivo sbagliato. Ogni test aggiunto è stato verificato fallire ripristinando il codice pre-fix. **Regole di dominio verificate integre in ogni percorso**: nessun fallback verso `SERVIZI E CONSULENZE`, guardrail NOTE E DICITURE ancorato a `totale_riga` in tutti e 4 i punti, soft delete rispettato nella propagazione, gerarchia admin > locale > globale intatta, auto-save solo in memoria locale (anti-contaminazione cross-tenant), nessun `__getattr__`. **Sani, non ricontrollare**: cascata P7M a 5 fallback, inversione segno TD04, guardia anti-doppione per identità naturale, mapping AI per `idx`, SSRF guard, `ContextVar`, `_build_master_canonical_map`, `multisede_routing.py`. **Gap dichiarati**: `ai_service.py:3579-3990` (trasformazioni pure di categoria, zero I/O verificato via grep — bassa priorità ma **non** dichiarato chiuso); `services/routers/riparto.py` e `fatture.py` nominati nel perimetro ma mai letti. **Deployato** (push `main` 3/8/2026 ore ~13:50, commit `54f345d`): CI verde su tutti e 3 i workflow rilevanti (Tests, OpenAPI Schema Drift Check, Requirements Consistency); Vercel non coinvolto (nessun file `apps/web/**` nel commit), worker Railway si ridistribuisce autonomamente dal push. La riga resta 🟡 finché non è fatta la passata 2 |
| 4 | AI | 🟢 | 5/7/2026 (Fable) | 2 HIGH + 4 MED + 4 LOW deployati | Ciclo chiuso |
| 5 | Performance | 🟡 | 19/6/2026 | RPC dashboard_stats_aggregata + skeleton | Prezzi/Fatture full-load ancora non convertiti (residuo noto). **Da riverificare con dati esatti dalla sessione originale** |
| 6 | Qualità/UI | 🟢 | 19/6/2026 | Filtro mese uniformato, sky-* → primary | commit df01a9c |
| 7 | Database | 🟢 | 30/7/2026 (audit + remediation stessa giornata; codice committato e deployato il 2/8/2026) | Audit read-only (9 findings) seguito da sessione di remediation nella stessa giornata: 2 HIGH + 4 MEDIUM + 1 LOW fixati e deployati sul DB live; 2 LOW restano aperti (non bloccanti). Suite pytest completa verde dopo i fix | **Verificato sul DB live prima di agire**: 0 righe orfane su `fatture_queue.user_id`/`ristorante_id`; `ricavi_email_queue` ha GIA' FK `ON DELETE CASCADE` su entrambe le colonne (confermato `confdeltype='c'`) — il commento in admin.py era quindi obsoleto, non il codice; nessun indice su `created_at`/GIN su `payload_meta` (confermato seq scan). **Fix applicati** (migration `20260730230000`/`20260730231500`/`20260730232500`/`20260730233000`, tutte applicate live via MCP): HIGH#1 — aggiunte FK `fatture_queue_user_id_fkey`/`fatture_queue_ristorante_id_fkey` (nullable, `ON DELETE CASCADE`): la cancellazione GDPR ora propaga automaticamente, rimossa la voce ridondante da `_SVUOTA_TABELLE_NO_CASCADE` in `account.py`, corretto il commento obsoleto in `admin.py` (rimossa anche la delete manuale ridondante su `ricavi_email_queue`). HIGH#2 — `release_stale_locks` ora passa a `dead` (non più `failed` a ciclo infinito) se `attempt_count >= max_attempts`, e rimanda `next_retry_at` di 1 minuto sul ramo `failed`; `claim_batch_for_processing` ha in più il filtro `attempt_count < max_attempts` come difesa in profondità. MEDIUM#4 — nuova RPC `purge_ricavi_email_queue` (90gg, azzera subject/attachment/last_error) + nuova funzione Python `purge_ricavi_xls_storage` in `email_queue_processor.py` che ora rimuove davvero i file dal bucket `ricavi-xls` (prima non venivano MAI rimossi). MEDIUM#5 — nuove RPC `purge_fatture_queue_last_error` (90gg su righe dead/scartata) e `purge_upload_events_retention` (365gg, hard delete). MEDIUM#6 — `_purge_xml`/`_purge_raw_body_sample` non girano più a ogni ciclo (~ogni 15s): spostate in `worker/run.py` sotto nuovo gate `WORKER_QUEUE_PURGE_INTERVAL_SECONDS` (default 6h), stesso pattern di `purge_cestino_scaduto`. LOW — grant residui `anon`/`authenticated` su `upload_events` revocati (`upload_events.id` è uuid, nessuna sequence da revocare a differenza di quanto ipotizzato nell'audit). **Aperti (non fixati, priorità bassa)**: (a) `/api/fatture/da-assegnare` legge `xml_content` di tutta la coda senza `.limit()`; (b) `resolve_unknown_tenant` su P.IVA duplicate prende la sede più recente senza disambiguare/segnalare l'ambiguità. Regole di dominio verificate OK durante l'audit: nessun fallback nascosto verso `SERVIZI E CONSULENZE`, constraint `fatture_categoria_not_empty_chk` e `fatture_note_diciture_solo_importo_zero_chk` rispettati. **Nota 2/8/2026**: le migration SQL erano già applicate live via MCP il 30/7, ma il codice Python (`account.py`, `admin.py`, `worker/email_queue_processor.py`) e le 4 migration stesse non erano mai stati committati/pushati — scoperto e corretto durante la sessione Architettura (commit `b725662`), ora genuinamente deployato |
| 8 | Architettura | 🟢 | 2/8/2026 (audit + remediation stessa sessione, 2 fasi, deployato) | Audit read-only (7 findings: 1 HIGH + 2 MEDIUM + 2 LOW + 2 INFO). Fase 1: remediation HIGH+MEDIUM (confermata esplicitamente da Mattia). Fase 2 (stessa sessione, su richiesta esplicita "chiudi prima i punti low e bassi rimasti in sospeso"): chiusi anche i 2 LOW + 2 INFO residui, poi revisionato tutto con `code-reviewer` che ha trovato e fatto fixare 2 residui indipendenti (vedi sotto). Suite pytest 10162 passed/0 failed dopo tutti i fix. **Nessun residuo aperto** | **Verificato che NON è tornato** `__getattr__` sugli helper dei router (già rotto 9 router in prod in passato): tutti i 13 router usano il wrapper esplicito `_fw()`. **Accoppiamento Next.js↔worker pulito**: 164/167 route.ts proxy dirette al worker, i 3 restanti sono legittimi (auth/me, auth/accetta-privacy via lib/auth.ts, tts stateless); `apps/web/package.json` non ha SDK OpenAI/Supabase/parsing XML-PDF, il frontend non ha nemmeno le dipendenze per fare logica pesante. **Worker-separato rispettato**: classificazione AI e parsing fatture restano solo nel worker/queue-worker. **Fix Fase 1**: HIGH — `services/fastapi_worker.py` (`_calcola_costi_auto_per_mese`/`_calcola_costi_auto_per_periodo`) usava un set hardcoded di categorie "Spese Generali" duplicato rispetto a `CATEGORIE_SPESE_GENERALI` in `config/constants.py` (già usata correttamente da `margine_service.py`/Margini) — rischio di disallineamento silenzioso Home vs Margini se la lista cambia in futuro; ora importa la costante condivisa. MEDIUM#1 — rimossa `ricalcola_prezzi_con_sconti` in `services/db_service.py` (già marcata DEPRECATED, zero chiamanti vivi verificati via grep, cadeva silenziosamente su `session_state` vuoto nel worker se richiamata) e il suo export da `services/__init__.py`. MEDIUM#2 — spostati `app_controllers.py`/`ui_helpers.py`/`sidebar_helper.py` (residui Streamlit orfani, ~2400 righe, zero chiamanti vivi oltre al proprio test) da `utils/` a nuova cartella `legacy_streamlit/` via `git mv`; aggiornati i 6 import interni fra i 3 file e le patch-string nel test; **scoperto e fixato un problema indipendente durante la verifica**: `tests/conftest.py` mocka `streamlit` solo per i test sotto `tests/` (pytest non eredita conftest da directory sorelle) — il test spostato lo aveva perso e falliva su `NoSessionContext` reale; aggiunto `legacy_streamlit/conftest.py` con lo stesso mock, ridotto al solo `streamlit` (unico modulo pesante richiesto); `pytest.ini` `testpaths` esteso a `tests legacy_streamlit` su scelta esplicita di Mattia (il test resta in CI, non solo storico). **Fix Fase 2 (residui LOW+INFO)**: LOW#1 — `NON_IGNORABILI` (duplicata carattere-per-carattere fra `mobile-briefing.tsx` e `home-briefing.tsx`) estratta in nuovo modulo condiviso `apps/web/src/lib/briefing-shared.ts`, entrambi i file ora importano da lì. LOW#2 — `services/routers/margini.py` importava direttamente `_calc_netto` da `ricavi.py` a livello di modulo (unico caso router→router diretto nel file); sostituito con un wrapper lazy locale (stesso principio di `_fw()`, import posticipato a runtime), nessun ciclo reale esistente (`ricavi.py` non importa mai `margini.py`). INFO#1 — CLAUDE.md corretto da "~7450" a "~8000" righe per `fastapi_worker.py` (reali: 8037, verificate con `wc -l`). INFO#2 — `_make_cache()` risultava triplicata, non duplicata: oltre a `db_service.py`/`documenti_service.py` (le 2 note dall'audit) esisteva una terza copia identica in `margine_service.py`, non vista prima; le tre erano byte-per-byte identiche. Unificata in nuova funzione pubblica `make_cache()` in `utils/streamlit_compat.py`, i 3 file sorgente ora importano con alias (`from utils.streamlit_compat import make_cache as _make_cache`) per non toccare le call-site esistenti. **Fix aggiuntivi trovati da `code-reviewer` sul diff cumulativo delle 2 fasi** (nessuno bloccante per l'uso in produzione, ma refusi reali): rimossa la voce `'ricalcola_prezzi_con_sconti'` residua nell'`__all__` di modulo di `services/db_service.py` (riga 2223 — distinta da quella già ripulita in `services/__init__.py` durante la Fase 1; nessun chiamante vivo con star-import verificato via grep, ma rendeva `from services.db_service import *` un `AttributeError` reale); corretto il docstring di `legacy_streamlit/app_controllers.py` che citava ancora il vecchio path `utils/app_controllers.py` e l'uso in `app.py` (rimosso dal repo il 17/7) invece del nuovo path/stato congelato; risolto uno staging Git incoerente sui 4 file spostati in `legacy_streamlit/` (erano `A`/`D` separati invece di rename riconosciuti, rischio di lasciare doppie copie su un commit futuro) con `git add` sui path sorgente per far riconoscere a Git i 4 rename. **Copertura dichiarata dall'agente audit**: services/, routers/, utils/, config/ auditati al 100%; apps/web route.ts verificate strutturalmente al 100% (167/167); lib/*.ts e componenti tsx auditati in profondità solo su un sottoinsieme mirato (~178 componenti desktop in `(app)/*` non letti riga per riga — gap dichiarato esplicitamente, da coprire in una passata dedicata se serve). Esclusi per istruzione esplicita: Database, Edge Functions, Security, DevOps/Config (già chiusi). **Deployato** (push `main`, 2/8/2026 pomeriggio, deroga esplicita all'orario): commit `6073bd6` (Architettura); nello stesso push anche `b725662`, lavoro Database del 30/7 che risultava dichiarato "deployato" ma non era mai stato committato (FK GDPR account.py/admin.py, purge_ricavi_xls_storage, 4 migration SQL) — scoperto verificando `git log` sui file prima del commit, corretto contestualmente. CI verde su tutti i workflow (Deploy Vercel, Tests, OpenAPI Drift, Requirements). Worker Railway si ridistribuisce autonomamente dal push, non verificabile da qui senza credenziali Railway — da controllare manualmente |
| 9 | Test | ⚪ | — | — | Esiste solo la suite che gira sempre (pytest ~10104 + Deno) — mai un audit sulla qualità/coverage dei test in sé |
| 10 | DevOps/Config | 🟢 | 30/7/2026 (audit + remediation + verifica dashboard, stessa giornata) | Audit read-only (12 findings) + remediation completa: 2 HIGH fixati, 4 MEDIUM chiusi (3 con fix, 1 come non-fare), 4 LOW chiusi (2 con fix, 2 verificati OK su dashboard), 2 INFO chiusi. Suite pytest 10130 passed/0 failed. **Nessun residuo aperto** | **Verifica dashboard (Mattia, screenshot)**: `SUPABASE_DB_URL` presente su GitHub Repository Secrets (aggiornato 3 settimane fa) — il backup non è più senza secret configurato, sospetto ~24gg chiuso; `ENABLE_INLINE_QUEUE_PROCESSOR` confermato `0` sul servizio `worker` su Railway (queue-worker separato attivo, nessun rischio doppio processing). **Sessione 1 (HIGH)**: HIGH#1 — rimosso il fallback silenzioso su `SUPABASE_KEY` (anon) nel ramo env var di `services/__init__.py:191-200` e in `worker/queue_processor.py:152-158`; ora entrambi richiedono `SUPABASE_SERVICE_ROLE_KEY` esplicita e falliscono con `RuntimeError` se assente (coerente col ramo `st.secrets` che già lo faceva). `worker/run.py:103-104` (rename compatibilità `.env` locale, non un fallback anon-key) lasciato invariato. HIGH#2 — i 3 marker `last_purge_time`/`last_retention_time`/`last_queue_purge_time` in `worker/run.py` ora si inizializzano a `time.monotonic() - INTERVALLO` invece che a `0.0`: primo purge al primo ciclo utile dopo boot, non più dopo 6h/24h di runtime ininterrotto. **Sessione 2 (chiusura residui, su richiesta esplicita "chiudiamo tutti i punti")**: MEDIUM(1) — secret deprecato `SUPABASE_KEY` in `.github/workflows/openapi-drift.yml:37` rinominato in `SUPABASE_SERVICE_ROLE_KEY` (verificato che il secret esiste già su GitHub, usato da `ricavi_queue_monitor.yml`/`queue-worker.yml`). MEDIUM(2) — `INVOICETRONIC_WEBHOOK_SECRET` **chiuso come non-fare**: verificato che è correttamente usato solo da `supabase/functions/invoicetronic-webhook/index.ts` (Deno), nessun fix necessario, comportamento voluto. MEDIUM(3) — `docker/docker-compose.prod.yml` aggiunta `WORKER_SECRET_KEY=${WORKER_SECRET_KEY}` mancante nel servizio worker. MEDIUM(4) — `ADMIN_EMAILS` duplicato lasciato invariato: fail-open per scelta esplicita già documentata, non un bug. LOW — `.env.example` rinominato `SUPABASE_KEY`→`SUPABASE_SERVICE_ROLE_KEY` con commento sul perché. LOW — URL worker Railway hardcoded: aggiunto secret opzionale `WORKER_HEALTH_URL` con fallback (stesso pattern già in `keepalive_worker.yml`) ai 3 workflow che non l'avevano (`worker_latency_check.yml`, `riparto_coerenza_check.yml`, `invoicetronic_eventi_sconosciuti_check.yml`); `apps/web/src/lib/auth.ts` aveva già l'override via `process.env.WORKER_URL`, nessuna modifica necessaria. INFO — le 3 env var 30/7 (`WORKER_PURGE_INTERVAL_SECONDS`, `WORKER_RETENTION_INTERVAL_SECONDS`, `WORKER_QUEUE_PURGE_INTERVAL_SECONDS`) aggiunte alla tabella in `DOCUMENTAZIONE/tecnica/TROUBLESHOOTING.md`. INFO — CORS: rimossi i 3 origin morti (`ohyeah.streamlit.app`, `ohyeah.app`, `envoicescan-ai-production.up.railway.app`) dal default hardcoded in `services/fastapi_worker.py:_build_allowed_origins`, restano i 4 domini vivi. **Chiusi dopo verifica dashboard**: LOW — `ENABLE_INLINE_QUEUE_PROCESSOR` verificato `0` su Railway (screenshot Variables servizio worker); LOW — `SUPABASE_DB_URL` verificato presente su GitHub Repository Secrets. | **Scope**: Railway (Dockerfile, config worker+queue-worker), Vercel (env `NEXT_PUBLIC_*` vs server-only), GitHub Actions (workflow+secrets), Supabase (secrets Edge Functions, CORS, cron), coerenza locale/staging/prod, rotation secrets. **Esclusi** (già coperti): schema DB→Database, logica Edge Function→Edge Functions, auth/sessioni→Security. **Verificato senza problemi**: nessun secret in git history, `.gitignore` corretto, nessun secret in `NEXT_PUBLIC_*` (solo `NEXT_PUBLIC_WHATSAPP_NUMERO`, pubblico per natura), `WORKER_SECRET_KEY` davvero fail-closed (righe 117-121,177 di fastapi_worker.py) e gate anche `/docs`/`/redoc`/`/openapi.json`, `bypass_guardia_piva` scoped correttamente per sede, `supabase/config.toml` intenzionale, security headers Next.js presenti, Dockerfile non-root senza secret in ENV/ARG. Suite pytest 10130 passed/0 failed verificata dopo entrambe le sessioni di fix |

## Nota metodologica

Le righe 1-6 sono state popolate il 30/7/2026 da ricostruzione a memoria —
un punto di partenza approssimato, non un dato certo. Il meccanismo previsto
è che ogni sessione riapra la dimensione che ha realmente lavorato e corregga
la propria riga con l'esito verificato.

**Aggiornamento correzioni:**
- **Security** — corretta il 30/7/2026 dalla sessione che ha svolto il lavoro:
  3 passate + 1 follow-up, tutti i commit citati verificati esistenti nel
  repo, nessun residuo aperto. Riga ora attendibile.
- **Bug** — riga riscritta il 3/8/2026 da una passata dedicata vera (la prima:
  fino a qui era sempre stata accorpata a Security). Non è più una ricostruzione
  a memoria, ma copre **solo il primo dei due perimetri**: resta da fare la
  passata 2 su margini/briefing/chat.
- **AI, Performance, Qualità/UI** — righe ancora quelle ricostruite a
  memoria del 30/7, **non ancora corrette dalle sessioni originali**. Restano
  da riverificare quando quelle chat vengono riaperte.
- **Database** — corretta il 2/8/2026 da una sessione diversa (Architettura),
  non dall'originale: la riga diceva "fixati e deployati" ma solo le migration
  SQL erano live, il codice Python non era mai stato committato. Da qui la
  regola generale: **"deployato" scritto in questa tabella non è una prova, va
  verificato con `git log -- <file>`** prima di darlo per acquisito. Vale
  soprattutto per le righe ancora ricostruite a memoria qui sopra.

Le passate del 4/7 e 5/7 sono di **Fable** (agente diverso, pre-esistente
all'attuale `oneflux-audit`), incluse perché coprono la stessa dimensione
nella sostanza. Le passate di Security/Qualità/Performance del 19-20/6 sono
manuali (Claude Code diretto), non tramite subagente.

Prima di fidarsi di questa tabella per decidere se una dimensione è "già
fatta e quindi non serve rifarla": il codice cambia, un audit di 40 giorni fa
può essere superato. Usarla per sapere COSA guardare, non per escludere una
rilettura se il contesto lo giustifica.

## Come aggiornare (una sessione alla volta — mai in parallelo)

Il flusso è sequenziale apposta: due sessioni che scrivono nello stesso file
in parallelo si sovrascrivono a vicenda senza avviso. Aggiornare una
dimensione per volta.

A fine di ogni passata (agente `oneflux-audit` o manuale):
1. Aggiorna la riga della dimensione: stato, data, esito, note — con i dati
   reali di quella sessione, non ricostruiti da fuori
2. Se sono rimasti findings aperti, elencali nella nota (non serve un file
   separato per dimensione — questa tabella è l'indice)
3. Salva/aggiorna la memoria corrispondente come sempre (progetto/feedback)
4. Se l'audit apre il caso per un'altra dimensione (come Edge Functions →
   Database il 30/7), annotalo nella colonna Note della dimensione aperta

## Prossima sessione: dimensione Bug — passata 2

> Sezione viva: la sessione che prende in carico questa consegna la riscrive con
> la propria per la dimensione successiva, non la lascia stagnare qui.

**Stato al 3/8/2026**: 7/10 dimensioni 🟢, 2 🟡 (Bug — passata 1 chiusa,
passata 2 da fare; Performance — residuo noto, riga ancora ricostruita a
memoria il 30/7), 1 ⚪ (Test).

**Perché la passata 2 di Bug adesso**: la passata 1 (3/8) ha coperto upload →
parsing → categorizzazione AI e ha chiuso 10 findings, ma il perimetro era
volutamente metà: `fastapi_worker.py` è ~8000 righe e tentarlo tutto insieme
produce un audit superficiale. La metà rimasta non è stata guardata da nessuno.

**Scope della passata 2**: margini / briefing / chat — concentrati per ~5000
righe dentro `services/fastapi_worker.py`. Includere `services/margine_service.py`
e i router collegati (`services/routers/margini.py`, `ricavi.py`).

**Portarsi dietro dalla passata 1** (dichiarati aperti, non chiusi in silenzio):
- `services/ai_service.py:3579-3990` — trasformazioni pure di categoria, zero
  I/O verificato via grep. Bassa priorità, ma **non** è stato dichiarato chiuso.
- `services/routers/riparto.py` e `services/routers/fatture.py` — erano nel
  perimetro nominale della passata 1 ma non sono mai stati letti.
- `services/routers/fatture.py:850` passa ancora `volte_visto: 1`: è un
  `insert()` puro nel ramo "record non esiste", quindi innocuo, ma ridondante
  col default DB. Diventerebbe dannoso se qualcuno lo convertisse in `upsert`
  per chiudere la race del check-then-act — miglioramento plausibile in futuro.
- **`prodotti_master` non ha l'invariante "descrizione sempre normalizzata"**,
  ed è la causa radice di B4. A romperlo è `aggiorna_streak_classificazione`
  (`ai_service.py:3130-3137`), che fa `upsert` con la descrizione grezza. Il
  fix pulito è lì, o una bonifica una-tantum con merge dei `volte_visto` (c'è
  un precedente: `migrations/035_clean_corrupted_descriptions.sql`). Finché
  regge, nessun endpoint ancorato a un `id` deve passare da una funzione che
  risolve per descrizione.
- Cleanup righe orfane su re-upload di fatture >2000 righe
  (`invoice_service.py:1938-1958`): la lista `numero_riga` è quella già
  troncata, quindi le righe 2001+ di una versione precedente scritta senza cap
  verrebbero hard-deleted. Caso raro, richiede una versione precedente
  pre-cap.

**Escludere**: Database, Edge Functions, Security, DevOps/Config, Architettura
(chiuse e deployate — riaprirle solo se l'audit ci inciampa per davvero).

**Modello**: Sonnet regge l'audit read-only. Per la remediation vale §3 di
`WORKFLOW.md` (default Opus, Sonnet è l'eccezione) — e comunque solo dopo
conferma esplicita di Mattia, mai in autonomia.

**Lezioni operative (le 5 del 2/8 restano valide, più 3 dal 3/8):**

1. **`git log -- <file>` prima di credere a "deployato" scritto qui.** Il
   lavoro Database del 30/7 risultava "fixato e deployato" in questa stessa
   tabella, ma solo le migration SQL erano davvero live (applicate via MCP):
   il codice Python collegato era rimasto nel working tree per 3 giorni.
   "Deployato" qui va letto come "le migration sono sul DB", mai esteso al
   codice applicativo senza verifica.
2. **`tests/conftest.py` non si eredita fra directory sorelle.** Se sposti
   file testati fuori da `tests/`, serve un conftest.py locale — un PASSED
   prima dello spostamento non dice nulla su dopo.
3. **`legacy_streamlit/` esiste dal 2/8** per il codice Streamlit orfano, già
   inclusa in `pytest.ini` `testpaths`. Se l'audit trova altro codice morto
   dello stesso tipo, isolarlo lì con lo stesso pattern (`git mv` + conftest
   se serve il mock).
4. **Questo file è tracciato da git** (eccezione `!AUDIT_ONEFLUX_STATO*.md`
   aggiunta il 2/8). Committalo insieme al lavoro che documenta.
5. **Ordine che ha funzionato due volte**: audit → remediation HIGH+MEDIUM (su
   conferma) → chiusura residui LOW/INFO → `code-reviewer` sul diff cumulativo
   → documento + memoria → deploy. Chiamare `code-reviewer` *dopo* aver chiuso
   i LOW: il 2/8 ha trovato 2 bug sfuggiti a tutti, il 3/8 ne ha trovati **4**,
   fra cui il più grave dell'intera sessione.
6. **Un agente che dichiara un gap a fine report va rimandato indietro, non
   assecondato.** Il 3/8 il primo giro ha lasciato ~3900 righe di
   `ai_service.py` non lette; il secondo giro mirato ha trovato lì il finding
   più grave della passata. Il costo di un secondo giro è basso, quello di un
   HIGH non visto no.
7. **Quando un fix riattiva una scrittura di massa su dati storici, il test
   sullo scoping si scrive PRIMA del deploy.** La propagazione riattivata il
   3/8 era inerte da mesi: al primo uso admin post-deploy tocca fatture reali
   di tutti i clienti. Verificare anche che il test fallisca davvero col
   codice pre-fix, altrimenti non prova nulla.
8. **Se una funzione cerca un record per chiave normalizzata, controlla sul DB
   live che la tabella contenga solo valori normalizzati.** `prodotti_master`
   non li ha: 5 descrizioni su 10 divergono, e due varianti della stessa voce
   convivono già come record distinti. Un endpoint ancorato a un `id` non deve
   passare da una funzione che risolve per descrizione.
9. **Un test verde al primo colpo non prova niente finché non l'hai visto
   fallire.** Rimetti il codice pre-fix e controlla che il test cada davvero.
   Il 3/8 tre test passavano per il motivo sbagliato: in questa suite
   `tests/conftest.py` sostituisce `requests` con un mock che **non è un
   package** e non espone eccezioni vere, quindi un `import requests` dentro
   un mock di risposta produce `exceptions must derive from BaseException` —
   il fallback scattava per quell'errore, non per il codice sotto test.
10. **Uno stesso status HTTP può avere più cause.** Il 429 di `/api/classify`
    è sia quota AI giornaliera sia rate limit per IP (30 req/60s): trattarli
    uguali ha introdotto una regressione che il primo giro di review non aveva
    visto. Quando mappi un codice di stato su una semantica, verifica chi
    altro lo emette sullo stesso endpoint.

## Chiusura del ciclo (quando tutte le righe sono 🟢 o 🟡 con nota esplicita)

Quando anche l'ultima dimensione è chiusa:
1. Aggiungere in cima al documento una riga "**Ciclo chiuso il gg/mm/aaaa**"
2. Spostare il file in `docs/storico/` (stesso posto dove sta lo storico del
   progetto — es. diagnosi Invoicetronic, migration legacy)
3. Se parte un nuovo ciclo di audit, crearne uno nuovo con la data corrente
   nel nome (es. `AUDIT_ONEFLUX_STATO_2026-10.md`) — non riusare questo file
