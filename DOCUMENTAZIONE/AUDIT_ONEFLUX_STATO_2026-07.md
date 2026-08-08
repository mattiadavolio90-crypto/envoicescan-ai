# Stato audit ONEFLUX — ciclo 2026-07

**Tutte e 10 le dimensioni sono 🟢, tutte con seconda passata e `code-reviewer`.**
Quello che resta non sono findings aperti: è **perimetro mai letto** (§1) e
**copertura test da scrivere** (§2). Sono due cose diverse e vanno tenute distinte.

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
| 6 | Qualità/UI | 🟢 | 4/8 (2ª) | Rischio più basso confermato; 1 MEDIUM reale (select morto in Admin) fixato — PR #11 |
| 7 | Database | 🟢 | 30/7 (deploy 2/8) | Migration live ma codice Python mai committato per 3 giorni — da lì la lezione 1 |
| 8 | Architettura | 🟢 | 2/8 | 2 fasi, deployato; `code-reviewer` introdotto qui per la prima volta |
| 9 | Test | 🟢 | 3/8 | La suite **non difendeva il MOL**: rotta la regola, 10.195 test restavano verdi |
| 10 | DevOps/Config | 🟢 | 30/7 | `openapi-drift.yml` corretto ma con trigger che non includeva `services/routers/**` |

---

## §1 — Perimetro mai letto (priorità alta)

Codice che **nessun audit ha mai attraversato**. Non è "controllato e giudicato
a basso rischio": è rischio ignoto per definizione.

| File | Stato | Perché conta |
|---|---|---|
| `services/ai_service.py:3392,3453` e `:3579-3990` | **mai letto** | Ultimo sito plausibile della classe troncamenti; se troncata → più chiamate GPT a pagamento |
| `services/routers/admin.py` | letto ~15% | 3010 righe (ricontate il 4/8: il doc diceva 2959), coperte solo da Security passata 3 + Bug |
| `services/routers/gruppo.py` | letto in parte | 8 query `.in_()` multi-sede senza paginazione. ⚠️ **Premessa corretta il 7/8**: qui era scritto che il cap PostgREST «scatta **prima**» in catena. Misurato: scatta a **~33 sedi** (`ricavi_giornalieri`, mese corrente) e **~42** (`margini_mensili`, 2 anni), contro le **4** di SUSHILAND. È rischio **latente**, non difetto attivo — al contrario del caso Performance, dove il cap era già addosso ai clienti. Restava un N+1 per sede (`gruppo.py:1253-1269`) |

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

## §3 — Aperti per scelta, con la loro ragione

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

Il ciclo si dichiara chiuso quando §1 e §2 sono vuote — non quando la tabella
è tutta 🟢 (lo è già dal 4/8). Allora:

1. Aggiungere in cima "**Ciclo chiuso il gg/mm/aaaa**"
2. Spostare questo file **e il suo STORICO** in `docs/storico/`
3. Per un nuovo ciclo, creare `AUDIT_ONEFLUX_STATO_2026-10.md` (data corrente
   nel nome) — non riusare questo file
