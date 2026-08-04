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
| 3 | Bug | 🟢 | 3/8/2026 (2 passate audit+remediation + bonifica dati stessa giornata) | **PASSATA 2 CHIUSA** (margini/briefing/chat): 3 giri read-only paralleli su **~16.800 righe** — il perimetro dichiarato dalla consegna ne stimava 5000, ma `daily_briefing_service.py` (1332 righe, il cuore vero del briefing) e altri 4 servizi non erano nominati; scoperti cercando `_BRIEFING_CODE_VERSION`, che in `fastapi_worker.py` non esiste. 11 findings dagli agenti + **1 HIGH trovato da me durante la remediation**, che nessun agente aveva visto. **Dei 3 findings verificati sul DB live, in tutti e 3 gli agenti avevano sbagliato la gravità — sempre per eccesso**: (a) "doppio conteggio costi di catena, il cliente vede due MOL diversi" → il difetto nel codice è reale (`_calcola_costi_auto_per_mese/_periodo` non filtravano `ripartita_su_gruppo`, mentre la RPC SQL e `margine_service.py` sì: la migration del 14/7 dichiarava di aver coperto tutti i percorsi e ne aveva saltato uno), ma le 746 righe ripartite (€66.083) stanno **tutte sulla sede tecnica** `Costi comuni di gruppo` (`sede_tecnica=true`), che ha **0 mesi con quote** e non è selezionabile come sede attiva da nessun cliente → i due addendi non si incontrano mai, nessun MOL sbagliato; declassato a MEDIUM (mina che si arma appena una fattura ripartita finisce su un PV reale). (b) "agent notturno rotto, non è mai partito" → ho **eseguito** il codice: `asyncio.create_task(funzione_sync())` **esegue** il corpo inline (bloccando) e fallisce solo dopo sul valore di ritorno, quindi la diagnosi era rovesciata; poi il DB: `{"enabled": false}` dal 30/5, mai un `last_run_at` → è spento e non ha mai girato, HIGH latente. (c) "righe Da Classificare entrano nel foodcost delle ricette" → il filtro manca davvero (160 descrizioni su 7 sedi selezionabili come ingredienti), ma il foodcost si calcola solo dagli ingredienti *scelti* e nessuna delle 5 ricette esistenti ne usa → MEDIUM. **L'HIGH trovato da me**: `chat alert 5` usava `ilike("categoria", "%SPESE%")` — **nessuna** delle 4 categorie reali contiene la parola "SPESE", quindi matchava **0 righe su 5827**: l'alert "spese generali non registrate" scattava anche nei mesi con spese regolarmente caricate. Falso allarme al cliente, da sempre. Trovato leggendo il codice intorno all'alert 2, non segnalato da nessun agente. **Altri HIGH**: `chat alert 2` faceva `.select("fatturato")` su `margini_mensili`, colonna **mai esistita** (errore 42703 riprodotto sul DB live), query sempre fallita dentro un `except: pass` → l'alert "ricavi mancanti" non è mai scattato per nessun cliente; `upsert_ricavi_modalita` era l'unico endpoint che scrive ricavi senza invalidare KPI Home e briefing (dopo "Carica Ricavi" il cliente vedeva il MOL vecchio fino a 30'); `prodotti_master` — `aggiorna_streak_classificazione` (unico chiamante vivo: `queue_processor.py:375`) fa upsert con la descrizione **grezza**, creando doppioni: **44 gruppi sul DB live, 6 con categorie in conflitto** (`CUORI FIL MERL` sta sia in PESCE sia in MATERIALE DI CONSUMO — quando vince il secondo, **esce dal food cost**). Fix: cerca il record normalizzato prima di inserire. **Limite dichiarato: il fix al codice previene solo 5 casi su 7 in futuro** — la normalizzazione non collassa `CUORI FIL.MERL`/`CUORI FIL MERL` (`FILETTOMERL` vs `FILETTO MERL`) né l'asterisco finale di `BRODO...TTL *`. **Bonifica dati eseguita in questa sessione** (dopo conferma esplicita di Mattia, criterio: vince la grafia realmente usata nelle fatture del cliente, perché è quella che già determina i costi calcolati oggi): dei 5 gruppi in conflitto di categoria trovati sul DB live (non 6 come stimato durante l'audit — un caso citato nella consegna non era più in conflitto), eliminati i 4 record fantasma con categoria minoritaria/sbagliata (id 13565 SERVIZI E CONSULENZE su "ALTRE PARTITE - ADDEBITO..." dove la grafia in uso è UTENZE E LOCALI; id 12634 FRUTTA su "SALV LIMONE X100" — salviette, non frutta; id 4511 SERVIZI E CONSULENZE su "SPESE RIATTIVAZIONE SERVIZIO/LINEA" dove la grafia in uso è UTENZE E LOCALI; id 6967 MATERIALE DI CONSUMO su uno zerbino dove la grafia in uso è MANUTENZIONE E ATTREZZATURE). **Errore commesso e corretto in corsa**: su `CUORI FIL MERL` (0 uso reale in nessuna fattura, viva o cestinata) ho eliminato per errore l'id col verso invertito rispetto alla mia stessa proposta — cancellato id 3913 (PESCE, la categoria corretta) invece di id 4074 (MATERIALE DI CONSUMO, l'errore); corretto aggiornando `UPDATE prodotti_master SET categoria='PESCE' WHERE id=4074` sul record superstite, verificato con query finale: **zero conflitti di categoria residui su `prodotti_master`**. Nessuna FK punta a `prodotti_master.id` (verificato su `information_schema` prima della delete). **Residuo dichiarato per il futuro**: il fix al codice resta a 5/7, i 2 casi di normalizzazione mancata (punto/asterisco) possono ricreare doppioni identici se ricompaiono in nuove fatture — non è stato scritto un fix aggiuntivo, priorità bassa. **MEDIUM/LOW**: costanti spese generali triplicate nel worker → derivate dall'unica fonte (`config/constants.py`); flag `parziale` sul mese in corso e `incluso_da_classificare` nei tool della chat; bullet vuoti non finiscono più nel prompt AI come `- ` nudo (invitava il modello a inventare); `home_config_post` invalida il briefing anche sui topic spenti — **errore mio corretto in corsa**: avevo scritto `body.topics_disabled is not None`, ma quel campo ha default `[]` non `None`, quindi avrebbe rigenerato il briefing a ogni salvataggio, anche solo del nome; ora confronta lo stato precedente; 4 `except: pass` negli alert chat ora loggano (uno di questi ha nascosto per mesi la query rotta); rimossi 2 rami irraggiungibili in `_narrative_phrase_for`; rimossa `get_inbox_badge_count` (residuo Streamlit, zero chiamanti — ma **4 test la coprivano**, riscritti su `get_inbox_notifications`: il primo grep escludeva `tests/`). **`code-reviewer` sul diff cumulativo** ha trovato 2 problemi reali: il ramo gemello dello streak leggeva solo `id,verified,confidence` e scriveva sempre `streak=1`, impedendo l'auto-promozione a `confidence='alta'` per i prodotti in sola grafia normalizzata (corretto replicando la logica dell'altro ramo; nel farlo ho intercettato un `now_streak = 1` fuori posto che avrebbe falsato il log della promozione); e il mancato bump di `_BRIEFING_CODE_VERSION` (12→**13**), senza cui il fix dei bullet non raggiunge chi ha già lo snapshot di oggi. **Verificato sano**: nessun fallback verso `SERVIZI E CONSULENZE`, `NOTE E DICITURE` solo a `totale_riga==0` (66 righe live, tutte a €0), `Da Classificare` escluse da tutti gli aggregatori di margine, `deleted_at IS NULL` ovunque, nessun `__getattr__`, rate limiting chat fail-closed, `salva_margini_anno` protetto contro l'azzeramento delle quote, `_to_float_it` e lo scorporo IVA dell'import Passbi corretti. Suite **10195 passed / 0 failed**, drift OpenAPI OK (193 endpoint), ogni test nuovo verificato fallire col codice pre-fix. Commit `9d8742e` | **Passata 1** (upload → parsing → categorizzazione AI), stessa giornata, commit `54f345d`+`0234416`, CI verde |
| 3b | Bug — dettaglio passata 1 | 🟢 | 3/8/2026 (passata 1 di 2: audit + remediation stessa sessione) | **Passata 1 chiusa** su upload → parsing (XML/P7M/PDF) → categorizzazione AI. Due giri read-only con `oneflux-audit` (Sonnet): 2 HIGH + 3 MEDIUM + 4 LOW + 1 INFO. Tutti rimediati (Opus), più 4 blocchi trovati da `code-reviewer` sul diff cumulativo. Suite 10172 passed/0 failed, OpenAPI drift OK (193 endpoint). **Resta aperta la passata 2** (margini/briefing/chat in `fastapi_worker.py`) | **Due giri, non uno**: il primo agente ha lasciato ~3900 righe di `ai_service.py` non lette e l'ha dichiarato solo a fine report; un secondo giro mirato ha trovato lì il finding più grave. **Tutti i findings riverificati a mano** leggendo il codice e cercando i chiamanti vivi, non presi per buoni dall'agente. **HIGH#1** — `salva_correzione_in_memoria_globale` (`ai_service.py`) aveva **zero chiamanti vivi**, quindi `_propaga_global_override_a_fatture_storiche` era irraggiungibile: le correzioni admin alla memoria globale **non si propagavano più alle fatture storiche**, valevano solo per le righe future. I due endpoint admin scrivevano `prodotti_master` in diretta (refactor lasciato a metà). Fix: `POST /conflitti/risolvi` azione "promuovi" ora passa da `salva_correzione_in_memoria_globale(is_admin=True)`; `PATCH /memoria/{prod_id}` fa una sola UPDATE ancorata a `prod_id` e poi chiama direttamente la propagazione — **non** passa dalla funzione, perché quella cerca il record per descrizione *normalizzata* e in `prodotti_master` convivono varianti non normalizzate (verificato sul DB live: 5 casi su 10 divergono; `id 4799` `'(I)100 COP EST. X DW 280CC'` normalizza esattamente su `id 17195` `'( )COP EST X DW 280CC'`, due record distinti già presenti — sarebbe finita su un record diverso o avrebbe creato un duplicato). **HIGH#2** — upsert a chunk di 500 senza transazione: su fallimento a metà le prime 500 righe restavano scritte ma l'evento loggato diceva `FAILED rows_saved=0`, cioè **il log sottostimava il danno**; `verifica_integrita_fattura` sta dentro lo stesso try e non veniva mai eseguita. Fix (scelta esplicita di Mattia, "cap + osservabilità", **niente rollback di compensazione**): `_MAX_RIGHE_PER_FATTURA = 2000` portata nel percorso vivo (esisteva solo nel ramo Streamlit morto, `upload_handler.py:1389`) + status `SAVED_PARTIAL` con conteggio reale e `partial_write: true` nei details (verificato sul DB live che il CHECK constraint ammette già quel valore). **MEDIUM#1** — al `JOB_TIMEOUT` (300s) il thread daemon resta vivo e un altro worker può riclamare lo stesso item: le righe non si duplicano (upsert idempotente) ma **le chiamate AI a pagamento sì**. Fix: `_claim_ancora_valido` (compare-and-swap su `locked_by`) prima di `salva_fattura_processata` e prima di `_auto_classify_saved_rows`, con status `skip` (che il ciclo già gestiva, era codice morto). **MEDIUM#2** — quota AI esaurita indistinguibile da errore di rete: entrambe finivano in `Da Classificare` senza dirlo al cliente. Fix: nuova `AIDailyLimitExceededError(RuntimeError)` (sottoclasse, così il mapping su 429 in `fastapi_worker` regge), `summary['ai_rate_limited']`, short-circuit sui chunk successivi, e `worker_client.py` ora traduce il 429 HTTP nell'eccezione invece di degradare a fallback locale mascherando la causa. **MEDIUM#3** — rimossa `svuota_memoria_globale`: dead code che cancellava `prodotti_master` di **tutti** i clienti senza conferma. **LOW#1** — `volte_visto` non cresceva mai (passato fisso a `1` negli upsert, che riscrivevano la colonna): campo omesso dal payload in 4 siti, il default DB copre l'insert e su conflitto il valore resta. Dati live coerenti con la diagnosi: 5011 record a 1, appena 172 sopra. **LOW#2** — rimossa `_extract_piva_from_xml` (dead code il cui fallback prendeva la P.IVA del **CedentePrestatore**, cioè il fornitore invece del destinatario, invertendo la semantica del routing multi-sede). **LOW#3** — `try/except` locale su `int(NumeroLinea)` nel ramo TD24 (l'eccezione faceva scartare l'intera riga, sballando la quadratura in silenzio). **LOW#4** — rimossa lettura morta in `_esiste_override_manuale_locale`. **INFO** — `ai_service.py:4507` usa `prezzo == 0` invece di `totale_riga == 0`, innocuo perché il guardrail a valle usa `totale_riga`: non toccato. **4 blocchi trovati da `code-reviewer`** sul diff cumulativo (di nuovo il passo che trova ciò che audit e remediation non vedono): (a) MEDIUM#2 inerte sul percorso HTTP di produzione — il 429 degradava a fallback locale; (b) LOW#1 incompleto, `upload_handler.py:762` (il sito **più caldo**, ogni upload) passava ancora `volte_visto: 1` — mancato perché il grep iniziale era limitato a `ai_service.py`; (c) PATCH admin con doppia scrittura che poteva riportare `verified=False` **dopo** che la propagazione di massa era già partita; (d) il mismatch id/descrizione normalizzata descritto sopra. Tutti chiusi. **Un secondo giro di `code-reviewer` sulle correzioni** ha poi trovato che il fix (a) aveva introdotto una regressione: il worker restituisce 429 per **due** motivi diversi — quota AI giornaliera e rate limiter per IP (30 req/60s, `_check_rate_limit`) — e trattarli uguali significava che un upload grosso (chunk da 30) faceva scattare il limite per IP, veniva letto come "quota esaurita" e **short-circuitava tutti i chunk rimanenti** con una diagnosi falsa, dove prima il fallback locale funzionava. Fix: il worker marca il 429 di quota con header `X-RateLimit-Scope: ai-daily-quota`, il client discrimina sull'header col testo come fallback per il rollout. **Nota sui test**: in questa suite `requests` è sostituito da un mock del conftest che non è un package e non espone eccezioni vere — un `import requests` dentro un mock di risposta dà `exceptions must derive from BaseException` e fa passare il test per il motivo sbagliato. Ogni test aggiunto è stato verificato fallire ripristinando il codice pre-fix. **Regole di dominio verificate integre in ogni percorso**: nessun fallback verso `SERVIZI E CONSULENZE`, guardrail NOTE E DICITURE ancorato a `totale_riga` in tutti e 4 i punti, soft delete rispettato nella propagazione, gerarchia admin > locale > globale intatta, auto-save solo in memoria locale (anti-contaminazione cross-tenant), nessun `__getattr__`. **Sani, non ricontrollare**: cascata P7M a 5 fallback, inversione segno TD04, guardia anti-doppione per identità naturale, mapping AI per `idx`, SSRF guard, `ContextVar`, `_build_master_canonical_map`, `multisede_routing.py`. **Gap dichiarati**: `ai_service.py:3579-3990` (trasformazioni pure di categoria, zero I/O verificato via grep — bassa priorità ma **non** dichiarato chiuso); `services/routers/riparto.py` e `fatture.py` nominati nel perimetro ma mai letti. **Deployato** (push `main` 3/8/2026 ore ~13:50, commit `54f345d`): CI verde su tutti e 3 i workflow rilevanti (Tests, OpenAPI Schema Drift Check, Requirements Consistency); Vercel non coinvolto (nessun file `apps/web/**` nel commit), worker Railway si ridistribuisce autonomamente dal push. La riga resta 🟡 finché non è fatta la passata 2 |
| 4 | AI | 🟢 | 5/7/2026 (Fable) | 2 HIGH + 4 MED + 4 LOW deployati | Ciclo chiuso |
| 5 | Performance | 🟢 | 3/8/2026 (passata read-only + **remediation stessa giornata, sera**) + **remediation MEDIUM 4/8/2026** | **Audit**: 13 findings (7 HIGH, 6 MEDIUM, 1 LOW). **Remediation**: chiusi **tutti e 4 i HIGH di correttezza/prestazioni prioritari** + la classe troncamenti sui siti realmente esposti. Suite **10227 → 10245 passed**, 0 failed, drift OpenAPI OK (193 endpoint). **DEPLOYATA in produzione il 3/8 alle 23:25** (PR #2 → merge `3215c06`): **CI verde per la prima volta su questo codice** — Tests (pytest + deno-test), OpenAPI Drift e Requirements Consistency, sia sulla PR sia su `main`. **Deploy verificato, non dedotto**: `/health` del worker Railway risponde `commit: 3215c066834f`, cioè esattamente il merge commit. **Nessun deploy Vercel** ed è corretto: i 20 file toccati sono tutti worker Python, zero sotto `apps/web/**` (il workflow `deploy-vercel.yml` filtra su quel path). Restano aperti i MEDIUM frontend/architetturali (vedi "Residui" a fondo riga) — **CHIUSA il 4/8/2026 con la seconda passata di remediation**: chiusi anche i **MEDIUM frontend/architetturali** (N+1 queue-worker, timeout route Next, render di Prezzi, code-splitting recharts). Suite **10245 → 10248 passed**, 0 failed, drift OpenAPI OK (193 endpoint), `tsc --noEmit` e `next build` puliti. La riga passa a 🟢: **nessun finding aperto**, restano solo i gap di lettura dichiarati (che sono perimetro non auditato, non difetti noti). | **REMEDIATION 3/8 sera — cosa è cambiato davvero.** **(1) HIGH#A — troncamento a 1000 righe, difetto di CORRETTEZZA già attivo sui clienti.** Nuovo helper condiviso `utils/supabase_paging.py` `fetch_all(builder)`: pagina qualunque query PostgREST già filtrata, riusando lo stesso builder (verificato sull'API reale che `range()` riscrive `offset`/`limit` e non li accumula: 9.612 righe paginate col builder riusato coincidono **ID per ID** con le stesse pagine chieste da builder nuovi). Applicato **solo ai 12 siti realmente esposti**, non ai 36 candidati dello sweep — la scala dei dati declassa il resto (lezione 11), e `admin.py:904`/`riparto_service.py:71`/`upload_handler.py:260`/`scadenziario.py:219` sono stati **letti e classificati falsi positivi** (chunk da 200, singola fattura max 250 righe, max 6 eventi per file). **Prova end-to-end del fix, non deduzione**: prima/dopo contro l'API di produzione su 4 sedi → `Da Classificare` era **assente dal filtro su tutte e 4** (30/26/25/28 categorie viste) e **ora c'è** (31/31/26/29). La misura sul DB live ha anche corretto in peggio il numero dell'audit: le sedi colpite erano **6, non 5**, e quelle che perdevano proprio `Da Classificare` erano **4**. **(2) HIGH#B/#C — troncamenti già scattati, non rischi futuri**: `gruppo.py:441` (briefing catena, max misurato **7.218 righe in un giorno**), `documenti_service.py:820` (scadenziario catena, **2.244 documenti per user** — già oltre il cap oggi), `fastapi_worker.py:4556` briefing "fatture arrivate ieri" (**3.775 righe in un solo giorno su una sede, 14 casi storici**) e `:5713` Stato di Salute (**6.299 righe in finestra 30gg**): tutti e 4 mostravano numeri sottostimati al cliente. Coperti anche `_fetch_documenti_cached` (alimenta l'intero Scadenziario), `_load_num_documento_map`, `fatture.py:247` (mesi del selettore periodo), `account.py:130`, `admin.py:2018` (**query cross-tenant, la più esposta**), `upload_handler.py:517`/`:845` (verifica post-upload: `rows_saved` troncato dichiarava salvate meno righe di quelle scritte), `riparto_service.py:350`, `prezzi.py:416`. **(3) HIGH#1 — le 14 cache inerti ora cachano davvero.** `utils/streamlit_compat.py` `make_cache` non tenta più `import streamlit` (un ramo morto che si riattiverebbe in silenzio è lo stesso difetto appena chiuso): è una cache vera su `utils/ttl_cache.py` `TTLCache`, **riusata invece di reinventata**, con la stessa interfaccia (`ttl=`, `.clear()`) così **nessuna delle 14 call-site cambia**. Due insidie trovate scrivendo la chiave, entrambe reali: il `repr` del client Supabase contiene l'**indirizzo di memoria** (ogni istanza sarebbe stata un miss → memoria occupata e zero benefici: ora gli oggetti opachi entrano nella chiave **per tipo**), e `get_fatture_cestino` riceve liste/dict non hashabili (con `hash()` una cache mancata sarebbe diventata un 500). **Le invalidazioni esistevano già** (`clear_fatture_cache` invalida 5 funzioni + 2 di `margine_service`): il codice era scritto per una cache vera, mancava solo la cache. Corretti i **docstring che affermavano il falso**: `margine_service.py:45` non dice più "cachati per 5 minuti" senza contesto ma dichiara che quella funzione **non è la strada usata in produzione** (gli endpoint chiamano `calcola_costi_automatici_per_anno_sql`, via RPC — verificato: il worker non chiama mai la variante pandas se non come fallback); aggiornato anche il commento gemello che diceva "il decoratore NON funziona". I commenti di `price_impact_service.py:367` e `tag_analytics_service.py:361` **sono diventati veri da soli** (citavano "la cache 120s" di `_carica_fatture_da_supabase`): nessuna modifica necessaria. **(4) HIGH#D — Ricette, aggregazione spostata nel database.** Nuova RPC `articoli_da_fatture` (migration `20260803230000`, `DISTINCT ON (descrizione)` ordinato per data, `SECURITY INVOKER` — nessun bypass RLS, categorie escluse passate come **parametro** perché la fonte di verità resta `config/constants.py` e il DB non deve tenerne una seconda copia divergente). **Misurato sulla sede più grande: 2.058 ms → 382 ms (5,4x), stessi identici 1.364 articoli, zero divergenze su prezzi e unità di misura.** Fallback al full-load se la RPC fallisce: il foodcost non deve mai rompersi. **Trappola incontrata e chiusa**: la prima versione della RPC tornava **1000 righe esatte** — il cap PostgREST vale **anche per le RPC che ritornano `TABLE`**, quindi stavo per reintrodurre esattamente il difetto che stavo correggendo; risolto paginando anche la RPC con `fetch_all`. **(5) Il residuo storico del 19/6 (Prezzi/Fatture full-load) è chiuso per la parte che conta**: i 5 endpoint di `prezzi.py` non avevano **nessuna** cache e ogni tab lazy rifaceva la stessa scansione. Ora condividono `_PREZZI_ROWS_CACHE` (TTL 15s, stesso valore e stessa logica di `_FATTURE_ROWS_TTL`), e soprattutto **l'invalidazione è agganciata a quella di FATTURE**: `_invalidate_fatture_rows_cache` svuota entrambe, perché leggono gli stessi dati e due pagine che divergono dopo un upload sono peggio di due pagine lente. **Misurato: aprire le 4 tab di Prezzi 21,2 s → 5,3 s** (prima tab 5,3 s a cache fredda, le successive ~0 ms). La conversione a RPC del full-load **non è stata fatta**: le misure dicono che il DB costa 11,7 ms e il 99,7% del tempo è trasporto, quindi la cache toglie 3 letture su 4 mentre una RPC avrebbe richiesto di riscrivere 5 endpoint per un guadagno sulla sola prima apertura. **(6) I test difendono il comportamento, non la forma.** Nuovo `tests/test_paginazione_e_cache_audit_performance.py` (25 test) con un fake che **si comporta come PostgREST** (tronca a `max_rows` senza errore) invece di ignorare `.range()`: verifica i bordi 999/1000/1001, che nessuna riga si perda o si duplichi, e che `Da Classificare` oltre la millesima riga resti visibile. **Verificato per mutazione**: ho rotto `fetch_all` (solo prima pagina) e `make_cache` (di nuovo no-op) → **11 test rossi su 25**; ripristinati → verdi. Allineati 3 fake pre-esistenti che non implementavano `.range()` (`test_briefing_fatture_arrivate`, `test_gruppo_fatture_arrivate`, `test_prezzi_score_fornitori`) — uno dei quali **mascherava l'errore dentro un `except` e restituiva `None` in silenzio**. — **(7) `code-reviewer` sul diff cumulativo ha trovato un difetto che avevo introdotto io, e che i 10.243 test verdi non vedevano.** Rendere reale `make_cache` aveva cachato anche `_get_cache_version_internal` (`documenti_service.py:82`), che **non è un dato ma il meccanismo di invalidazione stesso**: è la chiave con cui lo Scadenziario decide se la propria cache è scaduta, e i tre bump (`segna_fattura_pagata`, upsert/delete config fornitori) sono **read-modify-write** (`version = leggi() + 1`). **Riprodotto eseguendo il codice**, non dedotto: dopo un bump reale a 6 la funzione continuava a rispondere 5. Due danni distinti — una fattura appena segnata pagata continuava a comparire non pagata (la chiave non cambia, la cache a valle non scade), e due bump ravvicinati leggono lo stesso valore e scrivono lo stesso `version+1`, cioè **un'invalidazione persa per sempre, non ritardata**. Tolto il decoratore, con il perché scritto nel docstring, e aggiunti 2 test che **falliscono entrambi se qualcuno lo rimette** (verificato per mutazione). È il caso da ricordare: *un'ottimizzazione applicata uniformemente a 14 siti è sbagliata sul sito che governa gli altri 13.* **Sempre dal reviewer, corretti**: `_BRIEFING_CODE_VERSION` **13 → 14** (avevo cambiato i numeri di "fatture arrivate ieri" e dello Stato di Salute senza bumpare: i clienti avrebbero continuato a vedere lo snapshot con i valori sottostimati — la trappola numero uno di CLAUDE.md, presa in pieno); la spiegazione di `fetch_all` era **falsa** — `range()` non riscrive i parametri, `params.add()` li **accumula** (verificato: `offset=0&offset=1000&limit=1000&limit=1000`), e il codice funziona perché **è PostgREST a onorare l'ultimo duplicato**, garanzia del *server* non del client: commento riscritto, perché una ragione sbagliata sopravvive al refactor successivo (lezione 26); `except Exception: pass` sull'invalidazione di prezzi ora logga; `fetch_all` logga un warning quando raggiunge il cap di 50.000 (un troncamento muto è esattamente il difetto che il modulo combatte); e `account.py:132` **non filtrava `deleted_at IS NULL`** (regola di dominio #5) — difetto pre-esistente su una riga che stavo già toccando, con **334 documenti soft-deleted live su 3.420**: il contatore fatture del mese li contava. **Residui APERTI (non toccati, per scelta)**: i MEDIUM frontend/architetturali — cache per-processo vs `WORKER_WEB_CONCURRENCY=4` (l'invalidazione tocca 1 worker su 4: mitigato dal TTL corto, non eliminato; è un limite noto e già documentato in `utils/ttl_cache.py`), N+1 nel queue-worker, 39 route Next senza `AbortSignal.timeout`, `variazioni-tab.tsx` senza `useMemo`/virtualizzazione, bundle NON MISURATA (`recharts` statico, zero `dynamic()`), e i **gap di lettura dichiarati** (mobile `/m` mai letto, `ricavi.py`, `ai_service.py:3392`, `admin.py` letto ~15%). Per questo la riga resta 🟡 — **SECONDA PASSATA (4/8/2026) — chiusura dei MEDIUM.** **(1) N+1 nel queue-worker — risolto dove era davvero N+1.** `worker/queue_processor.py` chiamava `aggiorna_streak_classificazione` per OGNI descrizione del chunk, e ognuna faceva un SELECT su `prodotti_master` prima di scrivere: con chunk da 50 descrizioni erano fino a 50 round-trip di sola lettura per chunk, a ogni file caricato. Ora il chunk viene **pre-letto in 1 sola query** (`.in_("descrizione", chunk)`) e il record già noto viene passato alla funzione con il nuovo parametro `record_precaricato`. **Insidia trovata scrivendo il fix**: usare `None` come default avrebbe reso indistinguibili "non precaricato" e "precaricato ma assente" — il secondo caso avrebbe rifatto il SELECT invece di inserire il prodotto nuovo, cioè il bug che il fix doveva togliere. Risolto con una **sentinella esplicita** (`_STREAK_NON_PRECARICATO`), e i 3 test nuovi coprono entrambi i rami. **Verificato per mutazione**: forzando il SELECT anche col record precaricato, 2 test su 3 diventano rossi. Le altre call-site non cambiano (default invariato). **(2) Timeout sulle route Next — il numero dell'audit era sottostimato.** L'audit dichiarava "39 route senza `AbortSignal.timeout`". Verificate una per una: i 39 erano corretti, ma un controllo per-file (non per-regex sulla singola fetch) ne ha trovate **altre 9 che l'audit non aveva contato** — `gruppo/costi-comuni`, `riparto/regola-fornitore`, `margini/costo-personale-turni`, `margini/costo-spese-extra`, `admin/sistema/{invoicetronic,ricavi}-salute`, `workspace/{diario,inventario}`, `workspace/personale/export-mensile`. **Totale corretto: 47 route** (+ 4 file `_worker.ts` che ora ri-esportano `WORKER_TIMEOUT_MS`). Fix minimale e uniforme: solo `signal: AbortSignal.timeout(WORKER_TIMEOUT_MS)` sulla fetch, **senza toccare status code né gestione errori** — quegli helper (`workerGet`/`workerFetch`) hanno una semantica d'errore diversa (null / status fissi) e migrarci le route che propagano `res.status` reale avrebbe cambiato il comportamento verso il client per un fix che deve solo evitare l'hang. **1 route esclusa di proposito**: `home/briefing/route.ts`, che ha un commento esplicito nel codice ("nessun timeout corto qui: vogliamo aspettare che il worker si svegli") — è una scelta di design sul cold-start, non una dimenticanza, e applicare il fix ciecamente l'avrebbe rotta. **(3) `variazioni-tab.tsx` — memo che serve a qualcosa.** Sort+filtri+KPI erano ricalcolati a ogni render (anche solo digitando nella casella di ricerca). Ora `variazioni`/`sorted`/`filtered`/`categorieDisp`/`fornitoriDisp` e i 5 KPI sono in `useMemo`, la lista è **paginata a `PAGE_SIZE=100`** (stesso pattern già in produzione in `articoli-tab.tsx`) e `AlertCard` è `memo()`. **Punto non ovvio**: `memo()` da solo non sarebbe servito a niente, perché le tre callback erano create inline nel JSX (`onToggle={() => toggleCard(r)}`) e ogni render passava funzioni nuove a tutte le card. Le firme ora accettano la riga (`onToggle: (r) => void`) e le callback sono stabilizzate con `useCallback`, altrimenti la memoizzazione sarebbe stata **decorativa**. Aggiunto anche il reset di pagina al cambio filtri (restare a pagina 7 con 3 risultati mostra una lista vuota). `eslint` ha poi segnalato che `data?.variazioni ?? []` creava un array nuovo a ogni render, invalidando tutte le memo a valle: corretto anche quello. **(4) Code-splitting di recharts — fatto, ma il guadagno è piccolo e va detto.** I 5 componenti con `import ... from "recharts"` non sono stati riscritti (25 blocchi grafico sparsi: refactoring esteso e rischioso). Il taglio è stato fatto **a monte, nelle 3 `page.tsx`**, con `next/dynamic` sui componenti che importano recharts (`VariazioniTab`, `CalcoloTab`, `CopertiTab`, `AnalisiTab`, `AnalisiETagClient`): stesso effetto sul bundle, zero righe toccate nella logica dei grafici. **Errore incontrato e corretto**: la prima versione passava `ssr: false`, che in un Server Component **Next rifiuta in build** (il `tsc --noEmit` era verde — è un vincolo di build, non di tipi: il type-check da solo non basta a dire che passa). **MISURA REALE, non stimata** (metodo: `rm -rf .next && npm run build`, poi `du -sb .next/static/chunks`, confronto isolato via `git stash` delle sole 3 `page.tsx`): **3.749.227 → 3.690.467 byte, cioè −58.760 byte (−1,6%)**, chunk da 70 a 73. **È molto meno di quanto l'audit lasciasse supporre** e la ragione è probabilmente `optimizePackageImports` (già attivo in `next.config`), che faceva già buona parte del lavoro: il finding "bundle mai misurata" era legittimo, ma una volta misurata dice che qui non c'era un problema grosso. Il fix resta perché è gratis e corretto, non perché abbia spostato molto. **(5) Cache per-processo vs `WORKER_WEB_CONCURRENCY=4`: NON toccata, di proposito.** È l'unico MEDIUM lasciato aperto come scelta: risolverlo davvero significa una cache condivisa (Redis o simile), cioè infrastruttura nuova — sproporzionato per un MEDIUM già mitigato dal TTL corto e **già documentato come limite noto** in `utils/ttl_cache.py`. Va deciso come lavoro a sé, non infilato in coda a una passata. **(6) `code-reviewer` sul diff ha trovato di nuovo cio' che 10.248 test verdi non vedevano — due volte su due passate.** **(a) Il fallback del pre-fetch era finto.** Nel ramo `except` avevo scritto `_streak_precaricati = {}`: ma con la sentinella appena introdotta, `dict.get(desc)` su un dict vuoto restituisce `None`, che significa **"precaricato ma assente" = prodotto nuovo**, non "non precaricato". Quindi se il pre-fetch falliva, ogni descrizione del chunk saltava il ramo match-esatto e finiva nell'upsert: **streak azzerato a 1 e `confidence` riportata a `media` su prodotti gia' noti**, scavalcando perfino il guard `if row.get('verified'): return` che protegge i prodotti verificati a mano dall'admin. Il commento prometteva "fallback sicuro"/"streak per riga" e il codice faceva l'opposto. Corretto: il batch fallito ora vale `None` e la chiamata passa **la sentinella**, tornando davvero al comportamento pre-fix. È la stessa trappola del punto (1), ripresentata **dentro la correzione stessa** (lezione 25). **(b) Un test nuovo passava per la ragione sbagliata.** `test_streak_record_precaricato_none_...` asseriva `select_calls == 0`, ma quello non e' l'invariante: col ramo gemello, una descrizione che normalizza diversa **fa comunque** il suo lookup. Passava solo perche' avevo scelto una grafia gia' normalizzata (`"PRODOTTO NUOVO MAI VISTO"`), cioe' per caso. Riscritto su una grafia che normalizza diversa e asserendo il ramo effettivo (upsert chiamato, nessun update per match esatto) — e nel riscriverlo e' emerso che anche il fake era sbagliato (`eq()` sovrascritto restituiva sempre un record, simulando un gemello che doveva essere assente). Aggiunto `test_prefetch_fallito_non_azzera_lo_streak` a guardia di (a), **verificato per mutazione**: rimettendo `{}` diventa rosso. Suite finale **10.249 passed**. | **Il residuo del 19/6 è CONFERMATO, non chiuso**: nessuno ha convertito Prezzi/Fatture, l'unico commit di conversione resta `28b78f1` (19/6) e tocca solo la Home. **Ma la scoperta principale è un'altra**: il full-load è il problema *meno* grave di quelli trovati. — **MISURE (metodo dichiarato, lezione 19)**. Scala reale: 33.891 righe vive, 10 sedi, sede peggiore 9.612 righe. `EXPLAIN (ANALYZE, BUFFERS)` con le colonne/filtri esatti del codice: full-load 11,7 ms via Bitmap Index Scan su `idx_fatture_ristorante_id` — **il DB NON è il collo di bottiglia, e i 29 indici su `fatture` sono adeguati**. End-to-end via PostgREST con le credenziali di `.env`, wall clock: **Prezzi 4.306 ms / 2,45 MB / 10 round-trip**; **Fatture 4.711 ms / 3,95 MB / 10 round-trip**; la stessa domanda aggregata in SQL costa **13,7 ms** e la RPC `dashboard_stats_aggregata` già in produzione risponde in **227 ms / 1 KB / 1 round-trip** (mediana di 3 run). **Rapporto misurato ~19x**: il costo è **trasporto, non query** (round-trip minimo 293 ms). Le 4 tab di Prezzi sono lazy → **~4,3 s per tab aperta**, e i 5 endpoint di `prezzi.py` **non condividono cache** (a differenza di Fatture che ha un TTL 15s). — **HIGH#A — troncamento silenzioso a 1000 righe: è una CLASSE di difetti, non un caso.** `supabase/config.toml:14` `max_rows=1000` **è confermato attivo sul progetto hosted**: ho riprodotto la query esatta di `services/routers/fatture.py:758-764` contro l'API di produzione → **1000 righe, 30 categorie invece di 31, nessun errore, nessun log**. Effetto misurato sul DB live: **5 sedi su 10 perdono categorie dal filtro, fino a 5 su una sede**, e sulla sede più grande la categoria persa è esattamente **`Da Classificare`** — quella che la regola di dominio #1 di CLAUDE.md esiste per tenere visibile al cliente. **È un difetto di CORRETTEZZA emerso nella passata Performance.** Sweep sistematico (mio, indipendente): 173 `.select()…execute()` senza `.range()/.limit()/.single()`, di cui 36 su tabelle che possono superare le 1000 righe; l'agente ne ha contati 90 a rischio reale su 188 catene. **Ma la scala dei dati declassa buona parte dei candidati (lezione 11)**: `ricette` ha 5 righe, `fatture_queue` max 392/utente, e `admin.py:904` **non è un difetto** (chunka per 200 via `.in_()`, falso positivo del mio sweep corretto leggendolo). Restano rotti ORA i siti su `fatture`; `fatture_documenti` è **max 888 righe/sede = 89% del cap**, cioè una miccia con la data sopra. — **HIGH#B — `gruppo.py:441` è GIÀ scattato in produzione** (verificato sul DB live, non dedotto): il briefing di catena conta le fatture assegnate con `.in_("ristorante_id", ids)` senza `.range()` su finestra di 1 giorno; **3 clienti hanno superato le 1000 righe ingerite in un solo giorno, fino a 7.218 il 26/6** → nei giorni di carico massivo il numero mostrato era sottostimato. — **Altri HIGH da troncamento** (letti nel codice, non tutti misurati): `documenti_service.py:818-828` Scadenziario, un documento **già pagato può ricomparire come non pagato** oltre il 1000° (5 chiamanti vivi, incluso il briefing Home); `fastapi_worker.py:7596-7608` `_load_num_documento_map` (a ogni click di espansione riga in Prezzi, senza cache); `fastapi_worker.py:5198-5210` conteggio "righe da controllare" cappato a 1000 mentre **altri due punti dello stesso file fanno la stessa domanda con `count="exact"`** — tre implementazioni, una sola sbagliata; `fatture.py:245-256` mesi mancanti dal selettore periodo. — **HIGH#C — 14 funzioni dichiarano un TTL e non cachano nulla.** `utils/streamlit_compat.py:6-15`: `make_cache` prova `import streamlit`, che **non è installato per scelta** (CLAUDE.md), e ricade su `_noop`. Ogni `@_make_cache(ttl=…)` nel worker è quindi un decoratore inerte: `db_service.py` (8), `documenti_service.py` (4), `margine_service.py` (2). Il caso peggiore è `margine_service.py:39` `calcola_costi_automatici_per_anno` (costi del MOL), il cui **docstring afferma il falso** alla riga 45 ("I risultati sono cachati per 5 minuti"); idem i commenti di `price_impact_service.py:367`, `tag_analytics_service.py:361`, `documenti_service.py:551`. Solo `margine_service.py:157` dice la verità. — **HIGH#D — Ricette scarica tutta la storia**: `foodcost_service.py:181-213` (chiamante `workspace.py:163`) non ha filtro data né cache: **8.894 righe in 9 round-trip per produrre 1.493 articoli utili, spreco 6x**, a ogni apertura, e **peggiora ogni mese per costruzione**. — **MEDIUM**: cache in-process vs `WORKER_WEB_CONCURRENCY=4` (hit rate ~1/4, e `_invalidate_fatture_rows_cache` invalida **1 processo su 4** → fino a 15s di dati stantii dopo un cambio categoria); N+1 nel queue-worker (`queue_processor.py:363-375` → **3×D round-trip** per D descrizioni distinte); **39 route Next senza `AbortSignal.timeout`** (incluse tutte le `prezzi/*` e `home/*`) mentre `workerFetch` lo impone; `variazioni-tab.tsx:581-610` sort/filter a ogni render senza `useMemo` e lista non virtualizzata — **il pattern corretto esiste già** in `articoli-tab.tsx` (memo + `PAGE_SIZE=100`). — **VERIFICATO SANO, non ricontrollare**: il client Supabase memoizzato **non è regredito** (`fastapi_worker.py:916-946` + `services/__init__.py:203-210` `@lru_cache`) — era la causa vera del vecchio caso alert prezzi, e la prima ipotesi (pandas) era sbagliata; il **budget 4s dell'alert prezzi regge** (bulk + `df_precaricato`, executor condiviso); `xlsx` **è già lazy ovunque** (`await import("xlsx")` al click — mia impressione iniziale opposta, corretta verificando); Home con Suspense per blocco e `cache()` di React; Margini via RPC con fallback; nessun `time.sleep` in handler HTTP; `worker/run.py` con backoff e jitter. **`utils/ttl_cache.py` `TTLCache` (thread-safe, single-flight, già in prod a `fastapi_worker.py:5583`) è il rimpiazzo naturale di `_make_cache`**: un fix non deve inventare un quarto dict ad-hoc. — **GAP DICHIARATI (non chiusi)**: `routers/gruppo.py` letto solo in parte (**zona a priorità più alta**: in catena il cap si applica a `.in_()` multi-sede, quindi scatta a volume N volte più basso), `ricavi.py`, `riparto.py`, `ai_service.py` (memoria AI `:3392,3453` — se troncata, più chiamate GPT a pagamento), `upload_handler.py` (copertura test 11%: zona cieca doppia), `admin.py` letto ~15%, `email_queue_processor.py`, **mobile `/m` (3941 righe) solo inventariato, zero file letti**, componenti pesanti (`scadenziario-client.tsx` 2233, `margini/*.tsx`), bundle analysis **NON MISURATA** (niente `node_modules`/`.next` in locale; `recharts` è import statico in 5 componenti e **non esiste alcun `dynamic()` in tutto `apps/web`**), indici su tabelle diverse da `fatture` non verificati con EXPLAIN |
| 6 | Qualità/UI | 🟢 | 19/6/2026 | Filtro mese uniformato, sky-* → primary | commit df01a9c |
| 7 | Database | 🟢 | 30/7/2026 (audit + remediation stessa giornata; codice committato e deployato il 2/8/2026) | Audit read-only (9 findings) seguito da sessione di remediation nella stessa giornata: 2 HIGH + 4 MEDIUM + 1 LOW fixati e deployati sul DB live; 2 LOW restano aperti (non bloccanti). Suite pytest completa verde dopo i fix | **Verificato sul DB live prima di agire**: 0 righe orfane su `fatture_queue.user_id`/`ristorante_id`; `ricavi_email_queue` ha GIA' FK `ON DELETE CASCADE` su entrambe le colonne (confermato `confdeltype='c'`) — il commento in admin.py era quindi obsoleto, non il codice; nessun indice su `created_at`/GIN su `payload_meta` (confermato seq scan). **Fix applicati** (migration `20260730230000`/`20260730231500`/`20260730232500`/`20260730233000`, tutte applicate live via MCP): HIGH#1 — aggiunte FK `fatture_queue_user_id_fkey`/`fatture_queue_ristorante_id_fkey` (nullable, `ON DELETE CASCADE`): la cancellazione GDPR ora propaga automaticamente, rimossa la voce ridondante da `_SVUOTA_TABELLE_NO_CASCADE` in `account.py`, corretto il commento obsoleto in `admin.py` (rimossa anche la delete manuale ridondante su `ricavi_email_queue`). HIGH#2 — `release_stale_locks` ora passa a `dead` (non più `failed` a ciclo infinito) se `attempt_count >= max_attempts`, e rimanda `next_retry_at` di 1 minuto sul ramo `failed`; `claim_batch_for_processing` ha in più il filtro `attempt_count < max_attempts` come difesa in profondità. MEDIUM#4 — nuova RPC `purge_ricavi_email_queue` (90gg, azzera subject/attachment/last_error) + nuova funzione Python `purge_ricavi_xls_storage` in `email_queue_processor.py` che ora rimuove davvero i file dal bucket `ricavi-xls` (prima non venivano MAI rimossi). MEDIUM#5 — nuove RPC `purge_fatture_queue_last_error` (90gg su righe dead/scartata) e `purge_upload_events_retention` (365gg, hard delete). MEDIUM#6 — `_purge_xml`/`_purge_raw_body_sample` non girano più a ogni ciclo (~ogni 15s): spostate in `worker/run.py` sotto nuovo gate `WORKER_QUEUE_PURGE_INTERVAL_SECONDS` (default 6h), stesso pattern di `purge_cestino_scaduto`. LOW — grant residui `anon`/`authenticated` su `upload_events` revocati (`upload_events.id` è uuid, nessuna sequence da revocare a differenza di quanto ipotizzato nell'audit). **Aperti (non fixati, priorità bassa)**: (a) `/api/fatture/da-assegnare` legge `xml_content` di tutta la coda senza `.limit()`; (b) `resolve_unknown_tenant` su P.IVA duplicate prende la sede più recente senza disambiguare/segnalare l'ambiguità. Regole di dominio verificate OK durante l'audit: nessun fallback nascosto verso `SERVIZI E CONSULENZE`, constraint `fatture_categoria_not_empty_chk` e `fatture_note_diciture_solo_importo_zero_chk` rispettati. **Nota 2/8/2026**: le migration SQL erano già applicate live via MCP il 30/7, ma il codice Python (`account.py`, `admin.py`, `worker/email_queue_processor.py`) e le 4 migration stesse non erano mai stati committati/pushati — scoperto e corretto durante la sessione Architettura (commit `b725662`), ora genuinamente deployato |
| 8 | Architettura | 🟢 | 2/8/2026 (audit + remediation stessa sessione, 2 fasi, deployato) | Audit read-only (7 findings: 1 HIGH + 2 MEDIUM + 2 LOW + 2 INFO). Fase 1: remediation HIGH+MEDIUM (confermata esplicitamente da Mattia). Fase 2 (stessa sessione, su richiesta esplicita "chiudi prima i punti low e bassi rimasti in sospeso"): chiusi anche i 2 LOW + 2 INFO residui, poi revisionato tutto con `code-reviewer` che ha trovato e fatto fixare 2 residui indipendenti (vedi sotto). Suite pytest 10162 passed/0 failed dopo tutti i fix. **Nessun residuo aperto** | **Verificato che NON è tornato** `__getattr__` sugli helper dei router (già rotto 9 router in prod in passato): tutti i 13 router usano il wrapper esplicito `_fw()`. **Accoppiamento Next.js↔worker pulito**: 164/167 route.ts proxy dirette al worker, i 3 restanti sono legittimi (auth/me, auth/accetta-privacy via lib/auth.ts, tts stateless); `apps/web/package.json` non ha SDK OpenAI/Supabase/parsing XML-PDF, il frontend non ha nemmeno le dipendenze per fare logica pesante. **Worker-separato rispettato**: classificazione AI e parsing fatture restano solo nel worker/queue-worker. **Fix Fase 1**: HIGH — `services/fastapi_worker.py` (`_calcola_costi_auto_per_mese`/`_calcola_costi_auto_per_periodo`) usava un set hardcoded di categorie "Spese Generali" duplicato rispetto a `CATEGORIE_SPESE_GENERALI` in `config/constants.py` (già usata correttamente da `margine_service.py`/Margini) — rischio di disallineamento silenzioso Home vs Margini se la lista cambia in futuro; ora importa la costante condivisa. MEDIUM#1 — rimossa `ricalcola_prezzi_con_sconti` in `services/db_service.py` (già marcata DEPRECATED, zero chiamanti vivi verificati via grep, cadeva silenziosamente su `session_state` vuoto nel worker se richiamata) e il suo export da `services/__init__.py`. MEDIUM#2 — spostati `app_controllers.py`/`ui_helpers.py`/`sidebar_helper.py` (residui Streamlit orfani, ~2400 righe, zero chiamanti vivi oltre al proprio test) da `utils/` a nuova cartella `legacy_streamlit/` via `git mv`; aggiornati i 6 import interni fra i 3 file e le patch-string nel test; **scoperto e fixato un problema indipendente durante la verifica**: `tests/conftest.py` mocka `streamlit` solo per i test sotto `tests/` (pytest non eredita conftest da directory sorelle) — il test spostato lo aveva perso e falliva su `NoSessionContext` reale; aggiunto `legacy_streamlit/conftest.py` con lo stesso mock, ridotto al solo `streamlit` (unico modulo pesante richiesto); `pytest.ini` `testpaths` esteso a `tests legacy_streamlit` su scelta esplicita di Mattia (il test resta in CI, non solo storico). **Fix Fase 2 (residui LOW+INFO)**: LOW#1 — `NON_IGNORABILI` (duplicata carattere-per-carattere fra `mobile-briefing.tsx` e `home-briefing.tsx`) estratta in nuovo modulo condiviso `apps/web/src/lib/briefing-shared.ts`, entrambi i file ora importano da lì. LOW#2 — `services/routers/margini.py` importava direttamente `_calc_netto` da `ricavi.py` a livello di modulo (unico caso router→router diretto nel file); sostituito con un wrapper lazy locale (stesso principio di `_fw()`, import posticipato a runtime), nessun ciclo reale esistente (`ricavi.py` non importa mai `margini.py`). INFO#1 — CLAUDE.md corretto da "~7450" a "~8000" righe per `fastapi_worker.py` (reali: 8037, verificate con `wc -l`). INFO#2 — `_make_cache()` risultava triplicata, non duplicata: oltre a `db_service.py`/`documenti_service.py` (le 2 note dall'audit) esisteva una terza copia identica in `margine_service.py`, non vista prima; le tre erano byte-per-byte identiche. Unificata in nuova funzione pubblica `make_cache()` in `utils/streamlit_compat.py`, i 3 file sorgente ora importano con alias (`from utils.streamlit_compat import make_cache as _make_cache`) per non toccare le call-site esistenti. **Fix aggiuntivi trovati da `code-reviewer` sul diff cumulativo delle 2 fasi** (nessuno bloccante per l'uso in produzione, ma refusi reali): rimossa la voce `'ricalcola_prezzi_con_sconti'` residua nell'`__all__` di modulo di `services/db_service.py` (riga 2223 — distinta da quella già ripulita in `services/__init__.py` durante la Fase 1; nessun chiamante vivo con star-import verificato via grep, ma rendeva `from services.db_service import *` un `AttributeError` reale); corretto il docstring di `legacy_streamlit/app_controllers.py` che citava ancora il vecchio path `utils/app_controllers.py` e l'uso in `app.py` (rimosso dal repo il 17/7) invece del nuovo path/stato congelato; risolto uno staging Git incoerente sui 4 file spostati in `legacy_streamlit/` (erano `A`/`D` separati invece di rename riconosciuti, rischio di lasciare doppie copie su un commit futuro) con `git add` sui path sorgente per far riconoscere a Git i 4 rename. **Copertura dichiarata dall'agente audit**: services/, routers/, utils/, config/ auditati al 100%; apps/web route.ts verificate strutturalmente al 100% (167/167); lib/*.ts e componenti tsx auditati in profondità solo su un sottoinsieme mirato (~178 componenti desktop in `(app)/*` non letti riga per riga — gap dichiarato esplicitamente, da coprire in una passata dedicata se serve). Esclusi per istruzione esplicita: Database, Edge Functions, Security, DevOps/Config (già chiusi). **Deployato** (push `main`, 2/8/2026 pomeriggio, deroga esplicita all'orario): commit `6073bd6` (Architettura); nello stesso push anche `b725662`, lavoro Database del 30/7 che risultava dichiarato "deployato" ma non era mai stato committato (FK GDPR account.py/admin.py, purge_ricavi_xls_storage, 4 migration SQL) — scoperto verificando `git log` sui file prima del commit, corretto contestualmente. CI verde su tutti i workflow (Deploy Vercel, Tests, OpenAPI Drift, Requirements). Worker Railway si ridistribuisce autonomamente dal push, non verificabile da qui senza credenziali Railway — da controllare manualmente |
| 9 | Test | 🟢 | 3/8/2026 (sera — audit read-only 3 giri + remediation Fase 1 e Fase 2) | **Chiusa**: 3 HIGH (`ae620b6`) + tutti i MEDIUM/LOW (`f1d9e82`). Suite: **10195 → 10227 passed**, 43 skipped. Nessun file di produzione toccato in nessuna delle due fasi. La Fase 2 era inizialmente stata rimandata per scelta di Mattia, poi ripresa e chiusa nella stessa sessione | **Il finding centrale è una prova, non un'opinione**: ho rimosso entrambi i filtri della regola di dominio #1 da `margine_service.py:80-84` (`.neq('categoria','Da Classificare')` e `.neq('ripartita_su_gruppo', True)`) e ho rilanciato **tutta** la suite → **10195 passed, 0 failed**. La suite non difendeva il numero che il cliente guarda. Causa: `_build_query_mock` fa `query.neq.return_value = query` (i filtri non filtrano) e il dataset di test conteneva già solo righe pulite; la guardia `test_regole_dominio_guardia.py` controlla la *costante*, non la query. Fix: `_build_query_mock_filtrante` che applica davvero `.neq()`/`.is_()` + test dedicato, **verificato fallire** col codice pre-fix (food cost 1099 e 655 invece di 100; il reviewer ha aggiunto una terza mutazione non dichiarata, `.is_('deleted_at','null')` → 433, anch'essa rossa). **HIGH#2**: `controlla_rate_limit` (regola CLAUDE.md 5 tentativi → 15 min) e `verify_and_migrate_password` non erano coperti da **nessun** test — la regola era verificabile solo leggendo il sorgente. Aggiunti 8 test con `ph.verify` configurato esplicitamente: **necessario**, perché `argon2` è un `MagicMock()` nel conftest e `ph.verify('hash','password_sbagliata')` ritorna un Mock **truthy** (dimostrato), quindi un test scritto ingenuamente passerebbe con la verifica password rotta. Verificati fallire con soglia 5→50, con `ph.verify` che ingoia l'eccezione, e con `.lower()` rimosso dalla normalizzazione email. **HIGH#3**: `openapi-drift.yml` osservava solo `services/fastapi_worker.py`+`openapi/openapi.json`, ma i 193 endpoint vivono nei 12 router: i commit `b725662` e `ffdb50c` hanno toccato `services/routers/**` **senza far partire il check** (verificato su storia reale; il reviewer ha confermato via `gh run list` che per `ffdb50c` il workflow non è mai partito). Aggiunta una route sonda in un router → drift rilevato, **exit 1**: il gate funziona, era il trigger a non farlo scattare. Fix: `services/routers/**` nei `paths` di push e pull_request. **Misure oggettive prodotte** (prima non esistevano: nessun `.coveragerc`, `coverage` installato ma mai usato): **coverage reale 47%** — `upload_handler.py` **12%** (2227 righe, **0 righe di test**), `auth_service.py` 32%, `worker/run.py` 0%, `foodcost_service.py` 24%, `ai_service.py` 69%, `margine_service.py` 86%. **Correzione di scala**: i "~10195 test" non sono 10195 funzioni ma **106 file / 21.765 righe** gonfiati dalla parametrizzazione — il conteggio dei test non dice nulla sulla copertura. **I 43 skip sono benigni** e ora spiegati: 42 parametrizzati in `test_regole_dominio_guardia.py:276` (`non usa ADMIN_EMAILS`) + 1 documentato in `test_data_competenza_propagation.py:27`. **Due claim degli agenti smentite verificandole** (lezione 11): (a) "`__getattr__` usato in 11 router" → **falso**, sono 10 *commenti* che spiegano perché non va usato, tutti i router usano `_fw()`, la regola è rispettata; (b) "`verifica_credenziali` citato in 4 file di test" → i match sono in `legacy_streamlit/` + `.pyc`, e l'unico test lì **la sostituisce con una patch**. **Edge Functions Deno sane**: 108 test, 0 failed, girano davvero in CI (`tests.yml` job `deno-test`), HMAC copre 7 casi negativi su 9. — **FASE 2 (`f1d9e82`), chiude i residui**: **(1) tre cache in-process portavano dati fra un test e l'altro** senza che nulla se ne accorgesse: `_SESSIONE_CACHE` (sessione utente per token — la cache dietro l'HIGH Security del 29/7 e dietro il bug dello switch sede), `_FATTURE_ROWS_CACHE` (righe fattura per `ristorante_id`) e soprattutto **`_memoria_cache` di `ai_service`**, che contiene le categorie apprese **per utente** più `_loaded_user_ids`: se quel set sopravvive, il codice crede che l'utente sia già stato caricato, **non rilegge dal DB** e classifica con categorie ereditate da un altro test. Svuotata con la sua funzione ufficiale `invalida_cache_memoria()` e non azzerando il dict a mano, perché il contatore `version` deve avanzare o `_brand_union_cache` resta stantia. `_SUPABASE_CLIENT_CACHE` esclusa **di proposito** (memoizza un client stateless per (url,key), non dati) e la motivazione è scritta nel conftest. **(2) La guardia non si fida di una lista scritta a mano**: `test_conftest_cache_guardia.py` **scopre** le cache leggendo i sorgenti, così una cache aggiunta in futuro non può sfuggire in silenzio. Copre 4 moduli (`fastapi_worker`, `auth_service`, `routers/admin`, `ai_service`) e la regex è **case-insensitive** perché `ai_service` usa `_memoria_cache` minuscolo — una regex sul solo MAIUSCOLO avrebbe mancato proprio la cache più sensibile. Due test ausiliari sorvegliano la guardia stessa (regex degenerata, nomi morti in `CACHE_ESCLUSE`) e **hanno già intercettato un mio errore reale**: una regex allargata male che trovava **zero** cache e avrebbe reso il controllo decorativo senza dirlo. **(3)** `test_cambia_sede_invalida_cache.py` usava `except Exception`, quindi restava verde anche se la guardia 404 fosse sparita (bastava un `AttributeError` del mock): ora `pytest.raises(HTTPException)` + assert sullo status code, verificato fallire mutando 404→403. **(4)** `test_eccezioni_moduli_mockati.py` documenta e verifica il `TypeError: catching classes that do not inherit from BaseException`: sotto il conftest, `except RETRIABLE_ERRORS_PARSING` in `ai_service` **non cattura nulla** e nemmeno il `ValueError` finale (che è una classe reale) viene raggiunto, perché la tupla si valuta da sinistra. **Il codice di produzione è corretto** — il difetto è nell'ambiente di test: `openai`, `requests`, `argon2`, `xmltodict`, `supabase`, `tenacity` sono **tutti installati**, quindi la premessa del conftest ("moduli non disponibili nell'ambiente test puro") **oggi è falsa**. **(5)** `.coveragerc`: baseline **45%** con `branch = True` su 22.990 statement. **Nota di onestà sui numeri**: il 47% della Fase 1 era senza branch coverage e con `omit` diversi — **i due numeri non sono confrontabili** e la baseline da qui in avanti è 45%. Con branch coverage: `upload_handler.py` **11%**, `worker/run.py` **0%**, `foodcost_service.py` 17%, `auth_service.py` 36%, `margine_service.py` 85%, `ai_service.py` 67%. **(6) La CI copriva meno dello sviluppatore**: `tests.yml` lanciava `pytest tests/` mentre `pytest.ini` dichiara `testpaths = tests legacy_streamlit`, quindi i 9 test di `legacy_streamlit/` **giravano solo in locale** e una rottura lì non avrebbe fermato una merge. Ora il workflow lancia `pytest` senza argomenti. **Metodo**: ogni test nuovo verificato per mutazione, e le difese della Fase 1 **ri-verificate dopo** le modifiche al conftest (filtri MOL rimossi → rosso; soglia 5→50 → 2 rossi) per escludere che il nuovo conftest le avesse rese vacue |
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
- **Bug** — riga riscritta il 3/8/2026 da due passate dedicate vere (le prime:
  fino a qui era sempre stata accorpata a Security), entrambe nella stessa
  giornata, più una bonifica dati la sera stessa dopo decisione esplicita di
  Mattia. Non è più una ricostruzione a memoria e ora copre **entrambi** i
  perimetri: upload/parsing/AI (passata 1) e margini/briefing/chat (passata 2).
  🟢 senza residui bloccanti: i 5 doppioni con categoria in conflitto su
  `prodotti_master` sono stati bonificati sul DB live; resta solo il limite
  dichiarato del fix (5/7 casi futuri) come nota per la prossima volta che
  l'audit tocca questa zona.
- **AI, Qualità/UI** — righe ancora quelle ricostruite a
  memoria del 30/7, **non ancora corrette dalle sessioni originali**. Restano
  da riverificare quando quelle chat vengono riaperte.
- **Performance** — riga riscritta il 3/8/2026 da una passata read-only vera,
  con misure prese (non stimate) sul DB live e via PostgREST. Il residuo del
  19/6 era **vero** e resta aperto, ma la passata ha trovato **difetti più
  gravi del residuo stesso**, fra cui uno di correttezza già attivo sui
  clienti. **Resta 🟡 per scelta esplicita di Mattia**: la sessione è stata
  chiusa come sola consegna, senza scrivere codice. I 13 findings sono tutti
  aperti ed elencati nella riga e nella consegna qui sotto.
- **Test** — riga scritta il 3/8/2026 sera dalla sessione che ha fatto il
  lavoro (prima passata in assoluto su questa dimensione: era l'unica ⚪).
  Chiusa 🟡 **per scelta esplicita di Mattia**, non per mancanza di tempo:
  confermata la sola Fase 1 (i 3 HIGH), i MEDIUM/LOW sono elencati come
  residui nella consegna qui sotto. I numeri della riga sono misurati, non
  stimati: baseline `tests/` 10195 → 10204 dopo i 9 test nuovi, coverage 47%
  da `coverage run`, ogni test verificato fallire col codice pre-fix.
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

## Prossima sessione: `upload_handler.py` (ciclo 2026-07 chiuso, 10/10 🟢)

> Sezione viva: la sessione che prende in carico questa consegna la riscrive con
> la propria per la dimensione successiva, non la lascia stagnare qui.

**Stato al 4/8/2026**: **10/10 dimensioni 🟢**. Performance è stata chiusa in due
passate di remediation: i **HIGH il 3/8 sera** (deployati, PR #2 → `3215c06`) e i
**MEDIUM il 4/8** (dettaglio nella riga 5). **Nessun finding aperto** su nessuna
dimensione: quello che resta sono **gap di lettura dichiarati** — perimetro mai
auditato, non difetti noti — e **buchi di copertura test**, che sono lavoro di
scrittura, non di audit.

**Cosa è già stato fatto (non rifarlo).** *Passata HIGH (3/8, in produzione):*
paginazione dei 12 siti realmente esposti al cap PostgREST via
`utils/supabase_paging.py`; `make_cache` che ora cacha davvero su `TTLCache`;
RPC `articoli_da_fatture` per Ricette (2.058→382 ms); cache condivisa sui 5
endpoint di `prezzi.py` con invalidazione agganciata a FATTURE (4 tab: 21,2→5,3 s).
*Passata MEDIUM (4/8):* pre-fetch del chunk in `queue_processor.py` (via il nuovo
parametro `record_precaricato` di `aggiorna_streak_classificazione`);
`AbortSignal.timeout` su **47 route Next** (9 in più di quelle che l'audit aveva
contato) + `WORKER_TIMEOUT_MS` ri-esportato da 4 `_worker.ts`; `useMemo`/`memo` +
paginazione a 100 in `variazioni-tab.tsx`; `next/dynamic` sulle 3 `page.tsx` che
caricano recharts. Suite **10.248 verde**, drift OpenAPI OK, `tsc` e `next build`
puliti.

**Consegna per la prossima sessione — in ordine di valore:**

1. ~~**`upload_handler.py`: 1109 statement, 11% coverage, ZERO righe di test.**~~
   **CHIUSA il 4/8/2026.** Ricontato con metodo diverso (coverage mirata sui 4
   file di test che toccano il modulo, non fidandosi del numero scritto qui):
   11% confermato (1108 statement, 972 missed) — ma "ZERO righe di test" era
   la frase imprecisa, esisteva già `test_upload_handler_pure.py` (97 righe,
   3 funzioni pure). La sostanza reggeva: i due punti toccati dalla remediation
   HIGH (`:517`, `:845`, `response = query.execute()` → `rows = fetch_all(query)`)
   erano davvero scoperti. Aggiunto `tests/test_upload_handler_pagination.py`
   (7 test, riuso del pattern `FakePostgrest` già esistente in
   `test_paginazione_e_cache_audit_performance.py`) su
   `_collect_post_upload_quality_checks` e `_run_post_upload_ai_categorization`:
   verificano che con >1000 righe fake (troncamento PostgREST simulato) i
   contatori (`rows_saved`, `zero_price_rows`, `needs_review_rows`,
   `uncategorized_rows`, `rows_scanned`) vedano l'intero risultato, non solo la
   prima pagina. **Verificato per mutazione**: ripristinato temporaneamente
   `query.execute().data or []` al posto di `fetch_all(query)` su entrambi i
   punti — i test relativi sono andati rossi (1000 invece di 1500), poi
   ripristinato il fix reale (diff netto zero su `upload_handler.py`). Coverage
   del file 11% → 16% (972 → 909 statement mancanti); resta un file grande
   (2231 righe, parsing XML/P7M/PDF, dedup, orchestrazione AI a chunk) — non
   portato al 100% per scelta, fuori scope di questa consegna che era
   specificamente sui due punti della remediation Performance.
2. **Cache per-processo vs `WORKER_WEB_CONCURRENCY=4`** — l'unico MEDIUM lasciato
   aperto *per scelta*, non per dimenticanza: `clear_fatture_cache()` invalida
   **il processo che ha servito la richiesta**, non gli altri 3. Il TTL corto
   (15s) accorcia la finestra, non la elimina. Risolverlo davvero vuol dire
   invalidazione condivisa (colonna `cache_version`, già usata da
   `documenti_service`) o una cache esterna: **infrastruttura nuova**, quindi va
   deciso a mente fredda, non infilato in coda a una passata. Non abbassare
   ancora i TTL: è la scorciatoia che sembra un fix e non lo è.
3. **Zone mai lette** (gap dichiarati, non buchi scoperti dopo): `ricavi.py`,
   `ai_service.py:3392,3453` (memoria AI troncata → più chiamate GPT a
   pagamento: è l'ultimo sito plausibile della classe troncamenti che non ho
   verificato), `admin.py` letto ~15%, **mobile `/m` mai letto**.

**Modello**: audit con `oneflux-audit` (Sonnet), remediation con Opus — e
comunque solo dopo conferma esplicita di Mattia.

**Come riprodurre le misure** (perché un numero senza metodo non vale, lezione 19):
`EXPLAIN (ANALYZE, BUFFERS)` via MCP Supabase sulla sede `fd7ac484…` (9.612
righe, la peggiore), e per l'end-to-end uno script Python che legge le
credenziali da `.env` e chiama PostgREST con le colonne/filtri esatti del codice,
cronometrando le pagine da 1000 in sequenza. Per un fix di paginazione, la prova
che conta è il **prima/dopo sullo stesso dato reale** (qui: le categorie viste
dal filtro su 4 sedi), non il fatto che il codice ora chiami `.range()`.

**Portarsi dietro dalla dimensione Test.** La riga 9 è 🟢: HIGH e MEDIUM/LOW sono
tutti chiusi (`ae620b6` + `f1d9e82`). Quello che resta qui sotto **non sono
residui della dimensione**, sono **buchi di copertura** — lavoro di scrittura
test che nessun audit può fare in coda a sé stesso, e che va pianificato come
sessione propria:

- ~~`upload_handler.py`: 1109 statement, 11% coverage, ZERO righe di test.~~
  **CHIUSA il 4/8/2026** — vedi dettaglio in cima a questa sezione. Coverage
  16%, i due punti della remediation Performance ora difesi da test verificati
  per mutazione. Il file resta comunque il buco di copertura più grande del
  progetto in termini assoluti (909 statement ancora scoperti).
- **`worker/run.py`: 0%.** Il queue-worker non viene mai importato dalla suite.
- **`riparto.py`: 7 endpoint su 11 senza alcun test** (`riparto_da_fattura`,
  `riparto_manuale`, `riparto_modifica`, `riparto_duplica`, `riparto_incoerenze`,
  `gruppo_costi_comuni`, `costruisci_anteprima_righe`). Già segnalato come "mai
  letto" da due audit precedenti: ora sappiamo che non è nemmeno testato.
- **`verify_and_migrate_password`: coperto solo il ramo `$argon2`.** Il ramo
  SHA256 legacy + migrazione automatica (`auth_service.py:666-685`) resta
  scoperto, ed è quello che **riscrive `password_hash` sul DB**.
- **Ripensare il mock globale del conftest** è il lavoro strutturale che
  sbloccherebbe i rami `except`: `openai`, `requests`, `argon2`, `xmltodict`,
  `supabase`, `tenacity` sono **tutti installati**, quindi il conftest sta
  oscurando librerie reali e funzionanti. La Fase 2 ha reso il problema
  *visibile e verificato* (`test_eccezioni_moduli_mockati.py`) ma non l'ha
  rimosso: toglierlo significa rilanciare 10.000 test e sistemare le ricadute,
  che è una sessione a sé. **Chi lo farà: quel file di test diventerà rosso, ed
  è il segnale che il workaround va cancellato — non un fallimento da nascondere.**
- **`.coveragerc` non è un gate**: la baseline 45% è documentata e riproducibile,
  ma nessun workflow fallisce se scende. Trasformarla in soglia è una scelta da
  fare quando la copertura sarà salita abbastanza da non bloccare ogni PR.

**Fuori dalla dimensione Test, ma trovati qui e ancora aperti:**
- **Nessun test di regressione su `X-Reprocess-Key`** (il CRITICAL Edge Functions
  del 30/7): il canale è stato rimosso, ma nulla impedisce di reintrodurlo.
  L'idempotenza a livello DB è coperta solo da `test.ts`, script manuale
  **escluso dalla CI per design**.
- **Monitor CI che falliscono verdi**: `riparto_coerenza_check.yml` e
  `invoicetronic_eventi_sconosciuti_check.yml` fanno `exit 0` anche su HTTP != 200
  (annotazione rossa nei log, job verde). L'unico segnale è l'alert Telegram.

**Portarsi dietro dalle passate Bug** (dichiarati aperti, non chiusi in silenzio):
- **`prodotti_master`: il fix al codice copre 5 doppioni su 7 andando avanti.**
  `aggiorna_streak_classificazione` ora cerca il record normalizzato prima di
  inserire, ma `normalizza_descrizione` non collassa tutte le grafie:
  `CUORI FIL.MERL` → `FILETTOMERL` vs `CUORI FIL MERL` → `FILETTO MERL`, e
  l'asterisco di `BRODO...TTL *` sopravvive. **I 5 conflitti di categoria
  esistenti sono stati bonificati il 3/8 sera** (vince la grafia in uso reale
  nelle fatture); se in futuro l'audit trova nuovi doppioni in conflitto per
  questi due pattern di normalizzazione mancata, è il segnale che vale la pena
  estendere `normalizza_descrizione` invece di bonificare a mano di nuovo.
- `services/ai_service.py:3579-3990` — trasformazioni pure di categoria, zero
  I/O verificato via grep. Bassa priorità, ma **non** dichiarato chiuso.
- `services/routers/riparto.py` e `services/routers/fatture.py` — nominati nel
  perimetro della passata 1, mai letti. Il giro B della passata 2 li ha indicati
  di nuovo come collegati al riparto.
- `services/routers/fatture.py:850` passa ancora `volte_visto: 1`: `insert()`
  puro nel ramo "record non esiste", innocuo ma ridondante col default DB.
  Diventerebbe dannoso se convertito in `upsert`.
- Cleanup righe orfane su re-upload di fatture >2000 righe
  (`invoice_service.py:1938-1958`): la lista `numero_riga` è quella già
  troncata. Caso raro, richiede una versione precedente pre-cap.
- `_CATEGORIE_SPESE_M` (`fastapi_worker.py`) è **dead code**: il reviewer ha
  verificato che non ha consumatori. Lasciata per non allargare il diff.
- **L'agent notturno è spento** (`enabled=false` dal 30/5, mai eseguito). Il
  codice ora è corretto, ma la feature non è mai stata collaudata in produzione:
  accenderla è un collaudo, non un'ovvietà. 669 righe `needs_review` da smaltire.

**Escludere**: Bug, Database, Edge Functions, Security, DevOps/Config,
Architettura (chiuse e deployate — riaprirle solo se l'audit ci inciampa).

**Modello**: Sonnet regge l'audit read-only. Per la remediation vale §3 di
`WORKFLOW.md` (default Opus, Sonnet è l'eccezione) — e comunque solo dopo
conferma esplicita di Mattia, mai in autonomia.

**Lezioni operative (le 5 del 2/8 restano valide, più 5 dal 3/8 mattina, 5 dal 3/8 sera, 6 dal 4/8 (chiusura MEDIUM) e 7 dalla dimensione Test — 4 dalla Fase 1, 3 dalla Fase 2):**

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
11. **Un finding "grave" nel codice non è un danno in produzione finché non
    verifichi i dati.** Il 3/8 sera, **3 findings su 3 verificati sul DB live
    avevano la gravità sbagliata, sempre per eccesso**: il doppio conteggio dei
    costi di catena esiste nel codice ma le fatture ripartite stanno solo sulla
    sede tecnica, che non riceve quote; l'agent notturno "mai partito" è in
    realtà spento da maggio; le righe `Da Classificare` nel foodcost non sono
    usate da nessuna ricetta. Una query sul DB prima di scrivere il fix cambia
    priorità e comunicazione al cliente. **Non declassare mai senza la query**:
    tutti e tre restano difetti reali da chiudere, solo non urgenti.
12. **Riproduci il comportamento, non dedurlo.** L'agente aveva concluso che
    `asyncio.create_task(funzione_sync())` non eseguisse mai la funzione.
    Eseguendo 6 righe di Python si vede l'opposto: il corpo **viene eseguito**
    (bloccando), l'errore arriva dopo sul valore di ritorno. La diagnosi
    rovesciata avrebbe portato al fix sbagliato.
13. **Il perimetro dichiarato in una consegna va misurato, non creduto.** La
    consegna diceva "~5000 righe in `fastapi_worker.py`"; il perimetro reale
    era **~16.800**, perché il briefing vero vive in `daily_briefing_service.py`
    (1332 righe) che non era nominato. Scoperto cercando `_BRIEFING_CODE_VERSION`
    nel file sbagliato. `wc -l` sui file del perimetro prima di lanciare gli
    agenti costa 10 secondi ed evita un gap dichiarato a fine sessione.
14. **`grep` per "zero chiamanti" deve includere `tests/`.** `get_inbox_badge_count`
    sembrava morta e lo era nel runtime, ma **4 test la coprivano**: rimuoverla
    senza guardare avrebbe rotto la suite. Due di quei test verificavano un
    comportamento reale (isolamento fra sedi) e sono stati riscritti sulla
    funzione viva, non cancellati.
15. **Una DELETE con id letti a mano da una tabella proposta può invertirsi.**
    Il 3/8 sera, eseguendo la bonifica di `CUORI FIL MERL` appena confermata da
    Mattia, ho cancellato l'id con la categoria *giusta* (3913, PESCE) invece di
    quello sbagliato (4074, MATERIALE DI CONSUMO) — il verso nella mia stessa
    tabella era corretto, l'ho invertito solo nell'eseguirlo. Recuperato subito
    con un `UPDATE` sul record superstite, ma la riga cancellata non torna:
    su una tabella senza FK (quindi senza vincoli che avrebbero bloccato
    l'operazione sbagliata), il controllo va fatto **prima** della query
    distruttiva, non dopo — rileggere ogni id/categoria della propria proposta
    contro l'esito subito dopo l'esecuzione, non a "sembra fatto".

16. **Il modo per sapere se una suite difende una regola è romperla e rilanciarla.**
    La lezione 9 dice di far fallire ogni test nuovo; questa è la sua versione
    per i test *esistenti*. Rimuovendo i due `.neq()` da `margine_service.py`
    la suite intera è rimasta verde: 10195 test che non difendevano il MOL.
    Un mock che fa `query.neq.return_value = query` **accetta qualunque filtro
    senza applicarlo**, quindi il test verifica solo il dataset che gli hai dato,
    non la query che il codice esegue. Sospetta di ogni test DB il cui mock
    restituisce righe già pulite.
17. **Un mock che sostituisce una libreria di sicurezza rende vacuo il test che
    la riguarda.** `argon2` è un `MagicMock()`: `ph.verify(hash, 'password_sbagliata')`
    ritorna un Mock **truthy** e `VerifyMismatchError` non è nemmeno sollevabile.
    Un test "password sbagliata rifiutata" scritto senza configurare `side_effect`
    passa **sempre**, anche con la verifica rotta. Vale per `openai`, `tenacity`,
    `requests`, `fitz`: se il ramo sotto test dipende da un'eccezione tipizzata
    di un modulo mockato, il test non prova nulla — o peggio, fallisce con
    `TypeError` e il codice sotto non viene mai eseguito.
18. **Un gate CI può essere corretto e non partire mai.** `openapi-drift.yml`
    funziona (sonda → drift rilevato, exit 1), ma i suoi `paths` non includevano
    `services/routers/**`, dove vivono gli endpoint: 2 commit reali sono passati
    senza controllo. Verificare sempre **il trigger**, non solo il contenuto del
    workflow — e ricordare che una modifica a un trigger si collauda solo
    pushandola: in locale è invisibile.
19. **Il numero di test non è una misura di copertura.** "10195 test" sono 106
    file / 21.765 righe gonfiati dalla parametrizzazione. Il progetto aveva
    `coverage` installato e mai usato: 30 secondi per la prima misura reale
    (baseline **45%** con branch coverage, `upload_handler.py` all'11% e **zero**
    righe di test su 1109 statement). Prima di giudicare una suite, misurala:
    `python -m coverage run -m pytest`. **E dichiara sempre come l'hai misurata**:
    la prima misura di questa sessione dava 47% perché era senza `branch = True`
    e con altri `omit` — un numero di copertura senza la sua configurazione non
    è confrontabile con nulla, nemmeno con sé stesso una settimana dopo.

20. **Una guardia che legge una lista scritta a mano non è una guardia.** La
    fixture di reset cache elencava 6 nomi inline: `_SESSIONE_CACHE`,
    `_FATTURE_ROWS_CACHE` e `_memoria_cache` erano fuori, e nulla protestava. Il
    rimedio non è allungare la lista — è farla **scoprire dal sorgente**, così
    la cache aggiunta domani non può sfuggire. Corollario: **quando scrivi una
    guardia, scrivi anche i test che sorvegliano la guardia** (qui: "la regex
    trova davvero qualcosa" e "gli esclusi esistono ancora"). Sono serviti
    subito: una mia regex allargata male trovava **zero** cache e avrebbe reso
    il controllo decorativo restando verde.

21. **La CI può coprire meno dello sviluppatore, ed è il verso pericoloso.**
    `pytest.ini` dichiarava `testpaths = tests legacy_streamlit`, il workflow
    lanciava `pytest tests/`: 9 test esistevano, passavano in locale e **nessuna
    CI li ha mai eseguiti**. Quando un comando di CI ripete a mano ciò che la
    configurazione già dichiara, le due copie divergono in silenzio — e ci si
    accorge solo del caso in cui la CI è più permissiva, mai del contrario.

22. **Un limite di piattaforma può essere un bug di correttezza travestito da
    performance.** `max_rows=1000` di PostgREST non solleva errori: ritorna 1000
    righe e basta. Il codice a valle calcola su un sottoinsieme e produce un
    numero **sbagliato che sembra giusto** — categorie che spariscono da un
    filtro, un documento pagato che ricompare non pagato, un contatore
    sottostimato. Cercato in una passata *Performance*, trovato un difetto di
    *correttezza* già attivo sui clienti. Corollario operativo: `.select()` senza
    `.range()` su una tabella che può superare le 1000 righe è sospetto per
    definizione, e **il cap va verificato contro l'API di produzione**, non
    contro `supabase/config.toml` (che è la config della CLI locale).
23. **Misura il percorso, non la libreria.** L'`EXPLAIN ANALYZE` dice 11,7 ms e
    il wall clock end-to-end dice 4.306 ms: **il 99,7% del tempo non è nel
    database**. Senza le due misure separate si "ottimizza" la query sbagliata —
    ed è la stessa forma dell'errore del 28/7, quando il colpevole sembrava
    pandas ed era il client Supabase ricreato ogni volta. Prima di attribuire un
    costo, misura ogni tratto: query, trasporto, round-trip, rendering.
24. **Un grep che produce 173 risultati non produce 173 findings.** Il mio sweep
    ha segnalato `admin.py:904` come troncamento: leggendolo, chunka già per 200
    via `.in_()` e non può superare 200 righe. E la scala dei dati ha declassato
    metà dei candidati (`ricette`: 5 righe; `fatture_queue`: max 392). È la
    lezione 11 applicata a sé stessi: **il conteggio di un pattern è un punto di
    partenza per la verifica, non un risultato da riportare.** Vale anche al
    contrario: `fatture_documenti` a 888/1000 non è rotto oggi, ma è una miccia
    con la data sopra — va scritto come tale, non archiviato come "sano".
25. **Il fix può contenere lo stesso difetto che sta correggendo.** La prima
    versione della RPC `articoli_da_fatture` tornava **1000 righe esatte**: il
    cap PostgREST vale anche per le RPC che ritornano `TABLE`, non solo per le
    `.select()` sulle tabelle. Me ne sono accorto solo perché ho **confrontato il
    risultato con quello vecchio** invece di guardare il tempo: era 11x più
    veloce *perché* restituiva meno dati. Per un fix di performance la misura
    del tempo non basta mai — serve l'uguaglianza del risultato.
26. **Prima di costruire su un'assunzione sul comportamento di una libreria,
    verificala.** Avevo scritto nella docstring di `fetch_all` che `range()`
    "sovrascrive" i parametri; leggendo `postgrest` ho visto `params.add(...)`,
    che **accumula** — l'assunzione era sbagliata. Il codice funzionava lo
    stesso, ma per un motivo diverso da quello che avevo scritto: un commento
    che spiega la ragione sbagliata è un errore che sopravvive al refactor
    successivo. Verificato contro l'API reale (9.612 righe, ID per ID) e
    riscritta la spiegazione.
27. **Una cache che si attiva per la prima volta è un cambiamento di
    comportamento, non un'ottimizzazione.** Rendere reali 14 `@_make_cache`
    inerti significa introdurre dati potenzialmente stantii dove prima erano
    sempre freschi: prima di farlo va verificato **che le invalidazioni
    esistano** (qui sì: `clear_fatture_cache` era già scritta per una cache
    vera) e **cosa entra nella chiave** (il `repr` di un client Supabase
    contiene l'indirizzo di memoria: la cache non avrebbe mai colpito, occupando
    memoria per nulla).
28. **Un'ottimizzazione applicata uniformemente sbaglia sul sito che governa gli
    altri.** Rendere reale `make_cache` ha cachato anche
    `_get_cache_version_internal`, che non e' un dato ma **il meccanismo di
    invalidazione**: con i bump fatti in read-modify-write, due chiamate
    ravvicinate leggono lo stesso valore e ne perdono uno **per sempre**. Prima
    di applicare un cambiamento a N call-site identiche, chiedersi se una di
    quelle N e' l'infrastruttura delle altre. **La suite era verde (10.243) e non
    lo vedeva**: l'ha trovato `code-reviewer` sul diff — il passo che continua a
    trovare cio' che audit e remediation non vedono (vale anche per la riga 3).
29. **Un branch di feature non fa girare la CI: 10.245 test verdi in locale non
    sono un gate.** `tests.yml` e `openapi-drift.yml` scattano su push a
    `main`/`progetto` **o su `pull_request`**. Il 3/8 il codice era committato e
    pushato su `fix/audit-performance-remediation` e **zero workflow erano
    partiti** — lo stato sembrava verificato e non lo era. La CI e' partita solo
    aprendo la PR (#2), ed e' allora che ha girato **per la prima volta** su
    questo codice. Ordine corretto, e non e' burocrazia: **PR → CI verde →
    merge**, mai push diretto su `main` per "saltare un passaggio", perche' e'
    esattamente il passaggio che ti dice se il codice regge fuori dalla tua
    macchina. Corollario verificato lo stesso giorno: **il deploy va provato, non
    dedotto** — `/health` del worker espone il commit (`3215c066834f`), quindi
    "Railway ha ripreso il codice nuovo" e' un fatto controllabile in un secondo,
    non una speranza (vale anche per il caso opposto: Vercel **non** e' partito,
    ed era giusto cosi', perche' nessun file sotto `apps/web/**` era toccato).
30. **`tsc --noEmit` verde non vuol dire che builda.** Il code-splitting di
    recharts e' passato al type-check con `dynamic(..., { ssr: false })` in tre
    `page.tsx`, ed e' esploso in `next build`: **`ssr: false` non e' consentito in
    un Server Component**. E' un vincolo del framework, non dei tipi, e nessun
    type-checker poteva vederlo. Per le modifiche a `apps/web`, il gate vero e'
    `npm run build`, non `tsc`.
31. **Il conteggio di un finding va ricontato con un metodo diverso da quello che
    l'ha prodotto.** L'audit diceva "39 route senza `AbortSignal.timeout`" e i 39
    erano giusti — ma un controllo **per-file** invece che per-singola-fetch ne ha
    trovate **altre 9**, mai contate. (La mia prima regex di verifica, per contro,
    produceva 2 falsi positivi su file che il timeout ce l'avevano gia': una
    graffa letterale dentro `body: "{}"` chiudeva il match troppo presto.) Quando
    un numero e' il perimetro di un fix, va prodotto due volte in due modi
    diversi, altrimenti si chiude una dimensione lasciandoci dentro il 20%.
32. **`memo()` senza callback stabili e' decorazione.** Memoizzare `AlertCard` non
    avrebbe evitato **nessun** re-render finche' il JSX passava
    `onToggle={() => toggleCard(r)}`: props-funzione nuove a ogni render, quindi
    confronto sempre fallito. Il fix vero e' stato cambiare le **firme**
    (`onToggle: (r) => void`) e stabilizzare con `useCallback`. Stessa famiglia:
    `data?.variazioni ?? []` creava un array nuovo a ogni render e invalidava
    tutte le `useMemo` a valle — l'ha trovato `eslint react-hooks/exhaustive-deps`,
    non io. Una memoizzazione va verificata su cosa **cambia identita'**, non
    sull'aver scritto la parola `memo`.
33. **Una misura onesta puo' dire che il finding valeva poco, e va scritto lo
    stesso.** Il code-splitting di recharts ha spostato **58.760 byte (−1,6%)**:
    misurato davvero (`rm -rf .next && npm run build`, `du -sb .next/static/chunks`,
    confronto isolato con `git stash` delle sole 3 `page.tsx`), non stimato. Il
    finding "bundle mai misurata" era legittimo — ma una volta misurata dice che
    li' non c'era un problema grosso, probabilmente perche' `optimizePackageImports`
    faceva gia' il lavoro. Il fix resta perche' e' gratis e corretto, **non**
    perche' abbia spostato molto: gonfiare il risultato a posteriori avrebbe
    inquinato il documento per la prossima sessione.
34. **La sentinella risolve un'ambiguita' e ne crea una nuova nel ramo d'errore.**
    Distinguere "non precaricato" da "precaricato ma assente" con
    `_STREAK_NON_PRECARICATO` era corretto — ma nel `except` del pre-fetch avevo
    scritto `_streak_precaricati = {}`, e `{}.get(desc)` da' `None`, cioe' il
    **secondo** significato. Risultato: un pre-fetch fallito avrebbe azzerato lo
    streak e scavalcato il guard `verified` su prodotti gia' noti. Il commento
    diceva "fallback sicuro", il codice faceva il contrario. **Quando introduci
    una sentinella, il primo posto da rileggere e' il ramo che gestisce
    l'errore**: e' quello che nessun test felice percorre. L'ha trovato
    `code-reviewer` sul diff — **due passate su due** (vedi lezione 28).
35. **Un finding va chiuso, o dichiarato non-si-fa, ma non "quasi".** Dei 5 MEDIUM,
    4 sono stati fixati e 1 (cache per-processo vs 4 worker) e' rimasto aperto
    **per scelta esplicita**: risolverlo vuol dire infrastruttura nuova, cioe' una
    decisione, non una riga di codice. Un residuo scritto come decisione con la sua
    ragione e' informazione; lo stesso residuo lasciato implicito diventa, tre
    sessioni dopo, "non lo sapevamo".
36. **La suite intera puo' fallire dove i singoli file non falliscono, e non e'
    detto che sia il tuo diff.** Il 4/8, lanciando `pytest tests/` per intero con
    coverage, 84 test in 7 file (`test_prezzi_score_fornitori.py`,
    `test_tag_analytics_service.py`, ecc. — nessuno tocca `upload_handler.py`)
    sono andati rossi; rilanciati singolarmente, tutti verdi. E' inquinamento
    da ordine/stato condiviso fra file, non una regressione introdotta qui:
    verificato PRIMA di scrivere codice, per non inseguire un fantasma. Non
    approfondito oltre (fuori scope), ma **non e' piu' vero che la suite e'
    "10249 passed/0 failed" lanciata tutta insieme con coverage** — lanciata a
    sottoinsiemi mirati si', per intero no. Da investigare in una sessione
    dedicata se conta ancora come garanzia end-to-end prima del prossimo deploy
    grosso.

## Chiusura del ciclo (quando tutte le righe sono 🟢 o 🟡 con nota esplicita)

Quando anche l'ultima dimensione è chiusa:
1. Aggiungere in cima al documento una riga "**Ciclo chiuso il gg/mm/aaaa**"
2. Spostare il file in `docs/storico/` (stesso posto dove sta lo storico del
   progetto — es. diagnosi Invoicetronic, migration legacy)
3. Se parte un nuovo ciclo di audit, crearne uno nuovo con la data corrente
   nel nome (es. `AUDIT_ONEFLUX_STATO_2026-10.md`) — non riusare questo file
