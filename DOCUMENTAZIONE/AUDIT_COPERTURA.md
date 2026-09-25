# Certificato di copertura — cicli di audit luglio → settembre 2026

> **A cosa serve questo file.** Fra sei mesi o un anno, quando si riaprirà la
> domanda «l'app è sana?», la risposta onesta **non** è rifare tutto da capo.
> Questo documento dice **cosa è già stato guardato, con quale metro, e a quale
> commit**: da lì si riparte **sul diff**, non sull'intero codice. È l'unico
> artefatto dei tre cicli che è pensato per essere letto da lontano nel tempo.
>
> È tracciato da git di proposito (eccezione a `*AUDIT*.md` in `.gitignore`,
> riga 84): un certificato invisibile al versionamento non certifica niente.
>
> **Se quello che cerchi e' «quanto lavoro e' stato fatto»**, non e' questo il
> file: e' `DOCUMENTAZIONE/AUDIT_BILANCIO_LUGLIO_SETTEMBRE.md`, che misura il
> periodo 01/07 → 17/09 in un colpo solo. Questo qui serve a **ripartire**, non a
> fare il bilancio.

---

## La riga che conta

**Al commit `1011d10` del 17/09/2026** i tre cicli di audit (2026-07, 2026-08,
2026-09) sono **tutti chiusi**, e con essi l'audit di compliance legale del
09/09 e **tutte e nove le lenti trasversali** (L9 chiusa il 17/09). Da qui vale
la regola ordinaria: *quando tocchi un file, lo copri*.

| | |
|---|---|
| Commit certificato | `1011d10` — l'ultimo dei sei giri di review di L9, ed e' qui che la suite e' stata misurata |
| Data | 17/09/2026 |
| Suite | **14.804 raccolti** (14.220 verdi + 45 skip fuori da `-m sql`) — di cui **539 su un Postgres vero** e 101 Deno |
| Copertura backend eseguita | **65%** (`services,utils,config,worker` — 24.958 stmts, 8.224 miss) |
| Logica SQL | 148 migration; **25 funzioni del DB eseguite da test** (erano 0 fino al 07/09) |
| Lenti trasversali | **9 su 9 chiuse**, 18 difetti corretti — `docs/storico/audit-2026-09/INDICE_LENTI_L1_L9.md` |

> **Certificazione precedente: `a82213e` del 09/09/2026** — 13.258 verdi, 176 SQL,
> 61% di copertura, 144 migration. Quella riga e' rimasta ferma mentre il ciclo
> delle otto lenti (14 → 17/09) andava avanti: **+138 commit, +64 file di test
> (12.132 righe), 220 file toccati, +30.646 righe**. Il bilancio completo del
> periodo sta in `DOCUMENTAZIONE/AUDIT_BILANCIO_LUGLIO_SETTEMBRE.md`.

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
>   dichiarato: sulle collisioni della memoria normalizzata il vincitore era
>   gia' arbitrario e instabile fra una ricarica e l'altra; ora e'
>   deterministico (ultima voce per `id`, uuid casuale, senza semantica
>   temporale). Ri-misurato l'11/09/2026 in sola lettura, dopo che la review
>   dei commit di `main` aveva contestato la cifra «1 riga su 3.475» (era la
>   baseline, che campiona): **39 chiavi su 5.206** cambiano categoria rispetto
>   alla lettura per ordine fisico; sul cliente da 3.067 voci 28 gruppi
>   collidono e in **5 una correzione manuale perde** contro un'automatica —
>   la direzione non e' «verso il manuale», e' arbitraria. Da decidere a
>   parte: precedenza `classificato_da` manuale > automatico, e i **33
>   chiamanti di `fetch_all` su 34 senza `.order()`**, stessa classe. Suite
>   **13.363 verdi, 44 skip**.
>
> - **11/09/2026, branch `retail` (NON spedito) — Fase 5 del retail: sorveglianza
>   post-deploy.** Le Fasi 1-4 hanno dimostrato il vincolo «i ristoranti non
>   cambiano» **al momento del commit**; questa lo sorveglia **sui dati veri dopo
>   il deploy**, dove il danno si vedrebbe. La misura ha fatto cadere la premessa
>   della fase: il piano voleva contare i cambi «senza attore umano», ma su
>   **4.135** righe di `category_change_log` quelle con un attore sono **0** e
>   `source` ha **un solo valore** (`db_trigger`) — i GUC che il trigger legge non
>   li imposta nessun codice applicativo, solo le migration li nominano. Un filtro
>   sull'attore avrebbe selezionato il 100% delle righe: rumore puro, e un alert
>   che scatta ogni giorno viene ignorato entro una settimana. Segnale riscritto su
>   base **semantica**: una riga di una sede ristorazione che finisce in
>   `ARTICOLO DI VENDITA` e' sbagliata chiunque l'abbia scritta. Non tocca le
>   classi legittime (42,3% `Da Classificare`→reale, 55,7% reale→reale, 2,0%
>   ritorno in coda): guarda solo l'incrocio categoria×settore, che sullo storico
>   completo vale **0**. Scritti una view (**non applicata**), un endpoint `GET` di
>   sola lettura e un workflow cron con alert solo su anomalia. **11 mutanti**, di
>   cui uno ha smascherato un **presidio finto**: `ROTTA in testo` restava verde col
>   `curl` puntato altrove, perche' il path compare anche nel commento del workflow
>   — il monitor avrebbe preso 404 e taciuto per sempre. Due difetti veri trovati
>   dai presidi e non dalla lettura: `?ore=0` allargava la finestra invece di
>   stringerla (`or` su un falsy), e l'endpoint non aveva una guardia propria — vista
>   **solo dalla suite intera**, verde a file isolato. Reviewer **🟢** con tutte le
>   cifre ri-misurate; i suoi 3 findings non bloccanti chiusi lo stesso (la view era
>   l'unica delle 4 del repo senza `security_invoker`; il letterale della categoria
>   retail non era legato alla costante; la guardia per-rotta non era provata — il
>   test del 401 restava verde togliendola, perche' misurava il gate del router).
>   Coperto anche il caso «colonna `tipo_attivita` assente», che e' lo **stato reale
>   del DB oggi** e che nessun presidio copriva (`conftest_sql` applica sempre la
>   migration). Alla **seconda lettura** il reviewer ha trovato che il presidio su
>   `security_invoker` era un grep sul sorgente: commentando la riga `ALTER VIEW`,
>   la view nasce senza l'opzione e **32 test restano verdi** — stesso errore del
>   mutante 9, ripresentato nel fix di un finding. Reso comportamentale su
>   `pg_class.reloptions`. **18 mutanti, 18 uccisi**, 2 presidi finti smascherati.
>   Suite **13.873 verdi, 45 skip**; `-m sql` **192**; OpenAPI **197** senza drift.
>
> - **11/09/2026, branch `retail` (NON spedito) — Fase 4 del retail: briefing,
>   chat AI e soglie.** La chat diceva a un negozio «Rispondi SOLO a domande sui
>   dati del ristorante» e gli dava i benchmark della ristorazione italiana come
>   se fossero suoi (per il retail non esistono: da ~35% a ~78% secondo cosa si
>   vende). Il gate dei tool guardava le chiavi-PAGINA, e i `tab_off_*` della
>   Fase 3 non lo sono: il negozio non vedeva la tab Coperti e poteva comunque
>   chiederli in chat — e spegnerli via `pagine_abilitate` non era
>   un'alternativa, perche' `query_margini` e `query_coperti` condividono lo
>   stesso flag. Gate spostato sul settore, in **due punti**: la lista offerta al
>   modello e l'esecuzione nel dispatcher, che esegue per nome e non consulta
>   `tools`. Soglie: nessun colore sul KPI merce, ma la riga **resta** con
>   l'emoji neutra (il frontend mappa l'assenza di commento sullo stesso gauge
>   neutro: toglierla l'avrebbe spento). Nome KPI «Costo Merce» e testi delle
>   soglie rinominati **insieme**, o il negozio leggeva mezzo testo da ristorante.
>   **Il residuo degli script era piu' profondo di come era stato dichiarato**:
>   non solo «chiamano `classifica_con_ai` senza settore», ma sia `/api/classify`
>   sia il fallback locale risolvevano il settore SOLO da `user_id`, e
>   `ricategorizza_sede_ai.py` passa `user_id=None` — cadeva su ristorazione
>   **per costruzione**; lo stesso script ha un punto post-AI che sovrascrive
>   l'esito col dizionario; e `ricategorizza_sede.py` non usa affatto l'AI, quindi
>   saltava il chokepoint dove la Fase 1 aveva messo il filtro. Tutti e quattro
>   sono la **famiglia dei sette buchi della Fase 1**: un gate a monte che non
>   copre il punto a valle, e si trovano eseguendo, non leggendo.
>   **43 mutanti, 7 dei quali hanno smascherato presidi finti** — il settore non
>   arrivava dall'endpoint al prompt; un `settore=` cercato in una finestra di
>   testo pescava la chiamata successiva (riscritto sull'AST); il vincolo del
>   prompt ristorazione asseriva sei sottostringhe **scelte**, ed era cieco
>   proprio sulle quattro righe che avevo cambiato senza accorgermene — una pure
>   sgrammaticata in produzione («trainato principalmente **da il pesce**»),
>   trovata dal reviewer confrontando gli md5 del prompt sui due commit. Ora il
>   confronto e' sul prompt **intero** contro uno snapshot del commit di ieri, e
>   il prompt dei ristoranti ha lo stesso md5 di prima. Nello stesso giro, **due
>   affermazioni false nei miei commit**, corrette. **Lo stesso difetto e'
>   tornato QUATTRO volte in questa fase sola** — il settore al prompt, i tool di
>   gruppo, i topic del configuratore, le pagine abilitate — ogni volta col
>   codice corretto e il presidio che misurava la funzione invece del suo uso.
>   L'ultimo e' il piu' grave: `_pagine_con_settore` e' il gate della **Fase 3**,
>   e con `pagine_abilitate` NULL (il default di quasi tutti gli account) un
>   mutante al call site fa tornare `None`, quindi nessun `tab_off_*` raggiunge
>   il client: gli spegnimenti si sarebbero spenti **in silenzio, a ogni login**,
>   con la suite verde. Regola scritta in testa a
>   `tests/test_wiring_settore_endpoint.py`: **provare la funzione non prova che
>   qualcuno la usi**, e per ogni gate si muta il CALL SITE. Suite **13.823
>   verdi, 45 skip** (+241 presidi, 0 test esistenti toccati), baseline a zero
>   dopo ogni casella, OpenAPI senza drift (196 endpoint), `tsc` pulito,
>   `_BRIEFING_CODE_VERSION` 23 → 24. Commit `23c0706`, `f76ddf1`, `ec43fc2`,
>   `a6bb45d`, `e91f576`, `d4867c0`.
>
> - **11/09/2026, branch `retail` (NON spedito) — Fase 3 del retail: spegnimenti,
>   etichette e le sei whitelist di scrittura.** Le whitelist validavano la
>   categoria in arrivo contro `TUTTE_LE_CATEGORIE`, la lista dei ristoranti: il
>   menu del client era gia' filtrato dalla Fase 1, ma la whitelist e' l'ultimo
>   cancello prima del DB, e una chiamata API diretta scriveva CARNE sulla riga
>   di un negozio. Quattro punti passano ora da `categorie_ammesse(settore)`; due
>   restano su `TUTTE_LE_CATEGORIE` **di proposito** (scrivono solo su
>   `prodotti_master`, memoria dei ristoranti gia' chiusa al retail). Ricette,
>   coperti e centri di produzione spenti col meccanismo `tab_off_*` esistente,
>   senza toccare `_normalize_pagine` (5 chiamanti). Etichette da un centro unico
>   col settore **opzionale**, default ristorazione. Trovato e chiuso un
>   disallineamento client/server: il menu della catena offriva a un negozio
>   categorie che il backend rifiuta con 400.
>   **17 mutanti, tutti uccisi, ma 3 presidi su 56 erano finti** e li ha
>   smascherati la mutazione: uno era sulla funzione condivisa invece che
>   sull'endpoint (mutante 6 sopravvissuto a 28 test verdi), uno confrontava il
>   frontend con la lista attesa scritta **dentro il test** (cambiavano in blocco
>   col mutante), uno contava anche i commenti. Suite **13.582 verdi, 45 skip**
>   (+56 presidi, 0 test esistenti toccati), `-m sql` 180, baseline a zero dopo
>   ogni casella, OpenAPI senza drift, `tsc` pulito. Commit `5d9f367`, `c7e0d3b`,
>   `dd6ac5e`, `c693a17`.
>
> - **11/09/2026, branch `retail` (NON spedito) — Fase 2 del retail: il prompt
>   dei negozi.** Il classificatore AI aveva un solo prompt, scritto per un
>   ristorante: a un negozio proponeva 26 categorie alimentari che la validazione
>   per settore (Fase 1) scartava tutte, e il sintomo era indistinguibile da
>   «l'AI non classifica niente». `PROMPT_CLASSIFICAZIONE_RETAIL` ha cinque
>   categorie e una domanda sola — si rivende, o serve a far funzionare il
>   negozio? — decisa da fornitore e contesto della fattura, non dal prodotto
>   (lo stesso martello e' merce in una ferramenta e attrezzatura in una
>   libreria); quando gli indizi mancano la riga resta `Da Classificare`.
>   `get_prompt_classificazione(articoli_json, settore=None)`: kwarg additivo,
>   `None`/`ristorazione`/valore ignoto ritornano **letteralmente** il testo di
>   oggi, provato per uguaglianza e non con `in`. Cablaggio: **una riga** in
>   `ai_service.py:5393`, unico consumatore vivo del prompt. +2 file di test
>   (28 test, 0 esistenti toccati), **11 mutanti uccisi**, di cui due rifatti
>   perche' invalidi (uno mutava un commento, uno non si applicava affatto: il
>   verde non misurava niente). Il decimo ha trovato un buco nel presidio
>   stesso — il regex copiato dal test food reggeva **per caso**: restava
>   verde su `NON e' MAI valida`, che non contiene né `NON è MAI` né
>   `MAI una risposta`. Chiuso anche sul test food l'11/9 (`87a0739`, ok
>   esplicito di Mattia per toccare un test esistente). Ottava
>   lettura del reviewer verde, con due residui-script dichiarati
>   (`catscan_*` senza gate settore, non scrivono: da guardare in Fase 4).
>   Verbale: `DOCUMENTAZIONE/RETAIL_FASI.md`. Suite **13.526 verdi, 45 skip**,
>   `-m sql` 180, baseline a zero x2.
>
> - **12/09/2026, `c171433`+`ba359d1`+`49a548b` — Gestione Fatture: "Escludi dai
>   conti" e la vista "Per mese".** Colonna `fatture.oscurata` (migration
>   APPLICATA sul DB live): il cliente toglie una fattura da tutti i conteggi
>   lasciandola visibile in lista. Il filtro non ha un choke point — ~30 query
>   Python e 13 funzioni SQL — quindi oltre ai presidi di comportamento c'e' una
>   guardia anti-decadimento (`tests/test_oscurate_choke_point.py`) che obbliga
>   ogni query nuova su `fatture` a dichiarare se conta soldi o no, con elenco
>   motivato delle esenzioni: senza, l'helper farebbe la fine di `filter_active`
>   (0 usi su 30 siti in `fastapi_worker.py`). Piu' `users.vista_fatture`
>   (migration APPLICATA) per la terza vista. **+70 test**, tutti provati per
>   mutazione: 3 mutanti isolati sulle RPC, 4 sui filtri frontend, 3
>   sull'endpoint, 1 sul fuso (muore solo su America/Los_Angeles), 1 sulla
>   guardia. Due reperti del reviewer chiusi: empty-state della vista per mese su
>   una collezione diversa da quella resa, e `auth_login` che non valorizza le
>   preferenze (inerte oggi, documentato dove si incontra). Suite **13.943
>   verdi, 45 skip**, `-m sql` 208 (23 funzioni del DB esercitate, verificate
>   contro `pg_proc`).
>
> - **10-11/09/2026, branch `retail` (15 commit, NON spedito) — Fase 1 del retail:
>   l'isolamento per settore.** Colonna `ristoranti.tipo_attivita` (migration
>   scritta, NON applicata), `services/settore_service.py`, e un kwarg additivo
>   `settore` lungo tutta la catena di classificazione (memoria, GPT,
>   `classifica_con_ai`, guardrail IVA, hint, worker, coda admin, propagazione,
>   agente notturno, dropdown, anteprima coda). Per i ristoranti niente cambia:
>   baseline di sola lettura sui dati veri a zero dopo ogni passo (56 righe di
>   costi, 3.475 categorie). Sette passate di review (sei del reviewer, una a
>   mano) hanno trovato **sette buchi della stessa famiglia** — un
>   `settore=None` arrivato per una ragione che non c'entra col settore — tutti
>   chiusi eseguendo il codice, non leggendolo. +16 file di test (5.699 righe,
>   0 test esistenti toccati), 69 mutanti uccisi, 1 sopravvissuto motivato.
>   Verbale completo: `DOCUMENTAZIONE/RETAIL_FASI.md`. Suite **13.498 verdi,
>   45 skip**, `-m sql` 180.
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

> - 18/09/2026, `0999871` — **coerenza visiva, fasi 0-1** (lavoro estetico, non
>   audit): token `--positivo`/`--negativo`/`--incerto` tarati sui due temi e
>   **senza consumatori** (la fase 0 non doveva cambiare un pixel, e non lo
>   cambia), piu' 10 rinomine di etichette. Suite **14.763 verdi + 45 skip**
>   (= 14.808, tutti i raccolti dalla root; da `tests/` sono 14.799), **di cui
>   539 su un Postgres vero** (`-m sql`): nel run di default girano, non sono
>   esclusi — `pytest.ini` non ha `addopts`, il marker serve a isolarli o a
>   escluderli **a richiesta**. Comando misurato: `python -m pytest -q
>   -p no:randomly`. **+5 test**, tutti sul file dell'export catena.
>   **Review: verde al SESTO giro**, 10 difetti veri (B1-B10). Nessuno trovato
>   leggendo: tutti da un mutante o da una ricerca rifatta con un metodo diverso
>   da quello che li aveva mancati. I tre piu' seri erano dentro *fix* di rilievi
>   precedenti — l'export Excel che diceva una parola diversa dallo schermo nella
>   stessa tabella; `truncate` messo per fare spazio che rendeva "12.450,00 €"
>   come "12.45…", un importo plausibile e falso; il presidio che a perimetro
>   vuoto taceva con un solo skip. In questa fase **la correzione e' stata
>   pericolosa quanto il difetto**.
>   **Aperto, dichiarato:** l'app non e' mai stata guardata a schermo. Le cifre di
>   layout vengono dalle metriche del font, e fra le due stime "calcolate" c'e'
>   stata una divergenza del 26% corretta solo al quinto giro. Da vedere su un
>   portatile a 1140/1280px: le card di Agenda -> Personale con le paghe
>   inserite — difetto **preesistente**, sede in fase 3.

> - 18/09/2026 sera, `47657a2` — **coerenza visiva, fase 2 (colore)**, 13
>   commit da `7bffae6`: nel frontend del cliente il colore passa dai token
>   (`primary`/`primary-text`/`accent`, `positivo`/`negativo`/`incerto`,
>   `grafico-1..5`), mai dalla palette Tailwind. Misurato dopo: **0 classi di
>   palette, 0 esadecimali, 0 `var(--color-*)`** nel perimetro (tutta
>   `apps/web/src` meno admin, demo, `/m`, landing, auth, legal); in tutto
>   `src/` da 1.561 a 458, tutte nelle aree escluse. Suite **15.485 verdi + 45
>   skip = 15.530 raccolti** dalla root (`python -m pytest -q -p no:randomly`),
>   **+722** rispetto alle fasi 0-1: `tests/test_globals_css_contrasto.py`
>   (41: converte l'oklch di `globals.css` in sRGB e misura il contrasto sui
>   fondi reali nei due temi; 6 mutanti uccisi) e
>   `tests/test_colori_solo_token_frontend.py` (674 casi su 168 file; 8 mutanti,
>   6 rossi e 2 verdi come atteso — un commento e admin non devono scattare).
>   `tsc --noEmit`: 0 errori nel sorgente. **Un bug preesistente trovato dal
>   presidio prima di nascere**: `text-destructive-foreground` nel dialog di
>   conferma, token mai dichiarato, che Tailwind rendeva come niente. Il primo
>   run completo aveva UN rosso — un test che chiedeva `dark:` alle classi
>   prezzo della catena, premessa vecchia — corretto in `47657a2`.
>   **Aperto, dichiarato:** l'app non e' stata guardata a schermo (da questa
>   sessione non si renderizza): la verifica nei due temi la fa Mattia, partendo
>   da `/style-guide` che ora mostra tutti i token. Residui nuovi in
>   `scratchpad/piano_coerenza_visiva.md` §12: il bianco sui bottoni
>   `bg-primary` (2,71:1 / 2,17:1, kit shadcn, decisione di Mattia) e «Viola»
>   tolto dal selettore del diario (nessun token; gli appunti gia' viola si
>   vedono blu, da confermare).

> - **23/09/2026, `0435b0f`→`e501355` (6 commit) — fase 1 «assistente
>   consulente»: il briefing smette di festeggiare le perdite e di sollecitare
>   l'impossibile.** Tre difetti misurati sui 43 briefing di produzione.
>   (a) **Buona notizia disonesta**: sede `dcf1996e`, 1-2/9, «Agosto mostra un
>   miglioramento: la perdita e' scesa a € 9.380» su due mesi con fatturato
>   **0,00** — la "perdita" era la sola somma dei costi. Il gate guardava
>   `costi_mancanti`, che per costruzione (`_kpi_periodo`) e' `fatturato > 0 and
>   fb <= 0 and spese <= 0`: **False proprio quando il fatturato e' 0**, cioe'
>   lasciava passare il caso che doveva fermare. Ora `_mesi_confrontabili` chiede
>   incassi su ENTRAMBI i mesi. Misurato nel farlo: col fatturato a 0 il MOL non
>   puo' essere positivo, quindi il ramo "crescita" era gia' protetto per
>   aritmetica — la sua guardia e' dichiarata **non presidiabile per mutazione**
>   invece che contata fra i mutanti uccisi.
>   (b) **Personale reclamato dal 1°**: la busta paga arriva a meta' mese, 5 sedi
>   su 5 "in ritardo" ad agosto e settembre erano la norma. Ora dal 15
>   (`_GIORNO_SOLLECITO_PERSONALE`), mesi piu' vecchi subito.
>   (c) **Incasso ripetuto ogni giorno** (ignorato 25 volte su 35, un cliente ha
>   spento 4 avvisi). Prima stesura sbagliata: avevo ancorato la `dedupe_key`
>   alla settimana ISO **senza verificare chi la legge** — `_build_snapshot`
>   raggruppa per `topic_key` e quella chiave finisce solo in
>   `notifications_fingerprint`, che per suo docstring nessuno rilegge: l'avviso
>   sarebbe tornato ogni giorno come prima. Il topic e' in
>   `TOPIC_LIVE_NON_IGNORABILI` (il cliente non puo' spegnerlo), quindi l'unica
>   misura e' **non emetterlo**: gate all'emissione.
>   **La scelta del giorno e' stata sbagliata due volte, per lo stesso errore di
>   misura.** Lunedi' per abitudine; poi martedi' perche' «lunedi' 16,9% di buchi
>   contro una media del 4-5%». Quel dato contava le **chiusure come
>   dimenticanze**: tutti e 11 i buchi del lunedi' erano di UNA sede (CASATI 14),
>   chiusa il lunedi'. Escludendo per ogni sede i giorni che non lavora, il
>   lunedi' ha **0 buchi su 52** e la distribuzione e' piatta (3-6%): si prende il
>   massimo, **giovedi'** (6,2%). Il reviewer ha confermato con un criterio piu'
>   severo (via anche 14 buchi consecutivi di ferie): 3 su 6 restano il giovedi'.
>   **Coerenza con Salute** (trovata cercando chi altro legge cio' che cambiavo,
>   non nel diff): il briefing taceva sul personale fino al 15 ma `/api/home/salute`
>   e `_salute_indice_rosso` lo marcavano mancante dal 1° — l'incoerenza che il
>   docstring di `home_salute` dichiara di voler evitare, e `_salute_indice_rosso`
>   e' **il gate della buona notizia**, quindi un dato non ancora dovuto la
>   sopprimeva. Regola unica in `_personale_gia_dovuto`, col caso del capodanno.
>   `_BRIEFING_CODE_VERSION` 24 -> 25. **Mutanti: 13 applicati, 12 uccisi, 1
>   sopravvissuto per scelta dichiarata** (il tredicesimo e' la guardia della
>   chat, aggiunta dall'ultimo commit della fase: tolta, cade
>   `test_il_prompt_chat_non_contraddice_briefing_e_card`; l'unico
>   sopravvissuto resta cambiare il VALORE del giorno: quale
>   giorno e' prodotto, non regola — i test lo derivano dalla costante apposta);
>   piu' il ramo "crescita" della buona notizia, non presidiabile per aritmetica
>   e percio' non contato. Uno alla volta, ripristino da `git checkout`.
>   **Tre miei errori di metodo, corretti e registrati perche' si ripetono:**
>   (1) ho chiamato in due punti una `def` andata persa in una riscrittura —
>   sintassi valida, suite verde, due `NameError` in produzione, perche' nessun
>   test eseguiva quei rami; (2) un `cp` di ripristino dentro un ciclo ha
>   sovrascritto il backup con una versione **gia' mutata**: una suite ha dato 11
>   rossi finti e una guardia e' rimasta disattivata a `pass` senza che il
>   checksum lo rivelasse — ora il ripristino si fa con `git checkout`, unica
>   fonte affidabile; (3) ho dichiarato «15.810 verdi» misurando il **working
>   tree**: il test corretto non era committato, quindi HEAD conteneva ancora la
>   versione debole. Una cifra si dichiara sullo stato committato.
>   Due presidi erano **finti** e il reviewer li ha smascherati: asserivano su
>   `inspect.getsource` (che il simbolo esistesse), non sul comportamento —
>   riscritti eseguendo `_salute_indice_rosso` e `home_salute`.
>   Suite **15.810 verdi, 45 skip** (`-m "not sql" -p no:randomly`), misurata a
>   repo fermo su HEAD `e501355`.
>   **Aperti, dichiarati:** (i) prima del 15 l'indice di Salute e' meno
>   probabilmente rosso e quell'indice e' il gate della buona notizia — 9
>   combinazioni passano da rossa a non-rossa, 5 con la voce fatturato rossa: la
>   notizia resta aritmeticamente vera, ma l'allargamento **va deciso da Mattia**;
>   (ii) `giorni_chiusura_settimanali` esiste su `assistant_preferences` (NON su
>   `ristoranti`) e `_briefing_dati_mensili_mancanti` **non lo legge**: una sede
>   chiusa nel giorno guardato riceve l'avviso a vuoto; (iii) il mobile continua a
>   scrivere in `notification_inbox` una riga al giorno che nessun lettore in
>   produzione usa piu'; (iv) **due segnali sui ricavi con due politiche
>   diverse** nello stesso briefing — `upload_ricavi_failed` tollera le chiusure
>   (`finestra = giorni_chiusura + 1`, `fastapi_worker.py:7341`, e il commento
>   li lega esplicitamente per coerenza) mentre `incasso_mancante` no. Oggi il
>   giovedi' lo maschera; riappare il giorno in cui qualcuno ritara la costante.
>   E' la stessa famiglia di (ii). **Chiuso invece il quarto consumatore della
>   regola del personale**, trovato dal reviewer nell'ultima passata sulle
>   inerenze: il prompt della chat (`_build_chat_system_prompt`) calcolava il suo
>   `personale_ok` senza la guardia e prima del 15 avrebbe detto «non
>   registrato» mentre briefing e card tacevano — l'assistente si sarebbe
>   contraddetto da solo. **Non pushato**: lo decide Mattia.
>
> - **23/09/2026 — fase 2 «quota chat»: la misura ha cambiato il lavoro.**
>   Il piano prevedeva il budget mensile 300/600/900 con tetto 10%/giorno. Prima
>   di scrivere codice ho misurato il consumo sul DB live, e **la premessa non ha
>   retto**: 95 righe in `chat_usage_log` da giugno, 4 utenti, picco 11 domande in
>   un giorno, massimo mensile 37 contro i 300 proposti. Il budget mensile
>   risolveva un problema che nei dati non si vede: **sospeso, e riportato a
>   Mattia come decisione di prodotto** invece che implementato.
>   **Il mio errore, ed e' quello che vale la pena registrare**: avevo concluso
>   «nessun cliente e' mai stato bloccato». Tre refutatori indipendenti (workflow
>   in sola lettura) l'hanno smontata e avevano ragione — quando il tetto scatta
>   la RPC ritorna `-1` **senza inserire**, e il ramo `429` non scriveva ne' su DB
>   ne' sul logger, a differenza del fail-closed adiacente che un `logger.warning`
>   ce l'ha. Nessuna tabella alternativa esiste (verificate e inesistenti:
>   `rate_limit_log`, `auth_events`, `audit_log`, `chat_blocks`, `api_requests`).
>   **Quella non era una misura, era l'assenza dello strumento di misura**: una
>   tabella da cui i casi cercati sono rimossi per costruzione non puo' dimostrare
>   che non esistano. Stessa famiglia di «una guardia non deve tacere quando non
>   sa». Chiuso con una riga di log, presidiata.
>   Altri due rilievi dei refutatori, verificati da me a DB e **veri**: (a) 23
>   chiamate chat del 19/06 esistono in `ai_usage_events` e **non** in
>   `chat_usage_log` — erano di `scripts/chat_eval_diagnosi.py`, il cui docstring
>   dice «Cancellare i log di test dopo se serve»: righe scritte e poi rimosse a
>   mano, quindi **quel registro e' cancellabile e non fonda un'affermazione
>   storica**; (b) i pool erano calcolati coi piani di **oggi** applicati
>   retroattivamente (SUSHILAND aveva 1 sede fino al 16/06, non 5).
>   **Tre difetti veri corretti**, tutti indipendenti dal budget mensile:
>   (i) **il giorno della quota era UTC** — il contatore si azzerava all'01:00
>   (CET) o alle 02:00 (CEST) di Roma e chi chattava dopo mezzanotte spendeva la
>   quota del giorno prima. **Non teorico: 1 riga su 95 gia' addebitata al giorno
>   sbagliato** (2026-06-17T23:25Z = 18/06 01:25 a Roma). Non era nemmeno una
>   convenzione del prodotto: due RPC usano gia' `(now() AT TIME ZONE
>   'Europe/Rome')::date` e `_oggi_rome()` ha un docstring che descrive esattamente
>   questo difetto — la quota chat era l'eccezione rimasta indietro. Corretta nei
>   **due** punti che devono restare allineati (RPC + `_chat_domande_oggi`), o il
>   contatore mostrato e quello applicato divergono. Chiude il residuo dichiarato
>   in **L6**.
>   (ii) il messaggio del 429 diceva «Riprova domani», falso nelle due direzioni;
>   ora dice **quando** si azzera, allineato nei 3 punti (backend + 2 fallback
>   client).
>   (iii) il blocco non lasciava traccia (sopra).
>   **La firma della RPC non cambia** (stessi 4 parametri): la chat **non si
>   spegne in nessun ordine** — il rischio che il piano segnalava non si applica.
>   **Ma un ordine c'e' lo stesso**, e il reviewer ha corretto la mia
>   semplificazione: a DB la RPC e' **ancora quella UTC** (verificato su
>   `pg_proc.prosrc`) e qui le migration si applicano **a mano**. Fra il push del
>   codice e l'applicazione della migration l'enforcement (RPC, UTC) e il
>   contatore mostrato (Python, Roma) **divergono** fra mezzanotte e le 02:00 —
>   esattamente la condizione che il mio docstring dichiara di voler evitare.
>   Nessuno spegnimento e platea minima (4 utenti, 17 domande in 7 giorni), ma la
>   regola e': **migration prima o insieme al push, mai dopo.**
>   **4 mutanti applicati, 4 uccisi** (fuso→UTC, messaggio backend→«Riprova
>   domani», logging rimosso, messaggio client→«Riprova domani»), uno alla volta,
>   ripristino per sostituzione inversa: qui `git checkout` avrebbe scartato anche
>   i fix non committati, e il blocco dell'ambiente me l'ha impedito giustamente.
>   **Il quarto e' nato da un rosso che avevo committato**: la suite completa
>   girava ancora quando ho chiuso `6325bb9`, e conteneva
>   `test_429_spiega_il_limite_giornaliero`, che asseriva la parola «domani» —
>   cioe' il testo che avevo appena tolto perche' falso (1 failed, 15.820 passed).
>   Corretto in `19a7cf5`: il presidio **esegue** il TypeScript vero, quindi a
>   invecchiare era l'asserzione, non il codice. Il difetto di metodo: avevo
>   cercato le occorrenze del messaggio nel **codice** ma non i **test che lo
>   asseriscono** — un messaggio all'utente ha due famiglie di consumatori, e la
>   seconda vive in `tests/`. Vale anche la regola gia' scritta: **una cifra si
>   dichiara sullo stato committato, e dopo che la suite ha finito.**
>   `tests/test_chat_quota_giorno_di_roma.py` (7 test, casi scelti **dove i due
>   fusi divergono** — fra mezzanotte e le 02:00 di Roma nei due regimi CET/CEST:
>   un'ora qualunque non distingue UTC da Roma e lascia vivo il mutante).
>   **I tetti, decisi da Mattia il 23/09/2026 e implementati.** Il consumo era
>   **distribuito al contrario del tetto**: l'unico cliente che usa la chat ha 2
>   sedi `base` (pool 20/giorno) ed e' in crescita (3, 4, 5, 6, 6), mentre chi ha
>   150/giorno non la apre. La sua decisione ha **rovesciato l'impianto**: il
>   vincolo vero e' il **mese**, il giorno e' solo un freno perche' nessuno bruci
>   tutto in due giorni. `CHAT_BUDGET_MENSILE_PIANO` 300/600/900 (gli stessi
>   totali di prima: i vecchi 10/20/30 × 30, ma prima il mese **non aveva alcun
>   limite** — un cliente poteva fare 900 domande senza che nulla lo fermasse), e
>   il tetto giornaliero **derivato** al 10% (`CHAT_QUOTA_GIORNALIERA_PCT`), mai
>   scritto a mano: due tabelle di numeri divergono al primo ritocco di una sola,
>   e qui la divergenza sarebbe invisibile perche' l'enforcement usa il
>   giornaliero e il messaggio il mensile. Effetto voluto: il tetto del giorno
>   **triplica** (base 10 -> 30), che era il punto di partenza.
>   **Il 10% e' una scelta, non un arrotondamento**: il mese deve coprire almeno
>   10 giorni di uso pieno; al 20% un cliente esaurirebbe il mese in 5 giorni e
>   resterebbe fermo per 25 — il problema che il meccanismo esiste per evitare.
>   **La RPC ora dice QUALE limite e' scattato** (`-1` giorno, `-2` mese) perche'
>   le due frasi sono diverse: «torna domani» a chi ha finito il mese lo rimanda a
>   un giorno in cui sara' fermo di nuovo — lo stesso difetto del «Riprova domani»
>   corretto poche ore prima, un piano piu' su. Il mese e' controllato **per
>   primo** perche' dura di piu'. Un chiamante che conosce solo il vecchio
>   contratto legge `-2` come negativo e blocca comunque: il fail-safe resta dalla
>   parte giusta. **2 mutanti, 2 uccisi** (i due messaggi collassati in uno; la
>   tabella giornaliera scritta a mano invece che derivata).
>   ⚠️ **Ordine di deploy OBBLIGATO, e qui la differenza con la migration del
>   fuso**: quella non cambiava la firma, `20260923152816_chat_budget_mensile.sql`
>   **si'**. Il call site passa un parametro nuovo e il codice e' fail-closed:
>   finche' la migration non e' applicata, PostgREST non trova quella firma e **la
>   chat si spegne per tutti**. La vecchia firma a 4 parametri resta viva apposta
>   (nessun `DROP`), cosi' durante la finestra un worker non aggiornato continua a
>   funzionare. **Migration PRIMA del push.**
>   **Da pianificare, non fatto** (Mattia, 23/09): il **«Boost AI» fra i Servizi**
>   — `lib/trigger-servizi.ts` ha gia' l'impianto (4 trigger soft, banner
>   discreto, max 1 per pagina, dismissibile) e `lib/assistenza.ts` i 6 servizi,
>   ma **nessuno e' il boost AI**: va aggiunto. Modello da definire con lui: X€ al
>   mese per N domande in piu' al giorno. Il tono deve restare quello degli altri
>   trigger, non un blocco che vende.
>   **Cinque rilievi del reviewer, tutti chiusi.** (1) **Un quarto punto del
>   messaggio che avevo mancato**: `chat-widget.tsx:189` diceva ancora «torna
>   domani» — l'header del widget, che il cliente legge **prima** del 429 ed e'
>   piu' visibile della risposta. Preesistente, ma nel perimetro: e' lo stesso
>   difetto di metodo del rosso committato — **ho cercato la stringa esatta, non
>   il concetto**. (2) La guardia `test_il_messaggio_di_limite_dice_quando_si_azzera`
>   era **cieca**: il reviewer l'ha provato con un mutante che sposta la frase in
>   un commento e tronca il messaggio (7/7 verdi). Sostituita con un assert sul
>   `detail` del 429 **vero**; quel mutante ora muore. (3) La copia mobile del
>   messaggio non aveva presidio: `mobile-chat.tsx` **ricopiava a mano** la stessa
>   catena di `if` di `lib/home-chat.ts`, identica riga per riga — due copie di cui
>   l'harness ne esegue una sola, ed e' il motivo per cui la correzione del 429 ha
>   dovuto toccarle entrambe. Ora il mobile **chiama** la libreria (via anche la
>   costante duplicata `MAX_STORICO_INVIATO`), con un presidio che uccide il
>   mutante «rimetti la copia». (4) L'ordine di deploy, sopra. (5) La cifra dei
>   mutanti nella riga **L6** era rimasta a «3»: e' la trappola «la cifra vive in
>   piu' punti», corretta dove guardavo. **Totale: 6 mutanti, 6 uccisi** — 4 miei
>   piu' i 2 del reviewer, che sopravvivevano ai miei presidi.
>   **Tre passate di review, due rosse.** La prima ha trovato **il difetto piu'
>   grave della sessione**, che sarebbe arrivato in produzione: avevo lasciato
>   viva la vecchia firma a 4 parametri «cosi' un worker non aggiornato continua
>   a funzionare». Misurato su Postgres vero: fa **l'esatto contrario**. Col
>   `DEFAULT NULL` la firma a 5 e' chiamabile anche con 4 argomenti, quindi le
>   due sono entrambe candidate e Postgres solleva `AmbiguousFunction` — fra
>   migration e deploy il worker vecchio si rompe e, col fail-closed, **la chat
>   si spegne per tutti**: precisamente l'incidente che quella frase diceva di
>   evitare. Il rimedio era una riga, ed era gia' il precedente della casa
>   (`20260619100000_chat_usage_pool.sql`). Il `DROP` va **prima** del `CREATE`:
>   in fondo lascerebbe una finestra di pochi istanti in cui le firme coesistono.
>   **La seconda rossa: lo stesso mio errore due volte di fila.** Ho scritto
>   codice e non l'ho presidiato — prima il payload verso la RPC (si poteva
>   cancellare `p_limite_mensile`, cioe' spegnere la feature, con 15.836 test
>   verdi), poi i campi verso il frontend (`chat_limite_mese`/`chat_domande_mese`
>   non erano nominati da **nessun** test). Un presidio era anche una tautologia:
>   confrontava `CHAT_LIMITI_PIANO` con la funzione che lo produce, quindi una
>   tabella scritta a mano **coi valori giusti** passava. Ora verifica il
>   MECCANISMO: cambiata la percentuale, i tetti devono seguire.
>   **E un difetto di vista**: col giorno al 10%, chi va a pieno regime esaurisce
>   il mese al giorno 10 — dall'11 al 30 il contatore avrebbe detto «ti restano
>   30 domande oggi» mentre ogni invio prendeva 429. Lo stesso difetto di
>   promessa falsa corretto nel MESSAGGIO, lasciato nella VISTA.
>   **Mutanti: 20 riapplicati dal reviewer nella sola terza passata, tutti
>   ancorati per numero di riga e ripristinati con diff vuoto.** Nessun terzo
>   livello scoperto: `_chat_budget_mensile_per_piano`, `_chat_budget_mensile_pool`,
>   `quotaEsaurita`, il ramo `-2`, il `max(1, ...)` e `CHAT_QUOTA_GIORNALIERA_PCT`
>   hanno tutti un presidio **che esegue**.
>   **Quattro gap dichiarati e NON chiusi, perche' ereditati e simmetrici**: i
>   medesimi mutanti sopravvivono sul gemello del GIORNO, codice che questa fase
>   non tocca. (i) invertire il filtro di proprieta' in `_chat_domande_mese`
>   (`ristorante_id` <-> `user_id`) sopravvive — **sarebbe un leak fra clienti**,
>   e vale un presidio quando si torna sul file; (ii) cambiare la tabella letta;
>   (iii) `None if _chat_pool else ristorante_id` -> `ristorante_id`, che sbaglia
>   il conteggio dei multi-sede; (iv) il default di `chat_limite_mese`.
>   **Suite: 15.833 passed, 45 skipped, 0 failed** (`-m "not sql" -p no:randomly`),
>   misurata su `c240208`; durante il run un'altra sessione ha committato
>   `bf28328` (fase 3 margini, nessun file mio), quindi la cifra include anche i
>   loro test nuovi. **Non pushato.**
>
> - **24/09/2026 — fase 4 «assistente consulente», primo passo: due osservazioni
>   calcolate nel briefing. La misura ha di nuovo cambiato il lavoro.**
>   Il piano elencava cinque topic da consulente. **Prima del codice**, misura sul
>   DB live (sola lettura, stessa pipeline di `home_kpi`) su 8 sedi reali con
>   dati: food cost del mese sopra il 33% in **22 mesi consolidati su 32, 7 sedi
>   su 8** (condizione normale, non notizia); fornitore oltre l'80% di una
>   categoria in **26 coppie su 33, 7 sedi su 8** (quasi tutto bevande da un
>   distributore); prodotto/categoria in salita da 3 mesi: **0** alle soglie
>   utili, 3 casi da +1-6% a soglia zero (rilevatore verificato non cieco); le
>   scadenze «accumulate» falsate da **4 sedi su 8 che non segnano mai
>   «pagata»** (318-635 fatture «scadute» a sede); il MOL mese su mese cala circa
>   un mese su due, trainato da spese a gradini. **Il blocco vero e' la
>   freschezza**: fatture ferme al 30/06 su 4 sedi e a fine luglio su 2, e
>   l'ultimo mese caricato sistematicamente parziale (merce -27/-38%). L'unico
>   dato fresco ogni giorno e' l'incasso: 4 settimane contro 4, oltre il 10% in
>   7 valutazioni su 73. Riportato a Mattia, che ha scelto di procedere.
>   **Fatto**: `andamento_incasso` (il martedi', 4 settimane lun-dom contro le 4
>   prima, >= 20 giorni per finestra, da ±10%, coperti e scontrino se inseriti)
>   e `food_cost_alto` (finestra MOL, mese di due mesi prima solo se consolidato
>   dalla **merce** del mese dopo, oltre il 33% di `KPI_SOGLIE`, euro sopra la
>   norma, mai per il retail). Stanno nell'apertura, non sono card, si spengono
>   dal configuratore, **solo dal path asincrono** (E7). Il validatore della
>   narrativa ha un terzo controllo, `obbligatori`: se l'AI perde la percentuale
>   di un'osservazione si ricade sul template — un prompt non e' una garanzia.
>   `_BRIEFING_CODE_VERSION` 26 -> 27. Dettaglio in
>   `DOCUMENTAZIONE/tecnica/BRIEFING_HOME.md` §5-bis.
>   **Due mie affermazioni corrette dalla misura, prima del commit.** (a) Avevo
>   detto a Mattia che CASATI aveva agosto «consolidato»: la misura contava
>   qualunque fattura di settembre, ma erano solo utenze e manutenzione — il
>   codice guarda la merce e giustamente tace. (b) «Il lunedi' mattina l'incasso
>   della domenica puo' mancare» era un ragionamento: misurato dopo, manca nel
>   **28%** delle domeniche (22 su 78) il lunedi' e nel **15%** il martedi'.
>   **Eseguito sul DB live** (sola lettura) per ogni sede: da giugno
>   l'andamento sarebbe uscito 7 volte in 17 martedi' su 5 sedi; il food cost di
>   giugno a 5 sedi il 3/8; quello di luglio e agosto a nessuna.
>   **Mutanti: 27 per cancellazione, 27 uccisi**, uno alla volta, verificato che
>   il codice fosse cambiato, ripristino dal backup preso prima del primo mutante
>   con md5 identico (niente `git checkout`). Due guardie tolte **prima** della
>   mutazione perche' ridondanti (costi mancanti gia' coperti da food cost 0 o
>   nullo; osservazioni fuori dalle card gia' non azionabili): un mutante
>   sopravvissuto li' avrebbe accusato il test di una riga morta.
>   **Aperti, dichiarati:** (i) se la sede non ha altro da fare, «Tutto in ordine
>   per oggi» puo' comparire sotto un food cost critico — oggi su 0 sedi (tutte
>   hanno almeno un sollecito); il riquadro e' nel frontend, fermo sulla
>   decisione interfaccia; (ii) il 15% delle domeniche arriva dopo il martedi':
>   in quelle settimane l'ultima finestra ha un giorno pesante in meno; (iii) la
>   regola 3-ter-bis del prompt non e' presidiabile (testo al modello), la
>   difende il validatore; (iv) il secondo pezzo della fase — i solleciti in una
>   riga — non e' in questo commit.
>   **Prima passata del code-reviewer: NON CHIUSA, e aveva ragione.** Mutando su
>   una copia (`git archive`) ha trovato due regole scritte nella doc e senza
>   presidio: il minimo di 20 giorni sull'**ultima** finestra (la guardia contro
>   la sede che smette di inserire: 14 giorni su 28 farebbero un falso «-50%») e
>   il minimo di 20 giorni per i **coperti** (chi comincia a inserirli avrebbe
>   letto «+400%»), piu' lo scontrino calcolato sui soli giorni con coperti e la
>   fusione del fatturato mensile. Il codice era giusto, i test no: i miei 27
>   mutanti coprivano cio' che avevo scritto, non ogni regola dichiarata. Corretti
>   anche: numeri obbligatori pretesi nel ramo onboarding, testo AI troncato dal
>   limite di token accettato, settore letto fuori finestra, descrizione del
>   configuratore («una volta al mese» -> esce per 8 giorni). **8 mutanti nuovi,
>   8 uccisi.**
>   **Seconda passata: ancora NON CHIUSA, per il caso speculare.** Avevo
>   presidiato i coperti parziali nella finestra PRECEDENTE, non nell'ultima: la
>   sede che smette di inserire i coperti ma non l'incasso (falso «coperti -57%»)
>   restava scoperta — lo stesso errore del primo giro, sul lato opposto della
>   stessa regola. Test aggiunto, mutante ucciso. **Totale: 36 mutanti, 36
>   uccisi.** Ridondanti dichiarati dal reviewer: `cop_b > 0` (implicato da 20
>   giorni con coperti) e `d > 0` -> `d >= 0` (equivalente).
>   **Suite: 15.933 passed, 45 skipped, 0 failed** (`-m "not sql" -p
>   no:randomly`) su `e4d0d44`, HEAD fermo per tutto il run; nel working tree
>   c'erano file non committati di altre sessioni (tema, brevo). Un primo run su
>   `3d7ce5b` si era fermato su `test_home_briefing_cache_first` (1 failed):
>   **non riprodotto** — verde da solo, in coppia col file nuovo e nel run
>   completo successivo. Causa non identificata, dichiarata come tale.
>   **Da fare prima del push, non mio**: `openapi/openapi.json` e' in drift per
>   `AcceptSuggestionRequest.emoji` (commit `e874f8a`, sessione dei tag).
>   **Secondo pezzo, stesso giorno: i solleciti in una riga.** Fatturato,
>   personale, incasso di ieri e fatture del mese senza costi restano card, ma
>   nel racconto sono una riga in coda alle cose da fare («Per completare il
>   quadro mancano …»), anche nell'input all'AI (un solo bullet 🧩). Le fatture
>   che NON arrivano (SDI fermo, avvio) restano frase propria: sono un possibile
>   guasto, non un dato da inserire. Nessuna nuova versione: la 27 non e' mai
>   stata deployata. **11 mutanti, 11 uccisi.** Non eseguito sul DB live: la
>   raccolta delle notifiche scrive (ultimo accesso, promemoria agenda), quindi
>   il caso reale e' quello di produzione del 23/09 riprodotto nel test.
>   **Quarta passata del reviewer: NON CHIUSA, per un difetto vero che non avevo
>   visto.** Il producer `_briefing_dati_mensili_mancanti` metteva in
>   `payload['mese']` del personale SEMPRE il mese precedente, anche quando
>   l'unico mese mancante era un altro (il vero stava solo in `descrizione` e
>   nel titolo). Card, frase e fusione lo leggono da li': con luglio senza
>   personale e agosto senza fatturato il briefing diceva «il fatturato e il
>   costo del personale di agosto». **Preesistente dal 25/06**, ma il commit
>   `0435b0f` della fase 1 (personale dal 15, anch'esso non pushato) lo rende
>   frequente: dal 1 al 14 di ogni mese il mese appena chiuso esce dalla lista e
>   resta un mese piu' vecchio. Misura del reviewer: una sede ha solo agosto
>   scoperto, e dal 1/10 avrebbe letto «settembre». Il mio test non lo vedeva
>   perche' la fixture era **scritta a mano** con il mese mancante in `mese`:
>   non aveva la forma del payload vero. Ora un test parte dall'output del
>   producer. Chiuso anche il caso speculare: la frase fusa da sola (plurale),
>   e la fusione che distingueva «Agosto» da «agosto». **3 mutanti, 3 uccisi**
>   (14 in tutto sul secondo pezzo). Suite su `e0b189e`: **15.948 passed, 45
>   skipped, 0 failed** (`-m "not sql" -p no:randomly`), HEAD fermo.
>   **Certificata dal code-reviewer alla quinta passata** (`30e1e16`). Suite su
>   `30e1e16`: **15.955 passed, 45 skipped, 0 failed**, HEAD fermo. Nella stessa
>   chiusura: due file di test della fase 1 (`test_briefing_solleciti_calendario`,
>   `test_briefing_dati_mensili`) davano errore di raccolta lanciati da soli,
>   verdi in suite solo per l'ordine dei file — ora impostano l'ambiente.
>   **Non pushato.**
>   *Coda del 24/9 sera — la documentazione.* `LOGICA_BRIEFING.md`, il doc su
>   cui Mattia decide soglie e ordine, **non conteneva né la fase 1 né la 4**:
>   diceva ancora il personale reclamato dal mese precedente senza il giorno 15,
>   l'incasso mancante ogni giorno, il MOL festeggiato senza guardare il
>   fatturato, e nessuna osservazione. Anche `BRIEFING_HOME.md` era senza la
>   fase 1 (i commit `c61043c`/`664724d`/`d81bcbb` toccavano solo questo
>   verbale). Aggiornati entrambi; le **7 leve nuove** della tabella §9 entrano
>   in `test_logica_briefing_tabella_leve_tutta_verificata`, lette dalle
>   costanti. **7 mutanti sul doc, 7 uccisi.**
>
> - **24/09/2026 — fase 6 «assistente consulente»: la catena allo stesso livello
>   del PV.** Testo fisso, niente AI (decisione di Mattia). Due pezzi.
>   **A — il personale «dal 15» in catena.** La review pre-push del deploy del
>   24/9 aveva visto che la regola della fase 1 (`_personale_gia_dovuto`) stava
>   nei 4 consumatori del PV ma non in `gruppo.py`: dal 1° al 14 la catena
>   abbassava l'indice della sede, diceva «Mancano il costo del personale» e
>   «da completare» dove il PV taceva, visibile dal 1° ottobre. Ora
>   `_personale_non_ancora_dovuto` governa indice, avviso e frase; la sede resta
>   fuori dal confronto e la card Conti resta ambra, perche' il margine senza
>   personale e' davvero gonfiato. **B — le osservazioni del PV in catena**
>   (`_calcola_osservazioni`, riuso integrale di calcolo e frase), lista a parte
>   nella card «Da sapere», fuori dal conteggio degli avvisi, spegnibili in tre
>   modi. **La review ha trovato 2 blocchi veri**: due test esistenti sarebbero
>   diventati **rossi ogni martedi'** (il 29/9 il primo, prima della scadenza),
>   perche' l'endpoint ora calcolava le osservazioni sul loro client finto e il
>   mio «degradato» toglieva la cache; e **due mutanti sopravvivevano sul
>   collegamento dell'endpoint** (config e utente non passati), perche' i miei
>   test dell'endpoint mockavano la funzione ignorandone gli argomenti. La mia
>   verifica «al giorno 5» cambiava il giorno del mese, non quello della
>   settimana. Corretti: osservazioni best-effort come nel PV (il «degradato»
>   avrebbe spento cache e verde per un giorno intero a un guasto persistente),
>   uscita anticipata fuori dai giorni utili, rete intorno al calcolo, test che
>   cattura gli argomenti. Suite rifatta con la data forzata a **tre giorni**
>   (mar 29/9, dom 5/10, mar 6/10): 1.454 passed ciascuno.
>   **Mutanti sul codice finale: 38, tutti uccisi** (13 su A, 22 sul backend di
>   B, 3 sulla logica del frontend) — uno, la versione dei segnali non alzata,
>   solo dopo il test che ne ancora il valore (`>= 3`, come `_BRIEFING_CODE_VERSION`).
>   **Secondo giro della review**: un mutante sopravviveva allo spegnimento dal
>   configuratore della catena (`spenti = set()`), perche' la mia uscita
>   anticipata faceva passare i due test sullo spegnimento prima di arrivarci:
>   la correzione del primo giro aveva svuotato il presidio. Test aggiunto sul
>   martedi' in finestra, dove parlano entrambe; il reviewer ha girato 31
>   mutanti suoi, 29 uccisi, 1 equivalente (`cta_page`).
>   `_SEGNALI_CODE_VERSION` 2→3. Misura sui dati veri (sola lettura, 3 catene):
>   parlera' poco finche' i dati restano fermi — un'osservazione il martedi' 1/9
>   su 5 sedi, food cost di ottobre muto per le fatture di settembre assenti.
>   **Suite: 16.037 passed, 45 skipped** (`python -m pytest tests/ -m "not sql"
>   -q -p no:randomly`, working tree: include +2 test non committati di un'altra
>   sessione in `test_brevo_mittente_default.py`) **+ 545 `-m sql`**. Il reviewer,
>   su un clone pulito a `e316533` con `WORKER_DEV_MODE=1` e senza chiavi, misura
>   16.042: ambiente diverso, cifra non confrontabile 1:1. Drift OpenAPI
>   rigenerato; `tsc` pulito. Un primo giro `-m sql`
>   aveva dato 541 *errors*: `/dev/shm` pieno di 62 Postgres di test orfani,
>   non il codice. **Non pushato: va deployato prima del 1/10.**
>
> - **24-25/09/2026 — fase 7a «assistente consulente»: la STRUTTURA
>   dell'email settimanale, spenta.** Mattia: «il contenuto va studiato, la
>   struttura si pianifica»; a tutti i clienti attivi con disiscrizione, lunedi'
>   mattina, link alla Home. Fatto: invio condiviso (`services/email_service.py`,
>   template identico byte per byte a quello di admin.py, verificato), migration
>   `20260924223755_email_settimanale.sql` (preferenza default accesa + registro
>   UNIQUE utente/lunedi', CHECK, REVOKE nominale), `email_settimanale_service`
>   (destinatari, sezioni con un solo segnaposto, token HMAC fail-closed, tre
>   sicure: dry_run, `EMAIL_SETTIMANALE_ATTIVA`, registro-come-prenotazione),
>   13° router, anteprima admin, pagina pubblica `/disiscrizione` (nessun GET
>   che agisce) e one-click RFC 8058, interruttore nelle Impostazioni, cron del
>   lunedi'. **Due presidi esistenti hanno fermato il lavoro, giustamente**: la
>   guardia dei router (ogni endpoint dichiara la sua protezione, e il conteggio
>   dei router e' fissato) e quella dell'identita' dichiarativa (un endpoint
>   senza utente va motivato per iscritto), piu' la ricetta d'isolamento per
>   `solo_user_id`. **La review ha trovato un difetto vero**: col runbook come
>   l'avevo scritto (segreto assente fino alla 7c) l'anteprima — lo strumento
>   della 7b — andava in 500 in produzione, e i test non lo vedevano perche' la
>   fixture impostava sempre il segreto. Corretti anche: finestra d'invio 7-9:59
>   (con un'ora sola, un cron in ritardo di mezz'ora perdeva la settimana in
>   silenzio), cron spostati al :35 (alle 06:30 gira gia' un altro controllo),
>   token non ASCII (500 → 400), un errore del registro che fermava tutti i
>   clienti successivi, falso allarme Telegram ogni lunedi' a invio spento.
>   **Mutanti: 43, tutti uccisi** — 3 sopravvissuti al primo giro (intestazioni
>   verso Brevo, REVOKE su anon e authenticated: lo snapshot dei test non
>   riproduce le default privileges di Supabase, ora simulate e la migration
>   rieseguita), chiusi con test nuovi. **Suite: 16.144 passed, 47 skipped**
>   (`-m "not sql" -p no:randomly`, working tree con +2 test non committati di
>   un'altra sessione) **+ 553 `-m sql`**; OpenAPI 202 endpoint, `tsc` pulito.
>   **Prima del push che la porta**: applicare la migration (senza, la pagina
>   Impostazioni va in 500) e impostare `EMAIL_DISISCRIZIONE_SECRET` su Railway.
>   `EMAIL_SETTIMANALE_ATTIVA` resta assente fino alla 7c (privacy). **Non
>   pushato.** *Secondo giro della review*: CHIUSA, con tre mutanti suoi
>   sopravvissuti — un errore vero del registro contato come «settimana gia'
>   gestita» (i miei test sostituivano l'intera funzione invece di farla
>   fallire dentro), la preferenza fissa a «accesa» in `/api/account/me` e
>   tolta dall'export art. 20. Chiusi con 4 test (47 mutanti in tutto).
>
> - **25/09/2026 — fase 7b: il contenuto dell'email settimanale.** Prima la
>   misura, in sola lettura sui 4 lunedi' precedenti: 3 clienti con numeri
>   affidabili, 3 fermi (nessun dato da 4 settimane o mai). Poi la decisione di
>   Mattia: «mi spaventa inviare informazioni inutili o incomplete» — ogni
>   argomento parla solo se per quel cliente il dato e' affidabile. **La misura
>   ha smentito l'ipotesi di partenza**: l'SDI «attivo» non vuol dire fatture
>   automatiche (una catena lo ha su 4 sedi e carica tutto a mano, 214 fatture in
>   un giorno); il criterio e' il canale d'arrivo (`invoicetronic`) negli ultimi
>   30 giorni. Le note di credito sono salvate con importo positivo: escluse.
>   Quattro sezioni (incasso della settimana con entrambe le settimane a ≥6
>   giorni meno la chiusura dichiarata, fatture dallo SDI sul calendario di
>   Roma, osservazioni della fase 4 col producer vero, invito a riprendere a chi
>   e' fermo da 28 giorni); niente compiti. **Mutanti: 31**, 29 uccisi e 2
>   equivalenti (il limite superiore della settimana controllato due volte, in
>   query e in Python): tolto il doppione, i 5 mutanti sul controllo rimasto
>   muoiono. Il presidio L5 (`test_audit_ciclo_vita_colonne`) ha visto il file
>   nuovo che nomina `deleted_at`: taratura 33 → 34, motivata. Regole per Mattia
>   in LOGICA_BRIEFING §8-bis. **Suite: 16.196 passed, 47 skipped** (`-m "not
>   sql" -p no:randomly`, working tree con +2 test di un'altra sessione) **+ 553
>   `-m sql`**. L'email resta SPENTA: manca la 7c (privacy, segreto, prova).
>   *Review (CHIUSA, nessun blocco), cinque punti chiusi prima della 7c*: il
>   database non passato alle sezioni restava verde (i test del lavoro del lunedi'
>   usavano una sezione fissa) — ora un test fa girare `esegui` e `anteprima` con
>   le sezioni vere; una sezione fallita diventava «niente da dire» senza avviso
>   — ora e' un errore e la settimana non si registra; «dal 8», «dal 11», «dal
>   1» nelle date vere — ora «dall'8», «dall'11», «dal 1°»; preferenze
>   illeggibili = osservazioni ferme (fail-closed: un'email non si ritira);
>   l'anteprima di martedi' mostrava l'andamento che il lunedi' tace — la
>   sezione passa il suo giorno a `_briefing_osservazioni`. 10 mutanti, 10
>   uccisi.
>   Decisione di Mattia sul sesto punto: le fatture dallo SDI della sede
>   tecnica «Costi comuni di gruppo» entrano nell'elenco (per OFFSIDE erano 10
>   in una settimana, taciute), e solo li'. 5 mutanti, 5 uccisi.
>
> - **25/09/2026 — fase 7c: privacy e chi la riceve.** Alla richiesta di
>   approvare il testo privacy Mattia ha cambiato una decisione della 7a: «non e'
>   per tutti, e probabilmente per nessuno degli attuali clienti» — la abilita lui,
>   cliente per cliente. **Due interruttori, non uno**:
>   `users.email_settimanale_abilitata` (admin, default spento, migration
>   `20260925084916`) e `users.email_settimanale` (la scelta del cliente, che
>   resta): con una colonna sola, abilitare un cliente disiscritto avrebbe
>   annullato la sua disiscrizione. Scheda admin con l'interruttore e «Mandami una
>   prova» (compone l'email del cliente e la spedisce all'admin con [PROVA], senza
>   registro e anche prima di abilitarlo: gli admin sono esclusi dai
>   destinatari, quindi senza questo la «prova sulla tua casella» del piano non
>   era possibile). Nelle Impostazioni la scheda compare solo se abilitata
>   (`mostraEmailSettimanale`, provata con node). Informativa privacy v4.3 col
>   testo approvato da Mattia (+ «se e' attiva per il tuo account»); nessun
>   preavviso: per decisione di Mattia oggi non la riceve nessuno. Chiusi i
>   residui della review 7b (food cost col giorno dell'email, testo dell'avviso,
>   sezioni cadute nell'anteprima). Il finto DB dei test ora restituisce solo
>   le colonne chieste (un mock generoso non vedeva una colonna dimenticata nel
>   select). **Mutanti: 23, tutti uccisi.** Suite `-m "not sql"`: 2 rossi di
>   passaggio dal lavoro in corso di un'altra sessione (saldo Invoicetronic), verdi
>   al rilancio; `-m sql` 553 passed; OpenAPI 203 endpoint. Due file di doc
>   condivisi con quella sessione (MAPPA_TECNICA, DEPLOY_RUNBOOK): committate solo
>   le mie righe.
>   *Review 7c (CHIUSA)*: l'email di prova all'admin portava il link di
>   disiscrizione del cliente, nel testo e nel `List-Unsubscribe` one-click: un
>   clic su «Annulla iscrizione» in Gmail avrebbe disiscritto il cliente a sua
>   insaputa, senza rimedio dall'admin. Ora `componi_email(prova=True)` li toglie
>   entrambi. 4 mutanti, 4 uccisi.
>
> - **25/09/2026 — residui tecnici del piano consulente, tutti chiusi.**
>   (1) *Il conteggio della chat fra clienti*: invertire il filtro di proprieta'
>   in `_chat_domande_oggi/_mese` sopravviveva ai test (mock che accettavano
>   qualunque `eq`); ora un finto DB che filtra davvero, con due clienti e due
>   sedi, e i quattro chiamanti che passano `None` solo in pool — 15 mutanti
>   uccisi. (2) *Virgola nelle percentuali* del briefing in 3 frasi (buona
>   notizia, card MOL, avvisi prezzi); verificato che l'anonimizzazione dei nomi
>   verso OpenAI riconosce anche «+12,5%», e il test dell'anonimizzazione ora
>   usa il bullet PRODOTTO dal codice, non una stringa a mano (il suo stesso
>   commento ricordava un leak nato cosi'). `_BRIEFING_CODE_VERSION` 27 -> 28.
>   Un primo giro di mutanti dava «no tests ran»: rifatto. (3) *Il 429 della
>   chat* confrontato intero: «30» e' dentro «300». (4) *Chiusure*: «manca
>   l'incasso di ieri» tollera N giorni di chiusura come i ricavi automatici
>   (misurato: oggi nessuna sede ne dichiara, testo invariato per tutti).
>   (5) *La riga mobile quotidiana*: tolti endpoint e componente che scrivevano
>   ogni giorno una riga mai letta; e la campanella ora la scarta sempre — lo
>   scarto stava dentro il try del calcolo live, e un suo errore mostrava la
>   riga vecchia. (6) *Negozi*: la riga dei dati mancanti non dice «food cost»
>   (settore passato fino al testo, all'AI e al percorso veloce della Home).
>   (7) Ripiego sul titolo con il mese minuscolo. (8) *Costi AI*: il tracking
>   stava dopo i tre ritorni al template, quindi le frasi scartate erano pagate
>   ma non registrate. Mutanti totali: ~45, tutti uccisi o dichiarati
>   equivalenti (2). Suite `-m "not sql"`: 16.360 passed (1 rosso che fissava
>   «di Agosto» maiuscolo a meta' frase: aggiornato), `-m sql` 553, OpenAPI
>   202, `tsc` pulito sui sorgenti (un file generato dal dev server locale in
>   `.next/dev` cita la route tolta: non e' nel repo). **Non pushato.**
>
> - **25/09/2026 — passo 0 del piano «invio XML al commercialista»: l'avviso
>   sul saldo crediti Invoicetronic.** Prima la misura: a saldo zero il webhook
>   segna `failed` con «HTTP 403», il worker ritenta 8 volte e in circa 2 ore
>   ogni fattura in arrivo e' `dead`, per tutti i clienti e senza avviso (nessuna
>   chiamata a `/status` nel repo). Fatto: `services/invoicetronic_saldo.py`
>   (`GET /status` solo verso l'host Invoicetronic; soglia 100 da env; avvisi
>   Telegram sotto soglia subito e poi ogni 24 ore, subito se peggiora,
>   «rientrato» una volta, «illeggibile» al 2° controllo fallito e poi ogni 4),
>   controllo ogni 6 ore nel queue-worker con errore nel log all'avvio se
>   mancano le chiavi. Il 403 del saldo si riconosce dal `code` (il 403 da solo
>   vale anche per firme e sotto-chiavi): nel webhook la riga e' marcata
>   `payload_meta.api_error_code` e l'avviso parte al massimo una volta all'ora;
>   nel recupero XML del worker il motivo arriva a `last_error`. **Prima prova
>   del flusso vero della Edge Function**: nessun test eseguiva `processaEvento`;
>   ora un punto d'iniezione del client DB lo fa girare con un 403 simulato.
>   **Trovato**: `fetchXmlForResource` non ha chiamanti dal 30/7 (tolto il
>   reprocess), lasciata dov'e'; la Edge Function in produzione (v40) e' indietro
>   di un solo commit, che cambia un commento. **La review ha fermato la
>   chiusura, a ragione**: gli avvisi consigliavano «Riprova» dopo la ricarica,
>   ma le fatture fermate al webhook non hanno cliente (`user_id` NULL, P.IVA
>   `UNKNOWN`) e il worker, pur riscaricando l'XML, si ferma a «Tenant non
>   risolto» — lo stesso buco che da sempre ha il 404 temporaneo. Oggi nessuno
>   strumento le recupera: avvisi e runbook §4bis ora lo dicono, e sconsigliano
>   di assegnare il cliente a mano (il percorso della coda non ricontrolla la
>   P.IVA dell'XML). **Residuo aperto: il recupero** (il worker che ricava il
>   cliente dall'XML come fa il webhook), passo a parte. Corretti anche `/status`
>   rifiutato per saldo (ora vale 0, non «illeggibile») e due promesse del
>   runbook. **Mutanti: 41, tutti uccisi** — uno sopravviveva al primo giro (la
>   chiamata del controllo chiavi dentro `main` non era osservata): aggiunto il
>   test. Durante i mutanti la suite di un'altra sessione ha visto 2 rossi di
>   passaggio: la trappola nota dei mutanti letti da una suite in corso.
>   **Suite `-m "not sql"`: 16.314 passed, 48 skipped** (prima dei ritocchi della
>   review; 553 `-m sql` non rilanciati: nessun SQL toccato); **Deno 126**. Da
>   deployare: push (queue-worker) + Edge Function a mano.
>
> - **25/09/2026 — passo 0-bis del piano «invio XML al commercialista»: le
>   fatture che il webhook non ha potuto leggere ora ripartono.** Il residuo
>   aperto dal passo 0: una GET a Invoicetronic fallita nel webhook (saldo, 404,
>   timeout) lascia la riga senza cliente, e il worker — riscaricato l'XML — si
>   fermava a «Tenant non risolto»; «Riprova» la riportava a `dead`. Prima la
>   mappa, in sola lettura, con un workflow di 4 lettori e un critico: il gemello
>   Python (`multisede_routing`) non e' il webhook (niente candidati di ripiego,
>   che risolvono 26 fatture OFFSIDE su 34; niente CF; P.IVA normalizzata in un
>   altro modo). Fatto: `services/routing_coda.py`, porting riga per riga del
>   routing del webhook, con `routing_parita.json` letto da Deno e da Python;
>   nel worker `_risolvi_cliente` PRIMA del parsing (memoria e settore del
>   cliente), una sola UPDATE guardata da stato e lock, tentativi azzerati sulle
>   righe parcheggiate (senza, resolve_unknown_tenant le rimetteva pending
>   all'8° tentativo e nessuno le prelevava piu'); il nome SDI vero (serve ai
>   doppioni e al riparto); «Riprova» anche sulle fatture senza cliente nel
>   pannello. **Due scarti voluti dal webhook, verso il non assegnare**: la
>   P.IVA si legge con regex E parser XML e si assegna solo se coincidono (il
>   file di parita' mostra la regex del webhook ingannata da un commento e dal
>   RappresentanteFiscale); una P.IVA su piu' account non si assegna (il webhook
>   prende l'utente della sede piu' recente e la sede dal punteggio). Corretto
>   un commento falso del webhook sul caso `DE`+11 cifre. **Mutanti: 30, tutti
>   uccisi**, nella copia del repo in scratchpad (non piu' sul working tree
>   condiviso): al primo giro 3 sopravvissuti — un confine a 0,40 senza test,
>   un mutante invalido riscritto, una difesa irraggiungibile resa testabile.
>   Test: +77 `test_routing_coda`, +17 `test_worker_cliente_dall_xml`, +6 `-m
>   sql` (vincoli veri, due clienti, il trigger che riscatta una riga
>   parcheggiata), +10 `test_coda_fatture_frontend`, +7 Deno (133). Nessuna
>   migration. Il deploy e' lo stesso del passo 0 (push + Edge Function a mano).
>   *Review (verde, nessun blocco; 3 lenti, una col code-reviewer)*: tre rilievi
>   bassi corretti — una sede registrata proprio mentre il worker decide
>   lasciava la riga `unknown_tenant` per sempre (ora `resolve_unknown_tenant`
>   subito dopo il parcheggio); le righe ferme per «piu' account» o P.IVA letta
>   in due modi riscaricavano a ogni tentativo (ora tengono XML e metadati); un
>   BOM prima di `<?xml` fermava il parser (e il DTD ora e' vietato). 7 mutanti,
>   7 uccisi. **Residuo, decide Mattia**: `resolve_unknown_tenant` (SQL, usata
>   anche dal webhook) assegna alla sede piu' recente senza la regola «P.IVA su
>   piu' account»; oggi tocca solo l'ambiente di test (00000000000). E nessuna
>   azione admin sblocca una riga ferma per «piu' account».
>
> - **25/09/2026 — due piccole decisioni del piano consulente.** (1) *Buona
>   notizia sul margine*: si confronta solo se il costo del personale c'e' in
>   ENTRAMBI i mesi (`_mesi_confrontabili`). Misurato: LAND DEI SAPORI ha il
>   personale a luglio e non ad agosto, e agosto sarebbe risultato «molto meglio»
>   solo perche' mancavano gli stipendi. Chiude anche il dubbio «prima del 15».
>   (2) *Il verde «Tutto in ordine»* si spegne sotto un'osservazione negativa
>   (food cost alto, incasso sceso), nel PV (`osservazione_positiva`, affermativa:
>   severity sconosciuta = spento) e nella catena (`_conta_segnali_cache` conta le
>   osservazioni negative, senza toccare la severity). Nella Home e in `/m` il
>   nuovo caso «niente card, niente dati mancanti, niente verde» non mostra piu'
>   il titolo «Da fare oggi (0)» sopra una lista vuota: `lib/briefing-azioni.ts`
>   (il caso esisteva gia' con un arretrato aperto). `_BRIEFING_CODE_VERSION`
>   resta 28: non ancora deployata. Mutanti: 2 + 6, tutti uccisi; il cablaggio
>   nei due `.tsx` non ha presidio (rendering), dichiarato. Suite: `-m "not sql"` 16.507 passed + 49 skip, `-m
>   sql` 559, OpenAPI 202, `tsc` pulito sui sorgenti.
>   (3) *Soglia del food cost* confrontata con la storia della sede: misurata in
>   sola lettura, 25 volte su 40 mesi consolidati oggi, 20 con la proposta
>   (tace sulle 4 di LAND DEI SAPORI, stabile al 37,8%, e su OFFSIDE ad aprile,
>   migliorato dal 40,8% al 35,9%). Non scritta: il numero va a Mattia.

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
python -m pytest -q -m sql                      # 539 su Postgres vero (misurato il 17/09/2026)
python -m coverage run --source=services,utils,config,worker -m pytest tests/ -q
python -m coverage report --sort=cover          # atteso: >= 65%
```

**Se la copertura è scesa sotto il 65%**, qualcuno ha aggiunto codice senza
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
| Test / copertura | 09/2026 | copertura eseguita, non letta: 65% | scende sotto 65% |
| Edge Functions | 27/08/2026 | deployate v40/v13, repo avanti di 10 righe di soli commenti | si modifica `supabase/functions/` (**il deploy è manuale**) |
| DevOps / Config | 07-08/2026 | CI, secrets, runbook, backup provato il 10/08 | cambia la pipeline o il provider |
| Registro delle correzioni | 08/09/2026 | ogni scrittura su `fatture` dichiara attore, `source`, `batch_id` | nuovo scrittore di `categoria` che non passa dal chokepoint |
| Script che scrivono in produzione | 08/09/2026 | 41 censiti, 8 vivi dopo il go-live | nuovo script che scrive a DB |
| **Compliance legale (privacy, cookie, termini, GDPR)** | **09/09/2026** | documenti pubblici confrontati **col codice**, non riletti: destinatari dei dati vs host contattati, retention dichiarate vs purge esistenti, export art. 20 vs tabelle con PII | **cambia un flusso di dati verso terzi, o una dichiarazione della privacy** |

---

## Lenti trasversali — dal 14/09/2026

I tre cicli hanno guardato l'app **per strato**. Queste lenti la guardano **per
proprietà che attraversa gli strati**, e ognuna produce un artefatto che prima
non esisteva.

> **Visione d'insieme L1→L9**: `docs/storico/audit-2026-09/INDICE_LENTI_L1_L9.md`
> — cosa ha guardato ogni lente, cosa ha trovato, dove sta il suo artefatto, e
> cosa si impara leggendole di fila. La tabella qui sotto resta il registro con
> metro completo e condizioni di riapertura. Regola: un workflow ≤ 12 agenti, candidati calcolati in locale,
una lettura per elemento (lezione del 13/09: 30 agenti, 1,65M token, zero
sintesi).

| Lente | Chiusa il | Metro usato | Artefatto | Si riapre se… |
|---|---|---|---|---|
| **L1 — Sweep per classe di difetto** | 14/09/2026 (parziale) | rilevatori AST/grep su 8 classi (707 candidati), triage per classe, refutazione con misura sul DB solo per il cap PostgREST; 6 fix con mutante | `docs/storico/audit-2026-09/CLASSI_DI_DIFETTO.md`: 2 confermati e corretti, chokepoint `fetch_all` ordinato, residui per file:riga | si rieseguono i rilevatori quando si tocca `services/` o `apps/web/src/lib`; le classi non refutate si riaprono leggendo il chiamante |
| **L2 — Isolamento fra clienti, eseguito** | 14/09/2026 | 240 operazioni classificate dall'OpenAPI: le 66 con un id di risorsa chiamate con la sessione di A e gli id di B, nei due versi e sui propri id (controllo positivo); le 73 GET a tenant di sessione (41 con controllo positivo: devono nominare una risorsa propria) eseguite con l'altro cliente seminato; 8 RPC `gruppo_*` + 2 chat — su un Postgres vero attraverso `tests/helpers_supabase_sql.py` (il builder Supabase tradotto in SQL); impronta di ogni tabella tenant prima/dopo; 12 mutanti sul call site, 8 uccisi, 4 spiegati con misura | `tests/test_isolamento_per_risorsa.py` (315 test, `-m sql`): 152 chiamate cross-tenant (piu' 76 di controllo sui propri id), **0 leak, 0 scritture sull'altro**; 2 difetti corretti (PATCH turno accettava un dipendente altrui; assegna-sede rispondeva 500 invece di 404) | da solo: un endpoint nuovo con un id di risorsa senza ricetta, una GET cliente nuova fuori da `GET_SESSIONE`, o una GET che nomina il chiamante restando fuori dal controllo positivo, fanno fallire i test strutturali; a mano quando cambiano `_resolve_ristorante_id`/`_resolve_gruppo` o si rigenera lo snapshot (che oggi ha perso l'identity di `gruppo_tags`) |
| **L3 — La produzione parla** | 14/09/2026 | battito di 60 tabelle sul DB live (sola lettura), 13 workflow CI, corpi dei monitor, errori runtime Vercel e log/advisor Supabase del 13/09 | `docs/storico/audit-2026-09/MAPPA_SILENZI_2026-09-14.md`: 2 silenzi veri, 1 monitor corretto | ogni mese, o dopo un job/cron/webhook nuovo: si ri-esegue il battito e si confronta |
| **L4 — Esito statistico dell'AI** | 14/09/2026 (la domanda e' cambiata) | distribuzione di `fatture.categoria_fonte` sul DB live; `category_change_log` (4.135 righe, old->new su tutte) per la matrice di confusione; ground truth umano da `prodotti_utente`; streak di `prodotti_master` declassate vs controllo; 3+3 mutanti sul call site e sullo script, 5 uccisi, 1 spiegato con misura | `scripts/audit_chi_decide_la_categoria.py` + 10 presidi `-m sql`. **L'AI decide l'1,3%** delle righe con provenienza (4 su 309): il 94,8% e' deciso prima del modello e il 3,9% da un umano — misurare "quanto sbaglia l'AI" avrebbe descritto 4 righe. 1 difetto corretto: la correzione del cliente registrava l'attore su `fatture` e restava anonima su `prodotti_utente` (113 righe di registro senza attore, 3 dopo il deploy dell'attribuzione) | quando la quota AI cambia bruscamente (si rilancia lo script); quando `categoria_fonte` copre una fetta storica ampia, la matrice per fonte diventa misurabile davvero (oggi 309 righe su 39.530, 306 delle quali di settembre) |
| **L5 — Ciclo di vita di colonne e campi** | 15/09/2026 | `scripts/audit_ciclo_vita_colonne.py`: una lettura di **528** file di codice + 10 Edge Function + 148 SQL (ri-misurato il 16/09/2026: il 15/09 diceva 540+149 perche' il rilevatore camminava sul filesystem e contava anche file non versionati — vedi l'appendice del verbale), letture e scritture separate per ognuna delle 667 colonne (AST Python per il builder Supabase, regex per TypeScript e SQL, trigger e default inclusi), incrociate con la fotografia dei dati live (righe / non-NULL / distinti per colonna, `L5_stat_colonne_2026-09-15.csv`); taratura sui casi di esito noto; le 47 colonne NULL al 100% lette una per una al call site; 11 mutanti sul rilevatore + 1 sullo snapshot, 12 uccisi | `docs/storico/audit-2026-09/CICLO_DI_VITA_COLONNE.md` + `tests/test_audit_ciclo_vita_colonne.py` (13 presidi). **Nessuna colonna letta-e-mai-scritta che produca un numero sbagliato in pagina**: 4 lo sono per costruzione (`fattore_kg` ×2, che il frontend manda sempre null; `users.session_token` ×2, ramo legacy senza piu' dati), le altre 43 NULL al 100% hanno uno scrittore vero e nessun cliente le ha mai compilate. 11 colonne morte + 2 tabelle morte proposte per il drop, 4 decisioni per Mattia (il code-reviewer ha bocciato 2 tabelle «morte» del primo giro: `brand_ambigui` viva in `ai_service.py`, `email_rate_log` presupposta da un job GDPR). Saldato il debito di L2: identity di `gruppo_tags` emessa dal generatore dello snapshot, 4 colonne mancanti aggiunte, rattoppo tolto dalla fixture | quando si aggiunge una colonna o si rigenera lo snapshot: `--taratura` e poi l'inventario; il CSV dei dati si rifa' sul DB live (query nel docstring); `category_change_log.actor_*` si rimisura al primo cambio di categoria su `fatture` dopo il deploy dell'8/9. **16/09/2026**: il primo passaggio in CI dei 33 commit ha trovato il test di taratura rosso su GitHub e verde in locale, stesso commit — il rilevatore raccoglieva i file col `rglob` sul **filesystem**, contando 4 script di lavoro non versionati. Perimetro portato a `git ls-files` (`77eef5a`), taratura `deleted_at` 37→33, 2 mutanti uccisi. **Nessun verdetto dell'audit si sposta**: le 6 «lette e mai scritte» e i 5 esiti complessivi sono identici |
| **L6 — Tempo, concorrenza, dipendenze che cadono** | 15/09/2026 | un caso **eseguito** per famiglia, con l'osservabile del cliente: ora congelata alle 00:30 del 1° del mese a Roma (server al giorno prima) attraverso l'endpoint di upload vero e il modulo dei periodi del frontend in quattro fusi sullo stesso istante; due `claim_batch_for_processing` concorrenti, due `assegna_fattura_a_sede` (thread che aspetta il commit) e il lock del lotto invecchiato sotto un secondo processo, su Postgres vero; `openai.RateLimitError` sotto il `@retry` di produzione. Perimetro rimisurato con l'AST, non col grep: 6 letture dell'ora senza fuso nel backend (2 dei «8» erano commenti), 11 chiamate HTTP **tutte** con timeout (gli «8 senza» erano chiamate multi-riga), 3 client OpenAI su 4 col default del SDK (600 s, 2 retry nascosti). Verifica avversaria in workflow (5 agenti, sola lettura) sui rilievi: **2 rilievi miei smentiti, entrambi difetti veri**; 15 mutanti, 15 uccisi | `tests/test_upload_policy_giorno_di_roma.py` (3), `tests/test_periodo_giorno_di_roma_frontend.py` (24), `tests/test_sql_concorrenza_coda.py` (4, `-m sql`), `tests/test_ai_429_attraverso_il_retry_vero.py` (4), `tests/test_openai_client_timeout.py` (3), `tests/test_worker_lock_per_item.py` (6). **4 difetti corretti**: la policy date dell'upload decideva col giorno UTC (`oggi=_oggi_rome()` al call site); i client OpenAI di classificazione senza timeout (`OPENAI_TIMEOUT_SECONDS = 90`, guardia AST su ogni `OpenAI(`); **il lock della coda era del lotto ma il lavoro dell'item** (`_rinnova_lock` a ogni item); **il periodo di default di Margini e Analisi fatture lo decideva il giorno del server** — due Server Component su Vercel UTC: alle 00:30 del 1° ottobre «Mese in corso» mostrava settembre intero, KPI e MOL compresi (`oggiARoma()` in `lib/`). Dichiarati: `mark_queue_item_done`/`schedule_retry` restano senza controllo del chiamante, quota chat sul giorno UTC — **residuo CHIUSO il 23/09/2026**: portata a Europe/Rome nella RPC (`20260923141755_chat_quota_giorno_di_roma.sql`) e nel gemello `_chat_domande_oggi`, dopo aver misurato 1 riga su 95 gia' addebitata al giorno sbagliato; **6 mutanti, 6 uccisi** (4 miei + 2 del reviewer, che sopravvivevano: una guardia su `inspect.getsource` cieca a una frase spostata in commento, e la copia mobile del messaggio senza presidio), `tests/test_chat_quota_giorno_di_roma.py` + `tests/test_home_chat_frontend.py`, SDK 2 retry × tenacity 3, un item oltre il timeout continua a pagare l'AI | quando cambia `JOB_TIMEOUT`/`STALE_LOCK_MIN` (il presidio sui default lo dice) o si aggiunge un secondo queue-worker stabile (allora il controllo del chiamante nelle RPC diventa necessario); quando si tocca `_stop_su_tentativi_o_deadline` o le classi ritentabili; quando un nuovo `OpenAI(`, una nuova chiamata HTTP o un nuovo `calcolaPeriodo(` in un Server Component entra nel codice (le guardie lo dicono); al cambio d'ora del 25/10/2026 per i cron delle 06:30 UTC. ⚠️ Limite dichiarato del presidio frontend: `test_le_pagine_server_passano_il_giorno_di_roma_a_calcolaperiodo` legge il **sorgente** (regex su `calcolaPeriodo(`) — uccide il mutante realistico «argomento tolto», sopravvive a uno che conserva il testo (`(oggiARoma(), new Date())`); gli altri 23 casi dello stesso file eseguono il codice vero. Per chiuderlo servirebbe eseguire `resolvePeriodo` delle due pagine con `Date` congelata. E la guardia AST sui client OpenAI copre `services/ worker/ utils/`, **non** `scripts/` (3 script restano a 600 s, fuori dal runtime) |
| **L7 — Fatture ostili in ingresso** | 15/09/2026 | FatturaPA avversarie **eseguite** attraverso il parser vero (`estrai_dati_da_xml`), non lette: importi `nan`/`inf`/`1e400`, quantita' non finite, negativi, micro-quantita', totali fuori scala; il danno a valle misurato su Postgres vero (`numeric(10,2)` accetta NaN, `SUM()` lo propaga, `NaN > qualunque cifra`) e sul formatter del frontend eseguito con node (`formatEuro` -> "NaN €", mentre `formatPct` ha gia' la guardia `isFinite`); perimetro d'ingresso ri-misurato sul DB live (39.649 righe, 3.558 documenti). Verifica avversaria con un agente refutatore in sola lettura sui miei rilievi: **1 mio fix dichiarato completo era parziale, 1 mia affermazione era falsa**; 28 mutanti, 28 uccisi | `tests/test_importi_non_finiti_fattura_ostile.py` (286, di cui 1 `-m sql`). **3 difetti corretti**: gli importi non finiti passavano **entrambe** le copie di `_to_float_safe` (`invoice_service` + il gemello `documenti_service`) e tutti i rami di `_to_int_safe`, che in piu' sollevava `OverflowError`/`ValueError` fuori dal suo `except` — compreso il ritorno anticipato per i valori gia' numerici, perche' `json.loads` accetta i letterali NUDI `NaN`/`Infinity`; e il percorso scontrini/PDF (Vision) convertiva con tre `float()` nudi fuori da ogni helper (ora il chokepoint `_numeri_riga_scontrino`). Secondo difetto: una **scrittura incompleta taciuta** — il ritorno d'errore diceva `righe: 0` anche con un chunk da 500 gia' a DB, e il tetto di 2.000 righe **tronca e prosegue** con `verifica_integrita_fattura` che confronta il gia'-troncato e certifica "OK" (ora `righe_parziali` e `righe_troncate`, loggati dal worker). **Terzo difetto, trovato dal controllo delle inerenze e non dalla sweep**: lo stesso errore un piano piu' su — `/api/upload/invoice` rispondeva `righe_salvate=0` su qualunque fallimento, e quel numero ha un consumatore vero (`upload-modal.tsx` lo mostra accanto allo stato "error"); ora passa da `_esito_salvataggio_fallito`. **La domanda che chiude la lente non e' "il fix funziona" ma "il fix non rompe il resto"**: le guardie stanno in helper con **16 call site** nel solo `invoice_service`, e un valore legittimo che tornasse `default` sarebbe una regressione visibile solo al cliente, sui suoi euro. 205 test confrontano l'implementazione **pre-fix** (letta da `5c3aea0~1`) con quella attuale su 41 valori di traffico vero (formati it-IT, negativi delle note di credito, esponenziali, stringhe illeggibili, non-stringhe) per ogni default: **0 divergenze**, e un mutante che rifiutava i negativi muore. Il confronto e' a sua volta protetto dalla tautologia: un test verifica con l'AST che la copia pre-fix scritta nel test **corrisponda davvero** al sorgente di git (attenzione al BOM: `invoice_service.py` inizia con U+FEFF e `ast.parse` lo rifiuta), e muore se la si sabota. I **due rilievi non bloccanti del code-reviewer sono stati chiusi**, non rinviati: il job pytest della CI faceva un checkout **shallow**, quindi `git show 5c3aea0~1` non risolveva e il guardiano dell'equivalenza si **skippava in silenzio proprio sulla pipeline** (riprodotto con un clone `--depth 1`): ora `fetch-depth: 0` in `tests.yml`, e in CI quel test **falla** invece di skippare. E le righe di `queue_processor` che loggano troncamento e scrittura parziale — il capolinea della catena, l'unico punto dove un umano vede il problema — non avevano presidio: due mutanti del reviewer ci sopravvivevano. Estratte in `_errore_salvataggio` e `_avvisa_se_troncata`, +4 test, e quei due mutanti ora muoiono. Alla **seconda passata** il reviewer ha lasciato 4 rilievi non bloccanti, **chiusi tutti**: due cifre stantie (`3.557` sopravvissuto nella seconda colonna della stessa riga — la trappola «corretta dove guardavi» — e `CLAUDE.md` che si contraddiceva da solo, 539 a riga 39 e 538 a riga 176); la **riparazione sui segni delle note di credito senza presidio** (`_tot_grezzo` leggeva `"-12,50"` come 0.0 con `float()` nudo, quindi una riga negativa in formato it-IT non contava come negativa e i segni dell'**intero documento** venivano invertiti al contrario: ora `_inverti_nota_credito_in_blocco`, e il mutante che il reviewer segnalava come sopravvissuto muore); e il punto cieco del guardiano AST, che confrontava il **corpo** delle copie pre-fix ma non la **firma**. Dichiarato e NON corretto: le due copie di `_to_float_safe` divergono sulle migliaia it-IT (`documenti_service` non le gestisce, preesistente); `salva_fattura_processata` non rimuove le righe del chunk gia' scritto quando l'item muore `dead`. Verificate **eseguendo** e gia' difese, nessun difetto: XXE e billion-laughs (defusedxml blocca entrambi), P7M ostile (vuoto/spazzatura/zeri -> `ValueError` gestito), magic bytes, tetto righe, divisione totale/quantita', `numero_riga` da `enumerate` e non dall'XML | quando si tocca un `_to_float_safe`/`_to_int_safe` o si aggiunge un percorso d'ingresso che converte numeri fuori da quegli helper (il chokepoint Vision e' nato cosi'); quando `_MAX_RIGHE_PER_FATTURA` cambia o un fornitore supera le ~1.500 righe per documento (il piu' lungo oggi ne ha **657** su 3.558: il tetto non e' mai stato toccato); se un giorno si scrive su `fatture` con un client che non passa da httpx (SQL diretto, psycopg, una RPC): oggi e' `allow_nan=False` a impedire al NaN di arrivare a Postgres, non il nostro codice |
| **L8 — Mappa cache/snapshot e ordine di deploy** | 15/09/2026 | perimetro ri-misurato con l'AST, non col grep: **82 cache dichiarate** in 20 file (le «10 file / 126 occorrenze» del prompt contavano anche variabili locali chiamate `cache`, memoria AI e pool di client), ridotte alle **14 strutture + 11 funzioni `@_make_cache` che servono dati al cliente**; **82 righe di invalidazione riconducibili a 11 invalidatori con nome**; frontend confermato **132 file / 165 occorrenze** (158 `no-store`, 4 `revalidate`, 3 `force-dynamic`, 0 `unstable_cache`); 3 tabelle di stato vive misurate sul DB. Verifica avversaria con un agente refutatore in sola lettura: il rilievo **regge**, ma **2 mie affermazioni corrette** (la funzione si chiama `_conta_segnali_cache`, non `_segnali_sintesi` — che non esiste; e al briefing passano solo conteggio e severity, **non i testi**), impatto ridimensionato ai soli account multi-sede; 6 mutanti, 6 uccisi, tutti verificati come applicati davvero | `docs/storico/audit-2026-09/MATRICE_CACHE_2026-09-15.md` (la matrice scrittura × cache × invalidatore, celle vuote nominate una per una) + `tests/test_segnali_catena_snapshot_versionato.py` (17 test che **eseguono** il codice, nessun assert sul sorgente). **1 difetto corretto**: `gruppo_segnali_state` ha la **stessa forma** di `daily_briefing_state` ma **non registrava la versione della logica** — misurato sul DB live, **40 righe su 40** dal 28/06 al 15/09 su 3 account, zero con `code_version`. Un deploy che cambiava `_calcola_segnali` o le sue soglie non si vedeva **fino a mezzanotte di Roma** (l'unico svuotamento e' per-account al salvataggio della config; `force=true` ha **zero chiamanti di produzione**). Platea misurata a DB: **3 account** con ≥2 sedi attive non tecniche — piccola, ma interamente esposta. Corretti **entrambi i lettori**, non uno: l'endpoint ricalcola, e `_conta_segnali_cache` (che alimenta il briefing di catena) ritorna **`None` e non `0`**, o il gate `tutto_ok` si accenderebbe su un conteggio che non vale piu'. Le 40 righe si rigenerano da sole al primo deploy: nessuna migration. **Ordine di deploy: nessuna rotta orfana** (`--check-drift`: 198 endpoint, 0 drift); i 7 «path citati e non esposti» del primo rilevatore erano **tutti falsi positivi** — 5 per la query string, 2 perche' il confronto saltava **il livello proxy** delle route API di Next. Edge Function: scrivono solo su tabelle di coda, che nessuna cache serve. Dichiarati e non corretti: **3 `@st.cache_data` dichiarano `ttl=120` e non cachano nulla** (shim passthrough — un TTL che mente, l'opposto del difetto cercato), l'invalidazione di `margine_service` dipende da `sys.modules`, il ramo `pages.foodcost` e' codice morto, `revalidateSec` ha zero chiamanti | quando nasce una **tabella di snapshot** nuova (deve nascere con la versione della logica dentro, o eredita questo difetto); quando si tocca `_calcola_segnali` o le sue soglie → **bumpare `_SEGNALI_CODE_VERSION`**; quando si aggiunge una cache che serve dati al cliente (va nella matrice col suo invalidatore); se una delle tre `@st.cache_data` passthrough diventa vera |
| **L9 — La giornata del cliente e la parita' `/m`** | 17/09/2026 | perimetro misurato prima di guardare, e **la prima misura ha corretto la premessa**: «parita' `/m`» suggerisce uno specchio, ma sono **22 pagine desktop e 7 mobile** — il mobile non e' una riduzione del desktop, e' un prodotto diverso (5 tab: Home, Agenda, Movimenti, Assistente, Profilo). Cercare «le 15 pagine mancanti» avrebbe prodotto un elenco di non-difetti; la domanda utile e' **dove il mobile dice al cliente qualcosa di diverso e piu' sbagliato davanti agli stessi dati**. CTA: tutti gli `href`/`router.push`/`redirect` letterali confrontati con le **36 rotte pagina reali** (segmenti dinamici inclusi, route group normalizzati) -> **0 destinazioni inesistenti**; le destinazioni **costruite** lette a mano (tutte `${pathname}?${params}` o `mailto:`); il deep-link `/assistenza?servizio=<key>` verificato **nella cartella d'arrivo** e non dedotto dal nome (`marketplace.tsx` lo legge davvero, e le chiavi sono legate dal tipo `Servizio["key"]`). **tre giri di mutanti**: 6 al primo (tutti della stessa famiglia — cancellare un token che il test cerca), 7 al secondo dopo due mutanti *evasivi* del code-reviewer, e un terzo giro dopo altri 4 scritti **da fuori conoscendo le guardie**, di cui **2 sopravvissuti** (shadowing del flag; i due messaggi scambiati fra il ramo del guasto e quello del vuoto) piu' il **ritorno del mutante storico**, riaperto perche' avevo *sostituito* il vecchio presidio invece di affiancarlo: `statoLista` copre la decisione, non l'input che nasce nel `catch` del `.tsx`. un quarto giro dopo altri 3 scritti da fuori, di cui 2 sopravvissuti (l'invariante `#vuoto == #guasto` si pareggia **duplicando** un ramo mentre la vista di default resta scoperta; la finestra `righe[i:i+3]` del presidio sui messaggi era porosa nelle **due** direzioni, falso positivo su una riformattazione compreso). e un quinto dopo altri 2 (la regex raccoglieva i nomi dall'**assegnazione**: un ternario interposto ne faceva uscire uno, e la vista di default tornava scoperta; il parser del corpo si troncava su un ternario annidato). e un sesto dopo l'ultimo (i rami di due viste che si **scambiano** lo stato: gli insiemi restano identici, e una vista decide sui dati di un'altra). **23 mutanti provati, 23 uccisi**, 10 dei quali sopravvissuti al primo tentativo del loro presidio — **8 scritti dal reviewer**, e dal terzo giro in poi tutti i sopravvissuti sono suoi, ognuno verificato come applicato davvero (hash) e ogni ripristino confrontato per hash | `docs/storico/audit-2026-09/GIORNATA_DEL_CLIENTE_E_PARITA_M.md` + **32 casi** in `tests/test_esito_caricamento_frontend.py` (**41 -> 73** nel file: la baseline dichiarata «45» era sbagliata, e il «+24» era una sottrazione su una base mai misurata) e `statoLista()` in `lib/esito-caricamento.ts`. **4 difetti corretti su 6 stati vuoti** (stesso difetto, sei volte): il fix R10 del 3/9 era arrivato al desktop e **non a `/m`** — l'helper `lib/esito-caricamento.ts` era usato da 11 file, dieci desktop e **uno solo** mobile. Su 6 file mobile con uno stato vuoto, **4 non distinguevano «non c'e' niente» da «non sono riuscito a chiedere»**: incassi, spese, diario e turni dicevano «Nessun incasso inserito in questo mese.» col worker giu'. Non e' teorico: lo stato iniziale e' `null`/`[]`, quindi la frase falsa compare **al primo caricamento fallito, cioe' all'apertura della pagina**; il fallimento e' documentato dal repo stesso (Railway spegne il worker, il risveglio sfora gli 8s); e il toast d'errore **sparisce dopo pochi secondi** lasciando in pagina l'affermazione falsa. Il desktop, nella stessa situazione, dice «Non e' stato possibile caricare... Riprova». **La review ha bocciato la prima stesura, con tre rilievi veri.** (1) Il censimento contava i **file**, non gli stati vuoti: `mobile-turni.tsx` ha **tre viste** con tre liste, e il flag era collegato alla prima soltanto — restavano scoperte la mensile e **la giornaliera, che e' il default** (`modalita` parte da `"giornaliero"`): il primo giro aveva corretto il ramo che si raggiunge toccando il selettore e lasciato quello che si apre da solo. (2) I presidi leggevano la **forma** delle righe, e due mutanti *evasivi* — `(false && ...)` sul ramo, `setFallito(false)` nel `finally` — **ripristinavano il difetto intero con la suite verde**. La correzione non e' stata un test in piu' ma **spostare la decisione**: `statoLista()` in `lib/esito-caricamento.ts`, che i test **eseguono** (8 casi + l'invariante «con un guasto non si dice mai vuoto»); nei `.tsx` resta una riga che la chiama. Le guardie di forma residue coprono cio' che l'harness non esegue, e **una e' nata da un mutante sopravvissuto alla guardia stessa** (`caricamentoFallito: false` letterale, che spegne il guasto di una vista sola). (3) «Identico al desktop» sul blocco KPI era **piu' forte del vero**: il desktop ha tre stati via `statoBlocchi` (worker giu' → `BlockRetry` che **riprova**; vuoto → messaggio; dati), il mobile uno. Resta scartato — un blocco **assente** non afferma nulla di falso, mentre «Nessun incasso inserito» si' — ma come **scelta diversa accettata**, non come equivalenza. **2 sospetti scartati dopo verifica**: il blocco KPI mobile (vedi sopra: scelta diversa dal desktop, accettata — non un'equivalenza) e il briefing mobile, **gia' corretto** («Impossibile caricare il briefing») | quando nasce un **componente mobile che carica dati e mostra una lista**: va aggiunto a `_CLIENT_MOBILE` nel test, o il difetto rientra dalla finestra (oggi i client mobile che fanno fetch sono 10; i 4 con una lista sono presidiati, gli altri 6 non hanno stati vuoti da distinguere). Quando si aggiunge una pagina a `/m`, la domanda non e' «esiste anche sul desktop?» ma «dice qualcosa di diverso davanti agli stessi dati?». ⚠️ **Limite dichiarato**: l'harness esegue `lib/`, **non i `.tsx`** — i presidi sui quattro client leggono la **forma** del codice. Uccidono i mutanti realistici elencati, ma non sostituiscono un test di rendering: per quello servirebbe un runner frontend, che e' una **decisione esplicita di Mattia** (punto 9 del ciclo 2026-08). E la **giornata end-to-end su un account nuovo non e' stata eseguita**: richiederebbe un account vero in produzione (il locale punta al DB cloud reale). I percorsi sono stati letti, non percorsi |

### Le lenti ancora da fare, in ordine

**Nessuna: le nove lenti sono chiuse** (L9 il 17/09/2026). L1 resta *parziale*
per scelta dichiarata — le classi di difetto non refutate si chiudono leggendo
il chiamante, una per una, e sono elencate per `file:riga` in
`CLASSI_DI_DIFETTO.md`.

Da qui vale la regola ordinaria: **quando tocchi un file, lo copri**. Una lente
si riapre solo alle condizioni scritte nella sua riga qui sopra.

## Cosa NON è coperto — e resta una scelta, non una dimenticanza

Va scritto qui perché **nessun audit futuro lo riscopra come se fosse una novità**.

| Area | Misura | Perché è fuori |
|---|---|---|
| Frontend `.tsx` | 42.293 righe: rendering, hook, stato, effetti | Nessun runner npm **per scelta d'impianto**: `deploy-vercel.yml` scatta su `apps/web/**`, un runner deployerebbe a ogni test. La logica pura si estrae in `lib/` (87% presidiato) |
| 7 funzioni SQL di staff | `admin_ai_mensile`, `admin_consumi_mensili`, `admin_conteggio_fatture`, `admin_fatture_per_mese`, `get_ai_costs_summary`, `get_ai_costs_timeseries`, `get_ai_recent_operations` | Le vede solo l'owner, non i clienti; non spostano un euro sui loro numeri. Rendimento basso |
| Copertura backend oltre il 65% | 10 router su 12 a copertura parziale | Le aree grasse sono state prese e ognuna ha dato un bug vero. Oltre, il rendimento cala: si copre **quando si tocca il file** |
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
