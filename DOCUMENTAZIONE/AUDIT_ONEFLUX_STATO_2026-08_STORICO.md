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
