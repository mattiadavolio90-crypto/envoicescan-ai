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
