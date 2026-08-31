# Storico ciclo audit aperto il 29/08/2026

Verbale delle dimensioni chiuse. Ogni cifra qui è misurata al momento della
scrittura, col comando accanto — mai ereditata da un documento precedente.

---

## Dimensione «route API» — 30/08/2026

**Esito: aperta e chiusa nella stessa sessione.** Audit read-only completo del
layer + una rete strutturale sull'auth. Nessun difetto sfruttabile trovato; il
lavoro utile si è spostato dove la misura ha indicato, non dove il prompt
supponeva.

### Il risultato principale: le tre ipotesi di partenza erano false

Il prompt di sessione chiedeva di verificare tre ipotesi. **Tutte e tre
smentite dalla misura**, ed è il lascito più utile di questa dimensione:

| Ipotesi | Misura del 30/8/2026 |
|---|---|
| route che scrivono senza validare l'input | **0 body grezzi** su 114 POST/PUT/PATCH del worker — nessun `body: dict`, nessun `Body(...)` non tipizzato. Tutto Pydantic. |
| `ristorante_id` preso dal client | **0 route** lo leggono da query o body. Deriva sempre da `_resolve_ristorante_id` (`fastapi_worker.py:7578`) server-side. |
| soft-delete non applicato ovunque | **48/50** select su `fatture` filtrano. Le 2 restanti sono volute e commentate (`riparto.py:505-507`, `admin.py:999`). |

Il layer Next.js **non è un layer di sicurezza**: è un proxy trasparente.
0 route su 169 toccano Supabase, 163 inoltrano al worker con `Bearer` +
`X-Worker-Key`. Cercare lì difetti di autorizzazione era cercare nel posto
sbagliato — l'autorizzazione vive interamente nel worker.

Ricerca IDOR sul worker: 34 query per-id senza filtro tenant, di cui **32 in
`admin.py` dietro `Depends(_verify_admin)`** (accesso cross-tenant è il
requisito) e 2 con il check di proprietà eseguito separatamente nella stessa
funzione (`fatture.py:1030-1037` prima dell'update a `:1053`). **Nessun IDOR
raggiungibile da un utente non-admin.**

### Il rischio vero: strutturale, non puntuale

Misurato per introspezione di `app.routes` (non per grep):

```
totali=238  admin=49  authorization=179  SENZA IDENTITA'=10
```

(`admin=49` sono le route con `Depends(_verify_admin)`: 48 sotto `/api/admin/`
piu' `/api/account/svuota-dati`, che sta fuori da quel prefisso. I path sotto
`/api/admin/` sono **51**: i 3 di scarto sono i machine-gate in allowlist.)

228 endpoint su 238 risolvono l'identità del chiamante — ma **imperativamente
nel corpo dell'handler**, e tutti e **12** i router sono `APIRouter()` nudo,
nessuno con `dependencies=[...]`:

```bash
grep -n "APIRouter(" services/routers/*.py   # 12 file, tutti nudi
```

Il default è **aperto**: un endpoint nuovo che dimentica
`_resolve_user_from_token` è esposto e niente lo segnala — non un tipo, non un
lint, non un test. La copertura del 96% è disciplina, non struttura. È questa
la falla che è stata chiusa.

### La rete: `tests/test_route_api_auth_dichiarativa.py`

9 test che enumerano gli endpoint **dall'app vera** e falliscono se uno nuovo
non risolve l'identità. Allowlist di 10 deroghe, ognuna con la ragione scritta
accanto: chi aggiunge un endpoint senza auth deve motivarsi lì.

**Perché per introspezione e non per grep.** Il grep di
`_resolve_user_from_token` conta 187 occorrenze contro 179 endpoint che lo
usano — alcune funzioni la chiamano più volte, altre occorrenze sono wrapper e
import. Un test su regex del sorgente misura il proprio pattern, non l'app.

**Una trappola pagata durante la stesura, ora scritta nel docstring del test.**
Il gate admin esiste in **due** forme (documentate in `admin.py:7-8`): nel
decoratore e come parametro di funzione (`admin_user: dict = Depends(_verify_admin)`).
La prima stesura del classificatore guardava solo `route.dependencies` e
dichiarava **44 endpoint «senza identità», di cui 34 falsi positivi tutti
admin**. Se qualcuno semplifica `_dipendenze()` a una sola forma, il test torna
a mentire — per questo la ragione sta nel file, non solo qui.

Scarto rispetto all'inventario di apertura: i «12 senza identità» stimati per
grep sono in realtà **10**. `/api/auth/me`, `/logout` e `/accetta-privacy`
*hanno* il parametro `authorization` e validano il bearer inline
(`fastapi_worker.py:1284-1293, 1350-1361, 1376-1383`): sono autenticati, è
duplicazione, non un buco. Un test ad hoc verifica che restino **solo** questi
tre — se la lista cresce, il segnale `authorization` si sta sfaldando.

### Prova per mutazione — 8 mutanti, 8 esiti attesi

Su copia in scratchpad, mai sul file del branch. Ogni mutante verificato che si
applicasse davvero prima di leggerne l'esito (lezione del punto 9: due mutanti
«sopravvissuti» non applicavano nessuna mutazione).

| # | Mutante | Atteso | Esito |
|---|---|---|---|
| 1 | endpoint nuovo senza auth | rosso | ✅ ucciso |
| 2 | endpoint nuovo **con** `authorization` | **verde** | ✅ nessun falso positivo |
| 3 | `Depends(_verify_admin)` rimosso da una route admin | rosso | ✅ ucciso da **2** test |
| 4 | allowlist svuotata | rosso su 10 | ✅ esattamente i 10, nessuno di più |
| 5 | endpoint che **dichiara** `authorization` e non lo usa | rosso | ✅ ucciso |
| 6 | voce fantasma nell'allowlist | rosso | ✅ ucciso |
| 7 | sorgente illeggibile (`getsource` fallisce) | rosso | ✅ segnala invece di assolvere |
| 8 | gate via `Annotated[dict, Depends(...)]` | **verde** | ✅ riconosciuto; disattivando il ramo → rosso |

Il 5 è il più importante: è il modo esatto in cui il segnale di questa rete
potrebbe essere aggirato, ed è coperto.

I mutanti 7 e 8 provano i due fix aggiunti dopo il `code-reviewer` (sotto). Il
mutante 8 ha richiesto **tre stesure**: le prime due non caricavano nemmeno
l'app (import mancante, poi endpoint collocato *prima* della definizione di
`_verify_admin`) e il loro esito non misurava niente — la trappola che questo
ciclo documenta da due sessioni. Vale solo la terza, con l'endpoint verificato
montato in `app.routes`.

### Cosa ha trovato il `code-reviewer` (e che è stato corretto)

Il gate ha bloccato la chiusura per una ragione netta: **i file erano `git add`-ati
ma mai commitati** — non «committati e non pushati», come credevo. Per git non
esistevano. Corretto prima di procedere.

Tre findings sul test, tutti accolti e provati per mutazione:

- **`except (OSError, TypeError): continue` assolveva in silenzio** un endpoint
  di cui non si legge il sorgente. In una rete di sicurezza è lo stesso
  meccanismo dell'`except` silenziatore già pagato in questo repo: ora raccoglie
  gli illeggibili e **fallisce** nominandoli (mutante 7).
- **`Annotated[dict, Depends(_verify_admin)]` non era riconosciuta.** Forma oggi
  assente dal repo (0 occorrenze) e *fail-safe* — avrebbe rotto la CI, non aperto
  l'app — ma un test che sbaglia insegna a ignorarlo. Aggiunta, con controprova
  (mutante 8).
- **Il docstring prometteva più di quanto copre**: la sub-dependency annidata
  (`Depends(wrapper)` che dipende a sua volta dal gate) resta fuori. Ora è
  scritto nel file invece che taciuto.

Restano noti e non corretti, perché fail-safe o già documentati: il match
testuale su `_resolve_user_from_token` è soddisfatto anche da una menzione in
codice morto, e `/api/admin/riparto/auto-pulisci` resta il punto più esposto
della superficie (allowlistato con la sua ragione).

### Findings registrati — nessuno richiede intervento urgente

1. **`/api/parse` accetta `user_id: Form(None)` non verificato**
   (`fastapi_worker.py:847`, usato a `:900` e `:912`). **Severità bassa,
   misurata non ereditata**: è read-only (precarica la memoria classificazioni,
   non scrive), e i chiamanti sono interni (`services/worker_client.py:234`,
   `worker/queue_processor.py`) — nessun path dal browser. Gate: `X-Worker-Key`
   + rate-limit IP.
2. **Due dialetti di auth nel layer Next** — 99 route usano `getToken()`, 66
   riscrivono il cookie inline, e **27 file** ridefiniscono localmente
   `workerHeaders` duplicando `worker-config.ts:18`. Il commento a
   `worker-config.ts:7-8` dà la centralizzazione per compiuta: **è a metà**.
   Debito di leggibilità, non di sicurezza — entrambi i dialetti autenticano.
   `forbidden()` (`:30`) non è usata da nessuna delle 169 route.
3. **`/api/admin/riparto/auto-pulisci`** (`riparto.py:1065`) scrive con
   `?apply=true` sotto il solo `_verify_worker_key`. **Non è una dimenticanza**:
   `riparto.py:1004-1010` argomenta la scelta (consumatore GitHub Actions) e
   avverte cosa servirebbe per esporlo alla pagina admin. Rischio noto e
   accettato, ora anche vincolato dall'allowlist del test.

### Non fatto, e dichiarato

- **Alzare `dependencies=[...]` a livello di `APIRouter`** è la correzione
  strutturale piena, ma tocca 238 endpoint ed è un cambiamento di comportamento
  su tutto il traffico. Non fatto in questa sessione: il test chiude la falla di
  *regressione*, che è il valore vero. Resta aperto come scelta.
- **Scadenziario** (2.001 doc non pagati, 1.853 scaduti, `scadenziario-client.tsx`
  da 2.244 righe, UI di lettura mai auditata): non aperto. Resta la prossima
  priorità.

### Verifica

- `python -m pytest tests/test_route_api_auth_dichiarativa.py` → **9 passed**
  (rieseguito dopo i fix del reviewer)
- `python -m pytest tests/` → **11.511 passed, 43 skipped**, nessuna regressione
- Baseline radar ricontrollata a inizio sessione: `notification_inbox` 65 record
  — `operativa` 58 (ultima 28/8), `upload` 7 (ultima **1/6/2026**, blocco morto
  confermato), **`radar` 0**. Nessuna ritaratura da rivedere.

---

## Voci ereditate + primo pezzo di scadenziario — 31/08/2026

**Esito: 2 voci di roadmap su 3 erano false, e la terza aveva la domanda
sbagliata.** Il lavoro utile è finito altrove rispetto a dove era scritto.

### Le tre «voci aperte ereditate» ri-misurate

Erano marcate «verificate ancora vere il 30/8/2026». Non lo erano. All'inizio
della sessione le ho riprese per buone e **hanno prodotto lavoro fantasma**
finché la misura non le ha smontate: è il modo esatto in cui un documento sempre
in contesto propaga i propri errori — la lezione che questo ciclo documenta da
tre sessioni, pagata una quarta volta.

| Voce | Esito 31/8 |
|---|---|
| `normalizza_descrizione` «5 pattern su 7» | **FALSO.** Applica tutti e 7 gli step; le 6 costanti `REGEX_*` esistono, sono importate (`:17-22`) e popolate (30 + 19 + 10 pattern + 3 regex). Voce chiusa, nessun intervento. |
| blocco notifiche `source_type='upload'` «morto» | **FUORVIANTE.** Non è morto: è **irraggiungibile per costruzione** e già coperto da 5 test che lo dichiarano escluso per misura. La data «1/6/2026» non è un guasto: è la dismissione di Streamlit. |
| `check_weekly` «zero chiamanti» | **VERO, ma la domanda era mal posta** — vedi sotto. |

### `check_weekly`: non «da agganciare o rimuovere», ma catena morta a due anelli

La roadmap chiedeva una decisione di prodotto: agganciarlo o rimuoverlo.
**Nessuna delle due**, perché agganciarlo non produrrebbe niente.

Misurato sul DB live (progetto `vthikmfpywilukizputn`): `check_weekly` legge
`topic_key='price_alert'`, di cui esistono **3 righe in tutto, tutte
`source_type='upload'`, l'ultima 1/6/2026**. L'unico emettitore è
`upload_handler.py:2019`, dentro il percorso `legacy_streamlit` già morto.
Schedularlo leggerebbe 0 righe e tornerebbe `[]` per sempre.

Tenuto e non rimosso: la logica (`fornitore_critico_consecutivo`, 3+ mesi
consecutivi di rincari) è scritta e testata via `_check_consecutive_months`.
**Manca il produttore a monte, non questo codice.**

Il fatto è stato spostato **dal documento al codice**, dove non può marcire in
silenzio: docstring di `anomaly_radar_service.py` + 2 test nuovi in
`test_radar_aggancio_percorso_vivo.py`.

| # | Mutante | Atteso | Esito |
|---|---|---|---|
| 1 | `check_weekly` agganciato a `invoice_service` | rosso | ✅ ucciso |
| 2 | sorgente `price_alert` in forma **kwarg** | rosso | ✅ ucciso |
| 3 | sorgente `price_alert` in forma **dict** | rosso | ✅ ucciso |
| 4 | **controprova**: menzione in un *commento* | **verde** | ✅ nessun falso positivo |
| 5 | **controprova**: menzione in una *stringa a riga singola* | **verde** | ✅ nessun falso positivo |

**Il test è stato riscritto due volte, e la seconda per un difetto trovato dal
`code-reviewer`.** Vale la pena la cronaca, perché è la stessa classe di errore
che il ciclo insegue da tre sessioni:

- **Prima stesura** (match testuale riga per riga): falso positivo **sul
  docstring che avevo appena scritto** — cioè sul testo che documenta il
  difetto.
- **Seconda stesura** (match testuale + `tokenize` per saltare commenti e
  stringhe multi-riga): verde, e sembrava finita. Il `code-reviewer` l'ha provata
  per mutazione e ha trovato il **falso negativo**: cercava solo il kwarg
  `topic_key='price_alert'`, quindi **non vedeva `fastapi_worker.py:6443`**, dove
  il topic è una chiave di dict (`"topic_key": "price_alert"`). Montando la forma
  dict, il test restava verde. Un assert che passa col difetto presente — la
  classe esatta del `1280 not in (k[c],)` del 29/8.
- **Terza stesura**: **AST**, la tecnica già usata dieci righe più su nello
  stesso file (`test_ogni_call_site_del_repo_rispetta_la_firma`). L'albero vede
  entrambe le forme di scrittura e ignora per costruzione commenti e stringhe,
  senza bisogno di `tokenize`.

Il sorgente `fastapi_worker.py:6443` emerso dalla revisione **non cambia la
conclusione**: costruisce un dict in memoria con `source_type='live'` per il
briefing e non chiama mai `upsert_inbox_notifications`, quindi non persiste su
`notification_inbox` e `check_weekly` continuerebbe a leggere 0 righe. Ma è ora
**sorvegliato**: è nella lista dei sorgenti noti del test, e uno nuovo lo fa
fallire. Il test è stato rinominato di conseguenza —
`test_price_alert_non_ha_scrittori_vivi_su_notification_inbox` — perché
«emettitore» confondeva chi *costruisce* un record con chi lo *persiste*.

### Scadenziario: la dimensione era più piccola di come era scritta

Ri-misurata la copertura prima di aprirla: **69 test verdi** su 5 file
(backend, RPC, regole, chat, catena, KPI frontend). La roadmap diceva che i test
del punto 9 coprivano «`computeKpi` e `bucketizeDocumenti`»: sono **4 funzioni
su 4** — tutte le funzioni logiche esportate da `lib/scadenziario.ts` — e su 2
fusi. **Il difetto storico di fuso su `pagata_at` era già coperto anche in
lettura**, che era la preoccupazione principale con cui la dimensione era stata
messa 🔴.

Scoperto restava **solo** `scadenziario-client.tsx` (2.244 righe): rendering,
stato, hook. Cioè ciò che il punto 9 dichiara fuori perimetro per costruzione.

**Fatto il primo pezzo**, sulla strada già battuta con `poolSaturo`/F7:
`buildCashFlow` viveva dentro il componente, irraggiungibile da qualunque test.
È la funzione che decide **quanto denaro l'utente vede in ciascuna fascia di
esposizione futura** — sbagliarne un confine sposta euro veri fra due colonne.

Estratta in `apps/web/src/lib/scadenziario.ts`. Il refactor è provato
equivalente, non solo `tsc`-pulito: corpo della funzione **identico riga per
riga** all'originale (`diff` sul sorgente pre/post). 8 test nuovi, su fixture
**ai confini esatti** perché i confini non sono simmetrici — `scadute` è stretto
(`s < today`), le altre fasce inclusive (`s <= inN`): un documento che scade
oggi sta in «Entro 7gg».

| # | Mutante | Atteso | Esito |
|---|---|---|---|
| 1 | `s < today` → `s <= today` (confine scadute) | rosso | ✅ ucciso (4 test) |
| 2 | finestra 7gg → 6gg | rosso | ✅ ucciso |
| 3 | note di credito rientrano nel debito | rosso | ✅ ucciso (6 test) |
| 4 | `new Date()` invece di `parseLocalDate` | rosso | ✅ ucciso (3 test) |

Il 4 è il difetto storico di fuso: ora è coperto anche sulla barra cash-flow.
Un test asserisce che **le tre implementazioni degli stessi confini**
(`computeKpi`, `bucketizeDocumenti`, `buildCashFlow`) concordino: ciascuna
ricalcola il proprio `today`, ed è la terna che si separa al primo refactor di
una sola delle tre.

### Verifica

- `python -m pytest tests/` → **11.521 passed, 43 skipped** (era 11.511: +10)
- `npx tsc --noEmit` → pulito
- `tests/test_documentazione_onesta.py` → 51 passed
- **9 mutanti in totale, 9 esiti attesi**, ognuno verificato montato prima di
  leggerne l'esito (5 sulla catena morta, 4 sul cash-flow)
- `code-reviewer` eseguito sul diff cumulativo: ha trovato **un falso negativo
  nel test radar** (forma dict non vista) e **due affermazioni più larghe del
  codice** nei .md. Entrambi corretti e ri-provati per mutazione prima della
  chiusura.

### Non fatto, e dichiarato

- **`scadenziario-client.tsx` resta 2.210 righe di UI non testata** (`wc -l`, 31/8; era 2.244, `lib/scadenziario.ts` 200 → 245). Estratto
  solo `buildCashFlow`. Il resto (rendering, stato, hook, filtri client) richiede
  o altre estrazioni o un runner di componenti — che il punto 9 ha escluso per
  ragione strutturale (`deploy-vercel.yml`).
- **`dependencies=[...]` a livello di `APIRouter`** — invariata dalla sessione
  del 30/8: tocca 238 endpoint, cambia comportamento su tutto il traffico.

---

## Sessione 31/08/2026 (2ª) — chiusura dimensione «scadenziario»

**Verdetto: chiusa.** La logica che decide **quali fatture il cliente vede** e
**quali numeri legge** è uscita dal componente ed è coperta. Nel client resta
rendering, stato e hook — cioè ciò che non muove né euro né inclusioni.

### Cosa è stato fatto

7 funzioni estratte da `scadenziario-client.tsx` a `lib/scadenziario.ts`
(2.210 → **2.119** righe il client, 245 → **433** il lib):

| Funzione | Perché non poteva restare nel componente |
|---|---|
| `matchDocumento` | **il cuore**: decide l'inclusione di ogni riga |
| `filtraDocumenti` | wrapper, confini calcolati una volta sola |
| `aggregaPerSede` | riimplementava «è un debito» (3ª copia) |
| `statoDocumento` | 4ª derivazione dello stato, dentro `exportCsv` |
| `elencaFornitori` | decide le voci del filtro fornitore |
| `ordinaDocumenti` | decide l'ordine del CSV scaricato |
| `fornitoreKey` | dipendenza delle precedenti |

**`matchFiltriComuniRef` eliminato.** Era un ref assegnato *dentro* un `useMemo`
(side-effect in fase di render) per condividere una closure con `kpiPerSede`:
i due memo erano quindi legati da un ordine di valutazione implicito, e
`kpiPerSede` poteva leggere un predicato stale. Con la funzione pura il
problema non esiste più — non è stato "pulito per estetica".

### La divergenza trovata, e lasciata com'è

Il chip filtro **«Questo mese»** mostra `oggi..+30gg` (**cumulativo**, include
la settimana); la sezione in agenda **«Questo mese»** mostra `+8gg..+30gg` (la
esclude, perché la settimana ha già la sua sezione). **Stesse parole, due
insiemi diversi, nessun test su nessuno dei due.**

Non è un bug — sono due domande diverse — ma era una trappola: chi le allinea
«per coerenza» cambia ciò che il cliente vede. **Deciso da Mattia il 31/8: si
lascia il comportamento invariato e si scrive il perché in un test**
(`test_chip_mese_e_cumulativo_non_e_il_bucket_mese`), che asserisce entrambi i
lati e la relazione di sovrainsieme stretto fra loro.

### Prova per mutazione — 15 mutanti, 15 uccisi

Ognuno applicato su copia, **verificato montato** (`git diff` non vuoto) prima
di leggerne l'esito, e ripristinato prima del successivo.

| # | Mutante | Ucciso da |
|---|---|---|
| M1 | `s < today` → `<=` | `test_scadute_esclude_chi_scade_oggi` |
| M2-M3 | confini settimana `>=`/`<=` allentati | `test_settimana_include_oggi_e_il_settimo_giorno` |
| M4 | chip «mese» allineato al bucket | **`test_chip_mese_...`** |
| M5 | confine del bucket «mese» spostato | `test_chip_mese_...` + `test_bucket_e_kpi_concordano` |
| M6 | il periodo non esclude più le pagate | 4 test |
| M7 | lista fornitori vuota che filtra tutto | `test_filtro_fornitori_vuoto_non_filtra_nulla` |
| M8 | nome fornitore raro invece del frequente | `test_elenca_fornitori_deduplica_per_piva` |
| M9 | `soloNuove` invertito | `test_filtro_solo_nuove` |
| M10 | in `statoDocumento`, NC dopo pagata | `test_stato_documento_concorda_con_i_bucket` |
| M11-M12 | ramo personalizzato → `true`; estremo alto esclusivo | `test_personalizzato_e_le_senza_scadenza` |
| M13 | `?? Infinity` → `?? 0` | `test_ordina_mette_le_senza_scadenza_in_fondo` |
| M14 | NC contate fra i debiti per-sede | `test_aggrega_per_sede_conta_solo_i_debiti` |
| M15 | `parseLocalDate` → `new Date()` | 6 test, **entrambi i fusi** |

**Due cose misurate che smentiscono un'attesa, e vanno dette:**

1. **M13 al primo tentativo non è stato applicato**: `?? Infinity` compare
   **due volte** e la sostituzione è stata rifiutata invece di produrre un
   «sopravvissuto» che non misurava nulla. Ripetuto con contesto univoco
   (entrambe le righe insieme) → ucciso.
2. **M15 muore in *entrambi* i fusi**, non solo a Los Angeles come previsto.
   Indagato invece di darlo per buono: a Roma `new Date("2026-08-31")` vale
   **02:00 locali**, stesso giorno ma *non* mezzanotte, e basta a spostare un
   confronto inclusivo contro un estremo scelto dall'utente. La previsione
   «muore solo a ovest» vale per la lettura di `pagata_at` in `computeKpi`
   (altro file), non per questi confini. Il test è più forte del previsto, non
   più debole.

### Verifica

- `python -m pytest tests/` → **11.545 passed, 43 skipped** (era 11.521: +24)
- I 5 file storici dello scadenziario → **77** (la roadmap diceva 69: cifra
  già invecchiata prima di questa sessione); **101** col nuovo file dei filtri
- `npx tsc --noEmit` → pulito **prima e dopo** (misurato prima del refactor:
  già a zero, quindi ogni errore sarebbe stato mio)
- `check_documentazione.py` → pulito
- Nessun altro file dell'app usava i simboli spostati (verificato con grep)

### Correzioni dopo il `code-reviewer` (stessa sessione)

Il reviewer ha rifatto la prova per mutazione **da zero, con i suoi mutanti** e
ne ha trovati **3 che i miei 15 non coprivano**. Tutti e tre reali:

- **`extra` di `filtraDocumenti` non era esercitato da nessun test**: è il
  **filtro di sede**. Il mutante che lo ignora sopravviveva — in modalità catena
  un cliente avrebbe visto le fatture di tutte le sedi. Aggiunto
  `test_il_predicato_extra_filtra_la_sede`; il mutante ora muore.
- **`if (!key) continue` in `elencaFornitori`** non era coperto (nessuna fixture
  con fornitore vuoto): produceva una voce fantasma nel menu filtro. Coperto,
  mutante ucciso.
- **Il test sul locale non provava ciò che dichiarava.** La docstring diceva di
  catturare la rimozione di `"it"` da `localeCompare`. **Falso, misurato**:
  l'ordine accent-insensitive è il default UCA di Unicode — `undefined`, `it`,
  `en-US`, `sv-SE`, `de-DE` danno tutti `[Àlfa, Mario, Zeta]`. Il mutante
  **sopravvive** ed è ora dichiarato tale nella docstring, invece di essere
  coperto a parole. È lo stesso errore che il metodo vieta: un test che misura
  il proprio pattern, non il codice.

**Bilancio mutazione aggiornato: 18 mutanti, 17 uccisi, 1 sopravvissuto e
dichiarato.**

Corretti inoltre, sempre su segnalazione del reviewer:

- **Regressione O(n·m) reale**, non teorica: `filtroFornitori` era un `Set`
  (`.has` O(1)) ed era diventato un array (`.includes` O(m)) su liste che al
  worker arrivano **senza paginazione** (2.001 documenti non pagati su un
  cliente vero). Benchmark del reviewer: **199 ms** per 200 iterazioni a
  5.000×300. Il contratto pubblico resta l'array (i test lo serializzano), ma
  `filtraDocumenti`/`aggregaPerSede` costruiscono il `Set` **una volta** e lo
  passano a `matchDocumento`. Ri-misurato: **23 ms**.
- **Variabile morta** `scad` in `DocumentoRow`, rimasta dopo il passaggio a
  `statoDocumento` (`tsc` non la segnala: `noUnusedLocals` non è attivo).
- **`AUDIT_COPERTURA.md`**: due occorrenze di `50.958` non ri-misurate (di cui
  una nella nota che *insegna come misurare*), e il riepilogo frontend che
  sommava `17+31+14 = 62%` — le tre voci misuravano grandezze diverse e il 38%
  restante non stava da nessuna parte. Riscritto su un denominatore solo.

Il reviewer ha anche **verificato indipendentemente** che l'inversione dei rami
in `statoDocumento` è equivalente (il mutante che ripristina l'ordine del client
sopravvive: `parseLocalDate` ritorna `null`, mai `Invalid Date`), e che la
rimozione di `matchFiltriComuniRef` **corregge** un difetto invece di
introdurlo.

### Non fatto, e dichiarato

- **Il mutante sul locale `"it"` sopravvive** (vedi sopra): l'ordinamento
  accent-insensitive non è una specificità italiana. Dichiarato, non coperto.
- **`daysToCestino`** (soglia 30gg del cestino) e **`DocumentoRow.isOverdue`**
  (bordo rosso) **non sono stati estratti**: sono label e decorazione, non
  decidono inclusioni né importi. `isOverdue` è però stato **riscritto come
  `statoDocumento(doc) === "Scaduta"`** per non lasciare in giro una quarta
  definizione di «scaduto» a deriva libera. Sono esclusioni motivate, non
  dimenticanze.
- **Il rendering resta non testato** (2.119 righe): serve un runner di
  componenti, che il punto 9 ha escluso per ragione strutturale
  (`deploy-vercel.yml` scatta su `apps/web/**`).
- **`dependencies=[...]` a livello di `APIRouter`** — invariata: tocca 238
  endpoint, va aperta come dimensione a sé con la sua finestra di deploy.
