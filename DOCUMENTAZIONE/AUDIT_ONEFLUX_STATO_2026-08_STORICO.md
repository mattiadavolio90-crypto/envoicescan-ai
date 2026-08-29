# AUDIT ONEFLUX — ciclo 2026-08 — STORICO delle fasi chiuse

Un verbale per fase chiusa. Lo stato corrente e la roadmap stanno in
`AUDIT_ONEFLUX_STATO_2026-08.md`; qui resta cosa è stato fatto, cosa è stato
trovato e cosa è stato **scartato** — quest'ultima parte è la più utile a
distanza di mesi, perché è quella che nessuno ricostruisce dal codice.

---

## F1 — Frontend `catena/` — chiusa 28/08/2026

**Perimetro**: 10 file, 2.955 righe all'apertura / 3.012 alla chiusura (i fix a
`spreco-categorie` di altra sessione hanno toccato il perimetro mentre la fase
era in corso). Zero test frontend nel repo: l'unica rete è `tsc --noEmit`.

**Metodo**: lettura riga per riga in ordine di rischio, ogni ipotesi confermata
con una query sul DB live o chiusa in negativo con la misura che la esclude,
severità riverificata prima di scriverla.

### Esito delle ipotesi

| Ipotesi | Esito |
|---|---|
| H1 — ri-derivazione locale delle quote | **smontata**: il client legge `quota_importo`, nessun `importo × perc` nei 10 file |
| H2 — override mensile | **confermata, in forma diversa**: non il client, il criterio di completezza lato server → HIGH |
| H3 — campi nuovi scartati | **smontata**: `spesa_esclusa_mix`/`PrezzoValido` vivono nel modulo tag *di sede*, non in catena |
| H4 — isolamento sede↔gruppo | nessuna divergenza |
| H5 — cap PostgREST 1000 | **non attivo**, ma il limite vero è un altro (RPC satura a 500, client tronca a 60) |

### Il difetto HIGH

`gruppo_salute_componenti` aggrega solo `margini_mensili`, dove una sede in
modalità mensile ha `fatturato_netto = 0`: la completezza dichiarava "manca il
fatturato" su sedi che fatturano. OFFSIDE: `netto_rpc = 0` su 7 mesi su 7 con
**€437.898,49** di ricavi reali. Sul mese di default entrambi i PV a zero contro
**~€651.336** calcolati dal percorso corretto.

Conseguenza per il cliente: **MOL del gruppo nascosto**, sedi collassate in "dati
incompleti", e un messaggio che nominava la causa sbagliata.

**È la quarta ricomparsa della stessa causa-radice.**
`tests/test_gruppo_aggrega_sedi.py:75-91` documenta lo stesso difetto già
corretto in `_aggrega_sedi_mensili`: la correzione non era mai stata propagata.
Il fix è stato messo in `_salute_componenti_raw` — dove il periodo è già
risolto — così guariscono insieme tutti e 4 i chiamanti, invece di rattoppare il
singolo consumatore e lasciare il quinto percorso scoperto per la prossima volta.

### Findings e destino

| # | Sev. | Oggetto | Esito |
|---|---|---|---|
| H2-BIS | 🔴 HIGH | completezza ignora `ricavi_modalita_mensile` | fixato |
| F-CHAT | 🟠 MED | tool chat catena: token passato come `mese`, rotto da sempre | fixato |
| F-EXPORT | 🟠 MED | export XLSX perde l'avvertenza "parziale" | fixato |
| F-60 | 🟡 LOW/MED | troncamento silenzioso a 60 candidati | fixato |
| F-REDIRECT | 🟡 LOW | worker giù → redirect invece di BlockRetry | fixato |
| F-DACLASS | 🟡 LOW | `"Da Classificare"` hardcoded 7× su 4 file | fixato |
| F-DRIFT | ⚪→🟢 | 19 costi su 156: somma quote ≠ totale (max 1 cent, tot 19 cent) | **chiuso 28/8** (guardia SQL + sanatoria) |

`F-DRIFT` **chiuso il 28/8** con la migration `20260828210000` — e la causa
ipotizzata in planning era **sbagliata su tutti e tre i punti**. Vedi la sezione
dedicata in fondo a questo verbale.

### Verificati e scartati

Vale la pena registrarli, perché a rileggere il codice sembrano difetti:

- **Confronto float `===`** (`gruppo-tag-section.tsx:650-651`): sicuro. Confronta
  valori **dello stesso array**, non ricalcolati — non è il caso classico
  `0.1 + 0.2`.
- **`cellTone` con `coperti = 0`**: la guardia `v !== ex.worst` neutralizza il
  caso degenere `best == worst`.
- **Sede tecnica** "Costi comuni di gruppo": correttamente esclusa da
  `_resolve_gruppo` via `.eq("sede_tecnica", False)`.

### Correzioni al documento del ciclo

Tre imprecisioni corrette misurandole, non deducendole:

1. **€501.167 → €67.591,75** (query su `riparto_costi_catena`; anche 155→156
   costi e 1→2 utenti). La cifra era gonfiata ~7,4× e compariva in 3 punti,
   **incluso il criterio di priorità delle fasi**.
2. **Perimetro 9 → 10 file**: mancava `catena/fatture/page.tsx`, invisibile al
   grep perché usa `workerGet` e non `fetch`. Ha prodotto un finding.
3. **`/api/account/sedi`** è un `BlockRetry` di ping, non una fonte dati.

### Esito del `code-reviewer` (gate di chiusura)

**Verdetto: chiusa correttamente, nessun bug bloccante.** Il reviewer ha
verificato eseguendo, non leggendo: ha girato la libreria XLSX vera (`origin: -1`
produce davvero una riga in coda, e con `n_incompleti === 0` l'export è
bit-identico a prima) e ha riletto la definizione della RPC sul DB live,
confermando che `netto` è `sum(iva10 + iva22 + altri)` senza scorporo — quindi
sommare il lordo nell'override è la scelta giusta.

Tre rilievi non bloccanti, **tutti sistemati prima di chiudere**:

1. **N+1**: `_overrides_mese_sede` chiamata dentro il loop e non memoizzata →
   cache locale, una lettura per sede.
2. **Il secondo consumatore non era coperto**: `_salute_indici_batch` condivide
   la stessa RPC e dà 25 punti su 100 alla voce `netto > 0`. Il fix alza quindi
   anche l'*indice di salute*, non solo la completezza — corretto, ma non
   documentato e senza test. Ora c'è un test che misura i 25 punti.
3. **XLSX**: `"(parziale)"` finiva anche su celle senza numero
   (`"— (parziale)"`) → si appende solo a un valore numerico.

Due rilievi **restano aperti**, entrambi annotati per F7:

- **`nascosti` sottostima quando la RPC satura.** Il conteggio è esatto sul pool
  locale, ma nel ramo ricerca il pool arriva da una RPC che tronca a 500: il
  numero mostrato non è un limite superiore garantito. Il messaggio resta
  comunque un'uscita valida.
- **`toggleTutti` legge `tuttiSelezionati` dalla closure** dentro
  `setSelected(prev => …)`. Pre-esistente e innocuo in pratica, ma è il pattern
  che porta a stato stantio.

### Esito del `code-reviewer` (gate di chiusura)

**Due giri di review, due verdetti 🔴 NON CHIUSA** prima della chiusura vera.
**Primo giro:** Il reviewer ha trovato che il fix dell'HIGH
**non chiudeva il difetto che dichiarava chiuso**, e due dei test nuovi non
coprivano ciò che promettevano. Tutti e tre corretti prima di chiudere davvero.

1. **L'open redirect ha richiesto TRE stesure.** Le prime due sembravano
   entrambe complete, ed entrambe erano bypassabili:

   | Versione | Idea | Come cadeva |
   |---|---|---|
   | 1ª | filtro su `startsWith("//")` | la WHATWG rimuove TAB/LF/CR **prima** di parsare: `?next=%2F%09%2Fevil.com` arriva come `"/<TAB>/evil.com"`, non inizia con `//`, passa — e atterra su `https://evil.com` |
   | 2ª | `url.origin` + ritorno `pathname+search+hash` | il check passa, ma la ri-serializzazione reintroduce un **secondo parsing**: `/..//evil.com` ha origine interna e pathname `//evil.com`, protocol-relative. **In chiaro, senza encoding** |
   | 3ª | `url.origin` + ritorno `url.href` | giudizio e uso sulla **stessa** stringa: nessun parsing in mezzo |

   La 2ª è la più istruttiva: avevo corretto l'ipotesi giusta (non ispezionare
   il testo grezzo) e il difetto si era spostato **un livello più a valle** —
   prima il giudizio guardava una stringa diversa da quella eseguita, poi
   *restituiva* una stringa diversa da quella giudicata. `/..//app.oneflux.it.evil.com`
   mostrava perfino un dominio che sembra il nostro.

   Entrambe le volte avevo "verificato su decine di forme": erano tante ma
   **della stessa classe**. Ora c'è `tests/test_login_next_open_redirect.py` —
   44 test che eseguono la funzione estratta dal `.tsx` di produzione su ogni
   classe di bypass (protocol-relative, schemi non-http, backslash, caratteri
   rimossi in parsing, dot-segment, userinfo, suffisso di dominio, fragment,
   downgrade di schema) e sui 9 path legittimi. Verificati per mutazione: **le
   due versioni precedenti del fix vengono uccise** (4 e 12 test rossi), e così
   `url.host` al posto di `url.origin`, che lascerebbe passare un downgrade a
   `http://`.
2. **Il mock regalava una colonna che la query non chiedeva.** `FakeSB.select()`
   ignorava gli argomenti e restituiva sempre la riga intera: togliere
   `nome_ristorante` dalla select — **metà del fix** — non faceva fallire nulla,
   mentre in produzione la regola GDPR sul nome del ristorante sarebbe morta in
   silenzio. Ora `select()` proietta davvero.
3. **Il test sulla policy client leggeva il `.ts` come testo.** Difendeva due
   costanti, non il comportamento: mutilare la regex dei simboli o disattivare
   il controllo di lunghezza lo lasciava verde. Ora **esegue** la funzione vera
   in node e confronta il verdetto con quello di Python su 400 password.

**Secondo giro:** B2 e B3 confermati chiusi, ma l'open redirect era *ancora*
aperto — vedi il punto 1 sopra. Il reviewer ha anche fatto notare che il
verbale, a quel punto, dichiarava chiuso un difetto che non lo era: un `.md`
che mente, e `test_documentazione_onesta.py` non può accorgersene perché i
simboli citati esistono tutti. Corretto insieme al codice.

Non bloccante ma corretto lo stesso: **`password.length` conta unità UTF-16**,
`len()` di Python conta codepoint — `"Ab1!" + 3 emoji` misura 10 in JS e 7 in
Python, quindi il client diceva "ok" e il server rifiutava. Ora `[...password]`,
con un test che lo difende.

Confermati corretti dal reviewer, verificati eseguendo: nessun lock-out per gli
utenti esistenti (la policy si applica solo alla password *nuova*, e non è
chiamata in nessun percorso di login); il messaggio d'errore anzi *guadagna*
informazione (`" ".join(errori)` invece del solo primo); `fetchNotifiche` e
`fetchConfig` non lanciano mai e il `redirect()` non è dentro un try/catch; il
cookie di logout viene cancellato incondizionatamente anche a worker morto.

**Terzo giro: 🟢 B1 chiuso.** Il reviewer ha cercato il bypass su **1636
candidati** (schemi × prefissi × separatori, 14 caratteri di controllo iniettati
in ogni posizione, dot-segment fino a profondità 6, doppia codifica `%252f`,
userinfo, IPv6, homoglyph IDN) valutando **dove atterra il browser** e non cosa
ritorna la funzione: **zero fughe**. La ragione strutturale: `url.href` è
assoluto e serializzato dal parser stesso, quindi `new URL()` è idempotente su
di esso — mentre `pathname+search+hash` era una forma *relativa*, e una forma
relativa viene ri-risolta. Il livello non è stato spostato: è stato eliminato.

Verificata anche la fragilità dell'estrazione regex dal `.tsx`: funzione
rinominata, firma cambiata, riformattazione prettier e graffa a colonna 0
producono tutte un **AssertionError esplicito**, mai uno skip silenzioso.

Un rilievo non bloccante accolto: i 55 test che girano `node` erano protetti da
uno `skipif`, e `tests.yml` non dichiarava node — bastava un cambio d'immagine
del runner perché diventassero **skip verdi**. Ora c'è `actions/setup-node`, e
lo skip diventa un `fail` quando `CI=true`: in locale saltare è giusto, in CI un
ambiente senza node è un guasto, non un test da saltare.

**Residuo aperto, segnalato dal reviewer e non risolvibile in sessione**: la
route `account_cambia_password` non ha alcun test che copra
`verify_and_migrate_password` — disattivandola i 10 test restano verdi, cioè si
cambierebbe password senza conoscere la vecchia. È **preesistente a F2** (i test
la mockano a `True` per isolare la policy) e nessun altro file la copre.
Annotato per F7.

### Lezioni di metodo

- **Contare `.map(` e `reduce(` non misura il rischio.** I "78 siti di calcolo
  locale" che motivavano la priorità di F1 erano quasi tutti geometria SVG e
  scaling di heatmap; le ri-derivazioni di business vere erano **3**, tutte
  legittime. La fase era comunque quella giusta, ma per l'altra ragione (backend
  auditato / frontend mai letto).
- **La prova per mutazione ha cambiato due test su quattordici.** Un mutante che
  *scollegava* il fix sopravviveva, perché i test chiamavano l'helper
  direttamente e mai il collegamento; un altro che toglieva la guardia
  `lordo > 0` sopravviveva perché il caso partiva già da `netto = 0`. Senza
  mutazione sarebbero passati per test buoni.
- **F1 è stata eseguita su una roadmap che non era su `main`**: il commit di
  apertura del ciclo era rimasto su un branch abbandonato. I findings sono
  sopravvissuti perché derivano da codice e DB, non dal documento — ma il
  documento va messo su `main` **prima** di eseguire la fase, non dopo.

---

## F2 — Frontend impostazioni / account / auth — chiusa 28/08/2026

**Perimetro misurato**: 1.319 righe di pagine (804 `impostazioni/` + 515
`(auth)/`) **più 623** di route API e lib auth che il perimetro dichiarato non
elencava — `apps/web/src/lib/auth.ts` (167), `worker-config.ts` (92), le 15
route `api/auth/*` e `api/account/*` (361), `proxy.ts` (105). **Totale 1.942**.
Le pagine da sole non bastavano: due dei quattro difetti stanno in quei 623.

**Metodo**: lettura in ordine di rischio partendo da `lib/auth.ts` come chiave,
ogni ipotesi chiusa con una misura eseguita — validatore Python fatto girare
davvero, risoluzione URL provata in Node, esposizione contata sul DB live.

### Esito delle ipotesi del piano

| Ipotesi | Esito |
|---|---|
| H-PWD — validazioni client divergenti dal worker | **confermata, in forma doppia**: client 8 / server 10+categorie sul reset (attrito), e server 8 sul cambio password (buco) |
| H-SESS — stato "loggato" dopo la scadenza | **smontata sul desktop, confermata su `/m`**: `(app)/layout.tsx` distingue gli esiti, `(mobile)` no |
| H-ADMIN — confronti email case-sensitive nel client | **smontata**: `is_admin` arriva sempre dal worker, nessun confronto email nel client (l'unico `.toLowerCase()` è un filtro di ricerca) |

### Il difetto più grave, che nessuna ipotesi prevedeva

**Open redirect sul login.** `?next=` veniva letto da `useSearchParams` e messo
tal quale in `window.location.href`. Il produttore legittimo (`apps/web/src/proxy.ts:93`)
scrive sempre un pathname, ma **nessuno validava il consumatore**: un link
fabbricato portava fuori dominio **dopo un login riuscito**, cioè nel momento in
cui l'utente ha appena dimostrato di fidarsi del sito.

Provato risolvendo 14 forme contro l'URL di produzione: `//evil.com`,
`https://evil.com`, `javascript:alert(1)`, `/\evil.com`, `///evil.com`,
`//\evil.com` uscivano tutte dal dominio. Catena verificata intera: `/login` è
in `PUBLIC_PATHS`, il proxy lo lascia passare con la query intatta, il matcher
non lo esclude.

È emerso **leggendo il consumatore invece di fidarsi del produttore** — la
stessa asimmetria che in F1 aveva prodotto il difetto HIGH.

### La divergenza sulle password

Tre percorsi scrivono una password; **due applicavano la policy GDPR e uno no**:

| Percorso | Prima | Ora |
|---|---|---|
| Reset da token (`auth_service.py:613`) | policy completa | invariato |
| Imposta-password admin (`admin.py:2582`) | policy completa | invariato |
| **Cambio da area Account** (`account.py:198`) | **`len < 8`** | policy completa |

Misurato eseguendo il validatore vero: di 4 password che il client dichiarava
valide, **3 venivano rifiutate** dal server sul reset. E `reset-confirm`
restituisce solo `errori[0]`, quindi l'utente li scopriva **uno alla volta**.

`apps/web/src/lib/password-policy.ts` è ora la fonte unica lato client.
Replica solo lunghezza e categorie — blacklist, sequenze e carattere ripetuto
restano al server per scelta esplicita: liste lunghe che divergerebbero in
silenzio. **Verificata contro l'implementazione Python su 400 password
generate casualmente: zero divergenze.**

### Findings e destino

| # | Sev. | Oggetto | Esito |
|---|---|---|---|
| F2-REDIRECT | 🔴 HIGH | open redirect su `/login?next=` (anche `javascript:`) | fixato alla **3ª** stesura, 44 test di regressione |
| F2-PWD | 🟠 MED | cambio password fuori dalla policy GDPR + client che promette requisiti falsi | fixato |
| F2-MOBILE | 🟠 MED | cold-start del worker slogga dalla PWA (7 pagine, 82 sessioni/30gg) | fixato |
| F2-LOGOUT | 🟡 LOW | `logoutSession` unica chiamata worker senza timeout: worker appeso = utente non esce | fixato |
| F2-NOTEST | ⚪ | zero infrastruttura di test frontend (confermato anche in F1) | **aperto — a Mattia** |
| F2-VERIFY | ⚪ | `cambia-password` senza test su `verify_and_migrate_password` (preesistente) | **aperto — a F7** |

`F2-NOTEST` non è un fix d'audit: introdurre un runner è una decisione di
progetto. Nel frattempo gli invarianti client sono difesi da test **Python**
che girano in CI (`test_password_policy_client_allineata.py`), sul precedente
di `test_upload_ai_background.py:263`.

### Verificati e scartati

- **`runtime = "nodejs"` mancante** su `reset-request`/`reset-confirm`: sembra
  una svista, non lo è. **118 route su 169** non lo dichiarano, il default Next
  è già `nodejs` e non c'è override in `next.config`. Convenzione irregolare,
  non difetto. *Severità caduta alla verifica — la nona del progetto.*
- **Conferma "ELIMINA" hardcoded nel client** (`account-client.tsx`): il client
  manda la costante invece di ciò che l'utente digita, ma il **server** valida
  `strip().upper() != "ELIMINA"` e ha il guard sugli admin. Ridondanza, non buco.
- **`getCurrentUser()` in `impostazioni/page.tsx`**: collassa gli esiti, ma
  `(app)/layout.tsx` gira prima e li distingue, e `cache()` di React fa
  riusare l'esito nella stessa request. Corretto. **Su `/m` invece era un
  difetto vero**, perché lì quel layout non c'è: la differenza sta nella
  struttura dei route-group, non nel codice della pagina.
- **`forgot-password`**: normalizza lowercase e non enumera gli utenti.
- **Asimmetria `svuota-dati` case-sensitive vs `elimina` case-insensitive**:
  entrambe validate lato server, nessuna conseguenza.

### Lezioni di metodo

- **Il perimetro dichiarato conteneva le pagine, non il percorso.** «~1.900
  righe» era numericamente quasi giusto (1.942) ma per composizione sbagliata:
  mancavano le route API e `proxy.ts`, dove stanno 2 dei 4 difetti — incluso
  l'HIGH, che si capisce solo leggendo **produttore e consumatore insieme**.
  In F1 il perimetro era incompleto di un file; qui di un *layer*.
- **La mutazione ha di nuovo cambiato un test.** Il mutante "passa email e nome
  ristorante vuoti" sopravviveva: due regole GDPR sarebbero morte in silenzio e
  la suite non se ne sarebbe accorta. Il test che prometteva di coprirlo
  misurava l'*esito* invece dell'*argomento*. Terzo ciclo di fila in cui la
  mutazione trova un test che sembrava buono.
- **I route-group fratelli non ereditano le difese.** `(app)` e `(mobile)` sono
  gemelli sotto un root layout che non fa auth: ogni protezione aggiunta a uno
  va **aggiunta a mano** all'altro. È la versione strutturale della trappola già
  a verbale in CLAUDE.md («`/m` è un frontend separato, non responsive»), e vale
  per l'auth, non solo per la grafica.
- **Aver testato molto non vuol dire aver testato la cosa giusta.** Le forme
  provate sull'open redirect erano decine, ma tutte della stessa classe: prima
  varianti del *prefisso*, poi degli *schemi*. Nessuna conteneva un dot-segment,
  cioè l'unica classe che sopravviveva. Il numero di casi non misura la
  copertura; **misura la copertura l'elenco delle classi**, ed è per questo che
  il file di test le nomina una per una invece di elencare stringhe.
- **Quando validi una stringa che qualcun altro re-interpreterà, giudica e usa
  la stessa stringa.** Le prime due stesure sbagliavano su questo, nei due modi
  possibili: giudicare il testo grezzo mentre il browser normalizza (1ª), e
  ri-serializzare dopo aver giudicato (2ª). Ogni parsing in mezzo è un punto in
  cui le due stringhe divergono. Vale oltre gli URL: path, SQL, shell.
- **Un fix di sicurezza senza test di regressione si riscrive all'infinito.**
  `nextSicuro` è stata riscritta due volte prima che qualcuno chiedesse dove
  fossero i test — e non ce n'erano. I 44 test ora falliscono su entrambe le
  versioni bypassabili: se una terza idea "elegante" tornasse a una di quelle
  forme, la suite lo direbbe subito.
- **Un mock generoso è un test che mente.** `FakeSB` restituiva colonne mai
  richieste: metà del fix era scoperta e la suite diceva verde. I mock vanno
  resi *severi quanto la cosa vera*, non comodi.

---

## F-DRIFT — chiuso 28/08/2026 (residuo di F1)

**Due ipotesi sbagliate prima di quella giusta.** Vale la pena registrarle
entrambe, perché la seconda l'ho scritta io convinto di aver misurato.

| # | Ipotesi | Come è caduta |
|---|---|---|
| 1ª (dal planning) | i `round()` per-categoria di `riparto.py:1231-1253` | quello è codice di **lettura**: aggrega per la risposta API, non scrive nulla |
| 2ª (mia) | «dato storico, da un percorso che non esiste più» | **falsa**, e l'ha smontata il `code-reviewer` con due query |
| 3ª (vera) | `esplodi_quote_per_categoria(forza=True)` ricompone le quote-sede e fa riemergere i mezzi centesimi | riprodotta **eseguendo** la funzione vera |

### Perché la mia ipotesi era sbagliata

Avevo scritto due affermazioni come misurate. Erano entrambe false:

- **«I 19 sono *esattamente* i costi con centesimi dispari».** Avevo verificato
  che i 19 fossero tutti dispari, **mai il converso**: i costi con la stessa
  identica firma (2 sedi al 50%, centesimi dispari) sono **51**, e 32 pareggiano.
  La correlazione su cui poggiava tutta l'inferenza causale non esisteva.
- **«Dato storico».** Gli `updated_at` dei 19 stanno tutti fra le **10:38:37 e le
  10:40:27 del 27/8**: un singolo batch del giorno prima, da codice vivo nel repo
  (`scripts/pulizia_riparti_note_credito.py` → `esplodi_quote_per_categoria`).

Avevo guardato `min` e `max` delle date su **tutti** i costi invece che sui 19, e
la sovrapposizione dei due intervalli mi era sembrata una prova di dispersione.

### La causa vera

`esplodi_quote_per_categoria(forza=True)` **ricompone** la quota di ogni sede
sommandone le porzioni per-categoria, per poi rispezzarla. Quella somma fa
**riemergere i mezzi centesimi** che l'esplosione precedente aveva diviso:

```
header 2,95 → due sedi al 50% → 1,475 ciascuna → arrotondate: 1,48 + 1,48 = 2,96
```

Il ramo che pareggia le quote-sede **esisteva già**, ma girava solo sotto
`riallinea_al_netto`, cioè quando header e righe divergono. Su questi costi
coincidevano — quindi non pareggiava nessuno. I 32 sani hanno quote
**asimmetriche** in ingresso (`0,81 / 0,82`), i 19 le hanno **simmetriche**
(`1,48 / 1,48`): è la firma del difetto.

### Il fix: codice, non guardia

Ramo `else` in `services/riparto_service.py`, stessa convenzione "l'ultima sede
assorbe" di tutti gli altri percorsi. Verificato sugli **11 importi reali**:
prima nessuno pareggiava, ora tutti.

28 test (`tests/test_riparto_drift_ricomposizione.py`) che **eseguono la funzione
vera** con un fake client, non la mockano. 4 mutanti su 4 uccisi — il quarto
(pareggia la prima sede invece dell'ultima) sopravviveva perché *equivalente sul
pareggio*: ora c'è un test sulla convenzione, che conta perché due percorsi che
scelgono sedi diverse renderebbero rumore il confronto fra due esecuzioni.

### La migration: sanare e rendere visibile, senza bloccare

Due cose che il codice non può fare: **sanare i 19 già scritti**, e aggiungere la
classe **`quote_non_pareggiano`** a `v_riparto_incoerenze`. Verificata sul DB
live: intercetta esattamente i 19, tutti con scarto di 1 centesimo.

**La prima stesura aveva un `RAISE EXCEPTION` nelle due RPC, ed era sbagliata.**
`sostituisci_quote_riparto` sta nell'hot-path del worker
(`worker/queue_processor.py:976`), e la migration `20260827214500` del giorno
prima aveva deciso il contrario per il caso gemello: «non deve far fallire il
worker in hot-path: va segnalato dalla view, non bloccato dal DB». Due migration
consecutive non possono esprimere politiche opposte sullo stesso dato.

Corretti anche due difetti che il reviewer ha trovato nella sanatoria:
- il commento citava un `CHECK (quota_importo >= 0)` **rimosso il giorno prima**
  per consentire le note di credito;
- il filtro `>= 0` faceva il danno opposto: su un header **negativo** (ne
  esistono 6 live) avrebbe **scartato in silenzio** la correzione. Ora l'ordine è
  per `abs(quota_importo)`, che è giusto per entrambi i segni.

Soglia della classe a **0,005** e non 0,01: gli scarti reali valgono *esattamente*
un centesimo, quindi una soglia a 0,01 li avrebbe lasciati passare tutti.

### Lezioni

- **Una correlazione va verificata in entrambe le direzioni.** «Tutti i difettosi
  hanno X» non dice niente finché non si guarda quanti *non* difettosi hanno X.
  Erano 32 su 51, cioè il 63%: la mia "firma" era rumore.
- **Un'aggregazione va calcolata sul gruppo di cui si parla.** `min/max` degli
  `updated_at` su tutti i costi invece che sui 19 mi ha fatto vedere dispersione
  dove c'era un batch di due minuti — e ha trasformato "codice vivo" in "storia".
- **La misura sbagliata è più pericolosa dell'ipotesi sbagliata.** L'ipotesi dal
  planning era dichiaratamente un'ipotesi; la mia arrivava con numeri e query
  allegate, e sarebbe finita nel repo come spiegazione autorevole in un commento
  di migration. Il `code-reviewer` l'ha smontata in due query.
- **Il modo di fallire va scelto guardando chi chiama.** Una guardia corretta nel
  merito, messa nell'hot-path del worker, sarebbe stata una regressione: avrebbe
  bloccato l'elaborazione di una fattura per un centesimo.

---

## F3 — Frontend `components/` condivisi — chiusa 29/08/2026

**Perimetro misurato**: **7.277 righe in 53 file** (`wc -l`). La roadmap
dichiarava 7.274: la cifra giusta è 7.277 — vedi la nota sulle misure in fondo.
Suddiviso per rischio invece che per dimensione:

| Gruppo | Righe | Tocca dati cliente? | Esito |
|---|---|---|---|
| `fatture/` (3 file) | 1.055 | **sì — scrive** (assegna, scarta, ripartisce) | letto riga per riga |
| `nav/`, `brand/`, `legal/`, `admin/`, root (11 file) | 1.133 | sì (lettura/sessione) | letto riga per riga |
| `ui/` (23 file) | 2.414 | no (presentazione) | letto per campionamento mirato |
| `demo/` + `landing/` (16 file) | 2.675 | **no — zero `fetch`** | escluso con misura |

### Correzione al doc: `components/ui/` NON è shadcn vendored

La roadmap chiedeva di «dichiarare escluso con la misura (quanti file sono
vendored e non modificati)». La misura **smentisce la premessa**, quindi
l'esclusione per quel motivo non era disponibile:

- `grep -c radix-ui` su tutti i 23 file di `ui/` → **0**. Non è shadcn stock:
  il progetto usa `@base-ui/react` (`package.json`), su cui i componenti sono
  stati **riscritti a mano**.
- `git log --format='%an' -- components/ui/` → **14 commit, tutti di Mattia
  D'Avolio**, l'ultimo il 5/8/2026 (`d3bd811`, sostituzione di `confirm()`
  nativo con `ConfirmDialog`).

Sono quindi codice di progetto a tutti gli effetti. Restano comunque a rischio
basso — sono presentazionali e non fanno I/O — ma il motivo dell'esclusione è
**"non toccano dati né scritture"**, non "sono generati". La differenza conta:
la prima è verificabile, la seconda era falsa.

### `demo/` + `landing/` — esclusi con misura

`grep -rn "fetch(" demo/ landing/` (2.675 righe) → **zero occorrenze** (l'unico match è un
commento in `demo-chat.tsx` che dice esplicitamente «NIENTE fetch a /api/chat»).
Rendono contenuto hardcoded: nessun dato cliente, nessuna scrittura. Verificata
anche l'assenza di cifre spacciate per reali: l'unico `%` in `landing-page.tsx`
è un valore di opacità dentro un commento.

### Ipotesi verificate

**H-dominio — la coda reintroduce un fallback travestito lato client? NO.**
`dropdown-categoria.tsx` esclude esplicitamente sia `CATEGORIA_NON_CLASSIFICATA`
sia `"📝 NOTE E DICITURE"` dalle voci selezionabili (righe 54-59), con il motivo
documentato: sono stati che solo l'AI può assegnare, e i backend li rifiutano con
400/422. La costante TS `"Da Classificare"` (`lib/categorie-spesa.ts:23`) è
**identica** a quella Python (`config/constants.py:1929`). La variante errata
`"Da Clasificare"` compare solo come rifiuto difensivo lato server. Regole di
dominio #1 e #2 rispettate.

**H-percentuali — la tolleranza client sulle quote diverge dal server? NO,
è speculare.** `ripartisci-dialog.tsx:120` usa `Math.abs(sommaPerc - 100) > 0.5`;
`riparto.py:120` usa `abs(tot_perc - 100.0) > 0.5`. Stessa soglia, e l'ultima
quota assorbe il resto (`_quote_percentuali`), quindi la somma pareggia sempre
l'importo — coerente col fix F-DRIFT. Il default "parti uguali" con 3 sedi
produce 33.3×3 = 99.9: dentro tolleranza su entrambi i lati, e il residuo lo
assorbe l'ultima quota. Nessuna deriva.

**H-selezione — la selezione multipla può disallinearsi da `items`? NO.**
`selezione` viene potata a ogni rimozione riuscita (righe 198 e 254) e azzerata
alla chiusura della finestra (riga 364); tutti i consumatori la intersecano
comunque con `items`. Il confronto `prev.size === items.length` in `toggleTutte`
è quindi consistente.

### Findings

**1. 🟡 `MobileRedirect` non scatta su `/margini` — FIXATO**

`pathname.startsWith("/m")` matcha per **prefisso**, non per segmento: oltre alle
rotte mobile matcha anche `/margini`, che esiste in `(app)/`. Un utente su
telefono che arriva su `/margini` (bookmark, link, cronologia) **resta sul layout
desktop**, che per CLAUDE.md non è responsive.

Che sia involontario è documentato dalla storia. Il componente è stato introdotto
da `e6ed97f` (2/6/2026, *"PWA installabile con 5 sezioni"*); lo stesso giorno
`6ca6728` (*"Impostazioni dentro la PWA + rimossa «Vista completa»"*) ne ha
**tolto** la whitelist `MOBILE_ALLOWED` e il flag force-desktop, cioè ha stretto
il confinamento dei mobile dentro `/m` invece di allentarlo. `/margini` è più
vecchio del componente, quindi il difetto è latente fin dall'introduzione. Non
esiste `/m/margini`: la destinazione corretta è la home mobile.

Verificato che diverge **esattamente una rotta** su 14 e che nessuna delle **7**
rotte mobile (`/m` più `briefing`, `chat`, `diario`, `impostazioni`, `notifiche`,
`turni`) regredisce. Il fix allinea il
componente alla convenzione già usata altrove nel repo: `app-sidebar.tsx:166`
scrive `pathname === "/catena" || pathname.startsWith("/catena/")`. Era l'unico
punto che se ne discostava.

Rientra nella deroga (poche righe, componente condiviso, comportamento ovvio,
`tsc --noEmit` verde, nessun effetto sui numeri).

**2. 🟡 Il totale della coda è arrotondato all'euro — ✅ APPROVATO E CORRETTO 29/8**

`coda-da-assegnare.tsx:48`, `euro()` usa `maximumFractionDigits: 0`. È usata sui
**due totali** della coda (righe 351 e 379), mentre gli importi delle singole
fatture nella stessa finestra sono formattati **con i centesimi** (riga 476).
Sullo schermo convivono quindi righe tipo `€ 127,45` e un totale `€ 744`.

Misurato sul DB live (29/8), sullo stesso filtro che usa l'endpoint —
`fatture_queue` con `status = 'da_assegnare'` (`services/routers/fatture.py:1113`),
importo da `payload_meta->>'importo_totale'`: l'utente `2f3f93a1-…` ha **10
fatture in coda**, totale reale **743,60 €**, mostrato come **744 €**; **8 su 10**
hanno centesimi. Il filtro `status` è essenziale per riprodurre la misura: senza,
lo stesso utente conta 428 righe per 448.775,33 €.

Non è un errore di calcolo — `totale` è sommato sui valori pieni, e l'importo
scritto a DB non passa da qui. È solo presentazione. Ma è un **numero mostrato al
cliente**, quindi per la deroga era tornato a Mattia invece di essere corretto
d'iniziativa.

**Esito: approvato da Mattia il 29/8 e corretto.** Il verbale proponeva
`minimumFractionDigits: 2`; l'implementazione **rimuove** invece
`maximumFractionDigits: 0` senza aggiungere nulla, perché `Intl` con
`style: "currency"` su EUR ha già i 2 decimali di default — stesso risultato,
un'opzione in meno. Verificato: `743,60 €` contro il `744 €` di prima.

**Correzione dopo la review** (avevo scritto due cose sbagliate, trovate dal
`code-reviewer` e non da me):

1. Avevo scritto che le cifre "coincidono col formato delle righe per-fattura".
   Coincidono le **cifre**, non il **formato**: `euro()` mette il simbolo *dopo*
   (`743,60 €`), le righe per-fattura e `fmtEuro4()` lo mettono *prima*
   (`€ 743,60`). Restano quindi **2 varianti** di formato valuta nel file, non 1:
   il fix scende da 3 a 2, non azzera l'incoerenza. La posizione del simbolo è
   preesistente e fuori dal perimetro di questa decisione.
2. Avevo scritto che «`1000` rende `1000,00 €` senza separatore di migliaia» come
   se fosse una peculiarità del fix. **Falso**: è il comportamento standard di
   `it-IT`, che a 4 cifre non mette il separatore, e vale identico nelle righe
   per-fattura. Misurato: `10000` → `10.000,00 €` e `€ 10.000,00`; `448775.33` →
   `448.775,33 €` e `€ 448.775,33`. Il separatore c'è in entrambi da 10.000 in su.
   Non c'era nessun "dettaglio non toccato": non c'era proprio un difetto.

**3. 🔵 `ripartisci-dialog`: la somma percentuali diverge dal server sui valori
negativi — DA DECIDERE**

Il client somma **tutte** le percentuali (riga 113); il server scarta prima
quelle `<= 0` (`riparto.py:114`) e somma solo le positive. Con `120 / -20` il
client mostra «Totale: 100.0%», abilita il pulsante, e il server risponde **400**
(`somma attuale: 120.0`).

Fallisce in sicurezza — nessun dato sbagliato viene scritto, e serve digitare una
percentuale negativa per arrivarci — quindi è un difetto di UX, non di integrità.
Segnalato senza fix: cambierebbe una validazione su un percorso che scrive quote.

### Verifica

- `npx tsc --noEmit` → **EXIT 0**.
- Suite Python completa: **11.381 passed / 43 skipped / 0 failed** (168s).
- I 45 test F-DRIFT (`test_riparto_drift_ricomposizione.py` +
  `test_riparto_incoerenza_quote_non_pareggiano.py`) verificati ancora verdi.
- Il fix non ha test: `F2-NOTEST` resta aperto per decisione di Mattia (nessun
  runner di test frontend nel progetto). È stato verificato eseguendo la logica
  di matching su tutte e 14 le rotte `(app)` più le 7 mobile.

### Nota sulle misure — quattro numeri sbagliati in prima stesura

Il `code-reviewer` ha trovato **quattro cifre errate** in questo stesso verbale,
tutte corrette sopra:

- `ui/` dichiarato 2.689 righe, reale **2.414**; `demo/`+`landing/` dichiarato
  2.400, reale **2.675** — erano **invertiti**;
- totale dichiarato 7.274, reale **7.277**: avevo ripreso la cifra dalla roadmap
  invece di usare il mio stesso `wc -l`;
- «le 4 rotte mobile», in realtà **7**;
- provenienza del commit attribuita a `6ca6728` invece che a `e6ed97f`.

Nessuna cambia una conclusione, e il fix e i tre findings reggono tutti alla
riverifica indipendente. Ma è la **terza volta in questo ciclo** (dopo le due
correlazioni verificate in una sola direzione in F-DRIFT) che una misura entra
nel verbale senza ricontrollo. Il pattern è sempre lo stesso: **la cifra ripresa
da un documento invece che ri-misurata**, o misurata una volta sola e trascritta.
In un verbale il cui valore sta nell'essere verificabile, i numeri vanno
ri-misurati al momento di scriverli, non ricordati.

Aggiunta per lo stesso motivo: la misura sul DB live ora cita il filtro
`status = 'da_assegnare'`, senza il quale non è riproducibile da chi legge.

### Residui

Nessuno bloccante. Due findings (2 e 3) restano **decisioni aperte per Mattia**,
entrambi di sola presentazione/UX, nessuno dei due falsa un numero salvato.

---

## F4 — Frontend upload + dashboard — chiusa 29/08/2026

### Correzione al perimetro: la roadmap ne dichiarava un terzo

La roadmap elencava **5 file per 1.564 righe**. Il perimetro reale di
`(app)/analisi-fatture/` + `(app)/dashboard/` è di **4.409 righe in 18 file**
(`find … | xargs wc -l`, 29/8). Mancavano all'appello i **due file più grandi
dell'area**:

- `analisi-fatture/articoli-tab.tsx` — **856 righe**
- `analisi-fatture/pivot-tab.tsx` — **744 righe**

Non è un dettaglio contabile: `articoli-tab.tsx` è **il punto in cui il cliente
riclassifica le righe di fattura**, cioè la regola di dominio #1, ed è stato
toccato il 28/8 (`cbd38b0`, il refactor di "Da Classificare" a fonte unica).
Auditare F4 sui soli 5 file dichiarati avrebbe saltato proprio il file caldo.

È il secondo ciclo di fila in cui il perimetro scritto in roadmap non regge alla
misura (in F3 era la premessa su `ui/`): **il perimetro va misurato all'apertura
della fase**, non ereditato.

| Gruppo | Righe | File | Esito |
|---|---|---|---|
| `analisi-fatture/` | 2.666 | 9 | letto: `articoli-tab`, `pivot-tab`, `upload-modal` riga per riga |
| `dashboard/` | 1.743 | 9 | letto: `kpi-block`, `chat-widget`, `notifiche-widget` |

**Esposizione confermata**: 6.917 `upload_events` totali, **426 negli ultimi 30
giorni**, ultimo il 28/8 — percorso vivo, non storico.

### H1 (l'ipotesi della roadmap) — chiusa in NEGATIVO, nella sua forma forte

L'ipotesi era: il client filtra per estensione, il server valida i magic bytes;
se divergono, un file può essere **accettato dal client e silenzianmente perso**.

Verificato che non accade, su tre livelli:

1. **Il client è più STRETTO del server**, non più largo. Il modale accetta
   `[".xml", ".p7m"]` (`upload-modal.tsx:46`); il worker accetta gli stessi due e
   rifiuta il resto con **422 esplicito** (`fastapi_worker.py:1878`). La
   direzione pericolosa (client più permissivo) non esiste. Un PDF è respinto
   subito a schermo, con messaggio.
2. **La validazione magic-bytes È stata portata sul percorso vivo.** Non è
   rimasta solo in `upload_handler.py` (Streamlit, morto): `fastapi_worker.py:1892-1905`
   la riesegue su XML e P7M, con lo stesso strip del BOM e le stesse firme DER/PEM.
   Verifica non oziosa: `services/upload_policy.py` documenta che le policy sulle
   **date** erano invece rimaste indietro proprio così, e un cliente aveva
   `blocco_mesi_precedenti: true` credendolo attivo.
3. **Nessun file può finire in uno stato invisibile.** Ogni ramo della risposta
   risolve in uno stato terminale mostrato (`queued`/`skipped`/`success`/`error`,
   `upload-modal.tsx:160-180`), inclusi i casi ambigui multi-sede e il doppione
   già in coda.

**Limiti di dimensione: nessuna finestra silenziosa**, ma la motivazione va detta
con precisione (rilievo del `code-reviewer`). I 50 MB per file sono allineati su
tre punti (client `MAX_SIZE_MB`, worker, `MAX_UPLOAD_BYTES`). I **200 MB per
batch** della route Next.js invece **non sono un limite allineato: su questo
percorso sono irraggiungibili**, perché il modale fa **una fetch per file**
(`upload-modal.tsx:127-135`, loop `for`) e il `FormData` che la route somma
contiene sempre un solo file da ≤50 MB. La conclusione (nessun file perso) regge,
ma per questa ragione, non perché i tre livelli "concordino".

Nota minore: `MAX_FILE_SIZE_P7M = 50_000_000` (decimali) contro
`MAX_UPLOAD_BYTES = 52.428.800` (binari) lascia ~2,4 MB in cui il worker accetta
il body e l'estrazione P7M rifiuta — sempre con **422 visibile**, mai in
silenzio, e lo scarto è già commentato in `config/constants.py`.

### Altre ipotesi verificate

**Regola di dominio #1 in `articoli-tab.tsx`: rispettata.** Usa
`CATEGORIA_NON_CLASSIFICATA` dalla fonte unica, nessun literal, nessun fallback
travestito. Il criterio `daScegliereCategoria` è un **OR** (bassa confidenza AI
**oppure** categoria mancante) e il commento spiega il caso reale che lo impone:
le quote di gruppo proiettate hanno `needs_review` hardcoded a `False` anche con
categoria vuota — con l'AND restavano invisibili.

**Doppia scrittura PV + gruppo: gestita, inclusi i parziali.** Un articolo misto
richiede due scritture (`/api/riparto/riga-categoria` e
`/api/fatture/categoria-batch`); il codice le distingue, riporta il **fallimento
parziale** invece di dichiarare successo, e non scambia per successo un
`righe_aggiornate: 0` (che su `categoria-batch` significa "non ho scritto nulla",
mentre sulla rotta di gruppo è legittimo). Segnala anche
`ricalcolo_quote_ok === false`, che altrimenti lascerebbe il MOL disallineato in
silenzio.

**Export XLS ≠ schermo? NO.** `exportXls` legge dalla stessa prop `pivot` che
alimenta la tabella, e i filtri passano da URL param che la rifanno: export e
video non possono divergere per costruzione.

**Ricalcoli client in `pivot-tab.tsx`**: `totale`, `media`, `incidenza_pct` e
`grand_total` arrivano tutti dal server; il client arrotonda solo per la vista.
L'unico calcolo locale è la **% per periodo** (righe 78 e 390), che il server
davvero non espone (assente da `PivotResponse` in `lib/fatture.ts`). Legittimo.

**Timeout mancanti sui widget: NON è un rischio di blocco.** Né `chat-widget` né
`notifiche-widget` mettono `AbortSignal.timeout` sulle loro `fetch` — stessa
forma del finding F2 su `logoutSession` — ma qui le rotte server a valle ce
l'hanno entrambe (`chat/route.ts:30` con `CHAT_TIMEOUT_MS`, `notifiche/route.ts:16`
con `WORKER_TIMEOUT_MS`): un worker bloccato torna comunque un errore. Chiuso in
negativo.

### Findings

**1. 🟡 Sparkline YTD duplicata — e le due copie SONO GIÀ DIVERGENTI**

*(Correzione: in prima stesura avevo scritto che i due blocchi erano "identici" e
che quindi il rischio era solo di manutenzione. È falso, e l'ha smontato il
`code-reviewer`. La differenza sta esattamente nella riga che protegge da un
crash.)*

Il calcolo YTD è duplicato fra `dashboard/kpi-block.tsx` (`MolAndamento`) e
`catena/sintesi-catena.tsx` (`MolSparkline`): stesso path SVG, stesso
`ytdPct` con la guardia `primo > 0`, stesse label. Ma **la guardia sul numero di
punti sta in due posti diversi**:

| | guardia interna | guardia al call site |
|---|---|---|
| `MolSparkline` (catena) | **sì** — `if (punti.length < 2) return null` (:140) | no (:318) |
| `MolAndamento` (dashboard) | **no** | sì — `kpi.mol_mensile.length >= 2` (:312) |

`MolAndamento` con meno di 2 punti non è difeso da sé: con 1 punto `n - 1 === 0`
rende `x(i)` un `NaN` (path `MNaN,NaN`), con 0 punti `punti[n - 1].mol` solleva
**TypeError e rompe il render della Home**.

**Oggi non esplode**, perché entrambi i call site sono guardati: il cliente non
vede nulla di sbagliato. Ma la classificazione 🔵 "solo manutenzione" era troppo
generosa: le due copie si sono **già mosse in modo diverso**, ed è la forma
peggiore del copia-incolla — chi guardasse `MolSparkline` (che si difende da
sola) e ne deducesse che la guardia esterna su `MolAndamento` è ridondante,
introdurrebbe il crash rimuovendola.

Non fixato: tocca due pagine che mostrano numeri, fuori dalla deroga. La via
minima è spostare la guardia **dentro** `MolAndamento`, rendendolo sicuro come il
gemello, senza cambiare nulla di ciò che si vede.

**2. 🔵 `ai_pending`: il contratto del worker dice una cosa, il prodotto ne ha
decisa un'altra**

`UploadInvoiceResponse.ai_pending` (`fastapi_worker.py:1705`) è popolato per le
fatture sopra la soglia di righe, e il commento prescrive: *"needs_review_count
riflette solo regole+dizionario e sarà rivisto quando l'AI finisce: **il frontend
deve dirlo**, non spacciarlo per conteggio definitivo"*. Nel frontend
`ai_pending` **non è letto da nessuna parte** (`grep -rn ai_pending apps/web/src/`
→ zero).

Non è però una dimenticanza: il commit `dfdebc2` (27/8) si intitola *"rimuove il
messaggio ai_pending dal modale — confondeva più che aiutare"*. È una **decisione
di prodotto già presa**. Resta che il commento nel worker prescrive un
comportamento che il prodotto ha deliberatamente abbandonato: è il commento a
essere disallineato, non il frontend. Da aggiornare quando si tocca quel punto,
così non induce in errore chi lo legge.

### Verifica

- `npx tsc --noEmit` → **EXIT 0**.
- Nessuna modifica al codice in questa fase: F4 si chiude **senza fix**, tutte le
  ipotesi verificate chiudono in negativo.
- Misure DB rieseguite al momento della scrittura (`upload_events`: 6.917 / 426
  su 30gg / ultimo 28/8), non riprese da roadmap.

### Residui

Nessuno bloccante. Un finding 🔵 di manutenzione (sparkline duplicata) resta
**decisione aperta**. Confermato che `F2-NOTEST` continua a pesare qui: le tre
verifiche più delicate di questa fase (doppia scrittura parziale, stati terminali
dell'upload, OR di `daScegliereCategoria`) sono coperte **solo dalla lettura**,
perché non esiste un runner di test frontend.

---

## Chiusura decisioni 🟡 di F3 e F4 — 29/08/2026

Mattia ha approvato entrambe le decisioni 🟡 rimaste aperte dopo il merge di
F3+F4 (`429865d`). Accorpate in **una sola PR**: sono entrambe frontend, quindi
stessa pipeline `deploy-vercel.yml` e **un solo deploy**. I due 🔵 restano
aperti di proposito (vedi sotto).

**Diff: 2 file, +11/−3.**

### Fix 1 — centesimi sul totale della coda

`apps/web/src/components/fatture/coda-da-assegnare.tsx` — rimosso
`maximumFractionDigits: 0` da `euro()`. Dettagli e verifica nel finding 2 di F3
sopra, aggiornato con l'esito.

### Fix 2 — guardia spostata dentro `MolAndamento`

`apps/web/src/app/(app)/dashboard/kpi-block.tsx` — `if (punti.length < 2) return null`
come prima riga del corpo, nella stessa posizione del gemello `MolSparkline`
(`sintesi-catena.tsx:140`). La guardia al call-site è stata **rimossa**, non
lasciata in doppio: tenerle entrambe avrebbe ricreato la ridondanza che ha
permesso alle due copie di divergere. Il call-site passa da `>= 2` a `> 0`
(`mol_mensile` è `MolMensile[]` non opzionale — `lib/home.ts:87` — quindi
`.length` è sicuro), e il commento sopra, che descriveva la soglia dei 2 mesi
lì dov'era, è stato riscritto: lasciarlo sarebbe stato lo stesso difetto del
finding 🔵 su `ai_pending`.

**Provato per mutazione** (copia in scratchpad, mai sul file del branch),
disattivando la guardia:

| punti | con guardia | senza guardia |
|---|---|---|
| 1 | non renderizza | `d="MNaN,36.0"` — linea **disegnata sbagliata** |
| 0 | non renderizza | `TypeError: Cannot read properties of undefined` |

Il mutante muore in entrambi i casi. **Correzione al verbale F4**: avevo scritto
che `MolAndamento` "da solo crasherebbe a 0 punti", fermandomi al caso che
crasha. Il caso a **1 punto** è peggiore — non crasha, rende `NaN` dentro il
path SVG, cioè fallisce in modo silenzioso.

**Precisazione emersa in review**: il fix **sposta** la soglia dei 2 punti, non la
elimina. Oggi vive in **tre** posti — `services/fastapi_worker.py:7318`
(`if len(mol_mensile) < 2: mol_mensile = []`), il commento del tipo in
`lib/home.ts:86`, e ora il componente. È difesa in profondità, non duplicazione
da sanare: il worker garantisce già che la lista sia vuota o ≥2, quindi sui dati
reali il caso a 1 punto **non può arrivare** e la guardia interna protegge da un
riuso futuro, non da uno stato attuale. Per la stessa ragione il passaggio del
call-site da `>= 2` a `> 0` è indistinguibile sui dati veri.

### Verifica

- `npx tsc --noEmit` → **EXIT 0**
- `tests/test_documentazione_onesta.py` → **51 passed**
- Mutazione sulla guardia: 2 mutanti su 2 uccisi
- Nessun test frontend esiste su questo perimetro (F2-NOTEST resta ⚪ per
  decisione di Mattia): la prova per mutazione su copia è l'unica rete
  disponibile, ed è per questo che è stata fatta.

### Cosa resta aperto, di proposito

- 🔵 **`ripartisci-dialog`, percentuali negative** — client e server divergono,
  ma **fallisce in sicurezza**: il server risponde 400 e nessun numero sbagliato
  raggiunge il cliente. Non vale un deploy per sé.
- 🔵 **commento `ai_pending` nel worker** — è Python → **Railway**, pipeline
  diversa da questi due fix. Accorparlo qui non avrebbe senso: se lo prende F5,
  che tocca lo stesso worker.
