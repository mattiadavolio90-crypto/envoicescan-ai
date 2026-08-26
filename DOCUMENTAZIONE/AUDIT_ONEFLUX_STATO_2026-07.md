# Stato audit ONEFLUX — ciclo 2026-07

**Tutte e 10 le dimensioni sono 🟢, tutte con seconda passata e `code-reviewer`.**
§1 e §3b sono vuote. Restano **§2** (copertura test da scrivere: il mock globale
di `conftest.py`) e **§3c** — la lettura sistematica del frontend, aperta il
25/8/2026 dopo la chiusura di §3b, stesso gap che §3b aveva già chiuso lato
Python.

> ⚠️ **§3c non è più "solo copertura": la prima passata (25/8) ha trovato 39
> findings, 21 attivi su clienti reali e 7 HIGH attivi.** Il frontend non è un
> layer a basso rischio perché la logica di dominio sta nel worker: i difetti
> nascono nel *consumo* di quella logica. **Tutti e 7 gli HIGH sono corretti**:
> 4 il 25/8 (STORICO §26), gli ultimi 3 il 26/8 (STORICO §27). **E 14 dei 15
> MEDIUM/LOW** il 26/8 (STORICO §28 — erano 15, non 14: errore di somma).
> Resta **1 solo MEDIUM**, che richiede una migration sulle RPC di catena.
> Dettaglio dell'audit in STORICO §25.

> ⚠️ **"10 dimensioni verdi" non vuol dire "app analizzata al 100%".** Una
> dimensione è verde rispetto al perimetro *che quella passata si è scelta*, non
> rispetto al codice esistente. Misurato l'8/8: l'app è ~103.000 righe
> (53.000 Python + 49.600 TypeScript), e §1 ne ha lette in profondità ~30.000.
> Il conto onesto è in §3b. Questo non invalida il lavoro fatto — invalida solo
> la lettura "tabella verde = finito".

> **Dov'è il dettaglio.** Questo file dice *cosa manca*, in un minuto.
> Il dettaglio verificato di ogni passata — perimetro, findings, numeri
> misurati, errori corretti in corsa, le 36 lezioni operative — sta in
> **`AUDIT_ONEFLUX_STATO_2026-07_STORICO.md`**, stessa cartella.
> Aprilo quando riapri una dimensione e vuoi sapere cosa è già stato guardato.

Legenda: 🟢 chiusa · 🟡 residui aperti · ⚪ mai fatta.

| # | Dimensione | Stato | Ultima passata | In una riga |
|---|---|---|---|---|
| 1 | Security | 🟢 | 29/7 | 3 passate + follow-up; 1 CRITICAL (scrittura cross-tenant) + 2 HIGH fixati e deployati |
| 2 | Edge Functions | 🟢 | 4/8 (2ª) | 13/13 file riletti; HIGH nuovo (race rete-sicurezza ↔ claim worker) fixato — PR #5 |
| 3 | Bug | 🟢 | 3/8 (2 passate) | ~16.800 righe (non 5.000 come dichiarato); 2 HIGH + bonifica `prodotti_master` sul DB live |
| 4 | AI | 🟢 | 4/8 (2ª) | HIGH guardrail NOTE + bug preesistente: l'UPDATE su `fatture` falliva **sempre**, in silenzio — PR #6 |
| 5 | Performance | 🟢 | 3/8 + 4/8 | Il cap PostgREST 1000 righe era un difetto di **correttezza** già attivo sui clienti, non di performance |
| 6 | Qualità/UI | 🟢 | 4/8 (2ª) | Rischio più basso confermato; 1 MEDIUM reale (select morto in Admin) fixato — PR #11. **Gap dichiarato dalla passata stessa: 11 file grandi letti solo per grep mirato → §3c, aperta 25/8** |
| 7 | Database | 🟢 | 30/7 (deploy 2/8) | Migration live ma codice Python mai committato per 3 giorni — da lì la lezione 1 |
| 8 | Architettura | 🟢 | 2/8 | 2 fasi, deployato; `code-reviewer` introdotto qui per la prima volta |
| 9 | Test | 🟢 | 3/8 | La suite **non difendeva il MOL**: rotta la regola, 10.195 test restavano verdi |
| 10 | DevOps/Config | 🟢 | 30/7 | `openapi-drift.yml` corretto ma con trigger che non includeva `services/routers/**` |

---

## §1 — Perimetro mai letto (priorità alta)

**VUOTA dall'8/8/2026.** I 3 file rimasti sono stati letti al 100% (10.442
righe totali: 5212+3010+2220) e chiusi nella stessa sessione. Riepilogo: 0
CRITICAL, 3 HIGH (tutti confermati **attivi** sul DB live, non teorici — vedi
sotto), 8 MEDIUM, 6 LOW/INFO.

**I 3 HIGH sono stati fixati l'8/8/2026, più il MEDIUM di privilege
escalation.** Ogni fix è coperto da test nuovi (26 in 3 file) e ogni test è
stato verificato **per mutazione**: rimosso il fix, il test cade; ripristinato,
torna verde. Non è una formalità — il test sul febbraio riproduce l'errore
esatto (`day is out of range for month`), e quello sull'ordine SELECT/UPDATE
cade anche se il risultato resta giusto per caso. Suite completa: 10.633
passed, 0 failed; coverage **50.41% → 50.72%** (gate 45 tenuto; misurato con
`coverage json`, non l'arrotondamento del report a schermo).

**DEPLOYATO l'8/8/2026** — PR #18, merge `de54a1e`, CI verde su tutti e 4 i
check (pytest, deno-test, check-drift, verify-requirements). Worker Railway
verificato su `/health`: `commit = de54a1ed2a50`, cioè il merge stesso. Il fix
febbraio riapre 3.178 righe di fatture di febbraio 2026 che quella finestra non
poteva leggere. Deploy in orario di lavoro su ordine esplicito di Mattia
(deroga alla regola sera/notte, registrata qui perché la regola resta).

**Il `code-reviewer` ha bocciato la prima versione del fix, a ragione.** Avevo
invalidato la cache per-ristorante partendo dal `ristorante_id` di **una sola**
riga (`.limit(1)`), sull'assunto che un gruppo della coda appartenesse a una
sede sola. Falso e non verificato: la coda raggruppa per *descrizione* su tutti
i clienti, e sul DB live **47 gruppi su 264 sono cross-ristorante, fino a 5
sedi** — il fix ne sistemava una e lasciava le altre 4 stantie, cioè riproduceva
il difetto che diceva di chiudere. Ora si invalidano tutti i `ristorante_id`
distinti. È lo stesso errore di metodo già in memoria: **una premessa sul
perimetro va interrogata sul DB prima di scriverla nel codice**, non solo la
severità di un finding.

~~`services/ai_service.py:3392,3453` e `:3579-3990`~~ — **LETTO l'8/8/2026**,
5212/5212 righe. Il riferimento `file:riga` ereditato dal ciclo precedente era
**sbagliato**: quelle righe sono innocue (guardia argomenti, estrazione dict).
Il vero difetto della classe "troncamenti" era altrove nello stesso file, mai
letto neanche lì: `_chiama_gpt_classificazione` (4736-4902) non legge mai
`finish_reason` — un JSON valido ma incompleto (risposta tagliata a
`max_tokens` senza errore) non viene distinto da "il modello ha ignorato
alcuni articoli", e i due richiedono correzioni opposte. **Confermato attivo
sul DB**: `ai_usage_events`, 1 evento reale con `completion_tokens = 4096`
(cap esatto) su `batch_size: 50`, 11/4/2026 — non è solo un margine stretto,
è già successo. HIGH — **FIXATO l'8/8/2026**: `finish_reason == "length"` ora
logga batch_size e max_tokens. Nota di rettifica rispetto alla lettura iniziale:
il comportamento era già **sicuro** (gli idx mancanti finiscono in
`Da Classificare`, nessuno slittamento di categoria — verificato eseguendo il
codice pre-fix, che logga "2 non mappati, NESSUNO slittamento"). Il difetto era
di **diagnosticabilità**, non di correttezza: la causa era invisibile e sembrava
incapacità del modello, mentre il batch era solo troppo grande. La severità
HIGH resta corretta sul rischio operativo — righe non classificate senza che
nessuno sapesse perché — ma non c'erano dati sbagliati in produzione.
Test: `tests/test_ai_service_troncamento.py` (4). Un secondo MEDIUM: il loop di retry (5028-5057) ritenta
via GPT anche le righe che il modello ha rifiutato consapevolmente
(prompt vieta esplicitamente `Da Classificare`), spesa evitabile perché solo
il safety net deterministico a valle può davvero recuperarle. Terzo, MEDIUM:
zero test sul troncamento (`finish_reason`, `content=None` mai mockati in
tutta la suite). Regole di dominio #1 e #2 verificate rispettate su tutti i
rami: nessun fallback nascosto verso una categoria inventata.

~~`services/routers/admin.py`~~ — **LETTO l'8/8/2026**, 3010/3010 righe (49
endpoint mappati meccanicamente, 48/49 con `_verify_admin`; il 49° è
intenzionale e documentato, chiamato da GitHub Actions). Due HIGH:
(1) `admin_qualita_classifica` legge la categoria "precedente" per l'audit
log **dopo** aver già scritto quella nuova (`:987` rilegge righe appena
aggiornate da `:984`) — l'endpoint "Annulla" della coda categorie non annulla
nulla, riscrive la stessa categoria appena data. Bug **confermato leggendo il
codice** (`:987` rileggeva le righe già aggiornate da `:984`).
**Rettifica sull'evidenza**, segnalata dal `code-reviewer`: le "51 righe su 51
con `categoria_da = categoria_a`" citate al primo giro **non sono la prova** di
questo bug. Sono tutte `azione = 'auto_review'`, l'unica azione presente in
`ai_review_log`, e lì l'uguaglianza è **deliberata** — il ramo sconti logga
`(cat, cat)` di proposito (`admin.py:1331`). Di `azione = 'classifica'` non
esiste nessuna riga: l'endpoint bacato non era ancora mai stato loggato. Il
difetto era reale e va fixato lo stesso, ma la severità andava argomentata sul
codice, non su quel numero. Terza volta in questo ciclo che un conteggio viene
letto come conferma di ciò che si stava già cercando.
(2) Nessuno dei 5 percorsi che scrivono `fatture.categoria`/`needs_review`
in questo router invalida la cache briefing — stesso difetto, stesso
meccanismo, del caso già chiuso il 7/8 su `ricavi.py`: l'admin bonifica la
coda, il cliente in Home vede il numero vecchio fino a 30 minuti.
**Entrambi FIXATI l'8/8/2026**: la lettura di `categoria_da` spostata prima
dell'update (il test difende l'**ordine** delle operazioni, non solo il valore,
così una futura rilettura post-update ricadrebbe); invalidazione aggiunta su
tutti e 5 i percorsi — su **tutti** i `ristorante_id` distinti coinvolti dagli
ids (vedi la rettifica in testa a §1: i gruppi sono cross-sede), e globale in
`admin_auto_review`, che itera su tutti gli account. Verificato sul DB che
`ristorante_id` è sempre valorizzato (537/537 righe con `needs_review = true`),
ma il ramo senza rid resta e fa un clear globale: mai un no-op silenzioso.
4 MEDIUM, incluso un
vettore di privilege escalation **anch'esso fixato**: `admin_cambia_email` e
`admin_crea_cliente` ora rifiutano (403) un'email presente in `ADMIN_EMAILS`
per un account cliente — mancava in **due** punti, non solo in quello trovato
per primo. 4 LOW/INFO. Test: `tests/test_admin_qualita_fix_audit.py` (8).
Dettaglio in STORICO.

~~`services/routers/gruppo.py`~~ — **LETTO l'8/8/2026**, 2220/2220 righe
(era "letto in parte"). Un HIGH **attivo**, non latente: "Spreco per
categoria" calcola l'ultimo giorno del mese **indovinando** invece di usare
`calendar.monthrange` (come fa correttamente un'altra funzione nello stesso
file, `:2122`) — per febbraio produce sempre `AAAA-02-29`, che non esiste
negli anni non bisestili (2026 incluso, cioè ora). Postgres rifiuta la
query, l'errore viene inghiottito in silenzio, il cliente vede "zero spreco"
invece di un errore. **Riprodotto sul DB live** (sede SUSHILAND):
`2026-02-29` → APIError 22008; `2026-02-28` → 24 righe reali.
**FIXATO l'8/8/2026** con `calendar.monthrange`, allineandolo a `:2122` dello
stesso file. Test: `tests/test_gruppo_spreco_categorie_febbraio.py` (12,
parametrizzati su anni bisestili e non + tutti i 12 mesi) — sul codice pre-fix
cadono con `ValueError: day is out of range for month`, cioè riproducono la
causa esatta e non un sintomo. Rivalutazione del rischio latente §1 originale: le 8 query
`.in_()` multi-sede **confermate** al margine già scritto (~33-84 sedi contro
le 4 di SUSHILAND, MEDIUM/LOW), ma trovato un rischio latente **più vicino**
non ancora documentato — `gruppo_spesa_pivot` con `dimensione="fornitore"`
è una RPC SETOF col cap PostgREST 1000 righe non paginata: già a 273 righe
su 4 sedi con l'anno solo parziale, soglia reale stimata ~10 sedi (MEDIUM).

~~`services/routers/riparto.py` + `fatture.py`~~ — **CHIUSI e DEPLOYATI il 5/8/2026**
(PR #14, merge `5d69fe3`, worker Railway verificato su `/health` = commit deployato).
2 HIGH + 2 MEDIUM + gap residuo (RPC transazionale `sostituisci_quote_riparto`
per `riparto_modifica`) fixati; LOW/INFO documentati. Dettaglio completo in
STORICO §11.

~~`services/routers/ricavi.py`~~ — **CHIUSO e DEPLOYATO il 7/8/2026** (PR #15,
merge `a601991` su `main`, worker Railway verificato su `/health` = commit
`a60199179859` servito). 0 HIGH. Un solo difetto **attivo**: 4
percorsi di scrittura su 5 non invalidavano la cache KPI Home, e il cliente
vedeva il MOL vecchio fino a 2 minuti dopo aver caricato i ricavi. 3 latenti
fixati (coerenza fonti in `coperti-analisi`, paginazione, conteggio import).
Due correzioni di rotta valgono più dei findings: un HIGH dell'agente
**declassato** dai dati (le righe incriminate avevano `coperti = NULL`, già
scartate a valle), e la divergenza `margini_mensili` vs override su 15 mesi/17
— che sembrava il difetto più grave del ciclo ed è **by-design**, difesa da 6
siti di lettura. Dettaglio in STORICO §13, lezioni 38 e 39.

~~`worker/email_queue_processor.py`~~ — **LETTO e fixato il 7/8/2026** (PR #16,
merge `de580ae`). 538 righe, chiude il flusso ricavi end-to-end. **Nessun
difetto attivo**: il DB li ha declassati tutti (unico mittente, 61 record in
coda tutti `done` al primo tentativo, import alle 03:03 contro un TTL di 2
minuti, mapping a 5 righe contro un cap di 1000, zero record appesi). Fixati i
due a basso rischio: mancata invalidazione delle cache dopo l'upsert
(asimmetria coi 5 percorsi del router — LOW: dal queue-worker l'invalidazione
KPI **non attraversa il confine di processo**, quella del briefing sì) e mappa
ragione sociale letta senza filtro (MEDIUM latente). Restano documentati e
**non fixati**: ramo retry mai esercitato in produzione (verificare `now()`
come stringa PostgREST richiede una scrittura sul DB live), stato
`unknown_sender` previsto dallo schema e mai usato, record appeso in
`processing` se fallisce il mark-done, `imported_rows` ottimistico,
duplicazione dei parser rispetto al router (refactor su codice a copertura
zero: prima i test di caratterizzazione). Dettaglio in STORICO §14.

~~`services/routers/margini.py`~~ — **CHIUSO e DEPLOYATO il 6/8/2026** (commit
`516df5e`, worker Railway verificato su `/health` = commit deployato). 0 HIGH
(le difese esistenti reggevano), 2 MEDIUM fixati: Analisi Centri/Avanzata non
escludeva le righe `ripartita_su_gruppo=True` sulla sede tecnica; le RPC
`costi_automatici_mensili[_gruppo]` classificavano FOOD con whitelist chiusa
invece del catch-all del fallback pandas (regressione silenziosa già avvenuta
il 14/7). LOW/INFO documentati. Dettaglio completo in STORICO §12.

## §2 — Copertura test (lavoro di scrittura, non di audit)

Nessun audit può farlo in coda a sé stesso: va pianificato come sessione propria.

- ~~**L'invariante dell'override mensile non ha una guardia**~~ — **CHIUSA il
  7/8/2026** (PR #16). Non era un rischio futuro: **i lettori distratti erano
  già due e attivi**. Il chat alert (`fastapi_worker.py:2940`) diceva a OFFSIDE
  *"Fatturato/ricavi non registrati"* su 6 mesi 2026 da 54.000-75.000 € che il
  cliente aveva inserito; il briefing (`:5301`) non mostrava mai la card "mese
  senza costi" a queste sedi. Il conteggio «6 siti» era **sbagliato**, e la
  correzione a «13» scritta la prima volta era sbagliata anche lei: ricontato
  con grep indipendente + `code-reviewer`, i chiamanti reali sono **17** a
  `_load_mensile_overrides` + 3 a `_merge_override_mensile` + 2 a
  `_overrides_mese_sede` = **22 punti d'invocazione** su 4 file. Guardia
  scritta (Regola 6 in `tests/test_regole_dominio_guardia.py`), ancorata
  ai **campi di ricavo** e non alla tabella — ancorarla alla tabella produce 8
  falsi positivi, misurati. Dettaglio e lezioni 40-41 in STORICO §14.
- **`services/upload_handler.py`** — **codice vivo COPERTO il 7-8/8/2026** (PR #17),
  legacy escluso per scelta. Il «909 statement scoperti» scritto qui era **sbagliato**
  (misurato: 981/1108), ma soprattutto il numero aggregato **nascondeva la cosa
  che contava**: il file è due mondi. Split misurato dal report JSON di coverage:
  **codice vivo** (righe 1-892: dedup, lock upload, gating AI — importato dal
  worker di produzione, `fastapi_worker.py:2125`) = 465 statement, 339 scoperti;
  **legacy** `handle_uploaded_files` (893-2231, raggiungibile SOLO da
  `legacy_streamlit/app_controllers.py:1659`) = 643 statement, **642 scoperti**.
  Cioè il **65% del "buco più grande del progetto" era codice che nessun cliente
  esegue**. Coperto il vivo: 339 → **15 scoperti (97%)**, +70 test. I 15 residui
  sono rami `except` di conversione numerica. Il legacy resta scoperto per scelta:
  testarlo non difende nulla che i clienti tocchino, e sparisce da sé quando
  `legacy_streamlit/` verrà rimosso. **La voce NON è barrata**: chiuderla del
  tutto vorrebbe dire dichiarare coperto anche il legacy.
  Il valore vero non è la percentuale ma *cosa* difende: il ramo di gating
  (585-810) era a **copertura zero** pur avendo già dei test — quelli esistenti
  usavano di proposito righe con `descrizione: ""`, che non entrano mai nel ramo
  che chiama l'AI e scrive la categoria. Ora sono difese entrambe le regole di
  dominio: #2 con **due** guardrail distinti (pre-AI riga 585, e quello dentro il
  loop AI a riga 712) e #1 col principio 24/06. Il guardrail 712 si raggiunge per
  **due** strade, perché `categoria_target = force_categoria or categoria_finale`:
  la seconda è **la risposta dell'AI**, quindi ci arriva un prodotto qualunque se
  il modello risponde `NOTE E DICITURE` — ed è lo scenario più probabile in
  produzione. `FUSTI`/`CASSA 750/LITRO X12` (da `_PURE_DICITURE_EXACT`) coprono
  solo l'altra strada, quella via `force_categoria`. **Prima passata avevo scritto
  qui che erano "le uniche": era falso**, trovato dal `code-reviewer`. L'errore non
  era la forza bruta ma il suo perimetro — avevo fissato `categoria` come input
  e dimenticato il ramo `or` che rimette in gioco la categoria AI. Lezione: una
  ricerca esaustiva è esaustiva *solo sul dominio che le dai*. Ora c'è un test
  per ciascuna delle due strade.
  **Mutazione verificata su 7 rami, non dedotta** — 7 su 7 intercettate:
  guardrail NOTE (filtro `_row_importo == 0` rimosso) → 3 rossi; gating 24/06
  (`elif True`) → 5 rossi, incluso quello che impedisce a una categoria scartata
  di entrare in memoria e diventare "verità" al prossimo upload; guardrail 712
  disattivato → 1 rosso; filtro cross-tenant di `_find_existing_saved_ok_events`
  → 1 rosso; paginazione (`fetch_all` → `.execute()`) → 2 rossi; **`.eq('user_id')`
  rimosso dalla SELECT → 1 rosso**; `filter_active()` rimosso → 1 rosso;
  `.in_('file_origine')` rimosso → 1 rosso. Le ultime tre erano scoperte alla
  prima passata: il fake Supabase *registrava* i filtri senza applicarli, quindi
  una perdita di isolamento multi-tenant **in lettura** sarebbe passata verde.
  Ora `_FakeQuery` filtra davvero (eq/in_/`deleted_at`) e le righe di prova
  includono un secondo utente, un altro file e una riga soft-deleted — senza
  quelle, il filtro non ha nulla da escludere e il test resta vacuo comunque.
- ~~**`worker/run.py`** — 0%, mai importato dalla suite~~ — **CHIUSA l'8/8/2026**.
  Misurato prima di scrivere: confermato 0% ("Module worker.run was never
  imported"). Nessun refactoring: il `while True` di `main()` si esce facendo
  sollevare una sentinella `BaseException` da `time.sleep` mockato dopo N
  iterazioni — file entry point, nessun chiamante da servire con
  un'interfaccia più testabile. 36 test nuovi (`tests/test_worker_run.py`),
  coverage 0% → **93%**. Il corpo di `main()` non era "banale attorno a
  funzioni già coperte" come ipotizzato: conteneva backoff esponenziale con
  jitter su errore mai verificato, sleep adattivo (1s se `batch_claimed>0`
  altrimenti poll interval), 3 gate temporali indipendenti
  (`time.monotonic()`) per purge/retention mai testati — proprio la classe di
  bug già avvenuta nell'audit DevOps/Config del 30/7 (init a 0.0 rimandava il
  primo giro di ore) — e il killswitch `WORKER_ENABLED=0` legato
  all'incidente reale 9-11/6 (coda ricavi bloccata). Prima trappola:
  `_StopLoop` doveva ereditare da `BaseException`, non `Exception` — altrimenti
  il blocco `except Exception` di `main()` la intercetta come un errore
  qualunque e il loop continua invece di uscire verso il test (4 test rossi
  finché non corretto). Seconda: `caplog` di default cattura da WARNING in su,
  i log "righe eliminate" sono `logger.info` — serviva
  `caplog.set_level(logging.INFO, logger="worker.run")` esplicito, e
  `r.getMessage()` non `r.message` per leggere il testo interpolato. Le 9
  righe residue scoperte (50-51, 55→58, 98, 104, 156, 167-170) sono
  configurazione ambientale marginale (fallback `dotenv` assente, encoding
  non-Windows, `SUPABASE_KEY` legacy) — basso valore, lasciate.
- ~~**`services/routers/riparto.py`** — 7 endpoint su 11 senza alcun test~~ —
  **CHIUSA l'8/8/2026** (commit `9a2e046`, CI verde run 31253977525, worker
  Railway `/health` conferma `commit: 9a2e0468d772` = deployato). Il
  conteggio era sbagliato (10
  endpoint, non 11) e il file era già al 66%, non scoperto come suggerito.
  Misurato e coperto il punto di rischio reale: `riparto_da_fattura`
  (l'endpoint che ripartisce una fattura di struttura sul gruppo) era a 0%,
  ora coperto — 13 test nuovi, coverage file 66% → 78%, 2 mutazioni
  verificate rosse. Chiusi anche i 2 endpoint secondari di sola lettura
  rimasti (`riparto_incoerenze`, `gruppo_costi_comuni`) nella stessa
  giornata: 8 test nuovi (`tests/test_riparto_incoerenze_e_costi_comuni.py`),
  coverage file 78% → 86%, mutazione sul bucket orfano/senza-documento
  verificata rossa (3 test). Dettaglio in STORICO §15.
- ~~**`verify_and_migrate_password`** (`services/auth_service.py`) — il ramo SHA256
  legacy + migrazione automatica (riscrive `password_hash` sul DB) resta scoperto~~ —
  **CHIUSA l'8/8/2026**. Il ramo Argon2 (657-663) era già coperto; scoperto
  solo 665-685 (SHA256 legacy + migrazione). 9 test nuovi: match/non-match
  SHA256, migrazione riuscita (hash e `id` scritti sull'utente giusto),
  migrazione fallita ma password corretta → login comunque concesso
  (by-design, l'utente non perde l'accesso), `get_supabase_client` non
  ottenibile, password non stringa. 2 mutazioni verificate rosse (match
  SHA256 disattivato, `id` scritto sbagliato nell'update). `argon2` è
  mockato globalmente da `tests/conftest.py`: i test Argon2 verificano il
  wiring (`ph.verify`/`ph.hash` chiamati con gli argomenti giusti), non un
  vero round-trip di hashing. Dettaglio in STORICO §16.
- **Il mock globale di `tests/conftest.py` va ripensato** — `openai`, `requests`,
  `argon2`, `xmltodict`, `supabase`, `tenacity` sono **tutti installati davvero**:
  il conftest sta oscurando librerie funzionanti e rende vacui i test sui rami
  `except`. Toglierlo significa rilanciare 10.000 test e sistemare le ricadute.
  `tests/test_eccezioni_moduli_mockati.py` documenta il problema: **quando
  qualcuno lo rimuoverà quel file diventerà rosso, ed è il segnale atteso.**
- ~~**`.coveragerc` non è un gate**~~ — **CHIUSA l'8/8/2026** (commit
  `9a2e046`, primo run reale osservato: CI 31253977525, job `pytest` verde
  in 2m15s col nuovo step). `tests.yml` ora gira `coverage run -m pytest -q`
  seguito da `coverage report --fail-under=45`: il job pytest fallisce se la
  copertura scende sotto la baseline. Misurato prima di accendere il gate
  (suite completa, non un sottoinsieme): **50%** (23.275 statement, non i
  22.990 di riferimento — cresciuti nel frattempo), soglia tenuta a 45 come
  margine invece di alzarla al numero esatto misurato.

## §3a — Aperti per scelta, con la loro ragione

Non dimenticanze: decisioni. Riaprirle solo con la ragione che le ha chiuse.

- **Cache per-processo vs `WORKER_WEB_CONCURRENCY=4`** — `clear_fatture_cache()`
  invalida il processo che ha servito la richiesta, non gli altri 3. Il TTL 15s
  accorcia la finestra, non la elimina. Risolverlo davvero = invalidazione
  condivisa o cache esterna, cioè **infrastruttura nuova**.
  ⚠️ Non abbassare ancora i TTL: è la scorciatoia che sembra un fix e non lo è.
- **`normalizza_descrizione` (`utils/text_utils.py`) copre 5 pattern su 7** — `CUORI FIL.MERL` vs
  `CUORI FIL MERL`, e l'asterisco di `BRODO...TTL *`, sopravvivono. I 5 conflitti
  esistenti sono stati bonificati il 3/8. Se ne ricompaiono di nuovi **per questi
  due pattern**, è il segnale di estendere la funzione invece di bonificare a mano.
- **L'agent notturno è spento** (`enabled=false` dal 30/5, mai eseguito). Il codice
  ora è corretto ma la feature non è mai stata collaudata: accenderla **è un
  collaudo**, non un'ovvietà. 669 righe `needs_review` da smaltire.
- **3 MEDIUM AI** (prompt anti-"Da Classificare", superficie di prompt injection
  via descrizione fattura, rate-limit fail-open) — lasciati aperti il 4/8 per
  istruzione esplicita ("fix solo l'HIGH").
- **3 MEDIUM/LOW Qualità/UI** — quota chat non mostrata su mobile
  (`mobile-chat.tsx`); `userScalable: false` in `apps/web/src/app/layout.tsx`
  (WCAG 1.4.4, tocca il root layout); 5 LOW di accessibilità sparsi su 20+ file.

## §4 — Buchi di sorveglianza (trovati fuori dimensione)

- **Nessun test di regressione su `X-Reprocess-Key`** — il canale (CRITICAL Edge
  Functions del 30/7) è stato rimosso, ma **nulla impedisce di reintrodurlo**.
- **2 monitor CI che falliscono verdi** — `riparto_coerenza_check.yml` e
  `invoicetronic_eventi_sconosciuti_check.yml` fanno `exit 0` anche su HTTP ≠ 200:
  annotazione rossa nei log, job verde. L'unico segnale reale è l'alert Telegram.
- **`services/routers/fatture.py:850`** passa ancora `volte_visto: 1` — `insert()`
  puro, innocuo oggi, **dannoso se convertito in `upsert`**.
- **Cleanup righe orfane** su re-upload di fatture >2000 righe
  (`services/invoice_service.py:1938-1958`): la lista `numero_riga` è quella già
  troncata. Caso raro, richiede una versione precedente pre-cap.
- ~~**`_CATEGORIE_SPESE_M`** è dead code~~ — **falso, corretto il 4/8/2026**: ha un
  consumatore vivo in `services/routers/margini.py:76` (più un test che lo asserisce).
  Era scritto come "dead code verificato" e non lo era: se qualcuno l'avesse rimosso
  fidandosi, avrebbe rotto i margini.

---

## §3b — Perimetro che nessuna dimensione ha mai rivendicato

**Aperta l'8/8/2026**, dopo la chiusura di §1. **Prima sessione chiusa e
DEPLOYATA la sera dell'8/8** (PR #19, merge `af4c651`, `/health` = `af4c65165497`):
`workspace.py`, `db_service.py` e `auth_service.py` letti al 100%, punti 2-4 di
"come si chiude §3b" risolti.

**Seconda sessione — 10/8/2026: gli helper MOL e briefing di
`fastapi_worker.py`** (punto 4). **CHIUSA e DEPLOYATA il 10/8** — PR #20, merge
`8c8693e`, CI verde (pytest 10.757 passed + coverage 53% sopra il gate 45,
deno-test 108, verify-requirements; `check-drift` non parte perché la PR non
tocca `services/`, quindi nessun drift possibile). Worker Railway verificato su
`/health`: `commit = 8c8693e53d44`, cioè il merge stesso.
98 test nuovi in 3 file, **file 37% → 46%**,
totale 51% → 53% (gate 45). I 6 helper passano da ~285 statement scoperti a
**7**; i residui sono `except` best-effort e una guardia irraggiungibile
(`base <= 0` a `:4650`: il filtro `n > 0` a monte lascia solo valori positivi —
scoperta di proposito, documentata nel test).
**Nessun difetto attivo trovato: sono test, non fix.** Due sospetti sono stati
smontati dal DB live invece che dal codice:
- `.neq("ripartita_su_gruppo", True)` sembrava poter scartare le righe NULL
  (in SQL `col <> true` è NULL → PostgREST esclude). **Falso**: la colonna è
  `NOT NULL DEFAULT false`, 0 righe NULL su 34.000.
- Spegnere `uncategorized_rows` lascia la notifica legacy stantia (la rimozione
  sta *dentro* il gate `:6194`, al contrario del `price_alert` dove è
  deliberatamente fuori). **Reale ma latente**: 0 righe di quel topic in
  `notification_inbox`. Fissato con un test che descrive il comportamento
  attuale, non "corretto" — se un domani si allineano, quel test cade apposta.

La misura che ha spostato le priorità: **`data_competenza` è NULL su 33.771
righe su 34.000 (99,3%)**, e su **229** cade in un mese diverso da
`data_documento`. Il fallback `competenza → documento` non è un caso di bordo,
è il percorso normale di quasi tutto il MOL — da lì la scelta di far
interpretare davvero la `.or_()` al fake (vedi lezione 45 in STORICO §19).

**Terza sessione — 10/8/2026: `invoice_service.py`** (punto 1). Il file da cui
sono passate tutte le 34.000 righe attive: 2174/2174 righe lette, **45% → 75%**,
127 test nuovi in 4 file, 9 test vacui rimossi (suite 10.757 → **10.875**),
32 mutazioni verificate di cui 28 rosse. **DEPLOYATO il 10/8** — PR #22, merge
`517286e`, CI verde (pytest 10.875 passed + coverage 54% sopra il gate 45,
deno-test 108, verify-requirements; `check-drift` non parte perché il suo
trigger copre `fastapi_worker.py`/`routers/**`/`openapi.json`, non
`invoice_service.py` — nessun endpoint toccato, nessun drift possibile).
Worker Railway verificato su `/health`: `commit = 517286e54461`, cioè il merge
stesso. **Un difetto trovato e fixato**,
latente: `VisionDailyLimitExceededError` veniva sollevata e poi **inghiottita
dall'`except Exception` della stessa funzione**, che restituiva `[]` — quindi
l'`except` dedicato del chiamante (`upload_handler.py:1651`, che logga
`VISION_LIMIT_REACHED` e dice al cliente "quota esaurita, riprova domani") era
**irraggiungibile per costruzione** e il cliente avrebbe letto "Nessuna riga
estratta". Dimostrato eseguendo il codice pre-fix, non dedotto; severità latente
misurata sul DB (0 eventi `VISION_LIMIT_REACHED` su 6.505 upload).

Due decisioni di perimetro, entrambe con la misura che le regge:
- **Vision coperto per scelta di Mattia** benché il canale sia inattivo (0 righe
  PDF su 34.000, 0 eventi AI su 443, unico call site dentro il legacy già escluso
  da §2). La copertura è **prospettica, non protettiva**: il salto di coverage che
  produce non va letto come sicurezza aggiunta sui dati correnti.
- **P7M metodi 2-5 esclusi**: sono fallback dietro `asn1crypto`, che vince su ogni
  P7M ben formato — le 2.702 righe in produzione sono passate dal metodo 1. Sono
  **65 delle 205 righe ancora scoperte**: senza di esse il file starebbe a ~82%.

La misura che ha ribaltato le priorità: **TD24 vale 11.773 righe attive (35%)** con
`data_consegna` valorizzata sul **99,98%**, e i suoi test **replicavano
l'algoritmo invece di importarlo** (lo dichiarava il loro docstring): 21 test
verdi che proteggevano zero righe di produzione, su uno dei percorsi più caldi.
Ora coperti contro la funzione vera; la classe replica è stata rimossa.

~~Restano i minori (`documenti_service.py`, `scadenziario.py`, `tag.py`,
`tag_suggestion_service.py`) e la chat di `fastapi_worker.py`.~~ —
**Scadenziario (`documenti_service.py` + `routers/scadenziario.py`) CHIUSO
l'11/8/2026**, misurato per esposizione live prima di scegliere l'ordine (la
coverage da sola aveva già ingannato 2 volte in questo ciclo): era il modulo
minore con l'esposizione più alta (3.428 documenti, 284 pagamenti tracciati,
3 clienti reali con regole fornitore). Un HIGH fixato — **auto-pagato RID
irreversibile**: il ramo automatico forzava `pagata=True` su ogni fornitore a
regola RID, ignorando la dichiarazione esplicita dell'utente ("segna come non
pagata" tornava "Pagata" al primo reload). Confermato sul DB su 3 clienti
reali (CASATI 14, LAND DEI SAPORI, TIME CAFE), 40 documenti mostrati "Pagata"
contro il dato in DB — non un caso di bordo, è il comportamento normale della
feature (9 regole su 11 configurate in tutto il DB sono RID). Fix: nuova
colonna `pagata_manuale_at` che, se valorizzata dalla scrittura esplicita
dell'utente, vince sull'automatismo. 3 MEDIUM fixati: `filter_active()`
mancante sulla query che alimenta scadenza/pagata (1 punto su 6 nello stesso
file, live solo sull'ambiente test — non un HIGH come inizialmente
classificato, vedi lezione sotto); il flag `attiva` di una regola fornitore
non veniva onorato nel path realmente usato in produzione; `delete` di una
regola inesistente ritornava `ok:True` invece di segnalare l'errore. 2 LOW
fixati (dead code allineato invece che lasciato divergente; timezone
incoerente UTC/Roma). 19 test nuovi, 4 mutazioni verificate rosse→verde.
`documenti_service.py` 34,8%→55%.

**Quinta sessione — 24/8/2026: la feature Tag.** ~~Restano i minori (`tag.py`,
`tag_suggestion_service.py`)~~ — **CHIUSA il 24/8**. Il perimetro dichiarato
(2 file) era **incompleto**: la feature ne ha un terzo mai citato da nessuna
passata, `tag_analytics_service.py` (404 righe, **15%** di coverage, la più
bassa delle tre), che alimenta gli endpoint `/analisi` e `/orfani`. Incluso su
decisione di Mattia: auditare la feature come la vede il cliente.

Anche la misura di esposizione dell'11/8 era imprecisa: **4 sedi, non 3**, tutte
clienti reali attivi (LAND DEI SAPORI, TIME CAFE, SUSHILAND MARIANO, CASATI 14),
e **307 `custom_tag_suggestion_items` mai contati**. Il fatto che ha deciso le
severità: **un utente reale possiede 4 sedi e ha tag su 2** (85 associazioni +
7) — ogni difetto di isolamento *cross-sede a parità di user_id* è raggiungibile,
non teorico.

**3 HIGH + 3 MEDIUM fixati.** Il più grave non era un difetto di sicurezza ma un
numero sbagliato mostrato al cliente: `_compute_kpi` sommava **KG, LT e PZ** e ci
divideva la spesa. Misurato: **8 tag su 13, su 3 clienti**. Caso SCAMONE WAGYU:
**42,25 €** mostrati contro **43,51 €/pz** reali (252,97 pezzi sommati a 9,74 kg).
Lo stesso numero alimenta gli alert prezzi della Home via `price_impact_service`.
Fix: si usa la sola unità dominante per spesa, dichiarando in `spesa_esclusa_mix`
quanto resta fuori. La guardia è stata poi **estesa al trend** in un secondo
commit: correggere solo il KPI lasciava due prezzi diversi per lo stesso tag
nella stessa risposta, e l'alert nasceva da quello sbagliato.

Gli altri: `remove_tag_prodotto` era l'unico endpoint senza verifica di sede
(`rimuovi_associazione` filtra solo `user_id`); `prezzo_medio_tag` era una media
non ponderata di medie (sbilanciamento misurato **fino a 93:1**) che divergeva
dal prezzo ponderato dei KPI nella stessa risposta; `target_tag_id` arrivava dal
body senza validazione di sede — e il trigger DB riallinea `user_id`/`ristorante_id`
al tag padre, quindi l'anomalia **non lascia traccia referenziale** (il controllo
"0 associazioni orfane" non l'avrebbe mai vista); una collisione sull'unique
index abortiva il **ciclo intero** della pipeline (saltando dismiss e notifiche);
il DELETE-poi-INSERT degli item poteva lasciare un suggerimento **inaccettabile
per sempre** (`no_items_selected`); `?refresh=true` rispondeva **200 con la lista
vecchia** quando la pipeline falliva, indistinguibile da "nessun suggerimento nuovo".

**Un difetto trovato da me, non dall'agente**: le righe a prezzo ≤ 0 erano
scartate prima di *ogni* calcolo, quindi le note di credito non venivano scalate
dalla spesa — **−1.652 € non scalati** su prodotti taggati. Ora sono marcate
`PrezzoValido`: fuori dal prezzo, dentro la spesa.

**La lezione di questa sessione riguarda le severità dell'agente, di nuovo.**
L'agente non aveva accesso al DB e ha lasciato onestamente 3 numeri "da misurare,
non stimo" — ma sono proprio quelli che decidevano le sue severità. Misurati:
2 confermati (#4 e #5 ATTIVI) e **1 declassato**: il difetto sul trend che lui
dava per attivo ("basta una riga con quantità mancante") non ha **alcun dato che
lo attivi** — 0 righe su 2.016 hanno quantità nulla. Quarta volta in questo ciclo
che una severità cade a una query. Ha però anche **chiuso in negativo 4 piste**
con verifica (soft-delete conforme, cache non stantia, routing senza collisioni,
duplicazione esclusa dall'unique index parziale): lavoro risparmiato in futuro.

12 test nuovi in 3 file — **prima di oggi nessun test esercitava gli endpoint di
`routers/tag.py`** — più 3 aggiornati (codificavano il vecchio comportamento
sulla nota di credito). **10 mutazioni verificate rosse su 10.** Suite 10.971
passed, coverage 55% (gate 45). `tag_analytics_service` **15%→69%**,
`tag_suggestion_service` 41%→51%, `routers/tag.py` 23%→34%.
`tsc --noEmit` pulito, OpenAPI senza drift (194 endpoint).
Dettaglio in STORICO §22.

> ✅ **Deployato il 25/8/2026 mattina presto.** La CI di GitHub Actions parte
> solo su push a `main`/`progetto` o su `pull_request` — mai su push a un
> branch qualsiasi: il branch `audit-s3b-tag` non ha mai potuto avere una CI
> "in corso da osservare", andava aperta una PR per farla partire, cosa
> impossibile in sessione (`gh` non installato, API GitHub bloccata). I 4
> check sono stati **rieseguiti in locale** come sostituto verificabile:
> pytest 10.971 passed/0 failed, `check-drift` OpenAPI 194 endpoint senza
> drift, `verify-requirements` passato, `deno-test` non toccato (branch
> tocca 0 file sotto `supabase/`) — più `tsc --noEmit` pulito.
>
> Durante la sessione l'utente ha committato in concorrenza sullo stesso
> branch (`a8931b6`, fix "da verificare" Articoli/Costi di gruppo) e poi
> l'ha portato su `main` per conto suo: il branch audit è stato **rifondato
> su `origin/main` aggiornato** (`git rebase`, non force-push distruttivo —
> git ha riconosciuto `a8931b6` come patch-equivalente al commit già su
> main e l'ha scartato da solo), poi la verifica è stata **rifatta da capo**
> sul branch riallineato prima del merge.
>
> Merge `--ff-only` (nessun conflitto possibile, fast-forward puro) con
> conferma esplicita dell'utente: `main` `8fd014e` → `ebb842f`, pushato su
> origin. `/health` del worker Railway confermava ancora il commit
> precedente subito dopo il push (build in corso); ripollato con Monitor
> fino a **conferma alle 10:25 CEST del 25/8**: `{"commit":"ebb842f975f8", ...}`
> — deploy verificato, non presunto.

~~Resta di §3b la **chat** di `fastapi_worker.py`.~~ — **chat CHIUSA e DEPLOYATA
il 25/8/2026**, dettaglio in §23 dello STORICO. Con la chat chiusa **§3b è
vuota**: del ciclo resta solo §2 (mock globale `conftest.py`, rimandato per
decisione esplicita).

> ✅ **Deployato il 25/8/2026 pomeriggio** (`main` `de2d02a` → `d92de1d`).
> **Deploy in orario cliente su ordine esplicito e ripetuto dell'utente**, che
> ha confermato dopo che il conflitto con la finestra oraria di `CLAUDE.md`
> (16:00 di martedì) gli era stato posto per iscritto. Registrato qui perché
> sia una decisione consapevole a verbale, non un'eccezione silenziosa.
>
> **Questa volta la CI è girata davvero.** La lezione del deploy Tag di
> stamattina (la CI parte solo su push a `main`/`progetto` o su
> `pull_request`, mai su un branch qualsiasi) è stata applicata alla
> rovescia: invece di surrogare i check in locale, il fast-forward su `main`
> ha **fatto partire la CI reale**, e i 4 workflow sono verdi sul commit
> servito — `Tests` ✅, `OpenAPI Schema Drift Check` ✅, `Requirements
> Consistency` ✅, `Keep-alive Worker` ✅. È caduto così l'ultimo blocco del
> `code-reviewer`, che era esattamente *"verde sulla mia macchina non è verde
> in CI"*.
>
> Merge eseguito come **fast-forward puro** verificato prima
> (`git merge-base --is-ancestor origin/main audit-s3b-chat`), quindi
> nessun commit poteva andare perso. Deploy Railway automatico sul push
> (come da `docs/DEPLOY_RUNBOOK.md`). `/health` serviva ancora `de2d02af3900`
> subito dopo il push (build in corso); ripollato fino a conferma alle
> **16:19 CEST**: `{"commit":"d92de1d448cf","status":"ok"}` — **deploy
> verificato leggendo `/health`, non presunto dal push**. `POST /api/chat`
> risponde 401 senza chiave, come deve.

**Il `code-reviewer` ha bloccato la prima chiusura**: la migration per
`pagata_manuale_at` era scritta ma **mai applicata al DB live**, mentre il
codice già selezionava la colonna — deployato così avrebbe rotto l'intera
pagina Scadenziario per tutti i clienti (PostgREST 400, inghiottito dal
`try/except` che azzera scadenza/pagata). Migration applicata su
vthikmfpywilukizputn **con conferma esplicita dell'utente** (ALTER TABLE
additivo, nullable, nessun default: 3.428 righe, 0 riscritte), riverificata
con la query reale del codice. Lezione sul metodo: mutazione diretta sul file
di produzione (non su copia) era giustificata dalla dimensione del diff ma
non dal criterio giusto — **serve un commit a cui tornare**, non un diff
piccolo. Da riproporre come default finché il lavoro non è committato.

**Lezione**: l'agente di audit aveva invertito le due severità HIGH — dato
"confermato attivo" al bug che colpiva solo l'ambiente test di Mattia (0
clienti) e "latente" a quello che colpiva 3 clienti reali su 40 documenti.
Riverificato sul DB **prima** di accettare la classificazione (query diretta
su `ristoranti`/`fornitori_pagamenti_config`), come da metodo del ciclo.

Nasce da una domanda semplice:
"se tutte le dimensioni sono verdi e §1 è vuota, l'app è analizzata tutta?"
La risposta misurata è **no**, e la differenza non era scritta da nessuna parte.

Il metodo di questo ciclo — dimensioni prima, poi §1 sui file mai letti a fondo
— ha funzionato, ma §1 è stata popolata **a giudizio**, non da un inventario
esaustivo: ci sono finiti i file che le passate avevano segnalato, non tutti
quelli mai letti. Da qui la dispersione.

### Il conto misurato (8/8/2026)

| Perimetro | Dimensione | Stato reale |
|---|---|---|
| Python runtime (`services/`, `utils/`, `config/`, `worker/`) | 53.041 righe | ~30.000 lette a fondo in §1 |
| Frontend Next.js (`apps/web/src/`) | 49.635 righe, 395 file | mai letto riga per riga da nessuna dimensione |
| Route API Next.js | 168 `route.ts` | **162 sono proxy sottili** al worker (~28 righe medie) — rischio basso, concentrato nel Python già auditato |
| Edge Functions | 1.903 righe | ✅ **realmente completo** (13/13 file, 2 passate) |

### Cosa manca davvero, in ordine di rischio

**a) Moduli Python grossi mai auditati come oggetto proprio.** Sono comparsi
nelle passate solo di rimbalzo (citati mentre si guardava altro). La copertura
test è il proxy oggettivo di "quanto codice nessuno ha mai esercitato":

La colonna **esposizione live** è stata aggiunta l'8/8/2026 e ha **invertito
l'ordine di questa lista**: la coverage misura quanto codice nessuno ha
esercitato, non quanto codice i clienti *usano*. `workspace.py` era priorità 1
per coverage e "mai in §1", ma gestisce ~29 righe di dati veri.

| Modulo | Statement | Coverage | Esposizione live (misurata 8/8) | Note |
|---|---|---|---|---|
| `services/fastapi_worker.py` | 3.388 | 37,4% → **46%** | alta | ~~corpo unico~~ → **coperto per router per scelta**, vedi punto 4 sotto. **MOL + briefing CHIUSI il 10/8** |
| ~~`services/routers/workspace.py`~~ | 1.352 | 52,6% | **quasi nulla**: turni 0, regole 0, ingredienti 0, diario 2, inventario 6, dipendenti 1, spese_extra 15/3 sedi | **CHIUSO 8/8** |
| ~~`services/db_service.py`~~ | 1.092 | 36,7% | alta: 35.622 fatture, 4 endpoint cestino vivi | **CHIUSO 8/8**, 2242/2242 righe lette |
| ~~`services/invoice_service.py`~~ | 927 | 44,8% → **75%** | **altissima**: ingresso di tutti i dati, 35.622 righe passate da qui | **CHIUSO 10/8**, 2174/2174 righe lette |
| ~~`services/auth_service.py`~~ | 736 | 39,4% | alta: 16 sessioni attive, 7 utenti | **CHIUSO 8/8**, 1718/1718 righe lette |
| `services/routers/fatture.py` | 662 | 35,8% | alta | chiuso in §1 il 5/8 ma resta poco esercitato |
| ~~`services/documenti_service.py`~~ | 430 | 34,8% → **55%** | **alta, misurata sul DB 11/8**: 3.428 documenti, 1.905 con scadenza, 284 pagati | **CHIUSO 11/8**, 1582/1582 righe (doc+router) |
| `services/routers/scadenziario.py` | 274 | 25,7% → 26% | alta | letto in §3b 11/8, router thin senza test di endpoint propri |
| ~~`services/routers/tag.py`~~ | 209 | 23,3% → **34%** | media, rimisurata 24/8: 115 associazioni, 49 pending, **4 sedi reali** (non 3) | **CHIUSO 24/8**, 351/351 righe |
| ~~`services/tag_suggestion_service.py`~~ | 365 | 40,8% → **51%** | media | **CHIUSO 24/8**, 1019/1019 righe |
| ~~`services/tag_analytics_service.py`~~ | 167 | **15% → 69%** | media: alimenta `/analisi`, `/orfani` e gli alert prezzi Home | **mai in nessuna lista prima del 24/8** — 3 dei 6 difetti stavano qui |

**b) Frontend: 49.635 righe, 0 test.** La dimensione Qualità/UI (2ª passata,
4/8) ha fatto inventario + audit mirato e ha trovato un MEDIUM reale, ma
**dichiara essa stessa** il gap: *"11 file grandi (~10.000 righe) letti solo per
grep mirato, non riga per riga"*. Non esiste alcun test frontend (`0` file
`.test.ts*`/`.spec.ts*`): la rete di sicurezza è solo `tsc --noEmit` +
`next build`. Il rischio è mitigato dal fatto che la logica di dominio sta nel
worker Python, ma "mitigato" non è "verificato".

~~**c) La dimensione Test misura solo Python.**~~ — **DECISA l'8/8/2026**: il gate
**non** viene esteso al TypeScript, e ora `.coveragerc` lo dice per iscritto con
le sue ragioni. Non è pigrizia travestita: il frontend **non accede al DB** e non
contiene logica di dominio (misurato: zero `createClient`/`@supabase`, zero
`.insert(`/`.update(`/`.delete()` su 395 file), quindi le regole di CLAUDE.md non
sono nemmeno *esprimibili* lì e un gate TS non proteggerebbe l'invariante che
conta. Un gate che parte da ~0% è una soglia tenuta bassa per non rompere la CI:
costo reale, protezione nominale. Al suo posto una **guardia** (Regola 7 in
`tests/test_regole_dominio_guardia.py`, 2 test): cade se compare una route con
logica propria fuori dalle 6 dichiarate, o se il frontend inizia a parlare col DB.
Verificata per mutazione: aggiunta una finta route non-proxy → rossa.

### Come si chiude §3b

Non serve rileggere tutto. Serve **decidere il perimetro e dichiararlo**, invece
di lasciarlo implicito:

1. Una passata `oneflux-audit` per ciascuno dei moduli in (a) sopra la soglia.
   ~~priorità a `workspace.py`, `db_service.py`, `auth_service.py`~~ — i primi
   due **CHIUSI l'8/8**, `auth_service.py` in corso. **L'ordine è stato invertito
   dalle misure**: `db_service.py` è passato davanti a `workspace.py` perché
   l'esposizione live conta più della coverage (vedi la colonna nella tabella).
   ~~Restano: `invoice_service.py`~~ — **CHIUSO il 10/8** (45% → 75%, 1 fix
   latente, 121 test). ~~Restano i **minori**~~: **Scadenziario
   (`documenti_service.py` + `routers/scadenziario.py`) CHIUSO l'11/8**
   (34,8%→55%, 1 HIGH + 3 MEDIUM fixati, 19 test). ~~Restano `tag.py` 23,3%,
   `tag_suggestion_service.py` 40,8%~~ — **feature Tag CHIUSA il 24/8, DEPLOYATA il 25/8** (commit `ebb842f`, confermato su `/health` alle 10:25 CEST)
   (3 HIGH + 3 MEDIUM fixati, 14 test, 8 mutazioni; perimetro allargato al
   terzo file mai citato `tag_analytics_service.py` 15%→69%). ~~Resta la **chat**
   di `fastapi_worker.py`~~ — **CHIUSA il 25/8** (1 HIGH + 4 MEDIUM fixati, 21
   test, 4 mutazioni; perimetro reale 25 simboli contro i 4 dichiarati, ramo
   "catena" incluso). **DEPLOYATA il 25/8 pomeriggio** (commit `d92de1d`,
   confermato su `/health` alle 16:19 CEST, CI verde su `main`) — vedi §23
   dello STORICO.
2. ~~Per il frontend: le ~6 route API con logica propria e i componenti che
   scrivono sul DB~~ — **CHIUSO l'8/8**: le 6 route sono state lette (sono tutte
   auth/sessione + il proxy TTS), e il sotto-perimetro "componenti che scrivono
   sul DB" **non esiste** — misurato, il frontend non ha alcun accesso al
   database. Chiuso per assenza di oggetto, non per rinuncia.
3. ~~Estendere il gate coverage al TypeScript, o dichiararlo~~ — **DECISO
   l'8/8**, vedi (c) sopra.
4. ~~**`fastapi_worker.py` esce dalla lista "corpo unico"**~~ — **PRIMA TRANCHE
   CHIUSA il 10/8/2026**: MOL (`_calcola_costi_auto_per_mese`/`_per_periodo`,
   `_aggrega_mensili_margini`/`_aggrega_totali_margini`) e briefing
   (`_briefing_raccogli_notifiche`, `_scontrino_medio_significativo`) sono sotto
   guardia, 20 mutazioni verificate rosse. ~~Restano scoperti per scelta: la chat
   (`_chat_query_costi`, `_chat_loop_openai`, `_build_chat_system_prompt`,
   `_chat_trend_prezzo`)~~ — **chat CHIUSA il 25/8** (SECONDA TRANCHE): il
   perimetro dichiarato di 4 funzioni era in realtà di 25 simboli / ~1737 righe,
   **la quarta volta in questo ciclo che un perimetro dichiarato risulta
   incompleto**. Confermato che il file non ha nessun `@retry`/`tenacity`, quindi
   il mock globale di `conftest.py` (§2) non lo tocca. Resta scoperto
   `_run_agent_notturno` (125 scoperte, il numero più alto della tabella, ma
   `app_settings.agent_notturno.enabled=false` dal 30/5: coprirlo non difende
   nessun cliente). Testo originale della decisione: 3.388
   statement al 37,4% costano più di tre passate intere e producono ri-letture,
   dato che i router sono già stati auditati singolarmente. Il rischio vero sta
   negli **helper non-router** che nessuna passata "per router" ha rivendicato —
   e le due trovate l'8/8 (`_invalidate_home_kpi_cache`, `_briefing_appuntamenti`)
   sono emerse *partendo da un router*, non leggendo il file. Perimetro corretto
   per la prossima passata: gli helper condivisi (cache Home KPI, helper
   briefing, `_merge_override_mensile`, `_DEFAULT_ADMIN_EMAILS`), poche centinaia
   di righe. Una passata monolitica inviterebbe inoltre a refactor larghi proprio
   dove `__getattr__` ha già rotto 9 router in produzione.

**§3b è vuota dal 25/8/2026 pomeriggio.**

---

## §3c — Frontend: lettura sistematica dei client component grandi

**Aperta il 25/8/2026**, alla chiusura di §3b, su richiesta esplicita di
Mattia dopo una domanda diretta: *"per lo scopo dell'audit (app funzionante,
senza incoerenze soprattutto UI/UX visibili al cliente) è tutto chiuso?"*.
Risposta misurata: no. È lo stesso schema che l'8/8 aveva aperto §3b sul
Python ("10 dimensioni verdi non vuol dire app coperta al 100%"), applicato
ora al frontend — che la dimensione 6 (Qualità/UI) aveva già dichiarato
verde pur ammettendo essa stessa il gap.

**Il gap, con le parole della dimensione 6 (STORICO §6, 4/8/2026)**: *"11
file grandi (~10.000 righe) letti solo per grep mirato, non riga per riga"*.
Architettura (STORICO §8, 2/8) conferma lo stesso buco dal suo lato:
*"~178 componenti desktop in `(app)/*` non letti riga per riga — gap
dichiarato esplicitamente"*. 49.635 righe, 395 file, **zero test
frontend** (`0` file `.test.ts*`/`.spec.ts*`): l'unica rete è
`tsc --noEmit` + `next build`, che intercettano errori di tipo, non
incoerenze di prodotto.

**Perché non è un rischio teorico**: il ciclo ha già trovato, di rimbalzo,
la stessa classe di difetto due volte senza mai averla cercata di proposito:
1. **Un fix corretto lato worker che il frontend non consumava** — la
   feature Tag (§3b, 24/8): l'endpoint era stato corretto ma il client
   scartava i campi nuovi, scoperto solo perché qualcuno è andato a
   controllare il consumatore, non perché una passata lo cercasse.
2. **La stessa regola corretta solo in alcuni dei suoi punti di lettura** —
   sempre Tag: un KPI e il suo trend divergevano nella stessa risposta API
   perché il fix era stato applicato a un calcolo e non all'altro.
3. **Un `Select` morto** (dimensione 6, 4/8): componente shadcn con API
   sbagliata, il filtro periodo dei costi AI in Admin non apriva nulla — unico
   bug funzionale trovato dalla passata mirata, e trovato per caso pattern-
   matching su `Select`, non leggendo il file.

Se questo pattern è comparso 2-3 volte nei moduli già toccati, è ragionevole
aspettarsi altre occorrenze nei componenti mai letti — ed è esattamente la
classe di bug più visibile al cliente: non un dato sbagliato nel DB, ma un
numero che diverge fra due schermate, o un controllo che non fa quello che
promette a video.

**Perimetro proposto**: gli 11 file grandi già nominati nel verbale della
dimensione 6 (STORICO §6) come punto di partenza — `scadenziario-client.tsx`,
`analisi-e-tag-client.tsx`, `calcolo-tab.tsx` più gli altri 8 da recuperare
dal verbale originale — letti riga per riga con un obiettivo dichiarato:
cercare divergenze frontend↔backend (campi ignorati, calcoli duplicati
localmente che il backend ha già cambiato, stati derivati lato client invece
che letti dalla risposta API) e incoerenze fra pagine che mostrano lo stesso
dato in punti diversi. Non un audit di stile — quello la dimensione 6 l'ha
già fatto.

~~**Non ancora iniziata.**~~ — **PRIMA PASSATA (audit) CHIUSA il 25/8/2026**:
gli **11 file grandi letti riga per riga, 13.153 righe**, in 4 passate
`oneflux-audit` per dominio. **Nessun fix applicato**: la remediation attende
conferma esplicita di Mattia.

**Il perimetro degli 11 file non esisteva**: STORICO §6 ne nomina 3 e chiude con
«ecc.». Ricostruito **per misura** (`wc -l` su tutti i `.tsx`), non a memoria —
il criterio è scritto nel verbale insieme alla lista, così la prossima passata
non deve indovinare.

**39 findings, 21 attivi su clienti reali, 7 HIGH attivi; 35 piste chiuse in
negativo.** I due fatti strutturali che li spiegano, entrambi misurati:
`grep -ril openapi apps/web` → **0** (la CI protegge Python↔schema, nulla
protegge schema↔TypeScript), e **111 `await res.json()` nei `.tsx` di cui solo
16 annotati** (116 su tutto `src`).

Il pattern di fondo non è drift di *tipi* ma **di autorità**: su 4 dei 7 HIGH il
client ri-deriva localmente uno stato che il worker gli ha già mandato, o
interroga l'endpoint grezzo invece di quello che applica le regole di dominio.
La prova sta in `ricavi.py:1055-1060`, dove la regola è implementata **e
commentata** con la descrizione esatta del bug che si verifica altrove — capita
e corretta in un punto solo, mai propagata.

**3 severità dell'agente spostate su 6 misurate** (6ª, 7ª e 8ª volta nel ciclo
che una severità cade a una query): 2 declassate — costo assenze
(`turni_personale` **vuota**) e `trigger_servizi_off` (**0 clienti**) — e 1
**promossa**: la divergenza sede-singola↔catena sui tag, data per latente
sull'ipotesi «nessun tag di gruppo», mentre esiste «SALMONE» con 5 prodotti e
una divergenza misurata di **236,23 €** di note di credito non scalate.

**I fix Tag del 24/8 sono consumati** (`spesa_esclusa_mix`, trend, `PrezzoValido`
verificati uno per uno; anche `refresh_ok` si è rivelato corretto) **tranne
`prezzo_medio_tag`**, proprio il campo corretto quel giorno: arriva al client
dentro `fornitori.aggregati` e viene scartato.

**REMEDIATION prima tranche chiusa il 25/8** (autorizzata da Mattia): corretti
**4 HIGH su 7** — ripartizione per centro e dettaglio giornaliero in modalità
mensile (stessa causa-radice: l'override `ricavi_modalita_mensile` ignorato dai
due dialog), falso successo nel cambio categoria, deselezione prodotti nei
suggerimenti tag mai inviata al backend. Effetto misurato: **17 mesi su 4 sedi,
da € 83.778 a € 813.690** di netto letto correttamente dai dialog. 8 test nuovi
verificati per mutazione; `tsc`/`build`/drift OpenAPI puliti. Dettaglio in
**STORICO §26**, che rettifica anche una descrizione troppo indulgente di §25.

**Seconda tranche chiusa il 26/8 — gli ultimi 3 HIGH** (STORICO §27). Due
findings su tre sono stati **rettificati verificandoli**: il KPI «Pagate (mese)»
non sbagliava in Italia ma solo nei fusi a ovest di Greenwich, e le «tre
definizioni di oggi» erano in realtà due corrette più una scrittura ottimistica
sbagliata. Il terzo si è allargato: `blocco_mesi_precedenti` **e** la policy
trial erano entrambe morte con Streamlit, e un cliente reale
(`davide.pizzata.78@gmail.com`) aveva il flag acceso. 22 test nuovi, 7 mutanti
uccisi; scrivendoli sono emersi 2 difetti ereditati nei messaggi all'utente
(mese sbagliato per indice, anno sbagliato a gennaio).

**TERZA TRANCHE chiusa il 26/8 — i MEDIUM/LOW** (STORICO §28). Il conteggio
era sbagliato: i findings attivi erano **15**, non 14 (errore di somma
propagato per tre sezioni). **14 su 15 corretti.** Le due incoerenze più
visibili al cliente erano un contatore che si contraddiceva con quello sopra
di sé su 9 sedi su 10, e i selettori prodotti che tagliavano a 80 senza dirlo
(LAND DEI SAPORI vedeva il 4% del catalogo). **Quarta rettifica numerica del
ciclo**: le «22 descrizioni a cavallo F&B/spese-generali» sono **8** per
(sede, descrizione), che è lo scope reale dell'endpoint. E una **rettifica
della diagnosi di §25**: lo scarto fra i due contatori non dipendeva dal case
(zero descrizioni differiscono per sole maiuscole) ma dalle righe a importo 0.
17 test nuovi, 10 mutanti uccisi + 6 del reviewer.

**Resta aperta**: **1 solo MEDIUM**, la divergenza sede-singola↔catena sulle
note di credito (236,23 € misurati, riverificati il 26/8) — richiede una
**migration** su 6 RPC `gruppo_tag_*` e quindi conferma esplicita. Più il
perimetro non ancora letto (`carica-ricavi-dialog.tsx`, dove si **scrive** la
modalità mensile; `pivot-tab.tsx`; `score-tab.tsx`; `catena/*`; gli altri tab
di `workspace/` e `admin/`). Dettaglio in **STORICO §25** e **§28**.

Finché §2 o §3c sono aperte, **il ciclo non è chiuso** — anche con la tabella
tutta 🟢 e §1/§3b vuote.

---

## Come si lavora a questo documento

1. **Una sessione per volta.** Due sessioni che scrivono in parallelo si
   sovrascrivono senza avviso.
2. **Chi chiude una voce la barra e lascia la data** — mai cancellarla in
   silenzio: `~~voce~~ — CHIUSA il gg/mm`.
3. **Il dettaglio va nello STORICO, non qui.** Questo file deve restare
   leggibile in un minuto: è la sua unica funzione.
4. **"Deployato" scritto qui non è una prova**: verifica con
   `git log -- <file>` e con `/health` (il worker espone il commit).
   Il caso Database del 30/7 nasce esattamente da qui.
5. **Questo file è tracciato da git** grazie all'eccezione
   `!AUDIT_ONEFLUX_STATO*.md` in `.gitignore` (che copre anche lo STORICO,
   il cui nome è costruito apposta per matcharla). Committalo col lavoro
   che documenta.

**Modello**: audit read-only con `oneflux-audit` (Sonnet regge); remediation
con Opus e **solo dopo conferma esplicita di Mattia**; `code-reviewer` sul diff
cumulativo a fine sessione, sempre — anche sui fix piccoli, che è dove è
saltato in passato.

## Chiusura del ciclo

Il ciclo si dichiara chiuso quando **§1, §2, §3b e §3c** sono vuote — non
quando la tabella è tutta 🟢 (lo è già dal 4/8). **§1 è vuota dall'8/8/2026**
e i 3 HIGH che conteneva sono **fixati, testati e deployati** nella stessa
data (PR #18, merge `de54a1e`, worker Railway verificato su `/health` =
`de54a1ed2a50`). **§3b è vuota dal 25/8/2026 pomeriggio** (chat di
`fastapi_worker.py`, ultima voce, deployata commit `d92de1d`).

Restano aperte due cose:
- **§2**: il mock globale di `tests/conftest.py` — lavoro lungo dichiarato,
  esplicitamente non da aprire senza tempo dedicato.
- **§3c**: la lettura sistematica del frontend, aperta il 25/8 alla chiusura
  di §3b — stesso schema ("tabella verde ≠ app coperta") applicato al
  frontend invece che al Python. **Prima passata di audit chiusa il 25/8**
  (11 file, 13.153 righe, 39 findings di cui 21 attivi e 7 HIGH) e
  **remediation completata sugli HIGH**: 4 il 25/8 (STORICO §26), gli ultimi
  3 il 26/8 (STORICO §27) e 14 MEDIUM/LOW su 15 il 26/8 (STORICO §28).
  Resta 1 MEDIUM (migration sulle RPC di catena) e il perimetro
  non ancora letto. È la voce che oggi tiene aperto il ciclo insieme a §2.

Quel mock si è fatto sentire proprio scrivendo questi test: `tenacity` è
mockato globalmente, quindi il decoratore `@retry` su
`_chiama_gpt_classificazione` restituiva un MagicMock e la funzione vera non era
chiamabile — qualunque assert avrebbe confrontato un mock, passando per il
motivo sbagliato. Il primo workaround (fixture con `importlib.reload` del modulo
e `retry` pass-through) è stato **scartato dopo la review**: ricaricare
`ai_service` ricrea le classi di eccezione, mentre `upload_handler.py` cattura
`AIDailyLimitExceededError` & co. all'import — sarebbe rimasto legato alle
classi vecchie, con un `except` che non matcha più. La suite restava verde solo
per l'ordine di collection, cioè per fortuna. Soluzione finale senza reload né
stato globale toccato: la funzione non decorata si recupera dal mock stesso, che
registra la chiamata al decoratore. È la conferma concreta che la voce §2 non è
teorica: il mock rende vacui i test sui rami che usano librerie mockate, e ogni
file di test che li tocca deve pagare questo dazio.

MEDIUM/LOW consapevolmente **non** fixati (documentati, non dimenticati): retry
GPT sulle righe rifiutate consapevolmente dal modello, N+1 e RPC SETOF di
`gruppo.py` (soglia ~10 sedi contro le 4 di oggi), 3 endpoint admin
full-load-then-filter, divergenza badge/pagina su `pulisci_caratteri_corrotti`,
`admin_impersona` che non controlla il flag `attivo`. Nessuno è attivo sui dati
correnti; vanno ripresi in un ciclo successivo, non in coda a questo.

Quando entrambe le condizioni sono soddisfatte:

1. Aggiungere in cima "**Ciclo chiuso il gg/mm/aaaa**"
2. Spostare questo file **e il suo STORICO** in `docs/storico/`
3. Per un nuovo ciclo, creare `AUDIT_ONEFLUX_STATO_2026-10.md` (data corrente
   nel nome) — non riusare questo file
