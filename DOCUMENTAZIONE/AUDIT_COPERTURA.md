# Certificato di copertura — cicli di audit luglio → settembre 2026

> **A cosa serve questo file.** Fra sei mesi o un anno, quando si riaprirà la
> domanda «l'app è sana?», la risposta onesta **non** è rifare tutto da capo.
> Questo documento dice **cosa è già stato guardato, con quale metro, e a quale
> commit**: da lì si riparte **sul diff**, non sull'intero codice. È l'unico
> artefatto dei tre cicli che è pensato per essere letto da lontano nel tempo.
>
> È tracciato da git di proposito (eccezione a `*AUDIT*.md` in `.gitignore`,
> riga 84): un certificato invisibile al versionamento non certifica niente.

---

## La riga che conta

**Al commit `a82213e` del 09/09/2026** i tre cicli di audit (2026-07, 2026-08,
2026-09) sono **tutti chiusi**, e con essi l'audit di compliance legale dello
stesso giorno. Nessuna dimensione resta aperta. Da qui vale la regola ordinaria:
*quando tocchi un file, lo copri*.

| | |
|---|---|
| Commit certificato | `a82213e24effde39297993d54d8fd97c2485dc96` |
| Data | 09/09/2026 |
| Suite | 13.258 verdi, 44 skip, 0 rossi — di cui **176 su un Postgres vero** (`-m sql`) e 101 Deno |
| Copertura backend eseguita | **61%** (`services,utils,config,worker` — 24.239 stmts, 8.944 miss) |
| Perimetro backend | 57.297 righe Python |
| Logica SQL | 144 migration; **25 funzioni del DB eseguite da test** (erano 0 fino al 07/09) |

> Il commit precedentemente certificato era `13d188e` (13.237 verdi, 164 SQL,
> 143 migration, 20 funzioni). La differenza e' l'audit di compliance del
> 09/09/2026: +21 test (16 sui documenti legali, 12 sulle purge, meno quelli
> ricontati), +5 funzioni di retention eseguite davvero, +1 migration.

> **Lavoro ordinario dopo la certificazione** (non rientra nel perimetro d'audit,
> vale la regola «quando tocchi un file, lo copri»):
> - 09/09/2026, `5a88675` — l'indice di Salute della catena non divergeva piu' da
>   quello del PV: +12 test di comportamento su `_salute_indici_batch` /
>   `_completezza_dati_pv`, 4 mutanti uccisi. Suite **13.270 verdi, 44 skip**.
> - 09/09/2026 — in catena un errore non diventa piu' "tutto a posto": 7 punti
>   dove un `except` produceva il valore che significa "va bene" (compreso il
>   gate `tutto_ok`, acceso ogni mattina dalla cache segnali non ancora
>   generata). +22 test di comportamento, 13 mutanti uccisi — tre
>   **sopravvissuti al primo giro**, tutti per la stessa ragione: il presidio
>   guardava un helper mentre la riga mutata stava dentro l'endpoint. Riscritti
>   chiamando `gruppo_overview` / `gruppo_margini_coperti` /
>   `gruppo_spreco_categorie`. Misurato sul DB: su **34 snapshot su 34**
>   (2 account, 28/6 → 9/9) c'era almeno un segnale, da 4 a 28, mai zero — quindi
>   non "ogni tanto": **ogni giornata con dati, la prima apertura della pagina
>   mentiva**, fino al primo calcolo dei segnali (fra le 07:31 e le 16:21).
>   Suite **13.295 verdi, 44 skip**.
> - 09/09/2026 — il briefing non dice piu' due volte la stessa cosa. L'apertura
>   "fatture arrivate" ripeteva la voce to-do che sta due righe sotto e rimanda
>   alla stessa card (percorso template: ripetizione deterministica); in catena
>   lo stesso difetto su un altro tema, con in piu' un "qui sotto" FALSO su
>   mobile, dove la coda non esiste. +9 test, 4 mutanti uccisi, 5 test esistenti
>   ROVESCIATI (asserivano il testo duplicato). `_BRIEFING_CODE_VERSION` 21 -> 22:
>   senza bump la cache avrebbe servito la frase vecchia fino al TTL. La review
>   ha trovato una REGRESSIONE introdotta dal fix stesso (su mobile spariva
>   l'unica azione del giorno) e una mia affermazione piu' forte del vero — "la
>   card c'e' sempre" vale per la finestra temporale, non col toggle utente ne'
>   col taglio a 4 card: corrette entrambe, +3 test, 5 mutanti uccisi.
>   Suite **13.310 verdi, 44 skip**.
>
> - **10/09/2026, `da269ad` — la memoria si caricava a pagine senza un ordine, e
>   perdeva righe in silenzio.** `_fetch_all_rows` (4 chiamanti in `ai_service`)
>   paginava con `range()` senza ORDER BY: misurato sul DB vivo, su 10 letture
>   della memoria locale di un cliente con 3.067 voci, 2 tornavano con 66 e 653
>   id mancanti rimpiazzati da duplicati, col totale SEMPRE 3.067 — il worker
>   teneva quella memoria a meta' in cache per un'ora e in quell'ora le
>   correzioni del cliente non valevano. Trovato per caso dalla baseline del
>   retail (non riproducibile), non da un test: un aggregato che torna nasconde
>   errori che si compensano. Ora `.order("id")`; +3 test, 3 mutanti uccisi
>   (senza ordine, per descrizione, decrescente); due fake di test esistenti
>   hanno imparato `.order()` (decisione di Mattia). Effetto collaterale
>   dichiarato: sulle collisioni della memoria normalizzata vince l'ultima voce
>   per `id` invece che per ordine fisico (1 riga su 3.475 sui dati veri). Da
>   decidere a parte: **33 chiamanti di `fetch_all` su 34 senza `.order()`**,
>   stessa classe. Suite **13.363 verdi, 44 skip**.
>
> - **09/09/2026 — Fase 4: il banner in fondo alla Home fuso nella card.** La
>   card grande "Righe da classificare" era un doppione visivo della voce che il
>   briefing mostra gia' in cima ("2 prodotti da controllare"): due blocchi con
>   due numeri diversi che al cliente sembrano la stessa cosa. Decisione di
>   Mattia: una card sola, due righe; a zero righe non si mostra nulla (il verde
>   "tutte classificate" sparisce). Eliminati `da-classificare-card.tsx`,
>   `lib/home-da-classificare.ts` e `test_home_da_classificare_frontend.py`; la
>   voce "Righe classificate" e' tornata nell'elenco Salute desktop, da cui era
>   uscita l'1/9 proprio perche' la promuoveva quella card. Gli euro esclusi dai
>   margini viaggiano ora nel payload di `uncategorized_rows` e diventano la
>   seconda riga (`dettaglio`). +15 test, **8 mutanti uccisi**.
>   `_BRIEFING_CODE_VERSION` 22 -> 23.
>   Due cose trovate misurando e non leggendo: (a) un mutante sopravvissuto ha
>   smascherato una mia guardia RIDONDANTE (`'esclusi_importo' not in payload`,
>   coperta gia' dal gate a valle) — rimossa, non presidiata a forza; (b)
>   togliendola ho visto che gateavo su `importo <= 0`, che avrebbe fatto
>   sparire in silenzio la riga di LAND (-1.302,36 EUR di note di credito non
>   classificate, misurati il 3/9): un totale negativo e' un dato vero, non
>   un'assenza. Il gate e' passato sulle RIGHE, con presidio dedicato.
>   Le due popolazioni restano DUE FRASI separate: `testo` conta i prodotti
>   `needs_review` (7 giorni), `dettaglio` le righe 'Da Classificare' (storico,
>   escluse dai margini). Legarle in una frase sola sarebbe falso.
>   **Verifica delle inerenze (post-commit)**: ha trovato un difetto vero che i
>   9 mutanti non coprivano — i DUE cancelli in fila usavano criteri diversi
>   (`_dettaglio_esclusi` sulle righe, `_briefing_righe_da_classificare`
>   sull'importo): su LAND il record non veniva emesso a monte e la riga
>   spariva prima che la frase la componesse, senza che il presidio a valle
>   potesse accorgersene. +1 mutante (**10 su 10**). E tre commenti
>   promettevano ancora la card eliminata: `SaluteResponse.da_classificare` e'
>   servito ma non piu' letto da nessun componente (il campo resta: toglierlo e'
>   una modifica di contratto a se').
>   Un test esistente (`test_arretrato_sotto_soglia_e_silenzio`) e' stato
>   aggiornato: cadeva sia per il cambio voluto sia per un MOCK GENEROSO che
>   serviva le righe needs_review anche alla query sugli esclusi, fondendo due
>   popolazioni diverse.
>   **Due mie affermazioni corrette dalla review, misurate a DB:**
>   (a) il costo del round-trip in piu' NON e' assorbito da `_LIVE_SEGNALI_CACHE`
>   come diceva il piano — quella cache copre solo `get_notifiche` (:2836),
>   mentre il briefing chiama `_briefing_righe_da_classificare` direttamente da
>   `_briefing_raccogli_notifiche` (:6953), fuori cache. Il costo e' comunque
>   assorbito, ma da un ALTRO meccanismo: lo snapshot briefing e' cache-first
>   con `code_version` + TTL, quindi la raccolta gira 1-2 volte al giorno.
>   Esito accettabile, motivazione sbagliata: si annota perche' la prossima
>   volta qualcuno ci si appoggia.
>   (b) il rosso di `test_arretrato_sotto_soglia_e_silenzio` NON era un flake da
>   concorrenza come avevo scritto: era deterministico gia' su `4b0c9a5`, una
>   regressione mia mascherata da un mock generoso.
>   **Misura sui dati veri (chi cambia davvero in produzione):** una sola sede
>   cliente guadagna voce — SUSHILAND MARIANO, 13 righe / 474,92 EUR, prima
>   muta perche' l'arretrato (18) stava sotto soglia. LAND (-1.302,36 EUR) era
>   salvata **per caso** dal suo arretrato di 29: il bug dei due cancelli era
>   latente, non attivo, e sarebbe scattato appena sceso sotto 20. Perdono il
>   verde "tutte classificate" le 5 sedi a zero righe escluse (TIME CAFE,
>   CASATI 14, IL BARETTINO, OVERTIME, ambiente di test), come deciso.
>   Suite **13.322 verdi, 44 skip**.
>
> - **09/09/2026 — Fase 5: il MOL al centro anche nella catena.** Con dati di
>   costo incompleti la card "I conti del gruppo" NASCONDEVA il MOL e al suo
>   posto metteva il food cost, mentre il PV nello stesso caso lo mostra con un
>   avviso accanto: due viste dello stesso prodotto con due metriche diverse in
>   primo piano (screenshot del 9/9). Ora la catena fa come il PV: MOL grande
>   sempre, in ambra e con l'avviso "N PV con dati di costo incompleti: questo
>   margine non e' reale" (porta alla finestra Margini, che marca quali) finche'
>   non e' reale; food cost nella riga sotto, una volta; l'andamento segue il
>   MOL in ambra e senza certificare verde un "in meglio" che potrebbe essere
>   solo un costo mancante. `/m` allineato a mano, e guadagna lo stato "vuoto"
>   che non aveva (finiva nel ramo food cost con un "—" grande).
>   La scelta del ramo e il testo dell'avviso vivono in una funzione pura nuova,
>   `metricaPrincipaleConti` (`lib/catena-confronti.ts`), condivisa da desktop e
>   `/m`: il rendering `.tsx` non e' testabile, e due copie a mano divergono.
>   +15 test, **7 mutanti su 7**, con un PRESIDIO INCROCIATO: tintConti
>   certifica verde/rosso se e solo se la metrica dichiara il MOL affidabile —
>   il test che avrebbe fermato la divergenza PV-catena da cui e' nato il piano.
>   Trovato misurando: `margine_medio_perc` e' **Σmol/Σnetto** (gruppo.py:76),
>   cioe' lo stesso MOL gonfiato in percentuale — non il primo margine come il
>   commento del tipo TS lascia intendere. Nel ramo incompleto il badge
>   "margine %" e' nascosto: un numero falso con l'avviso e' la decisione, due
>   sarebbero rumore. `tsc --noEmit` pulito. NON fatta la prova visiva nel
>   browser (qui non c'e'): dichiarato.
>   **Review: rossa al primo giro, per il doc.** Avevo riscritto la tabella
>   della cascata in LOGICA_BRIEFING.md e lasciato venti righe sotto la nota
>   del 17/7 che diceva ancora "il MOL e' correttamente nascosto" — la
>   contraddizione che `test_documentazione_onesta` non puo' vedere (verifica
>   simboli, non senso). Riscritta come storico. Insieme: (a) il commento dei
>   tipi in `lib/gruppo.ts` affermava due cose ora false ("1° margine", "MOL
>   no"), corretto; (b) la sparkline con dati incompleti aveva colore e delta
>   neutri ma la FRECCIA ancora direzionale — un simbolo che certifica la
>   direzione di un MOL gonfiato: tolta, ed etichetta con caveat; (c) avevo
>   scritto "la catena adotta il modello del PV" mentre su Personale/Spese fa
>   il CONTRARIO (il PV li mostra, la catena li nasconde): scelta di prodotto
>   legittima, ma va detta come divergenza deliberata, non come allineamento —
>   ora lo dice il codice e il doc.
>   Non della fase, ma esiste: `test_home_briefing_cache_first` e' intermittente
>   perche' `_GENERATED_AT` e' catturato a IMPORT (riga 40) e una suite a
>   cavallo della mezzanotte UTC lo vede diventare "ieri" a meta' corsa.
>   Trappola gia' in memoria; chi tocca quel test dovrebbe congelare la data.
>   La misura su GRUPPO OFFSIDE (che MOL vedra' da domani) NON e' stata
>   possibile: MCP Supabase senza permesso. Resta da fare prima del push.
>   Suite **13.346 verdi, 44 skip** (ri-misurata dal reviewer dalla root: la
>   cifra 13.337 del commit era gia' superata da due commit docs altrui).
>
> - **09/09/2026 — Fase 6: periodo dichiarato, soglie condivise, misure su
>   OFFSIDE.** Tre cose piccole e una misura. (6a) La catena somma da gennaio
>   al mese CORRENTE, parziale, e lo etichettava "Anno 2026": accanto a un PV
>   che mostra un mese ("agosto", 0 EUR) il totale di gruppo (710.885 EUR) si
>   leggeva come un anno chiuso. Ora `_label_anno_parziale` scrive "Anno 2026 ·
>   gen–set, settembre in corso", nell'overview E nei tre endpoint che usano la
>   stessa finestra (dialog Margini e Coperti, dialog Spreco per categoria,
>   analisi tag — il quarto non era nel piano: trovato cercando chi altro
>   scriveva "Anno"; la pivot Spesa per PV NON cambia, e fa bene: la sua
>   finestra e' l'anno intero):
>   correggere solo l'overview li avrebbe lasciati a dire "Anno 2026" nel
>   titolo e nel nome del file esportato. La finestra NON cambia:
>   portarla al mese come il PV e' una decisione di prodotto, non un fix.
>   (6b) Le soglie 80/50 dell'indice di Salute erano in `daily_briefing_service`
>   dal 2/9 e `gruppo.py` le riscriveva come letterali in TRE punti (colore del
>   gruppo e dei PV; ripiego "salute rossa = da completare" in `_build_briefing`,
>   due volte): ora `_colore_salute_o_grigio` e `salute_e_rossa` importati. Il
>   test che mancava: si cambia `SALUTE_SOGLIA_VERDE` e la catena deve seguire
>   — prima restava verde. (6d) L'indice aveva tre unita' per lo stesso numero
>   ("78%" nel PV, "78 su 100" in catena, "78/100" su `/m`): ora "%" ovunque.
>   La palette della Salute era in due copie (`COLORI` nel PV, `TINT` in catena)
>   e gia' divergenti: il PV non aveva le varianti dark del testo. Una sola in
>   `lib/salute-tint.ts`, importata da entrambe; il PV guadagna il tema scuro.
>   Corretto anche il commento della cascata in `gruppo.py` che diceva ancora
>   "MOL no" (falso dalla Fase 5). NON allineati i nomi delle voci ("Fatture
>   caricate" nel PV vs "le fatture costo" in catena): in catena sono oggetti di
>   una frase ("Mancano ... — vai a completare"), non etichette; e non tolto il
>   "dati incompleti" ripetuto in tre punti della schermata catena: sono tre
>   superfici con tre ruoli (verdetto, qualifica del numero, elenco azionabile)
>   e togliere il caveat accanto al numero sarebbe il bug della Fase 5 daccapo.
>   **Le due misure di 6c, ESEGUITE su GRUPPO OFFSIDE** (2 PV, 2026, sola
>   lettura, coi percorsi veri: `_kpi_periodo` del PV e `_aggrega_sedi_mensili`
>   della catena, stesso mese): (1) food cost per sede-mese identico nelle due
>   viste su 18 sede-mesi, base NETTO in entrambe (gen: OFFSIDE 44,6%, OVERTIME
>   28,2%; gruppo 39,1% = 32.657,92/83.522,86); (2) Σ MOL dei PV = MOL del
>   gruppo su tutti e 9 i mesi, scarto massimo 0,01 EUR di arrotondamento
>   (gen −9.552,46; ago −25.429,63; set −11.666,61). In piu' le due RPC costi
>   (`costi_automatici_mensili` del PV e `..._gruppo` della catena) danno lo
>   stesso F&B e le stesse spese al centesimo su ogni sede-mese. Nessuna
>   divergenza: nessuno stop. Un dato che spiega gli screenshot, non un bug:
>   agosto e settembre hanno costi ma ZERO ricavi inseriti in entrambe le
>   sedi, quindi il PV mostra agosto a 0 EUR con MOL −14.589,54 e l'anno di
>   gruppo (MOL 93.508,43) porta dentro due mesi in perdita per assenza di
>   fatturato — e' il caso "personale/ricavi a 0 sui mesi recenti" gia' in
>   memoria, e l'etichetta nuova lo dice.
>   +23 test (13 backend, 10 frontend), **10 mutanti su 10** (etichetta nel
>   helper e nei quattro endpoint, soglie nei tre punti, palette senza dark e
>   senza grigio), `tsc --noEmit` pulito, OpenAPI senza drift. NON fatta la
>   prova visiva nel browser: dichiarato.
>   Suite **13.360 verdi, 44 skip** da `tests/` (seconda corsa piena sul commit
>   finale; la prima, senza il test dell'endpoint tag e senza
>   `test_documentazione_onesta`, dava 13.306 + 53); **13.369 dalla root**,
>   ri-misurata dal reviewer.
>   **Review: verde**, con la ri-misura sul DB fatta per conto suo (gennaio
>   2026 OFFSIDE SPORTS PUB: F&B 18.419,14 / spese 25.357,51 identiche nelle
>   due RPC; Σ food 2026 234.856,73 in entrambe) e 5 mutanti rifatti, tutti
>   uccisi. Tre rilievi non bloccanti, sistemati nel commit di chiusura: il
>   verbale nominava "Spesa per PV" al posto di "Spreco per categoria"; il
>   titolo del dialog Spreco allineava tre "·" con la nuova etichetta (ora un
>   trattino); `/m` aveva una TERZA e una QUARTA copia della palette (`DOT` e
>   `TXT` in `mobile-catena.tsx`), identiche per caso — ora derivate da
>   `SALUTE_TINT`. Il PV, con la palette unica, guadagna le varianti dark del
>   testo: un cambio visivo reale sulla Home, voluto.

---

## Come si riparte fra un anno — la procedura, in ordine

Il punto di questo file è **evitare l'audit totale**. Si procede così:

### 1. Si misura il diff, non il codice

```bash
git diff --stat a82213e..HEAD -- services utils config worker apps/web/src supabase
git log --oneline a82213e..HEAD | wc -l
```

Una dimensione della tabella qui sotto si riapre **solo se il diff tocca i suoi
percorsi**. Se `supabase/migrations/` è identico, la logica SQL non va riletta:
è stata letta tutta, corpo per corpo, il 07/09/2026.

### 2. Si verifica che la rete regga ancora

```bash
python -m pytest tests/ -q                      # atteso: verde
python -m pytest -q -m sql                      # 164 su Postgres vero
python -m coverage run --source=services,utils,config,worker -m pytest tests/ -q
python -m coverage report --sort=cover          # atteso: >= 61%
```

**Se la copertura è scesa sotto il 61%**, qualcuno ha aggiunto codice senza
presidio: quello è il perimetro da guardare, ed è già la risposta alla domanda
«da dove comincio».

### 3. Si ri-misura, non si eredita

Ogni cifra di questo file era vera il 09/09/2026 e **non lo sarà più**. Vanno
ri-misurate prima di essere citate. È l'errore che questi cicli hanno commesso e
corretto più volte: un numero copiato da un documento non è una misura.

---

## Cosa è stato coperto, dimensione per dimensione

Le tre colonne che servono a decidere: **quando**, **con quale metro**, e **cosa
farebbe riaprire la dimensione**.

| Dimensione | Chiusa il | Metro usato | Si riapre se… |
|---|---|---|---|
| Security | 07-08/2026 | 10 dimensioni del ciclo 07; auth, upload, open redirect, RLS | cambia `auth_service.py`, l'upload, o si introduce Supabase Auth |
| Bug / Qualità / Architettura | 07/2026 | lettura completa + `code-reviewer` per fase | refactor strutturale di `services/` |
| Performance | 07/2026 | query, indici, N+1 | rallentamenti misurati in produzione |
| AI / pipeline categorizzazione | 07-08/2026 | prompt, fallback, regole di dominio #1 e #2 | si tocca `ai_service.py` o il dizionario |
| Database (schema) | 30/07/2026 | schema, FK, orfani, indici — 9 finding | migration che cambiano struttura |
| **Database (corpi delle funzioni)** | **07-09/09/2026** | **78 corpi letti dal live** con `pg_get_functiondef`, 25 eseguiti da test | **nuove funzioni SQL, o `.rpc()` nuove** |
| Test / copertura | 09/2026 | copertura eseguita, non letta: 61% | scende sotto 61% |
| Edge Functions | 27/08/2026 | deployate v40/v13, repo avanti di 10 righe di soli commenti | si modifica `supabase/functions/` (**il deploy è manuale**) |
| DevOps / Config | 07-08/2026 | CI, secrets, runbook, backup provato il 10/08 | cambia la pipeline o il provider |
| Registro delle correzioni | 08/09/2026 | ogni scrittura su `fatture` dichiara attore, `source`, `batch_id` | nuovo scrittore di `categoria` che non passa dal chokepoint |
| Script che scrivono in produzione | 08/09/2026 | 41 censiti, 8 vivi dopo il go-live | nuovo script che scrive a DB |
| **Compliance legale (privacy, cookie, termini, GDPR)** | **09/09/2026** | documenti pubblici confrontati **col codice**, non riletti: destinatari dei dati vs host contattati, retention dichiarate vs purge esistenti, export art. 20 vs tabelle con PII | **cambia un flusso di dati verso terzi, o una dichiarazione della privacy** |

---

## Cosa NON è coperto — e resta una scelta, non una dimenticanza

Va scritto qui perché **nessun audit futuro lo riscopra come se fosse una novità**.

| Area | Misura | Perché è fuori |
|---|---|---|
| Frontend `.tsx` | 42.293 righe: rendering, hook, stato, effetti | Nessun runner npm **per scelta d'impianto**: `deploy-vercel.yml` scatta su `apps/web/**`, un runner deployerebbe a ogni test. La logica pura si estrae in `lib/` (87% presidiato) |
| 7 funzioni SQL di staff | `admin_ai_mensile`, `admin_consumi_mensili`, `admin_conteggio_fatture`, `admin_fatture_per_mese`, `get_ai_costs_summary`, `get_ai_costs_timeseries`, `get_ai_recent_operations` | Le vede solo l'owner, non i clienti; non spostano un euro sui loro numeri. Rendimento basso |
| Copertura backend oltre il 61% | 10 router su 12 a copertura parziale | Le aree grasse sono state prese e ognuna ha dato un bug vero. Oltre, il rendimento cala: si copre **quando si tocca il file** |
| 96 policy RLS | mai lette una per una | Con `auth.uid()` sempre NULL e ogni client su `service_role` (BYPASSRLS) **non filtrano nulla**: la protezione è applicativa, ed è già la dimensione Security |
| Costo del personale fermo a luglio | MOL di agosto/settembre non confrontabile | **Decisione dell'owner del 07/09/2026**: lo inseriscono i clienti (Margini → «Costo personale»), il briefing li avvisa dal 28/08 |
| Ricostruzione del DB dalle migration | 230 migration su un Postgres vuoto: **18 tabelle su 59, 171 file falliti** | Il repo **non sa ricostruire il database**. I test SQL girano sullo snapshot dello schema live (`supabase/schema_snapshot.sql`), non sulle migration. Un «Postgres in CI con le migration applicate» non è un'opzione |

---

## Il difetto che i tre cicli hanno diagnosticato — e che vale più delle cifre

> Ogni ciclo ha misurato **ciò che sapeva misurare** e ha chiamato «100%» il
> proprio perimetro. Il buco non era dentro nessuno dei tre: era **fra** i tre.
> La logica dentro il database — 8.930 righe di SQL che girano a ogni scrittura —
> non era in nessun perimetro perché nessun contatore contava i `.sql`.

Chi riaprirà un audit su questa app parta da lì: **non «ho guardato tutto?», ma
«cosa è rimasto fuori dalla domanda che ho fatto?»**. Le due domande hanno
risposte diverse, e solo la seconda trova qualcosa.

Corollario operativo, pagato caro tre volte in questi cicli: **un test verde non
prova che il codice funzioni**. `tsc --noEmit` non esegue niente; un mock
generoso resta verde sul bug (i test del radar passavano su una colonna mai
esistita); un assert sul testo del sorgente sopravvive a qualunque mutazione del
corpo. Un presidio si prova **per mutazione**, o non è un presidio.

---

## Dove sta il resto

| Serve… | Documento |
|---|---|
| I verbali dei tre cicli, per esteso | `docs/storico/AUDIT_ONEFLUX_STATO_2026-07*.md`, `..._2026-08*.md`, `AUDIT_ULTIMO_PERIMETRO_2026-09.md` |
| I prompt di lavoro del ciclo 09 | `docs/storico/audit-2026-09/` |
| Come si chiude una fase (i 5 punti) | `WORKFLOW.md` §5 |
| Dove sta cosa nel codice | `DOCUMENTAZIONE/MAPPA_TECNICA.md` |
