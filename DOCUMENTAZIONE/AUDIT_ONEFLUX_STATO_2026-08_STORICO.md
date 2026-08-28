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
| F-DRIFT | ⚪ | 19 costi su 156: somma quote ≠ totale (max 1 cent, tot 19 cent) | **aperto — a Mattia** |

`F-DRIFT` resta aperto per scelta: tocca numeri mostrati al cliente e sta lato
Python nel riparto, quindi fuori dalla deroga concessa in planning.

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
tal quale in `window.location.href`. Il produttore legittimo (`proxy.ts:93`)
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
| F2-REDIRECT | 🔴 HIGH | open redirect su `/login?next=` (anche `javascript:`) | fixato |
| F2-PWD | 🟠 MED | cambio password fuori dalla policy GDPR + client che promette requisiti falsi | fixato |
| F2-MOBILE | 🟠 MED | cold-start del worker slogga dalla PWA (7 pagine, 82 sessioni/30gg) | fixato |
| F2-LOGOUT | 🟡 LOW | `logoutSession` unica chiamata worker senza timeout: worker appeso = utente non esce | fixato |
| F2-NOTEST | ⚪ | zero infrastruttura di test frontend (confermato anche in F1) | **aperto — a Mattia** |

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
