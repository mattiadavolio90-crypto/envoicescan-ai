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
(2.210 → **2.118** righe il client, 245 → **442** il lib; misurati a HEAD
a chiusura, non al commit intermedio):

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

**Bilancio mutazione aggiornato: 20 mutanti, 19 uccisi, 1 sopravvissuto e
dichiarato** (il locale `"it"`).

La 2ª passata del reviewer ha trovato un ultimo buco **comportamentale**: la
guardia `chiavi.size > 0` introdotta con l'ottimizzazione del Set non era
raggiunta da nessun test. Oggi è irraggiungibile (entrambi i chiamanti passano
un Set coerente), ma il 4° parametro di `matchDocumento` è **pubblico di
firma**: il primo che lo chiamasse da fuori con un Set vuoto avrebbe visto la
lista svuotarsi. Coperto da `test_chiavi_precalcolate_coerenti_con_la_lista`,
che pinna anche l'equivalenza fra Set coerente e lista (l'ottimizzazione non
cambia cosa si vede). Mutanti M18/M19 uccisi.

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

### Il contatore: tre correzioni in cascata, tutte misurate

La sessione parallela ha chiuso il buco delle «1.970 righe non attribuite» che
avevo trovato, ma **aggiungendo una riga `(mobile)/` già presente**: l'area
finiva contata due volte (una 🟠 32%, una 🔴 con 0 lette) e la tabella sommava
**53.398** su 51.063 reali. Il buco era diventato un eccesso.

Rimosso il duplicato e ri-misurate le aree una per una: la riga «altre 4 aree
~2.600» ne elencava 4 su 7 e valeva in realtà **4.250** (dashboard 1.749 ·
impostazioni 806 · agenda 693 · notifiche 339 · assistenza 292 · style-guide
256 · file diretti 115). Corretti anche `scadenziario` (2.211, non 2.212) e il
backend (**55.450**, non 55.451).

**Ora la colonna «Totale area» somma esattamente 51.063**, cioè `git archive
HEAD` — ogni riga del frontend sta in una riga della tabella. Verificato
sommando la tabella, non fidandosi della frase che dichiarava la copertura.

> Lezione, già scritta in cima al contatore: **una cifra si ri-misura contro
> HEAD**, e una tabella che dichiara «copre tutto» va **sommata** prima di
> crederle. In una sola giornata lo stesso file ha sbagliato in tre modi
> diversi: righe mancanti, righe contate due volte, e una frase che affermava
> una copertura che la somma smentiva.

### Non fatto, e dichiarato

- **Il mutante sul locale `"it"` sopravvive** (vedi sopra): l'ordinamento
  accent-insensitive non è una specificità italiana. Dichiarato, non coperto.
- **`daysToCestino`** (soglia 30gg del cestino) e **`DocumentoRow.isOverdue`**
  (bordo rosso) **non sono stati estratti**: sono label e decorazione, non
  decidono inclusioni né importi. `isOverdue` è però stato **riscritto come
  `statoDocumento(doc) === "Scaduta"`** per non lasciare in giro una quarta
  definizione di «scaduto» a deriva libera. Sono esclusioni motivate, non
  dimenticanze.
- **Il rendering resta non testato** (2.118 righe): serve un runner di
  componenti, che il punto 9 ha escluso per ragione strutturale
  (`deploy-vercel.yml` scatta su `apps/web/**`).
- **`dependencies=[...]` a livello di `APIRouter`** — invariata: tocca 238
  endpoint, va aperta come dimensione a sé con la sua finestra di deploy.

---

## 31/8/2026 — dimensione `(app)/margini/` chiusa (3ª sessione della giornata)

**Perché questa area e non un'altra:** priorità per **esposizione, non per
dimensione**. `margini/` produce il MOL, che è una regola di dominio critica, e
i numeri che il cliente usa per decidere i prezzi.

### Il perimetro, misurato — e cosa NON copre

`(app)/margini/` sono **4.709 righe**. I test ne raggiungono **~400**: la logica
pura. Le altre ~4.300 sono JSX, hook React, stato, recharts — `esegui_ts` non sa
montare React, quindi sono irraggiungibili **per costruzione**, non per pigrizia.
Va scritto qui perché il contatore dice «margini 📖 100%» e quel 100% significa
*«ogni riga è stata letta e la logica pura è provata per mutazione»*, non *«ogni
riga ha un test»*.

### Le ipotesi del prompt di sessione, ridimensionate dai dati veri

Il prompt indicava tre piste. Misurate sul DB di produzione, due si sono
sgonfiate:

- **L'esclusione «Da Classificare» non è nel frontend**: 0 occorrenze in
  `(app)/margini/` e in `app/api/`. È backend — 9 copie (8 letterali, 1 sola con
  la costante e `.strip()`, `fastapi_worker.py:8004`) più 2 RPC SQL.
- **Sui dati veri la divergenza è teorica**: 172 righe `Da Classificare` con la
  grafia esatta, **0** con spazi, **0** col refuso `Da Clasificare`, **0** con
  `NOTE E DICITURE` senza emoji. Le 74 righe `📝 NOTE E DICITURE` hanno **tutte
  `totale_riga = 0`**: il guardrail regge.
- **Il MOL non si calcola nel frontend**: arriva dal worker
  (`services/routers/margini.py:254-255`, `:1174`). In `margini/` c'è solo
  ri-derivazione per la colonna Media.

### L'esposizione vera, che il prompt non aveva visto

`fetchNettoMese` (`periodi.ts:127-156`) — il gate «l'override mensile vince sui
giornalieri». Misurato su produzione:

| mese | netto override (usato) | netto giornaliero (scartato) |
|---|---:|---:|
| giugno 2026 | **73.322,73 €** | 3.227,27 € |
| maggio 2026 | 80.550 € | 80.551 € |

**70.095,46 € su un solo mese** dipendevano da quel ramo, che non aveva un test.

### Cosa è stato fatto

**6 fasi, 183 test nuovi su 4 file, 65 mutanti — 65 uccisi, 0 sopravvissuti**,
più 9 controprove (mutanti equivalenti) tutte correttamente sopravvissute.

| Fase | Oggetto | File di test | Mutanti |
|---|---|---|---|
| A | `fetchNettoMese` | `..._netto_mese_frontend.py` (15 test) | 8/8 |
| B | `periodi.ts` sincrono (periodi, scorporo, label) | `..._periodi_frontend.py` (109 test) | 15/15 |
| C | aggregati coperti + i 2 filtri del componente | `..._aggregati_frontend.py` | 9/9 |
| D | `pivotMedia`, `pctIncidenza`, `rowVal`, le 3 `derive` | idem (53 test in tutto per C+D+E) | 17/17 |
| E | `buildMesiList` | idem | 10/10 |
| F | equivalenza IVA | `..._iva_equivalenza_frontend.py` (6 test) | 6/6 |

I test di C, D ed E stanno in un file solo (`test_margini_aggregati_frontend.py`,
53 test) perché coprono un solo modulo: `lib/margini-aggregati.ts`.

**~275 righe di logica pura estratte** dai 4 componenti `.tsx` in
`lib/margini-aggregati.ts` (nuovo, 126 righe), **byte per byte, senza
correzioni**. Il diff dei componenti contiene **solo import e rimozioni**:
verificato riga per riga, nessuna logica cambiata. `buildMesiList` era duplicata
identica (`diff` vuoto) in `analisi-tab.tsx` e `carica-ricavi-dialog.tsx`: ora è
una sola.

### La tecnica dello stub `fetch`, riusabile

`helpers_ts.py` stubba `globalThis.fetch` a `throw` nel prologo (ban di rete). Per
testare `fetchNettoMese` lo si **riassegna dentro l'espressione node**, dopo il
prologo — nessuna modifica a `helpers_ts.py`, nessun effetto sugli altri test
(ogni `esegui_ts` è un processo node separato). Documentata nel docstring di
`tests/test_margini_netto_mese_frontend.py`.

**Il dettaglio che è costato un mutante**: lo stub deve servire `json` **anche
quando `ok` è false**. Una 500 di FastAPI ha un body JSON valido
(`{"detail": ...}`); uno stub che su `ok:false` non espone `json` è irrealistico,
e lasciava vivo il mutante che rimuove il controllo su `r.ok` — sopravviveva a
12 test su 12. Trovato dal `code-reviewer`, non dai miei mutanti.

### Due comportamenti fotografati, non corretti (decisione di Mattia)

**1. L'asimmetria della Media Ricavi netti** (`coperti-tab.tsx`, ora nel modulo).
`mesiVisibili` tiene i mesi con `coperti>0 OR ricavi>0`; `numMesiAttivi` conta
solo quelli con `coperti>0`. `aggregaRicavi` somma i **primi** ma divide per i
**secondi**: un mese con ricavi e senza coperti gonfia il numeratore senza
toccare il denominatore, e la media esce sovrastimata. La label dice «Media sui N
mesi con coperti» anche sulla riga Ricavi.

Misurato: **0 sedi su 8** oggi nel caso misto. Ma **si arma da solo** — le 66
righe `source='manuale'` hanno tutte `coperti` NULL. Il test lo fotografa con un
assert che dice esplicitamente cosa fare se diventa rosso.

**2. I 4 letterali IVA** in `carica-ricavi-dialog.tsx:451,452,477,478` (`/1.10`,
`/1.22`) invece di `scorporoNetto` — nonostante il commento del codice dichiari
che lo scorporo è «tenuto in un solo punto per evitare divergenze». Delta
economico oggi **zero**: i valori coincidono. Il test è una rete più larga del
fix — intercetta la divergenza **futura**, cioè il giorno in cui qualcuno cambia
un'aliquota in un posto solo e l'utente vede due totali diversi.

### Il mutante che ha corretto una mia fixture sbagliata

Il `?? 0` sulle quote di riparto: il mio test passava `quote_riparto_fb: None`, e
il mutante che toglie il coalesce **sopravviveva**. Non era un test debole nel
senso ovvio — in JavaScript `32 + null === 32`, quindi su `null` il mutante è
**equivalente**. Il caso che il `?? 0` protegge davvero è il campo **assente**:
`32 + undefined` fa `NaN`, e da lì ogni totale della colonna diventa «NaN €».
Un worker che omette la chiave invece di mandarla `null` è lo scenario
realistico. Il test ora prova entrambi, e il mutante muore.

> Lezione: **un mutante sopravvissuto va capito, non zittito.** Qui la risposta
> non era «aggiungi un assert», era «la fixture misurava il caso sbagliato».

### Il contatore: la cifra girava sbagliata da almeno due cicli

Ri-sommando la colonna a HEAD — come il contatore stesso impone — il totale non
tornava: **51.894** da `git archive`, contro i 51.063 dichiarati. Solo 40 righe
erano mie. Le altre 791 erano due errori vecchi:

- la voce `hooks/`+`proxy.ts`+file diretti valeva **622**, non 312: i file
  diretti in `app/` sono **495**, non 185 (`globals.css` da solo ne fa 296);
- `app/fonts/` contiene **due `.woff` binari** che `wc -l` conta come **481
  "righe"** pur non essendo codice.

Totale corretto: **51.413** (= 51.894 − 481 dei font), e la colonna ora somma
esattamente. A cascata: TOTALE APP **110.419**, letto **39.155 (35%)**, mai
guardato **53.614 (49%)** — le tre righe ricalcolate, con la somma verificata a
zero di scarto.

> È la **quarta** volta in tre giorni che questo file mente. Le prime tre erano
> righe mancanti, righe contate due volte, una frase smentita dalla somma.
> Questa era una voce ferma da due cicli più due file binari contati come
> sorgente. Il pattern non è la distrazione: è che **nessun test controlla
> l'aritmetica di un `.md`** — `check_documentazione.py` verifica i simboli, non
> le somme.

### Non fatto, e dichiarato — va in coda con la sua misura

- **Il mobile riscrive a mano il gate mensile.**
  `(mobile)/m/diario/mobile-incassi.tsx:215-235` importa da `periodi.ts` solo
  `scorporoNetto` e il tipo `NettoMese`, poi **riscrive** la scelta
  override-vs-giornalieri **senza la distinzione null/0**
  (`nettoAutorevole?.netto ?? risposta?.totale_netto ?? 0`). È esattamente il
  difetto che `fetchNettoMese` protegge, in un file che non lo chiama. Non
  toccato: è `(mobile)/`, area separata, fuori da questa dimensione.
- **Le 9 copie backend del filtro `Da Classificare`** + le NOTE senza emoji in
  `margine_service.py` e nelle 2 RPC: **0 righe attive** sui dati veri, e il fix
  richiede una migration su 7 account. Fuori dimensione (§5bis vieta gli
  strascichi).
- **I 4 letterali IVA**: remediation separata, da proporre.
- **Il rendering resta non testato** (~4.300 righe): serve un runner di
  componenti, escluso per ragione strutturale (`deploy-vercel.yml` scatta su
  `apps/web/**`, un runner lì farebbe partire un deploy di produzione a ogni
  merge di un test).

### La review: 40 mutanti indipendenti, e un difetto nell'harness del reviewer

Il `code-reviewer` ha rifatto la mutazione con **40 mutanti propri**: 39 uccisi,
1 equivalente. Ha inoltre verificato l'estrazione **meccanicamente** (`diff` fra
`git show 04ad48f:<file>` e il modulo nuovo): identiche byte per byte, unica
differenza la firma `rowVal(row: RowDef)` → `RowLike`, che è un allargamento di
tipo senza effetto a runtime.

**Il mutante più significativo è il suo R22**: ha mutato `aggregaRicavi` in modo
da *correggere* l'asimmetria, e 4 test sono diventati rossi. La fotografia è
quindi vincolante, non decorativa.

Il suo unico sopravvissuto (`?? 0` → `?? 1` in `aggregaCoperti`) è **equivalente
per davvero**, e l'ho verificato invece di crederci: il `filter(m.coperti != null)`
a monte cattura sia `null` sia `undefined`, quindi il `??` non scatta mai. È il
caso opposto a quello delle `DERIVE`, dove il filtro non c'è e infatti lì il
mutante muore.

> Nota metodologica che vale più del risultato: **il reviewer ha trovato un bug
> nel proprio harness**, non nel codice. Passava `--timeout=300` senza
> `pytest-timeout` installato, pytest usciva con **rc=4** (usage error), e lui
> leggeva `rc != 0` come «mutante ucciso». *Tutti* i mutanti risultavano morti,
> controprove incluse — ed è stata la contraddizione (una controprova su un
> commento che «uccide») a rivelarlo.
>
> **Un harness di mutazione va validato sui due lati**: un mutante palese deve
> morire *e* una controprova deve sopravvivere. La sola prova di sanità non
> basta, perché può «morire» per il motivo sbagliato. E `rc=1` (test rosso) va
> distinto da `rc≥2` (errore d'uso).

Due segnalazioni non bloccanti sono state chiuse subito: `DERIVE` era un
`Record` esportato **mutabile** (ora `Object.freeze` + `Readonly`), e il regex
del test IVA era sensibile alla spaziatura — `/1.10` senza spazio gli sfuggiva,
e il test sarebbe diventato rosso per una riformattazione invece che per un
cambio di sostanza (ora `/\s*1\.`).

Resta aperta, in coda: **`lib/` importa da `app/`** (`margini-aggregati` prende
`MESI_NOMI_SHORT` da `app/(app)/margini/periodi`). È un'inversione di
dipendenza, seconda occorrenza del pattern (`lib/demo-data.ts` fa già lo
stesso). Non girata ora: toccherebbe `periodi.ts`, che è importato anche da
`page.tsx` (Server Component) ed è appena stato coperto da 109 test — cambio a
basso valore fuori dal perimetro deciso. Da fare quando si tocca `periodi.ts`
per altro, spostando in `lib/` le costanti pure (`MESI_NOMI_*`, `IVA_DIVISORE_*`).

**Non verificato da nessuno:** le cifre DB del verbale (0 sedi su 8 nel caso
misto, 66 righe `source='manuale'` con `coperti` NULL) le ho misurate io in
ricognizione; la query read-only del reviewer è stata bloccata dal permission
system, quindi non ha potuto confermarle. Dichiarate come misurate una volta
sola.

---

## 1/9/2026 — dimensione `(app)/catena/` aperta e chiusa (3 file su 6)

Prima passata in assoluto sull'area: fino a ieri `(app)/catena/` era **l'unica
area frontend grande che nessuna passata avesse mai toccato** — non poco coperta,
zero.

### Il perimetro, misurato — e cosa NON copre

Coperti 3 file su 6 (1.360 righe delle 3.127), scelti perché contengono tutta
l'aggregazione multi-sede: `finestra-margini-coperti.tsx` (522),
`sintesi-catena.tsx` (559), `finestra-spesa-pv.tsx` (279).

**Non copre**: `gruppo-tag-section.tsx` (721), `finestra-costi-gruppo.tsx` (553),
`config-assistente-catena.tsx` (202), `card-segnali.tsx` (110), le 3 `page.tsx`
(181) — **1.767 righe**, in coda qui sotto con la loro misura. La scelta di
fermarsi a metà area è di Mattia: meglio 3 file chiusi davvero (§5bis) che 6
aperti a metà.

E **copre la logica pura, non il rendering**: `esegui_ts` non monta React. Un
componente può usare male una funzione corretta e i test non se ne accorgono.

### Le ipotesi del prompt, verificate sul DB prima di crederci

Il prompt imponeva di non ereditare le sue stesse ipotesi. Su tre, **due erano
sbagliate**:

- ❌ **La sparkline rossa su MOL negativo NON è armata.** Sembrava esposta su
  Offside, che ha MOL negativo in tutti e 8 i mesi 2026 (da −74.031 a −19.221:
  sta risalendo, e la linea sarebbe rossa). Ma `services/routers/gruppo.py:873`
  tiene solo i mesi con `netto_per_mese > 0`, e con `tot_lordo <= 0` il livello è
  `"nessuno"`, che a `sintesi-catena.tsx:318` non renderizza affatto la
  sparkline. Difetto reale nel codice, **non raggiungibile da nessun cliente**.
- ❌ **Zero letterali IVA nell'area** (0 occorrenze di `1.10`/`1.22`): lo
  scorporo è interamente nel worker. L'IVA compare solo come testo.
- ✅ La logica di confronto era tutta inline nei `.tsx`, e `lib/gruppo.ts` è un
  client del worker (`cache()` + `fetch`), non il posto dove estrarre.

### L'esposizione vera, misurata sul DB

**Solo 2 account su 7** superano `num_pv >= 2` e vedono la pagina — ma sono i due
più grandi del parco:

| Account | Sedi | Righe fattura | Costi aggregati |
|---|---:|---:|---:|
| Sushiland | 4 | 29.911 | 3.450.581 € |
| Offside / Overtime | 2 + 1 tecnica | 3.969 | 401.172 € |
| **Totale** | | **33.880** | **3.851.753 €** |

La sede tecnica "Costi comuni di gruppo" è esclusa correttamente lato backend
(`gruppo.py:669`): non è una fonte di doppio conteggio.

### Cosa è stato fatto

- **`apps/web/src/lib/catena-confronti.ts`** (284 righe): 15 funzioni + 3
  costanti soglia, estratte **byte per byte**. Gate di fedeltà superato — il
  diff dei 3 componenti contiene **solo import e chiamate**, zero logica
  (−120 righe, +37).
- **`tests/test_catena_confronti_frontend.py`** (81 test).
- **Mutazione: 55 mutanti, 52 uccisi, 3 sopravvissuti — tutti e 3 controprove
  attese.** Nessun mutante di difetto reale è sopravvissuto. (Il primo giro era
  51/48: i 4 in più vengono dal `code-reviewer`, vedi sotto.)

### La trappola dell'`import type`, che ha rotto l'harness al primo colpo

`import { type X } from "@/lib/gruppo"` **non basta**: la forma lascia in piedi
la import statement, node carica `lib/gruppo.ts` → `./worker` (import relativo
che il resolve hook non riscrive) e l'harness muore con `ERR_MODULE_NOT_FOUND`.
Serve `import type { X } from ...`, che sparisce del tutto allo strip dei tipi.
Vale per **ogni** futura estrazione che tocchi un tipo definito in un modulo con
side-effect.

### I due mutanti che hanno insegnato qualcosa

- **M11** (`-Infinity` → `+Infinity` in `ordinaRighe`) sopravviveva a una
  fixture con **un solo** null: la costante non veniva mai confrontata con se
  stessa, quindi il segno non cambiava nulla. Serve un secondo null, dove
  `-Inf - (-Inf) = NaN` e `sort` lascia la coppia com'è. **Era la fixture a
  essere povera, non l'assert a mancare** — stessa lezione del `?? 0` del 31/8.
- **CTRL-3** (`if (v == null) return ""` in `cellTone`) è **genuinamente
  equivalente**: `calcolaExtremes` filtra già i null, quindi best/worst sono
  sempre numeri e `null === <numero>` è già false. Nessuna fixture può ucciderlo.
  Documentato nel sorgente invece di forzare un test che lo zittisse.

### Otto comportamenti fotografati, non corretti (decisione di Mattia)

Ognuno ha un test che lo asserisce **sbagliato**, col perché nel corpo:

1. **`ordinaRighe`**: i null vanno in coda in `desc` ma **in testa** in `asc`
   (una sola coalescenza per due direzioni).
2. **`calcolaSparkline`**: con `primo <= 0` la linea è **rossa "in calo"** anche
   su un MOL che risale. Non raggiungibile oggi (vedi sopra), si arma se il
   filtro `netto > 0` del worker cambia.
3. **`tintConti`**: `livello_dati ?? "completo"` sceglie sull'assenza del campo
   l'ipotesi **più ottimista** — un worker che lo omettesse certificherebbe in
   verde un MOL non verificato. Il tipo lo dichiara non-nullable: TypeScript non
   vedrebbe mai il caso.
4. **`incidenzaPct`**: con `grand_total = 0` restituisce `0` → a schermo "0,0%"
   dove il dato non esiste ("—" sarebbe onesto).
5. **`pvPiuCaro`**: a parità di importo vince il **primo** nell'ordine di `pv` —
   tie-break implicito che dipende da come il worker ordina le sedi.
6. **`calcolaHeatMax`**: `?? 0` appiattisce null su 0.
7. **Due heatmap divergenti**: `heatStyle` (0.05/0.30) e `cellStyle`
   (0.06/0.34). Unificarle cambierebbe i colori a schermo: restano due funzioni
   e il test **dichiara** la divergenza.
8. **`euro2` omonime con output diverso**: `finestra-margini-coperti.tsx:376`
   usa `toFixed` (niente separatore migliaia), `gruppo-tag-section.tsx:29` usa
   `Intl`. Fuori perimetro, non toccate.

### Non fatto, e dichiarato — va in coda con la sua misura

- **I 3 file di `catena/` non aperti: 1.767 righe.** `gruppo-tag-section.tsx`
  (721) è il più grande e contiene già una delega a `lib/tag-candidati.ts`:
  è il candidato naturale della prossima passata sull'area.
- **7 copie locali di `euro`/`pct`/`num` e 3 di `MESI`** nell'area, mentre
  `lib/format.ts` è "FONTE UNICA" e `lib/mesi.ts` **cita catena** fra i file da
  centralizzare. Non deduplicate: sostituirle è un cambio di comportamento se
  l'output diverge (le due `euro2` lo dimostrano), e serve prima un test di
  equivalenza byte per byte.
- **`parseImportoIt`** (`finestra-costi-gruppo.tsx:354`): `replace(",", ".")`
  **non globale** → `"1.234,56"` diventa `NaN`. Bug vero, fuori perimetro.
- **Il rendering resta non testato**, qui come ovunque: serve un runner di
  componenti, escluso per ragione strutturale (un runner in `apps/web/` farebbe
  partire un deploy Vercel a ogni merge di un test).

### La review: due lacune vere, e un rilievo che non reggeva

Il `code-reviewer` ha costruito 45 mutanti indipendenti e ne ha trovati **4 che
il mio catalogo non copriva**. Due lacune reali, chiuse con 2 test (83 in totale):

- **`ordinaRighe` con margini negativi.** Un `?? 0` asimmetrico al posto di
  `-Infinity` fa sì che un PV **senza dato** scavalchi un PV con margine
  **negativo**: a schermo il locale che non ha caricato i costi appare «meno
  peggio» di quello che sta perdendo soldi. Le mie fixture non lo vedevano
  perché usavano solo valori positivi, dove `0` e `-Infinity` sono
  indistinguibili — perdono entrambi contro tutto. Un margine negativo qui non è
  teorico: Offside ha MOL negativo su tutti e 8 i mesi 2026.
- **Geometria assoluta della sparkline.** Il mio test verificava che `cx`/`cy`
  combaciassero con la fine di `d`, cioè la *coerenza interna*: un `d` sbagliato
  in modo coerente passava. Sopravvivevano PAD ignorato, **asse y capovolto**
  (grafico ribaltato) e `M` iniziale perso (path SVG invalido). Ora le coordinate
  sono asserite una per una.

**Un rilievo non reggeva, ed è stato verificato prima di accettarlo.** La prova
d'osservabilità allegata a `R04` (`[neg:-5, senza:null]` darebbe ordini diversi)
è **falsa**: su quella fixture mutante e originale danno lo stesso risultato in
entrambe le direzioni, misurato. Il difetto è reale ma si vede solo con un null
**fra** un positivo e un negativo. La conclusione del reviewer era giusta, la sua
dimostrazione no — ed è la ragione per cui un rilievo si riproduce prima di
scriverlo a verbale.

---

## 1/9/2026 (2ª passata) — `(app)/catena/` chiusa: gli altri 3 file

Seconda passata nella stessa giornata, sulla metà dell'area che la prima aveva
dichiarato in coda. Con questa, tutti e 6 i file di logica di `catena/` sono
passati sotto test.

### Il perimetro, misurato — e cosa NON copre

Coperti `gruppo-tag-section.tsx` (721→717), `finestra-costi-gruppo.tsx`
(553→549), `config-assistente-catena.tsx` (202→203). Estratte 22 funzioni in due
moduli nuovi: `lib/catena-tag.ts` (229) e `lib/catena-costi-gruppo.ts` (182).

**Non copre**, e va detto invece di lasciarlo intendere:

- **`card-segnali.tsx` (110 righe): zero copertura, per decisione.** È fetch +
  JSX; l'unica cosa estraibile è la mappa `ICONA`, che punta a componenti
  `lucide-react` e non entra in `lib/` senza cambiare forma. Resta il duplicato
  byte-per-byte con `(mobile)/m/briefing/mobile-catena.tsx:7-12`.
- **Le 3 `page.tsx`/`loading.tsx` (181 righe)**: zero logica pura.
- **Il rendering, ovunque.** `esegui_ts` non monta React: un componente può
  chiamare male una funzione corretta e nessun test se ne accorge. «Area chiusa»
  significa *logica pura coperta*, non *ogni riga testata*.

Copertura `catena/`: **2.746 su 3.037 righe (~90%)**.

### Le ipotesi del piano, verificate prima di crederci

Su cinque verificate, **tre erano sbagliate** — e due lo erano in modo che
avrebbe fatto sbagliare il lavoro:

1. **`percentualeBarra` non esiste.** Il prompt la dava come funzione duplicata 3
   volte; sono 3 espressioni inline, e la terza ha una formula diversa.
2. **`replaceAll` NON è il fix del bug dell'importo.** Il piano lo dava per
   scontato («deve uccidere»). Il mutante è invece **sopravvissuto**, e la
   verifica ha mostrato perché: a rompere `"1.234,56"` è il **punto** delle
   migliaia, non la seconda virgola — `replace` e `replaceAll` sono
   indistinguibili su ogni input realistico. Il fix vero è
   `Number(t.replace(/\./g, "").replace(",", "."))`. Se la sessione del fix
   avesse ereditato l'ipotesi, avrebbe "corretto" il bug lasciandolo intatto.
3. **L'anomalia `spesa === 0` su float è teorica, non reale.** `routers/gruppo.py:2242`
   manda `round(spesa, 2)`: un residuo di 0.00000001 non può arrivare al client.
   Resta una proprietà del backend, non della funzione — annotata come tale.

Verificate e confermate: l'import incrociato fra due moduli `lib/` sotto test
funziona (provato con un modulo sonda **prima** di scriverci sopra 60 test), e
`MESI` è condivisa fra la `<select>` e `MESI[mese-1]`, quindi estrarre `nomeMese`
avrebbe **duplicato** una lista di 12 stringhe già ridefinita 10 volte nel repo.
Non estratta.

### Il rischio di questa passata, e come è stato controllato

Diverso da quello della prima: qui quasi tutte le funzioni producono stringhe che
finiscono in uno `style` o in un `className`. Un "miglioramento" scritto mentre
si copia (un `Math.round` che prima non c'era) supera `tsc`, supera i test —
scritti *dopo*, sul codice già estratto — e supera anche il gate del diff, perché
nel `.tsx` resta solo una chiamata.

**Il gate `git diff | grep '^+'` dimostra che la logica è uscita dal `.tsx`, non
che sia arrivata intatta in `lib/`.** Per le due regex di slug, dove riscrivere
"meglio" è più tentante, il controllo vero è stato un oracolo: l'espressione
originale presa da `git show HEAD:` valutata contro il modulo nuovo su **236
input avversi** (unicode, emoji, doppi spazi, punteggiatura in testa e coda).
Zero divergenze.

### Il bilancio di mutazione

**52 mutanti, 48 uccisi, 4 sopravvissuti** — tutti e quattro esaminati, nessuno
zittito con un test costruito apposta.

L'harness è stato validato sui **tre** lati prima di usarlo: un mutante palese
(`return "999999%"`) muore, una controprova innocua (un commento cambiato)
sopravvive, e un pattern inesistente **ferma** il giro invece di produrre un
falso sopravvissuto. `pytest-timeout` resta non installato: `rc>=2` è trattato
come errore d'uso, mai come mutante ucciso.

I sopravvissuti, con il motivo:

- **`perPv ?? []` → `perPv || []`** — equivalenza vera: divergono solo su `0`,
  `""`, `false`, che il tipo esclude e su cui `.map` fallirebbe comunque.
- **`replace` → `replaceAll`** — equivalenza vera, ed è il rilievo più utile del
  giro (vedi sopra). Documentata nel sorgente perché la prossima sessione non
  ripeta l'errore del piano.
- **`n === 1` → `n <= 1`** nel conteggio costi — divergono solo per `0 < n < 1`,
  e `n` è un conteggio di righe.
- **`nonCorreggibili === costi` → `>=`** — i non correggibili sono un
  sottoinsieme dei costi, non possono superarli.

Gli ultimi due si ucciderebbero solo con fixture che il backend non può produrre:
un test così misurerebbe se stesso, non il codice. Sono annotati nel sorgente,
come fu fatto per M18 di `cellTone`.

**Due mutanti che sembravano equivalenti e non lo erano.** `=== minPrezzo` →
`<= minPrezzo` e `=== maxPrezzo` → `>= maxPrezzo` erano previsti dal piano come
controprove destinate a sopravvivere. Sono sopravvissuti davvero — ma per una
**fixture mancante**, non per equivalenza: in JS `null` si coerce a `0` con `>=`
e `<=` ma non con `===`, quindi su un tag sotto la soglia di confronto (gli
estremi sono `null`) il mutante colorerebbe di rosso **tutti** i PV. Mancava il
caso «prezzo reale con estremi nulli», cioè il tag con un solo punto vendita: il
più comune. Aggiunto, i due mutanti ora muoiono.

### Anomalie fotografate, non corrette

Nessuna corretta: decisione confermata da Mattia a inizio sessione. Le nuove:

| Dove | Cosa |
|---|---|
| `classePrezzo` | con prezzi uniformi (min === max) ogni PV prende **entrambe** le classi: è insieme il più caro e il più economico, e a schermo vince il rosso. `cellTone` risolve lo stesso caso con la guardia `best !== worst`, 15 righe più in là |
| `larghezzaBarra` | su spesa negativa (netta delle note di credito) produce `"-30%"`: la barra sparisce senza distinguersi da una spesa nulla |
| `altezzaBarraTrend` | il pavimento `Math.max(4, …)` si applica anche ai negativi: un mese chiuso in perdita si disegna come una barra positiva bassa |
| `nomeFileExport` | lo slug del nome non ha il trim di coda che ha quello del periodo: `"tag_pesce-_gennaio-2026.xlsx"` |
| `righeExportPv` | `Math.round` arrotonda i `.5` verso +∞, non lontano da zero: l'export di una nota di credito può differire di un centesimo da quanto darebbe la stessa cifra col segno opposto. **Trovata scrivendo i test, non prevista dal piano** |
| `parseImportoManuale` | `"1.234,56"` → NaN. Contenuto da `importoValido`: è un errore di **messaggio**, non di dato — il NaN non arriva al backend |
| `esitoCorrezioneCategoria` | `join(" e ")` su 3+ sedi produce «vale per A e B e C» |
| `segnaliDisattivati` / `pvEsclusi` | **la più seria**: lista vuota nel POST significa «niente escluso» per il backend, ma è anche lo stato iniziale dopo un load fallito. Difesa solo dal `disabled` del pulsante — una guardia di interfaccia su una regola di dati |

Su quest'ultima è stata presa una decisione esplicita: **non** si è scritta una
`configCaricata()` da chiamare nel `disabled`. Sarebbe stato codice nuovo in una
passata che ha per regola di non correggere, e avrebbe cambiato il comportamento
su uno stato oggi abilitato (un backend che risponde `200 {}`). Al suo posto,
`test_fotografa_liste_vuote_producono_liste_vuote` tiene il buco visibile.

**Nota metodologica sullo stesso punto**: su lista vuota nessuna mutazione di
quelle due funzioni è osservabile — qualunque filtro su `[]` dà `[]`. È un
**mutante impossibile**, non un mutante sopravvissuto, e nel bilancio non va
contato fra i secondi.

### Il contatore

`lib/` +411, `(app)/catena/` −7: delta **+404**. Un'estrazione non è a somma zero
e stavolta lo è ancora meno del solito, perché i due moduli portano i commenti
che spiegano le otto anomalie. Chi si aspetta il pareggio crede di aver sbagliato
la misura: è il contrario.

### Non fatto, e dichiarato — va in coda con la sua misura

- **`card-segnali.tsx` (110)** e il suo duplicato `ICONA` con `mobile-catena.tsx`.
- **Il fix di `parseImportoManuale`**, con la ricetta ora verificata, su **~25
  punti** dell'app. Dimensione a sé, con la sua finestra di deploy.
- **La guardia sulle liste vuote** di `config-assistente-catena`.
- **Le 7 copie di `euro`/`pct`/`num` e le 10 di `MESI`** — invariate: nessuna
  funzione estratta in questa passata formatta, di proposito, perché unificarle
  cambia output a schermo (`num` diverge davvero sui decimali).
- **Le 8 anomalie della prima passata**, ancora aperte.

### La review: una lacuna vera, trovata dove avevo generalizzato una conclusione

Il `code-reviewer` ha rifatto la mutazione con **59 mutanti suoi**, indipendenti,
uccidendone 54. Quattro dei cinque sopravvissuti sono le equivalenze già
dichiarate qui sopra, ri-provate in autonomia: tengono tutte.

Il quinto era mio, e non era nel mio catalogo. In `righeExportPv`,
`p.prezzo_medio ?? "—"` → `|| "—"` sopravviveva a tutti e 110 i test: le fixture
usavano solo `9.87` e `null`, mai **`0`**, che è l'unico valore su cui i due
operatori divergono. Ed è raggiungibile con dati veri —
`routers/gruppo.py:2250` calcola `round(spesa_pv / qta, 2)` quando la quantità è
positiva, e su un articolo in omaggio il risultato è `0.0`. Con `||` il cliente
avrebbe letto `—` («prezzo non disponibile») al posto di `0` («gratis»).

**La lezione non è la fixture mancante, è come è nata.** Poche ore prima avevo
scritto, nel commento di `estremiPrezzo`, che il `??` lì è equivalente a `||`
perché «`0`, `""` e `false` il tipo del parametro li esclude». Vero in quel
punto, dove il parametro è una lista. Poi non ho riverificato l'**altro** `??`
del file, dove il tipo è `number | null` e lo zero esiste eccome: ho trattato una
conclusione locale come una proprietà del modulo. Rilievo riprodotto prima di
accettarlo (sorgente `0`, mutante `"—"`), fixture aggiunta, mutante ora ucciso.

Il reviewer ha inoltre corretto due cifre della doc che avevo scritto senza
ri-misurare a fine lavoro: **194 test** per l'area, non 191, e i due moduli sono
**229/182 righe**, non 225/178. Ri-misurate e corrette — è la quinta volta in
tre giorni che una cifra viene ereditata invece che misurata.

**Fuori perimetro ma da dire**: nel range dei commit rivisti ce n'è uno di
un'altra sessione (`4bce085`, consumi admin) che porta una migration mai
confrontata col DB live. Il reviewer non ha potuto verificarla (l'MCP Supabase
gli nega il permesso). Non è di questa passata, ma è schema che nessuno ha
ancora controllato.

---

## 1/9/2026 — 3ª passata su `(app)/catena/`: gli export Excel, e un buco nell'harness

**Perché una terza passata su un'area dichiarata «chiusa al 90%».** Perché non
lo era. La 2ª passata aveva estratto la logica dei 3 file di *interazione*
(`gruppo-tag-section`, `finestra-costi-gruppo`, `config-assistente-catena`) e
aveva contato come «coperti» anche `finestra-margini-coperti.tsx` e
`finestra-spesa-pv.tsx` perché **importavano già** da `catena-confronti.ts`.
Il criterio era «il file importa da `lib/`», non «la logica del file è in
`lib/`»: dentro `exportXls()` — una funzione `async` dentro un componente React,
dopo un `await import("xlsx")` — restavano ~55 righe che nessun test poteva
raggiungere. Un file può essere coperto per metà e il criterio non se ne accorge.

**Perimetro misurato** (non ereditato): `catena/` è **2.937** righe su 9 file.
Dopo questa passata, **2.723 in 6 file** hanno la logica in `lib/` (**92,7%**).
Le **214 righe scoperte** sono, per file e con la ragione:

| File | Righe | Perché resta scoperto |
|---|---|---|
| `card-segnali.tsx` | 110 | fetch + JSX. L'unica non-JSX è `ICONA`, che mappa a componenti `lucide-react`: non entra in `lib/` senza cambiare forma |
| `page.tsx` | 76 | Server Component `async`. Contiene **due decisioni vere** (`num_pv < 2 → redirect`, `limite_giorno <= 0 → null`) ma sono dopo un `await fetch`: `helpers_ts` non le raggiunge |
| `loading.tsx` | 28 | skeleton, zero logica |

Le due decisioni di `page.tsx` sono l'unico residuo che **vale un test** e non
ce l'ha. Detto qui perché un `92,7%` senza questa riga si legge come «finito».

### Cosa è stato estratto

`apps/web/src/lib/catena-export.ts` (**194 righe**, 12 funzioni + 3 costanti):
la costruzione dei due file Excel. `xlsx` NON entra nel modulo — le funzioni
restituiscono righe e nomi file, il `.tsx` li passa a `json_to_sheet`. Il
confine è voluto: il test misura cosa il cliente legge nelle celle senza montare
la libreria.

**58 test** in `tests/test_catena_export_frontend.py`.

### Il buco nell'harness — il rilievo più importante della passata

Tre test sono falliti con `rc=9` e **stderr vuoto**, un messaggio che sembra un
difetto del modulo sotto test. Non lo era: `esegui_ts` passa l'argomento come
`json.dumps(argomento)` in coda a `node -e <script>`, e `json.dumps(-2.675)`
produce `-2.675`, che **node legge come flag** (`node: bad option: -2.675`).

`helpers_ts.py` era quindi **cieco a ogni argomento negativo scalare**, da
sempre. Nessuno se n'era accorto perché tutti i test esistenti passano oggetti o
liste, che iniziano con `{` o `[`. Un test che avesse provato un importo
negativo — esattamente la fixture che le passate precedenti hanno imposto come
regola — sarebbe fallito in un modo che si legge come «il modulo è rotto».

Corretto alla fonte con `"--"` prima dell'argomento. **Verificato che i 546 test
frontend esistenti restano verdi.** È infrastruttura condivisa da 12 file di
test: il fix vale per tutti quelli futuri.

La lezione: *un harness che non ha mai ricevuto un certo input non è provato su
quell'input, anche se ha 546 test verdi.* Le passate precedenti avevano scritto
la regola «fixture con negativi obbligatorie» ma l'avevano applicata solo dentro
oggetti, dove il bug non si vede.

### Fedeltà dell'estrazione: oracolo, non solo gate

Il gate `git diff -U0 | grep '^+'` è passato su entrambi i `.tsx` (solo import e
chiamate). Ma il gate dimostra che la logica è **uscita**, non che sia
**arrivata intatta** — ed è il rischio dichiarato nel piano.

Prova indipendente: l'espressione originale presa da `git show HEAD:<file>`,
ricostruita come modulo `.mjs` in scratchpad, valutata contro il modulo nuovo
sugli stessi input.

- **Margini**: 734 esiti (120 righe PV × 5 conteggi di incompleti × colonne,
  più note e nomi file su 9 etichette). **0 divergenze.**
- **Pivot**: 200 casi generati, ~2.593 celle. **0 divergenze.**

### Anomalie fotografate (non corrette)

| Dove | Cosa | Perché non ora |
|---|---|---|
| `arrotonda2` | L'arrotondamento sui mezzi centesimi **non è una regola sola**: `1.005 → 1` ma `0.005 → 0.01`; `2.675 → 2.68` ma `-2.675 → -2.67` | È lo stesso calcolo di `righeExportPv` in `catena-tag.ts` e di altri punti dell'app. Correggerlo **qui** darebbe due arrotondamenti diversi per lo stesso importo in due file scaricati lo stesso giorno: peggio dell'errore |
| `rigaTotalePivot` | La `%` della riga TOTALE è la costante `"100%"`, non la somma delle incidenze | Se il backend tronca o esclude righe, le colonne sommano a 99,8% mentre il totale dichiara 100%. Scelta di leggibilità, ma **il numero non è misurato** |
| `rigaExportPivot` | Un PV chiamato «Categoria» sovrascrive la prima colonna | Le chiavi dell'oggetto sono i nomi visualizzati, non gli id. Improbabile, non impossibile: il file uscirebbe muto |

**La causa dell'anomalia di arrotondamento era stata scritta male da me.** Il
primo commento diceva «`Math.round` arrotonda `.5` verso +∞, quindi `-40.005`
dà `-40`». Misurato: dà `-40.01`. La regola di `Math.round` è vera ma non è la
causa — è la rappresentazione binaria (`1.005*100` vale `100.49999…`, quindi non
c'è nessun `.5` da arrotondare). Corretto **sulla misura**, non sulla
supposizione: un commento sbagliato su un'anomalia fotografata è peggio di
nessun commento, perché la sessione che farà il fix lo leggerà come specifica.

Stessa dinamica sul test `test_riga_totale_grand_total_negativo`: avevo asserito
`-5000.56`, il valore vero è `-5000.55`. Aspettativa mia sbagliata, non il
codice — trasformato in un caso di fotografia esplicito.

### Note tecniche riusabili

- **Import a 3 livelli nell'harness funziona**: `catena-export → catena-tag →
  catena-confronti`. Provato con una sonda prima di scrivere i test, non dopo.
- **`import type` inutilizzato non lo segnala `tsc --noEmit`**: `MarginiCoperti`
  era importato e mai usato, e i tipi passavano. Trovato a mano.
- **`slugPeriodo` ha ora 3 chiamanti** in 3 file. Vive in `catena-tag.ts` per
  ragioni storiche. Non spostato (sarebbe refactor fuori scopo), ma dichiarato
  nel sorgente: una quarta copia della regex sarebbe il modo tipico di farle
  divergere.

### `page.tsx` chiuso — e perché non stava in `gruppo.ts`

Il verbale sopra dichiarava `page.tsx` «l'unico residuo che vale un test». È
stato fatto nella stessa sessione invece di rimandarlo: due predicati puri in
`catena-confronti.ts`, 12 test.

```ts
deveRedirigereAPuntoVendita(overview)  // num_pv < 2 → Home del PV
chatCatenaAttiva(config)               // pool AI > 0 → chat visibile
```

La prima decide se un account **vede** la modalità catena, la seconda se vede la
chat AI. Non sono dettagli di rendering.

**Perché non in `gruppo.ts`**, che sarebbe la casa naturale: quel modulo importa
`./worker` con un **path relativo**, e `helpers_ts` riscrive solo l'alias `@/`.
Verificato con una sonda (`ERR_MODULE_NOT_FOUND: Cannot find module
.../lib/worker`), non supposto. `gruppo.ts` **non è eseguibile sotto test**: è
un limite dell'harness da conoscere prima di progettare dove mettere una
funzione.

**`chatCatenaAttiva` è un type predicate** (`config is T`), non un `boolean`.
La condizione inline `!config || !config.enabled || …` restringeva il tipo di
`config`; sostituirla con una funzione che torna `boolean` ha prodotto due
`TS18047: 'config' is possibly null` sul `.tsx`. Il type predicate mantiene la
semantica **e** l'informazione di tipo, così il Server Component resta davvero
senza logica propria invece di guadagnare un `!` o un cast.

Copertura finale dell'area: **2.800/2.938 = 95%**. Le 138 righe residue
(`card-segnali.tsx` 110, `loading.tsx` 28) non contengono logica: fetch, JSX,
skeleton.

### Bilancio di mutazione

**Harness validato sui due lati** all'inizio del giro, non dato per buono dalla
sessione precedente: mutante palese (`return 999999`) **ucciso**, commento
cambiato **sopravvissuto**.

`catena-export.ts`: **33 mutanti, 30 uccisi al primo giro**, poi 31 dopo la
fixture nuova. I 4 casi, indagati uno per uno:

| Mutante | Esito | Perché |
|---|---|---|
| `v == null` → `v === null` | **fixture povera** → chiuso, **riverificato ucciso** | Una colonna assente dal dato dà `undefined`: col mutante **la chiave sparisce dall'oggetto** e le celle slittano rispetto all'header. Nessuna fixture aveva una colonna mancante |
| `=== 1` → `<= 1` in `notaIncompleti` | **equivalenza vera** | Per enumerazione: divergono **solo** su `0.5`, perché la guardia `<= 0` a monte esclude il resto sotto 1. Un conteggio di sedi frazionario non esiste |
| `?? 0` → `?? null` | **equivalenza vera** | `Math.round(null * 100) / 100` vale `0`: output identico |
| `?? 0` → `\|\| 0` | **equivalenza vera** — *diagnosi corretta a posteriori* | L'avevo classificato «fixture povera» e avevo scritto un test per ucciderlo. **La riverifica lo ha trovato ancora vivo.** Misurato dopo: post-`arrotonda2` divergono solo su `-0` (indistinguibile in JSON) e `NaN` (backend rotto). Il test è rimasto perché fissa un comportamento vero, ma la sua docstring ora dice che **non** uccide il mutante |

`catena-confronti.ts` (predicati nuovi): **8 mutanti, 8 uccisi** (validazione
harness inclusa).

**La distinzione che conta**: «sopravvissuto» non è un verdetto, è una domanda —
e la risposta va **misurata, non prevista**. Su E26 avevo previsto «fixture
povera» e scritto la fixture; solo la riverifica ha mostrato che era
un'equivalenza. **Un mutante che scrivi di aver ucciso senza rilanciare l'harness
non è ucciso**: è una supposizione con l'aspetto di un dato.

### Un errore di metodo da non ripetere

Ho lanciato un secondo giro di mutazione mentre il primo era ancora in corso: i
due scrivevano sulla **stessa cartella** `websrc_mut` e si sono scontrati a metà
catalogo (`shutil.Error: [Errno 17] File exists`), perdendo E30–E33. L'harness è
stato reso non-fatale (`dirs_exist_ok`, `rmtree(ignore_errors=True)`), ma la
regola resta: **un giro di mutazione alla volta**. Il rilancio ha completato i 4
mutanti mancanti — tutti uccisi.

### Il reviewer ha mutato il file vero del repo

Durante la review, `git status` ha mostrato `apps/web/src/lib/catena-export.ts`
modificato senza che io lo avessi toccato: `cols.find` → `cols.findLast`, e poco
dopo `"margine_perc"` → `"margine_eur" as keyof …`. Erano **mutanti del
`code-reviewer` montati sul sorgente vero**, non su una copia.

Rischi concreti, entrambi materializzati:
- ho quasi committato un mutante (il primo l'ho intercettato con `git diff`
  prima del commit — HEAD è rimasto integro, verificato riga per riga);
- la suite che stavo eseguendo in parallelo stava misurando **un albero mutato**:
  il risultato è stato scartato e rilanciato su albero pulito. Un «tutto verde»
  raccolto in quella finestra sarebbe stato un dato falso con l'aspetto di una
  prova.

Il reviewer è stato avvisato con le istruzioni dell'harness (copia in scratchpad
+ `-p conftest_mut`) e ha ripristinato da solo. **Non ho ripristinato a metà del
suo giro**: avrebbe falsato il suo esito facendo sopravvivere mutanti che invece
sarebbero morti.

**Regola che vale per chiunque, agente o umano**: durante una review o una
mutazione, `git diff` sul working tree va guardato **prima di ogni commit** — e
un giro di test lanciato mentre qualcun altro muta l'albero non misura il codice
che credi.

### L'harness dei test ora ha i suoi test

Dodici file di test dipendono da `esegui_ts` e **nessuno verificava l'harness**.
È così che il difetto sui negativi è sopravvissuto invisibile.

`tests/test_helpers_ts_harness.py`, 18 test: round-trip dei tipi già in uso
(nessuna regressione), i negativi scalari che prima uccidevano il processo, le
stringhe che *sembrano* flag (`"--help"`, `"-v"`, `"--"`) che devono restare
dati, e le due difese esistenti (`richiede`, modulo inesistente).

**Provato per mutazione, non solo scritto.** Rimuovendo il `"--"` da
`helpers_ts.py` falliscono **esattamente 3 test** — i negativi scalari — mentre
`[-1, -2]` continua a passare, perché una lista inizia con `[`. È precisamente
il motivo per cui il difetto era invisibile: la forma dell'input, non il suo
valore.

Nella docstring c'è l'indicazione che serve a chi lo vedrà fallire: *se questo
test fallisce, il bug non è nel modulo sotto test, è in `subprocess.run` dentro
`esegui_ts`*. Senza quella riga, un rc=9 con stderr vuoto manda a cercare nel
posto sbagliato — come è successo oggi.

### Un invariante che 61 test non coprivano

I test verificavano le righe dell'export una per una, mai il **rapporto fra
righe e header**. Ma `json_to_sheet(rows, { header })` mappa per chiave: se una
riga non ha una chiave dell'header quella cella esce vuota, o il valore finisce
sotto l'intestazione sbagliata.

Due test aggiunti (margini e pivot) che asseriscono
`set(riga.keys()) == set(header)` su riga PV, PV incompleto e riga gruppo
insieme. Il primo usa `COLS` nella **forma reale del `.tsx`**, con `altoMeglio` e
`tooltip` che `ColonnaExport` non dichiara: i test precedenti usavano una `COLS`
ridotta, quindi quella differenza non era coperta.

### Verifica di inerenza (chi altro chiama ciò che ho toccato)

Fatta in entrambe le direzioni, perché una sola non basta:

**In avanti** — ogni simbolo pubblico nuovo ha esattamente il chiamante previsto
(1 ciascuno), tranne `arrotonda2`, usata solo dentro `catena-export.ts` ed
esportata per il test: è un dettaglio implementativo, non un'API.

**All'indietro** — dei nomi spariti dai `.tsx` restano solo `slug` e
`periodoSlug` a zero occorrenze: erano variabili locali, sostituite da
`slugPeriodo` importata. Tutti gli altri (`toRow`, `header`, `rows`,
`gruppoRow`, `totaleRow`, `dimLabel`, `nota`) esistono ancora, riassegnati dalle
chiamate al modulo.

**Contratto pubblico invariato**: i tre `.tsx` toccati avevano 1 `export`
ciascuno prima e ne hanno 1 dopo. Nessuna funzione spostata era esportata,
quindi nessun chiamante esterno può essersi rotto — `sintesi-catena.tsx` importa
solo i due componenti, come prima.

**Nota sul gate di sessione**: l'hook segnalava `services/routers/account.py`
come «path sensibile toccato». Quel file **non è di questa sessione** — è di
`4bce085` (consumi admin, sessione parallela) e non compare in nessuno degli 11
commit di oggi, verificato con `git diff --name-only`. L'hook guarda lo stato
del repo, non l'autore del commit: con più sessioni in parallelo può segnalare
lavoro altrui, e la risposta giusta è verificare **di chi è**, non correre a
rivedere codice che non si è scritto.

### La review: 62 mutanti indipendenti, e una divergenza che il mio oracolo non vedeva

Il `code-reviewer` ha rifatto la mutazione con **62 mutanti propri, 57 uccisi**
(`catena-export` 46/51, i due predicati 11/11). **Nessun suo mutante sopravvive
fuori dal mio catalogo**, e ha confermato tutte e tre le equivalenze che avevo
dichiarato — inclusa la correzione su E26, che avevo sbagliato e poi corretto da
solo. Ha anche fatto un oracolo indipendente: 1698 confronti sui margini, 884
sulla pivot.

**Il rilievo che conta — `notaIncompleti(NaN)`:**

```
notaIncompleti(NaN):  originale → nessuna nota
                      mio       → "…: NaN sedi non hanno…"
```

Riorganizzando la guardia da `if (n > 0) {…}` a `if (n <= 0) return null` avevo
cambiato semantica: **`!(n > 0)` non è `n <= 0` per NaN**. Riprodotto e
corretto ripristinando la forma originale, con un test che la tiene ferma.

**Perché il mio oracolo non l'ha vista.** Generava valori avversari sugli
*importi* (`-0`, `NaN`, `1e9`, `0.1+0.2`) ma sul *conteggio* passava solo
`[0, 1, 2, 5, -1]` — interi plausibili. Il suo generava NaN anche lì. La
lezione: **un oracolo è forte quanto il parametro più trascurato**. Avevo
trattato `n_incompleti` come «un intero, cosa vuoi che succeda» — che è
esattamente il ragionamento che rende un input non testato.

**Dove il reviewer ha sbagliato**, riprodotto prima di rispondere: ha bloccato
su «282 test non corrisponde a nessuna misura», contando 269. Mancavano i **13
di `tag-candidati`**, che è di catena — estratto da `gruppo-tag-section.tsx`
nella 1ª passata. Il 282 è misurato con `--collect-only` e riproducibile.

Ma il rilievo era **utile lo stesso**: la cifra non diceva *cosa* contava, e per
questo due lettori indipendenti hanno ottenuto due numeri. Ora gli addendi sono
espliciti in `AUDIT_COPERTURA.md` (95+61+50+63+13), con detto perché i 18
dell'harness restano fuori. **Un numero giusto che nessuno può ricostruire è
fragile quanto uno sbagliato.**

Corretta anche una frase del commento su `arrotonda2` («dipende dal valore, non
dal segno»): misurato, sono **due passaggi** — il valore decide se il prodotto
cade su un `.5` esatto (`2.675*100` = `267.5` esatto, `1.005*100` =
`100.49999…`), e *se* c'è, il segno decide il verso. Per questo `2.675 → 2.68`
ma `-2.675 → -2.67`, mentre `1.005` e `-1.005` danno entrambi `1`.

---

## 1/9/2026 — I due bug fotografati, corretti su richiesta dell'owner

Mattia ha chiesto di chiuderli invece di rimandarli. Entrambi erano stati
classificati durante l'audit; **entrambi erano peggio della classificazione**.

### Il bug dell'importo italiano: 60 punti, non ~25

Il verbale della 2ª passata diceva «~25 punti dell'app». Misurato:
**60 occorrenze** in 16 file. E la forma non era una sola:

| Forma | Su `"1.234,56"` | Effetto |
|---|---|---|
| `Number(t.replace(",", "."))` | `NaN` | respinto, l'utente vede un errore |
| `parseFloat(t.replace(",", "."))` | **`1.234`** | **nessun errore**: entra nel dato |

**`parseFloat` è peggio di `Number`**, ed è la forma usata in
`carica-ricavi-dialog.tsx` — 27 occorrenze, i **ricavi**, il numeratore del MOL.
Un fatturato di 1.234,56 € veniva salvato come 1,23 €. Silenziosamente.

Il caso più insidioso resta `"1.234"` senza decimali: `1.234` supera la guardia
`importo > 0` e viene scritto. Un costo di 1.234 € diventa 1,23 €.

**Il fix non è una funzione, sono due.** Il punto non significa la stessa cosa
in tutti i campi:

- `parseNumeroIt` — **importi**: `"1.234"` = milleduecentotrentaquattro. Regola
  dell'ultimo gruppo di 3 cifre, la stessa di Excel in locale italiano.
- `parseDecimaleIt` — **ore, percentuali, costi orari**: `"33.333"` = 33,333.
  Applicare qui la regola delle migliaia darebbe un valore **mille volte più
  grande**: una percentuale di ripartizione a 33333.

Tutti i 58 punti classificati uno per uno. I placeholder del costo orario
(`"es. 12,50"`, `"es. 15,00"`) confermano che lì le migliaia non esistono: è la
prova che il campo, non l'intuizione, decide quale variante usare.

**Guardia aggiunta oltre il richiesto**: `Number()` accetta `"0x10"` (=16),
`"1e3"` (=1000) e `"Infinity"`. Nessuno li digita in un campo importo, ma
passavano — e un `"Infinity"` supera `importo > 0` e finisce in un POST.
`FORMA_NUMERICA` (`/^[+-]?[\d.,]+$/`) li respinge.

### L'arrotondamento

Ora il mezzo centesimo **sale sempre** ed è **simmetrico**: `2.675 → 2.68` e
`-2.675 → -2.68`. Prima erano due regole diverse a seconda del valore e del
segno (`1.005 → 1` per la rappresentazione binaria, `-2.675 → -2.67` perché su
`-267.5` esatto `Math.round` va verso +∞).

Il fix usa la notazione esponenziale (`Number(\`${x}e+2\`)`) per spostare il
punto senza moltiplicare, e arrotonda il valore assoluto riapplicando il segno.

### Prova

**47 test nuovi** su `format.ts`. **Mutazione 15/16**: l'unico sopravvissuto
(`centesimi/100` al posto di `` `${centesimi}e-2` ``) è **equivalenza vera** —
verificato su 57.000 centesimi interi, 0 divergenze: dopo `Math.round` il valore
è già intero, e dividere un intero per 100 non introduce l'errore che nasce
moltiplicando un decimale. Documentato nel sorgente invece che zittito.

I test che fotografavano le anomalie sono stati **riscritti, non cancellati**:
`test_fotografa_separatore_migliaia_produce_nan` è diventato
`test_separatore_migliaia_ora_funziona`, e ne è nato uno nuovo —
`test_la_vecchia_forma_sarebbe_una_regressione` — che tiene fermo che la vecchia
forma sbagliava. Serve perché `replace(",", ".")` era il pattern più diffuso
dell'app: chi lo incontrasse altrove potrebbe "uniformare" all'indietro.

### Inerenze del fix sui numeri, e perché il frontend era l'unica difesa

**In avanti**: `format.ts` è stato modificato in modo **puramente additivo** —
nessuna riga rimossa, verificato col diff. I 20 file che già lo importavano non
possono essersi rotti.

**All'indietro**: 17 file hanno cambiato comportamento, e in **11 punti** il
valore parsato finisce direttamente in un `POST`/`PUT`. Sono i posti dove un
errore di classificazione non è un fastidio ma un dato sbagliato permanente.

**Il backend non fa da rete.** `RicavoGiornalieroItem` dichiara
`fatturato_iva10: float = 0.0` senza `ge`/`le`, e i router leggono
`float(r.get("fatturato_iva10") or 0)`. Un fatturato di **1,23 €** al posto di
1.234,56 € sarebbe stato accettato senza un'obiezione, sommato nel MOL e
mostrato al cliente come suo.

È il motivo per cui questo bug era grave e non cosmetico: **l'unica difesa era
il parser del frontend**, e sbagliava.

### Un terzo bug, trovato mentre si verificava il secondo

`−1.234,56` con il **meno unicode** (U+2212) dava NaN. È il carattere che Word,
Excel e i PDF usano al posto del trattino: chi **incolla** un importo negativo —
la forma tipica di una nota di credito — si vedeva rifiutare il valore con il
solito messaggio sui campi mancanti.

Trovato provando gli importi negativi *con separatore di migliaia*, che è la
combinazione realistica. Normalizzati anche en dash e em dash, che i correttori
automatici inseriscono da soli.

**La lezione**: i due bug erano stati classificati leggendo il codice. Il terzo
si è visto solo generando input nella forma in cui arrivano davvero — copiati,
non digitati.

### Un campo che cambia natura a runtime — il difetto introdotto dal fix stesso

Ricontrollando a mano le 58 chiamate del fix (non per un test: **nessun test
copriva quel campo**), ho trovato che in `margini/analisi-tab.tsx` lo split del
food cost si compila **in euro o in percentuale**, con un interruttore a
schermo. Avevo applicato la variante «importi» a entrambe le modalità:

```
mode === "perc",  netto 50.000 €
  "33.333"  →  33333  →  (33333/100)*50000  =  16.666.500 €
  atteso                                        16.666 €
```

Mille volte tanto, scritto nel food cost **senza nessun errore visibile**.

**Perché non si era visto**: la variabile si chiama `raw`, il campo sembra un
importo come gli altri, `tsc` non ha niente da dire e la suite non lo tocca. Il
criterio che avevo dichiarato — «guarda il placeholder e dove finisce il
valore» — funziona solo se il campo ha **una** natura. Qui ne ha due, e la
sceglie l'utente premendo un bottone.

Fix: la variante dipende da `mode`. Verificato con un grep che è l'unico punto
dell'app con questa forma (le altre occorrenze di `mode === "perc"` sono
rendering).

**La lezione vera è sul metodo, non sul campo**: un fix applicato a 58 punti
con una sostituzione automatica va **riletto punto per punto**, perché la regola
che li accomuna è sintattica mentre quella che li distingue è semantica. La
sostituzione ha fatto la prima; solo la rilettura trova la seconda.

### La review del fix: una regressione mia, e il criterio sbagliato

Il `code-reviewer` ha bloccato con **3 rilievi, tutti fondati**. Il primo è una
**regressione che avevo introdotto io**, sullo stesso campo che il fix voleva
proteggere.

**Il criterio che avevo usato era sbagliato.** Avevo classificato i campi
chiedendomi *«che grandezza è?»* (un importo può superare il migliaio, una
percentuale no). La domanda giusta è *«che input è?»*:

| Input | Cosa garantisce | Variante |
|---|---|---|
| `type="number"` | Per spec HTML `e.target.value` è sempre un *valid floating-point number*: **punto decimale, mai virgola, mai migliaia**. La virgola la normalizza il browser | `parseDecimaleIt` |
| `type="text"` | testo libero: l'italiano ci scrive `1.700` | `parseNumeroIt` |

**La regressione (B1).** I 27 campi di `carica-ricavi-dialog.tsx` sono
`type="number"`. Ma il difetto vero non è l'utente che digita — è **il valore
ricaricato dal DB**:

`ricavi_modalita_mensile.fatturato_iva10` è `numeric(12,4)` e il write path non
arrotonda (`routers/ricavi.py:1463`), e c'è chi la alimenta a 4 decimali
(`ricavi.py:737`, import Passbi). Un valore a 3 decimali → `String()` →
`"12345.678"` → la regola delle migliaia → **12345678**.

```
apri "Carica ricavi" su un mese in modalità mensile
→ Salva senza toccare nulla
→ il fatturato viene ri-salvato ×1000, e passa `float(x)` senza errori
```

Prima del mio fix non succedeva: `parseFloat("12345.678")` dava `12345.678`.
**Ho rotto il campo che volevo proteggere.**

**B2** — stessa causa in `calcolo-tab.tsx` (le celle del MOL) e in
`analisi-tab.tsx`, dove avevo corretto solo la modalità `%`: anche quella euro è
`type="number"`, quindi il ramo condizionale sparisce e resta una sola variante.

**B3** — `numOr0` in `personale-tab.tsx`/`mobile-turni.tsx` serviva **quattro**
campi, non due: ore *e* lordo mensile, che sono grandezze diverse in campi
`type="text"`. Un `"1.700"` di stipendio valeva **1,7 €**, e finiva in
`lordo_mensile` → letto dal MOL. Questo **non era una regressione**: era il bug
originale, che il mio fix non aveva corretto perché l'helper condiviso rendeva
la regola inapplicabile.

**Lacune di test misurate dal reviewer**: le quattro varianti `*OZero` — quelle
usate in tutti i 27 campi dei ricavi — **non erano coperte da nessun test**. Si
poteva farle ritornare NaN, invertirne i rami o farle delegare alla funzione
sbagliata con la suite verde. 27 test aggiunti; i mutanti ora muoiono.

**Contestata una mia dichiarazione**: `centesimi/100` ≡ `` `${centesimi}e-2` ``
non è «equivalenza vera» ma «equivalente **nel dominio degli importi**». Per
`|n| >= 1e19` il template diventa notazione esponenziale e `Number("1e+21e-2")`
è `NaN`. Irraggiungibile con euro veri, ma la formulazione era troppo forte.

**Punto E, il timore che aveva motivato il rinvio del fix**: verificato che
**non si concretizza**. `arrotonda2` e `righeExportPv` ricevono entrambi valori
già arrotondati a 2 decimali dal backend (`gruppo.py:1066-1079` e `:2269`), e su
500.000 valori a 2 decimali le due forme danno 0 divergenze. I due arrotondamenti
divergerebbero solo su input a 3 decimali, che non arrivano a nessuno dei due.

**La lezione di metodo**: una sostituzione automatica su 58 punti applica una
regola **sintattica**; quella che distingue i casi è **semantica**. Rileggendo a
mano ho trovato 1 difetto (il dual-mode), il reviewer ne ha trovati altri 3 —
e il più grave veniva da un percorso che nessuno dei due aveva pensato a
guardare: non l'input dell'utente, ma il round-trip col database.
